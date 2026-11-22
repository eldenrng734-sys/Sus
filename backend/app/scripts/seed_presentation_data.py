"""Seed presentation data:
  - 200 leads assigned to admin (My View)
  - 2,000 total leads assigned to Sales Team A (Team View)
  - Realistic status, priority, source, and date distribution over the last 25 days.
  - Sample follow-up tasks for active KPIs.

Run via docker:
    docker compose --env-file .env -f infrastructure/docker-compose.yml exec backend python -m app.scripts.seed_presentation_data
"""

import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

import app.database.registry  # noqa: F401
from app.database.session import get_engine
from app.modules.leads.models import Interaction, Lead
from app.modules.tasks.models import Task
from app.modules.tenants.models import Team, Tenant, TenantMembership
from app.modules.users.models import User

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
]

COMPANIES = [
    "Apex Global", "Starlight Systems", "Nexus Logistics", "Horizon Media",
    "Vanguard Tech", "Cascade Dynamics", "Silverline Retail", "Summit Healthcare",
    "Pinnacle Finance", "BlueWave Solutions", "Solaria Energy", "Quantum Labs",
    "Ironclad Security", "Prime Real Estate", "Velocity Motors", "Crestview Capital",
]

SOURCES = [
    "website_form", "whatsapp", "facebook_lead_ads", "messenger", "manual", "csv"
]
STATUSES = ["new", "contacted", "qualified", "proposal", "won", "lost"]
STATUS_WEIGHTS = [0.35, 0.25, 0.15, 0.10, 0.08, 0.07]

PRIORITIES = ["low", "medium", "high"]
PRIORITY_WEIGHTS = [0.25, 0.50, 0.25]


def main() -> None:
    now = datetime.now(UTC)

    with Session(get_engine()) as db, db.begin():
        # 1. Find Acme tenant
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "acme"))
        if not tenant:
            tenant = db.scalar(select(Tenant).order_by(Tenant.created_at).limit(1))
        if not tenant:
            print("Error: No tenant found in database. Run seed first.")
            return

        tenant_id = tenant.id
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})

        # 2. Find Sales Team A
        team = db.scalar(
            select(Team).where(Team.tenant_id == tenant_id, Team.name == "Sales Team A")
        )
        if not team:
            team = db.scalar(select(Team).where(Team.tenant_id == tenant_id).limit(1))
        if not team:
            team = Team(id=uuid.uuid4(), tenant_id=tenant_id, name="Sales Team A")
            db.add(team)
            db.flush()

        team_id = team.id

        # 3. Find admin user
        admin_user = db.scalar(select(User).where(User.email == "admin@acme.test"))
        if not admin_user:
            admin_user = db.scalar(select(User).order_by(User.created_at).limit(1))

        # Ensure admin is a member of Team A
        admin_membership = db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == admin_user.id,
            )
        )
        if admin_membership:
            admin_membership.team_id = team_id
            db.flush()

        # Find team members (reps + manager)
        members = list(
            db.scalars(
                select(TenantMembership.user_id).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.team_id == team_id,
                )
            ).all()
        )
        if not members or admin_user.id not in members:
            members.append(admin_user.id)

        other_members = [m for m in members if m != admin_user.id]
        if not other_members:
            other_members = [admin_user.id]

        print(f"Target Tenant: {tenant.name} ({tenant_id})")
        print(f"Target Team: {team.name} ({team_id})")
        print(f"Admin User ID: {admin_user.id} ({admin_user.email})")
        print(f"Team Member IDs: {len(members)} users")

        # 4. Generate Leads:
        # 200 leads assigned to admin (My View)
        # 1,800 leads assigned to other team members (Team View total = 2000)
        leads_to_create: list[Lead] = []
        lead_counter = int(datetime.now().timestamp()) % 100000

        # Create 200 for admin
        for i in range(200):
            lead_counter += 1
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
            priority = random.choices(PRIORITIES, weights=PRIORITY_WEIGHTS)[0]
            source = random.choice(SOURCES)
            created_days_ago = random.randint(1, 25)
            created_time = now - timedelta(days=created_days_ago, hours=random.randint(0, 23))

            lost_reason = random.choice(["price", "timing", "competitor", "other"]) if status == "lost" else None

            lead = Lead(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}.{lead_counter}@presentation.test",
                phone=f"+1202{random.randint(1000000, 9999999)}",
                company_name=random.choice(COMPANIES),
                source=source,
                source_campaign="Presentation Campaign" if random.random() > 0.4 else None,
                status=status,
                lost_reason=lost_reason,
                priority=priority,
                lead_score=random.randint(40, 98),
                consent=True,
                assigned_user_id=admin_user.id,
                team_id=team_id,
                created_at=created_time,
                updated_at=created_time,
            )
            leads_to_create.append(lead)

        # Create 1,800 for the rest of Team A
        for i in range(1800):
            lead_counter += 1
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            assigned_rep = random.choice(other_members)
            status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
            priority = random.choices(PRIORITIES, weights=PRIORITY_WEIGHTS)[0]
            source = random.choice(SOURCES)
            created_days_ago = random.randint(1, 25)
            created_time = now - timedelta(days=created_days_ago, hours=random.randint(0, 23))

            lost_reason = random.choice(["price", "timing", "competitor", "other"]) if status == "lost" else None

            lead = Lead(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}.{lead_counter}@presentation.test",
                phone=f"+1202{random.randint(1000000, 9999999)}",
                company_name=random.choice(COMPANIES),
                source=source,
                source_campaign="Presentation Campaign" if random.random() > 0.4 else None,
                status=status,
                lost_reason=lost_reason,
                priority=priority,
                lead_score=random.randint(35, 95),
                consent=True,
                assigned_user_id=assigned_rep,
                team_id=team_id,
                created_at=created_time,
                updated_at=created_time,
            )
            leads_to_create.append(lead)

        db.bulk_save_objects(leads_to_create)
        db.flush()
        print(f"Created {len(leads_to_create)} leads (200 for Admin, 1,800 for Team members).")

        # 5. Create some lively sample Tasks for Admin (Follow-ups & Overdue)
        tasks_to_create: list[Task] = []
        admin_leads = [ld for ld in leads_to_create if ld.assigned_user_id == admin_user.id][:30]

        # 12 Follow-ups due today
        for idx, ld in enumerate(admin_leads[:12]):
            tasks_to_create.append(
                Task(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    lead_id=ld.id,
                    title=f"Call {ld.name} - Follow up on demo",
                    notes="Discuss pricing tier and contract terms.",
                    type="follow_up",
                    status="open",
                    due_at=now.replace(hour=14, minute=0, second=0),
                    assigned_user_id=admin_user.id,
                    team_id=team_id,
                )
            )

        # 3 Overdue tasks
        for idx, ld in enumerate(admin_leads[12:15]):
            tasks_to_create.append(
                Task(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    lead_id=ld.id,
                    title=f"Send proposal email to {ld.name}",
                    notes="Review requested discounts with manager.",
                    type="follow_up",
                    status="open",
                    due_at=now - timedelta(days=2),
                    assigned_user_id=admin_user.id,
                    team_id=team_id,
                )
            )

        db.bulk_save_objects(tasks_to_create)
        db.flush()
        print(f"Created {len(tasks_to_create)} presentation tasks for Admin.")

    print("\nPresentation data successfully generated!")
    print("  - My View: 200 leads assigned to you (+ 12 follow-ups due today, 3 overdue)")
    print("  - Team View: 2,000 total leads in Sales Team A with full pipeline analytics")
    print("  - Company View: all leads visible")


if __name__ == "__main__":
    main()
