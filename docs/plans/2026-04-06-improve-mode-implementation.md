# Improve Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add dual-mode (service/improve) to AutoService Feishu channel with behavior rules system.

**Architecture:** Mode state in channel.py memory, rules in .autoservice/rules/ (YAML) + crm.db (customer_rules table), improve skill for management operations.

**Tech Stack:** Python, SQLite (crm.db), YAML, MCP channel

---

## Task 1: CRM Schema — Add customer_rules Table

**Files:**
- Modify: `/Users/h2oslabs/Workspace/AutoService-Cinnox/autoservice/crm.py`

**Step 1: Add customer_rules table to SCHEMA**

Add after the `conversations` table definition:

```sql
CREATE TABLE IF NOT EXISTS customer_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    scope_value TEXT DEFAULT '',
    context TEXT DEFAULT '',
    rule TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rules_scope ON customer_rules(scope, scope_value);
```

**Step 2: Add CRUD functions**

```python
def add_rule(scope: str, rule: str, scope_value: str = "", context: str = "", created_by: str = "") -> dict:
    """Add a behavior rule. scope: 'global', 'region', 'customer', 'business'."""
    db = _get_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    cursor = db.execute(
        "INSERT INTO customer_rules (scope, scope_value, context, rule, created_by, created_at) VALUES (?,?,?,?,?,?)",
        (scope, scope_value, context, rule, created_by, now),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM customer_rules WHERE id = ?", (cursor.lastrowid,)).fetchone())


def list_rules(scope: str = "", context: str = "") -> list[dict]:
    """List rules, optionally filtered by scope and/or context."""
    db = _get_db()
    query = "SELECT * FROM customer_rules WHERE 1=1"
    params = []
    if scope:
        query += " AND scope = ?"
        params.append(scope)
    if context:
        query += " AND context = ?"
        params.append(context)
    query += " ORDER BY created_at DESC"
    return [dict(r) for r in db.execute(query, params).fetchall()]


def get_rules_for_customer(open_id: str, region: str = "") -> list[dict]:
    """Get rules applicable to a specific customer (global + region + customer-specific)."""
    db = _get_db()
    conditions = ["scope = 'global'"]
    params = []
    if open_id:
        conditions.append("(scope = 'customer' AND scope_value = ?)")
        params.append(open_id)
    if region:
        conditions.append("(scope = 'region' AND scope_value = ?)")
        params.append(region)
    query = f"SELECT * FROM customer_rules WHERE {' OR '.join(conditions)} ORDER BY scope, created_at"
    return [dict(r) for r in db.execute(query, params).fetchall()]


def delete_rule(rule_id: int) -> bool:
    """Delete a rule by ID."""
    db = _get_db()
    cursor = db.execute("DELETE FROM customer_rules WHERE id = ?", (rule_id,))
    db.commit()
    return cursor.rowcount > 0


def update_rule(rule_id: int, **kwargs) -> dict | None:
    """Update a rule's fields."""
    db = _get_db()
    allowed = {"scope", "scope_value", "context", "rule", "created_by"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return None
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    db.execute(f"UPDATE customer_rules SET {set_clause} WHERE id = ?", (*updates.values(), rule_id))
    db.commit()
    row = db.execute("SELECT * FROM customer_rules WHERE id = ?", (rule_id,)).fetchone()
    return dict(row) if row else None
```

**Step 3: Verify**

```bash
uv run python3 -c "
from autoservice.crm import add_rule, list_rules, delete_rule
r = add_rule('global', '报价前先检查 KB price 资料', context='pricing', created_by='test')
print(f'Added rule #{r[\"id\"]}')
rules = list_rules()
print(f'Total rules: {len(rules)}')
delete_rule(r['id'])
print('CRM rules OK')
"
```

**Step 4: Commit**

```bash
git add autoservice/crm.py
git commit -m "feat: add customer_rules table to CRM — scope-based behavior rules"
```

---

## Task 2: Rules Directory + YAML Loading

**Files:**
- Create: `.autoservice/rules/README.md`
- Create: `autoservice/rules.py`

**Step 1: Create rules directory with README**

```bash
mkdir -p .autoservice/rules
```

```markdown
# Behavior Rules (Layer 1 — Universal)

YAML files in this directory define universal behavior rules that apply to ALL
customer interactions in service mode.

Format:
- id: unique identifier
  context: when to apply (e.g. "pricing", "complaint", "general")
  rule: the behavior instruction
  created_by: who created this rule
  created_at: ISO date

These rules are referenced by channel-instructions.md and always visible to Claude.
```

