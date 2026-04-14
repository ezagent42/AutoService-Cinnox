# Pool Route Integration — Pool 融入路由体系

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** CC Pool 实例通过虚拟路由 (PoolRoute) 注册到 channel_server 的 exact_routes 体系，替代独立旁路，使 pool_mode 与交互模式共存。

**Architecture:** 引入 PoolRoute dataclass 作为虚拟路由，pool 实例首次收到消息时自动绑定并注册 exact route。Wildcard 实例始终只收观察副本。Pool sticky 过期时通过回调清理路由。同时修复 .mcp.json 导致 pool 实例启动多余 channel.py 的问题。

**Tech Stack:** Python 3.14, asyncio, websockets, Claude Agent SDK, pytest

**Key files:**
- `socialware/pool.py` — L1 base pool, sticky session
- `autoservice/cc_pool.py` — L2 CC pool subclass
- `channels/feishu/channel_server.py` — L2 channel server, routing logic

---

### Task 1: Add on_sticky_release callback to AsyncPool

**Files:**
- Modify: `socialware/pool.py:148-168` (\_\_init\_\_), `socialware/pool.py:424-456` (\_cleanup\_sticky)
- Test: `tests/test_cc_pool.py`

**Step 1: Write the failing test**

Add to `tests/test_cc_pool.py`:

```python
class TestStickyReleaseCallback:
    """Test on_sticky_release callback fires when sticky bindings expire."""

    @pytest.mark.asyncio
    async def test_callback_fires_on_expiry(self):
        """When sticky idle timeout expires, on_sticky_release is called with the key."""
        released_keys = []

        async def on_release(key: str):
            released_keys.append(key)

        config = PoolConfig(
            min_size=1, max_size=2, warmup_count=1,
            sticky_idle_timeout=0.1,  # 100ms for fast test
        )

        with patch("autoservice.cc_pool.create_cc_client", new_callable=lambda: lambda *a, **kw: asyncio.coroutine(lambda: make_mock_client())()) as mock_factory:
            pool = CCPool(config=config, on_sticky_release=on_release)
            pool._factory = lambda: asyncio.coroutine(lambda: make_mock_client())()
            await pool.start()

            try:
                # Bind a sticky session
                inst = await pool.acquire_sticky("chat_001")
                assert pool.sticky_count == 1

                # Wait for expiry
                await asyncio.sleep(0.3)

                # Trigger health check (which runs cleanup)
                await pool._cleanup_sticky()

                assert "chat_001" in released_keys
                assert pool.sticky_count == 0
            finally:
                await pool.stop()

    @pytest.mark.asyncio
    async def test_no_callback_when_none(self):
        """Pool works fine without on_sticky_release callback."""
        config = PoolConfig(
            min_size=1, max_size=2, warmup_count=1,
            sticky_idle_timeout=0.1,
        )

        with patch("autoservice.cc_pool.create_cc_client", new_callable=lambda: lambda *a, **kw: asyncio.coroutine(lambda: make_mock_client())()) as mock_factory:
            pool = CCPool(config=config)  # No callback
            pool._factory = lambda: asyncio.coroutine(lambda: make_mock_client())()
            await pool.start()

            try:
                await pool.acquire_sticky("chat_002")
                await asyncio.sleep(0.3)
                await pool._cleanup_sticky()
                assert pool.sticky_count == 0  # Still cleaned up, no error
            finally:
                await pool.stop()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cc_pool.py::TestStickyReleaseCallback -v`
Expected: FAIL — `CCPool()` does not accept `on_sticky_release` parameter

**Step 3: Implement on_sticky_release in AsyncPool**

In `socialware/pool.py`, modify `AsyncPool.__init__` (line 148):

```python
def __init__(
    self,
    config: PoolConfig,
    factory: Callable[[], Awaitable[T]],
    instance_prefix: str = "inst",
    logger: logging.Logger | None = None,
    on_sticky_release: Callable[[str], Awaitable[None]] | None = None,
):
    # ... existing fields ...
    self._on_sticky_release = on_sticky_release
```

