# 三层架构实施记录

**Date:** 2026-04-10
**Branch:** `worktree-feat+three-layer-architecture` (基于 `feat/evaluate-skill`)
**Plan:** [2026-04-09-three-layer-architecture.md](2026-04-09-three-layer-architecture.md) (方案 E: 全链路 Fork)
**Status:** Complete

---

## 实施目标

将当前扁平的 `autoservice/` 包按三层架构拆分为：

| 层 | 目录 | 职责 |
|----|------|------|
| L1 | `socialware/` | 基础框架 — 通道接入、插件加载、配置机制、session 框架、通用工具 |
| L2 | `autoservice/` | 客服应用 — CRM、客户管理、行为规则、业务配置数据 |
| L1 | `channels/` | 渠道层 — feishu MCP、web chat（从顶层 `feishu/` `web/` 迁入） |

---

## 模块分类 (代码分析结果)

### L1 → `socialware/` (框架层, 通用)

| 模块 | 说明 | 依赖 |
|------|------|------|
| `core.py` | generate_id, sanitize_name, ensure_dir | 无 |
| `config.py` | load_config 机制 + register_domain_defaults 注册机制 | 无 |
| `plugin_loader.py` | 插件发现 + 加载 | mock_db |
| `mock_db.py` | 通用 SQLite Mock 数据库 | 无 |
| `database.py` | 文件系统记录存储 | core, config |
| `importer.py` | 文件导入 (docx/xlsx/pdf) | core, config |
| `session.py` | session 框架机制 (prefix 参数化) | core, config |
| `logger.py` | 对话日志 | 无 |
| `api_client.py` | HTTP 客户端框架 | 无 |
| `api_interfaces.py` | API 接口抽象框架 (APIResponse, APIInterface, APIQueryEngine) | 无 |
| `claude.py` | Claude Agent SDK wrapper | 无 |
| `permission.py` | PermissionLevel + PermissionCheck + OperatorPermissions 基类 | 无 |

### L2 → `autoservice/` (业务层, 客服专用)

| 模块 | 说明 | 类型 |
|------|------|------|
| `domain_config.py` | LANG_CONFIGS 业务数据，注册到 L1 config | 新增 (拆分) |
| `domain_session.py` | DOMAIN_PREFIXES，包装 L1 session | 新增 (拆分) |
| `domain_permission.py` | 客服/营销权限默认值 | 新增 (拆分) |
| `api_interfaces.py` | COMMON_INTERFACES 业务接口定义 | 重写 (拆分) |
| `customer_manager.py` | 客户管理 (冷启动、来电客户) | 保留 |
| `crm.py` | CRM (联系人、对话历史) | 保留 |
| `rules.py` | 行为规则引擎 | 保留 |
| `core.py`, `config.py`, `database.py`, ... | 后向兼容 shim (re-export from socialware) | Shim |

### L1 → `channels/` (渠道层)

| 模块 | 来源 |
|------|------|
| `channels/feishu/` | git mv from `feishu/` |
| `channels/web/` | git mv from `web/` |

---

## 实施阶段

### Phase 1: 创建 socialware/ 目录，迁移 L1 模块
- **状态:** Complete
- **操作:** 创建 `socialware/` Python 包，包含 12 个框架模块
- **文件:** `socialware/__init__.py`, `core.py`, `config.py`, `plugin_loader.py`, `mock_db.py`, `database.py`, `importer.py`, `session.py`, `permission.py`, `logger.py`, `api_client.py`, `api_interfaces.py`, `claude.py`
- **关键设计:** `socialware/config.py` 引入 `register_domain_defaults()` 注册机制，允许 L2 在 import 时注入业务默认值

### Phase 2: 拆分"机制 vs 策略"模块
- **状态:** Complete
- **操作:** 将 config/session/permission/api_interfaces 按"机制 vs 策略"拆分
- **新增 L2 文件:**
  - `autoservice/domain_config.py` — LANG_CONFIGS + 自动注册到 L1
  - `autoservice/domain_session.py` — DOMAIN_PREFIXES + 包装 L1 session
  - `autoservice/domain_permission.py` — 客服/营销权限默认值 + check_permission
  - `autoservice/api_interfaces.py` — COMMON_INTERFACES + get_interface

### Phase 3: 移动渠道层 feishu/web → channels/
- **状态:** Complete
- **操作:** `git mv feishu channels/feishu && git mv web channels/web`
- **影响:** Makefile run-channel/run-web/run-server 路径更新

### Phase 4: 更新所有 import 路径 + 后向兼容 shim
- **状态:** Complete
- **策略:** 将 `autoservice/` 中的 L1 文件改为 thin re-export shims
- **效果:** 所有现有 `from autoservice.X import Y` 代码无需修改即可工作
- **Shim 文件:** core.py, config.py, database.py, importer.py, session.py, permission.py, mock_db.py, plugin_loader.py, logger.py, api_client.py, claude.py
- **直接更新:** `autoservice/customer_manager.py` 改为 `from socialware.core/config import ...`

### Phase 5: 添加 CODEOWNERS + CI boundary check
- **状态:** Complete
- **新增文件:**
  - `.github/CODEOWNERS` — L1 目录归 framework-team, L2 归 app-team
  - `.github/workflows/boundary-check.yml` — PR 跨层修改检测
  - `.github/workflows/upstream-sync.yml` — Fork 版本漂移监控

