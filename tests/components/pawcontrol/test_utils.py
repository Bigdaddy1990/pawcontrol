"""Tests for utility helpers."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Awaitable, Callable, Iterable
from types import MappingProxyType
from typing import cast

import pytest
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.types import JSONMutableMapping
from custom_components.pawcontrol.utils import (
    chunk_list,
    create_device_info,
    flatten_dict,
    merge_configurations,
    retry_on_exception,
    safe_divide,
    safe_get_nested,
    safe_set_nested,
    sanitize_dog_id,
    unflatten_dict,
)


@pytest.mark.asyncio
async def test_retry_on_exception_async_success() -> None:
    """Async callables should be retried and eventually succeed."""

    call_count = 0

    async def flaky_inner() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("temporary")
        return "ok"

    flaky: Callable[[], Awaitable[str]] = retry_on_exception(max_retries=2, delay=0)(
        flaky_inner
    )

    result: str = await flaky()

    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_on_exception_sync_runs_in_thread() -> None:
    """Sync callables should run in a worker thread and support retries."""

    call_count = 0
    call_threads: set[int] = set()
    main_thread_id = threading.get_ident()

    def flaky_sync_inner() -> str:
        nonlocal call_count
        call_count += 1
        call_threads.add(threading.get_ident())
        if call_count == 1:
            raise RuntimeError("boom")
        return "done"

    flaky_sync: Callable[[], Awaitable[str]] = retry_on_exception(
        max_retries=1, delay=0
    )(flaky_sync_inner)

    result: str = await flaky_sync()

    assert result == "done"
    assert call_count == 2
    assert main_thread_id not in call_threads


@pytest.mark.asyncio
async def test_retry_on_exception_raises_after_retries() -> None:
    """The last raised exception should bubble up when retries are exhausted."""

    async def always_fail_inner() -> None:
        raise ValueError("nope")

    always_fail: Callable[[], Awaitable[None]] = retry_on_exception(
        max_retries=1, delay=0
    )(always_fail_inner)

    with pytest.raises(ValueError):
        await always_fail()


def test_create_device_info_normalises_identifiers() -> None:
    """Device info helper should clean and deduplicate identifier tuples."""

    extra_identifiers: list[object] = [
        (" pawcontrol ", "  tracker-1  "),
        ("pawcontrol", "tracker-1"),  # duplicate once trimmed
        ("other", None),  # dropped because value missing
        ["custom", " device "],  # lists should be accepted and trimmed
        ("ignored", ""),  # empty value filtered out
    ]

    info = create_device_info(
        "Dog One",
        "Dog One",
        manufacturer="TestCo",
        model="Tracker",
        microchip_id=" aa-123 ",
        extra_identifiers=cast(Iterable[tuple[str, str]], extra_identifiers),
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

    data: JSONMutableMapping = {}
    result: JSONMutableMapping = safe_set_nested(data, "dog.profile.weight", 12.5)

    assert result is data
    assert safe_get_nested(data, "dog.profile.weight") == 12.5
    assert safe_get_nested(data, "dog.profile.unknown", default="n/a") == "n/a"


def test_flatten_and_unflatten_round_trip() -> None:
    """Flattened JSON mappings should expand back to their original structure."""

    data: JSONMutableMapping = {
        "dog": {"profile": {"weight": 12.5, "tags": ["active", "friendly"]}}
    }

    flattened = flatten_dict(data)

    assert flattened == {
        "dog.profile.weight": 12.5,
        "dog.profile.tags": ["active", "friendly"],
    }

    rebuilt = unflatten_dict(flattened)
    assert rebuilt == data


def test_chunk_list_and_safe_divide_utilities() -> None:
    """Chunking and safe division helpers should handle edge cases."""

    assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

    with pytest.raises(ValueError):
        chunk_list([1, 2], 0)

    assert safe_divide(10, 2) == 5
    assert safe_divide(10, 0, default=-1) == -1
    assert safe_divide(cast(float, "a"), 3, default=7) == 7


def test_merge_configurations_nested_mappings_and_protected_keys(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nested mappings merge recursively while respecting protected keys."""

    base_config: JSONMutableMapping = {
        "dog": {
            "profile": {"name": "Fido", "weight": 12.5},
            "modules": {"walk": {"enabled": True}},
        },
        "schedule": {"thresholds": {"min": 1}},
        "protected": {"secret": True},
    }

    user_config = MappingProxyType(
        {
            "dog": {
                "profile": {"weight": 10.0, "tags": ["energetic"]},
                "modules": {"walk": {"enabled": False}, "health": {"enabled": True}},
            },
            "schedule": {"thresholds": {"max": 5}},
            "protected": {"secret": False},
            "new_field": {"child": 1},
        }
    )

    caplog.set_level(logging.WARNING)

    merged = merge_configurations(base_config, user_config, {"protected"})

    assert merged["dog"]["profile"] == {
        "name": "Fido",
        "weight": 10.0,
        "tags": ["energetic"],
    }
    assert merged["dog"]["modules"] == {
        "walk": {"enabled": False},
        "health": {"enabled": True},
    }
    assert merged["schedule"]["thresholds"] == {"min": 1, "max": 5}
    assert merged["new_field"] == {"child": 1}
    assert merged["protected"] == {"secret": True}
    assert "Ignoring protected configuration key" in caplog.text
