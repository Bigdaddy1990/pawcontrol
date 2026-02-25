"""Focused unit tests for cache module edge cases."""

import asyncio

from tests.helpers.homeassistant_test_stubs import install_homeassistant_stubs

install_homeassistant_stubs()

from custom_components.pawcontrol import cache as cache_module


class _FakeStore:
    """Simple async store test double."""

    def __init__(self, _hass: object, _version: int, _key: str) -> None:
        self.saved_payloads: list[dict[str, object]] = []

    async def async_load(self) -> dict[str, object]:
        return {}

    async def async_save(self, data: dict[str, object]) -> None:
        self.saved_payloads.append(data)


def test_lru_set_existing_key_updates_without_eviction() -> None:
    """Updating an existing key should not increment evictions."""

    async def _run() -> None:
        lru = cache_module.LRUCache[int](max_size=1, default_ttl=30)
        await lru.set("dog", 1)
        await lru.set("dog", 2)

        assert await lru.get("dog") == 2
        stats = lru.get_stats()
        assert stats.evictions == 0
        assert stats.size == 1

    asyncio.run(_run())


def test_persistent_cache_periodic_save_triggers_by_write_count(monkeypatch) -> None:
    """Persistent cache should save only on configured write milestones."""

    async def _run() -> None:
        monkeypatch.setattr(cache_module, "Store", _FakeStore)
        persistent = cache_module.PersistentCache[dict[str, str]](object(), "paw")

        write_interval = cache_module._L2_SAVE_EVERY_N_WRITES
        for idx in range(write_interval - 1):
            await persistent.set("dog", {"id": str(idx)})

        fake_store = persistent._store
        assert isinstance(fake_store, _FakeStore)
        assert fake_store.saved_payloads == []

        await persistent.set("dog", {"id": "milestone"})
        assert len(fake_store.saved_payloads) == 1
        assert fake_store.saved_payloads[0]["dog"]["value"] == {"id": "milestone"}

    asyncio.run(_run())


def test_cached_decorator_preserves_metadata_and_sorts_kwargs() -> None:
    """Decorator should preserve metadata and generate deterministic keys."""

    class _FakeTwoLevelCache:
        def __init__(self) -> None:
            self.storage: dict[str, object] = {}
            self.set_calls: list[tuple[str, object, float, float]] = []

        async def get(self, key: str) -> object | None:
            return self.storage.get(key)

        async def set(
            self,
            key: str,
            value: object,
            *,
            l1_ttl: float,
            l2_ttl: float,
        ) -> None:
            self.storage[key] = value
            self.set_calls.append((key, value, l1_ttl, l2_ttl))

    async def _run() -> None:
        fake_cache = _FakeTwoLevelCache()

        @cache_module.cached(fake_cache, "stats", ttl=5)
        async def compute(*, z: int, a: int) -> str:
            """Example coroutine."""
            return f"{a}-{z}"

        first = await compute(z=9, a=1)
        second = await compute(a=1, z=9)

        assert first == "1-9"
        assert second == "1-9"
        assert len(fake_cache.set_calls) == 1
        key, _, l1_ttl, l2_ttl = fake_cache.set_calls[0]
        assert key == "stats:a=1:z=9"
        assert l1_ttl == 5
        assert l2_ttl == 20
        assert compute.__name__ == "compute"
        assert compute.__doc__ == "Example coroutine."

    asyncio.run(_run())


def test_cache_entry_and_stats_helpers_cover_edge_values() -> None:
    """Cache helper dataclasses should expose stable derived values."""
    entry = cache_module.CacheEntry[str](value="ok", timestamp=10.0, ttl_seconds=5.0)

    from unittest.mock import patch

    with patch("custom_components.pawcontrol.cache.time.time", return_value=12.0):
        assert entry.age_seconds == 2.0
        assert entry.ttl_remaining == 3.0
        assert entry.is_expired is False

    with patch("custom_components.pawcontrol.cache.time.time", return_value=20.0):
        assert entry.ttl_remaining == 0.0
        assert entry.is_expired is True

    stats = cache_module.CacheStats(hits=0, misses=0, evictions=1, size=2, max_size=3)
    assert stats.hit_rate == 0.0
    assert stats.to_dict()["hit_rate"] == 0.0


def test_persistent_cache_error_paths_and_delete_flow(monkeypatch) -> None:
    """Persistent cache should handle store failures and delete safely."""

    class _FailingStore:
        def __init__(self, _hass: object, _version: int, _key: str) -> None:
            self.saved_payloads: list[dict[str, object]] = []

        async def async_load(self) -> dict[str, object]:
            raise RuntimeError("load failed")

        async def async_save(self, data: dict[str, object]) -> None:
            self.saved_payloads.append(data)
            raise RuntimeError("save failed")

    async def _run() -> None:
        monkeypatch.setattr(cache_module, "Store", _FailingStore)
        persistent = cache_module.PersistentCache[dict[str, str]](object(), "paw")

        assert await persistent.get("missing") is None
        assert await persistent.delete("missing") is False

        await persistent.set("dog", {"id": "1"})
        assert await persistent.delete("dog") is True

        await persistent.async_save()

    asyncio.run(_run())
