"""Button platform for Paw Control integration.

This module provides interactive button entities for the Paw Control integration,
allowing users to perform quick actions like starting walks, feeding dogs,
logging activities, and system maintenance tasks.

The buttons follow Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations
- Robust error handling
- Efficient service call management
- Comprehensive user feedback
- Translation support
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .compat import DeviceInfo, EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    ICONS,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_TRAINING,
    MODULE_WALK,
    SERVICE_DAILY_RESET,
    SERVICE_END_WALK,
    SERVICE_FEED_DOG,
    SERVICE_GENERATE_REPORT,
    SERVICE_LOG_MEDICATION,
    SERVICE_PLAY_SESSION,
    SERVICE_START_GROOMING,
    SERVICE_START_WALK,
    SERVICE_SYNC_SETUP,
    SERVICE_TRAINING_SESSION,
    SERVICE_WALK_DOG,
)
from .entity import PawControlButtonEntity

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# No parallel updates to avoid service call conflicts
PARALLEL_UPDATES = 0

# Default values for quick actions
DEFAULT_WALK_DURATION_MIN = 30
DEFAULT_WALK_DISTANCE_M = 1000
DEFAULT_BREAKFAST_PORTION_G = 200
DEFAULT_LUNCH_PORTION_G = 150
DEFAULT_DINNER_PORTION_G = 200
DEFAULT_SNACK_PORTION_G = 50
DEFAULT_TRAINING_DURATION_MIN = 15
DEFAULT_PLAY_DURATION_MIN = 20


async def _call_service(
    hass: HomeAssistant,
    service: str,
    data: dict[str, Any],
    success_log: str,
    action_log: str,
    domain: str = DOMAIN,
) -> None:
    """Call a Home Assistant service with standardized logging."""
    try:
        await hass.services.async_call(domain, service, data, blocking=False)
        _LOGGER.info(success_log)
    except ServiceValidationError as err:
        _LOGGER.error("Failed to %s: %s", action_log, err)
    except Exception as err:  # pragma: no cover - unexpected error path
        _LOGGER.error("Unexpected error trying to %s: %s", action_log, err)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control button entities from config entry.

    Creates button entities based on configured dogs and enabled modules.
    Only creates buttons for modules that are enabled for each dog.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        async_add_entities: Callback to add entities

    Raises:
        PlatformNotReady: If coordinator hasn't completed initial data refresh
    """
    try:
        runtime_data = entry.runtime_data
        coordinator: PawControlCoordinator = runtime_data.coordinator

        # Ensure coordinator has completed initial refresh
        if not coordinator.last_update_success:
            _LOGGER.warning("Coordinator not ready, attempting refresh")
            await coordinator.async_refresh()
            if not coordinator.last_update_success:
                raise PlatformNotReady

        dogs = entry.options.get(CONF_DOGS, [])
        entities: list[PawControlButtonEntity | ButtonEntity] = []

        _LOGGER.debug("Setting up button entities for %d dogs", len(dogs))

        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            dog_name = dog.get(CONF_DOG_NAME, dog_id)

            if not dog_id:
                _LOGGER.warning("Skipping dog with missing ID: %s", dog)
                continue

            # Get enabled modules for this dog
            dog_modules = dog.get(CONF_DOG_MODULES, {})

            _LOGGER.debug(
                "Creating button entities for dog %s (%s) with modules: %s",
                dog_name,
                dog_id,
                list(dog_modules.keys()),
            )

            # Walk module buttons
            if dog_modules.get(MODULE_WALK, True):
                entities.extend(_create_walk_buttons(hass, coordinator, entry, dog_id))

            # Feeding module buttons
            if dog_modules.get(MODULE_FEEDING, True):
                entities.extend(
                    _create_feeding_buttons(hass, coordinator, entry, dog_id)
                )

            # Health module buttons
            if dog_modules.get(MODULE_HEALTH, True):
                entities.extend(
                    _create_health_buttons(hass, coordinator, entry, dog_id)
                )

            # Grooming module buttons
            if dog_modules.get(MODULE_GROOMING, False):
                entities.extend(
                    _create_grooming_buttons(hass, coordinator, entry, dog_id)
                )

            # Training module buttons
            if dog_modules.get(MODULE_TRAINING, False):
                entities.extend(
                    _create_training_buttons(hass, coordinator, entry, dog_id)
                )

            # Notification test button
            if dog_modules.get(MODULE_NOTIFICATIONS, True):
                entities.extend(
                    _create_notification_buttons(hass, coordinator, entry, dog_id)
                )

            # Core activity buttons (always available)
            entities.extend(_create_core_buttons(hass, coordinator, entry, dog_id))

        # System-wide buttons (always created)
        entities.extend(_create_system_buttons(hass, coordinator, entry))

        _LOGGER.info("Created %d button entities", len(entities))

        if entities:
            async_add_entities(entities, update_before_add=True)

    except Exception as err:
        _LOGGER.error("Failed to setup button entities: %s", err)
        raise


