"""严格的 HTTP 数据模型；响应中不回传原始审核请求。

FindingDTO、ReportDTO 与 contracts 的领域对象保持字段及枚举一致。
DTO 负责结构和类型校验；引用与结论一致性由 contracts.parse_final_review 校验。
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import MAX_INPUT_CHARS, StageError, StageStatus, validate_request_id, validate_review_request

ExecutionMode = Literal["fake", "live"]
AgentName = Literal["Analyst", "Critic", "Judge"]
NonBlank = Annotated[str, Field(min_length=1, pattern=r"\S")]

# 服务端和界面客户端共用 HTTP 状态码与固定消息，避免返回供应商原始错误正文。
ERROR_SPECS = {
    "invalid_request": (422, "Request does not match the review contract."),
    "duplicate_request": (409, "A review with this request_id is still running."),
    "capacity_exceeded": (429, "Review capacity is currently full."),
    "model_error": (502, "The model provider request failed."),
    "invalid_output": (502, "The model report did not match the review contract."),
    "network_timeout": (504, "A model network operation timed out."),
    "model_timeout": (504, "The model call deadline was exceeded."),
    "total_timeout": (504, "The review total deadline was exceeded."),
    "internal_error": (500, "An internal review error occurred."),
    "service_unavailable": (503, "The review service is shutting down."),
}


class DTO(BaseModel):
    """公共严格模型：禁止类型强转及额外字段，同时允许从领域对象属性读取数据。"""
    model_config = ConfigDict(strict=True, extra="forbid", from_attributes=True)


class ReviewBody(DTO):
    """审核 HTTP 请求；校验字段结构后复用领域层的标识及原文规则。"""
    request_id: str = Field(min_length=1, max_length=64)
    original_input: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    review_mode: Literal["logic", "evidence"] = "logic"

    @field_validator("request_id")
    @classmethod
    def valid_id(cls, value):
        """复用领域层标识规则，避免 HTTP 与 Python 入口接受不同的 request_id。"""
        return validate_request_id(value)

    @model_validator(mode="after")
    def valid_request(self):
        """补充原文非空白等业务校验，保留原始输入及其引用坐标。"""
        validate_review_request(self.original_input, self.review_mode)
        return self


class ResponseDTO(DTO):
    """已接收的角色回答；只允许三个已知角色，模型名和回答不得为空白。"""
    agent: AgentName
    model: NonBlank
    content: NonBlank


class StageDTO(DTO):
    """公开的阶段状态、错误码和原始输出，失败时也能展示进度。"""
    agent: AgentName
    model: NonBlank
    status: StageStatus
    error_code: StageError | None
    raw_output: str | None


class FindingDTO(DTO):
    """发现的传输结构；原文范围匹配和跨字段规则仍需领域层校验。"""
    category: Literal["logic", "evidence"]
    severity: Literal["low", "medium", "high"]
    message: NonBlank
    suggestion: NonBlank
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: NonBlank


class ReportDTO(DTO):
    """结构化报告的传输表示，与 FinalReview 的字段及枚举保持同步。"""
    summary: NonBlank
    verdict: Literal["pass", "needs_revision", "insufficient_evidence"]
    findings: tuple[FindingDTO, ...]
    limitations: tuple[NonBlank, ...]


class ErrorDTO(DTO):
    """公开错误结构；消息来自固定映射，stage 可为空以表示尚未进入具体角色。"""
    code: Literal[
        "invalid_request", "duplicate_request", "capacity_exceeded", "model_error",
        "invalid_output", "network_timeout", "model_timeout", "total_timeout",
        "internal_error", "service_unavailable",
    ]
    message: NonBlank
    stage: AgentName | None = None


class Envelope(DTO):
    """响应公共字段；仅携带标识、模式、回答及阶段，不嵌入原始请求。"""
    request_id: str | None
    review_id: str | None
    execution_mode: ExecutionMode
    responses: tuple[ResponseDTO, ...] = ()
    stages: tuple[StageDTO, ...] = ()


class SuccessResponse(Envelope):
    """成功响应必须包含完整、有序的三角色回答及三个成功阶段。"""
    request_id: str
    review_id: str
    status: Literal["succeeded"] = "succeeded"
    final_review: ReportDTO
    error: None = None

    @model_validator(mode="after")
    def complete(self):
        """拒绝缺少角色、角色乱序、非成功阶段或残留错误码的成功响应。"""
        expected = ["Analyst", "Critic", "Judge"]
        if [item.agent for item in self.responses] != expected:
            raise ValueError("Successful review must contain all three responses in order.")
        if [item.agent for item in self.stages] != expected or any(
            item.status != "succeeded" or item.error_code is not None for item in self.stages
        ):
            raise ValueError("Successful review must contain three successful stages.")
        return self


class FailureResponse(Envelope):
    """区分准入前拒绝与执行中失败；失败时允许返回已有的部分回答。"""
    status: Literal["rejected", "failed"]
    final_review: None = None
    error: ErrorDTO

    @model_validator(mode="after")
    def consistent_rejection(self):
        """检查标识与状态一致性，部分回答必须是三角色顺序的前缀。"""
        if self.status == "rejected" and (self.review_id is not None or self.responses or self.stages):
            raise ValueError("Rejected requests cannot contain a review or its results.")
        if self.status == "failed" and self.review_id is None:
            raise ValueError("Failed reviews must retain their review ID.")
        expected = ["Analyst", "Critic", "Judge"]
        if [item.agent for item in self.responses] != expected[:len(self.responses)]:
            raise ValueError("Partial responses must be an ordered prefix.")
        if self.stages and [item.agent for item in self.stages] != expected:
            raise ValueError("Stage records must include all three roles in order.")
        if self.status == "failed" and self.error.code != "internal_error" and len(self.stages) != 3:
            raise ValueError("Failed reviews must retain their stage records.")
        return self


class HealthResponse(DTO):
    """健康检查的最小响应，明确标出 fake 或 live 模式。"""
    status: Literal["ok"] = "ok"
    execution_mode: ExecutionMode
