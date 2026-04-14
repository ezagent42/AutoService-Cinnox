#!/usr/bin/env bash
# scripts/sync.sh — Sync current fork with upstream
#
# Usage: ./scripts/sync.sh [--dry-run] [--auto] [--branch <upstream-branch>]
# Default upstream branch: main
#
# Modes:
#   (default)   Interactive — prompts on conflict, shows merge output
#   --dry-run   Conflict pre-check only, do not merge
#   --auto      Non-interactive — merge if clean, fail with exit 1 on conflict
#               Designed for CI/script invocation. On success, also runs
#               sync-bridge.sh to generate code-diff artifact if available.

set -euo pipefail

DRY_RUN=false
AUTO=false
UPSTREAM_BRANCH="main"

while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)  DRY_RUN=true; shift ;;
    --auto)     AUTO=true; shift ;;
    --branch)   UPSTREAM_BRANCH="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--auto] [--branch <upstream-branch>]"
      echo ""
      echo "Options:"
      echo "  --dry-run   Conflict pre-check only, do not merge"
      echo "  --auto      Non-interactive: merge if clean, exit 1 on conflict"
      echo "  --branch    Upstream branch to sync (default: main)"
      exit 0
      ;;
    *)          echo "Unknown option: $1"; exit 1 ;;
  esac
done

# 1. Detect upstream remote
if ! git remote get-url upstream &>/dev/null; then
  echo "Error: 'upstream' remote not configured."
  echo "Run: git remote add upstream <upstream-repo-url>"
  exit 1
fi

# 2. Fetch upstream
echo "==> Fetching upstream..."
git fetch upstream "$UPSTREAM_BRANCH"

# 3. Show status
BEHIND=$(git rev-list --count HEAD..upstream/"$UPSTREAM_BRANCH")
AHEAD=$(git rev-list --count upstream/"$UPSTREAM_BRANCH"..HEAD)
echo "  Behind upstream: $BEHIND commits"
echo "  Ahead of upstream: $AHEAD commits"

if [ "$BEHIND" -eq 0 ]; then
  echo "Already up to date."
  exit 0
fi

# 4. Conflict pre-check (dry-run)
echo ""
echo "==> Conflict pre-check..."

# Use git merge-tree --write-tree (git 2.38+) for accurate conflict detection
# Falls back to old merge-tree if --write-tree is not available
CONFLICT_OUTPUT=""
if git merge-tree --write-tree HEAD upstream/"$UPSTREAM_BRANCH" >/dev/null 2>&1; then
  echo "  OK: No conflicts expected -- clean merge likely."
else
  CONFLICT_OUTPUT=$(git merge-tree --write-tree HEAD upstream/"$UPSTREAM_BRANCH" 2>&1 || true)
  CONFLICT_FILES=$(echo "$CONFLICT_OUTPUT" | grep "^CONFLICT" | sed 's/.*Merge conflict in //' || true)
  if [ -n "$CONFLICT_FILES" ]; then
    CONFLICT_COUNT=$(echo "$CONFLICT_FILES" | wc -l | tr -d ' ')
    echo "  WARNING: Potential conflicts detected in $CONFLICT_COUNT file(s):"
    echo "$CONFLICT_FILES" | while read -r f; do
      echo "    - $f"
    done
    HAS_CONFLICTS=true
  else
    echo "  OK: No conflicts expected -- clean merge likely."
    HAS_CONFLICTS=false
  fi
fi

if [ "$DRY_RUN" = true ]; then
  echo ""
  echo "[dry-run] Would merge $BEHIND commits from upstream/$UPSTREAM_BRANCH."
  echo "Upstream changes:"
  git log --oneline HEAD..upstream/"$UPSTREAM_BRANCH" | head -20
  [ "$BEHIND" -gt 20 ] && echo "  ... and $((BEHIND - 20)) more"
  exit 0
fi

# In --auto mode, abort if conflicts are expected
if [ "$AUTO" = true ] && [ "${HAS_CONFLICTS:-false}" = true ]; then
  echo ""
  echo "[auto] Conflicts detected — aborting. Run without --auto to resolve interactively."
  exit 1
fi

# 5. Execute merge
MERGE_BASE=$(git merge-base HEAD upstream/"$UPSTREAM_BRANCH")
echo ""
echo "==> Merging upstream/$UPSTREAM_BRANCH ($BEHIND commits)..."
if git merge upstream/"$UPSTREAM_BRANCH" -m "sync: merge upstream/$UPSTREAM_BRANCH ($BEHIND commits)"; then
  echo ""
  echo "Sync complete. Run 'git push' to update remote."

  # In --auto mode, generate code-diff artifact for dev-loop-skill integration
  if [ "$AUTO" = true ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    if [ -x "$SCRIPT_DIR/sync-bridge.sh" ]; then
      echo ""
      echo "==> Generating code-diff artifact..."
      "$SCRIPT_DIR/sync-bridge.sh" --merge-base "$MERGE_BASE" --auto
    fi
  fi
else
  echo ""
  echo "Merge conflicts detected. Resolve them, then:"
  echo "  git add <resolved-files>"
  echo "  git commit"
  echo ""
  echo "Conflict resolution tips by layer:"
  echo "  - socialware/ and channels/ (L1): prefer upstream version"
  echo "  - autoservice/ (L2): prefer upstream version"
  echo "  - plugins/<tenant>/ (L3): keep local version"
  exit 1
fi
