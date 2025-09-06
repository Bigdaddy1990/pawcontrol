"""Optimized dog data manager with caching and batch operations.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.util import dt as dt_util


class DogDataManager:
    """Optimized in-memory storage for dog related data with caching."""

    def __init__(self) -> None:
        """Initialize with optimized data structures."""
        self._dogs: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        # OPTIMIZATION: Cache for read operations
        self._read_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=5)  # 5 second cache

    async def async_ensure_dog(self, dog_id: str, defaults: Dict[str, Any]) -> None:
        """Ensure a dog entry exists, creating it with defaults if necessary."""
        async with self._lock:
            if dog_id not in self._dogs:
                self._dogs[dog_id] = defaults.copy()
                self._invalidate_cache()

    async def async_update_dog(self, dog_id: str, data: Dict[str, Any]) -> None:
        """Update data for a given dog."""
        async with self._lock:
            self._dogs.setdefault(dog_id, {}).update(data)
            self._invalidate_cache()

    async def async_update_batch(self, updates: Dict[str, Dict[str, Any]]) -> None:
        """OPTIMIZATION: Batch update multiple dogs at once.
        
        Args:
            updates: Dictionary mapping dog_id to update data
        """
        async with self._lock:
            for dog_id, data in updates.items():
                self._dogs.setdefault(dog_id, {}).update(data)
            self._invalidate_cache()

    async def async_remove_dog(self, dog_id: str) -> None:
        """Remove a dog from the manager."""
        async with self._lock:
            if dog_id in self._dogs:
                del self._dogs[dog_id]
                self._invalidate_cache()

    async def async_get_dog(self, dog_id: str) -> Optional[Dict[str, Any]]:
        """OPTIMIZATION: Get specific dog data without full copy.
        
        Args:
            dog_id: Dog identifier
            
        Returns:
            Dog data or None if not found
        """
        async with self._lock:
            if dog_id in self._dogs:
                # Return shallow copy for single dog
                return self._dogs[dog_id].copy()
            return None

    async def async_all_dogs(self) -> Dict[str, Dict[str, Any]]:
        """Return cached copy of all stored dog data.
        
        OPTIMIZATION: Uses cached data when available instead of deepcopy.
        """
        async with self._lock:
            # Check if cache is valid
            if self._is_cache_valid():
                return self._read_cache
            
            # Create new cache - shallow copy of dict with shallow copies of values
            # This is much faster than deepcopy for read-only access
            self._read_cache = {
                dog_id: dog_data.copy()
                for dog_id, dog_data in self._dogs.items()
            }
            self._cache_timestamp = dt_util.utcnow()
            
            return self._read_cache

    async def async_get_dog_ids(self) -> list[str]:
        """OPTIMIZATION: Get just the dog IDs without copying all data.
        
        Returns:
            List of dog identifiers
        """
        async with self._lock:
            return list(self._dogs.keys())

    async def async_dog_exists(self, dog_id: str) -> bool:
        """OPTIMIZATION: Check if dog exists without copying data.
        
        Args:
            dog_id: Dog identifier
            
        Returns:
            True if dog exists
        """
        async with self._lock:
            return dog_id in self._dogs

    def _invalidate_cache(self) -> None:
        """Invalidate the read cache."""
        self._read_cache = None
        self._cache_timestamp = None

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._read_cache is None or self._cache_timestamp is None:
            return False
        
        elapsed = dt_util.utcnow() - self._cache_timestamp
        return elapsed < self._cache_ttl
