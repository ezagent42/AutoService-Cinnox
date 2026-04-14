# L1/L2/L3 同步与提炼工具链设计

**Date:** 2026-04-12
**Status:** Implemented — 已实施
**Prerequisite:** [三层架构设计](2026-04-09-three-layer-architecture.md) 已实施 ([实施记录](2026-04-10-three-layer-implementation.md))

---

## 1. Problem

三层架构已落地，但日常开发中的同步和提炼操作仍依赖手动 git 命令。具体痛点：

1. **下行同步无自动化** — L1 框架更新后，每个 L2/L3 fork 都要人工 `git fetch upstream && git merge upstream/main`，容易遗忘导致版本漂移
2. **上行提炼无流程化** — L3 开发出通用模式后，缺少结构化流程将改动提炼回 L2/L1，导致重复实现
3. **Fork 关系不可见** — 不知道哪些 fork 存在、各自落后多少 commit、最后一次同步是什么时候
4. **冲突预检缺失** — merge 前不知道会不会冲突，冲突后缺少指引

## 2. Goals

1. **一键同步** — `make sync` 完成当前 fork 与 upstream 的 merge
2. **批量同步** — L2 maintainer 可以一键触发所有 L3 fork 的同步
3. **提炼辅助** — 结构化流程引导开发者从 L3 提取通用改动到 L2
4. **Fork 注册表** — 集中管理 fork 清单和同步状态
5. **冲突预检** — 在 merge 前 dry-run 检测冲突

## Non-Goals

- 不做完全自动 merge（冲突必须人工解决）
- 不做跨层代码自动迁移（提炼仍需人工判断哪些代码属于 L1 vs L2）
- v1 不做 GUI 界面

---

## 3. 设计总览

```
工具链组成:

scripts/
├── sync.sh              # 下行同步: merge upstream/main
├── sync-all.sh          # 批量同步: L2 maintainer 同步所有 L3
├── refine.sh            # 上行提炼: 交互式选择改动提 PR
├── sync-status.sh       # 状态检查: 显示当前 fork 同步状态
└── fork-registry.sh     # Fork 注册表管理

docs/
└── fork-registry.yaml   # Fork 清单 (由 L2 维护)

.github/workflows/
├── upstream-sync.yml    # [已有] 周期性漂移检测
├── auto-sync-pr.yml     # [新增] 上游更新时自动创建 sync PR
└── boundary-check.yml   # [已有] 层间边界守护

Makefile targets:
├── make sync            # 同步当前 fork 与 upstream
├── make sync-status     # 查看同步状态
├── make sync-all        # (L2 only) 批量同步所有 L3
└── make refine          # 交互式提炼
```

---

## 4. 详细设计

### 4.1 Fork 注册表 (`docs/fork-registry.yaml`)

由 L2 maintainer 维护，记录所有已知 L3 fork：

```yaml
# docs/fork-registry.yaml — L3 Fork 注册表
# 由 L2 (AutoService) 维护

upstream:
  l1: h2oslabs/socialware
  l2: h2oslabs/AutoService

forks:
  - name: cinnox
    repo: cinnox/AutoService
    layer: L3
    status: active          # active | inactive | archived
    contact: alice@cinnox.com
    created: 2026-04-01
    notes: "CINNOX 客服 demo"

  - name: acme
    repo: acme/AutoService
    layer: L3
    status: active
    contact: bob@acme.com
    created: 2026-04-10
    notes: "ACME 销售 bot"
```

**用途:**
- `sync-all.sh` 读取此文件获取所有 fork 地址
- `sync-status.sh` 遍历检查各 fork 的落后 commit 数
- CI workflow 可基于此文件触发批量操作

### 4.2 下行同步: `scripts/sync.sh`

**场景:** L3 开发者想把 L2 的最新改动 merge 到自己的 fork。

