from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
app.include_router(password_reset_router)
from app.modules.auth.router import router as auth_router
from app.modules.auth.service import AuthError
from app.modules.auth.password_reset import router as password_reset_router

app = FastAPI(title="AI Sales Assistant CRM", version="0.1.0")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request.headers.get("X-Request-ID"),
            }
        },
    )
