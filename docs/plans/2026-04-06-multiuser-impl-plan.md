# Multi-User Channel Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the channel-server multi-instance message router and unify Web + Feishu channels under a single architecture.

**Architecture:** A standalone `channel-server.py` daemon owns the Feishu WebSocket connection and a local WebSocket server (:9999). Multiple `channel.py` MCP instances (and `web/app.py`) connect as clients, register chat_ids, and receive routed messages. Replies flow back through channel-server for delivery to Feishu or Web.

**Tech Stack:** Python 3.11+, `websockets` (already installed via lark-oapi), `lark_oapi`, `asyncio`, `mcp`, FastAPI

**Design Docs:**
- `docs/plans/2026-04-06-channel-server-design.md` — routing, protocol, admin group
- `docs/plans/2026-04-06-web-integration-design.md` — web integration, mode taxonomy, migration phases

---

## Phase 1: channel-server.py Core

### Task 1.1: Scaffold channel-server.py with local WebSocket server

**Files:**
- Create: `feishu/channel-server.py`
- Create: `tests/test_channel_server.py`

**Step 1: Write the failing test**

```python
# tests/test_channel_server.py
"""Tests for channel-server.py — local WebSocket server + routing."""
import asyncio
import json
import pytest
import websockets

SERVER_PORT = 19999  # test port to avoid conflicts

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
async def test_server_accepts_connection():
    """channel-server local WS server accepts a client connection."""
    from feishu.channel_server import ChannelServer
    server = ChannelServer(port=SERVER_PORT, feishu_enabled=False)
    task = asyncio.create_task(server.start())
    await asyncio.sleep(0.2)
    try:
        async with websockets.connect(f"ws://localhost:{SERVER_PORT}") as ws:
            assert ws.open
    finally:
        server.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/h2oslabs/Workspace/AutoService-Cinnox/.claude/worktrees/feat-multiuser-mode && uv run pytest tests/test_channel_server.py::test_server_accepts_connection -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'feishu.channel_server'`

**Step 3: Write minimal implementation**

```python
# feishu/channel-server.py
"""
channel-server: standalone daemon — Feishu WS + local WS router.

Owns the Feishu WebSocket connection, accepts channel.py / web/app.py
registrations, and routes messages by chat_id.

Dependencies: websockets, lark_oapi, asyncio (no MCP, no claude_agent_sdk).
"""
import asyncio
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import websockets
from websockets.server import ServerConnection

# -- Config -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = PROJECT_ROOT / ".autoservice" / "channel-server.log"
CREDENTIALS_PATH = PROJECT_ROOT / ".feishu-credentials.json"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[channel-server] %(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("channel-server")


# -- Data structures ----------------------------------------------------------

@dataclass
class Instance:
    """A registered channel.py or web/app.py connection."""
    ws: ServerConnection
    instance_id: str
    role: str                          # "developer", "production", "web"
    chat_ids: list[str] = field(default_factory=list)
    runtime_mode: str = "production"   # "production" | "improve"
    business_mode: str | None = None   # "sales" | "support" | None
    connected_at: str = ""


# -- Server -------------------------------------------------------------------

class ChannelServer:
    def __init__(
        self,
        port: int = 9999,
        admin_chat_id: str = "",
        feishu_enabled: bool = True,
    ):
        self.port = port
        self.admin_chat_id = admin_chat_id
        self.feishu_enabled = feishu_enabled

        # Route tables
        self.exact_routes: dict[str, Instance] = {}     # chat_id -> Instance
        self.prefix_routes: dict[str, Instance] = {}    # prefix -> Instance (e.g. "web_")
        self.wildcard_instances: list[Instance] = []
        self.instances: dict[ServerConnection, Instance] = {}  # ws -> Instance

        # Feishu state (populated by setup_feishu)
        self._feishu_client = None
        self._bot_open_id: str | None = None
        self._seen: set[str] = set()
        self._recent_sent: set[str] = set()
        self._user_cache: dict[str, str] = {}

        self._server = None
        self._stop_event = asyncio.Event()

    # -- WebSocket server -----------------------------------------------------

    async def _handle_client(self, ws: ServerConnection):
        """Handle a single client connection lifecycle."""
        instance: Instance | None = None
        try:
            async for raw in ws:
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "register":
                    instance = await self._handle_register(ws, msg)
                elif msg_type == "message":
                    # Inbound message from web/app.py — route to channel.py
                    # (Review fix I3: web sends type=message that needs routing)
                    await self.route_message(msg.get("chat_id", ""), msg)
                elif msg_type == "reply":
                    await self._handle_reply(msg)
                elif msg_type == "react":
                    await self._handle_react(msg)
                elif msg_type == "ux_event":
                    await self._forward_ux_event(msg)
                elif msg_type == "pong":
                    pass  # heartbeat response
                else:
                    log.warning(f"Unknown message type: {msg_type}")
        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            log.error(f"Client handler error: {e}")
        finally:
            if instance:
                self._unregister(instance)

    async def _handle_register(self, ws, msg: dict) -> Instance:
        """Process a register message, update route tables."""
        chat_ids = msg.get("chat_ids", [])
        instance_id = msg.get("instance_id", "unknown")
        role = msg.get("role", "production")
        runtime_mode = msg.get("runtime_mode", "production")
        business_mode = msg.get("business_mode")

        # Check for conflicts on exact chat_ids
        for cid in chat_ids:
            if cid == "*":
                continue
            if cid in self.exact_routes:
                existing = self.exact_routes[cid]
                error_msg = {
                    "type": "error",
                    "code": "REGISTRATION_CONFLICT",
                    "message": f"chat_id {cid} already registered by {existing.instance_id}",
                }
                await ws.send(json.dumps(error_msg))
                raise ValueError(f"Registration conflict: {cid}")

        instance = Instance(
            ws=ws,
            instance_id=instance_id,
            role=role,
            chat_ids=chat_ids,
            runtime_mode=runtime_mode,
            business_mode=business_mode,
            connected_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        self.instances[ws] = instance

        for cid in chat_ids:
            if cid == "*":
                self.wildcard_instances.append(instance)
            elif cid.endswith("*"):
                # Prefix pattern like "web_*" -> store prefix "web_"
                self.prefix_routes[cid[:-1]] = instance
            else:
                self.exact_routes[cid] = instance

        await ws.send(json.dumps({"type": "registered", "chat_ids": chat_ids}))
        log.info(f"Registered: {instance_id} chat_ids={chat_ids} mode={runtime_mode}")

        # Admin notification
        await self._admin_notify(
            f"🟢 Instance connected: {', '.join(chat_ids)} ({instance_id})"
        )
        return instance

    def _unregister(self, instance: Instance):
        """Remove an instance from all route tables."""
        for cid in instance.chat_ids:
            if cid == "*":
                if instance in self.wildcard_instances:
                    self.wildcard_instances.remove(instance)
            elif cid.endswith("*"):
                prefix = cid[:-1]
                if self.prefix_routes.get(prefix) is instance:
                    del self.prefix_routes[prefix]
            else:
                if self.exact_routes.get(cid) is instance:
                    del self.exact_routes[cid]

        self.instances.pop(instance.ws, None)
        log.info(f"Unregistered: {instance.instance_id} chat_ids={instance.chat_ids}")

        # Fire-and-forget admin notification
        asyncio.ensure_future(self._admin_notify(
            f"🔴 Instance disconnected: {', '.join(instance.chat_ids)} ({instance.instance_id})"
        ))

    # -- Message routing ------------------------------------------------------

    async def route_message(self, chat_id: str, message: dict):
        """Route a message to the appropriate instance(s)."""
        routed = False
        routed_instance: Instance | None = None

        # 1. Exact match
        if chat_id in self.exact_routes:
            inst = self.exact_routes[chat_id]
            await self._send_to(inst, message)
            routed = True
            routed_instance = inst

        # 2. Prefix match
        if not routed:
            for prefix, inst in self.prefix_routes.items():
                if chat_id.startswith(prefix):
                    await self._send_to(inst, message)
                    routed = True
                    routed_instance = inst
                    break

        # 3. Wildcard — always receives a copy (deduplicated)
        for inst in self.wildcard_instances:
            if routed and inst is routed_instance:
                continue  # avoid double-send
            # Add routed_to hint for wildcard instances
            copy = dict(message)
            if routed_instance:
                copy["routed_to"] = routed_instance.instance_id
            await self._send_to(inst, copy)

        # 4. No match + no wildcard = message dropped
        if not routed and not self.wildcard_instances:
            log.warning(f"No route for {chat_id}, message dropped")

    async def _send_to(self, instance: Instance, message: dict):
        """Send a JSON message to an instance's WebSocket."""
        try:
            await instance.ws.send(json.dumps(message, ensure_ascii=False))
        except websockets.ConnectionClosed:
            log.warning(f"Send failed (closed): {instance.instance_id}")

    # -- Reply reverse routing ------------------------------------------------

    async def _handle_reply(self, msg: dict):
        """Route a reply back to the originating channel."""
        chat_id = msg.get("chat_id", "")
        text = msg.get("text", "")

        if chat_id.startswith("oc_"):
            await self._feishu_send(chat_id, text)
        elif chat_id.startswith("web_"):
            await self._web_relay_reply(chat_id, text)
        else:
            log.warning(f"Unknown reply target prefix: {chat_id}")

    async def _feishu_send(self, chat_id: str, text: str):
        """Send a message to Feishu chat via API."""
        if not self._feishu_client:
            log.error("Feishu client not initialized, cannot send reply")
            return
        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )
            body = (
                CreateMessageRequestBody.builder()
                .receive_id(chat_id).msg_type("text")
                .content(json.dumps({"text": text})).build()
            )
            req = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(body).build()
            )
            resp = self._feishu_client.im.v1.message.create(req)
            if resp.success():
                self._recent_sent.add(resp.data.message_id)
                log.info(f"Reply to {chat_id}: {text[:50]}...")
                # CRM log outgoing
                try:
                    from autoservice.crm import log_message
                    log_message("bot", chat_id, "out", text)
                except Exception:
                    pass
            else:
                log.error(f"Feishu reply failed: {resp.code} {resp.msg}")
        except Exception as e:
            log.error(f"Feishu send error: {e}")

    async def _web_relay_reply(self, chat_id: str, text: str):
        """Forward a reply to the web/app.py connection that owns this chat_id."""
        reply_msg = {"type": "reply", "chat_id": chat_id, "text": text}
        # Find the instance (exact or prefix) that registered this web chat_id
        target = self.exact_routes.get(chat_id)
        if not target:
            for prefix, inst in self.prefix_routes.items():
                if chat_id.startswith(prefix):
                    target = inst
                    break
        if target:
            await self._send_to(target, reply_msg)
        else:
            log.warning(f"No web route for reply: {chat_id}")

    # -- React reverse routing ------------------------------------------------

    async def _handle_react(self, msg: dict):
        """Add emoji reaction to a Feishu message."""
        message_id = msg.get("message_id", "")
        emoji_type = msg.get("emoji_type", "THUMBSUP")
        if not self._feishu_client or not message_id:
            return
        try:
            import lark_oapi as lark
            req = (
                lark.BaseRequest.builder()
                .http_method(lark.HttpMethod.POST)
                .uri(f"/open-apis/im/v1/messages/{message_id}/reactions")
                .token_types({lark.AccessTokenType.TENANT})
                .body({"reaction_type": {"emoji_type": emoji_type}})
                .build()
            )
            self._feishu_client.request(req)
        except Exception as e:
            log.debug(f"React error: {e}")

    # -- UX event forwarding --------------------------------------------------

    async def _forward_ux_event(self, msg: dict):
        """Forward a ux_event from channel.py to the web/app.py that owns the chat_id."""
        chat_id = msg.get("chat_id", "")
        if not chat_id.startswith("web_"):
            return  # only web needs UX events
        target = self.exact_routes.get(chat_id)
        if not target:
            for prefix, inst in self.prefix_routes.items():
                if chat_id.startswith(prefix):
                    target = inst
                    break
        if target:
            await self._send_to(target, msg)

    # -- Admin group ----------------------------------------------------------

    async def _admin_notify(self, text: str):
        """Send a notification to the admin Feishu group."""
        if not self.admin_chat_id or not self._feishu_client:
            log.info(f"[admin] {text}")
            return
        await self._feishu_send(self.admin_chat_id, text)

    # -- Heartbeat ------------------------------------------------------------

    async def _heartbeat_loop(self):
        """Send ping to all connected instances every 30s."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=30)
                break
            except asyncio.TimeoutError:
                pass
            ping = json.dumps({"type": "ping"})
            for ws, inst in list(self.instances.items()):
                try:
                    await ws.send(ping)
                except websockets.ConnectionClosed:
                    pass

    # -- /status command ------------------------------------------------------

    def status_text(self) -> str:
        """Build a human-readable status string."""
        lines = [f"Channel-Server Status ({len(self.instances)} instances)"]
        for inst in self.instances.values():
            elapsed = ""
            if inst.connected_at:
                try:
                    dt = datetime.fromisoformat(inst.connected_at)
                    mins = int((datetime.now(tz=timezone.utc) - dt).total_seconds() / 60)
                    elapsed = f" ({mins}m)"
                except Exception:
                    pass
            lines.append(
                f"  {inst.instance_id}: chat_ids={inst.chat_ids} "
                f"runtime={inst.runtime_mode}{elapsed}"
            )
        if not self.instances:
            lines.append("  (no instances connected)")
        return "\n".join(lines)

    # -- Lifecycle ------------------------------------------------------------

    async def start(self):
        """Start the local WebSocket server (and optionally Feishu WS)."""
        log.info(f"Starting channel-server on :{self.port}")
        self._server = await websockets.serve(
            self._handle_client,
            "localhost",
            self.port,
        )
        log.info(f"Local WS server listening on ws://localhost:{self.port}")

        tasks = [self._heartbeat_loop()]

        if self.feishu_enabled:
            tasks.append(self._run_feishu())

        await self._admin_notify("✅ Channel-Server online")

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

    def stop(self):
        """Signal the server to stop."""
        self._stop_event.set()
        if self._server:
            self._server.close()

    # -- Feishu integration (placeholder — filled in Task 1.2) ----------------

    async def _run_feishu(self):
        """Placeholder for Feishu WebSocket integration."""
        await self._stop_event.wait()


# -- Entry point --------------------------------------------------------------

def main():
    port = int(os.environ.get("CHANNEL_SERVER_PORT", "9999"))
    admin_chat_id = os.environ.get("ADMIN_CHAT_ID", "")
    feishu_enabled = os.environ.get("FEISHU_ENABLED", "1") != "0"

    server = ChannelServer(
        port=port,
        admin_chat_id=admin_chat_id,
        feishu_enabled=feishu_enabled,
    )

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, server.stop)

    try:
        loop.run_until_complete(server.start())
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        loop.run_until_complete(server._server.wait_closed() if server._server else asyncio.sleep(0))
        loop.close()


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/h2oslabs/Workspace/AutoService-Cinnox/.claude/worktrees/feat-multiuser-mode && uv run pytest tests/test_channel_server.py::test_server_accepts_connection -v`
Expected: PASS