```bash
#!/usr/bin/env bash
# scripts/sync.sh — 同步当前 fork 与 upstream
#
# Usage: ./scripts/sync.sh [--dry-run] [--branch <upstream-branch>]
# Default upstream branch: main

set -euo pipefail

DRY_RUN=false
UPSTREAM_BRANCH="main"

while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)  DRY_RUN=true; shift ;;
    --branch)   UPSTREAM_BRANCH="$2"; shift 2 ;;
    *)          echo "Unknown: $1"; exit 1 ;;
  esac
done

# 1. 检测 upstream remote
if ! git remote get-url upstream &>/dev/null; then
  echo "Error: 'upstream' remote not configured."
  echo "Run: git remote add upstream <upstream-repo-url>"
  exit 1
fi

# 2. Fetch upstream
echo "==> Fetching upstream..."
git fetch upstream "$UPSTREAM_BRANCH"

# 3. 显示状态
BEHIND=$(git rev-list --count HEAD..upstream/"$UPSTREAM_BRANCH")
AHEAD=$(git rev-list --count upstream/"$UPSTREAM_BRANCH"..HEAD)
echo "  Behind upstream: $BEHIND commits"
echo "  Ahead of upstream: $AHEAD commits"

if [ "$BEHIND" -eq 0 ]; then
  echo "Already up to date."
  exit 0
fi

# 4. 冲突预检 (dry-run)
echo ""
echo "==> Conflict pre-check..."
MERGE_BASE=$(git merge-base HEAD upstream/"$UPSTREAM_BRANCH")
CONFLICTING=$(git merge-tree "$MERGE_BASE" HEAD upstream/"$UPSTREAM_BRANCH" 2>/dev/null \
  | grep -c "^<<<<<<<" || true)

if [ "$CONFLICTING" -gt 0 ]; then
  echo "  ⚠ Potential conflicts detected in $CONFLICTING location(s)."
  echo "  Files likely to conflict:"
  git diff --name-only HEAD...upstream/"$UPSTREAM_BRANCH" | while read -r f; do
    # 只显示双方都修改的文件
    if git diff --name-only "$MERGE_BASE"..HEAD | grep -q "^$f$"; then
      echo "    - $f"
    fi
  done
else
  echo "  ✓ No conflicts expected — clean merge likely."
fi

if [ "$DRY_RUN" = true ]; then
  echo ""
  echo "[dry-run] Would merge $BEHIND commits from upstream/$UPSTREAM_BRANCH."
  echo "Upstream changes:"
  git log --oneline HEAD..upstream/"$UPSTREAM_BRANCH" | head -20
  exit 0
fi

# 5. 执行 merge
echo ""
echo "==> Merging upstream/$UPSTREAM_BRANCH ($BEHIND commits)..."
if git merge upstream/"$UPSTREAM_BRANCH" -m "sync: merge upstream/$UPSTREAM_BRANCH ($BEHIND commits)"; then
  echo ""
  echo "✓ Sync complete. Run 'git push' to update remote."
else
  echo ""
  echo "⚠ Merge conflicts detected. Resolve them, then:"
  echo "  git add <resolved-files>"
  echo "  git commit"
  echo ""
  echo "Conflict resolution tips:"
  echo "  - socialware/ 和 channels/ (L1): 通常接受 upstream 版本"
  echo "  - autoservice/ (L2): 通常接受 upstream 版本"
  echo "  - plugins/<tenant>/ (L3): 保留本地版本"
  exit 1
fi
```

**关键特性:**
- `--dry-run` 冲突预检，不实际 merge
- 自动检测 upstream remote 是否配置
- 冲突时提供分层解决指引
- 生成标准化 merge commit message

### 4.3 批量同步: `scripts/sync-all.sh`

**场景:** L2 maintainer 在发布框架更新后，想让所有 L3 fork 感知到。

```bash
#!/usr/bin/env bash
# scripts/sync-all.sh — 批量触发所有 L3 fork 同步
#
# 读取 docs/fork-registry.yaml, 对每个 active fork:
# - 方式 A: 通过 GitHub API 创建 sync PR (推荐)
# - 方式 B: 通过 GitHub API 触发 merge (需权限)
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

# 需要 yq 解析 YAML
if ! command -v yq &>/dev/null; then
  echo "Error: yq is required. Install: https://github.com/mikefarah/yq"
  exit 1
fi

echo "==> Reading fork registry..."

FORK_COUNT=$(yq '.forks | length' "$REGISTRY")
SYNCED=0
FAILED=0
SKIPPED=0

for i in $(seq 0 $((FORK_COUNT - 1))); do
  NAME=$(yq ".forks[$i].name" "$REGISTRY")
  REPO=$(yq ".forks[$i].repo" "$REGISTRY")
  STATUS=$(yq ".forks[$i].status" "$REGISTRY")

  if [ "$STATUS" != "active" ]; then
    echo "  ⊘ $NAME ($REPO) — skipped (status: $STATUS)"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  echo -n "  → $NAME ($REPO)... "

  if [ "$DRY_RUN" = true ]; then
    # 检查落后 commit 数
    BEHIND=$(gh api "repos/$REPO/compare/main...$(yq '.upstream.l2' "$REGISTRY"):main" \
      --jq '.behind_by' 2>/dev/null || echo "?")
    echo "behind $BEHIND commits [dry-run]"
    continue
  fi

  # 通过 GitHub API 创建同步 PR
  if gh api "repos/$REPO/merges" \
      -f base=main -f head=upstream/main \
      --method POST &>/dev/null; then
    echo "✓ synced"
    SYNCED=$((SYNCED + 1))
  else
    # 可能有冲突，创建 PR 让人工处理
    echo "⚠ conflict — creating PR"
    gh pr create \
      --repo "$REPO" \
      --title "sync: merge upstream/main" \
      --body "Automated sync from upstream. Please resolve conflicts if any." \
      --base main \
      --head upstream/main 2>/dev/null || true
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo "==> Summary: $SYNCED synced, $FAILED need manual merge, $SKIPPED skipped"
```

