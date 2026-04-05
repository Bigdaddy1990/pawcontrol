"""Tests for the PawControl cache helpers."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol import cache as cache_module


class _FakeStore:
    """Minimal async storage stub for persistent cache tests."""

    def __init__(self, _hass: Any, _version: int, _name: str) -> None:
        self._data: dict[str, dict[str, Any]] | None = None
        self.saved_payloads: list[dict[str, dict[str, Any]]] = []

    async def async_load(self) -> dict[str, dict[str, Any]] | None:
        """Return persisted payload."""
        return self._data

    async def async_save(self, payload: dict[str, dict[str, Any]]) -> None:
        """Persist payload snapshot."""
        self.saved_payloads.append(payload)
        self._data = payload


class _FailingStore(_FakeStore):
    """Store stub that raises for load/save to exercise error handling."""

    async def async_load(self) -> dict[str, dict[str, Any]] | None:
        """Raise an error to simulate storage load failure."""
        raise RuntimeError("load failed")

    async def async_save(self, payload: dict[str, dict[str, Any]]) -> None:
        """Raise an error to simulate storage save failure."""
class _FailingLoadStore(_FakeStore):
    """Store stub that simulates load failures."""

    async def async_load(self) -> dict[str, dict[str, Any]] | None:
        raise RuntimeError("load failed")


class _FailingSaveStore(_FakeStore):
    """Store stub that simulates save failures."""

    async def async_save(self, payload: dict[str, dict[str, Any]]) -> None:
        raise RuntimeError("save failed")


@pytest.mark.asyncio
async def test_lru_cache_updates_existing_key_without_eviction() -> None:
    """Updating an existing key should not increment eviction stats."""
    cache = cache_module.LRUCache[str](max_size=1, default_ttl=30)

    await cache.set("dog", "Milo")
    await cache.set("dog", "Luna")

    assert await cache.get("dog") == "Luna"
    stats = cache.get_stats()
    assert stats.evictions == 0
    assert stats.hits == 1


@pytest.mark.asyncio
async def test_lru_cache_expires_entries_and_counts_eviction() -> None:
    """Expired entries should be removed and counted as misses/evictions."""
    cache = cache_module.LRUCache[str](max_size=2, default_ttl=30)

    await cache.set("session", "active", ttl=0.01)
    await asyncio_sleep(0.02)

    assert await cache.get("session") is None
    stats = cache.get_stats()
    assert stats.misses == 1
    assert stats.evictions == 1


@pytest.mark.asyncio
async def test_lru_cache_evicts_oldest_entry_when_capacity_reached() -> None:
    """A full LRU cache should evict the oldest key before inserting a new one."""
    cache = cache_module.LRUCache[str](max_size=1, default_ttl=30)

    await cache.set("older", "Milo")
    await cache.set("newer", "Luna")

    assert await cache.get("older") is None
    assert await cache.get("newer") == "Luna"
    assert cache.get_stats().evictions == 1


@pytest.mark.asyncio
async def test_persistent_cache_saves_every_tenth_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L2 auto-save should trigger only on actual write milestones."""
    monkeypatch.setattr(cache_module, "Store", _FakeStore)
    persistent = cache_module.PersistentCache[str](hass=object(), name="paw")

    persistent.async_save = AsyncMock()  # type: ignore[method-assign]
    for index in range(9):
        await persistent.set(f"dog-{index}", "ok")

    persistent.async_save.assert_not_called()

    await persistent.set("dog-9", "ok")
    persistent.async_save.assert_awaited_once()


@pytest.mark.asyncio
async def test_two_level_cache_delete_removes_l1_and_l2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleting a key should prevent L2 re-promotion into L1."""
    monkeypatch.setattr(cache_module, "Store", _FakeStore)
    cache = cache_module.TwoLevelCache[str](hass=object(), name="paw")

    await cache.set("door", "open")
    await cache.delete("door")

    assert await cache.get("door") is None


@pytest.mark.asyncio
async def test_cached_decorator_preserves_metadata_and_memoizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decorator should keep wrapped metadata and avoid repeated work."""
    monkeypatch.setattr(cache_module, "Store", _FakeStore)
    cache = cache_module.TwoLevelCache[int](hass=object(), name="paw")

    calls: list[tuple[int, int]] = []

    @cache_module.cached(cache, "calc", ttl=5)
    async def add_dog_years(age: int, *, bonus: int = 0) -> int:
        """Add dog years."""
        calls.append((age, bonus))
        return age + bonus

    first = await add_dog_years(5, bonus=2)
    second = await add_dog_years(5, bonus=2)

    assert first == 7
    assert second == 7
    assert calls == [(5, 2)]
    assert add_dog_years.__name__ == "add_dog_years"
    assert add_dog_years.__doc__ == "Add dog years."


async def asyncio_sleep(seconds: float) -> None:
    """Helper to keep tests explicit about async scheduling."""
    import asyncio

    await asyncio.sleep(seconds)


