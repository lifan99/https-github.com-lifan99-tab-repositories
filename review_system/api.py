"""Local, single-worker HTTP application. No configuration is read on import."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .api_models import (
    ERROR_SPECS,
    ErrorDTO,
    FailureResponse,
    HealthResponse,
    ReportDTO,
    ResponseDTO,
    ReviewBody,
    StageDTO,
    SuccessResponse,
)
from .clients import AsyncOpenAICompatibleClient
from .config import Settings
from .environment import load_project_env
from .fakes import DemoClient
from .observability import configure_logging
from .runtime import create_http_client
from .service import ReviewService, ServiceError


@asynccontextmanager
async def default_resources():
    load_project_env()
    mode = os.getenv("REVIEW_EXECUTION_MODE", "live").strip().lower()
    if mode not in {"live", "fake"}:
        raise ValueError("REVIEW_EXECUTION_MODE must be live or fake.")
    if mode == "fake":
        settings = Settings("fake", "https://example.invalid", "", "fake", "fake-analyst", "fake-critic", "fake-judge")
        yield mode, DemoClient(), settings
    else:
        settings = Settings.from_env()
        async with create_http_client(settings) as http:
            yield mode, AsyncOpenAICompatibleClient(settings, http), settings


def error_response(mode, code, *, request_id=None, review_id=None, run=None):
    code = code if code in ERROR_SPECS else "internal_error"
    status_code, message = ERROR_SPECS[code]
    record = run.record if run else None
    stage = next((item.agent for item in record.stages if item.status == "failed"), None) if record else None
    body = FailureResponse(
        request_id=request_id, review_id=review_id, execution_mode=mode,
        status="failed" if review_id is not None else "rejected",
        responses=tuple(ResponseDTO.model_validate(item) for item in run.responses) if run else (),
        stages=tuple(StageDTO.model_validate(item) for item in record.stages) if record else (),
        error=ErrorDTO(code=code, message=message, stage=stage),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def create_app(*, resources_factory=None) -> FastAPI:
    """Inject an async context manager yielding (execution_mode, client, settings)."""
    factory = resources_factory or default_resources

    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        async with factory() as (mode, client, settings):
            # Validate mode before publishing resources or accepting requests.
            HealthResponse(execution_mode=mode)
            service = ReviewService(client, settings)
            app.state.execution_mode = mode
            app.state.service = service
            try:
                yield
            finally:
                await service.aclose()

    app = FastAPI(title="Local Multi-Agent Review", version="1.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return error_response(request.app.state.execution_mode, "invalid_request")

    @app.exception_handler(HTTPException)
    async def malformed_body(request, exc):
        # Invalid JSON bytes fail before Pydantic and are reported as HTTP 400
        # by the framework. Normalize only this endpoint's body rejection.
        if exc.status_code == 400 and request.method == "POST" and request.url.path == "/api/v1/reviews":
            return error_response(request.app.state.execution_mode, "invalid_request")
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        # Never serialize exception text, stack traces, request bodies or credentials.
        return error_response(
            request.app.state.execution_mode, "internal_error",
            request_id=getattr(request.state, "request_id", None),
            review_id=getattr(request.state, "review_id", None),
        )

    @app.get("/healthz", response_model=HealthResponse)
    async def health(request: Request):
        return HealthResponse(execution_mode=request.app.state.execution_mode)

    @app.post(
        "/api/v1/reviews", status_code=201, response_model=SuccessResponse,
        responses={status: {"model": FailureResponse} for status in (409, 422, 429, 500, 502, 503, 504)},
    )
    async def review(body: ReviewBody, request: Request):
        request.state.request_id = body.request_id
        mode = request.app.state.execution_mode
        try:
            accepted = await request.app.state.service.review(
                body.request_id, body.original_input, body.review_mode,
            )
        except ServiceError as exc:
            request.state.review_id = exc.review_id
            return error_response(
                mode, exc.code, request_id=body.request_id, review_id=exc.review_id, run=exc.run,
            )
        request.state.review_id = accepted.review_id
        result = accepted.result
        return SuccessResponse(
            request_id=body.request_id, review_id=accepted.review_id, execution_mode=mode,
            responses=tuple(ResponseDTO.model_validate(item) for item in result.responses),
            stages=tuple(StageDTO.model_validate(item) for item in result.record.stages),
            final_review=ReportDTO.model_validate(result.record.final_review),
        )

    return app
