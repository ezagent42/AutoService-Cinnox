---
name: "project-discussion-autoservice"
description: "AutoService 项目知识问答 skill。提供有实证支撑的项目知识服务——每个回答都附带测试输出或 file:line 引用。使用此 skill 当你需要了解 AutoService 的代码结构、模块关系、测试状态，验证某个模块是否正常工作，处理 Skill 5 的反馈分流结果，或查询项目测试 pipeline 格式。即使只是简单的项目问题也应该触发此 skill。"
---

# AutoService 项目知识库

> 由 Skill 0 (project-builder) 于 2026-04-10 自动生成。
> 这是一个**行为引擎**——指导如何查询和回答，数据存储在 `.artifacts/` 中。

## 项目概览

- **项目根目录**：d:\Work\h2os.cloud\AutoService-new
- **语言/框架**：Python 3.11+, FastAPI, Claude Agent SDK, MCP
- **测试框架**：pytest 9.0.3 + pytest-asyncio (asyncio_mode=auto)
- **模块数**：5 (autoservice, feishu, web, plugins, tests)
- **Artifact 空间**：.artifacts/
- **Skill 6 可用**：是 (.claude/skills/skill-6-artifact-registry/)

## 问答流程

被问到项目相关问题时，按以下步骤回答。目标是**每个回答都有实证**，不编造。

### Step 0: 检测更新（自动刷新）

每次回答前，检查是否有新的代码变更需要刷新索引：

1. 查询 `.artifacts/` 中的 `code-diff` 和 `e2e-report`，找出比 2026-04-10 更新的条目
2. 如果有新的 code-diff：重新读取受影响模块的源文件 + 重新跑 test-runner
3. 如果有新的 e2e-report：更新覆盖认知
4. 文件路径失效时，运行 `bash scripts/refresh-index.sh --module <name>` 重建索引

### Step 1: 解析问题 → 定位模块

查阅下方"模块索引"，找到问题涉及的模块。如果不确定，查"用户流程→模块映射"表。

### Step 2: 读取代码

根据索引中的文件路径，用 Read 工具读取**当前**代码。引用具体的 file:line。

### Step 3: 跑测试验证

运行对应的 test-runner 脚本，捕获**当前**输出作为证据：

```bash
bash scripts/test-{module_name}.sh
```

### Step 4: 查询已有知识

查询 `.artifacts/` 中的相关 artifact：

```bash
# 查询所有 artifact
python -c "import json; data=json.load(open('.artifacts/registry.json')); [print(f'{a[\"id\"]}: {a[\"name\"]} [{a[\"status\"]}]') for a in data['artifacts']]"

# 按类型查询
python -c "import json; data=json.load(open('.artifacts/registry.json')); [print(f'{a[\"id\"]}: {a[\"name\"]}') for a in data['artifacts'] if a['type']=='eval-doc']"
```

### Step 5: 组织回答

1. 直接回答问题
2. 附上证据：file:line 引用 + 测试输出
3. 如果在 `.artifacts/` 中找到相关的被驳回 eval-doc，引用它作为已知边界
4. 无法确认的断言标注 `[unverified]`

### Step 6: 分流判断（自然延伸）

如果讨论涉及 `.artifacts/` 中的 eval-doc 或 issue：

**结论是 bug**：Issue 保持 open → 进入 Phase 3（Skill 2 生成 test-plan）

**结论不是 bug**：
```bash
bash scripts/close-issue.sh --issue-url <url> --reason "<结论说明>"
```
同时在 eval-doc frontmatter 追加 `rejection_reason` 和 `rejected_at`。

---

## 模块索引

| 模块 | 路径 | 职责 | 测试命令 | 测试结果 | 用户流程 |
|------|------|------|---------|---------|---------|
| autoservice | autoservice/ | 核心库：配置、数据库、会话、权限、插件加载、CRM、API 客户端 | bash scripts/test-all.sh | 14/14 passed, 4 skipped | 插件加载, 记录CRUD, 客户冷启动, 会话管理, 权限检查, CRM追踪 |
| feishu | feishu/ | Feishu IM 通道：MCP stdio bridge + WebSocket 消息路由 | bash scripts/test-channel-server.sh | 6/6 passed | Feishu消息收发, Channel注册路由 |
| web | web/ | Web 聊天通道：FastAPI + access-code 认证 + WebSocket relay | bash scripts/test-web-relay.sh | 2/2 passed | Web对话, 登录认证, explain可视化 |
| plugins | plugins/ | 客户插件：声明式 MCP 工具 + HTTP 路由 | (无专属测试) | - | 插件发现, 工具注册, Mock数据服务 |
| tests | tests/ | 单元 + E2E 测试 | bash scripts/test-all.sh | 14/14 passed, 4 skipped | - |

