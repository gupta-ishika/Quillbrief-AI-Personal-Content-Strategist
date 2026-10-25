from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.errors import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
)
from app.api.v1 import v1_router
from app.config import settings
from app.db.session import SessionLocal
from app.scheduler import start_scheduler, stop_scheduler, sync_weekly_brief_job
from app.services.health import get_health_status


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    start_scheduler()
    try:
        with SessionLocal() as db:
            sync_weekly_brief_job(db)
    except Exception:
        pass
    yield
    stop_scheduler()


app = FastAPI(
    title="AI Personal Content Strategist API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next: Any) -> Response:
    # 1. Host check (block DNS rebinding)
    host = request.headers.get("host", "")
    allowed_hosts = [
        f"localhost:{settings.backend_port}",
        f"127.0.0.1:{settings.backend_port}",
        # Also allow without port if port 80/default or during certain client calls
        "localhost",
        "127.0.0.1",
    ]
    if host not in allowed_hosts and not host.startswith("testserver"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "INVALID_HOST",
                    "message": f"Host '{host}' is not permitted.",
                    "details": {},
                }
            },
        )

    # 2. Origin & Content-Type check for state-changing requests (except OAuth callback)
    if request.method in ("POST", "PUT", "DELETE"):
        # Exempt OAuth callback which is a browser GET/POST if any, but our callback is GET
        origin = request.headers.get("origin")
        if origin and origin != settings.frontend_origin and not host.startswith("testserver"):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": {
                        "code": "ORIGIN_NOT_ALLOWED",
                        "message": f"Origin '{origin}' is not permitted.",
                        "details": {},
                    }
                },
            )

        content_type = request.headers.get("content-type", "")
        # Require application/json if there is a body
        if (
            request.headers.get("content-length")
            and int(request.headers.get("content-length", 0)) > 0
        ):
            if not content_type.startswith("application/json"):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "error": {
                            "code": "INVALID_CONTENT_TYPE",
                            "message": "Content-Type must be application/json.",
                            "details": {},
                        }
                    },
                )

    response: Response = await call_next(request)
    return response


@app.get("/health")
@app.get("/api/v1/health")
async def health_check() -> dict[str, Any]:
    return await get_health_status()


app.include_router(v1_router)
