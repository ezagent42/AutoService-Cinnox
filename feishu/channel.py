#!/usr/bin/env python3
"""
autoservice-channel: Claude Code Channel MCP Server
Bridges Feishu messaging <-> Claude Code via MCP stdio protocol.

Based on the zchat-channel pattern:
- MCP low-level Server + stdio_server()
- Feishu WebSocket runs in background thread, pushes to asyncio.Queue
- poll_feishu_queue consumes queue, writes SessionMessage to write_stream
- server.run and poller run in parallel via anyio.create_task_group

Plugin tools from autoservice.plugin_loader are dynamically registered
alongside the core reply/react tools.
"""
import asyncio
import json
import logging
import os
import sys
import time
import threading
from pathlib import Path
from datetime import datetime, timezone

import anyio
import mcp.server.stdio
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification, Tool, TextContent

import requests as http_requests  # renamed to avoid conflict
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)

# -- Config ------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = PROJECT_ROOT / ".autoservice" / "feishu-channel.log"
CREDENTIALS_PATH = PROJECT_ROOT / ".feishu-credentials.json"
INSTRUCTIONS_PATH = Path(__file__).parent / "channel-instructions.md"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[autoservice-channel] %(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("autoservice-channel")
log.info(f"=== Channel started PID={os.getpid()} ===")


def load_credentials() -> tuple[str, str]:
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if app_id and app_secret:
        return app_id, app_secret
    if CREDENTIALS_PATH.exists():
        creds = json.loads(CREDENTIALS_PATH.read_text())
        return creds["app_id"], creds["app_secret"]
    log.error("Missing credentials")
    sys.exit(1)


APP_ID, APP_SECRET = load_credentials()

# -- Feishu Client -----------------------------------------------------------

feishu_client = (
    lark.Client.builder()
    .app_id(APP_ID)
    .app_secret(APP_SECRET)
    .log_level(lark.LogLevel.WARNING)
    .build()
)

# -- State -------------------------------------------------------------------

_seen: set[str] = set()
_recent_sent: set[str] = set()
_bot_open_id: str | None = None
_msg_counter = {"sent": 0, "received": 0}

# -- Reaction helper (fire-and-forget ack) ------------------------------------

ACK_EMOJI = "OnIt"  # built-in Feishu emoji, means "processing"


def send_reaction(message_id: str, emoji_type: str = ACK_EMOJI) -> None:
    """Add emoji reaction to a message. Non-blocking, errors logged."""
    try:
        req = (
            lark.BaseRequest.builder()
            .http_method(lark.HttpMethod.POST)
            .uri(f"/open-apis/im/v1/messages/{message_id}/reactions")
            .token_types({lark.AccessTokenType.TENANT})
            .body({"reaction_type": {"emoji_type": emoji_type}})
            .build()
        )
        resp = feishu_client.request(req)
        if not resp.success():
            log.debug(f"Reaction failed: {resp.code}")
    except Exception as e:
        log.debug(f"Reaction error: {e}")

# -- MCP Notification Injection -----------------------------------------------


async def inject_message(write_stream, msg: dict):
    """Send a channel notification to Claude Code via the MCP write stream."""
    notification = JSONRPCNotification(
        jsonrpc="2.0",
        method="notifications/claude/channel",
        params={
            "content": msg["text"],
            "meta": {
                "chat_id": msg["chat_id"],
                "message_id": msg["message_id"],
                "user": msg.get("user", "unknown"),
                "user_id": msg.get("user_id", ""),
                "ts": msg.get("ts", datetime.now(tz=timezone.utc).isoformat()),
            },
        },
    )
    await write_stream.send(SessionMessage(message=JSONRPCMessage(notification)))
    log.info(f"Injected: '{msg['text'][:60]}...' from {msg.get('user', '?')}")


async def poll_feishu_queue(queue: asyncio.Queue, write_stream):
    """Consume Feishu messages from queue and inject into Claude Code."""
    while True:
        msg = await queue.get()
        try:
            await inject_message(write_stream, msg)
        except Exception as e:
            log.error(f"inject error: {e}")


# -- Feishu WebSocket ---------------------------------------------------------


def setup_feishu(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Initialize Feishu WebSocket client, return connection info."""
    global _bot_open_id

    def on_message(data: P2ImMessageReceiveV1):
        global _bot_open_id

        event = data.event
        sender = event.sender
        message = event.message

        sender_id = sender.sender_id.open_id if sender.sender_id else ""
        sender_type = sender.sender_type or "user"

        # Detect bot open_id
        if sender_type == "app" and not _bot_open_id:
            _bot_open_id = sender_id
        # Skip bot's own messages
        if sender_type == "app" or (_bot_open_id and sender_id == _bot_open_id):
            return

        msg_id = message.message_id or ""
        if msg_id in _seen or msg_id in _recent_sent:
            return
        _seen.add(msg_id)

        # Ack reaction -- fire-and-forget, shows "processing" on the message
        threading.Thread(
            target=send_reaction, args=(msg_id,), daemon=True
        ).start()

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

        msg = {
            "text": text,
            "chat_id": chat_id,
            "message_id": msg_id,
            "user": sender_id,
            "user_id": sender_id,
            "ts": ts,
        }
        log.info(f"[feishu] {sender_id[:20]}: {text[:60]}")
        loop.call_soon_threadsafe(queue.put_nowait, msg)
        _msg_counter["received"] += 1

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )

    ws_client = lark.ws.Client(
        app_id=APP_ID,
        app_secret=APP_SECRET,
        event_handler=handler,
        log_level=lark.LogLevel.WARNING,
    )

    def ws_thread():
        try:
            ws_client.start()
        except Exception as e:
            log.error(f"Feishu WS error: {e}")

    thread = threading.Thread(target=ws_thread, daemon=True)
    thread.start()
    log.info(f"Feishu WS thread started")

    # Send startup message
    def send_startup():
        time.sleep(4)
        try:
            import requests
            resp = requests.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": APP_ID, "app_secret": APP_SECRET},
            )
            token = resp.json().get("tenant_access_token", "")
            headers = {"Authorization": f"Bearer {token}"}
            scope_resp = requests.get(
                "https://open.feishu.cn/open-apis/contact/v3/scopes",
                headers=headers,
            )
            user_ids = scope_resp.json().get("data", {}).get("user_ids", [])
            for uid in user_ids:
                body = (
                    CreateMessageRequestBody.builder()
                    .receive_id(uid).msg_type("text")
                    .content(json.dumps({"text": "AutoService \u5df2\u4e0a\u7ebf \u2705\n\u53d1\u9001\u4efb\u610f\u6d88\u606f\u5f00\u59cb\u4f7f\u7528"}))
                    .build()
                )
                req = CreateMessageRequest.builder().receive_id_type("open_id").request_body(body).build()
                resp_msg = feishu_client.im.v1.message.create(req)
                if resp_msg.success():
                    _recent_sent.add(resp_msg.data.message_id)
                    log.info(f"Startup msg sent to {uid[:20]}")
        except Exception as e:
            log.error(f"Startup msg error: {e}")

    threading.Thread(target=send_startup, daemon=True).start()


# -- MCP Server + Tools -------------------------------------------------------


def load_instructions() -> str:
    if INSTRUCTIONS_PATH.exists():
        return INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    return (
        "Messages from Feishu arrive as <channel> tags with chat_id, user, ts attributes. "
        "Reply with the reply tool -- your transcript never reaches the Feishu chat. "
        "When users send requests, use available plugin tools to process them, "
        "then reply with the result."
    )


def create_server() -> Server:
    return Server("autoservice-channel", instructions=load_instructions())


def register_tools(server: Server, plugin_tools: list):

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        core_tools = [
            Tool(
                name="reply",
                description=(
                    "Send a message to a Feishu chat. The user reads Feishu, not this "
                    "session -- anything you want them to see must go through this tool. "
                    "chat_id is from the inbound <channel> tag (oc_xxx format)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "string", "description": "Feishu chat ID (oc_xxx)"},
                        "text": {"type": "string", "description": "Message text"},
                    },
                    "required": ["chat_id", "text"],
                },
            ),
            Tool(
                name="react",
                description="Add an emoji reaction to a Feishu message",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string", "description": "Message ID (om_xxx)"},
                        "emoji_type": {"type": "string", "description": "Feishu emoji (THUMBSUP, DONE, OK)"},
                    },
                    "required": ["message_id", "emoji_type"],
                },
            ),
        ]
        dynamic_tools = [
            Tool(name=pt.name, description=pt.description, inputSchema=pt.input_schema)
            for pt in plugin_tools
        ]
        return core_tools + dynamic_tools

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "reply":
            return _handle_reply(arguments)
        elif name == "react":
            return _handle_react(arguments)
        # Plugin tools
        for pt in plugin_tools:
            if pt.name == name:
                result = pt.handler(**arguments)
                if asyncio.iscoroutine(result):
                    result = await result
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
        raise ValueError(f"Unknown tool: {name}")


def _handle_reply(args: dict) -> list[TextContent]:
    chat_id = args["chat_id"]
    text = args["text"]

    body = (
        CreateMessageRequestBody.builder()
        .receive_id(chat_id).msg_type("text")
        .content(json.dumps({"text": text})).build()
    )
    req = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(body).build()
    resp = feishu_client.im.v1.message.create(req)
    if resp.success():
        _recent_sent.add(resp.data.message_id)
        _msg_counter["sent"] += 1
        log.info(f"Reply to {chat_id}: {text[:50]}...")
        return [TextContent(type="text", text=f"Sent. message_id={resp.data.message_id}")]
    log.error(f"Reply failed: {resp.code} {resp.msg}")
    return [TextContent(type="text", text=f"Failed: {resp.code} {resp.msg}")]


def _handle_react(args: dict) -> list[TextContent]:
    req = (
        lark.BaseRequest.builder()
        .http_method(lark.HttpMethod.POST)
        .uri(f"/open-apis/im/v1/messages/{args['message_id']}/reactions")
        .token_types({lark.AccessTokenType.TENANT})
        .body({"reaction_type": {"emoji_type": args["emoji_type"]}})
        .build()
    )
    resp = feishu_client.request(req)
    if resp.success():
        return [TextContent(type="text", text=f"Reacted {args['emoji_type']}")]
    return [TextContent(type="text", text=f"Failed: {resp.code} {resp.msg}")]


# -- Main ---------------------------------------------------------------------


async def main():
    from autoservice.plugin_loader import discover
    plugins = discover("plugins")
    all_tools = []
    for p in plugins:
        all_tools.extend(p.tools)

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

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
        # Wait for MCP init before starting Feishu WS
        await anyio.sleep(2)
        setup_feishu(queue, loop)

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(server.run, read_stream, write_stream, init_opts)
                tg.start_soon(poll_feishu_queue, queue, write_stream)
        except Exception as e:
            log.error(f"Task group error: {e}")


def entry_point():
    asyncio.run(main())


if __name__ == "__main__":
    entry_point()
