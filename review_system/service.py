"""Single-event-loop admission and owned review tasks, independent of HTTP/UI."""

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from .clients import AsyncLLMClient
from .config import Settings
from .contracts import validate_request_id, validate_review_request
from .observability import log_event
from .workflow import ReviewResult, ReviewRun, WorkflowError, run_review_async


class ServiceError(RuntimeError):
    def __init__(self, code: str, *, review_id: str | None = None, run: ReviewRun | None = None):
        super().__init__(code)
        self.code = code
        self.review_id = review_id
        self.run = run


@dataclass(frozen=True)
class ServiceResult:
    review_id: str
    result: ReviewResult


class ReviewService:
    CAPACITY = 2

    def __init__(self, client: AsyncLLMClient, settings: Settings):
        self.client = client
        self.settings = settings
        self._active: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._closing = False

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    async def review(self, request_id: str, original_input: str, review_mode: str = "logic") -> ServiceResult:
        validate_request_id(request_id)
        validate_review_request(original_input, review_mode)
        if self._closing:
            log_event(review_id=None, status="rejected", error_code="service_unavailable")
            raise ServiceError("service_unavailable")
        deadline = asyncio.get_running_loop().time() + self.settings.total_timeout_seconds
        task = asyncio.create_task(self._execute(request_id, original_input, review_mode, deadline))
        self._tasks.add(task)
        try:
            return await task
        finally:
            # Awaiting a child propagates caller cancellation into it. Still collect it
            # before dropping ownership, including cancellation before its first step.
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self._tasks.discard(task)

    async def _execute(self, request_id, original_input, review_mode, deadline):
        def reject(code):
            log_event(review_id=None, status="rejected", error_code=code)
            return ServiceError(code)

        if self._closing:
            raise reject("service_unavailable")
        if request_id in self._active:
            raise reject("duplicate_request")
        if len(self._active) >= self.CAPACITY:
            raise reject("capacity_exceeded")
        review_id = str(uuid4())
        run = ReviewRun()
        self._active.add(request_id)
        started = deadline - self.settings.total_timeout_seconds

        def event(status, code=None):
            log_event(review_id=review_id, status=status, error_code=code,
                      elapsed_ms=(asyncio.get_running_loop().time() - started) * 1000)

        event("running")
        try:
            result = await run_review_async(
                original_input, self.client, review_mode=review_mode,
                analyst_model=self.settings.analyst_model,
                critic_model=self.settings.critic_model,
                judge_model=self.settings.judge_model,
                model_timeout_seconds=self.settings.model_timeout_seconds,
                total_timeout_seconds=self.settings.total_timeout_seconds,
                total_deadline=deadline, run=run, review_id=review_id,
            )
            event("succeeded")
            return ServiceResult(review_id, result)
        except asyncio.CancelledError:
            event("cancelled", "cancelled")
            raise
        except WorkflowError as exc:
            event("failed", exc.record.error_code)
            raise ServiceError(exc.record.error_code, review_id=review_id, run=run) from exc
        except Exception as exc:
            event("failed", "internal_error")
            raise ServiceError("internal_error", review_id=review_id, run=run) from exc
        finally:
            self._active.remove(request_id)

    async def aclose(self):
        self._closing = True
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.difference_update(tasks)
