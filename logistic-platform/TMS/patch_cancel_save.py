content = open('backend/routers/shipments.py', encoding='utf-8').read()

# Patch scenario 1&2 return to also save record
old1 = '''    # ── Scenario 1 & 2: open shipment ─────────────────────────
    if s.status == "open":
        s.status = "cancelled"
        db.commit()
        return {
            "message":          "Shipment cancelled successfully",
            "scenario":         "no_penalty",
            "driver_fee":       0,
            "shipper_refund":   0,
            "bid_count":        bid_count
        }'''

new1 = '''    # ── Scenario 1 & 2: open shipment ─────────────────────────
    if s.status == "open":
        s.status = "cancelled"
        rec = CancellationRecord(
            shipment_id=shipment_id, shipper_id=user["sub"],
            driver_id=s.assigned_driver_id, reason=reason,
            scenario="no_penalty", trip_amount=0, driver_fee=0, shipper_refund=0
        )
        db.add(rec)
        db.commit()
        return {
            "message":          "Shipment cancelled successfully",
            "scenario":         "no_penalty",
            "driver_fee":       0,
            "shipper_refund":   0,
            "bid_count":        bid_count
        }'''

# Patch assigned scenario return to save record
old2 = '''        # Mark shipment cancelled
        s.status = "cancelled"
        db.commit()

        return {
            "message":        "Shipment cancelled. Driver compensation applied.",
            "scenario":       "assigned_penalty",
            "driver_arrived": driver_arrived,
            "km_travelled":   round(km_travelled, 1),
            "total_route_km": round(total_route_km, 1),
            "trip_amount":    trip_amount,
            "driver_fee":     driver_fee,
            "shipper_refund": refund,
            "driver_id":      s.assigned_driver_id
        }'''

new2 = '''        # Mark shipment cancelled
        s.status = "cancelled"
        rec = CancellationRecord(
            shipment_id=shipment_id, shipper_id=user["sub"],
            driver_id=s.assigned_driver_id, reason=reason,
            scenario="assigned_penalty", trip_amount=trip_amount,
            driver_fee=driver_fee, shipper_refund=refund,
            km_travelled=round(km_travelled, 1),
            total_route_km=round(total_route_km, 1)
        )
        db.add(rec)
        db.commit()

        return {
            "message":        "Shipment cancelled. Driver compensation applied.",
            "scenario":       "assigned_penalty",
            "driver_arrived": driver_arrived,
            "km_travelled":   round(km_travelled, 1),
            "total_route_km": round(total_route_km, 1),
            "trip_amount":    trip_amount,
            "driver_fee":     driver_fee,
            "shipper_refund": refund,
            "driver_id":      s.assigned_driver_id
        }'''

# Patch in_transit scenario return to save record
old3 = '''        s.status = "cancelled"
        db.commit()

        return {
            "message":        "Shipment cancelled mid-trip. Proportional payment applied.",
            "scenario":       "in_transit_penalty",
            "completed_stops": completed_stops,
            "total_stops":    total_stops,
            "trip_amount":    trip_amount,
            "driver_fee":     driver_fee,
            "shipper_refund": refund,
            "driver_id":      s.assigned_driver_id
        }'''

new3 = '''        s.status = "cancelled"
        rec = CancellationRecord(
            shipment_id=shipment_id, shipper_id=user["sub"],
            driver_id=s.assigned_driver_id, reason=reason,
            scenario="in_transit_penalty", trip_amount=trip_amount,
            driver_fee=driver_fee, shipper_refund=refund,
            completed_stops=completed_stops, total_stops=total_stops
        )
        db.add(rec)
        db.commit()

        return {
            "message":        "Shipment cancelled mid-trip. Proportional payment applied.",
            "scenario":       "in_transit_penalty",
            "completed_stops": completed_stops,
            "total_stops":    total_stops,
            "trip_amount":    trip_amount,
            "driver_fee":     driver_fee,
            "shipper_refund": refund,
            "driver_id":      s.assigned_driver_id
        }'''

results = []
for old, new, label in [(old1,new1,'scenario1'), (old2,new2,'scenario3'), (old3,new3,'scenario4')]:
    if old in content:
        content = content.replace(old, new, 1)
        results.append(label + ' OK')
    else:
        results.append(label + ' NOT FOUND')

# Add GET endpoint for cancellation record
get_endpoint = '''

@router.get("/{shipment_id}/cancellation")
def get_cancellation_record(
    shipment_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """Get cancellation details for a shipment (shipper or driver)."""
    user = get_current_user(authorization)

    s = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not s:
        raise HTTPException(404, "Shipment not found")

    if user["role"] == "shipper" and s.shipper_id != user["sub"]:
        raise HTTPException(403, "Not your shipment")
    if user["role"] == "driver" and s.assigned_driver_id != user["sub"]:
        raise HTTPException(403, "Not assigned to this shipment")

    rec = db.query(CancellationRecord).filter(
        CancellationRecord.shipment_id == shipment_id
    ).order_by(CancellationRecord.cancelled_at.desc()).first()

    if not rec:
        return None

    shipper = db.query(User).filter(User.id == rec.shipper_id).first()
    driver  = db.query(User).filter(User.id == rec.driver_id).first() if rec.driver_id else None

    return {
        "scenario":        rec.scenario,
        "reason":          rec.reason,
        "trip_amount":     rec.trip_amount,
        "driver_fee":      rec.driver_fee,
        "shipper_refund":  rec.shipper_refund,
        "km_travelled":    rec.km_travelled,
        "total_route_km":  rec.total_route_km,
        "completed_stops": rec.completed_stops,
        "total_stops":     rec.total_stops,
        "cancelled_at":    rec.cancelled_at.isoformat(),
        "shipper_name":    shipper.name if shipper else None,
        "driver_name":     driver.name if driver else None,
        "driver_phone":    driver.phone if driver else None,
    }
'''

# Insert before the abandon endpoint
if '@router.post("/{shipment_id}/abandon")' in content:
    content = content.replace('@router.post("/{shipment_id}/abandon")', get_endpoint + '\n@router.post("/{shipment_id}/abandon")', 1)
    results.append('GET endpoint added OK')
else:
    results.append('GET endpoint: abandon marker not found')

open('backend/routers/shipments.py', 'w', encoding='utf-8').write(content)
for r in results:
    print(r)
