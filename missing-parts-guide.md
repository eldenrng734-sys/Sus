Revision of 17 Nov 2026 · audited against the live repository state on tsnm-hm after the origin/dev merge
memory.md was created to 
important to know -the lead demo data is at sysyntrix_crm_final_export

Keep `API_CONTRACT.md`, `DATABASE_SCHEMA.md`, `SECURITY.md` and `ARCHITECTURE.md` open next to the coding agent at all times. If this guide and those files disagree, the agent stops and asks. If you agree the code is right, update the contract in the same PR.

---

## 1. What changed in this revision

| # | Problem in the previous revision | Fix now |
| --- | --- | --- |
| 1 | Step #4 said notifications and users routers were not mounted; they now are | Appendix C and #4 updated to current truth |
| 2 | Step #5 said tasks/router.py did not exist; it now exists and is mounted | #5 rewritten: audit and complete what is there, do not rebuild |
| 3 | Step #6 said there was no approve/reject; both endpoints exist in tasks/router.py | #6 rewritten: audit the approval logic, add pause_followups and cancel_followups |
| 4 | Appendix B listed users/router.py and tasks/router.py as files to create; both exist | Appendix B updated |
| 5 | .env.example had a real JWT_SECRET_KEY value and WHATSAPP_ACCESS_TOKEN=hey | A3 and Step 0 require fixing to placeholders before distributing |
| 6 | .env.example uses N8N_SERVICE_SECRET; the guide says rename to SERVICE_HMAC_SECRET | A3 and #10 carry the rename instruction |
| 7 | requirements-dev.txt did not exist; pip-audit and respx were in requirements.txt | A2 instructs creating requirements-dev.txt and moving dev-only tools |
| 8 | automation/router.py has /health but is not mounted | #9 mounts the automation router in main.py |
| 9 | tasks/events.py and GET /due-follow-ups were missing from the router | #5 adds both |

**Two deliberate deviations from master §13** (update the master text to match). Workflow A does not run an LLM assessment or reassign a lead: capture already assigns and requests the initial assessment, while n8n conditionally asks the backend to assess only if the assessment is missing or failed, then ensures the rep is notified. Workflow B is triggered by backend-scheduled `task.due` events instead of an n8n schedule that polls every tenant.

---

## 2. Where we stand (audited 17 Nov 2026 — live repo)

| # | Step | Status | What is left |
| --- | --- | --- | --- |
| 1 | One Alembic head + CI check | 🟡 | Two heads: staged merge `9a7c3e1f6b42` joins outbox and notifications, `e5c9a1d7b3f2` remains separate. Test does not run `upgrade head`; CI has no heads check |
| 2 | DB roles and RLS audit | 🟡 | `crm_worker` exists. Compose still uses one superuser URL; no role assertions; one URL in `.env.example` |
| 3 | LLM adapter and AI worker | 🟡 | `default_analyzer` calls OpenAI directly. Missing: `ai/adapter.py`, `app/worker.py`, worker service in compose |
| 3b | AI evaluation set and accuracy report | 🟡 | Fixture, runner and unit tests exist. Missing: confusion-matrix/review-threshold reporting and `docs/AI_EVAL.md` |
| 4 | Notifications mount and users API | 🟡 | Both routers exist and are mounted. Missing: `GET /users` scope rules, tenant-timezone field in `/me`, single-use invitation tests |
| 5 | Tasks CRUD router | 🟡 | Router exists with list/create/get/patch/approve/reject/approval-queue. Missing: `GET /due-follow-ups`, `tasks/events.py`, idempotency key, version optimistic lock, `apply_data_scope`, timeline entry on update |
| 6 | Approval, pause-on-reply, opt-out cancel | 🟡 | Approve and reject endpoints exist. Missing: `pause_followups`, `cancel_followups`, wiring into inbound and opt-out paths |
| 7 | Frontend ↔ API connectivity | 🔴 | Empty `next.config.ts`; two API clients remain; `lib/api.ts` stores token in browser storage |
| 8 | Outbox fan-out and dispatcher | 🔴 | Single consumer, no `task.due`, no dispatcher |
| 9 | Internal automation endpoints, quiet hours | 🟡 | `/health` exists in `automation/router.py` but router is not mounted. Missing: remaining endpoints, `tenant_settings`, quiet-hours logic |
| 10–14 | n8n compose, workflows A/B/C, error flow | 🔴 | Nothing; `n8n/workflows/` directory holds `.gitkeep` |
| 15 | Dashboard API | 🔴 | Empty module |
| 16–21 | Frontend foundations and screens | 🟡 | Tasks, conversations, settings and integrations are mock shells; leads partly wired; `/` is a static placeholder |
| 22–23 | Caddy and production compose | 🔴 | `.gitkeep` only |
| 24 | Hardening | 🟡 | Auth rate limit and MFA exist; no CI audits |
| 25 | Platform admin API | 🔴 | `require_platform_admin` only |
| 26 | Backup, restore, export, delete | 🔴 | No `backup_job/` |
| 27 | Playwright | 🔴 | No `frontend/tests/` |
| 28 | Checklist, docs, demo | 🟡 | Setup and user guides exist; checklist and demo prep remain |
| 17b | Lead detail AI card, CSV upload UI, bulk assign | 🟡 | Basic AI card exists; CSV UI, timeline integration and bulk assign remain |

**Already built, do not rebuild:** auth (signup, login, logout, refresh rotation with reuse detection, TOTP MFA, password reset, rate limit); tenancy (RLS, `crm_app`, per-transaction `set_config`); leads (CRUD with idempotency and cursor pagination, capture pipeline with dedup and merge, round-robin, opt-out, transitions, CSV import); channels (WhatsApp inbound and outbound pipeline, Meta Lead Ads and Messenger, signed idempotent webhooks, public lead forms); credential encryption; conversations, messages and timeline; AI assessment (PII redaction, Pydantic validation, rules, model and prompt version) and the outbox job framework in `app/modules/ai/jobs.py`; `core/outbox.py`; teams; invitations (mounted and tested); notifications service (HMAC handler mounted); tasks router (list, create, get, patch, approve, reject, approval-queue — all mounted); users router (`/me`, `PATCH /me`, `GET /` — all mounted); internal HMAC auth; audit logging; 59 backend Python test files; frontend login, signup, accept-invite, reset-password and partly wired leads pages. A separate 50-record evaluation fixture, runner and tests also exist.

---

## 3. Ground rules (from the master guide)

- **🔒 PRs** (auth, RBAC, tenant context or RLS, webhooks, internal service auth, policy migrations): the ring reviewer **plus** the security approver (Dev 1; Dev 4 if Dev 1 wrote it). No exceptions.
- **Contract first, docs in the same PR.** Change `API_CONTRACT.md` in the PR that changes the endpoint. Do not batch contract fixes into #28.
- **Git:** `feature/<dev>-<step>-<name>` → `develop` → `main`; conventional commits; at most one Alembic migration per step, announced in chat first; merge at least daily.
- **Definition of done, every step:** merged into `develop`; unit and API tests plus a cross-tenant test and a role-scope test; no query without tenant context; reviews above; endpoint visible in `/docs`; contract and docs updated; demoed in the day's session.
- **Never cut:** #1–#7, #9, #15, #22, #23 and the cross-tenant tests in every step. #24, #26, #27 and #28 may shrink but are never skipped.
- **Cut order if late:** #21 bell → #17b bulk assign and CSV UI → cut-first widgets in #15 → #25 beyond the 403 test → master list.
- **Security beats schedule:** never weaken a security step to save time; cut features instead.
- **Effort:** S ≈ 0.5 day, M ≈ 1 day, L ≈ 2 days. Critical path: #5 → #6 → #8 → #9 → #12.

---

## 4. Part A: things only you can do (before coding)

The coding agent cannot create accounts, see your secrets or touch your server.

### A1. Toolchain

