"""HTTP client setup with OS trust store and polite API headers."""

from __future__ import annotations

import time
from typing import Any

import httpx
import truststore
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

truststore.inject_into_ssl()


class RateLimitedClient:
    """Thin httpx wrapper with rate limiting and retries."""

    def __init__(
        self,
        *,
        base_url: str = "",
        mailto: str = "pqm-readiness@example.org",
        requests_per_second: float = 5.0,
        timeout: float = 60.0,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        headers = {
            "User-Agent": f"pqm-readiness/0.1.0 (mailto:{mailto})",
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        self._client = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        self._min_interval = 1.0 / requests_per_second
        self._last_request_at = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RateLimitedClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_at = time.monotonic()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        self._throttle()
        response = self._client.get(url, params=params)
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "5"))
            logger.warning("Rate limited; sleeping {}s", retry_after)
            time.sleep(retry_after)
            response = self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()
