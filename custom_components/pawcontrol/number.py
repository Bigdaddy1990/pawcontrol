"""Number platform for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfMass,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    ICON_WEIGHT,
    ICON_TEMPERATURE,
    MIN_DOG_WEIGHT,
    MAX_DOG_WEIGHT,
    MIN_TEMPERATURE,
    MAX_TEMPERATURE,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl number entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for dog_name, dog_data in entry_data.items():
        coordinator = dog_data["coordinator"]
        config = dog_data["config"]
        
        # Add module-specific number entities
        modules = config.get("modules", {})
        
        if modules.get("health", {}).get("enabled", False):
            entities.extend([
                PawControlWeightNumber(coordinator, config),
                PawControlTemperatureNumber(coordinator, config),
                PawControlHealthScoreNumber(coordinator, config),
            ])
        
        if modules.get("feeding", {}).get("enabled", False):
            entities.append(PawControlDailyFoodAmountNumber(coordinator, config))
        
        if modules.get("walk", {}).get("enabled", False):
            entities.append(PawControlDailyWalkDurationNumber(coordinator, config))
        
        if modules.get("gps", {}).get("enabled", False):
            entities.extend([
                PawControlGeofenceRadiusNumber(coordinator, config),
                PawControlGPSUpdateIntervalNumber(coordinator, config),
            ])
        
        # Always add activity scores
        entities.extend([
            PawControlHappinessScoreNumber(coordinator, config),
            PawControlActivityScoreNumber(coordinator, config),
        ])
    
    async_add_entities(entities)


class PawControlNumberBase(CoordinatorEntity, NumberEntity):
    """Base class for PawControl number entities."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        config: dict[str, Any],
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._config = config
        self._dog_name = config.get(CONF_DOG_NAME, "Unknown")
        self._dog_id = self._dog_name.lower().replace(" ", "_")
        self._attr_mode = NumberMode.BOX

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._dog_id)},
            "name": f"PawControl - {self._dog_name}",
            "manufacturer": "PawControl",
            "model": "Dog Management System",
            "sw_version": "1.0.0",
        }


class PawControlWeightNumber(PawControlNumberBase):
    """Number entity for dog weight."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_weight_input"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gewicht"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_WEIGHT

    @property
    def native_min_value(self):
        """Return the minimum value."""
        return MIN_DOG_WEIGHT

    @property
    def native_max_value(self):
        """Return the maximum value."""
        return MAX_DOG_WEIGHT

    @property
    def native_step(self):
        """Return the step value."""
        return 0.1

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfMass.KILOGRAMS

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("profile", {}).get("weight", 15.0)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.coordinator.async_update_health(weight=value)


class PawControlTemperatureNumber(PawControlNumberBase):
    """Number entity for dog temperature."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_temperature_input"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Temperatur"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_TEMPERATURE

    @property
    def native_min_value(self):
        """Return the minimum value."""
        return MIN_TEMPERATURE

    @property
    def native_max_value(self):
        """Return the maximum value."""
        return MAX_TEMPERATURE

    @property
    def native_step(self):
        """Return the step value."""
        return 0.1

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfTemperature.CELSIUS

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("health", {}).get("temperature", 38.5)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.coordinator.async_update_health(temperature=value)


class PawControlHealthScoreNumber(PawControlNumberBase):
    """Number entity for health score."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_health_score_input"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gesundheitsscore"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:heart-pulse"

    @property
    def native_min_value(self):
        """Return the minimum value."""
        return 0

    @property
    def native_max_value(self):
        """Return the maximum value."""
        return 100

    @property
    def native_step(self):
        """Return the step value."""
        return 1

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("statistics", {}).get("health_score", 100)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self.coordinator._data["statistics"]["health_score"] = value
        await self.coordinator.async_request_refresh()


class PawControlHappinessScoreNumber(PawControlNumberBase):
    """Number entity for happiness score."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_happiness_score_input"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Glücklichkeitsscore"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:emoticon-happy"

    @property
    def native_min_value(self):
        """Return the minimum value."""
        return 0

    @property
    def native_max_value(self):
        """Return the maximum value."""
        return 100

    @property
    def native_step(self):
        """Return the step value."""
        return 1

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def native_value(self):
        """Return the current value."""
        return round(self.coordinator.data.get("statistics", {}).get("happiness_score", 100))

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self.coordinator._data["statistics"]["happiness_score"] = value
        await self.coordinator.async_request_refresh()


class PawControlActivityScoreNumber(PawControlNumberBase):
    """Number entity for activity score."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_activity_score_input"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Aktivitätsscore"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:run"

    @property
    def native_min_value(self):
        """Return the minimum value."""
        return 0

    @property
    def native_max_value(self):
        """Return the maximum value."""
        return 100

    @property
    def native_step(self):
        """Return the step value."""
        return 1

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("activity", {}).get("activity_score", 0)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self.coordinator._data["activity"]["activity_score"] = value
        await self.coordinator.async_request_refresh()


class PawControlDailyFoodAmountNumber(PawControlNumberBase):
    """Number entity for daily food amount."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_daily_food_amount"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Tägliche Futtermenge"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:food-drumstick"

    @property
    def native_min_value(self):
        """Return the minimum value."""
        return 50

    @property
    def native_max_value(self):
        """Return the maximum value."""
        return 2000

    @property
    def native_step(self):
        """Return the step value."""
        return 10

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "g"

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("feeding", {}).get("daily_amount", 500)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self.coordinator._data["feeding"]["daily_amount"] = value
        await self.coordinator.async_request_refresh()


class PawControlDailyWalkDurationNumber(PawControlNumberBase):
    """Number entity for daily walk duration."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_daily_walk_duration"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Tägliche Spaziergang-Dauer"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:dog-service"

    @property
    def native_min_value(self):
        """Return the minimum value."""
        return 0

    @property
    def native_max_value(self):
        """Return the maximum value."""
        return 480

    @property
    def native_step(self):
        """Return the step value."""
        return 5

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfTime.MINUTES

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("activity", {}).get("daily_walk_duration", 60)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("activity", {})["daily_walk_duration"] = value
        await self.coordinator.async_request_refresh()


class PawControlGeofenceRadiusNumber(PawControlNumberBase):
    """Number entity for geofence radius."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_geofence_radius"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Geofence-Radius"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:radius"

    @property
    def native_min_value(self):
        """Return the minimum value."""
        return 10

    @property
    def native_max_value(self):
        """Return the maximum value."""
        return 1000

    @property
    def native_step(self):
        """Return the step value."""
        return 10

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfLength.METERS

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("settings", {}).get("geofence_radius", 50)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("settings", {})["geofence_radius"] = value
        await self.coordinator.async_request_refresh()


class PawControlGPSUpdateIntervalNumber(PawControlNumberBase):
    """Number entity for GPS update interval."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_gps_update_interval"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} GPS-Update-Intervall"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:timer"

    @property
    def native_min_value(self):
        """Return the minimum value."""
        return 30

    @property
    def native_max_value(self):
        """Return the maximum value."""
        return 600

    @property
    def native_step(self):
        """Return the step value."""
        return 30

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfTime.SECONDS

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("settings", {}).get("gps_update_interval", 60)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("settings", {})["gps_update_interval"] = value
        await self.coordinator.async_request_refresh()
