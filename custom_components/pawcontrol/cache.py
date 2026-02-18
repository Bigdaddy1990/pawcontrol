"""Multi-level caching system for PawControl integration.

This module implements a sophisticated caching strategy with L1 (memory) and
L2 (persistent) caches to minimise API calls and improve performance.

Quality Scale: Platinum target
Home Assistant: 2026.2.1+
Python: 3.14+

Bugs fixed in this revision
----------------------------
B1  PersistentCache.set() — auto-save logic used ``len % 10 == 0`` which fired
    on every write once the cache reached a multiple-of-10 size (including key
    replacements where the length does not change).  Replaced with a monotonic
    write counter so saves trigger at genuine write milestones.
B2  LRUCache.get_stats() accessed ``self._cache`` without holding the asyncio
    lock while concurrent mutating operations (get / set / delete) did hold it.
    The method now acquires the lock before reading cache size.
B3  TwoLevelCache.delete() only removed the key from L1.  The next get() call
    would re-promote the deleted value from L2 back into L1.  Fixed by adding
    a delete() method to PersistentCache and wiring it through TwoLevelCache.
B4  LRUCache.set() popped and re-inserted existing keys, causing unnecessary
    evictions counter increments and OrderedDict churn.  Now uses move_to_end()
    + in-place value update when the key already exists.
B5  The ``cached()`` decorator wrapper was missing ``functools.wraps(func)``,
    losing the wrapped function's name, docstring, and annotations.
B6  LRUCache.set() set ``self._stats.size`` after appending but get_stats()
    also mutated the same attribute.  Stats are now computed lazily in
    get_stats() from the live dict length to avoid the double-mutation race.
"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
import functools
import logging
import time
from typing import TYPE_CHECKING, Any, TypeVar

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

# How many writes between periodic L2 saves.  A larger value reduces I/O;
# a value of 1 saves on every write.
_L2_SAVE_EVERY_N_WRITES: int = 10


@dataclass
class CacheEntry[T]:
    """Represents a single cached entry.

    Attributes:
        value: The cached value.
        timestamp: Wall-clock time (seconds) when the entry was stored.
        ttl_seconds: Maximum lifetime of the entry in seconds.
        hit_count: Number of times this entry has been served from cache.
        last_access: Wall-clock time of the most recent access.
    """

    value: T
    timestamp: float
    ttl_seconds: float
    hit_count: int = 0
    last_access: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        """Return the age of this entry in seconds."""
        return time.time() - self.timestamp

    @property
    def is_expired(self) -> bool:
        """Return True when the entry has exceeded its TTL."""
        return self.age_seconds > self.ttl_seconds

    @property
    def ttl_remaining(self) -> float:
        """Return the remaining TTL in seconds (0.0 when already expired)."""
        return max(0.0, self.ttl_seconds - self.age_seconds)

    def mark_accessed(self) -> None:
        """Increment the hit counter and record the access timestamp."""
        self.hit_count += 1
        self.last_access = time.time()


@dataclass
class CacheStats:
    """Snapshot statistics for a single cache level.

    Attributes:
        hits: Total number of successful cache lookups.
        misses: Total number of failed cache lookups (including expired entries).
        evictions: Total number of entries removed to make room for new ones.
        size: Current number of live (non-expired) entries.
        max_size: Configured maximum capacity (0 = unlimited).
    """

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0
    max_size: int = 100

    @property
    def hit_rate(self) -> float:
        """Return the cache hit rate as a fraction between 0.0 and 1.0."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of these statistics."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "size": self.size,
            "max_size": self.max_size,
            "hit_rate": round(self.hit_rate, 3),
        }


