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
- 节点类型限定: `process`, `decision`, `action`, `exit`
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

## Flow YAML 格式参考

```yaml
id: example-flow
name: 示例流程
description: 描述
tags: [tag1, tag2]

entry: first_node
exits:
  - node: end_node
    type: resolve  # or handoff
    next_flow: other-flow-id  # only for handoff type

nodes:
  - id: first_node
    label: 显示名称
    type: process  # process | decision | action | exit
    note: 可选说明文字

edges:
  - from: first_node
    to: end_node
    label: 可选边标签
```
