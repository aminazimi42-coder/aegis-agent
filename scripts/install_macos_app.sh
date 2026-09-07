#!/bin/sh
# T104 — Install the Aegis.app bundle to $HOME/Applications.
#
# Copies desktop/macos/Aegis.app into $HOME/Applications/Aegis.app.
# Does NOT write into the git worktree as the installed app.
# Prints the install path on success.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SRC_APP="$REPO_ROOT/desktop/macos/Aegis.app"
DEST_DIR="${HOME}/Applications"
DEST_APP="$DEST_DIR/Aegis.app"

if [ ! -d "$SRC_APP" ]; then
    echo "install_macos_app.sh: source bundle not found: $SRC_APP" >&2
    exit 1
fi

mkdir -p "$DEST_DIR"

# Remove a prior copy so the install is idempotent.
rm -rf "$DEST_APP"
cp -R "$SRC_APP" "$DEST_APP"

# Ensure the launcher remains executable.
chmod +x "$DEST_APP/Contents/MacOS/Aegis"

echo "installed: $DEST_APP"
