import sys
import subprocess
import os
import time
import atexit
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if not __package__:
    sys.path.insert(0, str(BASE_DIR.parent))
    __package__ = BASE_DIR.name

# ─── Auto-start eKYC backend ──────────────────────────────────────────────────
_EKYC_PORT = int(os.getenv("EKYC_PORT", "8002"))
_ekyc_proc = None

def _port_open(port):
    import socket
    s = socket.socket()
    r = s.connect_ex(("127.0.0.1", port)) == 0
    s.close()
    return r

def _find_ekyc():
    for p in [
        Path.home() / "OneDrive" / "Desktop" / "ekyc" / "AI-Native-E-KYC" / "backend",
        Path(f"C:/Users/{os.getenv('USERNAME','hp')}/OneDrive/Desktop/ekyc/AI-Native-E-KYC/backend"),
        BASE_DIR.parent.parent.parent.parent / "ekyc" / "AI-Native-E-KYC" / "backend",
    ]:
        if p.exists():
            return p
    return None

# Only run in the TOP-LEVEL process, not in uvicorn's reloaded worker
# uvicorn sets UVICORN_STARTED in the worker; we check its absence
if not os.environ.get("UVICORN_STARTED"):
    os.environ["UVICORN_STARTED"] = "1"
    if not _port_open(_EKYC_PORT):
        _ekyc_dir = _find_ekyc()
        if _ekyc_dir:
            print(f"[KYC] Starting eKYC on port {_EKYC_PORT}...")
            _ekyc_proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app",
                 "--port", str(_EKYC_PORT), "--host", "127.0.0.1"],
                cwd=str(_ekyc_dir),
            )
            # Wait up to 25s
            for _ in range(50):
                time.sleep(0.5)
                if _port_open(_EKYC_PORT):
                    print(f"[KYC] ✅ eKYC ready on port {_EKYC_PORT}")
                    break
            else:
                print(f"[KYC] ⚠ eKYC slow to start — will retry via proxy")

            def _cleanup():
                if _ekyc_proc and _ekyc_proc.poll() is None:
                    _ekyc_proc.terminate()
            atexit.register(_cleanup)
        else:
            print("[KYC] eKYC directory not found — start it manually: uvicorn main:app --port 8002")
    else:
        print(f"[KYC] eKYC already running on port {_EKYC_PORT}")
# ──────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .database import engine, Base
from .routers import auth, shipments, bids, tracking, drivers, pod, payments, messages, kyc
from .ws_manager import router as ws_router

# Create SQLAlchemy tables first so a fresh PostgreSQL/Neon database can run
# the compatibility migrations below without failing on missing tables.
Base.metadata.create_all(bind=engine)

def _run_schema_migration(sql: str) -> None:
    """Run one DDL statement in its own transaction so Postgres errors do not block later migrations."""
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception:
        pass

# Keep the users table aligned before any auth/KYC query runs.
for _sql in (
    "ALTER TABLE users ADD COLUMN kyc_status TEXT DEFAULT 'pending'",
    "ALTER TABLE users ADD COLUMN kyc_session_id TEXT",
    "ALTER TABLE users ADD COLUMN license_number TEXT",
    "ALTER TABLE users ADD COLUMN aadhaar_number VARCHAR",
    "ALTER TABLE users ADD COLUMN pan_number VARCHAR",
    "ALTER TABLE users ADD COLUMN kyc_name VARCHAR",
    "ALTER TABLE users ADD COLUMN kyc_dob VARCHAR",
    "ALTER TABLE users ADD COLUMN kyc_review_reason TEXT",
    "ALTER TABLE users ADD COLUMN kyc_review_details TEXT",
    "ALTER TABLE users ADD COLUMN kyc_verified_at TIMESTAMP",
):
    _run_schema_migration(_sql)

