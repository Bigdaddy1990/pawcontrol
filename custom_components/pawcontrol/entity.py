"""Base entity classes for PawControl integration.

This module provides comprehensive base entity classes for all platform
implementations in the Paw Control integration. These classes handle
common functionality like device information, data access, and state
management while following Home Assistant's Platinum standards.

Features:
- Complete asynchronous operation
- Full type annotations
- Comprehensive error handling
- Efficient data access patterns
- Robust device and entity management
- Translation support
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

try:  # pragma: no cover - fallback for tests without select platform
    from homeassistant.components.select import SelectEntity
except Exception:  # pragma: no cover

    class SelectEntity:  # type: ignore[misc]
        """Fallback SelectEntity for stubbed Home Assistant environments."""

        pass


try:  # pragma: no cover - fallback for tests without text platform
    from homeassistant.components.text import TextEntity
except Exception:  # pragma: no cover

    class TextEntity:  # type: ignore[misc]
        """Fallback TextEntity for stubbed Home Assistant environments."""

        pass


from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .compat import DeviceInfo, EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    ENTITY_UPDATE_DEBOUNCE_SECONDS,
    ICONS,
    INTEGRATION_VERSION,
    STATUS_READY,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import PawControlCoordinator
    from .types import DogConfig, DogData

_LOGGER = logging.getLogger(__name__)

# ==============================================================================
# BASE ENTITY CLASS
# ==============================================================================


class PawControlEntity(CoordinatorEntity["PawControlCoordinator"]):
    """Base entity class for PawControl integration.

    This class provides common functionality for all PawControl entities including:
    - Device information management
    - Dog data access patterns
    - Translation key handling
    - Availability management
    - Error handling and logging

    All platform-specific entities should inherit from this base class or one
    of its specialized subclasses.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize the base PawControl entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog this entity represents
            entity_key: Unique key for this entity type
            translation_key: Optional translation key for localization
            icon: Optional icon override for this entity
            entity_category: Optional category for entity organization
        """
        super().__init__(coordinator)
        self.entry = entry
        self.dog_id = dog_id
        self.entity_key = entity_key

        # Validate dog_id exists in coordinator
        if self.dog_id not in coordinator._dog_data:
            _LOGGER.warning(
                "Entity created for unknown dog_id: %s (entity: %s)",
                self.dog_id,
                entity_key,
            )

        # Set unique ID using entry, dog, and entity identifiers
        self._attr_unique_id = f"{entry.entry_id}_{dog_id}_{entity_key}"

        # Set translation key for localization support
        self._attr_translation_key = translation_key or entity_key

        # Platinum optimization: Smart icon handling
        self._attr_icon = self._determine_best_icon(icon)

        # Set entity category for organization
        if entity_category:
            self._attr_entity_category = entity_category

        # Cache dog configuration for efficient access
        self._dog_config: DogConfig | None = None
        self._last_config_update: float = 0

        # Platinum performance tracking
        self._last_state_change: float = 0
        self._update_count: int = 0

        # Set device info for proper device association
        self._setup_device_info()

    def _setup_device_info(self) -> None:
        """Set up device information for this entity.

        Creates a device entry that groups all entities for this dog together
        in the Home Assistant device registry.
        """
        try:
            dog_name = self.dog_name
            dog_config = self._get_dog_config()

            # Platinum enhancement: Include breed and size in device info
            device_name = f"🐕 {dog_name}"
            if dog_config.get("dog_breed") and dog_config["dog_breed"] != "Unknown":
                device_name += f" ({dog_config['dog_breed']})"

            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, self.dog_id)},
                name=device_name,
                manufacturer="Paw Control",
                model="Smart Dog Manager",
                sw_version=INTEGRATION_VERSION,
                configuration_url=f"/config/integrations/integration/{DOMAIN}",
                suggested_area="Pet Care",  # Platinum: suggested area
            )
        except Exception as err:
            _LOGGER.error(
                "Failed to setup device info for dog %s: %s",
                self.dog_id,
                err,
            )
            # Fallback device info
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, self.dog_id)},
                name=f"🐕 {self.dog_id}",
                manufacturer="Paw Control",
                model="Smart Dog Manager",
                sw_version=INTEGRATION_VERSION,
            )

    def _determine_best_icon(self, icon_override: str | None) -> str:
        """Determine the best icon for this entity.

        Platinum optimization: Smart icon selection based on context.

        Args:
            icon_override: Optional icon override

        Returns:
            Best Material Design icon for this entity
        """
        if icon_override:
            return icon_override

        # Try entity-specific icon first
        if self.entity_key in ICONS:
            return ICONS[self.entity_key]

        # Fall back to category-based icons
        category_map = {
            "walk": "walk",
            "feeding": "feeding",
            "health": "health",
            "grooming": "grooming",
            "training": "training",
            "gps": "gps",
            "location": "location",
            "activity": "activity",
            "statistics": "statistics",
        }

        for keyword, icon_key in category_map.items():
            if keyword in self.entity_key.lower():
                return ICONS.get(icon_key, "mdi:information")

        # Ultimate fallback
        return ICONS.get("settings", "mdi:information")

    def _get_default_icon(self) -> str:
        """Get default icon for this entity type.

        Returns:
            Default Material Design icon for this entity
        """
        return self._determine_best_icon(None)

    @property
    def dog_name(self) -> str:
        """Get the display name for this dog.

        Returns:
            Dog's configured name or dog_id as fallback
        """
        try:
            dog_config = self._get_dog_config()
            return (
                dog_config.get(CONF_DOG_NAME, self.dog_id)
                if dog_config
                else self.dog_id
            )
        except Exception as err:
            _LOGGER.debug("Failed to get dog name for %s: %s", self.dog_id, err)
            return self.dog_id

    @property
    def dog_data(self) -> DogData:
        """Get all current data for this dog.

        Returns:
            Complete dog data structure from coordinator
        """
        return self.coordinator.get_dog_data(self.dog_id)

    def _get_dog_config(self) -> DogConfig:
        """Get dog configuration with caching for performance.

        Caches the dog configuration to avoid repeated lookups while ensuring
        updates are detected when the configuration changes.

        Returns:
            Dog configuration dict or empty dict if not found
        """
        try:
            current_time = dt_util.utcnow().timestamp()

            # Cache configuration for 60 seconds to improve performance
            if self._dog_config is None or current_time - self._last_config_update > 60:
                dogs = self.entry.options.get("dogs", [])
                self._dog_config = next(
                    (dog for dog in dogs if dog.get(CONF_DOG_ID) == self.dog_id),
                    {},
                )
                self._last_config_update = current_time

            return self._dog_config

        except Exception as err:
            _LOGGER.debug("Failed to get dog config for %s: %s", self.dog_id, err)
            return {}

    @property
    def available(self) -> bool:
        """Check if this entity is available.

        An entity is considered available if:
        1. The coordinator is available
        2. The dog exists in coordinator data
        3. No critical errors are present
        4. Coordinator is in ready state (Platinum)

        Returns:
            True if entity is available, False otherwise
        """
        if not super().available:
            return False

        # Check if dog still exists in coordinator
        if self.dog_id not in self.coordinator._dog_data:
            _LOGGER.debug(
                "Entity %s unavailable: dog %s not in coordinator data",
                self.entity_id,
                self.dog_id,
            )
            return False

        # Platinum: Check coordinator health status
        status = getattr(self.coordinator, "coordinator_status", STATUS_READY)
        if isinstance(status, str) and status != STATUS_READY:
            _LOGGER.debug(
                "Entity %s unavailable: coordinator status is %s",
                self.entity_id,
                status,
            )
            return False

        return True

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional state attributes.

        Provides common attributes that are useful across all entity types.
        Subclasses can override this to add specific attributes.

        Platinum enhancement: Includes diagnostics and health info.

        Returns:
            Dictionary of additional state attributes
        """
        try:
            dog_config = self._get_dog_config()
            attributes = {
                "dog_id": self.dog_id,
                "dog_name": self.dog_name,
                "integration": DOMAIN,
                "integration_version": INTEGRATION_VERSION,
            }

            # Add dog breed and size if available
            if dog_config:
                if breed := dog_config.get("dog_breed"):
                    attributes["dog_breed"] = breed
                if size := dog_config.get("dog_size"):
                    attributes["dog_size"] = size
                if age := dog_config.get("dog_age"):
                    attributes["dog_age_years"] = age
                if weight := dog_config.get("dog_weight"):
                    attributes["dog_weight_kg"] = weight

            # Add last update timestamp
            if self.coordinator.last_update_success_time:
                attributes["last_updated"] = (
                    self.coordinator.last_update_success_time.isoformat()
                )

            # Platinum: Add diagnostic information
            if hasattr(self.coordinator, "coordinator_status"):
                attributes["coordinator_status"] = self.coordinator.coordinator_status
            if hasattr(self.coordinator, "error_count"):
                attributes["coordinator_errors"] = self.coordinator.error_count

            # Entity-specific diagnostics
            attributes["entity_updates"] = self._update_count
            if self._last_state_change > 0:
                attributes["last_state_change"] = dt_util.utc_from_timestamp(
                    self._last_state_change
                ).isoformat()

            return attributes

        except Exception as err:
            _LOGGER.debug(
                "Failed to get extra attributes for %s: %s",
                self.entity_id,
                err,
            )
            return {"dog_id": self.dog_id, "integration": DOMAIN}

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator data updates.

        Called when the coordinator reports new data. This method can be
        overridden by subclasses to perform specific update logic.

        Platinum optimization: Tracks update frequency for diagnostics.
        """
        try:
            current_time = dt_util.utcnow().timestamp()
            time_since_last = current_time - self._last_state_change

            # Platinum: Track update patterns for diagnostics
            if time_since_last < ENTITY_UPDATE_DEBOUNCE_SECONDS:
                _LOGGER.debug(
                    "Rapid update detected for %s (%.2fs since last)",
                    self.entity_id,
                    time_since_last,
                )

            self._last_state_change = current_time
            self._update_count += 1

            super()._handle_coordinator_update()
        except Exception as err:
            _LOGGER.error(
                "Error handling coordinator update for %s: %s",
                self.entity_id,
                err,
            )


# ==============================================================================
# SENSOR ENTITY CLASSES
# ==============================================================================


class PawControlSensorEntity(PawControlEntity):
    """Base sensor entity for PawControl.

    Provides specialized functionality for sensor entities including
    device class, state class, and unit of measurement handling.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        state_class: str | None = None,
        unit_of_measurement: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
        precision: int | None = None,
    ) -> None:
        """Initialize sensor entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog
            entity_key: Unique key for this entity type
            translation_key: Optional translation key for localization
            device_class: Device class for semantic meaning
            state_class: State class for statistics
            unit_of_measurement: Unit for the sensor value
            entity_category: Category for entity organization
            icon: Optional icon override
            precision: Number of decimal places for numeric values
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            icon=icon,
            entity_category=entity_category,
        )

        # Set sensor-specific attributes
        if device_class:
            self._attr_device_class = device_class
        if state_class:
            self._attr_state_class = state_class
        if unit_of_measurement:
            self._attr_native_unit_of_measurement = unit_of_measurement
        if precision is not None:
            self._attr_suggested_display_precision = precision

    def _get_default_icon(self) -> str:
        """Get default icon for sensor entities."""
        return ICONS.get("statistics", "mdi:chart-line")


# ==============================================================================
# BINARY SENSOR ENTITY CLASS
# ==============================================================================


class PawControlBinarySensorEntity(PawControlEntity):
    """Base binary sensor entity for PawControl.

    Provides specialized functionality for binary sensor entities including
    device class handling and boolean state management.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize binary sensor entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog
            entity_key: Unique key for this entity type
            translation_key: Optional translation key for localization
            device_class: Device class for semantic meaning
            entity_category: Category for entity organization
            icon: Optional icon override
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            icon=icon,
            entity_category=entity_category,
        )

        # Set binary sensor-specific attributes
        if device_class:
            self._attr_device_class = device_class

    def _get_default_icon(self) -> str:
        """Get default icon for binary sensor entities."""
        return ICONS.get("notifications", "mdi:information")


