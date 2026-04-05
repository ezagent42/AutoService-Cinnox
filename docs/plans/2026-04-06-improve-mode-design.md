# Improve Mode — 双模式飞书通道设计

**Date:** 2026-04-06
**Status:** Approved
**Authors:** Allen Woods + Claude

## 1. Overview

为 AutoService 飞书通道添加双模式：**service**（客服，默认）和 **improve**（改进）。通过 `/improve` 和 `/service` 命令切换。Improve 模式下可读写数据、审查对话、管理行为规则；service 模式下只面向客户交互。

## 2. Mode Switching

```
用户发送 /improve → 进入 improve 模式（当前会话持久）
用户发送 /service → 回到 service 模式
```

- 模式状态存储在 channel.py 内存 dict，key 为 chat_id
- 默认所有会话为 service 模式
- 切换时 inject 模式变更通知给 Claude Code
- **注意：** 模式状态仅存于进程内存，channel.py 重启后所有会话回到 service 模式（可接受：improve 是短时运维操作）

## 3. Permission Model

| 能力 | service | improve |
|------|---------|---------|
| 产品咨询（KB 检索） | Y | Y |
| 收集 lead 信息 | Y | N |
| 读取 CRM 联系人/对话记录 | N | Y |
| 导入/更新 KB 数据 | N | Y |
| 查看并标注过往对话 | N | Y |
| 自动分析对话质量 | N | Y |
| 管理行为规则（增删改查） | N | Y |
| 修改 skill 参数/prompt | N | Y |
| 执行系统命令 | N | Y |
| 读写文件系统 | N | Y |

**Enforcement mechanism:** Permissions are enforced at the prompt level via
`channel-instructions.md`, not via code-level access control. Claude Code
receives `mode` in the message meta and follows the instructions for that mode.
This is a soft boundary — adequate for a single-operator system but not a
substitute for code-level ACL if multi-operator access is added later.

## 4. Behavior Rules — Three-Layer Storage

```
┌─────────────────────────────────────────────┐
│ Layer 1: 通用规则                            │
│ .autoservice/rules/*.yaml                   │
│ 例："报价前先检查 KB 中 price 相关资料"        │
│ 加载时机：始终（channel-instructions 引用）    │
├─────────────────────────────────────────────┤
│ Layer 2: 客户规则                            │
│ crm.db → customer_rules 表                  │
│ scope: 'global', 'region', 'customer'       │
│ 例："美国客户优先推荐 toll-free 号码"          │
│ 加载时机：识别客户身份后加载一次               │
├─────────────────────────────────────────────┤
│ Layer 3: 业务私有规则                        │
│ crm.db → customer_rules 表 (scope='business')│
│ 例："Cinnox 报价时不主动提 volume discount"   │
│ 加载时机：匹配到具体业务场景时按需加载          │
│ (注：plugins/{customer}/rules/ 路径保留为     │
│  未来扩展，v1 统一使用 crm.db)               │
└─────────────────────────────────────────────┘
```

### Rule Data Structure

```yaml
# .autoservice/rules/pricing.yaml (Layer 1)
- id: 1
  context: "报价场景"
  rule: "先检查 KB 中标记为 price 相关的资料再回答"
  created_by: "allen"
  created_at: "2026-04-06"
```

```sql
-- crm.db customer_rules 表 (Layer 2 & 3)
CREATE TABLE customer_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,        -- 'global', 'region', 'customer', 'business'
    scope_value TEXT DEFAULT '',-- e.g. 'US', 'ou_3ab76...', 'pricing'
    context TEXT DEFAULT '',    -- when to apply: 'pricing', 'complaint', 'general'
    rule TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rules_scope ON customer_rules(scope, scope_value);
```

**Layer 1 vs Layer 2 `scope='global'` 的区别：**
Layer 1 YAML 是文件级别的，随 channel-instructions 静态加载，Claude 始终可见。
Layer 2 中 `scope='global'` 的记录是动态查询的，在识别客户后通过
`get_rules_for_customer()` 加载。建议 Layer 1 用于基础行为准则（少量、稳定），
Layer 2 global 用于频繁调整的运营规则。

### Rule Loading Flow (service mode)

```
客户首条消息到达
  |
  v
1. channel-instructions 引用 .autoservice/rules/ --> 通用规则始终可见
  |
  v
2. 识别客户身份 --> 读取 CRM customer_rules (scope=global/customer/region) --> 注入会话
  |
  v
3. 检测到特定场景 --> 按需读取业务场景规则 (scope=business, context=<场景>)
```

**Trigger for step 2:** Claude Code 调用 CRM plugin tool (如 cinnox_customer_lookup)
识别到客户后，主动查询 `get_rules_for_customer(open_id, region)` 获取适用规则。
**Trigger for step 3:** Claude Code 根据对话上下文判断进入特定场景（报价/投诉/技术问题），
查询 `list_rules(scope='business', context=<场景>)` 获取业务规则。

## 5. Improve Mode Capabilities

### 对话审查（人工 + 自动）
- 调出指定用户的历史对话
- 自动分析最近 N 条对话的回答质量
- 标注问题并生成改进规则

### 规则管理
- CRUD 三层规则
- 按层/scope/context 筛选和展示
- 规则生效验证（模拟场景测试）

### 数据管理
- 导入/更新 KB 数据
- 更新 CRM 联系人信息
- 查看系统状态（KB chunks, CRM contacts, rules count）

## 6. Implementation Changes

| 组件 | 变更 |
|------|------|
| `feishu/channel.py` | `_chat_modes` dict，检测 `/improve`、`/service`，inject 附带 `mode` |
| `feishu/channel-instructions.md` | 重写：按 mode 分节，引用 rules/ |
| `autoservice/crm.py` | 添加 `customer_rules` 表 + CRUD |
| `autoservice/rules.py` | 新建模块：Layer 1 YAML 规则的加载/保存/格式化 |
| `.autoservice/rules/` | 新建目录 + 示例 YAML |
| `skills/improve/SKILL.md` | 新建 improve skill |

## 7. Non-Goals (YAGNI)

- 不做 RBAC 细粒度权限（权限通过 prompt-level instructions 软限制）
- 不做规则版本历史
- 不做自动规则推荐
- 不做 improve 模式的 Web 通道适配
- 不做 plugins/{customer}/rules/ 目录结构（v1 统一用 crm.db scope='business'）