# Perform safe schema migrations (Option 1: keep data)
with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN est_time_hours FLOAT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN started_at TIMESTAMP"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN delivered_at TIMESTAMP"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN pickup_lat FLOAT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN pickup_lng FLOAT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN parent_shipment_id TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipment_destinations ADD COLUMN ack_status TEXT DEFAULT 'none'"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN num_trucks INTEGER DEFAULT 1"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN assigned_at TIMESTAMP"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN aadhaar_number VARCHAR"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN pan_number VARCHAR"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN kyc_name VARCHAR"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN kyc_dob VARCHAR"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN freight_adjusted_amount FLOAT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN freight_adjustment_delta FLOAT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN freight_adjustment_status TEXT DEFAULT 'none'"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN freight_adjustment_note TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN freight_adjustment_pi_id TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN freight_adjustment_requested_at TIMESTAMP"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN freight_adjustment_accepted_at TIMESTAMP"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE shipments ADD COLUMN freight_adjustment_paid_at TIMESTAMP"))
    except Exception:
        pass
    # POD & proof request migrations
    try:
        conn.execute(text("ALTER TABLE pods ADD COLUMN dest_id TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE pods ADD COLUMN pod_type TEXT DEFAULT 'delivery'"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE pods ADD COLUMN ack_status TEXT DEFAULT 'pending'"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE pods ADD COLUMN ack_notes TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE pods ADD COLUMN ack_at TIMESTAMP"))
    except Exception:
        pass
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS proof_requests (
                id TEXT PRIMARY KEY,
                shipment_id TEXT NOT NULL,
                shipper_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                image_url TEXT,
                created_at TIMESTAMP,
                fulfilled_at TIMESTAMP
            )
        """))
    except Exception:
        pass
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS complaints (
                id TEXT PRIMARY KEY,
                shipment_id TEXT NOT NULL,
                shipper_id TEXT NOT NULL,
                driver_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP,
                resolved_at TIMESTAMP
            )
        """))
    except Exception:
        pass
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                shipment_id TEXT NOT NULL,
                shipper_id TEXT NOT NULL,
                driver_id TEXT NOT NULL,
                amount FLOAT NOT NULL,
                currency TEXT DEFAULT 'inr',
                stripe_pi_id TEXT,
                stripe_pm_id TEXT,
                stripe_charge_id TEXT,
                status TEXT DEFAULT 'pending',
                card_last4 TEXT,
                card_brand TEXT,
                created_at TIMESTAMP,
                paid_at TIMESTAMP
            )
        """))
    except Exception:
        pass
    # Ensure payments table has the correct columns (migrate if old schema)
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN shipper_id TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN driver_id TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN stripe_pi_id TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN stripe_pm_id TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN stripe_charge_id TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN card_last4 TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN card_brand TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN paid_at TIMESTAMP"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN driver_fee FLOAT"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE payments ADD COLUMN shipper_refund FLOAT"))
    except Exception:
        pass

# Fix old 'succeeded' payments on non-delivered shipments → escrow_held
with engine.begin() as conn:
    try:
        conn.execute(text("""
            UPDATE payments SET status = 'escrow_held'
            WHERE status = 'succeeded'
            AND shipment_id IN (
                SELECT id FROM shipments WHERE status NOT IN ('delivered')
            )
        """))
    except Exception:
        pass
    # Create cancellation_records table if not exists
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS cancellation_records (
            id TEXT PRIMARY KEY,
            shipment_id TEXT NOT NULL,
            shipper_id TEXT NOT NULL,
            driver_id TEXT,
            reason TEXT NOT NULL,
            scenario TEXT NOT NULL,
            trip_amount FLOAT DEFAULT 0,
            driver_fee FLOAT DEFAULT 0,
            shipper_refund FLOAT DEFAULT 0,
            km_travelled FLOAT,
            total_route_km FLOAT,
            completed_stops INTEGER,
            total_stops INTEGER,
            cancelled_at TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS destination_change_requests (
            id TEXT PRIMARY KEY,
            shipment_id TEXT NOT NULL,
            dest_id TEXT NOT NULL,
            shipper_id TEXT NOT NULL,
            driver_id TEXT NOT NULL,
            new_address TEXT NOT NULL,
            new_lat FLOAT,
            new_lng FLOAT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP,
            responded_at TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            shipment_id TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMP,
            read_at TIMESTAMP
        )
    """))
    try:
        conn.execute(text("ALTER TABLE messages ADD COLUMN driver_id TEXT"))
    except Exception:
        pass
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ratings (
                id TEXT PRIMARY KEY,
                shipment_id TEXT NOT NULL,
                driver_id TEXT NOT NULL,
                shipper_id TEXT NOT NULL,
                score FLOAT NOT NULL,
                created_at TIMESTAMP
            )
        """))
    except Exception:
        pass
    try:
        conn.execute(text("SELECT 1"))
    except Exception:
        pass

# eKYC and Verification columns — run in a separate block so failures here never affect other migrations
with engine.begin() as conn:
    for col_name, col_type in [
        ("kyc_status", "TEXT DEFAULT 'pending'"),
        ("kyc_session_id", "TEXT"),
        ("license_number", "TEXT"),
        ("kyc_verified_at", "TIMESTAMP"),
        ("kyc_review_reason", "TEXT"),
        ("kyc_review_details", "TEXT"),
        ("verification", "TEXT DEFAULT 'no'")
    ]:
        try:
            conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
        except Exception:
            pass

# Backfill: shippers don't need KYC — mark existing ones as verified, and backfill verification column
with engine.begin() as conn:
    try:
        conn.execute(text(
            "UPDATE users SET kyc_status = 'verified' "
            "WHERE role = 'shipper' AND (kyc_status IS NULL OR kyc_status = 'pending')"
        ))
    except Exception:
        pass
    try:
        conn.execute(text(
            "UPDATE users SET verification = 'yes' "
            "WHERE role = 'shipper' OR kyc_status = 'verified'"
        ))
    except Exception:
        pass

app = FastAPI(
    title="FreightBid — Logistics Platform",
    description="Shipper-Driver bidding and shipment tracking platform",
    version="1.0.0"
)

# Allow frontend to call backend (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(auth.router,      prefix="/api/auth",      tags=["Auth"])
app.include_router(shipments.router, prefix="/api/shipments", tags=["Shipments"])
app.include_router(bids.router,      prefix="/api/shipments",  tags=["Bids"])
app.include_router(tracking.router,  prefix="/api/track",     tags=["Tracking"])
app.include_router(drivers.router,   prefix="/api/drivers",   tags=["Drivers"])
app.include_router(pod.router,       prefix="/api/pod",       tags=["POD"])
app.include_router(payments.router,  prefix="/api/payments",  tags=["Payments"])
app.include_router(messages.router,  prefix="/api/shipments",  tags=["Messages"])
app.include_router(kyc.router,       prefix="/api/kyc",       tags=["KYC"])
app.include_router(ws_router,        tags=["WebSockets"])


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "FreightBid API is running"}


@app.get("/api/diagnostic")
def diagnostic():
    import traceback
    import uuid
    from fastapi import Depends
    from sqlalchemy.orm import Session
    from .database import get_db, engine
    from .models import User

    # Using standard session creation to avoid nested Depends issues
    from .database import SessionLocal
    db = SessionLocal()

    try:
        # 1. Let's try to query columns in users
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("users")]
        
        # 2. Try registering a test user to see the exact insertion exception
        test_email = f"test_diagnostic_{uuid.uuid4().hex[:6]}@example.com"
        test_user = User(
            name="Test Diagnostic",
            email=test_email,
            password="test",
            role="shipper",
            phone="12345",
            kyc_status="pending"
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        db.delete(test_user)
        db.commit()
        
        return {"status": "success", "columns": columns}
    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "error_class": e.__class__.__name__,
            "error_msg": str(e),
            "traceback": traceback.format_exc()
        }
    finally:
        db.close()


# Absolute path — works no matter where uvicorn is run from
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
UPLOADS_DIR  = FRONTEND_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Serve uploaded images at /uploads/*
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Serve frontend static files — MUST come last
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


























