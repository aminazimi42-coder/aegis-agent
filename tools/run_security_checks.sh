#!/usr/bin/env bash
# Simple security checks runner for local development/CI
set -euo pipefail

echo "Running ruff..."
ruff check .

if command -v bandit >/dev/null 2>&1; then
  echo "Running bandit security scan..."
  bandit -r core -q || true
else
  echo "bandit not installed; skipping bandit scan"
fi

echo "Security checks completed."
