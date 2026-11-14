# API Contract

> **Status:** Target contract for the 15-day MVP. The current scaffold only implements `GET /health`; everything else in this file is the agreed contract to build against.
>
> **Normative sources:**
> - This file: conventions, headers, auth, tenancy, permissions, idempotency, and required behaviour.
> - OpenAPI at `/openapi.json` / `/docs`: exact request and response schemas.
>
> If this file and the generated OpenAPI disagree, fix both in the same PR. Any change touching auth, tenancy/RLS, permissions, or webhooks needs the security approver (Dev 1, or Dev 4 if Dev 1 is the author).

**Companion docs:** [`PRODUCT_REQUIREMENTS.md`](./PRODUCT_REQUIREMENTS.md) · [`ARCHITECTURE.md`](./ARCHITECTURE.md) · [`SECURITY.md`](./SECURITY.md) · [`DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md) · [`CONTRIBUTING.md`](./CONTRIBUTING.md) · [`guide.txt`](./guide.txt)

---

## Table of contents

1. [Contract rules](#1-contract-rules)
2. [Conventions](#2-conventions)
3. [Authentication and tenancy](#3-authentication-and-tenancy)
4. [Core resource shapes](#4-core-resource-shapes)
5. [Endpoint catalog](#5-endpoint-catalog)
6. [Auth endpoints](#6-auth-endpoints)
7. [Invitations, users and teams](#7-invitations-users-and-teams)
8. [Leads and assessments](#8-leads-and-assessments)
9. [Conversations and messages](#9-conversations-and-messages)
10. [Tasks and follow-ups](#10-tasks-and-follow-ups)
11. [Dashboard](#11-dashboard)
12. [Integrations, public forms and webhooks](#12-integrations-public-forms-and-webhooks)
13. [Audit and platform administration](#13-audit-and-platform-administration)
14. [Internal automation API (n8n)](#14-internal-automation-api-n8n)
15. [Health endpoints](#15-health-endpoints)
16. [Contract testing and change process](#16-contract-testing-and-change-process)

---

## 1. Contract rules

1. **The backend is the only authority.** The frontend, n8n, and the LLM never decide permissions, tenancy, or business rules.
2. **A `tenant_id` is never accepted from a request body or query string.** Tenant-scoped requests select the tenant with `X-Tenant-ID`, and the backend verifies an active membership on every request.
3. **Every tenant-owned response is scoped by tenant and role on the server.** Changing an ID or query parameter must never expose another tenant's data.
4. **All writes are idempotent where retries are possible.** Anything n8n, a webhook provider, or a browser can retry must be safe to retry.
5. **Errors are machine-readable and do not leak internals.** No stack traces, SQL, provider secrets, tokens, or raw tenant data in error messages.
6. **Additive changes stay in `v1`.** Breaking changes require a new major version (`/api/v2`) and a migration plan.
7. **UTC everywhere.** Timestamps are ISO 8601 with `Z`. Business-day calculations (quiet hours, dashboards) use the tenant's timezone, default `Asia/Dhaka`.
8. **Every endpoint is documented in OpenAPI and covered by at least one contract test.**

---

## 2. Conventions

### 2.1 Base URLs

| Environment | API base | Internal API |
| --- | --- | --- |
| Local | `http://localhost:8000/api/v1` | `http://localhost:8000/internal/v1` |
| Staging / production | `https://<host>/api/v1` | Private network only: `http://backend:8000/internal/v1` |

- Versioning is in the path: `/api/v1`.
- Health checks are unversioned: `/health`, `/health/ready`.
- The internal API is never exposed through the public reverse proxy.

### 2.2 Request and response format

- JSON, UTF-8, `Content-Type: application/json` except multipart uploads.
- IDs are UUID v4 strings.
- Enums are `lower_snake_case`.
- Single resource:

```json
{
  "data": {
    "id": "5f0c2c7e-5e0c-4f5a-9a5e-2f6a1f8b9c10"
  }
}
```

- List:

```json
{
  "data": [],
  "meta": {
    "next_cursor": null,
    "has_more": false
  }
}
```

- No response body for `204 No Content`.

### 2.3 Required and optional headers

| Header | Used on | Required | Notes |
| --- | --- | --- | --- |
| `Authorization: Bearer <access_token>` | All tenant API endpoints | Yes | Access token expires in 15 minutes |
| `X-Tenant-ID` | All tenant API endpoints | Yes | UUID; must match an active membership |
| `X-Request-ID` | All endpoints | No | UUID; generated if missing and echoed in the response |
| `Idempotency-Key` | Retryable `POST` endpoints | Yes where noted | 8–128 characters; UUID recommended |
| `X-CSRF-Token` | `POST /auth/refresh`, `POST /auth/logout` | Yes | Double-submit token from login/refresh |
| `Content-Type` | Requests with a body | Yes | `application/json` or `multipart/form-data` |
| `Accept-Language` | Optional | No | `en` or `bn`; affects user-facing messages, not data |
| `X-Service-Id` | Internal API | Yes | Must be an allow-listed service, e.g. `n8n` |
| `X-Timestamp` | Internal API and n8n events | Yes | Unix seconds; reject if skewed more than 300 seconds |
| `X-Signature` | Internal API and n8n events | Yes | `sha256=<hex>` HMAC over the canonical request |
| `X-Event-ID` | FastAPI → n8n events | Yes | Stable event UUID used for deduplication |

### 2.4 Error format

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      {
        "field": "email",
        "code": "invalid",
        "message": "Enter a valid email address"
      }
    ],
    "request_id": "f2a65c3e-6d47-4a4d-a7ee-2f4ad1e4d2b1"
  }
}
```

| HTTP | `error.code` | When |
| --- | --- | --- |
| 400 | `bad_request` | Malformed request, missing `X-Tenant-ID`, invalid cursor |
| 401 | `unauthorized` | Missing, expired, or invalid access token / refresh token |
| 403 | `email_not_verified` | Login before email verification |
| 403 | `forbidden` | Role, team, or tenant membership does not allow the action |
| 403 | `tenant_suspended` | Tenant is not active |
| 404 | `not_found` | Resource does not exist **in this tenant** |
| 409 | `conflict` | Duplicate lead, duplicate email, last-admin protection, invalid state transition |
| 409 | `version_conflict` | Stale `version` on an update |
| 409 | `idempotency_conflict` | Same idempotency key with a different request body |
| 413 | `payload_too_large` | JSON, CSV, or webhook body over the limit |
| 415 | `unsupported_media_type` | Wrong `Content-Type` |
| 422 | `validation_error` | Schema or business validation failed |
| 429 | `rate_limited` | Too many requests; includes `Retry-After` |
| 500 | `internal_error` | Unexpected server error; no internals in the message |
| 502 | `provider_error` | Upstream provider failed during an explicit provider action |
| 503 | `service_unavailable` | Dependency unavailable, e.g. database readiness check |

`404` is used instead of `403` for resources that exist in another tenant. Do not reveal that they exist.

### 2.5 Pagination, filtering and sorting

- List endpoints accept `limit` (default `25`, maximum `100`) and an opaque `cursor`.
- Responses return `meta.next_cursor` and `meta.has_more`. Clients must not parse the cursor.
- Cursors are stable enough for inserts because they encode `(created_at, id)` or the endpoint's declared sort key.
- `sort` is a whitelist per endpoint. Prefix `-` for descending: `sort=-created_at`.
- Unknown filters or sort fields return `422 validation_error`.
- Search uses `q`; it must be bounded (maximum 100 characters) and must not allow SQL wildcard injection.

### 2.6 Idempotency

Send `Idempotency-Key` on every retryable `POST`:

- `POST /api/v1/leads`
- `POST /api/v1/leads/import`
- `POST /api/v1/messages`
- `POST /api/v1/tasks`
- All mutating internal automation endpoints

Rules:

- Scope: `(tenant_id, caller_id, method, path, idempotency_key)`.
- TTL: 24 hours.
- Same key + same normalized body → replay the original status and body with `Idempotent-Replay: true`.
- Same key + different body → `409 idempotency_conflict`.
- Webhooks are deduplicated by the provider event ID, not by `Idempotency-Key`.

### 2.7 Concurrency

`Lead` and `Task` responses include an integer `version`. `PATCH` bodies must include the `version` the client last read:

```json
{
  "status": "qualified",
  "version": 3
}
```

If the row changed, return `409 version_conflict` and include the current resource in `error.details.current`. This prevents two reps overwriting each other.

> **Schema dependency:** `version` requires an integer `version` column on `leads` and `tasks` (or an equivalent optimistic-concurrency check based on `updated_at`). Add it in the first migration; do not rely on the browser's copy of `updated_at`.

### 2.8 Rate limits

Initial values; tune after load testing. Limits are per tenant and per user unless stated otherwise.

| Scope | Limit |
| --- | --- |
| Login | 5 attempts / minute / (email + IP) |
| Signup | 3 / hour / IP |
| Password reset request | 3 / 15 minutes / email |
| Public form submit | 20 / minute / IP and 100 / minute / form |
| Webhook receive | 300 / minute / provider |
| Authenticated API | 600 / minute / tenant/user |
| Internal automation API | 600 / minute / service |
| CSV import | 5 / hour / tenant |

Responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `Retry-After` on `429`.

### 2.9 CORS, CSRF and browser security

- The frontend calls the API same-origin through the reverse proxy.
- `Access-Control-Allow-Origin` is an explicit configured origin. Never `*` with credentials.
- `POST /auth/refresh` and `POST /auth/logout` use the refresh cookie and therefore require `X-CSRF-Token` plus an `Origin` check.
- Access tokens are kept in memory by the frontend. Do not store access or refresh tokens in `localStorage`.
- The public form endpoint may allow configured third-party origins, but it never uses cookies or credentials.
- TLS terminates at the reverse proxy. HSTS, `X-Content-Type-Options`, `Referrer-Policy`, and a frontend CSP are set there.
- Request body limits: JSON 1 MB, webhook 1 MB, CSV 10 MB, attachment 10 MB.

---

## 3. Authentication and tenancy

### 3.1 Token model

| Token | Lifetime | Transport | Storage |
| --- | --- | --- | --- |
| Access JWT | 15 minutes | `Authorization: Bearer` | Frontend memory only |
| Refresh token | 30 days | `HttpOnly` cookie | Hashed in database |
| CSRF token | 30 days | `X-CSRF-Token` header + readable cookie | Browser cookie / memory |

Access-token claims:

```json
{
  "sub": "user-uuid",
  "sid": "session-uuid",
  "jti": "token-uuid",
  "iat": 1762500000,
  "exp": 1762500900,
  "type": "access",
  "amr": ["pwd", "totp"]
}
```

The access token **does not carry role or tenant authorization**. The backend loads the active `tenant_memberships` row on every request. This makes role changes and deactivation take effect immediately. A session authenticates the **user**, not a tenant; the same session can select any active membership with `X-Tenant-ID`. If `refresh_tokens.tenant_id` is kept, treat it as the last-used tenant for UX only.

> **Open-decision resolution:** this contract chooses access token in memory + refresh token in an `HttpOnly` cookie, with CSRF protection. `SECURITY.md` lists token storage as an open decision; the security approver must confirm this before Day 2, and that document should then reference this section.

Refresh-token rules:

- Rotate on every successful refresh; the old token is single-use.
- Detect reuse of a rotated token and revoke the whole token family.
- Logout revokes the current session.
- Password reset, deactivation, role removal, and MFA reset revoke all of that user's sessions.
- Store only a hash of the refresh token, never the raw value.

### 3.2 Tenant selection and verification

For tenant API requests:

1. Read `X-Tenant-ID` (required, UUID).
2. Verify the authenticated user has an `is_active = true` membership in that tenant.
3. Verify the tenant status is `active`.
4. Set the transaction-local RLS context.
5. Apply role/team scoping.

Missing header → `400 bad_request`. Invalid tenant or no membership → `403 forbidden`. Do not return tenant data before these checks.

Tenant resolution by endpoint type:

| Endpoint type | Tenant source |
| --- | --- |
| Normal tenant API | `X-Tenant-ID`, verified against membership |
| Public form submit | `form_id` mapping in the integration/form record |
| Provider webhook | Provider account ID → integration → tenant |
| Internal automation API | Signed `X-Tenant-ID` **and** resource ownership verification |
| Platform admin | Separate namespace and platform role; audited |

### 3.3 Roles

| Role | Scope |
| --- | --- |
| `rep` | Assigned leads, related conversations, own tasks |
| `manager` | All leads/tasks/conversations in their team(s) |
| `admin` | All data in the company; users, teams, integrations, settings |
| `platform_admin` | Tenants and platform health only; separate from company admin |

A company admin is never automatically a platform admin. Platform admins do not get company data unless a temporary, approved, audited support grant exists.

> **Role-string alignment:** this contract uses `rep`, `manager`, `admin`, matching the current backend `tenant_memberships` CHECK constraint and `DATABASE_SCHEMA.md`. Keep seed data, API examples, and permission tests on the same set. Do not support both.

### 3.4 Permission matrix

| Capability | Rep | Manager | Company admin | Platform admin |
| --- | --- | --- | --- | --- |
| View leads | Assigned only | Team | Tenant | No, unless support grant |
| Create leads | Yes | Yes | Yes | No |
| Update lead status | Assigned leads | Team | Tenant | No |
| Assign/reassign leads | No | Team | Tenant | No |
| View conversations | Assigned | Team | Tenant | No |
| Send messages | Assigned | Team | Tenant | No |
| Manage own tasks | Yes | Yes | Yes | No |
| View team tasks/performance | No | Yes | Yes | No |
| Invite/deactivate users | No | No | Yes | No |
| Manage roles/teams | No | No | Yes | No |
| Manage integrations/credentials | No | No | Yes | No |
| View tenant audit log | No | No | Yes | No |
| View dashboard | `scope=me` | `me`, `team` | `me`, `team`, `company` | Platform health only |
| Manage tenants | No | No | No | Yes |

---

## 4. Core resource shapes

### 4.1 Lead

```json
{
  "id": "3d9f6f9a-5c4a-4f6c-9e74-0a7d2f1b8c11",
  "name": "Ayesha Rahman",
  "email": "ayesha@example.com",
  "phone": "+8801700000000",
  "company_name": "Acme Bangladesh",
  "source": "whatsapp",
  "source_campaign": "nov-demo",
  "external_id": "wamid.123",
  "status": "new",
  "lost_reason": null,
  "assigned_user_id": null,
  "team_id": null,
  "intent": "request_demo",
  "lead_score": 90,
  "priority": "high",
  "consent": true,
  "opted_out": false,
  "version": 1,
  "created_at": "2026-11-08T10:00:00Z",
  "updated_at": "2026-11-08T10:00:00Z"
}
```

Enums:

- `source`: `website_form | tracking | whatsapp | facebook_lead_ads | messenger | manual | csv`
- `status`: `new | contacted | qualified | proposal | won | lost`
- `priority`: `low | medium | high`
- `lost_reason`: `price | timing | no_response | competitor | not_qualified | other`

`name` is required. At least one of `email` or `phone` is required. `consent` must be `true` before any automated outbound follow-up. `opted_out = true` blocks outbound messages permanently for that lead.

### 4.2 Lead assessment

```json
{
  "id": "a5f1e0d4-0f39-4d8c-a3a8-2c9e6b2f7a44",
  "lead_id": "3d9f6f9a-5c4a-4f6c-9e74-0a7d2f1b8c11",
  "category": "business_customer",
  "intent": "request_demo",
  "interest": "CRM software",
  "buying_stage": "consideration",
  "sentiment": "positive",
  "priority": "high",
  "lead_score": 90,
  "recommended_action": "schedule_demo",
  "follow_up_days": 0,
  "confidence": 0.94,
  "needs_human_review": false,
  "review_status": "not_required",
  "status": "ok",
  "summary": null,
  "model": "provider/model-version",
  "prompt_version": "classify-v1",
  "created_at": "2026-11-08T10:00:04Z"
}
```

`lead_score` is 0–100. `needs_human_review` is true when `confidence < 0.6` or the model output required repair/fallback. `status` is `ok | fallback | failed`. `review_status` is an API-level human-review workflow field: `not_required | pending | approved | rejected`; `DATABASE_SCHEMA.md` includes the review columns and reviewer references.

### 4.3 Conversation and message

```json
{
  "id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "lead_id": "3d9f6f9a-5c4a-4f6c-9e74-0a7d2f1b8c11",
  "channel": "whatsapp",
  "status": "open",
  "assigned_user_id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
  "last_message_at": "2026-11-08T10:05:00Z",
  "unread_count": 1,
  "created_at": "2026-11-08T10:00:00Z"
}
```

```json
{
  "id": "c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f",
  "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "direction": "inbound",
  "text": "I need a CRM for my 20-person sales team. Please arrange a demo.",
  "provider_message_id": "wamid.HBgM...",
  "status": "received",
  "attachments": [],
  "created_at": "2026-11-08T10:05:00Z"
}
```

Enums:

- `channel`: `whatsapp | messenger`
- `conversation.status`: `open | pending | closed`
- `message.direction`: `inbound | outbound`
- `message.status`: `received | queued | sent | delivered | read | failed`

Attachments are private S3 objects. Responses return `id`, `filename`, `content_type`, `size_bytes`, and a short-lived signed `download_url`. Never return bucket keys or public URLs.

> **Schema alignment:** `DATABASE_SCHEMA.md` stores `messages.status`, `messages.sent_at`, `messages.delivered_at`, `messages.read_at`, and `conversations.assigned_user_id`. `conversation.unread_count` is computed from `conversation_reads` and inbound messages, not stored as a mutable counter.

### 4.4 Task

```json
{
  "id": "d4e5f6a7-b8c9-4d0e-8f1a-2b3c4d5e6f70",
  "lead_id": "3d9f6f9a-5c4a-4f6c-9e74-0a7d2f1b8c11",
  "assigned_user_id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
  "type": "follow_up",
  "title": "Send pricing follow-up",
  "notes": null,
  "due_at": "2026-11-09T10:00:00Z",
  "status": "open",
  "requires_approval": true,
  "approval_status": "pending",
  "completed_at": null,
  "version": 1,
  "created_at": "2026-11-08T10:00:05Z",
  "updated_at": "2026-11-08T10:00:05Z"
}
```

Enums:

- `type`: `call | meeting | reminder | follow_up`
- `status`: `open | done | cancelled | paused`
- `approval_status`: `not_required | pending | approved | rejected` (stored by `DATABASE_SCHEMA.md` with explicit approver/rejecter fields; the service keeps it consistent with `requires_approval`)

### 4.5 Integration

```json
{
  "id": "e6f7a8b9-c0d1-4e2f-8a3b-4c5d6e7f8a90",
  "provider": "whatsapp",
  "status": "active",
  "provider_account_id": "phone-number-id",
  "scopes": ["messages"],
  "expires_at": null,
  "connected_by_user_id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
  "created_at": "2026-11-08T10:00:00Z"
}
```

`status`: `active | expired | revoked | error`. The database stores `active | revoked | error`; `expired` is derived from `expires_at`. Credentials are write-only and never appear in any response.

### 4.6 Timeline event

```json
{
  "id": "f7a8b9c0-d1e2-4f3a-8b4c-5d6e7f8a9b01",
  "type": "status_changed",
  "actor": {
    "type": "user",
    "id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
    "name": "Rahim"
  },
  "summary": "Status changed from new to contacted",
  "metadata": {
    "from": "new",
    "to": "contacted"
  },
  "created_at": "2026-11-08T10:10:00Z"
}
```

Types: `lead_created | status_changed | assigned | note_added | message_received | message_sent | task_created | task_completed | assessment_created | opt_out | integration_event`.

### 4.7 CSV import job

```json
{
  "id": "a9b8c7d6-e5f4-4a3b-8c2d-1e0f9a8b7c6d",
  "status": "completed",
  "dry_run": false,
  "total_rows": 120,
  "created_count": 100,
  "duplicate_count": 15,
  "error_count": 5,
  "errors": [
    {
      "row": 42,
      "code": "missing_contact",
      "message": "Row must contain email or phone"
    }
  ],
  "created_at": "2026-11-08T10:00:00Z",
  "completed_at": "2026-11-08T10:00:12Z"
}
```

`status`: `queued | processing | completed | failed`. `errors` is capped at 100 items; a signed report URL may be included for the full list.

---

## 5. Endpoint catalog

Auth column: **Public** = no token; **Session** = access token, no `X-Tenant-ID`; **Tenant** = access token + `X-Tenant-ID`; **Internal** = HMAC service auth; **Platform** = platform-admin token + MFA.

Route ordering: declare static paths before parameterized paths (`GET /tasks/due-follow-ups` before `GET /tasks/{id}`), otherwise FastAPI may try to parse the literal segment as a UUID.

| Method | Path | Auth | Role | Purpose |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/auth/signup` | Public | — | Create company + first admin |
| POST | `/api/v1/auth/login` | Public | — | Start a session |
| POST | `/api/v1/auth/mfa/verify` | Public challenge | — | Complete MFA login |
| POST | `/api/v1/auth/refresh` | Cookie + CSRF | — | Rotate refresh token, issue access token |
| POST | `/api/v1/auth/logout` | Cookie + CSRF | — | Revoke session |
| POST | `/api/v1/auth/password-reset` | Public | — | Request reset email |
| POST | `/api/v1/auth/password-reset/confirm` | Public | — | Set new password |
| POST | `/api/v1/auth/change-password` | Session | Any | Change own password |
| POST | `/api/v1/auth/verify-email` | Public | — | Verify email token |
| POST | `/api/v1/auth/verify-email/resend` | Public | — | Resend verification email |
| GET | `/api/v1/auth/me` | Session | Any | Current user + memberships |
| POST | `/api/v1/auth/mfa/setup` | Session | Admin / platform | Start TOTP setup |
| POST | `/api/v1/auth/mfa/confirm` | Session | Admin / platform | Confirm TOTP setup |
| POST | `/api/v1/auth/mfa/disable` | Session | Admin / platform | Disable MFA |
| GET | `/api/v1/invitations` | Tenant | Admin | List invitations |
| POST | `/api/v1/invitations` | Tenant | Admin | Invite a user |
| POST | `/api/v1/invitations/{token}/accept` | Public / session | — | Accept invitation |
| POST | `/api/v1/invitations/{id}/resend` | Tenant | Admin | Resend invitation |
| DELETE | `/api/v1/invitations/{id}` | Tenant | Admin | Revoke invitation |
| GET | `/api/v1/users` | Tenant | Admin / manager | List users in scope |
| GET | `/api/v1/users/{id}` | Tenant | Admin / manager / self | Get user |
| PATCH | `/api/v1/users/{id}` | Tenant | Admin | Change role, team, active status |
| GET | `/api/v1/teams` | Tenant | Any | List teams in scope |
| POST | `/api/v1/teams` | Tenant | Admin | Create team |
| PATCH | `/api/v1/teams/{id}` | Tenant | Admin | Rename team |
| POST | `/api/v1/leads` | Tenant | Rep / manager / admin | Create lead manually |
| GET | `/api/v1/leads` | Tenant | Any | List/search leads |
| GET | `/api/v1/leads/{id}` | Tenant | Any | Lead detail |
| PATCH | `/api/v1/leads/{id}` | Tenant | Any (scoped) | Update status/priority |
| POST | `/api/v1/leads/{id}/assign` | Tenant | Manager / admin | Assign lead |
| POST | `/api/v1/leads/{id}/notes` | Tenant | Any (scoped) | Add note |
| POST | `/api/v1/leads/{id}/opt-out` | Tenant | Any (scoped) | Record opt-out |
| GET | `/api/v1/leads/{id}/timeline` | Tenant | Any (scoped) | Lead timeline |
| GET | `/api/v1/leads/{id}/assessments` | Tenant | Any (scoped) | Assessment history |
| POST | `/api/v1/leads/{id}/assess` | Tenant | Manager / admin | Request re-assessment |
| POST | `/api/v1/assessments/{id}/review` | Tenant | Rep / manager / admin | Approve/reject low-confidence assessment |
| POST | `/api/v1/leads/import` | Tenant | Manager / admin | Upload CSV |
| GET | `/api/v1/leads/imports/{id}` | Tenant | Manager / admin | Import status/report |
| GET | `/api/v1/conversations` | Tenant | Any (scoped) | List conversations |
| GET | `/api/v1/conversations/{id}` | Tenant | Any (scoped) | Conversation detail |
| GET | `/api/v1/conversations/{id}/messages` | Tenant | Any (scoped) | Message history |
| POST | `/api/v1/conversations/{id}/analyze` | Tenant | Any (scoped) | Generate and store summary and sentiment |
| GET | `/api/v1/conversations/{id}/analysis` | Tenant | Any (scoped) | Get latest summary and sentiment |
| POST | `/api/v1/conversations/{id}/read` | Tenant | Any (scoped) | Mark conversation read |
| POST | `/api/v1/messages` | Tenant | Any (scoped) | Send outbound message |
| POST | `/api/v1/tasks` | Tenant | Any (scoped) | Create task |
| GET | `/api/v1/tasks` | Tenant | Any (scoped) | List tasks |
| GET | `/api/v1/tasks/{id}` | Tenant | Any (scoped) | Task detail |
| PATCH | `/api/v1/tasks/{id}` | Tenant | Any (scoped) | Update/complete task |
| GET | `/api/v1/tasks/due-follow-ups` | Tenant | Any (scoped) | Due follow-ups |
| POST | `/api/v1/tasks/{id}/approve` | Tenant | Rep / manager / admin | Approve/reject follow-up |
| GET | `/api/v1/dashboard/summary` | Tenant | Any | Role-scoped dashboard |
| GET | `/api/v1/integrations` | Tenant | Admin | List integrations |
| POST | `/api/v1/integrations/{provider}/connect` | Tenant | Admin | Connect provider |
| POST | `/api/v1/integrations/{id}/test` | Tenant | Admin | Test connection |
| DELETE | `/api/v1/integrations/{id}` | Tenant | Admin | Disconnect/revoke |
| POST | `/api/v1/public/forms/{form_id}/submit` | Public | — | Website form submit |
| GET | `/api/v1/webhooks/{provider}` | Public | — | Meta verification challenge |
| POST | `/api/v1/webhooks/{provider}` | Public signature | — | Receive provider webhook |
| GET | `/api/v1/audit-logs` | Tenant | Admin | Tenant audit log |
| GET | `/api/v1/platform/tenants` | Platform | Platform admin | List tenants |
| GET | `/api/v1/platform/tenants/{id}` | Platform | Platform admin | Tenant summary |
| PATCH | `/api/v1/platform/tenants/{id}` | Platform | Platform admin | Suspend/activate tenant |
| GET | `/api/v1/platform/health` | Platform | Platform admin | Platform health |
| GET | `/internal/v1/automation/leads/{lead_id}` | Internal | n8n | Fetch lead context |
| POST | `/internal/v1/automation/leads/{lead_id}/assess` | Internal | n8n | Request AI assessment |
| POST | `/internal/v1/automation/leads/{lead_id}/assign` | Internal | n8n | Assign + create task |
| GET | `/internal/v1/automation/tasks/due` | Internal | n8n | Fetch due follow-ups |
| POST | `/internal/v1/automation/tasks/{task_id}/result` | Internal | n8n | Record follow-up result |
| POST | `/internal/v1/automation/messages` | Internal | n8n | Send approved message |
| POST | `/internal/v1/automation/notifications` | Internal | n8n | Notify a rep |
| GET | `/internal/v1/automation/health` | Internal | n8n | Internal readiness |
| GET | `/health` | Public | — | Liveness |
| GET | `/health/ready` | Public | — | Readiness (DB) |

