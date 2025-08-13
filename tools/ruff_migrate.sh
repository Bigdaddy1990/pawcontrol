#!/usr/bin/env bash
set -euo pipefail
echo ">> Formatting (ruff format)"
ruff format .
echo ">> Linting with auto-fix (safe+unsafe)"
ruff check . --fix --unsafe-fixes || true
echo ">> Add noqa to remaining violations to establish a clean baseline (you can revert selectively)"
ruff check . --add-noqa || true
echo ">> Remove unused noqa markers"
ruff check . --extend-select RUF100 --fix || true
echo "Baseline established. Subsequent commits will stay clean."
