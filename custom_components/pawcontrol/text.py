"""Text platform for Paw Control integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.components.text import TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_DOG_ID
from .const import ATTR_DOG_NAME
from .const import CONF_DOG_ID
from .const import CONF_DOG_NAME
from .const import CONF_DOGS
from .const import DOMAIN
from .const import MODULE_HEALTH
from .const import MODULE_NOTIFICATIONS
from .const import MODULE_WALK
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def _async_add_entities_in_batches(
    async_add_entities_func,
    entities,
    batch_size: int = 8,
    delay_between_batches: float = 0.1,
) -> None:
    """Add text entities in small batches to prevent Entity Registry overload.

    The Entity Registry logs warnings when >200 messages occur rapidly.
    By batching entities and adding delays, we prevent registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of text entities to add
        batch_size: Number of entities per batch (default: 8)
        delay_between_batches: Seconds to wait between batches (default: 0.1s)
    """
    total_entities = len(entities)

    _LOGGER.debug(
        "Adding %d text entities in batches of %d to prevent Registry overload",
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
        batch = entities[i: i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            "Processing text batch %d/%d with %d entities",
            batch_num,
            total_batches,
            len(batch),
        )

        # Add batch without update_before_add to reduce Registry load
        async_add_entities_func(batch, update_before_add=False)

        # Small delay between batches to prevent Registry flooding
        if i + batch_size < total_entities:  # No delay after last batch
            await asyncio.sleep(delay_between_batches)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control text platform."""
    runtime_data = getattr(entry, "runtime_data", None)

    if runtime_data:
        coordinator: PawControlCoordinator = runtime_data["coordinator"]
        dogs = runtime_data.get("dogs", [])
    else:
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        dogs = entry.data.get(CONF_DOGS, [])

    entities = []

    for dog in dogs:
        dog_id = dog[CONF_DOG_ID]
        dog_name = dog[CONF_DOG_NAME]
        modules = dog.get("modules", {})

        # Basic dog configuration texts
        entities.extend(
            [
                PawControlDogNotesText(coordinator, dog_id, dog_name),
                PawControlCustomLabelText(coordinator, dog_id, dog_name),
            ]
        )

        # Walk texts
        if modules.get(MODULE_WALK, False):
            entities.extend(
                [
                    PawControlWalkNotesText(coordinator, dog_id, dog_name),
                    PawControlCurrentWalkLabelText(
                        coordinator, dog_id, dog_name),
                ]
            )

        # Health texts
        if modules.get(MODULE_HEALTH, False):
            entities.extend(
                [
                    PawControlHealthNotesText(coordinator, dog_id, dog_name),
                    PawControlMedicationNotesText(
                        coordinator, dog_id, dog_name),
                    PawControlVetNotesText(coordinator, dog_id, dog_name),
                    PawControlGroomingNotesText(coordinator, dog_id, dog_name),
                ]
            )

        # Notification texts
        if modules.get(MODULE_NOTIFICATIONS, False):
            entities.extend(
                [
                    PawControlCustomMessageText(coordinator, dog_id, dog_name),
                    PawControlEmergencyContactText(
                        coordinator, dog_id, dog_name),
                ]
            )

    # Add entities in smaller batches to prevent Entity Registry overload
    # With 24+ text entities (2 dogs), batching prevents Registry flooding
    await _async_add_entities_in_batches(async_add_entities, entities, batch_size=8)

    _LOGGER.info(
        "Created %d text entities for %d dogs using batched approach",
        len(entities),
        len(dogs),
    )


class PawControlTextBase(
    CoordinatorEntity[PawControlCoordinator], TextEntity, RestoreEntity
):
    """Base class for Paw Control text entities."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        text_type: str,
        max_length: int = 255,
        mode: TextMode = TextMode.TEXT,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator)
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._text_type = text_type
        self._current_value: str = ""

        self._attr_unique_id = f"pawcontrol_{dog_id}_{text_type}"
        self._attr_name = f"{dog_name} {text_type.replace('_', ' ').title()}"
        self._attr_native_max = max_length
        self._attr_mode = mode

        # Device info - HA 2025.8+ compatible with configuration_url
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog_id)},
            "name": dog_name,
            "manufacturer": "Paw Control",
            "model": "Smart Dog",
            "sw_version": "1.0.0",
            "configuration_url": "https://github.com/BigDaddy1990/pawcontrol",
        }

    @property
    def native_value(self) -> str:
        """Return the current value."""
        return self._current_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "text_type": self._text_type,
            "character_count": len(self._current_value),
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous value
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in ("unknown", "unavailable"):
                self._current_value = last_state.state

    async def async_set_value(self, value: str) -> None:
        """Set new value."""
        if len(value) > self.native_max:
            value = value[: self.native_max]

        self._current_value = value
        self.async_write_ha_state()
        _LOGGER.debug(
            "Set %s for %s to: %s", self._text_type, self._dog_name, value[:50]
        )


class PawControlDogNotesText(PawControlTextBase):
    """Text entity for general dog notes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "notes", max_length=1000, mode=TextMode.TEXT
        )
        self._attr_icon = "mdi:note-text"

    async def async_set_value(self, value: str) -> None:
        """Set new notes value."""
        await super().async_set_value(value)

        # Log notes update as health data if meaningful content
        if len(value.strip()) > 10:
            await self.hass.services.async_call(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": f"Notes updated: {value[:100]}",
                },
            )


