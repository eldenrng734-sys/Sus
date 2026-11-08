# Product Requirements Document

> **Status:** product specification / target requirements for the 15-day MVP. The repository is an early backend scaffold, **not a working CRM or production-ready SaaS**.
> **Target** means a required product capability; **in scope** means planned for this MVP build; **post-MVP** means deferred. Nothing in this document is evidence that a capability is implemented unless explicitly identified as current.
> Unless explicitly identified as current, the requirements below describe the **target product**.

This document defines what we build, for whom, and the acceptance criteria the team must meet. It does not replace the detailed architecture, API, schema, or security specifications.

| Reference | Authority |
| --- | --- |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Component boundaries, data flow, tenancy, deployment, and verification gates |
| [SECURITY.md](./SECURITY.md) | Mandatory controls and security approval; security requirements take precedence |
| [API_CONTRACT.md](./API_CONTRACT.md) | Target routes, headers, payload conventions, and service authentication |
| [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) | Target tables, constraints, RLS policies, and database roles |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Contribution, review, and definition-of-done rules |
| [guide.txt](./guide.txt) | Delivery timeline, team plan, and glossary |

Product requirements are the authority for scope. Security requirements (SECURITY.md) always win if they appear to conflict. Resolve documentation conflicts explicitly in review; do not silently weaken security or treat a proposed design as approved.

## Contents

