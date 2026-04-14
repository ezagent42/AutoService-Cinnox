#!/bin/bash
set -euo pipefail

# Test runner for all tests
# Baseline: 14/14 passed, 4 skipped

usage() {
    echo "Usage: $(basename "$0") [--dry-run] [--help]"
    echo "Run all tests."
    exit 0
}

[[ "${1:-}" == "--help" ]] && usage
[[ "${1:-}" == "--dry-run" ]] && { echo "[dry-run] Would run: uv run pytest tests/ -v"; exit 0; }

cd "$(git rev-parse --show-toplevel)"
uv run pytest tests/ -v 2>&1
echo "EXIT_CODE=$?"
