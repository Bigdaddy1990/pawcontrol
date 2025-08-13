"""Button platform for Paw Control integration."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control button entities."""
    entities = []
    dogs = entry.options.get(CONF_DOGS, [])

    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue

        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})

        # Walk module buttons
        if modules.get(MODULE_WALK):
            entities.extend(
                [
                    StartWalkButton(hass, dog_id, dog_name),
                    EndWalkButton(hass, dog_id, dog_name),
                    QuickWalkButton(hass, dog_id, dog_name),
                ]
            )

        # Feeding module buttons
        if modules.get(MODULE_FEEDING):
            entities.extend(
                [
                    FeedBreakfastButton(hass, dog_id, dog_name),
                    FeedLunchButton(hass, dog_id, dog_name),
                    FeedDinnerButton(hass, dog_id, dog_name),
                    FeedSnackButton(hass, dog_id, dog_name),
                ]
            )

        # Health module buttons
        if modules.get(MODULE_HEALTH):
            entities.extend(
                [
                    LogWeightButton(hass, dog_id, dog_name),
                    GiveMedicationButton(hass, dog_id, dog_name),
                ]
            )

        # Grooming module buttons
        if modules.get(MODULE_GROOMING):
            entities.extend(
                [
                    GroomBathButton(hass, dog_id, dog_name),
                    GroomBrushButton(hass, dog_id, dog_name),
                    GroomNailsButton(hass, dog_id, dog_name),
                ]
            )

        # Training module buttons
        if modules.get(MODULE_TRAINING):
            entities.extend(
                [
                    StartTrainingButton(hass, dog_id, dog_name),
                    LogPlaySessionButton(hass, dog_id, dog_name),
                ]
            )

        # Notification test button
        if modules.get(MODULE_NOTIFICATIONS):
            entities.append(NotifyTestButton(hass, dog_id, dog_name))

        # Always add poop tracking button
        entities.append(LogPoopButton(hass, dog_id, dog_name))

    # Global buttons
    entities.extend(
        [
            DailyResetButton(hass),
            GenerateReportButton(hass),
            SyncSetupButton(hass),
        ]
    )

    async_add_entities(entities, True)


class PawControlButtonBase(ButtonEntity):
    """Base class for Paw Control buttons."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        dog_id: str,
        dog_name: str,
        button_type: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the button."""
        self.hass = hass
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._button_type = button_type

        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.button.{button_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=f"🐕 {dog_name}",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )


class StartWalkButton(PawControlButtonBase):
    """Button to start a walk."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "start_walk", "Start Walk", "mdi:dog-side"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_walk",
            {"dog_id": self._dog_id, "source": "manual"},
            blocking=False,
        )


class EndWalkButton(PawControlButtonBase):
    """Button to end a walk."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(hass, dog_id, dog_name, "end_walk", "End Walk", "mdi:home")

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "end_walk",
            {"dog_id": self._dog_id, "reason": "manual"},
            blocking=False,
        )


class QuickWalkButton(PawControlButtonBase):
    """Button to log a quick walk."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "quick_walk", "Quick Walk (30min)", "mdi:walk"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "walk_dog",
            {
                "dog_id": self._dog_id,
                "duration_min": 30,
                "distance_m": 1000,
            },
            blocking=False,
        )


class FeedBreakfastButton(PawControlButtonBase):
    """Button to log breakfast feeding."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "feed_breakfast", "Feed Breakfast", "mdi:food-apple"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "feed_dog",
            {
                "dog_id": self._dog_id,
                "meal_type": "breakfast",
                "portion_g": 200,
                "food_type": "dry",
            },
            blocking=False,
        )


class FeedLunchButton(PawControlButtonBase):
    """Button to log lunch feeding."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(hass, dog_id, dog_name, "feed_lunch", "Feed Lunch", "mdi:food")

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "feed_dog",
            {
                "dog_id": self._dog_id,
                "meal_type": "lunch",
                "portion_g": 150,
                "food_type": "wet",
            },
            blocking=False,
        )


class FeedDinnerButton(PawControlButtonBase):
    """Button to log dinner feeding."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "feed_dinner", "Feed Dinner", "mdi:food-variant"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "feed_dog",
            {
                "dog_id": self._dog_id,
                "meal_type": "dinner",
                "portion_g": 200,
                "food_type": "dry",
            },
            blocking=False,
        )


class FeedSnackButton(PawControlButtonBase):
    """Button to log snack feeding."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "feed_snack", "Give Snack", "mdi:cookie"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "feed_dog",
            {
                "dog_id": self._dog_id,
                "meal_type": "snack",
                "portion_g": 50,
                "food_type": "treat",
            },
            blocking=False,
        )


class LogWeightButton(PawControlButtonBase):
    """Button to log weight."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "log_weight", "Log Weight", "mdi:weight"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        # In a real implementation, this would open a dialog to enter weight
        _LOGGER.info(f"Weight logging requested for {self._dog_name}")


