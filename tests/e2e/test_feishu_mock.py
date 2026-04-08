#!/usr/bin/env python3
"""
E2E test: mock Feishu message → channel-server → routing → reply protocol.

This test starts its own channel-server (feishu_enabled=False) and connects
as a wildcard instance, then verifies message routing works end-to-end.
No external dependencies required.
"""
import asyncio
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import websockets


SERVER_PORT = 19990
PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


async def main():
    print("=== E2E: Mock Feishu via channel-server ===")
    print()

    # Start channel-server in-process
    from feishu.channel_server import ChannelServer
    server = ChannelServer(port=SERVER_PORT, feishu_enabled=False)
    server_task = asyncio.create_task(server.start())
    await asyncio.sleep(0.3)

    try:
        # Test 1: Connect and register as wildcard
        print("▶ Test 1: Register wildcard instance")
        async with websockets.connect(f"ws://localhost:{SERVER_PORT}") as ws:
            await ws.send(json.dumps({
                "type": "register",
                "role": "developer",
                "chat_ids": ["*"],
                "instance_id": "e2e-mock-feishu",
                "runtime_mode": "improve",
            }))
            resp = json.loads(await ws.recv())
            if resp["type"] == "registered":
                ok("Registered as wildcard instance")
            else:
                fail(f"Registration failed: {resp}")
                return

            # Test 2: Send a message and verify wildcard receives it
            print()
            print("▶ Test 2: Route message to wildcard")
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
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if msg.get("type") == "message" and msg.get("text") == "E2E test message":
                ok(f"Received routed message: {msg['text']}")
            else:
                fail(f"Unexpected message: {msg}")

            # Test 3: Verify runtime_mode and business_mode are preserved
            print()
            print("▶ Test 3: Verify mode fields preserved")
            if msg.get("runtime_mode") == "production" and msg.get("business_mode") == "sales":
                ok("runtime_mode=production, business_mode=sales preserved")
            else:
                fail(f"Mode fields wrong: runtime_mode={msg.get('runtime_mode')}, business_mode={msg.get('business_mode')}")

            # Test 4: Reply protocol
            print()
            print("▶ Test 4: Reply protocol")
            await ws.send(json.dumps({
                "type": "reply",
                "chat_id": "oc_e2e_test",
                "text": "E2E reply",
            }))
            ok("Reply sent (Feishu delivery skipped — no credentials)")

        # Test 5: Second client with specific chat_id + wildcard routing
        print()
        print("▶ Test 5: Specific + wildcard dual routing")
        async with websockets.connect(f"ws://localhost:{SERVER_PORT}") as ws_specific, \
                     websockets.connect(f"ws://localhost:{SERVER_PORT}") as ws_wildcard:
            # Register specific
            await ws_specific.send(json.dumps({
                "type": "register", "role": "production",
                "chat_ids": ["oc_customer_1"], "instance_id": "inst-customer-1",
            }))
            await ws_specific.recv()

            # Register wildcard
            await ws_wildcard.send(json.dumps({
                "type": "register", "role": "developer",
                "chat_ids": ["*"], "instance_id": "inst-dev",
            }))
            await ws_wildcard.recv()

            # Route message to customer_1
            await ws_specific.send(json.dumps({
                "type": "message",
                "chat_id": "oc_customer_1",
                "text": "Hello customer 1",
                "source": "feishu",
            }))

            msg_specific = json.loads(await asyncio.wait_for(ws_specific.recv(), timeout=3))
            msg_wildcard = json.loads(await asyncio.wait_for(ws_wildcard.recv(), timeout=3))

            if msg_specific.get("text") == "Hello customer 1":
                ok("Specific instance received message")
            else:
                fail(f"Specific got wrong message: {msg_specific}")

            if msg_wildcard.get("text") == "Hello customer 1" and msg_wildcard.get("routed_to") == "inst-customer-1":
                ok(f"Wildcard received copy with routed_to={msg_wildcard.get('routed_to')}")
            else:
                fail(f"Wildcard message wrong: {msg_wildcard}")

        # Test 6: Registration conflict
        print()
        print("▶ Test 6: Registration conflict rejection")
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
            if resp.get("type") == "error" and resp.get("code") == "REGISTRATION_CONFLICT":
                ok("Registration conflict correctly rejected")
            else:
                fail(f"Expected REGISTRATION_CONFLICT, got: {resp}")

        # Test 7: Status text
        print()
        print("▶ Test 7: Status text generation")
        status = server.status_text()
        if "instances" in status.lower() or "Instance" in status:
            ok(f"Status text generated: {status[:60]}...")
        else:
            fail(f"Status text unexpected: {status}")

    finally:
        server.stop()
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

    print()
    print(f"=== Results: {PASS} passed, {FAIL} failed ===")
    return FAIL == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
