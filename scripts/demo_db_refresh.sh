#!/usr/bin/env bash
# Reset the demo database and reload the standard sample collection.

set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LOCK_FILE="${EOAPI_DEMO_REFRESH_LOCK_FILE:-/tmp/eoapi-demo-refresh.lock}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.mock-oidc.yml:docker-compose.metrics.yml:infrastructure/docker-compose.hetzner.yml}"
EOAPI_GRAFANA_ROOT_URL="${EOAPI_GRAFANA_ROOT_URL:-https://${EOAPI_DOMAIN:?set EOAPI_DOMAIN}/monitoring/}"

export COMPOSE_FILE EOAPI_GRAFANA_ROOT_URL

cd "$ROOT_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another demo refresh is already running; exiting."
  exit 0
fi

echo "Stopping eoAPI demo stack..."
docker compose down

echo "Wiping PostgreSQL data directory..."
bash .github/workflows/ingest.sh --wipe-pgdata-only

echo "Starting eoAPI demo stack..."
docker compose pull --ignore-pull-failures
docker compose up -d --build --remove-orphans

echo "Loading standard demo data..."
docker compose --profile ingest run --rm ingest

echo "Restarting vector service after ingest..."
docker compose restart vector

echo "Demo database refresh complete."
