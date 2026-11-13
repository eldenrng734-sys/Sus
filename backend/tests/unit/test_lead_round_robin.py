"""Round-robin lead assignment.

The rotation is covered twice:

- pure unit tests for the ordering helper (no database);
- integration tests against a real PostgreSQL ``*_test`` database, because the
  cursor locking, the transaction boundary and the audit/interaction writes only
  exist in the database.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext
from app.modules.audit.models import AuditLog
from app.modules.auth.errors import AuthError
from app.modules.leads import assignment, service
from app.modules.leads.assignment import assign_round_robin, next_rep
from app.modules.leads.models import AssignmentCursor, Interaction, Lead
from tests.cross_tenant.support import admin_url

# --------------------------------------------------------------------------- #
# Pure rotation rules
# --------------------------------------------------------------------------- #


def test_first_assignment_uses_the_first_rep():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert next_rep([a, b, c], None) == a


def test_second_and_third_assignment_advance_the_rotation():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert next_rep([a, b, c], a) == b
    assert next_rep([a, b, c], b) == c


def test_fourth_assignment_restarts_the_rotation():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert next_rep([a, b, c], c) == a


def test_single_rep_keeps_receiving_leads():
    a = uuid.uuid4()
    assert next_rep([a], None) == a
    assert next_rep([a], a) == a


def test_no_reps_means_no_assignment():
    assert next_rep([], None) is None
    assert next_rep([], uuid.uuid4()) is None


def test_unknown_last_rep_restarts_from_the_first():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert next_rep([a, b, c], uuid.uuid4()) == a


# --------------------------------------------------------------------------- #
# Database-backed rotation
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def engine():
    url = admin_url()
    if url is None:
        pytest.skip("No test database configured (set TEST_DATABASE_URL or POSTGRES_* in .env)")
    # 127.0.0.1 avoids the ::1 first-hop timeout on Windows.
    url = url.set(host="127.0.0.1")
    test_engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM assignment_cursors LIMIT 1"))
    except OperationalError:
        test_engine.dispose()
        pytest.skip(f"Cannot reach a migrated test database at {url.database}")
    yield test_engine
    test_engine.dispose()


class Factory:
    """Creates one isolated tenant graph per test and removes it afterwards."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.tenant_ids: list[uuid.UUID] = []
        self.user_ids: list[uuid.UUID] = []
        self._clock = datetime.now(UTC) - timedelta(hours=1)

    def _next_timestamp(self) -> datetime:
        self._clock += timedelta(seconds=1)
        return self._clock

    def tenant(self) -> uuid.UUID:
        tenant_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :slug)"),
                {"id": tenant_id, "name": "RR Co", "slug": f"rr-{tenant_id.hex[:12]}"},
            )
        self.tenant_ids.append(tenant_id)
        return tenant_id

    def team(self, tenant_id: uuid.UUID, name: str = "Sales") -> uuid.UUID:
        team_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO teams (id, tenant_id, name) VALUES (:id, :t, :name)"),
                {"id": team_id, "t": tenant_id, "name": f"{name} {team_id.hex[:6]}"},
            )
        return team_id

    def member(
        self,
        tenant_id: uuid.UUID,
        team_id: uuid.UUID,
        *,
        role: str = "rep",
        membership_active: bool = True,
        user_active: bool = True,
    ) -> uuid.UUID:
        user_id = uuid.uuid4()
        joined_at = self._next_timestamp()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, is_active) "
                    "VALUES (:id, :email, 'x', :active)"
                ),
                {
                    "id": user_id,
                    "email": f"rr-{user_id.hex[:12]}@test.example",
                    "active": user_active,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO tenant_memberships "
                    "(tenant_id, user_id, role, team_id, is_active, created_at) "
                    "VALUES (:t, :u, :role, :team, :active, :joined)"
                ),
                {
                    "t": tenant_id,
                    "u": user_id,
                    "role": role,
                    "team": team_id,
                    "active": membership_active,
                    "joined": joined_at,
                },
            )
        self.user_ids.append(user_id)
        return user_id

    def lead(
        self,
        tenant_id: uuid.UUID,
        *,
        team_id: uuid.UUID | None = None,
        assigned_user_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        lead_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO leads "
                    "(id, tenant_id, name, email, source, team_id, assigned_user_id) "
                    "VALUES (:id, :t, :name, :email, 'manual', :team, :owner)"
                ),
                {
                    "id": lead_id,
                    "t": tenant_id,
                    "name": f"Lead {lead_id.hex[:6]}",
                    "email": f"lead-{lead_id.hex[:12]}@example.com",
                    "team": team_id,
                    "owner": assigned_user_id,
                },
            )
        return lead_id

    def actor(self, tenant_id: uuid.UUID) -> uuid.UUID:
        """A company admin without a team; used as the caller of the service."""
        user_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'x')"),
                {"id": user_id, "email": f"admin-{user_id.hex[:12]}@test.example"},
            )
            conn.execute(
                text(
                    "INSERT INTO tenant_memberships (tenant_id, user_id, role, is_active) "
                    "VALUES (:t, :u, 'admin', true)"
                ),
                {"t": tenant_id, "u": user_id},
            )
        self.user_ids.append(user_id)
        return user_id

    def context(
        self,
        tenant_id: uuid.UUID,
        *,
        role: str = "admin",
        team_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> TenantContext:
        return TenantContext(
            user_id=user_id or self.actor(tenant_id),
            tenant_id=tenant_id,
            membership_id=uuid.uuid4(),
            role=role,
            team_id=team_id,
            session_id=uuid.uuid4(),
        )

    def cleanup(self) -> None:
        with self.engine.begin() as conn:
            for tenant_id in self.tenant_ids:
                params = {"t": tenant_id}
                for table in (
                    "assignment_cursors",
                    "idempotency_keys",
                    "interactions",
                    "audit_logs",
                    "leads",
                    "tenant_memberships",
                    "teams",
                ):
                    conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), params)
                conn.execute(text("DELETE FROM tenants WHERE id = :t"), params)
            for user_id in self.user_ids:
                conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})


