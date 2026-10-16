"""Small allowlisted JSON event stream; never log prompts, outputs or exceptions."""

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
    """Configure only this package's event logger, once per process."""
    if not any(getattr(handler, "_review_events", False) for handler in LOGGER.handlers):
        handler = logging.StreamHandler()
        handler._review_events = True
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def log_event(*, review_id, stage=None, status, elapsed_ms=0, error_code=None):
    # These values originate in control flow. Sanitize unexpected injected client
    # codes too, so they cannot become an accidental channel for provider text.
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
        # A broken log sink must not turn a completed review into a model failure.
        return
