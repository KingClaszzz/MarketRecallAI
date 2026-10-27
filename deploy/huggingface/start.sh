#!/bin/sh
set -e
cd /app/backend

# Persistent storage is mounted at /data when enabled; otherwise the database lives in the container.
if [ -z "$DATABASE_URL" ]; then
  if [ -d /data ] && [ -w /data ]; then DB=/data/marketrecall.db; else DB=/app/backend/data/marketrecall.db; fi
  export DATABASE_URL="sqlite:///$DB"
else
  DB="${DATABASE_URL#sqlite:///}"
fi

# First start: pull price/onchain history, then rebuild the learned state from Walrus.
if [ ! -f "$DB.seeded" ]; then
  echo "Seeding $DB (${BACKFILL_DAYS:-90} days of history + Walrus restore)"
  python scripts/backfill.py --days "${BACKFILL_DAYS:-90}"
  python scripts/wipe_restore.py
  touch "$DB.seeded"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 7860 --workers 1
