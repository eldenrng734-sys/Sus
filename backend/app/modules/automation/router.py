"""Internal API for n8n. Reachable only on the private network, signed with HMAC.

Every endpoint takes one specific resource ID; there is deliberately no list-everything
route (API_CONTRACT.md section 14).
"""

from fastapi import APIRouter, Depends

from app.core.service_auth import InternalServiceContext, require_internal_service

router = APIRouter(prefix="/internal/v1/automation", tags=["internal automation"])


@router.get("/health")
def internal_health(
    context: InternalServiceContext = Depends(require_internal_service),
) -> dict:
    """Proves n8n can reach the API and that its signature is accepted."""
    return {"data": {"status": "ok", "service": context.service_id}}
