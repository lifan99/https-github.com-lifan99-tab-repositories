"""Strict HTTP DTOs; deliberately exclude the original request from responses."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import MAX_INPUT_CHARS, StageError, StageStatus, validate_request_id, validate_review_request

ExecutionMode = Literal["fake", "live"]
AgentName = Literal["Analyst", "Critic", "Judge"]
NonBlank = Annotated[str, Field(min_length=1, pattern=r"\S")]

# One public mapping shared by server and UI client. Never expose provider text.
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
    model_config = ConfigDict(strict=True, extra="forbid", from_attributes=True)


class ReviewBody(DTO):
    request_id: str = Field(min_length=1, max_length=64)
    original_input: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    review_mode: Literal["logic", "evidence"] = "logic"

    @field_validator("request_id")
    @classmethod
    def valid_id(cls, value):
        return validate_request_id(value)

    @model_validator(mode="after")
    def valid_request(self):
        validate_review_request(self.original_input, self.review_mode)
        return self


class ResponseDTO(DTO):
    agent: AgentName
    model: NonBlank
    content: NonBlank


class StageDTO(DTO):
    agent: AgentName
    model: NonBlank
    status: StageStatus
    error_code: StageError | None
    raw_output: str | None


class FindingDTO(DTO):
    category: Literal["logic", "evidence"]
    severity: Literal["low", "medium", "high"]
    message: NonBlank
    suggestion: NonBlank
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: NonBlank


class ReportDTO(DTO):
    summary: NonBlank
    verdict: Literal["pass", "needs_revision", "insufficient_evidence"]
    findings: tuple[FindingDTO, ...]
    limitations: tuple[NonBlank, ...]


class ErrorDTO(DTO):
    code: Literal[
        "invalid_request", "duplicate_request", "capacity_exceeded", "model_error",
        "invalid_output", "network_timeout", "model_timeout", "total_timeout",
        "internal_error", "service_unavailable",
    ]
    message: NonBlank
    stage: AgentName | None = None


class Envelope(DTO):
    request_id: str | None
    review_id: str | None
    execution_mode: ExecutionMode
    responses: tuple[ResponseDTO, ...] = ()
    stages: tuple[StageDTO, ...] = ()


class SuccessResponse(Envelope):
    request_id: str
    review_id: str
    status: Literal["succeeded"] = "succeeded"
    final_review: ReportDTO
    error: None = None

    @model_validator(mode="after")
    def complete(self):
        expected = ["Analyst", "Critic", "Judge"]
        if [item.agent for item in self.responses] != expected:
            raise ValueError("Successful review must contain all three responses in order.")
        if [item.agent for item in self.stages] != expected or any(
            item.status != "succeeded" or item.error_code is not None for item in self.stages
        ):
            raise ValueError("Successful review must contain three successful stages.")
        return self


class FailureResponse(Envelope):
    status: Literal["rejected", "failed"]
    final_review: None = None
    error: ErrorDTO

    @model_validator(mode="after")
    def consistent_rejection(self):
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
    status: Literal["ok"] = "ok"
    execution_mode: ExecutionMode
