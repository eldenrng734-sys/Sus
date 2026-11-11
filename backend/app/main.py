import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.modules.auth.errors import AuthError
from app.modules.auth.router import router as auth_router
from app.modules.teams.router import router as teams_router
from app.modules.leads.router import router as leads_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api.request")

app = FastAPI(title="AI Sales Assistant CRM", version="0.1.0")


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    raw_request_id = request.headers.get("X-Request-ID")

    try:
        request_id = str(uuid.UUID(raw_request_id)) if raw_request_id else str(uuid.uuid4())
    except (ValueError, TypeError, AttributeError):
        request_id = str(uuid.uuid4())

    request.state.request_id = request_id
    start_time = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "api_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status_code,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": request_id,
            }
        },
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(teams_router)
app.include_router(leads_router)


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
    return error_response(request, exc.status_code, exc.code, exc.message)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    messages = {
        400: ("bad_request", "Bad request"),
        401: ("unauthorized", "Unauthorized"),
        403: ("forbidden", "Forbidden"),
        404: ("not_found", "Resource not found"),
        409: ("conflict", "Conflict"),
        413: ("payload_too_large", "Payload too large"),
        415: ("unsupported_media_type", "Unsupported media type"),
        429: ("rate_limited", "Too many requests"),
        500: ("internal_error", "Internal server error"),
        502: ("provider_error", "Provider error"),
        503: ("service_unavailable", "Service unavailable"),
    }
    code, message = messages.get(exc.status_code, ("bad_request", "Request failed"))
    return error_response(request, exc.status_code, code, message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body"),
            "code": "invalid",
            "message": "Invalid value",
        }
        for error in exc.errors()
    ]
    return error_response(
        request, 422, "validation_error", "Request validation failed", details
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled_api_error",
        extra={"request_id": getattr(request.state, "request_id", None)},
    )
    return error_response(
        request, 500, "internal_error", "An unexpected error occurred"
    )
