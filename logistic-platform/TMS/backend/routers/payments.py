"""
Payments router — integrates with localstripe (Stripe-compatible simulation).
Localstripe runs at http://localhost:8420.

NEW FLOW (escrow model):
  1. POST /api/payments/{shipment_id}/award-and-pay
     Shipper selects a bid AND pays in one step.
     - Charges shipper via localstripe (escrow held by platform)
     - Awards the bid (shipment → "assigned", driver notified)
     - Payment status = "escrow_held"
     Driver can now see the trip with "Payment Secured" badge.

  2. POST /api/payments/{shipment_id}/release
     Called automatically when shipment is delivered.
     - Marks payment status = "released_to_driver"
     - Driver's earnings are confirmed.

  3. GET /api/payments/{shipment_id}/status
     Returns payment status for shipper or driver.

LEGACY endpoints kept for backward compatibility:
  POST /create-intent  (now only used for already-delivered shipments)
  POST /pay
"""

import datetime
import requests as http
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Payment, Shipment, Bid, User, Message
from ..auth_utils import get_current_user

router = APIRouter()

LOCALSTRIPE_URL = "http://localhost:8420"
ADJUSTMENT_PAYMENT_WINDOW_SECONDS = 5 * 60
STRIPE_KEY      = "sk_test_localstripe"
AUTH_HEADER     = {"Authorization": f"Bearer {STRIPE_KEY}"}


def _stripe_post(path: str, data: dict) -> dict:
    """POST to localstripe and return parsed JSON, raising on error."""
    try:
        resp = http.post(
            f"{LOCALSTRIPE_URL}{path}",
            data=data,
            headers=AUTH_HEADER,
            timeout=10
        )
    except http.exceptions.ConnectionError:
        raise HTTPException(
            503,
            "Payment service is unavailable. Make sure the localstripe Docker container "
            "is running: docker run -p 8420:8420 adrienverge/localstripe:latest"
        )
    except http.exceptions.Timeout:
        raise HTTPException(503, "Payment service timed out. Please try again.")

    body = resp.json()
    if not resp.ok:
        err = body.get("error", {})
        raise HTTPException(502, err.get("message", "Payment service error"))
    return body

def _active_escrow_payment(db: Session, shipment_id: str):
    return db.query(Payment).filter(
        Payment.shipment_id == shipment_id,
        Payment.status.in_(["escrow_held", "released_to_driver", "succeeded"])
    ).order_by(Payment.created_at.desc()).first()

def _adjustment_payload(s: Shipment):
    deadline = None
    seconds_left = None
    if s.freight_adjustment_requested_at and (s.freight_adjustment_status or "none") == "pending":
        deadline_dt = s.freight_adjustment_requested_at + datetime.timedelta(seconds=ADJUSTMENT_PAYMENT_WINDOW_SECONDS)
        deadline = deadline_dt.isoformat()
        seconds_left = max(0, int((deadline_dt - datetime.datetime.utcnow()).total_seconds()))
    return {
        "freight_adjusted_amount": s.freight_adjusted_amount,
        "freight_adjustment_delta": s.freight_adjustment_delta,
        "freight_adjustment_status": s.freight_adjustment_status or "none",
        "freight_adjustment_note": s.freight_adjustment_note,
        "freight_adjustment_requested_at": s.freight_adjustment_requested_at.isoformat() if s.freight_adjustment_requested_at else None,
        "freight_adjustment_accepted_at": s.freight_adjustment_accepted_at.isoformat() if s.freight_adjustment_accepted_at else None,
        "freight_adjustment_paid_at": s.freight_adjustment_paid_at.isoformat() if s.freight_adjustment_paid_at else None,
        "freight_adjustment_expires_at": deadline,
        "freight_adjustment_seconds_left": seconds_left,
    }


