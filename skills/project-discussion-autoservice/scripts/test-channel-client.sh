#!/bin/bash
set -euo pipefail

# Test runner for feishu/channel.py (ChannelClient)
# Baseline: 1/1 passed

usage() {
    echo "Usage: $(basename "$0") [--dry-run] [--help]"
    echo "Run ChannelClient tests."
    exit 0
}

[[ "${1:-}" == "--help" ]] && usage
[[ "${1:-}" == "--dry-run" ]] && { echo "[dry-run] Would run: uv run pytest tests/test_channel_client.py -v"; exit 0; }

cd "$(git rev-parse --show-toplevel)"
uv run pytest tests/test_channel_client.py -v 2>&1
echo "EXIT_CODE=$?"
