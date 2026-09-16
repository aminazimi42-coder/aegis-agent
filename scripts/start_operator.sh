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

# --- python3 preflight (T177) -------------------------------------------
# Require a usable python3 on PATH (prefer 3.11 when present).
PY3=""
if command -v python3.11 >/dev/null 2>&1; then
    PY3="$(command -v python3.11)"
elif command -v python3 >/dev/null 2>&1; then
    PY3="$(command -v python3)"
fi
if [ -z "$PY3" ]; then
    echo "start_operator: python3 not found — install Python 3.11 first."
    exit 1
fi

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

# --- single-instance lock (T163) ----------------------------------------
# Write a lock file under AEGIS_DATA_DIR that records pid and port.
# A second process that finds the port already bound must exit non-zero
# with a typed English error.  Do not kill the first process.  Do not
# bind another port.  A stale lock from a dead pid may be replaced.
LOCK_FILE="$AEGIS_DATA_DIR/aegis-engine.lock"

# Clean up the lock on exit so a normal shutdown does not leave a stale lock.
cleanup_lock() {
    rm -f "$LOCK_FILE" 2>/dev/null || true
}
trap cleanup_lock EXIT INT TERM

# If a lock file exists, check whether the recorded pid is still alive.
if [ -f "$LOCK_FILE" ]; then
    LOCKED_PID=""
    LOCKED_PORT=""
    # Read the pid and port from the lock file (one key per line).
    while IFS='=' read -r key val; do
        case "$key" in
            pid) LOCKED_PID="$val" ;;
            port) LOCKED_PORT="$val" ;;
        esac
    done < "$LOCK_FILE" 2>/dev/null || true
    # If the recorded pid is still alive and the port is still bound,
    # the engine is running — exit with a typed English error.
    if [ -n "$LOCKED_PID" ] && kill -0 "$LOCKED_PID" 2>/dev/null \
       && [ "$LOCKED_PORT" = "$PORT" ]; then
        echo "start_operator: port 8741 already in use"
        exit 1
    fi
    # Stale lock — the pid is dead.  Replace the lock file below.
    rm -f "$LOCK_FILE" 2>/dev/null || true
fi

if nc -z "$HOST" "$PORT" 2>/dev/null \
   || python3 -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('$HOST',$PORT))==0 else 1)" 2>/dev/null; then
    echo "start_operator: port 8741 already in use"
    exit 1
fi

# Write the lock file with the current pid and port.
echo "pid=$$" > "$LOCK_FILE"
echo "port=$PORT" >> "$LOCK_FILE"

# --- entitlement preflight (T191) ----------------------------------------
# Report the local entitlement state before bind.  Missing or expired
# does not crash — the engine still starts Echo-limited.  Valid continues
# to bind normally.  Three distinct typed lines for three states.
ENT_REASON="$("$PY" -c "
from core.entitlement import load
r = load()
print(r.get('reason', ''))
" 2>/dev/null || echo "")"
if [ -z "$ENT_REASON" ]; then
    echo "start_operator: entitlement valid"
else
    case "$ENT_REASON" in
        missing_file)
            echo "start_operator: entitlement missing"
            ;;
        expired)
            echo "start_operator: entitlement expired"
            ;;
        *)
            echo "start_operator: entitlement degraded ($ENT_REASON)"
            ;;
    esac
fi

# --- engine start --------------------------------------------------------
echo "Aegis engine — data dir: $AEGIS_DATA_DIR"
echo "Aegis engine — URL: http://127.0.0.1:8741/"

exec "$PY" -m uvicorn app.server:create_app --factory --host "$HOST" --port "$PORT"
