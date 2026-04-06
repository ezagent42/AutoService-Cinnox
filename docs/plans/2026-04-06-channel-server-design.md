# Channel-Server — 多实例消息路由层设计

**Date:** 2026-04-06
**Status:** Approved (with review amendments 2026-04-05)
**Authors:** Allen Woods + Claude
**Reviewer:** Claude Opus 4.6

## 1. Overview

`channel-server.py` 是独立守护进程，负责飞书连接 + 多 Claude Code 实例消息路由。不绑定 Claude Code，直接处理管理群命令和通知。

### Goals
1. **飞书连接唯一** — 解决多实例抢消息问题
2. **按 chat_id 路由** — 每个客户对话可分配专属 Claude Code 实例
3. **开发者全局视野** — 通配实例接收所有消息副本
4. **通道无关** — 飞书（`oc_`）、Web（`web_`）、未来 IM 通道统一路由协议
5. **管理群监控** — 新用户通知、实例状态、快捷指令

### Non-Goals (YAGNI)
- 不做自动实例创建/回收（v1 手动）
- 不做消息持久化队列（内存路由）
- 不做 HA/集群
- 不做实例间消息转发（开发者通过通配自然看到）

## 2. Architecture

```
飞书 WebSocket ←→ channel-server.py (守护进程, localhost:9999)
                    │ 本地 WebSocket Server
                    │
                    ├── channel.py#0 (开发者 Claude Code, chat_ids=["*"])
                    ├── channel.py#1 (客户A Claude Code, chat_ids=["oc_aaa"])
                    ├── channel.py#2 (客户B Claude Code, chat_ids=["oc_bbb"])
                    └── web/app.py   (Web 通道, chat_ids=["web_*"])

飞书
├── 管理群 (oc_admin) ← channel-server.py 直接处理
├── 用户A 单聊 (oc_aaa) ← 路由到 channel.py#1
└── 用户B 单聊 (oc_bbb) ← 路由到 channel.py#2
```

### 组件职责

**channel-server.py（新增）：**
- 飞书 WebSocket 唯一连接
- 本地 WebSocket server（:9999），接受 channel.py / web/app.py 注册
- 路由表：chat_id → WebSocket 连接
- 未注册 chat_id → 路由给通配 `*` 实例
- 管理群直接处理：通知（新用户、实例上下线）、命令（`/status`）、`@chat_id` 转发
- reply 反向路由：chat_id 前缀判断通道（`oc_` → 飞书，`web_` → Web）

**channel.py（改造）：**
- 不再连飞书 WebSocket
- 启动时连 `ws://localhost:9999`，发送注册消息
- chat_id 来源：环境变量 `AUTOSERVICE_CHAT_ID`（指定）或 `*`（通配）
- MCP stdio ↔ Claude Code 不变
- reply tool → 发给 channel-server.py → 路由到飞书/Web

**web/app.py（改造）：**
- 不再使用 claude_agent_sdk 独立会话
- 作为 WebSocket client 连 channel-server.py，注册 `web_` 前缀 chat_id
- 浏览器 ↔ FastAPI WebSocket ↔ channel-server.py ↔ channel.py ↔ Claude Code

## 3. Registration Protocol

```json
// channel.py → channel-server.py (连接后立即发送)
{
  "type": "register",
  "role": "developer",
  "chat_ids": ["*"],
  "instance_id": "claude-autoservice-cinnox-0406-abc"
}

// channel-server.py → channel.py (确认)
{
  "type": "registered",
  "chat_ids": ["*"]
}

// channel-server.py → channel.py (路由消息)
{
  "type": "message",
  "chat_id": "oc_aaa",
  "message_id": "om_xxx",
  "user": "林大猫 (ou_3ab76...)",
  "user_id": "ou_3ab76...",
  "text": "你们有什么产品？",
  "ts": "2026-04-06T00:00:00Z",
  "source": "feishu",
  "mode": "service"
}

// channel.py → channel-server.py (reply)
{
  "type": "reply",
  "chat_id": "oc_aaa",
  "text": "我们提供以下产品..."
}

// channel.py → channel-server.py (react)
{
  "type": "react",
  "message_id": "om_xxx",
  "emoji_type": "THUMBSUP"
}

// channel-server.py → channel.py (错误)
{
  "type": "error",
  "code": "REGISTRATION_CONFLICT",
  "message": "chat_id oc_aaa already registered by instance xyz"
}

// channel-server.py ↔ channel.py (心跳)
{
  "type": "ping"
}
{
  "type": "pong"
}
```

