import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.cross_tenant.support import set_tenant


def test_lead_cannot_be_assigned_to_a_member_of_another_company(admin_engine, seed):
    foreign_user = seed.b.users["rep"][0]
    with pytest.raises(IntegrityError, match="foreign key"):
        with admin_engine.begin() as conn:
            set_tenant(conn, seed.a.id)
            conn.execute(
                text(
                    "INSERT INTO leads (tenant_id, name, email, source, assigned_user_id) "
                    "VALUES (:t, 'X', :e, 'manual', :u)"
                ),
                {"t": seed.a.id, "e": f"fk-{uuid.uuid4().hex}@example.com", "u": foreign_user},
            )


def test_membership_cannot_use_a_team_of_another_company(admin_engine, seed):
    foreign_user = seed.b.users["rep"][0]
    with pytest.raises(IntegrityError, match="foreign key"):
        with admin_engine.begin() as conn:
            set_tenant(conn, seed.a.id)
            conn.execute(
                text(
                    "INSERT INTO tenant_memberships (tenant_id, user_id, role, team_id) "
                    "VALUES (:t, :u, 'rep', :team)"
                ),
                {"t": seed.a.id, "u": foreign_user, "team": seed.b.team_id},
            )
