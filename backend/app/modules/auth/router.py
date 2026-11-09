from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.modules.auth import service
from app.modules.auth.schemas import LoginRequest, SignupRequest
from fastapi import APIRouter, Depends, Request
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", status_code=201)
def signup(body: SignupRequest, session: Session = Depends(get_session)) -> dict:
    return {"data": service.signup(session, body)}


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    ip_address = request.client.host if request.client else None
    return {
        "data": service.login(
            session,
            body,
            ip_address=ip_address,
        )
    }