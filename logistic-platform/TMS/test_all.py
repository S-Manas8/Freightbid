"""
Full end-to-end test for TMS + eKYC integration.
Run: python test_all.py
"""
import requests
import json
import sys
import os

TMS   = "http://localhost:8000"
EKYC  = "http://localhost:8001"
PASS  = "\033[92m✓\033[0m"
FAIL  = "\033[91m✗\033[0m"
WARN  = "\033[93m⚠\033[0m"

results = []

def check(name, ok, detail=""):
    icon = PASS if ok else FAIL
    print(f"  {icon} {name}" + (f"  →  {detail}" if detail else ""))
    results.append((name, ok))

def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")

# ── 1. Server Health ──────────────────────────────────────────────────────────
section("1. Server Health")
try:
    r = requests.get(f"{TMS}/api/health", timeout=5)
    check("TMS backend running (port 8000)", r.status_code == 200, r.json().get("message",""))
except Exception as e:
    check("TMS backend running (port 8000)", False, str(e))

try:
    r = requests.get(f"{EKYC}/health", timeout=5)
    check("eKYC backend running (port 8001)", r.status_code == 200, r.json().get("status",""))
except Exception as e:
    check("eKYC backend running (port 8001)", False, str(e))

# ── 2. TMS Auth ───────────────────────────────────────────────────────────────
section("2. TMS Auth — Register & Login")
import uuid
test_email_driver  = f"testdriver_{uuid.uuid4().hex[:6]}@test.com"
test_email_shipper = f"testshipper_{uuid.uuid4().hex[:6]}@test.com"
driver_token = None
shipper_token = None
driver_id = None

try:
    r = requests.post(f"{TMS}/api/auth/register", json={
        "name": "Test Driver", "email": test_email_driver,
        "password": "test1234", "role": "driver", "phone": "9876543210"
    }, timeout=5)
    ok = r.status_code == 200
    data = r.json()
    driver_token = data.get("token")
    driver_id = data.get("id")
    kyc_status = data.get("kyc_status", "MISSING")
    check("Driver registration", ok, f"kyc_status={kyc_status}")
except Exception as e:
    check("Driver registration", False, str(e))

try:
    r = requests.post(f"{TMS}/api/auth/register", json={
        "name": "Test Shipper", "email": test_email_shipper,
        "password": "test1234", "role": "shipper", "phone": "9876543211"
    }, timeout=5)
    ok = r.status_code == 200
    data = r.json()
    shipper_token = data.get("token")
    kyc_status = data.get("kyc_status", "MISSING")
    check("Shipper registration", ok, f"kyc_status={kyc_status} (should be pending)")
except Exception as e:
    check("Shipper registration", False, str(e))

try:
    r = requests.post(f"{TMS}/api/auth/login", json={
        "email": test_email_driver, "password": "test1234"
    }, timeout=5)
    ok = r.status_code == 200
    data = r.json()
    kyc_status = data.get("kyc_status", "MISSING")
    check("Driver login", ok, f"kyc_status={kyc_status}")
except Exception as e:
    check("Driver login", False, str(e))

# ── 3. TMS KYC Endpoints ──────────────────────────────────────────────────────
section("3. TMS KYC Endpoints")
if driver_token:
    try:
        r = requests.get(f"{TMS}/api/kyc/status",
                         headers={"Authorization": f"Bearer {driver_token}"}, timeout=5)
        ok = r.status_code == 200
        data = r.json()
        check("GET /api/kyc/status", ok, f"kyc_status={data.get('kyc_status')}")
    except Exception as e:
        check("GET /api/kyc/status", False, str(e))

    try:
        r = requests.post(f"{TMS}/api/kyc/complete",
                          headers={"Authorization": f"Bearer {driver_token}"},
                          json={"session_id": "test-session-123", "status": "approved",
                                "license_number": "DL1234567890"},
                          timeout=8)
        ok = r.status_code == 200
        data = r.json()
        check("POST /api/kyc/complete (approve driver)", ok,
              f"kyc_status={data.get('kyc_status')}, license={data.get('license_number')}")
    except Exception as e:
        check("POST /api/kyc/complete", False, str(e))

    # Verify status updated
    try:
        r = requests.get(f"{TMS}/api/kyc/status",
                         headers={"Authorization": f"Bearer {driver_token}"}, timeout=5)
        data = r.json()
        ok = data.get("kyc_status") == "verified"
        check("KYC status updated to verified", ok, f"got: {data.get('kyc_status')}")
    except Exception as e:
        check("KYC status updated to verified", False, str(e))