@pytest.fixture()
def factory(engine):
    created = Factory(engine)
    yield created
    created.cleanup()


@pytest.fixture()
def session(engine):
    with Session(engine) as db_session:
        yield db_session


def load_lead(session: Session, lead_id: uuid.UUID) -> Lead:
    session.expire_all()
    lead = session.get(Lead, lead_id)
    assert lead is not None
    return lead


def cursor_state(session: Session, tenant_id: uuid.UUID, team_id: uuid.UUID):
    session.expire_all()
    return session.scalar(
        select(AssignmentCursor).where(
            AssignmentCursor.tenant_id == tenant_id,
            AssignmentCursor.team_id == team_id,
        )
    )


def test_rotation_assigns_each_rep_and_wraps(factory, session):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    rep_a = factory.member(tenant_id, team_id)
    rep_b = factory.member(tenant_id, team_id)
    rep_c = factory.member(tenant_id, team_id)
    context = factory.context(tenant_id)

    owners = []
    for _ in range(4):
        lead_id = factory.lead(tenant_id)
        result = service.auto_assign_lead(session, context, lead_id, team_id)
        assert result["assigned"] is True
        owners.append(uuid.UUID(result["assigned_user_id"]))

    assert owners == [rep_a, rep_b, rep_c, rep_a]

    last_lead = load_lead(session, lead_id)
    assert last_lead.team_id == team_id
    assert last_lead.version == 2

    interactions = session.scalars(select(Interaction).where(Interaction.lead_id == lead_id)).all()
    assert [item.type for item in interactions] == ["assigned"]
    assert interactions[0].source == "automation"
    assert interactions[0].details["assigned_user_id"] == str(rep_a)
    assert interactions[0].details["team_id"] == str(team_id)

    audits = session.scalars(
        select(AuditLog).where(AuditLog.entity_type == "lead", AuditLog.entity_id == lead_id)
    ).all()
    assert [item.action for item in audits] == ["lead.assigned"]
    assert audits[0].actor_type == "automation"
    assert audits[0].details["assigned_user_id"] == str(rep_a)
    assert audits[0].details["team_id"] == str(team_id)


def test_no_active_reps_leaves_the_lead_unowned(factory, session):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    factory.member(tenant_id, team_id, role="manager")
    lead_id = factory.lead(tenant_id)

    result = service.auto_assign_lead(session, factory.context(tenant_id), lead_id, team_id)

    assert result["assigned"] is False
    assert result["assigned_user_id"] is None
    assert load_lead(session, lead_id).assigned_user_id is None
    assert cursor_state(session, tenant_id, team_id).last_assigned_user_id is None
    assert session.scalars(select(Interaction).where(Interaction.lead_id == lead_id)).all() == []


def test_single_rep_receives_every_lead(factory, session):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    rep = factory.member(tenant_id, team_id)
    context = factory.context(tenant_id)

    for _ in range(3):
        lead_id = factory.lead(tenant_id)
        result = service.auto_assign_lead(session, context, lead_id, team_id)
        assert result["assigned_user_id"] == str(rep)


