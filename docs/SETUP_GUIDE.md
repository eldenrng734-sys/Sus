# SUS Setup Guide

This guide covers a local development setup on Windows using PowerShell. It is based on the checked-in backend, frontend, and Docker Compose configuration. The repository does not include default seed users.

## 1. Prerequisites

- Git.
- Docker Desktop with Docker Compose v2, for the bundled PostgreSQL, backend, and Mailpit services.
- Python 3.12 if running the backend or Alembic directly on Windows. The backend Dockerfile uses Python 3.12.
- Node.js and npm for the Next.js frontend. The repository does not specify a required Node.js version.

The Compose file does not run the frontend or n8n. The frontend is started separately. No n8n workflow is included.

## 2. Clone the repository

```powershell
git clone <repository-url> Sus
Set-Location Sus
```

Use your organization's repository URL in place of `<repository-url>`.

## 3. Configure the environment

Create a local environment file from the template:

```powershell
Copy-Item .env.example .env
```

Edit `.env` before starting services. The checked-in template contains populated example secret fields: replace every populated secret with a fresh, development-only value. Do not reuse example secrets, put real credentials in documentation, or use local development secrets in shared or production environments.

The settings class reads the repository-root `.env`. Docker Compose also reads it for variable substitution when invoked with `--env-file .env`.

| Purpose | Setting names used by the application or Compose |
| --- | --- |
| Compose PostgreSQL initialization | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| Database connections | `DATABASE_URL`, optional `MIGRATION_DATABASE_URL` |
| Application/authentication | `APP_ENV`, `JWT_SECRET_KEY`, `MFA_ENCRYPTION_KEY`, `COOKIE_SECURE`, `ALLOWED_ORIGINS` |
| Email and links | `SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM`, `FRONTEND_BASE_URL` |
| Conversation analysis | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS` |
| Assessment and review | `AI_REVIEW_CONFIDENCE_THRESHOLD` |
| Webhook/service authentication | `META_APP_SECRET`, `WHATSAPP_APP_SECRET`, `WEBHOOK_VERIFY_TOKEN`, `N8N_SERVICE_SECRET` |
| Separate LLM client | `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_INPUT_PRICE_PER_MTOK`, `LLM_OUTPUT_PRICE_PER_MTOK` |

These settings are defined in `backend\app\core\config.py`; Compose also supplies some service settings directly. The checked-in `.env.example` is not a complete declaration of every runtime setting, and some template fields are not currently wired to the application. Check the settings class and Compose configuration rather than assuming an unrecognized template field has an effect.

Important: Compose uses the root `.env` for interpolation but does not mount it into the backend container. The backend container receives only the variables explicitly listed in `infrastructure\docker-compose.yml` (and the Compose-defined Mailpit settings). For example, provider webhook secrets and AI provider settings are not all forwarded by the current Compose file. Do not assume that setting a value in the root `.env` makes it available inside the container; verify the active runtime configuration before using those integrations.

For Compose, `DATABASE_URL` must address PostgreSQL by the service hostname `db` and container port `5432`. For a backend run directly on Windows, use `localhost` and the published port `5433`; set `MIGRATION_DATABASE_URL` the same way if it is configured. A URL may use this shape, with your own local credentials and database:

```text
postgresql+psycopg://<user>:<password>@localhost:5433/<database>
```

When running the backend directly on Windows with Compose Mailpit, set `SMTP_HOST` to `localhost` and `SMTP_PORT` to `1025`. The Compose backend service is configured to reach Mailpit at `mailpit:1025`.

## 4. Start PostgreSQL

From the repository root:

```powershell
docker --version
docker compose version
docker compose --env-file .env -f infrastructure\docker-compose.yml up -d db
docker compose --env-file .env -f infrastructure\docker-compose.yml ps
```

The database service is named `db`, uses PostgreSQL 16, and publishes `127.0.0.1:5433` on the host. Its data is stored in the Compose `pgdata` named volume. Compose initializes the database named by `POSTGRES_DB`; it does not automatically create the separate test database used by cross-tenant tests.

Mailpit is included in the Compose file. The web interface is at `http://localhost:8025`; its SMTP port is `1025`.

## 5. Apply database migrations

Compose does not run Alembic automatically. After PostgreSQL is healthy, run:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml run --build --rm backend alembic upgrade head
```

This uses the backend container and the Compose database hostname. Alembic uses `MIGRATION_DATABASE_URL` when configured; otherwise it uses `DATABASE_URL`. Use only a local development database for this command.

If running Alembic on the host instead, install the backend dependencies first, configure the host database URL, then run from `backend\`:

```powershell
Set-Location backend
python -m alembic upgrade head
Set-Location ..
```

Do not run migrations against a shared or production database as part of local setup.

## 6. Install and start the backend

### Option A: Docker Compose

From the repository root:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml up --build
```

