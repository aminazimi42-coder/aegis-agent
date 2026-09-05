#!/bin/sh
# T87 — Install the aegis user command outside the git tree.
#
# This script creates a virtualenv under PREFIX (default
# $HOME/.local/aegis) and a thin launcher under BIN (default
# $HOME/.local/bin/aegis).  It never writes into the repository
# working tree.
#
# Usage:
#   sh scripts/install_local.sh
#
# Environment overrides:
#   AEGIS_PREFIX  — installation prefix (default: $HOME/.local/aegis)
#   AEGIS_BIN     — bin directory for the launcher (default: $HOME/.local/bin)

set -e

PREFIX="${AEGIS_PREFIX:-$HOME/.local/aegis}"
BIN="${AEGIS_BIN:-$HOME/.local/bin}"

# --- locate repo root relative to this script -----------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- create directories ---------------------------------------------------
mkdir -p "$PREFIX"
mkdir -p "$BIN"

# --- create venv ----------------------------------------------------------
python3 -m venv "$PREFIX/venv"

# --- install the repo (editable) into the venv -----------------------------
"$PREFIX/venv/bin/pip" install -e "$REPO_ROOT"

# --- write the launcher ---------------------------------------------------
cat > "$BIN/aegis" <<'LAUNCHER'
#!/bin/sh
exec "${AEGIS_PREFIX:-$HOME/.local/aegis}/venv/bin/python" -m core.twin_local "$@"
LAUNCHER
chmod +x "$BIN/aegis"

echo "installed: $BIN/aegis (venv: $PREFIX/venv)"
