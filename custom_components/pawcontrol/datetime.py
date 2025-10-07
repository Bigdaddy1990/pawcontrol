"""DateTime platform for Paw Control integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry
from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .entity import PawControlEntity
from .runtime_data import get_runtime_data
from .utils import async_call_add_entities, ensure_utc_datetime

_LOGGER = logging.getLogger(__name__)

# Date/time helpers write settings back to Paw Control. The coordinator
# serialises writes, so we lift the entity-level cap and let Home Assistant run
# updates in parallel when possible.
PARALLEL_UPDATES = 0


async def _async_add_entities_in_batches(
    async_add_entities_func,
    entities,
    batch_size: int = 12,
    delay_between_batches: float = 0.1,
) -> None:
    """Add datetime entities in small batches to prevent Entity Registry overload.

    The Entity Registry logs warnings when >200 messages occur rapidly.
    By batching entities and adding delays, we prevent registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of datetime entities to add
        batch_size: Number of entities per batch (default: 12)
        delay_between_batches: Seconds to wait between batches (default: 0.1s)
    """
    total_entities = len(entities)

    _LOGGER.debug(
        "Adding %d datetime entities in batches of %d to prevent Registry overload",
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
        batch = entities[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            "Processing datetime batch %d/%d with %d entities",
            batch_num,
            total_batches,
            len(batch),
        )

        # Add batch without update_before_add to reduce Registry load
        await async_call_add_entities(
            async_add_entities_func, batch, update_before_add=False
        )

        # Small delay between batches to prevent Registry flooding
        if i + batch_size < total_entities:  # No delay after last batch
            await asyncio.sleep(delay_between_batches)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control datetime platform."""
    runtime_data = get_runtime_data(hass, entry)
    if runtime_data is None:
        _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
        return

    coordinator: PawControlCoordinator = runtime_data.coordinator
    dogs = runtime_data.dogs

    entities = []

    for dog in dogs:
        dog_id = dog[CONF_DOG_ID]
        dog_name = dog[CONF_DOG_NAME]
        modules = dog.get("modules", {})

        # Basic dog datetime entities
        entities.extend(
            [
                PawControlBirthdateDateTime(coordinator, dog_id, dog_name),
                PawControlAdoptionDateDateTime(coordinator, dog_id, dog_name),
            ]
        )

        # Feeding datetime entities
        if modules.get(MODULE_FEEDING, False):
            entities.extend(
                [
                    PawControlBreakfastTimeDateTime(coordinator, dog_id, dog_name),
                    PawControlLunchTimeDateTime(coordinator, dog_id, dog_name),
                    PawControlDinnerTimeDateTime(coordinator, dog_id, dog_name),
                    PawControlLastFeedingDateTime(coordinator, dog_id, dog_name),
                    PawControlNextFeedingDateTime(coordinator, dog_id, dog_name),
                ]
            )

        # Health datetime entities
        if modules.get(MODULE_HEALTH, False):
            entities.extend(
                [
                    PawControlLastVetVisitDateTime(coordinator, dog_id, dog_name),
                    PawControlNextVetAppointmentDateTime(coordinator, dog_id, dog_name),
                    PawControlLastGroomingDateTime(coordinator, dog_id, dog_name),
                    PawControlNextGroomingDateTime(coordinator, dog_id, dog_name),
                    PawControlLastMedicationDateTime(coordinator, dog_id, dog_name),
                    PawControlNextMedicationDateTime(coordinator, dog_id, dog_name),
                ]
            )

        # Walk datetime entities
        if modules.get(MODULE_WALK, False):
            entities.extend(
                [
                    PawControlLastWalkDateTime(coordinator, dog_id, dog_name),
                    PawControlNextWalkReminderDateTime(coordinator, dog_id, dog_name),
                ]
            )

    # Add entities in smaller batches to prevent Entity Registry overload
    # With 48+ datetime entities (2 dogs), batching prevents Registry flooding
    await _async_add_entities_in_batches(async_add_entities, entities, batch_size=12)

    _LOGGER.info(
        "Created %d datetime entities for %d dogs using batched approach",
        len(entities),
        len(dogs),
    )


