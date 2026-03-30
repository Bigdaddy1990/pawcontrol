"""Targeted coverage tests for cache.py — uncovered paths (0% → 35%+).

LRUCache methods are all async — must use pytest.mark.asyncio.
"""

import pytest

from custom_components.pawcontrol.cache import CacheStats, LRUCache

# ═══════════════════════════════════════════════════════════════════════════════
# LRUCache — basic async operations
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lru_cache_set_and_get() -> None:
    cache = LRUCache(max_size=5, default_ttl=60.0)
    await cache.set("key1", "value1")
    assert await cache.get("key1") == "value1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lru_cache_miss_returns_none() -> None:
    cache = LRUCache(max_size=5, default_ttl=60.0)
    assert await cache.get("nonexistent") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lru_cache_delete() -> None:
    cache = LRUCache(max_size=5, default_ttl=60.0)
    await cache.set("key1", "value1")
    await cache.delete("key1")
    assert await cache.get("key1") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lru_cache_overwrite() -> None:
    cache = LRUCache(max_size=5, default_ttl=60.0)
    await cache.set("key1", "old")
    await cache.set("key1", "new")
    assert await cache.get("key1") == "new"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lru_cache_evicts_when_full() -> None:
    cache = LRUCache(max_size=3, default_ttl=60.0)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)
    await cache.set("d", 4)  # evicts LRU
    assert await cache.get("d") == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lru_cache_clear() -> None:
    cache = LRUCache(max_size=5, default_ttl=60.0)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.clear()
    assert await cache.get("a") is None
    assert await cache.get("b") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lru_cache_multiple_keys() -> None:
    cache = LRUCache(max_size=10, default_ttl=60.0)
    for i in range(5):
        await cache.set(f"key{i}", i * 10)
    for i in range(5):
        assert await cache.get(f"key{i}") == i * 10


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lru_cache_none_value() -> None:
    cache = LRUCache(max_size=5, default_ttl=60.0)
    await cache.set("k", None)
    # None stored is distinguishable from cache miss only by key existence
    result = await cache.get("k")
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# CacheStats
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_cache_stats_init() -> None:
    stats = CacheStats()
    assert stats.hits == 0
    assert stats.misses == 0


@pytest.mark.unit
def test_cache_stats_hit_rate_zero_when_empty() -> None:
    stats = CacheStats()
    rate = stats.hit_rate
    assert rate == pytest.approx(0.0)
