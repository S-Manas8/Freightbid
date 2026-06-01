# FreightBid — Escrow Wallet & Cancellation Policy
## Requirements

### Current State (what exists)
- Payment flows **directly** from shipper to platform via localstripe, only after delivery
- No escrow, no wallet, no driver payout mechanism
- Cancel only works on `open` shipments (no bids accepted yet)
- No penalty tracking on users or bids
- `User` model has no `wallet_balance`, `cancellation_count`, or `is_suspended`

### What We Are Building
Redesign the payment architecture so:
1. **Shipper pays FreightBid (escrow) at bid acceptance**, not at delivery
2. **FreightBid releases funds to driver** after delivery confirmation
3. **Cancellation at any stage** is handled with the correct fee/refund split
4. **Driver and shipper profiles** track trust signals (cancellation rate, suspension)

---

## REQ-1: Escrow Wallet

### REQ-1.1 — Wallet model on every user
Every `User` (shipper and driver) must have:
- `wallet_balance` (Float, default 0.0) — simulated INR balance
- `escrow_balance` (Float, default 0.0) — funds currently locked in escrow (shipper only meaningful)

### REQ-1.2 — Escrow lock at bid acceptance
When a shipper awards a bid (`POST /api/shipments/{id}/award`):
- The full `winning_bid_amount` is immediately deducted from `shipper.wallet_balance`
- The same amount is added to `shipper.escrow_balance`
- A new `EscrowTransaction` record is created with `status = "held"`
- If shipper has insufficient wallet balance, the award is blocked with a clear error

### REQ-1.3 — Escrow release at delivery
When all destinations are marked delivered (shipment status → `delivered`):
- The escrow amount is released to the driver's `wallet_balance`
- `shipper.escrow_balance` is reduced by the same amount
- The `EscrowTransaction` is updated to `status = "released"`
- Driver sees "Payment Secured — ₹X held by FreightBid" while in transit

### REQ-1.4 — Wallet top-up (simulation)
A simple endpoint `POST /api/wallet/topup` allows shippers to add simulated balance (for testing). No real payment needed — just increment `wallet_balance`.

### REQ-1.5 — Wallet balance visible in UI
- Shipper dashboard shows current wallet balance and escrow balance
- Driver dashboard shows wallet balance (earnings received)

---

## REQ-2: Shipper Cancellation Scenarios

### REQ-2.1 — Scenario 1: Cancel before any bids
**Condition:** `shipment.status == "open"` AND `bid_count == 0`
**Behavior:**
- Shipment marked `cancelled`
- No escrow was held (award never happened), so no refund needed
- No fee, no notification (no drivers involved)
- Zero-consequence cancellation

### REQ-2.2 — Scenario 2: Cancel after bids but before award
**Condition:** `shipment.status == "open"` AND `bid_count > 0`
**Behavior:**
- Shipment marked `cancelled`
- No escrow was held, so no refund needed
- All bidding drivers see the shipment as `cancelled` in their bid history
- Shipper's `cancellation_count` incremented
- If `cancellation_count > 3` in the current calendar month, shipper's `is_flagged = True`
- Flagged shippers show a cancellation rate badge visible to drivers on bid listings

### REQ-2.3 — Scenario 3: Cancel after award, driver not yet at pickup
**Condition:** `shipment.status == "assigned"` (driver travelling, not arrived)
**Sub-condition A — Grace period:** Cancelled within 5 minutes of `assigned_at` timestamp
- Treat as Scenario 2: full escrow refund to shipper wallet, no driver compensation
**Sub-condition B — After grace period:**
- Driver compensation = flat ₹200 (fixed for simulation; real formula uses GPS distance)
- Escrow split: ₹200 → driver wallet, remainder → shipper wallet
- `EscrowTransaction` updated with `fee_to_driver` and `refund_to_shipper` fields
- Shipment marked `cancelled`
- Shipper's `cancellation_count` incremented

### REQ-2.4 — Scenario 4: Cancel after driver arrived at pickup
**Condition:** `shipment.status == "assigned"` AND at least one destination has `ack_status == "pending_approval"` or `"approved"` (driver has sent arrival signal)
**Behavior:**
- Cancellation fee = 20% of `winning_bid_amount`
- Fee → driver wallet immediately
- Remaining 80% → shipper wallet
- Shipment marked `cancelled`
- Shipper's `cancellation_count` incremented
- A `CancellationLog` record is created with `stage = "after_arrival"` — this is shown prominently on the shipper's public profile

