#!/bin/sh
# T149 — Layer-3 Mac installer folder builder.
#
# Builds dist/AegisOperator-mac/ — a folder a stranger can copy to
# another Mac, run Install.command, and later start with the same
# start_operator.sh.  The installer folder is separate from the git
# repo and does not contain .git, _directive.txt, task_instruction.txt,
# .kms, or a live $HOME/.aegis.
#
# First runs scripts/pack_local_operator.sh so dist/aegis-local-operator
# is fresh, then copies the packed tree into the installer folder.
# Does not launch a browser.  Does not call codesign or notarytool.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- 1) refresh the pack --------------------------------------------------
sh "$REPO_ROOT/scripts/pack_local_operator.sh"

PACK="$REPO_ROOT/dist/aegis-local-operator"
OUT="$REPO_ROOT/dist/AegisOperator-mac"

# --- 2) replace the installer folder each run ---------------------------
rm -rf "$OUT"
mkdir -p "$OUT"

# --- 3) copy the packed tree into the installer folder -------------------
cp -R "$PACK" "$OUT/aegis-local-operator"

# --- 4) Install.command --------------------------------------------------
cat > "$OUT/Install.command" <<'INSTALL_CMD_EOF'
#!/bin/sh
# Aegis Operator — install to $HOME.
#
# Copies aegis-local-operator into $HOME/aegis-local-operator if that
# home copy is missing.  Does not overwrite an existing home copy
# unless the operator passes --replace.  Does not copy $HOME/.aegis.
# Does not launch a browser.

set -euo pipefail

CMD_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$CMD_DIR/aegis-local-operator"
DEST="$HOME/aegis-local-operator"

REPLACE=0
for arg in "$@"; do
    case "$arg" in
        --replace) REPLACE=1 ;;
    esac
done

if [ -d "$DEST" ]; then
    if [ "$REPLACE" -ne 1 ]; then
        echo "Install target: $DEST already exists — pass --replace to overwrite."
        echo "Data dir: $HOME/.aegis"
        echo "Start: ./start_operator.sh after venv"
        exit 0
    fi
    rm -rf "$DEST"
fi

cp -R "$SRC" "$DEST"

echo "Install target: $DEST"
echo "Data dir: $HOME/.aegis"
echo "Start: ./start_operator.sh after venv"
INSTALL_CMD_EOF
chmod +x "$OUT/Install.command"

# --- 4b) uninstall.command (copy of scripts/uninstall_aegis_operator.sh) --
cp "$REPO_ROOT/scripts/uninstall_aegis_operator.sh" "$OUT/uninstall.command"
chmod +x "$OUT/uninstall.command"

# --- 5) Aegis Operator.app (minimal unsigned bundle) ---------------------
APP="$OUT/Aegis Operator.app"
mkdir -p "$APP/Contents/MacOS"

cat > "$APP/Contents/Info.plist" <<'PLIST_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Aegis Operator</string>
    <key>CFBundleIdentifier</key>
    <string>lab.azimi.aegis.operator</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>AegisOperator</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon.png</string>
</dict>
</plist>
PLIST_EOF

cat > "$APP/Contents/MacOS/AegisOperator" <<'STUB_EOF'
#!/bin/sh
# Aegis Operator — .app launcher stub.
#
# Sets AEGIS_DATA_DIR and execs the adjacent pack start_operator.sh.
# Does not launch a browser.  Does not call codesign or notarytool.

set -euo pipefail

STUB_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALLER_DIR="$(cd "$STUB_DIR/../../.." && pwd)"
PACK_DIR="$INSTALLER_DIR/aegis-local-operator"

export AEGIS_DATA_DIR="${AEGIS_DATA_DIR:-$HOME/.aegis}"

exec "$PACK_DIR/start_operator.sh" "$@"
STUB_EOF
chmod +x "$APP/Contents/MacOS/AegisOperator"

# --- 5b) App icon resource -----------------------------------------------
mkdir -p "$APP/Contents/Resources"
"$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/generate_app_icon.py" \
    "$APP/Contents/Resources/AppIcon.png"

# --- 6) INSTALL.md --------------------------------------------------------
cat > "$OUT/INSTALL.md" <<'INSTALL_MD_EOF'
# Aegis Operator — Mac installer folder

## Now

1. Copy this folder (`AegisOperator-mac`) to the target Mac.
2. Run `Install.command` — or manually copy `aegis-local-operator` into `$HOME`.
3. `cd $HOME/aegis-local-operator`
4. `python3.11 -m venv .venv`
5. `pip install -e .`
6. `./start_operator.sh`
7. Open `http://127.0.0.1:8741/` yourself in a browser.

Uninstall: run `uninstall.command` (or `scripts/uninstall_aegis_operator.sh`) — it removes the copied program folder `$HOME/aegis-local-operator`; it does not delete `$HOME/.aegis`.

This app is unsigned; macOS Gatekeeper may warn; this is not App Store and not notarized.

Data stays in that account `$HOME/.aegis` — profile, actions, and exports stay on that laptop after uninstall, and a later install reuses that data.
INSTALL_MD_EOF

echo "$OUT"
