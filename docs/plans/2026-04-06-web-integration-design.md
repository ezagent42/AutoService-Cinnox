# Web Integration — channel-server 统一架构设计

**Date:** 2026-04-06
**Status:** Draft
**Authors:** Allen Woods + Claude
**Depends on:** [channel-server-design.md](2026-04-06-channel-server-design.md)

## 1. Overview

将 Web 端从独立 AI 后端（SDK/API 双模式）迁移为 channel-server.py 的纯前端。迁移后 Web 和飞书共享相同的 channel.py → Claude Code 路径，业务逻辑统一由 skills 和 `.autoservice/` 运行数据驱动。

### Goals

1. **Web/飞书一致** — 两端都是前端，通过 channel-server 路由到 channel.py
2. **channel-server 为总控** — 系统状态、路由表、连接管理的唯一入口
3. **业务逻辑下沉** — channel-instructions.md 只做薄路由，具体行为由 skills 和 `.autoservice/` 数据驱动
4. **模式体系统一** — 区分 runtime_mode（运行模式）和 business_mode（业务模式）

### Non-Goals

- 不保留 Web 端的 SDK/API 双后端
- 不在 channel-instructions.md 中硬编码业务细节
- 不做 Web 端独立的 model auto-switching

## 2. Mode Taxonomy

当前代码中 "mode" 混用在两个抽象层级，需要正式区分。

### Layer 1: runtime_mode — 运行模式

控制工具权限和系统访问级别。作用域为 per-instance（Claude Code 实例级）。

| 值 | 含义 | 典型用户 |
|----|------|---------|
| `production` | 生产部署，面向真实客户 | 自动实例 |
| `improve` | 开发调试，全权限 | 开发者 |

对应当前代码：飞书端的 `/improve` 和 `/service` 命令。重命名 `service` → `production` 以消除歧义。

### Layer 2: business_mode — 业务模式

控制 persona、对话流程和升级策略。作用域为 per-chat（对话级）。

| 值 | 含义 | 典型场景 |
|----|------|---------|
| `sales` | 营销获客、产品介绍、lead 收集 | 新客户咨询 |
| `support` | 售后服务、工单、账户问题 | 现有客户投诉 |

对应当前代码：Web 端 `auth_data.mode` 的 `"sales"/"service"`。重命名 Web 的 `"service"` → `"support"`。

### 两层关系

```
runtime_mode = improve
  └── 开发者可以用任何 business_mode 测试，也可以管理规则/KB/CRM

runtime_mode = production
  ├── business_mode = sales  → 加载 /sales-demo 或 /cinnox-demo skill
  └── business_mode = support → 加载 /customer-service skill
```

channel-instructions.md 只负责根据 runtime_mode 路由到正确的 skill，不包含 skill 的具体内容。

## 3. Architecture After Migration

```
浏览器 ↔ web/app.py ──┐
                       ├─ ws://localhost:9999 ─→ channel-server.py ─┐
飞书 IM ───────────────┘       (系统总控)                            │
                                                                    ├─ channel.py#0 ↔ Claude Code (improve, *)
管理群 ↔ channel-server.py 直接处理                                  ├─ channel.py#1 ↔ Claude Code (production, oc_aaa)
                                                                    └─ channel.py#2 ↔ Claude Code (production, web_xxx)
```

## 4. Component Responsibilities

### 4.1 channel-server.py — 系统总控

**从 channel.py 迁入：**

| 功能 | 来源 | 复杂度 |
|------|------|--------|
| 飞书 WebSocket 连接 | `setup_feishu()` | 中 |
| Bot 自身消息过滤 | `_bot_open_id` 检测 | 低 |
| 消息去重 | `_seen`, `_recent_sent` | 低 |
| ACK reaction | `send_reaction()` | 低 |
| 用户名解析 | `_resolve_user()` + CRM upsert | 中 |
| CRM 入站记录 | `increment_message_count/log_message` | 低 |
| 富文本解析 (text/post) | `on_message` 内 | 低 |
| 启动通知广播 | `send_startup()` | 低 |
| runtime_mode 切换 | `/improve` `/production` 命令拦截 | 低 |

