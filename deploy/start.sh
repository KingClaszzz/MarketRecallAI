#!/bin/sh
set -e
cd /app/backend

# Without DATABASE_URL the app falls back to SQLite inside the container (lost on every restart).
if [ -z "$DATABASE_URL" ]; then
  echo "DATABASE_URL is not set: using container-local SQLite"
fi

# Empty database: pull price/onchain history, then rebuild the learned state from Walrus.
# Skipped when the data was copied over with scripts/copy_db.py.
if ! python -c "
import sys
from sqlmodel import select
from app.db import Candle, get_session, init_db
init_db()
with get_session() as s:
    sys.exit(0 if s.exec(select(Candle).limit(1)).first() else 1)
"; then
  echo "Empty database: seeding ${BACKFILL_DAYS:-90} days of history and restoring memory from Walrus"
  python scripts/backfill.py --days "${BACKFILL_DAYS:-90}"
  python scripts/wipe_restore.py
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
