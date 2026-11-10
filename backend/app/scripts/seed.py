"""Dev-only seed data: 2 companies x 5 users. Safe to run repeatedly.

Run from the repo root:
    dc exec backend python -m app.scripts.seed
"""

import os
import sys
import uuid
from datetime import datetime, timezone

from argon2 import PasswordHasher
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

import app.database.registry  # noqa: F401  (loads every model)
from app.core.config import settings
from app.modules.tenants.models import Team, Tenant, TenantMembership
from app.modules.users.models import User

ALLOWED_ENVS = {"development", "dev", "local", "test"}

# Fixed namespace so seeded IDs are identical on every machine (handy for tests).
SEED_NS = uuid.UUID("6f1d2c3a-9b7e-4a58-8c14-2d5e7a9b0c31")

COMPANIES = [
    {"name": "Acme Traders", "slug": "acme", "domain": "acme.test"},
    {"name": "Globex Interiors", "slug": "globex", "domain": "globex.test"},
]
TEAM_NAMES = ["Sales Team A", "Sales Team B"]
# (email prefix, full name, role, team index or None)
PEOPLE = [
    ("admin", "Company Admin", "admin", None),
    ("manager", "Sales Manager", "manager", 0),
    ("rep1", "Rep One", "rep", 0),
    ("rep2", "Rep Two", "rep", 0),
    ("rep3", "Rep Three", "rep", 1),
]


def seed_id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NS, ":".join(parts))


def main() -> None:
    if settings.app_env.lower() not in ALLOWED_ENVS:
        sys.exit(f"Refusing to seed: APP_ENV={settings.app_env!r} is not a dev environment.")
    if not settings.database_url:
        sys.exit("DATABASE_URL is not set.")

    dev_password = os.environ.get("SEED_PASSWORD", "ChangeMe!12345")  # dev only
    hasher = PasswordHasher()  # Argon2id
    engine = create_engine(settings.database_url)

    for c in COMPANIES:
        # One transaction per company.
        with Session(engine) as db, db.begin():
            tenant_id = seed_id("tenant", c["slug"])
            # Transaction-local tenant context (needed once RLS is enabled on Day 3).
            db.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": str(tenant_id)},
            )

            if db.scalar(select(Tenant).where(Tenant.slug == c["slug"])):
                print(f"skip   {c['slug']} (already exists)")
                continue

            db.add(Tenant(id=tenant_id, name=c["name"], slug=c["slug"]))
            db.flush()

            teams = []
            for name in TEAM_NAMES:
                team = Team(id=seed_id("team", c["slug"], name), tenant_id=tenant_id, name=name)
                db.add(team)
                teams.append(team)
            db.flush()

            for prefix, full_name, role, team_idx in PEOPLE:
                email = f"{prefix}@{c['domain']}"
                user = db.scalar(select(User).where(User.email == email))
                if user is None:
                    user = User(
                        id=seed_id("user", email),
                        email=email,
                        full_name=full_name,
                        password_hash=hasher.hash(dev_password),
                        email_verified_at=datetime.now(timezone.utc),
                    )
                    db.add(user)
                    db.flush()
                db.add(
                    TenantMembership(
                        id=seed_id("membership", c["slug"], email),
                        tenant_id=tenant_id,
                        user_id=user.id,
                        team_id=teams[team_idx].id if team_idx is not None else None,
                        role=role,
                    )
                )
            print(f"seeded {c['slug']}: {len(TEAM_NAMES)} teams, {len(PEOPLE)} users")

    print(
        "done. Dev login password is set by SEED_PASSWORD (default in this file); never use it in production."
    )


if __name__ == "__main__":
    main()
