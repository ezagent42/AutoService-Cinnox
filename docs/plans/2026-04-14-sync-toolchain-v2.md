# 同步与提炼工具链 v2 — 自动化升级

**Date:** 2026-04-14
**Status:** Implemented — 已实施
**Prerequisite:** [v1 工具链](2026-04-12-sync-refine-toolchain.md) 已实施

---

## 1. Problem

v1 工具链解决了基本的同步/提炼操作，但仍有多处需要手动干预：

| 操作 | v1 状态 | 问题 |
|------|---------|------|
| L3 fork 注册 | 手动编辑 YAML | 易出错，不校验 |
| 正向同步 (sync) | 交互式 | CI/脚本无法调用 |
| 反向提炼 (refine) | 全交互式 | CI/脚本无法调用 |
| 全 fork 状态 | 单 fork 维度 | L2 maintainer 无法看到全景 |
| dev-loop-skill 集成 | 无 | sync 后无法自动触发测试验证 |
| fork 反注册 | 不存在 | 无法归档停用的 fork |

## 2. Goals

1. 所有脚本支持 `--auto` 非交互模式，可被 CI/其他脚本调用
2. Fork 注册/反注册自动化，包括 GitHub repo 校验
3. `sync-status --all` 聚合全部 fork 状态
4. `sync-bridge.sh` 桥接 sync/refine 操作与 dev-loop-skill 测试流水线
5. CI workflow 增加 post-sync 测试验证

## 3. Design

### 3.1 两层架构

```
┌─────────────────────────────────────────────────┐
│  sync/refine 脚本（git 操作层）                    │
│  register-fork / sync / refine / sync-all        │
│  ↕ 产出 code-diff artifact                       │
├─────────────────────────────────────────────────┤
│  dev-loop-skill（测试验证层）                      │
│  Skill 2 → 测试计划                               │
│  Skill 3 → 测试代码                               │
│  Skill 4 → 执行 + 回归检测                        │
│  Skill 6 → artifact 追踪                          │
└─────────────────────────────────────────────────┘
```

桥接通过 `.artifacts/code-diffs/` 目录衔接。`sync-bridge.sh` 负责在 sync/refine 完成后生成结构化的 code-diff artifact，dev-loop Skill 2 可直接消费。

### 3.2 完整自动 sync 流程

```
make sync-auto
  ├── 1. sync.sh --auto          # git merge upstream/main（无冲突时自动完成）
  ├── 2. sync-bridge.sh --auto   # 生成 code-diff artifact
  ├── 3. Skill 2                  # 从 code-diff 生成测试计划
  ├── 4. Skill 3                  # 生成测试代码
  ├── 5. Skill 4                  # 跑测试 + 回归检测
  └── 6. 全绿 → done             # 有回归 → 创建 issue
```

### 3.3 完整自动 refine 流程

```
make refine-auto COMMIT=abc123 LAYER=L2
  ├── 1. refine.sh --auto        # cherry-pick + 创建分支
  ├── 2. sync-bridge.sh --auto   # 生成 code-diff artifact
  ├── 3. Skill 2 + 3 + 4         # 测试验证
  ├── 4. --pr → gh pr create     # 自动创建 PR 到 upstream
  └── 5. Skill 5 verify          # 创建 issue 关联 PR
```

## 4. Implementation

### 4.1 新增脚本

| 脚本 | 用途 | 关键功能 |
|------|------|---------|
| `scripts/register-fork.sh` | 注册 L3 fork | `--repo`/`--name` 必填，`--auto` 跳过确认并自动 commit，GitHub repo 校验，防重复注册，支持重新激活已归档 fork |
| `scripts/unregister-fork.sh` | 归档/停用 fork | `--status archived\|inactive`，awk 跨平台替换 |
| `scripts/sync-bridge.sh` | 生成 code-diff artifact | 按层分类文件变更，生成带 YAML frontmatter 的 markdown，包含回归风险评估，尝试注册到 dev-loop artifact registry |

### 4.2 改造脚本

| 脚本 | 改动 |
|------|------|
| `scripts/sync.sh` | 新增 `--auto`：无冲突自动 merge，有冲突 exit 1；merge 成功后自动调 `sync-bridge.sh` 生成 artifact |
| `scripts/refine.sh` | 新增 `--auto --commit <hash> --layer L1\|L2 [--message] [--pr]`：全参数化，支持自动 cherry-pick → commit → push → PR |
| `scripts/sync-status.sh` | 新增 `--all`：读 fork-registry 遍历所有 fork，通过 GitHub API 查 behind/ahead；`--json` 输出结构化数据 |
| `.github/workflows/auto-sync-pr.yml` | 新增 `verify` job：sync 后跑 pytest + 生成 sync-bridge artifact |