Verify: `docker --version`, `docker compose version`, Python 3.12, Node LTS, `git --version`. Docker Desktop needs the WSL2 backend on Windows. The compose file is `infrastructure/docker-compose.yml`. The backend venv is `backend\backstore\`; activate it with:

```powershell
backend\backstore\Scripts\Activate.ps1
```

If the execution policy blocks activation, run first:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

### A2. Packages and pinned images

**Backend:** `pytest`, `httpx` and `ruff` are in `requirements.txt`. Move `pytest`, `httpx`, `ruff` and `respx` to `backend/requirements-dev.txt` and add `pip-audit` there. The runtime image must not carry test tools. Activate the venv and install:

```
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt
```

**Frontend:** `@tanstack/react-query`, `recharts`, `zod`, `@playwright/test`, `otplib`, and the badge, button, card, dialog, dropdown, skeleton, table and tabs shadcn components are already present. Do not reinstall or regenerate existing components. Install Chromium for Playwright only when running #27:

```
cd frontend
npx playwright install chromium
```

**Docker images:** find the newest stable `n8nio/n8n`, `caddy` 2.x and `postgres` 16.x patch tags that are at least two weeks old. Write them down; the agent pins exactly those and never uses `latest`.

**Server only (#26):** install `age` and `rclone`.

### A3. Secrets

Keep one git-ignored repository-root `.env`. The current `.env.example` has a real `JWT_SECRET_KEY` value and `WHATSAPP_ACCESS_TOKEN=hey`; replace those with explicit placeholders before distributing the template. Keep every production secret in a password manager.

The current `.env.example` uses `N8N_SERVICE_SECRET`; rename it to `SERVICE_HMAC_SECRET` everywhere (compose file, `.env`, `.env.example`). Generate secrets with these commands — run each line separately and store the output:

```
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SERVICE_HMAC_SECRET (n8n → backend)
python -c "import secrets; print(secrets.token_urlsafe(48))"   # N8N_EVENT_SIGNING_SECRET (backend dispatcher → n8n)
python -c "import secrets; print(secrets.token_hex(32))"       # N8N_ENCRYPTION_KEY (n8n credential store; never change after first start)
python -c "import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"  # INTEGRATION_ENCRYPTION_KEY (AES-256-GCM; check how integrations/crypto.py parses it)
python -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT_SECRET_KEY (replace the real value in .env.example with a placeholder)
python -c "import secrets; print(secrets.token_urlsafe(32))"   # run five times for crm_app, crm_worker, crm_migrator, crm_backup and n8n DB passwords
```

| Variable | Direction / purpose |
| --- | --- |
| `SERVICE_HMAC_SECRET` | **n8n → backend.** n8n signs every internal call; `core/service_auth.py` verifies |
| `N8N_EVENT_SIGNING_SECRET` | **backend dispatcher → n8n.** Must differ from `SERVICE_HMAC_SECRET` |
| `INTEGRATION_ENCRYPTION_KEY` | Encrypts stored integration credentials. `integrations/crypto.py` is AES-256-GCM; generate the key as base64 of 32 raw bytes (see command above) |
| `N8N_ENCRYPTION_KEY` | n8n credential store. Never change after the first n8n start |
| `JWT_SECRET_KEY` | Existing; replace the sample value in `.env.example` with `<your-jwt-secret>` |
| `DATABASE_URL` | crm_app connection (added in #2) |
| `WORKER_DATABASE_URL` | crm_worker connection (added in #2) |
| `MIGRATOR_DATABASE_URL` | crm_migrator connection (added in #2) |
| `BACKUP_DATABASE_URL` | crm_backup connection (added in #2) |
| Five DB passwords | `crm_app`, `crm_worker`, `crm_migrator`, `crm_backup`, n8n DB |

### A4. Accounts and keys

- **LLM API key** for the one provider you choose (A5.1). Variable: `OPENrouter_API_KEY` .
- **Meta and WhatsApp** (live demo only; all tests use mocks): `META_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`. Create and submit one or two WhatsApp message templates now (for example `follow_up_default`); approval takes hours to days.
- **SMTP provider** for production email. Mailpit stays dev-only.
- **VPS, domain and DNS A record** for #22 and #23. Open only ports 22, 80 and 443.
- **S3-compatible bucket** and access key for #26. Variables: `BACKUP_S3_REMOTE` and `BACKUP_S3_PATH`.
- **GitHub:** branch protection on `main` and `develop` requiring two approvals; deploy secrets; a named second security approver. Have the agent write `.github/CODEOWNERS` for `auth/`, `core/tenancy.py`, `core/permissions.py`, `core/service_auth.py`, `integrations/webhooks.py` and `alembic/versions/`, then enable 'Require review from Code Owners'.
- **Public tunnel** (optional, for Meta webhook tests): `cloudflared` or `ngrok` to `localhost:3000`, or test on staging.
FIX THIS THINGS I DID SOME THINGS Also, Compose doesn’t pass these integration values into the backend container. Template submission/approval still needs to happen in Meta.
SMTP — dev-only currently. The app defaults to Mailpit; there’s no production SMTP configuration in the root .env. The current email sender uses plain SMTP without provider authentication or TLS support.
VPS/domain/DNS, GitHub protections and approver — external setup required. These aren’t configured in .env. I found no .github/CODEOWNERS file.
S3 backup — not ready. BACKUP_S3_REMOTE and BACKUP_S3_PATH are absent, and the guide says backup work (#26) hasn’t been implemented.
Tunnel — optional and external. No tunnel configuration is present; set one up only when you’re ready to test Meta callbacks.
### A5. Decisions to make now

| Decision | Recommended default | Note |
| --- | --- | --- |
| 1. LLM provider | Anthropic (`llm_client.py` already has retry, backoff, timeout and cost logging). If you pick OpenAI, port those behaviours into `provider.py` first | One provider, one key, one data agreement | I  pick openrouter and want to use main model as nvidia/nemotron-3.5-lightning:free fallback model as LiquidAI: LFM3-1.7B (free) 
| 2. Contract drift (webhook, password-reset, send-message paths) | Code wins where it works; update `API_CONTRACT.md` in the same PR | Master rule: contract first | i will do it at last 
| 3. Quiet hours | 21:00–09:00 in the tenant timezone (Asia/Dhaka), stored in `tenant_settings`, admin-editable | Built in #9 and #20 |keep it the way its best for bangladesh
| 4. Follow-up scheduling | Backend writes `task.due` with `available_at = due_at` (#8). n8n never lists due tasks across tenants | `ARCHITECTURE.md` forbids it | keep it the way it its fast build for now but not the way it might cause future hinder . i want to finish this task asap
| 5. n8n licence | Email n8n for written confirmation before launch | Sustainable Use License | done 
| 6. Platform admin | `users.is_platform_admin` flag plus an MFA claim; cross-tenant reads only through narrowly scoped SECURITY DEFINER functions, never through the `crm_app` connection role |APPROVEd the proposed design. #25 |the 
| 7. Follow-up text | Task `notes` holds the approved text. Outside the 24-hour window an automated follow-up is skipped and the rep is notified | Per-tenant default templates are post-MVP |APPROVE
| 8. Support-access grants | Document as a known gap in `SECURITY.md` | Not built |DEFER TO POST-MVP.
| 9. Dashboard definitions | Conversion = leads created in period that are now `won` ÷ leads created in period. First response = first outbound message minus lead creation. Admin `scope=team` shows all teams unless `team_id` is given | Confirm with the product owner | APPROVE

### A6. Working with the AI coder

Paste this at the start of every session:

```
You are working in an existing multi-tenant FastAPI + PostgreSQL CRM.
1. Read the API_CONTRACT.md / DATABASE_SCHEMA.md / SECURITY.md sections I name. Match contract shapes exactly. If code and contract conflict, stop and ask; if we agree the code is right, update the contract in the same change.
2. Never trust tenant_id from the client. Use the tenancy dependency in core/tenancy.py. Every new tenant table needs RLS ENABLE + FORCE, a policy, composite FKs and an entry in the RLS coverage test.
3. Never use a superuser for application work or grant BYPASSRLS to crm_app/crm_worker. Any NOLOGIN role with BYPASSRLS must be narrowly scoped, explicitly approved and covered by the role allow-list test. Never skip or weaken a test. Never log secrets, tokens or message text. Do not add dependencies without telling me.
4. Write failing tests first: unit, API, cross-tenant, role-scope.
5. At most one Alembic migration per step; afterwards alembic heads shows exactly one head.
6. Run ruff and pytest. Show the output and the list of changed files. Do not touch unrelated files.
7. Name the PR after the step number and mark it 🔒 if the step is marked 🔒.
```

**Your review after every step:** `ruff` and `pytest -q` green; exactly one Alembic head; endpoint in `/docs`; a cross-tenant test and a role-scope test exist; `git diff` contains no keys, tokens or passwords; 🔒 PRs have two approvals.

---

## 5. Step 0 and ranking

### Step 0: stabilize what exists (before any new code)

1. Fix `.env.example`: replace the real `JWT_SECRET_KEY` value with `<your-jwt-secret>` and `WHATSAPP_ACCESS_TOKEN=hey` with `<whatsapp-access-token>`. Commit as a standalone cleanup PR.
2. Create `backend/requirements-dev.txt` with `pytest`, `httpx`, `ruff`, `respx` and `pip-audit`. Remove those five from `requirements.txt`. Update the venv: `pip install -r backend/requirements-dev.txt`.
3. Review any staged or unstaged changes; split them into focused PRs from `develop`: (a) merge migration plus AI job tests, (b) any remaining conflict resolutions.
4. `docs/SETUP_GUIDE.md` and `docs/USER_GUIDE.md` are present and README links resolve; keep them, update only for changes that require it.
5. Delete or git-ignore `needs.txt`.
6. Before merging anything, run `ruff check .`, `pytest -q` and `alembic heads` in `backend/`, and `npm run build` in `frontend/`.

### Ranking

Tier: 🔴 blocker · 🟠 core loop · 🟡 MVP-complete · 🟢 ship. ★ = hard task in the master plan.

| # | Step | Tier | 🔒 | Size | Needs | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | One Alembic head + CI check | 🔴 |  | S | none | 🟡 |
| 2 | DB roles and RLS audit | 🔴 | 🔒 | M | A3 | 🟡 |
| 3 | One LLM adapter, AI worker process | 🔴 | 🔒 | M | #2, LLM key | 🟡 |
| 3b | AI evaluation set and accuracy report | 🟠 |  | M | #3 | 🟡 |
| 4 | Users API audit, invitation tests | 🔴 | 🔒 | S | none | 🟡 |
| 5 | Tasks CRUD router — complete and harden | 🟠 | 🔒 | M | #2 | 🟡 |
| 6 | Pause-on-reply, opt-out cancel | 🟠 | 🔒 | M | #5 | 🟡 |
| 7 | Same-origin connectivity, api.ts security fix | 🟠 | 🔒 | M | none | 🔴 |
| 8 | Outbox fan-out and dispatcher | 🟠 | 🔒 | M | #3, #6 | 🔴 |
| 9 | Internal automation endpoints, quiet hours | 🟠 | 🔒 | L | #6, #8 | 🟡 |
| 10 | n8n in Docker Compose | 🟠 |  | M | A2, A3 | 🔴 |
| 11 | Workflow A: new lead | 🟠 |  | M | #9, #10 | 🔴 |
| 12 | Workflow B: follow-up | 🟠 |  | L | #9–#11 | 🔴 |
| 13 | Workflow C: customer reply | 🟠 |  | S | #9, #10 | 🔴 |
| 14 | Error workflow, requeue, exports | 🟠 |  | S | #11–#13 | 🔴 |
| 15 | Dashboard API | 🟡 | 🔒 | L | #5, #8, #9 | 🔴 |
| 16 | Frontend foundations | 🟡 |  | M | #4, #7 | 🟡 |
| 17 | Tasks page and approval queue | 🟡 |  | M | #5, #6, #16 | 🟡 |
| 17b | Lead detail AI card, CSV upload UI, bulk assign | 🟡 |  | M | #16 | 🟡 |
| 18 | Conversations inbox and reply box | 🟡 |  | L | #16 | 🟡 |
| 19 | Dashboard page | 🟡 |  | L | #15, #16 | 🟡 |
| 20 | Settings: users, teams, automation | 🟡 |  | M | #4, #9, #16 | 🟡 |
| 21 | Integrations settings, notification bell | 🟡 |  | M | #4, #16 | 🟡 |
| 22 | Caddy with TLS | 🟢 | 🔒 | M | domain | 🔴 |
| 23 | Production Docker Compose | 🟢 | 🔒 | L | #10, #22 | 🔴 |
| 24 | Hardening | 🟢 | 🔒 | M | none | 🟡 |
| 25 | Platform admin API | 🟢 | 🔒 | M | #2 | 🔴 |
| 26 | Backup, restore, export, delete | 🟢 |  | M | #2, bucket | 🔴 |
| 27 | Playwright end-to-end | 🟢 |  | M | #3, #17, #18 | 🔴 |
| 28 | Checklist, docs refresh, demo | 🟢 |  | M | all | 🟡 |

### Order of work

1. **Wave 1, gates (parallel):** #1, #2, #7, #4.
2. **Wave 2:** AI lane #3 → #3b, in parallel with tasks lane #5 → #6.
3. **Wave 3, three lanes:** automation #8 → #9 → #10 → #11 → #12 → #13 → #14 · dashboard API #15 · screens #16 → #17 → #17b → #18 → #20 → #19 → #21.
4. **Wave 4:** #24, #25, #26, #22 → #23, #27, then #28.

Merge into `develop` at least daily, and run the full suite in the integration window.

---

## 6. The steps

Every step lists the context, the text to give the agent, what only you do, and when it is done. 🔒 steps need the security approver.

### Phase 0: gates (#1–#4, #3b)

#### #1 One Alembic head + CI check 🔴 S

The staged merge migration `9a7c3e1f6b42` joins the outbox and notifications branches, but `e5c9a1d7b3f2` remains a separate head.

```
1. In backend/, run: alembic heads
   If there is more than one head, create a merge migration:
   alembic merge heads -m merge_all_heads
   Run alembic upgrade head on a temporary empty database to confirm the graph is linear.
