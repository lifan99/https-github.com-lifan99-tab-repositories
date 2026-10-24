"""审核请求、报告校验与不可变执行快照，遵循 v1 数据契约。

Finding、FinalReview 的字段和枚举与 api_models 中的 DTO 对应，修改时需同步两处及边界测试。
本模块负责依赖原文的引用校验，以及结论与发现、限制之间的跨字段规则。
"""

import json
import re
from dataclasses import dataclass
from typing import Literal

MAX_INPUT_CHARS = 20_000
REVIEW_MODES = frozenset({"logic", "evidence"})
VERDICTS = frozenset({"pass", "needs_revision", "insufficient_evidence"})
SEVERITIES = frozenset({"low", "medium", "high"})


class ContractError(ValueError):
    """请求或报告不符合契约；错误只描述字段路径，不拼接原始输入。"""


@dataclass(frozen=True)
class ReviewRequest:
    """已校验的原始输入和审核模式；保留原文，避免改变后续引用位置。"""
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
    """一条问题及修改建议；start、end 是原文中左闭右开的字符区间。"""
    category: str
    severity: str
    message: str
    suggestion: str
    start: int
    end: int
    quote: str


@dataclass(frozen=True)
class FinalReview:
    """经校验的最终报告；元组及冻结对象使已发布结果不被后续修改。"""
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
    """单个角色的执行快照；失败时仍可保留原始输出供排查。"""
    agent: str
    model: str
    status: StageStatus = "pending"
    raw_output: str | None = None
    error_code: StageError | None = None


@dataclass(frozen=True)
class ReviewRecord:
    """整次审核快照；仅在全部阶段及回调成功后填入 final_review。"""
    request: ReviewRequest
    stages: tuple[StageRecord, ...]
    final_review: FinalReview | None = None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    error_code: StageError | None = None


def validate_review_request(original_input: str, review_mode: str = "logic") -> ReviewRequest:
    """统一的请求校验入口，供工作流、服务及 HTTP 层复用。"""
    return ReviewRequest(original_input, review_mode)


def validate_request_id(value: str) -> str:
    """请求标识限 1～64 个 ASCII 字母、数字、下划线或连字符。"""
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
        raise ContractError("request_id must contain 1–64 ASCII letters, digits, underscores or hyphens.")
    return value


def _text(value, path: str) -> str:
    """要求非空白字符串；只用 strip 判断，不改变返回文本。"""
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path}: must be a non-blank string.")
    return value


def _enum(value, allowed: frozenset[str], path: str) -> str:
    """严格校验字符串枚举，不做类型转换。"""
    if not isinstance(value, str) or value not in allowed:
        raise ContractError(f"{path}: must be one of {', '.join(sorted(allowed))}.")
    return value


def _object(value, fields: set[str], path: str) -> dict:
    """要求对象字段集合完全匹配，同时拒绝缺少字段和额外字段。"""
    if not isinstance(value, dict):
        raise ContractError(f"{path}: must be an object.")
    if set(value) != fields:
        raise ContractError(f"{path}: expected exactly these fields: {', '.join(sorted(fields))}.")
    return value


def _unique_object(pairs):
    """在 JSON 解析阶段拒绝重复键，避免普通字典静默覆盖同名字段。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("report: duplicate object field.")
        result[key] = value
    return result


def _reject_constant(value):
    """拒绝 Python JSON 解码器默认允许的 NaN、Infinity 等非标准常量。"""
    raise ContractError("report: non-standard JSON numeric constant.")


def _finding(value, original_input: str, path: str) -> Finding:
    """严格校验问题字段、引用范围及原文匹配关系，再构造不可变记录。"""
    value = _object(value, {"category", "severity", "message", "suggestion", "start", "end", "quote"}, path)
    category = _enum(value["category"], REVIEW_MODES, f"{path}.category")
    severity = _enum(value["severity"], SEVERITIES, f"{path}.severity")
    message = _text(value["message"], f"{path}.message")
    suggestion = _text(value["suggestion"], f"{path}.suggestion")
    start, end = value["start"], value["end"]
    for field, coordinate in (("start", start), ("end", end)):
        # bool 也是 int 的子类，必须用精确类型比较拒绝布尔坐标。
        if type(coordinate) is not int:
            raise ContractError(f"{path}.{field}: must be an integer, not a boolean.")
    if not 0 <= start < end <= len(original_input):
        raise ContractError(f"{path}.start/end: invalid quote range.")
    quote = _text(value["quote"], f"{path}.quote")
    # 按 Unicode 码点切片核对；不能使用 UTF-8 字节位置，也不能先清理原文。
    if original_input[start:end] != quote:
        raise ContractError(f"{path}.quote: must match original_input[start:end].")
    return Finding(category, severity, message, suggestion, start, end, quote)


def parse_final_review(text: str, original_input: str) -> FinalReview:
    """按 v1 契约解析完整 JSON；不剥离代码围栏、不修复引用，也不补全字段。"""
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
    # 字段各自合法还不够：结论必须与问题严重程度及限制说明一致。
    if verdict == "needs_revision" and not findings:
        raise ContractError("report.findings: needs_revision requires at least one finding.")
    if verdict == "pass" and any(item.severity == "high" for item in findings):
        raise ContractError("report.verdict: pass cannot include a high-severity finding.")
    if verdict == "insufficient_evidence" and not limitations:
        raise ContractError("report.limitations: insufficient_evidence requires a limitation.")
    return FinalReview(summary, verdict, findings, limitations)