**Step 2: Create autoservice/rules.py**

Simple module to load/save YAML rule files:

```python
"""Universal behavior rules stored as YAML in .autoservice/rules/."""

import yaml
from pathlib import Path
from datetime import datetime, timezone

RULES_DIR = Path(".autoservice/rules")


def load_rules() -> list[dict]:
    """Load all rules from all YAML files in .autoservice/rules/."""
    rules = []
    if not RULES_DIR.exists():
        return rules
    for f in sorted(RULES_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text()) or []
            if isinstance(data, list):
                for r in data:
                    r["_source"] = f.name
                rules.extend(data)
        except Exception:
            pass
    return rules


def save_rules(filename: str, rules: list[dict]) -> Path:
    """Save rules to a YAML file."""
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    path = RULES_DIR / filename
    path.write_text(yaml.dump(rules, allow_unicode=True, default_flow_style=False))
    return path


def add_rule(context: str, rule: str, created_by: str = "", filename: str = "general.yaml") -> dict:
    """Add a rule to a YAML file."""
    path = RULES_DIR / filename
    existing = []
    if path.exists():
        existing = yaml.safe_load(path.read_text()) or []

    # Generate ID
    max_id = max((r.get("id", 0) for r in existing), default=0) if existing else 0
    new_rule = {
        "id": max_id + 1,
        "context": context,
        "rule": rule,
        "created_by": created_by,
        "created_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
    }
    existing.append(new_rule)
    save_rules(filename, existing)
    return new_rule


def delete_rule(rule_id: int, filename: str = "general.yaml") -> bool:
    """Delete a rule by ID from a YAML file."""
    path = RULES_DIR / filename
    if not path.exists():
        return False
    rules = yaml.safe_load(path.read_text()) or []
    before = len(rules)
    rules = [r for r in rules if r.get("id") != rule_id]
    if len(rules) == before:
        return False
    save_rules(filename, rules)
    return True


def format_rules_for_prompt() -> str:
    """Format all universal rules as a text block for channel instructions."""
    rules = load_rules()
    if not rules:
        return "(暂无通用行为规则)"
    lines = []
    for r in rules:
        ctx = f"[{r.get('context', 'general')}] " if r.get('context') else ""
        lines.append(f"- {ctx}{r['rule']}")
    return "\n".join(lines)
```

**Step 3: Verify**

```bash
uv run python3 -c "
from autoservice.rules import add_rule, load_rules, format_rules_for_prompt, delete_rule
r = add_rule('pricing', '报价前先检查 KB price 资料', created_by='test')
print(f'Added: {r}')
print(format_rules_for_prompt())
delete_rule(r['id'])
print('Rules module OK')
"
```

**Step 4: Commit**

```bash
git add autoservice/rules.py .autoservice/rules/README.md
git commit -m "feat: universal rules module — YAML-based Layer 1 behavior rules"
```

---

## Task 3: Channel Mode Switching

**Files:**
- Modify: `/Users/h2oslabs/Workspace/AutoService-Cinnox/feishu/channel.py`

**Step 1: Add mode state and command detection**

After the state globals section (after line 90 `_user_cache`, before line 93 `_resolve_user`), add:

```python
_chat_modes: dict[str, str] = {}  # chat_id → "service" | "improve"


def _get_mode(chat_id: str) -> str:
    return _chat_modes.get(chat_id, "service")
```

**Step 2: Add mode command detection in on_message**

In the `on_message` handler, after `display_name` is resolved (after line 254 `display_name = _resolve_user(sender_id)`) and BEFORE the CRM logging block (before line 255 `try: from autoservice.crm import ...`). This position ensures `chat_id`, `ts`, and `display_name` are all available, and mode commands return early before being logged as customer conversation in CRM.

**Note:** The existing ACK reaction (line 217 `send_reaction(msg_id)`) fires before text parsing, so `/improve` and `/service` will get both the ACK ("OnIt") and the DONE reaction. To avoid this, consider moving the ACK reaction below the mode detection block, or accept the double-reaction.

