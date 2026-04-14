#!/usr/bin/env bash
# scripts/refine.sh — Refinement assistant (extract L3 changes back to L2/L1)
#
# Interactive mode (default):
#   ./scripts/refine.sh [commit-hash | file-path]
#
# Auto mode (for CI/scripts):
#   ./scripts/refine.sh --auto --commit <hash> --layer L2|L1 [--message <msg>] [--pr]
#
# Options:
#   --auto       Non-interactive mode (requires --commit and --layer)
#   --commit     Commit hash to cherry-pick
#   --layer      Target layer: L1 or L2
#   --message    Commit message (auto-generated if omitted)
#   --pr         Auto-create PR via gh CLI after cherry-pick
#   -h, --help   Show help

set -euo pipefail

# Defaults
AUTO=false
TARGET=""
TARGET_LAYER=""
COMMIT_MSG=""
CREATE_PR=false

# Parse args
if [[ $# -gt 0 ]] && [[ "$1" != -* ]]; then
  # Positional arg (interactive mode): commit or file
  TARGET="$1"
  shift
fi

while [[ $# -gt 0 ]]; do
  case $1 in
    --auto)    AUTO=true; shift ;;
    --commit)  TARGET="$2"; shift 2 ;;
    --layer)   TARGET_LAYER="$2"; shift 2 ;;
    --message) COMMIT_MSG="$2"; shift 2 ;;
    --pr)      CREATE_PR=true; shift ;;
    -h|--help)
      sed -n '2,/^$/{ s/^# //; s/^#//; p }' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "=== Refine Assistant ==="
echo ""

# --- Auto mode validation ---
if [ "$AUTO" = true ]; then
  if [ -z "$TARGET" ]; then
    echo "Error: --auto requires --commit <hash>"
    exit 1
  fi
  if [ -z "$TARGET_LAYER" ]; then
    echo "Error: --auto requires --layer L1|L2"
    exit 1
  fi
  if [ "$TARGET_LAYER" != "L1" ] && [ "$TARGET_LAYER" != "L2" ]; then
    echo "Error: --layer must be L1 or L2 (got: $TARGET_LAYER)"
    exit 1
  fi
fi

# --- Step 1: Determine source ---
if [ -z "$TARGET" ]; then
  echo "Recent local commits (not in upstream):"
  echo ""
  if git remote get-url upstream &>/dev/null; then
    git log --oneline upstream/main..HEAD 2>/dev/null | head -20
  else
    git log --oneline -20
  fi
  echo ""
  read -rp "Enter commit hash or file path: " TARGET
fi

if [ -z "$TARGET" ]; then
  echo "Error: No target specified."
  exit 1
fi

# --- Step 2: Choose target layer ---
if [ -z "$TARGET_LAYER" ]; then
  echo ""
  echo "Refinement target layer:"
  echo "  1) L2 (autoservice) -- domain-level capability, useful for other tenants"
  echo "  2) L1 (socialware)  -- framework-level capability, useful for different apps"
  echo ""
  read -rp "Choose [1/2]: " LAYER_CHOICE

  case "$LAYER_CHOICE" in
    1) TARGET_LAYER="L2" ;;
    2) TARGET_LAYER="L1" ;;
    *) echo "Invalid choice"; exit 1 ;;
  esac
fi

# Set branch prefix based on layer
case "$TARGET_LAYER" in
  L2) BRANCH_PREFIX="upstream" ;;
  L1) BRANCH_PREFIX="upstream-l1" ;;
esac

# --- Step 3: Layer judgment checklist ---
echo ""
echo "==> Layer judgment checklist ($TARGET_LAYER):"
if [ "$TARGET_LAYER" = "L1" ]; then
  echo "  [ ] Would this feature be useful in a completely different app (education/healthcare)?"
  echo "  [ ] Does it contain customer-service-specific terms (customer/agent/CRM)?"
  echo "  [ ] Does it depend on modules in autoservice/?"
  echo ""
  echo "  If any answer is 'no', consider refining to L2 instead of L1."
else
  echo "  [ ] Would this feature be useful for a different tenant?"
  echo "  [ ] Does it contain tenant-specific data (customer names, product names)?"
  echo "  [ ] Does it depend on modules in plugins/<tenant>/?"
  echo ""
  echo "  If any answer is 'no', it may be better to keep in L3."
