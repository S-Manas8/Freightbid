import asyncio
import json
import datetime
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from typing import Dict, Set

from .database import SessionLocal
from .models import Shipment, User, Message, Bid
from .auth_utils import decode_token

# Simple in-memory manager for WebSocket connections per shipment and driver
class ShipmentWebSocketManager:
    def __init__(self) -> None:
        # Mapping of room_id (shipment_id:driver_id) -> set of active WebSocket connections
        self.connections: Dict[str, Set[WebSocket]] = {}
        # Lock to protect concurrent modifications
        self._lock = asyncio.Lock()

    async def connect(self, room_id: str, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and register it for a 1-to-1 room."""
        await websocket.accept()
        async with self._lock:
            if room_id not in self.connections:
                self.connections[room_id] = set()
            self.connections[room_id].add(websocket)

    async def disconnect(self, room_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket from the registry when the client disconnects."""
        async with self._lock:
            if room_id in self.connections:
                self.connections[room_id].discard(websocket)
                if not self.connections[room_id]:
                    # Clean up empty entry
                    del self.connections[room_id]

    async def broadcast(self, room_id: str, message: dict) -> None:
        """Send a JSON message to all clients listening to the given room_id (shipment_id:driver_id).

        If a connection raises an exception (e.g., closed), it is removed.
        """
        async with self._lock:
            sockets = list(self.connections.get(room_id, []))
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                # Remove problematic socket
                await self.disconnect(room_id, ws)

    async def broadcast_to_all_shipment_rooms(self, shipment_id: str, message: dict) -> None:
        """Send a message to all active driver rooms associated with a shipment_id (e.g. tracking, status updates)."""
        async with self._lock:
            matching_rooms = [r for r in self.connections.keys() if r.startswith(f"{shipment_id}:")]
        for room_id in matching_rooms:
            await self.broadcast(room_id, message)

# Global manager instance used across the application
ws_manager = ShipmentWebSocketManager()

# Helper function used by the tracking router
async def broadcast_shipment(shipment_id: str, data: dict) -> None:
    """Public API for broadcasting shipment updates to all active rooms for this shipment.

    The tracking router calls this after persisting a location event.
    """
    await ws_manager.broadcast_to_all_shipment_rooms(shipment_id, data)

router = APIRouter()

@router.websocket("/ws/shipment/{shipment_id}")
async def shipment_ws(websocket: WebSocket, shipment_id: str):
    # 1. Parse JWT token and optional driver_id from query string parameters
    token = websocket.query_params.get("token")
    driver_id = websocket.query_params.get("driver_id")
    if not token:
        # Close connection if token is missing (4008 = Policy Violation)
        await websocket.accept()
        await websocket.close(code=4008)
        return

    # 2. Decode and validate JWT token
    try:
        user = decode_token(token)
    except Exception:
        # Close connection if token is expired/invalid (4003 = Forbidden)
        await websocket.accept()
        await websocket.close(code=4003)
        return

    user_id = user.get("sub")
    role = user.get("role")

    # 3. Open DB session and verify authorization
    db = SessionLocal()
    try:
        s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
        if not s:
            await websocket.accept()
            await websocket.close(code=4004) # Not Found
            return

        # Determine target_driver_id and verify roles
        if role == "driver":
            target_driver_id = user_id
            # Allow if they are either assigned OR have placed a bid on this shipment
            has_bid = db.query(Bid).filter(Bid.shipment_id == shipment_id, Bid.driver_id == user_id).first() is not None
            is_assigned = s.assigned_driver_id == user_id
            if not (is_assigned or has_bid):
                await websocket.accept()
                await websocket.close(code=4003)
                return
        elif role == "shipper":
            if s.shipper_id != user_id:
                await websocket.accept()
                await websocket.close(code=4003)
                return
            target_driver_id = driver_id or s.assigned_driver_id
            if not target_driver_id:
                await websocket.accept()
                await websocket.close(code=4003)
                return
        else:
            await websocket.accept()
            await websocket.close(code=4003)
            return

        room_id = f"{shipment_id}:{target_driver_id}"

        # Fetch sender's real name from DB
        user_obj = db.query(User).filter(User.id == user_id).first()
        sender_name = user_obj.name if user_obj else "Unknown"

        # Connection is valid! Accept and register in manager
        await ws_manager.connect(room_id, websocket)

        # Send welcome/connected confirmation
        await websocket.send_json({"type": "connected"})

        # 4. Listen loop for client-sent events
        while True:
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
            except Exception:
                continue

            msg_type = data.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "chat":
                text = (data.get("text") or "").strip()
                if not text:
                    continue
                if len(text) > 1000:
                    text = text[:1000]

                # Persist message to DB with target_driver_id
                msg = Message(
                    shipment_id=shipment_id,
                    driver_id=target_driver_id,
                    sender_id=user_id,
                    sender_role=role,
                    body=text,
                    created_at=datetime.datetime.utcnow()
                )
                db.add(msg)
                db.commit()
                db.refresh(msg)

                # Broadcast to all connected clients in the shipment room
                await ws_manager.broadcast(room_id, {
                    "type": "chat",
                    "from_role": role,
                    "sender_name": sender_name,
                    "text": text,
                    "ts": msg.created_at.isoformat()
                })
    except WebSocketDisconnect:
        await ws_manager.disconnect(room_id, websocket)
    finally:
        db.close()
