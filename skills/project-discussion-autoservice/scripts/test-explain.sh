#!/bin/bash
set -euo pipefail

# Test runner for web/app.py explain command pipeline
# Baseline: 5/5 passed, 4 skipped (flows/ not yet created)

usage() {
    echo "Usage: $(basename "$0") [--dry-run] [--help]"
    echo "Run explain command tests."
    exit 0
}

[[ "${1:-}" == "--help" ]] && usage
[[ "${1:-}" == "--dry-run" ]] && { echo "[dry-run] Would run: uv run pytest tests/test_explain_command.py -v"; exit 0; }

cd "$(git rev-parse --show-toplevel)"
uv run pytest tests/test_explain_command.py -v 2>&1
echo "EXIT_CODE=$?"
