# AI Sales CRM: Build Guide for the Missing Pieces

Revised 15 Nov 2026 against the actual codebase at `e:\Sales assist\Sus`.
Every claim is grounded in a file you can open and verify.
Keep `API_CONTRACT.md`, `DATABASE_SCHEMA.md`, `SECURITY.md` and `ARCHITECTURE.md` open alongside the agent; it must follow them.

---

## 1. How the ranking works

Every step has a global number. Do them in number order, except where the Lanes note in section 4 says steps can run in parallel.

| Tier | Meaning |
| --- | --- |
| 🔴 Tier 1, Blocker | Nothing else works until this is done |
| 🟠 Tier 2, Core loop | The product's reason to exist: tasks, automation, follow-ups |
| 🟡 Tier 3, MVP-complete | Dashboards and screens people actually use |
| 🟢 Tier 4, Ship | Hardening, deployment, backups, end-to-end tests |

🔒 means the step touches auth, RBAC, tenant context, webhooks, or internal service auth. Its PR needs the ring reviewer **and** the security approver.

Size (one developer plus AI coder): **S** about half a day, **M** about a day, **L** about two days.

**If you fall behind, cut in this order:** #21, then extra dashboard widgets in #19, then everything in #25 beyond the 403 test. **Never cut:** #1 to #6, #9, #15, #22, and #23. #24, #26, and #27 may shrink in scope but are never skipped, because the SECURITY.md checklist needs a passing test for each of its items.

## 2. Part A: Things only you can do (before any coding)

## 2. What already exists (do not rebuild it)

> [!IMPORTANT]
> The dev branch merge brought the codebase far beyond "early scaffold". Read this section before giving the agent any instruction — building something twice wastes a full day.

| Already built | Evidence |
| --- | --- |
| Full auth: signup, login, logout, refresh rotation, MFA (TOTP), password reset, rate limiting | `backend/app/modules/auth/` — all files present and substantial |
| Tenant isolation: RLS policies, `crm_app` non-superuser role, per-transaction `set_config` | `core/tenancy.py`, RLS migrations |
| Lead CRUD with idempotency, cursor pagination, 7 filter params, duplicate detection | `leads/crud.py` (830 lines) |
| Lead capture pipeline: advisory lock, dedup by email/phone/external_id, merge, audit | `leads/capture.py` |
| Round-robin assignment with cursor and FOR UPDATE | `leads/assignment.py` |
| Lead opt-out enforcement | `leads/optout.py` |
| Lead status transitions | `leads/transitions.py` |
| CSV import | `leads/csv_import.py` |
| WhatsApp inbound (E.164, dedup, capture) | `integrations/whatsapp.py` |
| WhatsApp outbound: 24h window, opt-out, 6-step ordered pipeline, never holds DB lock over HTTP | `messaging/service.py` (512 lines) |
| Meta Lead Ads + Messenger inbound | `integrations/meta.py` (21KB) |
| Webhook signature verify before JSON parse + idempotent event storage | `integrations/webhooks.py` |
| Public lead forms | `lead_forms/` module, router mounted in `main.py` |
| Integration credential encryption (AES-256-GCM) | `integrations/crypto.py` |
| Conversations + messages + lead timeline | `conversations/service.py` (201 lines) |
| AI assessment: PII redact, Pydantic validate, business rules, persist with model/prompt version | `ai/service.py` |
| AI background job framework: outbox claim with FOR UPDATE SKIP LOCKED, tenant-per-event, LLM-outside-transaction pattern | `ai/jobs.py` — framework done, `default_analyzer` NOT wired |
| Outbox event system | `core/outbox.py`, `core/outbox_models.py` |
| Teams management | `teams/router.py`, `teams/service.py` |
| Invitations: invite, accept, deactivate, change role | `invitations/router.py` — **exists but NOT mounted in `main.py`** |
| Notifications module: service, crud, schemas, models | `notifications/` — router is INTERNAL HMAC route, NOT a user route |
| Internal service auth (HMAC canonical string, 300s timestamp tolerance) | `core/service_auth.py` |
| Audit logging | `audit/service.py` |
| Task model: full schema with approval, rejection, idempotency, version, check constraints | `tasks/models.py` — **no router yet** |
| Task creation from AI assessment | `tasks/service.py` — `create_assessment_follow_up()` only |
| Cross-tenant test suite: 61 test files | `tests/cross_tenant/` and `tests/unit/` |
| Frontend: login, signup, accept-invite, reset-password, leads list, lead detail, lead new | `frontend/src/app/` |

---

## 3. Part A: Things only you can do (before any coding)

The coding agent cannot create accounts, see your secrets, or touch your server. Finish this part first.

### A1. Verify your toolchain

```
docker --version
docker compose version
python --version    # must be 3.12
node --version      # LTS
git --version
```

Docker Desktop needs the WSL2 backend on (Windows). The compose file is at `infrastructure/docker-compose.yml`, not the project root.

### A2. Install packages yourself

**Backend** — `requirements.txt` is clean (no duplicates). Add only what is missing:

```bash
pip install pip-audit
```

Add `pip-audit` to `requirements.txt` as a dev dependency.

**Frontend** — current `package.json` has: Next.js 16.4.6, React 19.3.0, Tailwind 4.3.3. Install what is missing:

```bash
cd frontend
npm install recharts @tanstack/react-query
npm install -D @playwright/test otplib
npx playwright install chromium
npx shadcn@latest add table tabs badge dialog dropdown-menu
```

The `shadcn` command asks questions interactively — run it yourself. `respx` is already in the backend `requirements.txt`; do not add it again.

**Docker images:** find the newest stable `n8nio/n8n` tag and newest `caddy` 2.x tag that are at least two weeks old on Docker Hub. Write both down. The agent must pin those exact tags and never use `latest`.

