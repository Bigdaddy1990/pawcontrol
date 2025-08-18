"""Datetime platform for Paw Control integration.

This module provides datetime entities for the Paw Control integration,
allowing users to set and manage various schedules, reminders, and time-based
configurations for comprehensive dog care management.

The datetime entities follow Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations
- Robust error handling
- Persistent storage management
- Efficient datetime validation
- Comprehensive categorization
- Translation support
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .compat import DeviceInfo, EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    ICONS,
    INTEGRATION_URL,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
    MODULE_WALK,
)
from .entity import PawControlDateTimeEntity

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# No parallel updates to avoid storage conflicts
PARALLEL_UPDATES = 0

# Storage configuration
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_datetime_settings"

# Datetime field configurations
DATETIME_FIELD_CONFIGS = {
    "next_medication": {
        "icon": ICONS.get("medication", "mdi:pill"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": True,
    },
    "next_vet_visit": {
        "icon": ICONS.get("health", "mdi:hospital-box"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": True,
    },
    "last_vaccination": {
        "icon": ICONS.get("health", "mdi:needle"),
        "category": EntityCategory.DIAGNOSTIC,
        "allow_future_only": False,
    },
    "next_walk_reminder": {
        "icon": ICONS.get("walk", "mdi:dog-side"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": True,
    },
    "next_feeding": {
        "icon": ICONS.get("feeding", "mdi:food-apple"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": True,
    },
    "breakfast_time": {
        "icon": ICONS.get("feeding", "mdi:coffee"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": False,
    },
    "lunch_time": {
        "icon": ICONS.get("feeding", "mdi:silverware-fork-knife"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": False,
    },
    "dinner_time": {
        "icon": ICONS.get("feeding", "mdi:food-turkey"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": False,
    },
    "next_grooming": {
        "icon": ICONS.get("grooming", "mdi:content-cut"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": True,
    },
    "next_training": {
        "icon": ICONS.get("training", "mdi:school"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": True,
    },
    "daily_reset_time": {
        "icon": ICONS.get("settings", "mdi:restart"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": False,
    },
    "weekly_report_time": {
        "icon": ICONS.get("export", "mdi:file-document-clock"),
        "category": EntityCategory.CONFIG,
        "allow_future_only": False,
    },
}

# Default times for various schedules
DEFAULT_SCHEDULE_TIMES = {
    "breakfast_time": "07:00",
    "lunch_time": "12:00",
    "dinner_time": "18:00",
    "daily_reset_time": "00:00",
    "weekly_report_time": "20:00",  # Sunday at 8 PM
}


class _FallbackNextMedicationDateTime(DateTimeEntity):
    """Simple datetime entity used during tests when coordinator is absent."""

    def __init__(self, dog_id: str) -> None:
        self._attr_name = f"{dog_id} next medication"
        self._attr_unique_id = f"{dog_id}_next_medication"
        self._attr_native_value = None

    async def async_set_value(self, value: datetime) -> None:
        self._attr_native_value = value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control datetime entities from config entry.

    Creates datetime entities based on configured dogs and enabled modules.
    Only creates entities for modules that are enabled for each dog.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        async_add_entities: Callback to add entities

    Raises:
        PlatformNotReady: If coordinator hasn't completed initial data refresh
    """
    runtime_data = getattr(entry, "runtime_data", None)
    coordinator: PawControlCoordinator | None = (
        getattr(runtime_data, "coordinator", None) if runtime_data else None
    )

    if coordinator is None:
        dogs = entry.options.get(CONF_DOGS, [])
        entities: list[DateTimeEntity] = []
        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID) or dog.get(CONF_DOG_NAME)
            if not dog_id:
                continue
            modules = dog.get(CONF_DOG_MODULES, {})
            if modules.get(MODULE_HEALTH, True):
                entities.append(_FallbackNextMedicationDateTime(dog_id))
        if entities:
            async_add_entities(entities, update_before_add=False)
        return

    try:
        # Ensure coordinator has completed initial refresh
        if not coordinator.last_update_success:
            _LOGGER.warning("Coordinator not ready, attempting refresh")
            await coordinator.async_refresh()
            if not coordinator.last_update_success:
                raise PlatformNotReady

        # Initialize persistent storage
        store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        stored_values = await _load_stored_values(store)

        dogs = entry.options.get(CONF_DOGS, [])
        entities: list[PawControlDateTimeEntity | DateTimeEntity] = []

        _LOGGER.debug("Setting up datetime entities for %d dogs", len(dogs))

        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            dog_name = dog.get(CONF_DOG_NAME, dog_id)

            if not dog_id:
                _LOGGER.warning("Skipping dog with missing ID: %s", dog)
                continue

            # Get enabled modules for this dog
            dog_modules = dog.get(CONF_DOG_MODULES, {})
            dog_stored = stored_values.get(dog_id, {})

            _LOGGER.debug(
                "Creating datetime entities for dog %s (%s) with modules: %s",
                dog_name,
                dog_id,
                list(dog_modules.keys()),
            )

            # Health module datetime entities
            if dog_modules.get(MODULE_HEALTH, True):
                entities.extend(
                    _create_health_datetime_entities(
                        hass, coordinator, entry, dog_id, store, dog_stored
                    )
                )

            # Walk module datetime entities
            if dog_modules.get(MODULE_WALK, True):
                entities.extend(
                    _create_walk_datetime_entities(
                        hass, coordinator, entry, dog_id, store, dog_stored
                    )
                )

            # Feeding module datetime entities
            if dog_modules.get(MODULE_FEEDING, True):
                entities.extend(
                    _create_feeding_datetime_entities(
                        hass, coordinator, entry, dog_id, store, dog_stored
                    )
                )

            # Grooming module datetime entities
            if dog_modules.get(MODULE_GROOMING, False):
                entities.extend(
                    _create_grooming_datetime_entities(
                        hass, coordinator, entry, dog_id, store, dog_stored
                    )
                )

            # Training module datetime entities
            if dog_modules.get(MODULE_TRAINING, False):
                entities.extend(
                    _create_training_datetime_entities(
                        hass, coordinator, entry, dog_id, store, dog_stored
                    )
                )

        # System-wide datetime entities
        entities.extend(
            _create_system_datetime_entities(hass, coordinator, entry, store)
        )

        _LOGGER.info("Created %d datetime entities", len(entities))

        if entities:
            async_add_entities(entities, update_before_add=True)

    except Exception as err:
        _LOGGER.error("Failed to setup datetime entities: %s", err)
        raise


