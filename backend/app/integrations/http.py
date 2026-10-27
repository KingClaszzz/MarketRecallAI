import time

import httpx

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None, retries: int = 3, timeout: float = 20.0):
    for attempt in range(retries + 1):
        try:
            response = httpx.get(url, params=params, headers=headers, timeout=timeout)
            if response.status_code in RETRYABLE_STATUS and attempt < retries:
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
            return response.json()
        except httpx.TransportError:
            if attempt == retries:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")
