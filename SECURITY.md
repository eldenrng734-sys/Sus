# Security Policy

Security for the **AI Sales Assistant CRM** (multi-tenant SaaS). This document is the project security reference and should be read together with [guide.txt](./guide.txt) and [CONTRIBUTING.md](./CONTRIBUTING.md).

> 🔒 **The explanations in this project are simple, but the security requirements are not.**
> Do not skip or weaken any security step to save time. **Cut features instead.**

**Priority order of the whole product:** secure tenant isolation → CRM core → AI → automation. If isolation is wrong, no AI or dashboard makes this a safe SaaS product.

**Never cut:** RLS, auth, webhook signatures, MFA, encrypted credentials and the cross-tenant tests.

---

## Table of contents

1. [Non-negotiables](#1-non-negotiables)
2. [Security review process](#2-security-review-process)
3. [Tenant isolation (RLS)](#3-tenant-isolation-rls)
4. [Authentication](#4-authentication)
5. [Authorization & roles (RBAC)](#5-authorization--roles-rbac)
6. [Webhooks & lead capture](#6-webhooks--lead-capture)
7. [Integration credentials & secrets](#7-integration-credentials--secrets)
8. [n8n automation security](#8-n8n-automation-security)
9. [AI / LLM security](#9-ai--llm-security)
10. [Web application hardening](#10-web-application-hardening)
11. [Data protection & privacy](#11-data-protection--privacy)
12. [Logging, auditing & PII](#12-logging-auditing--pii)
13. [Infrastructure & deployment](#13-infrastructure--deployment)
14. [Threat model summary](#14-threat-model-summary)
15. [Security testing](#15-security-testing)
16. [Production-readiness checklist](#16-production-readiness-checklist)
17. [Open decisions & recommended additions](#17-open-decisions--recommended-additions)
18. [Reporting a vulnerability](#18-reporting-a-vulnerability)

---

## 1. Non-negotiables

These must **never be cut**, even if the project falls behind schedule:

- Row-Level Security (RLS) on all tenant tables
- Authentication (Argon2id, short-lived tokens, refresh rotation)
- Webhook signature validation
- MFA for admins
- Encrypted integration credentials
- Cross-tenant tests

If time runs short, cut features in this order instead: Meta Lead Ads/Messenger → tracking endpoint and round-robin → extra dashboard widgets → summary and sentiment.

---

## 2. Security review process

Any pull request that touches **auth, tenant context / RLS, permissions (RBAC) or webhooks** needs **two approvals**:

1. The ring reviewer (Dev 1 → Dev 2 → Dev 3 → Dev 4 → Dev 5 → Dev 1), **and**
2. The security approver: **Dev 1**, or **Dev 4** if Dev 1 is the author.

Additional rules:

- ★ (hard) tasks always get two reviewers.
- No exceptions to the security approver rule.
- Mob the first hour on Days 3 (RLS) and 7 (webhooks): all 5 developers on one screen, then split.
- Try to get a senior reviewer for about an hour on Days 3, 7 and 14.
- Every PR needs green CI (lint + tests).
- Definition of Done includes: *"Tenant isolation respected (no query without tenant context)."*

> ⚠️ **Note:** the ring reviewer for Dev 2's PRs is Dev 1, which is also the default security approver. For those PRs, name a distinct second approver so two different people sign off.

---

## 3. Tenant isolation (RLS)

**The most important security decision in the project.** All companies share one database. Every tenant-owned row has a `tenant_id`, and PostgreSQL itself (RLS) hides other companies' rows, so even if a developer forgets a filter in the code, Company B's data cannot leak to Company A.

### Rules

- One PostgreSQL database, shared tables, `tenant_id` on **every** tenant-owned row, enforced by RLS.
- **Never trust a `tenant_id` sent by the browser.** The backend verifies the user's membership and role on every request.
- RLS enabled with no matching policy means **access is denied by default**.
- Use **composite foreign keys including `tenant_id`**, so Company A's lead cannot link to Company B's user.
- The app DB role must **not** be a superuser and must **not** have `BYPASSRLS`.
- Use `FORCE ROW LEVEL SECURITY` so table owners are covered too.
- Apply the same policy to **every** tenant-owned table, not only `leads`.
- Isolation is built into the foundation on Day 3, not added later.

### Policy template

```sql
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads FORCE ROW LEVEL SECURITY;

CREATE POLICY leads_tenant_isolation ON leads
USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

### Setting the tenant per request

The backend sets the verified tenant **per transaction** (transaction-local, so it is safe with connection pooling):

```sql
SELECT set_config('app.tenant_id', 'verified-tenant-uuid', true);
```

The third argument `true` makes the setting transaction-local. Never use a session-level setting with pooled connections.

### Where RLS stops

RLS isolates **companies**. It does not separate a rep from a manager inside one company. Rep / manager / admin scoping (own leads vs team leads vs all leads) is enforced in application code and must be covered by role-scope tests (see [Security testing](#15-security-testing)).

---

## 4. Authentication

| Control | Requirement |
| --- | --- |
| Password storage | **Argon2id**. The real password is never stored |
| Access tokens | Short-lived JWT |
| Refresh tokens | Rotation on every use, plus logout and revocation |
| Email verification | Required |
| Password reset | Single-use, short-lived tokens |
| MFA | TOTP MFA for **admins** |
| Login protection | Rate limits on login, plus audit logging |
| Joining a company | **Invite-only**. Users join via invitation, accept, deactivate and role change are all audited |

Rules:

- Signup creates a tenant and its first admin. Everyone else joins by invitation.
- Deactivated users lose access immediately; revoke their refresh tokens.
- Reset and invitation tokens must be single-use and expire.
- Security-relevant events (login, failed login, password reset, role change, deactivation) go to `audit_logs`.

---

## 5. Authorization & roles (RBAC)

| Role | Can do |
| --- | --- |
| Sales representative | View assigned leads, update status, read conversations, add notes, complete tasks, approve permitted follow-ups |
| Sales manager | View team leads, assign leads, monitor reps, review performance, manage team tasks |
| Company admin | Manage company users, roles, integrations, lead and automation settings, all company data |
| Platform admin (our team) | Manage tenants, platform health and support. **Separate from company admins** |

Rules:

- All permission checks happen **server-side**. Hiding a button in the UI is not a control.
- A company admin is **never** automatically a platform admin.
- Managers see their own team; company admins see all teams in their company.
- **Dashboard queries are filtered by tenant AND role on the server.** Changing API parameters (e.g. `scope=company`) must reveal nothing the role is not allowed to see.
- Support access to customer data must be **temporary, approved and logged**.

---

## 6. Webhooks & lead capture

Every channel (website form, WhatsApp, Meta, CSV, manual) goes through **one pipeline**, so each control is written once and tested once:

1. Endpoint receives webhook / form.
2. **Validate the request and check the provider signature** (proves it really came from WhatsApp/Meta, not an attacker).
3. **Skip if already processed** via `webhook_events` (providers sometimes send the same event twice).
4. Find or create the lead (dedupe by email / phone / external ID).
5. Store the interaction or message.
6. Request AI assessment.
7. Assign the lead and create a task if rules say so.

Rules:

- A request with a **bad or missing signature is rejected**, never processed.
- Duplicate webhooks must **not** create duplicate leads or messages. Enforce this with `webhook_events` plus the unique index on `(tenant_id, provider, provider_message_id)`.
- Meta webhooks may contain only an ID. Fetch the details through the official API rather than trusting the payload.
- Prefer official APIs over scraping.
- Disclose tracking and collect **consent** where required. Record `consent` and honor `opted_out`.
- Public form endpoints validate input and are rate limited.

---

## 7. Integration credentials & secrets

- Integration credentials (access tokens, API keys) are **encrypted** before storage.
- For each integration, store: owner, provider account ID, scopes, expiry and encrypted credentials.
- Credentials are **hidden from ordinary users**. APIs never return them in responses.
- Use a **KMS / secrets manager** for tokens and encryption keys. Keys are never committed to the repository.
- Use **separate DB credentials** for the app, worker, migrator and admin roles. n8n does not receive CRM database credentials; it uses its own database and the internal API.
- Rotate credentials, and support revoking an integration.
- Never log secrets, tokens or passwords.

---

## 8. n8n automation security

n8n never touches the database directly. It calls our API like any other client, and FastAPI still checks permissions, business rules and the tenant.

- The **n8n editor is private**. Customers never access or edit workflows.
- Run n8n in Docker on a **private network**.
- FastAPI ↔ n8n use **authenticated internal requests** (HMAC service auth) on `/internal/v1/automation/*`.
- Internal endpoints expose **minimum scope** only, and require **idempotency keys**.
- n8n has no unrestricted DB access and cannot retrieve unrestricted data from other tenants.
- Unique event IDs + idempotency keys prevent duplicate messages and tasks.
- Retries are safe and logged. Failed workflows are logged and retryable.
- Keep **PII out of execution logs** and set an execution data retention period.
- Keep the n8n **encryption key stable and stored outside the workflow database**.
- Keep n8n updated, and put it behind a TLS reverse proxy.
- **Licensing:** the Sustainable Use License can cover workflows we run for clients if they cannot access or change them. Customer-configurable workflows or white-labeling may need a commercial license. Confirm with n8n before launch.

Follow-up safety (Workflow B and C) must check consent, opt-out, quiet hours and lead status before sending, and **follow-ups stop when the lead replies or opts out**.

---

## 9. AI / LLM security

**The AI gives advice; our code makes the decisions.**

- The LLM only reads text and returns an opinion. It **never** modifies data, assigns permissions or sends messages directly.
- Output is **structured JSON**, validated with **Pydantic**. Invalid output falls back safely and is never trusted blindly.
- **Low confidence** (e.g. below 0.6) marks the item for **human review**.
- Deterministic rules decide tasks, priority and approvals.
- **Redact unnecessary PII** before sending text to the model.
- Store the **model and prompt version** with each assessment for traceability.
- Log cost and use timeouts and retries in the LLM client wrapper.
- Privacy: text sent to a hosted LLM leaves our server. Choose a provider with suitable data-retention and contract terms.

---

## 10. Web application hardening

| Risk | Protection |
| --- | --- |
| SQL injection | Parameterized queries / ORM only |
| CSRF | Secure cookies, CSRF tokens |
| XSS | Output escaping, Content Security Policy (CSP) |
| Unauthorized APIs | Server-side auth + permission checks on every endpoint |
| API abuse | Tenant-aware rate limits, input validation, quotas |
| Missing headers | Security headers set on all responses |
| Vulnerable dependencies | Dependency scan in CI |

Planned in the Day 14 hardening task: cookies, CSRF, CSP, security headers, rate limits and dependency scanning.

---

## 11. Data protection & privacy

- **TLS everywhere**, with TLS terminated at the reverse proxy (Caddy/Nginx).
- **Encryption at rest** for the database, files and backups.
- **No public database port.** The DB sits on a private network.
- **Encrypted, off-server backups.** Restores are tested, not assumed.
- Attachments live in **private** S3-compatible storage.
- A defined **retention, export and deletion policy**. Tenant data can be securely deleted, with an export/delete script for it.
- Collect only the PII we need (names, phone numbers, emails) and respect consent and opt-out.

---

## 12. Logging, auditing & PII

- `audit_logs` records security events and important user actions.
- Support access to customer data is **logged**.
- Logs must contain **no passwords, tokens or unnecessary message content**.
- n8n execution logs hold minimal PII and have a retention limit.
- Requests carry request IDs for traceability.
- A log / PII leak review is part of Day 14.

---

## 13. Infrastructure & deployment

- Production Docker Compose with TLS, a **private DB network** and secrets management.
- Firewall, OS and dependency updates, and monitoring.
- Separate credentials for the app, worker, migrator and admin database roles. n8n has no CRM database credentials.
- The app database role is a **non-superuser without `BYPASSRLS`**.
- Secrets come from the environment or secrets manager, never the repository.
- Staging mirrors production security settings and auto-deploys from `develop`.

---

## 14. Threat model summary

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

---

## 15. Security testing

Tests are written **first** where possible (cross-tenant fixtures with two tenants exist before the RLS policies they check).

| Test suite | Covers |
| --- | --- |
| Cross-tenant tests | Company A cannot read, update or delete Company B's data; the app role cannot bypass RLS |
| RBAC tests | Reps, managers, admins and platform admins can only do what their role allows |
| Dashboard scope tests | Changing `scope` or other parameters reveals nothing beyond the role |
| Webhook tests | Same webhook twice creates no duplicates; a bad signature is rejected |
| Automation tests | n8n failure and retry behavior; follow-ups stop on reply or opt-out |
| Log / PII review | No passwords, tokens or unnecessary message content in logs |
| E2E (Playwright) | Core user journeys end to end |
| Dependency scan | Known-vulnerable packages in CI |

---

## 16. Production-readiness checklist

All items must be **tested**, not just implemented.

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

## 17. Open decisions & recommended additions

> The items below are **not specified in the original project guide**. They are gaps worth deciding early, ideally in a short design session before Day 2.

### Open design decisions

- **Tenant resolution before RLS context exists.** Signup, login, inbound webhooks, n8n calls, background jobs and platform-admin access all run without a normal user tenant context. Use the pre-tenant lookup policies in [`DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md#13-row-level-security); use a reviewed `SECURITY DEFINER` fallback only if a policy cannot express the lookup.
- **Token storage.** Decided in [`API_CONTRACT.md`](./API_CONTRACT.md): refresh token in an `HttpOnly` cookie with rotation and CSRF protection; access token in frontend memory.
- **Who triggers AI assessment and assignment.** The FastAPI capture service owns the initial assessment and deterministic assignment; n8n Workflow A is orchestration-only and idempotent.
- **Second security approver.** Name a distinct second approver so Dev 1 is not a single point of failure.

### Recommended additional controls

- **Prompt injection:** treat customer messages as untrusted input to the LLM; keep the LLM output advisory only, with no tool access.
- **CSV import:** guard against formula injection (cells beginning with `=`, `+`, `-`, `@`) and validate file size and type.
- **Public form endpoint:** add spam protection (e.g. rate limits, honeypot or CAPTCHA).
- **Attachments:** scan and restrict file types and sizes; serve from private storage with signed URLs.
- **WhatsApp outbound:** messages outside the 24-hour window require pre-approved templates; enforce this in follow-up logic.
- **Platform admin & support access:** build tenant management and the logged, temporary, approved support-access flow, since the checklist tests for it.

---

## 18. Reporting a vulnerability

If you find a security issue, **do not open a public issue.** Report it privately to the project team using the security contact or the designated approver.

- **Security contact:** privately message the team lead, the assigned security approver (Dev 1, or Dev 4 if Dev 1 is the author), or a project security mailbox if one exists
- Include: what you found, steps to reproduce, the affected endpoint or module, and the tenant or role impacted
- Cross-tenant data exposure, authentication bypass and webhook spoofing are treated as **critical**
- If the issue affects tenant isolation, RLS, auth, or webhook validation, escalate it immediately and hold any release until it is fixed or mitigated

---

*This file is part of the project documentation set: [`README.md`](./README.md), [`PRODUCT_REQUIREMENTS.md`](./PRODUCT_REQUIREMENTS.md), [`ARCHITECTURE.md`](./ARCHITECTURE.md), [`DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md), [`API_CONTRACT.md`](./API_CONTRACT.md) and [`CONTRIBUTING.md`](./CONTRIBUTING.md).*