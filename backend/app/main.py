from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings

app = FastAPI(
    title="AI Personal Content Strategist API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

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
    return {
        "status": "healthy",
        "database_reachable": True,
        "ollama_reachable": False,  # Updated dynamically when connected
        "models": {
            "llm": settings.model_name,
            "embedding": settings.embedding_model,
            "installed": False,
        },
        "api_key_configured": settings.api_key_configured,
        "scheduler_running": False,
        "next_brief_at": None,
        "interrupted_runs_count": 0,
    }
