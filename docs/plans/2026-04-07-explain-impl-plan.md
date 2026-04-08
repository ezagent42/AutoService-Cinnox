# /explain Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `/explain` admin command that generates interactive flow visualizations showing how AutoService processes user questions.

**Architecture:** Admin sends `/explain <query>` in Feishu management group → channel-server routes to wildcard Claude Code instance with `runtime_mode: "explain"` → explain skill matches/generates atomic flows from `.autoservice/flows/`, renders HTML with dagre auto-layout, serves via FastAPI → link sent back to admin group.

**Tech Stack:** Python (channel-server, FastAPI), YAML (flow definitions), HTML/CSS/JS (single-file template with vendored dagre.min.js), Canvas API for node graph rendering.

---

## Task 1: Config & Flows Infrastructure

**Files:**
- Create: `.autoservice/config.yaml`
- Create: `.autoservice/flows/_index.yaml`
- Create: `.autoservice/flows/identify-customer-type.yaml`
- Modify: `.gitignore:2-3`

### Step 1: Create `.autoservice/config.yaml`

```yaml
company: cinnox
base_url: https://cinnox.h2os.cloud
```

### Step 2: Create `.autoservice/flows/_index.yaml`

```yaml
flows:
  - id: identify-customer-type
    name: 识别客户类型
    tags: [customer, identification, gate]
    triggers: ["客户类型", "新客户还是老客户", "识别", "判断用户"]
```

### Step 3: Create first seed flow `.autoservice/flows/identify-customer-type.yaml`

Use the exact YAML from the design doc §2 (the `identify-customer-type` example).

### Step 4: Whitelist flows/ and config.yaml in `.gitignore`

Currently `.gitignore` has:
```
.autoservice/
!.autoservice/rules/
```

Add after line 3:
```
!.autoservice/flows/
!.autoservice/config.yaml
```

This ensures flows and config are tracked in git while the rest of `.autoservice/` (logs, database, uploads, explain/) stays gitignored.

### Step 5: Verify and commit

```bash
git status  # should show new files as untracked, not ignored
git add .autoservice/config.yaml .autoservice/flows/ .gitignore
git commit -m "feat: add .autoservice/config.yaml and flows infrastructure"
```

---

## Task 2: channel-server `/explain` Command

**Files:**
- Modify: `feishu/channel_server.py:341-382` (`_handle_admin_message`)
- Modify: `feishu/channel_server.py:1014-1029` (`help_text`)

### Step 1: Add `/explain` handler in `_handle_admin_message`

Insert **before** the unknown-command fallback (line 380), after the `/inject` block:

```python
        if text.startswith("/explain"):
            query = text[len("/explain"):].strip()
            if not query:
                await self._reply_feishu(msg["chat_id"], "Usage: /explain <场景描述>\n  Example: /explain 用户问DID号码的价格")
                return
            await self._reply_feishu(msg["chat_id"], f"🔍 正在分析流程: {query[:50]}...")
            explain_msg = {
                "type": "message",
                "chat_id": "admin_explain",
                "text": query,
                "message_id": f"explain_{datetime.now(timezone.utc).timestamp():.0f}",
                "user": "admin",
                "user_id": "",
                "runtime_mode": "explain",
                "business_mode": "customer_service",
                "source": "admin",
                "admin_chat_id": self.admin_chat_id,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            await self.route_message("admin_explain", explain_msg)
            return
```

### Step 2: Update `help_text`

In `help_text()` method (line 1014), add the `/explain` line:

```python
    def help_text(self) -> str:
        """Generate help text for /help command."""
        return (
            "📖 Channel Server Commands\n"
            "\n"
            "/status — Instances, active chats (with #N numbers)\n"
            "/help — This message\n"
            "/inject #N <text> — Send to chat by number\n"
            "/inject <chat_id> <text> — Send to chat by full ID\n"
            "  Example: /inject #1 注意当前活动打八折\n"
            "/explain <场景描述> — Generate flow visualization\n"
            "  Example: /explain 用户问DID号码的价格\n"
            "\n"
            "Non-command messages → forwarded to Claude Code\n"
            "\n"
            "Start dedicated instance:\n"
            "  ./autoservice.sh oc_<chat_id>"
        )
```