In `socialware/pool.py`, modify `_cleanup_sticky` (after line 456, after destroy loop):

```python
# Notify listener of expired keys
if self._on_sticky_release:
    for binding in removed_bindings:
        try:
            await self._on_sticky_release(binding.key)
        except Exception as e:
            self._log.warning("on_sticky_release callback failed for key=%s: %s",
                              binding.key, e)
```

Also add callback to `release_sticky` (line 402), after the checkin:

```python
if self._on_sticky_release:
    try:
        await self._on_sticky_release(key)
    except Exception as e:
        self._log.warning("on_sticky_release callback failed for key=%s: %s", key, e)
```

**Step 4: Pass callback through CCPool**

In `autoservice/cc_pool.py`, modify `CCPool.__init__` (line 236):

```python
def __init__(
    self,
    config: PoolConfig | None = None,
    mcp_servers: dict | None = None,
    system_prompt: str | None = None,
    on_sticky_release: Callable[[str], Awaitable[None]] | None = None,
):
    cfg = config or PoolConfig()
    super().__init__(
        config=cfg,
        factory=lambda: create_cc_client(cfg, mcp_servers=mcp_servers,
                                          system_prompt=system_prompt),
        instance_prefix="cc",
        logger=log,
        on_sticky_release=on_sticky_release,
    )
```

Add import at top of `autoservice/cc_pool.py`:

```python
from collections.abc import Awaitable, Callable
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_cc_pool.py::TestStickyReleaseCallback -v`
Expected: PASS

**Step 6: Commit**

```bash
git add socialware/pool.py autoservice/cc_pool.py tests/test_cc_pool.py
git commit -m "feat: add on_sticky_release callback to AsyncPool and CCPool"
```

---

### Task 2: Add PoolRoute and rewrite route_message

**Files:**
- Modify: `channels/feishu/channel_server.py:36-46` (data model), `channels/feishu/channel_server.py:55-83` (\_\_init\_\_), `channels/feishu/channel_server.py:985-1033` (route\_message)
- Test: `tests/test_channel_tools.py`

**Step 1: Write the failing tests**

Add to `tests/test_channel_tools.py`:

