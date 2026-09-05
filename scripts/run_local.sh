#!/bin/sh
# Start the local status view.
cd "$(dirname "$0")/.." || exit 1
exec ./.venv/bin/python -m core.twin_local status
