from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Shipment, User, Bid, Rating, ShipmentDestination, Payment, TrackingEvent, CancellationRecord, DestinationChangeRequest
from ..auth_utils import get_current_user

import datetime
import math

def haversine_distance(lat1, lon1, lat2, lon2):
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 0.0
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def _release_escrow(shipment_id: str, db: Session):
    """Mark escrow payment as released to driver after delivery."""
    payment = db.query(Payment).filter(
        Payment.shipment_id == shipment_id,
        Payment.status == "escrow_held"
    ).first()
    if payment:
        payment.status = "released_to_driver"
        db.commit()

def _freight_adjustment_payload(s: Shipment):
    status = s.freight_adjustment_status or "none"
    deadline = None
    seconds_left = None
    if s.freight_adjustment_requested_at and status == "pending":
        deadline_dt = s.freight_adjustment_requested_at + datetime.timedelta(minutes=5)
        deadline = deadline_dt.isoformat()
        seconds_left = max(0, int((deadline_dt - datetime.datetime.utcnow()).total_seconds()))
    return {
        "freight_adjusted_amount": s.freight_adjusted_amount,
        "freight_adjustment_delta": s.freight_adjustment_delta,
        "freight_adjustment_status": status,
        "freight_adjustment_note": s.freight_adjustment_note,
        "freight_adjustment_requested_at": s.freight_adjustment_requested_at.isoformat() if s.freight_adjustment_requested_at else None,
        "freight_adjustment_accepted_at": s.freight_adjustment_accepted_at.isoformat() if s.freight_adjustment_accepted_at else None,
        "freight_adjustment_paid_at": s.freight_adjustment_paid_at.isoformat() if s.freight_adjustment_paid_at else None,
        "freight_adjustment_expires_at": deadline,
        "freight_adjustment_seconds_left": seconds_left,
    }

def _ensure_adjustment_resolved_for_delivery(s: Shipment, db: Session = None):
    if (s.freight_adjustment_status or "none") == "pending":
        if s.freight_adjustment_requested_at:
            deadline = s.freight_adjustment_requested_at + datetime.timedelta(minutes=5)
            if datetime.datetime.utcnow() > deadline:
                s.freight_adjustment_status = "expired"
                s.freight_adjustment_accepted_at = datetime.datetime.utcnow()
                if db:
                    db.commit()
                return
        delta = float(s.freight_adjustment_delta or 0)
        if delta > 0:
            raise HTTPException(400, "Extra freight payment is pending before delivery can be completed")
        raise HTTPException(400, "Lower freight adjustment is pending shipper acceptance")

router = APIRouter()