# ==============================================================================
# BUTTON ENTITY CLASS
# ==============================================================================


class PawControlButtonEntity(PawControlEntity):
    """Base button entity for PawControl.

    Provides specialized functionality for button entities including
    press action handling and device class support.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize button entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog
            entity_key: Unique key for this entity type
            translation_key: Optional translation key for localization
            device_class: Device class for semantic meaning
            entity_category: Category for entity organization
            icon: Optional icon override
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            icon=icon,
            entity_category=entity_category,
        )

        # Set button-specific attributes
        if device_class:
            self._attr_device_class = device_class

    def _get_default_icon(self) -> str:
        """Get default icon for button entities."""
        return ICONS.get("settings", "mdi:gesture-tap-button")

    async def async_press(self) -> None:
        """Handle button press.

        This method should be overridden by specific button implementations
        to provide the actual button functionality.
        """
        _LOGGER.debug("Button pressed: %s", self.entity_id)


# ==============================================================================
# NUMBER ENTITY CLASS
# ==============================================================================


class PawControlNumberEntity(PawControlEntity):
    """Base number entity for PawControl.

    Provides specialized functionality for number entities including
    value range handling and step configuration.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        unit_of_measurement: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
        step: float | None = None,
        mode: str = "box",
    ) -> None:
        """Initialize number entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog
            entity_key: Unique key for this entity type
            translation_key: Optional translation key for localization
            device_class: Device class for semantic meaning
            unit_of_measurement: Unit for the number value
            entity_category: Category for entity organization
            icon: Optional icon override
            min_value: Minimum allowed value
            max_value: Maximum allowed value
            step: Step size for value changes
            mode: UI mode (box, slider)
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            icon=icon,
            entity_category=entity_category,
        )

        # Set number-specific attributes
        if device_class:
            self._attr_device_class = device_class
        if unit_of_measurement:
            self._attr_native_unit_of_measurement = unit_of_measurement
        if min_value is not None:
            self._attr_native_min_value = min_value
        if max_value is not None:
            self._attr_native_max_value = max_value
        if step is not None:
            self._attr_native_step = step
        self._attr_mode = mode

    def _get_default_icon(self) -> str:
        """Get default icon for number entities."""
        return ICONS.get("settings", "mdi:numeric")

    async def async_set_native_value(self, value: float) -> None:
        """Set the native value.

        This method should be overridden by specific number implementations
        to provide actual value setting functionality.

        Args:
            value: The new value to set
        """
        _LOGGER.debug("Number value set: %s = %s", self.entity_id, value)


# ==============================================================================
# SELECT ENTITY CLASS
# ==============================================================================


class PawControlSelectEntity(PawControlEntity, SelectEntity):
    """Base select entity for PawControl.

    Provides specialized functionality for select entities including
    options management and selection handling.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        options: list[str],
        translation_key: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize select entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog
            entity_key: Unique key for this entity type
            options: List of available selection options
            translation_key: Optional translation key for localization
            entity_category: Category for entity organization
            icon: Optional icon override
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            icon=icon,
            entity_category=entity_category,
        )

        # Set select-specific attributes
        self._attr_options = options

    def _get_default_icon(self) -> str:
        """Get default icon for select entities."""
        return ICONS.get("settings", "mdi:format-list-bulleted")

    async def async_select_option(self, option: str) -> None:
        """Select an option.

        This method should be overridden by specific select implementations
        to provide actual option selection functionality.

        Args:
            option: The option to select
        """
        _LOGGER.debug("Option selected: %s = %s", self.entity_id, option)


