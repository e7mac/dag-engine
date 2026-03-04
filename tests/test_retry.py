from __future__ import annotations

import time

import pytest

from src.engine.retry import with_retry
from src.types import RetryConfig


async def test_succeeds_immediately():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await with_retry(fn, RetryConfig(max_attempts=3, backoff_ms=100))
    assert result == "ok"
    assert call_count == 1


async def test_succeeds_on_second_attempt():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("fail")
        return "recovered"

    result = await with_retry(fn, RetryConfig(max_attempts=3, backoff_ms=100))
    assert result == "recovered"
    assert call_count == 2


async def test_succeeds_on_last_attempt():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("fail")
        return "barely"

    result = await with_retry(fn, RetryConfig(max_attempts=3, backoff_ms=50))
    assert result == "barely"
    assert call_count == 3


async def test_exhausts_attempts_and_raises():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        raise ValueError(f"attempt {call_count}")

    with pytest.raises(ValueError, match="attempt 3"):
        await with_retry(fn, RetryConfig(max_attempts=3, backoff_ms=50))

    assert call_count == 3


async def test_on_attempt_callback():
    attempts_seen: list[tuple[int, str]] = []

    async def fn():
        raise RuntimeError("boom")

    def on_attempt(attempt: int, exc: Exception) -> None:
        attempts_seen.append((attempt, str(exc)))

    with pytest.raises(RuntimeError):
        await with_retry(fn, RetryConfig(max_attempts=3, backoff_ms=50), on_attempt=on_attempt)

    assert len(attempts_seen) == 3
    assert attempts_seen[0] == (1, "boom")
    assert attempts_seen[2] == (3, "boom")


async def test_backoff_timing():
    """Verify exponential backoff: attempt 1 immediate, attempt 2 waits backoff_ms, attempt 3 waits 2*backoff_ms."""
    timestamps: list[float] = []

    async def fn():
        timestamps.append(time.monotonic())
        if len(timestamps) < 3:
            raise RuntimeError("fail")
        return "ok"

    backoff_ms = 200
    await with_retry(fn, RetryConfig(max_attempts=3, backoff_ms=backoff_ms))

    assert len(timestamps) == 3
    # Gap between attempt 1 and 2 should be ~backoff_ms (200ms)
    gap1 = (timestamps[1] - timestamps[0]) * 1000
    assert gap1 >= backoff_ms * 0.8, f"First gap {gap1}ms too short"

    # Gap between attempt 2 and 3 should be ~2*backoff_ms (400ms)
    gap2 = (timestamps[2] - timestamps[1]) * 1000
    assert gap2 >= backoff_ms * 2 * 0.8, f"Second gap {gap2}ms too short"
