"""服务准入回归：用事件控制并发时序，验证去重、容量恢复、任务收集和截止时间传递。"""

import asyncio
import json
from unittest.mock import patch

import pytest

from review_system.clients import LLMError
from review_system.config import Settings
from review_system.fakes import DemoClient
from review_system.service import ReviewService, ServiceError

SETTINGS = Settings("fake", "https://example.invalid", "", "m", "a", "c", "j")


def execute(scenario):
    """为异步服务场景添加总等待上限，避免并发测试死锁。"""
    async def bounded():
        async with asyncio.timeout(5):
            await scenario()
    asyncio.run(bounded())


class ControlledClient(DemoClient):
    """用独立事件控制每份审核的开始、放行和清理，精确验证并发时序。"""
    def __init__(self):
        self.entered = {name: asyncio.Event() for name in ("R1", "R2", "R3")}
        self.release = {name: asyncio.Event() for name in self.entered}
        self.cleaned = {name: asyncio.Event() for name in self.entered}
        self.calls = []
        self.fail = set()

    async def complete(self, *, model, messages):
        name = json.loads(messages[1]["content"])["original_input"]
        self.calls.append((name, model))
        if model == "a":
            self.entered[name].set()
            try:
                await self.release[name].wait()
                if name in self.fail:
                    raise LLMError("private provider error")
            finally:
                self.cleaned[name].set()
        return await super().complete(model=model, messages=messages)


def test_admission_conflict_capacity_cancel_recovery_and_reuse():
    """检查重复标识优先、满载拒绝、取消后恢复及已完成标识复用。"""
    async def scenario():
        client = ControlledClient()
        service = ReviewService(client, SETTINGS)
        first = asyncio.create_task(service.review("id1", "R1"))
        second = asyncio.create_task(service.review("id2", "R2"))
        try:
            await client.entered["R1"].wait()
            await client.entered["R2"].wait()
            assert service.active_count == 2
            for identifier, expected in [("id1", "duplicate_request"), ("id3", "capacity_exceeded")]:
                with pytest.raises(ServiceError) as caught:
                    await service.review(identifier, "R3")
                assert caught.value.code == expected
                assert caught.value.review_id is None
                assert len(client.calls) == 2
                assert service.active_count == 2
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert client.cleaned["R1"].is_set()
            assert service.active_count == 1
            client.release["R3"].set()
            third = await service.review("id3", "R3")
            assert third.result.record.status == "succeeded"
            client.release["R2"].set()
            result = await second
            again = await service.review("id2", "R2")
            assert result.review_id != again.review_id
            assert service.active_count == service.task_count == 0
            assert [model for name, model in client.calls if name == "R1"] == ["a"]
            assert [model for name, model in client.calls if name == "R2"] == ["a", "c", "j"] * 2
        finally:
            await service.aclose()
            await asyncio.gather(first, second, return_exceptions=True)
    execute(scenario)


def test_failure_releases_own_id_without_interrupting_peer():
    """失败只释放本次标识和名额，不影响其他审核。"""
    async def scenario():
        client = ControlledClient()
        client.fail.add("R1")
        service = ReviewService(client, SETTINGS)
        tasks = [asyncio.create_task(service.review(name, name)) for name in ("R1", "R2")]
        try:
            await client.entered["R1"].wait()
            await client.entered["R2"].wait()
            client.release["R1"].set()
            with pytest.raises(ServiceError) as caught:
                await tasks[0]
            assert caught.value.code == "model_error"
            assert caught.value.review_id
            assert caught.value.run.record.final_review is None
            assert service.active_count == 1
            client.fail.clear()
            assert (await service.review("R1", "R1")).result.record.status == "succeeded"
            client.release["R2"].set()
            assert (await tasks[1]).result.record.status == "succeeded"
        finally:
            await service.aclose()
            await asyncio.gather(*tasks, return_exceptions=True)
    execute(scenario)