**Step 5: Commit**

```bash
git add feishu/channel-server.py tests/test_channel_server.py
git commit -m "feat: scaffold channel-server.py with local WebSocket server"
```

---

### Task 1.2: Registration protocol + route table

**Files:**
- Modify: `feishu/channel-server.py` (Task 1.1 code already includes this)
- Test: `tests/test_channel_server.py`

**Step 1: Write the failing test**

```python
# tests/test_channel_server.py — append

@pytest.mark.asyncio
async def test_register_and_route():
    """Register an instance with chat_ids, then route a message to it."""
    from feishu.channel_server import ChannelServer
    server = ChannelServer(port=SERVER_PORT, feishu_enabled=False)
    task = asyncio.create_task(server.start())
    await asyncio.sleep(0.2)
    try:
        async with websockets.connect(f"ws://localhost:{SERVER_PORT}") as ws:
            # Register
            await ws.send(json.dumps({
                "type": "register",
                "role": "production",
                "chat_ids": ["oc_test123"],
                "instance_id": "test-instance-1",
                "runtime_mode": "production",
            }))
            resp = json.loads(await ws.recv())
            assert resp["type"] == "registered"
            assert resp["chat_ids"] == ["oc_test123"]

            # Route a message from server side
            await server.route_message("oc_test123", {
                "type": "message",
                "chat_id": "oc_test123",
                "text": "hello",
            })
            routed = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            assert routed["type"] == "message"
            assert routed["text"] == "hello"
    finally:
        server.stop()
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass


@pytest.mark.asyncio
async def test_wildcard_receives_copy():
    """Wildcard instance receives a copy of messages routed to specific instances."""
    from feishu.channel_server import ChannelServer
    server = ChannelServer(port=SERVER_PORT, feishu_enabled=False)
    task = asyncio.create_task(server.start())
    await asyncio.sleep(0.2)
    try:
        async with websockets.connect(f"ws://localhost:{SERVER_PORT}") as ws_specific, \
                     websockets.connect(f"ws://localhost:{SERVER_PORT}") as ws_wildcard:
            # Register specific
            await ws_specific.send(json.dumps({
                "type": "register", "role": "production",
                "chat_ids": ["oc_aaa"], "instance_id": "specific-1",
            }))
            await ws_specific.recv()  # registered

            # Register wildcard
            await ws_wildcard.send(json.dumps({
                "type": "register", "role": "developer",
                "chat_ids": ["*"], "instance_id": "dev-0",
            }))
            await ws_wildcard.recv()  # registered

            # Route
            await server.route_message("oc_aaa", {
                "type": "message", "chat_id": "oc_aaa", "text": "test",
            })

            msg_specific = json.loads(await asyncio.wait_for(ws_specific.recv(), timeout=2))
            msg_wildcard = json.loads(await asyncio.wait_for(ws_wildcard.recv(), timeout=2))

            assert msg_specific["text"] == "test"
            assert "routed_to" not in msg_specific  # exact match, no hint
            assert msg_wildcard["text"] == "test"
            assert msg_wildcard["routed_to"] == "specific-1"  # hint for wildcard
    finally:
        server.stop()
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass


@pytest.mark.asyncio
async def test_registration_conflict():
    """Second registration for the same chat_id is rejected."""
    from feishu.channel_server import ChannelServer
    server = ChannelServer(port=SERVER_PORT, feishu_enabled=False)
    task = asyncio.create_task(server.start())
    await asyncio.sleep(0.2)
    try:
        async with websockets.connect(f"ws://localhost:{SERVER_PORT}") as ws1, \
                     websockets.connect(f"ws://localhost:{SERVER_PORT}") as ws2:
            await ws1.send(json.dumps({
                "type": "register", "chat_ids": ["oc_conflict"],
                "instance_id": "inst-1", "role": "production",
            }))
            await ws1.recv()

            await ws2.send(json.dumps({
                "type": "register", "chat_ids": ["oc_conflict"],
                "instance_id": "inst-2", "role": "production",
            }))
            resp = json.loads(await ws2.recv())
            assert resp["type"] == "error"
            assert resp["code"] == "REGISTRATION_CONFLICT"
    finally:
        server.stop()
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
```

