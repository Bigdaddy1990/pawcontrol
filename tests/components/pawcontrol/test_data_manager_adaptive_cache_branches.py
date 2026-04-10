"""Additional branch coverage for ``AdaptiveCache`` metadata normalization."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pawcontrol import data_manager
from custom_components.pawcontrol.data_manager import AdaptiveCache


@pytest.mark.asyncio
async def test_given_non_datetime_created_at_when_get_then_metadata_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache get should replace invalid ``created_at`` values with ``_utcnow``."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(data_manager, "_utcnow", lambda: now)

    cache = AdaptiveCache[str](default_ttl=30)
    cache._data["dog"] = "buddy"
    cache._metadata["dog"] = {
        "created_at": "invalid",  # type: ignore[typeddict-item]
        "ttl": 30,
        "expiry": now + timedelta(seconds=30),
    }

    value, hit = await cache.get("dog")

    assert (value, hit) == ("buddy", True)
    assert cache._metadata["dog"]["created_at"] == now


@pytest.mark.asyncio
async def test_given_zero_ttl_when_get_then_entry_never_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalization should keep ``expiry`` unset when TTL is non-positive."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(data_manager, "_utcnow", lambda: now)

    cache = AdaptiveCache[int](default_ttl=10)
    cache._data["dog"] = 1
    cache._metadata["dog"] = {
        "created_at": now,
        "ttl": 0,
        "expiry": now + timedelta(seconds=1),
    }

    value, hit = await cache.get("dog")

    assert (value, hit) == (1, True)
    assert cache._metadata["dog"]["expiry"] is None


@pytest.mark.asyncio
async def test_given_expiry_before_created_at_when_get_then_expiry_recomputed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalization should recompute invalid expiry boundaries from TTL."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(data_manager, "_utcnow", lambda: now)

    cache = AdaptiveCache[str](default_ttl=5)
    cache._data["dog"] = "ok"
    cache._metadata["dog"] = {
        "created_at": now,
        "ttl": 5,
        "expiry": now,
    }

    _, hit = await cache.get("dog")

    assert hit is True
    assert cache._metadata["dog"]["expiry"] == now + timedelta(seconds=5)