### REVIEW: 协议补充

1. **`mode` 字段缺失** -- 当前 channel.py (line 301-308) 在消息 dict 中包含 `mode` 字段（service/improve），channel-instructions.md 依赖此字段切换行为。路由协议 message 类型必须透传此字段，否则下游 Claude Code 无法区分模式。已在 message 示例中添加。
2. **错误消息类型未定义** -- 注册冲突、无效 chat_id 等错误场景没有协议定义。已添加 error 类型。
3. **心跳机制缺失** -- WebSocket 连接可能静默断开（特别是 macOS 睡眠恢复后）。需要 ping/pong 心跳检测。已添加。
4. **`register` 消息未包含能力声明** -- channel.py 目前有 `/improve` 和 `/service` 模式切换逻辑。注册时应声明此实例是否支持模式切换，还是由 channel-server.py 统一处理。

## 4. Routing Logic

```python
# 伪代码
def route_message(chat_id, message):
    routed = False

    # 1. 精确匹配
    if chat_id in route_table:
        send_to(route_table[chat_id], message)
        routed = True

    # 2. 前缀匹配 (web_* 等)
    if not routed:
        for pattern, conn in prefix_routes.items():
            if chat_id.startswith(pattern):
                send_to(conn, message)
                routed = True
                break

    # 3. 通配
    # 无论是否命中上面的匹配，通配实例始终收到副本
    for conn in wildcard_connections:
        # 避免同一消息发送两次给同一连接（当通配实例也是精确匹配的实例时）
        if routed and conn == route_table.get(chat_id):
            continue
        send_to(conn, message)

    # 4. 无匹配 + 无通配 = 消息丢失 → 需要处理
    if not routed and not wildcard_connections:
        log.warning(f"No route for {chat_id}, message dropped")
        # 可选：缓存最近 N 条未路由消息，实例注册时回放
```

**关键：通配实例始终收到所有消息的副本，即使消息已被精确路由到专属实例。** 这保证开发者始终有全局视野。

### REVIEW: 路由逻辑注意事项

1. **原伪代码使用 if/for 无 return/routed 标记** -- 如果精确匹配命中，前缀匹配仍然会执行扫描（浪费）。已修正为 `routed` 标记控制流。
2. **重复发送风险** -- 当开发者通配实例同时也注册了某个精确 chat_id 时，同一消息会被发送两次。已在通配循环中加入去重检查。
3. **无通配 + 无匹配** -- 如果没有任何通配实例在线，且消息的 chat_id 无人注册，消息将静默丢失。已添加日志和可选缓存注释。

## 5. Admin Group (管理群)

channel-server.py 启动时需要配置管理群 chat_id（环境变量 `ADMIN_CHAT_ID`）。

### 自动通知

| 事件 | 通知内容 |
|------|---------|
| 新用户首条消息 | "🆕 新用户: {name} ({chat_id})\n启动实例: `./claude.sh {chat_id}`" |
| channel.py 实例连接 | "🟢 实例已连接: {chat_ids} ({instance_id})" |
| channel.py 实例断开 | "🔴 实例已断开: {chat_ids} ({instance_id})" |
| channel-server.py 启动 | "✅ Channel-Server 已上线" |

### 管理命令

| 命令 | 行为 |
|------|------|
| `/status` | 回复路由表：活跃实例列表、各实例 chat_ids、连接时长 |
| `@{chat_id} {text}` | 解析 → 注入到 chat_id 对应的 channel.py 实例（开发者介入） |

## 6. Instance Lifecycle

### 启动流程
```
开发者运行: ./claude.sh oc_aaa
  ↓
claude.sh 设置 AUTOSERVICE_CHAT_ID=oc_aaa
  ↓
Claude Code 启动 → .mcp.json → 启动 channel.py 子进程
  ↓
channel.py 读取 AUTOSERVICE_CHAT_ID
  ↓
连接 ws://localhost:9999 → 发送 register(chat_ids=["oc_aaa"])
  ↓
channel-server.py 更新路由表 → 管理群通知"实例已连接"
  ↓
后续 oc_aaa 消息 → channel-server.py → channel.py → Claude Code
```