---

## 6. Auth endpoints

### 6.1 `POST /api/v1/auth/signup`

Creates a tenant and its first company admin in one transaction. Sends a verification email. No tokens are issued until the email is verified.

```json
{
  "company_name": "Acme Bangladesh",
  "company_slug": "acme-bd",
  "full_name": "Ayesha Rahman",
  "email": "admin@acme.example",
  "password": "correct-horse-battery-staple",
  "accept_terms": true
}
```

`201 Created`

```json
{
  "data": {
    "tenant": {
      "id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
      "name": "Acme Bangladesh",
      "slug": "acme-bd"
    },
    "user": {
      "id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
      "email": "admin@acme.example",
      "full_name": "Ayesha Rahman",
      "email_verified": false
    },
    "membership": {
      "role": "admin",
      "is_active": true
    }
  }
}
```

Errors: `409 email_exists`, `409 slug_taken`, `422 validation_error`.

### 6.2 `POST /api/v1/auth/login`

```json
{
  "email": "admin@acme.example",
  "password": "correct-horse-battery-staple"
}
```

`200 OK` when MFA is not required:

```json
{
  "data": {
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 900,
    "csrf_token": "csrf-opaque-value",
    "user": {
      "id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
      "email": "admin@acme.example",
      "full_name": "Ayesha Rahman",
      "email_verified": true
    },
    "memberships": [
      {
        "tenant": {
          "id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
          "name": "Acme Bangladesh",
          "slug": "acme-bd"
        },
        "role": "admin",
        "team_id": null,
        "is_active": true
      }
    ]
  }
}
```

