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
    async def bounded():
        async with asyncio.timeout(5):
            await scenario()
    asyncio.run(bounded())


class ControlledClient(DemoClient):
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


def test_close_collects_tasks_before_resource_owner_closes_client():
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
    async def scenario():
        client = ControlledClient()
        service = ReviewService(client, SETTINGS)
        parent = asyncio.create_task(service.review("id1", "R1"))
        # The parent schedules its child, then this callback cancels the parent
        # before the child gets its first event-loop step.
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
    async def scenario():
        client = ControlledClient()
        service = ReviewService(client, SETTINGS)
        with pytest.raises(ValueError):
            await service.review(identifier, "R1")
        assert not client.calls
        assert service.active_count == service.task_count == 0
    execute(scenario)
