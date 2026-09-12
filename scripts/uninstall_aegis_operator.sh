#!/bin/sh
# T150 — Uninstall the Aegis Operator local program folder.
#
# Removes only $HOME/aegis-local-operator if present.
# Does NOT delete $HOME/.aegis or anything under it.
# Does NOT touch the git repo or /Users/Shared.
# Does NOT open a browser.  Does NOT kill port 8741.
#
# After uninstall the operator profile, actions, and exports stay in
# $HOME/.aegis — a later install reuses that data.

set -euo pipefail

TARGET="$HOME/aegis-local-operator"
DATA_DIR="$HOME/.aegis"

if [ -d "$TARGET" ]; then
    rm -rf "$TARGET"
    echo "Removed: $TARGET"
else
    echo "Not found: $TARGET (already removed)"
fi

echo "Left in place: $DATA_DIR"
echo "Profile, actions, and exports stay on this laptop after uninstall."
echo "A later install reuses the existing data in $DATA_DIR."
