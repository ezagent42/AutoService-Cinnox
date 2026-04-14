#!/bin/bash
set -euo pipefail

# Test runner for feishu/channel_server.py (ChannelServer)
# Baseline: 6/6 passed

usage() {
    echo "Usage: $(basename "$0") [--dry-run] [--help]"
    echo "Run ChannelServer tests."
    exit 0
}

[[ "${1:-}" == "--help" ]] && usage
[[ "${1:-}" == "--dry-run" ]] && { echo "[dry-run] Would run: uv run pytest tests/test_channel_server.py -v"; exit 0; }

cd "$(git rev-parse --show-toplevel)"
uv run pytest tests/test_channel_server.py -v 2>&1
echo "EXIT_CODE=$?"