class GiveMedicationButton(PawControlButtonBase):
    """Button to log medication."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "give_medication", "Give Medication", "mdi:pill"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "log_medication",
            {
                "dog_id": self._dog_id,
                "medication_name": "Daily Supplement",
                "dose": "1 tablet",
            },
            blocking=False,
        )


class GroomBathButton(PawControlButtonBase):
    """Button to log bath grooming."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "groom_bath", "Give Bath", "mdi:shower"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_grooming_session",
            {
                "dog_id": self._dog_id,
                "type": "bath",
                "notes": "Full bath with shampoo",
            },
            blocking=False,
        )


class GroomBrushButton(PawControlButtonBase):
    """Button to log brush grooming."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "groom_brush", "Brush Fur", "mdi:brush"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_grooming_session",
            {
                "dog_id": self._dog_id,
                "type": "brush",
                "notes": "Regular brushing",
            },
            blocking=False,
        )


class GroomNailsButton(PawControlButtonBase):
    """Button to log nail grooming."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "groom_nails", "Trim Nails", "mdi:content-cut"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_grooming_session",
            {
                "dog_id": self._dog_id,
                "type": "nails",
                "notes": "Nail trimming",
            },
            blocking=False,
        )


class StartTrainingButton(PawControlButtonBase):
    """Button to start training session."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "start_training", "Start Training", "mdi:school"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "start_training_session",
            {
                "dog_id": self._dog_id,
                "topic": "Basic Commands",
                "duration_min": 15,
                "notes": "Sit, stay, come practice",
            },
            blocking=False,
        )


class LogPlaySessionButton(PawControlButtonBase):
    """Button to log play session."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "log_play", "Log Play Session", "mdi:tennis-ball"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "play_with_dog",
            {
                "dog_id": self._dog_id,
                "duration_min": 20,
                "intensity": "medium",
            },
            blocking=False,
        )


class LogPoopButton(PawControlButtonBase):
    """Button to log poop."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "log_poop", "Log Poop", "mdi:emoticon-poop"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        # Update coordinator data
        coordinator = (
            self.hass.data[DOMAIN]
            .get(list(self.hass.data[DOMAIN].keys())[0], {})
            .get("coordinator")
        )
        if coordinator:
            dog_data = coordinator.get_dog_data(self._dog_id)
            if dog_data:
                dog_data["statistics"]["poop_count_today"] = (
                    dog_data["statistics"].get("poop_count_today", 0) + 1
                )
                dog_data["statistics"]["last_poop"] = datetime.now().isoformat()
                await coordinator.async_request_refresh()


class NotifyTestButton(PawControlButtonBase):
    """Button to test notifications."""

    def __init__(self, hass, dog_id, dog_name):
        """Initialize the button."""
        super().__init__(
            hass, dog_id, dog_name, "notify_test", "Test Notification", "mdi:bell-ring"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "notify_test",
            {
                "dog_id": self._dog_id,
                "message": f"Test notification for {self._dog_name}",
            },
            blocking=False,
        )


class DailyResetButton(ButtonEntity):
    """Button to trigger daily reset."""

    _attr_has_entity_name = True
    _attr_name = "Daily Reset"
    _attr_icon = "mdi:restart"

    def __init__(self, hass: HomeAssistant):
        """Initialize the button."""
        self.hass = hass
        self._attr_unique_id = f"{DOMAIN}.global.button.daily_reset"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

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
    _attr_name = "Generate Report"
    _attr_icon = "mdi:file-document"

    def __init__(self, hass: HomeAssistant):
        """Initialize the button."""
        self.hass = hass
        self._attr_unique_id = f"{DOMAIN}.global.button.generate_report"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

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
    _attr_name = "Sync Setup"
    _attr_icon = "mdi:sync"

    def __init__(self, hass: HomeAssistant):
        """Initialize the button."""
        self.hass = hass
        self._attr_unique_id = f"{DOMAIN}.global.button.sync_setup"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.hass.services.async_call(
            DOMAIN,
            "sync_setup",
            {},
            blocking=False,
        )


class MarkMedicationButton(BaseDogButton):
    def __init__(self, hass, dog_id):
        super().__init__(hass, dog_id, "mark_medication", "Medikament gegeben")

    async def async_press(self):
        now = self.hass.helpers.event.dt_util.utcnow().isoformat()
        self.hass.states.async_set(
            f"sensor.{DOMAIN}_{self._dog}_last_medication", now, {"via": "button"}
        )