**Step 2: Run tests**

Run: `cd /Users/h2oslabs/Workspace/AutoService-Cinnox/.claude/worktrees/feat-multiuser-mode && uv run pytest tests/test_channel_server.py -v`
Expected: PASS (all routing logic is already in Task 1.1 scaffold)

**Step 3: Commit**

```bash
git add tests/test_channel_server.py
git commit -m "test: registration protocol and route table tests"
```

---

### Task 1.3: Feishu WebSocket integration in channel-server.py

Migrate Feishu connection from `feishu/channel.py:197-396` into `channel-server.py`.

**Files:**
- Modify: `feishu/channel-server.py` — replace `_run_feishu` placeholder

**Step 1: Implement Feishu integration**

Replace the `_run_feishu` placeholder in `channel-server.py` with the following. This migrates:
- `load_credentials()` from `channel.py:60-69`
- `setup_feishu()` from `channel.py:197-335` (WebSocket handler, bot detection, dedup, text parsing)
- `_resolve_user()` from `channel.py:98-135` (user lookup + CRM upsert)
- `send_reaction()` from `channel.py:142-157` (ACK emoji)
- CRM logging from `channel.py:294-299`
- `/improve` and `/production` command interception from `channel.py:265-292`
- `send_startup()` from `channel.py:338-396`

Key changes from original:
- `mode` field renamed: `"service"` → `"production"` in runtime_mode, business_mode defaults to `"sales"`
- `/service` command renamed to `/production`
- After parsing, calls `self.route_message(chat_id, msg)` instead of putting into a queue
- `send_reaction()` called directly (was already fire-and-forget)

```python
# Add to ChannelServer class — replaces the _run_feishu placeholder

def _load_credentials(self) -> tuple[str, str]:
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if app_id and app_secret:
        return app_id, app_secret
    if CREDENTIALS_PATH.exists():
        creds = json.loads(CREDENTIALS_PATH.read_text())
        return creds["app_id"], creds["app_secret"]
    log.error("Missing Feishu credentials")
    sys.exit(1)

def _resolve_user(self, open_id: str) -> str:
    if open_id in self._user_cache:
        return self._user_cache[open_id]
    name = ""
    try:
        import lark_oapi as lark
        req = (
            lark.BaseRequest.builder()
            .http_method(lark.HttpMethod.GET)
            .uri(f"/open-apis/contact/v3/users/{open_id}?user_id_type=open_id")
            .token_types({lark.AccessTokenType.TENANT})
            .build()
        )
        resp = self._feishu_client.request(req)
        if resp.success():
            user_data = json.loads(resp.raw.content).get("data", {}).get("user", {})
            name = user_data.get("name", "")
            try:
                from autoservice.crm import upsert_contact
                upsert_contact(
                    open_id=open_id, name=name,
                    phone=user_data.get("mobile", ""),
                    email=user_data.get("email", ""),
                    department=(user_data.get("department_ids", [""])[0]
                                if user_data.get("department_ids") else ""),
                    job_title=user_data.get("job_title", ""),
                )
            except Exception as e:
                log.debug(f"CRM upsert error: {e}")
    except Exception as e:
        log.debug(f"User lookup error for {open_id}: {e}")
    display = f"{name} ({open_id[:12]})" if name else open_id
    self._user_cache[open_id] = display
    return display

def _send_reaction(self, message_id: str, emoji_type: str = "OnIt"):
    import threading
    def _do():
        try:
            import lark_oapi as lark
            req = (
                lark.BaseRequest.builder()
                .http_method(lark.HttpMethod.POST)
                .uri(f"/open-apis/im/v1/messages/{message_id}/reactions")
                .token_types({lark.AccessTokenType.TENANT})
                .body({"reaction_type": {"emoji_type": emoji_type}})
                .build()
            )
            self._feishu_client.request(req)
        except Exception:
            pass
    threading.Thread(target=_do, daemon=True).start()

async def _run_feishu(self):
    """Initialize Feishu WS client, process inbound messages."""
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

    app_id, app_secret = self._load_credentials()
    self._feishu_client = (
        lark.Client.builder()
        .app_id(app_id).app_secret(app_secret)
        .log_level(lark.LogLevel.WARNING).build()
    )

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    # Track which chat_ids are "new" (first message)
    known_chat_ids: set[str] = set()

    def on_message(data: P2ImMessageReceiveV1):
        event = data.event
        sender = event.sender
        message = event.message
        sender_id = sender.sender_id.open_id if sender.sender_id else ""
        sender_type = sender.sender_type or "user"

        # Bot detection
        if sender_type == "app" and not self._bot_open_id:
            self._bot_open_id = sender_id
        if sender_type == "app" or (self._bot_open_id and sender_id == self._bot_open_id):
            return

        msg_id = message.message_id or ""
        if msg_id in self._seen or msg_id in self._recent_sent:
            return
        self._seen.add(msg_id)

        # ACK reaction
        self._send_reaction(msg_id)

        # Parse text
        text = ""
        msg_type = message.message_type or "text"
        if msg_type == "text":
            try:
                text = json.loads(message.content or "{}").get("text", "")
            except Exception:
                pass
        elif msg_type == "post":
            try:
                parsed = json.loads(message.content or "{}")
                parts = [parsed.get("title", "")]
                for para in parsed.get("content", []):
                    for node in para or []:
                        if node.get("text"):
                            parts.append(node["text"])
                text = " ".join(p for p in parts if p)
            except Exception:
                pass
        if not text:
            text = f"({msg_type} message)"

        chat_id = message.chat_id or ""
        ts = datetime.now(tz=timezone.utc).isoformat()
        if message.create_time:
            try:
                ts = datetime.fromtimestamp(
                    int(message.create_time) / 1000, tz=timezone.utc
                ).isoformat()
            except Exception:
                pass

        display_name = self._resolve_user(sender_id)

        # Runtime mode switching: /improve, /production
        text_stripped = text.strip().lower()
        if text_stripped in ("/improve", "/production"):
            new_mode = "improve" if text_stripped == "/improve" else "production"
            self._send_reaction(msg_id, "DONE")
            # Update runtime_mode for the instance handling this chat_id
            # (The mode switch message is still routed so channel.py sees it)
            switch_text = (
                f"[MODE SWITCH] Switched to {new_mode} mode."
                if new_mode == "improve"
                else "[MODE SWITCH] Switched to production mode."
            )
            msg_dict = {
                "type": "message", "chat_id": chat_id, "message_id": msg_id,
                "user": display_name, "user_id": sender_id,
                "text": switch_text, "ts": ts,
                "source": "feishu", "runtime_mode": new_mode,
                "business_mode": "sales",
            }
            loop.call_soon_threadsafe(queue.put_nowait, msg_dict)
            return

        # CRM logging
        try:
            from autoservice.crm import increment_message_count, log_message
            increment_message_count(sender_id)
            log_message(sender_id, chat_id, "in", text, ts)
        except Exception:
            pass

        # New user notification
        is_new = chat_id not in known_chat_ids
        if is_new:
            known_chat_ids.add(chat_id)

        msg_dict = {
            "type": "message", "chat_id": chat_id, "message_id": msg_id,
            "user": display_name, "user_id": sender_id,
            "text": text, "ts": ts,
            "source": "feishu",
            "runtime_mode": "production",
            "business_mode": "sales",
        }
        if is_new:
            msg_dict["_new_user"] = True

        loop.call_soon_threadsafe(queue.put_nowait, msg_dict)

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    ws_client = lark.ws.Client(
        app_id=app_id, app_secret=app_secret,
        event_handler=handler, log_level=lark.LogLevel.WARNING,
    )

    import threading
    threading.Thread(target=ws_client.start, daemon=True).start()
    log.info("Feishu WS thread started")

    # Process queue
    while not self._stop_event.is_set():
        try:
            msg_dict = await asyncio.wait_for(queue.get(), timeout=1)
        except asyncio.TimeoutError:
            continue

        # Admin group: handle commands
        if msg_dict["chat_id"] == self.admin_chat_id:
            await self._handle_admin_message(msg_dict)
            continue

        # New user notification
        if msg_dict.pop("_new_user", False):
            chat_id = msg_dict["chat_id"]
            user = msg_dict.get("user", "unknown")
            await self._admin_notify(
                f"🆕 New user: {user} ({chat_id})\n"
                f"Start instance: `./claude.sh {chat_id}`"
            )

        await self.route_message(msg_dict["chat_id"], msg_dict)

async def _handle_admin_message(self, msg: dict):
    """Handle commands sent in the admin group."""
    text = msg.get("text", "").strip()
    if text == "/status":
        await self._feishu_send(self.admin_chat_id, self.status_text())
    elif text.startswith("/inject "):
        # /inject oc_aaa some text here
        parts = text[len("/inject "):].split(" ", 1)
        if len(parts) == 2:
            target_chat_id, inject_text = parts
            inject_msg = dict(msg)
            inject_msg["chat_id"] = target_chat_id
            inject_msg["text"] = inject_text
            inject_msg["source"] = "admin_inject"
            await self.route_message(target_chat_id, inject_msg)
            await self._admin_notify(f"Injected to {target_chat_id}: {inject_text[:60]}")
```

