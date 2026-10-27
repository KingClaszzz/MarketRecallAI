"""In-process rate limits. Assumes a single backend process."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings


class RateLimit:
    """At most `limit` hits per key in a sliding `window` of seconds."""

    def __init__(self, limit: int, window: float, message: str = "Too many requests. Try again in a minute."):
        self.limit, self.window, self.message = limit, window, message
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._swept = time.monotonic()

    def hit(self, key: str) -> int:
        """Raises 429 when over the limit; returns hits left."""
        now = time.monotonic()
        with self._lock:
            if now - self._swept > self.window:  # drop idle keys
                for k in [k for k, q in self._hits.items() if not q or now - q[-1] > self.window]:
                    del self._hits[k]
                self._swept = now
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                raise HTTPException(status_code=429, detail=self.message)
            hits.append(now)
            return self.limit - len(hits)


def client_ip(request: Request) -> str:
    """Behind `proxy_hops` trusted proxies, the client is that many entries from the right of X-Forwarded-For;
    entries further left are client-supplied and can be spoofed."""
    settings = get_settings()
    if settings.trust_proxy:
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if hops:
            return hops[-min(max(settings.proxy_hops, 1), len(hops))]
    return request.client.host if request.client else "unknown"
