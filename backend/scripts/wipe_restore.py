"""Delete the local learned state and rebuild it from Walrus. --all also deletes the forecast journal."""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import delete  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Forecast, Lesson, MemoryRef, PolicyState, get_session, init_db  # noqa: E402
from app.live.engine import current_book, restore_from_walrus  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="also wipe the forecast journal and memory index")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    init_db()
    assets = get_settings().assets

    before = {a: current_book(a)[0].episodes for a in assets}
    with get_session() as session:
        for table in (PolicyState, Lesson) + ((Forecast, MemoryRef) if args.all else ()):
            session.exec(delete(table))
        session.commit()
    print("episodes before wipe:", before)
    print("episodes after wipe: ", {a: current_book(a)[0].episodes for a in assets})
    for asset in assets:
        print(json.dumps(restore_from_walrus(asset), indent=2))
    print("episodes after restore:", {a: current_book(a)[0].episodes for a in assets})