### Phase 6: 创建 templates/ 脚手架
- **状态:** Complete
- **新增文件:**
  - `templates/app-template/pyproject.toml.tmpl`
  - `templates/app-template/Makefile.tmpl`
  - `templates/app-template/autoservice-info.yaml.tmpl`
  - `templates/create-tenant.sh` — 一键创建 L3 fork 脚本

### Phase 7: 验证
- **状态:** Complete
- **验证结果:**
  - L1 (socialware) imports: OK
  - L2 (autoservice domain) imports: OK
  - Backward-compatible shim imports: OK
  - L1 __init__ aggregation: OK
  - L2 __init__ aggregation: OK
  - Config registration (L2 -> L1): OK
  - Domain prefixes: OK

---

## 变更日志

| 时间 | Phase | 操作 | 结果 |
|------|-------|------|------|
| 2026-04-10 14:15 | 准备 | 创建 worktree, 分析模块边界 | 完成 16 模块分类 |
| 2026-04-10 14:20 | Phase 1 | 创建 socialware/ (12 模块) | 完成 |
| 2026-04-10 14:25 | Phase 2 | 机制-策略拆分 (4 模块) | 完成, 新增 4 个 domain_* 文件 |
| 2026-04-10 14:28 | Phase 3 | git mv feishu/web → channels/ | 完成 |
| 2026-04-10 14:30 | Phase 4 | 11 个 L2 shim + customer_manager 更新 | 完成, 全后向兼容 |
| 2026-04-10 14:32 | Phase 5 | CODEOWNERS + 2 CI workflows | 完成 |
| 2026-04-10 14:34 | Phase 6 | templates/ + create-tenant.sh | 完成 |
| 2026-04-10 14:36 | Phase 7 | Python import 验证 (7 项) | 全部通过 |

---

## 最终目录结构

```
.
├── socialware/                    # L1: 基础框架 (12 模块)
│   ├── __init__.py
│   ├── core.py
│   ├── config.py                  # register_domain_defaults() 注册机制
│   ├── plugin_loader.py
│   ├── mock_db.py
│   ├── database.py
│   ├── importer.py
│   ├── session.py                 # prefix 参数化, 无 DOMAIN_PREFIXES
│   ├── permission.py              # 基类, 无业务默认值
│   ├── api_interfaces.py          # 框架类, 无 COMMON_INTERFACES
│   ├── api_client.py
│   ├── logger.py
│   └── claude.py
├── channels/                      # L1: 渠道层
│   ├── feishu/                    # 飞书 MCP
│   └── web/                       # Web chat (FastAPI)
├── autoservice/                   # L2: 客服应用层
│   ├── __init__.py                # 聚合 re-export
│   ├── domain_config.py           # LANG_CONFIGS (NEW)
│   ├── domain_session.py          # DOMAIN_PREFIXES (NEW)
│   ├── domain_permission.py       # 权限默认值 (NEW)
│   ├── api_interfaces.py          # COMMON_INTERFACES (重写)
│   ├── customer_manager.py        # 客户管理
│   ├── crm.py                     # CRM
│   ├── rules.py                   # 行为规则
│   ├── core.py                    # shim → socialware
│   ├── config.py                  # shim → socialware + domain_config
│   ├── database.py                # shim → socialware
│   ├── importer.py                # shim → socialware
│   ├── session.py                 # shim → socialware + domain_session
│   ├── permission.py              # shim → socialware + domain_permission
│   ├── mock_db.py                 # shim → socialware
│   ├── plugin_loader.py           # shim → socialware
│   ├── logger.py                  # shim → socialware
│   ├── api_client.py              # shim → socialware
│   └── claude.py                  # shim → socialware
├── plugins/                       # L3: 租户插件
├── skills/                        # L2: Claude Code skills
├── templates/                     # L2: Fork 脚手架
│   ├── app-template/
│   └── create-tenant.sh
├── .github/
│   ├── CODEOWNERS
│   └── workflows/
│       ├── boundary-check.yml
│       └── upstream-sync.yml
├── CLAUDE.md                      # 更新为三层架构说明
└── Makefile                       # 更新路径 (channels/)
```

## 设计决策记录

### D1: 后向兼容 Shim 策略
**决策:** 保留 `autoservice/*.py` 作为 thin re-export shim
**理由:** 30+ 个文件 (skills, plugins, channels) 通过 `from autoservice.X import Y` 引用 L1 模块。全量改写 import 路径风险大且收益低。Shim 确保零中断迁移。
**后续:** 新代码应直接引用 `socialware.*`。Shim 可在后续版本中渐进移除。

### D2: Config 注册机制
**决策:** `socialware/config.py` 提供 `register_domain_defaults()`, L2 的 `domain_config.py` 在 import 时自动注册
**理由:** 避免 L1 硬编码业务数据。L2 import 即注册，对调用方透明。
**权衡:** 依赖 Python import side-effect，但 `autoservice/__init__.py` 显式 import 确保顺序可控。

### D3: Session Prefix 参数化
**决策:** `socialware/session.py` 的 `init_session()/generate_session_id()` 接受 `prefix` 参数
**理由:** 原 `DOMAIN_PREFIXES` 字典是业务数据。L1 不应知道 'cs'/'mk' 的含义。
**权衡:** L2 的 `domain_session.py` 提供带 DOMAIN_PREFIXES 查表的便捷包装。
