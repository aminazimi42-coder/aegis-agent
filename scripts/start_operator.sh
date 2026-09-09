#!/bin/sh
# T128 — operator start bundle.
#
# Starts the local Aegis engine (same uvicorn bind as scripts/run_local.sh)
# and prints one English line pointing the operator at the engine URL.
# The .app bundle is a wrapper around this script — it is not a store-signed
# product and requires this repo (or a copied bundle) to run.
#
# Exit non-zero if the venv or the operator app.html is missing.
# Never curls a cloud host; never binds 0.0.0.0.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- prerequisites -------------------------------------------------------
PY="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "start_operator: .venv/bin/python not found — create the venv first." >&2
    exit 1
fi

APP_HTML="$REPO_ROOT/desktop/macos/Aegis.app/Contents/Resources/app.html"
if [ ! -f "$APP_HTML" ]; then
    echo "start_operator: operator app.html not found — bundle incomplete." >&2
    exit 1
fi

# --- engine start (same bind as run_local.sh / uvicorn) ------------------
PORT="${AEGIS_PORT:-8741}"
HOST="127.0.0.1"
export AEGIS_DATA_DIR="${AEGIS_DATA_DIR:-$HOME/.aegis}"

echo "Aegis engine starting on http://${HOST}:${PORT} — the .app is a wrapper; use this repo or a copied bundle."
exec "$PY" -m uvicorn app.server:create_app --factory --host "$HOST" --port "$PORT"