@pytest.mark.parametrize("error", [RuntimeError("private-log-error"), asyncio.CancelledError()])
def test_admission_event_failure_releases_id_and_preserves_peer(error):
    """准入后的事件记录异常或取消也释放登记，不中断独立审核。"""
    async def scenario():
        client = ControlledClient()
        service = ReviewService(client, SETTINGS)
        peer = asyncio.create_task(service.review("id2", "R2"))
        try:
            await client.entered["R2"].wait()
            expected = asyncio.CancelledError if isinstance(error, asyncio.CancelledError) else ServiceError
            with patch("review_system.service.log_event", side_effect=[error, None]):
                with pytest.raises(expected) as caught:
                    await service.review("id1", "R1")
            if isinstance(caught.value, ServiceError):
                assert caught.value.code == "internal_error"
                assert caught.value.__cause__ is error
            assert service.active_count == service.task_count == 1
            assert client.calls == [("R2", "a")]
            assert not peer.done()
            client.release["R1"].set()
            assert (await service.review("id1", "R1")).result.record.status == "succeeded"
            client.release["R2"].set()
            assert (await peer).result.record.status == "succeeded"
            assert service.active_count == service.task_count == 0
        finally:
            await service.aclose()
            await asyncio.gather(peer, return_exceptions=True)
    execute(scenario)


def test_close_collects_tasks_before_resource_owner_closes_client():
    """关闭服务先等待子任务清理，且后续新请求被拒绝。"""
    async def scenario():
        client = ControlledClient()
        service = ReviewService(client, SETTINGS)
        parent = asyncio.create_task(service.review("id1", "R1"))
        await client.entered["R1"].wait()
        await service.aclose()
        assert client.cleaned["R1"].is_set()
        with pytest.raises(asyncio.CancelledError):
            await parent
        assert service.active_count == service.task_count == 0
        with pytest.raises(ServiceError, match="service_unavailable"):
            await service.review("new", "R3")
        assert len(client.calls) == 1
        await service.aclose()
    execute(scenario)


def test_parent_cancel_before_child_starts_leaves_no_registration():
    """父任务在子任务第一步前被取消，也不残留任务或活动标识。"""
    async def scenario():
        client = ControlledClient()
        service = ReviewService(client, SETTINGS)
        parent = asyncio.create_task(service.review("id1", "R1"))
        # 父任务创建子任务后，这个回调会先取消父任务；
        # 此时子任务尚未获得第一次执行机会，用于覆盖最早发生的取消。
        asyncio.get_running_loop().call_soon(parent.cancel)
        with pytest.raises(asyncio.CancelledError):
            await parent
        assert service.active_count == service.task_count == 0
        assert not client.calls
        client.release["R1"].set()
        assert (await service.review("id1", "R1")).result.record.status == "succeeded"
        await service.aclose()
    execute(scenario)


def test_service_passes_original_deadline_through_scheduling_delay():
    """调度延迟计入原始总预算，不因子任务稍后开始而延长。"""
    async def scenario():
        settings = Settings("fake", "https://example.invalid", "", "m", "a", "c", "j", total_timeout_seconds=0.01)
        client = ControlledClient()
        service = ReviewService(client, settings)
        execute_review = service._execute

        async def delayed(*args):
            await asyncio.sleep(0.02)
            return await execute_review(*args)

        with patch.object(service, "_execute", delayed):
            with pytest.raises(ServiceError) as caught:
                await service.review("id1", "R1")
        assert caught.value.code == "total_timeout"
        assert all(stage.status == "skipped" for stage in caught.value.run.record.stages)
        assert not client.calls
        assert service.active_count == service.task_count == 0
    execute(scenario)


@pytest.mark.parametrize("identifier", ["", "has space", "非ASCII", "x" * 65, 1, None, "a\n"])
def test_invalid_service_id_never_calls_model(identifier):
    """非法请求标识在创建模型调用或活动登记前被拒绝。"""
    async def scenario():
        client = ControlledClient()
        service = ReviewService(client, SETTINGS)
        with pytest.raises(ValueError):
            await service.review(identifier, "R1")
        assert not client.calls
        assert service.active_count == service.task_count == 0
    execute(scenario)
