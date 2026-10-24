"""旧同步模型客户端的离线回归：校验 HTTP 请求、错误分类、重定向和响应清理。"""

import json
from http.client import BadStatusLine, IncompleteRead
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler

import pytest

from review_system.clients import LLMError, OpenAICompatibleClient
from review_system.config import Settings


def settings():
    """构造固定离线配置；不读取环境或真实密钥。"""
    return Settings("qwen", "https://example.invalid/v1", "test-placeholder", "model", "model", "model", "model", 12)


def test_openai_compatible_request_and_response():
    """核验同步请求地址、认证头、JSON 和首个回答提取。"""
    response = BytesIO(json.dumps({"choices": [{"message": {"content": "Review"}}]}).encode())
    messages = [{"role": "user", "content": "Input"}]
    with patch("review_system.clients.urlopen", return_value=response) as send:
        assert OpenAICompatibleClient(settings()).complete(model="chosen-model", messages=messages) == "Review"
    request = send.call_args.args[0]
    assert request.full_url == "https://example.invalid/v1/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer test-placeholder"
    assert json.loads(request.data) == {"model": "chosen-model", "messages": messages, "stream": False}
    assert send.call_args.kwargs["timeout"] == 12


@pytest.mark.parametrize("error, message, code", [
    (TimeoutError(), "timed out", "network_timeout"),
    (URLError(TimeoutError()), "timed out", "network_timeout"),
    (URLError("unavailable"), "Could not connect", "model_error"),
    (HTTPError("https://example.invalid", 401, "Unauthorized", {}, None), "HTTP 401", "model_error"),
    (HTTPError("https://example.invalid", 429, "Too Many Requests", {}, None), "HTTP 429", "model_error"),
    (HTTPError("https://example.invalid", 503, "Unavailable", {}, None), "HTTP 503", "model_error"),
    (BadStatusLine("invalid status"), "interrupted", "model_error"),
    (OSError("connection reset"), "connection failed", "model_error"),
])
def test_transport_errors(error, message, code):
    """同步传输异常转换为稳定的 LLMError。"""
    with patch("review_system.clients.urlopen", side_effect=error):
        with pytest.raises(LLMError, match=message) as caught:
            OpenAICompatibleClient(settings()).complete(model="model", messages=[])
    assert caught.value.code == code
    assert caught.value.__cause__ is error


@pytest.mark.parametrize("error", [TimeoutError("private-timeout"), URLError(TimeoutError("private-timeout"))])
def test_response_read_timeout_has_network_code_and_closes_response(error):
    """读取正文超时标记为网络超时，并关闭响应。"""
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.side_effect = error
    with patch("review_system.clients.urlopen", return_value=response):
        with pytest.raises(LLMError, match="timed out") as caught:
            OpenAICompatibleClient(settings()).complete(model="model", messages=[])
    assert caught.value.code == "network_timeout"
    assert caught.value.__cause__ is error
    assert "private-timeout" not in str(caught.value)
    response.__exit__.assert_called_once()


def test_interrupted_response_read_is_normalized():
    """响应读取中断统一为模型错误，且不暴露私有详情。"""
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.side_effect = IncompleteRead(b"synthetic-private-response")
    with patch("review_system.clients.urlopen", return_value=response):
        with pytest.raises(LLMError, match="interrupted") as caught:
            OpenAICompatibleClient(settings()).complete(model="model", messages=[])
    assert "synthetic-private-response" not in str(caught.value)
    assert settings().api_key not in str(caught.value)
    response.__exit__.assert_called_once()


@pytest.mark.parametrize("status", [301, 302, 303])
def test_redirect_does_not_forward_api_key(status):
    """构造重定向请求时不转发认证头。"""
    response = BytesIO(b'{"choices": [{"message": {"content": "Review"}}]}')
    with patch("review_system.clients.urlopen", return_value=response) as send:
        OpenAICompatibleClient(settings()).complete(model="model", messages=[])
    request = send.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer test-placeholder"
    redirected = HTTPRedirectHandler().redirect_request(
        request, None, status, "Redirect", {}, "https://other.invalid/target",
    )
    assert not redirected.has_header("Authorization")
    assert "test-placeholder" not in repr(redirected.header_items())


@pytest.mark.parametrize("body", [b"not json", b"{}", b'{"choices": []}', b'{"choices": [{"message": {"content": null}}]}'])
def test_malformed_responses(body):
    """响应结构或回答内容非法时拒绝返回可用文本。"""
    with patch("review_system.clients.urlopen", return_value=BytesIO(body)):
        with pytest.raises(LLMError):
            OpenAICompatibleClient(settings()).complete(model="model", messages=[])
