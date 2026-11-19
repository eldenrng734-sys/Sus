# Multi-Tenant AI CRM — Engineering Memory & State Tracker

## Preamble Rules (Every Step)
1. Match `API_CONTRACT.md`, `DATABASE_SCHEMA.md`, `SECURITY.md` shapes exactly. Stop & ask on conflict; update contract in same change.
2. Never trust `tenant_id` from client. Use `core/tenancy.py`. Every tenant table needs `RLS ENABLE + FORCE`, policy, composite FKs, RLS coverage test.
3. No superuser for app work; no `BYPASSRLS` for `crm_app`/`crm_worker`. Never skip or weaken tests. Never log secrets, tokens, PII, or message text. No new dependencies without explicit approval.
4. Failing tests first: unit, API, cross-tenant, role-scope.
5. Max 1 Alembic migration per step; `alembic heads` must show exactly 1 head.
6. Run `ruff` and `pytest`. Keep changed files focused.
7. PR named after step number; mark 🔒 if security-sensitive.

---

## Environment & Tooling
- OS: Windows
- Branch: `tsnm-hm`
- Backend Venv: `backend\backstore\Scripts\python.exe`
- Alembic Head: `9b3c4d5e6f7a` (Linear single head)
- Ports: Backend 8000, Frontend 3000

--- I have short time for showing the project as a showcase so i will show the whole project in my local host platfrom and the ones marked (postponed) will be done later list them in table marked (postponed) when all the 25th step is done

## Phase / Step Progress Tracker