else:
    print(f"  {WARN} Skipping KYC tests — no driver token")

# ── 4. KYC Guard on Bids ──────────────────────────────────────────────────────
section("4. KYC Guard — Bid Blocking")

# Register a fresh unverified driver
unverified_token = None
try:
    r = requests.post(f"{TMS}/api/auth/register", json={
        "name": "Unverified Driver", "email": f"unverified_{uuid.uuid4().hex[:6]}@test.com",
        "password": "test1234", "role": "driver", "phone": "9876543212"
    }, timeout=5)
    unverified_token = r.json().get("token")
    check("Unverified driver registered", r.status_code == 200)
except Exception as e:
    check("Unverified driver registered", False, str(e))

if unverified_token and shipper_token:
    # Create a shipment as shipper
    shipment_id = None
    try:
        r = requests.post(f"{TMS}/api/shipments/", json={
            "pickup_address": "Mumbai", "drop_address": "Delhi",
            "goods_desc": "Test goods", "weight_kg": 100,
            "vehicle_type": "Truck", "num_trucks": 1
        }, headers={"Authorization": f"Bearer {shipper_token}"}, timeout=5)
        ok = r.status_code == 200
        resp_data = r.json() if ok else {}
        # shipment id can be under "id" or "shipment_id"
        shipment_id = resp_data.get("id") or resp_data.get("shipment_id")
        check("Shipper creates shipment", ok, f"id={shipment_id}")
    except Exception as e:
        check("Shipper creates shipment", False, str(e))

    if shipment_id:
        # Unverified driver tries to bid — should be blocked
        try:
            r = requests.post(f"{TMS}/api/shipments/{shipment_id}/bid",
                              json={"amount": 5000},
                              headers={"Authorization": f"Bearer {unverified_token}"},
                              timeout=5)
            blocked = r.status_code == 403
            detail = r.json().get("detail", "")
            check("Unverified driver bid BLOCKED (403)", blocked, detail[:60])
        except Exception as e:
            check("Unverified driver bid BLOCKED", False, str(e))

        # Verified driver can bid
        if driver_token:
            try:
                r = requests.post(f"{TMS}/api/shipments/{shipment_id}/bid",
                                  json={"amount": 4500},
                                  headers={"Authorization": f"Bearer {driver_token}"},
                                  timeout=5)
                ok = r.status_code == 200
                check("Verified driver bid ALLOWED (200)", ok, r.json().get("message",""))
            except Exception as e:
                check("Verified driver bid ALLOWED", False, str(e))

# ── 5. eKYC Session ───────────────────────────────────────────────────────────
section("5. eKYC — Session & Document Extraction")
session_id = None
try:
    r = requests.post(f"{EKYC}/api/v1/sessions",
                      json={"user_id": f"driver_{driver_id or 'test'}"},
                      timeout=5)
    ok = r.status_code == 200
    session_id = r.json().get("id")
    check("eKYC session creation", ok, f"session_id={session_id[:16] if session_id else 'None'}...")
except Exception as e:
    check("eKYC session creation", False, str(e))

