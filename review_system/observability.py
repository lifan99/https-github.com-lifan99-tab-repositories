"""只输出允许字段组成的 JSON 事件；不记录提示词、模型正文或异常详情。"""

import json
import logging
import math
from uuid import UUID

LOGGER = logging.getLogger("review_system.events")
_ERRORS = {
    "model_error", "invalid_output", "callback_error", "network_timeout", "model_timeout",
    "total_timeout", "cancelled", "duplicate_request", "capacity_exceeded", "service_unavailable",
    "internal_error",
}
_STATUSES = {"running", "succeeded", "failed", "cancelled", "skipped", "rejected"}


def configure_logging():
    """每个进程只安装一次本包事件日志处理器，不改动全局根日志器。"""
    if not any(getattr(handler, "_review_events", False) for handler in LOGGER.handlers):
        handler = logging.StreamHandler()
        handler._review_events = True
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def log_event(*, review_id, stage=None, status, elapsed_ms=0, error_code=None):
    # 即使值来自内部流程，也校验注入客户端返回的异常错误码，
    # 避免供应商文本通过错误码等字段意外进入日志。
    """清洗标识、状态、错误码和耗时后记录事件；日志写入失败不影响审核结果。"""
    try:
        review_id = str(UUID(review_id)) if review_id is not None else None
    except (ValueError, TypeError, AttributeError):
        review_id = None
    if not isinstance(stage, str) or stage not in {"Analyst", "Critic", "Judge"}:
        stage = None
    if not isinstance(status, str) or status not in _STATUSES:
        status = "failed"
    if error_code is not None and (not isinstance(error_code, str) or error_code not in _ERRORS):
        error_code = "internal_error"
    try:
        valid_elapsed = type(elapsed_ms) in (int, float) and math.isfinite(elapsed_ms)
    except OverflowError:
        valid_elapsed = False
    if not valid_elapsed:
        elapsed_ms = 0
    event = {
        "review_id": review_id, "stage": stage, "status": status,
        "elapsed_ms": max(0, round(elapsed_ms)), "error_code": error_code,
    }
    try:
        LOGGER.info(json.dumps(event, ensure_ascii=False, allow_nan=False))
    except Exception:
        # 日志输出故障不能把已完成的审核变成模型调用失败。
        return
