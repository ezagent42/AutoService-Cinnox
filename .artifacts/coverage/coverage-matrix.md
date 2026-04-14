---
type: coverage-matrix
id: coverage-matrix-001
status: draft
producer: skill-0
created_at: "2026-04-10"
---

# Coverage Matrix: AutoService

## 概览

| 指标 | 值 |
|------|-----|
| 总模块数 | 5 (autoservice, feishu, web, plugins, tests) |
| 代码测试覆盖模块 | 3/4 (feishu ✅, web ✅, autoservice/explain ✅, plugins ❌) |
| 操作 E2E 覆盖流程 | 2/8 |
| 环境受限测试 | 0 (所有测试可正常执行) |

## 代码测试覆盖

| 模块 | 测试文件 | 测试命令 | 结果 | 覆盖状态 |
|------|---------|---------|------|---------|
| feishu/channel.py (ChannelClient) | tests/test_channel_client.py | uv run pytest tests/test_channel_client.py -v | 1/1 passed | ✅ covered |
| feishu/channel_server.py | tests/test_channel_server.py | uv run pytest tests/test_channel_server.py -v | 6/6 passed | ✅ covered |
| web/websocket.py (WebChannelBridge) | tests/test_web_relay.py | uv run pytest tests/test_web_relay.py -v | 2/2 passed | ✅ covered |
| web/app.py (explain route) | tests/test_explain_command.py | uv run pytest tests/test_explain_command.py -v | 5/5 passed, 4 skipped | ✅ partial |
| autoservice/ (core library) | (无测试文件) | - | - | ❌ no tests |
| plugins/ | (无测试文件) | - | - | ❌ no tests |

## 操作 E2E 覆盖

| 用户流程 | E2E 测试 | 证据类型 | 覆盖状态 |
|---------|---------|---------|---------|
| Feishu IM 消息收发 (mock) | tests/e2e/test_feishu_mock.py | script output | ✅ covered |
| Web chat 端到端对话 | tests/e2e/test_web_chat.sh | curl + assertion | ✅ covered |
| 插件加载和工具注册 | (无) | - | ❌ not covered |
| 客户记录 CRUD | (无) | - | ❌ not covered |
| 权限检查流程 | (无) | - | ❌ not covered |
| CRM 联系人追踪 | (无) | - | ❌ not covered |
| 会话生命周期管理 | (无) | - | ❌ not covered |
| 文件导入 (DOCX/XLSX/PDF) | (无) | - | ❌ not covered |

## 环境受限覆盖

| 测试 | 所需环境 | 状态 | 说明 |
|------|---------|------|------|
| (无环境受限测试) | - | - | 所有测试均可在当前环境正常执行 |

**注意**：4 个 skipped 测试 (TestFlowYAML) 是代码层面的 `pytest.skip("flows/ not yet created")`，不是环境问题。这些测试在 `flows/` 目录创建后会自动启用。

## E2E 缺口清单

1. **插件加载和工具注册**：验证 `discover()` 加载插件、注册 MCP 工具、挂载 HTTP 路由
2. **客户记录 CRUD**：通过 API 创建/查询/更新/删除客户记录
3. **权限检查流程**：模拟不同权限级别的操作请求，验证审批流程
4. **CRM 联系人追踪**：Feishu 消息触发联系人创建、消息计数递增
5. **会话生命周期管理**：init_session → 对话 → save_session 完整流程
6. **文件导入**：DOCX/XLSX/PDF 文件导入为结构化数据
