import asyncio
import json
import os
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from streamlit.testing.v1 import AppTest

from review_system.api import create_app
from review_system.api_client import APIClientError
from review_system.api_models import ErrorDTO, FailureResponse
from review_system.clients import AsyncOpenAICompatibleClient
from review_system.config import Settings
from review_system.environment import PROJECT_ROOT
from review_system.workflow import MAX_INPUT_CHARS

JUDGE_TEXT = json.dumps({
    "summary": "Synthetic report", "verdict": "pass", "findings": [],
    "limitations": ["No external verification."],
})


def chat_response(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@contextmanager
def fake_provider(replies, *, mode="live"):
    # UI makes an HTTP request. The mock transport forwards it through real API
    # routes, service and workflow; only the provider boundary supplies fake data.
    send = Mock(side_effect=replies)
    send.api_requests = []
    clients = []
    real_client = httpx.Client
    settings = Settings("qwen", "https://example.invalid/v1", "synthetic", "m", "a", "c", "j")

    def handle(request):
        send.api_requests.append(request)

        async def invoke():
            @asynccontextmanager
            async def resources():
                async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as upstream:
                    clients.append(upstream)
                    yield mode, AsyncOpenAICompatibleClient(settings, upstream), settings

            api = create_app(resources_factory=resources)
            async with api.router.lifespan_context(api):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(api), base_url="http://test") as http:
                    return await http.post("/api/v1/reviews", content=request.content, headers={"Content-Type": "application/json"})
        response = asyncio.run(invoke())
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    with patch("review_system.api_client.httpx.Client", side_effect=factory):
        yield send
    assert all(client.is_closed for client in clients)


def test_interrupted_review_preserves_current_results_across_reruns():
    # Mock the environment loader and transport so no real .env or API is used.
    env = {"REVIEW_PROVIDER": "qwen", "QWEN_API_KEY": "synthetic-placeholder"}
    replies = [chat_response(content) for content in ["Analysis", "Critique", JUDGE_TEXT, "New analysis"]]
    replies.append(httpx.RemoteProtocolError("synthetic-private-response"))
    with patch.dict(os.environ, env, clear=True), patch("review_system.environment.load_project_env"), fake_provider(replies) as send:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        assert app.text_area[0].max_chars == MAX_INPUT_CHARS
        app.text_area[0].set_value("Synthetic input")
        app.button[0].click().run()
        assert not app.exception
        assert [item.value for item in app.markdown] == ["Analysis", "Critique", JUDGE_TEXT]
        assert app.metric[0].value == "pass"

        app.button[0].click().run()
        assert not app.exception
        assert [item.value for item in app.markdown] == ["New analysis"]
        assert len(app.error) == 1
        assert app.error[0].value == "Critic: The model provider request failed. (model_error)"
        assert [item.content for item in app.session_state["review_result"]] == ["New analysis"]
        assert send.call_count == 5
        assert not app.metric
        assert app.session_state["review_record"].final_review is None

        app.run()
        assert not app.exception
        assert [item.value for item in app.markdown] == ["New analysis"]
        assert len(app.error) == 1
        assert send.call_count == 5
        assert not app.metric

        app.text_area[0].set_value(" ")
        app.button[0].click().run()
        assert not app.exception
        assert not app.markdown
        assert len(app.error) == 1
        assert send.call_count == 5
        assert not app.table


def test_callback_error_preserves_response_for_later_rerun():
    env = {"REVIEW_PROVIDER": "qwen", "QWEN_API_KEY": "synthetic-placeholder"}
    with patch.dict(os.environ, env, clear=True), patch("review_system.environment.load_project_env"), fake_provider([chat_response(item) for item in ["Analysis", "Critique", JUDGE_TEXT]]) as send:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        app.text_area[0].set_value("Synthetic input")
        with patch("streamlit.markdown", side_effect=RuntimeError("synthetic-private-detail")):
            app.button[0].click().run()
        assert not app.exception
        assert len(app.error) == 1
        assert "Could not display the complete result" in app.error[0].value
        assert [item.content for item in app.session_state["review_result"]] == ["Analysis", "Critique", JUDGE_TEXT]
        assert send.call_count == 3

        app.run()
        assert not app.exception
        assert [item.value for item in app.markdown] == ["Analysis", "Critique", JUDGE_TEXT]
        assert not app.error
        assert send.call_count == 3


