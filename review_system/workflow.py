"""审核的唯一异步业务内核：顺序执行三个角色，保存不可变快照，并提供同步入口。"""

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
    """单个角色已接收的回答，包含实际使用的模型名称。"""
    agent: str
    model: str
    content: str


@dataclass(frozen=True)
class ReviewResult:
    """成功完成的审核结果，兼有原始回答和通过契约校验的报告快照。"""
    responses: tuple[AgentResponse, ...]
    record: ReviewRecord

    @property
    def final_response(self) -> str:
        """返回 Judge 的原始 JSON 文本；结构化报告位于 record.final_review。"""
        return self.responses[-1].content


@dataclass
class ReviewRun:
    """单次运行句柄；调用方在取消或失败后仍可读取最后快照和已接收回答。"""

    record: ReviewRecord | None = field(default=None, init=False)
    responses: tuple[AgentResponse, ...] = field(default=(), init=False)
    _started: bool = field(default=False, init=False, repr=False)


class WorkflowError(RuntimeError):
    """工作流失败，携带失败角色、已接收回答及最后状态快照。"""
    def __init__(self, agent: str, cause: Exception, completed: tuple[AgentResponse, ...], record: ReviewRecord):
        super().__init__(f"{agent} failed: {cause}")
        self.agent = agent
        self.completed = completed
        self.record = record


class _TotalTimeout(Exception):
    """用于显式检查总截止时间的内部异常。"""
    pass


class _CallbackFailure(Exception):
    """区分展示回调失败与模型调用失败，避免向外暴露回调异常详情。"""
    pass


async def _model_call(client, model, messages, seconds):
    """对一次模型调用施加独立截止时间，并拒绝已经超时才返回的结果。"""
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
        # 即使客户端吞掉定时器触发的取消，或阻塞循环后才返回，也不能发布超时结果。
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
    """按 Analyst、Critic、Judge 顺序审核；不同审核可共享客户端和容量信号量。

    总预算包含排队、模型调用及同步回调耗时；total_deadline 可进一步缩短预算。
    run 只可使用一次。失败通过 WorkflowError 保留快照，取消则更新快照后继续抛出 CancelledError。
    """
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
    # 用单调时钟固定本次截止时间，不在切换角色或获得名额后重新计时。
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
        """替换运行快照，并仅在阶段状态变化时记录事件，避免重复日志。"""
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
        """显式检查单调时钟，覆盖同步代码阻塞导致定时取消来不及触发的情况。"""
        if loop.time() >= deadline:
            raise _TotalTimeout()

    def stop(code, cause):
        """统一终止状态：当前阶段失败或取消，尚未开始的阶段跳过，保留已有回答。"""
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
        """错误发生时若总预算已耗尽，优先归类为整次审核超时。"""
        if loop.time() >= deadline:
            return stop("total_timeout", RuntimeError("Review total deadline exceeded."))
        return stop(code, cause)

    snapshot("queued")
    total_scope = asyncio.timeout_at(deadline)
    try:
        async with total_scope:
            # 将名额等待放在总预算内；异步上下文确保仅释放实际获得的名额。
            async with (slots if slots is not None else nullcontext()):
                check_deadline()
                snapshot("running")
                for index, (agent, model) in enumerate(assignments):
                    check_deadline()
                    stages[index] = replace(stages[index], status="running")
                    snapshot("running")
                    # 每次调用重新序列化本次审核的上下文；后续角色才能看到前序回答。
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
                    # 先保存文本原始输出，即使 Judge 的格式非法，也能在失败快照中查看。
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
                    # 回答先进入快照再调用同步回调；回调失败保留回答，并停止后续角色。
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
    # 取消属于任务控制信号；保存状态后原样抛出，供上层取消和清理继续传播。
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
    # 只有所有阶段、回调及最后期限检查都通过，才发布可使用的最终报告。
    snapshot("succeeded", report=final_review)
    return ReviewResult(tuple(completed), run.record)


def ensure_sync_context() -> None:
    """同步入口不能嵌套运行中的事件循环；异步调用方应直接 await 业务内核。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise RuntimeError("An event loop is already running; await run_review_async instead.")


def run_review(user_input: str, client: AsyncLLMClient, **kwargs) -> ReviewResult:
    """同步薄封装；传入客户端仍须提供异步 complete，异步调用方直接 await 内核。"""
    ensure_sync_context()
    return asyncio.run(run_review_async(user_input, client, **kwargs))
