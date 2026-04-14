# CC Pool — Claude Code SDK 实例池

## 概述

CC Pool 预创建并维护一组 `ClaudeSDKClient` 实例（每个实例对应一个持久化的 Claude Code 子进程），通过 checkout/return 语义复用子进程，消除每次查询的冷启动开销（~2-5s → ~0ms）。

## 架构

```
┌─────────────────────────────────────────┐
│              调用方                       │
│  (skill scripts / channel / web)        │
└─────────────┬───────────────────────────┘
              │  pool_query("...")
              ▼
┌─────────────────────────────────────────┐
│            CCPool                        │
│  ┌─────────────────────────────────┐    │
│  │  Available Queue                 │    │
│  │  [cc-001] [cc-002] [cc-003]     │    │
│  └─────────────────────────────────┘    │
│  • checkout() → 取出实例                 │
│  • query()    → 发送到子进程             │
│  • checkin()  → 归还实例                 │
│  • health_check_loop → 后台监控          │
└─────────────────────────────────────────┘
              │
              ▼  (per instance)
┌─────────────────────────────────────────┐
│       ClaudeSDKClient (SDK v0.1.56)     │
│  • connect()          → 启动子进程       │
│  • query(prompt)      → 复用子进程       │
│  • receive_response() → 流式接收         │
│  • disconnect()       → 终止子进程       │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│     claude CLI (local, via PATH)        │
│     持久子进程 — 一次启动，多次查询       │
└─────────────────────────────────────────┘
```

## 快速开始

### 1. 在代码中使用

```python
from autoservice.claude import pool_query

# 直接替代 query() — 签名一致
async for msg in pool_query("帮我分析这段代码"):
    print(msg)
```

### 2. 高级用法（手动管理池）

```python
from autoservice.cc_pool import get_pool, shutdown_pool, PoolConfig

# 自定义配置
config = PoolConfig(min_size=2, max_size=8, warmup_count=2)
pool = await get_pool(config)

# 使用上下文管理器
async with pool.acquire() as instance:
    await instance.client.query("hello")
    async for msg in instance.client.receive_response():
        handle(msg)

# 查看状态
print(pool.status())

# 关闭
await shutdown_pool()
```

## 配置

配置分三层，后加载的覆盖先加载的：

```
① config.yaml (共享默认) → ② config.local.yaml (本地覆盖) → ③ 环境变量 (部署注入)
```

### 方式一：共享配置（提交到 git）

`.autoservice/config.yaml` — 所有环境通用的默认值：
```yaml
cc_pool:
  min_size: 1
  max_size: 4
  warmup_count: 1
  max_queries_per_instance: 50
  max_lifetime_seconds: 3600
  permission_mode: bypassPermissions
```

### 方式二：本地覆盖（gitignored）

`.autoservice/config.local.yaml` — 密钥、测试/生产差异：
```yaml
cc_pool:
  min_size: 2
  max_size: 8
  warmup_count: 2
  model: claude-sonnet-4-5
  # cli_path: /usr/local/bin/claude
```

参考模板：`.autoservice/config.local.yaml.example`

### 方式三：环境变量（部署时注入）

| 环境变量 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `CC_POOL_MIN_SIZE` | int | 1 | 最小热实例数 |
| `CC_POOL_MAX_SIZE` | int | 4 | 最大并发实例数 |
| `CC_POOL_WARMUP_COUNT` | int | 1 | 启动时预创建数量 |
| `CC_POOL_MAX_QUERIES_PER_INSTANCE` | int | 50 | 单实例查询上限 |
| `CC_POOL_MAX_LIFETIME_SECONDS` | float | 3600 | 单实例最大存活秒数 |
| `CC_POOL_HEALTH_CHECK_INTERVAL` | float | 30 | 健康检查间隔 |
| `CC_POOL_CHECKOUT_TIMEOUT` | float | 30 | 池耗尽等待超时 |
| `CC_POOL_PERMISSION_MODE` | str | bypassPermissions | 权限模式 |
| `CC_POOL_MODEL` | str | (SDK默认) | 模型覆盖 |
| `CC_POOL_CLI_PATH` | str | (自动检测) | claude CLI 路径 |

