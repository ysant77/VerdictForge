from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    text: str


class PoliteAsyncHttpClient:
    """Async HTTP client with polite crawling defaults.

    Features:
    - bounded concurrency
    - jittered per-request delay
    - exponential backoff retries for 429/5xx
    """

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_s: float,
        max_concurrency: int,
        min_delay_s: float,
        max_retries: int,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=httpx.Timeout(timeout_s),
            follow_redirects=True,
        )
        self._sem = asyncio.Semaphore(max_concurrency)
        self._min_delay_s = min_delay_s
        self._max_retries = max_retries

    async def close(self) -> None:
        await self._client.aclose()

    async def get_text(self, url: str) -> FetchResult:
        async with self._sem:
            await asyncio.sleep(self._min_delay_s + random.random() * self._min_delay_s)

            last_exc: Optional[Exception] = None
            for attempt in range(self._max_retries):
                try:
                    resp = await self._client.get(url)
                    if resp.status_code in (429, 502, 503, 504):
                        backoff = min(10.0, (2 ** attempt) + random.random())
                        await asyncio.sleep(backoff)
                        continue
                    resp.raise_for_status()
                    return FetchResult(url=url, status_code=resp.status_code, text=resp.text)
                except Exception as e:
                    last_exc = e
                    backoff = min(10.0, (2 ** attempt) + random.random())
                    await asyncio.sleep(backoff)

            raise RuntimeError(f"Failed to fetch after retries: {url}") from last_exc
