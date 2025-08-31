from __future__ import annotations

import asyncio
from typing import Any, Dict


class DogDataManager:
    """In-memory storage for dog related data."""

    def __init__(self) -> None:
        self._dogs: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def async_ensure_dog(self, dog_id: str, defaults: Dict[str, Any]) -> None:
        """Ensure a dog entry exists, creating it with defaults if necessary."""
        async with self._lock:
            self._dogs.setdefault(dog_id, defaults.copy())

    async def async_update_dog(self, dog_id: str, data: Dict[str, Any]) -> None:
        """Update data for a given dog."""
        async with self._lock:
            self._dogs.setdefault(dog_id, {}).update(data)

    async def async_remove_dog(self, dog_id: str) -> None:
        """Remove a dog from the manager."""
        async with self._lock:
            self._dogs.pop(dog_id, None)

    async def async_all_dogs(self) -> Dict[str, Dict[str, Any]]:
        """Return a copy of all stored dog data."""
        async with self._lock:
            return copy.deepcopy(self._dogs)
