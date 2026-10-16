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
    return Settings("qwen", "https://example.invalid/v1", "test-placeholder", "model", "model", "model", "model", 12)


def test_openai_compatible_request_and_response():
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


@pytest.mark.parametrize("error, message", [
    (TimeoutError(), "timed out"),
    (URLError(TimeoutError()), "timed out"),
    (URLError("unavailable"), "Could not connect"),
    (HTTPError("https://example.invalid", 401, "Unauthorized", {}, None), "HTTP 401"),
    (HTTPError("https://example.invalid", 429, "Too Many Requests", {}, None), "HTTP 429"),
    (HTTPError("https://example.invalid", 503, "Unavailable", {}, None), "HTTP 503"),
    (BadStatusLine("invalid status"), "interrupted"),
    (OSError("connection reset"), "connection failed"),
])
def test_transport_errors(error, message):
    with patch("review_system.clients.urlopen", side_effect=error):
        with pytest.raises(LLMError, match=message):
            OpenAICompatibleClient(settings()).complete(model="model", messages=[])


def test_interrupted_response_read_is_normalized():
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
    with patch("review_system.clients.urlopen", return_value=BytesIO(body)):
        with pytest.raises(LLMError):
            OpenAICompatibleClient(settings()).complete(model="model", messages=[])