def _create_walk_buttons(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
) -> list[PawControlButtonEntity]:
    """Create walk-related button entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of walk button entities
    """
    return [
        StartWalkButton(hass, coordinator, entry, dog_id),
        EndWalkButton(hass, coordinator, entry, dog_id),
        QuickWalkButton(hass, coordinator, entry, dog_id),
    ]


def _create_feeding_buttons(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
) -> list[PawControlButtonEntity]:
    """Create feeding-related button entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of feeding button entities
    """
    return [
        FeedBreakfastButton(hass, coordinator, entry, dog_id),
        FeedLunchButton(hass, coordinator, entry, dog_id),
        FeedDinnerButton(hass, coordinator, entry, dog_id),
        FeedSnackButton(hass, coordinator, entry, dog_id),
    ]


def _create_health_buttons(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
) -> list[PawControlButtonEntity]:
    """Create health-related button entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of health button entities
    """
    return [
        LogWeightButton(hass, coordinator, entry, dog_id),
        GiveMedicationButton(hass, coordinator, entry, dog_id),
        LogHealthNoteButton(hass, coordinator, entry, dog_id),
    ]


def _create_grooming_buttons(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
) -> list[PawControlButtonEntity]:
    """Create grooming-related button entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of grooming button entities
    """
    return [
        GroomBathButton(hass, coordinator, entry, dog_id),
        GroomBrushButton(hass, coordinator, entry, dog_id),
        GroomNailsButton(hass, coordinator, entry, dog_id),
        GroomTeethButton(hass, coordinator, entry, dog_id),
        GroomEarsButton(hass, coordinator, entry, dog_id),
    ]


def _create_training_buttons(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
) -> list[PawControlButtonEntity]:
    """Create training-related button entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of training button entities
    """
    return [
        StartTrainingButton(hass, coordinator, entry, dog_id),
        LogPlaySessionButton(hass, coordinator, entry, dog_id),
    ]


def _create_notification_buttons(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
) -> list[PawControlButtonEntity]:
    """Create notification-related button entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of notification button entities
    """
    return [
        NotifyTestButton(hass, coordinator, entry, dog_id),
    ]


def _create_core_buttons(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
) -> list[PawControlButtonEntity]:
    """Create core activity button entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of core button entities
    """
    return [
        LogPoopButton(hass, coordinator, entry, dog_id),
    ]


def _create_system_buttons(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
) -> list[ButtonEntity]:
    """Create system-wide button entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry

    Returns:
        List of system button entities
    """
    return [
        DailyResetButton(hass, coordinator, entry),
        GenerateReportButton(hass, coordinator, entry),
        SyncSetupButton(hass, coordinator, entry),
        ToggleVisitorModeButton(hass, coordinator, entry),
    ]


# ==============================================================================
# WALK BUTTON ENTITIES
# ==============================================================================


