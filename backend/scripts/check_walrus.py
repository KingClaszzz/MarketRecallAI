"""Read-only Walrus Memory check: relayer health, key pair match, authenticated call."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from memwal import MemWal

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


async def main() -> int:
    memwal = MemWal.create(
        key=os.environ["MEMWAL_PRIVATE_KEY"],
        account_id=os.environ["MEMWAL_ACCOUNT_ID"],
        server_url=os.environ.get("MEMWAL_SERVER_URL", "https://relayer.memory.walrus.xyz"),
        namespace="mr-healthcheck",
    )
    ok = True
    try:
        print("health:", await memwal.health())

        public_key = await memwal.get_public_key_hex()
        expected = os.environ.get("MEMWAL_AGENT_ID", "")
        match = public_key.lower().removeprefix("0x") == expected.lower().removeprefix("0x")
        print(f"public key: {public_key} (matches MEMWAL_AGENT_ID: {match})")
        ok &= match

        page = await memwal.list_namespaces(limit=20)
        print("authenticated list_namespaces:", page)
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        ok = False
    finally:
        await memwal.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
