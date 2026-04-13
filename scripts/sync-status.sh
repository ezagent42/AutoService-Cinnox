#!/usr/bin/env bash
# scripts/sync-status.sh — Display current fork sync status
#
# Usage: ./scripts/sync-status.sh

set -euo pipefail

echo "=== Fork Sync Status ==="
echo ""

# Detect current layer
# Priority: .autoservice-info.yaml > directory heuristic
LAYER=""
if [ -f ".autoservice-info.yaml" ]; then
  LAYER=$(grep "^layer:" .autoservice-info.yaml 2>/dev/null | awk '{print $2}' || true)
fi

# Fallback: directory-based detection
if [ -z "$LAYER" ]; then
  if [ -d "socialware" ] && [ -d "autoservice" ]; then
    LAYER="L2"
  elif [ -d "plugins" ] && [ -d "autoservice" ]; then
    LAYER="L3"
  elif [ -d "autoservice" ]; then
    LAYER="L2-or-L3"
  else
    LAYER="?"
  fi
fi

echo "Current layer: $LAYER"
echo ""

# Upstream status
if git remote get-url upstream &>/dev/null; then
  UPSTREAM_URL=$(git remote get-url upstream)
  echo "Upstream: $UPSTREAM_URL"

  echo "  Fetching upstream..."
  git fetch upstream main --quiet 2>/dev/null || true

  BEHIND=$(git rev-list --count HEAD..upstream/main 2>/dev/null || echo "?")
  AHEAD=$(git rev-list --count upstream/main..HEAD 2>/dev/null || echo "?")
  LAST_SYNC=$(git log --oneline --grep="^sync:" -1 --format="%cd (%h %s)" \
    --date=short 2>/dev/null)
  [ -z "$LAST_SYNC" ] && LAST_SYNC="never"

  echo "  Behind: $BEHIND commits"
  echo "  Ahead:  $AHEAD commits"
  echo "  Last sync commit: $LAST_SYNC"

  if [ "$BEHIND" != "?" ] && [ "$BEHIND" -gt 0 ]; then
    echo ""
    echo "  Recent upstream changes:"
    git log --oneline HEAD..upstream/main | head -5
    [ "$BEHIND" -gt 5 ] && echo "  ... and $((BEHIND - 5)) more"
  fi
else
  echo "Upstream: not configured"
  echo "  Run: git remote add upstream <url>"
fi

# Downstream forks (L2 only)
echo ""
if [ "$LAYER" = "L2" ] && [ -f "docs/fork-registry.yaml" ]; then
  echo "=== Downstream Forks ==="
  if command -v yq &>/dev/null; then
    yq '.forks[] | .name + " (" + .repo + ") -- " + .status' \
      docs/fork-registry.yaml 2>/dev/null
  else
    echo "  (install yq for detailed fork info)"
    grep "  name:" docs/fork-registry.yaml 2>/dev/null | sed 's/.*name: /  - /' || echo "  (none registered)"
  fi
  echo ""
fi

# Layer file modification check
echo "=== Layer File Modification Check ==="
if git remote get-url upstream &>/dev/null; then
  MODIFIED_L1=$(git diff --name-only upstream/main...HEAD -- socialware/ channels/ 2>/dev/null | wc -l | tr -d ' ')
  MODIFIED_L2=$(git diff --name-only upstream/main...HEAD -- autoservice/ 2>/dev/null | wc -l | tr -d ' ')

  if [ "$LAYER" = "L3" ]; then
    [ "$MODIFIED_L1" -gt 0 ] && echo "  WARNING: L1 files modified ($MODIFIED_L1 files) -- should PR to L1 upstream"
    [ "$MODIFIED_L2" -gt 0 ] && echo "  WARNING: L2 files modified ($MODIFIED_L2 files) -- should PR to L2 upstream"
  fi
  if [ "$LAYER" = "L2" ]; then
    [ "$MODIFIED_L1" -gt 0 ] && echo "  WARNING: L1 files modified ($MODIFIED_L1 files) -- should PR to L1 upstream"
  fi
  [ "$MODIFIED_L1" -eq 0 ] && [ "$MODIFIED_L2" -eq 0 ] && echo "  OK: No cross-layer modifications"
else
  echo "  (skipped -- upstream not configured)"
fi