class StartWalkButton(PawControlButtonEntity, ButtonEntity):
    """Button to start a walk for the dog.

    Initiates GPS tracking and walk recording for the specified dog.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the start walk button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="start_walk",
            translation_key="start_walk",
            icon=ICONS.get("walk", "mdi:dog-side"),
        )
        self.hass = hass

    @property
    def available(self) -> bool:
        """Only available when walk is not in progress."""
        if not super().available:
            return False
        walk_data = self.dog_data.get("walk", {})
        return not walk_data.get("walk_in_progress", False)

    async def async_press(self) -> None:
        """Handle button press to start walk."""
        await _call_service(
            self.hass,
            SERVICE_START_WALK,
            {"dog_id": self.dog_id, "source": "manual"},
            f"Walk started for dog {self.dog_name} via button",
            f"start walk for dog {self.dog_name}",
        )


class EndWalkButton(PawControlButtonEntity, ButtonEntity):
    """Button to end a walk for the dog.

    Stops GPS tracking and finalizes walk statistics.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the end walk button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="end_walk",
            translation_key="end_walk",
            icon=ICONS.get("walk", "mdi:home"),
        )
        self.hass = hass

    @property
    def available(self) -> bool:
        """Only available when walk is in progress."""
        if not super().available:
            return False
        walk_data = self.dog_data.get("walk", {})
        return walk_data.get("walk_in_progress", False)

    async def async_press(self) -> None:
        """Handle button press to end walk."""
        await _call_service(
            self.hass,
            SERVICE_END_WALK,
            {"dog_id": self.dog_id, "reason": "manual"},
            f"Walk ended for dog {self.dog_name} via button",
            f"end walk for dog {self.dog_name}",
        )


