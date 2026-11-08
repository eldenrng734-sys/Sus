# Architecture

> **Status:** implementation-aware architecture for the 15-day MVP. The repository is an early backend scaffold, **not a working CRM or production-ready SaaS**.
> **Implemented** means present in source; **configured** means declared in infrastructure, not verified as deployed; **target** means required but not built; **proposal** means a design detail still needing approval.
> Unless explicitly identified as current, the flows and controls below describe the **target architecture**.

This document explains component boundaries, data flow, tenancy, reliability and deployment. It does not replace the detailed product, API, schema or security specifications.

| Reference | Authority |
| --- | --- |
| [PRODUCT_REQUIREMENTS.md](./PRODUCT_REQUIREMENTS.md), [guide.txt](./guide.txt) | Product scope, delivery priorities and team plan |
| [SECURITY.md](./SECURITY.md) | Mandatory controls and security approval; security requirements take precedence |
| [API_CONTRACT.md](./API_CONTRACT.md) | Target routes, headers, payload conventions and service authentication |
| [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) | Target tables, constraints, RLS policies and database roles |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Contribution, review and definition-of-done rules |

Code is evidence of what exists, not evidence that all target controls are satisfied. Generated OpenAPI describes implemented endpoints only. Resolve documentation conflicts explicitly in review; do not silently weaken security or treat a proposed design as approved.

## Contents

