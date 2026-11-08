import app.database.registry  # noqa: F401
from app.database.base import Base

MY_TABLES = [
    "leads",
    "contacts",
    "interactions",
    "integrations",
    "webhook_events",
]


def test_all_tables_have_required_tenant_id():
    """Every business table must have a non-null tenant_id."""

    for table_name in MY_TABLES:
        table = Base.metadata.tables[table_name]

        tenant_column = table.c.get("tenant_id")

        assert tenant_column is not None, f"{table_name} is missing tenant_id"

        assert tenant_column.nullable is False, f"{table_name}.tenant_id must be NOT NULL"


def test_webhook_dedup_constraint_exists():
    """Prevent duplicate webhook events."""

    table = Base.metadata.tables["webhook_events"]

    constraint_names = {constraint.name for constraint in table.constraints}

    assert "uq_webhook_events_dedup" in constraint_names


def test_lead_has_tenant_safe_foreign_keys():
    """Assigned users and teams must belong to the same tenant."""

    table = Base.metadata.tables["leads"]

    foreign_key_names = {constraint.name for constraint in table.foreign_key_constraints}

    assert "fk_leads_assigned_member" in foreign_key_names
    assert "fk_leads_team" in foreign_key_names


def test_contact_and_interaction_reference_leads():
    """Child records must reference leads using tenant-aware foreign keys."""

    expected_constraints = {
        "contacts": "fk_contacts_lead",
        "interactions": "fk_interactions_lead",
    }

    for table_name, expected_name in expected_constraints.items():
        table = Base.metadata.tables[table_name]

        foreign_key_names = {constraint.name for constraint in table.foreign_key_constraints}

        assert expected_name in foreign_key_names


def test_integration_owner_has_tenant_safe_foreign_key():
    """Integration owners must belong to the same tenant."""

    table = Base.metadata.tables["integrations"]

    foreign_key_names = {constraint.name for constraint in table.foreign_key_constraints}

    assert "fk_integrations_owner" in foreign_key_names