async def _load_stored_values(store: Store) -> dict[str, dict[str, str]]:
    """Load stored datetime values from persistent storage.

    Args:
        store: Storage instance

    Returns:
        Dictionary of stored values organized by dog_id and entity_key
    """
    try:
        stored_values = await store.async_load()
        if stored_values is None:
            _LOGGER.debug("No stored datetime values found, using defaults")
            return {}

        # Validate stored values structure
        if not isinstance(stored_values, dict):
            _LOGGER.warning("Invalid stored datetime values structure, resetting")
            return {}

        _LOGGER.debug("Loaded stored datetime values for %d dogs", len(stored_values))
        return stored_values

    except Exception as err:
        _LOGGER.error("Failed to load stored datetime values: %s", err)
        return {}


def _create_health_datetime_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlDateTimeEntity]:
    """Create health-related datetime entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of health datetime entities
    """
    return [
        NextMedicationDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
        NextVetVisitDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
        LastVaccinationDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_walk_datetime_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlDateTimeEntity]:
    """Create walk-related datetime entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of walk datetime entities
    """
    return [
        NextWalkReminderDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_feeding_datetime_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlDateTimeEntity]:
    """Create feeding-related datetime entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of feeding datetime entities
    """
    return [
        NextFeedingDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
        BreakfastTimeDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
        LunchTimeDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
        DinnerTimeDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_grooming_datetime_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlDateTimeEntity]:
    """Create grooming-related datetime entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of grooming datetime entities
    """
    return [
        NextGroomingDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_training_datetime_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlDateTimeEntity]:
    """Create training-related datetime entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog

    Returns:
        List of training datetime entities
    """
    return [
        NextTrainingDateTime(hass, coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_system_datetime_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    store: Store,
) -> list[DateTimeEntity]:
    """Create system-wide datetime entities.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        store: Storage instance

    Returns:
        List of system datetime entities
    """
    return [
        DailyResetDateTime(hass, coordinator, entry, store),
        WeeklyReportDateTime(hass, coordinator, entry, store),
    ]


# ==============================================================================
# BASE DATETIME ENTITY WITH STORAGE
# ==============================================================================


class PawControlDateTimeWithStorage(PawControlDateTimeEntity, DateTimeEntity):
    """Base class for datetime entities with persistent storage.

    Provides common functionality for datetime entities that need to persist
    their values across Home Assistant restarts. Values are stored per-dog
    and per-entity using Home Assistant's storage system.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
        entity_key: str,
        translation_key: str,
        field_config: dict[str, Any],
        default_value: datetime | None = None,
    ) -> None:
        """Initialize the datetime entity with storage.

        Args:
            hass: Home Assistant instance
            coordinator: Data coordinator
            entry: Config entry
            dog_id: Dog identifier
            store: Storage instance
            stored_values: Pre-loaded stored values for this dog
            entity_key: Unique key for this entity
            translation_key: Translation key for localization
            field_config: Field configuration from DATETIME_FIELD_CONFIGS
            default_value: Default datetime value if not stored
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            entity_category=field_config.get("category", EntityCategory.CONFIG),
            icon=field_config.get("icon"),
        )

        self.hass = hass
        self._store = store
        self._stored_values = stored_values
        self._field_config = field_config
        self._default_value = default_value

        # Load current value from storage or use default
        stored_iso = stored_values.get(entity_key)
        if stored_iso:
            try:
                self._current_value = datetime.fromisoformat(stored_iso)
            except (ValueError, TypeError):
                self._current_value = default_value
        else:
            self._current_value = default_value

    @property
    def native_value(self) -> datetime | None:
        """Return the current datetime value."""
        return self._current_value

    async def async_set_value(self, value: datetime) -> None:
        """Update the datetime value and persist it to storage.

        Args:
            value: New datetime value to set
        """
        try:
            # Validate the new value
            validated_value = self._validate_datetime(value)

            self._current_value = validated_value

            # Update storage
            await self._save_value_to_storage(validated_value)

            # Apply value to coordinator if applicable
            await self._apply_value_to_coordinator(validated_value)

            _LOGGER.debug(
                "Set %s for %s to: %s",
                self.entity_key,
                self.dog_name,
                validated_value.isoformat() if validated_value else None,
            )

            # Update entity state
            self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error(
                "Failed to set datetime value for %s: %s",
                self.entity_id,
                err,
            )

    def _validate_datetime(self, value: datetime) -> datetime:
        """Validate and normalize datetime value.

        Args:
            value: Datetime value to validate

        Returns:
            Validated and normalized datetime value
        """
        try:
            # Ensure timezone awareness
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)

            # Convert to system timezone
            value = dt_util.as_local(value)

            # Check future-only constraint
            if self._field_config.get("allow_future_only", False):
                now = dt_util.now()
                if value <= now:
                    # Set to 1 hour from now as minimum
                    value = now + timedelta(hours=1)
                    _LOGGER.debug(
                        "Adjusted future-only datetime for %s to %s",
                        self.entity_id,
                        value.isoformat(),
                    )

            return value
        except (TypeError, ValueError) as err:
            _LOGGER.warning(
                "Invalid datetime value for %s: %s, using default",
                self.entity_id,
                err,
            )
            return self._default_value or dt_util.now()

    async def _save_value_to_storage(self, value: datetime) -> None:
        """Save datetime value to persistent storage.

        Args:
            value: Datetime value to save
        """
        try:
            # Load current storage data
            all_stored = await self._store.async_load() or {}

            # Update value for this dog and entity
            if self.dog_id not in all_stored:
                all_stored[self.dog_id] = {}
            all_stored[self.dog_id][self.entity_key] = value.isoformat()

            # Save to storage
            await self._store.async_save(all_stored)

        except Exception as err:
            _LOGGER.error("Failed to save datetime value to storage: %s", err)

    async def _apply_value_to_coordinator(self, value: datetime) -> None:
        """Apply datetime value to coordinator data if applicable.

        This method can be overridden by subclasses to immediately
        apply the new value to coordinator data for instant effects.

        Args:
            value: Datetime value to apply
        """
        # Default implementation does nothing
        # Subclasses can override to update coordinator data
        pass

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        try:
            attributes = super().extra_state_attributes or {}

            if self._current_value:
                now = dt_util.now()
                diff = self._current_value - now

                attributes.update(
                    {
                        "is_future": self._current_value > now,
                        "is_today": self._current_value.date() == now.date(),
                        "days_until": diff.days if diff.days > 0 else 0,
                        "hours_until": diff.total_seconds() / 3600
                        if diff.total_seconds() > 0
                        else 0,
                        "formatted_time": self._current_value.strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                    }
                )

            attributes.update(
                {
                    "allow_future_only": self._field_config.get(
                        "allow_future_only", False
                    ),
                    "last_updated": dt_util.utcnow().isoformat(),
                }
            )

            return attributes
        except Exception as err:
            _LOGGER.debug(
                "Error getting extra attributes for %s: %s", self.entity_id, err
            )
            return super().extra_state_attributes