### 断开流程
```
开发者关闭 Claude Code (Ctrl+C 或 /exit)
  ↓
channel.py 子进程结束 → WebSocket 断开
  ↓
channel-server.py 检测断开 → 从路由表移除 oc_aaa
  ↓
管理群通知"实例已断开"
  ↓
后续 oc_aaa 消息 → 回退到通配实例(开发者)
```

### 开发者模式（通配）
```
./claude.sh           # 无参数 = 通配模式
  ↓
AUTOSERVICE_CHAT_ID=*
  ↓
channel.py register(chat_ids=["*"], role="developer")
  ↓
接收所有未被专属实例处理的消息 + 所有消息的副本
```

### REVIEW: channel-server.py 重启恢复

**Critical: 设计中未覆盖 channel-server.py 自身崩溃/重启的场景。**

当 channel-server.py 重启时：
1. 所有 channel.py 实例的 WebSocket 连接断开
2. channel.py 作为 MCP 子进程由 Claude Code 管理，不会自动重启
3. 开发者必须逐个重启所有 Claude Code 实例

**建议添加 channel.py 重连逻辑：**
```python
# channel.py 伪代码
async def connect_with_retry():
    while True:
        try:
            async with websockets.connect("ws://localhost:9999") as ws:
                await register(ws)
                await message_loop(ws)
        except (ConnectionRefused, ConnectionClosed):
            log.warning("channel-server disconnected, retrying in 3s...")
            await asyncio.sleep(3)
```

这样 channel-server.py 重启后，所有活跃的 channel.py 实例会自动重新注册。MCP stdio 连接和 Claude Code 不受影响。

## 7. Web Integration

```
浏览器 ↔ WebSocket ↔ web/app.py
                        │
                        ↕ ws://localhost:9999 (作为 client)
                        │ register(chat_ids=["web_session_xxx"])
                        │
                    channel-server.py
                        │
                        ↕ 路由到对应 channel.py
                        │
                    Claude Code 处理
```

Web 会话的 chat_id 格式：`web_{session_id}`

reply 反向路由：
- `oc_` 开头 → channel-server.py 用飞书 API 发送
- `web_` 开头 → channel-server.py 转发给 web/app.py 的 WebSocket 连接

## 8. claude.sh Changes

```bash
# 新增：接受 chat_id 参数
CHAT_ID="${1:-*}"  # 默认通配

# 传递给 channel.py
export AUTOSERVICE_CHAT_ID="$CHAT_ID"

# 使用方式
./claude.sh                    # 开发者模式（通配）
./claude.sh oc_8aac6e1a...     # 客户专属实例
```

### REVIEW: claude.sh 兼容性分析

**Important: 当前 claude.sh 使用 `$1` 作为 `--_internal` 的内部 mode 参数。**

claude.sh (line 302-305) 已经用 `$1` 判断 `--_internal`，`$2` 是 mode，`$3` 是 session name。直接改为 `$1` 接受 chat_id 会与现有内部调用冲突。

**建议实现方式：**
```bash
# 在 INTERACTIVE_FLAGS 构建之前解析 chat_id（排除 --_internal 场景）
if [ "$1" != "--_internal" ] && [ -n "$1" ]; then
    export AUTOSERVICE_CHAT_ID="$1"
    shift  # 移除 chat_id，后续 mode 选择正常工作
else
    export AUTOSERVICE_CHAT_ID="${AUTOSERVICE_CHAT_ID:-*}"
fi
```

或者使用显式 flag（更安全）：
```bash
./claude.sh --chat oc_8aac6e1a...
```

## 9. channel-server.py Process Management

### 启动
```bash
# 独立进程，不在 tmux/claude 内
python3 feishu/channel-server.py
# 或通过 Makefile
make run-server
```

### 配置（环境变量）
```bash
FEISHU_APP_ID=...              # 飞书应用
FEISHU_APP_SECRET=...          # 飞书应用
ADMIN_CHAT_ID=oc_xxx           # 管理群 chat_id
CHANNEL_SERVER_PORT=9999       # 本地 WebSocket 端口
```

### 依赖
- `lark_oapi` — 飞书 WebSocket + API
- `websockets` — 本地 WebSocket server
- `asyncio` — 事件循环

