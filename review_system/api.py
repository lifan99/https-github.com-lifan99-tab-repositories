"""本地单 worker 的 HTTP 应用工厂；导入时不加载配置或创建网络资源。"""

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
    """按显式模式提供客户端及配置；live 配置失败会阻止启动，不自动切到 fake。"""
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
    """按公开错误表构造稳定响应；保留已完成回答和阶段快照，不回传异常正文。"""
    code = code if code in ERROR_SPECS else "internal_error"
    status_code, message = ERROR_SPECS[code]
    record = run.record if run else None
    # 总预算可能在首个阶段开始前耗尽，此时没有失败角色，stage 为 None。
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
    """创建应用；可注入异步上下文管理器，产出执行模式、客户端和配置以便离线测试。"""
    factory = resources_factory or default_resources

    @asynccontextmanager
    async def lifespan(app):
        """启动时发布共享资源；关闭时先清理审核任务，再退出客户端资源上下文。"""
        configure_logging()
        async with factory() as (mode, client, settings):
            # 在发布共享资源及接收请求前校验执行模式。
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
        """统一处理请求结构或类型错误，不把框架的原始校验详情返回给调用方。"""
        return error_response(request.app.state.execution_mode, "invalid_request")

    @app.exception_handler(HTTPException)
    async def malformed_body(request, exc):
        # 非法 JSON 字节可能在 Pydantic 校验前被框架报为 HTTP 400；
        # 仅归一化审核端点的正文错误，保留其他端点原有的异常行为。
        """将本审核端点的非法正文统一映射为契约错误，其余 HTTP 异常沿用框架处理。"""
        if exc.status_code == 400 and request.method == "POST" and request.url.path == "/api/v1/reviews":
            return error_response(request.app.state.execution_mode, "invalid_request")
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        # 不序列化异常文本、调用栈、请求正文或认证信息。
        """为未预期异常返回通用错误，并保留已知的请求及审核标识。"""
        return error_response(
            request.app.state.execution_mode, "internal_error",
            request_id=getattr(request.state, "request_id", None),
            review_id=getattr(request.state, "review_id", None),
        )

    @app.get("/healthz", response_model=HealthResponse)
    async def health(request: Request):
        """报告应用存活状态和显式执行模式；不探测外部模型连通性。"""
        return HealthResponse(execution_mode=request.app.state.execution_mode)

    @app.post(
        "/api/v1/reviews", status_code=201, response_model=SuccessResponse,
        responses={status: {"model": FailureResponse} for status in (409, 422, 429, 500, 502, 503, 504)},
    )
    async def review(body: ReviewBody, request: Request):
        """提交后等待整次审核结束；成功返回三个阶段及最终报告，失败保留部分结果。"""
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
