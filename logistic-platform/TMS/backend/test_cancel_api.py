import sys; sys.path.insert(0,'.')
import requests as http
from database import SessionLocal
from models import User, Shipment, CancellationRecord
from auth_utils import create_token

db = SessionLocal()
driver = db.query(User).filter(User.name == 'varshit').first()
if not driver:
    driver = db.query(User).filter(User.role == 'driver').first()

print("Driver:", driver.name, driver.id[:8])
token = create_token(driver.id, 'driver')

# Find a cancelled shipment for this driver
cancelled = db.query(Shipment).filter(
    Shipment.assigned_driver_id == driver.id,
    Shipment.status == 'cancelled'
).first()

if not cancelled:
    print("No cancelled shipment found for this driver")
    db.close()
    exit()

print("Cancelled shipment:", cancelled.id[:8])

# Check cancellation record
rec = db.query(CancellationRecord).filter(
    CancellationRecord.shipment_id == cancelled.id
).first()
print("CancellationRecord:", rec.id[:8] if rec else "NONE", "driver_fee=" + str(rec.driver_fee if rec else 0))

# Test the API endpoint
r = http.get(
    f'http://localhost:8000/api/shipments/{cancelled.id}/cancellation',
    headers={'Authorization': f'Bearer {token}'}
)
print("API status:", r.status_code)
print("API response:", r.text[:300])

db.close()
