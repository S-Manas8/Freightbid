"""
Proof-of-Delivery (POD) router
Handles:
  - Driver uploading a delivery photo at a stop
  - Shipper requesting an on-demand proof photo
  - Driver fulfilling a proof request
  - Fetching PODs and proof requests for a shipment
"""

import os
import uuid
import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import POD, ProofRequest, Shipment, ShipmentDestination, User, Complaint
from ..auth_utils import get_current_user

router = APIRouter()

# ── Upload directory (served as /uploads/* by main.py) ────────
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE_MB   = 10


def _save_image(file: UploadFile) -> str:
    """Save uploaded image, return its public URL path."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Only JPEG, PNG, WEBP or GIF images are allowed")

    data = file.file.read()
    if len(data) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"Image must be under {MAX_SIZE_MB} MB")

    ext      = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    (UPLOAD_DIR / filename).write_bytes(data)
    return f"/uploads/{filename}"


# ─────────────────────────────────────────────────────────────
# 1. Driver uploads delivery photo for a stop
# POST /api/pod/{shipment_id}/destinations/{dest_id}/upload
# dest_id can be "none" for proof_request re-uploads
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/destinations/{dest_id}/upload")
async def upload_delivery_photo(
    shipment_id: str,
    dest_id: str,
    photo: UploadFile = File(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Driver uploads a delivery proof photo for a specific stop.
    dest_id can be 'none' for general/re-upload photos not tied to a stop."""
    user = get_current_user(authorization)
    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can upload delivery photos")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")

    # dest_id = "none" means a general photo not tied to a specific stop
    actual_dest_id = None
    if dest_id and dest_id != "none":
        dest = db.query(ShipmentDestination).filter(
            ShipmentDestination.id == dest_id,
            ShipmentDestination.shipment_id == shipment_id
        ).first()
        if not dest:
            raise HTTPException(404, "Destination not found")
        actual_dest_id = dest_id

    image_url = _save_image(photo)

    pod = POD(
        shipment_id=shipment_id,
        dest_id=actual_dest_id,
        image_url=image_url,
        notes=notes,
        pod_type="delivery",
        delivered_at=datetime.datetime.utcnow()
    )
    db.add(pod)
    db.commit()
    db.refresh(pod)

    return {
        "message": "Delivery photo uploaded successfully",
        "pod_id": pod.id,
        "image_url": image_url
    }


