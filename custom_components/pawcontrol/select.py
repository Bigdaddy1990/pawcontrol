"""Select platform for Paw Control integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .compat import EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOGS,
    DOMAIN,
    FOOD_BARF,
    FOOD_DRY,
    FOOD_TREAT,
    FOOD_WET,
    GROOMING_BATH,
    GROOMING_BRUSH,
    GROOMING_EARS,
    GROOMING_EYES,
    GROOMING_NAILS,
    GROOMING_TEETH,
    GROOMING_TRIM,
    INTENSITY_HIGH,
    INTENSITY_LOW,
    INTENSITY_MEDIUM,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_TRAINING,
)
from .coordinator import PawControlCoordinator
from .entity import PawControlSelectEntity

PARALLEL_UPDATES = 0
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_select_settings"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control select entities."""
    coordinator: PawControlCoordinator = entry.runtime_data.coordinator

    if not coordinator.last_update_success:
        await coordinator.async_refresh()
        if not coordinator.last_update_success:
            raise PlatformNotReady

    # Load stored values
    store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
    stored_values = await store.async_load() or {}

    entities = []
    dogs = entry.options.get(CONF_DOGS, [])

    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue

        modules = dog.get(CONF_DOG_MODULES, {})
        dog_stored = stored_values.get(dog_id, {})

        # Feeding module selects
        if modules.get(MODULE_FEEDING):
            entities.extend(
                [
                    DefaultFoodTypeSelect(
                        coordinator, entry, dog_id, store, dog_stored
                    ),
                    PreferredMealTimeSelect(
                        coordinator, entry, dog_id, store, dog_stored
                    ),
                ]
            )

        # Grooming module selects
        if modules.get(MODULE_GROOMING):
            entities.append(
                DefaultGroomingTypeSelect(coordinator, entry, dog_id, store, dog_stored)
            )

        # Training module selects
        if modules.get(MODULE_TRAINING):
            entities.extend(
                [
                    TrainingTopicSelect(coordinator, entry, dog_id, store, dog_stored),
                    TrainingIntensitySelect(
                        coordinator, entry, dog_id, store, dog_stored
                    ),
                ]
            )

        # Activity level select (always available)
        entities.append(
            ActivityLevelSelect(coordinator, entry, dog_id, store, dog_stored)
        )

    # Global selects
    entities.append(ExportFormatSelect(hass, coordinator, entry, store))

    async_add_entities(entities, True)


class PawControlSelectWithStorage(PawControlSelectEntity, SelectEntity):
    """Base class for select entities with persistent storage."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict,
        entity_key: str,
        translation_key: str,
        options: list[str],
        icon: str,
        default_option: str | None = None,
    ) -> None:
        """Initialize the select entity with storage."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            entity_key,
            options,
            translation_key=translation_key,
            entity_category=EntityCategory.CONFIG,
        )
        self._store = store
        self._stored_values = stored_values
        self._attr_icon = icon
        self._default_option = default_option or (options[0] if options else None)
        self._current_option = stored_values.get(entity_key, self._default_option)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Update the selected option and persist it."""
        self._current_option = option

        # Load current storage
        all_stored = await self._store.async_load() or {}

        # Update value for this dog and entity
        if self.dog_id not in all_stored:
            all_stored[self.dog_id] = {}
        all_stored[self.dog_id][self.entity_key] = option

        # Save to storage
        await self._store.async_save(all_stored)

        _LOGGER.debug(f"Set {self.entity_key} for {self.dog_name} to {option}")

        # Update in coordinator if needed
        await self._update_coordinator(option)

        self.async_write_ha_state()

    async def _update_coordinator(self, option: str) -> None:
        """Update coordinator with new value (override in subclasses)."""
        pass


class DefaultFoodTypeSelect(PawControlSelectWithStorage):
    """Select entity for default food type."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "default_food_type",
            "default_food_type",
            [FOOD_DRY, FOOD_WET, FOOD_BARF, FOOD_TREAT],
            "mdi:food",
            FOOD_DRY,
        )

    async def _update_coordinator(self, option: str) -> None:
        """Update coordinator with new food type."""
        self.dog_data.setdefault("feeding", {})["default_food_type"] = option
        await self.coordinator.async_request_refresh()


