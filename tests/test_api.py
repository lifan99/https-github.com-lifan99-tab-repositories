"""HTTP API 离线回归：用 ASGI 内存传输覆盖契约、准入、错误映射及应用生命周期。"""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest

from review_system.api import create_app
from review_system.clients import AsyncOpenAICompatibleClient, LLMError
from review_system.config import Settings
from review_system.fakes import DemoClient

SETTINGS = Settings("fake", "https://example.invalid/v1", "synthetic-key", "m", "a", "c", "j")
BODY = {"request_id": "test-id", "original_input": " 原文\n", "review_mode": "logic"}


class RecordingClient(DemoClient):
    """记录实际角色模型及解析后的上下文，并复用固定演示答案。"""
    def __init__(self):
        self.calls = []

    async def complete(self, *, model, messages):
        self.calls.append((model, json.loads(messages[1]["content"])))
        return await super().complete(model=model, messages=messages)


def run_api(operation, *, model_client=None, settings=SETTINGS):
    """显式进入应用生命周期，用内存 ASGI 客户端运行场景，并检查关闭前任务已清空。"""
    async def scenario():
        model = model_client or RecordingClient()
        lifetime = []

        @asynccontextmanager
        async def resources():
            lifetime.append("opened")
            try:
                yield "fake", model, settings
            finally:
                assert app.state.service.active_count == app.state.service.task_count == 0
                lifetime.append("closed")

        app = create_app(resources_factory=resources)
        async with asyncio.timeout(5):
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app, raise_app_exceptions=False), base_url="http://test",
                ) as http:
                    await operation(http, model, app)
        assert lifetime == ["opened", "closed"]
    asyncio.run(scenario())


def test_health_success_contract_context_and_completed_id_reuse():
    """验证健康响应、三阶段成功契约及已完成请求标识可重新执行。"""
    async def operation(http, model, app):
        assert (await http.get("/healthz")).json() == {"status": "ok", "execution_mode": "fake"}
        assert not model.calls
        first = await http.post("/api/v1/reviews", json=BODY)
        assert first.status_code == 201
        value = first.json()
        assert set(value) == {"request_id", "review_id", "execution_mode", "status", "responses", "stages", "final_review", "error"}
        UUID(value["review_id"])
        assert value["request_id"] == BODY["request_id"]
        assert value["execution_mode"] == "fake"
        assert value["error"] is None
        assert value["final_review"]["verdict"] == "insufficient_evidence"
        assert len(value["responses"]) == len(value["stages"]) == 3
        assert [model for model, _ in model.calls] == ["a", "c", "j"]
        assert all(context["original_input"] == BODY["original_input"] for _, context in model.calls)
        assert "analyst_output" in model.calls[1][1]
        assert "critic_output" in model.calls[2][1]
        assert "original_input" not in value
        second = await http.post("/api/v1/reviews", json=BODY)
        assert second.status_code == 201
        assert second.json()["review_id"] != value["review_id"]
        assert len(model.calls) == 6
        spec = (await http.get("/openapi.json")).json()
        assert set(spec["paths"]["/api/v1/reviews"]["post"]["responses"]) == {"201", "409", "422", "429", "500", "502", "503", "504"}
        assert (await http.get("/missing")).status_code == 404
        assert (await http.get("/api/v1/reviews")).status_code == 405
    run_api(operation)


