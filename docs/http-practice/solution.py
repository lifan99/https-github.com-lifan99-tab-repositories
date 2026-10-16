"""Q07–Q09 参考实现；与 exercise.py 接受同一组离线检查。"""

from http.client import HTTPException
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request

from review_system.clients import LLMError
from review_system.config import Settings


def build_request(
    base_url: str,
    api_key: str,
    *,
    model: str,
    messages: list[dict[str, str]],
) -> Request:
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(
            {"model": model, "messages": messages, "stream": False},
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    request.add_unredirected_header("Authorization", f"Bearer {api_key}")
    return request


def parse_response(response) -> str:
    try:
        payload = json.load(response)
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("The provider returned an invalid chat response.") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMError("The provider returned empty or non-text content.")
    return content


def complete_with_transport(
    settings: Settings,
    *,
    model: str,
    messages: list[dict[str, str]],
    send,
) -> str:
    request = build_request(
        settings.base_url, settings.api_key, model=model, messages=messages,
    )
    try:
        with send(request, timeout=settings.timeout_seconds) as response:
            return parse_response(response)
    except HTTPError as exc:
        raise LLMError(f"Provider request failed (HTTP {exc.code}).") from exc
    except TimeoutError as exc:
        raise LLMError("Provider request timed out.") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise LLMError("Provider request timed out.") from exc
        raise LLMError("Could not connect to the model provider.") from exc
    except OSError as exc:
        raise LLMError("Provider connection failed while reading the response.") from exc
    except HTTPException as exc:
        raise LLMError("Provider connection was interrupted.") from exc