# ==============================================================================
# TEXT ENTITY CLASS
# ==============================================================================


class PawControlTextEntity(PawControlEntity, TextEntity):
    """Base text entity for PawControl.

    Provides specialized functionality for text entities including
    length validation and pattern matching.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
        mode: str = "text",
    ) -> None:
        """Initialize text entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog
            entity_key: Unique key for this entity type
            translation_key: Optional translation key for localization
            entity_category: Category for entity organization
            icon: Optional icon override
            min_length: Minimum text length
            max_length: Maximum text length
            pattern: Regex pattern for validation
            mode: UI mode (text, password)
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            icon=icon,
            entity_category=entity_category,
        )

        # Set text-specific attributes
        if min_length is not None:
            self._attr_native_min = min_length
        if max_length is not None:
            self._attr_native_max = max_length
        if pattern:
            self._attr_pattern = pattern
        self._attr_mode = mode

    def _get_default_icon(self) -> str:
        """Get default icon for text entities."""
        return ICONS.get("settings", "mdi:form-textbox")

    async def async_set_value(self, value: str) -> None:
        """Set the text value.

        This method should be overridden by specific text implementations
        to provide actual value setting functionality.

        Args:
            value: The new text value to set
        """
        _LOGGER.debug("Text value set: %s = %s", self.entity_id, value)