## 详细模块描述

详见 `references/module-details.md`（从 `.artifacts/bootstrap/module-reports/*.json` 汇总生成）。

**autoservice** — 核心共享库，16 个 Python 文件。提供配置管理 (config.py:118)、文件数据库 CRUD (database.py:30)、客户管理 (customer_manager.py:19)、插件加载 (plugin_loader.py:229)、权限系统 (permission.py:279)、CRM (crm.py:67)、Mock 数据库 (mock_db.py:146)、API 客户端 (api_client.py:16)、会话管理 (session.py:122)。

**feishu** — Feishu IM 通道，3 个 Python 文件。ChannelClient (channel.py) 通过 WebSocket 连接 ChannelServer，ChannelServer (channel_server.py:20) 负责多通道消息路由（支持通配符注册和冲突检测）。

**web** — Web 聊天通道，6 个 Python 文件。FastAPI 应用 (app.py:30) 提供聊天 API + explain 路由 + 插件路由挂载；access-code 认证 (auth.py:15)；WebChannelBridge (websocket.py:13) 通过 WebSocket 连接 ChannelServer 进行消息中继。

**plugins** — 声明式插件系统。每个插件 (`plugins/<name>/`) 包含 plugin.yaml、routes.py、tools.py。当前有 `_example` 和 `cinnox` 两个插件。插件由 `autoservice/plugin_loader.py:229` 的 `discover()` 自动发现加载。

## 用户流程 → 模块映射

| 用户流程 | 操作步骤 | 涉及模块 | 入口 file:line | E2E 覆盖 | test-runner |
|---------|---------|---------|---------------|---------|------------|
| Feishu 消息收发 | 用户在 Feishu 群发消息 → ChannelServer 路由到 ChannelClient | feishu, autoservice | feishu/channel_server.py:20 | ✅ | test-channel-server.sh |
| Web 聊天对话 | 用户通过 Web 发消息 → WebChannelBridge 中继到 ChannelServer | web, feishu | web/app.py:30 | ✅ | test-web-relay.sh |
| 插件加载和注册 | discover() 扫描 plugins/ → 加载 plugin.yaml → 注册 MCP 工具和 HTTP 路由 | autoservice, plugins | autoservice/plugin_loader.py:229 | ❌ | - |
| 客户记录 CRUD | 通过 database.py 创建/查询/更新/删除客户记录 | autoservice | autoservice/database.py:30 | ❌ | - |
| 权限检查 | 操作请求 → check_permission() → 按优先级匹配规则 → 返回审批结果 | autoservice | autoservice/permission.py:279 | ❌ | - |
| CRM 联系人追踪 | Feishu 消息 → upsert_contact() → increment_message_count() → log_message() | autoservice | autoservice/crm.py:67 | ❌ | - |
| 会话生命周期 | init_session() → 对话 → save_session() | autoservice | autoservice/session.py:122 | ❌ | - |
| Explain 可视化 | /explain 路由 → 生成流程图 HTML | web | web/app.py (explain route) | ✅ partial | test-explain.sh |

## 测试 Pipeline 信息

供 Skill 3 (test-code-writer) 查询，了解如何在此项目中追加 E2E 测试用例。

- **测试框架**：pytest 9.0.3 + pytest-asyncio
- **E2E 测试目录**：tests/e2e/
- **E2E conftest 位置**：无独立 conftest.py（使用 pyproject.toml asyncio_mode=auto）
- **已有 fixture 列表**：无共享 fixture（每个测试自包含 mock server setup/teardown）
- **fixture 模式**：测试自行创建 mock WebSocket server，注入本地端口
- **测试命名规范**：test_{module}_{behavior}.py，函数 test_{behavior}()
- **证据采集工具**：stdout/stderr 捕获，pytest -v 输出
- **证据采集方式**：运行 test-runner 脚本，捕获输出作为证据
- **E2E 标记/marker**：无显式 marker（E2E 测试在 tests/e2e/ 目录下）
- **运行 E2E 的命令**：`uv run pytest tests/e2e/ -v`
- **运行全部测试**：`uv run pytest tests/ -v`

