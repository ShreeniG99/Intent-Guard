"""
test_broadcaster.py

Exercises firewall/broadcaster.py with REAL WebSocket clients against the
running server (main.py on :8000). Until now the broadcaster was code-complete
but never connected to by anything, so `broadcaster.broadcast(...)` inside
/checkout and /payments/capture always iterated an empty connection set.

Three checks:
  1. one client connected to /ws receives a broadcast triggered by an HTTP
     call (POST /pay/callback broadcasts {"event":"test_payment_authorized"}
     without needing a real Razorpay round-trip)
  2. TWO concurrent clients BOTH receive the same broadcast (fan-out)
  3. a client that has hung up does not break delivery to a live client
     (broadcast() drops dead sockets silently)

Run (server already up on :8000):
    python test_broadcaster.py
"""
import asyncio
import json
import uuid

import requests
import websockets

WS_URL = "ws://localhost:8000/ws"
BASE = "http://localhost:8000"


def trigger_broadcast():
    """POST /pay/callback -> writes an audit row + broadcaster.broadcast(...).
    Uses a random id so each test run's message is unambiguous."""
    marker = f"oid-{uuid.uuid4().hex[:10]}"
    r = requests.post(f"{BASE}/pay/callback", json={
        "razorpay_order_id": marker,
        "razorpay_payment_id": f"pay-{uuid.uuid4().hex[:10]}",
        "razorpay_signature": "test",
    })
    r.raise_for_status()
    return marker


async def recv_json(ws, timeout=5):
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(raw)


async def check_1_single_client():
    async with websockets.connect(WS_URL) as ws:
        await asyncio.sleep(0.3)  # let the server register the connection
        marker = await asyncio.get_event_loop().run_in_executor(None, trigger_broadcast)
        msg = await recv_json(ws)
        assert msg.get("event") == "test_payment_authorized", msg
        assert msg.get("order_id") == marker, (msg, marker)
    print("  1. single client received the broadcast  -> PASS")


async def check_2_fanout():
    async with websockets.connect(WS_URL) as a, websockets.connect(WS_URL) as b:
        await asyncio.sleep(0.3)
        marker = await asyncio.get_event_loop().run_in_executor(None, trigger_broadcast)
        ma, mb = await asyncio.gather(recv_json(a), recv_json(b))
        assert ma.get("order_id") == marker and mb.get("order_id") == marker, (ma, mb)
    print("  2. two concurrent clients both received it -> PASS")


async def check_3_dead_socket_tolerated():
    dead = await websockets.connect(WS_URL)
    live = await websockets.connect(WS_URL)
    await asyncio.sleep(0.3)
    await dead.close()                       # server still thinks 'dead' is connected
    await asyncio.sleep(0.2)
    marker = await asyncio.get_event_loop().run_in_executor(None, trigger_broadcast)
    msg = await recv_json(live)
    assert msg.get("order_id") == marker, msg
    await live.close()
    print("  3. broadcast survived a hung-up peer        -> PASS")


async def main():
    print("broadcaster e2e (real WebSocket clients):")
    await check_1_single_client()
    await check_2_fanout()
    await check_3_dead_socket_tolerated()
    print("\nALL BROADCASTER CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
