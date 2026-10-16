import asyncio
import json

import httpx
import pytest

from review_system.clients import AsyncOpenAICompatibleClient, LLMError
from review_system.config import Settings

SETTINGS = Settings("qwen", "https://example.invalid/v1", "synthetic-key", "m", "m", "m", "m", 12)


def test_async_request_contract_and_borrowed_client_lifetime():
    async def scenario():
        seen = []

        async def handle(request):
            await asyncio.sleep(0)
            seen.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "  答复\n"}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = AsyncOpenAICompatibleClient(SETTINGS, http)
            messages = [{"role": "user", "content": "中文"}]
            assert await client.complete(model="chosen", messages=messages) == "  答复\n"
            assert not http.is_closed
            request = seen[0]
            assert str(request.url) == SETTINGS.base_url + "/chat/completions"
            assert request.method == "POST"
            assert request.headers["authorization"] == "Bearer synthetic-key"
            assert request.headers["content-type"] == "application/json"
            assert json.loads(request.content) == {"model": "chosen", "messages": messages, "stream": False}
            assert request.extensions["timeout"] == {"connect": 12, "read": 12, "write": 12, "pool": 12}
        assert http.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401, 429, 503])
def test_status_errors_never_follow_redirect_or_expose_body(status):
    async def scenario():
        seen = []

        def handle(request):
            seen.append(request)
            return httpx.Response(status, text="synthetic-private", headers={"Location": "https://other.invalid"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as http:
            with pytest.raises(LLMError, match=f"HTTP {status}") as caught:
                await AsyncOpenAICompatibleClient(SETTINGS, http).complete(model="m", messages=[])
            assert "synthetic-private" not in str(caught.value)
            assert SETTINGS.api_key not in str(caught.value)
            assert len(seen) == 1
            assert seen[0].url.host == "example.invalid"
            assert not http.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("error_type, code, message", [
    (httpx.ConnectTimeout, "network_timeout", "timed out"),
    (httpx.ReadTimeout, "network_timeout", "timed out"),
    (httpx.WriteTimeout, "network_timeout", "timed out"),
    (httpx.PoolTimeout, "network_timeout", "timed out"),
    (httpx.ConnectError, "model_error", "Could not connect"),
    (httpx.ReadError, "model_error", "interrupted"),
    (httpx.WriteError, "model_error", "interrupted"),
    (httpx.RemoteProtocolError, "model_error", "interrupted"),
])
def test_transport_error_classification(error_type, code, message):
    async def scenario():
        def handle(request):
            raise error_type("synthetic-private", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            with pytest.raises(LLMError, match=message) as caught:
                await AsyncOpenAICompatibleClient(SETTINGS, http).complete(model="m", messages=[])
            assert caught.value.code == code
            assert "synthetic-private" not in str(caught.value)

    asyncio.run(scenario())


@pytest.mark.parametrize("body", [
    b"not json", b"{}", b'{"choices":[]}', b'{"choices":[{"message":{"content":null}}]}',
    b'{"choices":[{"message":{"content":" "}}]}',
])
def test_bad_response_content(body):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))) as http:
            with pytest.raises(LLMError):
                await AsyncOpenAICompatibleClient(SETTINGS, http).complete(model="m", messages=[])

    asyncio.run(scenario())


def test_cancelled_transport_cleans_up_without_closing_shared_client():
    async def scenario():
        entered, cleaned = asyncio.Event(), asyncio.Event()

        async def handle(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            task = asyncio.create_task(AsyncOpenAICompatibleClient(SETTINGS, http).complete(model="m", messages=[]))
            try:
                async with asyncio.timeout(2):
                    await entered.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    assert cleaned.is_set()
                    assert not http.is_closed
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_cancellation_during_response_body_read_closes_stream():
    async def scenario():
        entered, closed = asyncio.Event(), asyncio.Event()

        class SlowBody(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{"choices":'
                entered.set()
                await asyncio.Event().wait()

            async def aclose(self):
                closed.set()

        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=SlowBody()),
        )) as http:
            task = asyncio.create_task(AsyncOpenAICompatibleClient(SETTINGS, http).complete(model="m", messages=[]))
            try:
                async with asyncio.timeout(2):
                    await entered.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    assert closed.is_set()
                    assert not http.is_closed
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
