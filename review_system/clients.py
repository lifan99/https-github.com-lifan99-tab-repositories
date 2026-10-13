"""OpenAI-compatible chat transport, independent of the review workflow."""

from http.client import HTTPException
import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Settings


class LLMError(RuntimeError):
    """A model call failed or returned an unusable response."""


class LLMClient(Protocol):
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str: ...


class OpenAICompatibleClient:
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
