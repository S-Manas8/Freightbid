from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import TrackingEvent, Shipment
from ..auth_utils import get_current_user

router = APIRouter()


@router.post("/{shipment_id}/location")
async def update_location(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Driver sends their GPS location.
    Body: { lat, lng }
    Called every 10-30 seconds from the driver's browser/phone.
    """
    user = get_current_user(authorization)

    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can send location")

    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(404, "Shipment not found")

    if shipment.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "You are not assigned to this shipment")

    lat_val = float(data["lat"])
    lng_val = float(data["lng"])

    event = TrackingEvent(
        shipment_id=shipment_id,
        driver_id=user["sub"],
        lat=lat_val,
        lng=lng_val
    )
    db.add(event)
    db.commit()

    # Broadcast location update via WebSocket
    try:
        from ws_manager import broadcast_shipment
        await broadcast_shipment(shipment_id, {
            "type": "driver_location",
            "lat": lat_val,
            "lng": lng_val
        })
    except Exception as e:
        print(f"Failed to broadcast driver location: {e}")

    return {"message": "Location updated"}


@router.get("/{shipment_id}/location")
def get_latest_location(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Get the latest GPS location for a shipment.
    Shipper polls this to see where the driver is.
    """
    get_current_user(authorization)

    latest = db.query(TrackingEvent).filter(
        TrackingEvent.shipment_id == shipment_id
    ).order_by(TrackingEvent.timestamp.desc()).first()

    if not latest:
        return {"location": None, "message": "No location data yet"}

    return {
        "lat": latest.lat,
        "lng": latest.lng,
        "timestamp": latest.timestamp.isoformat()
    }
