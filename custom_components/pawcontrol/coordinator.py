"""Simplified coordinator for PawControl integration.

SIMPLIFIED: Removed enterprise patterns (7+ managers, batch processing, performance monitoring).
Maintains core DataUpdateCoordinator functionality with basic dog data management.

Quality Scale: Platinum
Home Assistant: 2025.9.1+
Python: 3.13+
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_GPS_UPDATE_INTERVAL,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    UPDATE_INTERVALS,
)
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Simplified coordinator for PawControl integration.

    Responsibilities:
    - Fetch and coordinate dog data updates
    - Manage configuration and dog profiles
    - Provide data interface for entities
    - Handle errors and recovery
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.config_entry = entry
        self._dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
        self.dogs = self._dogs_config

        # Calculate update interval based on complexity
        update_interval = self._calculate_update_interval()

        super().__init__(
            hass,
            _LOGGER,
            name="PawControl Data",
            update_interval=timedelta(seconds=update_interval),
            always_update=False,
        )

        # Simple data storage
        self._data: dict[str, Any] = {}

        _LOGGER.info(
            "Coordinator initialized: %d dogs, %ds interval",
            len(self.dogs),
            update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data for all dogs."""
        if not self.dogs:
            return {}

        all_data = {}
        errors = 0

        # Update each dog's data
        for dog in self.dogs:
            dog_id = dog[CONF_DOG_ID]
            try:
                dog_data = await self._fetch_dog_data(dog_id)
                all_data[dog_id] = dog_data
            except Exception as err:
                _LOGGER.warning("Failed to fetch data for %s: %s", dog_id, err)
                errors += 1
                # Use last known data or empty dict
                all_data[dog_id] = self._data.get(dog_id, {})

        # Fail if all dogs failed
        if errors == len(self.dogs) and len(self.dogs) > 0:
            raise UpdateFailed("All dogs failed to update")

        self._data = all_data
        return all_data

    async def _fetch_dog_data(self, dog_id: str) -> dict[str, Any]:
        """Fetch data for a single dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Dog data dictionary
        """
        dog_config = self.get_dog_config(dog_id)
        if not dog_config:
            raise ValueError(f"Dog {dog_id} not found")

        data = {"dog_info": dog_config}
        modules = dog_config.get("modules", {})

        # Add module data based on enabled modules
        if modules.get(MODULE_FEEDING):
            data[MODULE_FEEDING] = await self._get_feeding_data(dog_id)

        if modules.get(MODULE_WALK):
            data[MODULE_WALK] = await self._get_walk_data(dog_id)

        if modules.get(MODULE_GPS):
            data[MODULE_GPS] = await self._get_gps_data(dog_id)

        if modules.get(MODULE_HEALTH):
            data[MODULE_HEALTH] = await self._get_health_data(dog_id)

        return data

    async def _get_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Get feeding data for dog."""
        # Simple feeding data - can be expanded with actual data sources
        return {
            "last_feeding": None,
            "next_feeding": None,
            "daily_portions": 0,
            "status": "unknown",
        }

    async def _get_walk_data(self, dog_id: str) -> dict[str, Any]:
        """Get walk data for dog."""
        # Simple walk data - can be expanded with actual data sources
        return {
            "current_walk": None,
            "last_walk": None,
            "daily_walks": 0,
            "total_distance": 0,
            "status": "unknown",
        }

    async def _get_gps_data(self, dog_id: str) -> dict[str, Any]:
        """Get GPS data for dog."""
        # Simple GPS data - can be expanded with actual GPS sources
        return {
            "latitude": None,
            "longitude": None,
            "accuracy": None,
            "last_update": None,
            "status": "unknown",
        }

    async def _get_health_data(self, dog_id: str) -> dict[str, Any]:
        """Get health data for dog."""
        # Simple health data - can be expanded with actual health tracking
        return {
            "weight": None,
            "last_vet_visit": None,
            "medications": [],
            "status": "unknown",
        }

    def _calculate_update_interval(self) -> int:
        """Calculate update interval based on enabled modules."""
        if not self.dogs:
            return UPDATE_INTERVALS["minimal"]

        # Check for GPS requirements (fastest updates)
        has_gps = any(
            dog.get("modules", {}).get(MODULE_GPS, False) for dog in self.dogs
        )

        if has_gps:
            # Use GPS interval from options if available
            return self.config_entry.options.get(
                CONF_GPS_UPDATE_INTERVAL, UPDATE_INTERVALS["frequent"]
            )

        # Check module complexity
        total_modules = sum(
            len([m for m in dog.get("modules", {}).values() if m]) for dog in self.dogs
        )

        if total_modules > 10:
            return UPDATE_INTERVALS["normal"]
        elif total_modules > 5:
            return UPDATE_INTERVALS["frequent"]
        else:
            return UPDATE_INTERVALS["minimal"]

    # Public interface methods
    def get_dog_config(self, dog_id: str) -> dict[str, Any] | None:
        """Get dog configuration."""
        return next(
            (dog for dog in self._dogs_config if dog.get(CONF_DOG_ID) == dog_id), None
        )

    def get_enabled_modules(self, dog_id: str) -> set[str]:
        """Get enabled modules for dog."""
        config = self.get_dog_config(dog_id)
        if not config:
            return set()
        modules = config.get("modules", {})
        return {name for name, enabled in modules.items() if enabled}

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        """Check if module is enabled for dog."""
        config = self.get_dog_config(dog_id)
        return config.get("modules", {}).get(module, False) if config else False

    def get_dog_ids(self) -> list[str]:
        """Get all dog IDs."""
        return [dog.get(CONF_DOG_ID) for dog in self._dogs_config]

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        """Get data for specific dog."""
        return self._data.get(dog_id)

    def get_all_dogs_data(self) -> dict[str, Any]:
        """Get all dogs data."""
        return self._data.copy()

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        """Get data for a specific module of a dog."""
        return self._data.get(dog_id, {}).get(module, {})

    @property
    def available(self) -> bool:
        """Check if coordinator is available."""
        return self.last_update_success

    def get_update_statistics(self) -> dict[str, Any]:
        """Get basic update statistics."""
        return {
            "total_dogs": len(self.dogs),
            "last_update_success": self.last_update_success,
            "update_interval_seconds": self.update_interval.total_seconds(),
            "dogs_tracked": len(self._data),
        }
