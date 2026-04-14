import asyncio
import json
import pytest
import websockets

SERVER_PORT = 19998


@pytest.mark.asyncio
async def test_channel_connects_and_registers():
    registered = asyncio.Event()
    received_register = {}

    done = asyncio.Event()

    async def mock_handler(ws):
        nonlocal received_register
        msg = json.loads(await ws.recv())
        received_register = msg
        await ws.send(json.dumps({"type": "registered", "chat_ids": msg["chat_ids"]}))
        registered.set()
        # Keep connection open until test signals done
        await done.wait()

    async with websockets.serve(mock_handler, "localhost", SERVER_PORT):
        from channels.feishu.channel import ChannelClient
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

        done.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
