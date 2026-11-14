# AI Sales Assistant CRM

A secure, **multi-tenant SaaS CRM** with an AI sales assistant. Many companies use the same app, but each company's leads, conversations, users, integrations and reports stay private to that company.

> **Business value:** সম্ভাব্য Customer-দের সংগঠিত করা এবং Follow-up সহজ করা — organize potential customers and make follow-up easy.

**Goal:** In 15 build days (plus a Day 0 setup day), 5 developers build a working, secure, multi-company MVP.

**Stack:** Python (FastAPI) · PostgreSQL 16 · LLM API · n8n · React/Next.js · Docker

> 🔒 **Security rule for the whole project:** Do not skip or weaken any security step to save time. **Cut features instead.**

---

## Table of contents

1. [What we are building](#1-what-we-are-building)
2. [MVP scope](#2-mvp-scope)
3. [Architecture](#3-architecture)
4. [Tech stack](#4-tech-stack)
5. [Project structure](#5-project-structure)
6. [Getting started](#6-getting-started)
7. [Multi-tenant security (RLS)](#7-multi-tenant-security-rls)
8. [Roles & permissions](#8-roles--permissions)
9. [Database design](#9-database-design)
10. [Lead capture](#10-lead-capture)
11. [AI: classification & intent](#11-ai-classification--intent)
12. [n8n automation](#12-n8n-automation)
13. [API overview](#13-api-overview)
14. [Sales dashboards](#14-sales-dashboards)
15. [Security checklist](#15-security-checklist)
16. [Team workflow & contribution rules](#16-team-workflow--contribution-rules)
17. [15-day plan](#17-15-day-plan)
18. [Production-readiness checklist](#18-production-readiness-checklist)
19. [After the 15 days](#19-after-the-15-days)
20. [Glossary](#20-glossary)

---

## 1. What we are building

| Feature | What it means | Main module |
| --- | --- | --- |
| Lead Capture | Leads from website forms, WhatsApp, Facebook/Instagram, manual entry, CSV | `integrations`, `leads` |
| Lead Classification | AI sorts leads by type, interest, priority and score | `ai` |
| Customer Intent Detection | AI detects demo / pricing / support / info request, buying stage and sentiment | `ai` |
| Automatic Follow-up | n8n sends reminders and approved follow-ups; stops when the lead replies or opts out | `tasks`, `n8n/` |
| CRM Integration | Own REST API + webhooks; HubSpot/Salesforce connectors later (optional) | `integrations`, API |
| Sales Dashboard | Role-based dashboards for reps, managers and company admins | `dashboard`, frontend |

**Lead journey:** Capture → one CRM record with history → AI intent + classification + score → assign to rep → n8n follow-up → dashboard.

**Who does what (core rule):**

- **FastAPI (backend)** decides who can see and do what, and holds all business rules.
- **PostgreSQL** stores the real data. If it's not in the database, it didn't happen.
- **The LLM** only reads text and gives an opinion (intent, score). It never changes data.
- **n8n** only runs repeated or scheduled jobs, and always goes through our API.
- **React** only shows data and sends user actions to the API.

---

## 2. MVP scope

**✅ In scope (must ship)**

- Company signup + invite-based users
- Roles: Sales rep, Manager, Company admin (+ Platform admin, our team)
- Tenant isolation with PostgreSQL RLS
- Lead capture: website form, manual entry, CSV import, WhatsApp Cloud API
- Meta Lead Ads / Messenger in **test mode**
- Lead list, detail, assignment, status pipeline, notes, tasks
- AI classification, intent, scoring, summary, sentiment
- n8n: new-lead flow, follow-up reminders, reply handling
- Rep / manager / admin dashboards
- Docker deployment, backups, security tests

**⏭️ Out of scope (after Day 15)**

- Instagram & forum integrations
- HubSpot / Salesforce sync
- Billing, subscriptions, quotas
- Self-hosted LLM, vector DB, AI agents
- Microservices / Kubernetes
- n8n queue mode with Redis workers
- Separate DB per enterprise tenant

> ⚠️ Meta and WhatsApp production access needs app review and business verification. **Start the Meta developer app + WhatsApp test number setup on Day 1** so it is ready by Day 7.

### If we fall behind

Cut in this order: Meta Lead Ads/Messenger (Day 7) → tracking endpoint and round-robin (Day 6) → extra dashboard widgets (Day 13) → summary and sentiment (Day 8).

> 🚫 **Never cut:** RLS, auth, webhook signatures, MFA, encrypted credentials or the cross-tenant tests.

---

## 3. Architecture

```
Lead sources:   Website form · Tracking script · WhatsApp · Facebook · Manual · CSV
                                   │
Integration layer:   Webhooks · Signature check · Validation · Dedup (webhook_events)
                                   │
FastAPI backend:  Auth · Tenant context · RBAC · Leads · Tasks · Conversations · API
        │                      │                         │
   PostgreSQL (RLS)       LLM service              n8n automation
   system of record      (analysis only)     (reminders, follow-ups, notifications)
                                   │
Next.js dashboard:   Sales rep · Manager · Company admin
```

Leads come in from many places. They all enter through one door (the integration layer), which checks they are real and not duplicates. The backend saves them in the database, asks the AI for an opinion, and tells n8n to schedule follow-ups. The dashboard shows the result to each user based on their role.

> **Don't start with** microservices, Kubernetes, a vector database or an agent framework. Build one modular app first.

---

## 4. Tech stack

| Area | Technology | Purpose |
| --- | --- | --- |
| Frontend | Next.js + React + TypeScript | Lead lists, inbox, dashboards, settings |
| UI | Tailwind CSS + shadcn/ui + Recharts | Forms, tables, dialogs, charts |
| Data fetching | TanStack Query | API caching and state |
| Backend | Python 3.12 + FastAPI | APIs, business rules, permissions |
| Database | PostgreSQL 16 + RLS | Tenant-isolated system of record |
| ORM / migrations | SQLAlchemy 2 + Alembic | Models and schema changes |
| Validation | Pydantic v2 | Request/response and LLM output validation |
| AI | LLM API with structured JSON output | Intent, classification, scoring, summaries |
| Automation | n8n (self-hosted) | Follow-ups, reminders, notifications, retries |
| Auth | FastAPI + Argon2id + short-lived JWT + refresh rotation | Signup, login, reset, sessions |
| Testing | pytest, httpx, Playwright | Unit, API, cross-tenant and E2E tests |
| Deployment | Docker Compose + Caddy/Nginx (TLS) | Run and deploy |
| Files | Private S3-compatible storage | Attachments |

---

## 5. Project structure

```
ai-crm/
├── frontend/src/{app,components,dashboard,leads,conversations,tasks,settings}
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/        (config.py, security.py, permissions.py, tenancy.py)
│   │   ├── modules/     (auth, tenants, users, leads, conversations, tasks,
│   │   │                 ai, integrations, dashboard, audit)
│   │   ├── database/
│   │   └── schemas/
│   ├── alembic/
│   ├── tests/           (unit, api, cross_tenant, e2e)
│   └── requirements.txt
├── n8n/workflows/
├── infrastructure/{docker-compose.yml, reverse-proxy/}
└── README.md
```

Each backend module contains `models.py`, `schemas.py`, `service.py`, `router.py` and `tests/`, so 5 developers can work in parallel with minimal merge conflicts.

Companion docs: [`PRODUCT_REQUIREMENTS.md`](./PRODUCT_REQUIREMENTS.md), [`ARCHITECTURE.md`](./ARCHITECTURE.md), [`SECURITY.md`](./SECURITY.md), [`DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md), [`API_CONTRACT.md`](./API_CONTRACT.md), [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`guide.txt`](./guide.txt).

---

## 6. Getting started

### Prerequisites

- Git access to this repository
- Docker and Docker Compose
- Python 3.12 (for running backend tooling outside Docker)
- Node.js (for the Next.js frontend)

### Run locally

1. Clone the repository and copy the example environment file (to be added with the repo skeleton on Day 1).
2. Start the stack: `docker compose up`
3. Run database migrations (Alembic).
4. Load seed data: 2 companies with 5 users each.
5. Open the API docs at **http://localhost:8000/docs**.

> The exact commands and environment variables are finalised on Day 1 when the monorepo and Docker Compose skeleton land. **Day 0 checkpoint:** every developer's machine can open `localhost:8000/docs`.

Local email (verification, password reset) is caught by **Mailpit**.

### Testing

- `pytest` for unit, API and cross-tenant tests
- Playwright for end-to-end tests
- CI runs `ruff` + `pytest` on every PR

---

## 7. Multi-tenant security (RLS)

This is the most important design decision in the project. All companies share one database. Every tenant-owned row has a `tenant_id`, and **PostgreSQL itself (Row-Level Security) hides other companies' rows**, even if application code forgets a filter.

**Rules**

- One PostgreSQL database, shared tables, `tenant_id` on every tenant-owned row, enforced by RLS.
- **Never trust a `tenant_id` sent by the browser.** The backend verifies membership and role on every request.
- RLS enabled with no matching policy means access is denied by default.
- Composite foreign keys include `tenant_id`, so Company A's lead cannot link to Company B's user.
- The app DB role must **not** be a superuser or have `BYPASSRLS`; use `FORCE ROW LEVEL SECURITY` so table owners are covered too.
- Isolation is built in on Day 3, not added later.

```sql
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads FORCE ROW LEVEL SECURITY;

CREATE POLICY leads_tenant_isolation ON leads
USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

Per transaction, the backend sets the verified tenant (transaction-local, safe with connection pooling):

```sql
SELECT set_config('app.tenant_id', 'verified-tenant-uuid', true);
```

Apply the same policy to **every** tenant-owned table. Later, large customers can get a separate schema or database.

---

## 8. Roles & permissions

| Role | Can do |
| --- | --- |
| Sales representative | View assigned leads, update status, read conversations, add notes, complete tasks, approve permitted follow-ups |
| Sales manager | View team leads, assign leads, monitor reps, review performance, manage team tasks |
| Company admin | Manage company users, roles, integrations, lead and automation settings, all company data |
| Platform admin (our team) | Manage tenants, platform health and support, separate from company admins |

- A company admin is **never** automatically a platform admin.
- Managers see their own team; company admins see all teams in their company.
- Support access to customer data must be temporary, approved and logged.

---

## 9. Database design

| Table | Purpose |
| --- | --- |
| `tenants` | Company accounts |
| `users` | User identity |
| `tenant_memberships` | User ↔ company + role |
| `teams` | Sales teams in a company |
| `leads` | Lead details, source, status, owner, priority, score |
| `contacts` | Customer records after conversion |
| `conversations` / `messages` | WhatsApp, Facebook and other chats |
| `interactions` | Website activity, form submits, calls, events |
| `lead_assessments` | AI intent, classification, score, model + prompt version |
| `tasks` | Calls, meetings, reminders, follow-ups |
| `integrations` | Connected accounts, scopes, encrypted credentials |
| `webhook_events` | Incoming events, processing status, dedup |
| `audit_logs` | Security and important user actions |

**`leads`**: `id, tenant_id, name, email, phone, company_name, source, source_campaign, external_id, status, lost_reason, assigned_user_id, team_id, intent, lead_score, priority, consent, opted_out, created_at, updated_at`

**`messages`**: `id, tenant_id, conversation_id, provider_message_id, direction, message_text, attachment_reference, created_at`

**Indexes:** `(tenant_id, created_at)`, `(tenant_id, assigned_user_id)`, `(tenant_id, status)`, unique `(tenant_id, provider, provider_message_id)`.

**Lead status pipeline:** new → contacted → qualified → proposal → won / lost (with a lost reason).

---

## 10. Lead capture

| Source | How | What to capture |
| --- | --- | --- |
| Website forms | Form posts to FastAPI | Name, email, phone, requirement, consent, UTM |
| Website activity | Small first-party tracking script | Page visits, pricing views, demo requests |
| Facebook Lead Ads | Meta lead webhook + API fetch | Form fields, campaign, ad |
| Messenger | Messenger Platform | Messages, conversation IDs |
| WhatsApp | WhatsApp Cloud API | Messages, phone, history |
| Manual / CSV | CRM form and import | Rep-entered details |

**One pipeline for every channel**, so the logic is written once and tested once:

1. Endpoint receives webhook / form.
2. Validate the request and check the provider signature.
3. Skip if the event was already processed (`webhook_events`).
4. Find or create the lead (dedupe by email / phone / external ID).
5. Store the interaction or message.
6. Request AI assessment.
7. Assign the lead and create a task if rules say so.

Notes: Meta webhooks may only contain an ID, so fetch details via API. Prefer official APIs over scraping. Disclose tracking and collect consent where required.

---

## 11. AI: classification & intent

We send the customer's message to the LLM and ask it to fill in a fixed form (**structured JSON**). Our backend validates the answer and then decides what to do. **The AI gives advice; our code makes the decisions.**

Example message: *"I need a CRM for my 20-person sales team. Please arrange a demo this week."*

```json
{
  "category": "business_customer",
  "intent": "request_demo",
  "interest": "CRM software",
  "buying_stage": "consideration",
  "sentiment": "positive",
  "priority": "high",
  "lead_score": 90,
  "recommended_action": "schedule_demo",
  "follow_up_days": 0,
  "confidence": 0.94
}
```

| AI feature | Does |
| --- | --- |
| Classification | Type, industry, product interest, customer category |
| Intent detection | Demo, pricing, support, info, complaint |
| Lead scoring | Value / urgency estimate, combined with rule-based signals |
| Summary | Summarizes long conversations |
| Sentiment | Positive / neutral / negative |
| Recommended action | Call, demo, email or follow-up |

**Flow:** get permitted history → redact unnecessary PII → structured prompt → validate with Pydantic → save with model + prompt version → deterministic rules decide tasks and approval.

- The backend AI service redacts supplied lead identifiers plus email/phone patterns, builds a versioned prompt input, validates structured assessment output, and persists only redacted validated output with the model and prompt version.
- Conversation analysis uses the OpenAI API to summarize recent messages and classify customer sentiment. Configure `OPENAI_API_KEY` and optionally `OPENAI_MODEL` in the deployment environment; message content is redacted before it is sent.
- `POST /api/v1/conversations/{conversation_id}/analyze` generates and stores a conversation analysis; `GET /api/v1/conversations/{conversation_id}/analysis` returns its latest summary and sentiment.
- The LLM never modifies data, assigns permissions or sends messages directly.
- Low confidence (e.g. < 0.6) → mark for human review.
- Bangla and English are both supported and both included in the evaluation set.
- Privacy: text sent to a hosted LLM leaves our server. Choose a provider with suitable retention and contract terms.

---

## 12. n8n automation

n8n runs repeated jobs (reminders, due follow-ups). It **never touches the database directly**. It calls our API like any other client, and FastAPI still checks permissions, rules and the tenant.

- **Workflow A, new lead:** event → fetch lead via API → AI assessment → assign + task → notify rep.
- **Workflow B, follow-up:** schedule → due tasks from API → check consent, opt-out, quiet hours, status, replies → send approved message or request approval → save result.
- **Workflow C, customer reply:** save message → pause follow-ups → re-run intent → notify rep → new task if needed.

**Rules**

- The n8n editor is private; customers never access or edit workflows.
- FastAPI ↔ n8n use authenticated internal requests (HMAC service auth); no unrestricted DB access for n8n.
- Unique event IDs + idempotency keys prevent duplicate messages and tasks.
- Safe retries with logging; minimal PII in execution logs; set execution data retention.
- Stable encryption key stored outside the workflow DB; keep n8n updated; TLS via reverse proxy.
- **Licensing:** the Sustainable Use License can cover workflows we run for clients if they can't access or change them. Customer-configurable workflows or white-labeling may need a commercial license. Confirm with n8n before launch.

Workflow exports live in `n8n/workflows/`.

---

## 13. API overview

Interactive docs are served at `/docs` (OpenAPI). The contract is agreed **before** coding.

```
POST   /api/v1/auth/signup | /login | /refresh | /logout | /password-reset
POST   /api/v1/invitations          POST /api/v1/invitations/{token}/accept
GET    /api/v1/users                PATCH /api/v1/users/{id}
GET    /api/v1/teams                POST  /api/v1/teams

POST   /api/v1/leads                GET   /api/v1/leads
GET    /api/v1/leads/{id}           PATCH /api/v1/leads/{id}
POST   /api/v1/leads/{id}/assign    POST  /api/v1/leads/import
GET    /api/v1/leads/{id}/timeline  GET   /api/v1/leads/{id}/assessments

GET    /api/v1/conversations        POST  /api/v1/messages
POST   /api/v1/tasks                GET   /api/v1/tasks
PATCH  /api/v1/tasks/{id}           GET   /api/v1/tasks/due-follow-ups

GET    /api/v1/dashboard/summary?scope=me|team|company

POST   /api/v1/integrations/{provider}/connect
POST   /api/v1/webhooks/{provider}
POST   /api/v1/public/forms/{form_id}/submit
POST   /internal/v1/automation/*     (n8n only, service auth)
```

For each integration we store: owner, provider account ID, scopes, expiry and encrypted credentials.

---

## 14. Sales dashboards

| Sales rep | Sales manager | Company admin |
| --- | --- | --- |
| My new leads | Leads by source | Overall sales performance |
| My high-priority leads | Leads per rep | Team & rep performance |
| Follow-ups due today | Avg. first-response time | Lead-source performance |
| Overdue tasks | Follow-up completion rate | Integration health |
| Recent conversations | Conversion by rep | Automation success/failure |
| My conversion rate | Pipeline stages, lost reasons | Users & roles |

All dashboard queries are filtered by tenant **and** role on the server.

---

## 15. Security checklist

Everything here is required for the MVP.

**Authentication:** email verification, Argon2id, MFA for admins, single-use short-lived reset tokens, short-lived access tokens, refresh rotation + revocation, login rate limits, invite-only joining.

| Risk | Protection |
| --- | --- |
| Cross-company leakage | Tenant verification, RLS, authorization tests |
| Password attacks | Argon2id, MFA, rate limits |
| SQL injection | Parameterized queries / ORM |
| Unauthorized APIs | Server-side auth + permission checks |
| CSRF / XSS | Secure cookies, CSRF tokens, escaping, CSP |
| Webhook spoofing | Provider signature validation |
| Credential theft | Encryption, restricted access, rotation |
| API abuse | Tenant-aware rate limits, validation, quotas |
| Server attacks | Firewall, updates, monitoring |

**Data protection:** TLS everywhere, encryption at rest, KMS/secrets manager for tokens, separate DB credentials (app / n8n / admin), no public DB port, encrypted off-server backups, audit logs, retention/export/deletion policy, logged temporary support access.

---

## 16. Team workflow & contribution rules

### How we work

All 5 developers work on the **same layer at the same time** (e.g. everyone on backend), each building a **different feature of that layer**. At the end of the day the features are integrated and demoed together. Tasks **rotate** so everyone learns every part of the project. Whoever builds a module fixes its bugs and documents it.

- 15 build days × 5 hours = 75 hours per developer, plus a Day 0 setup day.
- Each developer owns exactly 3 hard (★) tasks.

### Daily rhythm (Asia/Dhaka)

| Time | Activity |
| --- | --- |
| 10:00 – 10:15 | Stand-up: yesterday, today, blockers |
| 10:15 – 13:30 | Build own feature on the day's layer (shared contracts posted in the first hour) |
| 13:30 – 14:30 | **Integration window:** merge PRs, fix conflicts, run the full test suite |
| 14:30 – 15:00 | Team demo of the integrated result + plan tomorrow |

### Git & quality rules

- Branches: `main` (release) ← `develop` (daily integration) ← `feature/<dev>-<feature>`
- Every PR needs green CI (lint + tests) and the reviews below
- API contract first: agree request/response schemas (OpenAPI) **before** coding
- Small PRs, merged at least once a day. No big-bang merges on Day 14
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`
- Announce in chat before creating a migration, to avoid Alembic "multiple heads"
- Publish shared contracts (API conventions, capture service, dashboard queries) in the first hour so others can build against them

### Review rules

- **Ring review:** Dev 1 → Dev 2 → Dev 3 → Dev 4 → Dev 5 → Dev 1 (each reviews the next developer's PRs).
- **★ PRs get two reviewers.**
- **Security approver:** any PR touching auth, tenant context/RLS, permissions (RBAC) or webhooks needs two approvals: the ring reviewer **plus Dev 1** (Dev 4 if Dev 1 is the author). No exceptions.
- **Mob the first hour** on Days 3 and 7 (RLS, webhooks): all 5 on one screen, then split.
- **Senior help:** try to get a senior for about an hour on Days 3, 7 and 14.

### Definition of Done (per task)

- [ ] Code merged into `develop`
- [ ] Unit / API tests written and passing
- [ ] Tenant isolation respected (no query without tenant context)
- [ ] Reviewed by the ring reviewer; if ★ or it touches auth, RLS or webhooks, also approved by the security approver
- [ ] Endpoint visible in `/docs` (OpenAPI)
- [ ] Demoed at the end-of-day session

---

## 17. 15-day plan

| Phase | Days | Focus | Outcome |
| --- | --- | --- | --- |
| Setup | 0 | Tools, Docker, FastAPI & RLS primer | All 5 PCs open `localhost:8000/docs` |
| 1. Foundation | 1–3 | Repo, DB models, auth, multi-tenancy | Signup/login works; cross-tenant tests pass |
| 2. CRM core & first slice | 4–5 | CRM APIs, first UI, staging | Log in on staging → create lead → see it in the list |
| 3. Lead capture | 6–7 | Capture pipeline, webhooks, integrations | All sources create leads through one service; no duplicates |
| 4. AI | 8–9 | LLM pieces, wiring, evaluation | Every new lead gets an assessment; accuracy recorded |
| 5. Automation | 10–11 | n8n workflows A, B, C | WhatsApp lead → assessed → assigned → reminder → reply → follow-ups pause |
| 6. Frontend & dashboards | 12–13 | Screens and role dashboards | Rep works fully in the UI; each role sees only its data |
| 7. Harden & ship | 14–15 | Security, tests, deploy, demo | Checklist tested; deployed MVP + live demo |

### Daily checkpoints

| Day | Checkpoint |
| --- | --- |
| 0 | All 5 PCs can open `localhost:8000/docs` |
| 1 | `docker compose up` → migrate → seed works on every PC; API contract agreed |
| 2 | Admin signs up, invites a rep, rep logs in |
| 3 | Cross-tenant tests pass; the app role cannot bypass RLS |
| 4 | Create lead → assign → note and task → timeline, all in `/docs` |
| 5 | Log in on the staging URL → create a lead → see it in the list |
| 6 | Form, CSV and manual entry create leads through one service |
| 7 | Same webhook sent twice creates no duplicates; bad signature rejected |
| 8 | One message goes in and a validated assessment comes out |
| 9 | Every new lead gets an assessment; accuracy recorded |
| 10 | A new lead triggers Workflow A automatically |
| 11 | WhatsApp lead → assessed → assigned → reminder → reply → follow-ups pause |
| 12 | A rep reads the AI insight, replies and completes a task entirely in the UI |
| 13 | Each role sees only its own data; changing API params reveals nothing else |
| 14 | Every checklist item is tested; bug list prioritized |
| 15 | Live demo, retrospective, post-MVP backlog |

The detailed per-developer, day-by-day task tables are in the full project guide.

---

## 18. Production-readiness checklist

- [ ] Company A cannot read, update or delete Company B's data
- [ ] A sales rep cannot access unauthorized team leads
- [ ] A manager cannot access another company's dashboard
- [ ] A company admin cannot access platform administration
- [ ] Duplicate webhooks don't create duplicate leads or messages
- [ ] Follow-ups stop when the lead replies or opts out
- [ ] n8n cannot retrieve unrestricted data from other tenants
- [ ] Integration credentials are encrypted and hidden from ordinary users
- [ ] Backups restore correctly; tenant data can be securely deleted
- [ ] Failed workflows are logged and safely retryable
- [ ] Logs contain no passwords, tokens or unnecessary message content

---

## 19. After the 15 days

| Phase | Adds |
| --- | --- |
| Next | Instagram, forums, WhatsApp/Meta production approval |
| Then | HubSpot / Salesforce sync, email channel |
| SaaS readiness | Billing, quotas, monitoring/alerts, n8n queue mode |
| Scale | Dedicated schema/DB for large tenants, self-hosted LLM option |

**Priority order:** secure tenant isolation → CRM core → AI → automation. If isolation is wrong, no AI or dashboard makes this a safe SaaS product.

---

## 20. Glossary

| Term | Plain meaning |
| --- | --- |
| Tenant | One customer company using our app |
| Multi-tenant | Many companies share one app and one database, but can never see each other's data |
| RLS (Row-Level Security) | A PostgreSQL feature that hides other companies' rows, even if our code forgets a filter |
| RBAC | Role-based access: what a rep, manager or admin is allowed to do |
| JWT / refresh token | Login "tickets". The access token expires quickly; the refresh token gets a new one |
| Argon2id | A safe way to store passwords. We never store the real password |
| Webhook | Another service (WhatsApp, Meta) calls our URL to tell us something happened |
| Signature check | Proof that a webhook really came from the provider and not from an attacker |
| Idempotency / dedup | Sending the same request twice has the same effect as once. No duplicate leads or messages |
| LLM | The AI model that reads text and returns intent, score and summary |
| Structured JSON output | The AI answers in a fixed format that our code can check |
| n8n | A tool that runs automated workflows (reminders, follow-ups) |
| Migration (Alembic) | A versioned script that changes the database structure |
| PII | Personal data such as names, phone numbers and emails |
| API contract (OpenAPI) | The agreed request/response format, visible at `/docs` |