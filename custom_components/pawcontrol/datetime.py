"""DateTime platform for PawControl integration."""
from __future__ import annotations

from datetime import datetime, date, time
import logging
from typing import Any

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    CONF_MODULES,
    MODULE_FEEDING,
    MODULE_WALK,
    MODULE_HEALTH,
    MODULE_TRAINING,
    MODULE_GROOMING,
    MODULE_VISITOR,
    ICON_CLOCK,
    ICON_CALENDAR,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl datetime entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for dog_name, dog_data in entry_data.items():
        coordinator = dog_data["coordinator"]
        config = dog_data["config"]
        
        # Get enabled modules
        modules = config.get(CONF_MODULES, {})
        
        # Feeding module entities
        if modules.get(MODULE_FEEDING, {}).get("enabled", False):
            entities.extend([
                PawControlLastFeedingDateTime(coordinator, config),
                PawControlLastFeedingMorningDateTime(coordinator, config),
                PawControlLastFeedingLunchDateTime(coordinator, config),
                PawControlLastFeedingEveningDateTime(coordinator, config),
                PawControlBreakfastTimeDateTime(coordinator, config),
                PawControlLunchTimeDateTime(coordinator, config),
                PawControlDinnerTimeDateTime(coordinator, config),
            ])
        
        # Walk module entities
        if modules.get(MODULE_WALK, {}).get("enabled", False):
            entities.extend([
                PawControlLastWalkDateTime(coordinator, config),
                PawControlLastOutsideDateTime(coordinator, config),
                PawControlLastPlayDateTime(coordinator, config),
            ])
        
        # Health module entities
        if modules.get(MODULE_HEALTH, {}).get("enabled", False):
            entities.extend([
                PawControlLastVetVisitDateTime(coordinator, config),
                PawControlNextVetAppointmentDateTime(coordinator, config),
                PawControlLastMedicationDateTime(coordinator, config),
                PawControlLastWeightCheckDateTime(coordinator, config),
                PawControlNextMedicationDateTime(coordinator, config),
            ])
        
        # Training module entities
        if modules.get(MODULE_TRAINING, {}).get("enabled", False):
            entities.extend([
                PawControlLastTrainingDateTime(coordinator, config),
                PawControlNextTrainingDateTime(coordinator, config),
            ])
        
        # Grooming module entities
        if modules.get(MODULE_GROOMING, {}).get("enabled", False):
            entities.extend([
                PawControlLastGroomingDateTime(coordinator, config),
                PawControlLastBathDateTime(coordinator, config),
                PawControlLastNailTrimDateTime(coordinator, config),
                PawControlNextGroomingDateTime(coordinator, config),
            ])
        
        # Visitor module entities
        if modules.get(MODULE_VISITOR, {}).get("enabled", False):
            entities.extend([
                PawControlVisitorStartDateTime(coordinator, config),
                PawControlVisitorEndDateTime(coordinator, config),
                PawControlEmergencyContactTimeDateTime(coordinator, config),
            ])
        
        # Always add last activity datetime
        entities.append(PawControlLastActivityDateTime(coordinator, config))
    
    async_add_entities(entities)


class PawControlDateTimeBase(CoordinatorEntity, DateTimeEntity):
    """Base class for PawControl datetime entities."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        config: dict[str, Any],
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator)
        self._config = config
        self._dog_name = config.get(CONF_DOG_NAME, "Unknown")
        self._dog_id = self._dog_name.lower().replace(" ", "_").replace("-", "_")
        self._attr_has_entity_name = True

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
    
    def _make_timezone_aware(self, dt: datetime) -> datetime:
        """Make datetime timezone-aware if it's not already."""
        if dt and dt.tzinfo is None:
            return dt_util.as_local(dt)
        return dt