2. Turn tests/unit/test_alembic_history.py into a real test: assert exactly one head, and assert that upgrade head succeeds on an empty temporary database (use a pytest fixture with a fresh connection).
3. Add a CI job with a Postgres service container that runs the same two checks and fails if the head count is not 1.
```

**Done when:** CI turns red if anyone introduces a second head.

---

#### #2 DB roles and RLS audit 🔴 🔒 M

Compose uses one superuser URL. `crm_app` and `crm_worker` exist in the database (migration `1fd32e46d6d9`), but role separation is not enforced in wiring or tests.

| Role | Used by | Rules |
| --- | --- | --- |
| `crm_app` | API | No superuser, no BYPASSRLS, not the table owner |
| `crm_worker` | AI worker and dispatcher | No superuser, no BYPASSRLS; only what outbox jobs need. Keep what `1fd32e46d6d9` grants; do not widen it |
| `crm_migrator` | Alembic only (table owner) | Subject to FORCE RLS |
| `crm_backup` | Backup job only | Read-only dump access; resolve whether full dumps under FORCE RLS require an approved BYPASSRLS grant against `DATABASE_SCHEMA.md` before deciding |

n8n has its own database user for `n8n_db` and never receives CRM database credentials.

```
Using DATABASE_SCHEMA.md section 15 and the role table above:
1. Confirm crm_app, crm_worker, crm_migrator and crm_backup exist with correct privileges. Do not grant BYPASSRLS to crm_app or crm_worker. Reconcile the backup role's full-dump requirement with DATABASE_SCHEMA.md's optional crm_resolver role; do not claim crm_backup is the only permitted exception.
2. infrastructure/docker-compose.yml passes DATABASE_URL (crm_app) to the API and WORKER_DATABASE_URL (crm_worker) to the worker and dispatcher. Migrations run as crm_migrator (MIGRATOR_DATABASE_URL). Only the backup job uses BACKUP_DATABASE_URL.
3. Extend tests/test_rls_coverage.py: every table with tenant_id has relrowsecurity AND relforcerowsecurity; crm_app and crm_worker have rolsuper=false and rolbypassrls=false; test the BYPASSRLS allow-list agreed in step 1; connected as crm_app with no app.tenant_id set, SELECT count(*) FROM leads returns 0.
4. .env.example gets DATABASE_URL, WORKER_DATABASE_URL, MIGRATOR_DATABASE_URL, BACKUP_DATABASE_URL and the n8n DB variables — placeholders only.
```

**You:** add the five DB passwords from A3 to `.env`.

**Done when:** the RLS audit test passes and `DATABASE_URL` no longer points at a superuser.

---

#### #3 One LLM adapter and the AI worker process 🔴 🔒 M

`ai/jobs.py` has the outbox claim framework and `default_analyzer` calls `analyze_with_openai` from `provider.py`. A separate `llm_client.py` is used by `classification.py` and the evaluation runner but not by `default_analyzer`. Nothing starts the job loop.

```
1. Create app/modules/ai/adapter.py: one Protocol, analyze(job: JobInput) -> AnalysisResult. ONE real adapter for the provider chosen in A5.1 (timeouts, retries, token and cost logging) and one FakeAnalyzer. LLM_PROVIDER env var selects it; an unknown value fails at startup; FakeAnalyzer is refused when APP_ENV=production.
2. Adapters never raise into the job runner: a provider error returns status=failed (the jobs.py contract).
3. In ai/jobs.py replace the direct analyze_with_openai call in default_analyzer with get_adapter(). Keep the flow exactly: load data, close the DB session, redact PII, call the adapter, validate with AssessmentOutput, persist with model and prompt version.
4. conversations/service.py uses the same adapter.
5. Create backend/app/worker.py so that python -m app.worker runs ai/jobs.run_forever with the adapter. Add a worker service to infrastructure/docker-compose.yml using WORKER_DATABASE_URL. Never start the loop inside main.py.
6. Tests use FakeAnalyzer and never touch the network: an adapter failure stores a failed assessment flagged for human review; an event goes dead after MAX_ATTEMPTS (5); confidence below 0.6 sets the review flag.
```

**You:** put the LLM key in `.env`, start the stack, create a lead, and within 30 seconds check that a `lead_assessments` row exists.

**Done when:** creating a lead produces an assessment through the worker, and every test passes offline.

---

#### #3b AI evaluation set and accuracy report 🟠 M

The repository already has a 50-record bilingual fixture at `backend/tests/fixtures/ai_evaluation.jsonl`, an evaluation runner at `backend/app/scripts/evaluate_ai.py`, and `backend/tests/unit/test_ai_evaluation_runner.py`. Extend these; do not create parallel files.

```
1. Review the existing synthetic fixture against the master requirement; add mixed-language examples and any missing expected labels (including priority) without introducing real customer text or phone numbers.
2. Extend backend/app/scripts/evaluate_ai.py to print the intent confusion table and metrics for the review threshold, including how many low-confidence predictions were wrong. Keep the existing per-field and per-language accuracy report.
3. Extend backend/tests/unit/test_ai_evaluation_runner.py to cover the added metrics with its injected fake predictor. The real provider run remains manual and outside CI.
4. Record the result in docs/AI_EVAL.md: date, model, prompt version and numbers. If 0.6 is wrong for this data, change the threshold and rerun.
```

**Done when:** the missing metrics are tested, and the numbers are in `docs/AI_EVAL.md` linked from the README. Also confirm that summary, sentiment, rule-based priority and task creation (master Day 8) have tests; add tests, not new code.

---

#### #4 Users API audit and invitation tests 🔴 🔒 S

`users/router.py` and `users/service.py` exist and are mounted. `notifications/router.py` is mounted. The tasks below audit and complete what is there.

```
1. Confirm GET /api/v1/users/me returns: profile, memberships, current role, and tenant timezone (default Asia/Dhaka until #9 adds tenant_settings). If tenant_timezone is missing, add it.
2. Confirm PATCH /me rejects role, email and tenant fields. Add a test for each rejected field.
3. Confirm GET /api/v1/users applies apply_data_scope: rep gets 403, manager sees own team, admin sees all. Add or confirm tests for each case.
4. Add the missing invitation tests: an invitation is single-use and expires; only admins invite; a deactivated membership gets 403 on its very next request and its refresh tokens are revoked; a tenant A invitation token cannot join tenant B; role changes are audited.
5. Do not add broad or wildcard CORS middleware. If a browser-based public-form embed requires cross-origin access, allow only its explicitly configured origin without credentials, per API_CONTRACT §2.9.
```

**Done when:** an admin invites a rep, the rep accepts and logs in, a deactivated rep loses access on the next request, and `/api/v1/users/me` works from the browser.

---

### Phase 1: Tasks API — complete and harden (#5, #6)

#### #5 Tasks CRUD router — complete and harden 🟠 🔒 M

`tasks/router.py` exists with list, create, get, patch, approve, reject and approval-queue endpoints, all mounted. What is missing: `GET /due-follow-ups`, `tasks/events.py`, idempotency key enforcement, optimistic version locking on PATCH, `apply_data_scope` on list, and a timeline entry on update. Give the agent `API_CONTRACT` sections 10.1–10.3, `tasks/models.py`, `tasks/router.py` and `tasks/service.py`.

```
Audit and extend the existing tasks/router.py and tasks/service.py:
1. GET /due-follow-ups must be declared BEFORE /{task_id}. It returns open follow_up tasks where due_at <= now, scoped by apply_data_scope. Confirm the route ordering is correct.
2. POST / must require an Idempotency-Key header. Reuse the idempotency helper from leads/crud.py: extract it to a shared module (core/idempotency.py or similar), do not copy it.
3. PATCH /{task_id}: a stale version field returns 409 conflict. Add the version check if it is not already in service.update_task.
4. apply_data_scope: confirm GET / uses it (rep own, manager team, admin all). Add it if missing.
5. Every PATCH writes an audit log and a lead timeline interaction (type task_updated). Add these if missing.
6. Create tasks/events.py with emit_task_event(session, event_type, task). Until #8 it writes nothing for event types that have no consumer yet; the function exists so callers do not need to change in #8.
7. Tests: cross-tenant read and update; rep sees only own, manager only team; a duplicate idempotency key replays the original response; two concurrent PATCHes give the second a 409; GET /tasks/due-follow-ups is not swallowed by /{task_id}.
```

---

#### #6 Pause-on-reply, opt-out cancel 🟠 🔒 M

The approve and reject endpoints exist in `tasks/router.py` and `tasks/service.py`. What is missing is the pause and cancel logic, and its wiring into the inbound message and opt-out paths.

```
1. Confirm POST /api/v1/tasks/{id}/approve (API_CONTRACT 10.5): 409 invalid_approval_state unless requires_approval is true and approval_status is pending. Manager approves own team, admin any, rep never. Approval writes an audit log and calls emit_task_event for task.due with available_at = max(now, due_at). There is no separate task.approved consumer.
2. Confirm POST /api/v1/tasks/{id}/reject: symmetric; it cancels any pending task.due row.
3. Add tasks/service.py pause_followups(session, lead_id, reason): sets status=paused on that lead's open tasks of type follow_up only. Call, meeting and reminder tasks are untouched. Writes a timeline entry. Call it from inbound.py or whatsapp.py where an inbound message is stored.
4. Add cancel_followups(session, lead_id, reason): same selection, status=cancelled. Call it from leads/optout.py. Opt-out is permanent; a reply is not.
5. Paused tasks are resumed only by a rep or manager (PATCH status=open). Nothing resumes them automatically.
Tests: an inbound message pauses that lead's follow-ups only (other leads and call tasks untouched); opt-out cancels; a paused or cancelled task cannot be sent (messaging returns 409); a rep gets 403 on approve; approving a task of a won or lost lead still cannot send; cross-tenant approve returns 404.
```

**Done when:** tests prove both an inbound message and an opt-out stop pending follow-ups.

---

### Phase 2: browser connectivity (#7)

#### #7 Same-origin connectivity and the api.ts security fix 🟠 🔒 M

`next.config.ts` is empty. Two API clients exist: `frontend/src/lib/api.ts` stores the access token in browser storage; `frontend/src/lib/api/client.ts` keeps it in memory and calls a configured absolute API URL. These must be unified before building more screens. `X-Tenant-ID` is required by API_CONTRACT §§2.3 and 3.2; it selects a tenant but is not authorization, because the backend verifies the caller's active membership on every request.

```
1. next.config.ts: add rewrites that proxy browser requests under /api/:path* to BACKEND_INTERNAL_URL (default http://localhost:8000; http://backend:8000 inside Compose). The current provider webhook route is /api/v1/webhooks/{provider}; also route it. Do not expose /internal. Same-origin authenticated requests need no CORS; configure only explicit public-form origins if required.
2. Replace both frontend/src/lib/api.ts and frontend/src/lib/api/client.ts with one relative-URL client. Migrate every caller: signup, invitation acceptance, password reset and lead screens. Keep the access token in memory (module variable or AuthProvider), never in localStorage or sessionStorage. On page load call POST /api/v1/auth/refresh (HttpOnly cookie plus X-CSRF-Token header) before rendering authenticated pages. Retry once on 401, then redirect to /login.
3. Keep X-Tenant-ID as the contract-required tenant selector. Never use it as proof of authorization: the server checks active membership and tenant status on every request before setting RLS context.
4. Verify the existing tests/cross_tenant/test_tenant_header.py: a request selecting a tenant the user does not belong to returns 403 and no tenant data. Add a case only if that behavior is not covered.
```

**You:** log in, reload the page, confirm the session refreshes with no console errors and no token under the browser's storage inspector.

---

### Phase 3: automation with n8n (#8–#14)

#### #8 Outbox fan-out and n8n dispatcher 🟠 🔒 M

`core/outbox.py` writes `lead.created` and `message.received`; `ai/jobs.py` claims them with `FOR UPDATE SKIP LOCKED`. With one row per event, the AI worker and n8n would compete.

```
Read core/outbox.py first and report how consumers are separated today. Then:
1. One row per consumer, written in the same transaction as the business change, each with its own uuid4 idempotency key:
   assessment.requested -> claimed by the AI worker (ai/jobs.py)
   lead.created, lead.replied, task.due, task.cancelled -> claimed by the n8n dispatcher
   An inbound message writes assessment.requested and lead.replied. Keep the worker able to drain legacy lead.created and message.received rows until none are pending.
2. Switch on tasks/events.py emit_task_event(): creating a follow-up writes task.due with available_at = due_at. Completing, cancelling, pausing or rescheduling a task cancels or replaces the pending row. Cancelling the row is an optimization; the real safety is the re-check at send time (#9).
3. Dispatcher: backend/app/dispatcher.py (python -m app.dispatcher, logic in core/dispatcher.py), connecting as crm_worker. Claims n8n-bound rows with SKIP LOCKED and POSTs them to the n8n webhook URL with X-Event-ID (the outbox row id), X-Timestamp and X-Signature = sha256=<hex> of HMAC-SHA256(N8N_EVENT_SIGNING_SECRET, timestamp + '.' + raw_body). Body: ids and event type only, never PII or message text. Exponential backoff; dead after MAX_ATTEMPTS (5); a dead event is never auto-retried.
4. Add the dispatcher service to infrastructure/docker-compose.yml.
Tests: signature format matches the canonical string; failed delivery retries and then goes dead; one new lead produces separate rows for the AI worker and the dispatcher; cancelling a task cancels its pending task.due; no event type is written without a consumer.
```

---

#### #9 Internal automation endpoints and quiet hours 🟠 🔒 L

`automation/router.py` has the `/health` endpoint but is not mounted in `main.py`. `core/service_auth.py` is complete. The notifications HMAC handler is already mounted. The endpoint set below intentionally differs from API_CONTRACT §14 (which currently includes assignment and due-task listing); reconcile and update the contract in the same PR before coding; stop and ask if that deviation is not approved.

```
1. Mount automation/router.py in main.py under /internal/v1/automation (the router already declares this prefix; just add app.include_router(automation_router)).
2. Implement the remaining endpoints under /internal/v1/automation with require_internal_service exactly as notifications/router.py does:
   GET  /health                  already exists; confirm it is mounted
   GET  /leads/{lead_id}         lead context: name, status, assigned_user_id, team_id, opted_out (no contact details)
   POST /leads/{lead_id}/assess  assess if assessment is missing or failed
   POST /messages                send; MUST go through messaging/service.py pipeline
   POST /tasks/{task_id}/result  record outcome: sent, failed, skipped, needs_approval; failed may carry retryable=true
   POST /notifications           already mounted via notifications/router.py; confirm it is reachable
3. Rules for every endpoint:
   - Open a normal tenant-scoped transaction (set_config app.tenant_id from the signed X-Tenant-ID). No bypass.
   - Resource id must belong to that tenant, otherwise 404 (not 403).
   - No list-all routes. No PATCH on tasks.
   - Idempotent: same key plus same body replays the stored response for 24 hours; same key with different body is 409.
4. POST /messages re-checks everything at send time: task is open (not paused, cancelled or done), approval satisfied, lead not opted out and not won or lost, consent exists, 24-hour window open, not quiet hours.
5. Quiet hours: new table tenant_settings (tenant_id PK, timezone, quiet_hours_start, quiet_hours_end; defaults 21:00–09:00 Asia/Dhaka; RLS ENABLE + FORCE; entry in the RLS coverage test). Helper: is_quiet_hours(tenant_id, now). During quiet hours: in one transaction move task due_at to end of the window (task stays open), emit new task.due with that available_at, return 202 with reason quiet_hours.
6. Retries: POST /tasks/{id}/result with failed + retryable=true makes the backend emit ONE retry task.due at now + 10 minutes. n8n holds no timers.
7. Settings API: GET and PUT /api/v1/settings/automation (admin only, audited) for timezone and quiet hours. Create app/modules/settings/ for this.
Tests (offline, no n8n): bad HMAC 401; timestamp outside 300 s 401; replay with different body 409; resource of another tenant 404; idempotent replay has no side effects; quiet hours reschedules instead of sending; paused, cancelled and done tasks and opted-out leads never send; rep gets 403 on the settings API.
```

---

#### #10 n8n in Docker Compose 🟠 M

Compose currently has mailpit, db, backend, worker (from #3) and dispatcher (from #8). The backend env passes `N8N_SERVICE_SECRET`; rename it to `SERVICE_HMAC_SECRET` everywhere.

```
Edit infrastructure/docker-compose.yml:
1. Networks: crm_net = backend, worker, dispatcher, db. automation_net = backend, dispatcher, n8n, n8n_db. n8n is NOT on crm_net and holds no CRM DB credentials.
2. n8n_db: pinned postgres 16.x, its own volume and credentials, automation_net only.
3. n8n: the pinned tag from A2, automation_net only, depends_on n8n_db. Environment: N8N_ENCRYPTION_KEY, DB_TYPE=postgresdb plus DB_POSTGRESDB_* from .env, EXECUTIONS_DATA_PRUNE=true, EXECUTIONS_DATA_MAX_AGE=24, EXECUTIONS_DATA_SAVE_ON_SUCCESS=none, GENERIC_TIMEZONE=Asia/Dhaka, N8N_DIAGNOSTICS_ENABLED=false, WEBHOOK_URL=http://n8n:5678/. Do NOT set N8N_LISTEN_ADDRESS=127.0.0.1: inside a container it blocks the dispatcher. Publish the editor with ports: 127.0.0.1:5678:5678 (host loopback only). Production uses the same binding; the editor is reached through an SSH tunnel; Caddy never routes it.
4. Healthcheck on /healthz.
5. Update .env.example with every new n8n variable.
```

**You:** bring the stack up, open `http://127.0.0.1:5678`, create the owner account and save its password. Make `SERVICE_HMAC_SECRET` and `N8N_EVENT_SIGNING_SECRET` available to Code nodes without writing them into any workflow JSON: check how the pinned n8n version exposes environment variables to Code nodes and never paste a secret into a workflow. Verify that n8n gets 200 from `GET /internal/v1/automation/health` and cannot resolve the CRM database host.

---

#### #11 Workflow A: new lead 🟠 M

The dispatcher delivers `lead.created`. Capture already assigns the lead and requests the initial assessment, so Workflow A must not reassign or duplicate completed work.

```
1. Sub-workflow sign-and-call: input method, path, body, tenant_id, idempotency_key. Signs with SERVICE_HMAC_SECRET using EXACTLY the canonical string in core/service_auth.py (v1 + service_id + tenant_id + METHOD + path + timestamp + idempotency_key + sha256(body)) and calls the internal API.
   Golden vector: add backend/tests/unit/test_service_auth_vectors.py with a fixed input and its expected signature. Copy the same vector into n8n/README.md, and require both the sub-workflow and simulate_n8n.py to reproduce it.
2. Workflow A on the lead.created webhook:
   a. Verify X-Signature (N8N_EVENT_SIGNING_SECRET over timestamp + '.' + raw body) and reject timestamps older than 300 s. Dedupe on X-Event-ID in n8n is best-effort; the real dedupe is the idempotency key (the event id) on every internal call.
   b. GET /leads/{id}.
   c. POST /leads/{id}/assess only if the lead has no assessment or the latest one failed.
   d. POST /notifications for the assigned rep (idempotency key = event id).
   Never reassign the lead. Never create a second assessment or a task.
3. backend/scripts/simulate_n8n.py makes the same signed calls so Workflow A can be tested without n8n. backend/scripts/simulate_whatsapp.py posts a correctly signed WhatsApp inbound webhook so a demo can start a lead.
```

**You:** import the workflow JSON, run it with a seeded lead, confirm the notification through the API.

---

#### #12 Workflow B: follow-up 🟠 L

Triggered by `task.due`. All safety decisions live in the backend (#9); n8n only orchestrates.

```
Workflow B on the task.due webhook:
1. Verify the signature; dedupe on the event id (best-effort).
2. POST /messages with the task id.
3. Backend answers: 200 sent; 202 quiet_hours (already rescheduled, nothing more to record); 409 approval_required; 409 opted_out; 409 window_closed; 409 task_not_open.
4. Record every outcome with POST /tasks/{id}/result and a non-sensitive error_code. Never log message text.
5. approval_required: notify rep and manager. window_closed: notify rep (automated follow-ups outside the window are skipped; a rep may send a template by hand). failed: report retryable=true once; a second failure records failed and notifies.
```

**Done when:** a `simulate_n8n.py` test proves that a lead who opted out or replied never receives the follow-up, and a stale `task.due` for a paused task is skipped.

---

#### #13 Workflow C: customer reply 🟠 S

A reply pauses follow-ups in the backend before `lead.replied` is emitted (#6), so even with n8n down they are already paused. Workflow C is a best-effort enhancement.

```
Workflow C on lead.replied:
1. Verify the signature; dedupe on the event id.
2. POST /notifications for the assigned rep; if the lead has no owner, notify the team managers.
3. POST /leads/{id}/assess to re-run intent.
n8n never creates tasks: backend rules create any follow-up task after the new assessment (create_assessment_follow_up). Idempotent for the same event id.
```

---

#### #14 Error workflow, requeue, exports 🟠 S

```
1. n8n error workflow: report workflow id, node name and error class only, never payload content, through the smallest existing internal endpoint (a notification to the tenant's admins). Add an endpoint only if that cannot work.
2. backend/scripts/requeue_dead.py: lists dead outbox events (id, type, attempts, last error code) and requeues one by id, writing an audit log. Document retry and dead behaviour in ARCHITECTURE.md: backoff, MAX_ATTEMPTS=5, a dead event is never auto-retried.
3. CI step: a grep for secret, token, password and key patterns under n8n/workflows/ fails the build.
4. Failure tests with simulate_n8n.py: with n8n down, events retry and go dead after 5 attempts; when n8n returns there are no duplicate messages or tasks; a 401 from the internal API is recorded without payload.
```

**You:** export with `n8n export:workflow --all --separate --output=n8n/workflows/`. Never export credentials. Run the grep before committing.

**Done when:** the simulated flow works end to end: WhatsApp lead → assessed → assigned → reminder dispatched → customer replies → follow-ups pause.

---

### Phase 4: dashboard API (#15)

#### #15 Dashboard summary API 🟡 🔒 L

`dashboard/__init__.py` is empty. Give the agent API_CONTRACT section 11, SECURITY section 5 and master §15.

| Scope | Widgets | Priority |
| --- | --- | --- |
| `me` (rep) | My new leads, my high-priority leads, follow-ups due today, overdue tasks, recent conversations (last 5), my conversion rate | Core |
| `team` (manager) | Leads by source, leads per rep, conversion by rep, pipeline stages and lost reasons | Core |
| `team` (manager) | Average first-response time, follow-up completion rate | Cut-first |
| `company` (admin) | Overall performance (created, won, conversion), users and roles (counts by role), lead-source performance (reuses manager queries without a team filter) | Core |
| `company` (admin) | Automation success and failure (outbox rows by status plus task results), integration health (integrations by status) | Cut-first |

```
Build dashboard/service.py and dashboard/router.py and mount them.
GET /api/v1/dashboard/summary?scope=<me, team or company>&from=&to=&team_id=
  me: any role. team: manager or admin. company: admin only. Any other combination returns 403 BEFORE any query runs.
  team_id is optional: a manager's own team is implied; admin without team_id sees all teams.
  Default range 30 days; more than 366 days returns 422. Group by day in tenant_settings.timezone (from #9).
  Response: one Pydantic schema per scope, with the field names from the widget table above. Publish the schema in the first hour of this step, because #19 is built from it.
Filter order: RLS (tenant context) first, then role scope as an explicit SQL WHERE. Never fetch cross-role data and filter it in Python.
Build in this order, one PR each: 1. rep widgets, 2. manager core, 3. admin core, 4. cut-first widgets.
Add the indexes from DATABASE_SCHEMA.md, run EXPLAIN ANALYZE on seeded data and put the result in the PR.
Tests: rep asking for team or company gets 403; manager asking for company gets 403; manager sees only own team; data from two tenants never mixes; range over 366 days returns 422; admin with team_id is filtered correctly.
```

---

### Phase 5: frontend screens (#16–#21)

For every screen:
- Use the client fixed in #7. Tokens stay in memory, never in browser storage.
- Render all customer-supplied text as plain text, never `dangerouslySetInnerHTML`.
- Handle 401 (login), 403 (access denied), empty and error states.
- Role-aware UI is a convenience; the server enforces authorization.
- The tasks, conversations, settings and integrations pages already exist as local-state mock shells. Replace the mock state with TanStack Query hooks; do not restyle or rebuild them.

#### #16 Frontend foundations 🟡 M

The Query provider, sidebar and shadcn components exist.

```
1. AuthProvider: bootstraps with the refresh call from #7 and exposes loading, user and roles.
2. useCurrentUser: GET /api/v1/users/me through TanStack Query, including the tenant timezone.
3. Role-aware navigation: links appear only if the role allows them. Route guards: unauthenticated goes to /login, wrong role goes to /403. Guards use /users/me; the server stays the real check.
4. Shared components: DataTable, EmptyState, ErrorBanner, LoadingSpinner, plus an apiError helper that maps 401, 403, 409 and 422 to UI states.
```

---

#### #17 Tasks page and approval queue 🟡 M

```
Tabs: Today, Overdue, Upcoming, Approval queue (approval_status=pending). Day buckets use the tenant timezone from /users/me.
Actions: mark done (PATCH status=done with version); approve and reject (manager and admin only); a 409 shows inline, refetches and lets the user retry.
Paused tasks show a 'Paused: customer replied' badge with a Resume action (PATCH status=open); cancelled tasks are read-only.
```

---

#### #17b Lead detail AI card, CSV upload, bulk assign 🟡 M

```
Lead detail: the current page already renders a basic AI card from latest_assessment in GET /api/v1/leads/{id}. Complete it with sentiment and the final review-state UX; load the activity timeline from the existing GET /api/v1/leads/{id}/timeline; add lost status/reason only after checking the contract and backend support.
Lead list: add CSV upload using the existing POST /api/v1/leads/import and display duplicate and row-error results. Bulk assign is cut-first and has no current API endpoint; omit it unless the API is designed and approved first.
The assessment-history route is documented in API_CONTRACT but is not implemented by the current AI router. Do not add it solely for the existing latest-assessment card; reconcile the contract if assessment history becomes a requirement.
```

---

#### #18 Conversations inbox and reply box 🟡 L

```
Left panel: conversations ordered by last_message_at descending. Right panel: the thread in chronological order plus a reply box.
Reply box: POST /api/v1/messages with conversation_id in the request body (this is the current API contract and route). Show the 24-hour window state from last_inbound_at (confirm the field is in the conversation response; add it to the schema if not). If the window is closed, disable free text, show 'Template required' and offer only currently approved WhatsApp templates. If the lead is opted out, disable the box and show an Opted out badge.
Link each conversation header to the lead detail page.
```

---

#### #19 Dashboard page 🟡 L

```
Three views driven by scope, drawn with Recharts and built from the #15 schema: rep (scope me), manager (team, with the per-rep breakdown), admin (company, with source breakdown and, when present, automation and integration health).
The scope selector offers only the scopes the role may use. A 403 shows an Access denied card.
The root route / already has a static dashboard shell in frontend/src/app/page.tsx; wire that page to the dashboard API rather than creating a duplicate route.
Build the rep view first; manager and admin views may follow in later PRs. Hide widgets the API does not return yet.
```

---

#### #20 Settings: users, teams, automation 🟡 M

```
Admin only. Three tabs:
  Users: list members; invite (POST /api/v1/invitations); change role and deactivate using the paths invitations/router.py actually implements.
  Teams: list (GET /api/v1/teams) and create (POST /api/v1/teams).
  Automation: timezone and quiet hours (GET and PUT /api/v1/settings/automation from #9).
Show the current role badge. Deactivation asks for confirmation.
```

---

#### #21 Integrations settings and notification bell 🟡 M (first to cut: the bell; keep the integrations page)

```
Backend first, because the bell calls routes that do not exist yet: GET /api/v1/notifications?read=false and PATCH /api/v1/notifications/{id}/read, tenant-scoped, a user sees only their own, with cross-tenant and own-only tests. Confirm DELETE /api/v1/integrations/{id} exists; if not, add it (admin only, audited).
Integrations page: list from GET /api/v1/integrations; a connect form with write-only credential fields (type password, never displayed again); disconnect; a Copy embed code button for the public lead form. GET never returns secrets; only admins can open the page (test both).
Bell: unread badge polled every 60 seconds, dropdown with mark-as-read.
```

---

### Phase 6: harden and ship (#22–#28)

#### #22 Reverse proxy with TLS (Caddy) 🟢 🔒 M(postponed)

```
Write infrastructure/reverse-proxy/Caddyfile for {domain}:
  /api/* goes to backend:8000 (including /api/v1/webhooks/{provider}); everything else goes to frontend:3000.
  /internal/* returns 404 and is never proxied. No route to n8n. /docs, /redoc and /openapi.json return 404 in production.
  Headers: Strict-Transport-Security max-age=63072000; includeSubDomains (no preload until the domain is final), X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy, and frame-ancestors none.
  Content-Security-Policy is NOT set statically in Caddy: Next.js needs a per-request nonce, so set it in Next middleware (script-src self plus the nonce, no unsafe-inline). Caddy sets the other headers.
  Request body limits from API_CONTRACT section 2.9 (1 MB on /api/v1/webhooks/*, 10 MB on CSV import).
  Pass the real client IP and make FastAPI trust forwarded headers only from the Caddy network (uvicorn --proxy-headers with forwarded-allow-ips set to the Caddy address).
Write infrastructure/reverse-proxy/README.md with the deploy steps.
```

**You:** point the domain's DNS A record at the server and wait for propagation. Then check that `https://<domain>/internal/v1/automation/health` returns 404.

---

#### #23 Production Docker Compose 🟢 🔒 L(postponed)

`infrastructure/docker-compose.yml` is dev-only (source-mounted, no frontend container, no Caddy).

```
Create infrastructure/docker-compose.prod.yml:
  frontend    built image, no published port
  backend     built image, non-root, no source mount, env from env_file
  worker      backend image, python -m app.worker, crm_worker
  dispatcher  backend image, python -m app.dispatcher, crm_worker
  db          postgres 16.x pinned, crm_net only, no published port
  n8n         pinned tag, automation_net only; the only port is 127.0.0.1:5678 on the host (SSH tunnel), never public
  n8n_db      postgres 16.x pinned, automation_net only, no published port
  migrate     one-shot: alembic upgrade head as crm_migrator; backend depends_on it with condition service_completed_successfully
  caddy       pinned 2.x tag; the only service publishing ports, and only 80 and 443
Healthchecks: db pg_isready; backend /health/ready (also pings the DB pool); n8n /healthz; worker and dispatcher write a heartbeat the healthcheck reads.
Restart unless-stopped on backend, worker, dispatcher, n8n, caddy. Log rotation (json-file max-size and max-file) on every service.
Secrets come from env_file only, never from the image or the compose file. Networks as in #10.
```

**You:** provision the VPS, install Docker, open only ports 22, 80 and 443, copy `.env` to the server with `chmod 600`, then run `docker compose -f infrastructure/docker-compose.prod.yml up -d`.

---

#### #24 Hardening 🟢 🔒 M(postponed)

```
1. Verify, and add tests where missing: refresh cookie is HttpOnly, Secure and SameSite=strict; a CSRF token is required on cookie-authenticated mutations; security headers arrive through Caddy; the CSP nonce works in a production build.
2. Public form: per-IP (10 per minute) and per-form (100 per hour) limits using the PostgreSQL-backed approach in auth/rate_limit.py. Honeypot: a filled hidden field returns the normal success response and stores nothing.
3. Tenant-aware limits on POST /messages and on the internal automation routes, because sending costs money.
4. CSV import (leads/csv_import.py): reject files over 10 MB or over a row cap (for example 5,000); require text/csv; validate phones as E.164 (a leading + is valid, never strip or quote it); report row-level errors instead of failing the whole file. Escape formula characters (= + - @) on any CSV export; the MVP has none.
5. An unverified email cannot log in (add the check in auth/service.py if missing).
6. FastAPI docs_url, redoc_url and openapi_url are disabled when APP_ENV=production.
7. CI: pip-audit -r requirements.txt; npm audit --omit=dev --audit-level=high; a test that scans the test-run logs for Bearer tokens, password= and message-text patterns.
```

---

#### #25 Platform admin API 🟢 🔒 M

```
platform/router.py under /api/v1/platform. Every route requires require_platform_admin AND an MFA-verified session (mfa_verified_at claim):
  GET  /tenants
  GET  /tenants/{id}          detail plus member count
  POST /tenants/{id}/suspend  sets status=suspended; audited
  GET  /health                DB connections and the dead outbox count across tenants
Cross-tenant reads never give crm_app BYPASSRLS. Follow the SECURITY DEFINER pattern and the optional crm_resolver role in DATABASE_SCHEMA.md; confirm with the security approver which narrowly scoped functions and privileges are needed, then reflect the approved role in the #2 allow-list test. The functions return counts and tenant metadata only, never lead or message data.
Tests: a company admin gets 403 on every /platform route; crm_app still cannot SELECT another tenant's leads; a suspended tenant's users fail the per-request membership check.
Document support-access grants as a known gap in SECURITY.md.
```

---

#### #26 Backup, restore, export, delete 🟢 M(postponed)

```
Fill backup_job/:
  backup.sh: connect as crm_backup (BACKUP_DATABASE_URL) and run pg_dump --format=custom; encrypt with age --recipient <public key>; upload with rclone copy to remote:bucket/crm/YYYY-MM-DD/; delete local files; log only success or failure, never connection strings. Ensure the role can dump all FORCE-RLS rows; if that requires BYPASSRLS, get explicit security approval and include it in the #2 role allow-list. A failure exits non-zero AND alerts (ping a health-check URL or send an email). Retention: 14 daily and 8 weekly dumps.
  restore.sh <file>: download, decrypt, restore into a scratch database (never production); assert tenants > 0 and leads > 0; then run the RLS coverage test against the restored database.
  export_tenant.py <tenant_id>: export one tenant as JSON (leads, conversations, tasks, assessments); audit entry tenant.exported.
  delete_tenant.py <tenant_id>: confirm twice; run as crm_migrator but set app.tenant_id first, because FORCE RLS applies to the table owner and a bare DELETE removes zero rows; check the composite-FK cascades; write the audit entry to a platform-level log that is not deleted with the tenant; verify zero rows remain in every tenant table afterwards.
Document in SECURITY.md that deleted tenant data stays in encrypted backups until the retention window ends.
```

**You:** create the bucket, run `age-keygen` and keep the private key offline in your password manager, add the cron entry `0 2 * * *`, and run one full restore by hand.

---

#### #27 Playwright end-to-end tests 🟢 M(postponed)

```
Create frontend/tests/ and a compose test profile: backend, worker with LLM_PROVIDER=fake (refused in production), db, frontend.
happy_path.spec.ts: log in as a seeded rep; create a lead in the UI; see it in the list with status new; open the detail page and see the AI card and the follow-up task the fake adapter produced; complete the task and see it done.
role_check.spec.ts: log in as a rep; the dashboard offers only scope me; requesting scope=company directly shows Access denied (the API returns 403), not a blank page.
Admin MFA: use a seeded test TOTP secret with otplib. Never add an MFA bypass to production code.
Add a CI job that runs both specs.
```

**You:** run `npx playwright test --headed` and watch both pass.

---

#### #28 Final checklist, docs refresh, demo prep 🟢 M(postponed)

```
1. Fill the table in section 7 with the real test file and test name for each item. An item without a test gets one, or is marked known gap in SECURITY.md.
2. ARCHITECTURE.md: document every mounted router (see Appendix C), the two networks, the worker and dispatcher, and the two deviations from master section 13 (Workflows A and B).
3. API_CONTRACT.md should already match the code (A5.2). Confirm with a final comparison against /openapi.json.
4. DATABASE_SCHEMA.md: replace crm_owner with crm_migrator; document tenant_settings and the role table.
5. Review and update docs/SETUP_GUIDE.md and docs/USER_GUIDE.md (one section per role); confirm every README link still works.
6. Seed two demo companies. Demo script, under 10 minutes: sign up Acme Sales (admin, manager, two reps) → invite and accept → backend/scripts/simulate_whatsapp.py sends a signed inbound message → the AI assessment appears on the lead detail page → rep notification and follow-up task → Workflow B runs (n8n, or simulate_n8n.py) → the customer replies through simulate_whatsapp.py and follow-ups pause → manager dashboard → admin company dashboard.
```

---

## 7. Master §18 checklist: where each proof comes from

| Checklist item | Proof |
| --- | --- |
| Company A cannot read, update or delete Company B's data | `tests/cross_tenant/`, extended in every step; #4, #5, #9, #15, #21 and #25 each add one |
| A sales rep cannot access unauthorized team leads | Role-scope tests in #5 and #15, plus the existing leads tests |
| A manager cannot access another company's dashboard | #15 cross-tenant dashboard test |
| A company admin cannot access platform administration | #25 test: 403 on every `/platform` route |
| Duplicate webhooks create no duplicate leads or messages | Existing webhook idempotency tests; replay check in #14 |
| Follow-ups stop when the lead replies or opts out | #6 tests; #12 simulate test |
| n8n cannot retrieve unrestricted data from other tenants | #9 (no list routes, foreign tenant returns 404) and the #10 check that n8n cannot reach the CRM database |
| Integration credentials are encrypted and hidden from ordinary users | Existing crypto tests; #21 test that GET never returns secrets and non-admins are refused |
| Backups restore correctly; tenant data can be securely deleted | #26 restore drill and delete test |
| Failed workflows are logged and safely retryable | #14 failure tests and the requeue script |
| Logs contain no passwords, tokens or unnecessary message content | #24 log-scan test; n8n retention settings from #10 |

**Priority order from the master guide:** secure tenant isolation, then CRM core, then AI, then automation. If isolation is wrong, nothing built on top of it makes this a safe SaaS product.

---

## Appendix A. Behaviour the agent must not change

| Behaviour | File | Why |
| --- | --- | --- |
| Signature verification runs before JSON parsing on webhook routes | `integrations/webhooks.py` | Stops DoS through malformed bodies |
| The DB session is closed before the LLM is called | `ai/jobs.py` | Never hold a row lock over a network call |
| Refresh tokens use family chains and reuse detection | `auth/sessions.py` | Token theft revokes the whole family |
| The outbound message pipeline commits before calling the Meta API | `messaging/service.py` | No duplicate sends on retry |
| `apply_data_scope` filters in SQL | `core/permissions.py` | Never fetch data and filter it in Python |
| `set_config('app.tenant_id', ..., true)` is re-run after every commit | `core/tenancy.py` | Transaction-local, safe with connection pooling |
| Webhook integration is resolved through a SECURITY DEFINER function | `integrations/webhooks.py` | `crm_app` needs no direct table access |

---

## Appendix B. Files that do not exist yet

```
backend/app/modules/ai/adapter.py                        (#3)
backend/app/worker.py                                    (#3)
backend/app/modules/tasks/events.py                      (#5)
backend/app/dispatcher.py and core/dispatcher.py         (#8)
backend/app/modules/settings/ (tenant_settings API)      (#9)
backend/app/modules/dashboard/service.py, router.py      (#15)
backend/app/modules/platform/router.py                   (#25)
backend/tests/unit/test_service_auth_vectors.py          (#11)
backend/scripts/simulate_n8n.py, simulate_whatsapp.py    (#11)
backend/scripts/requeue_dead.py                          (#14)
backend/requirements-dev.txt                             (Step 0 / A2)
.github/CODEOWNERS                                       (A4)
frontend/src/app/notifications (bell component)          (#21)
frontend/tests/happy_path.spec.ts, role_check.spec.ts    (#27)
infrastructure/reverse-proxy/Caddyfile                   (#22)
infrastructure/docker-compose.prod.yml                   (#23)
backup_job/backup.sh, restore.sh, export_tenant.py, delete_tenant.py   (#26)
docs/AI_EVAL.md                                          (#3b)
```

Files that now exist (removed from the previous revision's list):
- `backend/app/modules/users/router.py` and `service.py` — built and mounted
- `backend/app/modules/tasks/router.py` — built and mounted; `events.py` still missing (see #5)

For #3b, the fixture, runner and runner tests already exist at `backend/tests/fixtures/ai_evaluation.jsonl`, `backend/app/scripts/evaluate_ai.py` and `backend/tests/unit/test_ai_evaluation_runner.py`; only the missing evaluation outputs and documentation need to be added.

The root route already has a static dashboard shell in `frontend/src/app/page.tsx`; wire that page to the dashboard API for #19 rather than creating a duplicate route.

---

## Appendix C. Routers in `main.py` (17 Nov 2026 — live state)

| Router | Prefix | Status |
| --- | --- | --- |
| auth, password reset | `/api/v1/auth` | ✅ mounted |
| assessments | `/api/v1/assessments` | ✅ mounted |
| conversations | `/api/v1/conversations` and `/api/v1/leads/{id}/timeline` | ✅ mounted |
| messaging | `/api/v1/messages` | ✅ mounted |
| lead forms | `/api/v1/public/forms` | ✅ mounted |
| leads | `/api/v1/leads` | ✅ mounted |
| teams | `/api/v1/teams` | ✅ mounted |
| provider webhooks | `/api/v1/webhooks/{provider}` | ✅ mounted |
| integrations | `/api/v1/integrations` | ✅ mounted |
| invitations | `/api/v1` | ✅ mounted |
| notifications (internal HMAC handler) | `/internal/v1/automation/notifications` | ✅ mounted |
| users | `/api/v1/users` | ✅ mounted (GET /me, PATCH /me, GET /) |
| tasks | `/api/v1/tasks` | ✅ mounted (list, create, get, patch, approve, reject, approval-queue) |
| automation (internal) | `/internal/v1/automation` | ⚠️ /health exists in router but router NOT mounted yet — mount in #9 |
| automation settings | `/api/v1/settings/automation` | ❌ build in #9 |
| notifications (user bell routes) | `/api/v1/notifications` | ❌ build in #21 |
| dashboard | `/api/v1/dashboard` | ❌ build in #15 |
| platform | `/api/v1/platform` | ❌ build in #25 |
