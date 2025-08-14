"""Datetime platform for Paw Control integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Final

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.util import dt as dt_util

from .compat import DeviceInfo, EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .entity import PawControlEntityBase

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

PARALLEL_UPDATES: Final = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up datetime entities from a config entry."""
    coordinator = entry.runtime_data.coordinator

    if not coordinator.last_update_success:
        await coordinator.async_refresh()
        if not coordinator.last_update_success:
            raise PlatformNotReady

    entities = []
    dogs = entry.options.get(CONF_DOGS, [])

    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue

        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})

        # Health module datetime entities
        if modules.get(MODULE_HEALTH):
            entities.extend(
                [
                    NextMedicationDateTime(hass, coordinator, entry, dog_id, dog_name),
                    NextVetVisitDateTime(hass, coordinator, entry, dog_id, dog_name),
                    LastVaccinationDateTime(hass, coordinator, entry, dog_id, dog_name),
                ]
            )

        # Walk module datetime entities
        if modules.get(MODULE_WALK):
            entities.append(
                NextWalkReminderDateTime(hass, coordinator, entry, dog_id, dog_name)
            )

        # Feeding module datetime entities
        if modules.get(MODULE_FEEDING):
            entities.extend(
                [
                    NextFeedingDateTime(hass, coordinator, entry, dog_id, dog_name),
                    FeedingScheduleDateTime(
                        hass, coordinator, entry, dog_id, dog_name, "breakfast"
                    ),
                    FeedingScheduleDateTime(
                        hass, coordinator, entry, dog_id, dog_name, "lunch"
                    ),
                    FeedingScheduleDateTime(
                        hass, coordinator, entry, dog_id, dog_name, "dinner"
                    ),
                ]
            )

        # Grooming module datetime entities
        if modules.get(MODULE_GROOMING):
            entities.append(
                NextGroomingDateTime(hass, coordinator, entry, dog_id, dog_name)
            )

    # Global datetime entities
    entities.extend(
        [
            DailyResetDateTime(hass, coordinator, entry),
            WeeklyReportDateTime(hass, coordinator, entry),
        ]
    )

    async_add_entities(entities, update_before_add=True)