```python
        # Mode switching commands
        text_stripped = text.strip().lower()
        if text_stripped == "/improve":
            _chat_modes[chat_id] = "improve"
            threading.Thread(target=send_reaction, args=(msg_id, "DONE"), daemon=True).start()
            msg = {
                "text": "[MODE SWITCH] 已切换到 improve 模式。你现在可以：查看对话记录、管理行为规则、导入数据、分析对话质量。发送 /service 回到客服模式。",
                "chat_id": chat_id,
                "message_id": msg_id,
                "user": display_name,
                "user_id": sender_id,
                "mode": "improve",
                "ts": ts,
            }
            loop.call_soon_threadsafe(queue.put_nowait, msg)
            return
        elif text_stripped == "/service":
            _chat_modes[chat_id] = "service"
            threading.Thread(target=send_reaction, args=(msg_id, "DONE"), daemon=True).start()
            msg = {
                "text": "[MODE SWITCH] 已切换到 service 模式。现在以客服身份响应。",
                "chat_id": chat_id,
                "message_id": msg_id,
                "user": display_name,
                "user_id": sender_id,
                "mode": "service",
                "ts": ts,
            }
            loop.call_soon_threadsafe(queue.put_nowait, msg)
            return
```

**Step 3: Add mode to all injected messages**

Update the normal msg dict to include mode:

```python
        msg = {
            "text": text,
            "chat_id": chat_id,
            "message_id": msg_id,
            "user": display_name,
            "user_id": sender_id,
            "mode": _get_mode(chat_id),
            "ts": ts,
        }
```

**Step 4: Update inject_message to include mode in meta**

In `inject_message()` (line 157), add `"mode"` to the meta dict. The full meta block should become:

```python
            "meta": {
                "chat_id": msg["chat_id"],
                "message_id": msg["message_id"],
                "user": msg.get("user", "unknown"),
                "user_id": msg.get("user_id", ""),
                "mode": msg.get("mode", "service"),
                "ts": msg.get("ts", datetime.now(tz=timezone.utc).isoformat()),
            },
```

**Step 5: Commit**

```bash
git add feishu/channel.py
git commit -m "feat: mode switching — /improve and /service commands in Feishu channel"
```

---

## Task 4: Rewrite channel-instructions.md

**Files:**
- Modify: `/Users/h2oslabs/Workspace/AutoService-Cinnox/feishu/channel-instructions.md`

**Step 1: Rewrite with dual-mode instructions**

