#!/usr/bin/env python3
"""
CC Pool 集成测试 — 使用本地 Claude SDK CLI 实际运行。

前置条件：
  - 已安装 claude CLI (npm install -g @anthropic-ai/claude-code)
  - 已配置有效 API key (ANTHROPIC_API_KEY 环境变量或 ~/.claude/credentials)

运行：
  cd AutoService-cc-pool
  uv run python tests/integration_cc_pool.py

测试内容：
  1. 池启动 + warmup（实际启动 Claude Code 子进程）
  2. 单次查询（验证 pool.query 能拿到响应）
  3. 连续查询复用（同一实例被复用，query_count 递增）
  4. 池状态输出
  5. 性能对比：pool_query vs stateless query
  6. 优雅关闭
"""

import asyncio
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from autoservice.cc_pool import CCPool, PoolConfig, get_pool, shutdown_pool
from claude_agent_sdk.types import ResultMessage, AssistantMessage


DIVIDER = "=" * 60


async def test_pool_lifecycle():
    """测试 1: 池启动、warmup、状态、关闭"""
    print(f"\n{DIVIDER}")
    print("TEST 1: Pool lifecycle (start → warmup → status → shutdown)")
    print(DIVIDER)

    config = PoolConfig(
        min_size=1,
        max_size=2,
        warmup_count=1,
        max_queries_per_instance=10,
        health_check_interval=60,
        checkout_timeout=30,
    )

    t0 = time.time()
    pool = CCPool(config)
    await pool.start()
    warmup_time = time.time() - t0

    status = pool.status()
    print(f"  Warmup time: {warmup_time:.2f}s")
    print(f"  Status: total={status['total']}, available={status['available']}")
    for inst in status["instances"]:
        print(f"    {inst['id']}: healthy={inst['healthy']}, queries={inst['query_count']}")

    assert status["total"] == 1, f"Expected 1 instance, got {status['total']}"
    assert status["available"] == 1
    print("  ✓ Pool started with 1 warm instance")

    await pool.shutdown()
    assert pool.size == 0
    print("  ✓ Pool shut down cleanly")
    return warmup_time


async def test_single_query():
    """测试 2: 单次查询（通过池发送并接收响应）"""
    print(f"\n{DIVIDER}")
    print("TEST 2: Single query via pool")
    print(DIVIDER)

    config = PoolConfig(min_size=1, max_size=2, warmup_count=1, health_check_interval=60)
    pool = CCPool(config)
    await pool.start()

    t0 = time.time()
    response_text = ""
    msg_count = 0

    async for msg in pool.query("Reply with exactly: POOL_OK"):
        msg_count += 1
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if hasattr(block, "text"):
                    response_text += block.text
        elif isinstance(msg, ResultMessage):
            print(f"  Cost: ${msg.total_cost_usd:.6f}" if msg.total_cost_usd else "  Cost: N/A")

    query_time = time.time() - t0
    print(f"  Query time: {query_time:.2f}s")
    print(f"  Messages received: {msg_count}")
    print(f"  Response: {response_text[:200]}")

    status = pool.status()
    print(f"  Instance query_count: {status['instances'][0]['query_count']}")
    assert status["instances"][0]["query_count"] == 1
    print("  ✓ Single query successful")

    await pool.shutdown()
    return query_time


async def test_reuse():
    """测试 3: 连续查询复用同一实例"""
    print(f"\n{DIVIDER}")
    print("TEST 3: Instance reuse across multiple queries")
    print(DIVIDER)

    config = PoolConfig(min_size=1, max_size=1, warmup_count=1, health_check_interval=60)
    pool = CCPool(config)
    await pool.start()

    times = []
    for i in range(3):
        t0 = time.time()
        async for msg in pool.query(f"Reply with exactly: QUERY_{i}"):
            if isinstance(msg, ResultMessage):
                break
        elapsed = time.time() - t0
        times.append(elapsed)
        print(f"  Query {i}: {elapsed:.2f}s")

    status = pool.status()
    inst = status["instances"][0]
    print(f"  Instance {inst['id']}: query_count={inst['query_count']}, age={inst['age_seconds']}s")
    assert inst["query_count"] == 3, f"Expected 3 queries, got {inst['query_count']}"

    # 第 2、3 次查询应该比第 1 次快（无 cold start）
    if len(times) >= 2 and times[0] > 0:
        speedup = times[0] / max(times[1], 0.01)
        print(f"  Speedup (query 1 vs 2): {speedup:.1f}x")
    print("  ✓ Instance reused across 3 queries")

    await pool.shutdown()
    return times


