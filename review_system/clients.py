"""封装兼容 OpenAI 的聊天传输及统一错误；与审核业务流程分离。"""

import json
from http.client import HTTPException
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx

from .config import Settings


class LLMError(RuntimeError):
    """模型调用失败或响应不可用；code 供工作流和 HTTP 层做稳定的错误分类。"""

    def __init__(self, message: str, *, code: str = "model_error"):
        super().__init__(message)
        self.code = code


class LLMClient(Protocol):
    """同步客户端协议，供旧传输实现和 HTTP 教学练习使用。"""
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str: ...


class AsyncLLMClient(Protocol):
    """异步工作流依赖的最小接口；真实客户端与离线替身均可实现。"""
    async def complete(self, *, model: str, messages: list[dict[str, str]]) -> str: ...


class AsyncOpenAICompatibleClient:
    """借用外部共享的 HTTP 客户端；创建方负责关闭，单次模型调用不关闭它。"""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self.settings = settings
        self.http_client = http_client

    async def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        """发送非流式聊天请求，提取首个回答，并将网络或格式异常转换为 LLMError。"""
        try:
            response = await self.http_client.post(
                f"{self.settings.base_url}/chat/completions",
                json={"model": model, "messages": messages, "stream": False},
                headers={"Authorization": f"Bearer {self.settings.api_key}"},
                timeout=self.settings.timeout_seconds,
                # 禁止跟随重定向，避免将认证信息发送到其他地址。
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
        # 网络操作超时与工作流的模型预算超时分开标记，便于定位等待发生的层次。
        except httpx.TimeoutException as exc:
            raise LLMError("Provider request timed out.", code="network_timeout") from exc
        except httpx.ConnectError as exc:
            raise LLMError("Could not connect to the model provider.") from exc
        except httpx.RequestError as exc:
            raise LLMError("Provider connection was interrupted.") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("The provider returned an invalid chat response.") from exc


class OpenAICompatibleClient:
    """为 HTTP 教学练习保留的同步传输；业务工作流使用异步客户端。"""
    def __init__(self, settings: Settings):
        self.settings = settings

    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        """发送同步请求并管理响应资源；保留回答原始空白，不自动重试。"""
        request = Request(
            f"{self.settings.base_url}/chat/completions",
            data=json.dumps({"model": model, "messages": messages, "stream": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # 认证头仅用于初始请求；urllib 构造重定向请求时不会复制它。
        request.add_unredirected_header("Authorization", f"Bearer {self.settings.api_key}")
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                payload = json.load(response)
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise LLMError("The provider returned empty or non-text content.")
            return content
        except HTTPError as exc:
            # 只保留 HTTP 状态码，避免在公开错误中暴露可能含敏感输入的供应商正文。
            raise LLMError(f"Provider request failed (HTTP {exc.code}).") from exc
        except TimeoutError as exc:
            raise LLMError("Provider request timed out.", code="network_timeout") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise LLMError("Provider request timed out.", code="network_timeout") from exc
            raise LLMError("Could not connect to the model provider.") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("The provider returned an invalid chat response.") from exc
        except OSError as exc:
            raise LLMError("Provider connection failed while reading the response.") from exc
        except HTTPException as exc:
            raise LLMError("Provider connection was interrupted.") from exc
