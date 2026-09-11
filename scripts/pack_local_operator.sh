#!/bin/sh
# T143 — Layer-1 local operator pack builder.
#
# Recreates dist/aegis-local-operator/ from the repo root so the
# local operator can start without git, Hermes, or VS Code.  The pack
# contains only the runtime tree needed by scripts/start_operator.sh:
# app/, core/, agents/, scripts/start_operator.sh,
# scripts/reveal_export.sh, pyproject.toml, uv.lock, and the app.html
# the server serves.  It does not contain builder directives, tenant
# data, .git, .venv, _directive.txt, task_instruction.txt, .kms/,
# $HOME/.aegis, or Hermes session files.
#
# Exit 0 on success; non-zero on any copy failure.  Prints the output
# folder path and stops.  Does not bind a network port, does not curl
# a cloud host, does not launch a browser.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

OUT="$REPO_ROOT/dist/aegis-local-operator"

# --- recreate the output folder ------------------------------------------
rm -rf "$OUT"
mkdir -p "$OUT/scripts"
mkdir -p "$OUT/desktop/macos/Aegis.app/Contents/Resources"

# --- copy the runtime tree ------------------------------------------------
# app/ — the FastAPI server the operator starts.
cp -R "$REPO_ROOT/app" "$OUT/app"
# core/ — imported by app.server at module load.
cp -R "$REPO_ROOT/core" "$OUT/core"
# agents/ — lazily imported by the /propose route.
cp -R "$REPO_ROOT/agents" "$OUT/agents"
# scripts/start_operator.sh — the sole daily start path.
cp "$REPO_ROOT/scripts/start_operator.sh" "$OUT/scripts/start_operator.sh"
# scripts/reveal_export.sh — called by the signed-export reveal route.
cp "$REPO_ROOT/scripts/reveal_export.sh" "$OUT/scripts/reveal_export.sh"
# pyproject.toml + uv.lock — install from lockfile.
cp "$REPO_ROOT/pyproject.toml" "$OUT/pyproject.toml"
cp "$REPO_ROOT/uv.lock" "$OUT/uv.lock"
# app.html — the operator page served at the root.
cp "$REPO_ROOT/desktop/macos/Aegis.app/Contents/Resources/app.html" \
   "$OUT/desktop/macos/Aegis.app/Contents/Resources/app.html"

# --- strip bytecode caches and any tenant data ---------------------------
find "$OUT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$OUT" -type d -name .pytest_cache -prune -exec rm -rf {} +
find "$OUT" -type d -name .mypy_cache -prune -exec rm -rf {} +
find "$OUT" -type d -name .ruff_cache -prune -exec rm -rf {} +

# --- keep the start script executable -------------------------------------
chmod +x "$OUT/scripts/start_operator.sh"
chmod +x "$OUT/scripts/reveal_export.sh"

# --- root start_operator.sh (thin wrapper into scripts/) ------------------
# The pack root gets its own executable start path so the operator can
# run ./start_operator.sh directly from the copied folder.
cat > "$OUT/start_operator.sh" <<'ROOT_START_EOF'
#!/bin/sh
# T145 — thin root wrapper that execs scripts/start_operator.sh.
#
# Same env: AEGIS_DATA_DIR defaults to $HOME/.aegis, binds 127.0.0.1:8741,
# does not launch a browser.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/scripts/start_operator.sh" "$@"
ROOT_START_EOF
chmod +x "$OUT/start_operator.sh"

# --- entitlement.example.json (dummy, pack-only) --------------------------
# A dummy example file so the operator can copy it to
# $HOME/.aegis/entitlement.json and replace the fake values.  The engine
# never loads this example — the live path stays
# AEGIS_DATA_DIR/entitlement.json.
cat > "$OUT/entitlement.example.json" <<'ENTITLEMENT_EOF'
{
  "tenant_id": "example-tenant",
  "tier": "echo",
  "expires_at": null,
  "signature_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
}
ENTITLEMENT_EOF

# --- INSTALL.md (Now steps only) -----------------------------------------
cat > "$OUT/INSTALL.md" <<'INSTALL_EOF'
# Aegis local operator — install

## Now

1. Install Python 3.11.
2. Copy this folder into the operator account `$HOME` (for example
   `$HOME/aegis-local-operator`).  Do not copy into `/Users/Shared`
   unless that account can write there.
3. Create a venv: `python3.11 -m venv .venv`
4. Install from the lockfile: `uv sync` (or `pip install -e .`)
5. Start the engine: `./start_operator.sh`
6. Open `http://127.0.0.1:8741/` yourself in a browser.

The data dir is `$HOME/.aegis` in that account.  There is no cloud URL
and no Windows package.

## Optional local entitlement

The pack ships `entitlement.example.json` — a dummy file with fake values.
If you want a local tier file, copy it to `$HOME/.aegis/entitlement.json`
on this laptop and replace the dummy `tenant_id`, `tier`, `expires_at`, and
`signature_sha256` with real values.  When the file is missing the engine
stays Echo-limited; no file is required.
INSTALL_EOF

echo "$OUT"
