from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import settings


@lru_cache
def get_engine() -> Engine:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """One database session per request. Services call commit() themselves."""
    with Session(get_engine()) as session:
        yield session


def set_tenant_context(session: Session, tenant_id: str) -> None:
    """Tell PostgreSQL which company this transaction belongs to (for RLS).

    The `true` makes it transaction-local, so it cannot leak through connection pooling.
    Only call this with a tenant id the backend has verified or just created.
    """
    session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_id})
