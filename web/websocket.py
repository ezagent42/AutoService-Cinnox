"""
WebSocket handlers — multiplexed channel-server relay.

/ws       — generic endpoint (sends error + closes)
/ws/chat  — authenticated chat, relayed to channel-server via WebChannelBridge

Architecture:
  web/app.py opens ONE persistent WebSocket to channel-server (registered
  with chat_ids=["web_*"], role="web"). All browser sessions are multiplexed
  over that single connection. Each browser session gets a unique
  chat_id = "web_{session_id}". Replies are demuxed back to the correct
  browser by chat_id.
"""

import asyncio
import json
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from web import auth
from web import session_persistence as sessions


# ── Configuration (set by app.py) ─────────────────────────────────────────
CHANNEL_SERVER_URL: str = "ws://localhost:9999"


def configure(channel_server_url: str) -> None:
    global CHANNEL_SERVER_URL
    CHANNEL_SERVER_URL = channel_server_url


# ── WebChannelBridge (singleton) ─────────────────────────────────────────
class WebChannelBridge:
    """Maintains a single WS connection to channel-server and multiplexes
    all browser sessions over it."""

    def __init__(self) -> None:
        self._ws = None
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._connected = asyncio.Event()
        self._recv_task: asyncio.Task | None = None

    async def ensure_connected(self) -> None:
        if self._ws is not None and self._connected.is_set():
            return

        import websockets

        self._ws = await websockets.connect(CHANNEL_SERVER_URL)

        # Register with channel-server
        register_msg = {
            "type": "register",
            "chat_ids": ["web_*"],
            "role": "web",
            "instance_id": "web-app",
        }
        await self._ws.send(json.dumps(register_msg))

        # Wait for registration ack
        raw = await self._ws.recv()
        ack = json.loads(raw)
        if ack.get("type") != "registered":
            print(f"[bridge] unexpected register response: {ack}", flush=True)

        self._connected.set()
        self._recv_task = asyncio.create_task(self._receive_loop())
        print("[bridge] connected to channel-server", flush=True)

    async def _receive_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await self._ws.send(json.dumps({"type": "pong"}))
                    continue

                chat_id = msg.get("chat_id", "")
                if chat_id and chat_id in self._subscribers:
                    await self._subscribers[chat_id].put(msg)
                elif chat_id:
                    print(f"[bridge] no subscriber for chat_id={chat_id}", flush=True)

        except Exception as exc:
            print(f"[bridge] receive loop error: {exc}", flush=True)
        finally:
            # Notify all subscribers of disconnection
            self._connected.clear()
            err_msg = {"type": "error", "content": "channel-server disconnected"}
            for q in self._subscribers.values():
                try:
                    q.put_nowait(err_msg)
                except asyncio.QueueFull:
                    pass
            print("[bridge] receive loop ended", flush=True)

    def subscribe(self, chat_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[chat_id] = q
        return q

    def unsubscribe(self, chat_id: str) -> None:
        self._subscribers.pop(chat_id, None)

    async def send_message(self, msg: dict) -> None:
        if self._ws is None:
            raise RuntimeError("bridge not connected")
        await self._ws.send(json.dumps(msg))


# ── Module-level singleton ────────────────────────────────────────────────
_bridge: WebChannelBridge | None = None


async def _get_bridge() -> WebChannelBridge:
    global _bridge
    if _bridge is None:
        _bridge = WebChannelBridge()
    await _bridge.ensure_connected()
    return _bridge


# ── Generic WebSocket handler ────────────────────────────────────────────
async def ws_generic(websocket: WebSocket):
    """Generic /ws handler — not supported in relay mode."""
    await websocket.accept()
    await websocket.send_json({
        "type": "error",
        "content": "Generic /ws endpoint is not available. Use /ws/chat instead.",
    })
    await websocket.close(code=1000)


# ── Authenticated chat WebSocket ─────────────────────────────────────────
async def ws_chat(websocket: WebSocket):
    """Authenticated /ws/chat handler — relays to channel-server."""
    await websocket.accept()

    # Step 1: token authentication
    try:
        auth_data = json.loads(await websocket.receive_text())
    except (json.JSONDecodeError, WebSocketDisconnect):
        await websocket.close(code=1008)
        return

    ws_token = auth_data.get("token", "")
    if not auth.valid_token(ws_token):
        await websocket.send_json({
            "type": "error",
            "content": "Invalid or expired session. Please log in again.",
        })
        await websocket.close(code=1008)
        return

    access_code = auth.get_code_for_token(ws_token)

    mode = auth_data.get("mode", "sales")
    if mode not in ("sales", "service"):
        mode = "sales"

    # Step 2: init web session state
    web_session_id = sessions.new_web_session_id()
    chat_id = f"web_{web_session_id}"
    session_data: dict = {
        "session_id": web_session_id,
        "created_at": datetime.now().isoformat(),
        "mode": mode,
        "access_code": access_code,
        "customer_type": "unknown",
        "resolution": "active",
        "turn_count": 0,
        "conversation": [],
        "gate_cleared": False,
    }

    await websocket.send_json({
        "type": "ready",
        "web_session_id": web_session_id,
        "mode": mode,
    })

    # Step 3: connect to channel-server bridge
    try:
        bridge = await _get_bridge()
    except Exception as exc:
        await websocket.send_json({
            "type": "error",
            "content": f"Cannot connect to channel-server: {exc}",
        })
        await websocket.close(code=1011)
        return

    reply_queue = bridge.subscribe(chat_id)

    # Step 4: concurrent tasks
    async def browser_to_server():
        """Receive messages from browser, forward to channel-server."""
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "end_session":
                session_data["resolution"] = "resolved"
                sessions.save_session_data(web_session_id, session_data)
                await websocket.send_json({"type": "session_ended"})
                return  # exit task to trigger cleanup

            if msg.get("type") == "resume_session":
                target_id = msg.get("web_session_id", "")
                old = sessions.load_session_data(target_id, code_hint=access_code)
                can = old and (old.get("conversation") or old.get("claude_session_id"))
                if can:
                    session_data.update(old)
                    session_data["session_id"] = target_id
                    await websocket.send_json({
                        "type": "session_resumed",
                        "web_session_id": target_id,
                        "mode": old.get("mode", "sales"),
                        "history": old.get("conversation", []),
                        "turn_count": old.get("turn_count", 0),
                        "customer_type": old.get("customer_type", "unknown"),
                        "resolution": old.get("resolution", "active"),
                        "human_agent_active": old.get("human_agent_active", False),
                        "human_agent_name": old.get("human_agent_name", ""),
                        "human_agent_role": old.get("human_agent_role", ""),
                        "escalation_turn": old.get("escalation_turn", -1),
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Session not found or cannot be resumed.",
                    })
                continue

            user_text = msg.get("content", "").strip()
            if not user_text:
                continue

            auth.touch_token(ws_token)

            # Forward to channel-server
            await bridge.send_message({
                "type": "message",
                "chat_id": chat_id,
                "text": user_text,
                "session_data": session_data,
            })

    async def server_to_browser():
        """Read from reply_queue, forward to browser."""
        while True:
            msg = await reply_queue.get()
            msg_type = msg.get("type", "")

            if msg_type == "reply":
                text = msg.get("text", "")
                if text:
                    await websocket.send_json({
                        "type": "bot_text_delta",
                        "content": text,
                    })
                    await websocket.send_json({"type": "done"})

                    # Update conversation in session_data
                    conversation = session_data.setdefault("conversation", [])
                    conversation.append({"role": "bot", "content": text})
                    session_data["turn_count"] = len(
                        [t for t in conversation if t["role"] == "user"]
                    )
                    sessions.save_session_data(web_session_id, session_data)

            elif msg_type == "ux_event":
                # Forward UX events (thinking, kb_searching, etc.) directly
                payload = {k: v for k, v in msg.items() if k != "chat_id"}
                await websocket.send_json(payload)

            elif msg_type == "error":
                await websocket.send_json({
                    "type": "error",
                    "content": msg.get("content", "Unknown error"),
                })

    async def heartbeat():
        """Send heartbeat to browser every 15 seconds."""
        while True:
            await asyncio.sleep(15)
            try:
                await websocket.send_json({"type": "heartbeat"})
            except Exception:
                return

    try:
        tasks = [
            asyncio.create_task(browser_to_server()),
            asyncio.create_task(server_to_browser()),
            asyncio.create_task(heartbeat()),
        ]
        # Wait for any task to complete (browser_to_server ends on end_session
        # or disconnect; server_to_browser may end on bridge error)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in pending:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[ws/chat] error: {exc}", flush=True)
    finally:
        bridge.unsubscribe(chat_id)
        if session_data.get("turn_count", 0) > 0:
            sessions.save_session_data(web_session_id, session_data)
