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


def test_lru_cache_handles_miss_expiry_delete_and_clear() -> None:
    """LRU cache should track misses/evictions and support deletion + clear."""

    async def _run() -> None:
        lru = cache_module.LRUCache[int](max_size=2, default_ttl=30)

        assert await lru.get("missing") is None

        await lru.set("expired", 1, ttl=0)
        await asyncio.sleep(0)
        assert await lru.get("expired") is None

        await lru.set("a", 10)
        assert await lru.delete("a") is True
        assert await lru.delete("a") is False

        await lru.set("b", 20)
        await lru.clear()

        stats = lru.get_stats()
        assert stats.misses >= 2
        assert stats.evictions >= 1
        assert stats.size == 0

    asyncio.run(_run())


def test_persistent_cache_load_success_and_clear(monkeypatch) -> None:
    """Persistent cache should deserialize store payloads and clear state."""

    class _SeededStore:
        def __init__(self, _hass: object, _version: int, _key: str) -> None:
            self.saved_payloads: list[dict[str, object]] = []

        async def async_load(self) -> dict[str, object]:
            return {
                "dog": {
                    "value": {"name": "Buddy"},
                    "timestamp": 9999999999.0,
                    "ttl_seconds": 60.0,
                    "hit_count": 2,
                }
            }

        async def async_save(self, data: dict[str, object]) -> None:
            self.saved_payloads.append(data)

    async def _run() -> None:
        monkeypatch.setattr(cache_module, "Store", _SeededStore)
        persistent = cache_module.PersistentCache[dict[str, str]](object(), "paw")

        await persistent.async_load()
        assert await persistent.get("dog") == {"name": "Buddy"}
        assert await persistent.get("missing") is None

        assert await persistent.delete("dog") is True
        assert await persistent.delete("dog") is False

        await persistent.clear()
        stats = persistent.get_stats()
        assert stats.hits >= 1
        assert stats.misses >= 1
        assert stats.size == 0

        fake_store = persistent._store
        assert isinstance(fake_store, _SeededStore)
        assert fake_store.saved_payloads[-1] == {}

    asyncio.run(_run())


def test_persistent_cache_reload_short_circuit_and_expiry(monkeypatch) -> None:
    """Persistent cache should skip duplicate loads and evict expired entries."""

    class _CountingStore:
        def __init__(self, _hass: object, _version: int, _key: str) -> None:
            self.load_calls = 0

        async def async_load(self) -> dict[str, object]:
            self.load_calls += 1
            return {
                "stale": {
                    "value": {"name": "Old"},
                    "timestamp": 1.0,
                    "ttl_seconds": 1.0,
                }
            }

        async def async_save(self, _data: dict[str, object]) -> None:
            return None

    async def _run() -> None:
        monkeypatch.setattr(cache_module, "Store", _CountingStore)
        persistent = cache_module.PersistentCache[dict[str, str]](object(), "paw")

        await persistent.async_load()
        await persistent.async_load()

        fake_store = persistent._store
        assert isinstance(fake_store, _CountingStore)
        assert fake_store.load_calls == 1

        from unittest.mock import patch

        with patch("custom_components.pawcontrol.cache.time.time", return_value=10.0):
            assert await persistent.get("stale") is None

        assert await persistent.delete("missing") is False

    asyncio.run(_run())


def test_persistent_cache_delete_triggers_lazy_load(monkeypatch) -> None:
    """Delete should trigger async_load when cache has not been loaded yet."""

    class _EmptyStore:
        def __init__(self, _hass: object, _version: int, _key: str) -> None:
            self.load_calls = 0

        async def async_load(self) -> dict[str, object]:
            self.load_calls += 1
            return {}

        async def async_save(self, _data: dict[str, object]) -> None:
            return None

    async def _run() -> None:
        monkeypatch.setattr(cache_module, "Store", _EmptyStore)
        persistent = cache_module.PersistentCache[dict[str, str]](object(), "paw")

        assert await persistent.delete("missing") is False

        fake_store = persistent._store
        assert isinstance(fake_store, _EmptyStore)
        assert fake_store.load_calls == 1

    asyncio.run(_run())


def test_two_level_cache_forwards_operations_and_promotes_from_l2() -> None:
    """Two-level cache should delegate setup/get/set/delete/clear/save/stats."""

    class _FakeL1:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}
            self.deleted: list[str] = []
            self.cleared = False

        async def get(self, key: str) -> object | None:
            return self.values.get(key)

        async def set(self, key: str, value: object, ttl: float | None = None) -> None:
            self.values[key] = value

        async def delete(self, key: str) -> None:
            self.deleted.append(key)
            self.values.pop(key, None)

        async def clear(self) -> None:
            self.cleared = True
            self.values.clear()

        def get_stats(self) -> cache_module.CacheStats:
            return cache_module.CacheStats(hits=1)

    class _FakeL2:
        def __init__(self) -> None:
            self.values = {"cold": 42}
            self.deleted: list[str] = []
            self.cleared = False
            self.loaded = False
            self.saved = False

        async def async_load(self) -> None:
            self.loaded = True

        async def get(self, key: str) -> object | None:
            return self.values.get(key)

        async def set(self, key: str, value: object, ttl: float | None = None) -> None:
            self.values[key] = value

        async def delete(self, key: str) -> None:
            self.deleted.append(key)
            self.values.pop(key, None)

        async def clear(self) -> None:
            self.cleared = True
            self.values.clear()

        async def async_save(self) -> None:
            self.saved = True

        def get_stats(self) -> cache_module.CacheStats:
            return cache_module.CacheStats(misses=1)

    async def _run() -> None:
        cache = cache_module.TwoLevelCache[int](object())
        cache._l1 = _FakeL1()  # type: ignore[assignment]
        cache._l2 = _FakeL2()  # type: ignore[assignment]

        await cache.async_setup()
        assert cache._l2.loaded is True

        assert await cache.get("hot") is None
        assert await cache.get("cold") == 42
        assert cache._l1.values["cold"] == 42

        await cache.set("shared", 7, l1_ttl=5, l2_ttl=20)
        assert cache._l1.values["shared"] == 7
        assert cache._l2.values["shared"] == 7

        await cache.delete("shared")
        assert "shared" in cache._l1.deleted
        assert "shared" in cache._l2.deleted

        await cache.clear()
        assert cache._l1.cleared is True
        assert cache._l2.cleared is True

        await cache.async_save()
        assert cache._l2.saved is True

        stats = cache.get_stats()
        assert stats["l1"].hits == 1
        assert stats["l2"].misses == 1

    asyncio.run(_run())


def test_lru_cache_capacity_eviction_and_l1_hit_path() -> None:
    """LRU capacity eviction and TwoLevel L1-hit shortcut should both execute."""

    class _BypassL2:
        def __init__(self) -> None:
            self.get_calls = 0

        async def get(self, _key: str) -> object | None:
            self.get_calls += 1
            return None

    async def _run() -> None:
        lru = cache_module.LRUCache[int](max_size=1, default_ttl=30)
        await lru.set("first", 1)
        await lru.set("second", 2)

        assert await lru.get("first") is None
        assert await lru.get("second") == 2
        assert lru.get_stats().evictions == 1

        cache = cache_module.TwoLevelCache[int](object())
        cache._l1 = lru  # type: ignore[assignment]
        cache._l2 = _BypassL2()  # type: ignore[assignment]

        assert await cache.get("second") == 2
        assert cache._l2.get_calls == 0

    asyncio.run(_run())
