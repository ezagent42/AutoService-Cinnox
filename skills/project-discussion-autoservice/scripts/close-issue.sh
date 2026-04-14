#!/bin/bash
set -euo pipefail

# 关闭 GitHub issue 并附上结论说明。

DRY_RUN=false
ISSUE_URL=""
REASON=""

usage() {
    cat <<EOF
Usage: $(basename "$0") --issue-url <url> --reason <text> [--dry-run] [--help]

Close a GitHub issue with a conclusion comment.

Options:
  --issue-url <url>   GitHub issue URL or number (required)
  --reason <text>     Closing reason/conclusion (required)
  --dry-run           Show what would be done
  --help              Show this help message

Requires: gh CLI authenticated
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --issue-url) ISSUE_URL="$2"; shift 2 ;;
        --reason) REASON="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help) usage ;;
        *) echo "Error: unknown option '$1'." >&2; exit 1 ;;
    esac
done

if [[ -z "$ISSUE_URL" || -z "$REASON" ]]; then
    echo "Error: --issue-url and --reason are required." >&2
    exit 1
fi

if $DRY_RUN; then
    echo "[dry-run] Would close issue: $ISSUE_URL"
    echo "[dry-run] With reason: $REASON"
    exit 0
fi

gh issue comment "$ISSUE_URL" --body "**结论：不是 bug**

$REASON

_由 Skill 1 (project-discussion) 分流讨论后关闭。_"

gh issue close "$ISSUE_URL" --reason "not planned"
echo "Closed issue: $ISSUE_URL"