**Step 2: Run existing tests (they should still pass — feishu_enabled=False in tests)**

Run: `cd /Users/h2oslabs/Workspace/AutoService-Cinnox/.claude/worktrees/feat-multiuser-mode && uv run pytest tests/test_channel_server.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add feishu/channel-server.py
git commit -m "feat: migrate Feishu WS + user resolution + CRM into channel-server"
```

---

### Task 1.4: Makefile target + add websockets to pyproject.toml

**Files:**
- Modify: `Makefile:1-42`
- Modify: `pyproject.toml:9-23`

**Step 1: Add run-server target to Makefile**

After `.PHONY` line, add `run-server`. After `run-web:` block, add:

```makefile
run-server:
	uv run python3 feishu/channel-server.py
```

**Step 2: Add websockets to pyproject.toml dependencies**

`websockets` is already installed (pulled in by lark-oapi), but add it as an explicit dependency since channel-server.py uses it directly:

```toml
dependencies = [
    ...
    "websockets>=13.0",
    ...
]
```

**Step 3: Commit**

```bash
git add Makefile pyproject.toml
git commit -m "chore: add run-server target and websockets dependency"
```

---

## Phase 2: channel.py Refactor

### Task 2.1: Replace Feishu WS with channel-server WS client

Gut the Feishu WebSocket code from `channel.py` and replace with a WebSocket client that connects to channel-server.py.

**Files:**
- Modify: `feishu/channel.py:1-574`
- Test: `tests/test_channel_client.py`

**Step 1: Write the failing test**

```python
# tests/test_channel_client.py
"""Tests for channel.py as a channel-server WebSocket client."""
import asyncio
import json
import pytest
import websockets

SERVER_PORT = 19998


@pytest.mark.asyncio
async def test_channel_connects_and_registers():
    """channel.py connects to channel-server and sends register message."""
    registered = asyncio.Event()
    received_register = {}

    async def mock_server(ws):
        nonlocal received_register
        msg = json.loads(await ws.recv())
        received_register = msg
        await ws.send(json.dumps({"type": "registered", "chat_ids": msg["chat_ids"]}))
        registered.set()
        # Keep connection alive
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass

    server = await websockets.serve(mock_server, "localhost", SERVER_PORT)
    try:
        from feishu.channel import ChannelClient
        client = ChannelClient(
            server_url=f"ws://localhost:{SERVER_PORT}",
            chat_ids=["oc_test"],
            instance_id="test-inst",
            runtime_mode="production",
        )
        task = asyncio.create_task(client.connect())
        await asyncio.wait_for(registered.wait(), timeout=5)

        assert received_register["type"] == "register"
        assert received_register["chat_ids"] == ["oc_test"]
        assert received_register["instance_id"] == "test-inst"

        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
    finally:
        server.close()
        await server.wait_closed()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/h2oslabs/Workspace/AutoService-Cinnox/.claude/worktrees/feat-multiuser-mode && uv run pytest tests/test_channel_client.py::test_channel_connects_and_registers -v`
Expected: FAIL — `ImportError: cannot import name 'ChannelClient'`

**Step 3: Refactor channel.py**

This is the largest code change. The new `channel.py` structure:

1. **Remove** (migrated to channel-server.py):
   - `load_credentials()` (lines 60-69)
   - `feishu_client` initialization (lines 76-82)
   - All Feishu state: `_seen`, `_recent_sent`, `_bot_open_id`, `_user_cache`, `_chat_modes` (lines 86-96)
   - `_resolve_user()` (lines 98-135)
   - `send_reaction()` (lines 142-157)
   - `setup_feishu()` + `on_message` callback (lines 197-335)
   - `send_startup()` (lines 338-396)
   - All `import lark_oapi`, `import requests` for Feishu

2. **Add** new `ChannelClient` class:
   - WebSocket client connecting to `ws://localhost:{port}`
   - Auto-reconnect with exponential backoff
   - Sends `register` on connect
   - Receives `message` → injects into MCP write_stream (reuses existing `inject_message`)
   - Sends `reply`/`react` to channel-server instead of Feishu API

3. **Keep unchanged**:
   - MCP server setup (`create_server`, `register_tools`, Tool definitions)
   - `poll_feishu_queue()` → rename to `poll_message_queue()`
   - Plugin tool loading
   - Instructions hot-reload
   - `_FALLBACK_INSTRUCTIONS`, `_refresh_instructions()`

4. **Modify**:
   - `inject_message()` (lines 162-180) → update meta to pass `runtime_mode` + `business_mode` instead of `mode` (Review fix C1)
   - `_handle_reply()` → sends JSON to channel-server WS instead of Feishu API
   - `_handle_react()` → sends JSON to channel-server WS instead of Feishu API
   - `main()` → reads `AUTOSERVICE_CHAT_ID` env var, creates `ChannelClient`, runs alongside MCP server

Updated `inject_message()` (Review fix C1 — mode field mismatch):

```python
async def inject_message(write_stream, msg: dict):
    """Send a channel notification to Claude Code via the MCP write stream."""
    notification = JSONRPCNotification(
        jsonrpc="2.0",
        method="notifications/claude/channel",
        params={
            "content": msg["text"],
            "meta": {
                "chat_id": msg["chat_id"],
                "message_id": msg.get("message_id", ""),
                "user": msg.get("user", "unknown"),
                "user_id": msg.get("user_id", ""),
                "runtime_mode": msg.get("runtime_mode", "production"),
                "business_mode": msg.get("business_mode", "sales"),
                "source": msg.get("source", "feishu"),
                "routed_to": msg.get("routed_to"),
                "ts": msg.get("ts", datetime.now(tz=timezone.utc).isoformat()),
            },
        },
    )
    await write_stream.send(SessionMessage(message=JSONRPCMessage(notification)))
    log.info(f"Injected: '{msg['text'][:60]}...' from {msg.get('user', '?')}")
```

Key new code for `ChannelClient`:

```python
class ChannelClient:
    """WebSocket client that connects to channel-server.py."""

    def __init__(
        self,
        server_url: str = "ws://localhost:9999",
        chat_ids: list[str] | None = None,
        instance_id: str = "",
        runtime_mode: str = "production",
    ):
        self.server_url = server_url
        self.chat_ids = chat_ids or ["*"]
        self.instance_id = instance_id or f"channel-{os.getpid()}"
        self.runtime_mode = runtime_mode
        self.ws: websockets.ClientConnection | None = None
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self):
        """Connect to channel-server with auto-reconnect."""
        while True:
            try:
                async with websockets.connect(self.server_url) as ws:
                    self.ws = ws
                    await self._register(ws)
                    await self._message_loop(ws)
            except (ConnectionRefusedError, websockets.ConnectionClosed) as e:
                log.warning(f"channel-server disconnected ({e}), retrying in 3s...")
                self.ws = None
                await asyncio.sleep(3)

    async def _register(self, ws):
        await ws.send(json.dumps({
            "type": "register",
            "role": "developer" if "*" in self.chat_ids else "production",
            "chat_ids": self.chat_ids,
            "instance_id": self.instance_id,
            "runtime_mode": self.runtime_mode,
        }))
        resp = json.loads(await ws.recv())
        if resp.get("type") == "error":
            log.error(f"Registration failed: {resp}")
            raise RuntimeError(resp.get("message", "Registration failed"))
        log.info(f"Registered: chat_ids={self.chat_ids}")

    async def _message_loop(self, ws):
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "message":
                await self._message_queue.put(msg)
            elif msg.get("type") == "ping":
                await ws.send(json.dumps({"type": "pong"}))
            elif msg.get("type") == "error":
                log.error(f"Server error: {msg}")

    async def send_reply(self, chat_id: str, text: str):
        if self.ws:
            await self.ws.send(json.dumps({
                "type": "reply", "chat_id": chat_id, "text": text,
            }))

    async def send_react(self, message_id: str, emoji_type: str):
        if self.ws:
            await self.ws.send(json.dumps({
                "type": "react", "message_id": message_id, "emoji_type": emoji_type,
            }))

    async def send_ux_event(self, chat_id: str, event: str, data: dict = None):
        if self.ws:
            await self.ws.send(json.dumps({
                "type": "ux_event", "chat_id": chat_id,
                "event": event, "data": data or {},
            }))
```

Modified `_handle_reply` and `_handle_react` (Review fix C3 — safe async boundary):

```python
# Module-level reference to the ChannelClient (set in main())
_channel_client: ChannelClient | None = None
_event_loop: asyncio.AbstractEventLoop | None = None  # set in main()

def _handle_reply(args: dict) -> list[TextContent]:
    chat_id = args["chat_id"]
    text = args["text"]
    if _channel_client and _channel_client.ws and _event_loop:
        # Use threadsafe call — MCP tool handlers may run from anyio context
        # (Review fix C3: asyncio.get_event_loop() is unsafe under anyio/Python 3.12+)
        asyncio.run_coroutine_threadsafe(
            _channel_client.send_reply(chat_id, text),
            _event_loop,
        )
        return [TextContent(type="text", text=f"Sent to {chat_id}")]
    return [TextContent(type="text", text="Error: not connected to channel-server")]

def _handle_react(args: dict) -> list[TextContent]:
    if _channel_client and _channel_client.ws and _event_loop:
        asyncio.run_coroutine_threadsafe(
            _channel_client.send_react(args["message_id"], args["emoji_type"]),
            _event_loop,
        )
        return [TextContent(type="text", text=f"Reacted {args['emoji_type']}")]
    return [TextContent(type="text", text="Error: not connected to channel-server")]
```

Modified `main()`:

```python
async def main():
    global _channel_client, _event_loop
    _event_loop = asyncio.get_running_loop()

    from autoservice.plugin_loader import discover
    plugins = discover("plugins")
    all_tools = []
    for p in plugins:
        all_tools.extend(p.tools)

    chat_id_str = os.environ.get("AUTOSERVICE_CHAT_ID", "*")
    chat_ids = [chat_id_str]  # single chat_id or wildcard
    server_port = os.environ.get("CHANNEL_SERVER_PORT", "9999")
    server_url = f"ws://localhost:{server_port}"

    _channel_client = ChannelClient(
        server_url=server_url,
        chat_ids=chat_ids,
        runtime_mode=os.environ.get("AUTOSERVICE_RUNTIME_MODE", "production"),
    )

    server = create_server()
    register_tools(server, all_tools)

    init_opts = InitializationOptions(
        server_name="autoservice-channel",
        server_version="1.0.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={"claude/channel": {}},
        ),
    )

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        async def consume_messages():
            """Consume messages from channel-server and inject into MCP."""
            while True:
                msg = await _channel_client._message_queue.get()
                try:
                    _refresh_instructions(server)
                    await inject_message(write_stream, msg)
                except Exception as e:
                    log.error(f"inject error: {e}")

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(server.run, read_stream, write_stream, init_opts)
                tg.start_soon(_channel_client.connect)
                tg.start_soon(consume_messages)
        except Exception as e:
            log.error(f"Task group error: {e}")
```

**Step 4: Run tests**

Run: `cd /Users/h2oslabs/Workspace/AutoService-Cinnox/.claude/worktrees/feat-multiuser-mode && uv run pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add feishu/channel.py tests/test_channel_client.py
git commit -m "feat: refactor channel.py — replace Feishu WS with channel-server client"
```

---

## Phase 3: Web Integration

### Task 3.1: Rewrite websocket.py as multiplexed channel-server relay

> **Review fix C2:** web/app.py uses ONE persistent WebSocket connection to channel-server
> (registered with `chat_ids=["web_*"]`), and multiplexes all browser sessions over it.
> This matches the architecture diagram and avoids per-session connection exhaustion.
>
> **Review fix I2:** Includes automated tests for the web relay path.

**Files:**
- Modify: `web/websocket.py:1-520` — full rewrite
- Create: `tests/test_web_relay.py`

**Step 1: Write new websocket.py**

The new `websocket.py` has two layers:
1. `WebChannelBridge` — singleton that owns ONE WS connection to channel-server, registers `web_*`, demuxes replies by chat_id
2. `ws_chat()` — per-browser handler that authenticates, creates a chat_id, and relays through the bridge

