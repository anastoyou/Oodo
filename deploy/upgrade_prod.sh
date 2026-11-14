#!/usr/bin/env bash
# Safe Linux VPS release upgrade: back up DB, pull upstream odoo/, upgrade addons/, restart stack
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${APP_ROOT}/.env"

DB_NAME="${1:-${ODOO_DB:-localhost}}"
MODULES="${2:-custom_erp,custom_store}"

if [ -n "$(git -C "${APP_ROOT}/odoo" status --porcelain)" ]; then
    echo "[ERROR] ${APP_ROOT}/odoo has uncommitted edits. Aborting." >&2
    exit 1
fi

"${APP_ROOT}/deploy/backup_db.sh" "${DB_NAME}"
git -C "${APP_ROOT}/odoo" pull --ff-only

docker compose -f "${APP_ROOT}/docker-compose.prod.yml" run --rm --no-deps odoo \
    -d "${DB_NAME}" -u "${MODULES}" --stop-after-init --no-http

docker compose -f "${APP_ROOT}/docker-compose.prod.yml" up -d odoo nginx
echo "[SUCCESS] Production upgraded and restarted cleanly."

