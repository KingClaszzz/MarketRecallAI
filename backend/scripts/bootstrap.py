"""Seed memory from the backtest and snapshot it to Walrus. Run once after backfill.py.

Usage: python backend/scripts/bootstrap.py [--asset WAL]
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import init_db  # noqa: E402
from app.live.engine import bootstrap  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", action="append", help="repeatable; default: all configured assets")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    init_db()
    for asset in args.asset or get_settings().assets:
        print(asset, json.dumps(bootstrap(asset.upper()), indent=2, default=str))