class PreferredMealTimeSelect(PawControlSelectWithStorage):
    """Select entity for preferred meal schedule."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "meal_schedule",
            "meal_schedule",
            ["2 meals", "3 meals", "Free feeding"],
            "mdi:clock-outline",
            "3 meals",
        )

    async def _update_coordinator(self, option: str) -> None:
        """Update coordinator with new meal schedule."""
        self.dog_data.setdefault("feeding", {})["meal_schedule"] = option
        await self.coordinator.async_request_refresh()


class DefaultGroomingTypeSelect(PawControlSelectWithStorage):
    """Select entity for default grooming type."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "default_grooming_type",
            "default_grooming_type",
            [
                GROOMING_BATH,
                GROOMING_BRUSH,
                GROOMING_TRIM,
                GROOMING_NAILS,
                GROOMING_EARS,
                GROOMING_TEETH,
                GROOMING_EYES,
            ],
            "mdi:content-cut",
            GROOMING_BRUSH,
        )

    async def _update_coordinator(self, option: str) -> None:
        """Update coordinator with new grooming type."""
        self.dog_data.setdefault("grooming", {})["grooming_type"] = option
        await self.coordinator.async_request_refresh()


class TrainingTopicSelect(PawControlSelectWithStorage):
    """Select entity for training topic."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "training_topic",
            "training_topic",
            [
                "Basic Commands",
                "Leash Training",
                "Tricks",
                "Agility",
                "Socialization",
                "House Training",
                "Behavior Correction",
            ],
            "mdi:school",
            "Basic Commands",
        )

    async def _update_coordinator(self, option: str) -> None:
        """Update coordinator with new training topic."""
        self.dog_data.setdefault("training", {})["last_topic"] = option
        await self.coordinator.async_request_refresh()


class TrainingIntensitySelect(PawControlSelectWithStorage):
    """Select entity for training intensity."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "training_intensity",
            "training_intensity",
            [INTENSITY_LOW, INTENSITY_MEDIUM, INTENSITY_HIGH],
            "mdi:speedometer",
            INTENSITY_MEDIUM,
        )

    async def _update_coordinator(self, option: str) -> None:
        """Update coordinator with new training intensity."""
        self.dog_data.setdefault("training", {})["intensity"] = option
        await self.coordinator.async_request_refresh()


class ActivityLevelSelect(PawControlSelectWithStorage):
    """Select entity for activity level."""

    def __init__(self, coordinator, entry, dog_id, store, stored_values):
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            store,
            stored_values,
            "activity_level_setting",
            "activity_level_setting",
            [INTENSITY_LOW, INTENSITY_MEDIUM, INTENSITY_HIGH],
            "mdi:run",
            INTENSITY_MEDIUM,
        )

    async def _update_coordinator(self, option: str) -> None:
        """Update coordinator with new activity level."""
        self.dog_data.setdefault("activity", {})["activity_level"] = option
        await self.coordinator.async_request_refresh()


class ExportFormatSelect(SelectEntity):
    """Select entity for export format."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:file-export"
    _attr_options = ["csv", "json", "pdf"]
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        store: Store,
    ):
        """Initialize the select entity."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._store = store
        self._attr_unique_id = f"{entry.entry_id}_global_export_format"
        self._attr_translation_key = "export_format"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "global")},
            "name": "Paw Control System",
            "manufacturer": "Paw Control",
            "model": "Smart Dog Manager",
            "sw_version": "1.1.0",
        }

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Export Format"

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.entry.options.get("export_format", "csv")

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        _LOGGER.info(f"Export format set to {option}")

        # Would update config entry options in production
        # For now just log
        self.async_write_ha_state()