### 4.4 上行提炼: `scripts/refine.sh`

**场景:** L3 开发者在 `plugins/cinnox/tools.py` 中写了一个通用的功能，想提炼到 L2。

```bash
#!/usr/bin/env bash
# scripts/refine.sh — 交互式提炼辅助
#
# 引导开发者:
# 1. 选择要提炼的 commit 或文件
# 2. 判断目标层 (L2 or L1)
# 3. 创建提炼分支
# 4. 准备 PR
#
# Usage: ./scripts/refine.sh [commit-hash | file-path]

set -euo pipefail

TARGET="${1:-}"

echo "=== 提炼辅助 (Refine Assistant) ==="
echo ""

# Step 1: 确定提炼来源
if [ -z "$TARGET" ]; then
  echo "最近的本地 commit (未在 upstream 中):"
  echo ""
  git log --oneline upstream/main..HEAD 2>/dev/null | head -20 || \
    git log --oneline -20
  echo ""
  read -rp "输入 commit hash 或文件路径: " TARGET
fi

# Step 2: 判断目标层
echo ""
echo "提炼目标层:"
echo "  1) L2 (autoservice) — 通用客服能力，其他租户也能用"
echo "  2) L1 (socialware)  — 框架级能力，换个 app 也能用"
echo ""
read -rp "选择 [1/2]: " LAYER_CHOICE

case "$LAYER_CHOICE" in
  1) TARGET_LAYER="L2"; BRANCH_PREFIX="upstream" ;;
  2) TARGET_LAYER="L1"; BRANCH_PREFIX="upstream-l1" ;;
  *) echo "Invalid choice"; exit 1 ;;
esac

# Step 3: 层级判断检查
echo ""
echo "==> 层级判断清单:"
if [ "$TARGET_LAYER" = "L1" ]; then
  echo "  □ 换一个完全不同的 app (教育/医疗), 这个功能还有用吗?"
  echo "  □ 是否包含 'customer'/'agent'/'CRM' 等客服词汇?"
  echo "  □ 是否依赖 autoservice/ 中的模块?"
  echo ""
  echo "  如果以上任一为 '否', 可能应该提炼到 L2 而非 L1。"
else
  echo "  □ 换一个租户, 这个功能还有用吗?"
  echo "  □ 是否包含租户专属数据 (客户名、产品名)?"
  echo "  □ 是否依赖 plugins/<tenant>/ 中的模块?"
  echo ""
  echo "  如果以上任一为 '否', 可能应该留在 L3。"
fi

read -rp "确认继续? [y/N]: " CONFIRM
[ "$CONFIRM" != "y" ] && { echo "Aborted."; exit 0; }

# Step 4: 创建提炼分支
BRANCH_NAME="$BRANCH_PREFIX/refine-$(date +%Y%m%d)-$(echo "$TARGET" | tr '/' '-' | head -c 30)"
echo ""
echo "==> Creating branch: $BRANCH_NAME"
git checkout -b "$BRANCH_NAME"

# Step 5: 应用改动
if git cat-file -t "$TARGET" &>/dev/null; then
  echo "==> Cherry-picking commit: $TARGET"
  git cherry-pick "$TARGET" --no-commit
  echo "Changes staged. Review and adjust before committing."
elif [ -f "$TARGET" ]; then
  echo "==> File: $TARGET"
  echo "Edit this file to extract only the generalizable parts."
  echo "Remember to update imports (socialware.* for L1, autoservice.* for L2)."
else
  echo "==> No auto-extract. Manually add your changes to this branch."
fi

echo ""
echo "==> Next steps:"
echo "  1. Review and adjust the changes"
echo "  2. git add <files> && git commit -m 'refine: <description>'"
echo "  3. git push origin $BRANCH_NAME"
echo "  4. Create PR:"
if [ "$TARGET_LAYER" = "L1" ]; then
  echo "     Target: h2oslabs/socialware (L1 upstream)"
else
  echo "     Target: h2oslabs/AutoService (L2 upstream)"
fi
echo "     gh pr create --title 'refine: <description>'"
```