### Step 3: Commit

```bash
git add feishu/channel_server.py
git commit -m "feat: add /explain admin command in channel-server"
```

---

## Task 3: channel-instructions.md Updates

**Files:**
- Modify: `feishu/channel-instructions.md:12-16` (Message Format)
- Modify: `feishu/channel-instructions.md:17-30` (Mode Routing)
- Modify: `feishu/channel-instructions.md:50-55` (Data)

### Step 1: Update Message Format meta fields

Change line 13 from:
```
- `runtime_mode`: "production" | "improve"
```
To:
```
- `runtime_mode`: "production" | "improve" | "explain"
```

### Step 2: Add explain mode routing

After the `routed_to set (observation mode)` section, before `## File Messages`, add:

```markdown
### explain mode
Use /explain skill. The message text is the admin's query about a scenario.
Analyze the query, match or generate flows from `.autoservice/flows/`, render a visualization page.
Reply the generated URL back to the `admin_chat_id` found in the message meta (NOT to `chat_id`).
```

### Step 3: Add flows to Data section

Add to the Data section:
```
- `.autoservice/flows/` — 业务流程定义（atomic flows，YAML）
```

### Step 4: Commit

```bash
git add feishu/channel-instructions.md
git commit -m "feat: add explain mode routing and flows data reference"
```

---

## Task 4: channel.py — Pass `admin_chat_id` Through MCP

**Files:**
- Modify: `feishu/channel.py:134-163` (`inject_message`)

### Step 1: Add `admin_chat_id` to meta

In `inject_message()`, after the `file_path` check (line ~150), add:

```python
    if msg.get("admin_chat_id"):
        meta["admin_chat_id"] = msg["admin_chat_id"]
```

This ensures the explain skill can read `admin_chat_id` from the channel notification metadata and reply to the correct Feishu group.

### Step 2: Commit

```bash
git add feishu/channel.py
git commit -m "feat: pass admin_chat_id through MCP notification"
```

---

## Task 5: web/app.py — `/explain/` Route

**Files:**
- Modify: `web/app.py:134-137` (Page routes section)

### Step 1: Add AUTOSERVICE_DIR constant and /explain route

After the existing `ROOT` and `STATIC` constants (line 51-52), add:

```python
AUTOSERVICE_DIR = ROOT / ".autoservice"
```

After the `/chat` route (line 160), before the WebSocket routes section (line 163), add:

```python
@app.get("/explain/{path:path}")
async def serve_explain(path: str):
    """Serve generated explain flow visualization pages."""
    file = AUTOSERVICE_DIR / "explain" / path
    if file.exists() and file.suffix == ".html":
        return FileResponse(file)
    raise HTTPException(404, "Explain page not found")
```

### Step 2: Commit

```bash
git add web/app.py
git commit -m "feat: add /explain/ route for flow visualization pages"
```

---

## Task 6: Vendor dagre.min.js

**Files:**
- Create: `skills/explain/templates/dagre.min.js`

### Step 1: Download dagre

```bash
mkdir -p skills/explain/templates
curl -L "https://unpkg.com/@dagrejs/dagre@1.1.4/dist/dagre.min.js" -o skills/explain/templates/dagre.min.js
```

### Step 2: Verify the file is valid JS

```bash
wc -c skills/explain/templates/dagre.min.js  # expect ~30-50KB
head -c 100 skills/explain/templates/dagre.min.js  # should start with JS code
```

### Step 3: Commit

```bash
git add skills/explain/templates/dagre.min.js
git commit -m "feat: vendor dagre.min.js for flow graph auto-layout"
```

---

## Task 7: HTML Template

**Files:**
- Create: `skills/explain/templates/explain.html`

### Step 1: Create the fixed HTML template

This is the largest single file. It must be a self-contained HTML file with all CSS/JS inline. The template uses placeholder markers that the explain skill replaces:

