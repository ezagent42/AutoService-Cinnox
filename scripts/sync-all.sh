#!/usr/bin/env bash
# scripts/sync-all.sh — Batch sync all L3 forks
#
# Reads docs/fork-registry.yaml and for each active fork:
# - Attempts fast-forward merge via GitHub API
# - Falls back to creating a sync PR if conflicts exist
#
# Usage: ./scripts/sync-all.sh [--dry-run]
# Requires: gh CLI, yq

set -euo pipefail

DRY_RUN=false
[ "${1:-}" = "--dry-run" ] && DRY_RUN=true

REGISTRY="docs/fork-registry.yaml"

if [ ! -f "$REGISTRY" ]; then
  echo "Error: Fork registry not found: $REGISTRY"
  exit 1
fi

# Check dependencies
if ! command -v yq &>/dev/null; then
  echo "Error: yq is required. Install: https://github.com/mikefarah/yq"
  exit 1
fi

if ! command -v gh &>/dev/null; then
  echo "Error: gh CLI is required. Install: https://cli.github.com"
  exit 1
fi

# Read upstream L2 repo from registry
UPSTREAM_L2=$(yq '.upstream.l2' "$REGISTRY")

echo "==> Reading fork registry..."
echo "Upstream L2: $UPSTREAM_L2"
echo ""

FORK_COUNT=$(yq '.forks | length' "$REGISTRY")

if [ "$FORK_COUNT" -eq 0 ]; then
  echo "No forks registered."
  exit 0
fi

SYNCED=0
FAILED=0
SKIPPED=0

for i in $(seq 0 $((FORK_COUNT - 1))); do
  NAME=$(yq ".forks[$i].name" "$REGISTRY")
  REPO=$(yq ".forks[$i].repo" "$REGISTRY")
  STATUS=$(yq ".forks[$i].status" "$REGISTRY")

  if [ "$STATUS" != "active" ]; then
    echo "  -- $NAME ($REPO) -- skipped (status: $STATUS)"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  echo -n "  -> $NAME ($REPO)... "

  if [ "$DRY_RUN" = true ]; then
    # Check how far behind
    BEHIND=$(gh api "repos/$REPO/compare/main...$UPSTREAM_L2:main" \
      --jq '.behind_by' 2>/dev/null || echo "?")
    echo "behind $BEHIND commits [dry-run]"
    continue
  fi

  # Attempt fast-forward merge via GitHub API
  if gh api "repos/$REPO/merges" \
      -f base=main \
      -f head="$UPSTREAM_L2:main" \
      -f commit_message="sync: auto-merge upstream/main" \
      --method POST &>/dev/null; then
    echo "OK synced"
    SYNCED=$((SYNCED + 1))
  else
    # Conflict or permission issue -- create PR for manual resolution
    echo "CONFLICT -- creating PR"
    gh pr create \
      --repo "$REPO" \
      --title "sync: merge upstream/main" \
      --body "Automated sync from upstream ($UPSTREAM_L2). Please resolve conflicts if any." \
      --base main \
      --head "$UPSTREAM_L2:main" 2>/dev/null || {
        echo "    (PR creation failed -- check permissions)"
      }
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo "==> Summary: $SYNCED synced, $FAILED need manual merge, $SKIPPED skipped"