**新增：**

| 功能 | 说明 |
|------|------|
| 本地 WebSocket server (:9999) | 接受 channel.py / web/app.py 注册 |
| 路由表管理 | chat_id → WebSocket 连接映射 |
| Reply 反向路由 | `oc_` → 飞书 API, `web_` → WebSocket 转发 |
| 管理群通知/命令 | 实例上下线、`/status`、`@chat_id` 注入 |
| UX 事件转发 | channel.py 的 `ux_event` → web/app.py |
| runtime_mode 注册表 | 记录每个实例的 runtime_mode |

**不做：**
- 不运行 Claude（无 SDK/API/MCP 依赖）
- 不理解 business_mode 细节（透传给 channel.py）
- 不做 session persistence（前端自理）
- 不做业务逻辑（escalation、gate、customer type 等）

### 4.2 channel.py — MCP 业务桥接

**保留：**
- MCP stdio server + Claude Code 桥接
- Plugin tools 注册
- channel-instructions.md hot-reload

**改造：**

| 功能 | 变更 |
|------|------|
| 连接方式 | 去掉飞书 WS → 连 `ws://localhost:9999` + 自动重连 |
| `reply` tool | 发给 channel-server.py（附 chat_id），不再直连飞书 |
| `react` tool | 发给 channel-server.py（附 message_id） |
| 注册消息 | 包含 `chat_ids`, `runtime_mode`, `instance_id` |
| UX 事件 | 新增 `ux_event` 消息类型，供 web 前端显示中间状态 |

**删除：**
- 飞书 WebSocket 相关代码
- `_resolve_user()`, `send_reaction()`, CRM 记录（迁入 channel-server）
- `_seen`, `_recent_sent` 去重逻辑（迁入 channel-server）
- `/improve`, `/service` 命令处理（迁入 channel-server）
- `send_startup()` 广播（迁入 channel-server）

### 4.3 web/app.py — 纯 Web 前端

**保留：**

| 功能 | 说明 |
|------|------|
| 静态文件服务 | login.html, chat.html, CSS/JS |
| Access code 认证 | login → token → WebSocket auth |
| Plugin HTTP routes | `/api/kb_search`, `/api/save_lead` 等 |
| Session persistence | 存/读对话历史 JSON（纯前端状态） |
| Session resume | 加载旧对话发给浏览器 |
| Idle timeout | access code 超时释放 |

**改造：**

| 功能 | 变更 |
|------|------|
| WebSocket 端点 `/ws/chat` | 从 SDK/API 后端改为 channel-server relay |
| UX 事件显示 | 接收 channel-server 转发的 `ux_event` → 推送给浏览器 |
| business_mode | 建连时通过注册消息告知 channel-server |

**删除：**

| 模块/功能 | 理由 |
|-----------|------|
| `web/claude_backend.py` | AI 后端整体删除 |
| `web/system_prompts.py` | Prompt 由 channel-instructions.md + skills 管理 |
| `web/websocket.py` 中 SDK/API 逻辑 | 替换为 thin relay |
| `claude_agent_sdk` / `anthropic` 依赖 | web 不再直接调用 AI |
| Model auto-switching | 每个 Claude Code 实例自带 model |
| In-process tool execution | Claude Code 自行 Bash 调用 |
| KB presearch | Claude Code 通过 skills 决定 |
| Escalation regex detection | 迁入 skills |

### 4.4 channel-instructions.md — 薄路由层

channel-instructions.md 只做模式路由和工具提示，不包含业务细节：

```markdown
# AutoService Channel Instructions

消息通过 <channel> 标签到达，meta 中包含 runtime_mode 和 business_mode。

## 运行模式路由

### production 模式
根据 business_mode 选择 skill：
- sales → 使用 /sales-demo 或 /cinnox-demo skill
- support → 使用 /customer-service skill

加载 `.autoservice/rules/` 中的行为规则。
受限：不得读取 CRM 原始数据、不得执行系统命令、不得暴露内部信息。

### improve 模式
使用 /improve skill。全权限。

## 工具
- reply(chat_id, text) — 回复消息
- react(message_id, emoji_type) — 表情确认
- Plugin tools — 按已加载 plugins 可用

## 数据目录
- `.autoservice/rules/` — 行为规则
- `.autoservice/database/crm.db` — CRM
- `.autoservice/database/knowledge_base/` — KB
- `.autoservice/database/sessions/` — 会话日志
```

