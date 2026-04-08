# /explain Command — Flow Explorer Design

## Overview

Add `/explain` command to the admin management group. Given a natural language query (user question or custom scenario), it generates an interactive flow visualization showing how AutoService processes it. The visualization is a draggable node graph served as a web page, with annotation and discussion prompt generation.

## Architecture

```
管理群 /explain "用户问DID价格"
        │
        ▼
  channel-server
    1. 回复管理群 "正在分析..."
    2. 构造消息 (runtime_mode="explain", chat_id="admin_explain")
    3. route_message → wildcard instance
                              │
                              ▼
                     Claude Code 实例 [*]
                              │
                    channel-instructions 路由:
                    runtime_mode=explain → /explain skill
                              │
                          /explain skill
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
        1. 检索 flows/  2. 未命中则    3. 渲染 HTML
        LLM语义匹配      分析 skills     注入 JSON
        组合atomic flow  生成+保存flow   模板渲染
                │             │             │
                └──────┬──────┘             │
                       ▼                    ▼
                flow YAML → JSON     explain 模板
                       │                    │
                       └────────┬───────────┘
                                ▼
                   .autoservice/explain/{id}.html
                                │
                                ▼
                   reply → 管理群链接
                   https://{base_url}/explain/{id}.html
```

## File Structure

```
.autoservice/
  flows/                          # Flow source of truth (YAML, git tracked)
    _index.yaml                   # flow_id → description/tags/triggers
    identify-customer-type.yaml
    new-customer-lead.yaml
    kb-query-routing.yaml
    ...
  explain/                        # Generated explain pages (gitignored)
    {id}.html
  config.yaml                     # Public config: company, base_url (git tracked)
  config.local.yaml               # Private config: API keys (gitignored, existing)

skills/
  explain/
    SKILL.md                      # Explain skill definition
    templates/
      explain.html                # Fixed HTML template
      dagre.min.js                # Vendored auto-layout engine (~30KB)

web/app.py                        # Add /explain/{path} route serving .autoservice/explain/
```

## §1 Flow Granularity Principle

Based on function decomposition + DAG subgraph partitioning:

### Atomic Flow

A single decision unit:
- Contains **1 decision point** (branch/judgment) with all exit paths
- **3–8 nodes** (entry → preconditions → decision → branch results)
- Exactly **1 entry node**, **1–3 exit nodes** (resolve / handoff / error)
- Analogy: a function with single responsibility

### Composite Flow

Assembled by connecting atomic flows via exit→entry:
- Exit nodes of type `handoff` annotate `next_flow: <flow_id>`
- `/explain` rendering expands sub-flows with **max depth 3** and **visited-set cycle detection**
- Self-referencing flows (loops) render as a back-edge annotation, not recursive expansion
- Business execution follows `next_flow` chain

### Granularity Rules

| Signal | Action |
|---|---|
| A flow has >1 independent decision point | Split: each decision point becomes its own flow |
| A flow has only 1-2 nodes with no decision | Merge into upstream flow |
| Multiple flows share the same subsequence | Extract as independent flow, reuse via reference |

Most user questions = 2–4 atomic flows composed together.

## §2 Flow YAML Format

### Atomic Flow Example

```yaml
id: identify-customer-type
name: 识别客户类型
description: 根据用户首条消息判断新客户/老客户/合作伙伴
tags: [customer, identification, gate]

entry: check_signal
exits:
  - node: route_new
    type: handoff
    next_flow: new-customer-lead
  - node: route_existing
    type: handoff
    next_flow: existing-customer-verify
  - node: route_partner
    type: handoff
    next_flow: partner-escalation
  - node: ask_type
    type: handoff
    next_flow: identify-customer-type  # self-ref → renders as loop annotation

nodes:
  - id: check_signal
    label: 检查消息信号
    type: process
    note: 从首条消息提取意图关键词

  - id: has_signal
    label: 信号明确？
    type: decision
    condition: 消息包含客户类型关键词

  - id: route_new
    label: → 新客户流程
    type: exit

  - id: route_existing
    label: → 老客户流程
    type: exit

  - id: route_partner
    label: → 合作伙伴流程
    type: exit

  - id: ask_type
    label: 询问客户类型
    type: action
    note: "Happy to help! Are you new to CINNOX, or do you already have an account with us?"

edges:
  - from: check_signal
    to: has_signal
  - from: has_signal
    to: route_new
    label: 新客户信号
  - from: has_signal
    to: route_existing
    label: 老客户信号
  - from: has_signal
    to: route_partner
    label: 合作伙伴信号
  - from: has_signal
    to: ask_type
    label: 无明确信号
```

