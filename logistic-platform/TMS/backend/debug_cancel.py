import sys; sys.path.insert(0,'.')
from database import SessionLocal
from models import CancellationRecord, Shipment, User

db = SessionLocal()

print("=== CANCELLATION RECORDS ===")
recs = db.query(CancellationRecord).all()
if not recs:
    print("NONE FOUND")
for r in recs:
    s = db.query(Shipment).filter(Shipment.id == r.shipment_id).first()
    driver = db.query(User).filter(User.id == r.driver_id).first() if r.driver_id else None
    print("id=" + r.id[:8] + " scenario=" + r.scenario + " driver_fee=" + str(r.driver_fee) + " refund=" + str(r.shipper_refund))
    print("  shipment_status=" + (s.status if s else "?") + " driver=" + (driver.name if driver else "none"))

print("\n=== CANCELLED SHIPMENTS ===")
cancelled = db.query(Shipment).filter(Shipment.status == "cancelled").all()
print("Found " + str(len(cancelled)) + " cancelled shipments")
for s in cancelled:
    print("  " + s.id[:8] + " assigned_driver=" + str(s.assigned_driver_id)[:8] if s.assigned_driver_id else "  " + s.id[:8] + " no driver")

db.close()