class PawControlDateTimeBase(PawControlEntity, DateTimeEntity, RestoreEntity):
    """Base class for Paw Control datetime entities."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        datetime_type: str,
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name)
        self._datetime_type = datetime_type
        self._current_value: datetime | None = None

        self._attr_unique_id = f"pawcontrol_{dog_id}_{datetime_type}"
        self._apply_name_suffix(datetime_type.replace("_", " ").title())

        # Link entity to PawControl device entry for the dog
        self.update_device_metadata(
            model="Smart Dog",
            sw_version="1.0.0",
            configuration_url="https://github.com/BigDaddy1990/pawcontrol",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the current datetime value."""
        return self._current_value

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return extra state attributes."""
        return {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "datetime_type": self._datetime_type,
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous value
        if (last_state := await self.async_get_last_state()) is not None:  # noqa: SIM102
            if last_state.state not in ("unknown", "unavailable"):
                self._current_value = ensure_utc_datetime(last_state.state)

    async def async_set_value(self, value: datetime) -> None:
        """Set new datetime value."""
        self._current_value = value
        self.async_write_ha_state()
        _LOGGER.debug("Set %s for %s to %s", self._datetime_type, self._dog_name, value)


class PawControlBirthdateDateTime(PawControlDateTimeBase):
    """DateTime entity for dog birthdate."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "birthdate")
        self._attr_icon = "mdi:cake"

    async def async_set_value(self, value: datetime) -> None:
        """Set new birthdate and update age calculation."""
        await super().async_set_value(value)

        # Calculate and update age
        now = dt_util.now()
        age_years = (now - value).days / 365.25

        # This could update the dog age number entity
        _LOGGER.debug(
            "Updated birthdate for %s, calculated age: %.1f years",
            self._dog_name,
            age_years,
        )


class PawControlAdoptionDateDateTime(PawControlDateTimeBase):
    """DateTime entity for adoption date."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "adoption_date")
        self._attr_icon = "mdi:home-heart"


class PawControlBreakfastTimeDateTime(PawControlDateTimeBase):
    """DateTime entity for breakfast time."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "breakfast_time")
        self._attr_icon = "mdi:food-croissant"

        # Set default breakfast time
        now = dt_util.now()
        default_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        self._current_value = default_time


class PawControlLunchTimeDateTime(PawControlDateTimeBase):
    """DateTime entity for lunch time."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "lunch_time")
        self._attr_icon = "mdi:food"

        # Set default lunch time
        now = dt_util.now()
        default_time = now.replace(hour=13, minute=0, second=0, microsecond=0)
        self._current_value = default_time


class PawControlDinnerTimeDateTime(PawControlDateTimeBase):
    """DateTime entity for dinner time."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "dinner_time")
        self._attr_icon = "mdi:silverware-fork-knife"

        # Set default dinner time
        now = dt_util.now()
        default_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        self._current_value = default_time


class PawControlLastFeedingDateTime(PawControlDateTimeBase):
    """DateTime entity for last feeding (read-only)."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "last_feeding")
        self._attr_icon = "mdi:food-drumstick"

    @property
    def native_value(self) -> datetime | None:
        """Return the last feeding time from dog data."""
        dog_data = self.coordinator.get_dog_data(self._dog_id)
        if not dog_data or "feeding" not in dog_data:
            return self._current_value

        last_feeding = dog_data["feeding"].get("last_feeding")
        if last_feeding:
            timestamp = ensure_utc_datetime(last_feeding)
            if timestamp is not None:
                return timestamp

        return self._current_value

    async def async_set_value(self, value: datetime) -> None:
        """Set last feeding time and log feeding."""
        await super().async_set_value(value)

        # Log feeding event
        await self.hass.services.async_call(
            DOMAIN,
            "feed_dog",
            {
                ATTR_DOG_ID: self._dog_id,
                "meal_type": "snack",  # Default to snack for manual entries
            },
        )


class PawControlNextFeedingDateTime(PawControlDateTimeBase):
    """DateTime entity for next feeding reminder."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "next_feeding")
        self._attr_icon = "mdi:clock-alert"

    async def async_set_value(self, value: datetime) -> None:
        """Set next feeding reminder time."""
        await super().async_set_value(value)

        # This could schedule a reminder automation
        _LOGGER.debug("Next feeding reminder set for %s at %s", self._dog_name, value)