@pytest.mark.parametrize(
    ("hits", "misses", "expected"),
    [(0, 0, 0.0), (2, 1, 0.667)],
)
def test_cache_stats_hit_rate_rounding(hits: int, misses: int, expected: float) -> None:
    """Stats should calculate and round hit rates consistently."""
    stats = cache_module.CacheStats(hits=hits, misses=misses, max_size=10)

    assert stats.to_dict()["hit_rate"] == expected


@pytest.mark.asyncio
async def test_persistent_cache_load_get_and_save_filters_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent cache should load entries, count hits, and skip expired saves."""
    monkeypatch.setattr(cache_module, "Store", _FakeStore)
    persistent = cache_module.PersistentCache[str](hass=object(), name="paw")
    fake_store = persistent._store
    assert isinstance(fake_store, _FakeStore)
    now = time.time()
    fake_store._data = {
        "fresh": {"value": "ok", "timestamp": now, "ttl_seconds": 60.0},
        "expired": {"value": "old", "timestamp": now - 120, "ttl_seconds": 1.0},
    }

    assert await persistent.get("fresh") == "ok"
    assert await persistent.get("missing") is None

    await persistent.async_save()

    assert fake_store.saved_payloads[-1] == {
        "fresh": {
            "value": "ok",
            "timestamp": fake_store.saved_payloads[-1]["fresh"]["timestamp"],
            "ttl_seconds": 60.0,
            "hit_count": 1,
        }
    }


@pytest.mark.asyncio
async def test_persistent_cache_removes_expired_entry_on_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expired entries should be evicted from L2 when read."""
    monkeypatch.setattr(cache_module, "Store", _FakeStore)
    persistent = cache_module.PersistentCache[str](hass=object(), name="paw")
    persistent._cache["expired"] = cache_module.CacheEntry(
        value="old",
        timestamp=time.time() - 120.0,
        ttl_seconds=1.0,
    )
    persistent._loaded = True

    assert await persistent.get("expired") is None
    assert "expired" not in persistent._cache
    assert persistent.get_stats().misses == 1


@pytest.mark.asyncio
async def test_persistent_cache_handles_load_and_save_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent cache should swallow storage errors and mark itself loaded."""
    monkeypatch.setattr(cache_module, "Store", _FailingStore)
    persistent = cache_module.PersistentCache[str](hass=object(), name="paw")

    await persistent.async_load()
    await persistent.async_load()
    await persistent.async_save()

    assert persistent._loaded is True
    assert persistent._cache == {}


@pytest.mark.asyncio
async def test_two_level_cache_setup_clear_and_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two-level helper should expose setup/save/clear and stats pathways."""
    monkeypatch.setattr(cache_module, "Store", _FakeStore)
    cache = cache_module.TwoLevelCache[str](hass=object(), name="paw")

    await cache.async_setup()
    await cache.set("dog", "Nala")
    await cache.async_save()
    await cache.clear()

    assert await cache.get("dog") is None
    stats = cache.get_stats()
    assert set(stats) == {"l1", "l2"}
    assert stats["l1"].size == 0


@pytest.mark.asyncio
async def test_two_level_cache_promotes_l2_hit_into_l1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reads should promote values from L2 into L1 when only L2 contains the key."""
    monkeypatch.setattr(cache_module, "Store", _FakeStore)
    cache = cache_module.TwoLevelCache[str](hass=object(), name="paw")
    await cache._l2.set("dog", "Nova")

    assert await cache.get("dog") == "Nova"
    assert await cache._l1.get("dog") == "Nova"


@pytest.mark.asyncio
async def test_delete_returns_false_for_unknown_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete helpers should report when keys are absent."""
    monkeypatch.setattr(cache_module, "Store", _FakeStore)
    l1 = cache_module.LRUCache[str]()
    l2 = cache_module.PersistentCache[str](hass=object(), name="paw")

    assert await l1.delete("unknown") is False
    assert await l2.delete("unknown") is False


def test_cache_entry_ttl_remaining_is_never_negative() -> None:
    """Remaining TTL should floor at zero for expired entries."""
    entry = cache_module.CacheEntry(
        value="stale",
        timestamp=time.time() - 10.0,
        ttl_seconds=1.0,
    )

    assert entry.ttl_remaining == 0.0
@pytest.mark.asyncio
async def test_persistent_cache_load_failure_marks_cache_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load failures should not keep retrying forever on every access."""
    monkeypatch.setattr(cache_module, "Store", _FailingLoadStore)
    persistent = cache_module.PersistentCache[str](hass=object(), name="paw")

    assert await persistent.get("dog") is None

    assert persistent._loaded is True
    assert persistent._cache == {}
    assert persistent.get_stats().misses == 1


@pytest.mark.asyncio
async def test_persistent_cache_save_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Save failures should be logged but must not raise to callers."""
    monkeypatch.setattr(cache_module, "Store", _FailingSaveStore)
    persistent = cache_module.PersistentCache[str](hass=object(), name="paw")

    await persistent.set("dog", "Milo")
    await persistent.async_save()

    assert persistent.get_stats().size == 1
