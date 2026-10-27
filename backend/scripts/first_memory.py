"""Write one init memory to Walrus Memory Mainnet, then recall it back."""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from memwal import MemWal, RecallParams

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

NAMESPACE = "mr-healthcheck"


async def main() -> int:
    memwal = MemWal.create(
        key=os.environ["MEMWAL_PRIVATE_KEY"],
        account_id=os.environ["MEMWAL_ACCOUNT_ID"],
        server_url=os.environ.get("MEMWAL_SERVER_URL", "https://relayer.memory.walrus.xyz"),
        namespace=NAMESPACE,
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = (
        f"[INIT] MarketRecall AI memory initialized @{now}. "
        "Agent forecasts SUI 4h direction and learns from resolved outcomes."
    )
    try:
        result = await memwal.remember_and_wait(text, idempotency_key="marketrecall-init-v1")
        print("remember:", result)

        matches = await memwal.recall(RecallParams(query="MarketRecall initialized", limit=3))
        for memory in matches.results:
            print(f"recall: {memory.text!r} (distance={memory.distance:.3f})")
        if not matches.results:
            print("recall: no results yet")
    finally:
        await memwal.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
