"""Button platform for Paw Control integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .compat import EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_TRAINING,
    MODULE_WALK,
)
from .entity import PawControlButtonEntity

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control button entities."""
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

        modules = dog.get(CONF_DOG_MODULES, {})

        # Walk module buttons
        if modules.get(MODULE_WALK):
            entities.extend(
                [
                    StartWalkButton(hass, coordinator, entry, dog_id),
                    EndWalkButton(hass, coordinator, entry, dog_id),
                    QuickWalkButton(hass, coordinator, entry, dog_id),
                ]
            )

        # Feeding module buttons
        if modules.get(MODULE_FEEDING):
            entities.extend(
                [
                    FeedBreakfastButton(hass, coordinator, entry, dog_id),
                    FeedLunchButton(hass, coordinator, entry, dog_id),
                    FeedDinnerButton(hass, coordinator, entry, dog_id),
                    FeedSnackButton(hass, coordinator, entry, dog_id),
                ]
            )

        # Health module buttons
        if modules.get(MODULE_HEALTH):
            entities.extend(
                [
                    LogWeightButton(hass, coordinator, entry, dog_id),
                    GiveMedicationButton(hass, coordinator, entry, dog_id),
                ]
            )

        # Grooming module buttons
        if modules.get(MODULE_GROOMING):
            entities.extend(
                [
                    GroomBathButton(hass, coordinator, entry, dog_id),
                    GroomBrushButton(hass, coordinator, entry, dog_id),
                    GroomNailsButton(hass, coordinator, entry, dog_id),
                ]
            )

        # Training module buttons
        if modules.get(MODULE_TRAINING):
            entities.extend(
                [
                    StartTrainingButton(hass, coordinator, entry, dog_id),
                    LogPlaySessionButton(hass, coordinator, entry, dog_id),
                ]
            )

        # Notification test button
        if modules.get(MODULE_NOTIFICATIONS):
            entities.append(NotifyTestButton(hass, coordinator, entry, dog_id))

        # Always add poop tracking button
        entities.append(LogPoopButton(hass, coordinator, entry, dog_id))

    # Global buttons
    entities.extend(
        [
            DailyResetButton(hass, coordinator, entry),
            GenerateReportButton(hass, coordinator, entry),
            SyncSetupButton(hass, coordinator, entry),
        ]
    )

    async_add_entities(entities, True)


class StartWalkButton(PawControlButtonEntity, ButtonEntity):
    """Button to start a walk."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "start_walk", translation_key="start_walk"
        )
        self.hass = hass
        self._attr_icon = "mdi:dog-side"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_walk",
            {"dog_id": self.dog_id, "source": "manual"},
            blocking=False,
        )


class EndWalkButton(PawControlButtonEntity, ButtonEntity):
    """Button to end a walk."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "end_walk", translation_key="end_walk"
        )
        self.hass = hass
        self._attr_icon = "mdi:home"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "end_walk",
            {"dog_id": self.dog_id, "reason": "manual"},
            blocking=False,
        )


class QuickWalkButton(PawControlButtonEntity, ButtonEntity):
    """Button to log a quick walk."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "quick_walk", translation_key="quick_walk"
        )
        self.hass = hass
        self._attr_icon = "mdi:walk"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "walk_dog",
            {
                "dog_id": self.dog_id,
                "duration_min": 30,
                "distance_m": 1000,
            },
            blocking=False,
        )


class FeedBreakfastButton(PawControlButtonEntity, ButtonEntity):
    """Button to log breakfast feeding."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "feed_breakfast", translation_key="feed_breakfast"
        )
        self.hass = hass
        self._attr_icon = "mdi:food-apple"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "feed_dog",
            {
                "dog_id": self.dog_id,
                "meal_type": "breakfast",
                "portion_g": 200,
                "food_type": "dry",
            },
            blocking=False,
        )


class FeedLunchButton(PawControlButtonEntity, ButtonEntity):
    """Button to log lunch feeding."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "feed_lunch", translation_key="feed_lunch"
        )
        self.hass = hass
        self._attr_icon = "mdi:food"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "feed_dog",
            {
                "dog_id": self.dog_id,
                "meal_type": "lunch",
                "portion_g": 150,
                "food_type": "wet",
            },
            blocking=False,
        )


class FeedDinnerButton(PawControlButtonEntity, ButtonEntity):
    """Button to log dinner feeding."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "feed_dinner", translation_key="feed_dinner"
        )
        self.hass = hass
        self._attr_icon = "mdi:food-variant"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "feed_dog",
            {
                "dog_id": self.dog_id,
                "meal_type": "dinner",
                "portion_g": 200,
                "food_type": "dry",
            },
            blocking=False,
        )


class FeedSnackButton(PawControlButtonEntity, ButtonEntity):
    """Button to log snack feeding."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "feed_snack", translation_key="feed_snack"
        )
        self.hass = hass
        self._attr_icon = "mdi:cookie"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "feed_dog",
            {
                "dog_id": self.dog_id,
                "meal_type": "snack",
                "portion_g": 50,
                "food_type": "treat",
            },
            blocking=False,
        )


class LogWeightButton(PawControlButtonEntity, ButtonEntity):
    """Button to log weight."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "log_weight", translation_key="log_weight"
        )
        self.hass = hass
        self._attr_icon = "mdi:weight"

    async def async_press(self) -> None:
        """Handle button press."""
        # In a real implementation, this would open a dialog to enter weight
        _LOGGER.info(f"Weight logging requested for {self.dog_name}")