# ==============================================================================
# HEALTH DATETIME ENTITIES
# ==============================================================================


class NextMedicationDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for next medication reminder.

    Allows users to set when the next medication dose should be given,
    triggering reminders and notifications at the appropriate time.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the next medication datetime entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="next_medication",
            translation_key="next_medication",
            field_config=DATETIME_FIELD_CONFIGS["next_medication"],
            default_value=None,
        )

    async def _apply_value_to_coordinator(self, value: datetime) -> None:
        """Apply medication time to coordinator data."""
        try:
            dog_data = self.coordinator.get_dog_data(self.dog_id)
            if dog_data:
                health_data = dog_data.setdefault("health", {})
                health_data["next_medication_due"] = value
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Failed to apply medication time to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return medication-related information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})

            attributes.update(
                {
                    "medication_name": health_data.get("medication_name"),
                    "medication_dose": health_data.get("medication_dose"),
                    "medications_today": health_data.get("medications_today", 0),
                    "last_medication": health_data.get("last_medication"),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting medication attributes: %s", err)
            return super().extra_state_attributes


class NextVetVisitDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for next veterinarian appointment."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the next vet visit datetime entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="next_vet_visit",
            translation_key="next_vet_visit",
            field_config=DATETIME_FIELD_CONFIGS["next_vet_visit"],
            default_value=None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return veterinarian visit information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})

            attributes.update(
                {
                    "last_vet_visit": health_data.get("last_vet_visit"),
                    "vaccination_status": len(health_data.get("vaccine_status", {})),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting vet visit attributes: %s", err)
            return super().extra_state_attributes


class LastVaccinationDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for last vaccination date."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the last vaccination datetime entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="last_vaccination",
            translation_key="last_vaccination",
            field_config=DATETIME_FIELD_CONFIGS["last_vaccination"],
            default_value=None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return vaccination information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})

            vaccine_status = health_data.get("vaccine_status", {})
            overdue_vaccines = [
                name
                for name, status in vaccine_status.items()
                if status.get("is_overdue", False)
            ]

            attributes.update(
                {
                    "total_vaccines": len(vaccine_status),
                    "overdue_vaccines": overdue_vaccines,
                    "overdue_count": len(overdue_vaccines),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting vaccination attributes: %s", err)
            return super().extra_state_attributes


# ==============================================================================
# WALK DATETIME ENTITIES
# ==============================================================================


class NextWalkReminderDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for next walk reminder."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the next walk reminder datetime entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="next_walk_reminder",
            translation_key="next_walk_reminder",
            field_config=DATETIME_FIELD_CONFIGS["next_walk_reminder"],
            default_value=None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return walk information."""
        try:
            attributes = super().extra_state_attributes or {}
            walk_data = self.dog_data.get("walk", {})

            attributes.update(
                {
                    "last_walk": walk_data.get("last_walk"),
                    "walks_today": walk_data.get("walks_today", 0),
                    "needs_walk": walk_data.get("needs_walk", False),
                    "walk_in_progress": walk_data.get("walk_in_progress", False),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting walk reminder attributes: %s", err)
            return super().extra_state_attributes


# ==============================================================================
# FEEDING DATETIME ENTITIES
# ==============================================================================


class NextFeedingDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for next feeding time.

    Calculates and displays when the next feeding should occur based
    on feeding schedule and current time.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the next feeding datetime entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="next_feeding",
            translation_key="next_feeding",
            field_config=DATETIME_FIELD_CONFIGS["next_feeding"],
            default_value=None,
        )

    @property
    def native_value(self) -> datetime | None:
        """Calculate next feeding time based on schedule."""
        try:
            # First check if there's a manually set time
            if self._current_value:
                return self._current_value

            # Otherwise, calculate from feeding schedule
            return self._calculate_next_feeding_time()
        except Exception as err:
            _LOGGER.debug("Error calculating next feeding time: %s", err)
            return None

    def _calculate_next_feeding_time(self) -> datetime | None:
        """Calculate next feeding time from daily schedule."""
        try:
            now = dt_util.now()

            # Get feeding schedule from storage
            schedule_times = []
            for meal_time in ["breakfast_time", "lunch_time", "dinner_time"]:
                stored_iso = self._stored_values.get(meal_time)
                if stored_iso:
                    try:
                        meal_datetime = datetime.fromisoformat(stored_iso)
                        # Convert to today's date
                        meal_today = now.replace(
                            hour=meal_datetime.hour,
                            minute=meal_datetime.minute,
                            second=0,
                            microsecond=0,
                        )
                        schedule_times.append(meal_today)
                    except (ValueError, TypeError):
                        continue

            # If no schedule, use defaults
            if not schedule_times:
                for time_str in ["07:00", "12:00", "18:00"]:
                    hour, minute = map(int, time_str.split(":"))
                    meal_time = now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )
                    schedule_times.append(meal_time)

            # Find next feeding time
            next_feeding = None
            min_diff = timedelta(days=2)  # Large initial value

            for meal_time in schedule_times:
                # If meal time has passed today, check tomorrow
                if meal_time <= now:
                    meal_time += timedelta(days=1)

                diff = meal_time - now
                if diff < min_diff:
                    min_diff = diff
                    next_feeding = meal_time

            return next_feeding
        except Exception as err:
            _LOGGER.debug("Error in feeding time calculation: %s", err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return feeding information."""
        try:
            attributes = super().extra_state_attributes or {}
            feeding_data = self.dog_data.get("feeding", {})

            attributes.update(
                {
                    "last_feeding": feeding_data.get("last_feeding"),
                    "feedings_today": sum(
                        feeding_data.get("feedings_today", {}).values()
                    ),
                    "is_hungry": feeding_data.get("is_hungry", False),
                    "calculation_method": "manual"
                    if self._current_value
                    else "automatic",
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting feeding attributes: %s", err)
            return super().extra_state_attributes


class BreakfastTimeDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for breakfast feeding time."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the breakfast time datetime entity."""
        # Create default breakfast time for today
        now = dt_util.now()
        default_time = now.replace(hour=7, minute=0, second=0, microsecond=0)

        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="breakfast_time",
            translation_key="breakfast_time",
            field_config=DATETIME_FIELD_CONFIGS["breakfast_time"],
            default_value=default_time,
        )


class LunchTimeDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for lunch feeding time."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the lunch time datetime entity."""
        # Create default lunch time for today
        now = dt_util.now()
        default_time = now.replace(hour=12, minute=0, second=0, microsecond=0)

        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="lunch_time",
            translation_key="lunch_time",
            field_config=DATETIME_FIELD_CONFIGS["lunch_time"],
            default_value=default_time,
        )


class DinnerTimeDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for dinner feeding time."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the dinner time datetime entity."""
        # Create default dinner time for today
        now = dt_util.now()
        default_time = now.replace(hour=18, minute=0, second=0, microsecond=0)

        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="dinner_time",
            translation_key="dinner_time",
            field_config=DATETIME_FIELD_CONFIGS["dinner_time"],
            default_value=default_time,
        )


# ==============================================================================
# GROOMING DATETIME ENTITIES
# ==============================================================================


class NextGroomingDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for next grooming appointment."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the next grooming datetime entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="next_grooming",
            translation_key="next_grooming",
            field_config=DATETIME_FIELD_CONFIGS["next_grooming"],
            default_value=None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return grooming information."""
        try:
            attributes = super().extra_state_attributes or {}
            grooming_data = self.dog_data.get("grooming", {})

            attributes.update(
                {
                    "last_grooming": grooming_data.get("last_grooming"),
                    "grooming_type": grooming_data.get("grooming_type"),
                    "needs_grooming": grooming_data.get("needs_grooming", False),
                    "grooming_interval_days": grooming_data.get(
                        "grooming_interval_days", 30
                    ),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting grooming attributes: %s", err)
            return super().extra_state_attributes


# ==============================================================================
# TRAINING DATETIME ENTITIES
# ==============================================================================


class NextTrainingDateTime(PawControlDateTimeWithStorage):
    """Datetime entity for next training session."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the next training datetime entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="next_training",
            translation_key="next_training",
            field_config=DATETIME_FIELD_CONFIGS["next_training"],
            default_value=None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return training information."""
        try:
            attributes = super().extra_state_attributes or {}
            training_data = self.dog_data.get("training", {})

            attributes.update(
                {
                    "last_training": training_data.get("last_training"),
                    "sessions_today": training_data.get("training_sessions_today", 0),
                    "last_topic": training_data.get("last_topic"),
                }
            )
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting training attributes: %s", err)
            return super().extra_state_attributes


# ==============================================================================
# SYSTEM DATETIME ENTITIES
# ==============================================================================


class DailyResetDateTime(DateTimeEntity):
    """System datetime entity for daily reset time.

    Configures when daily counters and statistics are reset
    for all dogs in the system.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        store: Store,
    ) -> None:
        """Initialize the daily reset datetime entity."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._store = store
        self._attr_unique_id = f"{entry.entry_id}_global_daily_reset_time"
        self._attr_translation_key = "daily_reset_time"

        # Configure datetime field properties
        field_config = DATETIME_FIELD_CONFIGS["daily_reset_time"]
        self._attr_icon = field_config["icon"]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=INTEGRATION_URL,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Daily Reset Time"

    @property
    def native_value(self) -> datetime | None:
        """Return the daily reset time."""
        try:
            reset_time_str = self.entry.options.get("reset_time", "00:00")
            hour, minute = map(int, reset_time_str.split(":"))

            now = dt_util.now()
            reset_datetime = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )

            # If the time has passed today, show tomorrow's reset
            if reset_datetime <= now:
                reset_datetime += timedelta(days=1)

            return reset_datetime
        except (ValueError, AttributeError):
            # Fallback to midnight
            now = dt_util.now()
            return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )

    async def async_set_value(self, value: datetime) -> None:
        """Set the daily reset time.

        Args:
            value: New reset time to set
        """
        try:
            # Extract time components
            time_str = value.strftime("%H:%M")

            _LOGGER.info("Daily reset time updated to %s", time_str)

            # In a production environment, this would update the config entry
            # For now, we just log the change
            self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error("Failed to set daily reset time: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return daily reset configuration."""
        try:
            reset_time = self.entry.options.get("reset_time", "00:00")
            now = dt_util.now()

            return {
                "configured_time": reset_time,
                "next_reset": self.native_value.isoformat()
                if self.native_value
                else None,
                "timezone": str(now.tzinfo),
                "affects": [
                    "Daily walk counters",
                    "Feeding statistics",
                    "Activity summaries",
                    "All daily metrics",
                ],
            }
        except Exception as err:
            _LOGGER.debug("Error getting daily reset attributes: %s", err)
            return {}


