import asyncio
import json
import pytest
import websockets

MOCK_CS_PORT = 19997


@pytest.mark.asyncio
async def test_web_bridge_connects_and_registers():
    received_register = {}
    handler_done = asyncio.Event()

    async def mock_handler(ws):
        nonlocal received_register
        msg = json.loads(await ws.recv())
        received_register = msg
        await ws.send(json.dumps({"type": "registered", "chat_ids": msg["chat_ids"]}))
        # Keep connection alive until test signals done
        await handler_done.wait()

    server = await websockets.serve(mock_handler, "localhost", MOCK_CS_PORT)
    try:
        from web.websocket import WebChannelBridge
        import web.websocket as ws_mod

        old_url = ws_mod.CHANNEL_SERVER_URL
        ws_mod.CHANNEL_SERVER_URL = f"ws://localhost:{MOCK_CS_PORT}"
        bridge = WebChannelBridge()
        try:
            await bridge.ensure_connected()
            assert received_register["type"] == "register"
            assert received_register["chat_ids"] == ["web_*"]
            assert received_register["role"] == "web"
        finally:
            ws_mod.CHANNEL_SERVER_URL = old_url
            handler_done.set()
            if bridge._recv_task and not bridge._recv_task.done():
                bridge._recv_task.cancel()
                try:
                    await bridge._recv_task
                except (asyncio.CancelledError, Exception):
                    pass
            if bridge._ws:
                await bridge._ws.close()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_web_bridge_demuxes_replies():
    handler_done = asyncio.Event()

    async def mock_handler(ws):
        msg = json.loads(await ws.recv())
        await ws.send(json.dumps({"type": "registered", "chat_ids": msg["chat_ids"]}))
        # Small delay to let subscriber register
        await asyncio.sleep(0.05)
        await ws.send(
            json.dumps(
                {"type": "reply", "chat_id": "web_session_abc", "text": "Hello!"}
            )
        )
        await handler_done.wait()

    server = await websockets.serve(mock_handler, "localhost", MOCK_CS_PORT)
    try:
        from web.websocket import WebChannelBridge
        import web.websocket as ws_mod

        old_url = ws_mod.CHANNEL_SERVER_URL
        ws_mod.CHANNEL_SERVER_URL = f"ws://localhost:{MOCK_CS_PORT}"
        bridge = WebChannelBridge()
        try:
            await bridge.ensure_connected()
            q = bridge.subscribe("web_session_abc")
            msg = await asyncio.wait_for(q.get(), timeout=3)
            assert msg["type"] == "reply"
            assert msg["text"] == "Hello!"
            bridge.unsubscribe("web_session_abc")
        finally:
            ws_mod.CHANNEL_SERVER_URL = old_url
            handler_done.set()
            if bridge._recv_task and not bridge._recv_task.done():
                bridge._recv_task.cancel()
                try:
                    await bridge._recv_task
                except (asyncio.CancelledError, Exception):
                    pass
            if bridge._ws:
                await bridge._ws.close()
    finally:
        server.close()
        await server.wait_closed()