## Test Runners

| 脚本 | 模块 | 命令 | 基线结果 |
|------|------|------|---------|
| scripts/test-channel-client.sh | feishu/channel.py | uv run pytest tests/test_channel_client.py -v | 1/1 passed |
| scripts/test-channel-server.sh | feishu/channel_server.py | uv run pytest tests/test_channel_server.py -v | 6/6 passed |
| scripts/test-web-relay.sh | web/websocket.py | uv run pytest tests/test_web_relay.py -v | 2/2 passed |
| scripts/test-explain.sh | web/app.py (explain) | uv run pytest tests/test_explain_command.py -v | 5/5 passed, 4 skipped |
| scripts/test-e2e.sh | (E2E) | uv run pytest tests/e2e/test_feishu_mock.py -v | E2E integration |
| scripts/test-all.sh | (全局) | uv run pytest tests/ -v | 14/14 passed, 4 skipped |

## Artifact 交互

Skill 6 可用，路径：`.claude/skills/skill-6-artifact-registry/`

查询 artifact：
```bash
# 注意：skill-6 脚本使用 python3，在 Windows 上需改用 python
# 推荐直接使用 Python 读取 registry
python -c "
import json
with open('.artifacts/registry.json') as f:
    data = json.load(f)
for a in data['artifacts']:
    if a.get('status') == 'archived':
        print(f'{a[\"id\"]}: {a[\"name\"]} - {a.get(\"rejection_reason\", \"\")}')
"
```

注册新 artifact：
```bash
python -c "
import json
from datetime import datetime
with open('.artifacts/registry.json') as f:
    data = json.load(f)
data['artifacts'].append({
    'id': '{type}-{seq}',
    'name': '{name}',
    'type': '{type}',
    'status': 'draft',
    'producer': 'skill-1',
    'path': '.artifacts/{type}s/{filename}',
    'created_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'updated_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'related_ids': []
})
with open('.artifacts/registry.json', 'w') as f:
    json.dump(data, f, indent=2)
"
```

更新状态：
```bash
python -c "
import json
from datetime import datetime
with open('.artifacts/registry.json') as f:
    data = json.load(f)
for a in data['artifacts']:
    if a['id'] == '{artifact_id}':
        a['status'] = '{new_status}'
        a['updated_at'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
with open('.artifacts/registry.json', 'w') as f:
    json.dump(data, f, indent=2)
"
```

## 自我演进

### 动态层：自动刷新（Step 0）

- **新 code-diff** → 重新读取受影响模块 + 重新跑 test-runner
- **新 e2e-report** → 更新覆盖认知
- **文件路径失效** → `bash scripts/refresh-index.sh --module <name>`

### 知识层：artifact 积累

- 驳回结论 → eval-doc archived + rejection_reason
- Bug 修复历史 → eval-doc → test-plan → e2e-report 链条
- 覆盖变化 → 新 e2e-report 更新 coverage-matrix

### 何时需要重新 bootstrap

- 大规模重构（多模块重命名/合并/拆分）
- 新增完全独立的模块
- 测试框架更换

## 自验证记录

| test-runner | 基线结果 | 验证结果 | 匹配 |
|-------------|---------|---------|------|
| test-channel-client.sh | 1/1 passed | 1/1 passed | ✅ |
| test-channel-server.sh | 6/6 passed | 6/6 passed | ✅ |
| test-web-relay.sh | 2/2 passed | 2/2 passed | ✅ |
| test-explain.sh | 5/5 passed, 4 skipped | 5/5 passed, 4 skipped | ✅ |
| test-all.sh | 14/14 passed, 4 skipped | 14/14 passed, 4 skipped | ✅ |

## 环境依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| Python 3.11+ | 必需 | 运行时和测试 |
| uv | 必需 | 包管理和测试执行 |
| pytest + pytest-asyncio | 必需 | 测试框架 |
| websockets | 必需 | 测试中的 mock WebSocket server |
| git | 必需 | 版本控制 |
| gh CLI | 可选 | 关闭 GitHub issue |

**Windows 注意**：shell 脚本中使用 `python` 而非 `python3`（Windows 上 `python3` 指向 Microsoft Store）。
