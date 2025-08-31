"""Simple walk session management used in tests and examples.

The production integration offloads all persistence to the
:class:`PawControlDataManager`.  This module provides a lightweight in-memory
replacement offering asynchronous methods which mimic the behaviour of the
full implementation.  Each walk session is identified by a UUID and stored per
dog.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import copy
import uuid


@dataclass(slots=True)
class WalkSession:
    """Represent a single walk."""

    walk_id: str
    start: datetime
    end: Optional[datetime] = None
    distance: float = 0.0


class WalkManager:
    """Track walks for multiple dogs."""

    def __init__(self) -> None:
        self._active: Dict[str, WalkSession] = {}
        self._history: Dict[str, List[WalkSession]] = {}

    async def async_start_walk(self, dog_id: str) -> WalkSession:
        """Start a walk for ``dog_id``.

        Raises:
            ValueError: If a walk is already in progress for the dog.
        """
        if dog_id in self._active:
            raise ValueError("walk already in progress")
        session = WalkSession(str(uuid.uuid4()), datetime.utcnow())
        self._active[dog_id] = session
        self._history.setdefault(dog_id, []).append(session)
        return session

    async def async_end_walk(
        self, dog_id: str, distance: float = 0.0
    ) -> Optional[WalkSession]:
        """End the current walk for ``dog_id`` and return the session."""
        session = self._active.pop(dog_id, None)
        if not session:
            return None
        session.end = datetime.utcnow()
        session.distance = distance
        return session

    async def async_get_walks(self, dog_id: str) -> List[WalkSession]:
        """Return a copy of the walk history for ``dog_id``."""
        return [copy.copy(session) for session in self._history.get(dog_id, [])]
