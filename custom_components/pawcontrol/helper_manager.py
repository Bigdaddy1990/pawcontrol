"""Home Assistant Helper Management for PawControl integration.

Automatically creates and manages input_boolean, input_datetime, input_number
and other Home Assistant helpers required for PawControl feeding schedules,
health tracking, and automation workflows.

This module implements the helper creation functionality promised in info.md
but was previously missing from the integration.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Final

from homeassistant.components import (
    input_boolean,
    input_datetime,
    input_number,
    input_select,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    CONF_DOG_NAME,
    CONF_DOGS,
    DEFAULT_RESET_TIME,
    HEALTH_STATUS_OPTIONS,
    MEAL_TYPES,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_MEDICATION,
)

_LOGGER = logging.getLogger(__name__)

# Helper entity ID templates
HELPER_FEEDING_MEAL_TEMPLATE: Final[str] = (
    "input_boolean.pawcontrol_{dog_id}_{meal}_fed"
)
HELPER_FEEDING_TIME_TEMPLATE: Final[str] = (
    "input_datetime.pawcontrol_{dog_id}_{meal}_time"
)
HELPER_MEDICATION_REMINDER_TEMPLATE: Final[str] = (
    "input_datetime.pawcontrol_{dog_id}_medication_{med_id}"
)
HELPER_HEALTH_WEIGHT_TEMPLATE: Final[str] = (
    "input_number.pawcontrol_{dog_id}_current_weight"
)
HELPER_HEALTH_STATUS_TEMPLATE: Final[str] = (
    "input_select.pawcontrol_{dog_id}_health_status"
)
HELPER_VISITOR_MODE_TEMPLATE: Final[str] = (
    "input_boolean.pawcontrol_{dog_id}_visitor_mode"
)
HELPER_WALK_REMINDER_TEMPLATE: Final[str] = (
    "input_datetime.pawcontrol_{dog_id}_walk_reminder"
)
HELPER_VET_APPOINTMENT_TEMPLATE: Final[str] = (
    "input_datetime.pawcontrol_{dog_id}_vet_appointment"
)
HELPER_GROOMING_DUE_TEMPLATE: Final[str] = (
    "input_datetime.pawcontrol_{dog_id}_grooming_due"
)

# Default feeding times
DEFAULT_FEEDING_TIMES: Final[dict[str, str]] = {
    "breakfast": "07:00:00",
    "lunch": "12:00:00",
    "dinner": "18:00:00",
    "snack": "15:00:00",
}


class PawControlHelperManager:
    """Manages automatic creation and lifecycle of Home Assistant helpers for PawControl."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the helper manager.

        Args:
            hass: Home Assistant instance
            entry: Config entry for the PawControl integration
        """
        self._hass = hass
        self._entry = entry
        self._created_helpers: set[str] = set()
        self._cleanup_listeners: list[Callable[[], None]] = []

        # Track entities that were created by this manager
        self._managed_entities: dict[str, dict[str, Any]] = {}

    async def async_setup(self) -> None:
        """Setup the helper manager and create required helpers."""
        _LOGGER.debug("Setting up PawControl helper manager")

        try:
            dogs_config = self._entry.data.get(CONF_DOGS, {})
            enabled_modules = self._entry.options.get("modules", {})

            for dog_id, dog_config in dogs_config.items():
                await self._async_create_helpers_for_dog(
                    dog_id, dog_config, enabled_modules
                )

            # Setup daily reset to reset feeding toggles
            await self._async_setup_daily_reset()

            _LOGGER.info(
                "Helper manager setup complete: %d helpers created for %d dogs",
                len(self._created_helpers),
                len(dogs_config),
            )

        except Exception as err:
            _LOGGER.error("Failed to setup helper manager: %s", err)
            raise HomeAssistantError(f"Helper manager setup failed: {err}") from err

    async def _async_create_helpers_for_dog(
        self, dog_id: str, dog_config: dict[str, Any], enabled_modules: dict[str, bool]
    ) -> None:
        """Create all required helpers for a specific dog.

        Args:
            dog_id: Unique identifier for the dog
            dog_config: Dog configuration dictionary
            enabled_modules: Dictionary of enabled modules
        """
        dog_name = dog_config.get(CONF_DOG_NAME, dog_id)

        # Create feeding helpers if feeding module is enabled
        if enabled_modules.get(MODULE_FEEDING, False):
            await self._async_create_feeding_helpers(dog_id, dog_name)

        # Create health helpers if health module is enabled
        if enabled_modules.get(MODULE_HEALTH, False):
            await self._async_create_health_helpers(dog_id, dog_name)

        # Create medication helpers if medication module is enabled
        if enabled_modules.get(MODULE_MEDICATION, False):
            await self._async_create_medication_helpers(dog_id, dog_name)

        # Create visitor mode helper (always created)
        await self._async_create_visitor_helper(dog_id, dog_name)

    async def _async_create_feeding_helpers(self, dog_id: str, dog_name: str) -> None:
        """Create feeding-related helpers for a dog.

        Args:
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
        """
        # Create meal status toggles (input_boolean)
        for meal_type in MEAL_TYPES:
            entity_id = HELPER_FEEDING_MEAL_TEMPLATE.format(
                dog_id=slugify(dog_id), meal=meal_type
            )

            await self._async_create_input_boolean(
                entity_id=entity_id,
                name=f"{dog_name} {meal_type.title()} Fed",
                icon="mdi:food" if meal_type != "snack" else "mdi:food-apple",
                initial=False,
            )

        # Create meal time reminders (input_datetime)
        for meal_type in MEAL_TYPES:
            entity_id = HELPER_FEEDING_TIME_TEMPLATE.format(
                dog_id=slugify(dog_id), meal=meal_type
            )

            default_time = DEFAULT_FEEDING_TIMES.get(meal_type, "12:00:00")

            await self._async_create_input_datetime(
                entity_id=entity_id,
                name=f"{dog_name} {meal_type.title()} Time",
                has_date=False,
                has_time=True,
                initial=default_time,
            )

    async def _async_create_health_helpers(self, dog_id: str, dog_name: str) -> None:
        """Create health-related helpers for a dog.

        Args:
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
        """
        # Current weight tracker (input_number)
        weight_entity_id = HELPER_HEALTH_WEIGHT_TEMPLATE.format(dog_id=slugify(dog_id))

        await self._async_create_input_number(
            entity_id=weight_entity_id,
            name=f"{dog_name} Current Weight",
            min=0.5,
            max=200.0,
            step=0.1,
            unit_of_measurement="kg",
            icon="mdi:weight-kilogram",
            mode="box",
        )

        # Health status selector (input_select)
        status_entity_id = HELPER_HEALTH_STATUS_TEMPLATE.format(dog_id=slugify(dog_id))

        await self._async_create_input_select(
            entity_id=status_entity_id,
            name=f"{dog_name} Health Status",
            options=list(HEALTH_STATUS_OPTIONS),
            initial="good",
            icon="mdi:heart-pulse",
        )

        # Vet appointment reminder (input_datetime)
        vet_entity_id = HELPER_VET_APPOINTMENT_TEMPLATE.format(dog_id=slugify(dog_id))

        await self._async_create_input_datetime(
            entity_id=vet_entity_id,
            name=f"{dog_name} Next Vet Appointment",
            has_date=True,
            has_time=True,
            initial=None,
        )

        # Grooming due date (input_datetime)
        grooming_entity_id = HELPER_GROOMING_DUE_TEMPLATE.format(dog_id=slugify(dog_id))

        await self._async_create_input_datetime(
            entity_id=grooming_entity_id,
            name=f"{dog_name} Grooming Due",
            has_date=True,
            has_time=False,
            initial=None,
        )

    async def _async_create_medication_helpers(
        self, dog_id: str, dog_name: str
    ) -> None:
        """Create medication-related helpers for a dog.

        Args:
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
        """
        # For now, create generic medication reminder
        # In future, this could be expanded to create multiple medication helpers
        # based on dog's medication schedule

        med_entity_id = HELPER_MEDICATION_REMINDER_TEMPLATE.format(
            dog_id=slugify(dog_id), med_id="general"
        )

        await self._async_create_input_datetime(
            entity_id=med_entity_id,
            name=f"{dog_name} Medication Reminder",
            has_date=False,
            has_time=True,
            initial="08:00:00",
        )

    async def _async_create_visitor_helper(self, dog_id: str, dog_name: str) -> None:
        """Create visitor mode helper for a dog.

        Args:
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
        """
        entity_id = HELPER_VISITOR_MODE_TEMPLATE.format(dog_id=slugify(dog_id))

        await self._async_create_input_boolean(
            entity_id=entity_id,
            name=f"{dog_name} Visitor Mode",
            icon="mdi:account-group",
            initial=False,
        )

    async def _async_create_input_boolean(
        self,
        entity_id: str,
        name: str,
        icon: str | None = None,
        initial: bool = False,
    ) -> None:
        """Create an input_boolean helper.

        Args:
            entity_id: Entity ID for the helper
            name: Display name for the helper
            icon: Optional icon
            initial: Initial state
        """
        try:
            # Check if entity already exists
            entity_registry = er.async_get(self._hass)
            if entity_registry.async_get(entity_id):
                _LOGGER.debug("Helper %s already exists, skipping creation", entity_id)
                return

            # Create the helper
            await self._hass.services.async_call(
                input_boolean.DOMAIN,
                "create",
                {
                    "name": name,
                    "icon": icon,
                    "initial": initial,
                },
                target={"entity_id": entity_id},
                blocking=True,
            )

            self._created_helpers.add(entity_id)
            self._managed_entities[entity_id] = {
                "domain": input_boolean.DOMAIN,
                "name": name,
                "icon": icon,
                "initial": initial,
            }

            _LOGGER.debug("Created input_boolean helper: %s", entity_id)

        except Exception as err:
            _LOGGER.warning("Failed to create input_boolean %s: %s", entity_id, err)

    async def _async_create_input_datetime(
        self,
        entity_id: str,
        name: str,
        has_date: bool = True,
        has_time: bool = True,
        initial: str | None = None,
    ) -> None:
        """Create an input_datetime helper.

        Args:
            entity_id: Entity ID for the helper
            name: Display name for the helper
            has_date: Whether the helper includes date
            has_time: Whether the helper includes time
            initial: Initial datetime value (ISO format or time string)
        """
        try:
            # Check if entity already exists
            entity_registry = er.async_get(self._hass)
            if entity_registry.async_get(entity_id):
                _LOGGER.debug("Helper %s already exists, skipping creation", entity_id)
                return

            service_data = {
                "name": name,
                "has_date": has_date,
                "has_time": has_time,
            }

            if initial:
                service_data["initial"] = initial

            # Create the helper
            await self._hass.services.async_call(
                input_datetime.DOMAIN,
                "create",
                service_data,
                target={"entity_id": entity_id},
                blocking=True,
            )

            self._created_helpers.add(entity_id)
            self._managed_entities[entity_id] = {
                "domain": input_datetime.DOMAIN,
                "name": name,
                "has_date": has_date,
                "has_time": has_time,
                "initial": initial,
            }

            _LOGGER.debug("Created input_datetime helper: %s", entity_id)

        except Exception as err:
            _LOGGER.warning("Failed to create input_datetime %s: %s", entity_id, err)

    async def _async_create_input_number(
        self,
        entity_id: str,
        name: str,
        min: float,
        max: float,
        step: float = 1.0,
        unit_of_measurement: str | None = None,
        icon: str | None = None,
        mode: str = "slider",
        initial: float | None = None,
    ) -> None:
        """Create an input_number helper.

        Args:
            entity_id: Entity ID for the helper
            name: Display name for the helper
            min: Minimum value
            max: Maximum value
            step: Step size
            unit_of_measurement: Unit of measurement
            icon: Optional icon
            mode: Input mode (slider, box)
            initial: Initial value
        """
        try:
            # Check if entity already exists
            entity_registry = er.async_get(self._hass)
            if entity_registry.async_get(entity_id):
                _LOGGER.debug("Helper %s already exists, skipping creation", entity_id)
                return

            service_data = {
                "name": name,
                "min": min,
                "max": max,
                "step": step,
                "mode": mode,
            }

            if unit_of_measurement:
                service_data["unit_of_measurement"] = unit_of_measurement
            if icon:
                service_data["icon"] = icon
            if initial is not None:
                service_data["initial"] = initial

            # Create the helper
            await self._hass.services.async_call(
                input_number.DOMAIN,
                "create",
                service_data,
                target={"entity_id": entity_id},
                blocking=True,
            )

            self._created_helpers.add(entity_id)
            self._managed_entities[entity_id] = {
                "domain": input_number.DOMAIN,
                "name": name,
                "min": min,
                "max": max,
                "step": step,
                "mode": mode,
                "unit_of_measurement": unit_of_measurement,
                "icon": icon,
                "initial": initial,
            }

            _LOGGER.debug("Created input_number helper: %s", entity_id)

        except Exception as err:
            _LOGGER.warning("Failed to create input_number %s: %s", entity_id, err)

    async def _async_create_input_select(
        self,
        entity_id: str,
        name: str,
        options: list[str],
        initial: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Create an input_select helper.

        Args:
            entity_id: Entity ID for the helper
            name: Display name for the helper
            options: List of selectable options
            initial: Initial selected option
            icon: Optional icon
        """
        try:
            # Check if entity already exists
            entity_registry = er.async_get(self._hass)
            if entity_registry.async_get(entity_id):
                _LOGGER.debug("Helper %s already exists, skipping creation", entity_id)
                return

            service_data = {
                "name": name,
                "options": options,
            }

            if initial:
                service_data["initial"] = initial
            if icon:
                service_data["icon"] = icon

            # Create the helper
            await self._hass.services.async_call(
                input_select.DOMAIN,
                "create",
                service_data,
                target={"entity_id": entity_id},
                blocking=True,
            )

            self._created_helpers.add(entity_id)
            self._managed_entities[entity_id] = {
                "domain": input_select.DOMAIN,
                "name": name,
                "options": options,
                "initial": initial,
                "icon": icon,
            }

            _LOGGER.debug("Created input_select helper: %s", entity_id)

        except Exception as err:
            _LOGGER.warning("Failed to create input_select %s: %s", entity_id, err)

    async def _async_setup_daily_reset(self) -> None:
        """Setup daily reset to reset feeding toggles."""
        reset_time_str = self._entry.options.get("reset_time", DEFAULT_RESET_TIME)
        reset_time = dt_util.parse_time(reset_time_str)

        if reset_time is None:
            _LOGGER.warning("Invalid reset time, using default")
            reset_time = dt_util.parse_time(DEFAULT_RESET_TIME)

        if reset_time is None:
            return

        @callback
        def _daily_reset(_: datetime | None = None) -> None:
            """Reset feeding toggles daily."""
            self._hass.async_create_task(self._async_reset_feeding_toggles())

        # Schedule daily reset
        unsub = async_track_time_change(
            self._hass,
            _daily_reset,
            hour=reset_time.hour,
            minute=reset_time.minute,
            second=reset_time.second,
        )

        self._cleanup_listeners.append(unsub)
        _LOGGER.debug("Scheduled daily feeding reset at %s", reset_time_str)

    async def _async_reset_feeding_toggles(self) -> None:
        """Reset all feeding toggles to False."""
        try:
            dogs_config = self._entry.data.get(CONF_DOGS, {})

            for dog_id in dogs_config:
                for meal_type in MEAL_TYPES:
                    entity_id = HELPER_FEEDING_MEAL_TEMPLATE.format(
                        dog_id=slugify(dog_id), meal=meal_type
                    )

                    # Reset the toggle to False
                    await self._hass.services.async_call(
                        input_boolean.DOMAIN,
                        "turn_off",
                        target={"entity_id": entity_id},
                        blocking=False,
                    )

            _LOGGER.info("Reset feeding toggles for %d dogs", len(dogs_config))

        except Exception as err:
            _LOGGER.error("Failed to reset feeding toggles: %s", err)

    async def async_add_dog_helpers(
        self, dog_id: str, dog_config: dict[str, Any]
    ) -> None:
        """Add helpers for a newly added dog.

        Args:
            dog_id: Unique identifier for the dog
            dog_config: Dog configuration dictionary
        """
        enabled_modules = self._entry.options.get("modules", {})
        await self._async_create_helpers_for_dog(dog_id, dog_config, enabled_modules)

        _LOGGER.info("Created helpers for new dog: %s", dog_id)

    async def async_remove_dog_helpers(self, dog_id: str) -> None:
        """Remove helpers for a deleted dog.

        Args:
            dog_id: Unique identifier for the dog
        """
        slug_dog_id = slugify(dog_id)
        removed_count = 0

        # Find and remove all helpers for this dog
        for entity_id in list(self._created_helpers):
            if f"pawcontrol_{slug_dog_id}_" in entity_id:
                try:
                    domain = entity_id.split(".")[0]
                    await self._hass.services.async_call(
                        domain,
                        "delete",
                        target={"entity_id": entity_id},
                        blocking=True,
                    )

                    self._created_helpers.discard(entity_id)
                    self._managed_entities.pop(entity_id, None)
                    removed_count += 1

                except Exception as err:
                    _LOGGER.warning("Failed to remove helper %s: %s", entity_id, err)

        _LOGGER.info("Removed %d helpers for dog: %s", removed_count, dog_id)

    async def async_update_dog_helpers(
        self, dog_id: str, dog_config: dict[str, Any]
    ) -> None:
        """Update helpers when dog configuration changes.

        Args:
            dog_id: Unique identifier for the dog
            dog_config: Updated dog configuration dictionary
        """
        # For now, recreate helpers (future optimization: smart updates)
        await self.async_remove_dog_helpers(dog_id)
        await self.async_add_dog_helpers(dog_id, dog_config)

    def get_feeding_status_entity(self, dog_id: str, meal_type: str) -> str:
        """Get the entity ID for a feeding status helper.

        Args:
            dog_id: Unique identifier for the dog
            meal_type: Type of meal (breakfast, lunch, dinner, snack)

        Returns:
            Entity ID for the feeding status helper
        """
        return HELPER_FEEDING_MEAL_TEMPLATE.format(
            dog_id=slugify(dog_id), meal=meal_type
        )

    def get_feeding_time_entity(self, dog_id: str, meal_type: str) -> str:
        """Get the entity ID for a feeding time helper.

        Args:
            dog_id: Unique identifier for the dog
            meal_type: Type of meal (breakfast, lunch, dinner, snack)

        Returns:
            Entity ID for the feeding time helper
        """
        return HELPER_FEEDING_TIME_TEMPLATE.format(
            dog_id=slugify(dog_id), meal=meal_type
        )

    def get_weight_entity(self, dog_id: str) -> str:
        """Get the entity ID for a weight tracking helper.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            Entity ID for the weight helper
        """
        return HELPER_HEALTH_WEIGHT_TEMPLATE.format(dog_id=slugify(dog_id))

    def get_health_status_entity(self, dog_id: str) -> str:
        """Get the entity ID for a health status helper.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            Entity ID for the health status helper
        """
        return HELPER_HEALTH_STATUS_TEMPLATE.format(dog_id=slugify(dog_id))

    def get_visitor_mode_entity(self, dog_id: str) -> str:
        """Get the entity ID for a visitor mode helper.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            Entity ID for the visitor mode helper
        """
        return HELPER_VISITOR_MODE_TEMPLATE.format(dog_id=slugify(dog_id))

    @property
    def created_helpers(self) -> set[str]:
        """Return the set of created helper entity IDs."""
        return self._created_helpers.copy()

    @property
    def managed_entities(self) -> dict[str, dict[str, Any]]:
        """Return information about managed entities."""
        return self._managed_entities.copy()

    async def async_cleanup(self) -> None:
        """Cleanup helper manager resources."""
        # Cancel any scheduled listeners
        for unsub in self._cleanup_listeners:
            try:
                unsub()
            except Exception as err:
                _LOGGER.debug("Error cleaning up listener: %s", err)

        self._cleanup_listeners.clear()

        _LOGGER.debug("Helper manager cleanup complete")

    async def async_unload(self) -> None:
        """Unload helper manager and optionally remove created helpers.

        Note: By default, we do NOT remove helpers on unload to preserve
        user data. Users can manually delete helpers if desired.
        """
        await self.async_cleanup()

        _LOGGER.info(
            "Helper manager unloaded (%d helpers preserved)", len(self._created_helpers)
        )
