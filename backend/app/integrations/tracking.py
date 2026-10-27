import time
from contextlib import contextmanager
from typing import Iterator

from app.db import IntegrationLog, get_session


@contextmanager
def tracked(service: str, op: str) -> Iterator[None]:
    start = time.monotonic()
    error: str | None = None
    try:
        yield
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        raise
    finally:
        with get_session() as session:
            session.add(
                IntegrationLog(
                    service=service,
                    op=op,
                    ok=error is None,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    error=error,
                )
            )
            session.commit()
