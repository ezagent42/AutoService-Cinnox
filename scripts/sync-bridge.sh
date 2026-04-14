#!/usr/bin/env bash
# scripts/sync-bridge.sh — Bridge between sync/refine scripts and dev-loop-skill
#
# Generates a code-diff artifact in .artifacts/code-diffs/ that dev-loop-skill
# can consume (Skill 2 → test plan, Skill 3 → test code, Skill 4 → test run).
#
# Usage:
#   ./scripts/sync-bridge.sh --merge-base <commit> [--auto]
#   ./scripts/sync-bridge.sh --last-sync [--auto]
#
# Options:
#   --merge-base <commit>  Compare HEAD against this base commit
#   --last-sync            Auto-detect last sync commit as base
#   --auto                 Skip confirmation, register artifact automatically
#   -h, --help             Show help
#
# Output:
#   .artifacts/code-diffs/sync-<date>-<hash>.md  — structured code-diff artifact
#
# Integration with dev-loop-skill:
#   After this script generates the artifact, invoke:
#     Skill 2 (test-plan-generator)  → reads code-diff → generates test plan
#     Skill 3 (test-code-writer)     → reads test plan → writes pytest code
#     Skill 4 (test-runner)          → runs tests → generates e2e-report

set -euo pipefail

MERGE_BASE=""
LAST_SYNC=false
AUTO=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --merge-base) MERGE_BASE="$2"; shift 2 ;;
    --last-sync)  LAST_SYNC=true; shift ;;
    --auto)       AUTO=true; shift ;;
    -h|--help)
      sed -n '2,/^$/{ s/^# //; s/^#//; p }' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Determine base commit
if [ "$LAST_SYNC" = true ]; then
  MERGE_BASE=$(git log --grep="^sync:" -1 --format="%H" 2>/dev/null || true)
  if [ -z "$MERGE_BASE" ]; then
    echo "Error: No sync commit found in history."
    exit 1
  fi
  echo "Using last sync commit: $(git log -1 --oneline "$MERGE_BASE")"
fi

if [ -z "$MERGE_BASE" ]; then
  echo "Error: --merge-base <commit> or --last-sync required."
  exit 1
fi

# Validate commit exists
if ! git cat-file -t "$MERGE_BASE" &>/dev/null; then
  echo "Error: Commit '$MERGE_BASE' not found."
  exit 1
fi

# Ensure .artifacts directory exists
ARTIFACTS_DIR=".artifacts/code-diffs"
mkdir -p "$ARTIFACTS_DIR"

# Generate artifact ID
DATE_TAG=$(date +%Y%m%d)
SHORT_HASH=$(git rev-parse --short HEAD)
ARTIFACT_ID="sync-${DATE_TAG}-${SHORT_HASH}"
ARTIFACT_PATH="$ARTIFACTS_DIR/${ARTIFACT_ID}.md"

echo "==> Generating code-diff artifact: $ARTIFACT_ID"

# Collect diff stats
DIFF_STAT=$(git diff --stat "$MERGE_BASE"..HEAD)
FILES_CHANGED=$(git diff --name-only "$MERGE_BASE"..HEAD)
COMMIT_COUNT=$(git rev-list --count "$MERGE_BASE"..HEAD)
COMMIT_LOG=$(git log --oneline "$MERGE_BASE"..HEAD)

# Classify changes by layer
L1_FILES=$(echo "$FILES_CHANGED" | grep -E "^(socialware|channels)/" || true)
L2_FILES=$(echo "$FILES_CHANGED" | grep -E "^(autoservice|skills)/" || true)
L3_FILES=$(echo "$FILES_CHANGED" | grep -E "^plugins/" || true)
TEST_FILES=$(echo "$FILES_CHANGED" | grep -E "^tests/" || true)
OTHER_FILES=$(echo "$FILES_CHANGED" | grep -vE "^(socialware|channels|autoservice|skills|plugins|tests)/" || true)

# Count by layer
L1_COUNT=$(echo "$L1_FILES" | grep -c . || true)
L2_COUNT=$(echo "$L2_FILES" | grep -c . || true)
L3_COUNT=$(echo "$L3_FILES" | grep -c . || true)
TEST_COUNT=$(echo "$TEST_FILES" | grep -c . || true)

# Generate the artifact document
cat > "$ARTIFACT_PATH" << ARTIFACT_EOF
---
id: $ARTIFACT_ID
type: code-diff
status: draft
source: sync-bridge
merge_base: $(git rev-parse --short "$MERGE_BASE")
head: $SHORT_HASH
date: $(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S)
commits: $COMMIT_COUNT
---

