---
type: bootstrap-report
id: bootstrap-report-001
status: executed
producer: skill-0
created_at: "2026-04-10"
---

# Bootstrap Report: AutoService

## 环境问题与解决

- **python3 不可用 (Windows)**：`python3` 在 Windows 上指向 Microsoft Store 重定向器（exit code 49）。所有脚本改用 `python` 执行。这是 Windows 平台的已知问题。
- **shell 脚本兼容性**：skill-0 和 skill-6 的 shell 脚本中使用 `python3`，在 Windows 上需要直接用 Python 执行对应逻辑。已在 Skill 1 的 artifact 交互指令中标注此问题。
- **pytest 未全局安装**：全局 Python 3.11 没有 pytest。通过 `uv run pytest` 使用项目虚拟环境中的 pytest 9.0.3 解决。
- **测试端口 19997/19998**：测试文件引用了这两个端口，但测试自行创建 mock WebSocket server（soft dependency），无需外部服务。

## 测试执行结果

### 全量测试基线

```
命令：uv run pytest tests/ -v
结果：14 passed, 4 skipped in 2.89s
Exit code: 0
```

### 按文件统计

| 测试文件 | Passed | Skipped | Failed |
|---------|--------|---------|--------|
| tests/test_channel_client.py | 1 | 0 | 0 |
| tests/test_channel_server.py | 6 | 0 | 0 |
| tests/test_explain_command.py | 5 | 4 | 0 |
| tests/test_web_relay.py | 2 | 0 | 0 |

### Skipped 测试分析

4 个 skipped 测试均在 `tests/test_explain_command.py` 的 `TestFlowYAML` 类中：
- `test_index_has_all_flows` — skip reason: "flows/ not yet created"
- `test_flow_has_required_fields` — skip reason: "flows/ not yet created"
- `test_flow_entry_node_exists` — skip reason: "flows/ not yet created"
- `test_flow_edges_reference_valid_nodes` — skip reason: "flows/ not yet created"

**根因**：这些测试验证 `.autoservice/flows/` 目录下的 YAML 流程定义文件。该功能尚在开发中（explain 模式），`flows/` 目录未创建。这是**代码层面的 skip**（`pytest.skip()`），不是环境问题。当 `flows/` 目录和对应 YAML 文件创建后，这些测试会自动启用。

### E2E 测试

- `tests/e2e/test_feishu_mock.py` — Feishu mock 集成测试（未在基线中单独运行）
- `tests/e2e/test_web_chat.sh` — Web chat curl 测试（shell 脚本，需单独执行）

## 覆盖分析

### 覆盖矩阵摘要

- **代码测试覆盖**：3/4 代码模块有测试（feishu ✅, web ✅, autoservice/explain ✅, plugins ❌）
- **操作 E2E 覆盖**：2/8 用户流程有 E2E 测试
- **环境受限**：0 个测试因环境问题受限

### E2E 缺口

| 优先级 | 用户流程 | 原因 |
|--------|---------|------|
| P1 | 插件加载和工具注册 | 核心功能，直接影响所有通道 |
| P1 | 客户记录 CRUD | 核心数据流，无任何测试覆盖 |
| P2 | 权限检查流程 | 业务关键逻辑 |
| P2 | CRM 联系人追踪 | Feishu 通道依赖 |
| P3 | 会话生命周期管理 | 内部流程 |
| P3 | 文件导入 | 工具性功能 |

## 决策记录

| 决策 | 理由 |
|------|------|
| 模块分析使用 5 个并行 subagent | 5 个代码模块独立分析，最大化并行效率 |
| 不单独分析 docs/ 和 skills/ | docs/ 是文档（69 .md + 90 .json），skills/ 是 Claude Code skill 定义，不属于核心代码 |
| Windows 上 python 替代 python3 | python3 指向 MS Store，实际 Python 在 /c/Python311/python |
| 4 个 skipped 测试标记为代码级 skip | pytest.skip() 条件是 flows/ 目录不存在，属于功能未就绪，非环境问题 |
| 测试端口标记为 soft dependency | 测试自行创建 mock server，不需要外部服务 |

## 已知问题和边界

1. **autoservice/ 模块无专属测试**：核心库 16 个文件没有单元测试，仅通过集成测试间接覆盖
2. **plugins/ 无测试**：插件系统没有任何测试
3. **E2E 覆盖率低**：8 个用户流程中只有 2 个有 E2E 覆盖
4. **Makefile 使用 python3**：`make run-channel` 和 `make run-server` 在 Windows 上会失败
