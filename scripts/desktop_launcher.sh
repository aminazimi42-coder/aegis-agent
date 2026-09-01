#!/usr/bin/env bash
# Simple desktop launcher for the Aegis local companion engine
set -euo pipefail

PY=${PY:-python}
echo "Starting Aegis Desktop Engine..."
${PY} - <<PY
from core.desktop_engine import DesktopEngine
e=DesktopEngine()
print(e.run_task('local quick test'))
PY
