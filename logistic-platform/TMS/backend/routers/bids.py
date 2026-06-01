from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Bid, Shipment, User, Rating
from ..auth_utils import get_current_user

from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class BidCreate(BaseModel):
    amount: float

class AwardRequest(BaseModel):
    bid_id: Optional[str] = None

@router.post("/{shipment_id}/bid")
def place_bid(
    shipment_id: str,
    bid: BidCreate,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Driver places a bid on an open shipment.
    Body: { amount }
    - Only drivers can bid
    - Shipment must be 'open'
    - Driver cannot bid twice on same shipment
    """
    user = get_current_user(authorization)

    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can place bids")

    # KYC guard — driver must be verified before bidding
    driver_record = db.query(User).filter(User.id == user["sub"]).first()
    if driver_record and driver_record.kyc_status != "verified":
        status = driver_record.kyc_status if driver_record else "pending"
        if status == "rejected":
            raise HTTPException(403, "Your KYC verification was rejected. Please contact support.")
        elif status == "manual_review":
            raise HTTPException(403, "Your KYC is under manual review. You will be notified once approved.")
        else:
            raise HTTPException(403, "KYC verification required. Please complete your identity verification before placing bids.")


    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(404, "Shipment not found")

    if shipment.status != "open":
        raise HTTPException(400, f"Shipment is not open for bidding (status: {shipment.status})")

    # Check if driver already bid on this shipment
    existing_bid = db.query(Bid).filter(
        Bid.shipment_id == shipment_id,
        Bid.driver_id == user["sub"]
    ).first()

    if existing_bid:
        # Allow updating bid instead of blocking
        existing_bid.amount = float(bid.amount)
        db.commit()
        return {"message": "Bid updated successfully", "bid_amount": existing_bid.amount}

    new_bid = Bid(
        shipment_id=shipment_id,
        driver_id=user["sub"],
        amount=float(bid.amount)
    )
    db.add(new_bid)
    db.commit()
    db.refresh(new_bid)

    # Compute current bid stats for this shipment
    bid_count = db.query(Bid).filter(Bid.shipment_id == shipment_id).count()
    lowest_bid = db.query(Bid).filter(Bid.shipment_id == shipment_id).order_by(Bid.amount).first()
    lowest_amount = lowest_bid.amount if lowest_bid else None
    return {
        "message": "Bid placed successfully",
        "bid_id": new_bid.id,
        "bid_amount": new_bid.amount,
        "bid_count": bid_count,
        "lowest_bid": lowest_amount
    }

@router.get("/{shipment_id}/bids")
def get_bids_for_shipment(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Get all bids for a shipment — shipper sees this to pick the winner.
    Sorted by amount (lowest first).
    """
    user = get_current_user(authorization)

    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(404, "Shipment not found")

    # Shippers see all bids, drivers only see their own
    if user["role"] == "shipper":
        bids = db.query(Bid).filter(Bid.shipment_id == shipment_id).order_by(Bid.amount).all()
    else:
        bids = db.query(Bid).filter(
            Bid.shipment_id == shipment_id,
            Bid.driver_id == user["sub"]
        ).all()

    result = []
    for b in bids:
        driver = db.query(User).filter(User.id == b.driver_id).first()
        ratings = db.query(Rating).filter(Rating.driver_id == b.driver_id).all()
        driver_rating_count = len(ratings)
        driver_avg_rating = sum(r.score for r in ratings) / driver_rating_count if driver_rating_count > 0 else None
        result.append({
            "bid_id": b.id,
            "driver_name": driver.name if driver else "Unknown",
            "driver_phone": driver.phone if driver else None,
            "driver_avg_rating": driver_avg_rating,
            "driver_rating_count": driver_rating_count,
            "amount": b.amount,
            "is_winner": b.is_winner,
            "created_at": b.created_at.isoformat()
        })

    return result

@router.post("/{shipment_id}/award")
def award_shipment(
    shipment_id: str,
    award: AwardRequest,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Shipper awards the shipment to a specific bid (or auto-awards to lowest).
    Body: { bid_id } OR {} for auto-award to lowest bid
    """
    user = get_current_user(authorization)

    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can award shipments")

    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(404, "Shipment not found")

    if shipment.status != "open":
        raise HTTPException(400, "Shipment is already assigned or closed")

    if shipment.shipper_id != user["sub"]:
        raise HTTPException(403, "You don't own this shipment")

    # Auto-award to lowest bid if no bid_id given
    if award.bid_id:
        winning_bid = db.query(Bid).filter(Bid.id == award.bid_id).first()
        if not winning_bid or winning_bid.shipment_id != shipment_id:
            raise HTTPException(404, "Bid not found for this shipment")
    else:
        # Find the lowest bid automatically
        winning_bid = db.query(Bid).filter(
            Bid.shipment_id == shipment_id
        ).order_by(Bid.amount).first()
        if not winning_bid:
            raise HTTPException(400, "No bids placed yet — cannot award")

    # Mark winner
    winning_bid.is_winner = True

    # Update shipment
    shipment.status = "assigned"
    shipment.assigned_driver_id = winning_bid.driver_id
    shipment.winning_bid_amount = winning_bid.amount

    db.commit()

    driver = db.query(User).filter(User.id == winning_bid.driver_id).first()
    return {
        "message": "Shipment awarded successfully",
        "awarded_to": driver.name if driver else "Unknown",
        "winning_amount": winning_bid.amount
    }