1. [Overview](#1-overview)
2. [System diagram](#2-system-diagram)
3. [Who does what (core rule)](#3-who-does-what-core-rule)
4. [Tech stack](#4-tech-stack)
5. [Repository structure](#5-repository-structure)
6. [Request lifecycle](#6-request-lifecycle)
7. [Lead capture pipeline](#7-lead-capture-pipeline)
8. [AI layer](#8-ai-layer)
9. [Automation (n8n)](#9-automation-n8n)
10. [Frontend](#10-frontend)
11. [Deployment](#11-deployment)
12. [Architecture decisions (summary)](#12-architecture-decisions-summary)
13. [Changing this document](#13-changing-this-document)
14. [Reliability and transaction boundaries](#14-reliability-and-transaction-boundaries)
15. [Observability and operations](#15-observability-and-operations)
16. [Verification and release gates](#16-verification-and-release-gates)
17. [Implementation order and open decisions](#17-implementation-order-and-open-decisions)

---

## 1. Overview

The target is a **multi-tenant SaaS CRM implemented as a modular monolith**: one backend codebase and one shared PostgreSQL CRM database, with tenant isolation enforced by RLS and role/team visibility enforced by backend authorization.

Business journey: capture a lead → preserve one CRM history → assess intent and priority → assign a rep → perform safe follow-up → show role-scoped dashboards. AI failure must not prevent lead capture or human follow-up.

### Current implementation baseline

| Area | What exists now | What must not be assumed |
| --- | --- | --- |
| HTTP application | [main.py](./backend/app/main.py): FastAPI `0.1.0`, `GET /health` returning `{"status":"ok"}`, default OpenAPI/docs | No CRM routers, auth, middleware, readiness or DB connectivity checks |
| Configuration | [config.py](./backend/app/core/config.py): `app_env`, `database_url`, `.env` loading, extra settings ignored | Settings are not wired into the health-only application; production validation is absent |
| Persistence definitions | SQLAlchemy base/mixins, naming conventions and registry; five models: `tenants`, `users`, `tenant_memberships`, `teams`, `audit_logs` | Model definitions do not create a database; no engine/session dependency or executable migration chain exists |
| Security | Some model CHECK, unique and composite-FK constraints | No implemented authentication, RBAC, RLS policies, tenant resolver, MFA or encrypted integration storage |
| Infrastructure | Development Compose declares PostgreSQL 16 and a backend; Dockerfile uses Python 3.12 | No frontend, worker, n8n or reverse-proxy service is configured |
| Tests and CI | One health API test; CI declares Ruff lint, Ruff format check and pytest on Python 3.12 | No database, cross-tenant, provider, AI, workflow or browser test coverage yet |
| Other components | Empty frontend, n8n workflow and reverse-proxy directories | No UI application, workflow exports or TLS routing implementation |

**MVP scope:** onboarding, tenant isolation, CRM core, website/manual/CSV/WhatsApp capture, advisory AI, follow-ups and role dashboards. Meta Lead Ads/Messenger is test-mode, lower-priority scope. Tracking is optional/cuttable; Instagram, forums, billing, external CRM sync and autonomous AI are not MVP requirements.

---

## 2. System diagram

### Current development topology

```text
Host :8000 ──► backend /health       No database access from this route
                   │
                   └── Compose waits for database health before startup

Host 127.0.0.1:5433 ──► db:5432     PostgreSQL 16; persistent pgdata volume
```

### Target topology (not yet implemented)

```text
Browser ──TLS──► reverse proxy ──► Next.js dashboard
                     │
Forms / providers ────┴──────────► FastAPI public API /api/v1/*
                                       │
                         auth / tenant resolution / RBAC
                                       │
                               module services
                                       │
                               PostgreSQL CRM
                            business data + outbox
                                       ▲
                                       │ tenant-scoped transactions
                          backend-owned worker process
                              │                  │
                              ▼                  ▼ signed events
                         hosted LLM         private n8n
                                                │ service-auth requests
                                                ▼
                                  FastAPI /internal/v1/automation/*
```

The worker is a separate process from the **same backend codebase**, not a new microservice. PostgreSQL and n8n are private; the public proxy must reject `/internal/*`. n8n may have its own workflow database but receives **no CRM database credentials**. FastAPI alone communicates with messaging providers and the LLM through backend adapters.

---

## 3. Who does what (core rule)

| Component | Responsibility | Boundary |
| --- | --- | --- |
| **FastAPI services** | Business rules, tenant/role checks, assignment, approval, validation and CRM writes | Never trust client-selected tenancy or role without server verification |
| **PostgreSQL CRM** | System of record, constraints, tenant RLS, durable job/event state | App and worker must not use owner, superuser or `BYPASSRLS` credentials |
| **Backend worker** | Claim durable work, run assessments/imports, deliver events, retry safely | Establish tenant context for every job; do not bypass the service layer |
| **LLM** | Return structured advisory classifications, scores and summaries | No tools, database access, message sending or permission decisions |
| **n8n** | Schedule/orchestrate workflows through narrow internal APIs | No direct CRM SQL, LLM calls, independent assignment rules or provider sends |
| **Next.js frontend** | Display data, collect actions, manage UI state | Route guards are UX, not authorization; no backend/provider secrets |

**Rule of thumb:** AI advises, n8n schedules, the frontend displays, and backend services decide. Durable state belongs in PostgreSQL, not in process memory or n8n execution history.

---

## 4. Tech stack

| Area | Current evidence | Target / limitation |
| --- | --- | --- |
| Backend/runtime | FastAPI; Python 3.12 in Docker and CI | Modular monolith; one codebase for API and worker |
| ORM/driver | SQLAlchemy `>=2.0`, `psycopg[binary]` declared | Engine, session lifecycle and tenant dependencies still missing |
| Database | `postgres:16` in Compose | Shared schema with `ENABLE` + `FORCE ROW LEVEL SECURITY`; not implemented |
| Migrations | Alembic dependency; root `env.py` exposes metadata | No `alembic.ini`, migration environment or revisions; not runnable yet |
| Validation/config | Pydantic `>=2.0`, pydantic-settings | Strict request and LLM output schemas still to build |
| Frontend | Placeholder directory only | Next.js App Router, React, strict TypeScript; UI/query packages require frontend setup and confirmation |
| Authentication | No auth library or implementation | Argon2id, short-lived JWTs, refresh rotation, admin MFA; select libraries in security review |
| AI | No provider SDK/client | Hosted structured-output LLM behind one backend adapter; provider/model still undecided |
| Automation/jobs | No runner or workflow implementation | PostgreSQL outbox + backend worker; private self-hosted n8n |
| Quality | pytest, httpx, Ruff declared | PostgreSQL isolation/integration tests; Playwright after frontend setup |
| Deployment/files | Backend Dockerfile and development Compose | TLS proxy and private attachment storage still to design/configure |

Tailwind CSS, shadcn/ui, Recharts, TanStack Query and S3-compatible storage are **candidate choices from the earlier design, not installed dependencies**. Do not build against them until confirmed. Backend requirements are largely unpinned; reproducible dependency/version management is a release prerequisite.

**Not in the MVP:** microservices, Kubernetes, vector databases, AI agent frameworks, Redis or n8n queue mode. Add infrastructure only for a demonstrated need.

---

## 5. Repository structure

Paths below are relative to the repository root; markers describe the current checkout.

```text
backend/
  app/
    main.py                       health-only FastAPI entry point
    core/config.py                settings definition
    database/{base,registry}.py   ORM foundation and model imports
    modules/
      tenants/models.py           Tenant, Team, TenantMembership
      users/models.py             User
      audit/models.py             AuditLog
      auth/                       empty package
      leads/                      empty package
      conversations/              empty package
      tasks/                      empty package
      ai/                         empty package
      integrations/               empty package
      dashboard/                  empty package
    schemas/                      empty package
  alembic/                        placeholder only
  tests/test_health.py
  Dockerfile
  pyproject.toml
  requirements.txt
frontend/                         placeholder only
n8n/workflows/                    placeholder only
infrastructure/
  docker-compose.yml              development backend + PostgreSQL
  reverse-proxy/                  placeholder only
.github/workflows/ci.yml
.env.example
env.py                            metadata fragment, not a migration environment
```

Project documentation currently lives at the root; there is no `docs/` directory or `AGENTS.md`. `CRM/` is an ignored local Python virtual environment, **not another CRM application**. Do not commit it or rely on it existing in other checkouts.

### Target module layout and dependency rules

Add files when their feature is implemented; empty boilerplate is not a completed module.

| File / area | Responsibility |
| --- | --- |
| `router.py` | HTTP validation, dependencies, service invocation, response mapping; no business SQL |
| `schemas.py` | Module request/response and validated domain input/output shapes |
| `service.py` | Business operations and authorization-sensitive invariants |
| `models.py` | Module-owned SQLAlchemy models; tenant-owned models require `tenant_id` |
| `tests/` or `backend/tests/` | Module tests; shared isolation/integration suites remain under backend tests |
| `core/` | Shared config, authentication, permissions and tenant context, not feature business logic |
| `database/` | Base/registry, future engine/session setup and transaction helpers |
| `schemas/` | Shared API envelopes, errors and pagination, not a dumping ground for domain schemas |

Dependency direction: **router → service → models/database**. Cross-module business operations use service interfaces; model imports for metadata and foreign-key definitions are legitimate exceptions. Services accept a shared transaction/context; do not hide independent commits inside nested service calls.

| Module | Target ownership |
| --- | --- |
| `auth` | Login, sessions, invitations, verification, password reset, MFA |
| `tenants`, `users` | Companies, teams, memberships and global user identity |
| `leads` | Canonical lead capture/upsert, status pipeline, assignment, interactions and timeline |
| `conversations` | Conversations/messages, reply handling and outbound delivery state |
| `tasks` | Tasks, due follow-ups, approval and pause/cancel rules |
| `ai` | LLM adapter, prompt versions, assessment validation/history and review state |
| `integrations` | Provider signatures/adapters, form resolution, webhook receipts and credentials |
| `dashboard` | Read-only tenant/role-scoped aggregates; no separate source of business truth |
| `audit` | Redacted security/business audit records; platform and tenant visibility kept separate |

Global `users`, the `tenants` root and nullable platform audit records need explicit policies; do not mechanically add `tenant_id` to every model. The existing membership model supports one optional team per tenant membership; multi-team managers require a reviewed schema change, not UI-only support.

---

## 6. Request lifecycle

**Current:** only `/health` is implemented; it has no authentication or database dependency. `/docs` and `/openapi.json` are generated by FastAPI. All business request handling below is target behavior.

### Tenant API request

```text
Request + request ID
  → validate access JWT/session and active user
  → read X-Tenant-ID as an untrusted tenant selector
  → resolve active membership + active tenant through a narrow trusted lookup
  → begin business transaction and set verified tenant context
  → authorize role/team/resource scope
  → router → service → database
  → persist business changes + required audit/outbox records
  → commit before returning success; rollback on failure
```

Use a parameterized transaction-local setting on the **same connection/transaction** as the business queries:

```sql
SELECT set_config('app.tenant_id', :verified_tenant_id, true);
```

- `X-Tenant-ID` is not proof of authorization. Never accept tenant identity from a business request body or query parameter.
- Membership and tenant status must be checked on every request; JWT role claims or UI state are not authoritative.
- Set tenant context before any tenant-data query. Never use session-global settings that can leak through connection pooling.
- Commit/rollback ends the context. Each worker job and internal request needs a fresh verified context; missing context must deny access.
- RLS isolates **companies**. Services separately enforce `rep` (assigned), `manager` (team), `admin` (company) scope, including dashboards and child resources.
- Composite foreign keys include `tenant_id`, preventing cross-company references even when an ID is valid globally.

### Requests without an ordinary user membership

| Request type | Trusted resolution and boundary |
| --- | --- |
| Signup/login/refresh/invitation | Narrow identity/bootstrap path; no unrestricted tenant reads before authentication |
| Public form | Server-side `form_id` mapping + validation, consent and abuse controls |
| Provider webhook | Verify raw-body signature, then resolve provider account to an active integration/tenant |
| Internal automation | Service authentication, approved tenant scope and resource ownership; never a user JWT substitute |
| Background work | Trusted persisted job metadata; re-establish tenant context before business access |
| Platform administration | Separate namespace and platform role + MFA; no ordinary tenant-data access |

Exact bootstrap/resolver functions and privileges are still open in the schema/security review. Do not solve the bootstrap problem with a superuser app connection, a broad RLS bypass, or a client-controlled SQL setting.

Target namespaces are `/api/v1/*` for public/business APIs and `/internal/v1/automation/*` for private automation. `/health` is liveness only; target `/health/ready` must check database access and required schema availability. Follow the API contract for errors, pagination, idempotency and status codes rather than defining competing formats here.

---

## 7. Lead capture pipeline

All channels converge on the **same lead service**, not the same HTTP authentication mechanism. Adapters normalize source-specific input; they do not implement separate lead/assignment logic.

```text
Manual / CSV ── user authorization ──┐
Website form ── form verification ──┼──► normalized capture input
WhatsApp/Meta ── signed webhook ────┘            │
                                               ▼
                             tenant-scoped lead capture service
                             normalize → deduplicate → upsert lead
                             → store interaction/message + audit
                             → deterministic assignment when applicable
                             → durable assessment/event work
                                               │
                                             commit
                                               │
                                 worker → assessment / n8n delivery
```

### Inbound provider receipt

1. Enforce body-size limits and verify `X-Hub-Signature-256` over the **raw body**, before parsing JSON, with constant-time comparison.
2. Resolve the provider account through the approved integration mapping. Unknown, revoked or suspended mappings must not enter the capture pipeline.
3. Persist a verified `webhook_events` receipt and durable processing work transactionally. Acknowledge only after commit, without waiting for provider lookups, AI or n8n.
4. Process asynchronously under that tenant: fetch missing provider details through official APIs, normalize input and call the canonical capture service.
5. Mark processing outcome durably. A duplicate receipt must not create duplicate leads/messages; a previous failure must remain retryable.

The target schema uses `(provider, external_event_id)` for webhook deduplication; confirm real provider ID scope before adopting it. Deduplicate messages by provider message identity. Lead capture uses tenant-scoped normalized email/phone lookup-and-merge and a hard `(tenant_id, source, external_id)` key where present. Do not blindly merge ambiguous contacts or assume email/phone are globally unique.

Public forms require consent, abuse protection and configured origins; responses must not reveal lead/tenant identifiers. CSV import is a durable, size/row-limited job with validation and dry-run reporting. Tracking remains optional and must not become a source of unrestricted browser-supplied tenant IDs.

**Ownership:** the capture service owns lead creation, initial assessment enqueueing and deterministic assignment. AI may refine priority later; it does not block capture. n8n must not independently repeat those operations. Use database constraints/idempotency for races, not only a lookup followed by an unprotected insert.

---

## 8. AI layer

**Target:** one backend-owned adapter in `modules/ai/`. Neither n8n nor the frontend calls the LLM provider directly.

```text
Durable assessment job
  → load permitted tenant history + record input version
  → minimize/redact PII and build a versioned prompt
  → call hosted LLM outside the DB transaction
  → validate strict structured output
  → persist assessment/model/prompt version and review state
  → apply deterministic backend rules only if the result is still current
```

- Validate enums, score/confidence ranges and required fields with Pydantic; free-form model text is not a trusted command.
- Store assessment history in target `lead_assessments`; record model, prompt version, validated output, review state and usage/cost metadata where specified by the schema.
- Use bounded timeouts/retries. Invalid output, provider outage or exhausted retries produces a recorded fallback/failure and a human-review path, not a lost lead.
- The project threshold is `confidence < 0.6` for review. It is a configurable rule to validate, not a claim that model confidence is calibrated.
- English and Bangla support needs a representative evaluation set and recorded results before being advertised as working.
- Customer text is untrusted, including instructions inside messages. The LLM has no tools, secrets, cross-tenant context or authority to send messages or assign permissions.
- Reassessment requests must coalesce with pending work. Duplicate jobs and stale results must not overwrite newer history, manual decisions or review outcomes. The precise version/job uniqueness key still needs review.

Use the same service for automatic assessments and authorized manual re-assessment. Keep sensitive prompt text and raw customer messages out of ordinary logs and n8n payloads.

---

## 9. Automation (n8n)

```text
Committed outbox event → backend dispatcher → signed n8n webhook
                                              │
                                              ▼
                              service-auth internal API request
                                              │
                              tenant + resource + business checks
```

| Workflow | n8n orchestration | Backend-owned invariant |
| --- | --- | --- |
| **A: New lead** | Fetch lead; request assessment only if missing/failed; ensure task and rep notification | Capture already owns initial assessment/assignment; never reassign or duplicate work |
| **B: Follow-up** | Request due tasks for an approved tenant; request an approved send/reminder; record result | Recheck consent, opt-out, approval, quiet hours, lead state and provider rules immediately before sending |
| **C: Customer reply** | React to persisted reply event; notify rep and request follow-on work if needed | Store inbound message and pause follow-ups before emitting the reply event, even if n8n is down |

- Private network only; the editor is not customer-facing. Internal endpoints expose specific resources or bounded tenant-scoped due tasks, never unrestricted cross-tenant exports.
- Use the API contract's allow-listed service identity, HMAC authentication, timestamp window and action idempotency. Resource IDs must belong to the verified tenant; possession of an ID is not authorization.
- Outbox delivery is **at least once**. n8n deduplicates `event_id`; each side effect also has a stable logical idempotency key and database-enforced business uniqueness.
- n8n requests message sending through the backend; it never receives messaging-provider credentials. WhatsApp sends must respect the 24-hour window and approved templates where required.
- Exports belong in `n8n/workflows/` without embedded credentials; minimize and expire execution data containing tenant content.

**Security design gap:** the current target HMAC canonical string signs method, path/query, timestamp and body hash, but not `X-Tenant-ID`, service ID or idempotency headers. Those headers must not be described as cryptographically bound today. Before implementation, security review must choose a tenant-bound credential/scope model and/or a versioned signature covering security-relevant headers, with synchronized API contract and tests. A shared service key plus arbitrary tenant selection is not sufficient isolation.

Scheduled workflows also need an approved tenant-dispatch mechanism; do not add an unrestricted “list all tenants/leads” route to make scheduling convenient.

---

## 10. Frontend

**Current:** `frontend/` contains only a placeholder; there is no package manifest, installed UI stack or runnable frontend.

Target areas are auth/onboarding, lead list/detail/timeline, conversations, tasks/approval queue, role dashboards and tenant settings. Use Next.js App Router and strict TypeScript when scaffolding is approved.

- One API client follows `API_CONTRACT.md`: access JWT in memory, rotated refresh token in an `HttpOnly` cookie, CSRF token and Origin checks for cookie-authenticated actions. This target choice still requires the security approval noted in the contract; never persist tokens in local storage.
- The contract specifies a 15-minute access token and 30-day refresh token. Centralize refresh/retry and session-expiry handling; do not scatter it across pages.
- Clear tenant-specific cached data on tenant switch/logout and include tenant identity in all data-cache keys. Cancel stale requests so a late response cannot repopulate the previous tenant's screen.
- Route guards and role-aware navigation improve UX only; API authorization remains mandatory for every action and aggregate.
- No direct database access or provider secrets in the frontend. User-triggered retries reuse the same logical idempotency key.
- The client-state/query/UI packages are not yet confirmed; do not present candidate libraries as implemented architecture.

---

## 11. Deployment

### Current development setup

[docker-compose.yml](./infrastructure/docker-compose.yml) declares `db` and `backend`, a persistent `pgdata` volume and a PostgreSQL healthcheck. The backend waits for DB health but its application still does not connect to the DB.

- PostgreSQL is published only on host `127.0.0.1:5433`, forwarding to container `5432`; this is local development access, not the target production topology.
- The backend publishes `8000:8000` without a loopback restriction. Do not treat it as private or deploy this file unchanged to an internet-facing host.
- The backend bind-mounts source and starts Uvicorn with `--reload`; these are development settings.
- `.env.example` uses `crm_owner` for the database URL. The official PostgreSQL initialization user is privileged; these credentials are not suitable for tenant business traffic.
- Inside Compose, PostgreSQL is `db:5432`. A host-run backend would use `localhost:5433` and appropriate separate credentials.
- `Settings` resolves `.env` relative to the process working directory. Invoke Compose with an explicit root env file; do not assume root `.env` is automatically loaded from the infrastructure directory.

From the repository root, once local `.env` is prepared, the existing development stack is defined by:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build
```

This command starts infrastructure; it does **not** create tables or apply RLS. There is currently no runnable `alembic upgrade head` workflow.

### Target production topology and gates

```text
Internet :443 → TLS reverse proxy → frontend / public backend routes
                                       │
Private network: backend API + worker + PostgreSQL + n8n
                 /internal/* reachable only by approved internal clients
```

1. Add an explicit production configuration: no source mounts or reload, non-root processes, resource limits and reproducible dependency/container versions.
2. Only the TLS proxy publishes customer-facing ports. Remove DB/backend/n8n host publishing; deny internal paths at the proxy and restrict private-network reachability.
3. Separate `crm_app`, `crm_worker`, migration-owner, operator and backup roles. App/worker neither own tables nor bypass RLS. n8n's own storage credentials must not access the CRM database.
4. Run reviewed Alembic migrations as a one-off deployment step, not on each API startup. Include RLS, constraints and least-privilege grants before exposing tenant routes.
5. Inject secrets through environment/secrets management; encrypt provider credentials and keep encryption keys separate. Validate required production settings at startup without logging secret values.
6. Add readiness checks, alerting and encrypted off-server backups with a demonstrated restore, including workflow configuration and recovery of required encryption keys.
7. Decide attachment limits/scanning/private storage before enabling uploads. Signed access must remain tenant-authorized; storage-provider selection is not implemented.

Docker Compose is the intended MVP deployment mechanism, not evidence that the current development file is production-ready. RLS, MFA, credential encryption, webhook verification and cross-tenant tests are non-negotiable release gates.

---

## 12. Architecture decisions (summary)

| Decision | Reason / trade-off | Status |
| --- | --- | --- |
| Modular monolith; worker shares backend code | Small team and short delivery window; avoid network boundaries between domain modules | Target; package skeleton exists |
| Shared schema + `tenant_id` + RLS | Economical isolation; requires disciplined roles, resolver design and real PostgreSQL tests | Target; models only |
| Global users, tenant memberships | One identity may join multiple companies; selected tenant is verified per request | Model foundation exists |
| Backend owns capture, assessment enqueueing and assignment | Prevent duplicate ownership between capture, worker and n8n | Target, aligned with API/schema docs |
| Durable PostgreSQL outbox | Business write and job intent commit together; no Redis needed for MVP | Target; worker/fan-out details still proposed |
| Advisory structured AI | Validatable, auditable and replaceable; human workflow survives provider failure | Target |
| n8n uses narrow internal APIs | One place for permissions, consent and send policy; requires service-scope design | Target |
| No frontend enforcement of permissions | UI is untrusted; server owns all resource and aggregate scoping | Target |

**Later, only when justified:** external CRM sync, dedicated schema/database for enterprise tenants, n8n queue mode, self-hosted LLMs and advanced analytics. No speculative infrastructure is required to finish the MVP.

---

## 13. Changing this document

Architecture changes need a focused PR and tech-lead review. Update the API contract for route/auth/event changes and the schema blueprint plus migrations for persistence changes. Changes affecting auth, tenant context/RLS, permissions or webhooks require the ring reviewer **and** security approver: Dev 1, or Dev 4 when Dev 1 authors the change. Ensure two distinct people approve.

Record decision, alternatives, trade-offs, migration/rollback impact and tests. Mark proposals as approved only after review; mark target features as implemented only when source, migrations and tests demonstrate them. Keep security documentation aligned in the same PR.

---

## 14. Reliability and transaction boundaries

### Durable asynchronous work

Use the target PostgreSQL `outbox_events` table for assessment/import intent and automation events. Do **not** rely on FastAPI in-process background callbacks or an in-memory queue for work that must survive a restart.

1. Business data, required audit records and outbox intent commit atomically. Never dispatch an event before the business commit.
2. A backend worker claims bounded work with a short transaction/lease. The exact claim mechanism, cross-tenant metadata access and privilege policy require schema/security approval.
3. Re-establish verified tenant context and load permitted input. Release transactions before LLM, provider or n8n network calls.
4. Persist results in a new short transaction after checking resource state/version again. Mark completion only when that consumer's durable effect is recorded.
5. Retry transient failures with bounded exponential backoff/jitter. Recover abandoned claims; exhausted work enters visible `failed`/`dead` state with redacted errors and controlled replay.

**Fan-out proposal requiring review:** assessment processing and n8n delivery must have independent completion state. A single `processed` flag cannot safely mean “every consumer succeeded.” Choose separate per-consumer work rows or delivery tracking before implementation, and align event types/schema accordingly.

### Idempotency is layered, not exactly-once delivery

| Boundary | Protection |
| --- | --- |
| Provider → backend | Durable receipt dedup + unique provider message identity |
| User/n8n retry → API | Contract-specific idempotency header, actor/tenant/route scope and request hash; conflict on changed payload |
| Capture → assessment/task | Stable logical job/task uniqueness; retries return existing pending/result state |
| Backend → n8n | Stable event ID + workflow dedup; action idempotency remains required |
| Backend → messaging provider | Durable outbound intent, provider idempotency/reconciliation where supported |

The API contract specifies 24-hour request-key retention; business uniqueness must outlive that cache where a repeated side effect would be unsafe. Idempotency keys alone do not guarantee that a timed-out provider send did not succeed. Ambiguous sends need reconciliation/manual review rather than blind retries.

### Ordering and race safety

- A reply/opt-out pauses relevant follow-ups in the backend transaction, independent of n8n availability. Send-time checks must observe that state and a single claimed task, not a stale workflow snapshot.
- Define a serialization/version check between follow-up eligibility and outbound intent. A message already accepted by a provider cannot be recalled; do not promise absolute cancellation across an external network boundary.
- Use the API contract's optimistic versioning for conflicting lead updates. Automatic assignment must not override manual assignment; outdated assessment work must not overwrite a newer assessment.
- Avoid holding DB locks while calling providers. Persist intent, perform the external call and reconcile the durable result with clear retry semantics.

---

## 15. Observability and operations

These controls are targets; the scaffold has no custom operational instrumentation yet.

- Structured logs carry request/correlation ID, event/job ID, tenant identifier where appropriate, outcome, duration and non-sensitive error code. Never log tokens, passwords, provider secrets, full webhook bodies or customer message text.
- Record security/business audits separately from diagnostic logs. Tenant audit reads exclude platform-level records; global/support actions have an explicit audited path.
- Track API latency/error rate, DB connection pressure, webhook failures/duplicates, outbox age/retries/dead work, LLM latency/fallback/cost and outbound failures. Alert on stuck work and isolation/security failures.
- `/health` remains process liveness. Readiness should fail when required DB/schema dependencies are unavailable; an LLM/n8n outage should degrade those features without pretending the core CRM is down.
- Store timestamps in UTC; use tenant timezone for quiet hours/reporting, with the contract's `Asia/Dhaka` default. Synchronize service clocks for signed-request replay windows.
- Define retention/export/deletion and backup restore procedures with the schema/security policy. Apply them to webhook payloads, workflow execution history, assessments and attachments, not just lead rows.

---

## 16. Verification and release gates

### Current executable checks

From the backend directory, using Python 3.12 with `requirements.txt` installed, CI runs:

```powershell
ruff check .
ruff format --check .
pytest
```

The only current test asserts `/health` returns `200` and `{"status":"ok"}`. It does not prove database access, tenant isolation or production readiness. CI currently provisions no PostgreSQL test service and performs no frontend/E2E or dependency-security scan.

### Required coverage before release

| Layer | Required evidence |
| --- | --- |
| Unit/service | Assignment, transitions, merge rules, consent, quiet hours, approvals, LLM validation/fallback |
| API contract | Routes/schemas/errors, auth/refresh/CSRF, role scope and idempotent replay/conflict |
| PostgreSQL integration | Alembic upgrade, real app/worker roles, RLS deny-without-context, read/write isolation, composite FKs and pool reuse |
| Cross-tenant/role | Two companies and rep/manager/admin users; changing headers, IDs, filters and aggregate queries cannot reveal unauthorized data |
| Bootstrap/internal security | Login/form/provider resolvers, forged signatures, expiry/replay, unauthorized tenant selection and platform/support boundaries |
| Jobs/workflows | Crash after commit, duplicate/late events, lease recovery, per-consumer retry, AI outage and reply-vs-send races |
| Browser | Onboarding → capture → assessment → task → approved follow-up; tenant switch clears old data |
| Operations | Production port exposure, secrets handling, dependency checks, backup restore and documented rollback/replay |

Use PostgreSQL 16, not SQLite, for RLS/security integration tests. Seed synthetic data for two tenants as described in the schema blueprint. Do not expose tenant CRUD endpoints before their RLS policies, non-owner grants and cross-tenant tests land together.

---

## 17. Implementation order and open decisions

Implement vertical slices in the product's priority order: **secure tenant isolation → CRM core → AI → automation**.

1. **Foundation:** finalize schema/security decisions; initialize a real Alembic environment, engine/session lifecycle, DB roles and synthetic two-tenant fixtures.
2. **Identity and isolation:** implement bootstrap resolvers, authentication/refresh/MFA, verified membership context, RLS and authorization tests before exposing tenant data.
3. **CRM slice:** lead CRUD/assignment/timeline/tasks, one capture service and an approved frontend scaffold; prove two-tenant behavior end to end.
4. **Integrations and durability:** signed webhook receipts, CSV jobs, outbox/worker, failure recovery and deduplication; complete WhatsApp test flow.
5. **Advisory AI:** structured adapter, evaluation/fallback/review and stale-job protection; capture remains usable without AI.
6. **Automation and release:** scoped internal auth, reviewed workflow exports, follow-up safety, dashboards and operational gates. Cut lower-priority features, not security controls.

| Open decision / mismatch | Required resolution |
| --- | --- |
| Bootstrap access under RLS | Approve pre-tenant lookup policies (preferred) or narrow resolver functions/roles for identity, forms, webhooks, workers and platform administration |
| Internal tenant scope/signature | Bind approved tenant scope to service identity and protect security-relevant headers; update API/security docs and negative tests |
| Worker claims and event fan-out | Define claim privileges, leases, per-consumer state, retry/dead-work limits and assessment job uniqueness |
| n8n scheduling | Choose bounded per-tenant dispatch without granting cross-tenant resource enumeration |
| Single-team membership vs multi-team language | Limit MVP managers to the modeled team or approve a separate multi-team membership design |
| Frontend/provider dependencies | Confirm package choices, LLM provider/model, auth libraries and attachment storage/scanning before implementation |
| Platform support access | No tenant-data support access until a temporary approved/audited grant flow exists; omission must mean denial, not bypass |
| Policy and operations | Confirm retention durations, rate limits/quotas, monitoring thresholds, backup/restore ownership and recovery objectives |

`SECURITY.md` still lists token storage and AI ownership as open, while the API/schema documents propose resolutions. This document aligns with those target contracts but does not substitute for security approval. Resolve these cross-document differences explicitly before implementing the affected flows.
