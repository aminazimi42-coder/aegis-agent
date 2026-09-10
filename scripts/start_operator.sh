#!/bin/sh
# T140 — sole daily operator start path.
#
# Starts the local Aegis engine: exports AEGIS_DATA_DIR, uses the project
# venv (.venv), and binds 127.0.0.1:8741.  Prints one English block on
# start and one honest line on any failure.  Does not launch a browser.
#
# Exit non-zero if the venv or the operator app.html is missing, or if
# port 8741 is already bound.  Never curls a cloud host; never binds
# 0.0.0.0; never kills a stranger process.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# --- prerequisites -------------------------------------------------------
PY="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "start_operator: .venv/bin/python not found — create the venv first."
    exit 1
fi

APP_HTML="$REPO_ROOT/desktop/macos/Aegis.app/Contents/Resources/app.html"
if [ ! -f "$APP_HTML" ]; then
    echo "start_operator: operator app.html not found — bundle incomplete."
    exit 1
fi

# --- data dir -------------------------------------------------------------
export AEGIS_DATA_DIR="${AEGIS_DATA_DIR:-$HOME/.aegis}"
mkdir -p "$AEGIS_DATA_DIR"

# --- port check (do not kill a stranger process) -------------------------
HOST="127.0.0.1"
PORT="8741"
if nc -z "$HOST" "$PORT" 2>/dev/null \
   || python3 -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('$HOST',$PORT))==0 else 1)" 2>/dev/null; then
    echo "start_operator: the engine is already up at http://127.0.0.1:8741/."
    exit 1
fi

# --- engine start --------------------------------------------------------
echo "Aegis engine — data dir: $AEGIS_DATA_DIR"
echo "Aegis engine — URL: http://127.0.0.1:8741/"
echo "Aegis engine — Safari is opened by the operator, not by this script."

exec "$PY" -m uvicorn app.server:create_app --factory --host "$HOST" --port "$PORT"
