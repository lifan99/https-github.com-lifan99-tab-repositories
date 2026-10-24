"""在单个事件循环中统一管理审核准入、活动请求标识和子任务；不依赖 HTTP 或界面。"""

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from .clients import AsyncLLMClient
from .config import Settings
from .contracts import validate_request_id, validate_review_request
from .observability import log_event
from .workflow import ReviewResult, ReviewRun, WorkflowError, run_review_async


class ServiceError(RuntimeError):
    """服务层稳定错误码；已准入的审核失败时附带审核标识及运行快照。"""
    def __init__(self, code: str, *, review_id: str | None = None, run: ReviewRun | None = None):
        super().__init__(code)
        self.code = code
        self.review_id = review_id
        self.run = run


@dataclass(frozen=True)
class ServiceResult:
    """服务生成的审核标识与业务工作流成功结果。"""
    review_id: str
    result: ReviewResult


class ReviewService:
    """单实例审核服务；同一事件循环内至多接纳两份审核，满载立即拒绝。"""
    CAPACITY = 2

    def __init__(self, client: AsyncLLMClient, settings: Settings):
        self.client = client
        self.settings = settings
        self._active: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._closing = False

    @property
    def active_count(self) -> int:
        """当前已准入且尚未释放标识的审核数量。"""
        return len(self._active)

    @property
    def task_count(self) -> int:
        """服务仍持有的子任务数量，包括等待准入判断的任务。"""
        return len(self._tasks)

    async def review(self, request_id: str, original_input: str, review_mode: str = "logic") -> ServiceResult:
        """先校验请求再创建服务持有的子任务；调用方取消时等待子任务清理。"""
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
            # await 子任务会传播调用方的取消；移除持有关系前仍需收集任务，
            # 包括任务创建后尚未执行第一步就被取消的情况。
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self._tasks.discard(task)

    async def _execute(self, request_id, original_input, review_mode, deadline):
        """按关闭状态、重复标识、容量顺序准入，再运行审核并统一转换错误。"""
        def reject(code):
            log_event(review_id=None, status="rejected", error_code=code)
            return ServiceError(code)

        # 这些判断及随后占用标识之间没有 await，因此在单个事件循环中不会交错准入。
        # 活动标识只负责执行期间去重；审核结束后同一 request_id 可以再次执行。
        if self._closing:
            raise reject("service_unavailable")
        if request_id in self._active:
            raise reject("duplicate_request")
        if len(self._active) >= self.CAPACITY:
            raise reject("capacity_exceeded")
        # request_id 由调用方提供用于执行期间去重；review_id 由服务为本次执行生成。
        review_id = str(uuid4())
        run = ReviewRun()
        started = deadline - self.settings.total_timeout_seconds

        def event(status, code=None):
            log_event(review_id=review_id, status=status, error_code=code,
                      elapsed_ms=(asyncio.get_running_loop().time() - started) * 1000)

        self._active.add(request_id)
        try:
            event("running")
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
        # 成功、失败与取消均释放容量，允许后续审核复用名额。
        finally:
            self._active.remove(request_id)

    async def aclose(self):
        """阻止新请求，取消并收集全部已持有子任务，再由外层关闭 HTTP 客户端。"""
        self._closing = True
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.difference_update(tasks)