@router.post("/")
def create_shipment(
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Shipper creates a new shipment (load posting).
    Body: { pickup_address, drop_address, goods_desc, weight_kg, vehicle_type, deadline }
    """
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can post shipments")


    deadline = None
    if data.get("deadline"):
        try:
            deadline = datetime.datetime.fromisoformat(data["deadline"])
            now = datetime.datetime.utcnow()
            if deadline <= now:
                raise HTTPException(400, "Deadline must be in the future")
            if deadline > now + datetime.timedelta(days=365):
                raise HTTPException(400, "Deadline cannot be more than 1 year from today")
        except HTTPException:
            raise
        except Exception:
            pass

    shipment = Shipment(
        shipper_id=user["sub"],
        pickup_address=data.get("pickup_address", "Unknown"),
        pickup_lat=data.get("pickup_lat"),
        pickup_lng=data.get("pickup_lng"),
        drop_address=data.get("drop_address", ""),
        goods_desc=data.get("goods_desc"),
        weight_kg=float(data.get("weight_kg", 0)),
        vehicle_type=data.get("vehicle_type", "Truck"),
        deadline=deadline,
        est_time_hours=data.get("est_time_hours"),
        num_trucks=int(data.get("num_trucks", 1)),
        status="open"
    )
    destinations = data.get("destinations", [])
    if not destinations and not data.get("drop_address"):
        raise HTTPException(400, "Shipment must have at least one destination")

    db.add(shipment)
    db.flush()
    for idx, dest in enumerate(destinations):
        if not dest.get("address"):
            raise HTTPException(400, f"Destination {idx+1} address is required")
        d = ShipmentDestination(
            shipment_id=shipment.id,
            address=dest.get("address", f"Stop {idx+1}"),
            lat=dest.get("lat", 0.0),
            lng=dest.get("lng", 0.0),
            order_index=idx
        )
        db.add(d)

    db.commit()
    db.refresh(shipment)

    return {"message": "Shipment posted successfully", "shipment_id": shipment.id}


@router.get("/open")
def get_open_shipments(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Get all open shipments — drivers see this to place bids.
    """
    get_current_user(authorization)  # must be logged in

    shipments = db.query(Shipment).filter(Shipment.status == "open").all()
    result = []
    for s in shipments:
        bid_count = db.query(Bid).filter(Bid.shipment_id == s.id).count()
        lowest_bid = db.query(Bid).filter(Bid.shipment_id == s.id).order_by(Bid.amount).first()
        dests = db.query(ShipmentDestination).filter(ShipmentDestination.shipment_id == s.id).order_by(ShipmentDestination.order_index).all()

        result.append({
            "id": s.id,
            "pickup_address": s.pickup_address,
            "pickup_lat": s.pickup_lat,
            "pickup_lng": s.pickup_lng,
            "drop_address": s.drop_address,
            "goods_desc": s.goods_desc,
            "weight_kg": s.weight_kg,
            "vehicle_type": s.vehicle_type,
            "est_time_hours": s.est_time_hours,
            "deadline": s.deadline.isoformat() if s.deadline else None,
            "created_at": s.created_at.isoformat(),
            "bid_count": bid_count,
            "lowest_bid": lowest_bid.amount if lowest_bid else None,
            "destinations": [{"id": d.id, "address": d.address, "lat": d.lat, "lng": d.lng, "status": d.status, "order_index": d.order_index, "ack_status": d.ack_status} for d in dests]
        })

    return result


@router.get("/my")
def get_my_shipments(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Shipper: see all shipments they posted.
    Driver: see all shipments they were assigned to.
    """
    user = get_current_user(authorization)

    if user["role"] == "shipper":
        shipments = db.query(Shipment).filter(Shipment.shipper_id == user["sub"]).all()
    else:
        shipments = db.query(Shipment).filter(Shipment.assigned_driver_id == user["sub"]).all()

    result = []
    for s in shipments:
        bids = db.query(Bid).filter(Bid.shipment_id == s.id).all()
        dests = db.query(ShipmentDestination).filter(ShipmentDestination.shipment_id == s.id).order_by(ShipmentDestination.order_index).all()
        assigned_driver = None
        if s.assigned_driver_id:
            d = db.query(User).filter(User.id == s.assigned_driver_id).first()
            if d:
                assigned_driver = {"id": d.id, "name": d.name, "phone": d.phone}
        
        payment = db.query(Payment).filter(Payment.shipment_id == s.id).order_by(Payment.created_at.desc()).first()
        driver_fee = payment.driver_fee if (payment and payment.status == "cancelled_with_fee") else None
        shipper_refund = payment.shipper_refund if (payment and payment.status == "cancelled_with_fee") else None

        result.append({
            "id": s.id,
            "pickup_address": s.pickup_address,
            "pickup_lat": s.pickup_lat,
            "pickup_lng": s.pickup_lng,
            "drop_address": s.drop_address,
            "goods_desc": s.goods_desc,
            "weight_kg": s.weight_kg,
            "vehicle_type": s.vehicle_type,
            "status": s.status,
            "est_time_hours": s.est_time_hours,
            "deadline": s.deadline.isoformat() if s.deadline else None,
            "created_at": s.created_at.isoformat(),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "delivered_at": s.delivered_at.isoformat() if s.delivered_at else None,
            "winning_bid_amount": s.winning_bid_amount,
            **_freight_adjustment_payload(s),
            "assigned_driver": assigned_driver,
            "driver_fee": driver_fee,
            "shipper_refund": shipper_refund,
            "destinations": [
            {
                "id": d.id,
                "address": d.address,
                "lat": d.lat,
                "lng": d.lng,
                "status": d.status,
                "order_index": d.order_index,
                "ack_status": d.ack_status,
                "pending_change": next(
                    ({"new_address": r.new_address, "new_lat": r.new_lat, "new_lng": r.new_lng, "request_id": r.id}
                     for r in db.query(DestinationChangeRequest).filter(
                         DestinationChangeRequest.dest_id == d.id,
                         DestinationChangeRequest.status == "pending"
                     ).all()),
                    None
                )
            }
            for d in dests
        ],
            "bids": [
                {
                    "id": b.id,
                    "driver_id": b.driver_id,
                    "amount": b.amount,
                    "is_winner": b.is_winner,
                    "created_at": b.created_at.isoformat()
                }
                for b in bids
            ]
        })

    return result


@router.get("/my-bids")
def get_my_bids(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Driver fetches all their bids with full shipment details.
    Must be registered BEFORE /{shipment_id} to avoid route conflict.
    """
    user = get_current_user(authorization)
    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can access their bids")

    bids = (
        db.query(Bid, Shipment)
        .join(Shipment, Shipment.id == Bid.shipment_id)
        .filter(Bid.driver_id == user["sub"])
        .filter(or_(Shipment.status != "cancelled", Bid.is_winner == True))
        .order_by(Bid.created_at.desc())
        .all()
    )

    result = []
    for bid, shipment in bids:
        lowest = (
            db.query(Bid)
            .filter(Bid.shipment_id == shipment.id)
            .order_by(Bid.amount)
            .first()
        )
        lowest_amount = lowest.amount if lowest else None
        is_my_bid_lowest = lowest_amount is not None and bid.amount <= lowest_amount

        # Detect abandoned trip: shipment is "delivered" but a child shipment was
        # created for the remaining stops (parent_shipment_id points back to this one)
        was_abandoned = False
        if bid.is_winner and shipment.status == "delivered":
            child = db.query(Shipment).filter(
                Shipment.parent_shipment_id == shipment.id
            ).first()
            was_abandoned = child is not None

        payment = db.query(Payment).filter(Payment.shipment_id == shipment.id).order_by(Payment.created_at.desc()).first()
        driver_fee = payment.driver_fee if (payment and payment.status == "cancelled_with_fee") else None
        shipper_refund = payment.shipper_refund if (payment and payment.status == "cancelled_with_fee") else None

        result.append({
            "bid_id":             bid.id,
            "my_amount":          bid.amount,
            "is_winner":          bid.is_winner,
            "was_abandoned":      was_abandoned,
            "placed_at":          bid.created_at.isoformat(),
            "is_lowest":          is_my_bid_lowest,
            "lowest_amount":      lowest_amount,
            "shipment_id":        shipment.id,
            "shipment_status":    shipment.status,
            "pickup_address":     shipment.pickup_address,
            "drop_address":       shipment.drop_address,
            "goods_desc":         shipment.goods_desc,
            "weight_kg":          shipment.weight_kg,
            "vehicle_type":       shipment.vehicle_type,
            "deadline":           shipment.deadline.isoformat() if shipment.deadline else None,
            "winning_bid_amount": shipment.winning_bid_amount,
            **_freight_adjustment_payload(shipment),
            "driver_fee":         driver_fee,
            "shipper_refund":     shipper_refund,
            "total_bids":         db.query(Bid).filter(Bid.shipment_id == shipment.id).count(),
        })

    return result


@router.get("/{shipment_id}")
def get_shipment(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Get a single shipment with all bids."""
    get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    bids = db.query(Bid).filter(Bid.shipment_id == s.id).order_by(Bid.amount).all()
    driver = None
    if s.assigned_driver_id:
        d = db.query(User).filter(User.id == s.assigned_driver_id).first()
        if d:
            driver = {"id": d.id, "name": d.name, "phone": d.phone}

    rating = db.query(Rating).filter(Rating.shipment_id == s.id).first()
    shipper_rating = rating.score if rating else None
    
    dests = db.query(ShipmentDestination).filter(ShipmentDestination.shipment_id == s.id).order_by(ShipmentDestination.order_index).all()

    payment = db.query(Payment).filter(Payment.shipment_id == s.id).order_by(Payment.created_at.desc()).first()
    driver_fee = payment.driver_fee if (payment and payment.status == "cancelled_with_fee") else None
    shipper_refund = payment.shipper_refund if (payment and payment.status == "cancelled_with_fee") else None

    change_reqs = db.query(DestinationChangeRequest).filter(
        DestinationChangeRequest.shipment_id == s.id
    ).all()

    return {
        "id": s.id,
        "pickup_address": s.pickup_address,
        "pickup_lat": s.pickup_lat,
        "pickup_lng": s.pickup_lng,
        "drop_address": s.drop_address,
        "goods_desc": s.goods_desc,
        "weight_kg": s.weight_kg,
        "vehicle_type": s.vehicle_type,
        "status": s.status,
        "est_time_hours": s.est_time_hours,
        "deadline": s.deadline.isoformat() if s.deadline else None,
        "created_at": s.created_at.isoformat(),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "delivered_at": s.delivered_at.isoformat() if s.delivered_at else None,
        "winning_bid_amount": s.winning_bid_amount,
        **_freight_adjustment_payload(s),
        "driver_fee": driver_fee,
        "shipper_refund": shipper_refund,
        "assigned_driver": driver,
        "shipper_rating": shipper_rating,
        "destinations": [
            {
                "id": d.id,
                "address": d.address,
                "lat": d.lat,
                "lng": d.lng,
                "status": d.status,
                "order_index": d.order_index,
                "ack_status": d.ack_status,
                "pending_change": next(
                    ({"new_address": r.new_address, "new_lat": r.new_lat, "new_lng": r.new_lng, "request_id": r.id}
                     for r in db.query(DestinationChangeRequest).filter(
                         DestinationChangeRequest.dest_id == d.id,
                         DestinationChangeRequest.status == "pending"
                     ).all()),
                    None
                )
            }
            for d in dests
        ],
        "destination_change_requests": [
            {
                "id": cr.id,
                "dest_id": cr.dest_id,
                "new_address": cr.new_address,
                "new_lat": cr.new_lat,
                "new_lng": cr.new_lng,
                "status": cr.status,
                "created_at": cr.created_at.isoformat() if cr.created_at else None
            }
            for cr in change_reqs
        ],
        "bids": [
            {
                "id": b.id,
                "driver_id": b.driver_id,
                "amount": b.amount,
                "is_winner": b.is_winner,
                "created_at": b.created_at.isoformat()
            }
            for b in bids
        ]
    }


@router.post("/{shipment_id}/rate")
def rate_driver(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Shipper rates the assigned driver after delivery.
    Body: { score } (float 1-5)
    """
    user = get_current_user(authorization)

    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can rate drivers")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    if s.shipper_id != user["sub"]:
        raise HTTPException(403, "You don't own this shipment")

    if s.status != "delivered":
        raise HTTPException(400, "You can only rate after shipment is delivered")

    # Check if already rated
    existing_rating = db.query(Rating).filter(Rating.shipment_id == shipment_id).first()
    if existing_rating:
        raise HTTPException(400, "You have already rated this shipment")

    score = float(data.get("score", 0))
    if score < 1 or score > 5:
        raise HTTPException(400, "Score must be between 1 and 5")

    rating = Rating(
        shipment_id=shipment_id,
        driver_id=s.assigned_driver_id,
        shipper_id=user["sub"],
        score=score
    )
    db.add(rating)
    db.commit()

    return {"message": "Rating submitted successfully", "score": score}


@router.patch("/{shipment_id}/status")
def update_status(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Driver updates shipment status (in_transit → delivered).
    Body: { status }
    """
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    allowed_statuses = ["in_transit", "delivered"]
    if data["status"] not in allowed_statuses:
        raise HTTPException(400, f"Status must be one of: {allowed_statuses}")

    if user["role"] == "driver" and s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "You are not assigned to this shipment")

    if data["status"] == "delivered":
        _ensure_adjustment_resolved_for_delivery(s, db)

    s.status = data["status"]
    if data["status"] == "in_transit":
        s.started_at = datetime.datetime.utcnow()
    elif data["status"] == "delivered":
        s.delivered_at = datetime.datetime.utcnow()

    db.commit()
    # Auto-release escrow when driver marks delivered directly
    if data["status"] == "delivered":
        _release_escrow(shipment_id, db)

    return {"message": f"Status updated to {data['status']}"}


@router.post("/{shipment_id}/destinations/{dest_id}/arrive")
def driver_arrive_at_destination(
    shipment_id: str,
    dest_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Driver sends arrival acknowledgement at a stop.
    Sets ack_status = 'pending_approval'. Shipper must approve before
    driver can mark it delivered.
    """
    user = get_current_user(authorization)
    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can send arrival acknowledgements")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")

    if s.status != "in_transit":
        raise HTTPException(400, "Shipment is not in transit")

    dest = db.query(ShipmentDestination).filter(
        ShipmentDestination.id == dest_id,
        ShipmentDestination.shipment_id == shipment_id
    ).first()
    if not dest:
        raise HTTPException(404, "Destination not found")

    if dest.status == "delivered":
        raise HTTPException(400, "This stop is already delivered")

    if dest.ack_status == "pending_approval":
        raise HTTPException(400, "Arrival already sent — waiting for shipper approval")

    if dest.ack_status == "approved":
        raise HTTPException(400, "Arrival already approved — mark it delivered")

    # Enforce sequential order: previous stops must be delivered first
    all_dests = db.query(ShipmentDestination).filter(
        ShipmentDestination.shipment_id == shipment_id
    ).order_by(ShipmentDestination.order_index).all()

    for d in all_dests:
        if d.order_index < dest.order_index and d.status != "delivered":
            raise HTTPException(
                400,
                f"Complete stop #{d.order_index + 1} ({d.address}) before arriving at this one"
            )

    dest.ack_status = "pending_approval"
    db.commit()

    return {"message": "Arrival acknowledgement sent. Waiting for shipper approval."}


@router.post("/{shipment_id}/destinations/{dest_id}/approve")
def shipper_approve_arrival(
    shipment_id: str,
    dest_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Shipper approves the driver's arrival at a stop.
    Sets ack_status = 'approved'. Driver can now mark it delivered.
    """
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can approve arrivals")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    if s.shipper_id != user["sub"]:
        raise HTTPException(403, "You don't own this shipment")

    dest = db.query(ShipmentDestination).filter(
        ShipmentDestination.id == dest_id,
        ShipmentDestination.shipment_id == shipment_id
    ).first()
    if not dest:
        raise HTTPException(404, "Destination not found")

    if dest.ack_status not in ("pending_approval", "none"):
        raise HTTPException(400, "This stop is already approved or delivered")

    dest.ack_status = "approved"
    db.commit()

    return {"message": f"Arrival at stop approved. Driver can now mark it delivered."}


@router.patch("/{shipment_id}/destinations/{dest_id}")
def update_destination_status(
    shipment_id: str,
    dest_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    user = get_current_user(authorization)
    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or (user["role"] == "driver" and s.assigned_driver_id != user["sub"]):
        raise HTTPException(403, "Not authorized or not found")

    dest = db.query(ShipmentDestination).filter(
        ShipmentDestination.id == dest_id,
        ShipmentDestination.shipment_id == shipment_id
    ).first()
    if not dest:
        raise HTTPException(404, "Destination not found")

    if data.get("status") == "delivered":
        # Enforce that shipper has approved the arrival before allowing delivery mark
        if dest.ack_status != "approved":
            raise HTTPException(
                400,
                "Shipper must approve your arrival at this stop before you can mark it delivered"
            )

        # Enforce sequential order: every stop with a lower order_index must already be delivered
        all_dests = db.query(ShipmentDestination).filter(
            ShipmentDestination.shipment_id == shipment_id
        ).order_by(ShipmentDestination.order_index).all()

        for d in all_dests:
            if d.order_index < dest.order_index and d.status != "delivered":
                raise HTTPException(
                    400,
                    f"Complete stop #{d.order_index + 1} ({d.address}) before marking this one delivered"
                )

        if all(d.id == dest.id or d.status == "delivered" for d in all_dests):
            _ensure_adjustment_resolved_for_delivery(s, db)

        dest.status = "delivered"
        dest.ack_status = "approved"  # keep it consistent
        db.commit()

        # Re-fetch to check if all are now delivered
        all_dests = db.query(ShipmentDestination).filter(
            ShipmentDestination.shipment_id == shipment_id
        ).all()
        if all(d.status == "delivered" for d in all_dests):
            _ensure_adjustment_resolved_for_delivery(s, db)
            s.status = "delivered"
            s.delivered_at = datetime.datetime.utcnow()
            db.commit()
            # Auto-release escrow to driver
            _release_escrow(shipment_id, db)

    elif data.get("status") == "pending":
        dest.status = "pending"
        dest.ack_status = "none"
        db.commit()

    return {"message": "Destination updated"}


@router.post("/{shipment_id}/cancel")
def cancel_shipment(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Shipper cancels a shipment. Handles all scenarios:

    Scenario 1 — open, no bids:
      Free cancel. No payment involved.

    Scenario 2 — open, bids placed:
      Free cancel. Bids voided. No payment involved.

    Scenario 3 — assigned (escrow held, driver en route):
      20% of trip fare kept as compensation for driver.
      80% refunded to shipper (simulated — payment record updated).
      Shipment cancelled.

    Scenario 4 — in_transit:
      Cannot cancel via this endpoint. Use abandon instead.

    Body: { reason: str }
    """
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can cancel shipments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")
    if s.shipper_id != user["sub"]:
        raise HTTPException(403, "You don't own this shipment")
    if s.status == "delivered":
        raise HTTPException(400, "Cannot cancel a delivered shipment")
    if s.status == "cancelled":
        raise HTTPException(400, "Shipment is already cancelled")

    reason = (data.get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "Cancellation reason is required")

    bid_count = db.query(Bid).filter(Bid.shipment_id == shipment_id).count()

    # ── Scenario 1 & 2: open shipment ─────────────────────────
    if s.status == "open":
        s.status = "cancelled"
        rec = CancellationRecord(
            shipment_id=shipment_id, shipper_id=user["sub"],
            driver_id=s.assigned_driver_id, reason=reason,
            scenario="no_penalty", trip_amount=0, driver_fee=0, shipper_refund=0
        )
        db.add(rec)
        db.commit()
        return {
            "message":          "Shipment cancelled successfully",
            "scenario":         "no_penalty",
            "driver_fee":       0,
            "shipper_refund":   0,
            "bid_count":        bid_count
        }

    # ── Scenario 3: assigned — escrow held, driver en route ───
    if s.status == "assigned":
        # Check if driver has physically arrived at pickup
        dests = db.query(ShipmentDestination).filter(
            ShipmentDestination.shipment_id == shipment_id
        ).order_by(ShipmentDestination.order_index).all()

        driver_arrived = any(
            d.ack_status in ("pending_approval", "approved") for d in dests
        )

        trip_amount = s.winning_bid_amount or 0

        # ── KM-based compensation formula ─────────────────────
        # Total route = pickup → all stops (haversine)
        # Driver travelled = pickup → driver's last GPS position
        #
        # driver_fee = (km_travelled / total_route_km) × bid_amount
        # Minimum guaranteed: ₹50 (fuel cost floor)
        # Maximum cap: 50% of bid (driver hasn't loaded goods yet)

        total_route_km = 0.0
        prev_lat, prev_lng = s.pickup_lat, s.pickup_lng
        for d in dests:
            total_route_km += haversine_distance(prev_lat, prev_lng, d.lat, d.lng)
            prev_lat, prev_lng = d.lat, d.lng

        # Get driver's last known GPS position
        last_gps = db.query(TrackingEvent).filter(
            TrackingEvent.shipment_id == shipment_id
        ).order_by(TrackingEvent.timestamp.desc()).first()

        km_travelled = 0.0
        if last_gps and s.pickup_lat and s.pickup_lng:
            km_travelled = haversine_distance(
                s.pickup_lat, s.pickup_lng,
                last_gps.lat, last_gps.lng
            )

        # Calculate proportional fee
        if total_route_km > 0 and km_travelled > 0:
            proportion  = min(km_travelled / total_route_km, 0.50)  # cap at 50%
            driver_fee  = round(max(50.0, trip_amount * proportion), 2)
        elif driver_arrived:
            # Driver arrived but no GPS data — use 25% as fallback
            driver_fee = round(trip_amount * 0.25, 2)
        else:
            # Driver en route, no GPS — use 10% as fallback
            driver_fee = round(max(50.0, trip_amount * 0.10), 2)

        driver_fee = min(driver_fee, trip_amount * 0.50)  # hard cap at 50%
        refund     = round(trip_amount - driver_fee, 2)

        # Update payment record
        payment = db.query(Payment).filter(
            Payment.shipment_id == shipment_id,
            Payment.status.in_(["escrow_held", "succeeded", "pending"])
        ).first()
        if payment:
            payment.status = "cancelled_with_fee"
            payment.driver_fee = driver_fee
            payment.shipper_refund = refund
            db.commit()

        # Mark shipment cancelled
        s.status = "cancelled"
        rec = CancellationRecord(
            shipment_id=shipment_id, shipper_id=user["sub"],
            driver_id=s.assigned_driver_id, reason=reason,
            scenario="assigned_penalty", trip_amount=trip_amount,
            driver_fee=driver_fee, shipper_refund=refund,
            km_travelled=round(km_travelled, 1),
            total_route_km=round(total_route_km, 1)
        )
        db.add(rec)
        db.commit()

        return {
            "message":        "Shipment cancelled. Driver compensation applied.",
            "scenario":       "assigned_penalty",
            "driver_arrived": driver_arrived,
            "km_travelled":   round(km_travelled, 1),
            "total_route_km": round(total_route_km, 1),
            "trip_amount":    trip_amount,
            "driver_fee":     driver_fee,
            "shipper_refund": refund,
            "driver_id":      s.assigned_driver_id
        }

    # ── Scenario 4: in_transit — driver is on the road ────────
    # Goods are NOT considered loaded until shipper approves arrival.
    # Pay proportionally: (completed stops / total stops) × bid amount
    if s.status == "in_transit":
        all_dests      = db.query(ShipmentDestination).filter(
            ShipmentDestination.shipment_id == shipment_id
        ).order_by(ShipmentDestination.order_index).all()

        total_stops     = len(all_dests)
        completed_stops = sum(1 for d in all_dests if d.status == "delivered")
        trip_amount     = s.winning_bid_amount or 0

        if total_stops > 0 and completed_stops > 0:
            proportion = completed_stops / total_stops
            driver_fee = round(trip_amount * proportion, 2)
        else:
            # No stops completed — use km-based formula same as assigned
            last_gps = db.query(TrackingEvent).filter(
                TrackingEvent.shipment_id == shipment_id
            ).order_by(TrackingEvent.timestamp.desc()).first()

            total_route_km = 0.0
            prev_lat, prev_lng = s.pickup_lat, s.pickup_lng
            for d in all_dests:
                total_route_km += haversine_distance(prev_lat, prev_lng, d.lat, d.lng)
                prev_lat, prev_lng = d.lat, d.lng

            km_travelled = 0.0
            if last_gps and s.pickup_lat and s.pickup_lng:
                km_travelled = haversine_distance(
                    s.pickup_lat, s.pickup_lng, last_gps.lat, last_gps.lng
                )

            if total_route_km > 0 and km_travelled > 0:
                proportion = min(km_travelled / total_route_km, 0.50)
                driver_fee = round(max(50.0, trip_amount * proportion), 2)
            else:
                driver_fee = round(max(50.0, trip_amount * 0.10), 2)

        driver_fee = min(driver_fee, trip_amount)
        refund     = round(trip_amount - driver_fee, 2)

        payment = db.query(Payment).filter(
            Payment.shipment_id == shipment_id,
            Payment.status.in_(["escrow_held", "succeeded", "pending"])
        ).first()
        if payment:
            payment.status = "cancelled_with_fee"
            payment.driver_fee = driver_fee
            payment.shipper_refund = refund
            db.commit()

        s.status = "cancelled"
        rec = CancellationRecord(
            shipment_id=shipment_id, shipper_id=user["sub"],
            driver_id=s.assigned_driver_id, reason=reason,
            scenario="in_transit_penalty", trip_amount=trip_amount,
            driver_fee=driver_fee, shipper_refund=refund,
            completed_stops=completed_stops, total_stops=total_stops
        )
        db.add(rec)
        db.commit()

        return {
            "message":        "Shipment cancelled mid-trip. Proportional payment applied.",
            "scenario":       "in_transit_penalty",
            "completed_stops": completed_stops,
            "total_stops":    total_stops,
            "trip_amount":    trip_amount,
            "driver_fee":     driver_fee,
            "shipper_refund": refund,
            "driver_id":      s.assigned_driver_id
        }




@router.get("/{shipment_id}/cancellation")
def get_cancellation_record(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Get cancellation details for a shipment (shipper or driver)."""
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    if user["role"] == "shipper" and s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if user["role"] == "driver" and s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")

    rec = db.query(CancellationRecord).filter(
        CancellationRecord.shipment_id == shipment_id
    ).order_by(CancellationRecord.cancelled_at.desc()).first()

    if not rec:
        return None

    shipper = db.query(User).filter(User.id == rec.shipper_id).first()
    driver  = db.query(User).filter(User.id == rec.driver_id).first() if rec.driver_id else None

    return {
        "scenario":        rec.scenario,
        "reason":          rec.reason,
        "trip_amount":     rec.trip_amount,
        "driver_fee":      rec.driver_fee,
        "shipper_refund":  rec.shipper_refund,
        "km_travelled":    rec.km_travelled,
        "total_route_km":  rec.total_route_km,
        "completed_stops": rec.completed_stops,
        "total_stops":     rec.total_stops,
        "cancelled_at":    rec.cancelled_at.isoformat(),
        "shipper_name":    shipper.name if shipper else None,
        "driver_name":     driver.name if driver else None,
        "driver_phone":    driver.phone if driver else None,
    }

@router.post("/{shipment_id}/destinations/{dest_id}/change-request")
async def request_destination_change(
    shipment_id: str,
    dest_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Shipper requests a destination address change while trip is in_transit.
    Body: { new_address, new_lat (optional), new_lng (optional) }
    Driver must accept or reject. If rejected, trip ends at original stop.
    """
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can request destination changes")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")
    if s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if s.status != "in_transit":
        raise HTTPException(400, "Can only change destination while shipment is in transit")

    dest = db.query(ShipmentDestination).filter(
        ShipmentDestination.id == dest_id,
        ShipmentDestination.shipment_id == shipment_id
    ).first()
    if not dest:
        raise HTTPException(404, "Destination not found")
    if dest.status == "delivered":
        raise HTTPException(400, "This stop is already delivered — cannot change it")

    new_address = (data.get("new_address") or "").strip()
    if not new_address:
        raise HTTPException(400, "new_address is required")

    # Cancel any existing pending request for this dest
    db.query(DestinationChangeRequest).filter(
        DestinationChangeRequest.dest_id == dest_id,
        DestinationChangeRequest.status == "pending"
    ).delete()

    req = DestinationChangeRequest(
        shipment_id = shipment_id,
        dest_id     = dest_id,
        shipper_id  = user["sub"],
        driver_id   = s.assigned_driver_id,
        new_address = new_address,
        new_lat     = data.get("new_lat"),
        new_lng     = data.get("new_lng"),
        status      = "pending"
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Broadcast destination change requested via WebSocket
    try:
        from ws_manager import broadcast_shipment
        await broadcast_shipment(shipment_id, {
            "type": "shipment_status",
            "shipment_id": shipment_id,
            "status": s.status,
            "event": "destination_change_requested",
            "dest_id": dest_id,
            "new_address": new_address
        })
    except Exception as e:
        print(f"Failed to broadcast destination change request: {e}")

    return {
        "message":     "Destination change request sent to driver",
        "request_id":  req.id,
        "new_address": new_address,
        "dest_id":     dest_id
    }


@router.post("/{shipment_id}/destinations/{dest_id}/change-request/respond")
async def respond_destination_change(
    shipment_id: str,
    dest_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Driver accepts or rejects a destination change request.
    Body: { action: "accepted" | "rejected" }

    If accepted: destination address is updated, trip continues to new location.
    If rejected: destination is marked delivered at original location,
                 all subsequent stops are removed, trip ends after this stop.
    """
    user = get_current_user(authorization)
    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can respond to destination changes")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")

    req = db.query(DestinationChangeRequest).filter(
        DestinationChangeRequest.dest_id    == dest_id,
        DestinationChangeRequest.shipment_id == shipment_id,
        DestinationChangeRequest.status     == "pending"
    ).first()
    if not req:
        raise HTTPException(404, "No pending change request for this destination")

    action = data.get("action", "").strip()
    if action not in ("accepted", "rejected"):
        raise HTTPException(400, "action must be 'accepted' or 'rejected'")

    req.status      = action
    req.responded_at = datetime.datetime.utcnow()

    dest = db.query(ShipmentDestination).filter(
        ShipmentDestination.id == dest_id
    ).first()

    if action == "accepted":
        # Update the destination address
        dest.address = req.new_address
        if req.new_lat is not None:
            dest.lat = req.new_lat
        if req.new_lng is not None:
            dest.lng = req.new_lng

        # If it's the last stop in the sorted list, update shipment's drop_address
        all_dests = db.query(ShipmentDestination).filter(
            ShipmentDestination.shipment_id == shipment_id
        ).order_by(ShipmentDestination.order_index).all()
        if all_dests and all_dests[-1].id == dest.id:
            s.drop_address = req.new_address

        db.commit()

        # Broadcast destination change accepted via WebSocket
        try:
            from ws_manager import broadcast_shipment
            await broadcast_shipment(shipment_id, {
                "type": "shipment_status",
                "shipment_id": shipment_id,
                "status": s.status,
                "event": "destination_change_accepted",
                "dest_id": dest_id,
                "new_address": req.new_address
            })
        except Exception as e:
            print(f"Failed to broadcast destination change response (accepted): {e}")

        return {
            "message":     "Destination updated. Continue to new location.",
            "new_address": req.new_address
        }

    else:  # rejected
        # Remove all subsequent pending stops
        all_dests = db.query(ShipmentDestination).filter(
            ShipmentDestination.shipment_id == shipment_id
        ).order_by(ShipmentDestination.order_index).all()

        for d in all_dests:
            if d.order_index > dest.order_index and d.status == "pending":
                db.delete(d)

        # Update shipment's drop_address to the current (now final) stop's address
        s.drop_address = dest.address

        db.commit()

        # Broadcast destination change rejected via WebSocket
        try:
            from ws_manager import broadcast_shipment
            await broadcast_shipment(shipment_id, {
                "type": "shipment_status",
                "shipment_id": shipment_id,
                "status": s.status,
                "event": "destination_change_rejected",
                "dest_id": dest_id
            })
        except Exception as e:
            print(f"Failed to broadcast destination change response (rejected): {e}")

        return {
            "message": "Destination change rejected. Please deliver goods at the original location."
        }


@router.get("/{shipment_id}/destinations/{dest_id}/change-request")
def get_pending_change_request(
    shipment_id: str,
    dest_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Get pending destination change request for a stop (driver polls this)."""
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")
    if user["role"] == "driver" and s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")
    if user["role"] == "shipper" and s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")

    req = db.query(DestinationChangeRequest).filter(
        DestinationChangeRequest.dest_id     == dest_id,
        DestinationChangeRequest.shipment_id == shipment_id,
        DestinationChangeRequest.status      == "pending"
    ).first()

    if not req:
        return None

    return {
        "request_id":  req.id,
        "new_address": req.new_address,
        "new_lat":     req.new_lat,
        "new_lng":     req.new_lng,
        "created_at":  req.created_at.isoformat()
    }


@router.post("/{shipment_id}/abandon")
def abandon_shipment(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Driver abandons trip early. Pays proportional to distance covered.
    Splits remaining destinations into a new shipment.
    """
    user = get_current_user(authorization)
    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can abandon trips")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")

    if s.status != "in_transit":
        raise HTTPException(400, "Can only abandon an in-transit shipment")

    dests = db.query(ShipmentDestination).filter(ShipmentDestination.shipment_id == s.id).order_by(ShipmentDestination.order_index).all()
    
    if not dests:
        raise HTTPException(400, "No destinations found to split")

    total_distance = 0.0
    covered_distance = 0.0
    
    last_lat = s.pickup_lat
    last_lng = s.pickup_lng
    
    last_completed_dest = None

    for d in dests:
        dist = haversine_distance(last_lat, last_lng, d.lat, d.lng)
        total_distance += dist
        if d.status == "delivered":
            covered_distance += dist
            last_completed_dest = d
        last_lat = d.lat
        last_lng = d.lng

    if total_distance > 0 and s.winning_bid_amount:
        proportion = covered_distance / total_distance
        s.winning_bid_amount = round(s.winning_bid_amount * proportion, 2)
    else:
        s.winning_bid_amount = 0

    s.status = "delivered" # Mark as delivered for the driver's portion
    s.delivered_at = datetime.datetime.utcnow()

    # Extract pending destinations
    pending_dests = [d for d in dests if d.status == "pending"]

    if pending_dests:
        new_shipment = Shipment(
            shipper_id=s.shipper_id,
            pickup_address=last_completed_dest.address if last_completed_dest else s.pickup_address,
            pickup_lat=last_completed_dest.lat if last_completed_dest else s.pickup_lat,
            pickup_lng=last_completed_dest.lng if last_completed_dest else s.pickup_lng,
            goods_desc=s.goods_desc,
            weight_kg=s.weight_kg,
            vehicle_type=s.vehicle_type,
            status="open",
            parent_shipment_id=s.id
        )
        db.add(new_shipment)
        db.flush()

        for idx, d in enumerate(pending_dests):
            new_dest = ShipmentDestination(
                shipment_id=new_shipment.id,
                address=d.address,
                lat=d.lat,
                lng=d.lng,
                status="pending",
                order_index=idx
            )
            db.add(new_dest)
            
            # Delete old pending destinations
            db.delete(d)

    db.commit()
    return {"message": "Shipment split successfully", "earned": s.winning_bid_amount}
