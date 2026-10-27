"""Usage: python backend/scripts/backfill.py [--days 90] [--skip-onchain]"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.backfill import backfill_candles, backfill_onchain  # noqa: E402
from app.db import init_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--skip-onchain", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    print("candles saved:", backfill_candles(args.days))
    if not args.skip_onchain:
        print("onchain snapshots saved:", backfill_onchain(args.days))


if __name__ == "__main__":
    main()