**Server only (step #26):** install `age` (backup encryption) and `rclone` (upload to your bucket).

### A3. Generate secrets

Put them in `.env` (git-ignored, file is at `infrastructure/` or project root). Use the variable names already in `core/config.py`; the agent adds new names to `.env.example` with placeholder values only.

| Secret | How to generate |
| --- | --- |
| `SERVICE_HMAC_SECRET` (backend signs outbox → n8n calls) | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `N8N_EVENT_SIGNING_SECRET` (n8n verifies incoming events) — must differ from above | same command, run again |
| `INTEGRATION_ENCRYPTION_KEY` (Fernet, for credential storage) | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `N8N_ENCRYPTION_KEY` (**never change after first n8n start**) | `python -c "import secrets; print(secrets.token_hex(32))"` |
| DB passwords: `crm_app`, `crm_worker`, `crm_migrator`, `crm_backup`, n8n DB (5 different values) | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

Store every production secret in a password manager before closing the terminal.

### A4. Accounts and keys to collect

- **LLM API key** for the one provider you choose (decision 1 below).
- **Meta / WhatsApp** (optional for this guide, all tests use mocks): app secret, verify token, phone number ID, access token. Needed only for a live WhatsApp demo.
- **SMTP provider** for production email (verification, reset, invites). Mailpit is dev-only and already in `infrastructure/docker-compose.yml`.
- **VPS, domain, and DNS A record** for steps #22 and #23. Open only ports 22, 80, and 443.
- **S3-compatible bucket** with an access key for step #26.
- **GitHub:** branch protection on `main` and `develop` requiring two approvals; deploy secrets (SSH key, host); a named second security approver so Dev 1 is not a single point of failure.
- **WhatsApp message templates.** A follow-up sent more than 24 hours after the customer's last message must use a pre-approved template. Create one or two in Meta Business Manager now (e.g. `follow_up_default`) and submit them. Approval takes hours to days.
- **A public tunnel for webhook tests** (optional). Meta must reach an HTTPS URL. Point `cloudflared` or `ngrok` at `localhost:8000`, or test on staging.
- **Code owners.** The agent can write `.github/CODEOWNERS` naming the security approver for `auth/`, `core/tenancy.py`, `core/permissions.py`, `core/service_auth.py`, `integrations/webhooks.py`, and `alembic/versions/`. Enable "Require review from Code Owners" in branch protection.

### A5. Decisions to make now

1. **One LLM provider.** Recommended: Anthropic. `ai/llm_client.py` is already the primary (full retry, backoff, cost tracking, singleton via `lru_cache`). `ai/provider.py` has an OpenAI fallback. Pick one adapter and unify — step #3 wires it.
2. **Contract drift.** The code and `API_CONTRACT.md` differ on several paths (webhooks, password reset, send message). Keep working paths; update the contract to match them; follow the contract for every new endpoint going forward.
3. **Quiet hours default.** Suggested 21:00–09:00 in the tenant timezone (Asia/Dhaka), editable by admins.
4. **Follow-up scheduling.** The backend writes a `task.due` outbox event with `available_at = due_at` (step #8). Do not build an n8n schedule that lists all tenants — `ARCHITECTURE.md` forbids it.
5. **n8n license.** Email n8n and get written confirmation that your use fits the Sustainable Use License.
6. **Platform admin model.** A `users.is_platform_admin` flag (recommended, simplest) or a separate table.
7. **Where follow-up text comes from.** MVP rule: the task's `notes` field holds the approved message. Outside the 24-hour window the send is skipped and the rep is notified. Per-tenant default templates are post-MVP.
8. **Support-access grants.** Document as a known gap in `SECURITY.md`, not built in this guide.
9. **Dashboard definitions.** Conversion rate = share of leads created in the period that are currently `won`. Admin `scope=team` shows all teams unless a `team_id` is given. Confirm with the product owner.

### A6. Working with the AI coder

**Paste this at the start of every session:**

```
You are working in an existing multi-tenant FastAPI + PostgreSQL CRM.
1. Read the API_CONTRACT.md / DATABASE_SCHEMA.md / SECURITY.md sections I name. Match contract shapes exactly. If code and contract conflict, stop and ask.
2. Never trust tenant_id from the client. Use the existing tenancy dependency in core/tenancy.py. Every new tenant table needs RLS ENABLE + FORCE, a policy, composite FKs, and an entry in test_rls_coverage.
3. Never use a superuser or BYPASSRLS. Never skip or weaken a test. Never log secrets, tokens, or message text.
4. Write failing tests first (unit, API, cross-tenant, role-scope), then the code.
5. At most one Alembic migration per step. After it, alembic heads must show exactly one head.
6. Run ruff and pytest. Show me the output and the list of changed files. Do not touch unrelated files.
```

**Your review checklist after every step:**

- `ruff` and `pytest -q` are green, and `alembic heads` shows exactly one head.
- The new endpoint appears in `/docs` (FastAPI auto-docs).
- A cross-tenant test and a role-scope test exist for the new code.
- `git diff` contains no keys, tokens, or passwords.
- The PR is labeled 🔒 where required and has two approvals.

---

## 4. Master ranking table

| # | Step | Tier | 🔒 | Size | Needs |
| --- | --- | --- | --- | --- | --- |
| 1 | One Alembic head + CI check | 🔴 | | S | none |
| 2 | DB roles and RLS audit | 🔴 | 🔒 | M | A3 |
| 3 | Unify LLM adapter and wire AI worker | 🔴 | 🔒 | M | #2, LLM key |
| 4 | Mount invitations router; build users API; add CORS | 🔴 | 🔒 | M | #2 |
| 5 | Tasks CRUD router | 🟠 | 🔒 | M | #2 |
| 6 | Task approval and pause-on-reply | 🟠 | 🔒 | M | #5 |
| 7 | Frontend ↔ API connectivity (Next.js rewrites) | 🟠 | 🔒 | S | #4 |
| 8 | Outbox fan-out and n8n dispatcher | 🟠 | 🔒 | M | #3, #6 |
| 9 | Internal automation endpoints | 🟠 | 🔒 | L | #6, #8 |
| 10 | n8n service in Docker Compose | 🟠 | | M | A3, A2 |
| 11 | Workflow A: new lead | 🟠 | | M | #9, #10 |
| 12 | Workflow B: follow-up | 🟠 | | L | #9, #10, #11 |
| 13 | Workflow C: customer reply | 🟠 | | M | #9, #10 |
| 14 | Error workflow, retention, workflow exports | 🟠 | | S | #11–#13 |
| 15 | Dashboard API with scope tests | 🟡 | 🔒 | L | #5, #8 |
| 16 | Frontend foundations: nav, guards, query layer | 🟡 | | M | #7 |
| 17 | Tasks page and approval queue | 🟡 | | M | #5, #6, #16 |
| 18 | Conversations inbox and reply box | 🟡 | | L | #16 |
| 19 | Dashboard page (three roles) | 🟡 | | L | #15, #16 |
| 20 | Settings: users and teams | 🟡 | | M | #4, #16 |
| 21 | Integrations settings and notification bell | 🟡 | | M | #4, #16 |
| 22 | Reverse proxy with TLS (Caddy) | 🟢 | 🔒 | M | domain |
| 23 | Production Docker Compose | 🟢 | 🔒 | L | #10, #22 |
| 24 | Hardening gaps from SECURITY.md | 🟢 | 🔒 | M | none |
| 25 | Platform admin and audit-log API | 🟢 | 🔒 | M | #2 |
| 26 | Backup, restore, tenant export and delete | 🟢 | | M | bucket |
| 27 | Playwright end-to-end tests | 🟢 | | M | #17, #18 |
| 28 | Final checklist, docs refresh, demo | 🟢 | | M | all |

---

## 5. Phases and steps

**Lanes:** after step #7, three lanes can run simultaneously on different developers, or one after another if you work alone.
- **Lane 1 (automation):** #8 → #9 → #10 → #11 → #12 → #13 → #14
- **Lane 2 (dashboard API):** #15
- **Lane 3 (frontend screens):** #16 → #17 → #18 → #19 → #20 → #21

Merge into `develop` at least daily.

---

### Phase 0: Gates (steps 1–4)

These are not new features. Every absent feature depends on them being solid.

---

#### #1 — One Alembic head + CI check 🔴 S

**Context:** `needs.txt` (a dev scratchpad in the repo) shows a prior head conflict on `777c1482b0fb_add_outbox_events.py`. The dev merge added many merge migrations (`b381846ed83c`, `f31a9d8c2b47`, `f6a8c0d2e491`, etc.) that resolved those conflicts. Verify the chain is clean before writing any new migration.

**Tell the agent:**

```
1. Run `alembic heads` from backend/. If there is more than one head, create a single
   merge migration with `alembic merge heads -m "merge_all_heads"`.
2. Turn tests/unit/test_alembic_history.py (currently 337 bytes, likely a stub)
   into a real test: assert exactly one head AND that `upgrade head` succeeds
   on a clean empty database (use a temporary DB via pytest fixture).
3. Add a CI step (GitHub Actions) that runs `alembic heads` and fails if
   the count is not 1.
```

**Done when:** CI fails automatically if any developer introduces a second head.

---

#### #2 — DB roles and RLS audit 🔴 🔒 M

**Context:** `infrastructure/docker-compose.yml` currently uses a single `POSTGRES_USER` for everything. `core/tenancy.py` correctly sets `app.tenant_id` per transaction. The migrations create a `crm_app` role (confirmed in RLS migrations). The gap is that the compose and app wiring don't enforce role separation.

**Tell the agent:**

```
Using DATABASE_SCHEMA.md section 15:
1. The API connects as crm_app (non-superuser, no BYPASSRLS).
   The worker (step #3) connects as crm_worker.
   Migrations run as crm_migrator (table owner).
   Backups connect as crm_backup.
   None of these roles is a superuser or has BYPASSRLS.
2. Update infrastructure/docker-compose.yml to pass DATABASE_URL using
   the crm_app password from .env. Add WORKER_DATABASE_URL using crm_worker.
3. Extend tests/test_rls_coverage.py so every table with tenant_id MUST have
   RLS enabled AND forced, and so the connected role fails superuser and
   BYPASSRLS checks with explicit pg_has_role / rolbypassrls assertions.
4. Update .env.example with the five separate DB URLs (api, worker, migrator,
   backup, n8n) using placeholder values only.
```

**You:** add all five DB passwords generated in A3 to `.env`.

**Done when:** the RLS audit test passes. `DATABASE_URL` no longer points at a superuser role.

---

#### #3 — Unify LLM adapter and wire the AI worker 🔴 🔒 M

**Context:** two LLM providers co-exist right now:
- `ai/llm_client.py` — Anthropic API, full retry/backoff, singleton via `lru_cache`. Used nowhere currently.
- `ai/provider.py` — OpenAI Chat Completions (`analyze_with_openai`). Used by `conversations/service.py`.
- `ai/jobs.py` has a fully built outbox-claim framework but `default_analyzer` raises `NotImplementedError`.

The outbox job runner (`run_forever` / `run_once`) has no startup hook — it is never launched.

**Tell the agent:**

```
1. Create ai/adapter.py with one Protocol/ABC interface (analyze(job: JobInput) -> AnalysisResult).
   Add an AnthropicAdapter wrapping ai/llm_client.py and an OpenAIAdapter wrapping
   ai/provider.py. Select via LLM_PROVIDER env var ("anthropic" | "openai").
   Both adapters must handle provider errors and return status="failed"
   instead of raising (the jobs.py contract requires this).

2. Replace the NotImplementedError in ai/jobs.py default_analyzer with a call
   to get_adapter() from ai/adapter.py. Keep the existing flow exactly:
   load data → close DB session → redact PII → call adapter → validate with
   AssessmentOutput Pydantic model → persist via persist_assessment().

3. Update conversations/service.py to call the same adapter instead of
   importing analyze_with_openai directly. This removes the dual-provider split.

4. Add a worker service in infrastructure/docker-compose.yml that runs:
   python -m app.worker
   Create backend/app/worker.py that calls ai/jobs.run_forever(SessionLocal, analyzer=get_adapter()).
   The worker connects as crm_worker (WORKER_DATABASE_URL), not the API role.
   Do NOT start the job loop inside the API process (main.py).

5. Tests must use a fake adapter and never call the network.
   An adapter failure must produce a stored 'failed' assessment flagged for review.
   Test that the outbox event goes 'dead' after MAX_ATTEMPTS (5).
```

**You:** add the LLM key to `.env`, start the stack with `docker compose -f infrastructure/docker-compose.yml up`, create a lead, and within 30 seconds check that a `lead_assessments` row appears.

**Done when:** creating a lead produces an assessment row through the worker. All tests pass offline with the fake adapter.

---

#### #4 — Mount invitations router; build users API; add CORS 🔴 🔒 M

**Context — what already exists:**
- `invitations/router.py` is complete (invite, accept, deactivate membership, change role) but is **not imported or mounted in `app/main.py`**.
- `notifications/router.py` is an **internal HMAC route** at `/internal/v1/automation/notifications` using `require_internal_service`. It must NOT be mounted as a public user route. Mount it under the internal prefix alongside the automation router.
- `users/` module has only `models.py` — no router and no service. User profile management is missing.
- `main.py` has no CORS middleware, so the Next.js dev server (`localhost:3000`) cannot call the API.

**Tell the agent:**

```
1. Mount invitations/router.py in main.py under the existing /api/v1 prefix.
   It already imports correctly — just add the include_router call.

2. Mount notifications/router.py in main.py. It is an INTERNAL route.
   Its prefix is already /internal/v1/automation — confirm this and mount
   it alongside the automation router. DO NOT change it to a public route.

3. Build users/router.py and users/service.py:
   - GET /api/v1/users/me  → current user profile + roles (uses existing TenantContext)
   - PATCH /api/v1/users/me → update display_name, timezone only
   - GET /api/v1/users → list members of the caller's tenant (manager or admin only)
   Follow the apply_data_scope + require_roles pattern from core/permissions.py.
   Mount in main.py.

4. Add CORSMiddleware to main.py ONLY if Next.js rewrites (step #7) are
   not yet set up. If added: one explicit origin from CORS_ALLOWED_ORIGINS env,
   allow_credentials=True, never "*". The refresh cookie and X-CSRF-Token flow
   must keep working.

5. Tests: invitation is single-use and expires, only admins can invite,
   deactivating a user revokes their refresh tokens, role changes are audited.
   Add a cross-tenant test: an invitation token from tenant A cannot be accepted
   to join tenant B.
```

**Done when:** an admin can invite a rep, the rep accepts and logs in, a deactivated rep loses access immediately, and `/api/v1/users/me` works from the browser.

---

### Phase 1: Tasks API (steps 5–6)

---

#### #5 — Tasks CRUD router 🟠 🔒 M

**Context:** `tasks/models.py` is complete and production-quality. It has: `type` (call/meeting/reminder/follow_up), `status` (open/done/cancelled/paused), `requires_approval`, `approval_status`, `version` (optimistic locking), `idempotency_key`, composite FK constraints. `tasks/service.py` only has `create_assessment_follow_up()`. No router exists.

**Give the agent:** `API_CONTRACT.md` sections 10.1–10.3, `tasks/models.py`, and `tasks/service.py`.

**Tell the agent:**

```
Build tasks/router.py with these endpoints and mount it in main.py:
  GET  /api/v1/tasks              — list (rep: own, manager: team, admin: all)
  GET  /api/v1/tasks/due-follow-ups — declare BEFORE /tasks/{id} (router order matters)
  GET  /api/v1/tasks/{id}
  POST /api/v1/tasks              — requires Idempotency-Key header
  PATCH /api/v1/tasks/{id}        — uses version field, returns 409 on conflict

Reuse the idempotency module already in leads/crud.py (not a copy — import from there
or extract to a shared helper). Reuse apply_data_scope from core/permissions.py.

PATCH rules:
- Completing a task (status=done) sets completed_at = now(UTC).
- Cancelling stops reminders (write a 'task.cancelled' outbox event — step #8 will use it).
- Every change writes an audit log (audit/service.py) and a lead timeline entry
  (Interaction row with type='task_updated').

Test coverage required:
- Cross-tenant: tenant A cannot read or update tenant B's task.
- Role scope: rep only sees own tasks, manager only sees team tasks.
- Duplicate idempotency key: second POST returns 200 with the original response.
- Version conflict: two concurrent PATCHes, the second gets 409.
- Route order: GET /tasks/due-follow-ups must not be caught by /tasks/{id}.
```

---

#### #6 — Approval and pause-on-reply 🟠 🔒 M

**Context:** `tasks/models.py` already has `requires_approval`, `approval_status` (not_required/pending/approved/rejected), `approved_by_user_id`, `approved_at`, `rejected_by_user_id`, `rejected_at`, and DB check constraints enforcing consistency. The service layer for approval actions does not exist yet. `messaging/service.py` already enforces opt-out (`ensure_not_opted_out`) but there is no `pause_followups` function tied to inbound messages.

**Tell the agent:**

```
1. Add POST /api/v1/tasks/{id}/approve (API_CONTRACT.md section 10.5).
   - 409 invalid_approval_state unless requires_approval=true AND approval_status='pending'.
   - Approval never bypasses: consent check, opt-out check, quiet hours (step #9),
     or lead status ('won'/'lost' leads do not get new messages).
   - Manager can approve their team's tasks; admin can approve any; rep cannot approve.
   - Write audit log entry. Write a 'task.approved' outbox event.

2. Add POST /api/v1/tasks/{id}/reject with symmetric logic.

3. Add a pause_followups(session, lead_id, tenant_id, reason) function in tasks/service.py.
   It sets status='paused' on all open tasks for that lead and writes a lead timeline entry.
   Call it from two places:
     a. integrations/inbound.py (or whatsapp.py) when an inbound message is stored.
     b. leads/optout.py when a lead opts out.

4. Tests:
   - An inbound message pauses all open tasks for that lead.
   - An opt-out pauses all open tasks for that lead.
   - A paused lead cannot receive a new follow-up (messaging pipeline returns 409).
   - Rep cannot call /approve.
```

**Done when:** a test proves both inbound messages and opt-outs cancel pending follow-ups.

---

### Phase 2: Browser connectivity (step 7)

---

#### #7 — Frontend ↔ API connectivity 🟠 🔒 S

**Context:** `frontend/package.json` has Next.js 16.4.6. The API client at `frontend/src/lib/api.ts` (1.1KB) exists. The browser needs to call the backend without CORS issues. The preferred solution is a Next.js reverse-proxy rewrite — this avoids CORS entirely.

**Tell the agent:**

```
Preferred approach (try this first):
1. Add rewrites to next.config.ts (or next.config.js if .ts doesn't exist):
   {
     source: '/api/:path*',
     destination: 'http://localhost:8000/api/:path*'
   }
   Also add the webhooks path: '/webhooks/:path*' → 'http://localhost:8000/webhooks/:path*'
2. Update frontend/src/lib/api.ts to use relative URLs (/api/...) so the
   same code works in dev (proxied) and prod (Caddy routing).
3. The refresh cookie is HttpOnly and SameSite=strict — it flows through the
   proxy automatically. The X-CSRF-Token header must still be sent explicitly.

Only if rewrites fail: add CORSMiddleware to main.py per step #4 instruction.

Do NOT use '*' for allowed origins under any circumstances.
```

**You:** log in, reload the page, and confirm the session refreshes without a CORS error in the browser console.

---

### Phase 3: Automation with n8n (steps 8–14)

---

#### #8 — Outbox fan-out and n8n dispatcher 🟠 🔒 M

**Context:** `core/outbox.py` already has an outbox writer. `ai/jobs.py` claims `lead.created` and `message.received` events with `FOR UPDATE SKIP LOCKED`. The gap is that the outbox has no per-consumer separation — both the AI worker and n8n would compete for the same rows, causing missed events or double processing.

**Tell the agent:**

```
Read core/outbox.py first and report how consumers are separated today.
Then:

1. Rewrite the outbox writer (or add a new emit_for function) so each consumer
   gets its own row in the same transaction:
   - 'assessment.requested' → claimed by the AI worker (ai/jobs.py)
   - 'lead.created', 'lead.replied', 'task.due', 'task.cancelled' → claimed by n8n dispatcher
   Each row has its own idempotency key (uuid4) so one consumer cannot starve the other.

2. When a follow-up task is created (tasks/service.py create_assessment_follow_up
   or the new router's POST), write a 'task.due' outbox row with
   available_at = task.due_at. When a task is completed, cancelled, paused,
   or rescheduled, cancel or update the matching outbox row.

3. Build a dispatcher service (core/dispatcher.py or automation/dispatcher.py)
   that claims n8n-bound events and POSTs them to the n8n webhook URL:
   - Headers: X-Event-ID, X-Timestamp, X-Signature (HMAC-SHA256 of timestamp + "." + raw_body)
   - Payload: IDs only, never PII or message text.
   - Retry with exponential backoff; mark 'dead' after MAX_ATTEMPTS.
   - The dispatcher is a separate process (add to infrastructure/docker-compose.yml
     alongside the worker from step #3).

4. Tests:
   - Signature format: sha256=<hex> matches the canonical string.
   - Retry logic: failed delivery retries and eventually goes 'dead'.
   - Both consumers receive separate rows for the same lead.created event.
```

---

#### #9 — Internal automation endpoints 🟠 🔒 L

**Context:** `core/service_auth.py` is complete: HMAC canonical string is `v1 + service_id + tenant_id + METHOD + path + timestamp + idempotency_key + sha256(body)`, 300s timestamp tolerance, `InternalServiceContext` dataclass. `automation/router.py` has only the health endpoint. `notifications/router.py` already implements one internal endpoint (`POST /internal/v1/automation/notifications`).

**Give the agent:** `API_CONTRACT.md` section 14, `core/service_auth.py`, `notifications/router.py` (as a working example).

**Tell the agent:**

```
Implement the remaining endpoints in automation/router.py using the
require_internal_service dependency exactly as notifications/router.py does it.
All under /internal/v1/automation/:

  GET  /leads/{lead_id}            — lead context (name, status, assigned_user_id, team_id)
  POST /leads/{lead_id}/assess     — trigger assessment if missing or failed
  POST /messages                   — send a message (MUST reuse messaging/service.py pipeline:
                                     consent, opt-out, 24h window, quiet hours, approval_required)
  POST /tasks/{task_id}/result     — record send outcome (sent/failed/skipped/needs_approval)
  PATCH /tasks/{task_id}           — update due_at or status (reschedule from quiet-hours block)
  POST /notifications              — already exists in notifications/router.py, confirm mounted

Add a quiet_hours setting:
  - Per-tenant config row (or add columns to tenants table if no config table exists).
  - Default from A5 decision: 21:00–09:00 Asia/Dhaka.
  - is_quiet_hours(tenant_id, now) helper function.
  - If the send-message endpoint is called during quiet hours, do NOT send.
    Instead: set task.status='paused', write a 'task.due' outbox row with
    available_at = next quiet-hours end, return 202 with {"reason": "quiet_hours"}.

Every endpoint:
  - Validates that the specific resource ID belongs to X-Tenant-ID.
  - Has NO list-all route (by design — ARCHITECTURE.md section 14).
  - Is idempotent: same X-Idempotency-Key + same body = same response, 24h TTL.

Tests (all offline, no real n8n):
  - Bad HMAC signature → 401.
  - Timestamp outside 300s window → 401.
  - Replayed idempotency key with different body → 409.
  - Resource ID belonging to a different tenant → 404 (not 403, to avoid leaking existence).
  - Idempotent replay → original response body, no side effects.
```

---

#### #10 — n8n service in Docker Compose 🟠 M

**Context:** `infrastructure/docker-compose.yml` currently has: mailpit, db, backend. The `n8n/workflows/` directory has only `.gitkeep`. The backend env already has `N8N_SERVICE_SECRET` as a passthrough.

**Tell the agent:**

```
Edit infrastructure/docker-compose.yml:

1. Add two new named networks:
   crm_net: backend, worker, dispatcher, db (CRM database only)
   automation_net: backend, dispatcher, n8n, n8n_db

   n8n is NOT on crm_net and has no access to CRM DB credentials.
   The existing db service stays on crm_net only.

2. Add n8n_db service (postgres:16, pinned) with its own volume and credentials.
   On automation_net only.

3. Add n8n service (pinned tag you noted in A2):
   environment:
     N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY}
     DB_TYPE: postgresdb
     DB_POSTGRESDB_HOST: n8n_db
     DB_POSTGRESDB_DATABASE: n8n
     DB_POSTGRESDB_USER: ${N8N_DB_USER}
     DB_POSTGRESDB_PASSWORD: ${N8N_DB_PASSWORD}
     EXECUTIONS_DATA_PRUNE: "true"
     EXECUTIONS_DATA_MAX_AGE: "24"
     EXECUTIONS_DATA_SAVE_ON_SUCCESS: "none"
     NODE_FUNCTION_ALLOW_BUILTIN: "crypto"
     N8N_LISTEN_ADDRESS: "127.0.0.1"   # dev only
   On automation_net only.
   depends_on: n8n_db.

4. Add a 'dispatcher' service (the new dispatcher from step #8) on both networks.

5. Update .env.example with all new n8n variables.
```

**You:** `docker compose -f infrastructure/docker-compose.yml up`, open `http://127.0.0.1:5678`, create the n8n owner account, save the password, add the `SERVICE_HMAC_SECRET` as an n8n credential (HTTP Header Auth or custom). Verify n8n can call `GET /internal/v1/automation/health` and get 200.

**Done when:** n8n reaches the health endpoint and cannot reach the CRM database directly.

---

#### #11 — Workflow A: new lead 🟠 M

**Context:** n8n receives `lead.created` events from the dispatcher. The lead capture pipeline already assigns the lead and creates an initial assessment request via outbox. Workflow A must not duplicate that work.

**Tell the agent:**

```
Build a reusable sub-workflow "sign-and-call" first:
- Input: method, path, body (object), tenant_id, idempotency_key.
- Uses the crypto built-in to compute HMAC-SHA256 (N8N_EVENT_SIGNING_SECRET,
  timestamp + "." + rawBody).
- Calls the internal API, returns the response.

Workflow A triggers on the 'lead.created' webhook event:
1. Verify the incoming X-Signature (n8n Code node with crypto). Ignore if event_id already seen (use n8n static data or a dedupe node).
2. Fetch lead context via GET /internal/v1/automation/leads/{lead_id}.
3. Request assessment only if assessment is missing or status='failed'
   (POST /internal/v1/automation/leads/{lead_id}/assess).
4. Confirm the rep notification exists (POST /internal/v1/automation/notifications).
5. Record the result via POST /internal/v1/automation/tasks/{task_id}/result.

Workflow A must NEVER reassign the lead or create a second assessment — the backend
capture pipeline already did both.

Also write backend/scripts/simulate_n8n.py:
- Makes the same signed calls that n8n would make.
- Run against the dev stack to test without n8n running.
```

**You:** import the workflow JSON into n8n, run it with a seeded lead, and confirm the notification appears in the rep's notification list via the API.

---

#### #12 — Workflow B: follow-up 🟠 L

**Context:** Workflow B triggers on `task.due` outbox events dispatched by the dispatcher (step #8). The backend (`messaging/service.py`) already enforces: opt-out, 24h WhatsApp window, E.164 format. Step #9 adds quiet-hours enforcement. n8n only orchestrates — the backend makes all safety decisions.

**Tell the agent:**

```
Workflow B triggers on the 'task.due' webhook event:
1. Verify signature and deduplicate event_id.
2. POST /internal/v1/automation/messages with the task content.
3. The backend returns one of: 200 sent, 202 quiet_hours (auto-rescheduled),
   409 approval_required, 409 opted_out, 409 window_closed.
4. Record every outcome via POST /internal/v1/automation/tasks/{id}/result
   with a non-sensitive error_code (never log message text).
5. On approval_required: notify the rep/manager.
6. On failed: retry once after 10 minutes, then record 'failed' and notify.
```

**Done when:** a test with simulate_n8n.py proves that a lead who opted out or replied never receives the follow-up message.

---

#### #13 — Workflow C: customer reply 🟠 M

**Context:** `integrations/inbound.py` and `whatsapp.py` already store the inbound message and the `pause_followups` call (step #6) runs before the outbox event is emitted. That means: even if n8n is down, the follow-ups are already paused. Workflow C is best-effort enhancement.

**Tell the agent:**

```
Workflow C triggers on the 'lead.replied' webhook event:
1. Verify signature and deduplicate.
2. Notify the assigned rep: POST /internal/v1/automation/notifications.
3. Request a fresh assessment: POST /internal/v1/automation/leads/{id}/assess.
4. If the lead has no assigned user, create a task via PATCH /internal/v1/automation/tasks.

Workflow C must be idempotent for the same event_id.
```

---

#### #14 — Error workflow, retention, and exports 🟠 S

**Tell the agent:**

```
1. Create an n8n error workflow. It records a failure event (workflow_id, node_name,
   error class name) via POST /internal/v1/automation/tasks/{id}/result with
   status='failed'. It must NOT log payload content.
2. Document in ARCHITECTURE.md how outbox events retry (backoff, MAX_ATTEMPTS=5)
   and when they go 'dead' (after 5 attempts; a dead event is never auto-retried —
   a developer must manually requeue it).
3. Confirm the dispatcher marks dead events correctly (from step #8).
```

**You:** export all workflows with `n8n export:workflow --all --separate --output=n8n/workflows/`. **Never export credentials.** Run `git grep -E "(secret|token|password|key)" n8n/workflows/` before committing — if anything matches, strip it.

**Done when:** the full flow works end-to-end: WhatsApp lead → assessed → assigned → reminder dispatched → customer replies → follow-ups paused.

---

### Phase 4: Dashboard API (step 15)

---

#### #15 — Dashboard summary API 🟡 🔒 L

**Context:** `dashboard/__init__.py` is empty. No router, no service, no queries exist. This is the most work in a single step because it touches every table.

**Give the agent:** `API_CONTRACT.md` section 11 and `SECURITY.md` section 5.

**Tell the agent:**

```
Build dashboard/service.py, dashboard/router.py, and mount it.

Endpoint: GET /api/v1/dashboard/summary?scope=me|team|company&from=&to=
  - 'me': any role; 'team': manager or admin; 'company': admin only.
  - Any other combination: 403 immediately (do not compute then filter).
  - Default range: 30 days. Maximum: 366 days. Reject ranges > 366 with 422.
  - Group by day in the tenant timezone (store as a tenant config column or
    derive from tenants.settings JSONB if that column exists).

Filter order: RLS (implicit from tenant context) THEN role scope (explicit SQL WHERE).
Never compute cross-role data and filter it in Python — the query must only touch
the rows the caller may see.

Build in this order (ship incrementally, not as one giant PR):
  1. Rep KPIs: leads by status, tasks due today, overdue tasks.
  2. Team KPIs: same but team-scoped (manager and admin).
  3. Company KPIs: conversion rate (won / total created in period), lead sources breakdown.
  4. Automation health: count outbox_events by status (pending/processing/dead)
     — this tells us if n8n is falling behind without giving n8n DB access.

Add the indexes from DATABASE_SCHEMA.md and run EXPLAIN ANALYZE on seeded data.

Tests:
  - Rep requesting scope=company → 403.
  - Manager requesting scope=company → 403.
  - Manager sees only their team's data.
  - Dates spanning two tenants never cross (cross-tenant test).
  - Range > 366 days → 422.
```

---

### Phase 5: Frontend screens (steps 16–21)

**For every screen:**
- Use the existing API client (`src/lib/api.ts`) with token refresh.
- Keep tokens in memory, **never `localStorage`** (the refresh cookie is HttpOnly).
- Render all customer-supplied text as plain text, never `dangerouslySetInnerHTML`.
- Handle `401` (redirect to login), `403` (show "access denied"), and empty states.
- Role-aware UI is a convenience — the server enforces authorization.

---

#### #16 — Frontend foundations 🟡 M

**Tell the agent:**

```
1. Add TanStack Query provider (QueryClientProvider) to frontend/src/app/layout.tsx.
2. Build a useCurrentUser hook that calls GET /api/v1/users/me (built in step #4)
   and caches the result. Expose the user's roles to all pages.
3. Build role-aware navigation: sidebar links appear only if the role permits them.
4. Build a route guard HOC or middleware: unauthenticated → /login,
   wrong role → /403. Guards call /api/v1/users/me; the server stays the real check.
5. Build shared components: DataTable, EmptyState, ErrorBanner, LoadingSpinner.
   These are reused by every following page.
```

---

#### #17 — Tasks page and approval queue 🟡 M

**Context:** `tasks/models.py` has four statuses (open/done/cancelled/paused) and two approval states. The UI needs tabs.

```
Tabs: Today (due_at = today), Overdue (due_at < today, status=open),
      Upcoming (due_at > today), Approval Queue (approval_status=pending).

Actions:
  - Mark done → PATCH /api/v1/tasks/{id} { status: "done", version }
  - Approve (manager/admin only) → POST /api/v1/tasks/{id}/approve
  - Reject → POST /api/v1/tasks/{id}/reject
  - Show 409 version conflict inline, re-fetch and let user retry.
```

---

#### #18 — Conversations inbox and reply box 🟡 L

```
Left panel: conversation list ordered by last_message_at desc.
Right panel: message thread (chronological) + reply box.

Reply box:
  - Calls POST /api/v1/conversations/{id}/messages.
  - Show the 24-hour window state (last_inbound_at field on conversation).
    If window is closed: disable free-text, show "Template required" message,
    provide a template selector (hardcode the two WhatsApp templates from A4).
  - If lead.opted_out: disable entirely, show "Opted out" badge.
  - Link each conversation header to the lead detail page.
```

---

#### #19 — Dashboard page (three roles) 🟡 L

```
Build three views driven by the scope param, using Recharts:
  1. Rep view (scope=me): open leads, tasks due today, overdue tasks, win rate.
  2. Manager view (scope=team): same metrics for the team, plus rep-by-rep breakdown.
  3. Admin view (scope=company): company-wide metrics, source breakdown, automation health.

Role detection from useCurrentUser. If 403 is returned, show a clear "Access denied" card.
Build the rep view first. Ship the manager and admin views in the same PR only if time allows.
```

---

#### #20 — Settings: users and teams 🟡 M

```
Admin only. Two tabs:
  Users: list members, invite (POST /api/v1/invitations), change role
         (PATCH /api/v1/memberships/{id}/role), deactivate.
  Teams: list (GET /api/v1/teams), create (POST /api/v1/teams).

Show current role badge. After deactivating: optimistic removal from list.
```

---

#### #21 — Integrations settings and notification bell 🟡 M

> This is the first step to cut if you are running late.

```
Integrations:
  - List connected integrations (GET /api/v1/integrations).
  - Connect form: write-only credentials (never display back to user, field type=password).
  - Disconnect button (DELETE /api/v1/integrations/{id}).
  - Show a "Copy embed code" for the public lead form URL.

Notification bell:
  - Unread count badge (poll GET /api/v1/notifications?read=false every 60s, or
    WebSocket if already built).
  - Dropdown list of recent notifications with mark-as-read.
```

---

### Phase 6: Harden and ship (steps 22–28)

---

#### #22 — Reverse proxy with TLS (Caddy) 🟢 🔒 M

**Context:** `infrastructure/reverse-proxy/` exists but contains only `.gitkeep`.

**Tell the agent:**

```
Write infrastructure/reverse-proxy/Caddyfile:
  - {domain} → route:
      /api/* and /webhooks/* → backend:8000
      /* → frontend:3000
  - Return 404 for /internal/* (never expose internal routes to the internet).
  - Do NOT route the n8n editor (it stays on the private network).
  - Headers: Strict-Transport-Security max-age=63072000; includeSubDomains; preload
             X-Content-Type-Options: nosniff
             Referrer-Policy: strict-origin-when-cross-origin
             Content-Security-Policy: (allow own origin, block inline scripts)
  - Request body limit from API_CONTRACT.md section 2.9.

Write infrastructure/reverse-proxy/README.md with the deploy steps.
```

**You:** point the domain's DNS A record at the server IP. Wait for propagation before running `docker compose -f infrastructure/docker-compose.prod.yml up`.

---

#### #23 — Production Docker Compose 🟢 🔒 L

**Context:** `infrastructure/docker-compose.yml` is dev-only (source-mounted, single DB user, no frontend container, no Caddy, no worker).

**Tell the agent:**

```
Create infrastructure/docker-compose.prod.yml:

Services:
  frontend   — built image (not source-mounted), port not published
  backend    — built image, non-root user, no source mount, env from .env
  worker     — same image as backend, runs app/worker.py, connects as crm_worker
  dispatcher — same image as backend, runs app/dispatcher.py
  db         — postgres:16 (pinned), crm_net only, NO published ports
  n8n        — pinned tag, automation_net only, NO published ports
  n8n_db     — postgres:16 (pinned), automation_net only, NO published ports
  migrate    — one-shot job: alembic upgrade head as crm_migrator; must succeed before
               backend starts (use depends_on with condition: service_completed_successfully)
  caddy      — pinned 2.x tag, publishes ONLY ports 80 and 443

Healthchecks:
  db: pg_isready
  backend: GET /health (add /health/ready that also pings the DB connection pool)
  n8n: GET http://localhost:5678/healthz

Restart policies: unless-stopped on backend, worker, dispatcher, n8n, caddy.

Secrets: from env_file (never baked into the image or the compose file).

Networks:
  crm_net: backend, worker, dispatcher, db
  automation_net: backend, dispatcher, n8n, n8n_db
```

**You:** provision VPS, install Docker, configure firewall (allow 22, 80, 443 only), copy `.env` to server, then:
```bash
docker compose -f infrastructure/docker-compose.prod.yml up -d
```

---

#### #24 — Hardening gaps from SECURITY.md 🟢 🔒 M

**Tell the agent:**

```
1. Public form rate limiting: per-IP (10/min) and per-form-ID (100/hour) using
   the same PostgreSQL-backed approach as auth/rate_limit.py.
   Add a honeypot field (hidden input that must be empty; bots fill it → 422).

2. CSV import hardening (leads/csv_import.py):
   - Reject files over 10 MB.
   - Verify Content-Type is text/csv.
   - Neutralize formula injection: cells starting with =, +, -, @ get a leading
     single quote or are rejected with a row-level error (not a full import failure).

3. Email verification enforcement: check that an unverified email cannot log in.
   If not already enforced, add the check in auth/service.py login flow.

4. Add to CI (GitHub Actions):
   - pip-audit --require-hashes (after freezing requirements).
   - npm audit --omit=dev --audit-level=high.
   - A test that scans all log output from the test run for patterns matching
     tokens, passwords, and message text (regex: Bearer .{20,}, password=, body=).
```

---

#### #25 — Minimal platform admin API 🟢 🔒 M

**Tell the agent:**

```
Build platform/router.py:
  GET  /api/v1/platform/tenants          — list all tenants (name, status, created_at)
  GET  /api/v1/platform/tenants/{id}     — tenant detail + member count
  POST /api/v1/platform/tenants/{id}/suspend — set status='suspended'
  GET  /api/v1/platform/health           — system health (DB connections, outbox dead count)

All routes: require platform_admin role AND active MFA session (check mfa_verified_at
on the JWT claim or session). Use require_platform_admin from core/permissions.py.

Required test: a company admin gets 403 on every /platform route.
Document support-access grants as a known gap in SECURITY.md.
```

---

#### #26 — Backup, restore, export, and delete 🟢 M

**Context:** `backup_job/` directory exists but is empty.

**Tell the agent:**

```
Fill backup_job/:
  backup.sh:
    - Connect as crm_backup to run pg_dump --no-password --format=custom.
    - Encrypt the dump with: age --recipient <public-key> --output dump.age dump.pgdump
    - Upload with: rclone copy dump.age remote:bucket/crm/YYYY-MM-DD/
    - Delete local files after upload.
    - Log only success/failure, never connection strings.

  restore.sh <backup-file>:
    - Download from bucket, decrypt, restore into a scratch DB.
    - Assert row counts: tenants > 0, leads > 0.
    - Print a summary; do not restore into production automatically.

  export_tenant.py <tenant_id>:
    - Export all rows for one tenant as JSON (leads, conversations, tasks, assessments).
    - Write an audit log entry: 'tenant.exported', actor=platform_admin.

  delete_tenant.py <tenant_id>:
    - Confirm twice on the CLI.
    - Delete all rows for the tenant (relies on CASCADE on FK constraints).
    - Write an audit log entry before deleting.
    - Run as crm_migrator (has DELETE permission); never run as crm_app.
```

**You:** create the S3 bucket, generate the `age` key pair (`age-keygen`), keep the private key offline in your password manager, set a cron job on the server (`0 2 * * * /app/backup_job/backup.sh`), and run one full restore manually to prove it works.

---

#### #27 — Playwright end-to-end tests 🟢 M

**Tell the agent:**

```
Write two Playwright test files in frontend/tests/:

1. happy_path.spec.ts:
   - Log in as a seeded rep (seed in conftest or a test fixture script).
   - Create a lead via the UI form.
   - Confirm the lead appears in the list with correct name and status 'new'.
   - Open the lead detail. Confirm a task was created (AI assessment follow-up).
   - Complete the task. Confirm status changes to 'done'.

2. role_check.spec.ts:
   - Log in as a rep. Navigate to /dashboard?scope=company.
   - Confirm a 403 or "Access denied" message appears (not a blank page or crash).

For the admin MFA step (platform admin login): use a seeded test TOTP secret
stored in the test fixture. NEVER use a bypass or disable MFA in production code.
The TOTP library in devDependencies is otplib.
```

**You:** run `npx playwright test --headed` locally and watch both tests pass in a visible browser window.

---

#### #28 — Final checklist, docs refresh, and demo prep 🟢 M

**Tell the agent:**

```
1. Map every item in SECURITY.md section 16 (production checklist) to a named
   passing test. Present as a table: checklist item | test file | test name.
   Any item without a test: add the test or mark it explicitly as 'known gap'.

2. Update ARCHITECTURE.md:
   - Remove the line saying "current baseline: only /health exists".
   - Replace with the actual current state: list of all mounted routers,
     the two-network Docker setup, the worker/dispatcher services.

3. Update API_CONTRACT.md:
   - Align webhook paths, password-reset paths, and send-message path with
     what the code actually implements (from step A5 decision 2).

4. Update DATABASE_SCHEMA.md:
   - Replace any mention of crm_owner with crm_migrator (the actual role name).

5. Seed two demo companies with realistic but fictional data.
   Write a demo script covering this exact flow (time it to under 10 minutes):
     → Sign up company "Acme Sales" (admin + 1 manager + 2 reps)
     → Invite the manager and reps, have them accept
     → Submit a WhatsApp lead via simulate_n8n.py
     → Watch the AI assessment appear on the lead detail page
     → n8n sends the follow-up task; rep sees it on the Tasks page
     → Customer replies; follow-ups pause automatically
     → Manager opens dashboard and sees the team KPIs
     → Admin views the company dashboard conversion rate
```

---

## Appendix A — What the existing code does that you must not change

The following behaviours are correct and tested. The agent must preserve them exactly:

| Behaviour | File | Why it matters |
| --- | --- | --- |
| Signature verification runs before JSON parsing on webhook routes | `integrations/webhooks.py` | Prevents DoS via malformed bodies |
| DB session is closed before the LLM is called | `ai/jobs.py` pattern | Never holds a row lock over a network call |
| Refresh tokens use family chains + reuse detection | `auth/sessions.py` | Revokes the entire family on token theft |
| Outbound message pipeline commits before calling Meta API | `messaging/service.py` | Prevents duplicate sends on retry |
| `apply_data_scope` filters at the SQL query level | `core/permissions.py` | Never fetches data and filters in Python |
| `set_config('app.tenant_id', ..., true)` is re-run after every commit | `core/tenancy.py` SQLAlchemy event | Transaction-local; safe with connection pooling |
| Webhook integration resolved via SECURITY DEFINER function | `integrations/webhooks.py` | `crm_app` does not need direct table access |

---

## Appendix B — Files that do not exist yet

You can give these paths directly to the agent as targets to create:

```
backend/app/modules/users/router.py        (step #4)
backend/app/modules/users/service.py       (step #4)
backend/app/modules/tasks/router.py        (step #5)
backend/app/ai/adapter.py                  (step #3)
backend/app/worker.py                      (step #3)
backend/app/dispatcher.py                  (step #8)
backend/app/core/dispatcher.py             (step #8, alternate location)
backend/app/modules/dashboard/service.py   (step #15)
backend/app/modules/dashboard/router.py    (step #15)
frontend/src/app/tasks/page.tsx            (step #17)
frontend/src/app/conversations/page.tsx    (step #18)
frontend/src/app/dashboard/page.tsx        (step #19)
frontend/src/app/settings/page.tsx         (step #20)
frontend/src/app/integrations/page.tsx     (step #21)
frontend/src/app/notifications/page.tsx    (step #21)
infrastructure/reverse-proxy/Caddyfile     (step #22)
infrastructure/docker-compose.prod.yml     (step #23)
backup_job/backup.sh                       (step #26)
backup_job/restore.sh                      (step #26)
backup_job/export_tenant.py                (step #26)
backup_job/delete_tenant.py                (step #26)
frontend/tests/happy_path.spec.ts          (step #27)
frontend/tests/role_check.spec.ts          (step #27)
scripts/simulate_n8n.py                    (step #11)
```

---

## Appendix C — Routers currently mounted in main.py

(Confirmed from `backend/app/main.py`)

| Router | Prefix | Status |
| --- | --- | --- |
| auth_router | /api/v1/auth | ✅ mounted |
| password_reset_router | /api/v1/auth | ✅ mounted |
| assessments_router | (ai module) | ✅ mounted |
| conversations_router | /api/v1/conversations | ✅ mounted |
| lead_forms_router | /api/v1/public/forms | ✅ mounted |
| leads_router | /api/v1/leads | ✅ mounted |
| messaging_router | /api/v1/conversations | ✅ mounted |
| teams_router | /api/v1/teams | ✅ mounted |
| webhook_router | /webhooks | ✅ mounted |
| integrations_router | /api/v1/integrations | ✅ mounted |
| invitations_router | /api/v1 | ❌ NOT mounted — fix in step #4 |
| notifications_router | /internal/v1/automation | ❌ NOT mounted — fix in step #4 |
| users_router | /api/v1/users | ❌ does not exist — build in step #4 |
| tasks_router | /api/v1/tasks | ❌ does not exist — build in step #5 |
| dashboard_router | /api/v1/dashboard | ❌ does not exist — build in step #15 |
| automation_router | /internal/v1/automation | ✅ mounted (health only — extend in step #9) |
