"""Tests for utility helpers."""

from __future__ import annotations

import threading

import pytest
from custom_components.pawcontrol.utils import retry_on_exception


@pytest.mark.asyncio
async def test_retry_on_exception_async_success() -> None:
    """Async callables should be retried and eventually succeed."""

    call_count = 0

    @retry_on_exception(max_retries=2, delay=0)
    async def flaky() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("temporary")
        return "ok"

    result = await flaky()

    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_on_exception_sync_runs_in_thread() -> None:
    """Sync callables should run in a worker thread and support retries."""

    call_count = 0
    call_threads: set[int] = set()
    main_thread_id = threading.get_ident()

    @retry_on_exception(max_retries=1, delay=0)
    def flaky_sync() -> str:
        nonlocal call_count
        call_count += 1
        call_threads.add(threading.get_ident())
        if call_count == 1:
            raise RuntimeError("boom")
        return "done"

    result = await flaky_sync()

    assert result == "done"
    assert call_count == 2
    assert main_thread_id not in call_threads


@pytest.mark.asyncio
async def test_retry_on_exception_raises_after_retries() -> None:
    """The last raised exception should bubble up when retries are exhausted."""

    @retry_on_exception(max_retries=1, delay=0)
    async def always_fail() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await always_fail()