### 4.5 同步状态: `scripts/sync-status.sh`

```bash
#!/usr/bin/env bash
# scripts/sync-status.sh — 显示当前 fork 同步状态
#
# Usage: ./scripts/sync-status.sh

set -euo pipefail

echo "=== Fork Sync Status ==="
echo ""

# 检测当前层级
if [ -f ".autoservice-info.yaml" ]; then
  LAYER=$(grep "^layer:" .autoservice-info.yaml 2>/dev/null | awk '{print $2}' || echo "?")
else
  # 通过目录判断
  if [ -d "socialware" ] && [ -d "autoservice" ]; then
    LAYER="L2"
  else
    LAYER="?"
  fi
fi

echo "Current layer: $LAYER"
echo ""

# Upstream 状态
if git remote get-url upstream &>/dev/null; then
  UPSTREAM_URL=$(git remote get-url upstream)
  echo "Upstream: $UPSTREAM_URL"

  git fetch upstream main --quiet 2>/dev/null || true

  BEHIND=$(git rev-list --count HEAD..upstream/main 2>/dev/null || echo "?")
  AHEAD=$(git rev-list --count upstream/main..HEAD 2>/dev/null || echo "?")
  LAST_SYNC=$(git log --oneline --grep="^sync:" -1 --format="%cd (%h %s)" \
    --date=short 2>/dev/null || echo "never")

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

# Layer-specific info
echo ""
if [ "$LAYER" = "L2" ] && [ -f "docs/fork-registry.yaml" ]; then
  echo "=== Downstream Forks ==="
  if command -v yq &>/dev/null; then
    yq '.forks[] | .name + " (" + .repo + ") — " + .status' \
      docs/fork-registry.yaml 2>/dev/null
  else
    echo "  (install yq for detailed fork info)"
    grep "name:" docs/fork-registry.yaml | sed 's/.*name: /  - /'
  fi
fi

echo ""
echo "=== Layer File Modification Check ==="
# 检查本 fork 是否修改了不应修改的层
CURRENT_BRANCH=$(git branch --show-current)
if git remote get-url upstream &>/dev/null; then
  MODIFIED_L1=$(git diff --name-only upstream/main...HEAD -- socialware/ channels/ 2>/dev/null | wc -l)
  MODIFIED_L2=$(git diff --name-only upstream/main...HEAD -- autoservice/ 2>/dev/null | wc -l)

  if [ "$LAYER" = "L3" ]; then
    [ "$MODIFIED_L1" -gt 0 ] && echo "  ⚠ L1 files modified ($MODIFIED_L1 files) — should PR to L1 upstream"
    [ "$MODIFIED_L2" -gt 0 ] && echo "  ⚠ L2 files modified ($MODIFIED_L2 files) — should PR to L2 upstream"
  fi
  if [ "$LAYER" = "L2" ]; then
    [ "$MODIFIED_L1" -gt 0 ] && echo "  ⚠ L1 files modified ($MODIFIED_L1 files) — should PR to L1 upstream"
  fi
  [ "$MODIFIED_L1" -eq 0 ] && [ "$MODIFIED_L2" -eq 0 ] && echo "  ✓ No cross-layer modifications"
fi
```

### 4.6 GitHub Actions: 自动创建 Sync PR

当 L2 main 更新后，自动向所有 L3 fork 创建同步 PR：

