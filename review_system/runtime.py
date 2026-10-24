"""为同步 Python 调用管理一次事件循环及其 HTTP 资源，确保请求结束后关闭连接。"""

import asyncio

import httpx

from .clients import AsyncOpenAICompatibleClient
from .config import Settings
from .workflow import ensure_sync_context, run_review_async


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    """创建模型 HTTP 客户端；使用操作超时并禁止重定向，生命周期由调用方管理。"""
    return httpx.AsyncClient(timeout=settings.timeout_seconds, follow_redirects=False)


async def review_with_settings(user_input, settings: Settings, *, review_mode="logic", on_response=None):
    """在一次异步调用中创建和关闭 HTTP 客户端，并把角色模型及预算传给内核。"""
    async with create_http_client(settings) as http_client:
        return await run_review_async(
            user_input, AsyncOpenAICompatibleClient(settings, http_client),
            analyst_model=settings.analyst_model, critic_model=settings.critic_model,
            judge_model=settings.judge_model, review_mode=review_mode, on_response=on_response,
            model_timeout_seconds=settings.model_timeout_seconds,
            total_timeout_seconds=settings.total_timeout_seconds,
            # 此信号量只属于本次调用；跨请求统一容量由长驻的 ReviewService 管理。
            slots=asyncio.Semaphore(2),
        )


def run_review_with_settings(user_input, settings: Settings, *, review_mode="logic", on_response=None):
    """同步脚本入口；确认没有运行中的事件循环后创建本次调用的事件循环。"""
    ensure_sync_context()
    return asyncio.run(review_with_settings(
        user_input, settings, review_mode=review_mode, on_response=on_response,
    ))