# Test OCR with a synthetic image
if session_id:
    try:
        import numpy as np
        import cv2
        from PIL import Image, ImageDraw, ImageFont
        import io

        # Create a synthetic Aadhaar-like image
        img = Image.new("RGB", (600, 350), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 20),  "Government of India",        fill=(0, 0, 0))
        draw.text((20, 60),  "Sutapa Pal Datta",           fill=(0, 0, 0))
        draw.text((20, 90),  "Date of Birth/DOB: 26/01/1979", fill=(0, 0, 0))
        draw.text((20, 120), "Female/ FEMALE",             fill=(0, 0, 0))
        draw.text((20, 180), "6641 2804 9316",             fill=(0, 0, 0))
        draw.text((20, 220), "VID : 9179 3343 7087 9130",  fill=(0, 0, 0))
        draw.text((20, 260), "Aadhaar",                    fill=(0, 0, 0))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)

        r = requests.post(f"{EKYC}/api/v1/documents/extract",
                          data={"session_id": session_id, "side": "front"},
                          files={"file": ("aadhaar.jpg", buf, "image/jpeg")},
                          timeout=30)
        ok = r.status_code == 200
        if ok:
            data = r.json()
            fields = data.get("extracted_fields", {})
            doc_type = data.get("doc_type", "unknown")
            conf = round((data.get("ocr_confidence", 0)) * 100, 1)
            has_name = bool(fields.get("name"))
            has_dob  = bool(fields.get("dob"))
            has_id   = bool(fields.get("id_number"))
            check("eKYC document extraction (OCR)", ok,
                  f"doc_type={doc_type}, conf={conf}%, name={has_name}, dob={has_dob}, id={has_id}")
            if fields:
                for k, v in fields.items():
                    print(f"       {k}: {v}")
        else:
            check("eKYC document extraction (OCR)", False, r.text[:100])
    except ImportError:
        print(f"  {WARN} Skipping OCR test — PIL/numpy not available for synthetic image")
    except Exception as e:
        check("eKYC document extraction (OCR)", False, str(e))

# ── 6. eKYC Risk & Compliance ─────────────────────────────────────────────────
section("6. eKYC — Risk & Compliance")
if session_id:
    try:
        r = requests.post(f"{EKYC}/api/v1/risk/assess", json={
            "session_id": session_id,
            "doc_result": {"extracted_fields": {"name": "Test Driver", "dob": "01/01/1990"},
                           "ocr_confidence": 0.85, "quality_score": 0.9,
                           "is_tampered": False, "doc_type": "national_id"},
            "biometric_result": {"face_match_score": 0.92, "liveness_score": 0.88,
                                 "deepfake_score": 0.05, "is_live": True, "is_match": True},
            "behavioral": {"session_duration_ms": 0.4, "retry_count": 0,
                           "device_anomaly": 0.0, "ip_risk": 0.0}
        }, timeout=10)
        ok = r.status_code == 200
        if ok:
            data = r.json()
            check("eKYC risk assessment", ok,
                  f"risk_score={data.get('risk_score')}, level={data.get('risk_level')}")
        else:
            check("eKYC risk assessment", False, r.text[:100])
    except Exception as e:
        check("eKYC risk assessment", False, str(e))

    try:
        r = requests.post(f"{EKYC}/api/v1/compliance/screen", json={
            "session_id": session_id,
            "extracted_fields": {"name": "Test Driver", "dob": "01/01/1990"},
            "country_code": "IN"
        }, timeout=10)
        ok = r.status_code == 200
        if ok:
            data = r.json()
            check("eKYC compliance screening", ok,
                  f"sanctioned={data.get('is_sanctioned')}, pep={data.get('is_pep')}, status={data.get('overall_status')}")
        else:
            check("eKYC compliance screening", False, r.text[:100])
    except Exception as e:
        check("eKYC compliance screening", False, str(e))

# ── 7. Frontend Pages ─────────────────────────────────────────────────────────
section("7. Frontend Pages")
pages = [
    ("/", "Login page"),
    ("/pages/driver.html", "Driver dashboard"),
    ("/pages/shipper.html", "Shipper dashboard"),
    ("/pages/kyc.html", "KYC page"),
]
for path, name in pages:
    try:
        r = requests.get(f"{TMS}{path}", timeout=5)
        ok = r.status_code == 200 and "html" in r.headers.get("content-type","")
        check(name, ok, f"HTTP {r.status_code}")
    except Exception as e:
        check(name, False, str(e))

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
passed = sum(1 for _, ok in results if ok)
total  = len(results)
failed = [(name, ok) for name, ok in results if not ok]

print(f"\n  Passed: {passed}/{total}")
if failed:
    print(f"\n  Failed tests:")
    for name, _ in failed:
        print(f"    {FAIL} {name}")
else:
    print(f"\n  \033[92mAll tests passed!\033[0m")

print()
