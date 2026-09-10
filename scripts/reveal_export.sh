#!/usr/bin/env bash
#
# reveal_export.sh — Reveal a previously exported file in macOS Finder.
#
# Usage: reveal_export.sh <path>
#
# Calls `open -R` with the given local path.  Does not open a browser,
# does not copy the file, does not bind a network port.
#
# T142 — Optional Reveal control for the signed-export button.

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: reveal_export.sh <path>" >&2
  exit 1
fi

TARGET="$1"

if [ ! -f "$TARGET" ]; then
  echo "file not found: $TARGET" >&2
  exit 1
fi

# macOS: reveal the file in Finder.
open -R "$TARGET"