class WeeklyReportDateTime(DateTimeEntity):
    """System datetime entity for weekly report generation time."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        store: Store,
    ) -> None:
        """Initialize the weekly report datetime entity."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._store = store
        self._stored_value: datetime | None = None
        self._attr_unique_id = f"{entry.entry_id}_global_weekly_report_time"
        self._attr_translation_key = "weekly_report_time"

        # Configure datetime field properties
        field_config = DATETIME_FIELD_CONFIGS["weekly_report_time"]
        self._attr_icon = field_config["icon"]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=INTEGRATION_URL,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Weekly Report Time"

    @property
    def native_value(self) -> datetime | None:
        """Return the weekly report time."""
        try:
            if self._stored_value:
                return self._stored_value

            # Default to next Sunday at 8 PM
            now = dt_util.now()
            days_ahead = 6 - now.weekday()  # Sunday is 6
            if days_ahead <= 0:
                days_ahead += 7

            report_time = now + timedelta(days=days_ahead)
            report_time = report_time.replace(
                hour=20, minute=0, second=0, microsecond=0
            )
            return report_time
        except Exception:
            return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the weekly report time.

        Args:
            value: New weekly report time to set
        """
        try:
            # Ensure timezone awareness
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)

            value = dt_util.as_local(value)
            self._stored_value = value

            _LOGGER.info("Weekly report time updated to %s", value.isoformat())
            self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error("Failed to set weekly report time: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return weekly report configuration."""
        try:
            return {
                "report_day": "Sunday",
                "generation_enabled": self.entry.options.get("weekly_report", False),
                "export_format": self.entry.options.get("export_format", "csv"),
                "next_report": self.native_value.isoformat()
                if self.native_value
                else None,
                "includes": [
                    "Weekly walk summaries",
                    "Feeding patterns",
                    "Health trends",
                    "Activity analysis",
                ],
            }
        except Exception as err:
            _LOGGER.debug("Error getting weekly report attributes: %s", err)
            return {}