class GiveMedicationButton(PawControlButtonEntity, ButtonEntity):
    """Button to log medication."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "give_medication", translation_key="give_medication"
        )
        self.hass = hass
        self._attr_icon = "mdi:pill"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "log_medication",
            {
                "dog_id": self.dog_id,
                "medication_name": "Daily Supplement",
                "dose": "1 tablet",
            },
            blocking=False,
        )


class GroomBathButton(PawControlButtonEntity, ButtonEntity):
    """Button to log bath grooming."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "groom_bath", translation_key="groom_bath"
        )
        self.hass = hass
        self._attr_icon = "mdi:shower"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_grooming",
            {
                "dog_id": self.dog_id,
                "type": "bath",
                "notes": "Full bath with shampoo",
            },
            blocking=False,
        )


class GroomBrushButton(PawControlButtonEntity, ButtonEntity):
    """Button to log brush grooming."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "groom_brush", translation_key="groom_brush"
        )
        self.hass = hass
        self._attr_icon = "mdi:brush"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_grooming",
            {
                "dog_id": self.dog_id,
                "type": "brush",
                "notes": "Regular brushing",
            },
            blocking=False,
        )


class GroomNailsButton(PawControlButtonEntity, ButtonEntity):
    """Button to log nail grooming."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "groom_nails", translation_key="groom_nails"
        )
        self.hass = hass
        self._attr_icon = "mdi:content-cut"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_grooming",
            {
                "dog_id": self.dog_id,
                "type": "nails",
                "notes": "Nail trimming",
            },
            blocking=False,
        )


class StartTrainingButton(PawControlButtonEntity, ButtonEntity):
    """Button to start training session."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "start_training", translation_key="start_training"
        )
        self.hass = hass
        self._attr_icon = "mdi:school"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "training_session",
            {
                "dog_id": self.dog_id,
                "topic": "Basic Commands",
                "duration_min": 15,
                "notes": "Sit, stay, come practice",
            },
            blocking=False,
        )


class LogPlaySessionButton(PawControlButtonEntity, ButtonEntity):
    """Button to log play session."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "log_play", translation_key="log_play"
        )
        self.hass = hass
        self._attr_icon = "mdi:tennis-ball"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "play_session",
            {
                "dog_id": self.dog_id,
                "duration_min": 20,
                "intensity": "medium",
            },
            blocking=False,
        )


class LogPoopButton(PawControlButtonEntity, ButtonEntity):
    """Button to log poop."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "log_poop", translation_key="log_poop"
        )
        self.hass = hass
        self.coordinator = coordinator
        self._attr_icon = "mdi:emoticon-poop"

    async def async_press(self) -> None:
        """Handle button press."""
        # Update coordinator data directly
        dog_data = self.coordinator.get_dog_data(self.dog_id)
        if dog_data:
            dog_data.setdefault("statistics", {})["poop_count_today"] = (
                dog_data.get("statistics", {}).get("poop_count_today", 0) + 1
            )
            dog_data["statistics"]["last_poop"] = dt_util.now().isoformat()
            dog_data["statistics"]["last_action"] = dt_util.now().isoformat()
            dog_data["statistics"]["last_action_type"] = "poop_logged"
            await self.coordinator.async_request_refresh()


class NotifyTestButton(PawControlButtonEntity, ButtonEntity):
    """Button to test notifications."""

    def __init__(self, hass, coordinator, entry, dog_id):
        """Initialize the button."""
        super().__init__(
            coordinator, entry, dog_id, "notify_test", translation_key="notify_test"
        )
        self.hass = hass
        self._attr_icon = "mdi:bell-ring"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "notify_test",
            {
                "dog_id": self.dog_id,
                "message": f"Test notification for {self.dog_name}",
            },
            blocking=False,
        )


# Global Buttons
class DailyResetButton(ButtonEntity):
    """Button to trigger daily reset."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:restart"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass, coordinator, entry):
        """Initialize the button."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_daily_reset"
        self._attr_translation_key = "daily_reset"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "global")},
            "name": "Paw Control System",
            "manufacturer": "Paw Control",
            "model": "Smart Dog Manager",
            "sw_version": "1.1.0",
        }

    @property
    def name(self) -> str:
        """Return name of the button."""
        return "Daily Reset"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "daily_reset",
            {},
            blocking=False,
        )


class GenerateReportButton(ButtonEntity):
    """Button to generate report."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:file-document"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass, coordinator, entry):
        """Initialize the button."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_generate_report"
        self._attr_translation_key = "generate_report"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "global")},
            "name": "Paw Control System",
            "manufacturer": "Paw Control",
            "model": "Smart Dog Manager",
            "sw_version": "1.1.0",
        }

    @property
    def name(self) -> str:
        """Return name of the button."""
        return "Generate Report"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "generate_report",
            {
                "scope": "daily",
                "target": "notification",
                "format": "text",
            },
            blocking=False,
        )


class SyncSetupButton(ButtonEntity):
    """Button to sync setup."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:sync"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass, coordinator, entry):
        """Initialize the button."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_sync_setup"
        self._attr_translation_key = "sync_setup"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "global")},
            "name": "Paw Control System",
            "manufacturer": "Paw Control",
            "model": "Smart Dog Manager",
            "sw_version": "1.1.0",
        }

    @property
    def name(self) -> str:
        """Return name of the button."""
        return "Sync Setup"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "sync_setup",
            {},
            blocking=False,
        )