| # | Step | Tier | 🔒 | Status | Notes |
|---|------|------|----|--------|-------|
| 1 | One Alembic head + CI check | 🔴 | | ✅ Done | Linear heads test, CI job added |
| 2 | DB roles and RLS audit | 🔴 | 🔒 | ✅ Done | `6bc6d10a90da` migration, role assertions, RLS tests |
| 3 | LLM adapter & AI worker | 🔴 | 🔒 | ✅ Done | `AnthropicAdapter`, `FakeAnalyzer`, worker process |
| 3b| AI eval set & report | 🟠 | | ✅ Done | 60 records, confusion matrix, `docs/AI_EVAL.md` |
| 4 | Users API & invitations audit | 🔴 | 🔒 | ✅ Done | Extra fields forbid, timezone Asia/Dhaka, token revocation on deactivation |
| 5 | Tasks CRUD router harden | 🟠 | 🔒 | ✅ Done | `/due-follow-ups` route ordering, idempotency, version conflict 409, timeline entry |
| 6 | Pause-on-reply, opt-out cancel | 🟠 | 🔒 | ✅ Done | Inbound reply pauses follow-ups, opt-out cancels, 409 on send if paused/cancelled/won/lost, 403 on rep approve |
| 7 | Same-origin connectivity & api.ts fix | 🟠 | 🔒 | ✅ Done | Unified relative client, in-memory tokenStore, session refresh on mount, proxy rewrites |
| 8 | Outbox fan-out & dispatcher | 🟠 | 🔒 | ✅ Done | Fan-out with distinct UUIDs, HMAC-SHA256 signing, PII sanitize, task.due cancellation |
| 9 | Internal automation & quiet hours | 🟠 | 🔒 | ✅ Done | Reconciled §14, quiet hours 202 reschedule, tenant_settings RLS, settings API |
| 10 | n8n compose setup | 🟠 | | ✅ Done | crm_net / automation_net network isolation, n8n_db pinned postgres 16.8, n8n 1.76.3, healthcheck |
| 11 | Workflow A: new lead | 🟠 | | ✅ Done | Golden vector, sign-and-call sub-workflow, workflow_a_new_lead.json, simulate_n8n.py, simulate_whatsapp.py |
| 12 | Workflow B: follow-up | 🟠 | | ✅ Done | Webhook task.due, idempotent message dispatch, quiet hours reschedule, outcome recording to task result, simulate_n8n & unit tests |
| 13 | Workflow C: customer reply | 🟠 | | ✅ Done | Webhook lead.replied, HMAC check, GET lead context, rep notification, POST assess intent re-run, simulate_n8n Workflow C & unit tests |
| 14 | Error workflow & requeue | 🟠 | | ✅ Done | workflow_error_handler.json, requeue_dead.py, ARCHITECTURE.md retry/dead spec, CI workflow security grep, POST /internal/v1/automation/errors |
| 15 | Dashboard API | 🟡 | 🔒 | ✅ Done | Scope-based summary API (me/team/company), RBAC pre-query validation, date range validation, pipeline, KPIs, reps performance, health metrics |
| 16 | Frontend foundations | 🟡 | | ✅ Done | AuthProvider session bootstrap, useCurrentUser with tenant timezone, role-aware navigation guards, 403 page, shared components (DataTable, EmptyState, ErrorBanner, LoadingSpinner, parseApiError) |
| 17 | Tasks page & approval queue | 🟡 | | ✅ Done | Tabs: Today, Overdue, Upcoming, Approval queue, Completed, All; tenant timezone day bucketing; optimistic lock 409 inline retry; Paused badge + Resume action; manager/admin approval actions; TanStack Query |
| 17b| Lead detail AI card & CSV upload | 🟡 | | ✅ Done | AI card with sentiment & manager review UX; activity timeline via GET /leads/{id}/timeline; lost status & reasons; CSV upload with dry run & error breakdown; bulk assign omitted |
| 18 | Conversations inbox & reply box | 🟡 | | ✅ Done | Left panel ordered by last_message_at desc; thread in chronological order; POST /messages; 24h compliance window from last_inbound_at; approved WhatsApp templates; opt-out badge & disable; lead profile link |
| 19 | Dashboard page | 🟡 | | ✅ Done | Scope-driven views (me, team, company) via Recharts; role-filtered scope selector; period presets (7d, 30d, 90d); 403 access denied card; pipeline funnel chart, reps leaderboard, automation/integration health |
| 20 | Settings: users, teams, automation | 🟡 | | ✅ Done | Admin-only settings page (/settings); Users tab with member listing, role promotion/demotion, invite modal, deactivation confirmation modal; Teams tab with team creation and inline renaming; Automation tab with timezone and quiet hours (HH:MM); 0 TS/ESLint errors, 30/30 unit tests passed |
| 21 | Integrations settings & notification bell | 🟡 | | ✅ Done | Migration 8f2b3c4d5e6f for notifications.read_at with GRANT UPDATE; User routes GET /api/v1/notifications, PATCH /api/v1/notifications/{id}/read, POST /mark-all-read; GET /api/v1/lead-forms/primary; NotificationBell component with 60s polling & mark-read; Integrations page (/integrations) with write-only credentials, WhatsApp/Meta connect & disconnect modals, copy public lead form embed code; 0 TS/ESLint errors, 30/30 unit tests passed |
| 22-23 | Production deployment & Caddy | 🟢 | 🔒 | ⏳ Postponed | Reverse proxy, TLS, CSP nonce, and prod compose (local showcase active) |
| 24 | Hardening | 🟢 | 🔒 | ⏳ Postponed | Production security scan & log scrubbing verification |
| 25 | Platform admin API | 🟢 | 🔒 | ✅ Done | Migration 9b3c4d5e6f7a (SECURITY DEFINER functions platform_list_tenants, platform_get_tenant, platform_suspend_tenant, platform_get_health); require_platform_admin with mandatory MFA enforcement ('totp' in amr); GET /tenants, GET /tenants/{id}, POST /tenants/{id}/suspend, PATCH /tenants/{id}, GET /health; cross-tenant audit logging with tenant_id=None; 403 forbidden for company admins/managers/reps; 403 tenant_suspended for suspended tenant users; 10/10 unit tests passed |
| 26 | Backup, restore, export | 🟢 | | ⏳ Postponed | Offsite encrypted pg_dump & retention verification |
| 27 | Playwright E2E | 🟢 | | ⏳ Postponed | Browser E2E suite |
| 28 | Checklist, docs & demo | 🟢 | | ⏳ Postponed | Final audit checklist & demo walk-through scripts |

---

## Showcase Ready State (Steps 1–21 & 25 Complete)
All primary application foundations, security policies, AI workflows, CRM core pipelines, dashboard analytics, tenant settings, and platform administrative APIs are implemented and verified.
- **Backend**: FastAPI with RLS on all tenant tables, single Alembic head (`9b3c4d5e6f7a`), strictly validated API endpoints.
- **Frontend**: Next.js App Router with role-aware navigation, in-memory tokens, TanStack Query hooks, Recharts analytics, and write-only channel integrations.
- **Postponed Steps**: Steps 22–24 and 26–28 are catalogued above for production deployment and release hardening.