- `{{FLOW_DATA}}` — JSON array of flow objects
- `{{QUERY}}` — the original explain query string
- `{{GENERATED_AT}}` — ISO timestamp
- `{{DAGRE_JS}}` — contents of dagre.min.js (inlined)

The template implements:

**Layout (3 panels):**
- Top: Canvas with draggable SVG nodes (using dagre for initial layout)
- Bottom-left: Node detail panel (note, editable annotation, 3-state mark)
- Bottom-right: Progressive discussion prompt with copy button

**Node rendering (SVG, not Canvas):**
SVG is better for interactive node graphs — each node is a DOM element, so click/drag handling is simpler than Canvas hit-testing. Use dagre to compute positions, then render SVG `<g>` groups.

- `process` nodes: rounded rect, fill #3b82f6, white text
- `decision` nodes: diamond (rotated square), fill #f59e0b, white text
- `action` nodes: rect, fill #10b981, white text
- `exit` nodes: circle, fill #6b7280, white text
- Edges: dark gray (#374151) paths with arrowhead markers
- `handoff` exit nodes: dashed border + expand button (▶)

**Interactions:**
- Drag: mousedown on node → track delta → update transform on mousemove → mouseup stops
- Click: populate left panel with node details
- Mark: 3 buttons (✅ ⚠️ ❌) per node, stored in state object
- Expand: click ▶ on handoff exit → load sub-flow from `FLOW_DATA` array, re-run dagre for sub-graph, insert inline
- Copy: button copies prompt textarea to clipboard with "Copied!" feedback

**Prompt generation:**
```javascript
function updatePrompt() {
    const marked = nodes.filter(n => n.mark && n.mark !== 'ok');
    if (marked.length === 0) {
        promptEl.textContent = `请解释"${QUERY}"这个场景的整体处理流程和设计思路。`;
        return;
    }
    const flowNames = flows.map(f => f.name).join(' → ');
    let text = `我在查看"${QUERY}"的处理流程，由以下子流程组成：${flowNames}。\n`;
    text += `我标记了 ${marked.length} 个需要讨论的节点：\n`;
    marked.forEach((n, i) => {
        const icon = n.mark === 'improve' ? '⚠️' : '❌';
        const annotation = n.annotation || '(未添加注释)';
        text += `${i+1}. ${icon} "${n.flowName} / ${n.label}" — ${annotation}\n`;
    });
    text += `请针对这些节点提出改进建议。`;
    promptEl.textContent = text;
}
```

**Style rules (light theme):**
```css
body { margin: 0; font-family: system-ui, sans-serif; background: #ffffff; color: #1e293b; }
.panel { background: #f8fafc; border: 1px solid #e2e8f0; }
svg text { font-family: system-ui, sans-serif; font-size: 13px; }
```

**Critical: the template must work identically every time. No randomness, no dynamic fetches. Same FLOW_DATA → same rendering.**

### Step 2: Test template locally

Create a test HTML with hardcoded FLOW_DATA matching the `identify-customer-type` flow:

```bash
# After creating the template, open it to verify rendering:
open skills/explain/templates/explain.html
```

Verify:
- Nodes render in correct shapes and colors
- Drag works
- Click shows node details
- Mark buttons toggle correctly
- Prompt updates in real time
- Copy button works

### Step 3: Commit

```bash
git add skills/explain/templates/explain.html
git commit -m "feat: explain flow explorer HTML template with dagre layout"
```

---

## Task 8: Explain Skill (SKILL.md)

**Files:**
- Create: `skills/explain/SKILL.md`

### Step 1: Create the explain skill

```markdown
---
name: explain
description: 分析用户场景的处理流程，生成交互式流程图可视化页面。当 runtime_mode 为 explain 时自动触发。
---

# /explain — Flow Explorer

当管理群发送 `/explain <场景>` 时，本 skill 分析该场景的处理流程并生成可视化网页。

## 触发条件

channel 消息 meta 中 `runtime_mode: "explain"`。

## 处理步骤

### 1. 读取流程索引

```bash
cat .autoservice/flows/_index.yaml
```

### 2. 匹配已有流程

将用户查询与 `_index.yaml` 中每个 flow 的 `name`、`tags`、`triggers` 进行语义对比。
选出所有相关的 atomic flow（通常 2-4 个），按执行顺序排列。

**匹配规则：**
- 精确匹配 triggers 中的关键词 → 高置信
- tags 交集 ≥ 2 → 中置信
- name 语义相关 → 低置信（需结合上下文判断）
- 选出的 flow 集合应能完整覆盖查询场景的处理路径

### 3. 未匹配时动态生成

如果现有 flow 无法覆盖查询场景，分析以下文件生成新的 atomic flow：
- `skills/cinnox-demo/SKILL.md` — 销售流程
- `skills/customer-service/SKILL.md` — 客服流程
- `feishu/channel-instructions.md` — 路由规则
- `.autoservice/rules/` — 行为规则

**生成要求：**
- 每个 flow 遵循 atomic flow 原则：3-8 节点，1 个决策点
- 必须包含所有 required fields: `id`, `name`, `description`, `tags`, `entry`, `exits`, `nodes`, `edges`
- 保存到 `.autoservice/flows/{id}.yaml`
- 更新 `_index.yaml` 添加新 flow 条目

### 4. 渲染 HTML

读取匹配/生成的所有 flow YAML 文件，转为 JSON 数组。

读取模板和 dagre：
```bash
cat skills/explain/templates/explain.html
cat skills/explain/templates/dagre.min.js
```

替换模板中的占位符：
- `{{FLOW_DATA}}` → JSON 数组（所有相关 flow）
- `{{QUERY}}` → 用户的原始查询
- `{{GENERATED_AT}}` → 当前 ISO 时间戳
- `{{DAGRE_JS}}` → dagre.min.js 的完整内容

### 5. 保存并回复

```bash
mkdir -p .autoservice/explain
```

将渲染后的 HTML 保存到 `.autoservice/explain/{id}.html`，其中 `{id}` 为基于查询的 slug（如 `did-pricing-flow`）。

读取 base_url：
```bash
cat .autoservice/config.yaml
```

使用 `reply` 工具回复到 `admin_chat_id`（从 channel 消息 meta 中获取）：

```
reply(chat_id=meta.admin_chat_id, text="🔍 流程分析完成\n{base_url}/explain/{id}.html")
```

**注意：reply 的 chat_id 必须是 meta 中的 `admin_chat_id`，不是 `chat_id`（后者是合成的 `admin_explain`）。**

## 循环引用处理

展开 `next_flow` 时：
- 最大深度 3 层
- 维护 visited set，已访问的 flow 不再展开
- 自引用的 flow 在 FLOW_DATA 中标记 `"self_ref": true`，模板渲染为回环箭头
```

### Step 2: Symlink into .claude/skills

```bash
ln -sfn ../../skills/explain .claude/skills/explain 2>/dev/null || true
```

Or run `make setup` which handles all skill symlinks.

### Step 3: Commit

```bash
git add skills/explain/SKILL.md
git commit -m "feat: explain skill — flow analysis and visualization"
```

---

## Task 9: Seed Flows from cinnox-demo

**Files:**
- Create: `.autoservice/flows/new-customer-lead.yaml`
- Create: `.autoservice/flows/existing-customer-verify.yaml`
- Create: `.autoservice/flows/kb-query-routing.yaml`
- Create: `.autoservice/flows/subagent-orchestration.yaml`
- Create: `.autoservice/flows/escalation.yaml`
- Modify: `.autoservice/flows/_index.yaml`

### Step 1: Create seed flows

Extract atomic flows from `skills/cinnox-demo/SKILL.md` following the granularity rules. Each flow has 1 decision point, 3-8 nodes.

**`new-customer-lead.yaml`** — Lead collection gate:
- Entry: receive_info → has_all_fields? → (yes: confirm → save → exit:resolve) / (no: ask_missing → loop)

**`existing-customer-verify.yaml`** — Identity verification:
- Entry: ask_identity → has_all_4_fields? → (yes: save → route_inquiry) / (no: ask_missing → loop)

**`kb-query-routing.yaml`** — Knowledge base query routing:
- Entry: run_route_query → check_domain → (contact_center: exit:product-query) / (global_telecom: exit:region-query) / (ambiguous: clarify → loop)

**`subagent-orchestration.yaml`** — Subagent pipeline:
- Entry: kb_subagent → draft_response → copywriting → reviewer → (passed: exit:resolve) / (failed: fix → re-review)

**`escalation.yaml`** — Escalation to human:
- Entry: check_trigger → (billing/complaint/kb_empty/explicit: propose_escalation → confirmed? → trigger_handoff) / (no trigger: exit:resolve)

### Step 2: Update `_index.yaml` with all seed flows

```yaml
flows:
  - id: identify-customer-type
    name: 识别客户类型
    tags: [customer, identification, gate]
    triggers: ["客户类型", "新客户还是老客户", "识别", "判断用户"]

  - id: new-customer-lead
    name: 新客户信息收集
    tags: [customer, lead, collection, gate]
    triggers: ["收集信息", "lead", "姓名", "公司", "邮箱", "电话"]

  - id: existing-customer-verify
    name: 老客户身份验证
    tags: [customer, existing, verification, gate]
    triggers: ["验证身份", "老客户", "账户", "account ID"]

  - id: kb-query-routing
    name: 知识库查询路由
    tags: [kb, query, routing, domain]
    triggers: ["产品问题", "价格", "DID", "功能", "知识库", "查询"]

  - id: subagent-orchestration
    name: 子代理编排
    tags: [subagent, pipeline, kb, copywriting, review]
    triggers: ["子代理", "产品查询", "回答", "KB搜索", "copywriting"]

  - id: escalation
    name: 转接人工
    tags: [escalation, human, transfer, handoff]
    triggers: ["转接", "人工", "投诉", "billing", "技术故障", "转人工"]
```

### Step 3: Commit

```bash
git add .autoservice/flows/
git commit -m "feat: seed 6 atomic flows from cinnox-demo skill"
```

---

## Task 10: Integration Test

**Files:**
- Create: `tests/test_explain_command.py`

### Step 1: Write integration tests

```python
"""Tests for /explain command pipeline."""
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from feishu.channel_server import ChannelServer


@pytest.fixture
def server():
    """Create a ChannelServer with Feishu disabled."""
    return ChannelServer(
        port=0,
        feishu_enabled=False,
        admin_chat_id="oc_admin_test",
    )


class TestExplainCommand:
    """Test /explain admin command in channel-server."""

    @pytest.mark.asyncio
    async def test_explain_no_query_returns_usage(self, server):
        """'/explain' with no query should reply with usage."""
        server._reply_feishu = AsyncMock()
        msg = {"chat_id": "oc_admin_test", "text": "/explain"}
        await server._handle_admin_message(msg)
        server._reply_feishu.assert_called_once()
        reply_text = server._reply_feishu.call_args[0][1]
        assert "Usage" in reply_text

    @pytest.mark.asyncio
    async def test_explain_routes_to_wildcard(self, server):
        """'/explain <query>' should route message with runtime_mode=explain."""
        server._reply_feishu = AsyncMock()
        server.route_message = AsyncMock()
        msg = {"chat_id": "oc_admin_test", "text": "/explain 用户问DID价格"}
        await server._handle_admin_message(msg)

        # Should reply with "analyzing" first
        assert server._reply_feishu.call_count == 1
        assert "正在分析" in server._reply_feishu.call_args[0][1]

        # Should route to wildcard via admin_explain
        server.route_message.assert_called_once()
        call_args = server.route_message.call_args
        assert call_args[0][0] == "admin_explain"
        routed_msg = call_args[0][1]
        assert routed_msg["runtime_mode"] == "explain"
        assert routed_msg["text"] == "用户问DID价格"
        assert routed_msg["admin_chat_id"] == "oc_admin_test"

    @pytest.mark.asyncio
    async def test_help_includes_explain(self, server):
        """/help should list the /explain command."""
        text = server.help_text()
        assert "/explain" in text


class TestFlowYAML:
    """Test flow YAML structure validity."""

    def test_index_has_all_flows(self):
        """_index.yaml should reference all flow files."""
        import yaml
        flows_dir = Path(__file__).parent.parent / ".autoservice" / "flows"
        if not flows_dir.exists():
            pytest.skip("flows/ not yet created")

        index = yaml.safe_load((flows_dir / "_index.yaml").read_text())
        indexed_ids = {f["id"] for f in index["flows"]}

        flow_files = [
            f.stem for f in flows_dir.glob("*.yaml")
            if f.name != "_index.yaml"
        ]
        for fid in flow_files:
            assert fid in indexed_ids, f"Flow file {fid}.yaml not in _index.yaml"

    def test_flow_has_required_fields(self):
        """Each flow YAML must have all required fields."""
        import yaml
        flows_dir = Path(__file__).parent.parent / ".autoservice" / "flows"
        if not flows_dir.exists():
            pytest.skip("flows/ not yet created")

        required = {"id", "name", "description", "tags", "entry", "exits", "nodes", "edges"}
        for f in flows_dir.glob("*.yaml"):
            if f.name == "_index.yaml":
                continue
            flow = yaml.safe_load(f.read_text())
            missing = required - set(flow.keys())
            assert not missing, f"{f.name} missing fields: {missing}"

    def test_flow_entry_node_exists(self):
        """The entry node must exist in the nodes list."""
        import yaml
        flows_dir = Path(__file__).parent.parent / ".autoservice" / "flows"
        if not flows_dir.exists():
            pytest.skip("flows/ not yet created")

        for f in flows_dir.glob("*.yaml"):
            if f.name == "_index.yaml":
                continue
            flow = yaml.safe_load(f.read_text())
            node_ids = {n["id"] for n in flow["nodes"]}
            assert flow["entry"] in node_ids, f"{f.name}: entry '{flow['entry']}' not in nodes"


class TestExplainRoute:
    """Test web/app.py /explain route."""

    @pytest.mark.asyncio
    async def test_explain_serves_existing_file(self):
        """GET /explain/test.html should serve from .autoservice/explain/."""
        from fastapi.testclient import TestClient
        from web.app import app

        # Create a test explain file
        explain_dir = Path(__file__).parent.parent / ".autoservice" / "explain"
        explain_dir.mkdir(parents=True, exist_ok=True)
        test_file = explain_dir / "test-flow.html"
        test_file.write_text("<html><body>test</body></html>")

        try:
            client = TestClient(app)
            resp = client.get("/explain/test-flow.html")
            assert resp.status_code == 200
            assert "test" in resp.text
        finally:
            test_file.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_explain_404_for_missing(self):
        """GET /explain/nonexistent.html should return 404."""
        from fastapi.testclient import TestClient
        from web.app import app

        client = TestClient(app)
        resp = client.get("/explain/nonexistent.html")
        assert resp.status_code == 404
```

### Step 2: Run tests

```bash
uv run pytest tests/test_explain_command.py -v
```

Expected: All tests pass.

### Step 3: Commit

```bash
git add tests/test_explain_command.py
git commit -m "test: explain command integration tests"
```

---

## Task Summary

| Task | Component | Files |
|------|-----------|-------|
| 1 | Config & flows infrastructure | `.autoservice/config.yaml`, `.autoservice/flows/`, `.gitignore` |
| 2 | channel-server `/explain` command | `feishu/channel_server.py` |
| 3 | channel-instructions routing | `feishu/channel-instructions.md` |
| 4 | channel.py admin_chat_id passthrough | `feishu/channel.py` |
| 5 | web/app.py `/explain/` route | `web/app.py` |
| 6 | Vendor dagre.min.js | `skills/explain/templates/dagre.min.js` |
| 7 | HTML template | `skills/explain/templates/explain.html` |
| 8 | Explain skill SKILL.md | `skills/explain/SKILL.md` |
| 9 | Seed flows from cinnox-demo | `.autoservice/flows/*.yaml` |
| 10 | Integration tests | `tests/test_explain_command.py` |

**Dependency order:** Tasks 1-5 can be done in any order. Task 6 must precede Task 7. Task 7 must precede Task 8. Task 9 should follow Task 1. Task 10 should be last.
