"""One asynchronous review core, with immutable snapshots and a sync facade."""

import asyncio
import json
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from typing import Callable

from .agents import ANALYST, CRITIC, JUDGE
from .clients import AsyncLLMClient, LLMError
from .config import validate_seconds
from .contracts import MAX_INPUT_CHARS as MAX_INPUT_CHARS
from .contracts import (
    ContractError,
    ReviewRecord,
    StageRecord,
    parse_final_review,
    validate_review_request,
)
from .observability import log_event


@dataclass(frozen=True)
class AgentResponse:
    agent: str
    model: str
    content: str


@dataclass(frozen=True)
class ReviewResult:
    responses: tuple[AgentResponse, ...]
    record: ReviewRecord

    @property
    def final_response(self) -> str:
        return self.responses[-1].content


@dataclass
class ReviewRun:
    """One-shot handle retained by the owner to inspect progress after cancellation."""

    record: ReviewRecord | None = field(default=None, init=False)
    responses: tuple[AgentResponse, ...] = field(default=(), init=False)
    _started: bool = field(default=False, init=False, repr=False)


class WorkflowError(RuntimeError):
    def __init__(self, agent: str, cause: Exception, completed: tuple[AgentResponse, ...], record: ReviewRecord):
        super().__init__(f"{agent} failed: {cause}")
        self.agent = agent
        self.completed = completed
        self.record = record


class _TotalTimeout(Exception):
    pass


class _CallbackFailure(Exception):
    pass


async def _model_call(client, model, messages, seconds):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    scope = asyncio.timeout_at(deadline)
    try:
        async with scope:
            content = await client.complete(model=model, messages=messages)
    except TimeoutError as exc:
        if not scope.expired():
            raise
        raise LLMError("Model call deadline exceeded.", code="model_timeout") from exc
    if scope.expired() or loop.time() >= deadline:
        # A client that swallowed the timer's cancellation still cannot publish success.
        raise LLMError("Model call deadline exceeded.", code="model_timeout")
    return content


async def run_review_async(
    user_input: str,
    client: AsyncLLMClient,
    *,
    analyst_model: str,
    critic_model: str,
    judge_model: str,
    review_mode: str = "logic",
    on_response: Callable[[AgentResponse], None] | None = None,
    model_timeout_seconds: float = 60,
    total_timeout_seconds: float = 150,
    total_deadline: float | None = None,
    slots: asyncio.Semaphore | None = None,
    run: ReviewRun | None = None,
    review_id: str | None = None,
) -> ReviewResult:
    request = validate_review_request(user_input, review_mode)
    validate_seconds(model_timeout_seconds, "model_timeout_seconds")
    validate_seconds(total_timeout_seconds, "total_timeout_seconds")
    if total_deadline is not None:
        validate_seconds(total_deadline, "total_deadline")
    run = run if run is not None else ReviewRun()
    if run._started:
        raise ValueError("ReviewRun can only be used once; create one per review.")
    run._started = True
    loop = asyncio.get_running_loop()
    deadline = loop.time() + total_timeout_seconds
    if total_deadline is not None:
        deadline = min(deadline, total_deadline)
    assignments = ((ANALYST, analyst_model), (CRITIC, critic_model), (JUDGE, judge_model))
    stages = [StageRecord(agent.name, model) for agent, model in assignments]
    completed: list[AgentResponse] = []
    context = {"original_input": request.original_input, "review_mode": request.review_mode}
    final_review = None
    logged_states = ["pending"] * 3
    stage_started = [None] * 3

    def snapshot(status, error_code=None, report=None):
        run.record = ReviewRecord(request, tuple(stages), report, status, error_code)
        run.responses = tuple(completed)
        if review_id is not None:
            for index, stage in enumerate(stages):
                if stage.status != logged_states[index]:
                    now = loop.time()
                    if stage.status == "running":
                        stage_started[index] = now
                    elapsed = now - stage_started[index] if stage_started[index] is not None else 0
                    log_event(review_id=review_id, stage=stage.agent, status=stage.status,
                              elapsed_ms=elapsed * 1000, error_code=stage.error_code)
                    logged_states[index] = stage.status

    def check_deadline():
        if loop.time() >= deadline:
            raise _TotalTimeout()

    def stop(code, cause):
        agent = "Review"
        for index, stage in enumerate(stages):
            if stage.status == "running":
                agent = stage.agent
                stages[index] = replace(
                    stage, status="cancelled" if code == "cancelled" else "failed", error_code=code,
                )
            elif stage.status == "pending":
                stages[index] = replace(stage, status="skipped")
        snapshot("cancelled" if code == "cancelled" else "failed", code)
        return WorkflowError(agent, cause, tuple(completed), run.record)

    def failure(code, cause):
        if loop.time() >= deadline:
            return stop("total_timeout", RuntimeError("Review total deadline exceeded."))
        return stop(code, cause)

    snapshot("queued")
    total_scope = asyncio.timeout_at(deadline)
    try:
        async with total_scope:
            async with (slots if slots is not None else nullcontext()):
                check_deadline()
                snapshot("running")
                for index, (agent, model) in enumerate(assignments):
                    check_deadline()
                    stages[index] = replace(stages[index], status="running")
                    snapshot("running")
                    messages = [
                        {"role": "system", "content": agent.system_prompt},
                        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                    ]
                    try:
                        content = await _model_call(client, model, messages, model_timeout_seconds)
                    except LLMError:
                        raise
                    except Exception as exc:
                        raise LLMError("Model client failed.") from exc
                    if isinstance(content, str):
                        stages[index] = replace(stages[index], raw_output=content)
                        snapshot("running")
                    if not isinstance(content, str) or not content.strip():
                        raise LLMError("The model returned empty or non-text content.")
                    if agent is JUDGE:
                        final_review = parse_final_review(content, request.original_input)
                    check_deadline()
                    response = AgentResponse(agent.name, model, content)
                    completed.append(response)
                    context[f"{agent.name.lower()}_output"] = content
                    snapshot("running")
                    if on_response is not None:
                        try:
                            on_response(response)
                        except Exception as exc:
                            raise _CallbackFailure() from exc
                    check_deadline()
                    stages[index] = replace(stages[index], status="succeeded")
                    snapshot("running")
                check_deadline()
        check_deadline()
    except asyncio.CancelledError:
        stop("cancelled", RuntimeError("Review cancelled."))
        raise
    except _TotalTimeout as exc:
        raise stop("total_timeout", RuntimeError("Review total deadline exceeded.")) from exc
    except TimeoutError as exc:
        if total_scope.expired():
            raise stop("total_timeout", RuntimeError("Review total deadline exceeded.")) from exc
        raise failure("model_error", RuntimeError("Model client failed.")) from exc
    except _CallbackFailure as exc:
        raise failure("callback_error", RuntimeError("Response callback failed.")) from exc.__cause__
    except ContractError as exc:
        raise failure("invalid_output", exc) from exc
    except LLMError as exc:
        raise failure(exc.code, exc) from exc
    snapshot("succeeded", report=final_review)
    return ReviewResult(tuple(completed), run.record)


def ensure_sync_context() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise RuntimeError("An event loop is already running; await run_review_async instead.")


def run_review(user_input: str, client: AsyncLLMClient, **kwargs) -> ReviewResult:
    """Synchronous facade; client.complete must be async. Async callers await the core."""
    ensure_sync_context()
    return asyncio.run(run_review_async(user_input, client, **kwargs))
