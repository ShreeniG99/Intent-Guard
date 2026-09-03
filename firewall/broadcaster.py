"""
broadcaster.py

Thin in-process WebSocket broadcaster, per plan doc Section 6: a set of
open connections, no Redis pub/sub -- single FastAPI process, no
multi-instance fan-out problem to solve. A dead connection is dropped
silently rather than crashing the broadcast to everyone else.
"""
from starlette.websockets import WebSocket


class Broadcaster:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self._connections -= dead


broadcaster = Broadcaster()
