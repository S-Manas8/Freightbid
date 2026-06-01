import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from dotenv import load_dotenv

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "backend"

from .models import Base

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SQLITE_PATH = Path(os.getenv("SQLITE_DATABASE_PATH", BASE_DIR / "logistics.db"))
POSTGRES_URL = os.getenv("DATABASE_URL")


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def fetch_sqlite_rows(engine, table):
    inspector = inspect(engine)
    if table.name not in inspector.get_table_names():
        return []

    source_columns = {col["name"] for col in inspector.get_columns(table.name)}
    target_columns = [col.name for col in table.columns if col.name in source_columns]
    if not target_columns:
        return []

    column_sql = ", ".join(quote_identifier(col) for col in target_columns)
    table_sql = quote_identifier(table.name)
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT {column_sql} FROM {table_sql}")).mappings().all()
    return [dict(row) for row in rows]


def copy_table(source_engine, target_engine, table):
    rows = fetch_sqlite_rows(source_engine, table)
    if not rows:
        return 0, 0

    inserted = 0
    with target_engine.begin() as conn:
        for start in range(0, len(rows), 500):
            chunk = rows[start:start + 500]
            stmt = pg_insert(table).values(chunk).on_conflict_do_nothing()
            result = conn.execute(stmt)
            inserted += result.rowcount or 0

    return len(rows), inserted


def main():
    if not POSTGRES_URL:
        raise SystemExit("DATABASE_URL is required and must point to your Neon/PostgreSQL database.")
    if not POSTGRES_URL.startswith(("postgresql://", "postgres://")):
        raise SystemExit("DATABASE_URL must be a PostgreSQL URL for this migration.")
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite database not found: {SQLITE_PATH}")

    source_engine = create_engine(f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False})
    target_engine = create_engine(POSTGRES_URL)

    Base.metadata.create_all(bind=target_engine)

    total_source = 0
    total_inserted = 0
    for table in Base.metadata.sorted_tables:
        source_count, inserted_count = copy_table(source_engine, target_engine, table)
        total_source += source_count
        total_inserted += inserted_count
        print(f"{table.name}: copied {inserted_count}/{source_count}")

    print(f"Done. Inserted {total_inserted} rows from {total_source} SQLite rows.")


if __name__ == "__main__":
    main()
