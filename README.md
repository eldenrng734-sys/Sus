# SUS - AI Sales Assistant CRM

SUS is a multi-tenant CRM for capturing and managing sales leads. The backend provides tenant-scoped lead, team, conversation, authentication, and AI assessment APIs; a Next.js frontend provides a limited set of account and lead screens.

> **Implementation status:** This repository contains a working backend and an incomplete frontend. This README describes implemented behavior, not the full product plan. Dashboards, task management, user-facing notifications, integration setup screens, and several other planned features are not complete.

## What is implemented

- Tenant signup, login, refresh/logout, password reset, email-verification and MFA endpoints.
- Lead creation, scoped listing and details, updates, notes/timeline, assignment, and CSV import.
- Team listing and admin team creation/renaming.
- Conversation and message persistence, including Meta and WhatsApp webhook routes.
- OpenAI-backed conversation analysis and versioned lead assessments, with manager/admin assessment review.
- An HMAC-authenticated internal API to persist rep notifications.
- Tenant-aware data scoping, role checks, PostgreSQL RLS migrations, and cross-tenant tests.
- Next.js screens for login, signup, invitation acceptance, and limited lead workflows.

Some capabilities are API-only or incomplete in the UI. In particular, outbound messages are stored as `queued`; this repository does not deliver them through a messaging provider. The notification API has no user-facing inbox. See the [User Guide](docs/USER_GUIDE.md) for role-specific availability and limitations.

## Technology

| Area | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy |
| Database | PostgreSQL 16, Alembic, row-level security |
| Frontend | Next.js, React, TypeScript |
| AI | OpenAI-backed conversation analysis; a separate LLM assessment client |
| Local services | Docker Compose, PostgreSQL, Mailpit |
| Backend tests and lint | pytest, Ruff |

Dependency versions and environment settings are defined in `backend\requirements.txt`, `frontend\package.json`, `backend\app\core\config.py`, and `.env.example`. The example environment file is for configuration reference only; replace all secret values with fresh local values and do not use sample secrets in shared or production environments.

## Architecture

```text
Browser (Next.js) --> FastAPI API --> PostgreSQL
                             |          tenant scoping + RLS
                             +--> OpenAI conversation analysis

Meta / WhatsApp --> provider webhook routes --> validated, persisted CRM data
n8n or another trusted internal caller --> HMAC-protected notification API
```

The backend owns authorization and tenant-scoped data access. The frontend calls the API through the rewrite in `frontend\next.config.ts`. Docker Compose runs the database, backend, and Mailpit; the frontend and any external automation service run separately.

## Repository layout

```text
backend\
  app\core\                 Configuration, authentication, tenancy, permissions
  app\modules\              Auth, leads, teams, conversations, AI, integrations, etc.
  alembic\                  Database migrations
  tests\                    Backend tests
frontend\
  src\app\                  Next.js routes and screens
infrastructure\
  docker-compose.yml        Local database, backend, and Mailpit services
docs\                       Setup and user guides
```

## Quick start

Prerequisites: Git, Docker with the Compose plugin, and Node.js/npm for the frontend. Python 3.12 is needed when running backend commands directly on the host; the backend container uses Python 3.12.

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
# Edit .env and replace all populated example secrets with fresh local values.

docker compose --env-file .env -f infrastructure\docker-compose.yml up -d db
docker compose --env-file .env -f infrastructure\docker-compose.yml run --build --rm backend alembic upgrade head
docker compose --env-file .env -f infrastructure\docker-compose.yml up --build
```

In another terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

The API is available at `http://localhost:8000`; interactive OpenAPI documentation is at `http://localhost:8000/docs`. The frontend runs at `http://localhost:3000`. For detailed host-based setup, environment requirements, tests, and troubleshooting, see the [Setup Guide](docs/SETUP_GUIDE.md).

Compose startup does not run database migrations automatically. No default seed users are provided; create an account through signup or use the invitation flow after an administrator creates an invitation.

## Environment and database

The application reads configuration from the repository-root `.env`. Compose uses the `db` hostname from inside containers. A backend run directly on the host must use the published PostgreSQL port (`localhost:5433`). Alembic uses `MIGRATION_DATABASE_URL` when set and otherwise falls back to `DATABASE_URL`.

