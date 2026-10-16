import asyncio
import json
import logging
from contextlib import contextmanager
from io import StringIO
from unittest.mock import patch

import pytest

from review_system.clients import LLMError
from review_system.config import Settings
from review_system.fakes import DemoClient
from review_system.observability import LOGGER, configure_logging, log_event
from review_system.service import ReviewService, ServiceError

SETTINGS = Settings("fake", "https://example.invalid", "private-key", "m", "a", "c", "j")


@contextmanager
def captured_events():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    previous_level = LOGGER.level
    LOGGER.setLevel(logging.INFO)
    LOGGER.addHandler(handler)
    try:
        yield stream
    finally:
        LOGGER.removeHandler(handler)
        LOGGER.setLevel(previous_level)


def events(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_success_events_are_correlated_ordered_and_contain_only_control_fields():
    async def scenario():
        service = ReviewService(DemoClient(), SETTINGS)
        with captured_events() as stream:
            result = await service.review("private-request-id", "private-original-input")
        data = events(stream)
        assert len(data) == 8
        assert {item["review_id"] for item in data} == {result.review_id}
        assert [(item["stage"], item["status"]) for item in data] == [
            (None, "running"), ("Analyst", "running"), ("Analyst", "succeeded"),
            ("Critic", "running"), ("Critic", "succeeded"), ("Judge", "running"),
            ("Judge", "succeeded"), (None, "succeeded"),
        ]
        assert all(set(item) == {"review_id", "stage", "status", "elapsed_ms", "error_code"} for item in data)
        assert all(type(item["elapsed_ms"]) is int and item["elapsed_ms"] >= 0 for item in data)
        assert "private-" not in stream.getvalue()
        assert "fake" not in stream.getvalue()
    asyncio.run(scenario())


def test_failure_events_preserve_stage_and_omit_provider_exception_text():
    class Failing(DemoClient):
        async def complete(self, *, model, messages):
            if model == "c":
                raise LLMError("private-provider-body")
            return await super().complete(model=model, messages=messages)

    async def scenario():
        service = ReviewService(Failing(), SETTINGS)
        with captured_events() as stream:
            with pytest.raises(ServiceError):
                await service.review("private-id", "private-original")
        data = events(stream)
        assert [(item["stage"], item["status"]) for item in data[-3:]] == [
            ("Critic", "failed"), ("Judge", "skipped"), (None, "failed"),
        ]
        assert data[-1]["error_code"] == data[-3]["error_code"] == "model_error"
        assert "private-" not in stream.getvalue()
    asyncio.run(scenario())


def test_cancellation_and_rejection_emit_distinct_safe_events():
    async def scenario():
        entered = asyncio.Event()

        class Waiting(DemoClient):
            async def complete(self, *, model, messages):
                entered.set()
                await asyncio.Event().wait()

        service = ReviewService(Waiting(), SETTINGS)
        with captured_events() as stream:
            async with asyncio.timeout(5):
                task = asyncio.create_task(service.review("private-id", "private-input"))
                await entered.wait()
                with pytest.raises(ServiceError):
                    await service.review("private-id", "other-private-input")
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        data = events(stream)
        rejection = next(item for item in data if item["status"] == "rejected")
        assert rejection["review_id"] is None and rejection["error_code"] == "duplicate_request"
        assert data[-1]["status"] == "cancelled" and data[-1]["error_code"] == "cancelled"
        assert any(item["stage"] == "Analyst" and item["status"] == "cancelled" for item in data)
        assert "private-" not in stream.getvalue()
    asyncio.run(scenario())


def test_logging_setup_is_idempotent_and_does_not_reconfigure_root_logger():
    root_handlers = list(logging.getLogger().handlers)
    configure_logging()
    configure_logging()
    assert sum(bool(getattr(handler, "_review_events", False)) for handler in LOGGER.handlers) == 1
    assert logging.getLogger().handlers == root_handlers


def test_unexpected_values_are_sanitized_and_broken_sink_does_not_fail_review():
    with captured_events() as stream:
        log_event(review_id="private-id", stage=["private-stage"], status="private-status",
                  elapsed_ms=10**1000, error_code={"private": "detail"})
    assert events(stream) == [{"review_id": None, "stage": None, "status": "failed", "elapsed_ms": 0, "error_code": "internal_error"}]

    async def scenario():
        with patch.object(LOGGER, "info", side_effect=OSError("broken sink")):
            result = await ReviewService(DemoClient(), SETTINGS).review("id", "text")
        assert result.result.record.status == "succeeded"
    asyncio.run(scenario())
