"""Tests for feishu.channel_server — local WebSocket routing daemon."""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets

# We import directly since feishu/__init__.py exists
from channels.feishu.channel_server import ChannelServer

SERVER_PORT = 19999


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _start_server(port: int = SERVER_PORT) -> ChannelServer:
    """Create and start a ChannelServer with Feishu disabled."""
    srv = ChannelServer(port=port, feishu_enabled=False)
    await srv.start()
    # Give the server a moment to bind
    await asyncio.sleep(0.05)
    return srv


async def _stop_server(srv: ChannelServer) -> None:
    await srv.stop()


async def _connect(port: int = SERVER_PORT) -> websockets.asyncio.client.ClientConnection:
    return await websockets.connect(f"ws://localhost:{port}")


async def _send_json(ws, msg: dict) -> None:
    await ws.send(json.dumps(msg))


async def _recv_json(ws, timeout: float = 2.0) -> dict:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_server_accepts_connection():
    """Connect to server, verify connection stays open."""
    srv = await _start_server()
    try:
        ws = await _connect()
        assert ws.protocol.state.name == "OPEN"
        await ws.close()
    finally:
        await _stop_server(srv)


@pytest.mark.asyncio
async def test_register_and_route():
    """Register with a specific chat_id, route a message, verify receipt."""
    srv = await _start_server()
    try:
        ws = await _connect()
        # Register for a specific chat_id
        await _send_json(ws, {
            "type": "register",
            "chat_ids": ["oc_aaa"],
            "instance_id": "inst-1",
            "role": "agent",
        })
        resp = await _recv_json(ws)
        assert resp["type"] == "registered"
        assert resp["chat_ids"] == ["oc_aaa"]

        # Route a message to that chat_id
        await srv.route_message("oc_aaa", {
            "type": "message",
            "chat_id": "oc_aaa",
            "text": "hello",
        })

        routed = await _recv_json(ws)
        assert routed["type"] == "message"
        assert routed["chat_id"] == "oc_aaa"
        assert routed["text"] == "hello"

        await ws.close()
    finally:
        await _stop_server(srv)


@pytest.mark.asyncio
async def test_wildcard_receives_copy():
    """Register a specific instance + wildcard; both receive the message.

    The wildcard copy should include a 'routed_to' hint.
    """
    srv = await _start_server()
    try:
        ws_specific = await _connect()
        ws_wildcard = await _connect()

        # Register specific
        await _send_json(ws_specific, {
            "type": "register",
            "chat_ids": ["oc_aaa"],
            "instance_id": "inst-specific",
            "role": "agent",
        })
        resp1 = await _recv_json(ws_specific)
        assert resp1["type"] == "registered"

        # Register wildcard
        await _send_json(ws_wildcard, {
            "type": "register",
            "chat_ids": ["*"],
            "instance_id": "inst-wildcard",
            "role": "developer",
        })
        resp2 = await _recv_json(ws_wildcard)
        assert resp2["type"] == "registered"

        # Route message
        await srv.route_message("oc_aaa", {
            "type": "message",
            "chat_id": "oc_aaa",
            "text": "test",
        })

        # Specific instance gets the message without routed_to
        msg_specific = await _recv_json(ws_specific)
        assert msg_specific["type"] == "message"
        assert "routed_to" not in msg_specific

        # Wildcard gets a copy WITH routed_to hint
        msg_wc = await _recv_json(ws_wildcard)
        assert msg_wc["type"] == "message"
        assert msg_wc["routed_to"] == "inst-specific"

        await ws_specific.close()
        await ws_wildcard.close()
    finally:
        await _stop_server(srv)


@pytest.mark.asyncio
async def test_registration_conflict():
    """Register same chat_id twice -- second registration gets an error."""
    srv = await _start_server()
    try:
        ws1 = await _connect()
        ws2 = await _connect()

        await _send_json(ws1, {
            "type": "register",
            "chat_ids": ["oc_conflict"],
            "instance_id": "inst-first",
            "role": "agent",
        })
        resp1 = await _recv_json(ws1)
        assert resp1["type"] == "registered"

        # Second registration for same chat_id should fail
        await _send_json(ws2, {
            "type": "register",
            "chat_ids": ["oc_conflict"],
            "instance_id": "inst-second",
            "role": "agent",
        })
        resp2 = await _recv_json(ws2)
        assert resp2["type"] == "error"
        assert resp2["code"] == "REGISTRATION_CONFLICT"
        assert "oc_conflict" in resp2["message"]

        await ws1.close()
        await ws2.close()
    finally:
        await _stop_server(srv)


@pytest.mark.asyncio
async def test_unregister_on_disconnect():
    """Register, disconnect, then verify the route table is cleared."""
    srv = await _start_server()
    try:
        ws = await _connect()
        await _send_json(ws, {
            "type": "register",
            "chat_ids": ["oc_gone"],
            "instance_id": "inst-gone",
            "role": "agent",
        })
        resp = await _recv_json(ws)
        assert resp["type"] == "registered"
        assert "oc_gone" in srv.exact_routes

        # Disconnect
        await ws.close()
        # Give server time to process the disconnect
        await asyncio.sleep(0.1)

        assert "oc_gone" not in srv.exact_routes
        assert len(srv._ws_to_instance) == 0
    finally:
        await _stop_server(srv)


@pytest.mark.asyncio
async def test_inbound_message_routing():
    """Send type=message from a 'web' client, verify it routes to wildcard."""
    srv = await _start_server()
    try:
        ws_wildcard = await _connect()
        ws_web = await _connect()

        # Register wildcard
        await _send_json(ws_wildcard, {
            "type": "register",
            "chat_ids": ["*"],
            "instance_id": "inst-dev",
            "role": "developer",
        })
        resp = await _recv_json(ws_wildcard)
        assert resp["type"] == "registered"

        # Web client sends a message (not registered, just sends type=message)
        await _send_json(ws_web, {
            "type": "message",
            "chat_id": "web_sess_123",
            "text": "Hi from web",
        })

        # Wildcard should receive it
        msg = await _recv_json(ws_wildcard)
        assert msg["type"] == "message"
        assert msg["chat_id"] == "web_sess_123"
        assert msg["text"] == "Hi from web"

        await ws_wildcard.close()
        await ws_web.close()
    finally:
        await _stop_server(srv)
