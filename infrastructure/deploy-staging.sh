#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; source .env.staging; set +a
DC="docker compose -f infrastructure/docker-compose.staging.yml --env-file .env.staging"

git fetch origin
git checkout dev
git merge --ff-only origin/dev

$DC up -d --build db
$DC run --rm backend alembic upgrade head

$DC exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -v pw="$CRM_APP_PASSWORD" <<'SQL'
ALTER ROLE crm_app WITH LOGIN PASSWORD :'pw';
SQL

$DC up -d --build backend

$DC exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA \
  -c "SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname='crm_app'" | grep -qx t

sleep 5
curl -fsS http://localhost:8000/health
echo "deploy ok"
