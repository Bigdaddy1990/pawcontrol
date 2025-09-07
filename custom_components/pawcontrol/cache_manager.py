"""Specialized cache management for PawControl integration.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

Ultra-fast multi-tier cache with LRU eviction and hot key tracking.
Extracted from monolithic coordinator for better maintainability.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Cache configuration constants
CACHE_TTL_FAST = 10  # seconds
CACHE_TTL_MEDIUM = 120  # seconds
CACHE_TTL_SLOW = 900  # seconds


class CacheManager:
    """Ultra-fast multi-tier cache with LRU eviction and hot key tracking."""

    def __init__(self, max_size: int = 150) -> None:
        """Initialize cache with size limit and LRU eviction.

        Args:
            max_size: Maximum cache entries
        """
        self._cache: dict[str, dict[str, Any]] = {}
        self._expiry: dict[str, datetime] = {}
        self._access_count: dict[str, int] = defaultdict(int)
        self._last_access: dict[str, datetime] = {}
        self._max_size = max_size
        self._lock = asyncio.Lock()

        # Hot key tracking for performance optimization
        self._hot_keys: set[str] = set()
        self._cache_hits = 0
        self._cache_misses = 0

        _LOGGER.debug("CacheManager initialized with max_size=%d", max_size)

    async def get(self, key: str) -> dict[str, Any] | None:
        """Get cached data with async lock for thread safety.

        Args:
            key: Cache key

        Returns:
            Cached data or None if not found/expired
        """
        async with self._lock:
            now = dt_util.utcnow()

            # Check expiry first (fast path)
            if key in self._expiry and now > self._expiry[key]:
                self._evict_entry(key)
                self._cache_misses += 1
                return None

            if key not in self._cache:
                self._cache_misses += 1
                return None

            # Update access statistics
            self._access_count[key] += 1
            self._last_access[key] = now
            self._cache_hits += 1

            # Track hot keys
            if self._access_count[key] > 5:
                self._hot_keys.add(key)

            # Return copy for safety
            return self._cache[key].copy()

    async def set(
        self, key: str, data: dict[str, Any], ttl_seconds: int = CACHE_TTL_MEDIUM
    ) -> None:
        """Set cached data with TTL and LRU management.

        Args:
            key: Cache key
            data: Data to cache
            ttl_seconds: Time to live in seconds
        """
        async with self._lock:
            now = dt_util.utcnow()

            # LRU eviction if needed
            if len(self._cache) >= self._max_size and key not in self._cache:
                await self._evict_lru()

            self._cache[key] = data.copy()
            self._expiry[key] = now + timedelta(seconds=ttl_seconds)
            self._last_access[key] = now

            # Don't reset access count for existing entries
            if key not in self._access_count:
                self._access_count[key] = 0

    async def invalidate(
        self, key: str | None = None, pattern: str | None = None
    ) -> int:
        """Invalidate cache entries by key or pattern.

        Args:
            key: Specific key to invalidate
            pattern: Pattern to match keys (e.g., "dog_*")

        Returns:
            Number of entries invalidated
        """
        async with self._lock:
            if key:
                if key in self._cache:
                    self._evict_entry(key)
                    return 1
                return 0

            if pattern:
                # Batch invalidation by pattern
                keys_to_remove = [
                    k for k in self._cache.keys() if k.startswith(pattern.rstrip("*"))
                ]
                for k in keys_to_remove:
                    self._evict_entry(k)
                return len(keys_to_remove)

            return 0

    async def clear_expired(self) -> int:
        """Clear expired entries efficiently.

        Returns:
            Number of entries cleared
        """
        async with self._lock:
            now = dt_util.utcnow()
            expired_keys = [key for key, expiry in self._expiry.items() if now > expiry]

            for key in expired_keys:
                self._evict_entry(key)

            return len(expired_keys)

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()
            self._expiry.clear()
            self._access_count.clear()
            self._last_access.clear()
            self._hot_keys.clear()
            self._cache_hits = 0
            self._cache_misses = 0

    def _evict_entry(self, key: str) -> None:
        """Evict single cache entry.

        Args:
            key: Key to evict
        """
        self._cache.pop(key, None)
        self._expiry.pop(key, None)
        self._access_count.pop(key, None)
        self._last_access.pop(key, None)
        self._hot_keys.discard(key)

    async def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._last_access:
            return

        # Find LRU entry (skip hot keys)
        lru_key = None
        oldest_time = dt_util.utcnow()

        for key, last_time in self._last_access.items():
            if key not in self._hot_keys and last_time < oldest_time:
                lru_key = key
                oldest_time = last_time

        if lru_key:
            self._evict_entry(lru_key)

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        total_accesses = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_accesses * 100 if total_accesses > 0 else 0

        return {
            "total_entries": len(self._cache),
            "max_size": self._max_size,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": round(hit_rate, 1),
            "hot_keys": len(self._hot_keys),
            "total_accesses": sum(self._access_count.values()),
        }

    async def get_cache_entry_details(self, key: str) -> dict[str, Any] | None:
        """Get detailed information about a cache entry.

        Args:
            key: Cache key

        Returns:
            Entry details or None if not found
        """
        async with self._lock:
            if key not in self._cache:
                return None

            now = dt_util.utcnow()
            expiry = self._expiry.get(key)

            return {
                "key": key,
                "size": len(str(self._cache[key])),
                "access_count": self._access_count.get(key, 0),
                "last_access": self._last_access.get(key),
                "expires_at": expiry,
                "ttl_remaining": (expiry - now).total_seconds() if expiry else None,
                "is_hot_key": key in self._hot_keys,
            }

    async def optimize_cache(self) -> dict[str, Any]:
        """Perform cache optimization and return optimization report.

        Returns:
            Optimization report
        """
        async with self._lock:
            initial_size = len(self._cache)

            # Clear expired entries - fix recursive call
            now = dt_util.utcnow()
            expired_keys = [key for key, expiry in self._expiry.items() if now > expiry]

            for key in expired_keys:
                self._evict_entry(key)

            expired_cleared = len(expired_keys)

            # Promote frequently accessed entries to hot keys
            promoted_keys = 0
            for key, count in self._access_count.items():
                if count >= 3 and key not in self._hot_keys:
                    self._hot_keys.add(key)
                    promoted_keys += 1

            # Remove stale hot keys
            demoted_keys = 0
            for key in list(self._hot_keys):
                if self._access_count.get(key, 0) < 2:
                    self._hot_keys.discard(key)
                    demoted_keys += 1

            final_size = len(self._cache)

            return {
                "initial_entries": initial_size,
                "final_entries": final_size,
                "expired_cleared": expired_cleared,
                "hot_keys_promoted": promoted_keys,
                "hot_keys_demoted": demoted_keys,
                "current_hot_keys": len(self._hot_keys),
                "optimization_completed": True,
            }