```python
class TestPoolRouteIntegration:
    """Test that pool_mode routes messages through PoolRoute, not wildcard."""

    @pytest.mark.asyncio
    async def test_pool_route_created_on_first_message(self):
        """First message for unknown chat_id creates a PoolRoute."""
        from channels.feishu.channel_server import ChannelServer
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)

        # Mock pool
        mock_pool = AsyncMock()
        mock_pool.acquire_sticky = AsyncMock(return_value=MagicMock(id="cc-001"))

        async def mock_session_query(chat_id, prompt, **kw):
            return
            yield  # make it an async generator

        mock_pool.session_query = mock_session_query
        server._pool = mock_pool

        msg = {"type": "message", "text": "hello", "chat_id": "oc_test1",
               "user": "test", "source": "feishu"}

        await server.route_message("oc_test1", msg)

        assert "oc_test1" in server.pool_routes
        assert server.pool_routes["oc_test1"].instance_id == "cc-001"

    @pytest.mark.asyncio
    async def test_pool_route_reused_on_second_message(self):
        """Second message for same chat_id reuses existing PoolRoute."""
        from channels.feishu.channel_server import ChannelServer
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)

        mock_pool = AsyncMock()
        mock_pool.acquire_sticky = AsyncMock(return_value=MagicMock(id="cc-001"))

        async def mock_session_query(chat_id, prompt, **kw):
            return
            yield

        mock_pool.session_query = mock_session_query
        server._pool = mock_pool

        msg = {"type": "message", "text": "hello", "chat_id": "oc_test1",
               "user": "test", "source": "feishu"}

        await server.route_message("oc_test1", msg)
        await server.route_message("oc_test1", msg)

        # acquire_sticky called twice (by session_query), but pool_routes entry created once
        assert len(server.pool_routes) == 1

    @pytest.mark.asyncio
    async def test_exact_route_takes_priority_over_pool(self):
        """WebSocket exact route has higher priority than pool."""
        from channels.feishu.channel_server import ChannelServer, Instance
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)

        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        inst = Instance(ws=mock_ws, instance_id="ws-001", role="agent",
                        chat_ids=["oc_test1"])
        server.exact_routes["oc_test1"] = inst

        mock_pool = AsyncMock()
        server._pool = mock_pool

        msg = {"type": "message", "text": "hello", "chat_id": "oc_test1",
               "user": "test", "source": "feishu"}

        await server.route_message("oc_test1", msg)

        # Pool should NOT be used
        assert "oc_test1" not in server.pool_routes
        # WebSocket should receive the message
        mock_ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_wildcard_gets_observation_copy_with_pool(self):
        """Wildcard instance gets routed_to marker when pool handles message."""
        from channels.feishu.channel_server import ChannelServer, Instance
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)

        # Add wildcard instance
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        wc_inst = Instance(ws=mock_ws, instance_id="dev-001", role="developer",
                           chat_ids=["*"])
        server.wildcard_instances.append(wc_inst)

        # Mock pool
        mock_pool = AsyncMock()
        mock_pool.acquire_sticky = AsyncMock(return_value=MagicMock(id="cc-001"))

        async def mock_session_query(chat_id, prompt, **kw):
            return
            yield

        mock_pool.session_query = mock_session_query
        server._pool = mock_pool

        msg = {"type": "message", "text": "hello", "chat_id": "oc_test1",
               "user": "test", "source": "feishu"}

        await server.route_message("oc_test1", msg)

        # Pool should handle the message
        assert "oc_test1" in server.pool_routes

        # Wildcard should get observation copy with routed_to
        mock_ws.send.assert_called_once()
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert "routed_to" in sent

    @pytest.mark.asyncio
    async def test_admin_chat_excluded_from_pool(self):
        """Admin group messages should not be routed through pool."""
        from channels.feishu.channel_server import ChannelServer
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True,
                               admin_chat_id="oc_admin")

        mock_pool = AsyncMock()
        server._pool = mock_pool

        msg = {"type": "message", "text": "hello", "chat_id": "oc_admin",
               "user": "admin", "source": "feishu"}

        await server.route_message("oc_admin", msg)

        # Pool should NOT handle admin messages
        assert "oc_admin" not in server.pool_routes

    @pytest.mark.asyncio
    async def test_pool_route_cleaned_on_sticky_release(self):
        """When sticky expires, pool_route is removed."""
        from channels.feishu.channel_server import ChannelServer, PoolRoute
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)

        mock_pool = AsyncMock()
        server._pool = mock_pool
        server.pool_routes["oc_expired"] = PoolRoute(
            pool=mock_pool, chat_id="oc_expired", instance_id="cc-001"
        )

        await server._on_pool_route_expired("oc_expired")

        assert "oc_expired" not in server.pool_routes

    @pytest.mark.asyncio
    async def test_pool_none_falls_back_to_wildcard(self):
        """When pool is None (failed to start), wildcard handles messages."""
        from channels.feishu.channel_server import ChannelServer, Instance
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)
        server._pool = None  # Pool failed to start

        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        wc_inst = Instance(ws=mock_ws, instance_id="dev-001", role="developer",
                           chat_ids=["*"])
        server.wildcard_instances.append(wc_inst)

        msg = {"type": "message", "text": "hello", "chat_id": "oc_test1",
               "user": "test", "source": "feishu"}

        await server.route_message("oc_test1", msg)

        # Wildcard should handle (no routed_to since pool didn't route)
        mock_ws.send.assert_called_once()
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert "routed_to" not in sent
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_channel_tools.py::TestPoolRouteIntegration -v`
Expected: FAIL — `PoolRoute` not defined, `pool_routes` not an attribute, etc.