Cookies set:

| Cookie | Flags |
| --- | --- |
| `refresh_token` | `HttpOnly`, `Secure` in staging/prod, `SameSite=Strict`, `Path=/api/v1/auth`, 30 days |
| `csrf_token` | `Secure` in staging/prod, `SameSite=Strict`, `Path=/`, not `HttpOnly`, 30 days |

`202 Accepted` when MFA is required:

```json
{
  "data": {
    "mfa_required": true,
    "challenge_token": "short-lived-challenge-token",
    "expires_in": 300
  }
}
```

`202 Accepted` when an admin has not enrolled MFA yet:

```json
{
  "data": {
    "mfa_setup_required": true,
    "setup_token": "short-lived-setup-token",
    "expires_in": 600
  }
}
```

The two `202` bodies are distinguished by `mfa_required` vs `mfa_setup_required`. The setup token is valid only for `/auth/mfa/setup` and `/auth/mfa/confirm`; after confirmation, the user logs in again to receive a normal access token.

Errors: `401 invalid_credentials` (generic), `403 email_not_verified`, `403 account_disabled`, `429 rate_limited`.

### 6.3 `POST /api/v1/auth/mfa/verify`

Completes the login challenge.

```json
{
  "challenge_token": "short-lived-challenge-token",
  "code": "123456"
}
```

