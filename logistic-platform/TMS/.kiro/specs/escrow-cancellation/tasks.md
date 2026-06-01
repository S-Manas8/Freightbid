# FreightBid — Escrow & Cancellation: Tasks

## Task 1: Database — New Models & Migrations
- [ ] Add `wallet_balance`, `escrow_balance`, `cancellation_count`, `is_flagged`, `is_suspended`, `suspended_until`, `bid_penalty_until` to `User` model in `models.py`
- [ ] Add `assigned_at`, `cancellation_stage` to `Shipment` model in `models.py`
- [ ] Add `EscrowTransaction` model to `models.py`
- [ ] Add `CancellationLog` model to `models.py`
- [ ] Add all `ALTER TABLE` migrations to `main.py` startup block
- [ ] Add `CREATE TABLE IF NOT EXISTS` for `escrow_transactions` and `cancellation_logs` in `main.py`

## Task 2: Wallet Router
- [ ] Create `backend/routers/wallet.py`
- [ ] Implement `POST /api/wallet/topup` — adds simulated balance to `user.wallet_balance`
- [ ] Implement `GET /api/wallet/balance` — returns `wallet_balance` and `escrow_balance`
- [ ] Register wallet router in `main.py`

## Task 3: Escrow Lock at Award
- [ ] Modify `award_shipment` in `bids.py` to check `shipper.wallet_balance >= winning_bid_amount`
- [ ] On award: deduct from `shipper.wallet_balance`, add to `shipper.escrow_balance`
- [ ] Create `EscrowTransaction` record with `status = "held"`
- [ ] Set `shipment.assigned_at = datetime.utcnow()`
- [ ] Return clear error if wallet balance insufficient

## Task 4: Escrow Release at Delivery
- [ ] Add `_release_escrow(shipment_id, db)` helper function in `shipments.py`
- [ ] Call `_release_escrow` when all destinations are delivered (inside `update_destination_status`)
- [ ] Release: add `winning_bid_amount` to `driver.wallet_balance`, reduce `shipper.escrow_balance`
- [ ] Update `EscrowTransaction.status = "released"`, set `released_at`

## Task 5: Shipper Cancellation Endpoint
- [ ] Add `detect_cancellation_stage(shipment, db)` helper in `shipments.py`
- [ ] Add `calculate_cancellation_split(stage, shipment, db)` helper in `shipments.py`
- [ ] Implement `GET /api/shipments/{id}/cancel-preview` — returns stage + fee breakdown (no side effects)
- [ ] Rewrite `POST /api/shipments/{id}/cancel` to handle all 5 scenarios:
  - Scenario 1 (no_bids): mark cancelled, no escrow action
  - Scenario 2 (bids_placed): mark cancelled, increment shipper `cancellation_count`, flag if > 3/month
  - Scenario 3a (assigned_grace): full escrow refund to shipper
  - Scenario 3b (assigned): ₹200 to driver, remainder to shipper
  - Scenario 4 (after_arrival): 20% to driver, 80% to shipper
  - Scenario 5 (mid_trip): proportional + return allowance to driver, remainder to shipper
- [ ] Create `CancellationLog` record for every cancellation
- [ ] Update `EscrowTransaction.status = "split"` or `"refunded"` as appropriate

## Task 6: Driver Cancellation Endpoint
- [ ] Implement `POST /api/shipments/{id}/driver-cancel` in `shipments.py`
- [ ] Full escrow refund to shipper wallet
- [ ] Increment driver `cancellation_count`
- [ ] Set `driver.bid_penalty_until = now() + 7 days`
- [ ] If driver had arrived (ack_status check): set `driver.is_suspended = True`, `suspended_until = now() + 48h`
- [ ] Re-open shipment: `status = "open"`, clear `assigned_driver_id`, clear `assigned_at`
- [ ] Create `CancellationLog` record

## Task 7: Suspension Check on Bid Placement
- [ ] In `place_bid` (bids.py): check `driver.is_suspended` and `driver.suspended_until`
- [ ] If suspended and `suspended_until > now()`: reject bid with "You are suspended until {date}"
- [ ] If `suspended_until <= now()`: auto-clear `is_suspended = False`

## Task 8: Frontend — api.js
- [ ] Add `cancelShipment(shipmentId, reason)` — POST `/api/shipments/{id}/cancel`
- [ ] Add `driverCancelShipment(shipmentId, reason)` — POST `/api/shipments/{id}/driver-cancel`
- [ ] Add `getCancelPreview(shipmentId)` — GET `/api/shipments/{id}/cancel-preview`
- [ ] Add `topupWallet(amount)` — POST `/api/wallet/topup`
- [ ] Add `getWalletBalance()` — GET `/api/wallet/balance`

## Task 9: Frontend — Shipper Dashboard
- [ ] Add wallet balance chip to stats bar: `💰 ₹X available · 🔒 ₹Y in escrow`
- [ ] Add "Cancel" button on shipment cards for `open` and `assigned` statuses
- [ ] Build cancel preview modal: calls `getCancelPreview`, shows stage + fee breakdown
- [ ] Add reason dropdown (mandatory) to cancel modal
- [ ] On confirm: call `cancelShipment`, show result toast with "₹X → Driver · ₹Y refunded"
- [ ] Show "Insufficient wallet balance" error in award flow if balance too low
- [ ] Add "Top Up Wallet" button with amount input

## Task 10: Frontend — Driver Dashboard
- [ ] Add "Payment Secured — ₹X held by FreightBid" badge on `assigned` and `in_transit` trip cards
- [ ] Add "Cancel Trip" button on `assigned` trips
- [ ] Build driver cancel modal with penalty warning: "You will receive ₹0. Your bids will be ranked lower for 7 days."
- [ ] Show suspension banner at top of page if `is_suspended == True`
- [ ] Add cancellation rate to My Rating tab

## Task 11: Frontend — Load Cards (Driver View)
- [ ] Fetch shipper profile data when loading open shipments (or include in shipment response)
- [ ] Show `⚠️ N cancellations this month` badge on load cards for flagged shippers
