import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.core.tenancy import TenantContext, get_tenant_context
from app.database.session import get_session
from app.main import auth_error_handler
from app.modules.auth.errors import AuthError
from app.modules.auth.router import router as auth_router
from tests.cross_tenant.support import (
    PASSWORD,
    USER_PLAN,
    Seed,
    admin_url,
    app_url,
    assert_is_test_database,
    seed_tenant,
)

NEEDED_TABLES = {"tenants", "users", "tenant_memberships", "teams", "leads", "refresh_tokens"}


@pytest.fixture(scope="session", autouse=True)
def _jwt_secret() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "jwt_secret_key", "t" * 48)
        yield


@pytest.fixture(scope="session")
def admin_engine() -> Iterator[Engine]:
    url = admin_url()
    if url is None:
        pytest.skip("No test database configured (set TEST_DATABASE_URL or POSTGRES_* in .env)")
    assert_is_test_database(url)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            tables = {row[0] for row in rows}
    except OperationalError:
        engine.dispose()
        pytest.skip("Cannot reach crm_test (Docker running? ran local_migrate_test_db?)")
    if not NEEDED_TABLES <= tables:
        engine.dispose()
        pytest.skip("crm_test is not migrated: run scripts.local_migrate_test_db")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(admin_engine: Engine) -> Iterator[Engine]:
    url = app_url()
    if url is None:
        pytest.skip("Set TEST_APP_DATABASE_URL (the non-owner crm_app role) to run RLS tests")
    assert_is_test_database(url)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def seed(admin_engine: Engine) -> Seed:
    """Two companies with the same shape. Unique names per run, so no clean-up is needed."""
    suffix = uuid.uuid4().hex[:8]
    password_hash = hash_password(PASSWORD)
    with admin_engine.begin() as conn:  # one transaction per company
        a = seed_tenant(conn, "a", suffix, password_hash)
    with admin_engine.begin() as conn:
        b = seed_tenant(conn, "b", suffix, password_hash)
    return Seed(a=a, b=b)


@pytest.fixture(scope="session")
def make_client() -> Callable[[Engine], TestClient]:
    """A small test app: the real login routes + the real tenant dependency."""

    def _make(engine: Engine) -> TestClient:
        mini = FastAPI()
        mini.add_exception_handler(AuthError, auth_error_handler)
        mini.include_router(auth_router)

        @mini.get("/_ctx")
        def ctx_route(ctx: TenantContext = Depends(get_tenant_context)) -> dict:
            return {"tenant_id": str(ctx.tenant_id), "role": ctx.role}

        @mini.get("/_leads")
        def leads_route(
            ctx: TenantContext = Depends(get_tenant_context),
            session: Session = Depends(get_session),
        ) -> dict:
            # Deliberately NO tenant filter: only the database (RLS) may limit this.
            ids = session.scalars(text("SELECT id FROM leads")).all()
            return {"ids": sorted(str(i) for i in ids)}

        def _session() -> Iterator[Session]:
            with Session(engine) as session:
                yield session

        mini.dependency_overrides[get_session] = _session
        return TestClient(mini, client=("127.0.0.1", 50000))

    return _make


@pytest.fixture(scope="session")
def admin_client(make_client: Callable[[Engine], TestClient], admin_engine: Engine) -> TestClient:
    return make_client(admin_engine)


@pytest.fixture(scope="session")
def tokens(admin_client: TestClient, seed: Seed) -> dict[tuple[str, str], dict[str, str]]:
    """Log in every seeded user once. Key: (company letter, user key)."""
    result: dict[tuple[str, str], dict[str, str]] = {}
    for letter in ("a", "b"):
        for key, _role, _active in USER_PLAN:
            email = seed.get(letter).users[key][1]
            response = admin_client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
            assert response.status_code == 200, response.text
            token = response.json()["data"]["access_token"]
            result[(letter, key)] = {"Authorization": f"Bearer {token}"}
    return result