### 4.3 新增 Makefile targets

```makefile
sync-auto          # sync.sh --auto
sync-status-all    # sync-status.sh --all
register-fork      # REPO=owner/repo NAME=tenant [CONTACT=] [AUTO=1]
unregister-fork    # REPO=owner/repo [STATUS=archived] [AUTO=1]
refine-auto        # COMMIT=hash LAYER=L2 [MSG=] [PR=1]
sync-bridge        # sync-bridge.sh --last-sync --auto
```

## 5. Testing Results

| 测试 | 结果 | 说明 |
|------|------|------|
| register-fork --help | PASS | 正确显示用法 |
| unregister-fork --help | PASS | |
| sync --help | PASS | 显示 --auto 选项 |
| refine --help | PASS | 显示 --auto/--commit/--layer/--pr |
| sync-status --help | PASS | 显示 --all/--json |
| sync-bridge --help | PASS | 显示 --merge-base/--last-sync |
| register-fork --auto | PASS | 正确追加到 fork-registry.yaml，自动 commit |
| 重复注册拦截 | PASS | exit 1 + 提示信息 |
| unregister-fork --auto | PASS | status: active → archived（修复了 sed 跨平台 bug，改用 awk） |
| 重新激活已归档 fork | PASS | status: archived → active |
| sync-status (单 fork) | PASS | 正确显示 layer/upstream/behind/ahead |
| sync-status --all | PASS | 表格显示所有 fork，API 失败时优雅降级为 "?" |
| sync-bridge --merge-base | PASS | 生成结构化 code-diff artifact，按层分类 |
| refine --auto 参数校验 | PASS | 缺 --commit/--layer/--layer 无效值均 exit 1 |
| sync --auto (无 upstream) | PASS | 正确报错 |

### 修复的 bug

1. **sed 多行替换在 MSYS/Git Bash 下失败**: `sed -i '/pattern/{n;n;s/...}` 语法不兼容。改用 `awk` 做跨平台匹配替换
2. **gh API 失败时输出泄漏**: 非公开 repo 的 API 错误 JSON 显示在表格中。改用 `grep -q` 先校验再提取

## 6. Script Inventory (完整清单)

| 脚本 | 优先级 | 模式 | 测试状态 |
|------|--------|------|---------|
| `sync.sh` | P0 | interactive + `--auto` + `--dry-run` | 已测试 |
| `sync-status.sh` | P0 | single + `--all` + `--json` | 已测试 |
| `register-fork.sh` | P0 | interactive + `--auto` | 已测试 |
| `unregister-fork.sh` | P0 | interactive + `--auto` | 已测试 |
| `refine.sh` | P1 | interactive + `--auto --commit --layer [--pr]` | 参数校验已测试，cherry-pick 需实际 commit |
| `sync-all.sh` | P2 | `--dry-run` | 需 yq + gh + 注册 fork |
| `sync-bridge.sh` | P1 | `--merge-base` / `--last-sync` + `--auto` | 已测试 |
| `auto-sync-pr.yml` | P2 | CI push trigger | 需 GitHub Actions 环境 |
| `fork-registry.yaml` | 数据 | — | 被脚本读写 |

## 7. dev-loop-skill 能力映射

| Dev-Loop Skill | 在 sync/refine 中的角色 |
|---|---|
| Skill 2 (test-plan-generator) | 读 sync-bridge 产出的 code-diff → 生成回归测试计划 |
| Skill 3 (test-code-writer) | 从测试计划生成 pytest 代码 |
| Skill 4 (test-runner) | 执行测试 + 区分 regression vs new-case |
| Skill 5 (feature-eval) | refine 时 verify 模式创建 GitHub issue |
| Skill 6 (artifact-registry) | 全链路 artifact 追踪 (code-diff → test-plan → e2e-report) |

## 8. Future Work

| # | 能力 | 复杂度 | 说明 |
|---|------|--------|------|
| 1 | PR label `refine:L2` 自动触发 cherry-pick | 中 | GitHub Actions 监听 L3 PR label |
| 2 | Fork 状态 dashboard（定时生成 markdown 报告） | 低 | `sync-status --all --json` + 模板 |
| 3 | Slack/Feishu 通知 | 低 | CI workflow 加 webhook step |
| 4 | `sync-bridge.sh` 自动触发 Skill 2→3→4 | 中 | 需 dev-loop-skill CLI 入口 |
