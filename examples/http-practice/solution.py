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
    """构造非流式 POST 请求；序列化消息但不修改输入，也不在此处发送请求。"""
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(
            {"model": model, "messages": messages, "stream": False},
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # 认证头只属于初始请求，重定向时不转发给其他地址。
    request.add_unredirected_header("Authorization", f"Bearer {api_key}")
    return request


def parse_response(response) -> str:
    """读取首个回答并验证非空白文本；传入响应的关闭责任留给调用方。"""
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
    """通过注入的 send 发送一次请求，管理响应上下文并统一转换网络异常。"""
    request = build_request(
        settings.base_url, settings.api_key, model=model, messages=messages,
    )
    try:
        with send(request, timeout=settings.timeout_seconds) as response:
            return parse_response(response)
    # HTTPError 是 URLError 的子类，需先处理以保留 HTTP 状态码；不回显供应商正文。
    except HTTPError as exc:
        raise LLMError(f"Provider request failed (HTTP {exc.code}).") from exc
    except TimeoutError as exc:
        raise LLMError("Provider request timed out.", code="network_timeout") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise LLMError("Provider request timed out.", code="network_timeout") from exc
        raise LLMError("Could not connect to the model provider.") from exc
    except OSError as exc:
        raise LLMError("Provider connection failed while reading the response.") from exc
    except HTTPException as exc:
        raise LLMError("Provider connection was interrupted.") from exc
