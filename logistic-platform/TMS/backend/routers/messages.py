"""
Messages router — in-app chat between shipper and driver for a shipment.
"""
import datetime
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Message, Shipment, User, Bid
from ..auth_utils import get_current_user

router = APIRouter()


@router.post("/{shipment_id}/messages")
async def send_message(
    shipment_id: str,
    data: dict,
    driver_id: str = None,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Send a message on a shipment thread. Both shipper and driver can send."""
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    # Determine driver_id for this 1-to-1 chat thread
    if user["role"] == "driver":
        target_driver_id = user["sub"]
        # Allow if they are either the assigned driver OR have placed a bid on the shipment
        has_bid = db.query(Bid).filter(Bid.shipment_id == shipment_id, Bid.driver_id == user["sub"]).first() is not None
        is_assigned = s.assigned_driver_id == user["sub"]
        if not (is_assigned or has_bid):
            raise HTTPException(403, "You must have placed a bid or be assigned to this shipment to chat.")
    elif user["role"] == "shipper":
        if s.shipper_id != user["sub"]:
            raise HTTPException(403, "Not your shipment")
        
        target_driver_id = driver_id or data.get("driver_id")
        if not target_driver_id:
            target_driver_id = s.assigned_driver_id
            
        if not target_driver_id:
            raise HTTPException(400, "driver_id is required for shippers to initiate chat.")
    else:
        raise HTTPException(403, "Unauthorized role")

    body = (data.get("body") or "").strip()
    if not body:
        raise HTTPException(400, "Message body cannot be empty")
    if len(body) > 1000:
        raise HTTPException(400, "Message too long (max 1000 chars)")

    msg = Message(
        shipment_id = shipment_id,
        driver_id   = target_driver_id,
        sender_id   = user["sub"],
        sender_role = user["role"],
        body        = body,
        created_at  = datetime.datetime.utcnow()
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    sender = db.query(User).filter(User.id == user["sub"]).first()
    sender_name = sender.name if sender else "Unknown"

    try:
        from ws_manager import ws_manager
        # Broadcast to the specific 1-to-1 chat room: shipment_id:driver_id
        room_id = f"{shipment_id}:{target_driver_id}"
        await ws_manager.broadcast(room_id, {
            "type": "chat",
            "from_role": msg.sender_role,
            "sender_name": sender_name,
            "text": msg.body,
            "ts": msg.created_at.isoformat()
        })
    except Exception as e:
        print(f"Failed to broadcast HTTP post message: {e}")

    return {
        "id":          msg.id,
        "body":        msg.body,
        "sender_id":   msg.sender_id,
        "sender_name": sender_name,
        "sender_role": msg.sender_role,
        "created_at":  msg.created_at.isoformat(),
        "read_at":     None
    }


@router.get("/{shipment_id}/messages")
def get_messages(
    shipment_id: str,
    driver_id: str = None,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Get all messages for a 1-to-1 driver-shipper thread."""
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    if user["role"] == "driver":
        target_driver_id = user["sub"]
        has_bid = db.query(Bid).filter(Bid.shipment_id == shipment_id, Bid.driver_id == user["sub"]).first() is not None
        is_assigned = s.assigned_driver_id == user["sub"]
        if not (is_assigned or has_bid):
            raise HTTPException(403, "You must have placed a bid or be assigned to this shipment to chat.")
    elif user["role"] == "shipper":
        if s.shipper_id != user["sub"]:
            raise HTTPException(403, "Not your shipment")
        target_driver_id = driver_id
        if not target_driver_id:
            target_driver_id = s.assigned_driver_id
        if not target_driver_id:
            raise HTTPException(400, "driver_id is required for shippers")
    else:
        raise HTTPException(403, "Unauthorized role")

    msgs = db.query(Message).filter(
        Message.shipment_id == shipment_id,
        Message.driver_id == target_driver_id
    ).order_by(Message.created_at).all()

    # Mark unread messages from the other party as read
    now = datetime.datetime.utcnow()
    for m in msgs:
        if m.sender_id != user["sub"] and m.read_at is None:
            m.read_at = now
    db.commit()

    result = []
    for m in msgs:
        sender = db.query(User).filter(User.id == m.sender_id).first()
        result.append({
            "id":          m.id,
            "body":        m.body,
            "sender_id":   m.sender_id,
            "sender_name": sender.name if sender else "Unknown",
            "sender_role": m.sender_role,
            "created_at":  m.created_at.isoformat(),
            "read_at":     m.read_at.isoformat() if m.read_at else None,
            "is_mine":     m.sender_id == user["sub"]
        })

    return result


@router.get("/messages/notifications")
def get_message_notifications(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Unread chat notifications without marking messages as read."""
    user = get_current_user(authorization)

    if user["role"] == "shipper":
        rows = (
            db.query(Message, Shipment)
            .join(Shipment, Message.shipment_id == Shipment.id)
            .filter(
                Shipment.shipper_id == user["sub"],
                Message.sender_id != user["sub"],
                Message.read_at == None
            )
            .order_by(Message.created_at.desc())
            .all()
        )
    elif user["role"] == "driver":
        rows = (
            db.query(Message, Shipment)
            .join(Shipment, Message.shipment_id == Shipment.id)
            .filter(
                Message.driver_id == user["sub"],
                Message.sender_id != user["sub"],
                Message.read_at == None
            )
            .order_by(Message.created_at.desc())
            .all()
        )
    else:
        raise HTTPException(403, "Unauthorized role")

    grouped = {}
    for msg, shipment in rows:
        key = f"{msg.shipment_id}:{msg.driver_id}"
        if key not in grouped:
            sender = db.query(User).filter(User.id == msg.sender_id).first()
            grouped[key] = {
                "shipment_id": msg.shipment_id,
                "driver_id": msg.driver_id,
                "shipment_title": shipment.goods_desc,
                "pickup_address": shipment.pickup_address,
                "drop_address": shipment.drop_address,
                "sender_name": sender.name if sender else "Unknown",
                "latest_body": msg.body,
                "latest_at": msg.created_at.isoformat(),
                "unread": 0
            }
        grouped[key]["unread"] += 1

    return list(grouped.values())


@router.get("/{shipment_id}/messages/unread-count")
def get_unread_count(
    shipment_id: str,
    driver_id: str = None,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Get count of unread messages from the other party."""
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    if user["role"] == "driver":
        target_driver_id = user["sub"]
    else:
        target_driver_id = driver_id

    query = db.query(Message).filter(
        Message.shipment_id == shipment_id,
        Message.sender_id   != user["sub"],
        Message.read_at     == None
    )
    if target_driver_id:
        query = query.filter(Message.driver_id == target_driver_id)

    count = query.count()
    return {"unread": count}