# ─────────────────────────────────────────────────────────────
# 2. Get all PODs for a shipment (shipper & driver can view)
# GET /api/pod/{shipment_id}/photos
# ─────────────────────────────────────────────────────────────
@router.get("/{shipment_id}/photos")
def get_shipment_photos(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Get all delivery photos for a shipment."""
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    # Only shipper who owns it or assigned driver can view
    if user["role"] == "shipper" and s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if user["role"] == "driver" and s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")

    pods = db.query(POD).filter(POD.shipment_id == shipment_id).order_by(POD.delivered_at).all()

    result = []
    for p in pods:
        dest    = db.query(ShipmentDestination).filter(ShipmentDestination.id == p.dest_id).first() if p.dest_id else None
        shipper = db.query(User).filter(User.id == s.shipper_id).first()
        result.append({
            "pod_id":        p.id,
            "dest_id":       p.dest_id,
            "dest_address":  dest.address if dest else None,
            "image_url":     p.image_url,
            "notes":         p.notes,
            "pod_type":      p.pod_type,
            "uploaded_at":   p.delivered_at.isoformat(),
            "shipper_name":  shipper.name if shipper else "Unknown",
            "shipper_phone": shipper.phone if shipper else None,
            "ack_status":    p.ack_status or "pending",
            "ack_notes":     p.ack_notes or "",
        })

    return result


# ─────────────────────────────────────────────────────────────
# 3. Shipper raises a proof request
# POST /api/pod/{shipment_id}/proof-request
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/proof-request")
def create_proof_request(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Shipper requests driver to send a photo of goods right now."""
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can request proof photos")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")
    if s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if s.status != "in_transit":
        raise HTTPException(400, "Can only request proof while shipment is in transit")

    # Check if there's already a pending request
    existing = db.query(ProofRequest).filter(
        ProofRequest.shipment_id == shipment_id,
        ProofRequest.status == "pending"
    ).first()
    if existing:
        raise HTTPException(400, "A proof request is already pending — wait for the driver to respond")

    req = ProofRequest(
        shipment_id=shipment_id,
        shipper_id=user["sub"],
        status="pending"
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    return {
        "message": "Proof request sent to driver",
        "request_id": req.id
    }


# ─────────────────────────────────────────────────────────────
# 4. Driver fulfills a proof request by uploading a photo
# POST /api/pod/{shipment_id}/proof-request/{request_id}/fulfill
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/proof-request/{request_id}/fulfill")
async def fulfill_proof_request(
    shipment_id: str,
    request_id: str,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Driver uploads a photo to fulfill the shipper's proof request."""
    user = get_current_user(authorization)
    if user["role"] != "driver":
        raise HTTPException(403, "Only drivers can fulfill proof requests")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s or s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")

    req = db.query(ProofRequest).filter(
        ProofRequest.id == request_id,
        ProofRequest.shipment_id == shipment_id,
        ProofRequest.status == "pending"
    ).first()
    if not req:
        raise HTTPException(404, "Proof request not found or already fulfilled")

    image_url = _save_image(photo)

    req.status       = "fulfilled"
    req.image_url    = image_url
    req.fulfilled_at = datetime.datetime.utcnow()

    # Also store as a POD record for history
    pod = POD(
        shipment_id=shipment_id,
        dest_id=None,
        image_url=image_url,
        notes="Proof requested by shipper",
        pod_type="proof_request",
        delivered_at=datetime.datetime.utcnow()
    )
    db.add(pod)
    db.commit()

    return {
        "message": "Proof photo uploaded successfully",
        "image_url": image_url
    }


# ─────────────────────────────────────────────────────────────
# 5. Get proof requests for a shipment
# GET /api/pod/{shipment_id}/proof-requests
# ─────────────────────────────────────────────────────────────
@router.get("/{shipment_id}/proof-requests")
def get_proof_requests(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Get all proof requests for a shipment (shipper & driver)."""
    user = get_current_user(authorization) 

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    if user["role"] == "shipper" and s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if user["role"] == "driver" and s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")

    requests = db.query(ProofRequest).filter(
        ProofRequest.shipment_id == shipment_id
    ).order_by(ProofRequest.created_at.desc()).all()

    return [
        {
            "request_id":   r.id,
            "status":       r.status,
            "image_url":    r.image_url,
            "created_at":   r.created_at.isoformat(),
            "fulfilled_at": r.fulfilled_at.isoformat() if r.fulfilled_at else None
        }
        for r in requests
    ]


# ─────────────────────────────────────────────────────────────
# 6. Shipper acknowledges a POD photo (approve / reject)
# POST /api/pod/{shipment_id}/photos/{pod_id}/acknowledge
# Body: { action: "approved" | "rejected", notes: "..." }
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/photos/{pod_id}/acknowledge")
def acknowledge_pod(
    shipment_id: str,
    pod_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Shipper approves or rejects a delivery/proof photo."""
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can acknowledge photos")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")
    if s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")

    pod = db.query(POD).filter(
        POD.id == pod_id,
        POD.shipment_id == shipment_id
    ).first()
    if not pod:
        raise HTTPException(404, "Photo not found")

    action = data.get("action")
    if action not in ("approved", "rejected"):
        raise HTTPException(400, "action must be 'approved' or 'rejected'")

    pod.ack_status = action
    pod.ack_notes  = data.get("notes", "")
    pod.ack_at     = datetime.datetime.utcnow()
    db.commit()

    return {"message": f"Photo {action} successfully"}


# ─────────────────────────────────────────────────────────────
# 7. Raise a complaint against a driver
# POST /api/pod/{shipment_id}/complaint
# Body: { reason, description }
# ─────────────────────────────────────────────────────────────
@router.post("/{shipment_id}/complaint")
def raise_complaint(
    shipment_id: str,
    data: dict,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Shipper raises a formal complaint against the driver."""
    user = get_current_user(authorization)
    if user["role"] != "shipper":
        raise HTTPException(403, "Only shippers can raise complaints")

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")
    if s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if not s.assigned_driver_id:
        raise HTTPException(400, "No driver assigned to this shipment")

    reason = data.get("reason", "").strip()
    if not reason:
        raise HTTPException(400, "Reason is required")

    complaint = Complaint(
        shipment_id=shipment_id,
        shipper_id=user["sub"],
        driver_id=s.assigned_driver_id,
        reason=reason,
        description=data.get("description", "").strip(),
        status="open"
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    return {
        "message": "Complaint raised successfully",
        "complaint_id": complaint.id
    }


# ─────────────────────────────────────────────────────────────
# 8. Get complaints for a shipment
# GET /api/pod/{shipment_id}/complaints
# ─────────────────────────────────────────────────────────────
@router.get("/{shipment_id}/complaints")
def get_complaints(
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

    complaints = db.query(Complaint).filter(
        Complaint.shipment_id == shipment_id
    ).order_by(Complaint.created_at.desc()).all()

    return [
        {
            "complaint_id": c.id,
            "reason":       c.reason,
            "description":  c.description,
            "status":       c.status,
            "created_at":   c.created_at.isoformat()
        }
        for c in complaints
    ]