### Required Fields

Every flow YAML must have: `id`, `name`, `description`, `tags`, `entry`, `exits`, `nodes`, `edges`. The explain skill validates these before saving dynamically generated flows.

### Node Types

| type | Meaning | Shape |
|---|---|---|
| `process` | Processing/analysis step | Rounded rectangle |
| `decision` | Judgment/branch | Diamond |
| `action` | Send message / execute operation | Rectangle |
| `exit` | Exit point (resolve/handoff/error) | Circle |

### Index File `_index.yaml`

```yaml
flows:
  - id: identify-customer-type
    name: 识别客户类型
    tags: [customer, identification, gate]
    triggers: ["谁", "客户类型", "新客户还是老客户"]

  - id: new-customer-lead
    name: 新客户信息收集
    tags: [customer, lead, collection]
    triggers: ["收集信息", "lead", "姓名公司邮箱"]

  - id: kb-query-routing
    name: 知识库查询路由
    tags: [kb, query, routing, domain]
    triggers: ["产品问题", "价格", "DID", "功能"]
```

### Index Matching Strategy

Matching is **LLM-driven**: Claude Code reads `_index.yaml` and uses semantic understanding to select relevant flows based on the `/explain` query. No embedding database or fuzzy-match algorithm needed — Claude compares the query against `name`, `tags`, and `triggers` fields and selects the best-matching combination of atomic flows. This is simple, accurate, and requires zero additional infrastructure.

## §3 HTML Template & Interaction

### Layout

```
+----------------------------------------------------------+
| 🔍 CINNOX Flow Explorer                    [← 返回列表]  |
+----------------------------------------------------------+
|                                                          |
|  Canvas (draggable node flow graph, auto-layout)         |
|                                                          |
|   [process]──→◇decision◇──→[action]──→(exit)            |
|                    │                                     |
|                    └──→[action]──→(exit)                 |
|                                                          |
+---------------------------+------------------------------+
| 📝 节点详情                | 💬 讨论                      |
|                           |                              |
| (初始: 点击节点查看详情)    | (初始: 引导文字)              |
| ─────────────────         |                              |
| [节点名称]                | 无标记时:                     |
| 类型: decision            | "请解释这个流程的整体设计思路" |
| 说明: ...                 |                              |
| 注释: (可编辑文本框)       | 有标记时:                     |
| 标记: ✅正常 ⚠️待改进 ❌问题| 自动生成讨论 prompt           |
|                           |                    [复制]   |
+---------------------------+------------------------------+
```

### Auto-Layout

Initial node positions computed by vendored **dagre.min.js** (directed graph layout, ~30KB inline). Dagre computes a layered layout suitable for flowcharts. After initial render, users can drag nodes freely; positions persist in localStorage.

### Core Interactions

- **Drag nodes** — free layout on canvas, position persisted in localStorage
- **Click node** — left panel shows note + editable annotation + status mark
- **Mark nodes** — three states (OK / improve / problem); marked nodes appear in discussion prompt
- **Expand composite** — exit nodes with `handoff` show expand button, loads `next_flow` sub-graph inline (max depth 3, cycle detection)
- **Progressive discussion prompt** — initially shows guide text; updates live as user marks nodes; no marks = general overview prompt

### Prompt Output

When no nodes are marked:
> 请解释"用户问DID价格"这个场景的整体处理流程和设计思路。

When nodes are marked:
> 我在查看"用户问DID价格"的处理流程，由以下子流程组成：识别客户类型 → 新客户信息收集 → 知识库查询路由。
> 我标记了 2 个需要讨论的节点：
> 1. ⚠️ "知识库查询路由 / 判断 domain" — [user annotation]
> 2. ❌ "新客户信息收集 / 收集全部字段" — [user annotation]
> 请针对这些节点提出改进建议。

### Style (consistent across all generated pages)

