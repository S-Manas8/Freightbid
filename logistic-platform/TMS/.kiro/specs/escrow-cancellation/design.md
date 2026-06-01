# FreightBid — Escrow & Cancellation: Design

## Architecture Overview

```
Shipper awards bid
       ↓
Escrow locked (shipper.wallet_balance -= amount, shipper.escrow_balance += amount)
       ↓
Driver sees "Payment Secured — ₹X"
       ↓
Either: Delivery confirmed → escrow released to driver.wallet_balance
    Or: Cancellation → fee split per scenario, remainder refunded to shipper
```

---

## New Database Models

### 1. User (additions via ALTER TABLE migration)
```python
wallet_balance    Float  default=0.0   # simulated INR balance
escrow_balance    Float  default=0.0   # funds currently locked
cancellation_count Integer default=0
is_flagged        Boolean default=False
is_suspended      Boolean default=False
suspended_until   DateTime nullable
bid_penalty_until DateTime nullable
```

### 2. EscrowTransaction (new table)
```python
id              TEXT PK
shipment_id     TEXT FK shipments.id
shipper_id      TEXT FK users.id
driver_id       TEXT FK users.id
amount          Float          # total held
status          TEXT           # held / released / refunded / split
fee_to_driver   Float default=0
refund_to_shipper Float default=0
created_at      DateTime
released_at     DateTime nullable
```

### 3. CancellationLog (new table)
```python
id              TEXT PK
shipment_id     TEXT FK shipments.id
cancelled_by    TEXT           # "shipper" or "driver"
stage           TEXT           # no_bids / bids_placed / assigned_grace /
                               # assigned / after_arrival / mid_trip
reason          TEXT           # mandatory
driver_lat      Float nullable
driver_lng      Float nullable
escrow_held     Float
fee_to_driver   Float default=0
refund_to_shipper Float
cancelled_at    DateTime
```

### 4. Shipment (additions)
```python
assigned_at     DateTime nullable   # timestamp when bid was awarded (for grace period)
cancellation_stage TEXT nullable    # which scenario applied
```

---

## New / Modified API Endpoints

### Wallet
| Method | Path | Who | Description |
|--------|------|-----|-------------|
| POST | `/api/wallet/topup` | shipper | Add simulated balance |
| GET | `/api/wallet/balance` | any | Get wallet + escrow balance |

### Escrow (internal, called by award/cancel/deliver)
No direct frontend calls — escrow operations are side effects of existing endpoints.

### Cancellation
| Method | Path | Who | Description |
|--------|------|-----|-------------|
| POST | `/api/shipments/{id}/cancel` | shipper | Cancel with scenario detection |
| POST | `/api/shipments/{id}/driver-cancel` | driver | Driver cancels assigned trip |
| GET | `/api/shipments/{id}/cancel-preview` | shipper | Preview fee breakdown before confirming |

### Modified: Award endpoint
`POST /api/shipments/{id}/award` — now also:
- Checks `shipper.wallet_balance >= winning_bid_amount`
- Locks escrow
- Sets `shipment.assigned_at = now()`

### Modified: Delivery endpoint
When all destinations delivered (status → `delivered`):
- Calls `_release_escrow(shipment_id)` to pay driver

---

## Cancellation Logic (backend)

```python
def detect_cancellation_stage(shipment, db) -> str:
    bid_count = db.query(Bid).filter(Bid.shipment_id == shipment.id).count()
    
    if shipment.status == "open":
        if bid_count == 0:
            return "no_bids"
        else:
            return "bids_placed"
    
    if shipment.status == "assigned":
        # Check grace period (5 minutes)
        grace_cutoff = shipment.assigned_at + timedelta(minutes=5)
        if datetime.utcnow() <= grace_cutoff:
            return "assigned_grace"
        
        # Check if driver has arrived
        dests = db.query(ShipmentDestination).filter(...)
        driver_arrived = any(d.ack_status in ("pending_approval","approved") for d in dests)
        if driver_arrived:
            return "after_arrival"
        return "assigned"
    
    if shipment.status == "in_transit":
        return "mid_trip"
    
    raise HTTPException(400, "Cannot cancel at this stage")


def calculate_cancellation_split(stage, shipment, db) -> dict:
    amount = shipment.winning_bid_amount or 0
    
    if stage in ("no_bids", "bids_placed", "assigned_grace"):
        return {"fee_to_driver": 0, "refund_to_shipper": amount}
    
    if stage == "assigned":
        return {"fee_to_driver": 200, "refund_to_shipper": max(0, amount - 200)}
    
    if stage == "after_arrival":
        fee = round(amount * 0.20, 2)
        return {"fee_to_driver": fee, "refund_to_shipper": round(amount - fee, 2)}
    
    if stage == "mid_trip":
        dests = db.query(ShipmentDestination).filter(...)
        total = len(dests)
        completed = sum(1 for d in dests if d.status == "delivered")
        proportional = round((completed / total) * amount, 2) if total > 0 else 0
        # Return allowance: last completed stop → pickup, ₹10/km
        return_km = haversine_distance(last_stop.lat, last_stop.lng, shipment.pickup_lat, shipment.pickup_lng)
        return_allowance = round(return_km * 10, 2)
        driver_total = proportional + return_allowance
        refund = max(0, round(amount - driver_total, 2))
        return {"fee_to_driver": driver_total, "refund_to_shipper": refund}
```

---

## Frontend Changes

### Shipper Dashboard
1. **Stats bar** — add wallet chip: `💰 ₹X available · 🔒 ₹Y in escrow`
2. **Shipment cards** — add Cancel button for `open` and `assigned` statuses
3. **Cancel modal** — shows:
   - Stage detected (e.g. "Driver has arrived — 20% fee applies")
   - Fee breakdown: "₹X → Driver · ₹Y → Your wallet"
   - Reason dropdown (mandatory)
   - Confirm button
4. **Award flow** — if wallet insufficient, show "Top up wallet to award this bid"

### Driver Dashboard
1. **Trip cards** — add "Payment Secured — ₹X held by FreightBid" badge for `assigned`/`in_transit`
2. **Cancel Trip button** — on `assigned` trips, with penalty warning modal
3. **Suspension banner** — shown at top of page if suspended
4. **My Rating tab** — add cancellation rate stat

### Load Cards (driver view)
- Show shipper cancellation rate: `⚠️ 2 cancellations this month` if flagged

---

## Migration Plan

All new columns added via `ALTER TABLE` in `main.py` startup block (existing pattern). New tables created via `CREATE TABLE IF NOT EXISTS`. No data loss.

---

## File Changes Summary

| File | Change |
|------|--------|
| `backend/models.py` | Add fields to User, Shipment; add EscrowTransaction, CancellationLog |
| `backend/main.py` | Add migrations for new columns/tables |
| `backend/routers/shipments.py` | Modify award (escrow lock), modify cancel (scenario detection), add driver-cancel, add cancel-preview |
| `backend/routers/payments.py` | Modify delivery release to use escrow |
| `backend/routers/wallet.py` | New file: topup + balance endpoints |
| `frontend/js/api.js` | Add cancelShipment, driverCancelShipment, getCancelPreview, topupWallet, getWalletBalance |
| `frontend/pages/shipper.html` | Wallet chip, cancel button, cancel modal |
| `frontend/js/driver.js` | Escrow badge, cancel trip button, suspension banner |
