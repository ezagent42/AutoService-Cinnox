---
name: improve
description: AutoService 改进模式 — 对话审查、规则管理、数据运维
---

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

**读取方式：**
```bash
uv run python3 -c "
from autoservice.crm import get_contact_history, list_contacts, search_contacts
# 查看特定用户对话
history = get_contact_history('open_id_here', limit=50)
# 列出所有联系人
contacts = list_contacts()
# 搜索联系人
results = search_contacts('林大猫')
"
```

### 2. 行为规则管理

三层规则的增删改查。

#### Layer 1 — 通用规则（.autoservice/rules/*.yaml）

稳定的基础行为准则，始终对 Claude 可见。

```bash
# 列出所有通用规则
uv run python3 -c "from autoservice.rules import load_rules; import json; print(json.dumps(load_rules(), indent=2, ensure_ascii=False))"

# 添加通用规则
uv run python3 -c "from autoservice.rules import add_rule; add_rule('pricing', '报价前先检查 KB price 资料', created_by='allen')"

# 删除通用规则
uv run python3 -c "from autoservice.rules import delete_rule; delete_rule(1)"

# 格式化为 prompt 文本
uv run python3 -c "from autoservice.rules import format_rules_for_prompt; print(format_rules_for_prompt())"
```

#### Layer 2 — 客户规则（crm.db, scope: global/region/customer）

动态的运营规则，识别客户后加载。

```bash
# 添加客户规则
uv run python3 -c "from autoservice.crm import add_rule; add_rule('region', '优先推荐 toll-free 号码', scope_value='US', context='pricing', created_by='allen')"

# 添加特定客户规则
uv run python3 -c "from autoservice.crm import add_rule; add_rule('customer', 'VIP客户需详细回复', scope_value='ou_xxx', created_by='allen')"

# 查询某客户适用的所有规则
uv run python3 -c "from autoservice.crm import get_rules_for_customer; import json; print(json.dumps(get_rules_for_customer('ou_xxx', region='US'), indent=2, ensure_ascii=False))"

# 列出所有规则
uv run python3 -c "from autoservice.crm import list_rules; import json; print(json.dumps(list_rules(), indent=2, ensure_ascii=False))"

# 删除规则
uv run python3 -c "from autoservice.crm import delete_rule; delete_rule(1)"
```

#### Layer 3 — 业务私有规则（crm.db, scope: business）

场景触发的业务规则，按需加载。

```bash
# 添加业务规则
uv run python3 -c "from autoservice.crm import add_rule; add_rule('business', '报价时不主动提 volume discount', context='pricing', created_by='allen')"
```

### 3. 数据管理

- **导入 KB 数据**：使用 /knowledge-base skill 的 `kb build` 命令
- **更新 CRM 联系人**：
```bash
uv run python3 -c "from autoservice.crm import upsert_contact; upsert_contact('ou_xxx', company='NewCorp')"
```
- **查看系统状态**：
```bash
# KB chunks 数
uv run python3 -c "import sqlite3; db=sqlite3.connect('.autoservice/database/knowledge_base/kb.db'); print(f'KB chunks: {db.execute(\"SELECT COUNT(*) FROM kb_chunks\").fetchone()[0]}')"
# CRM contacts 数
uv run python3 -c "from autoservice.crm import list_contacts; print(f'Contacts: {len(list_contacts())}')"
# Rules 数
uv run python3 -c "from autoservice.crm import list_rules; from autoservice.rules import load_rules; print(f'Layer 1: {len(load_rules())}, Layer 2+3: {len(list_rules())}')"
```

### 4. 自动分析

当用户要求"分析最近 N 条对话"时：

1. 从 CRM 检索最近 N 条对话（含 in/out）
2. 逐条分析：
   - 回答是否准确（与 KB 数据一致？）
   - 是否遵守已有规则？
   - 是否有更好的回应方式？
   - 是否错过了推销/升级机会？
3. 生成改进建议列表
4. 对每条建议，提议转为具体规则（指定 Layer 和 scope）
5. 用户确认后写入对应存储

## 注意事项

- 修改规则后，告知用户规则将在下次 service 模式对话中生效
- 分析对话时，保持客观，引用具体对话内容作为依据
- 不要自动修改 SKILL.md 文件，除非用户明确要求
- Layer 1 (YAML) 用于少量稳定的基础准则；Layer 2 global 用于频繁调整的运营规则
