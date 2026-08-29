from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.composition import AppContainer
from packages.harness_common.schemas.api import api_error
from packages.model.errors import ModelProviderError
from packages.security.auth import AuthError


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def install_http_contracts(app: FastAPI, *, component: str, container: AppContainer) -> None:
    @app.middleware("http")
    async def request_id_and_rpc_wal(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        if request.method in MUTATING_METHODS and response.status_code < 400:
            # RPC middleware 只记录请求消息投递意图，业务状态变更由 Service 层 WAL 负责。
            container.rpc_wal.append(
                request_id=request_id,
                scope="rpc_delivery",
                source=component,
                action=f"{request.method} {request.url.path}",
                payload={"path": request.url.path, "method": request.method},
                parent_request_id=request.headers.get("X-Parent-Request-ID"),
            )
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError):
        return JSONResponse(
            status_code=exc.status_code,
            content=api_error(
                code=exc.code,
                message=exc.message,
                status_code=exc.status_code,
                details=exc.details,
                trace_id=getattr(request.state, "request_id", None),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = str(exc.detail) if isinstance(exc.detail, str) else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=api_error(
                code=code,
                message=code,
                status_code=exc.status_code,
                trace_id=getattr(request.state, "request_id", None),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=api_error(
                code="validation_error",
                message="Request validation failed",
                status_code=422,
                details=exc.errors(),
                trace_id=getattr(request.state, "request_id", None),
            ),
        )

    @app.exception_handler(ModelProviderError)
    async def model_provider_error_handler(request: Request, exc: ModelProviderError):
        return JSONResponse(
            status_code=502,
            content=api_error(
                code="model_provider_error",
                message=exc.message,
                status_code=502,
                retryable=exc.retryable,
                details=exc.details,
                trace_id=getattr(request.state, "request_id", None),
            ),
        )