# ==============================================================================
# SWITCH ENTITY CLASS
# ==============================================================================


class PawControlSwitchEntity(PawControlEntity):
    """Base switch entity for PawControl.

    Provides specialized functionality for switch entities including
    on/off state management and device class support.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize switch entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog
            entity_key: Unique key for this entity type
            translation_key: Optional translation key for localization
            device_class: Device class for semantic meaning
            entity_category: Category for entity organization
            icon: Optional icon override
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            icon=icon,
            entity_category=entity_category,
        )

        # Set switch-specific attributes
        if device_class:
            self._attr_device_class = device_class

    def _get_default_icon(self) -> str:
        """Get default icon for switch entities."""
        return ICONS.get("settings", "mdi:toggle-switch")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on.

        This method should be overridden by specific switch implementations
        to provide actual turn-on functionality.

        Args:
            **kwargs: Additional arguments
        """
        _LOGGER.debug("Switch turned on: %s", self.entity_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off.

        This method should be overridden by specific switch implementations
        to provide actual turn-off functionality.

        Args:
            **kwargs: Additional arguments
        """
        _LOGGER.debug("Switch turned off: %s", self.entity_id)


# ==============================================================================
# DATETIME ENTITY CLASS
# ==============================================================================


class PawControlDateTimeEntity(PawControlEntity):
    """Base datetime entity for PawControl.

    Provides specialized functionality for datetime entities including
    date/time value management and formatting.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize datetime entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog
            entity_key: Unique key for this entity type
            translation_key: Optional translation key for localization
            entity_category: Category for entity organization
            icon: Optional icon override
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            icon=icon,
            entity_category=entity_category,
        )

    def _get_default_icon(self) -> str:
        """Get default icon for datetime entities."""
        return ICONS.get("settings", "mdi:calendar-clock")

    async def async_set_value(self, value: Any) -> None:
        """Set the datetime value.

        This method should be overridden by specific datetime implementations
        to provide actual value setting functionality.

        Args:
            value: The new datetime value to set
        """
        _LOGGER.debug("Datetime value set: %s = %s", self.entity_id, value)


