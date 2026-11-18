"""
Tests for Alembic migration graph integrity.

test_migration_history_has_one_head  — runs in every CI/unit pass; no DB needed.
test_upgrade_head_on_empty_database  — requires a live Postgres database; skipped
    when ALEMBIC_TEST_DATABASE_URL is not set (or TEST_DATABASE_URL as a fallback).
    In CI the postgres service sets TEST_DATABASE_URL.
"""

import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    # Keep the script_location absolute so the test works from any cwd.
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    return cfg


def test_migration_history_has_one_head() -> None:
    """The migration graph must always have exactly one head.

    This test runs without a database; it only reads the migration files.
    CI fails immediately if someone introduces a second head.
    """
    cfg = _alembic_config()
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, (
        f"Expected exactly 1 Alembic head, found {len(heads)}: {heads}. "
        "Run `alembic merge heads -m merge_all_heads` to fix."
    )


def test_upgrade_head_on_empty_database() -> None:
    """Running `alembic upgrade head` on a brand-new, empty database must succeed.

    Skipped when no suitable database URL is available so local unit-test runs
    never fail because of missing infrastructure.  CI provides the URL through
    the postgres service container (TEST_DATABASE_URL env var).
    """
    url = os.environ.get("ALEMBIC_TEST_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set ALEMBIC_TEST_DATABASE_URL (or TEST_DATABASE_URL) to run the "
            "upgrade-head integration test."
        )

    # Safety check: never run against a database whose name does not contain
    # 'test' — this guards against accidental runs on production.
    db_name = url.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in db_name.lower():
        pytest.skip(
            f"Database name '{db_name}' does not contain 'test'. "
            "Refusing to run destructive migration test against a non-test database."
        )

    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Cannot connect to test database: {exc}")

    cfg = _alembic_config()
    cfg.set_main_option("sqlalchemy.url", url)

    # Run upgrade to head.
    from alembic import command as alembic_command

    alembic_command.upgrade(cfg, "head")

    # Confirm the DB now agrees with the script about the current head.
    script_dir = ScriptDirectory.from_config(cfg)
    expected_head = script_dir.get_heads()[0]

    with engine.connect() as conn:
        migration_ctx = MigrationContext.configure(conn)
        current = migration_ctx.get_current_heads()

    engine.dispose()

    assert set(current) == {expected_head}, (
        f"After upgrade head, DB is at {current} but script head is {expected_head}."
    )