业务细节（对话流程、escalation 规则、gate 机制、customer type 推断、persona）全部在各 skill 的 SKILL.md 中定义，或作为 `.autoservice/rules/*.yaml` 运行数据存储。

### 4.5 Skills 和 .autoservice/ 职责

| 业务功能 | 归属 | 说明 |
|----------|------|------|
| Sales 对话流程 | `skills/sales-demo/SKILL.md` 或 `skills/cinnox-demo/SKILL.md` | 已有，保持不变 |
| Support 对话流程 | `skills/customer-service/SKILL.md` | 已有，保持不变 |
| Improve 操作指南 | `skills/improve/SKILL.md` | 已有，保持不变 |
| Escalation 规则 | `.autoservice/rules/escalation.yaml` | 新增：触发词、条件、行为。Skill 读取此文件决定是否升级 |
| Gate 机制 | Skill 内定义 | 各 skill 自行定义 lead collection → KB 查询的流程门控 |
| Customer type 推断 | Skill 内定义 | Claude 自行从对话中判断，不再靠 Python regex |
| Human agent handoff | `.autoservice/rules/escalation.yaml` + Skill | 规则定义在数据中，执行逻辑在 skill instructions 中 |
| Persona | `plugins/*/references/persona.md` | 已有机制，不变 |
| 行为规则（三层） | `.autoservice/rules/*.yaml` | 已有机制，不变 |

## 5. Protocol Additions

补充 channel-server-design.md §3 的注册协议：

```json
// register — 增加 runtime_mode, business_mode
{
  "type": "register",
  "role": "developer",
  "chat_ids": ["*"],
  "instance_id": "claude-autoservice-cinnox-0406-abc",
  "runtime_mode": "improve",
  "business_mode": null
}

// web/app.py register — ONE connection, prefix pattern (Review fix C2)
{
  "type": "register",
  "role": "web",
  "chat_ids": ["web_*"],
  "instance_id": "web-app",
  "runtime_mode": "production"
}

// message — 携带两层 mode
{
  "type": "message",
  "chat_id": "web_sess_20260406_120000",
  "source": "web",
  "user": "DEMO-1234",
  "user_id": "web_anon_abc",
  "text": "你们有什么产品？",
  "ts": "2026-04-06T12:00:00Z",
  "runtime_mode": "production",
  "business_mode": "sales",
  "routed_to": null
}

// ux_event — channel.py → channel-server → web/app.py
{
  "type": "ux_event",
  "chat_id": "web_sess_xxx",
  "event": "kb_searching",
  "data": {"query": "pricing plans"}
}
```

### web/app.py 注册流程

web/app.py 启动时开 **一个** 持久 WebSocket 连接到 channel-server，注册 `web_*`（前缀匹配）。所有浏览器 session 复用此连接。

```
web/app.py 启动 → 连 ws://localhost:9999 → register(chat_ids=["web_*"], role="web")
  ↓
浏览器连接 /ws/chat → auth token 验证 → 生成 web_session_id → chat_id = "web_{session_id}"
  → web/app.py 内部 subscribe(chat_id) 到 bridge 的 reply 队列
  → 浏览器消息 → bridge.send_message(type=message, chat_id=web_xxx)
  → channel-server 路由到 channel.py 实例 → Claude Code 处理
  → reply(chat_id="web_xxx") → channel-server → web/app.py bridge → demux by chat_id → 浏览器
```

### business_mode 确定时机

- **Web 端**：用户建连时由前端 UI 选择（login 页面选 sales/support），通过注册消息传递
- **飞书端**：channel-server.py 默认 `sales`，可通过管理群命令 `/mode oc_aaa support` 切换，或由 Claude Code 根据对话内容自动判断后通知 channel-server 更新

## 6. Web-Specific Concerns