def _expire_overdue_adjustment(s: Shipment, db: Session):
    if (s.freight_adjustment_status or "none") != "pending" or not s.freight_adjustment_requested_at:
        return False
    deadline = s.freight_adjustment_requested_at + datetime.timedelta(seconds=ADJUSTMENT_PAYMENT_WINDOW_SECONDS)
    if datetime.datetime.utcnow() <= deadline:
        return False

    s.freight_adjustment_status = "expired"
    s.freight_adjustment_accepted_at = datetime.datetime.utcnow()
    db.add(Message(
        shipment_id=s.id,
        driver_id=s.assigned_driver_id,
        sender_id=s.assigned_driver_id,
        sender_role="driver",
        body="Extra freight payment window expired. Driver will continue to the previous/original location.",
        created_at=datetime.datetime.utcnow()
    ))
    db.commit()
    return True


# ─────────────────────────────────────────────────────────────
# 0. Get payment intent for award (step 1 of award-and-pay)
# POST /api/payments/{shipment_id}/award-intent
# Body: { bid_id } or {} for lowest bid
# Returns payment_intent_id + amount so frontend can show modal
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/award-intent")
def create_award_intent(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Step 1 of award flow: shipper selects a bid, we create a PaymentIntent.
    Shipment is NOT yet awarded — that happens only after payment succeeds.
    Returns: { payment_intent_id, amount, bid_id, driver_name }
    """
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can initiate payments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")
    if s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if s.status != "open":
        raise HTTPException(400, "Shipment is not open for bidding")

    # Resolve which bid to award
    bid_id = data.get("bid_id")
    if bid_id:
        winning_bid = db.query(Bid).filter(Bid.id == bid_id, Bid.shipment_id == shipment_id).first()
        if not winning_bid:
            raise HTTPException(404, "Bid not found for this shipment")
    else:
        winning_bid = db.query(Bid).filter(Bid.shipment_id == shipment_id).order_by(Bid.amount).first()
        if not winning_bid:
            raise HTTPException(400, "No bids placed yet")

    driver = db.query(User).filter(User.id == winning_bid.driver_id).first()
    amount_paise = max(50, int(winning_bid.amount * 100))

    intent = _stripe_post("/v1/payment_intents", {
        "amount":                    amount_paise,
        "currency":                  "inr",
        "payment_method_types[]":    "card",
        "metadata[shipment_id]":     shipment_id,
        "metadata[bid_id]":          winning_bid.id,
        "metadata[shipper_id]":      user["sub"],
    })

    # Save a pending payment record (not yet awarded)
    db.query(Payment).filter(
        Payment.shipment_id == shipment_id,
        Payment.status == "pending"
    ).delete()

    payment = Payment(
        shipment_id  = shipment_id,
        shipper_id   = user["sub"],
        driver_id    = winning_bid.driver_id,
        amount       = winning_bid.amount,
        currency     = "inr",
        stripe_pi_id = intent["id"],
        status       = "pending"
    )
    db.add(payment)
    db.commit()

    return {
        "payment_intent_id": intent["id"],
        "amount":            winning_bid.amount,
        "bid_id":            winning_bid.id,
        "driver_name":       driver.name if driver else "Unknown",
        "currency":          "inr"
    }


# ─────────────────────────────────────────────────────────────
# 1. Confirm payment + award shipment atomically
# POST /api/payments/{shipment_id}/award-and-pay
# Body: { payment_intent_id, bid_id, card_number, exp_month, exp_year, cvc }
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/award-and-pay")
def award_and_pay(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Step 2: Shipper pays. On success, bid is awarded and shipment → 'assigned'.
    Driver can now see the trip with 'Payment Secured' badge.
    """
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can make payments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if s.status != "open":
        raise HTTPException(400, "Shipment is no longer open")

    pi_id  = data.get("payment_intent_id", "").strip()
    bid_id = data.get("bid_id", "").strip()
    if not pi_id or not bid_id:
        raise HTTPException(400, "payment_intent_id and bid_id are required")

    card_number = str(data.get("card_number", "")).replace(" ", "")
    exp_month   = data.get("exp_month")
    exp_year    = data.get("exp_year")
    cvc         = str(data.get("cvc", "")).strip()

    if not all([card_number, exp_month, exp_year, cvc]):
        raise HTTPException(400, "Card details are required")

    # Find the pending payment record
    payment = db.query(Payment).filter(
        Payment.shipment_id  == shipment_id,
        Payment.stripe_pi_id == pi_id,
        Payment.status       == "pending"
    ).first()
    if not payment:
        raise HTTPException(404, "Payment record not found or already processed")

    # Find the bid
    winning_bid = db.query(Bid).filter(Bid.id == bid_id, Bid.shipment_id == shipment_id).first()
    if not winning_bid:
        raise HTTPException(404, "Bid not found")

    # Charge the shipper via localstripe
    pm = _stripe_post("/v1/payment_methods", {
        "type":              "card",
        "card[number]":      card_number,
        "card[exp_month]":   str(int(exp_month)),
        "card[exp_year]":    str(int(exp_year)),
        "card[cvc]":         cvc,
    })

    amount_paise = max(50, int(payment.amount * 100))
    intent = _stripe_post("/v1/payment_intents", {
        "amount":                 amount_paise,
        "currency":               "inr",
        "payment_method":         pm["id"],
        "confirm":                "true",
        "metadata[shipment_id]":  shipment_id,
        "metadata[bid_id]":       bid_id,
    })

    if intent.get("status") != "succeeded":
        payment.status = "failed"
        db.commit()
        raise HTTPException(402, f"Payment failed. Status: {intent.get('status', 'unknown')}")

    # Extract charge info
    charge_id = None
    latest = intent.get("latest_charge")
    if isinstance(latest, dict):
        charge_id = latest.get("id")
    elif isinstance(latest, str):
        charge_id = latest
    else:
        clist = intent.get("charges", {}).get("data", [])
        if clist:
            charge_id = clist[0].get("id")

    card_info = pm.get("card", {})

    # ── Payment succeeded — now award the bid atomically ──────
    winning_bid.is_winner           = True
    s.status                        = "assigned"
    s.assigned_driver_id            = winning_bid.driver_id
    s.winning_bid_amount            = winning_bid.amount

    # Update payment record — status = escrow_held (platform holds funds)
    payment.status           = "escrow_held"
    payment.stripe_pi_id     = intent["id"]
    payment.stripe_pm_id     = pm["id"]
    payment.stripe_charge_id = charge_id
    payment.card_last4       = card_info.get("last4")
    payment.card_brand       = card_info.get("brand")
    payment.paid_at          = datetime.datetime.utcnow()

    db.commit()

    driver = db.query(User).filter(User.id == winning_bid.driver_id).first()
    return {
        "message":      "Payment successful. Shipment awarded to driver.",
        "awarded_to":   driver.name if driver else "Unknown",
        "winning_amount": winning_bid.amount,
        "payment_id":   payment.id,
        "card_brand":   payment.card_brand,
        "card_last4":   payment.card_last4,
        "charge_id":    charge_id,
        "escrow_status": "held"
    }


# ─────────────────────────────────────────────────────────────
# 2. Release escrow to driver after delivery
# POST /api/payments/{shipment_id}/release
# Called automatically when shipment is delivered
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/release")
def release_payment(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Mark escrow as released to driver after delivery confirmation."""
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")
    if s.status != "delivered":
        raise HTTPException(400, "Shipment must be delivered before releasing payment")

    payment = db.query(Payment).filter(
        Payment.shipment_id == shipment_id,
        Payment.status == "escrow_held"
    ).first()
    if not payment:
        return {"message": "No escrow payment to release"}

    payment.status = "released_to_driver"
    db.commit()

    return {
        "message":  "Payment released to driver",
        "amount":   payment.amount,
        "driver_id": payment.driver_id
    }


# ─────────────────────────────────────────────────────────────
# 3. Get payment status
# GET /api/payments/{shipment_id}/status
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/adjustment-request")
def request_freight_adjustment(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    user = get_current_user(authorization)
    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can request freight adjustments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")
    if s.status not in ("assigned", "in_transit"):
        raise HTTPException(400, "Freight can be adjusted only before delivery")
    if not s.winning_bid_amount:
        raise HTTPException(400, "No original bid amount found")

    original = float(s.winning_bid_amount)
    if data.get("extra_amount") is not None:
        try:
            extra_amount = round(float(data.get("extra_amount")), 2)
        except Exception:
            raise HTTPException(400, "Valid extra amount is required")
        if extra_amount <= 0:
            raise HTTPException(400, "Extra amount must be greater than zero")
        adjusted_amount = round(original + extra_amount, 2)
    else:
        try:
            adjusted_amount = round(float(data.get("amount")), 2)
        except Exception:
            raise HTTPException(400, "Valid adjusted amount is required")
        if adjusted_amount <= 0:
            raise HTTPException(400, "Adjusted amount must be greater than zero")

    delta = round(adjusted_amount - original, 2)
    if delta == 0:
        raise HTTPException(400, "Adjusted amount is the same as the current freight")

    note = (data.get("note") or "").strip()[:500]
    now = datetime.datetime.utcnow()
    s.freight_adjusted_amount = adjusted_amount
    s.freight_adjustment_delta = delta
    s.freight_adjustment_status = "pending"
    s.freight_adjustment_note = note
    s.freight_adjustment_pi_id = None
    s.freight_adjustment_requested_at = now
    s.freight_adjustment_accepted_at = None
    s.freight_adjustment_paid_at = None

    db.add(Message(
        shipment_id=shipment_id,
        driver_id=user["sub"],
        sender_id=user["sub"],
        sender_role="driver",
        body=f"Freight adjustment requested: final freight ₹{adjusted_amount:,.0f} ({'+' if delta > 0 else ''}₹{delta:,.0f}). {note}".strip(),
        created_at=now
    ))
    db.commit()

    driver = db.query(User).filter(User.id == user["sub"]).first()
    return {
        "message": "Freight adjustment sent to shipper",
        "original_amount": original,
        **_adjustment_payload(s),
        "driver_name": driver.name if driver else None,
    }


@router.post("/{shipment_id}/adjustment-accept")
def accept_freight_adjustment(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can accept freight adjustments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    _expire_overdue_adjustment(s, db)
    if (s.freight_adjustment_status or "none") != "pending":
        raise HTTPException(400, "No pending freight adjustment")

    delta = float(s.freight_adjustment_delta or 0)
    adjusted_amount = float(s.freight_adjusted_amount or 0)
    if delta > 0:
        raise HTTPException(400, "Extra freight must be paid before it is accepted")
    if adjusted_amount <= 0:
        raise HTTPException(400, "Invalid adjusted amount")

    payment = _active_escrow_payment(db, shipment_id)
    if payment:
        payment.shipper_refund = abs(delta)
        payment.amount = adjusted_amount

    s.winning_bid_amount = adjusted_amount
    s.freight_adjustment_status = "accepted"
    s.freight_adjustment_accepted_at = datetime.datetime.utcnow()
    db.commit()

    return {
        "message": "Lower freight accepted. Driver will receive adjusted amount after delivery.",
        **_adjustment_payload(s),
    }


@router.post("/{shipment_id}/adjustment-reject")
def reject_freight_adjustment(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can reject freight adjustments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    _expire_overdue_adjustment(s, db)
    if (s.freight_adjustment_status or "none") != "pending":
        raise HTTPException(400, "No pending freight adjustment")

    s.freight_adjustment_status = "rejected"
    s.freight_adjustment_accepted_at = datetime.datetime.utcnow()
    db.commit()
    return {"message": "Freight adjustment rejected", **_adjustment_payload(s)}


@router.post("/{shipment_id}/adjustment-intent")
def create_adjustment_intent(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can pay freight adjustments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    _expire_overdue_adjustment(s, db)
    if (s.freight_adjustment_status or "none") != "pending":
        raise HTTPException(400, "No pending freight adjustment")

    delta = float(s.freight_adjustment_delta or 0)
    if delta <= 0:
        raise HTTPException(400, "This adjustment does not require extra payment")

    intent = _stripe_post("/v1/payment_intents", {
        "amount": max(50, int(delta * 100)),
        "currency": "inr",
        "payment_method_types[]": "card",
        "metadata[shipment_id]": shipment_id,
        "metadata[type]": "freight_adjustment",
    })
    s.freight_adjustment_pi_id = intent["id"]
    db.commit()

    return {
        "payment_intent_id": intent["id"],
        "amount": delta,
        "adjusted_total": s.freight_adjusted_amount,
        "currency": "inr",
    }


@router.post("/{shipment_id}/adjustment-pay")
def pay_freight_adjustment(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can pay freight adjustments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    _expire_overdue_adjustment(s, db)
    if (s.freight_adjustment_status or "none") != "pending":
        raise HTTPException(400, "No pending freight adjustment")

    delta = float(s.freight_adjustment_delta or 0)
    adjusted_amount = float(s.freight_adjusted_amount or 0)
    if delta <= 0:
        raise HTTPException(400, "This adjustment does not require extra payment")

    pi_id = data.get("payment_intent_id", "").strip()
    if not pi_id or pi_id != s.freight_adjustment_pi_id:
        raise HTTPException(400, "Payment intent does not match this adjustment")

    card_number = str(data.get("card_number", "")).replace(" ", "")
    exp_month = data.get("exp_month")
    exp_year = data.get("exp_year")
    cvc = str(data.get("cvc", "")).strip()
    if not all([card_number, exp_month, exp_year, cvc]):
        raise HTTPException(400, "Card details are required")

    pm = _stripe_post("/v1/payment_methods", {
        "type": "card",
        "card[number]": card_number,
        "card[exp_month]": str(int(exp_month)),
        "card[exp_year]": str(int(exp_year)),
        "card[cvc]": cvc,
    })
    intent = _stripe_post("/v1/payment_intents", {
        "amount": max(50, int(delta * 100)),
        "currency": "inr",
        "payment_method": pm["id"],
        "confirm": "true",
        "metadata[shipment_id]": shipment_id,
        "metadata[type]": "freight_adjustment",
    })
    if intent.get("status") != "succeeded":
        raise HTTPException(402, f"Payment failed. Status: {intent.get('status', 'unknown')}")

    payment = _active_escrow_payment(db, shipment_id)
    if payment:
        payment.amount = adjusted_amount

    now = datetime.datetime.utcnow()
    s.winning_bid_amount = adjusted_amount
    s.freight_adjustment_status = "paid"
    s.freight_adjustment_accepted_at = now
    s.freight_adjustment_paid_at = now
    db.commit()

    return {
        "message": "Extra freight paid and added to escrow",
        "extra_paid": delta,
        "adjusted_total": adjusted_amount,
        **_adjustment_payload(s),
    }


@router.get("/{shipment_id}/status")
def get_payment_status(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    if user["role"] == "shipper" and s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if user["role"] == "driver" and s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")
    _expire_overdue_adjustment(s, db)
    payment = db.query(Payment).filter(
        Payment.shipment_id == shipment_id
    ).order_by(Payment.created_at.desc()).first()

    if not payment:
        return {"status": "not_initiated", "amount": s.winning_bid_amount, **_adjustment_payload(s)}

    shipper = db.query(User).filter(User.id == payment.shipper_id).first()
    driver  = db.query(User).filter(User.id == payment.driver_id).first()

    return {
        "payment_id":    payment.id,
        "status":        payment.status,
        "amount":        payment.amount,
        "currency":      payment.currency,
        "card_brand":    payment.card_brand,
        "card_last4":    payment.card_last4,
        "charge_id":     payment.stripe_charge_id,
        "paid_at":       payment.paid_at.isoformat() if payment.paid_at else None,
        "created_at":    payment.created_at.isoformat(),
        "shipper_name":  shipper.name if shipper else None,
        "shipper_phone": shipper.phone if shipper else None,
        "driver_name":   driver.name if driver else None,
        "escrow_status": payment.status,
        "driver_fee":     payment.driver_fee,
        "shipper_refund": payment.shipper_refund,
        **_adjustment_payload(s),
    }


# ─────────────────────────────────────────────────────────────
# LEGACY: create-intent (kept for backward compat)
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/create-intent")
def create_payment_intent(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can initiate payments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")
    if s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if s.status not in ("delivered",):
        raise HTTPException(400, "Use /award-intent to pay at bid acceptance")
    if not s.winning_bid_amount:
        raise HTTPException(400, "No winning bid amount set")

    existing = db.query(Payment).filter(
        Payment.shipment_id == shipment_id,
        Payment.status.in_(["succeeded", "escrow_held", "released_to_driver"])
    ).first()
    if existing:
        raise HTTPException(400, "This shipment has already been paid")

    amount_paise = max(50, int(s.winning_bid_amount * 100))
    intent = _stripe_post("/v1/payment_intents", {
        "amount":                    amount_paise,
        "currency":                  "inr",
        "payment_method_types[]":    "card",
        "metadata[shipment_id]":     shipment_id,
        "metadata[shipper_id]":      user["sub"],
    })

    db.query(Payment).filter(
        Payment.shipment_id == shipment_id,
        Payment.status == "pending"
    ).delete()

    payment = Payment(
        shipment_id  = shipment_id,
        shipper_id   = user["sub"],
        driver_id    = s.assigned_driver_id,
        amount       = s.winning_bid_amount,
        currency     = "inr",
        stripe_pi_id = intent["id"],
        status       = "pending"
    )
    db.add(payment)
    db.commit()

    return {
        "payment_intent_id": intent["id"],
        "amount":            s.winning_bid_amount,
        "currency":          "inr",
        "status":            intent["status"]
    }


# ─────────────────────────────────────────────────────────────
# LEGACY: /pay (kept for backward compat)
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/pay")
def confirm_payment(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can make payments")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")

    pi_id = data.get("payment_intent_id", "").strip()
    if not pi_id:
        raise HTTPException(400, "payment_intent_id is required")

    card_number = str(data.get("card_number", "")).replace(" ", "")
    exp_month   = data.get("exp_month")
    exp_year    = data.get("exp_year")
    cvc         = str(data.get("cvc", "")).strip()

    if not all([card_number, exp_month, exp_year, cvc]):
        raise HTTPException(400, "card_number, exp_month, exp_year and cvc are required")

    payment = db.query(Payment).filter(
        Payment.shipment_id  == shipment_id,
        Payment.stripe_pi_id == pi_id,
        Payment.status       == "pending"
    ).first()
    if not payment:
        raise HTTPException(404, "Payment record not found or already processed")

    pm = _stripe_post("/v1/payment_methods", {
        "type":              "card",
        "card[number]":      card_number,
        "card[exp_month]":   str(int(exp_month)),
        "card[exp_year]":    str(int(exp_year)),
        "card[cvc]":         cvc,
    })

    amount_paise = max(50, int(payment.amount * 100))
    intent = _stripe_post("/v1/payment_intents", {
        "amount":                 amount_paise,
        "currency":               "inr",
        "payment_method":         pm["id"],
        "confirm":                "true",
        "metadata[shipment_id]":  shipment_id,
    })

    if intent.get("status") != "succeeded":
        payment.status = "failed"
        db.commit()
        raise HTTPException(402, f"Payment not completed. Status: {intent.get('status', 'unknown')}")

    charge_id = None
    latest = intent.get("latest_charge")
    if isinstance(latest, dict):
        charge_id = latest.get("id")
    elif isinstance(latest, str):
        charge_id = latest
    else:
        clist = intent.get("charges", {}).get("data", [])
        if clist:
            charge_id = clist[0].get("id")

    card_info = pm.get("card", {})
    payment.status           = "succeeded"
    payment.stripe_pi_id     = intent["id"]
    payment.stripe_pm_id     = pm["id"]
    payment.stripe_charge_id = charge_id
    payment.card_last4       = card_info.get("last4")
    payment.card_brand       = card_info.get("brand")
    payment.paid_at          = datetime.datetime.utcnow()
    db.commit()

    return {
        "message":    "Payment successful",
        "payment_id": payment.id,
        "amount":     payment.amount,
        "currency":   "inr",
        "card_brand": payment.card_brand,
        "card_last4": payment.card_last4,
        "charge_id":  charge_id,
        "paid_at":    payment.paid_at.isoformat()
    }


