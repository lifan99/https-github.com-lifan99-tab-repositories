"""OpenAI-compatible chat transport, independent of the review workflow."""

import json
from http.client import HTTPException
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx

from .config import Settings


class LLMError(RuntimeError):
    """A model call failed or returned an unusable response."""

    def __init__(self, message: str, *, code: str = "model_error"):
        super().__init__(message)
        self.code = code


class LLMClient(Protocol):
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str: ...


class AsyncLLMClient(Protocol):
    async def complete(self, *, model: str, messages: list[dict[str, str]]) -> str: ...


class AsyncOpenAICompatibleClient:
    """Borrow a shared HTTP client; the creator owns its lifetime."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self.settings = settings
        self.http_client = http_client

    async def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        try:
            response = await self.http_client.post(
                f"{self.settings.base_url}/chat/completions",
                json={"model": model, "messages": messages, "stream": False},
                headers={"Authorization": f"Bearer {self.settings.api_key}"},
                timeout=self.settings.timeout_seconds,
                follow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise LLMError("The provider returned empty or non-text content.")
            return content
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"Provider request failed (HTTP {exc.response.status_code}).") from exc
        except httpx.TimeoutException as exc:
            raise LLMError("Provider request timed out.", code="network_timeout") from exc
        except httpx.ConnectError as exc:
            raise LLMError("Could not connect to the model provider.") from exc
        except httpx.RequestError as exc:
            raise LLMError("Provider connection was interrupted.") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("The provider returned an invalid chat response.") from exc


class OpenAICompatibleClient:
    """Legacy synchronous transport retained for HTTP teaching exercises."""
    def __init__(self, settings: Settings):
        self.settings = settings

    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        request = Request(
            f"{self.settings.base_url}/chat/completions",
            data=json.dumps({"model": model, "messages": messages, "stream": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # Send credentials only to the configured endpoint, never to redirects.
        request.add_unredirected_header("Authorization", f"Bearer {self.settings.api_key}")
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                payload = json.load(response)
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise LLMError("The provider returned empty or non-text content.")
            return content
        except HTTPError as exc:
            # Do not expose provider bodies, which may contain sensitive input.
            raise LLMError(f"Provider request failed (HTTP {exc.code}).") from exc
        except TimeoutError as exc:
            raise LLMError("Provider request timed out.") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise LLMError("Provider request timed out.") from exc
            raise LLMError("Could not connect to the model provider.") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("The provider returned an invalid chat response.") from exc
        except OSError as exc:
            raise LLMError("Provider connection failed while reading the response.") from exc
        except HTTPException as exc:
            raise LLMError("Provider connection was interrupted.") from exc