fi

if [ "$AUTO" = false ]; then
  echo ""
  read -rp "Continue? [y/N]: " CONFIRM
  [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ] && { echo "Aborted."; exit 0; }
fi

# --- Step 4: Create refinement branch ---
BRANCH_NAME="$BRANCH_PREFIX/refine-$(date +%Y%m%d)-$(echo "$TARGET" | tr '/' '-' | cut -c1-30)"
echo ""
echo "==> Creating branch: $BRANCH_NAME"
git checkout -b "$BRANCH_NAME"

# --- Step 5: Apply changes ---
CHERRY_PICK_OK=false
if git cat-file -t "$TARGET" &>/dev/null 2>&1; then
  echo "==> Cherry-picking commit: $TARGET"
  if git cherry-pick "$TARGET" --no-commit; then
    echo "Changes staged. Review and adjust before committing."
    CHERRY_PICK_OK=true
  else
    echo "Cherry-pick had conflicts. Resolve them before continuing."
    if [ "$AUTO" = true ]; then
      echo "[auto] Aborting cherry-pick due to conflicts."
      git cherry-pick --abort 2>/dev/null || true
      git checkout - 2>/dev/null || true
      git branch -D "$BRANCH_NAME" 2>/dev/null || true
      exit 1
    fi
  fi
elif [ -f "$TARGET" ]; then
  echo "==> File: $TARGET"
  echo "Edit this file to extract only the generalizable parts."
  echo "Remember to update imports (socialware.* for L1, autoservice.* for L2)."
else
  echo "==> '$TARGET' is neither a commit nor a file."
  echo "Manually add your changes to this branch."
fi

# --- Step 6: Auto-commit + PR (auto mode only) ---
if [ "$AUTO" = true ] && [ "$CHERRY_PICK_OK" = true ]; then
  # Generate commit message if not provided
  if [ -z "$COMMIT_MSG" ]; then
    ORIGINAL_MSG=$(git log -1 --format="%s" "$TARGET" 2>/dev/null || echo "refine changes")
    COMMIT_MSG="refine($TARGET_LAYER): $ORIGINAL_MSG"
  fi

  git commit -m "$COMMIT_MSG"
  echo "Committed: $COMMIT_MSG"

  # Generate code-diff artifact for dev-loop-skill
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  if [ -x "$SCRIPT_DIR/sync-bridge.sh" ]; then
    echo ""
    echo "==> Generating code-diff artifact..."
    MERGE_BASE=$(git merge-base HEAD~1 HEAD)
    "$SCRIPT_DIR/sync-bridge.sh" --merge-base "$MERGE_BASE" --auto
  fi

  # Auto-create PR if requested
  if [ "$CREATE_PR" = true ]; then
    if command -v gh &>/dev/null; then
      echo ""
      echo "==> Pushing and creating PR..."
      git push -u origin "$BRANCH_NAME" 2>/dev/null
      if [ "$TARGET_LAYER" = "L1" ]; then
        PR_TARGET="h2oslabs/socialware"
      else
        PR_TARGET="h2oslabs/AutoService"
      fi
      gh pr create \
        --title "$COMMIT_MSG" \
        --body "Automated refinement from downstream fork.

**Source commit:** \`$TARGET\`
**Target layer:** $TARGET_LAYER
**Branch:** \`$BRANCH_NAME\`" \
        --base main 2>/dev/null && echo "PR created." || echo "PR creation failed (check upstream repo permissions)."
    else
      echo "WARNING: gh CLI not available, skipping PR creation."
    fi
  fi
fi

# --- Step 7: Next steps (interactive mode) ---
if [ "$AUTO" = false ]; then
  echo ""
  echo "==> Next steps:"
  echo "  1. Review and adjust the changes"
  echo "  2. git add <files> && git commit -m 'refine: <description>'"
  echo "  3. git push origin $BRANCH_NAME"
  echo "  4. Create PR:"
  if [ "$TARGET_LAYER" = "L1" ]; then
    echo "     Target repo: h2oslabs/socialware (L1 upstream)"
  else
    echo "     Target repo: h2oslabs/AutoService (L2 upstream)"
  fi
  echo "     gh pr create --title 'refine: <description>'"
fi
