#!/usr/bin/env bash
# Load the standard EOEPCA sentinel-2-iceland collection into pgSTAC.
#
# Defaults match docker-compose database credentials. Override with PG* env vars
# or EOAPI_COLLECTIONS_FILE / EOAPI_ITEMS_FILE.
#
# Examples:
#   ./.github/workflows/ingest.sh
#   docker compose --profile ingest run --rm ingest
#   ./.github/workflows/ingest.sh --wipe-db
#   ./.github/workflows/ingest.sh --wipe-pgdata-only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECTION_DIR="${EOAPI_COLLECTION_DIR:-${SCRIPT_DIR}/data/sentinel-2-iceland}"
COLLECTIONS_FILE="${EOAPI_COLLECTIONS_FILE:-${COLLECTION_DIR}/collections.json}"
ITEMS_FILE="${EOAPI_ITEMS_FILE:-${COLLECTION_DIR}/items.json}"

PGUSER="${PGUSER:-username}"
PGPASSWORD="${PGPASSWORD:-password}"
PGHOST="${PGHOST:-database}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-postgis}"
DSN="${PGDSN:-postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}}"

run_pypgstac() {
  if [ -f pyproject.toml ] && command -v uv >/dev/null 2>&1; then
    uv run pypgstac "$@"
  elif command -v pypgstac >/dev/null 2>&1; then
    pypgstac "$@"
  elif command -v uv >/dev/null 2>&1; then
    uv pip install --system 'pypgstac[psycopg]==0.9.9'
    pypgstac "$@"
  else
    pip install --quiet 'pypgstac[psycopg]==0.9.9'
    pypgstac "$@"
  fi
}

wipe_pgdata() {
  if [ ! -d .pgdata ]; then
    return 0
  fi

  echo "Wiping PostgreSQL data directory (.pgdata)..."
  # Files are owned by the postgres container user; remove them as root.
  docker run --rm -v "$(pwd):/workspace" -w /workspace alpine \
    sh -c 'rm -rf .pgdata && mkdir .pgdata'
}

WIPE_DB=false
WIPE_PGDATA_ONLY=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --wipe-db)
      WIPE_DB=true
      shift
      ;;
    --wipe-pgdata-only)
      WIPE_PGDATA_ONLY=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [ "$WIPE_PGDATA_ONLY" = true ]; then
  wipe_pgdata
  exit 0
fi

if [ "$WIPE_DB" = true ]; then
  echo "Stopping services and wiping database volume..."
  COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.mock-oidc.yml}"
  export COMPOSE_FILE
  docker compose down
  wipe_pgdata
  docker compose up -d database
  PGHOST="${MY_DOCKER_IP:-127.0.0.1}"
  PGPORT=5439
  export PGHOST PGPORT
  DSN="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
  run_pypgstac pgready --dsn "$DSN"
  docker compose up -d
fi

for file in "$COLLECTIONS_FILE" "$ITEMS_FILE"; do
  if [ ! -f "$file" ]; then
    echo "File not found: $file" >&2
    exit 1
  fi
done

echo "Using collections file: $COLLECTIONS_FILE"
echo "Using items file: $ITEMS_FILE"
echo "Using database: postgresql://${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"

run_pypgstac pgready --dsn "$DSN"

echo "Loading collections..."
run_pypgstac load collections "$COLLECTIONS_FILE" --dsn "$DSN" --method insert_ignore

echo "Loading items..."
run_pypgstac load items "$ITEMS_FILE" --dsn "$DSN" --method insert_ignore

echo "Ingestion complete."