不依赖 `mcp`、`claude_agent_sdk` 或任何 Claude Code 组件。

## 10. Implementation Changes

| 组件 | 变更 |
|------|------|
| `feishu/channel-server.py` | 新增：飞书 WS + 本地 WS server + 路由 + 管理群 |
| `feishu/channel.py` | 改造：去掉飞书 WS，改连 localhost:9999 |
| `web/app.py` | 改造：连 channel-server.py 而非独立 SDK |
| `claude.sh` | 改造：接受 chat_id 参数，传递环境变量 |
| `Makefile` | 新增：`run-server` target |
| `.mcp.json` | 不变（仍然启动 channel.py） |

### REVIEW: 需要迁移的关键功能清单

从 channel.py 迁移到 channel-server.py 的功能（容易遗漏）：

| 功能 | channel.py 当前位置 | 迁移目标 | 复杂度 |
|------|---------------------|----------|--------|
| 用户名解析 `_resolve_user()` | line 98-135 | channel-server.py | 中（依赖 feishu_client + CRM） |
| CRM 记录 `increment_message_count/log_message` | line 295-299 | channel-server.py | 低 |
| ACK reaction `send_reaction()` | line 142-157, 224 | channel-server.py | 低 |
| 模式切换 `/improve`, `/service` | line 265-292 | **需决策** | 高（见下） |
| 消息去重 `_seen`, `_recent_sent` | line 86-87 | channel-server.py | 低 |
| bot 自身消息过滤 `_bot_open_id` | line 88, 213-215 | channel-server.py | 低 |
| 富文本解析 (text/post) | line 228-248 | channel-server.py | 低 |
| 启动广播 `send_startup()` | line 338-396 | channel-server.py | 低 |

**模式切换决策点：** 当前 `/improve` 和 `/service` 命令在 channel.py 中处理，修改 `_chat_modes` 状态并影响后续消息路由。迁移后有两个选项：
- (A) channel-server.py 拦截处理 -- 简单，但 channel-server.py 需要理解业务模式
- (B) 透传给 channel.py -- 保持 channel-server.py 纯路由，但每个实例需要维护自己的模式状态

## 11. Message Flow Examples

### 客户首次对话
```
林大猫(飞书单聊) → "你好"
  → 飞书 WS → channel-server.py
  → 路由表无 oc_aaa → 转发给通配实例(开发者 Claude Code)
  → 管理群通知："🆕 新用户: 林大猫 (oc_aaa)\n./claude.sh oc_aaa"
  → 开发者 Claude Code 处理 → reply → channel-server.py → 飞书
```

### 分配专属实例
```
开发者新终端: ./claude.sh oc_aaa
  → channel.py#1 注册 oc_aaa
  → 管理群："🟢 实例已连接: oc_aaa"
  → 后续 oc_aaa 消息路由到 channel.py#1
  → 开发者通配实例仍收到副本
```

### 开发者飞书介入
```
开发者在管理群: "@oc_aaa 注意当前活动打八折"
  → channel-server.py 解析 → 注入 channel.py#1
  → Claude Code 实例 1 收到指示 → 下次回复参考
```

### Web 用户对话
```
浏览器 → web/app.py WebSocket → "Hello"
  → web/app.py → channel-server.py (type=message, chat_id=web_sess123)
  → 路由到通配实例(开发者) 或已注册的专属实例
  → Claude Code 处理 → reply(chat_id=web_sess123)
  → channel-server.py → web/app.py → 浏览器
```

## 12. Design Review Findings

**Reviewer:** Claude Opus 4.6
**Date:** 2026-04-05
**Scope:** Architecture validation against current codebase

### What Works Well

- **Clean separation of concerns** -- channel-server.py as pure routing daemon is the right architectural choice. Keeping it independent of MCP and Claude Code means it can be tested, restarted, and monitored independently.
- **YAGNI discipline** -- the Non-Goals section correctly defers HA, persistence, and auto-scaling. For a v1 with a handful of instances, in-memory routing is entirely sufficient.
- **Admin group as observability** -- using a Feishu group as a lightweight monitoring channel is pragmatic and fits the existing workflow.
- **Backward-compatible .mcp.json** -- keeping channel.py as the MCP server entry point means Claude Code configuration does not change.

### Critical Issues (Must Fix)

**C1. channel-server.py restart loses all instances with no recovery path**