def test_inactive_membership_is_skipped(factory, session):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    rep_a = factory.member(tenant_id, team_id)
    factory.member(tenant_id, team_id, membership_active=False)
    rep_c = factory.member(tenant_id, team_id)
    context = factory.context(tenant_id)

    owners = []
    for _ in range(3):
        lead_id = factory.lead(tenant_id)
        result = service.auto_assign_lead(session, context, lead_id, team_id)
        owners.append(uuid.UUID(result["assigned_user_id"]))

    assert owners == [rep_a, rep_c, rep_a]


def test_inactive_user_is_skipped(factory, session):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    rep_a = factory.member(tenant_id, team_id)
    factory.member(tenant_id, team_id, user_active=False)
    rep_c = factory.member(tenant_id, team_id)
    context = factory.context(tenant_id)

    owners = []
    for _ in range(2):
        lead_id = factory.lead(tenant_id)
        result = service.auto_assign_lead(session, context, lead_id, team_id)
        owners.append(uuid.UUID(result["assigned_user_id"]))

    assert owners == [rep_a, rep_c]


def test_new_rep_joins_at_the_end_of_the_rotation(factory, session):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    rep_a = factory.member(tenant_id, team_id)
    rep_b = factory.member(tenant_id, team_id)
    rep_c = factory.member(tenant_id, team_id)
    context = factory.context(tenant_id)

    first = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_id)
    second = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_id)
    assert [first["assigned_user_id"], second["assigned_user_id"]] == [
        str(rep_a),
        str(rep_b),
    ]

    rep_d = factory.member(tenant_id, team_id)

    owners = []
    for _ in range(2):
        lead_id = factory.lead(tenant_id)
        result = service.auto_assign_lead(session, context, lead_id, team_id)
        owners.append(uuid.UUID(result["assigned_user_id"]))

    assert owners == [rep_c, rep_d]


def test_rotation_continues_after_the_last_rep_leaves(factory, session):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    factory.member(tenant_id, team_id)  # rep A
    rep_b = factory.member(tenant_id, team_id)
    rep_c = factory.member(tenant_id, team_id)
    context = factory.context(tenant_id)

    service.auto_assign_lead(session, context, factory.lead(tenant_id), team_id)
    second = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_id)
    assert second["assigned_user_id"] == str(rep_b)

    with factory.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE tenant_memberships SET is_active = false "
                "WHERE tenant_id = :t AND user_id = :u"
            ),
            {"t": tenant_id, "u": rep_b},
        )

    third = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_id)
    assert third["assigned_user_id"] == str(rep_c)


def test_teams_keep_independent_rotations(factory, session):
    tenant_id = factory.tenant()
    team_a = factory.team(tenant_id, "Alpha")
    team_b = factory.team(tenant_id, "Beta")
    a1 = factory.member(tenant_id, team_a)
    a2 = factory.member(tenant_id, team_a)
    b1 = factory.member(tenant_id, team_b)
    b2 = factory.member(tenant_id, team_b)
    context = factory.context(tenant_id)

    first = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_a)
    second = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_b)
    third = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_a)
    fourth = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_b)

    assert [first["assigned_user_id"], third["assigned_user_id"]] == [str(a1), str(a2)]
    assert [second["assigned_user_id"], fourth["assigned_user_id"]] == [str(b1), str(b2)]


def test_other_tenants_never_receive_the_lead(factory, session):
    tenant_a = factory.tenant()
    tenant_b = factory.tenant()
    team_a = factory.team(tenant_a)
    team_b = factory.team(tenant_b)
    rep_a = factory.member(tenant_a, team_a)
    factory.member(tenant_b, team_b)
    factory.member(tenant_b, team_b)
    context = factory.context(tenant_a)

    owners = set()
    for _ in range(3):
        lead_id = factory.lead(tenant_a)
        result = service.auto_assign_lead(session, context, lead_id, team_a)
        owners.add(result["assigned_user_id"])

    assert owners == {str(rep_a)}


def test_existing_assignment_is_not_overwritten(factory, session):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    rep_a = factory.member(tenant_id, team_id)
    rep_b = factory.member(tenant_id, team_id)
    owner = factory.member(tenant_id, team_id)
    lead_id = factory.lead(tenant_id, team_id=team_id, assigned_user_id=owner)
    context = factory.context(tenant_id)

    result = service.auto_assign_lead(session, context, lead_id, team_id)

    assert result["assigned"] is False
    assert result["assigned_user_id"] == str(owner)
    assert load_lead(session, lead_id).assigned_user_id == owner
    assert cursor_state(session, tenant_id, team_id) is None

    # The rotation is untouched: the next unowned lead still starts at rep A.
    next_result = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_id)
    assert next_result["assigned_user_id"] == str(rep_a)

    after = service.auto_assign_lead(session, context, factory.lead(tenant_id), team_id)
    assert after["assigned_user_id"] == str(rep_b)


