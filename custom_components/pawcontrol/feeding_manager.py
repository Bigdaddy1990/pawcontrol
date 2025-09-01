"""Light‑weight feeding management utilities for PawControl.

The real integration uses the :class:`PawControlDataManager` to persist
information, however some unit tests and example code only need an in-memory
representation.  The :class:`FeedingManager` implemented here stores feeding
information per dog and exposes simple asynchronous helper methods.  The
implementation is intentionally compact but mirrors the interface of the
production code which simplifies testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class FeedingEvent:
    """Represent a single feeding event."""

    time: datetime
    amount: float
    meal_type: Optional[str] = None


class FeedingManager:
    """Store and retrieve feeding information for dogs."""

    def __init__(self) -> None:
        self._feedings: Dict[str, List[FeedingEvent]] = {}

    async def async_add_feeding(
        self,
        dog_id: str,
        amount: float,
        meal_type: Optional[str] = None,
        time: Optional[datetime] = None,
    ) -> FeedingEvent:
        """Record a feeding event for a dog.

        Args:
            dog_id: Identifier of the dog.
            amount: Amount of food provided.
            meal_type: Optional description of the meal.
            time: Optional timestamp.  ``datetime.utcnow`` is used if omitted.
        """

        event = FeedingEvent(time or datetime.utcnow(), amount, meal_type)
        self._feedings.setdefault(dog_id, []).append(event)
        return event

    async def async_get_feedings(self, dog_id: str) -> List[FeedingEvent]:
        """Return a copy of the feeding history for ``dog_id``."""

        return list(self._feedings.get(dog_id, []))

    async def async_get_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Return aggregated feeding data with strict type consistency.

        The returned ``feedings_today`` field is always a mapping of meal type
        to integer count.  ``total_feedings_today`` provides the numeric total
        to avoid callers needing to sum the mapping themselves.
        """

        feedings = self._feedings.get(dog_id, [])
        if not feedings:
            return {"last_feeding": None, "feedings_today": {}, "total_feedings_today": 0}

        now = datetime.utcnow()
        feedings_today: Dict[str, int] = {}
        for event in feedings:
            if event.time.date() != now.date():
                continue
            meal = event.meal_type or "unknown"
            feedings_today[meal] = feedings_today.get(meal, 0) + 1

        last_event = max(feedings, key=lambda e: e.time, default=None)
        last_time = last_event.time if last_event else None
        last_hours = ((now - last_time).total_seconds() / 3600) if last_time else None

        return {
            "last_feeding": last_time.isoformat() if last_time else None,
            "last_feeding_type": last_event.meal_type if last_event else None,
            "last_feeding_hours": last_hours,
            "feedings_today": feedings_today,
            "total_feedings_today": sum(feedings_today.values()),
        }
