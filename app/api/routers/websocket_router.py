import asyncio
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.api.dependencies.auth_dependencies import resolve_token_user
from app.core.connection import SessionLocal
from app.core.token_utils import decode_token
from app.services.websocket_service import websocket_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    # JWT를 URL/접속 로그에 남기지 않도록 첫 프레임으로 인증한다.
    await websocket.accept()
    connected = False
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if not isinstance(auth, dict) or auth.get("type") != "authenticate":
            await websocket.close(code=1008, reason="Authentication required")
            return
        token = auth.get("token")
        if not isinstance(token, str) or not token:
            await websocket.close(code=1008, reason="Authentication required")
            return
        with SessionLocal() as db:
            user = resolve_token_user(token, db)
            if user.id != user_id:
                await websocket.close(code=1008, reason="Forbidden")
                return

        await websocket_service.connect(websocket, user_id)
        connected = True
        while True:
            # 유휴 상태에서도 만료된 인증으로 구독이 계속되지 않게 한다.
            decode_token(token)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                continue
            await websocket.send_json({"type": "pong", "message": "연결 유지됨"})
    except (HTTPException, ValueError, asyncio.TimeoutError):
        await websocket.close(code=1008, reason="Authentication failed or expired")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.error("WebSocket connection failed", exc_info=False)
        try:
            await websocket.close(code=1011, reason="Connection failed")
        except RuntimeError:
            pass
    finally:
        if connected:
            await websocket_service.disconnect(user_id, websocket)
