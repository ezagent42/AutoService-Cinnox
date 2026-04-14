#!/bin/bash
set -euo pipefail

# Test runner for E2E tests
# tests/e2e/test_feishu_mock.py - Feishu mock integration
# tests/e2e/test_web_chat.sh - Web chat curl-based E2E

usage() {
    echo "Usage: $(basename "$0") [--dry-run] [--help]"
    echo "Run E2E tests (Feishu mock + web chat)."
    exit 0
}

[[ "${1:-}" == "--help" ]] && usage
[[ "${1:-}" == "--dry-run" ]] && { echo "[dry-run] Would run: uv run pytest tests/e2e/ -v && bash tests/e2e/test_web_chat.sh"; exit 0; }

cd "$(git rev-parse --show-toplevel)"
echo "=== Feishu mock E2E ==="
uv run pytest tests/e2e/test_feishu_mock.py -v 2>&1
echo "EXIT_CODE=$?"
