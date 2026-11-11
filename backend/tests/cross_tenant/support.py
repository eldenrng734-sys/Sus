"""Helpers for the cross-tenant tests. They run against a REAL PostgreSQL, never mocks."""

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL, Connection, make_url

PASSWORD = "correct-horse-battery"

# Remove this marker from the tests that use it once Dev 5's RLS migration and the
# non-owner crm_app role are merged into dev. From then on they must pass for real.
rls_pending = pytest.mark.xfail(
    reason="RLS policies / crm_app role not merged yet (Dev 5, Day 3)", strict=False
)

ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


def read_dotenv() -> dict[str, str]:
    values: dict[str, str] = {}
    if ROOT_ENV.exists():
        for raw in ROOT_ENV.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def admin_url() -> URL | None:
    """The owner connection used to create test data. Always the crm_test database."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return make_url(explicit)
    env = read_dotenv()
    user, password = env.get("POSTGRES_USER"), env.get("POSTGRES_PASSWORD")
    if not user or not password:
        return None
    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host="localhost",
        port=int(os.environ.get("POSTGRES_HOST_PORT", "5433")),
        database="crm_test",
    )


def app_url() -> URL | None:
    """The NON-owner application role (crm_app). Needed for the real RLS tests."""
    explicit = os.environ.get("TEST_APP_DATABASE_URL")
    return make_url(explicit) if explicit else None


def assert_is_test_database(url: URL) -> None:
    if not (url.database or "").endswith("_test"):
        pytest.fail(f"Refusing to run: '{url.database}' is not a *_test database", pytrace=False)


@dataclass
class TenantData:
    id: uuid.UUID
    name: str
    team_id: uuid.UUID
    users: dict[str, tuple[uuid.UUID, str]] = field(default_factory=dict)  # key -> (id, email)
    lead_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class Seed:
    a: TenantData
    b: TenantData

    def get(self, letter: str) -> TenantData:
        return self.a if letter == "a" else self.b


OTHER = {"a": "b", "b": "a"}

# (key, role, membership active?). ex_rep has a DEACTIVATED membership.
USER_PLAN = [
    ("admin", "admin", True),
    ("manager", "manager", True),
    ("rep", "rep", True),
    ("rep2", "rep", True),
    ("ex_rep", "rep", False),
]


def set_tenant(conn: Connection, tenant_id: uuid.UUID) -> None:
    conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})


def seed_tenant(conn: Connection, letter: str, suffix: str, password_hash: str) -> TenantData:
    """One company: team, 5 people, 3 leads. The tenant context is set BEFORE any insert."""
    tenant_id, team_id = uuid.uuid4(), uuid.uuid4()
    set_tenant(conn, tenant_id)
    name = f"Company {letter.upper()} {suffix}"
    conn.execute(
        text("INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": tenant_id, "name": name, "slug": f"co-{letter}-{suffix}"},
    )
    conn.execute(
        text("INSERT INTO teams (id, tenant_id, name) VALUES (:id, :t, :name)"),
        {"id": team_id, "t": tenant_id, "name": f"Sales {letter.upper()}"},
    )
    data = TenantData(id=tenant_id, name=name, team_id=team_id)

    for key, role, active in USER_PLAN:
        user_id = uuid.uuid4()
        email = f"{key}-{letter}-{suffix}@test.example"
        conn.execute(
            text(
                "INSERT INTO users (id, email, full_name, password_hash, email_verified_at) "
                "VALUES (:id, :email, :name, :ph, now())"
            ),
            {"id": user_id, "email": email, "name": f"{key} {letter.upper()}", "ph": password_hash},
        )
        conn.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role, team_id, is_active) "
                "VALUES (:t, :u, :role, :team, :active)"
            ),
            {"t": tenant_id, "u": user_id, "role": role, "team": team_id, "active": active},
        )
        data.users[key] = (user_id, email)

    assignees = [data.users["rep"][0], data.users["rep2"][0], None]
    for i, assignee in enumerate(assignees):
        lead_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO leads (id, tenant_id, name, email, source, assigned_user_id) "
                "VALUES (:id, :t, :name, :email, 'manual', :assignee)"
            ),
            {
                "id": lead_id,
                "t": tenant_id,
                "name": f"Lead {i} {letter.upper()}",
                "email": f"lead{i}-{letter}-{suffix}@example.com",
                "assignee": assignee,
            },
        )
        data.lead_ids.append(lead_id)
    return data
