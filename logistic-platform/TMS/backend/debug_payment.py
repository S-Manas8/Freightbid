import sys
sys.path.insert(0, '.')
from database import SessionLocal
from models import Shipment, Payment, User

db = SessionLocal()

print("=== SHIPMENTS (awarded/active/delivered) ===")
shipments = db.query(Shipment).filter(
    Shipment.status.in_(['assigned', 'in_transit', 'delivered'])
).all()
print(f"Found {len(shipments)} shipments")

for s in shipments:
    pay = db.query(Payment).filter(Payment.shipment_id == s.id).first()
    driver = db.query(User).filter(User.id == s.assigned_driver_id).first() if s.assigned_driver_id else None
    print(f"\n  ID:      {s.id}")
    print(f"  Status:  {s.status}")
    print(f"  Amount:  {s.winning_bid_amount}")
    print(f"  Driver:  {driver.name if driver else 'none'} ({s.assigned_driver_id})")
    if pay:
        print(f"  Payment: {pay.status} | amount={pay.amount} | paid_at={pay.paid_at}")
        print(f"           shipper_id={pay.shipper_id} | driver_id={pay.driver_id}")
    else:
        print(f"  Payment: NONE")

print("\n=== ALL PAYMENTS ===")
payments = db.query(Payment).all()
print(f"Found {len(payments)} payment records")
for p in payments:
    print(f"  {p.id[:8]}.. shipment={p.shipment_id[:8]}.. status={p.status} amount={p.amount}")

db.close()