**Step 3: Add PoolRoute dataclass and pool_routes dict**

In `channel_server.py` after the `Instance` dataclass (line ~46):

```python
@dataclass
class PoolRoute:
    """Virtual route backed by a CC Pool sticky session.

    Unlike Instance (WebSocket-backed), PoolRoute dispatches messages
    through pool.session_query() and receives replies via MCP callbacks.
    """
    pool: Any  # CCPool — use Any to avoid circular import
    chat_id: str
    instance_id: str  # pool instance id (e.g. "cc-001")
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

In `ChannelServer.__init__` (after line 73):

```python
# Pool virtual routes (chat_id → PoolRoute)
self.pool_routes: dict[str, PoolRoute] = {}
```

**Step 4: Rewrite route_message**

Replace `route_message` (lines 985-1033) with:

```python
async def route_message(self, chat_id: str, message: dict) -> None:
    """Route a message to the appropriate instance(s)."""
    routed = False
    routed_by: str | None = None  # instance_id for observation tagging

    # 1. Exact match (WebSocket)
    if chat_id in self.exact_routes:
        inst = self.exact_routes[chat_id]
        await self._send(inst.ws, message)
        routed = True
        routed_by = inst.instance_id

    # 2. Prefix match
    if not routed:
        for prefix, inst in self.prefix_routes.items():
            if chat_id.startswith(prefix):
                await self._send(inst.ws, message)
                routed = True
                routed_by = inst.instance_id
                break

    # 3. Pool route (existing sticky binding)
    if not routed and chat_id in self.pool_routes:
        route = self.pool_routes[chat_id]
        asyncio.create_task(
            self._handle_pool_message(chat_id, message),
            name=f"pool-msg-{chat_id}",
        )
        routed = True
        routed_by = route.instance_id

    # 4. Pool auto-assign (first message, pool_mode enabled, not admin)
    if (not routed
            and self.pool_mode
            and self._pool is not None
            and chat_id != self.admin_chat_id):
        try:
            instance = await self._pool.acquire_sticky(chat_id)
            self.pool_routes[chat_id] = PoolRoute(
                pool=self._pool, chat_id=chat_id, instance_id=instance.id,
            )
            asyncio.create_task(
                self._handle_pool_message(chat_id, message),
                name=f"pool-msg-{chat_id}",
            )
            routed = True
            routed_by = instance.id
            log.info("Pool assigned: chat_id=%s -> %s", chat_id, instance.id)
        except Exception as e:
            log.error("Pool assign failed for chat_id=%s: %s", chat_id, e)

    # 5. Wildcard — always send observation copy
    for inst in self.wildcard_instances:
        if routed_by and routed_by == inst.instance_id:
            continue  # don't double-send to the handler
        if routed:
            wc_msg = {**message, "routed_to": routed_by}
        else:
            wc_msg = message
        await self._send(inst.ws, wc_msg)

    # 6. Nothing handled
    if not routed and not self.wildcard_instances:
        log.warning("No route for chat_id=%s, message dropped", chat_id)
    elif not routed and self.wildcard_instances:
        user = message.get("user", "unknown")
        source = message.get("source", "?")
        log.info(
            "No dedicated instance for [%s] %s -> wildcard\n"
            "   To start dedicated: ./autoservice.sh %s",
            source, user, chat_id,
        )