async def test_performance_comparison():
    """测试 4: 池查询 vs 无状态查询 性能对比"""
    print(f"\n{DIVIDER}")
    print("TEST 4: Performance comparison (pool vs stateless)")
    print(DIVIDER)

    from autoservice.claude import query as stateless_query

    prompt = "Reply with exactly one word: BENCHMARK"

    # Stateless query (cold start each time)
    t0 = time.time()
    async for msg in stateless_query(prompt):
        if isinstance(msg, ResultMessage):
            break
    stateless_time = time.time() - t0
    print(f"  Stateless query: {stateless_time:.2f}s")

    # Pool query (warm instance)
    config = PoolConfig(min_size=1, max_size=1, warmup_count=1, health_check_interval=60)
    pool = CCPool(config)
    await pool.start()

    # First pool query (instance already warm from start)
    t0 = time.time()
    async for msg in pool.query(prompt):
        if isinstance(msg, ResultMessage):
            break
    pool_time_1 = time.time() - t0
    print(f"  Pool query (1st): {pool_time_1:.2f}s")

    # Second pool query (same subprocess)
    t0 = time.time()
    async for msg in pool.query(prompt):
        if isinstance(msg, ResultMessage):
            break
    pool_time_2 = time.time() - t0
    print(f"  Pool query (2nd): {pool_time_2:.2f}s")

    await pool.shutdown()

    print(f"\n  Summary:")
    print(f"    Stateless:  {stateless_time:.2f}s (new subprocess each time)")
    print(f"    Pool (1st): {pool_time_1:.2f}s (subprocess already warm)")
    print(f"    Pool (2nd): {pool_time_2:.2f}s (reusing same subprocess)")
    if stateless_time > 0:
        print(f"    Pool speedup: {stateless_time / max(pool_time_2, 0.01):.1f}x")
    print("  ✓ Performance comparison complete")


async def test_pool_status_detail():
    """测试 5: 池状态详细输出"""
    print(f"\n{DIVIDER}")
    print("TEST 5: Pool status detail")
    print(DIVIDER)

    config = PoolConfig(min_size=2, max_size=4, warmup_count=2, health_check_interval=60)
    pool = CCPool(config)
    await pool.start()

    # Checkout one
    inst = await pool.checkout()
    inst.query_count = 3

    status = pool.status()
    import json
    print(json.dumps(status, indent=2))
    assert status["checked_out"] == 1
    assert status["available"] == 1

    await pool.checkin(inst)
    status = pool.status()
    assert status["checked_out"] == 0
    print(f"\n  After checkin: available={status['available']}")
    print("  ✓ Status reflects checkout/checkin correctly")

    await pool.shutdown()


async def main():
    print("CC Pool Integration Tests")
    print(f"Working directory: {Path.cwd()}")
    print(f"Using local Claude CLI")

    try:
        warmup_time = await test_pool_lifecycle()
        query_time = await test_single_query()
        times = await test_reuse()
        await test_performance_comparison()
        await test_pool_status_detail()

        print(f"\n{DIVIDER}")
        print("ALL TESTS PASSED ✓")
        print(DIVIDER)
        print(f"\nKey metrics:")
        print(f"  Warmup (subprocess init): {warmup_time:.2f}s")
        print(f"  First query:              {query_time:.2f}s")
        print(f"  Subsequent queries:       {times[1]:.2f}s / {times[2]:.2f}s")
        print(f"\nLog file: .autoservice/logs/cc_pool.log")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
