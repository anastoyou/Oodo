#!/usr/bin/env bash
# Daily automated PostgreSQL + filestore backup on Linux VPS production
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${APP_ROOT}/.env"

DB_NAME="${1:-${ODOO_DB:-localhost}}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${APP_ROOT}/backups"
STAGE_DIR="$(mktemp -d "${BACKUP_DIR}/.tmp_prod_${STAMP}_XXXXXX")"
OUT_ZIP="${BACKUP_DIR}/${DB_NAME}_${STAMP}.zip"

cleanup() { rm -rf "${STAGE_DIR}"; }
trap cleanup EXIT

docker exec -e "PGPASSWORD=${DB_PASSWORD}" odoo-prod-db \
    pg_dump -U "${DB_USER}" --no-owner "${DB_NAME}" > "${STAGE_DIR}/dump.sql"

if [ -d "${APP_ROOT}/data/filestore/${DB_NAME}" ]; then
    cp -a "${APP_ROOT}/data/filestore/${DB_NAME}" "${STAGE_DIR}/filestore"
fi

python3 - <<PY
import json, zipfile
from pathlib import Path

stage = Path("${STAGE_DIR}")
out = Path("${OUT_ZIP}")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(stage / "dump.sql", "dump.sql")
    manifest = {"odoo_dump": "1", "db_name": "${DB_NAME}", "major_version": "${ODOO_BRANCH:-20.0}"}
    zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    fs = stage / "filestore"
    if fs.is_dir():
        for p in sorted(fs.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(stage).as_posix())
PY

find "${BACKUP_DIR}" -maxdepth 1 -name "${DB_NAME}_*.zip" -mtime +30 -delete
echo "Backup saved: ${OUT_ZIP}"

