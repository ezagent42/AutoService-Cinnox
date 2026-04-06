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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import websockets
from websockets.asyncio.server import ServerConnection

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
            task = asyncio.create_task(self._run_feishu(), name="feishu-ws")
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
    # Feishu placeholder
    # ------------------------------------------------------------------

    async def _run_feishu(self) -> None:
        """Placeholder -- real Feishu WebSocket integration added in a later task."""
        log.info("Feishu WS placeholder running (waiting for stop)")
        await self._stop_event.wait()

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

        # 4. No route at all
        if routed_instance is None and not self.wildcard_instances:
            log.warning("No route for chat_id=%s, message dropped", chat_id)

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    async def _handle_reply(self, ws: ServerConnection, msg: dict) -> None:
        """Reverse-route a reply from an instance back to the originating channel."""
        chat_id = msg.get("chat_id", "")

        if chat_id.startswith("oc_"):
            # Feishu -- would call Feishu API (placeholder)
            log.info("Reply to Feishu chat_id=%s text=%s", chat_id, msg.get("text", "")[:60])
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
        """Forward a reaction to Feishu API (placeholder)."""
        log.info(
            "React message_id=%s emoji=%s",
            msg.get("message_id", "?"),
            msg.get("emoji_type", "?"),
        )

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
            await ws.send(json.dumps(msg))
        except websockets.ConnectionClosed:
            log.debug("Send failed -- connection already closed")

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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

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
    await server._stop_event.wait()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