`200 OK` with the same body/cookies as a successful login. `401 invalid_mfa_code`; `429 rate_limited` after repeated failures. A recovery code may be used once in place of the TOTP code.

### 6.4 `POST /api/v1/auth/refresh`

No body. Requires the `refresh_token` cookie and `X-CSRF-Token`.

`200 OK`

```json
{
  "data": {
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 900,
    "csrf_token": "new-csrf-opaque-value"
  }
}
```

The refresh cookie is rotated. Reuse of an old refresh token revokes the token family and returns `401 session_revoked`.

### 6.5 `POST /api/v1/auth/logout`

Requires the refresh cookie and `X-CSRF-Token`. Revokes the current session and clears both cookies. `204 No Content`. Always returns `204` for an already-invalid session so logout is safe to retry.

### 6.6 Password reset

`POST /api/v1/auth/password-reset`

```json
{ "email": "admin@acme.example" }
```

Always `202 Accepted`:

```json
{ "data": { "message": "If the account exists, a reset email has been sent." } }
```

`POST /api/v1/auth/password-reset/confirm`

```json
{
  "token": "single-use-reset-token",
  "new_password": "new-correct-horse-battery-staple"
}
```

`204 No Content`. The token is single-use and short-lived; all sessions are revoked.

### 6.7 Email verification