class PawControlCustomLabelText(PawControlTextBase):
    """Text entity for custom dog label."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator, dog_id, dog_name, "custom_label", max_length=50)
        self._attr_icon = "mdi:label"


class PawControlWalkNotesText(PawControlTextBase):
    """Text entity for walk notes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walk_notes",
            max_length=500,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:walk"

    async def async_set_value(self, value: str) -> None:
        """Set new walk notes."""
        await super().async_set_value(value)

        # Add notes to current walk if one is active
        dog_data = self.coordinator.get_dog_data(self._dog_id)
        if dog_data and dog_data.get("walk", {}).get("walk_in_progress", False):
            _LOGGER.debug("Added notes to active walk for %s", self._dog_name)


class PawControlCurrentWalkLabelText(PawControlTextBase):
    """Text entity for current walk label."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "current_walk_label", max_length=100
        )
        self._attr_icon = "mdi:tag"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dog_data = self.coordinator.get_dog_data(self._dog_id)
        if not dog_data:
            return False

        # Only available when walk is in progress
        return dog_data.get("walk", {}).get("walk_in_progress", False)


class PawControlHealthNotesText(PawControlTextBase):
    """Text entity for health notes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_notes",
            max_length=1000,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:heart-pulse"

    async def async_set_value(self, value: str) -> None:
        """Set new health notes."""
        await super().async_set_value(value)

        # Log health notes
        if value.strip():
            await self.hass.services.async_call(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": value,
                },
            )


class PawControlMedicationNotesText(PawControlTextBase):
    """Text entity for medication notes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "medication_notes",
            max_length=500,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:pill"

    async def async_set_value(self, value: str) -> None:
        """Set new medication notes."""
        await super().async_set_value(value)

        # Log medication if notes contain meaningful information
        if value.strip() and len(value.strip()) > 5:
            await self.hass.services.async_call(
                DOMAIN,
                "log_medication",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "medication_name": "Manual Entry",
                    "dose": value,
                },
            )


class PawControlVetNotesText(PawControlTextBase):
    """Text entity for veterinary notes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "vet_notes",
            max_length=1000,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:medical-bag"

    async def async_set_value(self, value: str) -> None:
        """Set new vet notes."""
        await super().async_set_value(value)

        # Log as health data with vet context
        if value.strip():
            await self.hass.services.async_call(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": f"Vet notes: {value}",
                },
            )


class PawControlGroomingNotesText(PawControlTextBase):
    """Text entity for grooming notes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "grooming_notes",
            max_length=500,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:content-cut"

    async def async_set_value(self, value: str) -> None:
        """Set new grooming notes."""
        await super().async_set_value(value)

        # Start grooming session if notes are added
        if value.strip() and len(value.strip()) > 10:
            await self.hass.services.async_call(
                DOMAIN,
                "start_grooming",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "type": "brush",
                    "notes": value,
                },
            )


class PawControlCustomMessageText(PawControlTextBase):
    """Text entity for custom notification message."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "custom_message",
            max_length=300,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:message-text"

    async def async_set_value(self, value: str) -> None:
        """Set new custom message and send notification."""
        await super().async_set_value(value)

        # Send custom message as notification if not empty
        if value.strip():
            await self.hass.services.async_call(
                DOMAIN,
                "notify_test",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "message": value,
                },
            )


class PawControlEmergencyContactText(PawControlTextBase):
    """Text entity for emergency contact information."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "emergency_contact",
            max_length=200,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:phone-alert"


class PawControlMicrochipText(PawControlTextBase):
    """Text entity for microchip number."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator, dog_id, dog_name, "microchip", max_length=20)
        self._attr_icon = "mdi:chip"
        self._attr_mode = TextMode.PASSWORD  # Hide microchip number


class PawControlBreederInfoText(PawControlTextBase):
    """Text entity for breeder information."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "breeder_info",
            max_length=300,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:account-group"


class PawControlRegistrationText(PawControlTextBase):
    """Text entity for registration information."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator, dog_id, dog_name, "registration", max_length=100)
        self._attr_icon = "mdi:certificate"


class PawControlInsuranceText(PawControlTextBase):
    """Text entity for insurance information."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "insurance_info",
            max_length=300,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:shield-account"


class PawControlAllergiesText(PawControlTextBase):
    """Text entity for allergies and restrictions."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "allergies",
            max_length=500,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:alert-circle"

    async def async_set_value(self, value: str) -> None:
        """Set new allergies information."""
        await super().async_set_value(value)

        # Log allergies as important health data
        if value.strip():
            await self.hass.services.async_call(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": f"Allergies/Restrictions updated: {value}",
                },
            )


class PawControlTrainingNotesText(PawControlTextBase):
    """Text entity for training notes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "training_notes",
            max_length=1000,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:school"


class PawControlBehaviorNotesText(PawControlTextBase):
    """Text entity for behavior notes."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "behavior_notes",
            max_length=1000,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:emoticon-happy"

    async def async_set_value(self, value: str) -> None:
        """Set new behavior notes."""
        await super().async_set_value(value)

        # Log behavior changes as health data
        if value.strip() and len(value.strip()) > 10:
            await self.hass.services.async_call(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": f"Behavior notes: {value}",
                },
            )


class PawControlLocationDescriptionText(PawControlTextBase):
    """Text entity for custom location description."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "location_description",
            max_length=200,
            mode=TextMode.TEXT,
        )
        self._attr_icon = "mdi:map-marker-outline"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dog_data = self.coordinator.get_dog_data(self._dog_id)
        if not dog_data:
            return False

        # Available when GPS module is enabled
        dog_info = self.coordinator.get_dog_info(self._dog_id)
        if not dog_info:
            return False

        modules = dog_info.get("modules", {})
        return modules.get("gps", False)
