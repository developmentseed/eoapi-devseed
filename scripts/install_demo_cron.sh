#!/usr/bin/env bash
# Install host cron for refreshing the public demo database at midnight Eastern.

set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-$(pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.mock-oidc.yml:docker-compose.metrics.yml:infrastructure/docker-compose.hetzner.yml}"
EOAPI_GRAFANA_ROOT_URL="${EOAPI_GRAFANA_ROOT_URL:-https://${EOAPI_DOMAIN:?set EOAPI_DOMAIN}/monitoring/}"

: "${ACME_EMAIL:?set ACME_EMAIL}"

if ! command -v crontab >/dev/null 2>&1; then
  echo "crontab is not installed. Install cron before enabling the demo refresh schedule." >&2
  exit 1
fi

cron_file="$(mktemp)"
existing_cron="$(mktemp)"
if ! crontab -l > "$existing_cron" 2>/dev/null; then
  : > "$existing_cron"
fi

sed '/# eoapi-demo-refresh begin/,/# eoapi-demo-refresh end/d' \
  "$existing_cron" \
  > "$cron_file"

cat >> "$cron_file" <<CRON
# eoapi-demo-refresh begin
CRON_TZ=America/New_York
0 0 * * * cd '${DEPLOY_PATH}' && EOAPI_DOMAIN='${EOAPI_DOMAIN}' ACME_EMAIL='${ACME_EMAIL}' COMPOSE_FILE='${COMPOSE_FILE}' EOAPI_GRAFANA_ROOT_URL='${EOAPI_GRAFANA_ROOT_URL}' bash scripts/demo_db_refresh.sh >> demo-refresh.log 2>&1
# eoapi-demo-refresh end
CRON

crontab "$cron_file"
rm "$cron_file" "$existing_cron"

crontab -l | sed -n '/# eoapi-demo-refresh begin/,/# eoapi-demo-refresh end/p'