# Code Diff: $ARTIFACT_ID

## Summary

- **Base:** \`$(git log -1 --oneline "$MERGE_BASE")\`
- **Head:** \`$(git log -1 --oneline HEAD)\`
- **Commits:** $COMMIT_COUNT
- **Files changed:** $(echo "$FILES_CHANGED" | grep -c . || echo 0)

## Layer Impact

| Layer | Files | Impact |
|-------|-------|--------|
| L1 (socialware/channels) | $L1_COUNT | $([ "$L1_COUNT" -gt 0 ] && echo "CHANGED" || echo "none") |
| L2 (autoservice/skills) | $L2_COUNT | $([ "$L2_COUNT" -gt 0 ] && echo "CHANGED" || echo "none") |
| L3 (plugins) | $L3_COUNT | $([ "$L3_COUNT" -gt 0 ] && echo "CHANGED" || echo "none") |
| Tests | $TEST_COUNT | $([ "$TEST_COUNT" -gt 0 ] && echo "CHANGED" || echo "none") |

## Commit Log

\`\`\`
$COMMIT_LOG
\`\`\`

## Files Changed

### L1 (socialware / channels)
$([ -n "$L1_FILES" ] && echo "$L1_FILES" | sed 's/^/- /' || echo "_(none)_")

### L2 (autoservice / skills)
$([ -n "$L2_FILES" ] && echo "$L2_FILES" | sed 's/^/- /' || echo "_(none)_")

### L3 (plugins)
$([ -n "$L3_FILES" ] && echo "$L3_FILES" | sed 's/^/- /' || echo "_(none)_")

### Tests
$([ -n "$TEST_FILES" ] && echo "$TEST_FILES" | sed 's/^/- /' || echo "_(none)_")

### Other
$([ -n "$OTHER_FILES" ] && echo "$OTHER_FILES" | sed 's/^/- /' || echo "_(none)_")

## Diff Stat

\`\`\`
$DIFF_STAT
\`\`\`

## Detailed Diff

\`\`\`diff
$(git diff "$MERGE_BASE"..HEAD -- '*.py' '*.yaml' '*.yml' '*.json' | head -500)
\`\`\`

$([ "$(git diff "$MERGE_BASE"..HEAD -- '*.py' '*.yaml' '*.yml' '*.json' | wc -l)" -gt 500 ] && echo "_(truncated to 500 lines — full diff available via git)_" || true)

## Regression Risk Assessment

$([ "$L1_COUNT" -gt 0 ] && echo "- **HIGH**: L1 framework changes affect all downstream consumers" || true)
$([ "$L2_COUNT" -gt 0 ] && echo "- **MEDIUM**: L2 business logic changes may affect tenant behavior" || true)
$([ "$L3_COUNT" -gt 0 ] && echo "- **LOW**: L3 plugin changes are tenant-scoped" || true)
$([ "$TEST_COUNT" -eq 0 ] && echo "- **WARNING**: No test file changes — verify test coverage manually" || true)

## Next Steps (dev-loop-skill)

1. Feed this artifact to **Skill 2** (test-plan-generator) to generate regression test plan
2. Use **Skill 3** (test-code-writer) to implement test cases
3. Run **Skill 4** (test-runner) to validate no regressions
ARTIFACT_EOF

echo "  Written: $ARTIFACT_PATH"
echo "  Commits: $COMMIT_COUNT"
echo "  Layer impact: L1=$L1_COUNT L2=$L2_COUNT L3=$L3_COUNT tests=$TEST_COUNT"

# Register in artifact registry if available
if [ "$AUTO" = true ]; then
  REGISTRY_SCRIPT=""
  # Check dev-loop-skill artifact registry
  for candidate in \
    ".artifacts/scripts/register.sh" \
    "../dev-loop-skills/skills/skill-6-artifact-registry/scripts/register.sh"; do
    if [ -x "$candidate" ]; then
      REGISTRY_SCRIPT="$candidate"
      break
    fi
  done

  if [ -n "$REGISTRY_SCRIPT" ]; then
    echo "==> Registering artifact in dev-loop registry..."
    "$REGISTRY_SCRIPT" \
      --type code-diff \
      --id "$ARTIFACT_ID" \
      --path "$ARTIFACT_PATH" \
      --status draft 2>/dev/null && echo "  Registered." || echo "  (registry not initialized, skipping)"
  else
    echo "  (dev-loop artifact registry not found, skipping auto-registration)"
  fi
fi

echo ""
echo "Done. To generate test plan:"
echo "  Invoke dev-loop Skill 2 with artifact: $ARTIFACT_PATH"