# Feeding DateTime Entities
class PawControlLastFeedingDateTime(PawControlDateTimeBase):
    """DateTime entity for last feeding."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_feeding_datetime"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Fütterung"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:food-drumstick"

    @property
    def native_value(self):
        """Return the current value."""
        last_feeding = self.coordinator.data.get("status", {}).get("last_feeding")
        if last_feeding:
            try:
                dt = datetime.fromisoformat(last_feeding)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("status", {})["last_feeding"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlLastFeedingMorningDateTime(PawControlDateTimeBase):
    """DateTime entity for last morning feeding."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_feeding_morning"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letztes Frühstück"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:weather-sunset-up"

    @property
    def native_value(self):
        """Return the current value."""
        last_feeding = self.coordinator.data.get("feeding", {}).get("last_morning")
        if last_feeding:
            try:
                dt = datetime.fromisoformat(last_feeding)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("feeding", {})["last_morning"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlLastFeedingLunchDateTime(PawControlDateTimeBase):
    """DateTime entity for last lunch feeding."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_feeding_lunch"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letztes Mittagessen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:weather-sunny"

    @property
    def native_value(self):
        """Return the current value."""
        last_feeding = self.coordinator.data.get("feeding", {}).get("last_lunch")
        if last_feeding:
            try:
                dt = datetime.fromisoformat(last_feeding)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("feeding", {})["last_lunch"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlLastFeedingEveningDateTime(PawControlDateTimeBase):
    """DateTime entity for last evening feeding."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_feeding_evening"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letztes Abendessen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:weather-sunset-down"

    @property
    def native_value(self):
        """Return the current value."""
        last_feeding = self.coordinator.data.get("feeding", {}).get("last_evening")
        if last_feeding:
            try:
                dt = datetime.fromisoformat(last_feeding)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("feeding", {})["last_evening"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlBreakfastTimeDateTime(PawControlDateTimeBase):
    """DateTime entity for breakfast time."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_breakfast_time"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Frühstückszeit"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_CLOCK

    @property
    def native_value(self):
        """Return the current value."""
        time_str = self.coordinator.data.get("feeding", {}).get("breakfast_time", "07:00")
        try:
            time_parts = time_str.split(":")
            if len(time_parts) == 2:
                dt = datetime.combine(
                    date.today(),
                    time(int(time_parts[0]), int(time_parts[1]))
                )
                return self._make_timezone_aware(dt)
        except (ValueError, IndexError, AttributeError):
            pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("feeding", {})["breakfast_time"] = value.strftime("%H:%M")
        await self.coordinator.async_request_refresh()


class PawControlLunchTimeDateTime(PawControlDateTimeBase):
    """DateTime entity for lunch time."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_lunch_time"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Mittagszeit"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_CLOCK

    @property
    def native_value(self):
        """Return the current value."""
        time_str = self.coordinator.data.get("feeding", {}).get("lunch_time", "12:00")
        try:
            time_parts = time_str.split(":")
            if len(time_parts) == 2:
                dt = datetime.combine(
                    date.today(),
                    time(int(time_parts[0]), int(time_parts[1]))
                )
                return self._make_timezone_aware(dt)
        except (ValueError, IndexError, AttributeError):
            pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("feeding", {})["lunch_time"] = value.strftime("%H:%M")
        await self.coordinator.async_request_refresh()


class PawControlDinnerTimeDateTime(PawControlDateTimeBase):
    """DateTime entity for dinner time."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_dinner_time"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Abendessenzeit"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_CLOCK

    @property
    def native_value(self):
        """Return the current value."""
        time_str = self.coordinator.data.get("feeding", {}).get("dinner_time", "18:00")
        try:
            time_parts = time_str.split(":")
            if len(time_parts) == 2:
                dt = datetime.combine(
                    date.today(),
                    time(int(time_parts[0]), int(time_parts[1]))
                )
                return self._make_timezone_aware(dt)
        except (ValueError, IndexError, AttributeError):
            pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("feeding", {})["dinner_time"] = value.strftime("%H:%M")
        await self.coordinator.async_request_refresh()


# Walk DateTime Entities
class PawControlLastWalkDateTime(PawControlDateTimeBase):
    """DateTime entity for last walk."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_walk_datetime"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzter Spaziergang"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:dog-service"

    @property
    def native_value(self):
        """Return the current value."""
        last_walk = self.coordinator.data.get("status", {}).get("last_walk")
        if last_walk:
            try:
                dt = datetime.fromisoformat(last_walk)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("status", {})["last_walk"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlLastOutsideDateTime(PawControlDateTimeBase):
    """DateTime entity for last time outside."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_outside"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Zuletzt draußen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:nature"

    @property
    def native_value(self):
        """Return the current value."""
        last_outside = self.coordinator.data.get("activity", {}).get("last_outside")
        if last_outside:
            try:
                dt = datetime.fromisoformat(last_outside)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("activity", {})["last_outside"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlLastPlayDateTime(PawControlDateTimeBase):
    """DateTime entity for last playtime."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_play"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letztes Spielen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:tennis-ball"

    @property
    def native_value(self):
        """Return the current value."""
        last_play = self.coordinator.data.get("activity", {}).get("last_play")
        if last_play:
            try:
                dt = datetime.fromisoformat(last_play)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("activity", {})["last_play"] = value.isoformat()
        await self.coordinator.async_request_refresh()


# Health DateTime Entities
class PawControlLastVetVisitDateTime(PawControlDateTimeBase):
    """DateTime entity for last vet visit."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_vet_visit"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzter Tierarztbesuch"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:hospital-box"

    @property
    def native_value(self):
        """Return the current value."""
        last_vet = self.coordinator.data.get("status", {}).get("last_vet_visit")
        if last_vet:
            try:
                dt = datetime.fromisoformat(last_vet)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("status", {})["last_vet_visit"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlNextVetAppointmentDateTime(PawControlDateTimeBase):
    """DateTime entity for next vet appointment."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_next_vet_appointment"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Nächster Tierarzttermin"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_CALENDAR

    @property
    def native_value(self):
        """Return the current value."""
        next_vet = self.coordinator.data.get("health", {}).get("next_vet_appointment")
        if next_vet:
            try:
                dt = datetime.fromisoformat(next_vet)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("health", {})["next_vet_appointment"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlLastMedicationDateTime(PawControlDateTimeBase):
    """DateTime entity for last medication."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_medication"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Medikation"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:pill"

    @property
    def native_value(self):
        """Return the current value."""
        last_med = self.coordinator.data.get("status", {}).get("last_medication")
        if last_med:
            try:
                dt = datetime.fromisoformat(last_med)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("status", {})["last_medication"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlLastWeightCheckDateTime(PawControlDateTimeBase):
    """DateTime entity for last weight check."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_weight_check"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Gewichtskontrolle"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:weight-kilogram"

    @property
    def native_value(self):
        """Return the current value."""
        last_weight = self.coordinator.data.get("health", {}).get("last_weight_check")
        if last_weight:
            try:
                dt = datetime.fromisoformat(last_weight)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("health", {})["last_weight_check"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlNextMedicationDateTime(PawControlDateTimeBase):
    """DateTime entity for next medication."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_next_medication"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Nächste Medikation"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:pill-multiple"

    @property
    def native_value(self):
        """Return the current value."""
        next_med = self.coordinator.data.get("health", {}).get("next_medication")
        if next_med:
            try:
                dt = datetime.fromisoformat(next_med)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("health", {})["next_medication"] = value.isoformat()
        await self.coordinator.async_request_refresh()


# Training DateTime Entities
class PawControlLastTrainingDateTime(PawControlDateTimeBase):
    """DateTime entity for last training."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_training"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letztes Training"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:whistle"

    @property
    def native_value(self):
        """Return the current value."""
        last_training = self.coordinator.data.get("status", {}).get("last_training")
        if last_training:
            try:
                dt = datetime.fromisoformat(last_training)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("status", {})["last_training"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlNextTrainingDateTime(PawControlDateTimeBase):
    """DateTime entity for next training."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_next_training"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Nächstes Training"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-check"

    @property
    def native_value(self):
        """Return the current value."""
        next_training = self.coordinator.data.get("training", {}).get("next_session")
        if next_training:
            try:
                dt = datetime.fromisoformat(next_training)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("training", {})["next_session"] = value.isoformat()
        await self.coordinator.async_request_refresh()


# Grooming DateTime Entities
class PawControlLastGroomingDateTime(PawControlDateTimeBase):
    """DateTime entity for last grooming."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_grooming"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Pflege"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:content-cut"

    @property
    def native_value(self):
        """Return the current value."""
        last_grooming = self.coordinator.data.get("status", {}).get("last_grooming")
        if last_grooming:
            try:
                dt = datetime.fromisoformat(last_grooming)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("status", {})["last_grooming"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlLastBathDateTime(PawControlDateTimeBase):
    """DateTime entity for last bath."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_bath"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letztes Bad"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:shower"

    @property
    def native_value(self):
        """Return the current value."""
        last_bath = self.coordinator.data.get("grooming", {}).get("last_bath")
        if last_bath:
            try:
                dt = datetime.fromisoformat(last_bath)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("grooming", {})["last_bath"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlLastNailTrimDateTime(PawControlDateTimeBase):
    """DateTime entity for last nail trim."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_nail_trim"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Krallenpflege"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:hand-saw"

    @property
    def native_value(self):
        """Return the current value."""
        last_nail = self.coordinator.data.get("grooming", {}).get("last_nail_trim")
        if last_nail:
            try:
                dt = datetime.fromisoformat(last_nail)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("grooming", {})["last_nail_trim"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlNextGroomingDateTime(PawControlDateTimeBase):
    """DateTime entity for next grooming."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_next_grooming"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Nächste Pflege"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-heart"

    @property
    def native_value(self):
        """Return the current value."""
        next_grooming = self.coordinator.data.get("grooming", {}).get("next_appointment")
        if next_grooming:
            try:
                dt = datetime.fromisoformat(next_grooming)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("grooming", {})["next_appointment"] = value.isoformat()
        await self.coordinator.async_request_refresh()


# Visitor DateTime Entities
class PawControlVisitorStartDateTime(PawControlDateTimeBase):
    """DateTime entity for visitor start."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_visitor_start"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Besucherbeginn"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:account-clock"

    @property
    def native_value(self):
        """Return the current value."""
        visitor_start = self.coordinator.data.get("status", {}).get("visitor_start")
        if visitor_start:
            try:
                dt = datetime.fromisoformat(visitor_start)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("status", {})["visitor_start"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlVisitorEndDateTime(PawControlDateTimeBase):
    """DateTime entity for visitor end."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_visitor_end"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Besucherende"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:account-clock-outline"

    @property
    def native_value(self):
        """Return the current value."""
        visitor_end = self.coordinator.data.get("status", {}).get("visitor_end")
        if visitor_end:
            try:
                dt = datetime.fromisoformat(visitor_end)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("status", {})["visitor_end"] = value.isoformat()
        await self.coordinator.async_request_refresh()


class PawControlEmergencyContactTimeDateTime(PawControlDateTimeBase):
    """DateTime entity for emergency contact time."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_emergency_contact_time"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Notfallkontaktzeit"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:phone-alert"

    @property
    def native_value(self):
        """Return the current value."""
        contact_time = self.coordinator.data.get("emergency", {}).get("last_contact")
        if contact_time:
            try:
                dt = datetime.fromisoformat(contact_time)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("emergency", {})["last_contact"] = value.isoformat()
        await self.coordinator.async_request_refresh()


# General DateTime Entities
class PawControlLastActivityDateTime(PawControlDateTimeBase):
    """DateTime entity for last activity."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_activity"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Aktivität"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:history"

    @property
    def native_value(self):
        """Return the current value."""
        last_activity = self.coordinator.data.get("activity", {}).get("last_activity")
        if last_activity:
            try:
                dt = datetime.fromisoformat(last_activity)
                return self._make_timezone_aware(dt)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the value."""
        self.coordinator._data.setdefault("activity", {})["last_activity"] = value.isoformat()
        await self.coordinator.async_request_refresh()
