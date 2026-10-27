"""Usage: python backend/scripts/backtest.py [--asset WAL] [--no-onchain] [--out path.csv]"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtest.walkforward import BacktestConfig, run_backtest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", default="SUI")
    parser.add_argument("--no-onchain", action="store_true")
    parser.add_argument("--out", default=None, help="default: backend/data/backtest_<asset>.csv")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    asset = args.asset.upper()
    result = run_backtest(BacktestConfig(asset=asset, with_onchain=not args.no_onchain, include_ablation=not args.no_onchain))
    result["rows"].to_csv(args.out or Path(__file__).resolve().parents[1] / "data" / f"backtest_{asset}.csv")
    print(json.dumps(result["report"], indent=2, default=str))


if __name__ == "__main__":
    main()
