"""Validated review data and immutable execution snapshots (contract v1)."""

import json
import re
from dataclasses import dataclass
from typing import Literal

MAX_INPUT_CHARS = 20_000
REVIEW_MODES = frozenset({"logic", "evidence"})
VERDICTS = frozenset({"pass", "needs_revision", "insufficient_evidence"})
SEVERITIES = frozenset({"low", "medium", "high"})


class ContractError(ValueError):
    """Invalid request or report; messages contain field paths, not input data."""


@dataclass(frozen=True)
class ReviewRequest:
    original_input: str
    review_mode: str = "logic"

    def __post_init__(self):
        if not isinstance(self.original_input, str):
            raise ContractError("original_input: must be a string.")
        if not self.original_input.strip():
            raise ContractError("original_input: Enter text, code, reasoning, or a proposal to review.")
        if len(self.original_input) > MAX_INPUT_CHARS:
            raise ContractError(f"original_input: Input must contain at most {MAX_INPUT_CHARS:,} characters.")
        _enum(self.review_mode, REVIEW_MODES, "review_mode")


@dataclass(frozen=True)
class Finding:
    category: str
    severity: str
    message: str
    suggestion: str
    start: int
    end: int
    quote: str


@dataclass(frozen=True)
class FinalReview:
    summary: str
    verdict: str
    findings: tuple[Finding, ...]
    limitations: tuple[str, ...]


StageStatus = Literal["pending", "running", "succeeded", "failed", "skipped", "cancelled"]
StageError = Literal[
    "model_error", "invalid_output", "callback_error", "network_timeout",
    "model_timeout", "total_timeout", "cancelled",
]


@dataclass(frozen=True)
class StageRecord:
    agent: str
    model: str
    status: StageStatus = "pending"
    raw_output: str | None = None
    error_code: StageError | None = None


@dataclass(frozen=True)
class ReviewRecord:
    request: ReviewRequest
    stages: tuple[StageRecord, ...]
    final_review: FinalReview | None = None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    error_code: StageError | None = None


def validate_review_request(original_input: str, review_mode: str = "logic") -> ReviewRequest:
    return ReviewRequest(original_input, review_mode)


def validate_request_id(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
        raise ContractError("request_id must contain 1–64 ASCII letters, digits, underscores or hyphens.")
    return value


def _text(value, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path}: must be a non-blank string.")
    return value


def _enum(value, allowed: frozenset[str], path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ContractError(f"{path}: must be one of {', '.join(sorted(allowed))}.")
    return value


def _object(value, fields: set[str], path: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError(f"{path}: must be an object.")
    if set(value) != fields:
        raise ContractError(f"{path}: expected exactly these fields: {', '.join(sorted(fields))}.")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("report: duplicate object field.")
        result[key] = value
    return result


def _reject_constant(value):
    raise ContractError("report: non-standard JSON numeric constant.")


def _finding(value, original_input: str, path: str) -> Finding:
    value = _object(value, {"category", "severity", "message", "suggestion", "start", "end", "quote"}, path)
    category = _enum(value["category"], REVIEW_MODES, f"{path}.category")
    severity = _enum(value["severity"], SEVERITIES, f"{path}.severity")
    message = _text(value["message"], f"{path}.message")
    suggestion = _text(value["suggestion"], f"{path}.suggestion")
    start, end = value["start"], value["end"]
    for field, coordinate in (("start", start), ("end", end)):
        if type(coordinate) is not int:
            raise ContractError(f"{path}.{field}: must be an integer, not a boolean.")
    if not 0 <= start < end <= len(original_input):
        raise ContractError(f"{path}.start/end: invalid quote range.")
    quote = _text(value["quote"], f"{path}.quote")
    if original_input[start:end] != quote:
        raise ContractError(f"{path}.quote: must match original_input[start:end].")
    return Finding(category, severity, message, suggestion, start, end, quote)


def parse_final_review(text: str, original_input: str) -> FinalReview:
    """Parse exact JSON without repairs; accept only the v1 report contract."""
    validate_review_request(original_input)
    _text(text, "report")
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except ContractError:
        raise
    except (ValueError, RecursionError) as exc:
        raise ContractError("report: must be a valid JSON document without extra text.") from exc
    payload = _object(payload, {"summary", "verdict", "findings", "limitations"}, "report")
    summary = _text(payload["summary"], "report.summary")
    verdict = _enum(payload["verdict"], VERDICTS, "report.verdict")
    for field in ("findings", "limitations"):
        if not isinstance(payload[field], list):
            raise ContractError(f"report.{field}: must be a list.")
    findings = tuple(
        _finding(item, original_input, f"report.findings[{index}]")
        for index, item in enumerate(payload["findings"])
    )
    limitations = tuple(
        _text(item, f"report.limitations[{index}]")
        for index, item in enumerate(payload["limitations"])
    )
    if verdict == "needs_revision" and not findings:
        raise ContractError("report.findings: needs_revision requires at least one finding.")
    if verdict == "pass" and any(item.severity == "high" for item in findings):
        raise ContractError("report.verdict: pass cannot include a high-severity finding.")
    if verdict == "insufficient_evidence" and not limitations:
        raise ContractError("report.limitations: insufficient_evidence requires a limitation.")
    return FinalReview(summary, verdict, findings, limitations)