`POST /api/v1/auth/verify-email`

```json
{ "token": "single-use-verification-token" }
```

`204 No Content`; token is single-use and expires. `POST /api/v1/auth/verify-email/resend` accepts `{ "email": "..." }` and always returns `202` to avoid account enumeration.

### 6.8 `GET /api/v1/auth/me`

Requires access token (no `X-Tenant-ID`). Returns the current user and memberships:

```json
{
  "data": {
    "user": {
      "id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
      "email": "admin@acme.example",
      "full_name": "Ayesha Rahman",
      "is_active": true,
      "mfa_enabled": true
    },
    "memberships": [
      {
        "tenant_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
        "tenant_name": "Acme Bangladesh",
        "role": "admin",
        "team_id": null,
        "is_active": true
      }
    ]
  }
}
```

### 6.9 MFA management

Admin roles (company admin and platform admin) must have MFA enabled before using admin endpoints or receiving a normal access token. If an admin has not enrolled yet, login returns a setup-only token; the UI sends them through the MFA setup flow before any tenant data is accessible.

These endpoints are identity-scoped: send the access token (or the short-lived setup token for first enrollment), but **do not** send `X-Tenant-ID`.

`POST /api/v1/auth/mfa/setup`

`200 OK`

```json
{
  "data": {
    "secret": "BASE32SECRET",
    "otpauth_uri": "otpauth://totp/...",
    "recovery_codes": ["ABCD-EFGH", "IJKL-MNOP"]
  }
}
```

`POST /api/v1/auth/mfa/confirm`

```json
{ "code": "123456" }
```

`200 OK`; MFA becomes active. Recovery codes are shown only once and stored hashed.

`POST /api/v1/auth/mfa/disable` requires the current password and a valid code. `204 No Content`. Audited.

### 6.10 `POST /api/v1/auth/change-password`

Requires access token.

```json
{
  "current_password": "old-password",
  "new_password": "new-password"
}
```

`204 No Content`; revokes all other sessions.

---

## 7. Invitations, users and teams

### 7.1 Invitations

`POST /api/v1/invitations` (admin only)

```json
{
  "email": "rep@acme.example",
  "role": "rep",
  "team_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
}
```

`201 Created`

```json
{
  "data": {
    "id": "c3d4e5f6-a7b8-4c9d-8e0f-1a2b3c4d5e6f",
    "email": "rep@acme.example",
    "role": "rep",
    "team_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
    "status": "pending",
    "expires_at": "2026-11-15T10:00:00Z",
    "created_at": "2026-11-08T10:00:00Z"
  }
}
```

Rules: 7-day expiry, single-use token, email must match at acceptance, admin cannot invite a `platform_admin`, and the last active company admin cannot be removed or demoted.

`GET /api/v1/invitations?status=pending` (admin) returns a paginated list.

`POST /api/v1/invitations/{token}/accept`

New user (no existing account for that email):

```json
{
  "full_name": "Rahim Uddin",
  "password": "correct-horse-battery-staple"
}
```

Existing user: the request must include a valid access token for that same email; `password` and `full_name` are omitted. The server links the existing user to the invited tenant.

`200 OK` returns the user, membership and, for a new user, the same token/cookie response as login. `410 invitation_expired`, `409 already_member`, `403 email_mismatch`.

`POST /api/v1/invitations/{id}/resend` and `DELETE /api/v1/invitations/{id}` are admin-only; both are audited.

### 7.2 Users

`GET /api/v1/users?role=rep&team_id=<uuid>&is_active=true&cursor=<cursor>&limit=25`

- Admin: all users in the tenant.
- Manager: users in their team(s).
- Rep: only self.

Response items include user plus membership:

```json
{
  "data": [
    {
      "id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
      "email": "rep@acme.example",
      "full_name": "Rahim Uddin",
      "is_active": true,
      "membership": {
        "role": "rep",
        "team_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
        "is_active": true
      }
    }
  ],
  "meta": { "next_cursor": null, "has_more": false }
}
```

`PATCH /api/v1/users/{id}` (admin only)

```json
{
  "full_name": "Rahim Uddin",
  "role": "manager",
  "team_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
  "is_active": true
}
```

Role/team/active changes are audited. `409 last_admin` if the change would leave the tenant with no active admin.

### 7.3 Teams

`GET /api/v1/teams` — reps see their own team, managers their teams, admins all.

`POST /api/v1/teams` (admin)

```json
{ "name": "Dhaka Sales" }
```

`201 Created` with team `{id, name, created_at, updated_at}`.

`PATCH /api/v1/teams/{id}` (admin) renames a team. `409 duplicate_name` within the tenant.

---

## 8. Leads and assessments

### 8.1 `POST /api/v1/leads`

Requires `Idempotency-Key`.

```json
{
  "name": "Ayesha Rahman",
  "email": "ayesha@example.com",
  "phone": "+8801700000000",
  "company_name": "Acme Bangladesh",
  "source": "manual",
  "consent": true,
  "assigned_user_id": null,
  "team_id": null,
  "notes": "Met at a demo event"
}
```

`201 Created` returns a `Lead`. `409 duplicate_lead` includes `existing_lead_id` when an active lead in the tenant already has the same normalized email, phone, or `(source, external_id)`.

`assigned_user_id` and `team_id` may be supplied only by a manager/admin; a rep-created lead is assigned to that rep or left unassigned. `notes` becomes the first timeline note.

Normalization: email lowercased/trimmed; phone normalized to E.164 where possible. Dedupe is scoped to the tenant.

### 8.2 `GET /api/v1/leads`

Query parameters:

| Parameter | Notes |
| --- | --- |
| `q` | Name, email, phone, company; max 100 chars |
| `status` | Repeatable or comma-separated |
| `source` | Repeatable or comma-separated |
| `priority` | `low`, `medium`, `high` |
| `assigned_user_id` | UUID |
| `team_id` | UUID |
| `created_from`, `created_to` | ISO 8601 |
| `sort` | `created_at`, `updated_at`, `lead_score`, `priority` |
| `limit`, `cursor` | Pagination |

Role scoping is applied before filters and cannot be overridden by query parameters.

- Rep: only leads assigned to them.
- Manager: leads assigned to users in their team(s).
- Admin: all tenant leads.

### 8.3 `GET /api/v1/leads/{id}`