class QuickWalkButton(PawControlButtonEntity, ButtonEntity):
    """Button to log a quick walk with default values.

    Records a standard walk without requiring real-time tracking.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the quick walk button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="quick_walk",
            translation_key="quick_walk",
            icon=ICONS.get("walk", "mdi:walk"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log quick walk."""
        await _call_service(
            self.hass,
            SERVICE_WALK_DOG,
            {
                "dog_id": self.dog_id,
                "duration_min": DEFAULT_WALK_DURATION_MIN,
                "distance_m": DEFAULT_WALK_DISTANCE_M,
            },
            (
                f"Quick walk logged for dog {self.dog_name}: "
                f"{DEFAULT_WALK_DURATION_MIN} min, {DEFAULT_WALK_DISTANCE_M} m"
            ),
            f"log quick walk for dog {self.dog_name}",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return button configuration details."""
        try:
            attributes = super().extra_state_attributes or {}
            attributes.update(
                {
                    "default_duration_min": DEFAULT_WALK_DURATION_MIN,
                    "default_distance_m": DEFAULT_WALK_DISTANCE_M,
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting quick walk attributes: %s", err)
            return super().extra_state_attributes


# ==============================================================================
# FEEDING BUTTON ENTITIES
# ==============================================================================


class FeedBreakfastButton(PawControlButtonEntity, ButtonEntity):
    """Button to log breakfast feeding."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the feed breakfast button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="feed_breakfast",
            translation_key="feed_breakfast",
            icon=ICONS.get("feeding", "mdi:coffee"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log breakfast."""
        await _call_service(
            self.hass,
            SERVICE_FEED_DOG,
            {
                "dog_id": self.dog_id,
                "meal_type": "breakfast",
                "portion_g": DEFAULT_BREAKFAST_PORTION_G,
                "food_type": "dry",
            },
            f"Breakfast logged for dog {self.dog_name}",
            f"log breakfast for dog {self.dog_name}",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return feeding details."""
        try:
            attributes = super().extra_state_attributes or {}
            feeding_data = self.dog_data.get("feeding", {})
            feedings_today = feeding_data.get("feedings_today", {})

            attributes.update(
                {
                    "default_portion_g": DEFAULT_BREAKFAST_PORTION_G,
                    "breakfast_count_today": feedings_today.get("breakfast", 0),
                    "last_feeding": feeding_data.get("last_feeding"),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting breakfast attributes: %s", err)
            return super().extra_state_attributes


class FeedLunchButton(PawControlButtonEntity, ButtonEntity):
    """Button to log lunch feeding."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the feed lunch button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="feed_lunch",
            translation_key="feed_lunch",
            icon=ICONS.get("feeding", "mdi:silverware-fork-knife"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log lunch."""
        await _call_service(
            self.hass,
            SERVICE_FEED_DOG,
            {
                "dog_id": self.dog_id,
                "meal_type": "lunch",
                "portion_g": DEFAULT_LUNCH_PORTION_G,
                "food_type": "wet",
            },
            f"Lunch logged for dog {self.dog_name}",
            f"log lunch for dog {self.dog_name}",
        )


class FeedDinnerButton(PawControlButtonEntity, ButtonEntity):
    """Button to log dinner feeding."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the feed dinner button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="feed_dinner",
            translation_key="feed_dinner",
            icon=ICONS.get("feeding", "mdi:food-turkey"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log dinner."""
        await _call_service(
            self.hass,
            SERVICE_FEED_DOG,
            {
                "dog_id": self.dog_id,
                "meal_type": "dinner",
                "portion_g": DEFAULT_DINNER_PORTION_G,
                "food_type": "dry",
            },
            f"Dinner logged for dog {self.dog_name}",
            f"log dinner for dog {self.dog_name}",
        )


class FeedSnackButton(PawControlButtonEntity, ButtonEntity):
    """Button to log snack feeding."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the feed snack button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="feed_snack",
            translation_key="feed_snack",
            icon=ICONS.get("feeding", "mdi:food-apple"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log snack."""
        await _call_service(
            self.hass,
            SERVICE_FEED_DOG,
            {
                "dog_id": self.dog_id,
                "meal_type": "snack",
                "portion_g": DEFAULT_SNACK_PORTION_G,
                "food_type": "treat",
            },
            f"Snack logged for dog {self.dog_name}",
            f"log snack for dog {self.dog_name}",
        )


# ==============================================================================
# HEALTH BUTTON ENTITIES
# ==============================================================================


class LogWeightButton(PawControlButtonEntity, ButtonEntity):
    """Button to initiate weight logging.

    In a complete implementation, this would open a dialog or form
    to enter the dog's current weight.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the log weight button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="log_weight",
            translation_key="log_weight",
            icon=ICONS.get("health", "mdi:weight-kilogram"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to initiate weight logging."""
        # In a complete implementation, this could open a dialog or form.
        await _call_service(
            self.hass,
            "paw_control_log_weight_dialog",
            {"dog_id": self.dog_id},
            f"Weight logging initiated for dog {self.dog_name}",
            f"log weight for dog {self.dog_name}",
            domain="script",
        )


class GiveMedicationButton(PawControlButtonEntity, ButtonEntity):
    """Button to log medication administration."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the give medication button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="give_medication",
            translation_key="give_medication",
            icon=ICONS.get("medication", "mdi:pill"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log medication."""
        await _call_service(
            self.hass,
            SERVICE_LOG_MEDICATION,
            {
                "dog_id": self.dog_id,
                "medication_name": "Daily Supplement",
                "dose": "1 tablet",
            },
            f"Medication logged for dog {self.dog_name}",
            f"log medication for dog {self.dog_name}",
        )


class LogHealthNoteButton(PawControlButtonEntity, ButtonEntity):
    """Button to log a health note or observation."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the log health note button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="log_health_note",
            translation_key="log_health_note",
            icon=ICONS.get("health", "mdi:note-text"),
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log health note."""
        try:
            # In a complete implementation, this would open a text input dialog
            _LOGGER.info("Health note logging initiated for dog %s", self.dog_name)
        except Exception as err:
            _LOGGER.error(
                "Error initiating health note for dog %s: %s", self.dog_name, err
            )


# ==============================================================================
# GROOMING BUTTON ENTITIES
# ==============================================================================


class GroomBathButton(PawControlButtonEntity, ButtonEntity):
    """Button to log bath grooming session."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the groom bath button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="groom_bath",
            translation_key="groom_bath",
            icon=ICONS.get("grooming", "mdi:shower"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log bath grooming."""
        await _call_service(
            self.hass,
            SERVICE_START_GROOMING,
            {
                "dog_id": self.dog_id,
                "grooming_type": "bath",
                "notes": "Full bath with shampoo",
            },
            f"Bath grooming logged for dog {self.dog_name}",
            f"log bath grooming for dog {self.dog_name}",
        )


class GroomBrushButton(PawControlButtonEntity, ButtonEntity):
    """Button to log brush grooming session."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the groom brush button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="groom_brush",
            translation_key="groom_brush",
            icon=ICONS.get("grooming", "mdi:brush"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log brush grooming."""
        await _call_service(
            self.hass,
            SERVICE_START_GROOMING,
            {
                "dog_id": self.dog_id,
                "grooming_type": "brush",
                "notes": "Regular brushing session",
            },
            f"Brush grooming logged for dog {self.dog_name}",
            f"log brush grooming for dog {self.dog_name}",
        )


class GroomNailsButton(PawControlButtonEntity, ButtonEntity):
    """Button to log nail trimming session."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the groom nails button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="groom_nails",
            translation_key="groom_nails",
            icon=ICONS.get("grooming", "mdi:content-cut"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log nail trimming."""
        await _call_service(
            self.hass,
            SERVICE_START_GROOMING,
            {
                "dog_id": self.dog_id,
                "grooming_type": "nails",
                "notes": "Nail trimming session",
            },
            f"Nail grooming logged for dog {self.dog_name}",
            f"log nail grooming for dog {self.dog_name}",
        )


class GroomTeethButton(PawControlButtonEntity, ButtonEntity):
    """Button to log teeth cleaning session."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the groom teeth button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="groom_teeth",
            translation_key="groom_teeth",
            icon=ICONS.get("grooming", "mdi:tooth"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log teeth cleaning."""
        await _call_service(
            self.hass,
            SERVICE_START_GROOMING,
            {
                "dog_id": self.dog_id,
                "grooming_type": "teeth",
                "notes": "Teeth cleaning session",
            },
            f"Teeth grooming logged for dog {self.dog_name}",
            f"log teeth grooming for dog {self.dog_name}",
        )


class GroomEarsButton(PawControlButtonEntity, ButtonEntity):
    """Button to log ear cleaning session."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the groom ears button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="groom_ears",
            translation_key="groom_ears",
            icon=ICONS.get("grooming", "mdi:ear-hearing"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log ear cleaning."""
        await _call_service(
            self.hass,
            SERVICE_START_GROOMING,
            {
                "dog_id": self.dog_id,
                "grooming_type": "ears",
                "notes": "Ear cleaning session",
            },
            f"Ear grooming logged for dog {self.dog_name}",
            f"log ear grooming for dog {self.dog_name}",
        )


# ==============================================================================
# TRAINING BUTTON ENTITIES
# ==============================================================================


class StartTrainingButton(PawControlButtonEntity, ButtonEntity):
    """Button to start a training session."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the start training button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="start_training",
            translation_key="start_training",
            icon=ICONS.get("training", "mdi:school"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to start training."""
        await _call_service(
            self.hass,
            SERVICE_TRAINING_SESSION,
            {
                "dog_id": self.dog_id,
                "topic": "Basic Commands",
                "duration_min": DEFAULT_TRAINING_DURATION_MIN,
                "notes": "Sit, stay, come practice",
            },
            f"Training session logged for dog {self.dog_name}",
            f"log training for dog {self.dog_name}",
        )


class LogPlaySessionButton(PawControlButtonEntity, ButtonEntity):
    """Button to log a play session."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the log play session button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="log_play",
            translation_key="log_play",
            icon=ICONS.get("activity", "mdi:tennis-ball"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log play session."""
        await _call_service(
            self.hass,
            SERVICE_PLAY_SESSION,
            {
                "dog_id": self.dog_id,
                "duration_min": DEFAULT_PLAY_DURATION_MIN,
                "intensity": "medium",
            },
            f"Play session logged for dog {self.dog_name}",
            f"log play session for dog {self.dog_name}",
        )


# ==============================================================================
# CORE ACTIVITY BUTTON ENTITIES
# ==============================================================================


class LogPoopButton(PawControlButtonEntity, ButtonEntity):
    """Button to log a bathroom break."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the log poop button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="log_poop",
            translation_key="log_poop",
            icon=ICONS.get("statistics", "mdi:emoticon-poop"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to log bathroom break."""
        try:
            # Update coordinator data directly for immediate response
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                stats = dog_data.setdefault("statistics", {})
                current_time = dt_util.now()

                # Increment poop count
                stats["poop_count_today"] = stats.get("poop_count_today", 0) + 1
                stats["last_poop"] = current_time.isoformat()
                stats["last_action"] = current_time.isoformat()
                stats["last_action_type"] = "poop_logged"

                # Trigger coordinator update
                await self.coordinator.async_request_refresh()

                _LOGGER.info("Bathroom break logged for dog %s", self.dog_name)
        except Exception as err:
            _LOGGER.error(
                "Failed to log bathroom break for dog %s: %s", self.dog_name, err
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return current poop statistics."""
        try:
            attributes = super().extra_state_attributes or {}
            stats_data = self.dog_data.get("statistics", {})

            attributes.update(
                {
                    "count_today": stats_data.get("poop_count_today", 0),
                    "last_poop": stats_data.get("last_poop"),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting poop attributes: %s", err)
            return super().extra_state_attributes


# ==============================================================================
# NOTIFICATION BUTTON ENTITIES
# ==============================================================================


class NotifyTestButton(PawControlButtonEntity, ButtonEntity):
    """Button to test notification system."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
    ) -> None:
        """Initialize the notify test button."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="notify_test",
            translation_key="notify_test",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("notifications", "mdi:bell-ring"),
        )
        self.hass = hass

    async def async_press(self) -> None:
        """Handle button press to test notifications."""
        await _call_service(
            self.hass,
            "notify",
            {
                "title": "Paw Control Test",
                "message": f"Test notification for {self.dog_name} - {dt_util.now().strftime('%H:%M:%S')}",
            },
            f"Test notification sent for dog {self.dog_name}",
            f"send test notification for dog {self.dog_name}",
            domain="notify",
        )


# ==============================================================================
# SYSTEM BUTTON ENTITIES
# ==============================================================================


class DailyResetButton(ButtonEntity):
    """Button to trigger daily counter reset for all dogs."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the daily reset button."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_daily_reset"
        self._attr_translation_key = "daily_reset"
        self._attr_icon = ICONS.get("settings", "mdi:restart")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=f"/config/integrations/integration/{DOMAIN}",
        )

    @property
    def name(self) -> str:
        """Return name of the button."""
        return "Daily Reset"

    async def async_press(self) -> None:
        """Handle button press to reset daily counters."""
        await _call_service(
            self.hass,
            SERVICE_DAILY_RESET,
            {},
            "Daily reset triggered via button",
            "trigger daily reset",
        )


class GenerateReportButton(ButtonEntity):
    """Button to generate and send daily report."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the generate report button."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_generate_report"
        self._attr_translation_key = "generate_report"
        self._attr_icon = ICONS.get("export", "mdi:file-document")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=f"/config/integrations/integration/{DOMAIN}",
        )

    @property
    def name(self) -> str:
        """Return name of the button."""
        return "Generate Report"

    async def async_press(self) -> None:
        """Handle button press to generate report."""
        await _call_service(
            self.hass,
            SERVICE_GENERATE_REPORT,
            {
                "scope": "daily",
                "target": "notification",
                "format": "text",
            },
            "Report generation triggered via button",
            "generate report",
        )


class SyncSetupButton(ButtonEntity):
    """Button to synchronize setup and refresh configuration."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sync setup button."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_sync_setup"
        self._attr_translation_key = "sync_setup"
        self._attr_icon = ICONS.get("settings", "mdi:sync")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=f"/config/integrations/integration/{DOMAIN}",
        )

    @property
    def name(self) -> str:
        """Return name of the button."""
        return "Sync Setup"

    async def async_press(self) -> None:
        """Handle button press to sync setup."""
        await _call_service(
            self.hass,
            SERVICE_SYNC_SETUP,
            {},
            "Setup sync triggered via button",
            "sync setup",
        )


class ToggleVisitorModeButton(ButtonEntity):
    """Button to toggle visitor mode on/off."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the toggle visitor mode button."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_toggle_visitor_mode"
        self._attr_translation_key = "toggle_visitor_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=f"/config/integrations/integration/{DOMAIN}",
        )

    @property
    def name(self) -> str:
        """Return name of the button."""
        return "Toggle Visitor Mode"

    @property
    def icon(self) -> str:
        """Return icon based on current visitor mode state."""
        return (
            ICONS.get("visitor", "mdi:account-group-outline")
            if self.coordinator.visitor_mode
            else ICONS.get("visitor", "mdi:account-group")
        )

    async def async_press(self) -> None:
        """Handle button press to toggle visitor mode."""
        try:
            new_state = not self.coordinator.visitor_mode
            await self.coordinator.set_visitor_mode(new_state)
            _LOGGER.info(
                "Visitor mode %s via button", "enabled" if new_state else "disabled"
            )
        except Exception as err:
            _LOGGER.error("Failed to toggle visitor mode: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return current visitor mode state."""
        try:
            return {
                "current_state": self.coordinator.visitor_mode,
                "next_state": not self.coordinator.visitor_mode,
            }
        except Exception as err:
            _LOGGER.debug("Error getting visitor mode attributes: %s", err)
            return {}