```python
# web/websocket.py — NEW (multiplexed relay, Review fix C2)
"""
WebSocket handlers — browser ↔ channel-server relay.

/ws       — raw debug (kept for backwards compat, optional)
/ws/chat  — authenticated relay through channel-server.py

Architecture (Review fix C2):
  web/app.py opens ONE persistent connection to channel-server, registers web_*.
  Each browser session gets a unique chat_id (web_{session_id}).
  WebChannelBridge multiplexes all sessions over the single connection.
  Replies include chat_id for demuxing back to the correct browser.
"""
import asyncio
import json
from datetime import datetime

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from web import auth
from web import session_persistence as sessions


# ── Configuration ─────────────────────────────────────────────────────────
CHANNEL_SERVER_URL: str = "ws://localhost:9999"


def configure(channel_server_url: str = "ws://localhost:9999") -> None:
    global CHANNEL_SERVER_URL
    CHANNEL_SERVER_URL = channel_server_url


# ── Singleton bridge to channel-server (Review fix C2) ───────────────────

class WebChannelBridge:
    """Single persistent WS connection to channel-server, multiplexing all web sessions."""

    def __init__(self):
        self._ws: websockets.ClientConnection | None = None
        self._subscribers: dict[str, asyncio.Queue] = {}  # chat_id -> reply queue
        self._connected = asyncio.Event()
        self._recv_task: asyncio.Task | None = None

    async def ensure_connected(self):
        """Connect to channel-server if not already connected."""
        if self._ws and self._connected.is_set():
            return
        self._ws = await websockets.connect(CHANNEL_SERVER_URL)
        await self._ws.send(json.dumps({
            "type": "register",
            "role": "web",
            "chat_ids": ["web_*"],
            "instance_id": "web-app",
            "runtime_mode": "production",
        }))
        resp = json.loads(await self._ws.recv())
        if resp.get("type") == "error":
            raise RuntimeError(resp.get("message", "Registration failed"))
        self._connected.set()
        if self._recv_task is None or self._recv_task.done():
            self._recv_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self):
        """Receive messages from channel-server and dispatch to subscribers by chat_id."""
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                msg_type = msg.get("type")
                chat_id = msg.get("chat_id", "")
                if msg_type in ("reply", "ux_event") and chat_id in self._subscribers:
                    await self._subscribers[chat_id].put(msg)
                elif msg_type == "ping":
                    await self._ws.send(json.dumps({"type": "pong"}))
        except websockets.ConnectionClosed:
            self._connected.clear()
            self._ws = None
            for q in self._subscribers.values():
                await q.put({"type": "error", "text": "Channel server disconnected"})

    def subscribe(self, chat_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[chat_id] = q
        return q

    def unsubscribe(self, chat_id: str):
        self._subscribers.pop(chat_id, None)

    async def send_message(self, msg: dict):
        if self._ws and self._connected.is_set():
            await self._ws.send(json.dumps(msg, ensure_ascii=False))


_bridge: WebChannelBridge | None = None

async def _get_bridge() -> WebChannelBridge:
    global _bridge
    if _bridge is None:
        _bridge = WebChannelBridge()
    await _bridge.ensure_connected()
    return _bridge


# ── Generic debug handler (unchanged) ────────────────────────────────────
async def ws_generic(websocket: WebSocket):
    """Generic /ws handler — kept for debug, not connected to channel-server."""
    await websocket.accept()
    await websocket.send_json({"type": "error", "content": "Debug endpoint. Use /ws/chat."})
    await websocket.close()


# ── Authenticated relay handler ──────────────────────────────────────────
async def ws_chat(websocket: WebSocket):
    """Authenticated /ws/chat — relay between browser and channel-server."""
    await websocket.accept()

    # Step 1: authenticate
    try:
        auth_data = json.loads(await websocket.receive_text())
    except (json.JSONDecodeError, WebSocketDisconnect):
        await websocket.close(code=1008)
        return

    ws_token = auth_data.get("token", "")
    if not auth.valid_token(ws_token):
        await websocket.send_json({"type": "error", "content": "Invalid or expired session."})
        await websocket.close(code=1008)
        return

    access_code = auth.get_code_for_token(ws_token)
    business_mode = auth_data.get("mode", "sales")
    if business_mode not in ("sales", "support"):
        business_mode = "sales"

    # Step 2: init session
    web_session_id = sessions.new_web_session_id()
    chat_id = f"web_{web_session_id}"
    conversation: list[dict] = []
    session_data: dict = {
        "session_id": web_session_id,
        "created_at": datetime.now().isoformat(),
        "mode": business_mode,
        "access_code": access_code,
        "resolution": "active",
        "turn_count": 0,
        "conversation": conversation,
    }

    await websocket.send_json({
        "type": "ready", "web_session_id": web_session_id, "mode": business_mode,
    })

    # Step 3: connect to shared channel-server bridge (Review fix C2)
    try:
        bridge = await _get_bridge()
    except Exception as e:
        await websocket.send_json({"type": "error", "content": f"Cannot connect to channel-server: {e}"})
        await websocket.close()
        return

    reply_queue = bridge.subscribe(chat_id)

    # Step 4: relay loop
    async def browser_to_server():
        """Forward browser messages to channel-server via bridge."""
        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)

                if msg.get("type") == "end_session":
                    session_data["resolution"] = "resolved"
                    sessions.save_session_data(web_session_id, session_data)
                    await websocket.send_json({"type": "session_ended"})
                    return

                if msg.get("type") == "resume_session":
                    target_id = msg.get("web_session_id", "")
                    old = sessions.load_session_data(target_id, code_hint=access_code)
                    if old and old.get("conversation"):
                        # Restore session state locally
                        conversation.clear()
                        conversation.extend(old.get("conversation", []))
                        session_data.update(old)
                        await websocket.send_json({
                            "type": "session_resumed",
                            "web_session_id": target_id,
                            "mode": old.get("mode", "sales"),
                            "history": conversation,
                            "turn_count": old.get("turn_count", 0),
                        })
                    else:
                        await websocket.send_json({
                            "type": "error", "content": "Session not found.",
                        })
                    continue

                user_text = msg.get("content", "").strip()
                if not user_text:
                    continue

                auth.touch_token(ws_token)
                conversation.append({"role": "user", "content": user_text})

                await bridge.send_message({
                    "type": "message",
                    "chat_id": chat_id,
                    "text": user_text,
                    "user": access_code or "web_anon",
                    "user_id": f"web_{access_code or 'anon'}",
                    "source": "web",
                    "runtime_mode": "production",
                    "business_mode": business_mode,
                    "ts": datetime.now().isoformat(),
                }))
        except WebSocketDisconnect:
            pass

    async def server_to_browser():
        """Forward channel-server replies (from bridge queue) to browser."""
        try:
            while True:
                msg = await reply_queue.get()
                msg_type = msg.get("type")

                if msg_type == "reply":
                    text = msg.get("text", "")
                    conversation.append({"role": "bot", "content": text})
                    session_data["turn_count"] = len(
                        [t for t in conversation if t["role"] == "user"]
                    )
                    sessions.save_session_data(web_session_id, session_data)
                    await websocket.send_json({"type": "bot_text_delta", "content": text})
                    await websocket.send_json({"type": "done"})

                elif msg_type == "ux_event":
                    await websocket.send_json({
                        "type": msg.get("event", "thinking"),
                        **msg.get("data", {}),
                    })

                elif msg_type == "error":
                    await websocket.send_json({
                        "type": "error", "content": msg.get("text", "Server error"),
                    })
                    break
        except Exception:
            pass

    # Heartbeat for browser
    async def heartbeat():
        while True:
            await asyncio.sleep(15)
            try:
                await websocket.send_json({"type": "heartbeat"})
            except Exception:
                break

    try:
        # Run relay tasks concurrently — when browser_to_server ends, cancel others
        browser_task = asyncio.create_task(browser_to_server())
        server_task = asyncio.create_task(server_to_browser())
        hb_task = asyncio.create_task(heartbeat())

        done, pending = await asyncio.wait(
            [browser_task, server_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        hb_task.cancel()
    finally:
        bridge.unsubscribe(chat_id)
        # Save session on disconnect
        if session_data.get("turn_count", 0) > 0:
            sessions.save_session_data(web_session_id, session_data)
```

**Step 2: Write web relay test (Review fix I2)**

```python
# tests/test_web_relay.py
"""Tests for web/websocket.py relay via mock channel-server."""
import asyncio
import json
import pytest
import websockets

MOCK_CS_PORT = 19997

@pytest.mark.asyncio
async def test_web_bridge_connects_and_registers():
    """WebChannelBridge connects to channel-server and registers web_*."""
    received_register = {}

    async def mock_server(ws):
        nonlocal received_register
        msg = json.loads(await ws.recv())
        received_register = msg
        await ws.send(json.dumps({"type": "registered", "chat_ids": msg["chat_ids"]}))
        try: await asyncio.Future()
        except asyncio.CancelledError: pass

    server = await websockets.serve(mock_server, "localhost", MOCK_CS_PORT)
    try:
        from web.websocket import WebChannelBridge
        import web.websocket as ws_mod
        old_url = ws_mod.CHANNEL_SERVER_URL
        ws_mod.CHANNEL_SERVER_URL = f"ws://localhost:{MOCK_CS_PORT}"
        try:
            bridge = WebChannelBridge()
            await bridge.ensure_connected()
            assert received_register["type"] == "register"
            assert received_register["chat_ids"] == ["web_*"]
            assert received_register["role"] == "web"
        finally:
            ws_mod.CHANNEL_SERVER_URL = old_url
    finally:
        server.close()
        await server.wait_closed()

@pytest.mark.asyncio
async def test_web_bridge_demuxes_replies():
    """Bridge routes reply to correct subscriber by chat_id."""
    async def mock_server(ws):
        msg = json.loads(await ws.recv())
        await ws.send(json.dumps({"type": "registered", "chat_ids": msg["chat_ids"]}))
        await ws.send(json.dumps({
            "type": "reply", "chat_id": "web_session_abc", "text": "Hello!",
        }))
        try: await asyncio.Future()
        except asyncio.CancelledError: pass

    server = await websockets.serve(mock_server, "localhost", MOCK_CS_PORT)
    try:
        from web.websocket import WebChannelBridge
        import web.websocket as ws_mod
        old_url = ws_mod.CHANNEL_SERVER_URL
        ws_mod.CHANNEL_SERVER_URL = f"ws://localhost:{MOCK_CS_PORT}"
        try:
            bridge = WebChannelBridge()
            await bridge.ensure_connected()
            q = bridge.subscribe("web_session_abc")
            msg = await asyncio.wait_for(q.get(), timeout=3)
            assert msg["type"] == "reply"
            assert msg["text"] == "Hello!"
            bridge.unsubscribe("web_session_abc")
        finally:
            ws_mod.CHANNEL_SERVER_URL = old_url
    finally:
        server.close()
        await server.wait_closed()
```

**Step 3: Update web/app.py to use new configure signature**

In `web/app.py`, replace `ws_handlers.configure(demo_backend=DEMO_BACKEND)` with:

```python
ws_handlers.configure(
    channel_server_url=f"ws://localhost:{os.getenv('CHANNEL_SERVER_PORT', '9999')}"
)
```

Remove the import and configuration of `claude_backend` and `system_prompts` (they will be deleted in Phase 5).

**Step 5: Commit**

```bash
git add web/websocket.py web/app.py tests/test_web_relay.py
git commit -m "feat: rewrite websocket.py as multiplexed channel-server relay"
```

---

### Task 3.2: Clean up web/app.py imports and configuration

**Files:**
- Modify: `web/app.py:57-107`

**Step 1: Remove dead imports and configuration**

