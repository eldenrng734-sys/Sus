"""Lead status pipeline rules (API_CONTRACT 8.4). Pure logic: no database."""

from app.modules.auth.errors import AuthError

ALLOWED: dict[str, set[str]] = {
    "new": {"contacted", "qualified", "lost"},
    "contacted": {"qualified", "proposal", "lost"},
    "qualified": {"proposal", "won", "lost"},
    "proposal": {"won", "lost"},
    "won": set(),
    "lost": set(),  # terminal; only an admin may reopen (see below)
}
LOST_REASONS = {"price", "timing", "no_response", "competitor", "not_qualified", "other"}


class LeadError(AuthError):
    """Handled by the same error handler as AuthError (standard error format)."""


def check_transition(
    current: str,
    new: str,
    lost_reason: str | None = None,
    is_admin: bool = False,
    reopen_reason: str | None = None,
) -> None:
    """Raise LeadError unless current -> new is allowed."""
    if new not in ALLOWED:
        raise LeadError(422, "validation_error", "Unknown status")
    if new == current:
        return  # no change, nothing to check

    reopening = current == "lost" and new == "contacted"
    if reopening:
        if not is_admin:
            raise LeadError(403, "forbidden", "Only an admin can reopen a lost lead")
        if not (reopen_reason or "").strip():
            raise LeadError(422, "validation_error", "A reason is required to reopen a lead")
        return

    if new not in ALLOWED[current]:
        raise LeadError(
            409, "invalid_status_transition", f"Cannot move a lead from {current} to {new}"
        )

    if new == "lost":
        if lost_reason not in LOST_REASONS:
            raise LeadError(422, "validation_error", "A valid lost_reason is required")
