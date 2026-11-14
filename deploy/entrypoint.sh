#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/app"
export ODOO_ENV="${ODOO_ENV:-production}"

echo "Generating production runtime configuration via scripts/odoo_ctl.py..."
python3 - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/opt/app/scripts")
import odoo_ctl

cfg = odoo_ctl.load_env(Path("/opt/app"))
conf = odoo_ctl.write_runtime_conf(Path("/opt/app"), cfg, prod=True)
print(f"Runtime config written to {conf}")
PY

exec python3 "${APP_ROOT}/odoo/odoo-bin" -c "${APP_ROOT}/data/odoo.runtime.conf" "$@"