Returns the lead plus optional expansions:

- `include=owner,team,latest_assessment,next_task`
- `include=latest_assessment` is the default for the lead detail page.

`404 not_found` if the lead does not exist in the verified tenant.

### 8.4 `PATCH /api/v1/leads/{id}`

Allowed fields: `name`, `email`, `phone`, `company_name`, `priority`, `status`, `lost_reason`, `assigned_user_id` (manager/admin only), `team_id` (manager/admin only), `version`.

Status transitions:

| From | Allowed to |
| --- | --- |
| `new` | `contacted`, `qualified`, `lost` |
| `contacted` | `qualified`, `proposal`, `lost` |
| `qualified` | `proposal`, `won`, `lost` |
| `proposal` | `won`, `lost` |
| `won` | Terminal |
| `lost` | Terminal; admin may reopen to `contacted` with an audit reason |

`lost_reason` is required when moving to `lost`. `409 invalid_status_transition` otherwise. Every status change is audited and adds a timeline event.

### 8.5 `POST /api/v1/leads/{id}/assign`

Manager/admin only.

```json
{
  "assigned_user_id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
  "team_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
}
```

The target user must be an active member of the tenant and, for a manager, of the manager's team. `200 OK` returns the updated lead. Assignment is audited and creates a timeline event.

Round-robin assignment is a server-side rule. It must be transactional and idempotent; it never trusts a user ID from the browser unless a manager/admin explicitly assigns.

### 8.6 Notes and opt-out

`POST /api/v1/leads/{id}/notes`

```json
{ "text": "Asked for a demo next Tuesday." }
```

`201 Created` returns a note interaction and adds a timeline event.

`POST /api/v1/leads/{id}/opt-out`

```json
{ "reason": "Customer asked to stop messages" }
```

`200 OK`; sets `opted_out = true`, records the opt-out timestamp and source, cancels open automated follow-up tasks, and adds an audit/timeline event. Outbound message attempts return `403 opt_out`; attempts without consent return `403 no_consent`.

### 8.7 Timeline

`GET /api/v1/leads/{id}/timeline?types=status_changed,message_received&cursor=&limit=`

Returns timeline events newest first. Notes, status changes, assignments, messages, tasks, and assessments all appear here so the UI has one history.

### 8.8 Assessments

`GET /api/v1/leads/{id}/assessments?cursor=&limit=10`

Returns assessment history, newest first. Assessment input text and prompt are not returned; only the validated output, model, prompt version, confidence, and review state.

`POST /api/v1/leads/{id}/assess` (manager/admin) enqueues a re-assessment. `202 Accepted`; rate-limited. The auto-assessment on new lead/message is a background job and is not triggered by this endpoint synchronously.

`POST /api/v1/assessments/{id}/review`

```json
{
  "decision": "approve",
  "note": "Checked the conversation; score is reasonable."
}
```

`200 OK`. Allowed for the assigned rep, manager, or admin. `decision`: `approve | reject`. Rejecting marks the assessment `review_status=rejected` and creates a task for manual follow-up. Review is audited.

### 8.9 CSV import

`POST /api/v1/leads/import`

- `Content-Type: multipart/form-data`
- `file`: CSV, maximum 10 MB / 10,000 rows
- `dry_run`: `true` to validate and report without writing
- `Idempotency-Key`: required

Required CSV headers: `name` plus at least one of `email` or `phone`. Optional: `company_name`, `source`, `priority`, `owner_email`, `team_name`, `consent`, `notes`.

`202 Accepted`

```json
{
  "data": {
    "id": "a9b8c7d6-e5f4-4a3b-8c2d-1e0f9a8b7c6d",
    "status": "queued",
    "dry_run": false
  }
}
```

`GET /api/v1/leads/imports/{id}` returns the import job shape from section 4.7. Duplicate rows are reported, not silently merged. CSV values are escaped on export to prevent spreadsheet formula injection.

---

## 9. Conversations and messages

### 9.1 Conversations

`GET /api/v1/conversations?lead_id=&channel=&status=&assigned_user_id=&unread=true&cursor=&limit=`

Role scoping:

- Rep: conversations for assigned leads.
- Manager: conversations for leads owned by their team.
- Admin: all tenant conversations.

`GET /api/v1/conversations/{id}` returns the conversation, lead summary, assigned user, and unread count.

`GET /api/v1/conversations/{id}/messages?cursor=&limit=50` returns messages newest first. `meta.next_cursor` loads older messages.

`POST /api/v1/conversations/{id}/analyze` sends up to the latest 100 messages (bounded to 20,000 characters) to the configured OpenAI model after redacting known lead name/contact information, email addresses, and phone numbers. It validates and stores the summary, sentiment, model, prompt version, confidence, and review status in `lead_assessments`. Configure `OPENAI_API_KEY` and optionally `OPENAI_MODEL`; a missing key returns `503`, and provider/invalid-output errors return `502`.

`GET /api/v1/conversations/{id}/analysis` returns the latest stored summary and sentiment for that conversation. Both routes use the caller's normal lead visibility scope.

`POST /api/v1/conversations/{id}/read` marks unread messages as read and returns `204`. It is scoped to the caller.

### 9.2 `POST /api/v1/messages`

Requires `Idempotency-Key`.

```json
{
  "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "text": "Thanks Ayesha. Does Tuesday at 3 PM work for a demo?"
}
```

`202 Accepted`

```json
{
  "data": {
    "id": "c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f",
    "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "direction": "outbound",
    "status": "queued",
    "created_at": "2026-11-08T10:15:00Z"
  }
}
```

Rules:

- Caller must have access to the conversation's lead.
- `opted_out = true` → `403 opt_out`.
- `consent = false` → `403 no_consent`.
- Conversation closed → `409 conversation_closed` unless the caller reopens it (not in MVP).
- The message is persisted and queued; the provider send happens in a background worker.
- Provider message IDs and delivery status are updated by webhooks.
- Text maximum 4,096 characters.
- Outbound attachments are post-MVP. Inbound attachments are stored as private references and exposed as short-lived signed URLs in message responses.

Errors: `409 idempotency_conflict`, `422 validation_error`, `503 provider_unavailable` only for explicit provider actions, not for queued messages.

---

## 10. Tasks and follow-ups

### 10.1 Create task

`POST /api/v1/tasks`

Requires `Idempotency-Key`.

```json
{
  "lead_id": "3d9f6f9a-5c4a-4f6c-9e74-0a7d2f1b8c11",
  "type": "follow_up",
  "title": "Send pricing follow-up",
  "notes": "Mention the 20-seat plan.",
  "due_at": "2026-11-09T10:00:00Z",
  "assigned_user_id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
  "requires_approval": true
}
```

`201 Created` returns a task. A rep may create tasks only for leads they can access and may assign only to themselves. Managers/admins can assign within scope. `due_at` must be in the future unless an admin overrides.

### 10.2 List and get tasks

`GET /api/v1/tasks?status=open&assigned_user_id=&lead_id=&due_before=&due_after=&overdue=true&cursor=&limit=`

- Rep: own tasks.
- Manager: team tasks.
- Admin: tenant tasks.
- `overdue=true` means `status=open` and `due_at < now`.

`GET /api/v1/tasks/{id}` returns the task with lead summary.

### 10.3 Update task

`PATCH /api/v1/tasks/{id}`

```json
{
  "status": "done",
  "notes": "Customer replied; demo booked.",
  "due_at": "2026-11-10T10:00:00Z",
  "assigned_user_id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
  "version": 2
}
```

Allowed: `status`, `notes`, `due_at`, `assigned_user_id` (manager/admin), `version`. Completing sets `completed_at`. Cancelling stops reminders. Every change is audited and appears on the lead timeline.