### REQ-2.5 — Scenario 5: Cancel mid-trip (goods loaded, stops in progress)
**Condition:** `shipment.status == "in_transit"` AND at least one destination `status == "delivered"`
**Behavior:**
- Proportional pay = `(completed_stops / total_stops) * winning_bid_amount`
- Return allowance = ₹10/km for estimated return distance (use haversine from last completed stop to pickup)
- Driver receives: proportional pay + return allowance
- Shipper receives: remainder from escrow
- Shipment marked `cancelled`
- All undelivered destinations remain as a record (not re-opened — shipper must post a new load)
- A `CancellationLog` record is created with `stage = "mid_trip"`

---

## REQ-3: Driver Cancellation

### REQ-3.1 — Driver cancels after award (before starting)
**Condition:** `shipment.status == "assigned"`, driver has not started trip
**Behavior:**
- Full escrow refunded to shipper wallet
- Driver receives nothing
- Driver's `cancellation_count` incremented
- Driver's `bid_penalty_until` set to 7 days from now (bids ranked lower during this period)
- Shipment re-opened for bidding (status → `open`, `assigned_driver_id` cleared)
- Next-lowest bid is shown to shipper for quick re-award

### REQ-3.2 — Driver cancels after arriving at pickup
**Condition:** `shipment.status == "assigned"` AND driver has sent arrival signal
**Behavior:**
- Same as REQ-3.1 PLUS:
- Driver's `is_suspended` set to `True`, `suspended_until` = 48 hours from now
- Suspended drivers cannot place new bids

---

## REQ-4: Cancellation Logging

Every cancellation (shipper or driver) must create a `CancellationLog` record with:
- `shipment_id`
- `cancelled_by` — "shipper" or "driver"
- `stage` — "no_bids" / "bids_placed" / "assigned_grace" / "assigned" / "after_arrival" / "mid_trip"
- `reason` — mandatory dropdown selection from frontend
- `driver_lat`, `driver_lng` — last known GPS at cancellation time
- `escrow_held` — total amount that was in escrow
- `fee_to_driver` — compensation paid to driver (0 if none)
- `refund_to_shipper` — amount returned to shipper
- `cancelled_at` — timestamp

---

## REQ-5: Trust & Reputation Signals

### REQ-5.1 — Shipper profile
- `cancellation_count` (Integer, default 0) on User
- `is_flagged` (Boolean, default False) — auto-set when monthly cancellations > 3
- Cancellation rate shown on shipper's public profile (visible to drivers before bidding)
- `CancellationLog` entries with `stage = "after_arrival"` shown as a separate "serious cancellations" count

### REQ-5.2 — Driver profile
- `cancellation_count` (Integer, default 0) on User
- `is_suspended` (Boolean, default False)
- `suspended_until` (DateTime, nullable)
- `bid_penalty_until` (DateTime, nullable) — bids placed during this window are ranked lower
- Cancellation rate shown publicly on driver profile

---

## REQ-6: UI Changes

### REQ-6.1 — Shipper dashboard
- Wallet balance chip in the stats bar (balance + escrow locked)
- "Cancel Shipment" button on shipment cards (visible for `open` and `assigned` statuses)
- Cancel modal with mandatory reason dropdown and clear fee breakdown before confirming
- After cancellation: show "₹X sent to driver · ₹Y refunded to your wallet"

### REQ-6.2 — Driver dashboard
- "Payment Secured — ₹X held by FreightBid" badge on assigned/in-transit trips
- "Cancel Trip" button on assigned trips (with penalty warning)
- Suspension banner if `is_suspended == True`
- Cancellation rate shown on My Rating tab

### REQ-6.3 — Bid listings (driver view)
- Shipper cancellation rate shown on each load card
- Flagged shippers shown with a ⚠️ badge

---

## Out of Scope (for this spec)
- Real UPI/bank integration (wallet top-up is simulated)
- Push notifications / SMS (logged as in-app only)
- Admin dispute resolution UI
- Auto-release after 24 hours (can be a future background job)