class PawControlDateTimeBase(PawControlEntityBase, DateTimeEntity):
    """Base class for Paw Control datetime entities."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: Any,
        entry: ConfigEntry,
        dog_id: str,
        entity_type: str,
        translation_key: str | None = None,
        icon: str = "mdi:calendar-clock",
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, entry, dog_id, entity_type, translation_key)
        self._attr_icon = icon
        self._stored_value: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        """Return the current datetime value."""
        # First check stored value
        if self._stored_value:
            return self._stored_value

        # Then check coordinator data
        dog_data = self.coordinator.get_dog_data(self.dog_id)
        if dog_data:
            value = dog_data.get("datetime_settings", {}).get(self._entity_type)
            if value:
                try:
                    return datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    pass

        return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the datetime value."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        self._stored_value = value

        # Update coordinator data
        dog_data = self.coordinator.get_dog_data(self.dog_id)
        if dog_data:
            dog_data.setdefault("datetime_settings", {})[self._entity_type] = (
                value.isoformat()
            )

        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()


class NextMedicationDateTime(PawControlDateTimeBase):
    """Datetime entity for next medication."""

    def __init__(self, hass, coordinator, entry, dog_id, dog_name):
        """Initialize the datetime entity."""
        self.hass = hass
        super().__init__(
            coordinator, entry, dog_id, "next_medication", "next_medication", "mdi:pill"
        )


class NextVetVisitDateTime(PawControlDateTimeBase):
    """Datetime entity for next vet visit."""

    def __init__(self, hass, coordinator, entry, dog_id, dog_name):
        """Initialize the datetime entity."""
        self.hass = hass
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "next_vet_visit",
            "next_vet_visit",
            "mdi:hospital-box",
        )


class LastVaccinationDateTime(PawControlDateTimeBase):
    """Datetime entity for last vaccination."""

    def __init__(self, hass, coordinator, entry, dog_id, dog_name):
        """Initialize the datetime entity."""
        self.hass = hass
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "last_vaccination",
            "last_vaccination",
            "mdi:needle",
        )


class NextWalkReminderDateTime(PawControlDateTimeBase):
    """Datetime entity for next walk reminder."""

    def __init__(self, hass, coordinator, entry, dog_id, dog_name):
        """Initialize the datetime entity."""
        self.hass = hass
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "next_walk_reminder",
            "next_walk_reminder",
            "mdi:dog-side",
        )


class NextFeedingDateTime(PawControlDateTimeBase):
    """Datetime entity for next feeding."""

    def __init__(self, hass, coordinator, entry, dog_id, dog_name):
        """Initialize the datetime entity."""
        self.hass = hass
        super().__init__(
            coordinator, entry, dog_id, "next_feeding", "next_feeding", "mdi:food-apple"
        )

    @property
    def native_value(self) -> datetime | None:
        """Calculate next feeding time based on schedule."""
        now = dt_util.now()
        dog_data = self.coordinator.get_dog_data(self.dog_id)

        if not dog_data:
            return None

        feeding_schedule = dog_data.get("feeding", {}).get("schedule", {})
        if not feeding_schedule:
            return None

        # Find next scheduled feeding
        next_feeding = None
        min_diff = timedelta(days=1)

        for meal, time_str in feeding_schedule.items():
            if not time_str:
                continue

            try:
                # Parse time string (HH:MM format)
                hour, minute = map(int, time_str.split(":"))
                feeding_time = now.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )

                # If time has passed today, check tomorrow
                if feeding_time <= now:
                    feeding_time += timedelta(days=1)

                diff = feeding_time - now
                if diff < min_diff:
                    min_diff = diff
                    next_feeding = feeding_time

            except (ValueError, AttributeError):
                continue

        return next_feeding


class FeedingScheduleDateTime(PawControlDateTimeBase):
    """Datetime entity for feeding schedule times."""

    def __init__(self, hass, coordinator, entry, dog_id, dog_name, meal_type):
        """Initialize the datetime entity."""
        self.hass = hass
        self._meal_type = meal_type
        super().__init__(
            coordinator,
            entry,
            dog_id,
            f"feeding_{meal_type}",
            f"feeding_{meal_type}",
            "mdi:clock-outline",
        )
        self._attr_name = f"{meal_type.capitalize()} Time"


class NextGroomingDateTime(PawControlDateTimeBase):
    """Datetime entity for next grooming."""

    def __init__(self, hass, coordinator, entry, dog_id, dog_name):
        """Initialize the datetime entity."""
        self.hass = hass
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "next_grooming",
            "next_grooming",
            "mdi:content-cut",
        )


class DailyResetDateTime(DateTimeEntity):
    """Global datetime entity for daily reset time."""

    _attr_has_entity_name = True
    _attr_name = "Daily Reset Time"
    _attr_icon = "mdi:restart"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass, coordinator, entry):
        """Initialize the datetime entity."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_daily_reset_time"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the daily reset time."""
        reset_time = self.entry.options.get("reset_time", "00:00")
        try:
            hour, minute = map(int, reset_time.split(":"))
            now = dt_util.now()
            reset_datetime = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if reset_datetime < now:
                reset_datetime += timedelta(days=1)
            return reset_datetime
        except (ValueError, AttributeError):
            return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the daily reset time."""
        # Update config entry options
        time_str = value.strftime("%H:%M")
        _LOGGER.info("Daily reset time updated to %s", time_str)
        # Would update the config entry options here
        self.async_write_ha_state()


class WeeklyReportDateTime(DateTimeEntity):
    """Global datetime entity for weekly report generation."""

    _attr_has_entity_name = True
    _attr_name = "Weekly Report Time"
    _attr_icon = "mdi:file-document-clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass, coordinator, entry):
        """Initialize the datetime entity."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_weekly_report_time"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )
        self._stored_value = None

    @property
    def native_value(self) -> datetime | None:
        """Return the weekly report time."""
        if self._stored_value:
            return self._stored_value

        # Default to Sunday at 20:00
        now = dt_util.now()
        days_ahead = 6 - now.weekday()  # Sunday is 6
        if days_ahead <= 0:
            days_ahead += 7

        report_time = now + timedelta(days=days_ahead)
        report_time = report_time.replace(hour=20, minute=0, second=0, microsecond=0)
        return report_time

    async def async_set_value(self, value: datetime) -> None:
        """Set the weekly report time."""
        self._stored_value = value
        _LOGGER.info("Weekly report time updated to %s", value.isoformat())
        self.async_write_ha_state()
