#!/usr/bin/env bash
# scripts/unregister-fork.sh — Deactivate or archive an L3 fork
#
# Usage:
#   ./scripts/unregister-fork.sh --repo owner/repo [--status archived|inactive] [--auto]
#
# Options:
#   --repo      GitHub owner/repo (required)
#   --status    Target status: archived (default) or inactive
#   --auto      Skip confirmation, auto-commit
#   -h, --help  Show help

set -euo pipefail

REGISTRY="docs/fork-registry.yaml"

REPO=""
TARGET_STATUS="archived"
AUTO=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --repo)    REPO="$2"; shift 2 ;;
    --status)  TARGET_STATUS="$2"; shift 2 ;;
    --auto)    AUTO=true; shift ;;
    -h|--help)
      sed -n '2,/^$/{ s/^# //; s/^#//; p }' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [ -z "$REPO" ]; then
  echo "Error: --repo is required."
  exit 1
fi

if [ "$TARGET_STATUS" != "archived" ] && [ "$TARGET_STATUS" != "inactive" ]; then
  echo "Error: --status must be 'archived' or 'inactive' (got: $TARGET_STATUS)"
  exit 1
fi

if [ ! -f "$REGISTRY" ]; then
  echo "Error: Registry not found: $REGISTRY"
  exit 1
fi

# Check fork exists
if ! grep -q "repo: $REPO" "$REGISTRY"; then
  echo "Error: Fork '$REPO' not found in registry."
  exit 1
fi

# Check current status
CURRENT_STATUS=$(grep -A5 "repo: $REPO" "$REGISTRY" | grep "status:" | awk '{print $2}' || echo "?")
if [ "$CURRENT_STATUS" = "$TARGET_STATUS" ]; then
  echo "Fork '$REPO' is already $TARGET_STATUS."
  exit 0
fi

echo "==> Will change fork '$REPO' status: $CURRENT_STATUS -> $TARGET_STATUS"

if [ "$AUTO" = false ]; then
  read -rp "Confirm? [y/N]: " CONFIRM
  [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ] && { echo "Aborted."; exit 0; }
fi

# Update status in registry
# Use awk for portable multi-line matching
awk -v repo="$REPO" -v new_status="$TARGET_STATUS" '
  /repo:/ && $0 ~ repo { found=1 }
  found && /status:/ { sub(/status: .*/, "status: " new_status); found=0 }
  { print }
' "$REGISTRY" > "${REGISTRY}.tmp" && mv "${REGISTRY}.tmp" "$REGISTRY"

echo "Done. Fork '$REPO' is now $TARGET_STATUS."

if [ "$AUTO" = true ]; then
  git add "$REGISTRY"
  git commit -m "fork: $TARGET_STATUS $REPO" --quiet
  echo "Auto-committed."
fi