```yaml
# .github/workflows/auto-sync-pr.yml
# 放在 L2 repo 中。当 main 有 push 时，向已注册的 L3 fork 创建 sync PR。
name: Auto Sync PR

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  notify-forks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install yq
        run: |
          wget -qO /usr/local/bin/yq \
            https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64
          chmod +x /usr/local/bin/yq

      - name: Create sync PRs for active forks
        env:
          GH_TOKEN: ${{ secrets.FORK_SYNC_TOKEN }}
        run: |
          REGISTRY="docs/fork-registry.yaml"
          [ ! -f "$REGISTRY" ] && { echo "No registry"; exit 0; }

          FORK_COUNT=$(yq '.forks | length' "$REGISTRY")

          for i in $(seq 0 $((FORK_COUNT - 1))); do
            NAME=$(yq ".forks[$i].name" "$REGISTRY")
            REPO=$(yq ".forks[$i].repo" "$REGISTRY")
            STATUS=$(yq ".forks[$i].status" "$REGISTRY")

            [ "$STATUS" != "active" ] && continue

            echo "Syncing $NAME ($REPO)..."

            # 尝试 fast-forward merge
            gh api "repos/$REPO/merges" \
              -f base=main \
              -f head="${{ github.repository_owner }}/AutoService:main" \
              -f commit_message="sync: auto-merge upstream/main" \
              --method POST 2>/dev/null && {
                echo "  ✓ $NAME synced"
                continue
            }

            # 有冲突，创建 PR
            echo "  ⚠ $NAME has conflicts, creating PR..."
            # Fork 方需要在自己的 repo 中配置 workflow 接收此通知
          done
```

### 4.7 Makefile 集成

```makefile
# --- Sync & Refine ---
sync:
	@bash scripts/sync.sh

sync-dry:
	@bash scripts/sync.sh --dry-run

sync-status:
	@bash scripts/sync-status.sh

sync-all:
	@bash scripts/sync-all.sh

refine:
	@bash scripts/refine.sh
```

---

## 5. 工作流全景

### 5.1 下行同步 (日常)

```
L1 maintainer pushes to socialware/main
  │
  ├──[auto]──→ L2 GitHub Action detects (upstream-sync.yml)
  │             → 提示 "L1 has N new commits"
  │
  └──[manual]─→ L2 developer runs: make sync
                 → git fetch upstream && git merge upstream/main
                 → push to L2/main
                   │
                   ├──[auto]──→ auto-sync-pr.yml → 为每个 L3 创建 sync PR
                   │
                   └──[manual]─→ L3 developer runs: make sync
                                  → merge upstream/main
```

### 5.2 上行提炼 (按需)

```
L3 developer 在 plugins/cinnox/ 中实现了通用功能
  │
  └──→ make refine
       → 交互式选择: commit or file
       → 层级判断检查 (L2 or L1?)
       → 创建 upstream/* 分支
       → 开发者调整代码、更新 import
       → git push + gh pr create
       → L2 maintainer review → merge
       → L2 再决定是否继续提炼到 L1
```

### 5.3 状态监控 (定期)

```
每周一 09:00 UTC (cron):
  upstream-sync.yml 检测各 fork 漂移
  → 落后 > 50 commits → GitHub warning

随时手动:
  make sync-status → 显示当前 fork 的同步状态 + 跨层修改检查
```

---

## 6. 实施优先级

| 优先级 | 工具 | 价值 | 复杂度 |
|--------|------|------|--------|
| **P0** | `scripts/sync.sh` + Makefile | 最常用操作，每次上游更新都要用 | 低 |
| **P0** | `scripts/sync-status.sh` | 快速了解当前状态 | 低 |
| **P1** | `docs/fork-registry.yaml` | 批量操作的基础 | 低 |
| **P1** | `scripts/refine.sh` | 引导开发者正确提炼 | 中 |
| **P2** | `scripts/sync-all.sh` | L2 maintainer 用，当前 fork 数量少 | 中 |
| **P2** | `auto-sync-pr.yml` | 自动化批量同步 | 中 |

**建议实施顺序:** P0 先落地（sync + status），P1 在第一次提炼需求出现时实现，P2 在 fork 数量 > 3 时实现。

---

## 7. 安全考虑

1. **`sync-all.sh` / `auto-sync-pr.yml` 需要跨 repo 权限** — 使用 GitHub App 或 PAT with repo scope
2. **`refine.sh` 不自动 push** — 只创建本地分支，push 和 PR 由开发者手动确认
3. **冲突解决指引按层级** — L1/L2 文件优先接受 upstream，L3 文件优先保留本地
4. **Fork 注册表不含 secret** — 只有 repo URL 和元数据，不含 credentials
