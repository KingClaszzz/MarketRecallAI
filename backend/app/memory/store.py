"""Walrus Memory adapter. Every write is mirrored in MemoryRef so the dashboard can link blobs."""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import datetime, time, timezone

from memwal import MemWalSync, RecallParams
from sqlmodel import func, select

from app.config import get_settings
from app.db import MemoryRef, get_session
from app.integrations.tracking import tracked

log = logging.getLogger(__name__)

NS_EPISODES = "mr-episodes"
NS_CREDIBILITY = "mr-credibility"
NS_LESSONS = "mr-lessons"
NS_DECISIONS = "mr-decisions"


# A MemWalSync client shared across threads deadlocks (its asyncio.Lock binds to one event loop),
# so each thread gets its own, with a cap on concurrent calls.
_local = threading.local()
_slots = threading.BoundedSemaphore(4)
WAIT_FOR_SLOT_S = 15


def _client() -> MemWalSync:
    if not hasattr(_local, "client"):
        s = get_settings()
        _local.client = MemWalSync.create(key=s.memwal_private_key, account_id=s.memwal_account_id,
                                          server_url=s.memwal_server_url)
    return _local.client


@contextmanager
def _slot():
    if not _slots.acquire(timeout=WAIT_FOR_SLOT_S):
        raise TimeoutError("walrus memory is busy")
    try:
        yield
    finally:
        _slots.release()


def writes_today() -> int:
    start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    with get_session() as session:
        return session.exec(
            select(func.count()).select_from(MemoryRef).where(MemoryRef.ts >= start, MemoryRef.status == "STORED")
        ).one()


def remember(namespace: str, kind: str, text: str, ref: dict | None = None, essential: bool = False) -> MemoryRef:
    """Write one memory. Non-essential writes respect the daily budget; failures are logged, not raised."""
    row = MemoryRef(namespace=namespace, kind=kind, text=text, ref=ref or {})
    if not essential and writes_today() >= get_settings().memwal_max_writes_per_day:
        row.status = "SKIPPED_BUDGET"
    else:
        try:
            with tracked("walrus", f"remember {namespace}"), _slot():
                result = _client().remember_and_wait(text, namespace=namespace)
            row.memwal_id, row.blob_id, row.status = result.id, result.blob_id, "STORED"
        except Exception as exc:
            log.exception("walrus remember failed")
            row.status, row.error = "FAILED", f"{type(exc).__name__}: {exc}"[:500]
    with get_session() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def recall(namespace: str, query: str, limit: int = 5, max_distance: float | None = None) -> list[dict]:
    with tracked("walrus", f"recall {namespace}"), _slot():
        result = _client().recall(RecallParams(query=query, limit=limit, namespace=namespace, max_distance=max_distance))
    return [
        {"blob_id": m.blob_id, "text": m.text, "distance": m.distance, "created_at": str(m.created_at)}
        for m in result.results
    ]
