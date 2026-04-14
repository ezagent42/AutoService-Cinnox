# Socialware 三层架构设计 — L1/L2/L3 全链路 Fork 策略

**Date:** 2026-04-09
**Version:** 4.0
**Status:** Approved
**Authors:** Allen Woods + Claude

### 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0 | 2026-04-09 | 初版: 三层模型 + Package+Worktree 混合策略 (方案 C) |
| 2.0 | 2026-04-09 | L3 统一走 fork (方案 D), 弃用 worktree; 新增子租户 (L3→L3') 分析; 新增 `.git` 安全分析 |
| 3.0 | 2026-04-09 | 全 fork 风险全景: 10 类风险识别 + 分级防控体系 (P0/P1/P2); 新增 CI 自动化方案 (sync bot, boundary check, reusable workflow); 新增 fork 注册表和生命周期管理 |
| 4.0 | 2026-04-10 | L1→L2 从 Python 包依赖改为 fork (方案 E: 全链路 Fork); 跨语言扩展性分析; 统一同步机制 (全链路 git merge); 简化迁移路径 (无需 shim 兼容层) |

---

## 1. Problem & Goals

### Problem

AutoService (v0.1.0) 采用扁平的两层 fork 模型：upstream repo 同时包含框架代码和业务代码，客户 fork 在同一 repo 内扩展。实际开发中出现以下痛点：

1. **边界模糊** — `autoservice/` 包中，通用框架模块（`core.py`, `plugin_loader.py`）与客服业务模块（`customer_manager.py`, `crm.py`）平铺共存，无结构性区分
2. **提炼困难** — 客户 fork 改动混合了框架改进和业务逻辑，cherry-pick 回 upstream 需要手动拆分 commit（实证：commit `ee07d24` "cherry-picked from Cinnox fork"）
3. **灰色地带** — `config.py` 硬编码了 `marketing`/`customer-service` 的 domain 数据，`session.py` 硬编码了 `DOMAIN_PREFIXES`，框架代码被业务语义污染
4. **复用受限** — 如果要基于同一框架做一个 "AI 教育助手"（非客服），必须 fork 整个 repo 再删除客服相关代码

### Goals

1. **三层分离** — L1 (socialware base) / L2 (app template) / L3 (tenant instance) 各自独立演进
2. **双向同步** — L1 更新能高效同步到所有 L2，L2 更新能同步到所有 L3；反向提炼路径同样清晰
3. **开发态零摩擦** — L1 和 L2 同步迭代时无需发版环路，改了立刻生效
4. **租户隔离** — 每个 L3 拥有独立 repo，代码和数据天然隔离
5. **支持子租户** — L3 可以基于 L3 创建子租户 (L3')，不增加架构复杂度

### Non-Goals

- 不做多租户 SaaS 运行时（每个租户 = 独立部署）
- 不做 L1 的 plugin marketplace（v1 阶段）
- 不做自动化的跨层代码迁移工具

---

## 2. 方案评估

### 2.1 候选方案

评估了五种 L1↔L2↔L3 的组织方式：

#### 方案 A：纯 Fork 链

```
L1 repo → fork → L2 repo → fork → L3 repo
```

L1/L2/L3 每一层都是上一层的 GitHub fork。

#### 方案 B：纯分支 (Branch/Worktree)

```
单一 repo, 多分支:
  main (L1) → branch template/* (L2) → branch tenant/* (L3)
```

所有层在同一个 repo 的不同分支中。

#### 方案 C：Package + Worktree 混合

```
L1 = 独立 Python 包
L2 = 独立 repo, 依赖 L1
L3 = L2 的 worktree 分支 (demo) 或 fork (交付)
```

L3 分两类：内部 demo 用 worktree 分支，正式交付用 fork。

#### 方案 D：Package + Fork (统一 Fork)

```
L1 = 独立 Python 包
L2 = 独立 repo, 依赖 L1
L3 = 统一走 fork (无论 demo 还是交付)
```

#### 方案 E：全链路 Fork

```
L1 repo → fork → L2 repo → fork → L3 repo
目录命名空间隔离: socialware/ (L1) vs autoservice/ (L2) vs plugins/ (L3)
CODEOWNERS + CI 边界守护
```

L1/L2/L3 全部走 fork，但通过**目录级命名空间**实现层间边界（不同于方案 A 的隐性约定）。

### 2.2 对比矩阵

| 维度 | A: 纯 Fork 链 | B: 纯分支 | C: Pkg+Worktree | D: Pkg+Fork | **E: 全链路 Fork** |
|------|:---:|:---:|:---:|:---:|:---:|
| L1/L2 边界清晰度 | 差 (隐性) | 差 (分支≠隔离) | 强制 (包边界) | 强制 (包边界) | **目录命名空间 + CODEOWNERS** |
| L1→L2 同步 | merge | merge (同 repo) | 版本升级 | 版本升级 | **merge (统一机制)** |
| L2→L1 回馈 | cherry-pick | cherry-pick | 独立 PR | 独立 PR | **跨 repo PR** |
| L3 提炼到 L2 | 跨 repo PR | cherry-pick | cherry-pick | 跨 repo PR | **跨 repo PR** |
| 租户隔离 | 好 | 无 | 部分 | 完全 | **完全** |
| 跨语言支持 | 好 | 好 | **仅 Python** | **仅 Python** | **好 (语言无关)** |
| 非代码资产传播 | 自然 | 自然 | 需手动同步 | 需手动同步 | **自然 (git merge)** |
| 开发态零延迟 | 同 repo | 同 repo | editable install | editable install | **同 repo (fork 内直接引用)** |
| 新租户成本 | ~30 分钟 | ~5 分钟 | ~5 分钟 (demo) | ~30 分钟 | **~30 分钟 (可脚本化)** |
| Code review | 原生 PR | 无原生流程 | 混合 | 原生 PR | **原生 PR** |
| 误操作爆炸半径 | 单个 repo | 所有租户 | 所有 demo | 单个 repo | **单个 repo** |
| 子租户 (L3→L3') | fork 链加深 | 分支爆炸 | 混合问题加倍 | plugin 或 fork | **plugin 或 fork** |

### 2.3 各方案深度分析

#### 方案 A 的核心问题

1. **L1/L2 无包边界** — L1 和 L2 的代码在同一个 repo 中，fork 只是拷贝，修改 L1 代码毫无阻拦
2. **多层 fork 的 merge 冲突累积** — L1 的改动到 L3 要经过两次 merge，冲突概率翻倍
3. **GitHub 不支持 "fork 的 fork" 直接向 L1 提 PR** — 回馈路径断裂
4. **每个 L3 fork 含完整 L1+L2 代码** — 10 个租户 = 10 份框架代码拷贝，版本漂移不可控

实际案例：当前项目 commit `ee07d24` 的 cherry-pick 就是此模式的痛点体现。

#### 方案 B 的核心问题

1. **L1 和 L2 无结构性边界** — 分支是时间线的分叉，不是模块的隔离
2. **租户权限无法隔离** — GitHub 不支持分支级读权限（需 GitHub Enterprise 或 GitLab）
3. **CI/CD 复杂** — 单一 repo 需要按分支前缀配置不同 pipeline，矩阵爆炸

#### 方案 C 的核心问题：`.git` 安全缺陷

方案 C 在 demo 阶段使用 worktree 分支。这带来一个结构性安全风险：

**所有 tenant 分支的完整历史存储在同一个 `.git/` 目录中。**

```
autoservice/.git/
├── objects/           ← 所有 tenant 的所有 commit 的所有文件内容
├── refs/heads/
│   ├── main
│   ├── tenant/cinnox-demo     ← cinnox 的全部代码
│   ├── tenant/acme-demo       ← acme 的全部代码
│   └── tenant/edu-demo        ← edu 的全部代码
```

安全风险：

```bash
# 任何有 repo 读权限的人，一条命令看到所有租户
git branch -a
git show tenant/acme-demo:plugins/acme/tools.py   # 不用切分支就能看

# 即使删除了分支，对象仍在 .git/objects/ 中
git branch -D tenant/old-customer
git fsck --unreachable   # 能找到 "已删除" 分支的内容

# clone 也是全量的
git clone <repo>   # 默认拉取所有分支引用
# --single-branch 只限制初始 fetch，后续 git fetch 仍拿到所有分支
```

即使是内部 demo 阶段，不同租户也可能涉及：
- 不同客户的业务逻辑（插件代码本身就是商业信息）
- 不同客户的 mock 数据（可能基于真实数据脱敏）
- 不同客户的 API endpoint / credential placeholder

GitHub 平台层面无法限制分支级读权限。**有 repo 读权限 = 能看到所有租户的所有代码。**

此外，方案 C 还有以下问题：
- Demo → 交付切换并非 "一条命令"（需迁移 CI/CD、更新 remote、通知人员）
- worktree 的提炼没有 PR review 流程，质量保障弱
- `git push --force` 等误操作会影响所有 demo 租户

#### 方案 D 为何优于方案 C

方案 D 在 L1/L2 层面与方案 C 相同（L1 为独立包），但 L3 统一走 fork，解决了方案 C 的所有安全问题：

1. **安全隔离**：每个 L3 是独立 repo，由 GitHub 平台保证读权限隔离
2. **一致性**：不区分 demo/交付，管理模型统一，无状态切换成本
3. **Code review**：L3 向 L2 的提炼天然走 GitHub PR，有 review 流程
4. **误操作隔离**：一个 fork 的 force push 不影响其他 fork

但方案 D 仍有一个结构性约束：**L1→L2 走 Python 包依赖，限定了整个框架栈为 Python。**

#### 方案 E 为何优于方案 D：跨语言扩展性

方案 D/C 的 L1 是独立 Python 包，这意味着：

1. **L1 只能包含 Python 代码** — 渠道层 (`feishu/`, `web/`) 作为 Python 包分发，但未来可能需要 Go/Rust 的高性能网关、Node.js 前端、或其他语言的 channel adapter
2. **非代码资产无法通过 pip 分发** — CI 模板 (`.github/workflows/`)、Makefile、CLAUDE.md、skill 模板、文档等无法作为 Python 依赖传播。L2 需要手动复制并维护这些文件
3. **两套同步机制** — L1→L2 走 `pip install` 版本升级，L2→L3 走 `git merge upstream/main`，开发者需要理解两种不同的同步模型
4. **开发态需要额外配置** — L1/L2 共同迭代需要 `[tool.uv.sources]` editable install 配置，而 fork 模型下直接在同一 repo 内修改即可

方案 E（全链路 Fork）解决了以上所有问题：

1. **语言无关** — L1 可以包含任何语言的代码、配置模板、CI workflow、文档。fork 是 repo 级拷贝，不受包管理器限制
2. **非代码资产自然传播** — `.github/workflows/`、`Makefile`、`CLAUDE.md`、`templates/` 等通过 `git merge upstream/main` 自动同步到 L2
3. **统一同步机制** — L1→L2 和 L2→L3 使用完全相同的 `git merge upstream/main` 流程，心智模型统一
4. **零配置开发态** — fork 内 `socialware/` 和 `autoservice/` 目录共存，修改即生效，无需 editable install

**方案 E 与方案 A 的关键区别：**

方案 A 的问题是 L1/L2 无结构性边界。方案 E 通过以下机制解决：

| 机制 | 效果 |
|------|------|
| **目录命名空间** | `socialware/` = L1 拥有，`autoservice/` = L2 拥有，物理目录分离 |
| **CODEOWNERS** | L2 开发者修改 `socialware/` 需要 L1 maintainer review |
| **CI boundary check** | PR 自动检测跨层修改并发出警告 |
| **L1 release 分支** | L1 通过 release 分支管理版本，L2 选择性 merge |

### 2.4 Diff/提炼效率深入对比

这是 worktree 被认为最有优势的维度，逐操作对比：

| 操作 | Worktree | Fork | 实际差距 |
|------|----------|------|----------|
| 查看租户与 L2 的差异 | `git diff main...tenant/x` | `git fetch cinnox && git diff main...cinnox/main` | **+2~10 秒 (fetch)** |
| cherry-pick 到 L2 | `git cherry-pick <hash>` | `git cherry-pick <hash>` (fetch 后同语法) | **零** |
| 文件级提取 | `git checkout tenant/x -- file` | `git checkout cinnox/main -- file` | **零** |
| 同时查看多个租户代码 | 多个 worktree 目录已存在 | 多个 clone 或 `git remote add` | **首次多 1-2 分钟** |
| 批量同步 L2 到所有租户 | `for b in tenant/*; merge main` | 每个 fork 单独 fetch+merge | **中等（可脚本化）** |
| 提炼质量保障 | 无原生流程 | **GitHub PR + review** | **Fork 更优** |

**结论：Worktree 每次提炼节省约 2-10 秒的 fetch 时间，但缺少 PR review 流程。在 10 个租户的生命周期内，fetch 的总额外时间 < 1 小时；而一次没有 review 的错误提炼可能造成数小时的排查成本。**

### 2.5 新租户创建成本深入对比

| 步骤 | Worktree | Fork |
|------|----------|------|
| 创建代码空间 | `git branch` (1 秒) | `gh repo fork` (1-2 分钟) |
| 配置上游同步 | 0 (同 repo) | `git remote add upstream` (30 秒) |
| CI/CD 配置 | 0 (共享 main pipeline) | 配置新 repo 的 Actions/secrets (10-30 分钟) |
| 添加租户内容 | mkdir + plugin.yaml (5 分钟) | 同左 (5 分钟) |
| **总计** | **~5 分钟** | **~20-40 分钟** |

但这是一次性成本，且可以通过脚本模板化：

```bash
# create-tenant.sh — 一键创建 L3 fork
TENANT=$1
ORG=${2:-h2oslabs}

gh repo fork h2oslabs/AutoService --org "$ORG" --fork-name "$TENANT-autoservice" --clone
cd "$TENANT-autoservice"
git remote add upstream git@github.com:h2oslabs/AutoService.git
mkdir -p "plugins/$TENANT"
cp -r plugins/_example/* "plugins/$TENANT/"
sed -i "s/_example/$TENANT/g" "plugins/$TENANT/plugin.yaml"
# ... 配置 .autoservice-info.yaml ...
```

脚本化后实际操作时间 < 5 分钟，与 worktree 差距可忽略。

### 2.6 决策

**选定方案 E：全链路 Fork 策略。**

```
L1: socialware                   ← 基础框架 repo
    │ fork
    ▼
L2: autoservice                  ← 客服 app (fork of socialware)
    │ fork
    ▼
L3: cinnox/autoservice           ← 租户 (fork of autoservice)
```

核心理由：
1. **跨语言扩展性** — L1 不限于 Python，未来可包含 Go 网关、Node.js 前端、或其他语言的 channel adapter
2. **非代码资产自然传播** — CI 模板、Makefile、CLAUDE.md、文档等通过 git merge 同步，无需手动复制
3. **统一心智模型** — L1→L2→L3 全链路使用同一种同步机制 (`git merge upstream/main`)，降低认知负担
4. **租户隔离** — 每一层都是独立 repo，GitHub 平台保证读权限隔离
5. **目录级边界** — `socialware/` (L1) 与 `autoservice/` (L2) 通过 CODEOWNERS + CI 守护，虽非包边界但在工程实践中同样有效
6. **零配置开发态** — fork 内所有代码共存，修改即生效，无需 editable install 配置

**为何放弃方案 D (Package + Fork)：** 包依赖模型限定了 L1 为 Python，无法适应跨语言需求；L1→L2 和 L2→L3 使用不同的同步机制增加了复杂度；非代码资产（CI、模板、文档）无法通过 pip 传播。

---

## 3. Architecture

### 3.1 三层模型

```
┌─────────────────────────────────────────────────────────────────┐
│  L1: socialware (独立 repo)                                      │
│  框架层 — 通道接入、插件加载、配置管理、session 框架、通用工具         │
│  目录: socialware/  channels/  templates/                        │
│  判断标准: 换一个完全不同的 app (教育/医疗/...) 还有没有用?          │
└────────────────────────────┬────────────────────────────────────┘
                             │ fork
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  L2: autoservice (fork of socialware)                            │
│  应用层 — 客服业务逻辑、CRM、客户管理、行业 skills                   │
│  继承: socialware/  channels/  templates/  (来自 L1, 不修改)      │
│  新增: autoservice/  plugins/  skills/  (L2 拥有)                │
│  判断标准: 换一个租户, 这个模块还有没有用?                           │
└──────────────┬────────────────────────┬────────────────────────┘
               │ fork                   │ fork
               ▼                        ▼
┌──────────────────────┐  ┌──────────────────────────────────────┐
│  L3: cinnox/         │  │  L3: acme/                           │
│  AutoService         │  │  AutoService                         │
│  独立 repo            │  │  独立 repo                            │
│  继承: socialware/    │  │  继承: socialware/                    │
│  继承: autoservice/   │  │  继承: autoservice/                   │
│  新增: plugins/cinnox/│  │  新增: plugins/acme/                  │
│                      │  │                                      │
│  ┌─ 子租户 (plugin) ─┐│  └──────────────────────────────────────┘
│  │ plugins/companyA/ ││
│  │ plugins/companyB/ ││
│  └───────────────────┘│
└──────────────────────┘
```

### 3.2 L1: socialware repo 结构

```
socialware/                              # L1 独立 repo (GitHub: h2oslabs/socialware)
├── socialware/                          # 框架核心 (Python, 但不限于 Python)
│   ├── __init__.py                      # 只导出框架级 API
│   ├── core.py                          # 工具函数 (generate_id, sanitize_name, ensure_dir)
│   ├── config.py                        # 配置加载机制 (load_config) — 无业务数据
│   ├── plugin_loader.py                 # 插件发现 + 加载 (Plugin, PluginTool, PluginRoute)
│   ├── mock_db.py                       # 通用 Mock 数据库
│   ├── database.py                      # 通用记录存储
│   ├── importer.py                      # 文件导入 (docx/xlsx/pdf)
│   ├── session.py                       # session 框架 — 只有机制, 无 DOMAIN_PREFIXES
│   ├── permission.py                    # 权限框架 — PermissionLevel 基类, 无具体级别
│   ├── logger.py                        # 对话日志
│   └── api_client.py                    # HTTP 客户端框架
├── channels/                            # 渠道接入层 (不在 socialware/ 包内, 支持多语言扩展)
│   ├── feishu/                          # 飞书 MCP channel
│   │   ├── channel.py
│   │   ├── channel_server.py
│   │   └── channel-instructions.md
│   └── web/                             # Web chat (FastAPI 骨架)
│       ├── app.py
│       └── static/
├── templates/                           # L2 脚手架 (fork 后使用)
│   └── app-template/
│       ├── pyproject.toml.tmpl
│       ├── Makefile.tmpl
│       └── plugins/_example/
├── .github/
│   ├── workflows/
│   │   ├── ci-reusable.yml              # L2/L3 可调用的 reusable workflow
│   │   └── boundary-check.yml           # 层间边界检测
│   └── CODEOWNERS                       # socialware/ 目录归 L1 team
├── pyproject.toml
├── CLAUDE.md
└── Makefile
```

> **跨语言扩展点:** `channels/` 独立于 `socialware/` Python 包之外。未来如果需要 Go 网关或 Node.js 前端，只需在 `channels/` 下新建目录，不影响 Python 核心。

**L1 的准入标准：** 假设要基于 socialware 做一个 "AI 教育辅导" app（完全不涉及客服），这个模块是否仍然有用？

| 收入 L1 | 留在 L2 | 理由 |
|----------|---------|------|
| `core.py` | | 纯工具函数, 零业务语义 |
| `plugin_loader.py` | | 通用插件发现, 不含 "客服" 概念 |
| `mock_db.py` | | 表结构抽象 (customers/products/subscriptions 足够通用) |
| `database.py` | | 通用记录存储 |
| `importer.py` | | 文件导入能力 |
| `logger.py` | | 对话日志 |
| `feishu/`, `web/` | | 渠道接入 (socialware 的 "social" 部分) |
| `config.py` 的 `load_config()` | `config.py` 的 `LANG_CONFIGS` | 机制是 L1, 数据是 L2 |
| `session.py` 的框架 | `session.py` 的 `DOMAIN_PREFIXES` | 同上 |
| `permission.py` 的基类 | 具体 `OperatorPermissions` | 同上 |
| `api_client.py` 的框架 | `COMMON_INTERFACES` 定义 | 同上 |
| | `customer_manager.py` | "客户冷启动"、"来电客户" 是纯客服概念 |
| | `crm.py` | contacts/conversations 是客服 CRM |
| | `rules.py` | 行为规则引擎, 当前实现客服向 |

### 3.3 L2: autoservice 应用结构

```
autoservice/                             # L2 repo (fork of socialware)
│                                        # GitHub: h2oslabs/AutoService
│
│  ── 继承自 L1 (不修改, 跟随 upstream merge) ──
├── socialware/                          # L1 框架核心 (CODEOWNERS 保护)
├── channels/                            # L1 渠道层 (CODEOWNERS 保护)
├── templates/                           # L1 脚手架
│
│  ── L2 新增 (应用层) ──
├── autoservice/                         # L2 业务包
│   ├── __init__.py
│   ├── customer_manager.py              # 客户管理
│   ├── crm.py                           # CRM
│   ├── rules.py                         # 行为规则
│   ├── domain_config.py                 # LANG_CONFIGS 数据 (从 config.py 拆出)
│   ├── domain_session.py                # DOMAIN_PREFIXES (从 session.py 拆出)
│   └── api_interfaces.py               # COMMON_INTERFACES (从 api_interfaces.py 拆出)
├── plugins/
│   └── _example/                        # 插件模板
│       ├── plugin.yaml
│       ├── tools.py
│       └── routes.py
├── skills/
│   ├── _shared/                         # 共享 skill 工具
│   ├── customer-service/                # 客服 skill
│   ├── sales-demo/                      # 销售 skill
│   ├── marketing/                       # 营销 skill
│   ├── knowledge-base/                  # 知识库 skill
│   ├── explain/                         # 流程可视化
│   └── improve/                         # 代码优化
├── commands/                            # Claude Code commands
├── agents/                              # Claude Code agents
├── hooks/                               # Claude Code hooks
├── tests/
├── docs/
│   └── fork-registry.yaml               # L3 fork 注册表
├── .github/
│   ├── workflows/                       # 继承 L1 的 CI + L2 新增的
│   └── CODEOWNERS                       # 更新: socialware/ → L1 team, autoservice/ → L2 team
├── .autoservice-info.yaml               # 应用元数据
├── .mcp.json                            # MCP 服务配置
├── pyproject.toml                       # L2 自身依赖 (不再依赖 socialware 包)
├── CLAUDE.md
└── Makefile
```

**L2 的 `pyproject.toml`:**

```toml
[project]
name = "autoservice"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # 不再需要 socialware 依赖 — socialware/ 目录已通过 fork 存在于本 repo
    # L2 自身的额外依赖
    "anthropic",
    "fastapi",
    # ...
]
```

**L2 的 `.github/CODEOWNERS`:**

```
# L1 框架层 — 修改需要 L1 maintainer review
/socialware/         @h2oslabs/framework-team
/channels/           @h2oslabs/framework-team
/templates/          @h2oslabs/framework-team

# L2 应用层 — L2 team 拥有
/autoservice/        @h2oslabs/app-team
/plugins/            @h2oslabs/app-team
/skills/             @h2oslabs/app-team
```

> **Import 路径:** L2 代码引用 L1 通过 `from socialware import ...`，引用 L2 自身通过 `from autoservice import ...`。两个 Python 包在同一 repo 内共存，通过目录名天然隔离。

### 3.4 L3: 租户实例 (统一 Fork)

每个 L3 是 L2 的独立 fork:

```
cinnox/AutoService                       # fork of h2oslabs/AutoService
│
│  ── 继承自 L1 (不修改) ──
├── socialware/                          # L1 框架
├── channels/                            # L1 渠道
│
│  ── 继承自 L2 (不修改) ──
├── autoservice/                         # L2 业务包
├── plugins/_example/                    # L2 插件模板
├── skills/customer-service/             # L2 客服 skill
│
│  ── L3 新增 (租户专属) ──
├── plugins/
│   └── cinnox/                          # 租户专属
│       ├── plugin.yaml
│       ├── tools.py
│       ├── routes.py
│       ├── mock_data/accounts.json
│       └── references/glossary.json
├── skills/
│   └── cinnox-demo/                     # 租户专属
├── .autoservice-info.yaml               # customer: cinnox
└── (通过 git merge upstream/main 保持与 L2 同步)
```

**三层目录所有权:**

| 目录 | 所有者 | L3 可修改? |
|------|--------|-----------|
| `socialware/` | L1 | 否 (CODEOWNERS) |
| `channels/` | L1 | 否 |
| `autoservice/` | L2 | 否 (改进请提 PR 到 upstream) |
| `plugins/_example/` | L2 | 否 |
| `plugins/租户名/` | L3 | 是 |
| `skills/租户名/` | L3 | 是 |

**无论 demo 还是正式交付，L3 始终是独立 fork。** 不区分阶段，管理模型统一。

---

## 4. 同步与提炼工作流

### 4.1 开发态工作区

全链路 fork 模式下，每一层都是独立 repo clone:

```
~/work/
├── socialware/                  # L1 (git clone, 仅 L1 maintainer 需要)
├── autoservice/                 # L2 (git clone of fork)
├── autoservice-cinnox/          # L3 (git clone of fork)
└── autoservice-acme/            # L3 (git clone of fork)
```

**开发态零配置:** L2 repo 内 `socialware/` 和 `autoservice/` 目录共存，修改 `socialware/` 代码后保存即可在同一 repo 内的 `autoservice/` 代码中生效，无需 editable install 或版本升级。

L3 的情况也相同 — 所有三层代码都在同一个 fork repo 内，修改即生效。

> **注意:** L2 开发者一般不直接修改 `socialware/` 目录。如果需要改动，应在独立的 L1 clone 中修改后提 PR 到 L1 upstream，然后 L2 通过 merge 获取更新。紧急情况下可在 L2 中直接修改 `socialware/`，但事后必须提 PR 回 L1。

### 4.2 L1 → L2 同步 (框架更新)

L1→L2 使用与 L2→L3 相同的 git merge 机制:

```bash
# L2 repo 配置 upstream (一次性)
cd ~/work/autoservice/
git remote add upstream git@github.com:h2oslabs/socialware.git

# 每次 L1 有更新:
git fetch upstream
git merge upstream/main
# 冲突仅可能发生在 L2 修改了 L1 拥有的文件 (socialware/, channels/)
# 如果遵守 CODEOWNERS 纪律, merge 通常是 clean 的
```

**L1 版本管理:** L1 使用 release 分支 (`release/v0.2`, `release/v0.3`) 管理版本。L2 可以选择 merge 特定 release 分支而非 main:

```bash
# L2 选择性 merge L1 的稳定版本
git fetch upstream
git merge upstream/release/v0.2   # 只拿稳定版本, 不跟 main 的开发中代码
```

### 4.3 L2 → 所有 L3 同步 (应用更新)

每个 L3 fork 通过 upstream remote 跟踪 L2:

```bash
# L3 fork 的初始配置 (一次性)
cd ~/work/autoservice-cinnox/
git remote add upstream git@github.com:h2oslabs/AutoService.git

# 每次 L2 main 有更新:
git fetch upstream
git merge upstream/main
# 冲突仅可能发生在 plugins/ 和 skills/ (租户专属目录)
```

批量同步可用脚本:

```bash
# sync-all-forks.sh
FORKS=("cinnox/AutoService" "acme/AutoService" "edu/AutoService")
for fork in "${FORKS[@]}"; do
    echo "Syncing $fork..."
    gh api "repos/$fork/merges" \
        -f base=main -f head=upstream/main \
        --method POST 2>/dev/null \
        && echo "  OK" \
        || echo "  CONFLICT — needs manual merge"
done
```

或通过 GitHub Actions 在 L2 push main 时自动触发所有 fork 的同步 PR。

### 4.4 L3 → L2 提炼 (从租户中提取通用模式)

```bash
# Step 1: 在 L2 repo 中添加 L3 的 remote (一次性)
cd ~/work/autoservice/
git remote add cinnox git@github.com:cinnox/AutoService.git

# Step 2: fetch (每次提炼前, 2-10 秒)
git fetch cinnox

# Step 3: 查看差异
git diff main...cinnox/main
git log main..cinnox/main --oneline

# Step 4a: cherry-pick 整个通用 commit
git cherry-pick <hash>

# Step 4b: 文件级提取
git checkout cinnox/main -- autoservice/some_module.py
git commit -m "refine: extract <module> from cinnox"

# Step 4c: 部分改动 → patch
git diff main...cinnox/main -- autoservice/rules.py > /tmp/rules.patch
git apply /tmp/rules.patch
```

或者 L3 的开发者直接在 GitHub 上向 L2 提 PR（标准 fork PR 流程，有 review）。

### 4.5 L2 → L1 提炼 (从应用层提取框架能力)

两种方式:

```bash
# 方式 1: L2 maintainer 在 L1 独立 clone 中修改 (推荐)
cd ~/work/socialware/
git checkout -b refine/session-framework
# 修改代码...
git commit -m "feat: add pluggable session ID generator"
git push origin refine/session-framework
# → 向 socialware repo 提 PR

# 方式 2: L2 maintainer 在 L2 fork 中向 L1 upstream 提 PR
# (与 L3→L2 提炼相同的标准 fork PR 流程)
cd ~/work/autoservice/
git checkout -b upstream/improve-session
# 修改 socialware/ 下的代码...
git push origin upstream/improve-session
# → 在 GitHub 上创建 PR: h2oslabs/AutoService → h2oslabs/socialware

# PR review checklist 必须包含:
# "这个改动是否对所有基于 socialware 的 app 都有意义?
#  如果只对客服场景有用, 应该放在 L2."
```

### 4.6 L1 → 所有 L2 广播 (框架发版)

```bash
# L1 创建 release 分支
cd ~/work/socialware/
git checkout -b release/v0.2
git tag v0.2.0
git push origin release/v0.2 v0.2.0

# 每个 L2 通过 merge 获取更新 (与 L2→L3 机制完全相同)
cd ~/work/autoservice/
git fetch upstream
git merge upstream/release/v0.2
git push origin main

# 批量通知所有 L2 (如果有多个 L2 app):
# 同 4.3 的批量 sync 脚本, 只是 upstream 指向 socialware
```

### 4.7 完整流转图

```
              L1: socialware
             ┌──────────────┐
             │    main      │◄──────── PR (框架级改进)
             │ release/v0.2 │                ▲
             └──────┬───────┘                │
                    │ fork + merge            │
                    ▼                         │
             L2: autoservice                 │
             ┌──────────────┐                │
             │    main      │────────────────┘
             │ socialware/  │  (继承, 不修改)
             │ autoservice/ │  (L2 拥有)
             │              │◄──────── PR (通用模式)
             └──┬───────┬───┘                ▲
                │       │                    │
         fork   │       │   fork             │
                ▼       ▼                    │
          L3:cinnox   L3:acme ───────────────┘
          ┌────────┐  ┌────────┐
          │ fork   │  │  fork  │
          │ (独立)  │  │ (独立)  │
          └────────┘  └────────┘

  同步方向 (↓): 全链路 git merge upstream
  提炼方向 (↑): 全链路 GitHub PR
```

---

## 5. 子租户分析 (L3 基于 L3)

### 5.1 场景

Cinnox (L3) 是一个客服平台，它自己有多个下游客户 (Company A, Company B)，每个客户需要定制化的客服 bot。这形成了 "租户的租户":

```
L2: autoservice
  └── fork → L3: cinnox/AutoService
                └── ??? → L3': cinnox-companyA
                └── ??? → L3': cinnox-companyB
```

### 5.2 三种 L3→L3' 方案

#### 方案 X: Fork of Fork (L3' fork L3)

```
L2 → fork → L3 → fork → L3'
```

| 维度 | 评价 |
|------|------|
| 同步链 | L1→L2→L3→L3' (三跳 merge) |
| L3' 向 L2 提 PR | GitHub 不支持 fork-of-fork 直接向 grandparent 提 PR |
| 隔离 | 好 (独立 repo) |
| 复杂度 | 高 — 三层 fork 维护成本陡增 |
| 适用场景 | L3' 有大量独立代码改动 (不仅仅是配置/数据差异) |

#### 方案 Y: Plugin 多租户 (推荐)

```
L3: cinnox/AutoService
├── plugins/
│   ├── cinnox-base/          ← 共享的 cinnox 逻辑 (CRM, billing)
│   ├── cinnox-companyA/      ← Company A 专属 (不同产品目录、不同计费规则)
│   └── cinnox-companyB/      ← Company B 专属
├── config/
│   ├── companyA.yaml         ← Company A 运行配置
│   └── companyB.yaml         ← Company B 运行配置
```

| 维度 | 评价 |
|------|------|
| 同步链 | 无额外链路 — L3 merge upstream/main 即可 |
| 隔离 | 代码层面无隔离 (同一 repo)，但部署层面可隔离 (不同实例加载不同 plugin) |
| 复杂度 | 最低 — 复用现有 plugin_loader.py 机制 |
| 适用场景 | L3' 之间差异主要是配置和数据 (产品目录、客户列表、品牌定制) |

插件加载器已经原生支持此模式——`plugin_loader.discover()` 会扫描 `plugins/*/plugin.yaml`，每个子租户就是一个 plugin 目录：

```yaml
# plugins/cinnox-companyA/plugin.yaml
name: cinnox-companyA
version: 1.0.0
description: Company A customer service bot
mode: mock
installer: cinnox

mcp_tools:
  - name: companyA_product_lookup
    handler: tools.product_lookup
    # ...

mock_server:
  seed_data: mock_data/companyA_products.json
  database: .autoservice/database/companyA/mock.db

references:
  - references/companyA_glossary.json
```

不同部署实例通过环境变量或启动参数指定加载哪些 plugin:

```bash
# 部署 Company A 的实例
ACTIVE_PLUGINS=cinnox-base,cinnox-companyA make run-channel

# 部署 Company B 的实例
ACTIVE_PLUGINS=cinnox-base,cinnox-companyB make run-channel
```

#### 方案 Z: Flat Fork (L3' 也 fork L2)

```
L2 → fork → L3  (cinnox)
L2 → fork → L3' (cinnox-companyA)   ← 直接 fork L2, 再 cherry-pick L3 的改动
```

| 维度 | 评价 |
|------|------|
| 同步链 | L3' 需要同时跟踪 L2 (upstream) 和 L3 (cherry-pick) |
| 复杂度 | 极高 — 两个上游来源，冲突频繁 |
| 适用场景 | 不推荐 |

### 5.3 决策树

```
L3 需要创建子租户 (L3') 时:

  L3' 与 L3 的差异是什么?
  │
  ├── 仅配置/数据 (产品目录、客户列表、品牌、mock 数据)
  │   └── → 方案 Y: Plugin 多租户
  │         在 L3 中为每个子租户添加 plugins/sub-tenant/ 目录
  │         部署时按实例加载不同 plugin
  │         不增加 repo, 不增加 git 复杂度
  │
  ├── 少量代码定制 (个别工具函数不同、某个 skill 不同)
  │   └── → 方案 Y: Plugin 多租户
  │         将差异封装在 plugin 的 tools.py / routes.py 中
  │         共享逻辑放在 cinnox-base plugin
  │
  └── 大量独立代码改动 (不同渠道、不同框架级行为)
      └── → 方案 X: Fork of Fork
            L3' fork L3, 独立演进
            接受三跳同步链的维护成本
            仅当差异大到 plugin 无法封装时使用
```

### 5.4 推荐

**默认使用方案 Y (Plugin 多租户)。** 理由：

1. **现有 plugin 系统天然支持** — `plugin_loader.discover()` 已经自动扫描 `plugins/*/plugin.yaml`，零额外开发
2. **零 git 复杂度** — 不增加 repo、不加深 fork 链、不增加 merge 跳数
3. **符合实际差异量** — L3' 之间的差异通常是产品/客户/品牌数据，不是框架级代码。当前 cinnox 的 `plugin.yaml` 展示了这种模式：MCP tools + mock data + references 的组合已经足够表达一个租户的差异
4. **部署隔离可行** — 同一套代码，不同实例加载不同 plugin，运行时隔离

只有当子租户需要修改 `autoservice/` 或 `feishu/`/`web/` 等非 plugin 代码时，才升级为 fork-of-fork (方案 X)。

---

## 6. "机制 vs 策略" 拆分原则

当前代码中最大的灰色地带是"框架提供机制, 但硬编码了业务策略"的模块。全链路 fork 模式下，拆分的结果是将代码放入不同的**目录**（`socialware/` vs `autoservice/`），而非不同的 repo。

### 6.1 config.py 拆分

```python
# socialware/config.py — 只有机制 (L1 目录, CODEOWNERS 保护)
def load_config(config_path: Path) -> dict:
    """Load configuration from a YAML file."""
    ...

def get_domain_config(domain: str, config_path: Path = None,
                      defaults: dict = None) -> dict:
    """Get configuration for a domain. Caller provides defaults."""
    ...

# autoservice/domain_config.py — 业务数据 (L2 目录)
from socialware.config import get_domain_config

LANG_CONFIGS = {
    'zh': {
        'marketing': { ... },
        'customer-service': { ... },
    },
    'en': { ... },
}

def get_cs_config(domain: str, config_path=None, language='zh') -> dict:
    """Get customer-service domain config with L2 defaults."""
    defaults = LANG_CONFIGS.get(language, {}).get(domain, {})
    return get_domain_config(domain, config_path, defaults)
```

### 6.2 session.py 拆分

```python
# socialware/session.py — 框架机制 (L1 目录)
def generate_session_id(prefix: str, base_dir: Path,
                        external_id: str = "") -> str:
    """Generate session ID: {prefix}_{YYYYMMDD}_{seq}_{external_id}"""
    ...

def init_session(prefix: str, base_dir: Path, ...) -> tuple[str, Path]:
    ...

# autoservice/domain_session.py — 业务策略 (L2 目录)
from socialware.session import init_session

DOMAIN_PREFIXES = {'customer-service': 'cs', 'marketing': 'mk'}

def init_cs_session(domain: str, config=None) -> tuple[str, Path]:
    prefix = DOMAIN_PREFIXES.get(domain, domain[:2])
    base_dir = Path(config['database_path'])
    return init_session(prefix, base_dir, ...)
```

> **Fork 模式优势:** `socialware/` 和 `autoservice/` 在同一 repo 内，`from socialware import ...` 和 `from autoservice import ...` 都是本地导入，无需 pip install 或 editable 配置。拆分的约束通过 CODEOWNERS 和 CI boundary check 执行，而非包管理器。

### 6.3 判断清单

对于每个函数/类, 问自己:

| 问题 | 是 → `socialware/` | 否 → `autoservice/` |
|------|---------|---------|
| 换个完全不同的 app, 这个函数还有用吗? | `socialware/` | `autoservice/` |
| 删掉这个函数, 框架还能加载插件和接入渠道吗? | `socialware/` | `autoservice/` |
| 这个函数的参数名/返回值含有 "customer"/"agent"/"CRM" 等客服词汇? | `autoservice/` | (看上面两条) |
| 其他非客服类 app 会需要一个类似的但参数不同的版本吗? | `socialware/` (抽象版) | `autoservice/` (具体版) |

---

## 7. Fork 操作指南

### 7.1 创建 L3 租户 (新 fork)

```bash
# 方式 1: GitHub CLI
gh repo fork h2oslabs/AutoService \
    --org cinnox \
    --fork-name autoservice \
    --clone
cd autoservice

# 方式 2: GitHub Web UI fork 后 clone
git clone git@github.com:cinnox/autoservice.git
cd autoservice

# 配置 upstream
git remote add upstream git@github.com:h2oslabs/AutoService.git

# 添加租户专属内容
mkdir -p plugins/cinnox skills/cinnox-demo
cp -r plugins/_example/* plugins/cinnox/
# 编辑 plugin.yaml, tools.py, .autoservice-info.yaml ...
git add plugins/cinnox/ skills/cinnox-demo/ .autoservice-info.yaml
git commit -m "feat: initialize cinnox tenant"
git push origin main
```

### 7.2 日常开发

```bash
# L3 开发者日常工作
cd ~/work/autoservice-cinnox/
# ... 修改 plugins/cinnox/ 或 skills/cinnox-demo/ ...
git commit -m "feat: add billing inquiry flow"
git push origin main
```

### 7.3 同步 L2 更新到 L3

```bash
cd ~/work/autoservice-cinnox/
git fetch upstream
git merge upstream/main
# 冲突仅可能发生在 plugins/ 和 skills/ (租户专属目录)
# 因为 L3 不应修改 autoservice/ 核心代码, merge 通常是 clean 的
git push origin main
```

### 7.4 L3 提炼到 L2

```bash
# 方式 1: L3 开发者在 GitHub 上向 L2 提 PR (推荐)
# 在 cinnox/autoservice fork 中:
git checkout -b upstream/improve-rules-engine
# ... 修改 autoservice/rules.py ...
git push origin upstream/improve-rules-engine
# → 在 GitHub 上创建 PR: cinnox/autoservice:upstream/improve-rules-engine → h2oslabs/AutoService:main

# 方式 2: L2 maintainer 从 L3 cherry-pick
cd ~/work/autoservice/
git remote add cinnox git@github.com:cinnox/autoservice.git  # 一次性
git fetch cinnox
git cherry-pick <hash>
```

### 7.5 创建子租户 (L3 内 plugin)

```bash
cd ~/work/autoservice-cinnox/

# 为 Company A 创建子租户 plugin
mkdir -p plugins/cinnox-companyA/mock_data plugins/cinnox-companyA/references

# 创建 plugin.yaml (基于 cinnox 的结构)
cat > plugins/cinnox-companyA/plugin.yaml << 'EOF'
name: cinnox-companyA
version: 1.0.0
description: Company A customized customer service
mode: mock
installer: cinnox

mcp_tools:
  - name: companyA_customer_lookup
    handler: tools.customer_lookup
    input_schema:
      type: object
      properties:
        identifier:
          type: string
      required: [identifier]

mock_server:
  seed_data: mock_data/accounts.json
  database: .autoservice/database/companyA/mock.db

references:
  - references/glossary.json
EOF

# 复制并定制 tools.py, mock_data, references
cp plugins/cinnox/tools.py plugins/cinnox-companyA/tools.py
# ... 按 Company A 需求修改 ...

git add plugins/cinnox-companyA/
git commit -m "feat: add Company A sub-tenant plugin"
```

---

## 8. 全 Fork 风险全景与防控

全 fork 策略将隔离做到了极致，但引入了一组分布式管理的风险。按危害等级分为三类。

### 8.0 风险总览

| # | 风险 | 类别 | 危害 | 发生概率 | 防控难度 |
|---|------|------|------|----------|----------|
| R1 | Fork 版本漂移 | 同步类 | **高** | **高** | 中 |
| R2 | L3 侵入 L2 代码 | 边界类 | **高** | **高** | 中 |
| R3 | 合并冲突累积 | 同步类 | **高** | 中 | 中 |
| R4 | L1 breaking change 连锁 | 同步类 | **高** | 低 | 低 |
| R5 | 提炼遗漏 | 流程类 | 中 | **高** | 高 |
| R6 | Fork 可见性盲区 | 管理类 | 中 | **高** | 低 |
| R7 | 孤儿 Fork | 管理类 | 中 | 中 | 低 |
| R8 | Secret/Credential 泄露 | 安全类 | **高** | 低 | 低 |
| R9 | CI/CD 配置漂移 | 管理类 | 中 | 中 | 中 |
| R10 | Fork 创建成本 | 效率类 | 低 | 每次创建 | 低 |

---

### 8.1 R1: Fork 版本漂移 (同步类, 高危高频)

**问题:** L3 fork 长期不 merge upstream，各 fork 运行的 L2 版本逐渐分裂。6 个月后某个 fork 落后 main 200+ commits，merge 变成噩梦。最终放弃 merge，fork 彻底分叉成独立项目。

**为什么全链路 fork 加剧了这个问题:** worktree 模式下，开发者在同一个 repo 工作，对 main 的更新有天然感知。fork 是独立 repo，不 fetch 就看不到 upstream 有更新。全链路 fork 下，L2 对 L1 也可能漂移（不仅是 L3 对 L2），需要同时监控两层同步状态。

**防控:**

**(1) 自动化 sync bot (必须)**

```yaml
# .github/workflows/upstream-sync.yml
# 放在 L2 repo 的模板中, 每个 L3 fork 创建时自动继承
name: Upstream Sync Check
on:
  schedule:
    - cron: '0 9 * * 1'   # 每周一 9:00 UTC
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Check upstream divergence
        run: |
          git remote add upstream https://github.com/h2oslabs/AutoService.git
          git fetch upstream main

          BEHIND=$(git rev-list --count HEAD..upstream/main)
          echo "behind_count=$BEHIND" >> $GITHUB_OUTPUT

          if [ "$BEHIND" -gt 0 ]; then
            echo "::warning::This fork is $BEHIND commits behind upstream/main"
          fi
        id: check

      - name: Auto-merge if clean
        if: steps.check.outputs.behind_count > 0
        run: |
          git config user.name "sync-bot"
          git config user.email "sync-bot@autoservice"
          git merge upstream/main --no-edit && git push || \
            echo "::error::Auto-merge failed — manual intervention needed"

      # 如果 auto-merge 失败, 创建 PR 让人工处理
      - name: Create sync PR on conflict
        if: failure()
        uses: peter-evans/create-pull-request@v6
        with:
          title: "sync: merge upstream/main (conflict needs manual resolution)"
          body: "Auto-sync with upstream failed due to merge conflicts. Please resolve manually."
          branch: auto-sync/upstream-main
```

**(2) L2 侧的 fork 健康度看板 (推荐)**

L2 maintainer 定期运行脚本检查所有已知 fork 的落后程度:

```bash
# check-fork-health.sh
FORKS=("cinnox/autoservice" "acme/autoservice" "edu/autoservice")
echo "Fork Health Report — $(date)"
echo "================================"
for fork in "${FORKS[@]}"; do
    BEHIND=$(gh api "repos/$fork/compare/main...h2oslabs:AutoService:main" \
             --jq '.behind_by' 2>/dev/null || echo "N/A")
    LAST_SYNC=$(gh api "repos/$fork/commits/main" --jq '.commit.committer.date' 2>/dev/null)
    echo "$fork: behind=$BEHIND, last_commit=$LAST_SYNC"
done
```

**(3) 版本号纪律**

在 `.autoservice-info.yaml` 中记录 L2 基线版本:

```yaml
fork:
  customer: cinnox
  upstream_version: 0.3.0       # 上次 sync 时 L2 的版本
  last_sync: 2026-04-09
```

启动时检查并打印版本警告。

---

### 8.2 R2: L3 侵入 L2 代码 (边界类, 高危高频)

**问题:** L3 开发者为了快速解决问题，直接修改 `autoservice/` 目录下的 L2 代码（例如 `autoservice/crm.py`），而非只改 `plugins/` 和 `skills/`。下次 merge upstream 时产生不必要的冲突；改动无法被其他 fork 复用。

**当前代码中的具体耦合点:**
- `feishu/channel_server.py:197` — `from autoservice.crm import upsert_contact`
- `feishu/channel_server.py:592` — `from autoservice.crm import increment_message_count, log_message`
- `web/app.py:91` — `from autoservice.plugin_loader import discover`

L3 开发者很容易以为 `autoservice/` 是"自己的代码"而直接修改。

**防控:**

**(1) CODEOWNERS 文件 (必须)**

在 L2 repo 中设置, fork 继承:

```
# .github/CODEOWNERS
# L1 框架层 — 修改需要 L1 maintainer review
/socialware/     @h2oslabs/framework-team
/channels/       @h2oslabs/framework-team

# L2 应用层 — 修改需要 L2 maintainer review
/autoservice/    @h2oslabs/app-team
/Makefile        @h2oslabs/app-team
/pyproject.toml  @h2oslabs/app-team

# L3 租户可自由修改的区域
/plugins/        # 无 owner 限制
/skills/         # 无 owner 限制
/.autoservice-info.yaml  # 无 owner 限制
```

**(2) CI 侵入检测 (推荐)**

```yaml
# .github/workflows/boundary-check.yml
name: Boundary Check
on: [pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Check for L2 core modifications
        run: |
          # 如果这是 L3 fork (检查 .autoservice-info.yaml 的 customer 字段)
          CUSTOMER=$(grep 'customer:' .autoservice-info.yaml | awk '{print $2}')
          if [ "$CUSTOMER" != "~" ] && [ -n "$CUSTOMER" ]; then
            CORE_CHANGES=$(git diff --name-only origin/main...HEAD | grep -E '^(socialware/|channels/|autoservice/)' || true)
            if [ -n "$CORE_CHANGES" ]; then
              echo "::warning::L3 fork is modifying L2 core code:"
              echo "$CORE_CHANGES"
              echo ""
              echo "If this is a framework improvement, please submit a PR to upstream instead."
              echo "If this is a tenant-specific need, consider implementing it as a plugin."
            fi
          fi
```

**(3) 目录约定文档 (必须)**

在 L2 的 CLAUDE.md / CONTRIBUTING.md 中明确:

```
## L3 Fork 修改规则

| 目录 | 可修改? | 所有者 | 说明 |
|------|---------|--------|------|
| plugins/你的租户/ | YES | L3 | 租户专属, 自由修改 |
| skills/你的租户/ | YES | L3 | 租户专属, 自由修改 |
| .autoservice-info.yaml | YES | L3 | 租户元数据 |
| socialware/ | NO | L1 | 框架核心, 改进请提 PR 到 L1 upstream |
| channels/ | NO | L1 | 渠道层, 改进请提 PR 到 L1 upstream |
| autoservice/ | NO | L2 | 应用核心, 改进请提 PR 到 L2 upstream |
| pyproject.toml | 谨慎 | L2 | 可添加依赖, 不要修改已有依赖版本 |
```

---

### 8.3 R3: 合并冲突累积 (同步类, 高危中频)

**问题:** 即使 L3 遵守边界只改 `plugins/`，L2 的某些更新仍可能与 L3 冲突:
- L2 修改了 `plugins/_example/plugin.yaml` 的格式 → L3 的 plugin.yaml 基于旧格式
- L2 重命名了 `autoservice/` 的模块 → L3 的 tools.py 中有 `from autoservice.xxx import ...`
- L2 更新了 `.gitignore` / `Makefile` / `pyproject.toml`

**防控:**

**(1) 高频小步同步 (必须)**

R1 的 sync bot 已覆盖自动化。关键纪律: **每周 merge，不要攒。** 1 周的 diff 可能 5 个文件 20 行冲突；1 个月的 diff 可能 30 个文件 200 行冲突。

**(2) L2 的 breaking change 预告 (必须)**

L2 做以下改动前，必须先在 changelog 或 GitHub Discussion 中预告:
- 重命名 `autoservice/` 下的模块或函数
- 修改 `plugin.yaml` 的 schema
- 修改 `Makefile` targets
- 升级 `pyproject.toml` 中的依赖大版本

**(3) 冲突热点隔离**

L2 的 `plugins/_example/` 是最大冲突热点 — L3 会基于它创建自己的 plugin, 但两者无 git 关系（复制而非继承）。

做法: L3 的 plugin **永远不修改** `plugins/_example/`，只在自己的 `plugins/租户名/` 目录工作。`plugins/_example/` 跟随 upstream 自动更新。

---

### 8.4 R4: L1 Breaking Change 连锁 (同步类, 高危低频)

**问题:** L1 (socialware) 做了 breaking change（例如 `plugin_loader.discover()` 的参数变了），L2 merge upstream 后修改了调用代码，推送到 main。所有 L3 fork 下次 sync 时，如果 `socialware/` 目录和 `autoservice/` 目录的改动不是原子的，运行会报错。

**全链路 fork 对此风险的影响:** 与 Package 模式不同，fork 模式下 L1 的改动通过 merge 传播，L2 无法"锁定版本"——要么 merge 最新代码，要么不 merge。这使得版本选择的粒度从"版本号"变为"commit/分支"。

**防控:**

**(1) L1 release 分支 + tag (必须)**

```
socialware repo:
  main              — 开发中, 可能有不稳定改动
  release/v0.1      — v0.1.x 稳定分支
  release/v0.2      — v0.2.x 稳定分支 (可能有 breaking change)
  tag: v0.1.0, v0.1.1, v0.2.0 ...
```

L2 选择 merge 哪个 release 分支, 而非盲目跟 main:

```bash
# L2 锁定 L1 的稳定版本
git fetch upstream
git merge upstream/release/v0.1   # 只拿 v0.1 的 bug fix, 不跟 main
```

Breaking change 时:
1. L1 在 main 中标记旧 API 为 deprecated (加 warning)
2. L1 创建新 release 分支 (`release/v0.2`) 真正移除旧 API
3. L2 在 merge 新 release 分支时, 同步更新所有调用代码, 并在 CHANGELOG 中写清楚 L3 需要改什么

**(2) L2 的 `.autoservice-info.yaml` 版本追踪**

```yaml
# .autoservice-info.yaml
fork:
  upstream: h2oslabs/socialware
  upstream_release: v0.1        # 当前跟踪的 L1 release 分支
  last_sync: 2026-04-10
```

L2 的 CI 可以检查当前 `socialware/` 目录是否对应声明的 release 版本。

---

### 8.5 R5: 提炼遗漏 (流程类, 中危高频)

**问题:** L3 开发者在自己 fork 中做了一个很好的通用改进（比如 `plugin.yaml` 支持新的 `references` 格式），但没有意识到应该提炼回 L2。多个 L3 各自发明了类似方案，出现功能分裂。

**这是全 fork 模式最隐蔽的风险** — 没有人犯错，只是缺少一个反馈环。

**防控:**

**(1) 定期 Fork Diff Review (推荐)**

L2 maintainer 每月检查活跃 fork 的差异:

```bash
# review-forks.sh — 找出各 fork 对 L1/L2 核心代码的改动
FORKS=("cinnox/autoservice" "acme/autoservice")
for fork in "${FORKS[@]}"; do
    echo "=== $fork ==="
    gh api "repos/$fork/compare/h2oslabs:AutoService:main...$fork:main" \
        --jq '.files[] | select(.filename | startswith("socialware/") or startswith("channels/") or startswith("autoservice/")) | .filename' \
        2>/dev/null
    echo ""
done
```

如果发现某个 fork 修改了 `socialware/`、`channels/` 或 `autoservice/` 下的文件，主动联系该 fork 的维护者讨论是否应该提 PR。

**(2) PR 模板引导 (必须)**

L2 repo 的 PR template 中加入引导:

```markdown
<!-- .github/PULL_REQUEST_TEMPLATE.md -->
## Checklist

- [ ] 这个改动只影响我的 plugin/skill 目录
- [ ] 这个改动修改了 L2 核心代码, 并且:
  - [ ] 其他租户也会受益于此改动
  - [ ] 已经提 PR 到 upstream (link: #___)
```

**(3) 租户改动月报**

将 `review-forks.sh` 集成到 CI, 每月生成报告发到团队 channel, 列出:
- 各 fork 落后 commit 数
- 各 fork 对 L2 核心代码的改动列表
- 疑似可提炼的通用改动

---

### 8.6 R6: Fork 可见性盲区 (管理类, 中危高频)

**问题:** L2 maintainer 不知道:
- 现在有多少个活跃 fork?
- 每个 fork 跑的是什么版本?
- 哪个 fork 最近有活动? 哪个已经废弃?
- 有没有 fork 在生产环境运行?

GitHub 的 fork 列表页信息有限，且包含大量无关的临时 fork。

**防控:**

**(1) Fork 注册表 (必须)**

在 L2 repo 中维护一个 fork 注册文件:

```yaml
# docs/fork-registry.yaml
forks:
  - name: cinnox
    repo: cinnox/autoservice
    status: production          # production | demo | archived
    contact: ops@cinnox.com
    created: 2026-04-09
    last_sync: 2026-04-09

  - name: acme
    repo: acme/autoservice
    status: demo
    contact: dev@acme.com
    created: 2026-04-15
    last_sync: 2026-04-15
```

每次创建新 fork 时同步更新此注册表（写入 `create-tenant.sh` 脚本）。

**(2) 健康度仪表盘**

基于 R1 的 `check-fork-health.sh`，可以扩展为 GitHub Actions 定期运行 + 输出 markdown 报告:

```
Fork Health Report — 2026-04-09
================================
cinnox/autoservice:    behind=0   last_activity=2026-04-08   status=OK
acme/autoservice:      behind=12  last_activity=2026-03-25   status=WARNING
edu/autoservice:       behind=47  last_activity=2026-02-01   status=STALE
```

---

### 8.7 R7: 孤儿 Fork (管理类, 中危中频)

**问题:** 某个客户 demo 结束、合同终止、或项目暂停，对应的 fork 被遗忘。潜在风险:
- fork 中可能残留客户的 mock 数据或 credential placeholder
- fork 仍然是 public 的（如果 L2 是 public repo, fork 默认也是 public）
- 占用 GitHub 资源, 混淆 fork 列表

**防控:**

**(1) 生命周期管理 (推荐)**

在 fork 注册表中加入 `expires` 字段:

```yaml
  - name: edu-demo
    repo: h2oslabs/edu-autoservice
    status: demo
    expires: 2026-07-01          # demo 3 个月后自动归档
```

CI 定期检查过期 fork, 提醒 maintainer 是否归档 (archive repo)。

**(2) 归档而非删除**

过期 fork → `gh repo archive` (只读, 不删除)。保留历史, 防止意外丢失。

---

### 8.8 R8: Secret/Credential 泄露 (安全类, 高危低频)

**问题:**
- Fork 继承了 L2 的 `.gitignore`, 但 L3 开发者可能在 `plugins/cinnox/` 下意外提交了 API key
- `.autoservice/config.local.yaml` 被 `.gitignore` 排除, 但如果 L3 添加了新的配置文件未加入 gitignore
- GitHub fork 默认 **不继承** parent repo 的 secrets, 但 L3 可能自行配置了 secrets, 如果 fork 是 public 的就有泄露风险

**防控:**

**(1) .gitignore 防线 (已有, 需加固)**

当前 `.gitignore` 已排除 `.autoservice/`, `.env`, `.feishu-credentials.json`。加固:

```gitignore
# 新增: 防止任何 credential 文件被提交
*credentials*
*secret*
*.key
*.pem
# 新增: 防止 plugin 中的敏感数据
plugins/*/config.local.*
plugins/*/.env
```

**(2) Pre-commit hook (推荐)**

```yaml
# .pre-commit-config.yaml (L2 提供, fork 继承)
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

**(3) Fork 默认 private (推荐)**

如果 L2 repo 是 private, 则所有 fork 也自动 private。如果 L2 是 public:
- 使用 `create-tenant.sh` 创建 fork 时, 加 `--private` 标志
- 或在 GitHub org 设置中限制 fork 可见性

---

### 8.9 R9: CI/CD 配置漂移 (管理类, 中危中频)

**问题:** L2 提供了标准的 GitHub Actions workflow, fork 继承了这些文件, 但:
- L3 可能修改了 workflow 来适配自己的部署环境 (不同的云平台、不同的 secrets name)
- L2 更新了 workflow, L3 merge 时产生冲突
- 不同 fork 的 CI 行为不一致, 出问题时排查困难

**防控:**

**(1) Reusable workflow (推荐)**

L2 将核心 CI 逻辑封装为 reusable workflow, L3 只调用:

```yaml
# L2 repo: .github/workflows/ci-reusable.yml
name: CI
on:
  workflow_call:
    inputs:
      tenant:
        required: true
        type: string

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: uv sync
      - run: make check
      - run: uv run pytest tests/ -v
```

```yaml
# L3 fork: .github/workflows/ci.yml (租户只需这几行)
name: CI
on: [push, pull_request]
jobs:
  ci:
    uses: h2oslabs/AutoService/.github/workflows/ci-reusable.yml@main
    with:
      tenant: cinnox
```

L2 更新 reusable workflow → 所有 L3 自动获得更新, 无需 merge。

**(2) 分离 L2 通用 workflow 和 L3 部署 workflow**

```
.github/workflows/
├── ci.yml                   ← L2 提供, 不要改 (lint, test, boundary check)
├── upstream-sync.yml        ← L2 提供, 不要改 (auto sync)
└── deploy-cinnox.yml        ← L3 自己的部署, 自由修改
```

约定: `ci.yml` 和 `upstream-sync.yml` 跟随 upstream, L3 不修改。部署 workflow L3 自建。

---

### 8.10 R10: Fork 创建成本 (效率类, 低危每次)

**问题:** 每次创建新租户需要 fork repo + 配置 remote + 配置 CI secrets + 初始化 plugin 目录, 手动操作 ~30-60 分钟, 容易遗漏步骤。

**防控:**

**自动化 `create-tenant.sh` (必须)**

```bash
#!/bin/bash
set -euo pipefail

TENANT=$1
ORG=${2:-h2oslabs}
UPSTREAM="h2oslabs/AutoService"
FORK_NAME="${TENANT}-autoservice"

echo "==> Creating fork for tenant: $TENANT"

# 1. Fork repo
gh repo fork "$UPSTREAM" --org "$ORG" --fork-name "$FORK_NAME" --clone
cd "$FORK_NAME"

# 2. Configure upstream
git remote add upstream "git@github.com:${UPSTREAM}.git"

# 3. Initialize tenant plugin
mkdir -p "plugins/$TENANT/mock_data" "plugins/$TENANT/references"
cp -r plugins/_example/* "plugins/$TENANT/"
sed -i "s/_example/$TENANT/g" "plugins/$TENANT/plugin.yaml"

# 4. Set tenant metadata
sed -i "s/customer: ~/customer: $TENANT/" .autoservice-info.yaml
sed -i "s/description: ~/description: $TENANT AI service bot/" .autoservice-info.yaml

# 5. Commit and push
git add .
git commit -m "feat: initialize $TENANT tenant"
git push origin main

# 6. Update fork registry (in L2 repo)
echo "  - name: $TENANT" >> ../autoservice/docs/fork-registry.yaml
echo "    repo: $ORG/$FORK_NAME" >> ../autoservice/docs/fork-registry.yaml
echo "    status: demo" >> ../autoservice/docs/fork-registry.yaml
echo "    created: $(date +%Y-%m-%d)" >> ../autoservice/docs/fork-registry.yaml

echo ""
echo "Done. Fork: https://github.com/$ORG/$FORK_NAME"
echo "Next steps:"
echo "  1. Configure GitHub secrets for CI/CD"
echo "  2. Edit plugins/$TENANT/plugin.yaml"
echo "  3. Add mock data and references"
```

---

### 8.11 防控体系总结

按实施优先级排序:

**P0 — 创建 fork 时立即配置 (Day 0):**

| 措施 | 覆盖风险 | 实施方式 |
|------|----------|----------|
| `create-tenant.sh` 自动化 | R10 | 脚本 |
| `.github/CODEOWNERS` | R2 | 文件 |
| `.gitignore` 加固 | R8 | 文件 |
| `.autoservice-info.yaml` 元数据 | R1, R6 | 文件 |
| 修改规则文档 | R2 | CLAUDE.md / CONTRIBUTING.md |

**P1 — L2 repo 基础设施 (Week 1):**

| 措施 | 覆盖风险 | 实施方式 |
|------|----------|----------|
| `upstream-sync.yml` 自动同步 | R1, R3 | GitHub Actions |
| `boundary-check.yml` 侵入检测 | R2 | GitHub Actions |
| PR template | R2, R5 | `.github/PULL_REQUEST_TEMPLATE.md` |
| Fork 注册表 | R6, R7 | `docs/fork-registry.yaml` |
| Reusable CI workflow | R9 | GitHub Actions |

**P2 — 运营态监控 (Month 1+):**

| 措施 | 覆盖风险 | 实施方式 |
|------|----------|----------|
| Fork 健康度看板 | R1, R6, R7 | 定期脚本 + 报告 |
| Fork diff review (月度) | R5 | 人工 + 脚本辅助 |
| 孤儿 fork 归档 | R7 | 注册表 expires + 检查 |
| Pre-commit gitleaks | R8 | pre-commit hook |
| L1 语义化版本 + deprecation | R4 | 版本管理纪律 |

---

## 9. Migration Path

全链路 fork 模式的迁移比 Package 模式更简单——不需要 pip 发布、editable install 配置、或 import shim 兼容层。

### Phase 1: 创建 L1 repo (socialware) — 目录拆分

1. 创建 `socialware` 仓库
2. 从当前 `autoservice/` 中提取 L1 模块，移入 `socialware/` 目录:
   - `core.py`, `plugin_loader.py`, `mock_db.py`, `database.py`, `importer.py`
   - `session.py` (移除 `DOMAIN_PREFIXES`), `config.py` (移除 `LANG_CONFIGS`)
   - `permission.py` (保留基类), `logger.py`, `api_client.py`
3. 将 `feishu/`, `web/` 移入 `channels/` 目录
4. 创建 `.github/CODEOWNERS`、CI workflow 模板
5. 建立 `pyproject.toml` (作为可选的 Python 包, 但主要通过 fork 分发)
6. 验证: `from socialware import core, plugin_loader` 可用

### Phase 2: 将当前 repo 转为 L2 (fork of socialware)

1. 在 GitHub 上将当前 repo 设为 socialware 的 fork (或重新 fork)
2. 仓库内同时存在 `socialware/` (继承自 L1) 和 `autoservice/` (L2 业务)
3. `autoservice/` 只保留 L2 模块: `customer_manager.py`, `crm.py`, `rules.py`, `domain_config.py`, `domain_session.py`, `api_interfaces.py`
4. 更新 import 路径: `from autoservice.core import ...` → `from socialware.core import ...`
5. 配置 CODEOWNERS: `socialware/` → L1 team, `autoservice/` → L2 team
6. 验证: `make run-channel` 和 `make run-web` 正常启动

> **无需 shim 层:** Package 模式下需要在 `autoservice/__init__.py` 中保留 shim re-export 以兼容旧 import 路径。Fork 模式下，由于 `socialware/` 目录直接存在于 repo 中，可以直接修改所有 import 路径，无需兼容期。

### Phase 3: 将现有租户转为 L3 fork

1. 为 cinnox 创建 L2 的独立 fork repo
2. 租户的 `plugins/cinnox/` 和 `skills/cinnox-demo/` 保留在 fork 中
3. L2 main 分支只保留 `plugins/_example/`
4. 配置 fork 的 upstream remote
5. 更新 L3 的 import 路径 (如 `plugins/cinnox/tools.py` 中的 `from autoservice.mock_db` → `from socialware.mock_db`)
6. 验证: fork 中 `git merge upstream/main` 无冲突

### Phase 4: 验证完整工作流

1. 在 L3 (cinnox fork) 中做一个改进
2. 通过 PR 提炼到 L2
3. 在 L2 中 merge 后, 另一个 L3 fork sync 验证
4. 模拟 L2 → L1 提炼: 在 L1 独立 clone 中修改 `socialware/`, 提 PR, merge 后 L2 fetch + merge
5. 模拟 L3 内创建子租户 plugin

### 运行时数据迁移

**零影响。** `.autoservice/` 目录使用相对路径，被 `.gitignore` 排除，不受 repo 结构变化影响。每个 fork 的本地 `.autoservice/` 目录独立存在。