class PawControlLastVetVisitDateTime(PawControlDateTimeBase):
    """DateTime entity for last vet visit."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "last_vet_visit")
        self._attr_icon = "mdi:medical-bag"

    @property
    def native_value(self) -> datetime | None:
        """Return the last vet visit from dog data."""
        dog_data = self.coordinator.get_dog_data(self._dog_id)
        if not dog_data or "health" not in dog_data:
            return self._current_value

        last_visit = dog_data["health"].get("last_vet_visit")
        if last_visit:
            timestamp = ensure_utc_datetime(last_visit)
            if timestamp is not None:
                return timestamp

        return self._current_value

    async def async_set_value(self, value: datetime) -> None:
        """Set last vet visit and log health data."""
        await super().async_set_value(value)

        # Log vet visit
        await self.hass.services.async_call(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: self._dog_id,
                "note": f"Vet visit recorded for {value.strftime('%Y-%m-%d')}",
            },
        )


class PawControlNextVetAppointmentDateTime(PawControlDateTimeBase):
    """DateTime entity for next vet appointment."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "next_vet_appointment")
        self._attr_icon = "mdi:calendar-medical"

    async def async_set_value(self, value: datetime) -> None:
        """Set next vet appointment."""
        await super().async_set_value(value)

        # This could create calendar event or reminder
        _LOGGER.debug(
            "Next vet appointment scheduled for %s at %s", self._dog_name, value
        )


class PawControlLastGroomingDateTime(PawControlDateTimeBase):
    """DateTime entity for last grooming session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "last_grooming")
        self._attr_icon = "mdi:content-cut"

    @property
    def native_value(self) -> datetime | None:
        """Return the last grooming from dog data."""
        dog_data = self.coordinator.get_dog_data(self._dog_id)
        if not dog_data or "health" not in dog_data:
            return self._current_value

        last_grooming = dog_data["health"].get("last_grooming")
        if last_grooming:
            timestamp = ensure_utc_datetime(last_grooming)
            if timestamp is not None:
                return timestamp

        return self._current_value

    async def async_set_value(self, value: datetime) -> None:
        """Set last grooming and log grooming session."""
        await super().async_set_value(value)

        # Log grooming session
        await self.hass.services.async_call(
            DOMAIN,
            "start_grooming",
            {
                ATTR_DOG_ID: self._dog_id,
                "type": "full_grooming",
                "notes": f"Grooming session on {value.strftime('%Y-%m-%d')}",
            },
        )


class PawControlNextGroomingDateTime(PawControlDateTimeBase):
    """DateTime entity for next grooming appointment."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "next_grooming")
        self._attr_icon = "mdi:calendar-clock"


class PawControlLastMedicationDateTime(PawControlDateTimeBase):
    """DateTime entity for last medication."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "last_medication")
        self._attr_icon = "mdi:pill"

    async def async_set_value(self, value: datetime) -> None:
        """Set last medication and log medication."""
        await super().async_set_value(value)

        # Log medication
        await self.hass.services.async_call(
            DOMAIN,
            "log_medication",
            {
                ATTR_DOG_ID: self._dog_id,
                "medication_name": "Manual Entry",
                "dose": "As scheduled",
            },
        )


class PawControlNextMedicationDateTime(PawControlDateTimeBase):
    """DateTime entity for next medication reminder."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "next_medication")
        self._attr_icon = "mdi:alarm-plus"

    async def async_set_value(self, value: datetime) -> None:
        """Set next medication reminder."""
        await super().async_set_value(value)

        # This could schedule medication reminder
        _LOGGER.debug(
            "Next medication reminder set for %s at %s", self._dog_name, value
        )


