#!/usr/bin/env bash
# scripts/sync-status.sh — Display current fork sync status
#
# Usage:
#   ./scripts/sync-status.sh          # Status of current repo
#   ./scripts/sync-status.sh --all    # Aggregate status of all registered L3 forks
#
# Options:
#   --all       Show status of all registered forks (requires gh CLI)
#   --json      Output as JSON (for script consumption)
#   -h, --help  Show help

set -euo pipefail

MODE="single"
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --all)  MODE="all"; shift ;;
    --json) JSON_OUTPUT=true; shift ;;
    -h|--help)
      sed -n '2,/^$/{ s/^# //; s/^#//; p }' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ======================================================================
# --all mode: aggregate dashboard for all registered L3 forks
# ======================================================================
if [ "$MODE" = "all" ]; then
  REGISTRY="docs/fork-registry.yaml"
  if [ ! -f "$REGISTRY" ]; then
    echo "Error: Fork registry not found: $REGISTRY"
    exit 1
  fi

  if ! command -v gh &>/dev/null; then
    echo "Error: gh CLI required for --all mode."
    exit 1
  fi

  # Get upstream L2 repo
  if command -v yq &>/dev/null; then
    UPSTREAM_L2=$(yq '.upstream.l2' "$REGISTRY")
    FORK_COUNT=$(yq '.forks | length' "$REGISTRY")
  else
    UPSTREAM_L2=$(grep "l2:" "$REGISTRY" | awk '{print $2}')
    FORK_COUNT=$(grep "  - name:" "$REGISTRY" | wc -l | tr -d ' ')
  fi

  echo "=== Fork Sync Dashboard ==="
  echo "Upstream L2: $UPSTREAM_L2"
  echo "Registered forks: $FORK_COUNT"
  echo ""

  if [ "$FORK_COUNT" -eq 0 ]; then
    echo "No forks registered."
    exit 0
  fi

  # Table header
  printf "%-15s %-30s %-8s %-8s %-8s %s\n" "NAME" "REPO" "STATUS" "BEHIND" "AHEAD" "LAST_SYNC"
  printf "%-15s %-30s %-8s %-8s %-8s %s\n" "----" "----" "------" "------" "-----" "---------"

  # JSON array start
  [ "$JSON_OUTPUT" = true ] && echo "["

  FIRST=true
  for i in $(seq 0 $((FORK_COUNT - 1))); do
    if command -v yq &>/dev/null; then
      NAME=$(yq ".forks[$i].name" "$REGISTRY")
      REPO=$(yq ".forks[$i].repo" "$REGISTRY")
      STATUS=$(yq ".forks[$i].status" "$REGISTRY")
    else
      # Fallback: simple grep-based extraction (fragile but works)
      NAME=$(grep -A0 "  - name:" "$REGISTRY" | sed -n "$((i+1))p" | awk '{print $3}')
      REPO=$(grep "    repo:" "$REGISTRY" | sed -n "$((i+1))p" | awk '{print $2}')
      STATUS=$(grep "    status:" "$REGISTRY" | sed -n "$((i+1))p" | awk '{print $2}')
    fi

    if [ "$STATUS" != "active" ]; then
      printf "%-15s %-30s %-8s %-8s %-8s %s\n" "$NAME" "$REPO" "$STATUS" "-" "-" "-"
      continue
    fi

    # Query GitHub API for divergence (graceful on failure)
    BEHIND="?"
    AHEAD="?"
    LAST_SYNC="?"
    COMPARE_RAW=$(gh api "repos/$REPO/compare/main...$UPSTREAM_L2:main" 2>/dev/null || true)
    if echo "$COMPARE_RAW" | grep -q '"behind_by"' 2>/dev/null; then
      BEHIND=$(echo "$COMPARE_RAW" | grep -o '"behind_by":[0-9]*' | cut -d: -f2)
      AHEAD=$(echo "$COMPARE_RAW" | grep -o '"ahead_by":[0-9]*' | cut -d: -f2)
    fi

    # Get last sync commit
    SYNC_RAW=$(gh api "repos/$REPO/commits?per_page=20" 2>/dev/null || true)
    if echo "$SYNC_RAW" | grep -q '"sync:' 2>/dev/null; then
      LAST_SYNC=$(echo "$SYNC_RAW" | grep -B2 '"sync:' | grep '"date"' | head -1 | grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}' || echo "?")
    else
      LAST_SYNC="never"
    fi

    if [ "$JSON_OUTPUT" = true ]; then
      [ "$FIRST" = false ] && echo ","
      echo "  {\"name\":\"$NAME\",\"repo\":\"$REPO\",\"status\":\"$STATUS\",\"behind\":$BEHIND,\"ahead\":$AHEAD,\"last_sync\":\"$LAST_SYNC\"}"
      FIRST=false
    else
      printf "%-15s %-30s %-8s %-8s %-8s %s\n" "$NAME" "$REPO" "$STATUS" "$BEHIND" "$AHEAD" "$LAST_SYNC"
    fi
  done

  [ "$JSON_OUTPUT" = true ] && echo "]"
  exit 0
fi

# ======================================================================
# Default mode: single repo status
# ======================================================================
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
