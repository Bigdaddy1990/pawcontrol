"""Tests for utility helpers."""

from __future__ import annotations

import re
import threading

import pytest
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.utils import (
    chunk_list,
    create_device_info,
    retry_on_exception,
    safe_divide,
    safe_get_nested,
    safe_set_nested,
    sanitize_dog_id,
)


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


def test_create_device_info_normalises_identifiers() -> None:
    """Device info helper should clean and deduplicate identifier tuples."""

    info = create_device_info(
        "Dog One",
        "Dog One",
        manufacturer="TestCo",
        model="Tracker",
        microchip_id=" aa-123 ",
        extra_identifiers=[
            (" pawcontrol ", "  tracker-1  "),
            ("pawcontrol", "tracker-1"),  # duplicate once trimmed
            ("other", None),  # dropped because value missing
            ["custom", " device "],  # lists should be accepted and trimmed
            ("ignored", ""),  # empty value filtered out
        ],
    )

    assert info["manufacturer"] == "TestCo"
    assert info["model"] == "Tracker"
    assert info["name"] == "Dog One"

    assert (DOMAIN, "dog_one") in info["identifiers"]
    assert ("pawcontrol", "tracker-1") in info["identifiers"]
    assert ("custom", "device") in info["identifiers"]
    assert ("microchip", "AA123") in info["identifiers"]


def test_sanitize_dog_id_generates_stable_identifier() -> None:
    """Sanitising removes illegal characters and ensures leading letters."""

    assert sanitize_dog_id("Fido-01") == "fido_01"

    hashed = sanitize_dog_id("!!!")
    assert hashed.startswith("dog_")
    assert re.fullmatch(r"dog_[0-9a-f]{8}", hashed)


def test_safe_nested_helpers_round_trip() -> None:
    """Setting and getting nested values should be resilient to missing keys."""

    data: dict[str, object] = {}
    result = safe_set_nested(data, "dog.profile.weight", 12.5)

    assert result is data
    assert safe_get_nested(data, "dog.profile.weight") == 12.5
    assert safe_get_nested(data, "dog.profile.unknown", default="n/a") == "n/a"


def test_chunk_list_and_safe_divide_utilities() -> None:
    """Chunking and safe division helpers should handle edge cases."""

    assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

    with pytest.raises(ValueError):
        chunk_list([1, 2], 0)

    assert safe_divide(10, 2) == 5
    assert safe_divide(10, 0, default=-1) == -1
    assert safe_divide("a", 3, default=7) == 7