### 6.1 Session Persistence

Web session 数据（conversation history, customer_type, resolution 等）继续由 web/app.py 管理：

- web/app.py 维护 `session_data` dict，每次收到 reply 后追加 conversation
- 保存到 `.autoservice/database/sessions/{access_code}/{session_id}.json`
- Session resume: web/app.py 加载 JSON → 发给浏览器恢复 UI

channel-server.py 和 channel.py 不感知 session persistence。

### 6.2 UX 中间状态

Web 前端需要 `thinking`, `kb_searching`, `kb_sources` 等中间状态来显示 UI 指示器。

方案：channel.py 在 Claude Code 执行 tool 时，发送 `ux_event` 给 channel-server.py，channel-server.py 转发给对应的 web/app.py 连接。

channel.py 如何知道 Claude Code 在执行 tool？通过 MCP tool call 拦截：
- `call_tool("reply", ...)` → 正常 reply
- `call_tool("Bash", {command: "curl .../kb_search..."})` → 发送 `ux_event(kb_searching)` 给 channel-server，然后执行

飞书端忽略 `ux_event`（飞书 UI 不需要这些状态）。

### 6.3 Heartbeat

Web WebSocket 需要 heartbeat 保持连接。两层 heartbeat：
- web/app.py ↔ 浏览器：web/app.py 自行发 heartbeat（前端自理）
- web/app.py ↔ channel-server.py：复用 channel-server 的 ping/pong 机制

## 7. Migration Phases

### Phase 1: channel-server.py 核心

新增 `feishu/channel-server.py`：
- 飞书 WebSocket 连接（从 channel.py 迁移）
- 本地 WebSocket server (:9999)
- 注册协议 + 路由表
- Reply 反向路由（`oc_` → 飞书 API）
- 管理群基础通知
- 消息去重、bot 过滤、ACK reaction
- 用户名解析 + CRM 入站记录
- runtime_mode 命令拦截（`/improve`, `/production`）

验证：飞书消息能路由到 channel.py，reply 能返回飞书。

### Phase 2: channel.py 改造

改造 `feishu/channel.py`：
- 去掉飞书 WebSocket 代码
- 新增 WebSocket client 连 localhost:9999 + 自动重连
- 注册协议实现
- reply/react 改为发给 channel-server.py
- 删除迁出的功能（去重、用户解析、CRM 记录、startup 广播等）

验证：飞书端功能等价（消息收发、mode 切换、plugin tools）。

### Phase 3: Web 集成

改造 `web/app.py` + `web/websocket.py`：
- web/app.py 作为 WebSocket client 连 channel-server.py
- 注册 `web_{session_id}` chat_id
- websocket.py 改为 thin relay（浏览器 ↔ channel-server 透传）
- Reply 反向路由（`web_` → WebSocket 转发到浏览器）
- UX 事件透传
- 删除 SDK/API 后端代码

验证：Web 对话能通过 channel-server → channel.py → Claude Code 完成。

### Phase 4: 业务逻辑统一

- 更新 channel-instructions.md 为薄路由层
- 创建 `.autoservice/rules/escalation.yaml`
- 验证各 skill 在新架构下工作正常
- 统一 mode 命名（production/improve + sales/support）

验证：两端的 sales/support/improve 模式行为一致。

### Phase 5: 清理

- 删除 `web/claude_backend.py`
- 删除 `web/system_prompts.py`
- 精简 `web/websocket.py`
- 更新 `claude.sh`（接受 chat_id 参数）
- 更新 `Makefile`（新增 `run-server` target）
- 更新 `pyproject.toml`（移除 web 不再需要的依赖）

## 8. Files Changed Summary

| 文件 | 操作 | Phase |
|------|------|-------|
| `feishu/channel-server.py` | 新增 | 1 |
| `feishu/channel.py` | 大改 | 2 |
| `feishu/channel-instructions.md` | 重写（精简） | 4 |
| `web/app.py` | 改造 | 3 |
| `web/websocket.py` | 大改（精简为 relay） | 3 |
| `web/claude_backend.py` | 删除 | 5 |
| `web/system_prompts.py` | 删除 | 5 |
| `claude.sh` | 改造 | 5 |
| `Makefile` | 新增 target | 5 |
| `.autoservice/rules/escalation.yaml` | 新增 | 4 |