```

**Step 5: Add _on_pool_route_expired callback**

In `ChannelServer` class:

```python
async def _on_pool_route_expired(self, chat_id: str) -> None:
    """Called when a pool sticky binding expires or is released."""
    removed = self.pool_routes.pop(chat_id, None)
    if removed:
        log.info("Pool route expired: chat_id=%s (was %s)", chat_id, removed.instance_id)
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_tools.py::TestPoolRouteIntegration -v`
Expected: PASS

**Step 7: Commit**

```bash
git add channels/feishu/channel_server.py tests/test_channel_tools.py
git commit -m "feat: PoolRoute virtual routing — pool integrates into exact_routes priority"
```

---

### Task 3: Wire on_sticky_release callback in _start_pool

**Files:**
- Modify: `channels/feishu/channel_server.py:147-195` (\_start\_pool)

**Step 1: Write the failing test**

Add to `tests/test_channel_tools.py`:

```python
class TestStartPoolCallback:
    @pytest.mark.asyncio
    async def test_start_pool_wires_callback(self):
        """_start_pool passes on_sticky_release to CCPool."""
        from channels.feishu.channel_server import ChannelServer
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)

        with patch("channels.feishu.channel_server.CCPool") as MockPool, \
             patch("channels.feishu.channel_server.load_pool_config") as mock_config, \
             patch("channels.feishu.channel_server.discover", return_value=[]), \
             patch("channels.feishu.channel_server.create_channel_mcp_server"):

            mock_config.return_value = PoolConfig(min_size=1, max_size=2)
            mock_pool_instance = AsyncMock()
            MockPool.return_value = mock_pool_instance

            await server._start_pool()

            # Verify on_sticky_release was passed
            call_kwargs = MockPool.call_args[1]
            assert "on_sticky_release" in call_kwargs
            assert call_kwargs["on_sticky_release"] == server._on_pool_route_expired
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_tools.py::TestStartPoolCallback -v`
Expected: FAIL — `on_sticky_release` not passed

**Step 3: Modify _start_pool to pass callback**

In `channel_server.py`, `_start_pool()`, change the CCPool construction (line ~188):

```python
self._pool = CCPool(
    config=config,
    mcp_servers={"channel-tools": {"type": "sdk", "name": "channel-tools", "instance": channel_mcp}},
    system_prompt=instructions,
    on_sticky_release=self._on_pool_route_expired,
)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_channel_tools.py::TestStartPoolCallback -v`
Expected: PASS

**Step 5: Commit**

```bash
git add channels/feishu/channel_server.py tests/test_channel_tools.py
git commit -m "feat: wire on_sticky_release callback from pool to channel_server"
```

---

### Task 4: Fix .mcp.json override — prevent pool instances from spawning channel.py

**Files:**
- Modify: `autoservice/cc_pool.py:178-220` (create\_cc\_client)
- Test: `tests/test_cc_pool.py`

**Step 1: Write the failing test**

Add to `tests/test_cc_pool.py`:

```python
class TestMcpServerOverride:
    """Verify pool instances override project .mcp.json to prevent channel.py spawn."""

    @pytest.mark.asyncio
    async def test_mcp_servers_includes_autoservice_channel_disabled(self):
        """When mcp_servers is provided, autoservice-channel should be overridden."""
        from autoservice.cc_pool import create_cc_client, PoolConfig

        captured_options = {}

        with patch("autoservice.cc_pool.ClaudeSDKClient") as MockSDK, \
             patch("autoservice.cc_pool.CCClient") as MockClient:

            mock_sdk_instance = MagicMock()
            MockSDK.return_value = mock_sdk_instance
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            MockClient.return_value = mock_client

            def capture_options(options):
                captured_options["mcp_servers"] = options.mcp_servers
                return mock_sdk_instance

            MockSDK.side_effect = capture_options

            config = PoolConfig()
            channel_tools = {"type": "sdk", "name": "channel-tools"}
            await create_cc_client(
                config,
                mcp_servers={"channel-tools": channel_tools},
            )

            # autoservice-channel should be explicitly disabled
            assert "autoservice-channel" in captured_options["mcp_servers"]
            # channel-tools should be present
            assert "channel-tools" in captured_options["mcp_servers"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cc_pool.py::TestMcpServerOverride -v`
Expected: FAIL — `autoservice-channel` not in mcp_servers

**Step 3: Add .mcp.json override in create_cc_client**

In `autoservice/cc_pool.py`, modify `create_cc_client` (after line 212):

```python
if mcp_servers:
    # Override project .mcp.json's autoservice-channel to prevent
    # pool instances from spawning channel.py WebSocket clients.
    # Pool instances use injected channel-tools MCP server instead.
    merged = {"autoservice-channel": {"disabled": True}}
    merged.update(mcp_servers)
    options.mcp_servers = merged
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cc_pool.py::TestMcpServerOverride -v`
Expected: PASS

**Step 5: Verify SDK respects disabled flag**

If the SDK does not support `{"disabled": True}`, use an alternative approach — set `mcp_servers` as the explicit full dict, which replaces (not merges with) .mcp.json. Check SDK docs or test empirically. If needed, use `setting_sources=["user"]` (skip project) and re-add skills via `plugins` parameter.

**Step 6: Commit**

```bash
git add autoservice/cc_pool.py tests/test_cc_pool.py
git commit -m "fix: override autoservice-channel in pool instances to prevent channel.py spawn"
```

---

### Task 5: Export PoolRoute from channel_server and clean up old code

**Files:**
- Modify: `channels/feishu/channel_server.py`

**Step 1: Remove old fallback pool code**

The old `route_message` had this dead code path (former lines 1014-1020, 1022-1032). Verify it has been fully replaced by Task 2's rewrite. Ensure no references to the old pattern remain.

**Step 2: Update _handle_pool_message docstring**

```python
async def _handle_pool_message(self, chat_id: str, message: dict) -> None:
    """Route a message through the CC Pool.

    Called by route_message when a PoolRoute exists or is newly created.
    Formats the message as a <channel> prompt and sends via session_query.
    Responses arrive via _pool_reply_callback (MCP tool callback).
    """
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/test_channel_tools.py tests/test_cc_pool.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add channels/feishu/channel_server.py
git commit -m "refactor: clean up old pool fallback code, update docstrings"
```

---

### Task 6: Integration test — end-to-end pool routing

**Files:**
- Create: `tests/test_pool_routing_e2e.py`

**Step 1: Write integration test**

```python
"""Integration test: pool routing end-to-end (mocked SDK, real routing logic)."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from channels.feishu.channel_server import ChannelServer, Instance, PoolRoute


class TestPoolRoutingE2E:

    @pytest.mark.asyncio
    async def test_full_flow_two_customers(self):
        """Two customers get different pool instances via sticky sessions."""
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)

        # Track which chat_ids the pool dispatched
        dispatched = []

        mock_pool = AsyncMock()
        instance_a = MagicMock(id="cc-001", is_healthy=True)
        instance_b = MagicMock(id="cc-002", is_healthy=True)

        sticky_map = {}

        async def mock_acquire_sticky(key):
            if key not in sticky_map:
                sticky_map[key] = instance_a if len(sticky_map) == 0 else instance_b
            return sticky_map[key]

        mock_pool.acquire_sticky = mock_acquire_sticky

        async def mock_session_query(chat_id, prompt, **kw):
            dispatched.append(chat_id)
            return
            yield

        mock_pool.session_query = mock_session_query
        server._pool = mock_pool

        # Customer A sends message
        await server.route_message("oc_cust_a", {
            "type": "message", "text": "hi", "chat_id": "oc_cust_a",
            "user": "Alice", "source": "feishu"
        })

        # Customer B sends message
        await server.route_message("oc_cust_b", {
            "type": "message", "text": "hello", "chat_id": "oc_cust_b",
            "user": "Bob", "source": "feishu"
        })

        # Both got pool routes
        assert "oc_cust_a" in server.pool_routes
        assert "oc_cust_b" in server.pool_routes
        assert server.pool_routes["oc_cust_a"].instance_id == "cc-001"
        assert server.pool_routes["oc_cust_b"].instance_id == "cc-002"

        # Customer A sends second message — reuses existing route
        await server.route_message("oc_cust_a", {
            "type": "message", "text": "follow up", "chat_id": "oc_cust_a",
            "user": "Alice", "source": "feishu"
        })

        # Wait for async tasks
        await asyncio.sleep(0.1)

        assert dispatched.count("oc_cust_a") == 2
        assert dispatched.count("oc_cust_b") == 1

    @pytest.mark.asyncio
    async def test_exact_route_overrides_pool(self):
        """Dedicated CLI instance takes priority even when pool is active."""
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)

        mock_pool = AsyncMock()
        server._pool = mock_pool

        # Register exact WebSocket instance for cust_a
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        server.exact_routes["oc_cust_a"] = Instance(
            ws=mock_ws, instance_id="ws-001", role="agent", chat_ids=["oc_cust_a"]
        )

        await server.route_message("oc_cust_a", {
            "type": "message", "text": "hi", "chat_id": "oc_cust_a",
            "user": "Alice", "source": "feishu"
        })

        # WebSocket got it, pool didn't
        mock_ws.send.assert_called_once()
        assert "oc_cust_a" not in server.pool_routes

    @pytest.mark.asyncio
    async def test_pool_route_expires_and_reassigns(self):
        """After sticky expiry, new message creates fresh pool route."""
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)

        mock_pool = AsyncMock()
        mock_pool.acquire_sticky = AsyncMock(return_value=MagicMock(id="cc-003"))

        async def mock_session_query(chat_id, prompt, **kw):
            return
            yield

        mock_pool.session_query = mock_session_query
        server._pool = mock_pool

        # Simulate expired route cleanup
        server.pool_routes["oc_old"] = PoolRoute(
            pool=mock_pool, chat_id="oc_old", instance_id="cc-001"
        )
        await server._on_pool_route_expired("oc_old")
        assert "oc_old" not in server.pool_routes

        # New message triggers fresh assignment
        await server.route_message("oc_old", {
            "type": "message", "text": "back again", "chat_id": "oc_old",
            "user": "Alice", "source": "feishu"
        })

        assert "oc_old" in server.pool_routes
        assert server.pool_routes["oc_old"].instance_id == "cc-003"
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/test_pool_routing_e2e.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_pool_routing_e2e.py
git commit -m "test: add pool routing integration tests"
```

---

### Task 7: Restart and verify in production

**Step 1: Kill orphan pool instances from old make pool-start**

```bash
# Kill old standalone pool instances (from make pool-start)
kill <PID_12267> <PID_43376> 2>/dev/null
```

**Step 2: Restart channel_server**

```bash
kill <current_channel_server_pid>
nohup uv run python3 channels/feishu/channel_server.py > .autoservice/logs/channel_server.log 2>&1 &
```

**Step 3: Verify pool_mode startup**

```bash
grep -E 'pool_mode|Pool started|Pool assigned' .autoservice/logs/channel_server.log | tail -10
```

Expected:
```
Loaded pool_mode=True from .../config.local.yaml
CC Pool started in pool_mode (min=1, max=4)
Channel-Server online (pool_mode)
```

**Step 4: Verify no extra channel.py from pool**

```bash
ps aux | grep 'channel.py' | grep -v grep
```

Expected: only the current MCP server's channel.py, NOT pool-spawned ones.

**Step 5: Send test message from Feishu and verify pool routing**

```bash
grep 'Pool assigned\|Pool routing' .autoservice/logs/channel_server.log | tail -5
```

Expected: `Pool assigned: chat_id=oc_xxx -> cc-001`

**Step 6: Check pool status**

```bash
make pool-status
```

Expected: query count > 0, sticky count > 0.

**Step 7: Final commit**

```bash
git add -A
git commit -m "feat: pool route integration — pool_mode coexists with WebSocket routing"
```
