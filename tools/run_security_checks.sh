#!/usr/bin/env bash
# Simple security checks runner for local development/CI
set -euo pipefail

echo "Running ruff..."
ruff check .

if command -v bandit >/dev/null 2>&1; then
  echo "Running bandit security scan (JSON output)..."
  bandit -r core -f json -o /tmp/bandit-report.json
  # fail if any issues were found
  python - <<PY
import json
data=json.load(open('/tmp/bandit-report.json'))
issues=len(data.get('results',[]))
print('Bandit issues found:', issues)
raise SystemExit(1) if issues>0 else None
PY
else
  echo "bandit not installed; skipping bandit scan"
fi

echo "Security checks completed."