# ==============================================================================
# DEVICE TRACKER ENTITY CLASS
# ==============================================================================


class PawControlDeviceTrackerEntity(PawControlEntity):
    """Base device tracker entity for PawControl.

    Provides specialized functionality for device tracker entities including
    location management and GPS coordinate handling.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize device tracker entity.

        Args:
            coordinator: The data update coordinator
            entry: The config entry for this integration instance
            dog_id: Unique identifier for the dog
            entity_key: Unique key for this entity type
            translation_key: Optional translation key for localization
            icon: Optional icon override
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            icon=icon,
        )

    def _get_default_icon(self) -> str:
        """Get default icon for device tracker entities."""
        return ICONS.get("gps", "mdi:crosshairs-gps")

    @property
    def force_update(self) -> bool:
        """Force update for device trackers."""
        return True


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================


def create_entity_id(entry: ConfigEntry, dog_id: str, entity_key: str) -> str:
    """Create a consistent entity ID.

    Args:
        entry: The config entry
        dog_id: The dog identifier
        entity_key: The entity key

    Returns:
        Formatted entity ID string
    """
    return f"{DOMAIN}.{dog_id}_{entity_key}"


def validate_dog_exists(coordinator: PawControlCoordinator, dog_id: str) -> bool:
    """Validate that a dog exists in the coordinator.

    Args:
        coordinator: The data coordinator
        dog_id: The dog identifier to validate

    Returns:
        True if dog exists, False otherwise
    """
    return dog_id in coordinator._dog_data


def get_entity_icon(entity_type: str, entity_key: str) -> str:
    """Get appropriate icon for an entity.

    Args:
        entity_type: The type of entity (sensor, binary_sensor, etc.)
        entity_key: The specific entity key

    Returns:
        Material Design icon string
    """
    # First try specific entity key
    if icon := ICONS.get(entity_key):
        return icon

    # Fall back to entity type
    return ICONS.get(entity_type, "mdi:information")