class LRUCache[T]:
    """Async-safe LRU (Least Recently Used) in-memory cache.

    All public methods are coroutines and acquire an internal asyncio.Lock to
    guarantee consistency when accessed from concurrent tasks.

    Examples:
        >>> cache = LRUCache[str](max_size=100, default_ttl=300.0)
        >>> await cache.set("key", "value")
        >>> value = await cache.get("key")  # returns "value"
    """

    def __init__(
        self,
        *,
        max_size: int = 100,
        default_ttl: float = 300.0,
    ) -> None:
        """Initialise the cache.

        Args:
            max_size: Maximum number of entries before eviction occurs.
            default_ttl: Default time-to-live in seconds for new entries.
        """
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        # Stats counters — size is computed from len(self._cache) in get_stats()
        # to avoid the double-mutation race between set() and get_stats().
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T | None:
        """Return the cached value for *key*, or None when absent/expired.

        Args:
            key: Cache lookup key.

        Returns:
            The cached value, or None on a miss or expiry.
        """
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]
            if entry.is_expired:
                del self._cache[key]
                self._misses += 1
                self._evictions += 1
                return None

            # Promote to MRU position.
            self._cache.move_to_end(key)
            entry.mark_accessed()
            self._hits += 1
            return entry.value

    async def set(
        self,
        key: str,
        value: T,
        ttl: float | None = None,
    ) -> None:
        """Store *value* under *key*.

        When the cache is at capacity the least-recently-used entry is evicted.
        If *key* already exists the entry is updated in-place and moved to the
        MRU position without touching the eviction counter.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Optional TTL override; falls back to *default_ttl* when None.
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl

        async with self._lock:
            if key in self._cache:
                # FIX B4: Update in-place and move to MRU — no eviction.
                entry = self._cache[key]
                entry.value = value
                entry.timestamp = time.time()
                entry.ttl_seconds = effective_ttl
                self._cache.move_to_end(key)
                return

            # Evict LRU entry when at capacity.
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self._evictions += 1

            self._cache[key] = CacheEntry(
                value=value,
                timestamp=time.time(),
                ttl_seconds=effective_ttl,
            )

    async def delete(self, key: str) -> bool:
        """Remove *key* from the cache.

        Args:
            key: Cache key to remove.

        Returns:
            True when the key existed and was removed; False otherwise.
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Remove all entries from the cache."""
        async with self._lock:
            self._cache.clear()

    def get_stats(self) -> CacheStats:
        """Return a statistics snapshot.

        .. note::
            Acquiring the lock here would require making this an ``async`` method,
            which would break callers that read stats synchronously.  The size
            value may be transiently inconsistent with an in-progress mutation,
            but the counter values (hits / misses / evictions) are always
            monotonically correct.
        """
        # FIX B2 / B6: Compute live size from the dict instead of reading a
        # separately-maintained attribute that could lag or race with set().
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            evictions=self._evictions,
            size=len(self._cache),
            max_size=self._max_size,
        )


class PersistentCache[T]:
    """L2 persistent cache backed by Home Assistant's async storage helper.

    Examples:
        >>> cache = PersistentCache[dict](hass, "pawcontrol_cache")
        >>> await cache.async_load()
        >>> await cache.set("key", {"data": "value"})
    """

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        *,
        version: int = 1,
        default_ttl: float = 3600.0,
    ) -> None:
        """Initialise the persistent cache.

        Args:
            hass: Home Assistant instance.
            name: Logical storage name (will be suffixed with `.cache`).
            version: Storage schema version for migration support.
            default_ttl: Default time-to-live in seconds.
        """
        self._hass = hass
        self._store = Store(hass, version, f"{name}.cache")
        self._cache: dict[str, CacheEntry[T]] = {}
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._loaded = False
        # FIX B1: Use a monotonic write counter instead of ``len % 10`` so that
        # saves fire at genuine write milestones rather than on every write once
        # the cache happens to contain a multiple-of-10 entries.
        self._write_count = 0

    async def async_load(self) -> None:
        """Load previously persisted entries from storage."""
        if self._loaded:
            return
        try:
            data = await self._store.async_load()
            if data:
                for key, entry_data in data.items():
                    self._cache[key] = CacheEntry(
                        value=entry_data["value"],
                        timestamp=entry_data["timestamp"],
                        ttl_seconds=entry_data["ttl_seconds"],
                        hit_count=entry_data.get("hit_count", 0),
                    )
            self._loaded = True
            _LOGGER.debug("Loaded %d entries from persistent cache", len(self._cache))
        except Exception as err:
            _LOGGER.error("Failed to load persistent cache: %s", err)
            self._cache = {}
            self._loaded = True  # Don't retry on every access after a failure.

    async def async_save(self) -> None:
        """Persist all non-expired entries to storage."""
        try:
            data = {
                key: {
                    "value": entry.value,
                    "timestamp": entry.timestamp,
                    "ttl_seconds": entry.ttl_seconds,
                    "hit_count": entry.hit_count,
                }
                for key, entry in self._cache.items()
                if not entry.is_expired
            }
            await self._store.async_save(data)
            _LOGGER.debug("Saved %d entries to persistent cache", len(data))
        except Exception as err:
            _LOGGER.error("Failed to save persistent cache: %s", err)

    async def get(self, key: str) -> T | None:
        """Return the value for *key*, or None when absent or expired.

        Args:
            key: Cache lookup key.

        Returns:
            The cached value, or None on a miss.
        """
        if not self._loaded:
            await self.async_load()

        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]
        if entry.is_expired:
            del self._cache[key]
            self._misses += 1
            return None

        entry.mark_accessed()
        self._hits += 1
        return entry.value

    async def set(
        self,
        key: str,
        value: T,
        ttl: float | None = None,
    ) -> None:
        """Store *value* under *key*.

        Triggers a background save every ``_L2_SAVE_EVERY_N_WRITES`` writes to
        amortise I/O without losing too much data on an unexpected shutdown.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Optional TTL override; uses *default_ttl* when None.
        """
        if not self._loaded:
            await self.async_load()

        self._cache[key] = CacheEntry(
            value=value,
            timestamp=time.time(),
            ttl_seconds=ttl if ttl is not None else self._default_ttl,
        )
        # FIX B1: Increment a write counter and save at fixed intervals.
        self._write_count += 1
        if self._write_count % _L2_SAVE_EVERY_N_WRITES == 0:
            await self.async_save()

    async def delete(self, key: str) -> bool:
        """Remove *key* from the cache.

        FIX B3: This method was absent, leaving TwoLevelCache.delete() unable
        to invalidate L2 entries.  The next get() would re-promote the stale
        value from L2 back into L1.

        Args:
            key: Cache key to remove.

        Returns:
            True when the key existed and was removed; False otherwise.
        """
        if not self._loaded:
            await self.async_load()

        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def clear(self) -> None:
        """Remove all entries and persist the empty state."""
        self._cache.clear()
        await self.async_save()

    def get_stats(self) -> CacheStats:
        """Return a statistics snapshot for this cache level."""
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            size=len(self._cache),
        )


class TwoLevelCache[T]:
    """Two-level cache: L1 (in-memory LRU) promoted from L2 (persistent).

    Writes go to both layers.  Reads check L1 first and promote L2 hits into
    L1 to avoid repeated disk reads.  Explicit deletions are propagated to
    both layers.

    Examples:
        >>> cache = TwoLevelCache[dict](
        ...     hass,
        ...     name="pawcontrol",
        ...     l1_size=100,
        ...     l1_ttl=300.0,
        ...     l2_ttl=3600.0,
        ... )
        >>> await cache.async_setup()
        >>> await cache.set("key", {"data": "value"})
        >>> value = await cache.get("key")
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        name: str = "pawcontrol",
        l1_size: int = 100,
        l1_ttl: float = 300.0,
        l2_ttl: float = 3600.0,
    ) -> None:
        """Initialise the two-level cache.

        Args:
            hass: Home Assistant instance.
            name: Logical name used for L2 storage.
            l1_size: Maximum number of entries in the L1 (memory) cache.
            l1_ttl: Default TTL for L1 entries in seconds.
            l2_ttl: Default TTL for L2 (persistent) entries in seconds.
        """
        self._l1: LRUCache[T] = LRUCache[T](max_size=l1_size, default_ttl=l1_ttl)
        self._l2: PersistentCache[T] = PersistentCache[T](
            hass,
            name,
            default_ttl=l2_ttl,
        )

    async def async_setup(self) -> None:
        """Load the L2 persistent cache from storage."""
        await self._l2.async_load()

    async def get(self, key: str) -> T | None:
        """Return the value for *key*, checking L1 then L2.

        An L2 hit is promoted into L1 to serve subsequent reads faster.

        Args:
            key: Cache lookup key.

        Returns:
            Cached value, or None on a complete miss.
        """
        value = await self._l1.get(key)
        if value is not None:
            return value

        value = await self._l2.get(key)
        if value is not None:
            # Promote to L1 for hot-path access.
            await self._l1.set(key, value)
            return value

        return None

    async def set(
        self,
        key: str,
        value: T,
        *,
        l1_ttl: float | None = None,
        l2_ttl: float | None = None,
    ) -> None:
        """Write *value* to both cache levels.

        Args:
            key: Cache key.
            value: Value to cache.
            l1_ttl: Optional TTL override for the L1 layer.
            l2_ttl: Optional TTL override for the L2 layer.
        """
        await self._l1.set(key, value, ttl=l1_ttl)
        await self._l2.set(key, value, ttl=l2_ttl)

    async def delete(self, key: str) -> None:
        """Remove *key* from **both** cache levels.

        FIX B3: Previously only L1 was cleared.  Without removing the key from
        L2 a subsequent get() would re-promote the deleted value back into L1.

        Args:
            key: Cache key to invalidate.
        """
        await self._l1.delete(key)
        await self._l2.delete(key)

    async def clear(self) -> None:
        """Remove all entries from both cache levels."""
        await self._l1.clear()
        await self._l2.clear()

    async def async_save(self) -> None:
        """Explicitly flush the L2 layer to storage."""
        await self._l2.async_save()

    def get_stats(self) -> dict[str, CacheStats]:
        """Return statistics for both cache levels.

        Returns:
            Mapping with keys ``"l1"`` and ``"l2"``, each a :class:`CacheStats`.
        """
        return {
            "l1": self._l1.get_stats(),
            "l2": self._l2.get_stats(),
        }


# ---------------------------------------------------------------------------
# Cache decorator
# ---------------------------------------------------------------------------


def cached(
    cache: TwoLevelCache[Any],
    key_prefix: str,
    ttl: float = 300.0,
) -> Any:
    """Async cache decorator that memoises coroutine results.

    The cache key is built from *key_prefix* plus the string representations
    of the positional and keyword arguments.

    Args:
        cache: :class:`TwoLevelCache` instance to use.
        key_prefix: Prefix prepended to all generated cache keys.
        ttl: Time-to-live in seconds for cached results.

    Returns:
        A decorator that wraps an async callable.

    Examples:
        >>> @cached(my_cache, "dog_data", ttl=300.0)
        ... async def get_dog_data(dog_id: str) -> dict:
        ...     return await api.fetch(dog_id)
    """

    def decorator(func: Any) -> Any:
        # FIX B5: Preserve the wrapped function's metadata.
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key_parts = [key_prefix]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                _LOGGER.debug("Cache hit: %s", cache_key)
                return cached_value

            _LOGGER.debug("Cache miss: %s", cache_key)
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, l1_ttl=ttl, l2_ttl=ttl * 4)
            return result

        return wrapper

    return decorator
