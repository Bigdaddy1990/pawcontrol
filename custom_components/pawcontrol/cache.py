"""Multi-level caching system for PawControl integration.

This module implements a sophisticated caching strategy with L1 (memory) and
L2 (persistent) caches to minimize API calls and improve performance.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
import logging
import time
from typing import TYPE_CHECKING, Any, TypeVar

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

if TYPE_CHECKING:
  pass  # noqa: E111

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry[T]:
  """Represents a cached entry.

  Attributes:
      value: Cached value
      timestamp: When entry was cached
      ttl_seconds: Time to live in seconds
      hit_count: Number of cache hits
      last_access: Last access timestamp
  """  # noqa: E111

  value: T  # noqa: E111
  timestamp: float  # noqa: E111
  ttl_seconds: float  # noqa: E111
  hit_count: int = 0  # noqa: E111
  last_access: float = field(default_factory=time.time)  # noqa: E111

  @property  # noqa: E111
  def age_seconds(self) -> float:  # noqa: E111
    """Return age of entry in seconds."""
    return time.time() - self.timestamp

  @property  # noqa: E111
  def is_expired(self) -> bool:  # noqa: E111
    """Return True if entry has expired."""
    return self.age_seconds > self.ttl_seconds

  @property  # noqa: E111
  def ttl_remaining(self) -> float:  # noqa: E111
    """Return remaining TTL in seconds."""
    return max(0.0, self.ttl_seconds - self.age_seconds)

  def mark_accessed(self) -> None:  # noqa: E111
    """Mark entry as accessed."""
    self.hit_count += 1
    self.last_access = time.time()


@dataclass
class CacheStats:
  """Cache statistics.

  Attributes:
      hits: Number of cache hits
      misses: Number of cache misses
      evictions: Number of evictions
      size: Current cache size
      max_size: Maximum cache size
  """  # noqa: E111

  hits: int = 0  # noqa: E111
  misses: int = 0  # noqa: E111
  evictions: int = 0  # noqa: E111
  size: int = 0  # noqa: E111
  max_size: int = 100  # noqa: E111

  @property  # noqa: E111
  def hit_rate(self) -> float:  # noqa: E111
    """Return cache hit rate (0.0-1.0)."""
    total = self.hits + self.misses
    return self.hits / total if total > 0 else 0.0

  def to_dict(self) -> dict[str, Any]:  # noqa: E111
    """Convert to dictionary."""
    return {
      "hits": self.hits,
      "misses": self.misses,
      "evictions": self.evictions,
      "size": self.size,
      "max_size": self.max_size,
      "hit_rate": round(self.hit_rate, 3),
    }


class LRUCache[T]:
  """LRU (Least Recently Used) cache implementation.

  Examples:
      >>> cache = LRUCache[str](max_size=100, default_ttl=300.0)
      >>> cache.set("key", "value")
      >>> value = cache.get("key")
  """  # noqa: E111

  def __init__(  # noqa: E111
    self,
    *,
    max_size: int = 100,
    default_ttl: float = 300.0,
  ) -> None:
    """Initialize LRU cache.

    Args:
        max_size: Maximum number of entries
        default_ttl: Default time-to-live in seconds
    """
    self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
    self._max_size = max_size
    self._default_ttl = default_ttl
    self._stats = CacheStats(max_size=max_size)
    self._lock = asyncio.Lock()

  async def get(self, key: str) -> T | None:  # noqa: E111
    """Get value from cache.

    Args:
        key: Cache key

    Returns:
        Cached value or None if not found/expired
    """
    async with self._lock:
      if key not in self._cache:  # noqa: E111
        self._stats.misses += 1
        return None

      entry = self._cache[key]  # noqa: E111

      # Check expiration  # noqa: E114
      if entry.is_expired:  # noqa: E111
        self._cache.pop(key)
        self._stats.misses += 1
        self._stats.evictions += 1
        return None

      # Move to end (most recently used)  # noqa: E114
      self._cache.move_to_end(key)  # noqa: E111
      entry.mark_accessed()  # noqa: E111
      self._stats.hits += 1  # noqa: E111

      return entry.value  # noqa: E111

  async def set(  # noqa: E111
    self,
    key: str,
    value: T,
    ttl: float | None = None,
  ) -> None:
    """Set value in cache.

    Args:
        key: Cache key
        value: Value to cache
        ttl: Optional TTL override
    """
    async with self._lock:
      # Remove if exists  # noqa: E114
      if key in self._cache:  # noqa: E111
        self._cache.pop(key)

      # Evict oldest if at capacity  # noqa: E114
      if len(self._cache) >= self._max_size:  # noqa: E111
        oldest_key = next(iter(self._cache))
        self._cache.pop(oldest_key)
        self._stats.evictions += 1

      # Add new entry  # noqa: E114
      entry = CacheEntry(  # noqa: E111
        value=value,
        timestamp=time.time(),
        ttl_seconds=ttl or self._default_ttl,
      )
      self._cache[key] = entry  # noqa: E111
      self._stats.size = len(self._cache)  # noqa: E111

  async def delete(self, key: str) -> bool:  # noqa: E111
    """Delete entry from cache.

    Args:
        key: Cache key

    Returns:
        True if entry was deleted
    """
    async with self._lock:
      if key in self._cache:  # noqa: E111
        self._cache.pop(key)
        self._stats.size = len(self._cache)
        return True
      return False  # noqa: E111

  async def clear(self) -> None:  # noqa: E111
    """Clear all entries from cache."""
    async with self._lock:
      self._cache.clear()  # noqa: E111
      self._stats.size = 0  # noqa: E111

  def get_stats(self) -> CacheStats:  # noqa: E111
    """Return cache statistics."""
    self._stats.size = len(self._cache)
    return self._stats


class PersistentCache[T]:
  """Persistent L2 cache using Home Assistant storage.

  Examples:
      >>> cache = PersistentCache[dict](hass, "pawcontrol_cache")
      >>> await cache.async_load()
      >>> await cache.set("key", {"data": "value"})
  """  # noqa: E111

  def __init__(  # noqa: E111
    self,
    hass: HomeAssistant,
    name: str,
    *,
    version: int = 1,
    default_ttl: float = 3600.0,
  ) -> None:
    """Initialize persistent cache.

    Args:
        hass: Home Assistant instance
        name: Storage name
        version: Storage version
        default_ttl: Default TTL in seconds
    """
    self._hass = hass
    self._store = Store(hass, version, f"{name}.cache")
    self._cache: dict[str, CacheEntry[T]] = {}
    self._default_ttl = default_ttl
    self._stats = CacheStats()
    self._loaded = False

  async def async_load(self) -> None:  # noqa: E111
    """Load cache from storage."""
    if self._loaded:
      return  # noqa: E111

    try:
      data = await self._store.async_load()  # noqa: E111
      if data:  # noqa: E111
        # Reconstruct cache entries
        for key, entry_data in data.items():
          self._cache[key] = CacheEntry(  # noqa: E111
            value=entry_data["value"],
            timestamp=entry_data["timestamp"],
            ttl_seconds=entry_data["ttl_seconds"],
            hit_count=entry_data.get("hit_count", 0),
          )
      self._loaded = True  # noqa: E111
      _LOGGER.debug("Loaded %d entries from persistent cache", len(self._cache))  # noqa: E111
    except Exception as e:
      _LOGGER.error("Failed to load persistent cache: %s", e)  # noqa: E111
      self._cache = {}  # noqa: E111

  async def async_save(self) -> None:  # noqa: E111
    """Save cache to storage."""
    try:
      # Convert to serializable format  # noqa: E114
      data = {  # noqa: E111
        key: {
          "value": entry.value,
          "timestamp": entry.timestamp,
          "ttl_seconds": entry.ttl_seconds,
          "hit_count": entry.hit_count,
        }
        for key, entry in self._cache.items()
        if not entry.is_expired
      }

      await self._store.async_save(data)  # noqa: E111
      _LOGGER.debug("Saved %d entries to persistent cache", len(data))  # noqa: E111
    except Exception as e:
      _LOGGER.error("Failed to save persistent cache: %s", e)  # noqa: E111

  async def get(self, key: str) -> T | None:  # noqa: E111
    """Get value from cache.

    Args:
        key: Cache key

    Returns:
        Cached value or None
    """
    if not self._loaded:
      await self.async_load()  # noqa: E111

    if key not in self._cache:
      self._stats.misses += 1  # noqa: E111
      return None  # noqa: E111

    entry = self._cache[key]

    if entry.is_expired:
      del self._cache[key]  # noqa: E111
      self._stats.misses += 1  # noqa: E111
      return None  # noqa: E111

    entry.mark_accessed()
    self._stats.hits += 1
    return entry.value

  async def set(  # noqa: E111
    self,
    key: str,
    value: T,
    ttl: float | None = None,
  ) -> None:
    """Set value in cache.

    Args:
        key: Cache key
        value: Value to cache
        ttl: Optional TTL override
    """
    if not self._loaded:
      await self.async_load()  # noqa: E111

    entry = CacheEntry(
      value=value,
      timestamp=time.time(),
      ttl_seconds=ttl or self._default_ttl,
    )
    self._cache[key] = entry

    # Auto-save periodically (every 10 entries)
    if len(self._cache) % 10 == 0:
      await self.async_save()  # noqa: E111

  async def clear(self) -> None:  # noqa: E111
    """Clear cache."""
    self._cache.clear()
    await self.async_save()

  def get_stats(self) -> CacheStats:  # noqa: E111
    """Return cache statistics."""
    self._stats.size = len(self._cache)
    return self._stats


class TwoLevelCache[T]:
  """Two-level cache with L1 (memory) and L2 (persistent) layers.

  Examples:
      >>> cache = TwoLevelCache[dict](
      ...   hass,
      ...   name="pawcontrol",
      ...   l1_size=100,
      ...   l1_ttl=300.0,
      ...   l2_ttl=3600.0,
      ... )
      >>> await cache.async_setup()
      >>> await cache.set("key", {"data": "value"})
  """  # noqa: E111

  def __init__(  # noqa: E111
    self,
    hass: HomeAssistant,
    *,
    name: str = "pawcontrol",
    l1_size: int = 100,
    l1_ttl: float = 300.0,
    l2_ttl: float = 3600.0,
  ) -> None:
    """Initialize two-level cache.

    Args:
        hass: Home Assistant instance
        name: Cache name
        l1_size: L1 cache size
        l1_ttl: L1 TTL in seconds
        l2_ttl: L2 TTL in seconds
    """
    self._hass = hass
    self._l1 = LRUCache[T](max_size=l1_size, default_ttl=l1_ttl)
    self._l2 = PersistentCache[T](
      hass,
      name,
      default_ttl=l2_ttl,
    )

  async def async_setup(self) -> None:  # noqa: E111
    """Set up cache."""
    await self._l2.async_load()

  async def get(self, key: str) -> T | None:  # noqa: E111
    """Get value from cache.

    Checks L1 first, then L2. Promotes L2 hits to L1.

    Args:
        key: Cache key

    Returns:
        Cached value or None
    """
    # Try L1
    value = await self._l1.get(key)
    if value is not None:
      return value  # noqa: E111

    # Try L2
    value = await self._l2.get(key)
    if value is not None:
      # Promote to L1  # noqa: E114
      await self._l1.set(key, value)  # noqa: E111
      return value  # noqa: E111

    return None

  async def set(  # noqa: E111
    self,
    key: str,
    value: T,
    *,
    l1_ttl: float | None = None,
    l2_ttl: float | None = None,
  ) -> None:
    """Set value in cache.

    Writes to both L1 and L2.

    Args:
        key: Cache key
        value: Value to cache
        l1_ttl: Optional L1 TTL override
        l2_ttl: Optional L2 TTL override
    """
    await self._l1.set(key, value, ttl=l1_ttl)
    await self._l2.set(key, value, ttl=l2_ttl)

  async def delete(self, key: str) -> None:  # noqa: E111
    """Delete from cache.

    Args:
        key: Cache key
    """
    await self._l1.delete(key)
    # Note: L2 will expire naturally

  async def clear(self) -> None:  # noqa: E111
    """Clear all caches."""
    await self._l1.clear()
    await self._l2.clear()

  async def async_save(self) -> None:  # noqa: E111
    """Save L2 cache to storage."""
    await self._l2.async_save()

  def get_stats(self) -> dict[str, CacheStats]:  # noqa: E111
    """Return statistics for both cache levels."""
    return {
      "l1": self._l1.get_stats(),
      "l2": self._l2.get_stats(),
    }


# Cache decorators


def cached(
  cache: TwoLevelCache[Any],
  key_prefix: str,
  ttl: float = 300.0,
) -> Any:
  """Decorator to cache function results.

  Args:
      cache: Cache instance
      key_prefix: Key prefix for cache entries
      ttl: Time to live in seconds

  Returns:
      Decorated function

  Examples:
      >>> @cached(my_cache, "dog_data", ttl=300.0)
      ... async def get_dog_data(dog_id: str):
      ...   return await api.fetch(dog_id)
  """  # noqa: E111

  def decorator(func: Any) -> Any:  # noqa: E111
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
      # Generate cache key from args  # noqa: E114
      key_parts = [key_prefix]  # noqa: E111
      key_parts.extend(str(arg) for arg in args)  # noqa: E111
      key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))  # noqa: E111
      cache_key = ":".join(key_parts)  # noqa: E111

      # Try cache  # noqa: E114
      cached_value = await cache.get(cache_key)  # noqa: E111
      if cached_value is not None:  # noqa: E111
        _LOGGER.debug("Cache hit: %s", cache_key)
        return cached_value

      # Call function  # noqa: E114
      _LOGGER.debug("Cache miss: %s", cache_key)  # noqa: E111
      result = await func(*args, **kwargs)  # noqa: E111

      # Store in cache  # noqa: E114
      await cache.set(cache_key, result, l1_ttl=ttl, l2_ttl=ttl * 4)  # noqa: E111

      return result  # noqa: E111

    return wrapper

  return decorator  # noqa: E111
