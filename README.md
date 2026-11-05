# AI Sales Assist

A small CRM service built with FastAPI and PostgreSQL.

## Stack

- **FastAPI** – HTTP API (`main.py`)
- **PostgreSQL 16** – database, via Docker Compose
- **Docker** – containerized API + database

## Project layout

```
main.py             FastAPI app (health endpoint at /health)
requirements.txt    Python dependencies
Dockerfile          Container image for the API
docker-compose.yml  API + Postgres services
```

## Run locally

### With Docker Compose (recommended)

```bash
docker compose up --build
```

The API is available at http://localhost:8000/health and returns `{"status": "ok"}`.

### Without Docker

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Configuration

The Compose file ships development defaults (database name `brain`, password
`postgres`). Never use these in production — set real values through environment
variables or a `.env` file, which is git-ignored.

## Status

Early scaffold: only the health endpoint exists so far.

# AI Sales Assistant CRM

## Run locally
1. `Copy-Item .env.example .env`
2. `docker compose -f infrastructure/docker-compose.yml --env-file .env up --build`
3. Open http://localhost:8000/docs

## Test locally (from the backend folder)
`ruff check .` then `ruff format --check .` then `pytest`
