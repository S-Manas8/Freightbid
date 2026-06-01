import sys, requests as http
sys.path.insert(0, '.')
from database import SessionLocal
from models import Shipment, ShipmentDestination, DestinationChangeRequest, User
from auth_utils import create_token

db = SessionLocal()
s = db.query(Shipment).filter(Shipment.status == 'in_transit').first()
if not s:
    print("No in_transit shipment"); db.close(); exit()

dest = db.query(ShipmentDestination).filter(
    ShipmentDestination.shipment_id == s.id,
    ShipmentDestination.status == 'pending'
).first()

print("Shipment:", s.id[:8], "dest:", dest.id[:8] if dest else "none", dest.address if dest else "")

# Check pending change requests
reqs = db.query(DestinationChangeRequest).filter(
    DestinationChangeRequest.shipment_id == s.id
).all()
print("Change requests:", len(reqs))
for r in reqs:
    print("  req:", r.id[:8], "status:", r.status, "new_addr:", r.new_address, "dest_id:", r.dest_id[:8])

# Test the endpoint directly
shipper = db.query(User).filter(User.id == s.shipper_id).first()
driver  = db.query(User).filter(User.id == s.assigned_driver_id).first()
st = create_token(s.shipper_id, 'shipper')
dt = create_token(s.assigned_driver_id, 'driver')

print("\nTesting POST change-request...")
r = http.post(
    f'http://localhost:8000/api/shipments/{s.id}/destinations/{dest.id}/change-request',
    json={'new_address': 'Delhi, India', 'new_lat': 28.6139, 'new_lng': 77.2090},
    headers={'Authorization': f'Bearer {st}'}
)
print("Status:", r.status_code, r.text[:200])

print("\nTesting GET change-request (driver poll)...")
r2 = http.get(
    f'http://localhost:8000/api/shipments/{s.id}/destinations/{dest.id}/change-request',
    headers={'Authorization': f'Bearer {dt}'}
)
print("Status:", r2.status_code, r2.text[:200])

db.close()
