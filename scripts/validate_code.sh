#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Running Ruff code check..."
./.venv/bin/ruff check app/ tests/

echo "Running Bandit security audit..."
./.venv/bin/bandit -r app/ -ll
