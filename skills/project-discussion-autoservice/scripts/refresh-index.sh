#!/bin/bash
set -euo pipefail

# 刷新 Skill 1 的模块索引。
# 当检测到文件移动/重命名、test-runner 失败、或新模块出现时调用。

DRY_RUN=false
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
MODULE=""
ALL=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--module <name>] [--all] [--dry-run] [--help]

Refresh Skill 1 module index.

Options:
  --module <name>   Refresh a specific module
  --all             Refresh all modules
  --dry-run         Show what would be refreshed
  --help            Show this help message
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --module) MODULE="$2"; shift 2 ;;
        --all) ALL=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help) usage ;;
        *) echo "Error: unknown option '$1'." >&2; exit 1 ;;
    esac
done

if [[ -z "$MODULE" && "$ALL" != "true" ]]; then
    echo "Error: specify --module <name> or --all." >&2
    exit 1
fi

if $DRY_RUN; then
    if $ALL; then
        echo "[dry-run] Would refresh all modules in $PROJECT_ROOT"
    else
        echo "[dry-run] Would refresh module '$MODULE' in $PROJECT_ROOT"
    fi
    exit 0
fi

cd "$PROJECT_ROOT"
echo "=== Skill 1 Index Refresh ==="

if $ALL; then
    echo "Scope: all modules"
    for runner in "$(dirname "$0")"/test-*.sh; do
        [[ -f "$runner" ]] || continue
        name=$(basename "$runner")
        echo "  Running: $name"
        if bash "$runner" > /dev/null 2>&1; then
            echo "    → PASS"
        else
            echo "    → FAIL (test-runner may need updating)"
        fi
    done
else
    echo "Scope: module '$MODULE'"
    RUNNER="$(dirname "$0")/test-${MODULE}.sh"
    if [[ -f "$RUNNER" ]]; then
        echo "Running test-runner: test-${MODULE}.sh"
        bash "$RUNNER" 2>&1
    else
        echo "No test-runner found for module '$MODULE'."
    fi
fi

echo "Index refresh complete."
