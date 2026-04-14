# CC Pool 有状态会话支持设计方案

**Date:** 2026-04-14
**Status:** Phase 1 实施中
**Prerequisite:** [三层架构](2026-04-10-three-layer-implementation.md) 已合入 main

---

## Problem

当前每个客户对话需要手动启动一个 Claude Code 进程（tmux session）。CC Pool 已有无状态池化能力，但缺少 Session Affinity。需要让同一 chat_id 始终绑定同一 Claude Code 实例，实现多轮有状态对话。

## Phase 1: L1 Sticky Bindings + L2 session_query

- L1 `socialware/pool.py`: `StickyBinding` 数据结构 + `acquire_sticky(key)` / `release_sticky(key)` / `_cleanup_sticky()`
- L2 `autoservice/cc_pool.py`: `session_query(chat_id, prompt)` / `end_session(chat_id)` + config 字段
- 纯增量，不破坏现有 API

## Phase 2: channel_server 池集成

- 提取 `channel_tools.py`，通过 SDK MCP server 注入
- `channel_server.py` 增加 `pool_mode` 开关
- 双模式共存：WebSocket 优先，池兜底

详见 plan file。
