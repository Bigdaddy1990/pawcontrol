"""Home Assistant Helper Management for PawControl integration.

Automatically creates and manages input_boolean, input_datetime, input_number
and other Home Assistant helpers required for PawControl feeding schedules,
health tracking, and automation workflows.

This module implements the helper creation functionality promised in info.md
but was previously missing from the integration.

Quality Scale: Bronze target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import datetime
from typing import Any, Final, cast

from homeassistant.components import (
    input_boolean,
    input_datetime,
    input_number,
    input_select,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .compat import ConfigEntry, HomeAssistantError
from .const import (
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_MODULES,
    DEFAULT_RESET_TIME,
    HEALTH_STATUS_OPTIONS,
    MEAL_TYPES,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_MEDICATION,
)
from .coordinator_support import CacheMonitorRegistrar
from .types import (
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    MODULE_TOGGLE_KEYS,
    CacheDiagnosticsMetadata,
    CacheDiagnosticsSnapshot,
    DogConfigData,
    DogModulesConfig,
    HelperManagerSnapshot,
    HelperManagerStats,
    ModuleToggleKey,
    ensure_dog_modules_config,
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


# ---------------------------------------------------------------------------
# Diagnostics helpers


def _collate_entity_domains(entities: Mapping[str, dict[str, Any]]) -> dict[str, int]:
    """Return a histogram of entity domains managed by the helper manager."""

    domains: dict[str, int] = {}
    for entity_id in entities:
        if isinstance(entity_id, str) and "." in entity_id:
            domain = entity_id.split(".", 1)[0]
        else:
            domain = "unknown"
        domains[domain] = domains.get(domain, 0) + 1
    return domains


class _HelperManagerCacheMonitor:
    """Expose helper manager state to the cache monitor registry."""

    __slots__ = ("_manager",)

    def __init__(self, manager: PawControlHelperManager) -> None:
        self._manager = manager

    def _build_payload(
        self,
    ) -> tuple[HelperManagerStats, HelperManagerSnapshot, CacheDiagnosticsMetadata]:
        manager = self._manager
        created_helpers: Collection[str] = getattr(manager, "_created_helpers", set())
        managed_entities: Mapping[str, dict[str, Any]] = getattr(
            manager, "_managed_entities", {}
        )
        dog_helpers: Mapping[str, Collection[str]] = getattr(
            manager, "_dog_helpers", {}
        )
        cleanup_listeners: Sequence[Callable[[], None]] = getattr(
            manager, "_cleanup_listeners", []
        )

        per_dog: dict[str, int] = {
            str(dog_id): len(helpers)
            for dog_id, helpers in dog_helpers.items()
            if isinstance(helpers, Collection)
        }

        domains = _collate_entity_domains(managed_entities)

        stats: HelperManagerStats = {
            "helpers": len(created_helpers),
            "dogs": len(per_dog),
            "managed_entities": len(managed_entities),
        }

        snapshot: HelperManagerSnapshot = {
            "per_dog": per_dog,
            "entity_domains": domains,
        }

        diagnostics: CacheDiagnosticsMetadata = {
            "per_dog_helpers": per_dog,
            "entity_domains": domains,
            "cleanup_listeners": len(cleanup_listeners),
            "daily_reset_configured": bool(
                getattr(manager, "_daily_reset_configured", False)
            ),
        }

        return stats, snapshot, diagnostics

    def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:
        stats, snapshot, diagnostics = self._build_payload()
        return {
            "stats": cast(dict[str, Any], dict(stats)),
            "snapshot": cast(dict[str, Any], dict(snapshot)),
            "diagnostics": diagnostics,
        }

    def get_stats(self) -> dict[str, Any]:
        stats, _snapshot, _diagnostics = self._build_payload()
        return cast(dict[str, Any], dict(stats))

    def get_diagnostics(self) -> CacheDiagnosticsMetadata:
        _stats, _snapshot, diagnostics = self._build_payload()
        return diagnostics


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
        self._dog_helpers: dict[str, list[str]] = {}
        self._daily_reset_configured = False

    async def async_initialize(self) -> None:
        """Reset internal state prior to creating helpers."""

        for unsubscribe in self._cleanup_listeners:
            try:
                unsubscribe()
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.debug(
                    "Error cleaning up listener during initialization: %s", err
                )

        self._cleanup_listeners.clear()
        self._created_helpers.clear()
        self._managed_entities.clear()
        self._dog_helpers.clear()
        self._daily_reset_configured = False

        _LOGGER.debug("Helper manager initialized for entry %s", self._entry.entry_id)

    def register_cache_monitors(
        self, registrar: CacheMonitorRegistrar, *, prefix: str = "helpers"
    ) -> None:
        """Register helper diagnostics with the data manager cache monitor."""

        if registrar is None:
            raise ValueError("registrar is required")

        monitor = _HelperManagerCacheMonitor(self)
        registrar.register_cache_monitor(f"{prefix}_cache", monitor)

    @staticmethod
    def _normalize_dogs_config(dogs: Any) -> list[DogConfigData]:
        """Convert raw config entry dog data into typed dictionaries."""

        normalized: list[DogConfigData] = []

        if isinstance(dogs, Mapping):
            for dog_id, dog_config in dogs.items():
                if not isinstance(dog_config, Mapping):
                    continue
                dog_dict: dict[str, Any] = dict(dog_config)
                dog_dict.setdefault(DOG_ID_FIELD, str(dog_id))
                dog_dict.setdefault(DOG_NAME_FIELD, str(dog_dict[DOG_ID_FIELD]))
                normalized.append(cast(DogConfigData, dog_dict))
            return normalized

        if isinstance(dogs, Sequence) and not isinstance(dogs, str | bytes):
            for dog_config in dogs:
                if not isinstance(dog_config, Mapping):
                    continue
                dog_dict = dict(dog_config)
                dog_id = dog_dict.get(DOG_ID_FIELD)
                if not isinstance(dog_id, str):
                    continue
                if not isinstance(dog_dict.get(DOG_NAME_FIELD), str):
                    dog_dict[DOG_NAME_FIELD] = dog_id
                normalized.append(cast(DogConfigData, dog_dict))

        return normalized

    @staticmethod
    def _normalize_enabled_modules(modules: Any) -> frozenset[str]:
        """Return a normalized set of enabled module identifiers."""

        normalized: set[str] = set()

        if isinstance(modules, Mapping):
            for module, enabled in modules.items():
                if (
                    isinstance(module, str)
                    and module in MODULE_TOGGLE_KEYS
                    and bool(enabled)
                ):
                    normalized.add(module)
            return frozenset(normalized)

        if isinstance(modules, Sequence) and not isinstance(modules, str | bytes):
            for module in modules:
                if isinstance(module, str) and module in MODULE_TOGGLE_KEYS:
                    normalized.add(module)
            return frozenset(normalized)

        if isinstance(modules, str) and modules in MODULE_TOGGLE_KEYS:
            return frozenset({modules})

        return frozenset()

    async def async_setup(self) -> None:
        """Setup the helper manager and create required helpers."""
        _LOGGER.debug("Setting up PawControl helper manager")

        try:
            dogs_config = self._normalize_dogs_config(
                self._entry.data.get(CONF_DOGS, [])
            )
            modules_option = (
                self._entry.options.get(CONF_MODULES)
                or self._entry.options.get("modules")
                or []
            )
            enabled_modules = self._normalize_enabled_modules(modules_option)

            await self.async_initialize()
            created_helpers = await self.async_create_helpers_for_dogs(
                dogs_config, enabled_modules
            )

            _LOGGER.info(
                "Helper manager setup complete: %d helpers created for %d dogs",
                len(self._created_helpers),
                len(created_helpers),
            )

        except Exception as err:
            _LOGGER.error("Failed to setup helper manager: %s", err)
            raise HomeAssistantError(f"Helper manager setup failed: {err}") from err

    async def async_create_helpers_for_dogs(
        self,
        dogs: Sequence[DogConfigData],
        enabled_modules: Collection[str] | Mapping[str, bool],
    ) -> dict[str, list[str]]:
        """Create helpers for all provided dogs and return created entity IDs."""

        created: dict[str, list[str]] = {}
        enabled_lookup: dict[str, bool] = {}
        if isinstance(enabled_modules, Mapping):
            for module, value in enabled_modules.items():
                if isinstance(module, str) and module in MODULE_TOGGLE_KEYS:
                    enabled_lookup[module] = bool(value)
        else:
            for module in enabled_modules:
                if isinstance(module, str) and module in MODULE_TOGGLE_KEYS:
                    enabled_lookup[module] = True

        for dog in dogs:
            dog_id = dog.get(DOG_ID_FIELD)
            if not isinstance(dog_id, str) or not dog_id:
                _LOGGER.debug(
                    "Skipping helper creation for dog without valid id: %s", dog
                )
                continue

            modules_config = ensure_dog_modules_config(dog)
            for module, enabled in enabled_lookup.items():
                module_key = cast(ModuleToggleKey, module)
                modules_config[module_key] = enabled

            before_creation = set(self._created_helpers)
            await self._async_create_helpers_for_dog(dog_id, dog, modules_config)
            new_helpers = sorted(self._created_helpers - before_creation)

            if not new_helpers:
                continue

            existing = self._dog_helpers.setdefault(dog_id, [])
            for helper in new_helpers:
                if helper not in existing:
                    existing.append(helper)

            created[dog_id] = new_helpers
            _LOGGER.debug("Created %d helpers for dog %s", len(new_helpers), dog_id)

        if created:
            await self._ensure_daily_reset_listener()

        return created

    async def _async_create_helpers_for_dog(
        self,
        dog_id: str,
        dog_config: DogConfigData,
        enabled_modules: DogModulesConfig,
    ) -> None:
        """Create all required helpers for a specific dog.

        Args:
            dog_id: Unique identifier for the dog
            dog_config: Dog configuration dictionary
            enabled_modules: Dictionary of enabled modules
        """
        dog_name_raw = dog_config.get(DOG_NAME_FIELD)
        dog_name = (
            dog_name_raw if isinstance(dog_name_raw, str) and dog_name_raw else dog_id
        )

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

    async def _ensure_daily_reset_listener(self) -> None:
        """Ensure the daily reset listener is configured exactly once."""

        if self._daily_reset_configured:
            return

        try:
            await self._async_setup_daily_reset()
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.warning("Failed to configure daily reset listener: %s", err)
        else:
            self._daily_reset_configured = True

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
            dog_ids: list[str] = list(self._dog_helpers)

            if not dog_ids:
                dogs_raw = self._entry.data.get(CONF_DOGS, [])
                if isinstance(dogs_raw, Mapping):
                    dog_ids = [str(dog_id) for dog_id in dogs_raw]
                elif isinstance(dogs_raw, Sequence) and not isinstance(
                    dogs_raw, str | bytes
                ):
                    for dog_config in dogs_raw:
                        if isinstance(dog_config, Mapping):
                            dog_id = dog_config.get(CONF_DOG_ID)
                            if isinstance(dog_id, str):
                                dog_ids.append(dog_id)

            for dog_id in dog_ids:
                slug_dog_id = slugify(dog_id)
                for meal_type in MEAL_TYPES:
                    entity_id = HELPER_FEEDING_MEAL_TEMPLATE.format(
                        dog_id=slug_dog_id, meal=meal_type
                    )

                    await self._hass.services.async_call(
                        input_boolean.DOMAIN,
                        "turn_off",
                        target={"entity_id": entity_id},
                        blocking=False,
                    )

            _LOGGER.info("Reset feeding toggles for %d dogs", len(dog_ids))

        except Exception as err:
            _LOGGER.error("Failed to reset feeding toggles: %s", err)

    async def async_add_dog_helpers(
        self, dog_id: str, dog_config: Mapping[str, Any]
    ) -> None:
        """Add helpers for a newly added dog.

        Args:
            dog_id: Unique identifier for the dog
            dog_config: Dog configuration dictionary
        """
        dog_data_raw: dict[str, Any] = dict(dog_config)
        dog_data_raw[DOG_ID_FIELD] = dog_id
        dog_name_value = dog_data_raw.get(DOG_NAME_FIELD)
        if not isinstance(dog_name_value, str) or not dog_name_value:
            dog_data_raw[DOG_NAME_FIELD] = dog_id

        dog_data = cast(DogConfigData, dog_data_raw)

        modules_option = (
            self._entry.options.get(CONF_MODULES)
            or self._entry.options.get("modules")
            or []
        )
        enabled_modules = self._normalize_enabled_modules(modules_option)

        await self.async_create_helpers_for_dogs([dog_data], enabled_modules)

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

        self._dog_helpers.pop(dog_id, None)

        _LOGGER.info("Removed %d helpers for dog: %s", removed_count, dog_id)

    async def async_update_dog_helpers(
        self, dog_id: str, dog_config: Mapping[str, Any]
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

    def get_helper_count(self) -> int:
        """Return the total number of helpers managed by this instance."""

        return len(self._created_helpers)

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
        self._daily_reset_configured = False
        self._dog_helpers.clear()

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