## 9. Design Review Findings

**Reviewer:** Claude Opus 4.6 (code-reviewer agent)
**Date:** 2026-04-06
**Scope:** Architecture validation against current codebase + implementation plan consistency

### What Works Well

- **Clean separation of concerns** — three-tier split (channel-server as router, channel.py as MCP bridge, web/app.py as frontend) has well-defined boundaries.
- **Mode taxonomy** — splitting overloaded `mode` into `runtime_mode` + `business_mode` resolves real ambiguity where `_chat_modes` conflates deployment context with conversation persona.
- **YAGNI discipline** — no HA, no persistence queue, no auto-scaling for v1.

### Critical Issues (Must Fix)

**C1. `inject_message()` meta field mismatch**

Current `inject_message()` in `channel.py:174` passes `"mode": msg.get("mode", "service")`. New protocol uses `runtime_mode` + `business_mode` as separate fields. If not updated, Claude Code will always see `mode: "service"` regardless of what channel-server sends — the entire mode taxonomy is silently broken.

Fix: Task 2.1 must update `inject_message()` to pass both new fields in meta.

**C2. Web per-session connections vs architecture diagram**

§3 architecture diagram shows `web/app.py` as a **single** client with `chat_ids=["web_*"]` using prefix matching. But §5 registration flow describes each browser session opening its own WebSocket to channel-server with a unique `web_{session_id}`. 50 concurrent web users = 50 WebSocket connections + route table entries + heartbeats.

Fix: web/app.py should open **one** persistent connection, register `web_*`, and multiplex all browser sessions over it. Replies include `chat_id` for demuxing.

**C3. MCP tool handler async boundary**

`_handle_reply` using `asyncio.get_event_loop().create_task()` inside MCP tool handler is unsafe. MCP runs under `anyio` task group; `asyncio.get_event_loop()` may return wrong loop or raise errors on Python 3.12+.

Fix: Use threading (like current `send_reaction()`), or make handler async with `await`.

### Important Issues (Should Fix)

**I1. `_seen` set grows unboundedly in channel-server**

Channel-server is a long-running daemon; `_seen` and `_recent_sent` never prune. Use `collections.deque(maxlen=10000)` alongside the set, evicting old entries.

**I2. No test for web relay path**

Web relay (websocket.py rewrite) has authentication, session persistence, bidirectional relay, and error handling — zero automated tests. Add `tests/test_web_relay.py` using mock WebSocket server.

**I3. channel-server `_handle_client` missing `type: "message"` handler**

Web/app.py sends `type: "message"` through its registered WebSocket, but `_handle_client` only handles `register`, `reply`, `react`, `ux_event`, `pong`. Web user messages will be dropped silently.

Fix: Add `message` handler in `_handle_client` that calls `route_message()`.

**I4. `session_persistence` API compatibility**

Verify `save_session_data(web_session_id, session_data)` reads `access_code` from the dict internally. If it needs an explicit parameter, update the relay code.

**I5. `_resolve_user` blocks Feishu SDK callback thread**

Synchronous HTTP request in Feishu event callback blocks the SDK's event processing. Inherited from current channel.py, but more impactful in long-running daemon. Accept for v1, add TODO for v2.

### Suggestions (Nice to Have)

**S1.** Add `"protocol_version": 1` to register messages for future compatibility.

**S2.** `_new_user` sentinel in message dict is fragile — handle admin notification immediately instead of embedding in message.

**S3.** `claude.sh` chat_id detection heuristic (`[[ "$1" != [123] ]]`) is fragile. Prefer explicit `--chat` flag.

**S4.** Design doc §5 says `@chat_id` for admin injection, but `/inject chat_id text` is better (avoids Feishu at-mention ambiguity). Align docs.

**S5.** Web graceful degradation — show "service unavailable" with retry instead of WebSocket close when channel-server is down.

**S6.** `_recent_sent` also never pruned — fix alongside `_seen` (I1).
