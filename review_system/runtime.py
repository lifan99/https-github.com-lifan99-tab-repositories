"""Own the event loop and HTTP resources for one synchronous Python invocation."""

import asyncio

import httpx

from .clients import AsyncOpenAICompatibleClient
from .config import Settings
from .workflow import ensure_sync_context, run_review_async


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.timeout_seconds, follow_redirects=False)


async def review_with_settings(user_input, settings: Settings, *, review_mode="logic", on_response=None):
    async with create_http_client(settings) as http_client:
        return await run_review_async(
            user_input, AsyncOpenAICompatibleClient(settings, http_client),
            analyst_model=settings.analyst_model, critic_model=settings.critic_model,
            judge_model=settings.judge_model, review_mode=review_mode, on_response=on_response,
            model_timeout_seconds=settings.model_timeout_seconds,
            total_timeout_seconds=settings.total_timeout_seconds,
            slots=asyncio.Semaphore(2),
        )


def run_review_with_settings(user_input, settings: Settings, *, review_mode="logic", on_response=None):
    ensure_sync_context()
    return asyncio.run(review_with_settings(
        user_input, settings, review_mode=review_mode, on_response=on_response,
    ))
