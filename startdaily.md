# Daily Startup (Windows PowerShell)

Run the commands below in the VS Code integrated terminal. They assume the repository is open at `T:\My code\AI Sales Assist` and Docker Desktop is running.

If a terminal is not at the repository root, run:

```powershell
Set-Location 'T:\My code\AI Sales Assist'
```

## One-time setup

### 1. Create your local settings file

Check whether `.env` already exists:

```powershell
Test-Path .env
```

If the result is `False`, create it:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and replace example secrets with local development values. Never overwrite an existing `.env` or use development secrets in production.

### 2. Install frontend packages

From the repository root:

```powershell
npm --prefix frontend ci
```

This installs the exact dependency versions recorded in the frontend lockfile. Run it for initial setup or when dependencies change.

### 3. Create local database tables

Start the services as described in **Daily startup**, then list the Alembic migration heads:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml run --build --rm backend alembic heads
```

Continue only if the output shows exactly one migration entry marked `(head)`. If it shows multiple heads or an error, stop and investigate; do not merge revisions as a workaround.

Apply migrations only to your local development database:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml run --build --rm backend alembic upgrade head
```

Compose does not apply migrations automatically. Run this migration step for a new local database or after pulling code that adds migrations—not as part of routine daily startup.

### 4. Optional: create demo accounts

Signup can create your own account. To create the development demo accounts instead, run this once after migrations, only against a local development database:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml exec backend python -m app.scripts.seed
```

The seed script creates demo companies and users such as `admin@acme.test`. Its default password is documented in `backend\app\scripts\seed.py`; use seeded accounts only for local development.

## Daily startup

### Terminal 1: database, backend, and email inbox

From the repository root:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml up -d db mailpit backend
```

This starts PostgreSQL, FastAPI, and Mailpit. The backend waits for PostgreSQL to become healthy. Check service status:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml ps
```

Check the backend:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

The expected response has `status` set to `ok`. If the health check fails, wait a few seconds and retry. If it still fails, inspect the logs:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml logs --tail 100 backend
```

### Terminal 2: frontend

Open a second VS Code terminal at the repository root:

```powershell
npm --prefix frontend run dev
```

Leave this terminal running and open `http://localhost:3000`.

## Useful addresses

| What | Address |
|---|---|
| App | http://localhost:3000 |
| Backend health | http://localhost:8000/health |
| API docs | http://localhost:8000/docs |
| Local email inbox | http://localhost:8025 |

## When something looks wrong

| Problem | What to do |
|---|---|
| Docker says it cannot connect | Start Docker Desktop, wait until it is running, then retry. |
| Backend health check fails | Run `docker compose --env-file .env -f infrastructure\docker-compose.yml logs --tail 100 backend` and check the backend error. |
| See running services | Run `docker compose --env-file .env -f infrastructure\docker-compose.yml ps`. |
| A page says “not found” or “request could not be completed” | Check the browser Network request URL, status, and response body. Confirm the backend health check and API route in `http://localhost:8000/docs`; restarting Next.js alone may not fix a backend 404. |
| Changed `backend\requirements.txt` | Rebuild and restart the backend: `docker compose --env-file .env -f infrastructure\docker-compose.yml up -d --build backend`. |
| Changed backend `.env` values used by Compose | Recreate the backend: `docker compose --env-file .env -f infrastructure\docker-compose.yml up -d backend`. |
| Changed `frontend\next.config.ts` or frontend environment values | Stop the frontend with `Ctrl+C`, then run `npm --prefix frontend run dev` again. |
| Frontend packages are missing | Run `npm --prefix frontend ci` from the repository root. |

Backend source changes reload automatically in the development container.

## Optional: AI and automation services

Only start these if you are working on AI scoring or n8n workflows:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml up -d worker dispatcher n8n_db n8n
```

## Finish for the day

Stop the Compose services:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml stop
```

This stops services but keeps the database volume. Press `Ctrl+C` in the frontend terminal to stop Next.js. Do not use `down -v` for routine shutdown; it removes Compose volumes, including local database data.
