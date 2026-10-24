"""运行资源回归：确认模型超时或调用方取消后，运行入口关闭自己创建的 HTTP 客户端。"""

import asyncio
from unittest.mock import patch

import httpx
import pytest

from review_system.config import Settings
from review_system.runtime import review_with_settings
from review_system.workflow import WorkflowError


@pytest.mark.parametrize("cancel", [False, True])
def test_owned_http_client_closes_after_timeout_or_cancellation(cancel):
    """预算到期或外部取消后，请求完成清理且运行入口关闭自有客户端。"""
    async def scenario():
        entered = asyncio.Event()
        cleaned = asyncio.Event()

        async def handle(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        settings = Settings(
            "qwen", "https://example.invalid/v1", "synthetic", "m", "a", "c", "j",
            model_timeout_seconds=5 if cancel else 0.02,
        )
        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        with patch("review_system.runtime.create_http_client", return_value=http):
            task = asyncio.create_task(review_with_settings("input", settings))
            try:
                await entered.wait()
                if cancel:
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    with pytest.raises(WorkflowError) as caught:
                        await task
                    assert caught.value.record.error_code == "model_timeout"
                assert cleaned.is_set()
                assert http.is_closed
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await http.aclose()

    async def bounded():
        async with asyncio.timeout(5):
            await scenario()

    asyncio.run(bounded())
