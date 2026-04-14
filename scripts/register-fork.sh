#!/usr/bin/env bash
# scripts/register-fork.sh — Register an L3 fork into fork-registry.yaml
#
# Usage:
#   ./scripts/register-fork.sh --repo owner/repo --name tenant-name [options]
#   ./scripts/register-fork.sh --repo cinnox/AutoService --name cinnox --contact alice@cinnox.com
#
# Options:
#   --repo      GitHub owner/repo (required)
#   --name      Tenant display name (required)
#   --layer     Fork layer, default: L3
#   --contact   Contact email
#   --notes     Free-text notes
#   --auto      Skip confirmation prompt
#   -h, --help  Show help

set -euo pipefail

REGISTRY="docs/fork-registry.yaml"

# Defaults
REPO=""
NAME=""
LAYER="L3"
CONTACT=""
NOTES=""
AUTO=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --repo)    REPO="$2"; shift 2 ;;
    --name)    NAME="$2"; shift 2 ;;
    --layer)   LAYER="$2"; shift 2 ;;
    --contact) CONTACT="$2"; shift 2 ;;
    --notes)   NOTES="$2"; shift 2 ;;
    --auto)    AUTO=true; shift ;;
    -h|--help)
      sed -n '2,/^$/{ s/^# //; s/^#//; p }' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Validate required args
if [ -z "$REPO" ] || [ -z "$NAME" ]; then
  echo "Error: --repo and --name are required."
  echo "Run: $0 --help"
  exit 1
fi

# Validate repo format (owner/repo)
if ! echo "$REPO" | grep -qE '^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$'; then
  echo "Error: --repo must be in 'owner/repo' format (got: $REPO)"
  exit 1
fi

# Ensure registry exists
if [ ! -f "$REGISTRY" ]; then
  echo "Error: Registry not found: $REGISTRY"
  echo "Expected to be in L2 repo root."
  exit 1
fi

# Check for duplicate
if grep -q "repo: $REPO" "$REGISTRY" 2>/dev/null; then
  EXISTING_STATUS=$(grep -A5 "repo: $REPO" "$REGISTRY" | grep "status:" | awk '{print $2}' || echo "?")
  if [ "$EXISTING_STATUS" = "active" ]; then
    echo "Error: Fork '$REPO' is already registered (status: active)."
    echo "To re-activate an archived fork, use: $0 --repo $REPO --name $NAME (will update status)"
    exit 1
  elif [ "$EXISTING_STATUS" = "archived" ] || [ "$EXISTING_STATUS" = "inactive" ]; then
    echo "Fork '$REPO' exists but is $EXISTING_STATUS. Re-activating..."
    awk -v repo="$REPO" '
      /repo:/ && $0 ~ repo { found=1 }
      found && /status:/ { sub(/status: .*/, "status: active"); found=0 }
      { print }
    ' "$REGISTRY" > "${REGISTRY}.tmp" && mv "${REGISTRY}.tmp" "$REGISTRY"
    echo "Done. Fork '$REPO' is now active."
    exit 0
  fi
fi

# Verify repo exists on GitHub (if gh available)
if command -v gh &>/dev/null; then
  echo "Verifying GitHub repo: $REPO ..."
  if ! gh repo view "$REPO" --json name &>/dev/null 2>&1; then
    echo "WARNING: Cannot access GitHub repo '$REPO' (private or doesn't exist)."
    if [ "$AUTO" = false ]; then
      read -rp "Continue anyway? [y/N]: " CONFIRM
      [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ] && { echo "Aborted."; exit 0; }
    fi
  else
    echo "  OK: Repo verified."
  fi
fi

# Build YAML entry
TODAY=$(date +%Y-%m-%d)
ENTRY="  - name: $NAME
    repo: $REPO
    layer: $LAYER
    status: active
    contact: ${CONTACT:-\"\"}"
[ -n "$NOTES" ] && ENTRY="$ENTRY
    notes: \"$NOTES\""
ENTRY="$ENTRY
    created: $TODAY"

# Show and confirm
echo ""
echo "==> Will register fork:"
echo "$ENTRY"
echo ""

if [ "$AUTO" = false ]; then
  read -rp "Confirm? [y/N]: " CONFIRM
  [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ] && { echo "Aborted."; exit 0; }
fi

# Append to registry
# Handle the case where forks: [] is empty array on one line
if grep -q "^forks: \[\]" "$REGISTRY"; then
  # Replace empty array with populated array
  sed -i "s/^forks: \[\]/forks:/" "$REGISTRY"
  echo "$ENTRY" >> "$REGISTRY"
else
  # Append to existing forks list
  echo "$ENTRY" >> "$REGISTRY"
fi

echo ""
echo "Registered: $NAME ($REPO) as $LAYER fork."
echo ""
echo "Next steps:"
echo "  1. git add $REGISTRY && git commit -m 'fork: register $NAME ($REPO)'"
echo "  2. git push"
echo "  3. Ensure $REPO has 'upstream' remote pointing to this repo"

if [ "$AUTO" = true ]; then
  # In auto mode, also commit
  git add "$REGISTRY"
  git commit -m "fork: register $NAME ($REPO) as $LAYER" --quiet
  echo ""
  echo "Auto-committed registration."
fi
