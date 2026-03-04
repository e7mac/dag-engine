from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from src.types import RetryConfig


async def with_retry(
    fn: Callable[..., Any],
    config: RetryConfig,
    on_attempt: Callable[[int, Exception], None] | None = None,
) -> Any:
    """Retry wrapper with exponential backoff.

    Retry schedule:
      - Attempt 1: immediate
      - Attempt N (N >= 2): wait backoff_ms * 2^(N-2) ms
    """
    last_exc: Exception | None = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if on_attempt:
                on_attempt(attempt, exc)
            if attempt < config.max_attempts:
                delay_s = (config.backoff_ms * (2 ** (attempt - 1))) / 1000.0
                await asyncio.sleep(delay_s)

    raise last_exc  # type: ignore[misc]