1. [Product overview](#1-product-overview)
2. [Product goals](#2-product-goals)
3. [Target users](#3-target-users)
4. [Core problem statement](#4-core-problem-statement)
5. [MVP scope](#5-mvp-scope)
6. [Key principles](#6-key-principles)
7. [User stories](#7-user-stories)
8. [Functional requirements](#8-functional-requirements)
9. [Non-functional requirements](#9-non-functional-requirements)
10. [UX and product behavior expectations](#10-ux-and-product-behavior-expectations)
11. [Implementation baseline](#11-implementation-baseline)
12. [Requirements-to-module traceability](#12-requirements-to-module-traceability)
13. [Definition of done and acceptance criteria](#13-definition-of-done-and-acceptance-criteria)
14. [Key constraints and assumptions](#14-key-constraints-and-assumptions)
15. [Risks and mitigations](#15-risks-and-mitigations)
16. [Prioritized backlog (MVP)](#16-prioritized-backlog-mvp)
17. [Open decisions](#17-open-decisions)
18. [Cross-document alignment](#18-cross-document-alignment)
19. [Product summary](#19-product-summary)

---

## 1. Product overview

This project delivers an AI-powered, multi-tenant SaaS CRM for sales teams. The product helps companies organize leads, track follow-up tasks, monitor conversations, and use AI to classify intent and prioritize outreach. The system is built as a secure, shared-platform application where each company's data remains isolated from every other company.

The product is designed for a 15-day MVP build by a 5-person team and should prioritize secure tenant isolation, role-based permissions, lead capture, AI-assisted summarization and scoring, task automation, and dashboards for sales roles.

### Current implementation baseline

| Area | What exists now | What must not be assumed |
| --- | --- | --- |
| HTTP application | [`backend/app/main.py`](./backend/app/main.py): FastAPI `0.1.0`, `GET /health` returning `{"status":"ok"}`, default OpenAPI/docs | No CRM routers, auth, middleware, readiness, or database-connectivity checks |
| Configuration | [`backend/app/core/config.py`](./backend/app/core/config.py): `app_env`, `database_url`, `.env` loading | Settings are not wired into the application; production validation is absent |
| Persistence definitions | SQLAlchemy base/mixins, naming conventions, registry; five models (`tenants`, `users`, `tenant_memberships`, `teams`, `audit_logs`) | Model definitions do not create a database; no engine/session dependency or executable migration chain exists |
| Security | Some model CHECK, unique, and composite-FK constraints | No implemented authentication, RBAC, RLS policies, tenant resolver, MFA, or encrypted integration storage |
| Infrastructure | Development Compose declares PostgreSQL 16 and a backend; Dockerfile uses Python 3.12 | No frontend, worker, n8n, or reverse-proxy service is configured |
| Tests and CI | One health API test; CI declares Ruff lint, Ruff format check, and pytest on Python 3.12 | No database, cross-tenant, provider, AI, workflow, or browser test coverage yet |
| Other components | Empty frontend, n8n workflow, and reverse-proxy directories | No UI application, workflow exports, or TLS routing implementation |

The only current executable product evidence is the `/health` test asserting `200 OK` with `{"status":"ok"}`. Every requirement below must be proven with source, migrations, and tests before it counts as shipped.
## 2. Product goals

### Primary business goals

- Help sales teams capture, organize, and follow up on leads faster.
- Reduce manual lead triage through AI classification and intent detection.
- Give managers and company admins visibility into performance without exposing unrelated tenant data.
- Support multi-company operations without cross-tenant data leakage.
- Automate routine follow-up reminders and response tracking via n8n.

### Strategic goals

- Build a secure foundation before expanding into integrations or advanced AI features.
- Keep the platform modular so multiple developers can work in parallel with limited merge conflicts.
- Keep lead capture and automation centralized through one validated pipeline.
- Use backend-enforced permissions and PostgreSQL RLS as the primary control layer.

---

## 3. Target users

### Sales representative (`rep`)

- Views assigned leads and opportunities.
- Updates lead status and records notes.
- Responds to conversations and completes tasks.
- Works from a focused, action-oriented dashboard.

### Sales manager (`manager`)

- Reviews team pipeline health and team performance.
- Assigns and reassigns leads within their team.
- Understands conversion, follow-up completion, and rep productivity.
- Sees only team-level data within the tenant.

### Company admin (`admin`)

- Manages company users, roles, integrations, and automation settings.
- Oversees all teams and lead activity in their company.
- Configures connected services and safety settings.

### Platform admin (`platform_admin`, our team)

- Manages tenant-level platform operations and support.
- Has platform access separate from company admins.
- Must not gain cross-company visibility through normal company admin paths.

Role values must stay `rep`, `manager`, `admin`, matching the backend `tenant_memberships` CHECK constraint and `DATABASE_SCHEMA.md`. Do not support both old and new role vocabularies.

---

## 4. Core problem statement

Sales teams often struggle with scattered lead sources, delayed follow-up, and weak prioritization. Without a unified CRM, they miss opportunities and lose visibility into customer intent.

This product addresses that by combining:

- a central lead capture pipeline
- AI-driven classification and scoring
- task and follow-up automation
- role-aware dashboards and permissions
- strict multi-tenant security boundaries

---

## 5. MVP scope

### In scope (must ship)

- Company signup and invite-based onboarding
- Roles: Sales rep, Sales manager, Company admin, Platform admin
- Multi-tenant data isolation with PostgreSQL RLS
- Lead capture from website forms, manual entry, CSV import, and WhatsApp
- Meta Lead Ads / Messenger in test mode
- Lead list, detail, status pipeline, notes, assignment, and tasks
- AI classification, intent detection, scoring, summary, and sentiment
- n8n workflows for new-lead processing and follow-up reminders
- Role-based dashboards for reps, managers, and admins
- Docker-based deployment and backup/security checks

### Out of scope for the MVP

- Instagram and forum integrations
- HubSpot / Salesforce sync (post-MVP)
- Email channel (post-MVP)
- Billing, subscriptions, and quotas (post-MVP)
- AI agent workflows beyond advisory scoring (post-MVP)
- Separate DB-per-tenant enterprise model (post-MVP)
- Kubernetes, vector databases, Redis, or n8n queue mode (not MVP)
- Tracking endpoint and round-robin assignment (cuttable if time runs short)

**Cut order if behind schedule:** Meta Lead Ads/Messenger → tracking endpoint and round-robin → extra dashboard widgets → summary and sentiment. Never cut RLS, auth, webhook signatures, MFA for admins, encrypted credentials, or cross-tenant tests.

---

## 6. Key principles

1. **Tenant isolation first:** secure tenant isolation → CRM core → AI → automation. If isolation is wrong, no AI or dashboard makes this a safe SaaS product.
2. **The backend is the authority:** business logic and permission checks happen in FastAPI services.
3. **The AI is advisory only:** it provides scores and recommendations; the application decides actions.
4. **Automation is safe and auditable:** automation calls the API, never the database directly.
5. **Lead capture is unified:** all sources enter through the same validation, deduplication, and processing pipeline.
6. **Security is non-negotiable:** do not skip or weaken any security step to save time. Cut features instead.

---

## 7. User stories

### Tenant onboarding

- As a new business owner, I want to create a company and admin account so I can set up my sales workspace.
- As an invited user, I want to accept an invitation and join my company so I can access the correct workspace.
- As a company admin, I want to invite and manage users so the team can work in the right roles.

### Lead management

- As a sales rep, I want to view my assigned leads so I can prioritize follow-up.
- As a manager, I want to see team leads and their pipeline state so I can monitor progress.
- As a company admin, I want to manage lead assignment and team structure so sales operations work correctly.
- As a user, I want to add notes, tasks, and status updates so the lead history is complete.

### Lead capture

- As a website visitor or customer, I want to submit my details through a form so a sales rep can follow up.
- As a sales team, I want CSV import and manual entry to behave like the same lead pipeline so we have a consistent process.
- As an ops team, I want duplicate-webhook protection so the same lead is not created twice.

### AI and automation

- As a sales rep, I want AI to score and classify a new lead so I know how urgent and valuable it is.
- As a manager, I want AI summaries and sentiment so I can understand a lead quickly.
- As a team, I want reminders and follow-ups to be scheduled automatically so no lead is missed.
- As a user, I want follow-up tasks to pause when a lead replies or opts out so the system respects consent.

### Dashboards and reporting

- As a sales rep, I want my dashboard to show high-priority leads and due follow-ups.
- As a manager, I want team conversion, source performance, and pipeline metrics.
- As a company admin, I want to view enterprise-level metrics and integration health.

---

## 8. Functional requirements

### 8.1 Authentication and access

- Users must be able to sign up, log in, log out, reset password, and verify email.
- Access tokens must be short-lived and refresh tokens must rotate.
- Passwords must be stored using Argon2id.
- MFA must be supported for admins.
- Invite-only user onboarding must be enforced.
- User deactivation must revoke active access immediately.

### 8.2 Multi-tenant access and authorization

- All tenant-owned data must include `tenant_id`.
- Every database query for tenant data must be enforced by PostgreSQL RLS.
- The backend must verify membership and role on every request.
- Role-based rules must be enforced server-side.
- Managers must only see data within their team or assigned scope.
- Company admins must see all company data but not platform-admin data.
- Platform admin access must be logically separate from company admin access.

### 8.3 Lead lifecycle

- Users must be able to create, update, search, and assign leads.
- Leads must include source, status, priority, score, owner, and lead history.
- Each lead must be associated with a single tenant.
- The system must support status changes across the CRM lifecycle.
- Leads must have notes, tasks, and timeline events.
- Duplicate detection must happen before lead creation.

### 8.4 Lead capture and integrations

- Public form submissions must be accepted through a controlled endpoint.
- Webhooks must be validated using provider signatures.
- Duplicate webhook events must be ignored via idempotency logic.
- CSV and manual import must go through the same lead creation pipeline.
- WhatsApp and Meta inbound events must be processed through the same validation and dedup rules.
- Integration credentials must be encrypted before storage.

### 8.5 AI requirements

- New leads and messages may trigger AI assessment.
- The model must return structured JSON that is validated before use.
- Low-confidence results must be flagged for human review.
- AI output must include at least: category, intent, priority, lead_score, sentiment, recommended action, and confidence.
- AI responses must be stored with the model and prompt version.
- AI must never directly change permissions, data, or messages without backend enforcement.

### 8.6 Automation and follow-up

- n8n must orchestrate reminder and follow-up tasks.
- Follow-up actions must check consent, opt-out status, quiet hours, and lead state.
- Follow-up tasks must stop when the lead replies or opts out.
- Internal n8n calls must use authenticated service-to-service access.
- Retries and triggers must be idempotent.

### 8.7 Dashboard and reporting

- Sales rep dashboard: new leads, priority queue, due follow-ups, overdue tasks, recent conversations.
- Manager dashboard: team performance, lead sources, average response time, follow-up completion.
- Company admin dashboard: overall company performance, team comparison, integration status, automation health.
- Dashboard queries must be filtered by tenant and role server-side.

---

## 9. Non-functional requirements

### 9.1 Security

- Multi-tenant isolation is a core product requirement; no tenant may access another tenant's data.
- Auth, tenant context, RBAC, and webhook validation require a security approver review.
- Webhook signatures must be validated and invalid requests rejected.
- Integration secrets must never be stored in plaintext or returned in API responses.
- Logs must not contain passwords, tokens, or unnecessary message content.
- Cross-tenant regression tests must exist and pass before release.

### 9.2 Reliability

- The system must gracefully handle duplicate webhook submissions.
- Retryable automation should be safe and idempotent.
- Integration failures must be logged, tracked, and visible to the admin.
- Backup and restore procedures must be tested before production rollout.

### 9.3 Performance

- The system should handle lead list, inbox, and dashboard queries within reasonable response times for an MVP workload.
- Indexes must be designed around tenant-scoped queries and common dashboards.
- Large lead and message tables must be queryable without leaking data across tenants.

### 9.4 Privacy and compliance

- Collect only necessary PII and respect privacy and consent rules.
- Public forms must collect consent where required.
- Attachments must live in private storage, not public URLs.
- Data retention and secure deletion paths must be defined.

---

## 10. UX and product behavior expectations

- The app must feel like a fast operational CRM, not a generic dashboard.
- A rep should be able to understand the lead state, contact history, and next action without extra clicks.
- Every role should see a tailored dashboard and a narrow set of actions.

---

## 11. Implementation baseline

The repository currently implements only the items marked **current** below; all other functional requirements are target requirements awaiting implementation, migrations, and tests.

| Requirement area | Current state | Target state |
| --- | --- | --- |
| Authentication | Not implemented | Signup, login, refresh rotation, MFA for admins |
| Tenant isolation | Models defined only; no RLS policies | PostgreSQL RLS + server-side membership verification |
| Lead lifecycle | Not implemented | CRUD, pipeline, assignment, notes, tasks, timeline |
| Lead capture | Not implemented | Website form, manual, CSV, WhatsApp/Meta with signature validation and dedup |
| AI | Not implemented | Structured validation, fallback, human review at confidence < 0.6 |
| Automation | Not implemented | n8n orchestrates via signed internal API; no direct DB access |
| Dashboards | Frontend placeholder only | Role-scoped rep/manager/admin dashboards |
| Deployment | Dev Compose + backend Dockerfile | TLS proxy, separate DB roles, one-off migrations, backups |
| Tests | One health API test | Unit, API, PostgreSQL RLS, cross-tenant, workflow, browser |

Do not expose tenant CRUD endpoints before their RLS policies, non-owner grants, and cross-tenant tests land together.

---

## 12. Requirements-to-module traceability

Maps each requirement area to the backend module expected to own it. Empty packages must be populated when the feature is implemented.

| Requirement area | Owning module(s) | Notes |
| --- | --- | --- |
| Authentication and access | `auth`, `tenants`, `users` | Login, sessions, invitations, MFA |
| Multi-tenant access and authorization | `tenants`, `users`, core | RLS context, membership verification, RBAC |
| Lead lifecycle | `leads`, `tasks` | CRUD, pipeline, assignment, notes, timeline |
| Lead capture and integrations | `integrations`, `leads` | Forms, webhooks, CSV, dedup, credentials |
| AI requirements | `ai` | Structured LLM adapter, validation, fallback |
| Automation and follow-up | `tasks`, backend worker, n8n | Internal API, idempotent sends, consent checks |
| Dashboard and reporting | `dashboard`, frontend | Read-only tenant/role-scoped aggregates |

Modules talk to each other through `service.py` interfaces, not each other's models. Routers never query the database directly.

---

## 13. Definition of done and acceptance criteria

### Definition of done per feature

- Code is merged into `develop`
- Unit or API tests are written and passing
- Tenant isolation is respected; no query is executed without tenant context
- Review is complete by the ring reviewer
- If `★` or touches auth, RLS, permissions, or webhooks, the required security approval is complete
- The endpoint is visible in `/docs` (OpenAPI)
- The feature is demonstrated in the end-of-day integration session

### Core acceptance criteria

- A business can sign up and create a company.
- An invited employee can join and authenticate as a sales user.
- A rep can create and update a lead.
- A manager can see team leads without seeing another company's data.
- A company admin can manage roles and integrations for their tenant.
- A webhook with a bad signature is rejected.
- A duplicate webhook does not create duplicate leads or messages.
- AI assigns lead intent and score with validation and fallback behavior.
- Follow-up actions pause on reply or opt-out.
- Dashboard data respects tenant and role permissions.

> **Current executable evidence:** only `/health` returns `200 OK` / `{"status":"ok"}`. None of the acceptance criteria above are implemented yet; each must be proven with source, migrations, and tests before release.

---

## 14. Key constraints and assumptions

- Product builds in a shared PostgreSQL database with tenant-scoped RLS.
- Database and API development must be consistent with the schema blueprint.
- Security requirements are non-negotiable and may require cutting features.
- AI is not autonomous; it is a decision-support layer, not a system of record.
- n8n is a workflow automation layer, not a privileged database client.
- The MVP assumes test-mode Meta and WhatsApp integration and not full production channel onboarding.

---

## 15. Risks and mitigations

### Risk: cross-tenant leakage
Mitigation: RLS, tenant-aware DB policies, server-side authorization, cross-tenant security tests.

### Risk: duplicate lead creation
Mitigation: capture pipeline validation, dedup keys, webhook event storage, unique indexes.

### Risk: insecure automation
Mitigation: service authentication, minimum-scope internal routes, idempotency keys, safe retry logic.

### Risk: AI misuse
Mitigation: structured output validation, confidence thresholds, human review, and deterministic backend rules.

### Risk: integration compromise
Mitigation: encrypted credentials, rotation, restricted scopes, and minimal privilege access.

---

## 16. Prioritized backlog (MVP)

### P0 — Must ship

- Tenant isolation and core auth
- Role-based access and company membership
- Lead CRUD, pipeline, assignment, notes/tasks
- Capture pipeline and deduplication
- AI classification and intent scoring
- Follow-up automation and reply handling
- Rep/manager/admin dashboards
- Security tests, backups, and deployment readiness

### P1 — Important but can be cut if necessary

- Meta Lead Ads / Messenger test mode
- Additional dashboard widgets
- Enhanced summary/sentiment features
- More advanced reporting analytics

### P2 — Post-MVP

- HubSpot / Salesforce sync
- Billing and subscriptions
- AI agent workflows beyond advisory scoring
- Separate DB-per-tenant enterprise model

---

## 17. Open decisions

The following product scope decisions are not fully resolved and need agreement before implementation:

1. **Contact conversion:** whether lead-to-contact conversion ships in the MVP or remains deferred.
2. **Support access:** whether temporary, approved, audited platform support access to tenant data ships in the MVP.
3. **Auth token storage:** refresh token in HttpOnly cookie + CSRF vs. bearer token; confirmed in `API_CONTRACT.md` but pending security approver sign-off.
4. **AI assessment ownership/job uniqueness:** capture service owns initial assessment; the version/job uniqueness key to prevent stale work overwriting newer results needs review.
5. **Retention durations:** final legal/product policy for messages, assessments, audit logs, and backups.
6. **Multi-team managers:** the membership model supports one optional team per membership; multi-team manager scope requires a reviewed schema change.
7. **Attachment scanning:** file-type allow-list, malware scanning, and size limits before enabling uploads.

---

## 18. Cross-document alignment

| Topic | Authoritative doc | This document's role |
| --- | --- | --- |
| Product scope and priorities | `PRODUCT_REQUIREMENTS.md` | Defines what we build and why |
| Component boundaries and data flow | `ARCHITECTURE.md` | Explains how parts fit together |
| Security rules and approval | `SECURITY.md` | Mandatory controls; takes precedence |
| Routes, headers, payloads | `API_CONTRACT.md` | Target API contract |
| Tables, RLS, constraints | `DATABASE_SCHEMA.md` | Target database schema |
| Team workflow and reviews | `CONTRIBUTING.md` | How changes are made and reviewed |

If this document and a sibling disagree, fix both in the same PR. Changes touching auth, tenancy/RLS, permissions, or webhooks require the ring reviewer **and** security approver: Dev 1, or Dev 4 when Dev 1 authors the change. Ensure two distinct people approve.

---

## 19. Product summary

The AI Sales Assistant CRM is a secure, modern sales platform for multi-company teams. It unifies lead capture, AI-based scoring and intent detection, task automation, and dashboard reporting in a single tenant-isolated SaaS application.

The MVP is intentionally scoped to the most valuable core flows: secure onboarding, lead management, AI-assisted prioritization, follow-up automation, and role-aware visibility. The product is designed to be secure and production-ready from the start, with a strong emphasis on tenant isolation, operational safety, and quality delivery under a tight 15-day schedule.