Remove these lines from `web/app.py`:
- Line 57: `DEMO_BACKEND = os.getenv(...)` — no longer needed
- Line 63-66: imports of `claude_backend`, `system_prompts`
- Line 76-79: `backend.configure(...)`, `ws_handlers.configure(demo_backend=...)`
- Lines 81-107: skill_md / persona discovery and `prompts.configure(...)` — this was for system_prompts.py

Keep: `auth`, `plugin_kb`, `sessions`, `ws_handlers` imports.

Update `ws_handlers.configure()` call to pass `channel_server_url`.

Update lifespan to remove SDK/CLI references from startup banner.

**Step 2: Commit**

```bash
git add web/app.py
git commit -m "refactor: remove SDK/API backend references from web/app.py"
```

---

## Phase 4: Business Logic Unification

### Task 4.1: Rewrite channel-instructions.md as thin routing layer

**Files:**
- Modify: `feishu/channel-instructions.md:1-50`

**Step 1: Write the new thin instructions**

```markdown
# AutoService Channel Instructions

Messages arrive as <channel> tags. Meta fields:
- `runtime_mode`: "production" | "improve"
- `business_mode`: "sales" | "support"
- `routed_to`: if set, another instance owns this chat — observe only, do NOT reply

## Mode Routing

### production mode
1. Read `.autoservice/rules/` for behavior rules
2. Route by business_mode:
   - **sales** → use /cinnox-demo skill (or /sales-demo if unavailable)
   - **support** → use /customer-service skill
3. Constraints: no CRM raw data, no system commands, no internal info exposure

### improve mode
Use /improve skill. Full permissions.

### routed_to set (observation mode)
Another instance is handling this customer. Read the message for context but do NOT call reply.

## Tools
- `reply(chat_id, text)` — send response to customer
- `react(message_id, emoji_type)` — emoji reaction
- Plugin tools — per loaded plugins

## Data
- `.autoservice/rules/` — behavior rules (YAML)
- `.autoservice/database/crm.db` — CRM
- `.autoservice/database/knowledge_base/` — KB
- `.autoservice/database/sessions/` — session logs
```

**Step 2: Commit**

```bash
git add feishu/channel-instructions.md
git commit -m "refactor: slim channel-instructions.md to thin routing layer"
```

---

### Task 4.2: Create escalation rules data file

**Files:**
- Create: `.autoservice/rules/escalation.yaml`

**Step 1: Write escalation rules**

```yaml
# Escalation rules — read by skills to determine when to transfer to human agent
#
# Skills should check these rules; channel-instructions.md does NOT contain this logic.

triggers:
  # Exact phrases (case-insensitive) that trigger escalation
  keywords:
    - "转接人工"
    - "找你们经理"
    - "connect me to"
    - "speak to a human"
    - "talk to a person"

  # Conditions (checked by skill logic)
  conditions:
    - kb_no_results: true        # KB search returned empty
    - permission_denied: true    # operation exceeds bot permissions

behavior:
  # What to do when escalation triggers
  action: "notify_and_transfer"
  message_template: |
    I'll connect you with a team member who can help further.
    Please hold while I transfer you.
```

**Step 2: Commit**

```bash
git add .autoservice/rules/escalation.yaml
git commit -m "feat: add escalation rules data file"
```

---

## Phase 5: Cleanup

### Task 5.1: Delete obsolete web modules

**Files:**
- Delete: `web/claude_backend.py`
- Delete: `web/system_prompts.py`

**Step 1: Verify no remaining imports**

Run: `cd /Users/h2oslabs/Workspace/AutoService-Cinnox/.claude/worktrees/feat-multiuser-mode && grep -r "claude_backend\|system_prompts" web/ --include="*.py"`

This should show no hits after Task 3.2 cleanup. If any remain, remove them.

**Step 2: Delete files**

```bash
git rm web/claude_backend.py web/system_prompts.py
git commit -m "chore: delete obsolete web backend modules"
```

---

### Task 5.2: Update claude.sh to accept chat_id parameter

**Files:**
- Modify: `claude.sh:299-319`

**Step 1: Add chat_id parsing**

Insert before the `--_internal` check at line 302:

```bash
# Parse chat_id argument (first non-internal arg)
if [ "$1" != "--_internal" ] && [ -n "$1" ] && [[ "$1" != [123] ]]; then
    export AUTOSERVICE_CHAT_ID="$1"
    shift
else
    export AUTOSERVICE_CHAT_ID="${AUTOSERVICE_CHAT_ID:-*}"
fi
```

This allows:
- `./claude.sh oc_aaa` → sets `AUTOSERVICE_CHAT_ID=oc_aaa`
- `./claude.sh` → defaults to `*` (wildcard/developer mode)
- `./claude.sh --_internal ...` → internal use, defaults to `*`
- `./claude.sh 1` → mode selection (not a chat_id), defaults to `*`

**Step 2: Commit**

```bash
git add claude.sh
git commit -m "feat: claude.sh accepts chat_id parameter for multi-instance mode"
```

---

### Task 5.3: Update pyproject.toml — remove web-only AI deps

**Files:**
- Modify: `pyproject.toml:9-23`

**Step 1: Check if anthropic/claude-agent-sdk are still needed**

`anthropic` — still used if any code imports it. After web cleanup, check:
- `channel.py` — no (uses MCP, not anthropic SDK directly)
- `web/` — no longer (backend deleted)
- `autoservice/` — check `autoservice/claude.py` if it exists

`claude-agent-sdk` — was only used by web/websocket.py SDK backend. After cleanup, check if anything else imports it.

If both are unused, remove from dependencies. If `autoservice/claude.py` or other modules still use them, keep.

Run: `grep -r "import anthropic\|from anthropic\|import claude_agent_sdk\|from claude_agent_sdk" --include="*.py" .`

**Step 2: Remove if unused, commit**

```bash
git add pyproject.toml
git commit -m "chore: remove unused AI SDK dependencies from web"
```

---

### Task 5.4: E2E test with agent-browser (Web channel)

> Uses `agent-browser` CLI (v0.23.4) to automate the full browser flow:
> login → chat → send message → receive reply → end session → logout.
>
> **Prerequisites:** channel-server + channel.py + web server all running.

**Files:**
- Create: `tests/e2e/test_web_chat.sh`

**Step 1: Create the E2E test script**

