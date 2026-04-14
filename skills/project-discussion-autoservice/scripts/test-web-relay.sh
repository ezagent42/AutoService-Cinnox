#!/bin/bash
set -euo pipefail

# Test runner for web/websocket.py (WebChannelBridge)
# Baseline: 2/2 passed

usage() {
    echo "Usage: $(basename "$0") [--dry-run] [--help]"
    echo "Run WebChannelBridge relay tests."
    exit 0
}

[[ "${1:-}" == "--help" ]] && usage
[[ "${1:-}" == "--dry-run" ]] && { echo "[dry-run] Would run: uv run pytest tests/test_web_relay.py -v"; exit 0; }

cd "$(git rev-parse --show-toplevel)"
uv run pytest tests/test_web_relay.py -v 2>&1
echo "EXIT_CODE=$?"