See Section 6 review amendment above. Without reconnection logic in channel.py, a channel-server.py crash requires manually restarting every Claude Code instance. This is operationally unacceptable even for v1.

**C2. Multiple instances registering for the same chat_id is undefined**

The design does not specify what happens when a second instance registers for `oc_aaa` while a first is already active. Possible semantics:
- **Last-writer-wins** -- second registration silently replaces first (dangerous, first instance keeps running but receives nothing)
- **Reject** -- return error, second instance must handle gracefully
- **Multicast** -- both receive the message (both reply = user gets duplicates)

Recommendation: Reject with an explicit error message. The first instance must be disconnected (or unregistered) before re-assignment.

**C3. Reply routing race condition**

When a wildcard developer instance and a dedicated instance both receive the same message, both may call `reply`. The design implicitly assumes only the dedicated instance replies, but there is no protocol-level enforcement. The developer wildcard instance's Claude Code has no way to know a dedicated instance also received the message.

Recommendation: Add a `routed_to` field in the message sent to wildcard instances:
```json
{
  "type": "message",
  "chat_id": "oc_aaa",
  "routed_to": "instance-1-oc_aaa",
  ...
}
```
The wildcard instance's channel-instructions.md can then instruct Claude Code to observe but not reply when `routed_to` is set.

### Important Issues (Should Fix)

**I1. `web/app.py` integration path is architecturally inconsistent**

The current web/app.py (websocket.py line 80-91) uses `claude_agent_sdk` to create its own Claude subprocess per web session -- it is a self-contained Claude Code host. The design proposes making it a thin WebSocket relay to channel-server.py, which then routes to an external channel.py/Claude Code instance.

This means:
- Web sessions can no longer have independent Claude Code subprocesses
- Web sessions must share instances with Feishu sessions (or get their own dedicated `./claude.sh web_sess_xxx` instances)
- The entire SDK-based conversation persistence (session_data, gate_cleared, customer_type detection, model switching, escalation) in websocket.py currently runs in-process -- this logic has no new home

The design should explicitly address whether web keeps its own SDK backend or fully migrates to the channel-server architecture. Partial migration would be confusing.

**I2. Admin group `@chat_id` injection is ambiguous**

Section 5 specifies `@oc_aaa some text` in the admin group triggers message injection. However:
- Feishu `@mention` creates a structured `at` tag in JSON, not plain `@text`. Parsing raw text for `@oc_aaa` requires the message to NOT use Feishu's at-mention feature.
- If the user types `@oc_aaa` as plain text, Feishu might auto-link it if a user/bot has that ID.
- The design should specify exact format: e.g., `/inject oc_aaa some text` as a slash command, which avoids ambiguity with Feishu's at-mention system.

**I3. Port 9999 conflict risk**

Port 9999 is a commonly used port (e.g., PHP-FPM debug, some DevOps tools). The design should specify fallback behavior or auto-detection. Using a less common port or Unix domain socket (`/tmp/autoservice-channel.sock`) would be more robust for local-only communication.

**I4. Feishu API dependency for admin group**

The admin group requires the bot to be added to a group chat. The design assumes `ADMIN_CHAT_ID` exists and the bot has permission to post there. If not configured, channel-server.py should degrade gracefully (log locally instead of crashing).

### Suggestions (Nice to Have)

**S1. Structured logging format**

channel-server.py should use structured JSON logging from day one. When debugging routing issues across multiple instances, grep-friendly logs are essential.

**S2. Metrics endpoint**

Add a simple HTTP endpoint (e.g., `GET /metrics` on port 9998) exposing: active connections, route table size, messages routed per chat_id, uptime. This is trivial to add with asyncio and avoids needing to send `/status` in the admin group.

**S3. Message ordering guarantee**

The design uses in-memory routing with no sequence numbers. If channel-server.py receives two messages for the same chat_id in rapid succession, the WebSocket send order to the channel.py instance is not guaranteed (asyncio task scheduling). Consider adding a sequence number per chat_id for ordering.

**S4. Graceful shutdown for channel-server.py**

On SIGTERM/SIGINT, channel-server.py should:
1. Stop accepting new Feishu messages
2. Send a `{"type": "shutdown"}` message to all connected instances
3. Wait up to 5 seconds for in-flight replies
4. Close all connections
5. Post final message to admin group