@pytest.mark.parametrize("body", [
    {}, [], None, {**BODY, "request_id": ""}, {**BODY, "request_id": "x" * 65},
    {**BODY, "request_id": "中文"}, {**BODY, "request_id": "has space"}, {**BODY, "request_id": 12},
    {**BODY, "request_id": "id\n"}, {**BODY, "original_input": " \n"}, {**BODY, "original_input": 42},
    {**BODY, "original_input": "x" * 20001}, {**BODY, "original_input": False},
    {**BODY, "review_mode": "unknown"}, {**BODY, "review_mode": []},
    {**BODY, "api_key": "private-key"}, {**BODY, "execution_mode": "live"},
])
def test_invalid_requests_return_safe_422_and_make_no_calls(body):
    """非法正文返回固定 422 错误，不调用模型，也不暴露输入内容。"""
    async def operation(http, model, app):
        response = await http.post("/api/v1/reviews", json=body)
        assert response.status_code == 422
        value = response.json()
        assert value["error"]["code"] == "invalid_request"
        assert value["request_id"] is value["review_id"] is value["final_review"] is None
        assert value["responses"] == value["stages"] == []
        assert "private-key" not in response.text and BODY["original_input"] not in response.text
        assert not model.calls
    run_api(operation)


@pytest.mark.parametrize("content", [b'{"private":', b'\xff', b'null'])
def test_invalid_json_is_sanitized(content):
    """非法 JSON 统一转为公开请求错误，不泄露正文。"""
    async def operation(http, model, app):
        response = await http.post("/api/v1/reviews", content=content, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request"
        assert "private" not in response.text
        assert not model.calls
    run_api(operation)


@pytest.mark.parametrize("code,status", [("model_error", 502), ("network_timeout", 504), ("model_timeout", 504), ("total_timeout", 504)])
def test_workflow_error_mapping_keeps_partial_results_and_hides_exception(code, status):
    """工作流错误映射为对应 HTTP 状态，同时保留部分结果并隐藏异常正文。"""
    class Failing(RecordingClient):
        async def complete(self, *, model, messages):
            if model == "c":
                raise LLMError("private-provider-body-and-key", code=code)
            return await super().complete(model=model, messages=messages)

    async def operation(http, model, app):
        response = await http.post("/api/v1/reviews", json=BODY)
        assert response.status_code == status
        value = response.json()
        assert value["error"]["code"] == code
        assert value["error"]["stage"] == "Critic"
        assert value["review_id"] and value["status"] == "failed"
        assert [item["agent"] for item in value["responses"]] == ["Analyst"]
        assert [item["status"] for item in value["stages"]] == ["succeeded", "failed", "skipped"]
        assert value["final_review"] is None
        assert "private-provider" not in response.text
        assert app.state.service.active_count == 0
    run_api(operation, model_client=Failing())


@pytest.mark.parametrize("judge", ['not JSON', '{"summary": "missing fields"}', json.dumps({
    "summary": "s", "verdict": "needs_revision", "limitations": [], "findings": [{
        "category": "logic", "severity": "high", "message": "m", "suggestion": "s",
        "start": 0, "end": 1, "quote": "wrong",
    }],
})])
def test_invalid_judge_only_exposes_raw_output_in_failed_stage(judge):
    """非法 Judge 回答只保留在失败阶段，不发布为最终报告。"""
    class BadJudge(RecordingClient):
        async def complete(self, *, model, messages):
            if model == "j":
                return judge
            return await super().complete(model=model, messages=messages)

    async def operation(http, model, app):
        response = await http.post("/api/v1/reviews", json=BODY)
        assert response.status_code == 502
        value = response.json()
        assert value["error"]["code"] == "invalid_output"
        assert value["error"]["stage"] == "Judge"
        assert len(value["responses"]) == 2
        assert value["stages"][2]["raw_output"] == judge
        assert value["stages"][2]["status"] == "failed"
        assert value["final_review"] is None
    run_api(operation, model_client=BadJudge())


@pytest.mark.parametrize("model_budget,total_budget,code", [(0.02, 5, "model_timeout"), (5, 0.02, "total_timeout")])
def test_real_budget_expiry_through_route(model_budget, total_budget, code):
    """通过完整路由触发真实预算超时，检查公开错误码及部分结果。"""
    class Waiting(RecordingClient):
        async def complete(self, *, model, messages):
            if model == "c":
                await asyncio.Event().wait()
            return await super().complete(model=model, messages=messages)

    async def operation(http, model, app):
        response = await http.post("/api/v1/reviews", json=BODY)
        assert response.status_code == 504
        assert response.json()["error"]["code"] == code
        assert len(response.json()["responses"]) == 1
        assert app.state.service.active_count == app.state.service.task_count == 0
    run_api(operation, model_client=Waiting(), settings=replace(SETTINGS, model_timeout_seconds=model_budget, total_timeout_seconds=total_budget))


@pytest.mark.parametrize("status", [401, 429, 503])
def test_upstream_http_status_is_502_not_local_429(status):
    """供应商 HTTP 错误映射为 502，区别于本地容量满载的 429。"""
    async def scenario():
        calls = []

        def handle(request):
            calls.append(request)
            return httpx.Response(status, text="private-upstream-body")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as upstream:
            @asynccontextmanager
            async def resources():
                yield "live", AsyncOpenAICompatibleClient(SETTINGS, upstream), SETTINGS
            app = create_app(resources_factory=resources)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as http:
                    response = await http.post("/api/v1/reviews", json=BODY)
                    assert response.status_code == 502
                    assert response.json()["error"]["code"] == "model_error"
                    assert response.json()["execution_mode"] == "live"
                    assert "private-upstream" not in response.text
                    assert len(calls) == 1
                    assert not upstream.is_closed
    asyncio.run(scenario())


def test_http_admission_cancellation_peer_isolation_and_recovery():
    """验证 HTTP 准入去重、容量限制、取消隔离及释放后的恢复。"""
    async def scenario():
        entered = {name: asyncio.Event() for name in ("R1", "R2")}
        released = {name: asyncio.Event() for name in entered}
        cleaned = {name: asyncio.Event() for name in entered}
        calls = []

        class Waiting(DemoClient):
            async def complete(self, *, model, messages):
                original = json.loads(messages[1]["content"])["original_input"]
                calls.append((original, model))
                if model == "a" and original in entered:
                    entered[original].set()
                    try:
                        await released[original].wait()
                    finally:
                        cleaned[original].set()
                return await super().complete(model=model, messages=messages)

        @asynccontextmanager
        async def resources():
            yield "fake", Waiting(), SETTINGS
            assert app.state.service.active_count == app.state.service.task_count == 0

        app = create_app(resources_factory=resources)
        async with asyncio.timeout(5), app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as http:
                def post(name):
                    return http.post("/api/v1/reviews", json={"request_id": name, "original_input": name})

                tasks = [asyncio.create_task(post(name)) for name in entered]
                try:
                    await entered["R1"].wait()
                    await entered["R2"].wait()
                    for name, status, code in [("R1", 409, "duplicate_request"), ("R3", 429, "capacity_exceeded")]:
                        response = await post(name)
                        assert response.status_code == status
                        body = response.json()
                        assert body["error"]["code"] == code
                        assert body["status"] == "rejected" and body["review_id"] is None
                        assert body["responses"] == body["stages"] == []
                        assert len(calls) == 2
                    tasks[0].cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await tasks[0]
                    assert cleaned["R1"].is_set()
                    assert (await post("R3")).status_code == 201
                    released["R2"].set()
                    assert (await tasks[1]).status_code == 201
                    await app.state.service.aclose()
                    response = await post("R4")
                    assert response.status_code == 503
                    assert response.json()["error"]["code"] == "service_unavailable"
                    assert not any(name == "R4" for name, _ in calls)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.run(scenario())


def test_lifespan_waits_for_live_http_cleanup_before_closing_shared_client():
    """应用退出先收集模型请求任务，再关闭共享 HTTP 客户端。"""
    async def scenario():
        entered = asyncio.Event()
        events = []

        async def transport(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                assert not upstream.is_closed
                events.append("request-cleaned")

        upstream = httpx.AsyncClient(transport=httpx.MockTransport(transport))

        @asynccontextmanager
        async def resources():
            async with upstream:
                yield "live", AsyncOpenAICompatibleClient(SETTINGS, upstream), SETTINGS
                assert app.state.service.active_count == 0
                assert events == ["request-cleaned"]
            events.append("client-closed")

        app = create_app(resources_factory=resources)
        async with asyncio.timeout(5):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as http:
                async with app.router.lifespan_context(app):
                    task = asyncio.create_task(http.post("/api/v1/reviews", json=BODY))
                    await entered.wait()
                with pytest.raises(asyncio.CancelledError):
                    await task
        assert upstream.is_closed
        assert events == ["request-cleaned", "client-closed"]
    asyncio.run(scenario())


@pytest.mark.parametrize("defect", ["core", "response", "error_response"])
def test_internal_defects_return_safe_500_not_input_or_provider_error(defect):
    """内部缺陷返回通用 500，不误归类为请求或供应商错误。"""
    async def operation(http, model, app):
        if defect == "core":
            target = "review_system.service.run_review_async"
        elif defect == "response":
            target = "review_system.api.ReportDTO.model_validate"
        else:
            # 先制造准入失败，再让错误响应模型构造失败，以覆盖未预期异常的处理。
            await app.state.service.aclose()
            target = "review_system.api.StageDTO.model_validate"
        if defect == "error_response":
            from review_system.api_models import FailureResponse
            constructor = FailureResponse
            calls = 0

            def fail_once(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise ValueError("private-response-contract-defect")
                return constructor(*args, **kwargs)

            with patch("review_system.api.FailureResponse", side_effect=fail_once):
                response = await http.post("/api/v1/reviews", json=BODY)
        else:
            with patch(target, side_effect=ValueError("private-internal-defect")):
                response = await http.post("/api/v1/reviews", json=BODY)
        assert response.status_code == 500
        value = response.json()
        assert value["error"]["code"] == "internal_error"
        assert value["final_review"] is None
        assert "private-" not in response.text
        assert app.state.service.active_count == 0
    run_api(operation)


@pytest.mark.parametrize("mode", [None, "live", "invalid"])
def test_invalid_live_startup_is_explicit_and_never_falls_back_to_fake(mode):
    """真实模式配置非法时明确启动失败，不自动降级为演示模式。"""
    async def scenario():
        env = {} if mode is None else {"REVIEW_EXECUTION_MODE": mode}
        with patch("review_system.api.load_project_env") as load, patch.dict("os.environ", env, clear=True), patch("review_system.api.create_http_client") as create:
            app = create_app()
            load.assert_not_called()
            with pytest.raises(ValueError):
                async with app.router.lifespan_context(app):
                    pytest.fail("Invalid live configuration must not start.")
            load.assert_called_once()
            create.assert_not_called()
    asyncio.run(scenario())


def test_explicit_fake_startup_ignores_credentials_and_never_creates_http_transport():
    """显式 fake 模式无需模型凭据，也不创建真实模型传输。"""
    async def scenario():
        with patch("review_system.api.load_project_env"), patch.dict("os.environ", {"REVIEW_EXECUTION_MODE": "fake"}, clear=True), patch("review_system.api.create_http_client") as create:
            app = create_app()
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as http:
                    assert (await http.get("/healthz")).json()["execution_mode"] == "fake"
                    result = await http.post("/api/v1/reviews", json=BODY)
                    assert result.status_code == 201
                    assert result.json()["execution_mode"] == "fake"
            create.assert_not_called()
    asyncio.run(scenario())


def test_independent_apps_do_not_share_closing_or_admission_state():
    """不同应用实例分别持有关闭和准入状态，互不影响。"""
    async def scenario():
        @asynccontextmanager
        async def resources():
            yield "fake", RecordingClient(), SETTINGS

        first, second = create_app(resources_factory=resources), create_app(resources_factory=resources)
        async with first.router.lifespan_context(first), second.router.lifespan_context(second):
            assert first.state.service is not second.state.service
            await first.state.service.aclose()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(second), base_url="http://test") as http:
                assert (await http.post("/api/v1/reviews", json=BODY)).status_code == 201
    asyncio.run(scenario())