### 10.4 Due follow-ups

`GET /api/v1/tasks/due-follow-ups?due_before=2026-11-09T23:59:59Z&limit=50`

Returns open follow-up tasks due before the given time for the caller's scope. This is the UI endpoint. n8n uses the separate internal endpoint, which can query a tenant's due tasks with service auth.

### 10.5 Follow-up approval

`POST /api/v1/tasks/{id}/approve`

```json
{
  "decision": "approve",
  "note": "Approved for WhatsApp follow-up."
}
```

`decision`: `approve | reject`. Only tasks with `requires_approval = true` and `approval_status = pending` can be acted on. The assigned rep may approve their own permitted follow-ups; managers/admins may approve within scope. `200 OK`. `409 invalid_approval_state` otherwise. The decision is audited.

Approval does **not** bypass consent, opt-out, quiet hours, or the lead status check.

---

## 11. Dashboard

`GET /api/v1/dashboard/summary?scope=me|team|company&from=2026-10-01&to=2026-11-08`

- `scope=me`: any role.
- `scope=team`: manager/admin.
- `scope=company`: company admin only.
- `from`/`to` default to the last 30 days; maximum range 366 days.
- Buckets use the tenant's timezone.

`200 OK`

```json
{
  "data": {
    "scope": "team",
    "period": {
      "from": "2026-10-01",
      "to": "2026-11-08",
      "timezone": "Asia/Dhaka"
    },
    "kpis": {
      "new_leads": 123,
      "high_priority_leads": 12,
      "follow_ups_due_today": 8,
      "overdue_tasks": 3,
      "conversion_rate": 0.18,
      "avg_first_response_seconds": 420
    },
    "leads_by_source": [
      { "source": "whatsapp", "count": 50 },
      { "source": "website_form", "count": 30 }
    ],
    "leads_by_status": [
      { "status": "new", "count": 40 },
      { "status": "contacted", "count": 30 }
    ],
    "pipeline": {
      "new": 40,
      "contacted": 30,
      "qualified": 20,
      "proposal": 10,
      "won": 15,
      "lost": 8
    },
    "lost_reasons": [
      { "reason": "price", "count": 4 }
    ],
    "reps": [
      {
        "user_id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
        "name": "Rahim Uddin",
        "leads": 30,
        "won": 5,
        "conversion_rate": 0.17
      }
    ],
    "integration_health": [
      { "provider": "whatsapp", "status": "active", "last_event_at": "2026-11-08T10:05:00Z" }
    ],
    "automation_health": {
      "workflow_a_success_rate": 0.98,
      "workflow_b_success_rate": 0.95,
      "failed_runs_24h": 2
    }
  }
}
```

Role-inappropriate sections are omitted. Changing `scope` or date parameters must never reveal another team's or tenant's data; unauthorized scope → `403 forbidden`.

---

## 12. Integrations, public forms and webhooks

### 12.1 Integrations

`GET /api/v1/integrations` (admin only)

Returns sanitized integrations. Credentials are never included.

`POST /api/v1/integrations/{provider}/connect` (admin only)

`provider`: `whatsapp | meta | website_form`.

Generic body:

```json
{
  "provider_account_id": "phone-number-id",
  "credentials": {
    "access_token": "provider-secret",
    "verify_token": "meta-verify-token"
  },
  "scopes": ["messages"]
}
```

Provider-specific credentials are validated, encrypted at rest, and never logged or returned. WhatsApp requires `phone_number_id`, `waba_id`, `access_token`, and `verify_token`; Meta requires `app_id`, `app_secret`, `access_token`, and `verify_token`. `201 Created` returns the integration shape. `502 provider_error` if the provider rejects the credentials.

`POST /api/v1/integrations/{id}/test` (admin) performs a minimal provider check and returns `{ "data": { "status": "ok" } }` or `502`.

`DELETE /api/v1/integrations/{id}` (admin) revokes the connection and returns `204`.

### 12.2 Public website form

`POST /api/v1/public/forms/{form_id}/submit`

No access token, no `X-Tenant-ID`, no credentials. `form_id` is an opaque public identifier mapped to one tenant.

```json
{
  "name": "Ayesha Rahman",
  "email": "ayesha@example.com",
  "phone": "+8801700000000",
  "company_name": "Acme Bangladesh",
  "message": "I need a CRM for 20 people.",
  "consent": true,
  "consent_version": "2026-01",
  "utm": {
    "source": "facebook",
    "medium": "paid",
    "campaign": "nov-demo"
  },
  "_hp": ""
}
```

`202 Accepted`

```json
{
  "data": {
    "status": "received",
    "reference": "pf_9f2c1a7b"
  }
}
```

Rules:

- `consent` must be `true`; otherwise `422 consent_required`.
- `_hp` is a honeypot; if filled, return the same `202` without creating a lead.
- The server sets `source=website_form`, maps UTM values, applies rate limits, and deduplicates by normalized email/phone.
- The response never returns the lead ID or tenant information.
- CORS is allowed only for configured form origins and never with credentials.

### 12.3 Provider webhooks

`GET /api/v1/webhooks/{provider}` — Meta verification challenge.

Query: `hub.mode`, `hub.verify_token`, `hub.challenge`. If the token matches the tenant's configured verify token, return the challenge as plain text with `200`; otherwise `403`.

`POST /api/v1/webhooks/{provider}` — `provider` is `whatsapp` or `meta`.

Required provider header: `X-Hub-Signature-256: sha256=<hex>` computed over the **raw request body** with the app secret. Verify before parsing JSON, using constant-time comparison.

Processing contract:

1. Read the raw body (maximum 1 MB).
2. Verify the signature and, where supported, timestamp/replay protection.
3. Resolve the tenant from the provider account/integration record, never from a request field.
4. Insert the event into `webhook_events` with a unique provider event ID.
5. If the event already exists, return `200` and do nothing.
6. Validate and enqueue processing; return `200` quickly.
7. If persistence fails, return `500` so the provider retries.

Responses:

- `200 {"status":"ok"}` — accepted or duplicate.
- `400 malformed_payload` — signature valid but body invalid.
- `401 invalid_signature` — missing/invalid signature.
- `403 unknown_provider_account` — no matching integration.
- `413 payload_too_large`.

Never trust tenant, lead, or user IDs in the webhook payload. Resolve and verify them server-side. Store only the minimum payload needed for retry; redact PII from logs.

---

## 13. Audit and platform administration

### 13.1 Tenant audit log

`GET /api/v1/audit-logs?actor_user_id=&action=&entity_type=&from=&to=&cursor=&limit=` (admin only)

Returns append-only audit records:

```json
{
  "data": [
    {
      "id": "f7a8b9c0-d1e2-4f3a-8b4c-5d6e7f8a9b01",
      "actor_user_id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
      "action": "lead.assigned",
      "entity_type": "lead",
      "entity_id": "3d9f6f9a-5c4a-4f6c-9e74-0a7d2f1b8c11",
      "ip_address": "203.0.113.10",
      "created_at": "2026-11-08T10:10:00Z",
      "details": { "assigned_user_id": "..." }
    }
  ],
  "meta": { "next_cursor": null, "has_more": false }
}
```

`details` is redacted: no passwords, tokens, credentials, or message bodies. Platform-level audit records are not visible here.

### 13.2 Platform admin API

