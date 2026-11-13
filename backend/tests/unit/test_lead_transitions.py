import pytest

from app.modules.leads.transitions import LeadError, check_transition


@pytest.mark.parametrize(
    ("current", "new"),
    [
        ("new", "contacted"),
        ("new", "qualified"),
        ("contacted", "proposal"),
        ("qualified", "won"),
        ("proposal", "won"),
    ],
)
def test_allowed_moves(current, new):
    check_transition(current, new)


@pytest.mark.parametrize(
    ("current", "new"),
    [("new", "proposal"), ("new", "won"), ("contacted", "won"), ("won", "lost"), ("lost", "won")],
)
def test_forbidden_moves(current, new):
    with pytest.raises(LeadError) as exc:
        check_transition(current, new)
    assert exc.value.code == "invalid_status_transition"


def test_lost_needs_a_reason():
    with pytest.raises(LeadError) as exc:
        check_transition("new", "lost")
    assert exc.value.status_code == 422
    check_transition("new", "lost", lost_reason="price")


def test_unknown_lost_reason_is_rejected():
    with pytest.raises(LeadError):
        check_transition("new", "lost", lost_reason="because")


def test_won_is_terminal():
    for target in ("new", "contacted", "lost"):
        with pytest.raises(LeadError):
            check_transition("won", target)


def test_only_admin_can_reopen_with_a_reason():
    with pytest.raises(LeadError) as exc:
        check_transition("lost", "contacted", is_admin=False, reopen_reason="x")
    assert exc.value.status_code == 403
    with pytest.raises(LeadError) as exc:
        check_transition("lost", "contacted", is_admin=True)
    assert exc.value.status_code == 422
    check_transition("lost", "contacted", is_admin=True, reopen_reason="Customer came back")


def test_same_status_is_a_no_op():
    check_transition("new", "new")