def test_bad_judge_quote_replaces_previous_report_and_survives_rerun():
    env = {"REVIEW_PROVIDER": "qwen", "QWEN_API_KEY": "synthetic-placeholder"}
    bad_report = json.dumps({
        "summary": "New report", "verdict": "needs_revision", "findings": [{
            "category": "evidence", "severity": "high", "message": "Unsupported claim",
            "suggestion": "Check evidence", "start": 0, "end": 2, "quote": "wrong",
        }], "limitations": [],
    })
    replies = [chat_response(content) for content in [
        "Analysis", "Critique", JUDGE_TEXT, "New analysis", "New critique", bad_report,
    ]]
    with patch.dict(os.environ, env, clear=True), patch("review_system.environment.load_project_env"), fake_provider(replies) as send:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        app.text_area[0].set_value("Synthetic input")
        app.button[0].click().run()
        assert not app.exception
        assert app.metric[0].value == "pass"
        app.selectbox[0].select("evidence")
        app.button[0].click().run()
        assert not app.exception
        assert not app.metric
        assert [item.value for item in app.markdown] == ["New analysis", "New critique"]
        assert len(app.warning) == 1
        assert app.code[0].value == bad_report
        assert "invalid_output" in app.error[0].value
        record = app.session_state["review_record"]
        assert app.session_state["completed_review_mode"] == "evidence"
        assert record.final_review is None
        assert [stage.status for stage in record.stages] == ["succeeded", "succeeded", "failed"]
        for call in send.call_args_list[3:]:
            payload = json.loads(call.args[0].content)
            assert json.loads(payload["messages"][1]["content"])["review_mode"] == "evidence"
        assert send.call_count == 6
        app.run()
        assert not app.exception
        assert not app.metric
        assert app.code[0].value == bad_report
        assert send.call_count == 6


def test_structured_findings_and_limitations_are_visible():
    report = (Path(__file__).parent / "fixtures/d2/valid_report.json").read_text()
    env = {"REVIEW_PROVIDER": "qwen", "QWEN_API_KEY": "synthetic-placeholder"}
    with patch.dict(os.environ, env, clear=True), patch("review_system.environment.load_project_env"), fake_provider(
        [chat_response(item) for item in ["A", "C", report]],
    ) as send:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        app.text_area[0].set_value("仅用内存保存记录，重启后历史仍在。")
        app.button[0].click().run()
        assert not app.exception
        assert app.metric[0].value == "needs_revision"
        assert app.code[0].value == "重启后历史仍在"
        text = "\n".join(item.value for item in app.text)
        payload = json.loads(report)
        assert payload["summary"] in text
        assert payload["findings"][0]["message"] in text
        assert payload["findings"][0]["suggestion"] in text
        assert payload["limitations"][0] in text
        assert app.table[0].value["Status"].tolist() == ["succeeded"] * 3
        app.run()
        assert not app.exception
        assert app.metric[0].value == "needs_revision"
        assert send.call_count == 3


def test_fake_mode_visible_and_ui_needs_no_provider_key():
    with patch.dict(os.environ, {}, clear=True), patch("review_system.environment.load_project_env"), fake_provider(
        [chat_response(item) for item in ["A", "C", JUDGE_TEXT]], mode="fake",
    ) as send:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        app.text_area[0].set_value("原文")
        app.button[0].click().run()
        assert not app.exception
        assert "FAKE" in app.warning[0].value
        assert "do not assess" in app.warning[0].value
        assert len(send.api_requests) == 1
        payload = json.loads(send.api_requests[0].content)
        assert set(payload) == {"request_id", "original_input", "review_mode"}
        app.run()
        assert "FAKE" in app.warning[0].value
        assert len(send.api_requests) == 1


def test_uncertain_submission_reuses_id_until_confirmed_then_new_id():
    captured = []

    def submit(**kwargs):
        captured.append(kwargs)
        if len(captured) == 1:
            raise APIClientError("Waiting for the service timed out.")
        code = "duplicate_request" if len(captured) == 2 else "capacity_exceeded"
        return FailureResponse(
            request_id=kwargs["request_id"], review_id=None, execution_mode="fake", status="rejected",
            error=ErrorDTO(code=code, message="synthetic rejection"),
        )

    with patch.dict(os.environ, {}, clear=True), patch("review_system.environment.load_project_env"), patch("review_system.api_client.submit_review", side_effect=submit):
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        app.text_area[0].set_value("text")
        app.button[0].click().run()
        assert not app.exception
        assert len(captured) == 1 and app.info
        original_id = captured[0]["request_id"]
        app.run()
        assert len(captured) == 1
        app.button[0].click().run()
        assert captured[1]["request_id"] == original_id and app.info
        app.button[0].click().run()
        assert captured[2]["request_id"] == original_id and not app.info
        app.button[0].click().run()
        assert captured[3]["request_id"] != original_id
        assert not app.metric


def test_changed_material_gets_new_id_after_uncertain_outcome():
    with patch.dict(os.environ, {}, clear=True), patch("review_system.environment.load_project_env"), patch(
        "review_system.api_client.submit_review", side_effect=APIClientError("Unconfirmed"),
    ) as submit:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        app.text_area[0].set_value("first")
        app.button[0].click().run()
        app.text_area[0].set_value("second")
        app.button[0].click().run()
        assert submit.call_args_list[0].kwargs["request_id"] != submit.call_args_list[1].kwargs["request_id"]
        assert not app.exception


def test_invalid_local_input_or_configuration_does_not_send_http():
    with patch.dict(os.environ, {"REVIEW_API_TIMEOUT_SECONDS": "10"}, clear=True), patch("review_system.environment.load_project_env"), patch("review_system.api_client.submit_review") as submit:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        app.text_area[0].set_value(" ")
        app.button[0].click().run()
        assert app.error and not app.info
        app.text_area[0].set_value("valid input")
        app.button[0].click().run()
        assert "must exceed" in app.error[0].value
        assert not app.exception and not app.info
        submit.assert_not_called()
