import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'logistics.db'}")
SQLITE_FALLBACK = f"sqlite:///{BASE_DIR / 'logistics.db'}"

def _make_engine(url):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)

# Try configured DB; fall back to SQLite if unreachable or its driver is missing.
try:
    engine = _make_engine(DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print(f"[DB] Connected to: {DATABASE_URL[:40]}...")
except Exception as e:
    if not DATABASE_URL.startswith("sqlite"):
        print(f"[DB] Cannot reach configured DB ({e.__class__.__name__}), falling back to SQLite")
        DATABASE_URL = SQLITE_FALLBACK
        engine = _make_engine(DATABASE_URL)
    else:
        raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