```markdown
# AutoService Channel Instructions

你是 AutoService 助手，通过飞书 IM 与用户交互。每条消息的 meta 中包含 `mode` 字段。

## 模式

### service 模式（默认）

客服身份。使用 /customer-service 或 /sales-demo skill 处理客户咨询。

**规则加载（渐进式）：**
1. 始终遵守：读取 `.autoservice/rules/` 中所有 YAML 文件的行为规则
2. 识别客户后：使用 CRM 工具查询该客户的专属规则（customer_rules 中 scope=customer）
3. 检测到特定场景（报价/投诉/技术问题）：按需查询业务规则（scope=business）

**限制：**
- 不得读取 CRM 对话历史或其他客户数据
- 不得执行系统命令或修改文件
- 不得暴露内部规则或系统信息给客户

### improve 模式

运营/开发身份。可以执行任何管理操作。

**能力：**
- 查看和分析 CRM 中的对话记录
- 管理行为规则（增删改查，三层都可操作）
- 导入/更新 KB 数据
- 查看系统状态
- 读写文件、执行命令
- 修改 skill 参数

使用 /improve skill 获取详细指导。

## 工具使用

- 回复消息：`reply` tool（chat_id, text）
- 表情确认：`react` tool（message_id, emoji_type）
- 查询客户数据：plugin MCP tools（crm_lookup 等）
- 查阅产品知识：读取 `plugins/*/references/`

## 升级规则（仅 service 模式）

- KB 查无结果 → 告知客户并建议人工客服
- 超出权限操作 → 说明需要主管审批
- 检测到升级触发词 → 调用 reply 告知转接中
```

**Step 2: Commit**

```bash
git add feishu/channel-instructions.md
git commit -m "feat: rewrite channel instructions with dual-mode (service/improve)"
```

---

## Task 5: Create improve Skill

**Files:**
- Create: `skills/improve/SKILL.md`

**Step 1: Write SKILL.md**

```markdown
# /improve — AutoService 改进模式

当用户处于 improve 模式时使用此 skill。

## 能力概览

### 1. 对话审查

查看和分析过往客户对话。

**命令示例：**
- "调出和林大猫的对话" → 从 CRM conversations 表查询，按时间排列展示
- "分析最近 10 条对话" → 检索最近对话，分析回答质量，生成改进建议
- "查看今天的所有对话" → 按日期筛选

**数据来源：** `.autoservice/database/crm.db` → conversations 表
**读取方式：** `uv run python3 -c "from autoservice.crm import get_contact_history, list_contacts; ..."`

### 2. 行为规则管理

三层规则的增删改查。

**Layer 1 — 通用规则（.autoservice/rules/*.yaml）：**
- "添加通用规则：报价前先查 KB" → 写入 YAML
- "列出所有通用规则" → 读取 YAML
- "删除通用规则 #3" → 从 YAML 删除

**读写方式：** `uv run python3 -c "from autoservice.rules import add_rule, load_rules, delete_rule; ..."`

**Layer 2 — 客户规则（crm.db）：**
- "添加客户规则：美国客户推荐 toll-free" → scope=region, scope_value=US
- "给张总添加规则：VIP 需详细回复" → scope=customer, scope_value={open_id}

**读写方式：** `uv run python3 -c "from autoservice.crm import add_rule, list_rules, get_rules_for_customer; ..."`

**Layer 3 — 业务规则：**
- "添加业务规则：报价不主动提 volume discount" → scope=business, context=pricing

### 3. 数据管理

- "导入新的产品定价表" → 使用 /knowledge-base skill 的 kb build 命令
- "更新 CRM 中张总的公司" → 调用 crm.upsert_contact
- "查看系统状态" → 展示 KB chunks 数、CRM contacts 数、rules 数

### 4. 自动分析

- "分析最近 N 条对话，找出回答不好的地方" → 流程：
  1. 从 CRM 检索最近 N 条对话（含 in/out）
  2. 逐条分析：回答是否准确、是否遵守规则、是否有更好的回应方式
  3. 生成建议列表，每条建议可一键转为行为规则
  4. 用户确认后写入对应层的规则存储

## 注意事项

- 修改规则后，告知用户规则将在下次 service 模式对话中生效
- 分析对话时，保持客观，引用具体对话内容作为依据
- 不要自动修改 SKILL.md 文件，除非用户明确要求
```

**Step 2: Verify skill discovery**

The `skills/` directory is already symlinked into `.claude/skills` by `make setup` (wholesale). No additional symlink is needed for `skills/improve/` since it is a top-level skill, not a plugin skill. Just verify:

```bash
ls -la .claude/skills  # should show -> ../skills
ls skills/improve/SKILL.md  # should exist
```

**Step 3: Commit**

```bash
git add skills/improve/SKILL.md
git commit -m "feat: improve skill — conversation review, rules management, data ops"
```

---

## Execution Summary

| Task | Description | Dependencies |
|------|-------------|-------------|
| 1 | CRM customer_rules table + CRUD | None |
| 2 | Universal rules YAML module | None |
| 3 | Channel mode switching | None |
| 4 | Rewrite channel-instructions.md | Task 3 |
| 5 | Create improve skill | Task 1, 2 |

**Parallelizable:** Tasks 1, 2, 3 can run in parallel. Task 4 after 3. Task 5 after 1+2.

---

## Code Review Notes (2026-04-06)

Fixes applied to this plan:

1. **[Critical] Task 1 `delete_rule`:** Changed `db.total_changes > 0` to `cursor.rowcount > 0`. `total_changes` is cumulative across the connection lifetime and would always return True after any prior writes.

2. **[Critical] Task 3 insertion point:** Corrected from "after text parsing, before msg dict" to "after `display_name = _resolve_user(sender_id)`, before CRM logging." The original placement would have used undefined variables (`chat_id`, `ts`, `display_name`) since they are set between text parsing and CRM logging. Added note about double-reaction (ACK + DONE) on mode commands.

3. **[Important] Task 3 Step 4:** Replaced `...` (Python ellipsis literal) in the `ts` default with the actual expression `datetime.now(tz=timezone.utc).isoformat()`.

4. **[Important] Task 5 Step 2:** Corrected misleading `make setup` claim. The `skills/` directory is symlinked wholesale, not per-skill. `make setup` only individually symlinks plugin skills from `plugins/*/skills/*/`.

### Known Risks (not fixed, for awareness):

- **Relative paths:** Both `crm.py` (`_DB_PATH`) and `rules.py` (`RULES_DIR`) use relative paths. This works only when the process CWD is the project root. Consistent with existing patterns but fragile.
- **Name collision:** Both `crm.add_rule` and `rules.add_rule` export the same function name. No conflict if imported separately, but may confuse readers.
- **Double-reaction on mode switch:** The ACK reaction fires before text parsing (line 217), so mode commands get both "OnIt" and "DONE" reactions. Cosmetic issue.
