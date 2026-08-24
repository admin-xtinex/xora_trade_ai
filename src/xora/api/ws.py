from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from xora.persistence.queries import Analytics

router = APIRouter()


@router.websocket("/ws")
async def live(ws: WebSocket) -> None:
    await ws.accept()
    analytics = Analytics()
    try:
        while True:
            await ws.send_json({"type": "snapshot", "data": analytics.live_snapshot()})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
    except Exception:
        await ws.close()