Base: `/api/v1/platform`. Requires a platform-admin access token and MFA; company-admin tokens are rejected with `403 forbidden`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/platform/tenants` | List tenants with status and usage summary |
| GET | `/platform/tenants/{id}` | Tenant summary |
| PATCH | `/platform/tenants/{id}` | Set `active` or `suspended` |
| GET | `/platform/health` | Platform health summary |

Rules:

- Platform admins cannot read tenant leads, messages, or credentials through these endpoints.
- Any support access to tenant data must be a separate, time-limited, approved grant with audit logging. It is not part of the normal tenant API and requires security approval before implementation.
- Suspending a tenant blocks tenant API access (`403 tenant_suspended`) but preserves data for export/restore.

---

## 14. Internal automation API (n8n)

### 14.1 Network and authentication

- Only reachable on the private Docker network; never through the public reverse proxy.
- n8n has **no database credentials**. It calls this API like any other service.
- Authentication is HMAC service auth, not a user JWT.

Required headers:

| Header | Value |
| --- | --- |
| `X-Service-Id` | `n8n` (allow-listed) |
| `X-Tenant-ID` | Tenant UUID; resource ownership is still verified |
| `X-Timestamp` | Unix seconds; reject if skew > 300 seconds |
| `X-Idempotency-Key` | Unique per logical action; stored 24 hours |
| `X-Signature` | `sha256=<hex>` |

Canonical string:

```text
METHOD
PATH
TIMESTAMP
SHA256(raw_body)
```

- `PATH` is the request path **including the query string** exactly as sent, e.g. `/internal/v1/automation/tasks/due?limit=50`.
- For an empty body, use `SHA256(b"")`.
- The signature is `HMAC-SHA256(secret, canonical_string)`, hex-encoded, and sent as `X-Signature: sha256=<hex>`.
- Compare in constant time. Reject missing/invalid signatures with `401`.
- Reject replayed idempotency keys with `409` unless the request body is identical, in which case replay the stored response.

### 14.2 Internal endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/internal/v1/automation/leads/{lead_id}` | Lead + latest assessment + owner/team context |
| POST | `/internal/v1/automation/leads/{lead_id}/assess` | Request an AI assessment (202) |
| POST | `/internal/v1/automation/leads/{lead_id}/assign` | Assign lead and optionally create a task |
| GET | `/internal/v1/automation/tasks/due?due_before=&limit=100` | Due follow-ups for the tenant |
| POST | `/internal/v1/automation/tasks/{task_id}/result` | Record follow-up result |
| POST | `/internal/v1/automation/messages` | Send an approved message |
| POST | `/internal/v1/automation/notifications` | Notify a rep |
| GET | `/internal/v1/automation/health` | Internal readiness |

There is deliberately **no** internal endpoint that lists all leads, all messages, or raw tenant data. Every endpoint requires a specific resource ID and verifies it belongs to `X-Tenant-ID`.

**Ownership (resolves an open question in `SECURITY.md`):** the FastAPI capture service owns lead creation, the initial AI assessment job, and deterministic assignment. n8n Workflow A is orchestration only: it fetches the lead, checks whether an assessment already exists, requests one only if missing or failed, and ensures a task/notification exists. It must **not** reassign an already assigned lead or create a duplicate task. `POST .../assign` and `POST .../assess` are idempotent and return the existing result when the requested action is already satisfied.

Example: record a follow-up result

```json
{
  "status": "sent",
  "message_id": "c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f",
  "task_status": "done",
  "note": "Sent approved WhatsApp follow-up."
}
```

`status`: `sent | failed | skipped | needs_approval`. A failed result must include a non-sensitive `error_code`; never include provider tokens or full payloads. The endpoint is idempotent by task ID + idempotency key.

Send an approved message:

```json
{
  "conversation_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "text": "Following up on your demo request.",
  "approval_task_id": "d4e5f6a7-b8c9-4d0e-8f1a-2b3c4d5e6f70"
}
```

`202 Accepted`; the same consent/opt-out/quiet-hours rules as the user-facing message endpoint still apply. `409 approval_required` if the task is not approved.

Notify a rep:

```json
{
  "user_id": "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d",
  "type": "new_lead",
  "title": "New high-priority lead",
  "body": "Ayesha Rahman requested a demo.",
  "entity_type": "lead",
  "entity_id": "3d9f6f9a-5c4a-4f6c-9e74-0a7d2f1b8c11"
}
```

`202 Accepted`. Notification bodies must not contain credentials, tokens, or full message histories.

### 14.3 FastAPI → n8n event contract

FastAPI emits events from a transactional outbox. The worker posts to the n8n webhook URL with:

| Header | Value |
| --- | --- |
| `X-Event-ID` | Stable event UUID |
| `X-Timestamp` | Unix seconds; reject if skew > 300 seconds |
| `X-Signature` | `sha256=<hex>` where the signature is `HMAC-SHA256(secret, timestamp + "." + raw_body)` |

```json
{
  "event_id": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
  "event_type": "lead.created",
  "tenant_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "occurred_at": "2026-11-08T10:00:05Z",
  "data": {
    "lead_id": "3d9f6f9a-5c4a-4f6c-9e74-0a7d2f1b8c11"
  }
}
```

Event types:

| Event | Emitted when |
| --- | --- |
| `lead.created` | A lead is created through any channel |
| `lead.assigned` | A lead is assigned |
| `message.received` | An inbound WhatsApp/Messenger message is stored |
| `message.sent` | An outbound message is accepted by the provider |
| `lead.replied` | A customer reply pauses follow-ups |
| `task.due` | A follow-up task becomes due |
| `assessment.completed` | A validated AI assessment is stored |
| `integration.error` | A provider connection needs attention |

Delivery is **at least once**. n8n must deduplicate by `event_id` and return `2xx` quickly. n8n must not call the LLM provider directly; Workflow A requests assessment through the internal API.

---

## 15. Health endpoints

`GET /health` — public liveness.

```json
{ "status": "ok" }
```

`GET /health/ready` — readiness. Checks database connectivity and migration head. `200` when ready, `503` otherwise.

```json
{
  "status": "ready",
  "checks": {
    "database": "ok"
  }
}
```

No version numbers, environment variables, connection strings, or stack traces in health responses.

---

## 16. Contract testing and change process

Every endpoint must have:

- An OpenAPI schema test (request/response validation).
- An authentication test: missing token, expired token, wrong tenant, inactive membership.
- A role test: the allowed role succeeds; a same-tenant role denial returns `403 forbidden`.
- Cross-tenant tests with two seeded companies: tenant A's token + tenant B's tenant header or resource ID must return no data. Use `404 not_found` when the resource belongs to another tenant so its existence is not revealed.
- Idempotency tests for retryable writes.
- A test that error responses follow the standard envelope and contain no internals.

Webhook-specific tests:

- Valid signature accepted once.
- Same event twice creates no duplicate lead/message.
- Invalid signature rejected.
- Unknown provider account rejected.
- Oversized/malformed body rejected without a 500 stack trace.

Contract change process:

1. Update OpenAPI schemas and this file in the same PR.
2. Add contract tests.
3. If the change touches auth, tenancy/RLS, permissions, webhooks, or internal automation auth, get the security approver.
4. Announce breaking changes before merging; never silently rename or remove a field in `v1`.
5. Deprecations use `Deprecation` and `Sunset` headers and a migration note in this file.

---

## Appendix A — Quick examples

Login and call a tenant endpoint:

```bash
curl -s http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@acme.example","password":"correct-horse-battery-staple"}'
```

```bash
curl -s http://localhost:8000/api/v1/leads \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Tenant-ID: <tenant_uuid>" \
  -H "X-Request-ID: 5f0c2c7e-5e0c-4f5a-9a5e-2f6a1f8b9c10"
```

Create a lead:

```bash
curl -s http://localhost:8000/api/v1/leads \
  -X POST \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Tenant-ID: <tenant_uuid>" \
  -H "Idempotency-Key: 0f8fad5b-d9cb-469f-a165-70867728950e" \
  -H "Content-Type: application/json" \
  -d '{"name":"Ayesha Rahman","email":"ayesha@example.com","source":"manual","consent":true}'
```
