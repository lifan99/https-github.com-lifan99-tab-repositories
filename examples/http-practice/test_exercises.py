"""显式运行的教学验收；默认检查 exercise，HTTP_PRACTICE_IMPL=solution 检查答案。"""

from copy import deepcopy
from http.client import BadStatusLine, IncompleteRead
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import socket
from unittest.mock import MagicMock, Mock
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler

import pytest

from review_system.clients import LLMError
from review_system.config import Settings


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """自动阻断套接字连接及域名解析，确保练习只使用注入的传输。"""
    def blocked(*args, **kwargs):
        raise AssertionError("本练习使用注入的 send，不允许真实网络连接。")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture(scope="session")
def implementation():
    """按环境变量选择待练习文件或参考答案，并按独立模块加载。"""
    name = os.environ.get("HTTP_PRACTICE_IMPL", "exercise")
    if name not in {"exercise", "solution"}:
        pytest.fail("HTTP_PRACTICE_IMPL 只能是 exercise 或 solution")
    spec = importlib.util.spec_from_file_location(
        f"http_practice_{name}", Path(__file__).with_name(f"{name}.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def settings():
    """提供固定的离线端点、模型和合成密钥，避免依赖本机环境。"""
    return Settings(
        provider="qwen", base_url="https://example.invalid/compatible-mode/v1",
        api_key="synthetic-key", model="default-model",
        analyst_model="fake-a", critic_model="fake-c", judge_model="fake-j",
        timeout_seconds=12,
    )


@pytest.mark.parametrize("suffix", ["", "/"])
def test_q07_request_contract(implementation, settings, suffix):
    messages = [{"role": "user", "content": '中文、换行\n和引号 "OK" 🐍'}]
    original = deepcopy(messages)
    request = implementation.build_request(
        settings.base_url + suffix, settings.api_key,
        model="chosen-model", messages=messages,
    )
    assert request.full_url == settings.base_url + "/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Authorization") == "Bearer synthetic-key"
    assert isinstance(request.data, bytes)
    assert json.loads(request.data) == {
        "model": "chosen-model", "messages": original, "stream": False,
    }
    assert messages == original


@pytest.mark.parametrize("status", [301, 302, 303])
def test_q07_redirect_credentials(implementation, settings, status):
    request = implementation.build_request(
        settings.base_url, settings.api_key, model="fake", messages=[],
    )
    redirected = HTTPRedirectHandler().redirect_request(
        request, None, status, "Redirect", {}, "https://other.invalid/target",
    )
    # 直接检查 urllib 生成的新请求，而不是实际连接重定向地址。
    assert not redirected.has_header("Authorization")


@pytest.mark.parametrize("content", ["OK", "  保留原始文本\n"])
def test_q08_valid_text(implementation, content):
    body = {"choices": [
        {"message": {"content": content}},
        {"message": {"content": "第二份不应被选择"}},
    ]}
    with BytesIO(json.dumps(body).encode()) as response:
        assert implementation.parse_response(response) == content
        assert not response.closed, "parse_response 不拥有传入资源"


@pytest.mark.parametrize("body", [
    b"not json", b"{}", b'{"choices": []}', b"[]",
    b'{"choices": [{"message": {}}]}',
])
def test_q08_invalid_structure(implementation, body):
    with BytesIO(body) as response:
        with pytest.raises(LLMError, match="invalid chat response") as caught:
            implementation.parse_response(response)
        assert caught.value.__cause__ is not None


@pytest.mark.parametrize("content", [None, "", " \n\t", 123, ["text"]])
def test_q08_invalid_content(implementation, content):
    body = {"choices": [{"message": {"content": content}}]}
    with BytesIO(json.dumps(body).encode()) as response:
        with pytest.raises(LLMError, match="empty or non-text"):
            implementation.parse_response(response)


def test_q09_success_and_cleanup(implementation, settings):
    response = BytesIO(b'{"choices": [{"message": {"content": "OK"}}]}')
    send = Mock(return_value=response)
    messages = [{"role": "user", "content": "Input"}]
    assert implementation.complete_with_transport(
        settings, model="chosen-model", messages=messages, send=send,
    ) == "OK"
    send.assert_called_once()
    request = send.call_args.args[0]
    assert request.full_url == settings.base_url + "/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer synthetic-key"
    assert json.loads(request.data) == {
        "model": "chosen-model", "messages": messages, "stream": False,
    }
    assert send.call_args.kwargs == {"timeout": 12}
    assert response.closed


@pytest.mark.parametrize("error, message, code", [
    (HTTPError("https://example.invalid", 401, "synthetic-private", {}, None), "HTTP 401", "model_error"),
    (HTTPError("https://example.invalid", 429, "synthetic-private", {}, None), "HTTP 429", "model_error"),
    (HTTPError("https://example.invalid", 503, "synthetic-private", {}, None), "HTTP 503", "model_error"),
    (TimeoutError("synthetic-private"), "timed out", "network_timeout"),
    (URLError(TimeoutError("synthetic-private")), "timed out", "network_timeout"),
    (URLError("synthetic-private"), "Could not connect", "model_error"),
    (OSError("synthetic-private"), "connection failed", "model_error"),
    (BadStatusLine("synthetic-private"), "interrupted", "model_error"),
])
def test_q09_transport_failures(implementation, settings, error, message, code):
    send = Mock(side_effect=error)
    with pytest.raises(LLMError, match=message) as caught:
        implementation.complete_with_transport(
            settings, model="fake", messages=[], send=send,
        )
    assert caught.value.__cause__ is error
    assert caught.value.code == code
    assert "synthetic-private" not in str(caught.value)
    send.assert_called_once()


def test_q09_invalid_json_still_closes_response(implementation, settings):
    response = BytesIO(b"not json")
    with pytest.raises(LLMError, match="invalid chat response"):
        implementation.complete_with_transport(
            settings, model="fake", messages=[], send=Mock(return_value=response),
        )
    assert response.closed


def test_q09_interrupted_read_exits_context(implementation, settings):
    response = MagicMock()
    response.__enter__.return_value = response
    error = IncompleteRead(b"synthetic-private")
    response.read.side_effect = error
    with pytest.raises(LLMError, match="interrupted") as caught:
        implementation.complete_with_transport(
            settings, model="fake", messages=[], send=Mock(return_value=response),
        )
    response.__exit__.assert_called_once()
    assert caught.value.__cause__ is error
    assert "synthetic-private" not in str(caught.value)


def test_q09_keyboard_interrupt_propagates(implementation, settings):
    with pytest.raises(KeyboardInterrupt):
        implementation.complete_with_transport(
            settings, model="fake", messages=[],
            send=Mock(side_effect=KeyboardInterrupt()),
        )
