import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_mock_engine


def _migration_module():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "c8d49f2176aa_create_notifications.py"
    )
    spec = importlib.util.spec_from_file_location("notification_migration", migration_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load notification migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notification_migration_upgrade_and_downgrade_are_reversible(monkeypatch):
    statements = []
    engine = create_mock_engine(
        "postgresql://",
        lambda statement, *_args, **_kwargs: statements.append(str(statement)),
    )
    migration = _migration_module()

    connection = engine.connect()
    monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
    migration.upgrade()
    migration.downgrade()

    sql = "\n".join(statements)
    assert migration.down_revision == "f6a8c0d2e491"
    assert "CREATE TABLE notifications" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "DROP TABLE notifications" in sql