The Compose database service is `db` (PostgreSQL 16), published on `127.0.0.1:5433`; Mailpit is available on ports `1025` (SMTP) and `8025` (web UI). The full Compose stack does not include the frontend or n8n. See the [Setup Guide](docs/SETUP_GUIDE.md) before configuring a separate test database.

## Authentication, roles, and tenant isolation

Tenant membership roles are `rep`, `manager`, and `admin`; platform administration is a separate user flag, not a tenant membership role. Reps are scoped to assigned leads, managers to their team, and tenant admins to tenant data. The API also validates active membership and tenant context. PostgreSQL RLS policies provide a database-level isolation layer for protected tables.

Admin-only endpoints include team management, invitations/membership changes, lead assignment/import, and assessment review. A platform-admin authorization dependency exists, but no platform-administration route or UI is currently registered. For precise permissions and the limited user interface, see the [User Guide](docs/USER_GUIDE.md).

Do not treat tenant IDs supplied by a client as authorization. Use the authenticated API and its tenant context; never expose tokens, provider credentials, or full conversation histories in logs or documentation.

## Internal rep notification API

The internal endpoint `POST /internal/v1/automation/notifications` is HMAC-authenticated for the `n8n` service. Keep it on a private network and configure `N8N_SERVICE_SECRET` through the approved deployment environment. No n8n workflow or signing script is included in this repository.

Required headers are `X-Service-Id: n8n`, `X-Tenant-ID` (canonical lowercase UUID), `X-Timestamp` (Unix seconds), `X-Idempotency-Key` (8-128 characters), and `X-Signature: sha256=<64 lowercase hex characters>`. The timestamp must be within 300 seconds of backend time; raw request bodies are limited to 16 KiB.

Serialize the JSON body once to UTF-8 bytes and send those exact bytes. Hash the bytes with SHA-256, then sign this UTF-8 canonical message using HMAC-SHA256 and the service secret. Use one LF between lines and no trailing LF:

```text
v1
n8n
<tenant-uuid>
POST
/internal/v1/automation/notifications
<unix-seconds>
<idempotency-key>
<lowercase-sha256-of-raw-body>
```

Set `X-Signature` to `sha256=` followed by the lowercase hexadecimal HMAC digest. Reuse the same idempotency key and byte-identical body for retries during the 24-hour validity window; use a new key for each new logical notification. Never include the secret in workflow exports, logs, or execution data.

## API and testing

- OpenAPI UI: `http://localhost:8000/docs`
- Backend tests: from `backend\`, run `pytest`
- Backend lint: from `backend\`, run `ruff check . --output-format=full`
- Backend formatting check: from `backend\`, run `ruff format --check .`
- Frontend scripts: from `frontend\`, `npm run dev`, `npm run build`, `npm run start`, and `npm run lint`. No frontend test script is defined in `package.json`.

Some cross-tenant tests require a separately configured test database and application database role. Do not run database tests or migrations against production or shared data. The Setup Guide describes the repository's test database expectations and the limits of the checked-in setup.

## Known gaps

- No dashboard API or dashboard UI is registered.
- There is no task listing/management API or task UI, although task records can be created by backend assessment logic.
- The internal notification endpoint persists notifications, but there is no user-facing notification list/read API or inbox.
- There is no user-facing integration connection/configuration API or screen. Provider webhook endpoints do not provide self-service integration setup.
- Platform-admin routes and screens are not implemented.
- Conversation analysis is integrated; a separate message-classification function is not wired into the main conversation flow.
- Outbound message requests are persisted as queued and are not sent by a provider in this repository.
- MFA setup/verification screens and a complete tenant-selection flow are not connected in the frontend.
- The lead list/create UI has integration gaps documented in the User Guide; use the API documentation for supported backend operations.

## Documentation

- [Setup Guide](docs/SETUP_GUIDE.md)
- [User Guide](docs/USER_GUIDE.md)
- [API contract](API_CONTRACT.md)
- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Database schema](DATABASE_SCHEMA.md)
- [Product requirements](PRODUCT_REQUIREMENTS.md)