This starts the Compose services, including PostgreSQL, the backend, and Mailpit. The backend is served on port `8000`. Keep the terminal open while using the services.

### Option B: Run the backend on Windows

In a new PowerShell terminal from the repository root:

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Configure `.env` for host access before starting: PostgreSQL must use `localhost:5433`, and Mailpit must use `localhost:1025` if email delivery to the local capture service is needed. If PowerShell blocks virtual-environment activation, follow your machine's approved execution-policy guidance; do not weaken system policy globally just for this project.

## 7. Install and start the frontend

In another PowerShell terminal from the repository root:

```powershell
Set-Location frontend
npm install
npm run dev
```

The frontend is served at `http://localhost:3000`. `frontend\next.config.ts` rewrites `/api/v1/*` requests to the backend at `http://localhost:8000/api/v1/*`.

Available frontend scripts are `dev`, `build`, `start`, and `lint`. There is no frontend test script in `frontend\package.json`.

## 8. Verify the application

- Backend API documentation: `http://localhost:8000/docs`
- Backend OpenAPI schema: `http://localhost:8000/openapi.json`
- Frontend: `http://localhost:3000`
- Mailpit: `http://localhost:8025`
- Compose status: `docker compose --env-file .env -f infrastructure\docker-compose.yml ps`

The API documentation loads only when the backend is running. No default seed account is created; signup creates a tenant and its initial admin, while later users join through an administrator-created invitation.

## 9. Run tests and lint

From the repository root, run backend tests:

```powershell
Set-Location backend
pytest
```

Backend lint and formatting checks:

```powershell
ruff check . --output-format=full
ruff format --check .
```

Frontend lint:

```powershell
Set-Location ..\frontend
npm run lint
```

The cross-tenant database tests require a separately provisioned, migrated test database named with a `*_test` suffix. They read `TEST_DATABASE_URL` (or test-specific `POSTGRES_*` settings) for an owner connection and require `TEST_APP_DATABASE_URL` for the non-owner `crm_app` role used to exercise RLS. Both URLs must point only to a disposable test database. The Compose service initializes the configured development database; it does not provision this test database or its application role. The repository's test skip messages refer to a local migration script that is not present in the repository, so this guide does not provide an unverified provisioning command. Without the required test database, those database-backed tests may be skipped; report that limitation rather than treating them as passed.

## 10. Common issues

### The backend cannot connect to PostgreSQL

- Confirm `docker compose ... ps` shows `db` healthy.
- A containerized backend uses `db:5432`; a host-run backend uses `localhost:5433`.
- Confirm `.env` is in the repository root and that the Compose command includes `--env-file .env`.
- Confirm the database name and credentials in the connection URL match the Compose initialization settings.

### Alembic cannot connect or apply migrations

- Run the migration command from the repository root after PostgreSQL is healthy.
- Check that `MIGRATION_DATABASE_URL`, if set, points to the same local database intended for migration; it takes precedence over `DATABASE_URL`.
- Do not resolve permissions errors by using a production or shared database. Use the local migration credentials and seek project-owner guidance if the local database role is not permitted to migrate.

### The frontend cannot reach the API

- Start the backend on port `8000`.
- Start the frontend on port `3000`.
- Confirm the rewrite in `frontend\next.config.ts` still targets `http://localhost:8000`.
- The current frontend has incomplete lead-list/create wiring; see the [User Guide](USER_GUIDE.md). The API documentation is the source of truth for backend operations.

### Signup or login does not complete

- Check backend logs for the explicit authentication error.
- Email verification is required by the authentication flow, but signup does not automatically send a verification email in the current implementation.
- Admin accounts require MFA at the backend. The frontend MFA setup/verification screens are not connected; use the documented API routes in `/docs` where available.

### AI analysis is unavailable

Conversation analysis requires a valid `OPENAI_API_KEY` and uses `OPENAI_MODEL` when configured. Without a provider key, the analysis endpoint cannot make a live provider request. Do not paste credentials into issue reports or logs.

### Cross-tenant tests are skipped

Configure both test database connections described above and ensure the database is migrated. The checked-in test configuration does not provide a complete database-provisioning procedure. Never point either test URL at a non-test database.

## 11. Further documentation

- [README](../README.md)
- [User Guide](USER_GUIDE.md)
- [API contract](../API_CONTRACT.md)
- [Architecture](../ARCHITECTURE.md)
- [Security](../SECURITY.md)