- **Light theme** — white background (#ffffff), light gray panels (#f8fafc)
- **Node colors fixed**: process=#3b82f6, decision=#f59e0b, action=#10b981, exit=#6b7280
- **Edges**: dark gray (#374151), solid arrowheads
- **System font** for UI, monospace for code/values
- **Single self-contained HTML file** — dagre.min.js inlined, all CSS inline

## §4 Base URL Configuration

File: `.autoservice/config.yaml` (git tracked, public config)

```yaml
company: cinnox
base_url: https://cinnox.h2os.cloud
```

This is distinct from `.autoservice/config.local.yaml` (gitignored) which holds API keys and secrets. `config.yaml` stores non-sensitive deployment configuration.

The explain skill reads `base_url` to construct the link sent back to the admin group.

## §5 Admin Command Flow

### channel-server.py

New command in `_handle_admin_message`:

```
/explain <natural language query>
```

Behavior:
1. Parse the query text after `/explain `
2. Reply to admin group: "正在分析流程，请稍候..."
3. Construct message:
   ```python
   {
       "type": "message",
       "chat_id": "admin_explain",         # synthetic chat_id
       "text": query,                       # the raw natural language query
       "user": "admin",
       "runtime_mode": "explain",           # triggers explain routing
       "business_mode": "customer_service",
       "source": "admin",
       "admin_chat_id": self.admin_chat_id, # so skill can reply back here
   }
   ```
4. Route via `route_message("admin_explain", msg)` — hits wildcard instance

### channel.py → Claude Code

Claude Code receives the message via MCP notification. `channel-instructions.md` routes `runtime_mode: "explain"` to the /explain skill.

The explain skill uses `reply(admin_chat_id, url)` to send the link back to the admin group (not to `admin_explain`).

### explain skill (SKILL.md)

1. Read `.autoservice/flows/_index.yaml`
2. LLM semantic match: select relevant atomic flows for the query
3. If no match: analyze skills/rules/instructions, generate new atomic flow(s), validate required YAML fields, save to `flows/`, update `_index.yaml`
4. Load matched flow YAML(s), convert to JSON
5. Read `skills/explain/templates/explain.html`, inline `dagre.min.js`
6. Inject flow JSON + metadata into template
7. Save to `.autoservice/explain/{id}.html`
8. Read `base_url` from `.autoservice/config.yaml`
9. Reply via `reply(admin_chat_id, url)` to the admin group

## §6 Integration Points

### channel-instructions.md additions

Data section:
```
- `.autoservice/flows/` — 业务流程定义（atomic flows，YAML）
```

Mode routing — new section:
```
### explain mode
Use /explain skill. Analyze the query, match/generate flows, render visualization.
Reply the generated URL back to admin_chat_id from the message meta.
```

### web/app.py addition

Add a route to serve generated explain pages from `.autoservice/explain/`:

```python
@app.get("/explain/{path:path}")
async def serve_explain(path: str):
    file = AUTOSERVICE_DIR / "explain" / path
    if file.exists():
        return FileResponse(file)
    raise HTTPException(404)
```

### Business execution

When processing customer messages in production mode, Claude Code can reference `.autoservice/flows/` to understand the expected processing sequence. Flows are descriptive context, not prescriptive.

## §7 Summary of Components

| Component | Action |
|---|---|
| `channel_server.py` | Add `/explain` admin command, update `help_text()` |
| `channel-instructions.md` | Add `explain` mode routing + flows data reference |
| `skills/explain/SKILL.md` | New skill: match/generate flows, render HTML, validate YAML |
| `skills/explain/templates/explain.html` | Fixed HTML template with canvas + dagre auto-layout |
| `skills/explain/templates/dagre.min.js` | Vendored layout engine (~30KB) |
| `.autoservice/flows/*.yaml` | Atomic flow definitions (git tracked) |
| `.autoservice/flows/_index.yaml` | Flow index for LLM-driven retrieval |
| `.autoservice/config.yaml` | Public config: company name, base_url (git tracked) |
| `.autoservice/explain/` | Generated explain pages (gitignored) |
| `web/app.py` | Add `/explain/{path}` route |

## §8 Review Issues Addressed

| Issue | Resolution |
|---|---|
| C1: Static file path mismatch | Generated HTML → `.autoservice/explain/` (gitignored) + dedicated FastAPI route |
| C2: `[EXPLAIN]` prefix routing undefined | Use `runtime_mode: "explain"` metadata field, matching existing routing pattern |
| C3: Missing chat_id | Synthetic `chat_id: "admin_explain"` + `admin_chat_id` in metadata for reply |
| I1: config.yaml vs config.local.yaml | `config.yaml` = public (tracked), `config.local.yaml` = secrets (gitignored) |
| I2: Circular flow references | Max expansion depth 3 + visited-set; self-refs render as loop annotation |
| I3: No flow validation | Explain skill validates required YAML fields before saving |
| I4: Matching underspecified | Explicitly LLM-driven semantic matching against index |
| M1: Auto-layout needed | Vendor dagre.min.js (~30KB) inline for directed graph layout |
| M2: help_text not updated | Added to component table |