class PawControlLastWalkDateTime(PawControlDateTimeBase):
    """DateTime entity for last walk."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "last_walk")
        self._attr_icon = "mdi:walk"

    @property
    def native_value(self) -> datetime | None:
        """Return the last walk from dog data."""
        dog_data = self.coordinator.get_dog_data(self._dog_id)
        if not dog_data or "walk" not in dog_data:
            return self._current_value

        last_walk = dog_data["walk"].get("last_walk")
        if last_walk:
            timestamp = ensure_utc_datetime(last_walk)
            if timestamp is not None:
                return timestamp

        return self._current_value

    async def async_set_value(self, value: datetime) -> None:
        """Set last walk time and log walk."""
        await super().async_set_value(value)

        # Start and immediately end a walk for historical entry
        await self.hass.services.async_call(
            DOMAIN,
            "start_walk",
            {ATTR_DOG_ID: self._dog_id},
        )

        # End the walk
        await self.hass.services.async_call(
            DOMAIN,
            "end_walk",
            {ATTR_DOG_ID: self._dog_id},
        )


class PawControlNextWalkReminderDateTime(PawControlDateTimeBase):
    """DateTime entity for next walk reminder."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "next_walk_reminder")
        self._attr_icon = "mdi:bell-ring"

    async def async_set_value(self, value: datetime) -> None:
        """Set next walk reminder."""
        await super().async_set_value(value)

        # This could schedule walk reminder
        _LOGGER.debug("Next walk reminder set for %s at %s", self._dog_name, value)


class PawControlVaccinationDateDateTime(PawControlDateTimeBase):
    """DateTime entity for vaccination dates."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "vaccination_date")
        self._attr_icon = "mdi:needle"

    async def async_set_value(self, value: datetime) -> None:
        """Set vaccination date and log health data."""
        await super().async_set_value(value)

        # Log vaccination
        await self.hass.services.async_call(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: self._dog_id,
                "note": f"Vaccination recorded for {value.strftime('%Y-%m-%d')}",
            },
        )


class PawControlTrainingSessionDateTime(PawControlDateTimeBase):
    """DateTime entity for training sessions."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "training_session")
        self._attr_icon = "mdi:school"

    async def async_set_value(self, value: datetime) -> None:
        """Set training session date."""
        await super().async_set_value(value)

        # Log training session
        await self.hass.services.async_call(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: self._dog_id,
                "note": f"Training session on {value.strftime('%Y-%m-%d')}",
            },
        )


class PawControlEmergencyDateTime(PawControlDateTimeBase):
    """DateTime entity for emergency events."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the datetime entity."""
        super().__init__(coordinator, dog_id, dog_name, "emergency_date")
        self._attr_icon = "mdi:alert"

    async def async_set_value(self, value: datetime) -> None:
        """Set emergency date and log critical health data."""
        await super().async_set_value(value)

        # Log emergency event
        await self.hass.services.async_call(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: self._dog_id,
                "note": f"EMERGENCY EVENT recorded for {value.strftime('%Y-%m-%d %H:%M')}",
            },
        )

        # Send urgent notification
        runtime_data = get_runtime_data(self.hass, self.coordinator.config_entry)
        notification_manager = getattr(runtime_data, "notification_manager", None)
        if notification_manager:
            await notification_manager.async_send_notification(
                self._dog_id,
                "🚨 Emergency Event Logged",
                f"Emergency event logged for {self._dog_name} on {value.strftime('%Y-%m-%d %H:%M')}",
                priority="urgent",
            )
