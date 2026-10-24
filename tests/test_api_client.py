"""界面 HTTP 客户端回归：严格核验响应一致性、超时行为及传输资源归属。"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from review_system.api_client import APIClientError, APISettings, ReviewAPIClient, submit_review
from review_system.api_models import ERROR_SPECS, FailureResponse, SuccessResponse

PAYLOAD = json.loads((Path(__file__).parent / "fixtures/d5/success_response.json").read_text())


def invoke(response, *, original=" 原文\n"):
    """用内存 HTTP 替身调用客户端，返回测试指定的服务响应。"""
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as http:
        return ReviewAPIClient(APISettings(), http).review("test-id", original)


def test_client_request_has_only_public_fields_and_borrows_transport():
    """提交仅含公开字段；调用完成后借用的传输仍由外部持有。"""
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(201, json=PAYLOAD)

    with httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True) as http:
        result = ReviewAPIClient(APISettings(timeout_seconds=181), http).review("test-id", " 原文\n", "evidence")
        assert isinstance(result, SuccessResponse)
        assert result.execution_mode == "fake"
        assert not http.is_closed
    request = seen[0]
    assert str(request.url) == "http://127.0.0.1:8000/api/v1/reviews"
    assert json.loads(request.content) == {"request_id": "test-id", "original_input": " 原文\n", "review_mode": "evidence"}
    assert "authorization" not in request.headers
    assert request.extensions["timeout"] == {key: 181 for key in ("connect", "read", "write", "pool")}


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(request_id="someone-else"),
    lambda p: p.update(review_id="not-a-uuid"),
    lambda p: p.update(execution_mode="unknown"),
    lambda p: p.update(status="running"),
    lambda p: p.update(final_review=None),
    lambda p: p["responses"].pop(),
    lambda p: p["stages"].pop(),
    lambda p: p["responses"][0].update(content="changed"),
    lambda p: p["stages"][0].update(status="failed"),
    lambda p: p["final_review"].update(summary="different from Judge"),
    lambda p: p.update(unexpected="private-value"),
    lambda p: p.update(error={"code": "model_error"}),
])
def test_inconsistent_success_is_never_published(mutate):
    """拒绝标识、回答、阶段或最终报告彼此不一致的成功响应。"""
    payload = deepcopy(PAYLOAD)
    mutate(payload)
    with pytest.raises(APIClientError, match="invalid response") as caught:
        invoke(httpx.Response(201, json=payload))
    assert "private-value" not in str(caught.value)


def test_final_quote_is_rechecked_against_submitted_original():
    """客户端使用本次提交的原文再次验证最终报告引用。"""
    payload = deepcopy(PAYLOAD)
    report = {"summary": "s", "verdict": "needs_revision", "limitations": [], "findings": [{
        "category": "logic", "severity": "high", "message": "m", "suggestion": "s",
        "start": 0, "end": 1, "quote": "wrong",
    }]}
    payload["final_review"] = report
    text = json.dumps(report)
    payload["responses"][-1]["content"] = payload["stages"][-1]["raw_output"] = text
    with pytest.raises(APIClientError, match="invalid response"):
        invoke(httpx.Response(201, json=payload))


@pytest.mark.parametrize("code", ["invalid_request", "duplicate_request", "capacity_exceeded", "internal_error", "service_unavailable"])
def test_valid_rejection_is_parsed_without_exception(code):
    """合法拒绝响应作为业务结果返回，无需抛出传输异常。"""
    status, message = ERROR_SPECS[code]
    body = {"request_id": None if code == "invalid_request" else "test-id", "review_id": None,
            "execution_mode": "fake", "status": "rejected", "responses": [], "stages": [],
            "final_review": None, "error": {"code": code, "message": message, "stage": None}}
    result = invoke(httpx.Response(status, json=body))
    assert isinstance(result, FailureResponse) and result.error.code == code
    with pytest.raises(APIClientError):
        invoke(httpx.Response(418, json=body))


@pytest.mark.parametrize("status,body", [(200, PAYLOAD), (500, {"detail": "private-stack"}), (201, {}), (302, PAYLOAD)])
def test_unexpected_status_or_shape_is_sanitized(status, body):
    """未知状态码或非法响应结构转为通用客户端错误。"""
    with pytest.raises(APIClientError) as caught:
        invoke(httpx.Response(status, json=body, headers={"Location": "https://other.invalid"}))
    assert "private-stack" not in str(caught.value)


@pytest.mark.parametrize("exception", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadError])
def test_network_failure_is_safe_and_never_retried(exception):
    """网络失败不泄露异常细节，也不自动重试可能仍在执行的提交。"""
    calls = []

    def handle(request):
        calls.append(request)
        raise exception("private-error-details")

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(APIClientError) as caught:
            ReviewAPIClient(APISettings(), http).review("id", "text")
        assert "private-error" not in str(caught.value)
        assert len(calls) == 1
        assert not http.is_closed


def test_owned_http_client_closes_after_failure():
    """便捷提交入口失败时也关闭自己创建的 HTTP 客户端。"""
    owned = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="private")))
    with patch("review_system.api_client.httpx.Client", return_value=owned):
        with pytest.raises(APIClientError):
            submit_review("id", "text", settings=APISettings())
    assert owned.is_closed


@pytest.mark.parametrize("url", ["", "ftp://localhost", "http://user:secret@localhost", "http://localhost?key=x", "http://localhost/#fragment", "http://localhost:bad", "http://localhost:99999"])
def test_api_settings_reject_invalid_urls_without_echoing_them(url):
    """非法后端地址提前报错，错误消息不回显地址。"""
    with pytest.raises(ValueError) as caught:
        APISettings(url)
    assert "secret" not in str(caught.value)


def test_ui_wait_budget_is_larger_than_backend_budget_without_reading_model_key(monkeypatch):
    """界面等待预算必须大于后端总预算，读取配置不依赖模型密钥。"""
    monkeypatch.delenv("REVIEW_API_BASE_URL", raising=False)
    monkeypatch.delenv("REVIEW_API_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("REVIEW_TOTAL_TIMEOUT_SECONDS", "200")
    settings = APISettings.from_env()
    assert settings.timeout_seconds == 230
    monkeypatch.setenv("REVIEW_API_TIMEOUT_SECONDS", "200")
    with pytest.raises(ValueError, match="must exceed"):
        APISettings.from_env()