优先级：环境变量 > YAML > 默认值

## CLI 命令

```bash
# 查看池状态
make pool-status
# 或
uv run python -m autoservice.cc_pool_cli status

# 启动池（前台运行，Ctrl+C 关闭）
make pool-start
# 或
uv run python -m autoservice.cc_pool_cli start

# 查看日志（最近 50 行）
make pool-logs
# 或
uv run python -m autoservice.cc_pool_cli logs

# 实时跟踪日志
uv run python -m autoservice.cc_pool_cli logs -f
```

### Status 输出示例

```
──────────────────────────────────────────────────
  CC Pool Status
──────────────────────────────────────────────────
  运行状态:   ● 运行中
  总实例数:   2 / 4
  可用:       1
  已借出:     1
  更新时间:   2026-04-12T15:30:00

  ID         健康   查询数   存活(s)
  ────────── ───── ─────── ─────────
  cc-001     ✓      12       245.3
  cc-002     ✓      3        120.8
──────────────────────────────────────────────────
```

## 测试

### 单元测试（mock，无需 API key）

```bash
make pool-unit
# 或
uv run python -m pytest tests/test_cc_pool.py -v
```

22 个测试覆盖：
- PoolConfig 加载（默认值 / 环境变量 / YAML）
- PooledInstance 健康检查、回收判断
- CCPool 启动/关闭、checkout/checkin、上下文管理器
- 池耗尽超时、不健康实例回收、过载回收
- status 输出、convenience query

### 集成测试（需要本地 claude CLI + API key）

```bash
make pool-test
# 或
uv run python tests/integration_cc_pool.py
```

前置条件：
- 已安装 claude CLI: `npm install -g @anthropic-ai/claude-code`
- 已配置 API key: `ANTHROPIC_API_KEY` 环境变量 或 `~/.claude/credentials`

测试内容：
1. **池生命周期** — start → warmup → status → shutdown
2. **单次查询** — pool.query() 发送并接收响应
3. **实例复用** — 3 次连续查询使用同一子进程
4. **性能对比** — pool_query vs stateless query 耗时对比
5. **状态详情** — checkout/checkin 后状态变化

### 性能预期

| 操作 | 无池 (stateless) | 有池 (pool) |
|------|-----------------|-------------|
| 首次查询 | ~3-5s (冷启动) | ~3-5s (warmup 阶段) |
| 后续查询 | ~3-5s (每次重启) | ~0.5-2s (复用子进程) |
| 并发 N 查询 | N 个子进程 | min(N, max_size) 个子进程 |

## 日志

日志自动写入 `.autoservice/logs/cc_pool.log`，级别：

- **DEBUG** — checkout/checkin/create/destroy 每次操作
- **INFO** — start/shutdown/warmup/recycle
- **WARNING** — disconnect 异常、配置加载失败
- **ERROR** — 实例创建失败

同时输出 INFO+ 到 stderr（终端可见）。

## 回收机制

实例在以下条件下自动回收（disconnect 并创建新实例）：

1. **查询次数超限** — `query_count >= max_queries_per_instance`（默认 50）
2. **存活时间超限** — `age >= max_lifetime_seconds`（默认 3600s）
3. **子进程死亡** — `process.returncode is not None`

回收发生在：
- `checkin()` 归还时检查
- 健康监控循环定期扫描空闲实例

## 文件结构

```
autoservice/
  cc_pool.py          # 核心实现：PoolConfig, PooledInstance, CCPool
  cc_pool_cli.py      # CLI 命令：status, start, stop, logs
  claude.py           # pool_query() 入口

tests/
  test_cc_pool.py          # 单元测试（mock）
  integration_cc_pool.py   # 集成测试（真实 SDK）

.autoservice/
  config.yaml                    # 共享配置（提交到 git）
  config.local.yaml              # 本地覆盖（gitignored）
  config.local.yaml.example      # 配置模板（提交到 git）
  logs/cc_pool.log               # 运行日志
  cc_pool_status.json            # 状态快照（CLI 读取）
```
