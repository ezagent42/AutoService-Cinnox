# SDK 模式性能优化方案

> 版本: v0.6.0 | 日期: 2026-03-17

## 问题描述

CINNOX Demo WebUI 会话响应慢，用户提问后需等待 10-25 秒才能看到回复。

## 根因分析

### 优化前架构（多 Agent 流水线）

```
用户提问
  → Claude CLI 推理 (system prompt 37KB / ~9000 tokens)
  → route_query.py (Bash 子进程, ~1s)
  → Agent tool → 启动 subagent CLI 子进程
    → subagent 推理 (product-query / region-query)
    → subagent 调 kb_search.py (又一个子进程)
    → subagent 返回结构化结果
  → 可能再调 copywriting subagent (又一次推理)
  → 可能再调 reviewer subagent (又一次推理)
  → 最终回复
```

**瓶颈拆解：**

| 瓶颈 | 耗时 | 说明 |
|------|------|------|
| System Prompt 过大 | +2-3s | 37KB SKILL.md 每轮都发送，推理前需处理 9000+ token |
| Subagent 多级流水线 | +8-15s | 每个 subagent = 新的 Claude CLI 子进程 + 推理，最多 3-4 次 |
| route_query.py 子进程 | +0.5-2s | Windows 上 Python 子进程启动开销大 |
| max_turns=15 | — | 允许过多 tool_use 轮次，容易发散 |

**总计：单次产品问题响应 10-25 秒**

---

## 优化方案

### 1. System Prompt 精简：37KB → 6.4KB（-83%）

**文件**：新建 `SKILL_WEB.md`（web 专用精简版），保留原 `SKILL.md` 供 CLI 使用。

**精简内容**：
- 去掉 Step 1 (KB 预检)、Step 2 (会话 banner)、Step 7 (save_session)、Step 8 (审计)
- 去掉 subagent 编排规则（Step 3.5 整节）
- 去掉详细示例、UAT 用例引用
- 合并重复规则，压缩表格
- 保留所有业务规则：GATE、客户识别、Lead 收集、路由、反幻觉、升级

**预估提速**：每轮推理减少 ~7000 token 输入 → 推理快 30-40%

### 2. 架构扁平化：多 Agent → 单 Agent

**优化前**：
```
主 Agent → Agent tool → product-query subagent → kb_search
                      → copywriting subagent
                      → reviewer subagent
```

**优化后**：
```
主 Agent → Bash: curl /api/route_query (in-process 拦截, <1ms)
         → Bash: curl /api/kb_search   (in-process 拦截, <10ms)
         → 直接组织回复
```

**关键改动**：
- `allowed_tools` 从 `["Bash", "Agent"]` 改为 `["Bash"]`
- SKILL_WEB.md 指导主 agent 直接 `curl /api/kb_search` 和 `curl /api/route_query` 查询
- server.py `_execute_tool()` in-process 快速路径拦截所有 curl 调用（kb_search + route_query + save_lead + mock_account）

**预估提速**：省掉 2-3 次 Claude 推理 + 子进程启动 → 提速 2-3x

### 3. route_query.py 从子进程改为 in-process 调用

**问题**：日志显示 agent 调 `uv run route_query.py` 时路径错误（`h2os/cloud` vs `h2os.cloud`），导致重试 3 次浪费 13 秒。

**方案**：
- 新增 HTTP 端点 `GET /api/route_query?query=...`
- `_execute_tool()` 拦截 `route_query` 相关命令，直接调用 `route_query.route()` Python 函数
- SKILL_WEB.md 改为 `curl` 调用，彻底消除路径问题 + 子进程开销

### 4. max_turns 降低：15 → 8

减少不必要的 tool_use 循环，防止发散。正常流程只需：
1. route_query（1 轮）
2. kb_search（1 轮）
3. 可能的 save_lead（1 轮）
4. 最终回复

8 轮足够覆盖所有正常场景。

---

## 改动文件

| 文件 | 改动 |
|------|------|
| `.claude/skills/cinnox-demo/SKILL_WEB.md` | **新建** — 6.4KB web 专用精简 prompt |
| `web/server.py` | 加载 SKILL_WEB.md；`allowed_tools=["Bash"]`；`max_turns=8`；移除 subagent 追踪代码；新增 route_query in-process 拦截 + HTTP 端点；解除 SDK 模式 kb_search 直查限制 |
| `.claude/skills/cinnox-demo/SKILL.md` | **未修改** — CLI 模式仍使用完整版 |

## 预估效果

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| System prompt 大小 | ~40KB (~9000 tokens) | ~8KB (~2000 tokens) | -80% |
| 产品问题响应时间 | 10-25s | 3-8s | 2-3x |
| Claude 推理次数/轮 | 3-5 次 | 1-2 次 | -60% |
| 子进程启动次数 | 3-5 次 | 0 次 (全部 in-process) | -100% |
| 简单问候响应时间 | 3-5s | 1-3s | ~2x |

## 兼容性

- CLI 模式 (`/cinnox-demo`) 不受影响，仍使用完整 SKILL.md + 多 Agent 架构
- Web 模式自动使用 SKILL_WEB.md，如文件不存在则 fallback 到精简后的 SKILL.md
- 所有业务规则（GATE、路由、升级、反幻觉）保持一致
- KB 搜索结果通过 server.py in-process 拦截，质量不变
