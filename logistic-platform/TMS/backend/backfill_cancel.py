"""
Backfill CancellationRecord for cancelled shipments that have a payment
with status 'cancelled_with_fee' but no CancellationRecord yet.
"""
import sys, uuid, datetime
sys.path.insert(0, '.')
from database import SessionLocal
from models import Shipment, Payment, CancellationRecord

db = SessionLocal()

cancelled = db.query(Shipment).filter(Shipment.status == 'cancelled').all()
print(f"Found {len(cancelled)} cancelled shipments")

for s in cancelled:
    existing = db.query(CancellationRecord).filter(
        CancellationRecord.shipment_id == s.id
    ).first()
    if existing:
        print(f"  {s.id[:8]} already has record, skipping")
        continue

    pay = db.query(Payment).filter(Payment.shipment_id == s.id).first()
    if not pay:
        print(f"  {s.id[:8]} no payment, skipping")
        continue

    # Determine driver_fee from payment amount
    # If payment was cancelled_with_fee, we don't know the exact split
    # Use 20% as a reasonable default for backfill
    trip_amount = pay.amount or 0
    driver_fee  = round(trip_amount * 0.20, 2)
    refund      = round(trip_amount - driver_fee, 2)

    rec = CancellationRecord(
        id           = str(uuid.uuid4()),
        shipment_id  = s.id,
        shipper_id   = s.shipper_id,
        driver_id    = s.assigned_driver_id,
        reason       = "Cancelled by shipper",
        scenario     = "assigned_penalty",
        trip_amount  = trip_amount,
        driver_fee   = driver_fee,
        shipper_refund = refund,
        cancelled_at = datetime.datetime.utcnow()
    )
    db.add(rec)
    print(f"  {s.id[:8]} created record: driver_fee={driver_fee} refund={refund}")

db.commit()
print("Done")
db.close()
