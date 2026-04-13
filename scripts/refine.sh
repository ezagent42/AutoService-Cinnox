#!/usr/bin/env bash
# scripts/refine.sh — Interactive refinement assistant
#
# Guides developers through extracting generalizable changes
# from L3 (tenant) back to L2 (domain) or L1 (framework).
#
# Usage: ./scripts/refine.sh [commit-hash | file-path]

set -euo pipefail

TARGET="${1:-}"

echo "=== Refine Assistant ==="
echo ""

# Step 1: Determine source of refinement
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

# Step 2: Choose target layer
echo ""
echo "Refinement target layer:"
echo "  1) L2 (autoservice) -- domain-level capability, useful for other tenants"
echo "  2) L1 (socialware)  -- framework-level capability, useful for different apps"
echo ""
read -rp "Choose [1/2]: " LAYER_CHOICE

case "$LAYER_CHOICE" in
  1) TARGET_LAYER="L2"; BRANCH_PREFIX="upstream" ;;
  2) TARGET_LAYER="L1"; BRANCH_PREFIX="upstream-l1" ;;
  *) echo "Invalid choice"; exit 1 ;;
esac

# Step 3: Layer judgment checklist
echo ""
echo "==> Layer judgment checklist:"
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

echo ""
read -rp "Continue? [y/N]: " CONFIRM
[ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ] && { echo "Aborted."; exit 0; }

# Step 4: Create refinement branch
BRANCH_NAME="$BRANCH_PREFIX/refine-$(date +%Y%m%d)-$(echo "$TARGET" | tr '/' '-' | cut -c1-30)"
echo ""
echo "==> Creating branch: $BRANCH_NAME"
git checkout -b "$BRANCH_NAME"

# Step 5: Apply changes
if git cat-file -t "$TARGET" &>/dev/null 2>&1; then
  echo "==> Cherry-picking commit: $TARGET"
  if git cherry-pick "$TARGET" --no-commit; then
    echo "Changes staged. Review and adjust before committing."
  else
    echo "Cherry-pick had conflicts. Resolve them before continuing."
  fi
elif [ -f "$TARGET" ]; then
  echo "==> File: $TARGET"
  echo "Edit this file to extract only the generalizable parts."
  echo "Remember to update imports (socialware.* for L1, autoservice.* for L2)."
else
  echo "==> '$TARGET' is neither a commit nor a file."
  echo "Manually add your changes to this branch."
fi

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
