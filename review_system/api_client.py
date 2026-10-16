"""Synchronous HTTP consumer for Streamlit; no provider credentials or model calls."""

import os
from dataclasses import dataclass
from uuid import UUID

import httpx
from pydantic import ValidationError

from .api_models import ERROR_SPECS, FailureResponse, ReportDTO, ReviewBody, SuccessResponse
from .config import env_seconds, validate_base_url, validate_seconds
from .contracts import parse_final_review


@dataclass(frozen=True)
class APISettings:
    base_url: str = "http://127.0.0.1:8000"
    timeout_seconds: float = 180

    def __post_init__(self):
        validate_base_url(self.base_url, "REVIEW_API_BASE_URL")
        validate_seconds(self.timeout_seconds, "REVIEW_API_TIMEOUT_SECONDS")

    @classmethod
    def from_env(cls):
        total = env_seconds("REVIEW_TOTAL_TIMEOUT_SECONDS", "150")
        timeout = env_seconds("REVIEW_API_TIMEOUT_SECONDS", str(total + 30))
        if timeout <= total:
            raise ValueError("REVIEW_API_TIMEOUT_SECONDS must exceed REVIEW_TOTAL_TIMEOUT_SECONDS.")
        return cls(os.getenv("REVIEW_API_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/"), timeout)


class APIClientError(RuntimeError):
    """The caller has no trustworthy completed response; do not retry automatically."""


class ReviewAPIClient:
    def __init__(self, settings: APISettings, http_client: httpx.Client):
        self.settings = settings
        self.http_client = http_client

    def review(self, request_id: str, original_input: str, review_mode="logic") -> SuccessResponse | FailureResponse:
        body = ReviewBody(request_id=request_id, original_input=original_input, review_mode=review_mode)
        try:
            response = self.http_client.post(
                self.settings.base_url.rstrip("/") + "/api/v1/reviews",
                json=body.model_dump(), timeout=self.settings.timeout_seconds, follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise APIClientError("Waiting for the review service timed out. The server may still be processing this request.") from exc
        except httpx.RequestError as exc:
            raise APIClientError("Could not obtain a response from the review service. Check that the local API is running.") from exc
        try:
            if response.status_code == 201:
                result = SuccessResponse.model_validate_json(response.content)
                if result.request_id != request_id:
                    raise ValueError("Mismatched request ID")
                UUID(result.review_id)
                for answer, stage in zip(result.responses, result.stages, strict=True):
                    if answer.model != stage.model or answer.content != stage.raw_output:
                        raise ValueError("Response/stage mismatch")
                report = parse_final_review(result.responses[-1].content, original_input)
                if ReportDTO.model_validate(report) != result.final_review:
                    raise ValueError("Final report mismatch")
                return result
            result = FailureResponse.model_validate_json(response.content)
            if ERROR_SPECS[result.error.code][0] != response.status_code:
                raise ValueError("Status/error mismatch")
            expected_id = None if result.error.code == "invalid_request" else request_id
            if result.request_id != expected_id:
                raise ValueError("Mismatched request ID")
            if result.review_id is not None:
                UUID(result.review_id)
            return result
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            raise APIClientError("The review service returned an invalid response. No result was published.") from exc


def submit_review(request_id, original_input, *, review_mode="logic", settings=None):
    settings = settings or APISettings.from_env()
    with httpx.Client(trust_env=False, follow_redirects=False) as http:
        return ReviewAPIClient(settings, http).review(request_id, original_input, review_mode)
