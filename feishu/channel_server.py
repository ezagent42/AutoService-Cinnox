"""
channel-server: standalone WebSocket daemon for multi-instance message routing.

Listens on a local port (default 9999) and routes messages between
Feishu/Web inbound connections and registered channel.py / web instances.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import websockets
from websockets.asyncio.server import ServerConnection

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / ".feishu-credentials.json"
ACK_EMOJI = "OnIt"

log = logging.getLogger("channel-server")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Instance:
    """A registered channel.py or web/app.py client."""
    ws: ServerConnection
    instance_id: str
    role: str                          # "developer" | "agent" | "web"
    chat_ids: list[str]
    runtime_mode: str = "service"      # "service" | "improve"
    business_mode: str = "customer_service"
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Channel Server
# ---------------------------------------------------------------------------

class ChannelServer:
    """Local WebSocket server that routes messages between instances."""

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 9999,
        feishu_enabled: bool = True,
        admin_chat_id: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.feishu_enabled = feishu_enabled
        self.admin_chat_id = admin_chat_id

        # Route tables
        self.exact_routes: dict[str, Instance] = {}      # chat_id -> Instance
        self.prefix_routes: dict[str, Instance] = {}     # prefix  -> Instance
        self.wildcard_instances: list[Instance] = []      # role=developer, chat_ids=["*"]

        # ws -> Instance reverse lookup (for disconnect cleanup)
        self._ws_to_instance: dict[ServerConnection, Instance] = {}

        self._stop_event = asyncio.Event()
        self._server: websockets.asyncio.server.Server | None = None
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the WebSocket server (and optionally the Feishu connection)."""
        self._stop_event.clear()

        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=20,
        )
        log.info("WebSocket server listening on %s:%s", self.host, self.port)

        if self.feishu_enabled:
            task = asyncio.create_task(self._run_feishu_safe(), name="feishu-ws")
            self._tasks.append(task)

        await self._notify_admin("Channel-Server online")

    async def stop(self) -> None:
        """Gracefully shut down."""
        log.info("Shutting down channel-server ...")
        self._stop_event.set()

        # Cancel background tasks
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        # Close WebSocket server
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        await self._notify_admin("Channel-Server offline")
        log.info("Channel-server stopped.")

    # ------------------------------------------------------------------
    # Feishu integration
    # ------------------------------------------------------------------

    # -- Feishu state (initialised in _run_feishu) ----------------------

    _feishu_client: object | None = None      # lark.Client (typed loosely to avoid import at module level)
    _bot_open_id: str | None = None
    _seen: set[str] = set()
    _recent_sent: set[str] = set()
    _user_cache: dict[str, str] = {}          # open_id -> display name
    _chat_modes: dict[str, str] = {}          # chat_id -> "production" | "improve"
    _known_chats: set[str] = set()            # chat_ids seen so far (for first-message tracking)
    _msg_counter: dict[str, int] = {"sent": 0, "received": 0}

    # -- Credentials ----------------------------------------------------

    @staticmethod
    def _load_credentials() -> tuple[str, str]:
        """Read Feishu app credentials from env vars or .feishu-credentials.json."""
        app_id = os.environ.get("FEISHU_APP_ID")
        app_secret = os.environ.get("FEISHU_APP_SECRET")
        if app_id and app_secret:
            return app_id, app_secret
        # Search: project root, then git toplevel (for worktrees)
        search_paths = [CREDENTIALS_PATH]
        try:
            import subprocess
            git_root = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(PROJECT_ROOT), stderr=subprocess.DEVNULL,
            ).decode().strip()
            search_paths.append(Path(git_root) / ".feishu-credentials.json")
        except Exception:
            pass
        for p in search_paths:
            if p.exists():
                creds = json.loads(p.read_text())
                log.info("Loaded Feishu credentials from %s", p)
                return creds["app_id"], creds["app_secret"]
        raise RuntimeError(
            "Missing Feishu credentials — set FEISHU_APP_ID/FEISHU_APP_SECRET "
            f"or create .feishu-credentials.json (searched: {[str(p) for p in search_paths]})"
        )

    # -- User resolution ------------------------------------------------

    def _resolve_user(self, open_id: str) -> str:
        """Look up user name via cache / Feishu API / CRM. Returns 'Name (open_id…)' or bare open_id."""
        if open_id in self._user_cache:
            return self._user_cache[open_id]

        import lark_oapi as lark  # lazy

        name = ""
        try:
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
                        open_id=open_id,
                        name=name,
                        phone=user_data.get("mobile", ""),
                        email=user_data.get("email", ""),
                        department=(user_data.get("department_ids", [""])[0]
                                    if user_data.get("department_ids") else ""),
                        job_title=user_data.get("job_title", ""),
                    )
                except Exception as e:
                    log.debug("CRM upsert error: %s", e)
        except Exception as e:
            log.debug("User lookup error for %s: %s", open_id, e)

        display = f"{name} ({open_id[:12]})" if name else open_id
        self._user_cache[open_id] = display
        return display

    # -- Reaction helper ------------------------------------------------

    def _send_reaction(self, message_id: str, emoji_type: str = ACK_EMOJI) -> None:
        """Add emoji reaction to a Feishu message. Blocking, meant for daemon thread."""
        import lark_oapi as lark  # lazy

        try:
            req = (
                lark.BaseRequest.builder()
                .http_method(lark.HttpMethod.POST)
                .uri(f"/open-apis/im/v1/messages/{message_id}/reactions")
                .token_types({lark.AccessTokenType.TENANT})
                .body({"reaction_type": {"emoji_type": emoji_type}})
                .build()
            )
            resp = self._feishu_client.request(req)
            if not resp.success():
                log.debug("Reaction failed: %s", resp.code)
        except Exception as e:
            log.debug("Reaction error: %s", e)

    # -- Admin message handling -----------------------------------------

    async def _handle_admin_message(self, msg: dict) -> None:
        """Process slash-commands from the admin chat."""
        text = msg.get("text", "").strip()

        if text == "/status":
            await self._reply_feishu(msg["chat_id"], self.status_text())
            return

        if text.startswith("/inject "):
            # /inject <chat_id> <text…>
            parts = text.split(None, 2)
            if len(parts) < 3:
                await self._reply_feishu(msg["chat_id"], "Usage: /inject <chat_id> <text>")
                return
            target_chat_id = parts[1]
            injected_text = parts[2]
            injected_msg = {
                "type": "message",
                "chat_id": target_chat_id,
                "text": injected_text,
                "message_id": f"inject_{datetime.now(timezone.utc).timestamp():.0f}",
                "user": "admin-inject",
                "user_id": "",
                "runtime_mode": "production",
                "business_mode": "customer_service",
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            await self.route_message(target_chat_id, injected_msg)
            await self._reply_feishu(msg["chat_id"], f"Injected to {target_chat_id}")
            return

    # -- Feishu reply helper --------------------------------------------

    async def _reply_feishu(self, chat_id: str, text: str) -> None:
        """Send a text message to a Feishu chat. Best-effort."""
        if self._feishu_client is None:
            log.debug("_reply_feishu: no feishu client")
            return

        def _do_send():
            try:
                from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
                body = (
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                )
                req = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(body).build()
                resp = self._feishu_client.im.v1.message.create(req)
                if resp.success() and resp.data and resp.data.message_id:
                    self._recent_sent.add(resp.data.message_id)
                    self._msg_counter["sent"] += 1
            except Exception as e:
                log.warning("_reply_feishu error: %s", e)

        threading.Thread(target=_do_send, daemon=True).start()

    # -- Main Feishu loop -----------------------------------------------

    async def _run_feishu_safe(self) -> None:
        """Wrapper that logs errors instead of silently swallowing them."""
        try:
            await self._run_feishu()
        except Exception as e:
            log.error("Feishu integration failed: %s", e, exc_info=True)

    async def _run_feishu(self) -> None:
        """Connect to Feishu via WebSocket, consume messages and route them."""
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
            P2ImMessageReceiveV1,
        )

        # --- credentials + client ---
        app_id, app_secret = self._load_credentials()

        self._feishu_client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )

        # --- per-instance mutable state (avoid class-var sharing) ---
        self._seen = set()
        self._recent_sent = set()
        self._user_cache = {}
        self._chat_modes = {}
        self._known_chats = set()
        self._msg_counter = {"sent": 0, "received": 0}

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict] = asyncio.Queue()

        # --- on_message callback (runs in WS thread) ---
        def on_message(data: P2ImMessageReceiveV1):
            event = data.event
            sender = event.sender
            message = event.message

            sender_id = sender.sender_id.open_id if sender.sender_id else ""
            sender_type = sender.sender_type or "user"

            # Detect bot open_id
            if sender_type == "app" and not self._bot_open_id:
                self._bot_open_id = sender_id
            # Skip bot's own messages
            if sender_type == "app" or (self._bot_open_id and sender_id == self._bot_open_id):
                return

            msg_id = message.message_id or ""
            if msg_id in self._seen or msg_id in self._recent_sent:
                return
            # Bound the _seen set
            if len(self._seen) > 10000:
                self._seen.clear()
            self._seen.add(msg_id)

            # ACK reaction (fire-and-forget)
            threading.Thread(target=self._send_reaction, args=(msg_id,), daemon=True).start()

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

            # Resolve user name
            display_name = self._resolve_user(sender_id)

            # Track first-message from a chat_id for admin notification
            is_new_chat = chat_id and chat_id not in self._known_chats
            if is_new_chat:
                self._known_chats.add(chat_id)

            # Mode switching commands
            text_stripped = text.strip().lower()
            if text_stripped == "/improve":
                self._chat_modes[chat_id] = "improve"
                threading.Thread(target=self._send_reaction, args=(msg_id, "DONE"), daemon=True).start()
                msg = {
                    "type": "message",
                    "text": "[MODE SWITCH] 已切换到 improve 模式。你现在可以：查看对话记录、管理行为规则、导入数据、分析对话质量。发送 /production 回到生产模式。",
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "user": display_name,
                    "user_id": sender_id,
                    "runtime_mode": "improve",
                    "business_mode": "customer_service",
                    "ts": ts,
                }
                loop.call_soon_threadsafe(queue.put_nowait, msg)
                return
            elif text_stripped == "/production":
                self._chat_modes[chat_id] = "production"
                threading.Thread(target=self._send_reaction, args=(msg_id, "DONE"), daemon=True).start()
                msg = {
                    "type": "message",
                    "text": "[MODE SWITCH] 已切换到 production 模式。现在以客服身份响应。",
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "user": display_name,
                    "user_id": sender_id,
                    "runtime_mode": "production",
                    "business_mode": "customer_service",
                    "ts": ts,
                }
                loop.call_soon_threadsafe(queue.put_nowait, msg)
                return

            # CRM logging
            try:
                from autoservice.crm import increment_message_count, log_message
                increment_message_count(sender_id)
                log_message(sender_id, chat_id, "in", text, ts)
            except Exception as e:
                log.debug("CRM log error: %s", e)

            current_mode = self._chat_modes.get(chat_id, "production")
            msg = {
                "type": "message",
                "text": text,
                "chat_id": chat_id,
                "message_id": msg_id,
                "user": display_name,
                "user_id": sender_id,
                "source": "feishu",
                "runtime_mode": current_mode,
                "business_mode": "sales",
                "ts": ts,
            }
            log.info("[feishu] %s: %s", display_name, text[:60])
            loop.call_soon_threadsafe(queue.put_nowait, msg)
            self._msg_counter["received"] += 1

            # Notify admin about new user's first message
            if is_new_chat and self.admin_chat_id and chat_id != self.admin_chat_id:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"_admin_notify": f"New chat: {chat_id} from {display_name}"},
                )

        # --- Start Feishu WebSocket in daemon thread ---
        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .build()
        )
        ws_client = lark.ws.Client(
            app_id=app_id,
            app_secret=app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.ERROR,  # suppress "processor not found" warnings for unhandled event types
        )
        # Suppress noisy Lark logger for unhandled event types (reaction, message_read, etc.)
        logging.getLogger("Lark").setLevel(logging.CRITICAL)

        def ws_thread():
            # lark_oapi.ws.client captures asyncio.get_event_loop() at import
            # time into a module-level `loop` variable, then calls
            # loop.run_until_complete() in start(). If the import happened in
            # the main thread (which has a running loop), this fails with
            # "This event loop is already running".
            # Fix: patch the module-level loop to a fresh one for this thread.
            import lark_oapi.ws.client as _ws_mod
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            _ws_mod.loop = new_loop
            try:
                ws_client.start()
            except Exception as e:
                log.error("Feishu WS error: %s", e)

        t = threading.Thread(target=ws_thread, daemon=True)
        t.start()
        log.info("Feishu WS thread started")

        # --- Startup notification (daemon thread, 4s delay) ---
        def send_startup():
            time.sleep(4)
            try:
                import requests as _req
                resp = _req.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": app_id, "app_secret": app_secret},
                )
                token = resp.json().get("tenant_access_token", "")
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

                scope_resp = _req.get(
                    "https://open.feishu.cn/open-apis/contact/v3/scopes", headers=headers,
                )
                scope = scope_resp.json().get("data", {})
                user_ids = set(scope.get("user_ids", []))

                for dept_id in scope.get("department_ids", []):
                    page_token = ""
                    while True:
                        url = (f"https://open.feishu.cn/open-apis/contact/v3/users/find_by_department"
                               f"?department_id={dept_id}&page_size=50&user_id_type=open_id")
                        if page_token:
                            url += f"&page_token={page_token}"
                        dr = _req.get(url, headers=headers)
                        dd = dr.json().get("data", {})
                        for u in dd.get("items", []):
                            uid = u.get("open_id", "")
                            if uid:
                                user_ids.add(uid)
                        if not dd.get("has_more"):
                            break
                        page_token = dd.get("page_token", "")

                if not user_ids:
                    log.info("No users in scope — startup msg skipped")
                    return

                log.info("Sending startup to %d user(s)", len(user_ids))
                for uid in user_ids:
                    body = (
                        CreateMessageRequestBody.builder()
                        .receive_id(uid).msg_type("text")
                        .content(json.dumps({"text": "AutoService 已上线 ✅\n发送任意消息开始使用"}))
                        .build()
                    )
                    req = CreateMessageRequest.builder().receive_id_type("open_id").request_body(body).build()
                    resp_msg = self._feishu_client.im.v1.message.create(req)
                    if resp_msg.success():
                        self._recent_sent.add(resp_msg.data.message_id)
                        log.info("Startup msg sent to %s", uid[:20])
                    else:
                        log.debug("Startup msg skipped %s: %s", uid[:20], resp_msg.code)
            except Exception as e:
                log.error("Startup msg error: %s", e)

        threading.Thread(target=send_startup, daemon=True).start()

        # --- Consumer loop: read from queue, route ---
        try:
            while not self._stop_event.is_set():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # Internal admin notification pseudo-message
                if "_admin_notify" in msg:
                    await self._notify_admin(msg["_admin_notify"])
                    continue

                chat_id = msg.get("chat_id", "")

                # Admin group: intercept slash commands, pass through normal messages
                if self.admin_chat_id and chat_id == self.admin_chat_id:
                    text = msg.get("text", "").strip()
                    if text.startswith("/"):
                        await self._handle_admin_message(msg)
                        continue
                    # Non-command messages in admin group → route normally
                    # so Claude Code can assist the admin

                # Normal routing
                await self.route_message(chat_id, msg)
        except asyncio.CancelledError:
            log.info("Feishu consumer loop cancelled")

    # ------------------------------------------------------------------
    # Client handler
    # ------------------------------------------------------------------

    async def _handle_client(self, ws: ServerConnection) -> None:
        """Handle a single WebSocket client (channel.py or web/app.py)."""
        log.info("Client connected from %s", ws.remote_address)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await self._send(ws, {"type": "error", "code": "INVALID_JSON", "message": "Could not parse message"})
                    continue

                msg_type = msg.get("type")
                if msg_type == "register":
                    await self._handle_register(ws, msg)
                elif msg_type == "reply":
                    await self._handle_reply(ws, msg)
                elif msg_type == "react":
                    await self._handle_react(ws, msg)
                elif msg_type == "message":
                    await self._handle_inbound_message(ws, msg)
                elif msg_type == "ux_event":
                    await self._handle_ux_event(ws, msg)
                elif msg_type == "pong":
                    pass  # heartbeat response, no-op
                else:
                    log.warning("Unknown message type: %s", msg_type)
        except websockets.ConnectionClosed:
            log.info("Client disconnected")
        finally:
            self._unregister(ws)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def _handle_register(self, ws: ServerConnection, msg: dict) -> None:
        chat_ids: list[str] = msg.get("chat_ids", [])
        instance_id: str = msg.get("instance_id", "unknown")
        role: str = msg.get("role", "agent")
        runtime_mode: str = msg.get("runtime_mode", "service")
        business_mode: str = msg.get("business_mode", "customer_service")

        # Check for conflicts on exact chat_ids
        for cid in chat_ids:
            if cid == "*":
                continue
            if cid.endswith("*"):
                # prefix pattern like "web_*"
                continue
            if cid in self.exact_routes:
                existing = self.exact_routes[cid]
                await self._send(ws, {
                    "type": "error",
                    "code": "REGISTRATION_CONFLICT",
                    "message": f"chat_id {cid} already registered by instance {existing.instance_id}",
                })
                return

        inst = Instance(
            ws=ws,
            instance_id=instance_id,
            role=role,
            chat_ids=chat_ids,
            runtime_mode=runtime_mode,
            business_mode=business_mode,
        )
        self._ws_to_instance[ws] = inst

        for cid in chat_ids:
            if cid == "*":
                self.wildcard_instances.append(inst)
            elif cid.endswith("*"):
                prefix = cid[:-1]  # "web_*" -> "web_"
                self.prefix_routes[prefix] = inst
            else:
                self.exact_routes[cid] = inst

        await self._send(ws, {"type": "registered", "chat_ids": chat_ids})
        log.info("Registered instance %s role=%s chat_ids=%s", instance_id, role, chat_ids)
        await self._notify_admin(f"Instance connected: {instance_id} chat_ids={chat_ids}")

    def _unregister(self, ws: ServerConnection) -> None:
        inst = self._ws_to_instance.pop(ws, None)
        if inst is None:
            return

        for cid in inst.chat_ids:
            if cid == "*":
                try:
                    self.wildcard_instances.remove(inst)
                except ValueError:
                    pass
            elif cid.endswith("*"):
                prefix = cid[:-1]
                self.prefix_routes.pop(prefix, None)
            else:
                self.exact_routes.pop(cid, None)

        log.info("Unregistered instance %s", inst.instance_id)
        # Fire-and-forget admin notification -- can't await in sync context
        # The caller should handle this if needed; we log instead.

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    async def route_message(self, chat_id: str, message: dict) -> None:
        """Route a message to the appropriate instance(s)."""
        routed_instance: Instance | None = None

        # 1. Exact match
        if chat_id in self.exact_routes:
            routed_instance = self.exact_routes[chat_id]
            await self._send(routed_instance.ws, message)

        # 2. Prefix match (only if no exact match)
        if routed_instance is None:
            for prefix, inst in self.prefix_routes.items():
                if chat_id.startswith(prefix):
                    routed_instance = inst
                    await self._send(inst.ws, message)
                    break

        # 3. Wildcard -- always receives a copy
        for inst in self.wildcard_instances:
            # Skip if this wildcard instance is also the exact/prefix match
            if routed_instance is not None and inst.ws is routed_instance.ws:
                continue
            # Add routed_to hint when message was also sent to a specific instance
            if routed_instance is not None:
                wc_msg = {**message, "routed_to": routed_instance.instance_id}
            else:
                wc_msg = message
            await self._send(inst.ws, wc_msg)

        # 4. Log actionable info when no dedicated instance exists
        if routed_instance is None and self.wildcard_instances:
            user = message.get("user", "unknown")
            source = message.get("source", "?")
            log.info(
                "💬 [%s] %s → wildcard (no dedicated instance)\n"
                "   To start dedicated instance:  ./autoservice.sh %s",
                source, user, chat_id,
            )
        elif routed_instance is None and not self.wildcard_instances:
            log.warning("No route for chat_id=%s, message dropped", chat_id)

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    async def _handle_reply(self, ws: ServerConnection, msg: dict) -> None:
        """Reverse-route a reply from an instance back to the originating channel."""
        chat_id = msg.get("chat_id", "")

        if chat_id.startswith("oc_"):
            text = msg.get("text", "")
            log.info("Reply to Feishu chat_id=%s text=%s", chat_id, text[:60])
            await self._reply_feishu(chat_id, text)
        elif chat_id.startswith("web_"):
            # WebSocket relay -- find the web instance that owns this chat_id
            target = self.exact_routes.get(chat_id) or self._find_prefix_instance(chat_id)
            if target is not None:
                await self._send(target.ws, {
                    "type": "reply",
                    "chat_id": chat_id,
                    "text": msg.get("text", ""),
                })
            else:
                log.warning("Reply for web chat_id=%s but no instance found", chat_id)
        else:
            log.warning("Reply for unknown channel prefix: chat_id=%s", chat_id)

    async def _handle_react(self, ws: ServerConnection, msg: dict) -> None:
        """Forward a reaction to Feishu API."""
        message_id = msg.get("message_id", "")
        emoji_type = msg.get("emoji_type", "THUMBSUP")
        log.info("React message_id=%s emoji=%s", message_id, emoji_type)
        if message_id and self._feishu_client:
            threading.Thread(
                target=self._send_reaction, args=(message_id, emoji_type), daemon=True
            ).start()

    async def _handle_inbound_message(self, ws: ServerConnection, msg: dict) -> None:
        """Handle an inbound message from a web client or other source."""
        chat_id = msg.get("chat_id", "")
        if not chat_id:
            await self._send(ws, {"type": "error", "code": "MISSING_CHAT_ID", "message": "message requires chat_id"})
            return
        # Route to registered instances
        await self.route_message(chat_id, msg)

    async def _handle_ux_event(self, ws: ServerConnection, msg: dict) -> None:
        """Forward UX events to the appropriate web connection."""
        chat_id = msg.get("chat_id", "")
        target = self.exact_routes.get(chat_id) or self._find_prefix_instance(chat_id)
        if target is not None:
            await self._send(target.ws, msg)
        else:
            log.debug("ux_event for chat_id=%s but no web instance found", chat_id)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status_text(self) -> str:
        """Generate human-readable status for /status command."""
        lines = ["=== Channel Server Status ==="]
        lines.append(f"Instances connected: {len(self._ws_to_instance)}")
        lines.append(f"Exact routes: {len(self.exact_routes)}")
        lines.append(f"Prefix routes: {len(self.prefix_routes)}")
        lines.append(f"Wildcard instances: {len(self.wildcard_instances)}")
        lines.append("")

        for inst in self._ws_to_instance.values():
            uptime = datetime.now(timezone.utc) - inst.connected_at
            minutes = int(uptime.total_seconds() // 60)
            lines.append(
                f"  {inst.instance_id} role={inst.role} "
                f"chat_ids={inst.chat_ids} "
                f"runtime={inst.runtime_mode} "
                f"uptime={minutes}m"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_prefix_instance(self, chat_id: str) -> Instance | None:
        for prefix, inst in self.prefix_routes.items():
            if chat_id.startswith(prefix):
                return inst
        return None

    @staticmethod
    async def _send(ws: ServerConnection, msg: dict) -> None:
        try:
            data = json.dumps(msg, ensure_ascii=False)
            await ws.send(data)
            log.debug("Sent %d bytes to %s: type=%s chat_id=%s",
                       len(data), getattr(ws, 'id', '?'), msg.get('type'), msg.get('chat_id'))
        except websockets.ConnectionClosed:
            log.warning("Send failed -- connection already closed")
        except Exception as e:
            log.error("Send error: %s", e)

    async def _notify_admin(self, text: str) -> None:
        """Fire-and-forget admin notification. Degrades gracefully."""
        if not self.admin_chat_id:
            log.info("[admin] %s", text)
            return
        # Placeholder: would send via Feishu API
        log.info("[admin → %s] %s", self.admin_chat_id, text)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _async_main() -> None:
    log_file = PROJECT_ROOT / ".autoservice" / "logs" / "channel-server.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(str(log_file), mode="a", encoding="utf-8"),
            logging.StreamHandler(),  # also print to terminal
        ],
    )
    # Keep terminal output at INFO, file at DEBUG
    logging.getLogger().handlers[0].setLevel(logging.DEBUG)   # file
    logging.getLogger().handlers[1].setLevel(logging.INFO)    # terminal

    port = int(os.environ.get("CHANNEL_SERVER_PORT", "9999"))
    admin_chat_id = os.environ.get("ADMIN_CHAT_ID")
    feishu_enabled = os.environ.get("FEISHU_ENABLED", "true").lower() in ("true", "1", "yes")

    server = ChannelServer(
        port=port,
        feishu_enabled=feishu_enabled,
        admin_chat_id=admin_chat_id,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(server.stop()))

    await server.start()

    sep = "=" * 60
    print(f"\n{sep}")
    print("  AutoService Channel Server")
    print(f"  Listening  : ws://localhost:{port}")
    print(f"  Feishu     : {'enabled' if feishu_enabled else 'disabled'}")
    if admin_chat_id:
        print(f"  Admin group: {admin_chat_id}")
    print()
    print("  Next steps:")
    print(f"    1. Start Claude Code:  ./autoservice.sh")
    print(f"    2. Start Claude Code:  ./autoservice.sh oc_<chat_id>")
    print(f"    3. Start Web server:   make run-web")
    print(sep + "\n")

    await server._stop_event.wait()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