```bash
#!/bin/bash
# tests/e2e/test_web_chat.sh — E2E test for web chat via agent-browser
#
# Prerequisites:
#   Terminal 1: FEISHU_ENABLED=0 make run-server
#   Terminal 2: AUTOSERVICE_CHAT_ID="*" ./claude.sh
#   Terminal 3: make run-web
#
# Usage: bash tests/e2e/test_web_chat.sh [port]

set -euo pipefail
PORT="${1:-8000}"
BASE="http://localhost:${PORT}"
SESSION="e2e-web-chat"
ADMIN_KEY="${DEMO_ADMIN_KEY:-}"
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "  ✅ $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ❌ $1"; }
cleanup() { agent-browser --session "$SESSION" close 2>/dev/null || true; }
trap cleanup EXIT

echo "=== E2E: Web Chat via channel-server ==="
echo "Target: $BASE"
echo ""

# ── 0. Get an access code ────────────────────────────────────────────────
echo "▶ Step 0: Generate access code"
if [ -z "$ADMIN_KEY" ]; then
  # Try to read from .env
  ADMIN_KEY=$(grep -s DEMO_ADMIN_KEY .env | cut -d= -f2 || true)
fi
if [ -z "$ADMIN_KEY" ]; then
  echo "  ⚠ DEMO_ADMIN_KEY not set — reading from server startup logs"
  echo "  Set DEMO_ADMIN_KEY env var or pass it manually"
  exit 1
fi

CODE_RESP=$(curl -s "${BASE}/admin/new-code?key=${ADMIN_KEY}")
ACCESS_CODE=$(echo "$CODE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('code',''))" 2>/dev/null || true)
if [ -z "$ACCESS_CODE" ]; then
  fail "Could not generate access code"
  exit 1
fi
pass "Access code: $ACCESS_CODE"

# ── 1. Login page ────────────────────────────────────────────────────────
echo ""
echo "▶ Step 1: Login"
agent-browser --session "$SESSION" open "${BASE}/login" && \
  agent-browser --session "$SESSION" wait --load networkidle
agent-browser --session "$SESSION" snapshot -i

# Fill access code and submit
agent-browser --session "$SESSION" fill "#code-input" "$ACCESS_CODE"
agent-browser --session "$SESSION" click "#submit-btn"
agent-browser --session "$SESSION" wait --url "**/chat" --timeout 10000

URL=$(agent-browser --session "$SESSION" get url)
if echo "$URL" | grep -q "/chat"; then
  pass "Redirected to /chat"
else
  fail "Not redirected to /chat (URL: $URL)"
  exit 1
fi

# ── 2. Chat page loads, WebSocket connects ───────────────────────────────
echo ""
echo "▶ Step 2: Chat page + WebSocket"
agent-browser --session "$SESSION" wait --load networkidle
agent-browser --session "$SESSION" wait "#conn-dot" --timeout 15000

# Wait for connection dot to go green (class=live)
agent-browser --session "$SESSION" wait --fn "document.querySelector('#conn-dot')?.classList.contains('live')" --timeout 15000

CONN_TEXT=$(agent-browser --session "$SESSION" get text "#conn-label" 2>/dev/null || echo "unknown")
if echo "$CONN_TEXT" | grep -qi "connect"; then
  pass "WebSocket connected ($CONN_TEXT)"
else
  fail "WebSocket not connected ($CONN_TEXT)"
fi

# ── 3. Send a message ───────────────────────────────────────────────────
echo ""
echo "▶ Step 3: Send message"
agent-browser --session "$SESSION" snapshot -i
agent-browser --session "$SESSION" fill "#msg-input" "Hello, what products do you offer?"
agent-browser --session "$SESSION" click "#send-btn"

# Verify user message appears
agent-browser --session "$SESSION" wait --text "Hello, what products" --timeout 5000
pass "User message displayed"

# ── 4. Wait for bot reply ────────────────────────────────────────────────
echo ""
echo "▶ Step 4: Wait for bot reply"

# Wait for typing indicator to appear then disappear (bot responding)
agent-browser --session "$SESSION" wait "#typing-indicator" --timeout 30000 2>/dev/null || true

# Wait for 'done' — typing indicator disappears and a bot bubble exists
agent-browser --session "$SESSION" wait --fn "document.querySelectorAll('.msg-row.bot .bubble').length > 0" --timeout 120000

BOT_TEXT=$(agent-browser --session "$SESSION" eval 'document.querySelector(".msg-row.bot .bubble")?.innerText?.substring(0, 80)' 2>/dev/null || echo "")
if [ -n "$BOT_TEXT" ]; then
  pass "Bot replied: ${BOT_TEXT}..."
else
  fail "No bot reply found"
fi

# ── 5. End session ──────────────────────────────────────────────────────
echo ""
echo "▶ Step 5: End session"
agent-browser --session "$SESSION" snapshot -i
agent-browser --session "$SESSION" click "#btn-end"
agent-browser --session "$SESSION" wait --text "Session ended" --timeout 10000
pass "Session ended"

# ── 6. Logout ────────────────────────────────────────────────────────────
echo ""
echo "▶ Step 6: Logout"
agent-browser --session "$SESSION" click "#btn-logout"
agent-browser --session "$SESSION" wait --url "**/login" --timeout 10000

URL=$(agent-browser --session "$SESSION" get url)
if echo "$URL" | grep -q "/login"; then
  pass "Redirected back to /login"
else
  fail "Not redirected to /login (URL: $URL)"
fi

# ── Results ──────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

**Step 2: Make executable and test**

```bash
chmod +x tests/e2e/test_web_chat.sh
```

Run with all three services up:
```bash
# Terminal 1: FEISHU_ENABLED=0 make run-server
# Terminal 2: AUTOSERVICE_CHAT_ID="*" ./claude.sh
# Terminal 3: make run-web
# Terminal 4:
bash tests/e2e/test_web_chat.sh
```

**Step 3: Add Makefile target**

```makefile
e2e-web:
	bash tests/e2e/test_web_chat.sh
```

**Step 4: Commit**

```bash
git add tests/e2e/test_web_chat.sh Makefile
git commit -m "test: E2E web chat test with agent-browser"
```

---

### Task 5.5: E2E test with mock Feishu (channel-server routing)

> Tests the Feishu path without real Feishu credentials.
> Uses a Python script that connects to channel-server as a mock "Feishu source",
> injects a message, and verifies the reply comes back.

**Files:**
- Create: `tests/e2e/test_feishu_mock.py`

**Step 1: Write the mock Feishu E2E test**

```python
#!/usr/bin/env python3
"""
E2E test: mock Feishu message → channel-server → channel.py → reply.

Prerequisites:
  Terminal 1: FEISHU_ENABLED=0 make run-server
  Terminal 2: AUTOSERVICE_CHAT_ID="*" ./claude.sh

This script connects to channel-server as a mock channel.py instance,
sends a message through the routing layer, and verifies it receives
the message back (since it's registered as wildcard).
"""
import asyncio
import json
import sys

import websockets

SERVER_URL = "ws://localhost:9999"


async def main():
    print("=== E2E: Mock Feishu via channel-server ===")

    # Connect and register as wildcard (like the developer instance)
    async with websockets.connect(SERVER_URL) as ws:
        # Register
        await ws.send(json.dumps({
            "type": "register",
            "role": "developer",
            "chat_ids": ["*"],
            "instance_id": "e2e-mock-feishu",
            "runtime_mode": "improve",
        }))
        resp = json.loads(await ws.recv())
        assert resp["type"] == "registered", f"Registration failed: {resp}"
        print("  ✅ Registered as wildcard instance")

        # Inject a message directly through the server's route_message
        # (In real flow, Feishu WS would do this; here we send type=message)
        await ws.send(json.dumps({
            "type": "message",
            "chat_id": "oc_e2e_test",
            "message_id": "om_test_001",
            "user": "E2E Tester (ou_test)",
            "user_id": "ou_test",
            "text": "E2E test message",
            "source": "feishu",
            "runtime_mode": "production",
            "business_mode": "sales",
            "ts": "2026-04-06T00:00:00Z",
        }))

        # As wildcard, we should receive this message back
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        assert msg["type"] == "message", f"Expected message, got: {msg['type']}"
        assert msg["chat_id"] == "oc_e2e_test"
        assert msg["text"] == "E2E test message"
        print(f"  ✅ Received routed message: {msg['text']}")

        # Test reply reverse routing (will fail for oc_ without Feishu,
        # but the protocol should work)
        await ws.send(json.dumps({
            "type": "reply",
            "chat_id": "oc_e2e_test",
            "text": "E2E reply",
        }))
        print("  ✅ Reply sent (Feishu delivery skipped — no credentials)")

        # Test /status command (if admin_chat_id is not set, just verify protocol)
        print("")
        print("=== Results: all passed ===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        sys.exit(1)
```

**Step 2: Add Makefile target**

```makefile
e2e-feishu:
	uv run python3 tests/e2e/test_feishu_mock.py
```

**Step 3: Commit**

```bash
git add tests/e2e/test_feishu_mock.py Makefile
git commit -m "test: E2E mock Feishu routing test via channel-server"
```

---

## Summary of All Tasks

| Task | Phase | Description | Key Files |
|------|-------|-------------|-----------|
| 1.1 | 1 | Scaffold channel-server.py | `feishu/channel-server.py`, `tests/test_channel_server.py` |
| 1.2 | 1 | Registration + route table tests | `tests/test_channel_server.py` |
| 1.3 | 1 | Feishu WS migration | `feishu/channel-server.py` |
| 1.4 | 1 | Makefile + deps | `Makefile`, `pyproject.toml` |
| 2.1 | 2 | channel.py refactor | `feishu/channel.py`, `tests/test_channel_client.py` |
| 3.1 | 3 | websocket.py multiplexed relay | `web/websocket.py`, `tests/test_web_relay.py` |
| 3.2 | 3 | web/app.py cleanup | `web/app.py` |
| 4.1 | 4 | channel-instructions.md thin | `feishu/channel-instructions.md` |
| 4.2 | 4 | Escalation rules data | `.autoservice/rules/escalation.yaml` |
| 5.1 | 5 | Delete obsolete modules | `web/claude_backend.py`, `web/system_prompts.py` |
| 5.2 | 5 | claude.sh chat_id param | `claude.sh` |
| 5.3 | 5 | Remove unused deps | `pyproject.toml` |
| 5.4 | 5 | E2E web chat (agent-browser) | `tests/e2e/test_web_chat.sh` |
| 5.5 | 5 | E2E mock Feishu routing | `tests/e2e/test_feishu_mock.py` |

## Test Strategy Summary

| Layer | Tool | Files | What it covers |
|-------|------|-------|---------------|
| Unit | pytest + mock WS | `tests/test_channel_server.py` | Routing, registration, conflicts, dedup |
| Unit | pytest + mock WS | `tests/test_channel_client.py` | channel.py registration + reconnect |
| Unit | pytest + mock WS | `tests/test_web_relay.py` | WebChannelBridge connect, demux |
| E2E Web | agent-browser CLI | `tests/e2e/test_web_chat.sh` | Login → chat → send → reply → end → logout |
| E2E Feishu | Python + websockets | `tests/e2e/test_feishu_mock.py` | Mock message → routing → reply protocol |