def test_concurrent_requests_cannot_pick_the_same_position(factory, engine):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    rep_a = factory.member(tenant_id, team_id)
    rep_b = factory.member(tenant_id, team_id)
    lead_one = factory.lead(tenant_id)
    lead_two = factory.lead(tenant_id)

    with Session(engine) as first_session, Session(engine) as second_session:
        first_lead = first_session.scalar(select(Lead).where(Lead.id == lead_one).with_for_update())
        first_result = assign_round_robin(first_session, lead=first_lead, team_id=team_id)
        assert first_result is not None and first_result.user_id == rep_a

        second_session.execute(text("SET LOCAL lock_timeout = '250ms'"))
        second_lead = second_session.scalar(
            select(Lead).where(Lead.id == lead_two).with_for_update()
        )
        with pytest.raises(OperationalError):
            assign_round_robin(second_session, lead=second_lead, team_id=team_id)

        first_session.commit()
        second_session.rollback()

        second_lead = second_session.scalar(
            select(Lead).where(Lead.id == lead_two).with_for_update()
        )
        second_result = assign_round_robin(second_session, lead=second_lead, team_id=team_id)
        assert second_result is not None
        second_session.commit()

    assert second_result.user_id == rep_b
    with Session(engine) as check_session:
        assert cursor_state(check_session, tenant_id, team_id).last_assigned_user_id == rep_b


def test_database_failure_rolls_back_assignment(factory, session, monkeypatch):
    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    factory.member(tenant_id, team_id)
    lead_id = factory.lead(tenant_id)

    def explode(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(assignment, "record_audit_event", explode)

    with pytest.raises(RuntimeError):
        service.auto_assign_lead(session, factory.context(tenant_id), lead_id, team_id)

    assert load_lead(session, lead_id).assigned_user_id is None
    assert cursor_state(session, tenant_id, team_id) is None
    assert session.scalars(select(Interaction).where(Interaction.lead_id == lead_id)).all() == []


def test_auto_assign_rejects_a_team_from_another_tenant(factory, session):
    tenant_a = factory.tenant()
    tenant_b = factory.tenant()
    team_b = factory.team(tenant_b)
    factory.member(tenant_b, team_b)
    lead_id = factory.lead(tenant_a)

    with pytest.raises(AuthError) as exc:
        service.auto_assign_lead(session, factory.context(tenant_a), lead_id, team_b)

    assert exc.value.status_code == 422
    assert load_lead(session, lead_id).assigned_user_id is None


def test_creating_an_unowned_lead_for_a_team_starts_the_rotation(factory, session):
    from app.modules.leads import crud
    from app.modules.leads.schemas import LeadCreate

    tenant_id = factory.tenant()
    team_id = factory.team(tenant_id)
    rep_a = factory.member(tenant_id, team_id)
    rep_b = factory.member(tenant_id, team_id)
    context = factory.context(tenant_id)

    first, _ = crud.create_lead(
        session,
        context,
        LeadCreate(name="Website lead", email="first@example.com", team_id=team_id),
        "rr-create-key-1",
    )
    second, _ = crud.create_lead(
        session,
        context,
        LeadCreate(name="Website lead", email="second@example.com", team_id=team_id),
        "rr-create-key-2",
    )

    assert first["assigned_user_id"] == str(rep_a)
    assert first["team_id"] == str(team_id)
    assert second["assigned_user_id"] == str(rep_b)

    events = session.scalars(
        select(Interaction).where(Interaction.lead_id == uuid.UUID(first["id"]))
    ).all()
    assert [event.type for event in events] == ["lead_created", "assigned"]
    assert events[1].source == "automation"


def test_manager_cannot_round_robin_outside_their_team(factory, session):
    tenant_id = factory.tenant()
    manager_team = factory.team(tenant_id, "Own")
    other_team = factory.team(tenant_id, "Other")
    manager_id = factory.member(tenant_id, manager_team)
    factory.member(tenant_id, other_team)
    # Managers only see leads of their own team, so the lead starts in that team.
    lead_id = factory.lead(tenant_id, team_id=manager_team)

    context = factory.context(tenant_id, role="manager", team_id=manager_team, user_id=manager_id)

    with pytest.raises(AuthError) as exc:
        service.auto_assign_lead(session, context, lead_id, other_team)

    assert exc.value.status_code == 403
