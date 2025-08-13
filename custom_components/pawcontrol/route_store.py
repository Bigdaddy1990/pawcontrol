"""Route storage for Paw Control integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class RouteHistoryStore:
    """Manage route history storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str, domain: str):
        """Initialize the storage."""
        self.hass = hass
        self._store = Store(hass, 1, f"{domain}_{entry_id}_route_history")
        self._data: Dict[str, Any] = {}

    async def async_load(self) -> Dict[str, Any]:
        """Load route history from storage."""
        try:
            self._data = await self._store.async_load() or {"dogs": {}}
        except (HomeAssistantError, OSError) as err:
            _LOGGER.warning("Failed to load route history: %s", err)
            self._data = {"dogs": {}}
        return self._data

    async def async_save(self, data: Dict[str, Any]) -> None:
        """Save route history to storage."""
        self._data = data
        await self._store.async_save(data)

    async def async_add_walk(
        self,
        hass: HomeAssistant,
        entry_id: str,
        domain: str,
        dog_id: str,
        start_time: str | None,
        end_time: str,
        distance_m: float,
        duration_s: float,
        points_count: int,
        limit: int = 500,
    ) -> None:
        """Add a walk to the route history."""
        await self.async_load()

        dogs_data = self._data.setdefault("dogs", {})
        dog_routes = dogs_data.setdefault(dog_id, [])

        route_entry = {
            "start": start_time,
            "end": end_time,
            "distance_m": round(distance_m, 1),
            "duration_s": int(duration_s),
            "points": points_count,
            "created": dt_util.utcnow().isoformat(),
        }

        dog_routes.append(route_entry)

        # Keep only the last 'limit' routes
        if len(dog_routes) > limit:
            dog_routes[:] = dog_routes[-limit:]

        await self.async_save(self._data)

    async def async_list(self, dog_id: str) -> List[Dict[str, Any]]:
        """List routes for a dog."""
        await self.async_load()
        return self._data.get("dogs", {}).get(dog_id, [])

    async def async_purge(self, older_than_days: int | None = None) -> None:
        """Purge old routes."""
        await self.async_load()

        if older_than_days is None:
            # Clear all
            self._data = {"dogs": {}}
        else:
            cutoff = dt_util.utcnow() - timedelta(days=older_than_days)

            for dog_id, routes in self._data.get("dogs", {}).items():
                filtered_routes = []
                for route in routes:
                    try:
                        route_time = dt_util.parse_datetime(
                            route.get("created") or route.get("end")
                        )
                        if route_time and route_time > cutoff:
                            filtered_routes.append(route)
                    except (TypeError, ValueError):
                        # Keep if we can't parse the date
                        filtered_routes.append(route)

                self._data["dogs"][dog_id] = filtered_routes

        await self.async_save(self._data)
