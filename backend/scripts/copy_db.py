"""Copy every table from the local SQLite database into an empty hosted Postgres (run once before deploying).

Usage: python backend/scripts/copy_db.py "postgresql://user:pass@host/db?sslmode=require" [--from path/to/marketrecall.db]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlmodel import SQLModel, create_engine  # noqa: E402

from app import db  # noqa: E402

BATCH = 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Postgres URL")
    parser.add_argument("--from", dest="source", default=str(Path(__file__).resolve().parents[1] / "data" / "marketrecall.db"))
    args = parser.parse_args()

    source = create_engine(f"sqlite:///{Path(args.source).as_posix()}")
    db._engine = None
    db.get_settings().database_url = args.target
    target = db.get_engine()
    if target.dialect.name != "postgresql":
        raise SystemExit("target must be a Postgres URL")
    db.init_db()

    tables = SQLModel.metadata.sorted_tables
    with target.connect() as conn:
        filled = [t.name for t in tables if conn.execute(select(func.count()).select_from(t)).scalar()]
    if filled:
        raise SystemExit(f"target is not empty ({', '.join(filled)}); refusing to copy over existing data")

    with source.connect() as src, target.begin() as dst:
        for table in tables:
            rows = [dict(r) for r in src.execute(select(table)).mappings()]
            for i in range(0, len(rows), BATCH):
                dst.execute(table.insert(), rows[i:i + BATCH])
            if "id" in table.c and rows:  # explicit ids leave the sequence behind
                dst.exec_driver_sql(f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', 'id'), {max(r['id'] for r in rows)})")
            print(f"{table.name:<18} {len(rows):>7}")


if __name__ == "__main__":
    main()
