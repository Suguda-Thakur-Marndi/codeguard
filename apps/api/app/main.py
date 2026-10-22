"""Main FastAPI application entry point."""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import CodeGuardException
from app.core.logging import logger, redact_sensitive_data, request_id_ctx


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces baseline OWASP security headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )
        if settings.APP_ENV == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        return response


MAX_BODY_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB payload limit


class MaxPayloadSizeMiddleware(BaseHTTPMiddleware):
    """Rejects incoming HTTP requests with Content-Length exceeding the configured threshold."""

    def __init__(self, app: FastAPI, max_bytes: int = MAX_BODY_SIZE_BYTES):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                length = int(content_length)
                if length > self.max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": f"Request entity exceeds the maximum allowed size of {self.max_bytes} bytes",
                            }
                        },
                    )
            except ValueError:
                pass
        return await call_next(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attaches unique X-Request-ID and tracks request lifecycle with structured logging."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx.set(req_id)
        start_time = time.perf_counter()

        logger.info(
            f"HTTP {request.method} {request.url.path}",
            extra={
                "event": "http_request_started",
                "extra_fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": request.client.host if request.client else None,
                },
            },
        )

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            response.headers["X-Request-ID"] = req_id

            logger.info(
                f"HTTP {request.method} {request.url.path} -> {response.status_code} in {duration_ms:.2f}ms",
                extra={
                    "event": "http_request_completed",
                    "duration_ms": duration_ms,
                    "extra_fields": {
                        "status_code": response.status_code,
                        "method": request.method,
                        "path": request.url.path,
                    },
                },
            )
            return response
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(
                f"HTTP {request.method} {request.url.path} failed in {duration_ms:.2f}ms: {exc}",
                extra={
                    "event": "http_request_failed",
                    "duration_ms": duration_ms,
                },
                exc_info=True,
            )
            raise
        finally:
            request_id_ctx.reset(token)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and shutdown hooks."""
    logger.info(
        f"Starting CodeGuard AI API [env={settings.APP_ENV}, debug={settings.DEBUG}]",
        extra={"event": "application_startup"},
    )
    yield
    logger.info("Shutting down CodeGuard AI API", extra={"event": "application_shutdown"})


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title="CodeGuard AI API",
        description="Production-grade agentic GitHub Pull Request review platform API (Phase 1)",
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.APP_ENV != "production" else None,
        redoc_url="/redoc" if settings.APP_ENV != "production" else None,
        lifespan=lifespan,
    )

    # 0. Request payload size cap
    app.add_middleware(MaxPayloadSizeMiddleware)

    # 1. Security Headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. Request context & timing middleware
    app.add_middleware(RequestContextMiddleware)

    # 3. CORS Configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
        allow_headers=["*"],
    )

    # 4. Exception Handlers
    @app.exception_handler(CodeGuardException)
    async def codeguard_exception_handler(
        request: Request, exc: CodeGuardException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": redact_sensitive_data(exc.message),
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(f"Unhandled server error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected internal error occurred",
                }
            },
        )

    # 5. Master Router Mount
    app.include_router(api_v1_router)

    # Root landing endpoint
    @app.get("/", tags=["System"])
    def root() -> dict:
        return {
            "name": "CodeGuard AI API",
            "version": settings.APP_VERSION,
            "phase": "Phase 1 - Production Foundation",
            "release_phase": "Phase 8 - Production Release",
            "environment": settings.APP_ENV,
            "docs": "/docs" if settings.APP_ENV != "production" else "disabled",
            "health": "/api/v1/health",
            "live": "/api/v1/live",
            "ready": "/api/v1/ready",
        }

    return app


app = create_app()
