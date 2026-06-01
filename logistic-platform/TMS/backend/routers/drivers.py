from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Rating, Shipment
from ..auth_utils import get_current_user

router = APIRouter()


@router.get("/me/profile")
def get_my_driver_profile(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Driver fetches their own profile — same data as public profile but uses JWT identity.
    Must be registered BEFORE /{driver_id}/profile so 'me' isn't matched as a driver_id.
    """
    user = get_current_user(authorization)
    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can access this endpoint")

    return get_driver_profile(user["sub"], db, authorization)


@router.get("/{driver_id}/profile")
def get_driver_profile(
    driver_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Get a driver's public profile — average rating, trip count, full rating history.
    Visible to any logged-in user (shippers use this when evaluating bids).
    """
    get_current_user(authorization)  # must be logged in

    driver = db.query(User).filter(User.id == driver_id, User.role == "driver").first()
    if not driver:
        raise HTTPException(404, "Driver not found")

    # All ratings this driver has received across all shippers
    ratings = (
        db.query(Rating)
        .filter(Rating.driver_id == driver_id)
        .order_by(Rating.created_at.desc())
        .all()
    )

    total = len(ratings)
    avg   = round(sum(r.score for r in ratings) / total, 2) if total else None

    # Star breakdown: count of each score 1-5
    breakdown = {str(i): 0 for i in range(1, 6)}
    for r in ratings:
        key = str(int(r.score))
        if key in breakdown:
            breakdown[key] += 1

    # Total completed trips
    completed_trips = db.query(Shipment).filter(
        Shipment.assigned_driver_id == driver_id,
        Shipment.status == "delivered"
    ).count()

    # Build rating history with shipment info
    history = []
    for r in ratings:
        shipment = db.query(Shipment).filter(Shipment.id == r.shipment_id).first()
        shipper  = db.query(User).filter(User.id == r.shipper_id).first()
        history.append({
            "score":          r.score,
            "created_at":     r.created_at.isoformat(),
            "shipper_name":   shipper.name if shipper else "Unknown",
            "shipment_goods": shipment.goods_desc if shipment else "—",
            "shipment_route": (
                f"{shipment.pickup_address} → {shipment.drop_address}"
                if shipment else "—"
            ),
        })

    return {
        "driver_id":       driver.id,
        "driver_name":     driver.name,
        "driver_phone":    driver.phone,
        "avg_rating":      avg,
        "total_ratings":   total,
        "completed_trips": completed_trips,
        "breakdown":       breakdown,
        "history":         history,
    }
