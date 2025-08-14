"""Text platform for Paw Control integration.

This module provides text input entities for the Paw Control integration,
allowing users to enter and store various textual information like notes,
descriptions, and configuration values for comprehensive dog care management.

The text entities follow Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations
- Robust error handling
- Persistent storage management
- Efficient text validation
- Comprehensive categorization
- Translation support
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from homeassistant.components.text import TextEntity, TextMode
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
    MAX_NOTE_LENGTH,
    MAX_STRING_LENGTH,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
    SERVICE_LOG_HEALTH,
)
from .entity import PawControlTextEntity

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# No parallel updates to avoid storage conflicts
PARALLEL_UPDATES = 0

# Storage configuration
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_text_settings"

# Text field configurations with validation rules
TEXT_FIELD_CONFIGS = {
    "health_notes": {
        "max_length": MAX_NOTE_LENGTH,
        "mode": TextMode.TEXT,
        "icon": ICONS.get("health", "mdi:note-medical"),
        "category": EntityCategory.DIAGNOSTIC,
    },
    "medication_notes": {
        "max_length": MAX_STRING_LENGTH,
        "mode": TextMode.TEXT,
        "icon": ICONS.get("medication", "mdi:pill"),
        "category": EntityCategory.DIAGNOSTIC,
    },
    "vet_notes": {
        "max_length": MAX_NOTE_LENGTH,
        "mode": TextMode.TEXT,
        "icon": ICONS.get("health", "mdi:hospital-box"),
        "category": EntityCategory.DIAGNOSTIC,
    },
    "training_notes": {
        "max_length": MAX_STRING_LENGTH,
        "mode": TextMode.TEXT,
        "icon": ICONS.get("training", "mdi:school"),
        "category": EntityCategory.DIAGNOSTIC,
    },
    "grooming_notes": {
        "max_length": MAX_STRING_LENGTH,
        "mode": TextMode.TEXT,
        "icon": ICONS.get("grooming", "mdi:content-cut"),
        "category": EntityCategory.DIAGNOSTIC,
    },
    "general_notes": {
        "max_length": MAX_NOTE_LENGTH,
        "mode": TextMode.TEXT,
        "icon": ICONS.get("statistics", "mdi:note-text"),
        "category": EntityCategory.DIAGNOSTIC,
    },
    "emergency_contact": {
        "max_length": MAX_STRING_LENGTH,
        "mode": TextMode.TEXT,
        "icon": ICONS.get("emergency", "mdi:phone"),
        "category": EntityCategory.CONFIG,
    },
    "veterinarian_contact": {
        "max_length": MAX_STRING_LENGTH,
        "mode": TextMode.TEXT,
        "icon": ICONS.get("health", "mdi:stethoscope"),
        "category": EntityCategory.CONFIG,
    },
    "export_path": {
        "max_length": 500,
        "mode": TextMode.TEXT,
        "icon": ICONS.get("export", "mdi:folder-export"),
        "category": EntityCategory.CONFIG,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control text entities from config entry.
    
    Creates text entities based on configured dogs and enabled modules.
    Only creates entities for modules that are enabled for each dog.
    
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

        # Initialize persistent storage
        store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        stored_values = await _load_stored_values(store)

        dogs = entry.options.get(CONF_DOGS, [])
        entities: list[PawControlTextEntity | TextEntity] = []

        _LOGGER.debug("Setting up text entities for %d dogs", len(dogs))

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
                "Creating text entities for dog %s (%s) with modules: %s",
                dog_name,
                dog_id,
                list(dog_modules.keys())
            )

            # Core text entities (always available)
            entities.extend(_create_core_text_entities(hass, coordinator, entry, dog_id, store, dog_stored))

            # Health module text entities
            if dog_modules.get(MODULE_HEALTH, True):
                entities.extend(_create_health_text_entities(hass, coordinator, entry, dog_id, store, dog_stored))

            # Training module text entities
            if dog_modules.get(MODULE_TRAINING, False):
                entities.extend(_create_training_text_entities(hass, coordinator, entry, dog_id, store, dog_stored))

            # Grooming module text entities
            if dog_modules.get(MODULE_GROOMING, False):
                entities.extend(_create_grooming_text_entities(hass, coordinator, entry, dog_id, store, dog_stored))

        # System-wide text entities
        entities.extend(_create_system_text_entities(hass, coordinator, entry, store))

        _LOGGER.info("Created %d text entities", len(entities))
        
        if entities:
            async_add_entities(entities, update_before_add=True)

    except Exception as err:
        _LOGGER.error("Failed to setup text entities: %s", err)
        raise


async def _load_stored_values(store: Store) -> dict[str, dict[str, str]]:
    """Load stored values from persistent storage.
    
    Args:
        store: Storage instance
        
    Returns:
        Dictionary of stored values organized by dog_id and entity_key
    """
    try:
        stored_values = await store.async_load()
        if stored_values is None:
            _LOGGER.debug("No stored values found, using defaults")
            return {}
        
        # Validate stored values structure
        if not isinstance(stored_values, dict):
            _LOGGER.warning("Invalid stored values structure, resetting")
            return {}
            
        _LOGGER.debug("Loaded stored values for %d dogs", len(stored_values))
        return stored_values
        
    except Exception as err:
        _LOGGER.error("Failed to load stored values: %s", err)
        return {}


def _create_core_text_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlTextEntity]:
    """Create core text entities available for all dogs.
    
    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of core text entities
    """
    return [
        GeneralNotesText(hass, coordinator, entry, dog_id, store, dog_stored),
        EmergencyContactText(hass, coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_health_text_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlTextEntity]:
    """Create health-related text entities.
    
    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of health text entities
    """
    return [
        HealthNotesText(hass, coordinator, entry, dog_id, store, dog_stored),
        MedicationNotesText(hass, coordinator, entry, dog_id, store, dog_stored),
        VetNotesText(hass, coordinator, entry, dog_id, store, dog_stored),
        VeterinarianContactText(hass, coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_training_text_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlTextEntity]:
    """Create training-related text entities.
    
    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of training text entities
    """
    return [
        TrainingNotesText(hass, coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_grooming_text_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    dog_id: str,
    store: Store,
    dog_stored: dict[str, str],
) -> list[PawControlTextEntity]:
    """Create grooming-related text entities.
    
    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        store: Storage instance
        dog_stored: Stored values for this dog
        
    Returns:
        List of grooming text entities
    """
    return [
        GroomingNotesText(hass, coordinator, entry, dog_id, store, dog_stored),
    ]


def _create_system_text_entities(
    hass: HomeAssistant,
    coordinator: PawControlCoordinator,
    entry: ConfigEntry,
    store: Store,
) -> list[TextEntity]:
    """Create system-wide text entities.
    
    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entry: Config entry
        store: Storage instance
        
    Returns:
        List of system text entities
    """
    return [
        ExportPathText(hass, coordinator, entry, store),
    ]

# ==============================================================================
# BASE TEXT ENTITY WITH STORAGE
# ==============================================================================

class PawControlTextWithStorage(PawControlTextEntity, TextEntity):
    """Base class for text entities with persistent storage.
    
    Provides common functionality for text entities that need to persist
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
        default_value: str = "",
    ) -> None:
        """Initialize the text entity with storage.
        
        Args:
            hass: Home Assistant instance
            coordinator: Data coordinator
            entry: Config entry
            dog_id: Dog identifier
            store: Storage instance
            stored_values: Pre-loaded stored values for this dog
            entity_key: Unique key for this entity
            translation_key: Translation key for localization
            field_config: Field configuration from TEXT_FIELD_CONFIGS
            default_value: Default value if not stored
        """
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key=entity_key,
            translation_key=translation_key,
            entity_category=field_config.get("category", EntityCategory.DIAGNOSTIC),
            icon=field_config.get("icon"),
            min_length=0,
            max_length=field_config.get("max_length", MAX_STRING_LENGTH),
            mode=field_config.get("mode", TextMode.TEXT),
        )
        
        self.hass = hass
        self._store = store
        self._stored_values = stored_values
        self._default_value = default_value
        
        # Load current value from storage or use default
        self._current_value = stored_values.get(entity_key, default_value)

    @property
    def native_value(self) -> str | None:
        """Return the current text value."""
        return self._current_value

    async def async_set_value(self, value: str) -> None:
        """Update the text value and persist it to storage.
        
        Args:
            value: New text value to set
        """
        try:
            # Validate the new value
            validated_value = self._validate_value(value)
            
            if validated_value != value:
                _LOGGER.debug(
                    "Value for %s truncated from %d to %d characters",
                    self.entity_id,
                    len(value),
                    len(validated_value),
                )
            
            self._current_value = validated_value

            # Update storage
            await self._save_value_to_storage(validated_value)
            
            # Apply value to coordinator if applicable
            await self._apply_value_to_coordinator(validated_value)

            _LOGGER.debug(
                "Set %s for %s to: %s",
                self.entity_key,
                self.dog_name,
                validated_value[:50] + "..." if len(validated_value) > 50 else validated_value,
            )
            
            # Update entity state
            self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error(
                "Failed to set value for %s: %s",
                self.entity_id,
                err,
            )

    def _validate_value(self, value: str) -> str:
        """Validate and sanitize text value.
        
        Args:
            value: Value to validate
            
        Returns:
            Validated and sanitized value
        """
        try:
            if not isinstance(value, str):
                value = str(value)
            
            # Trim whitespace
            value = value.strip()
            
            # Enforce max length
            if self._attr_native_max and len(value) > self._attr_native_max:
                value = value[:self._attr_native_max]
            
            return value
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Invalid value for %s, using default",
                self.entity_id,
            )
            return self._default_value

    async def _save_value_to_storage(self, value: str) -> None:
        """Save value to persistent storage.
        
        Args:
            value: Value to save
        """
        try:
            # Load current storage data
            all_stored = await self._store.async_load() or {}

            # Update value for this dog and entity
            if self.dog_id not in all_stored:
                all_stored[self.dog_id] = {}
            all_stored[self.dog_id][self.entity_key] = value

            # Save to storage
            await self._store.async_save(all_stored)
            
        except Exception as err:
            _LOGGER.error("Failed to save value to storage: %s", err)

    async def _apply_value_to_coordinator(self, value: str) -> None:
        """Apply value to coordinator data if applicable.
        
        This method can be overridden by subclasses to immediately
        apply the new value to coordinator data for instant effects.
        
        Args:
            value: Value to apply
        """
        # Default implementation does nothing
        # Subclasses can override to update coordinator data
        pass

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        try:
            attributes = super().extra_state_attributes or {}
            attributes.update({
                "character_count": len(self._current_value) if self._current_value else 0,
                "max_length": self._attr_native_max,
                "last_updated": dt_util.utcnow().isoformat(),
                "is_default": self._current_value == self._default_value,
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting extra attributes for %s: %s", self.entity_id, err)
            return super().extra_state_attributes

# ==============================================================================
# CORE TEXT ENTITIES
# ==============================================================================

class GeneralNotesText(PawControlTextWithStorage):
    """Text entity for general notes about the dog.
    
    Allows users to store miscellaneous observations, reminders,
    or notes that don't fit into specific categories.
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
        """Initialize the general notes text entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="general_notes",
            translation_key="general_notes",
            field_config=TEXT_FIELD_CONFIGS["general_notes"],
            default_value="",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional note information."""
        try:
            attributes = super().extra_state_attributes or {}
            attributes.update({
                "note_type": "general",
                "can_be_shared": True,
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting general notes attributes: %s", err)
            return super().extra_state_attributes


class EmergencyContactText(PawControlTextWithStorage):
    """Text entity for emergency contact information."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the emergency contact text entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="emergency_contact",
            translation_key="emergency_contact",
            field_config=TEXT_FIELD_CONFIGS["emergency_contact"],
            default_value="",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return emergency contact information."""
        try:
            attributes = super().extra_state_attributes or {}
            attributes.update({
                "contact_type": "emergency",
                "importance": "critical",
                "usage": "Emergency situations when owner unavailable",
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting emergency contact attributes: %s", err)
            return super().extra_state_attributes

# ==============================================================================
# HEALTH TEXT ENTITIES
# ==============================================================================

class HealthNotesText(PawControlTextWithStorage):
    """Text entity for health-related notes and observations.
    
    Stores health observations, symptoms, behavioral changes,
    and other health-related information.
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
        """Initialize the health notes text entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="health_notes",
            translation_key="health_notes",
            field_config=TEXT_FIELD_CONFIGS["health_notes"],
            default_value="",
        )

    async def _apply_value_to_coordinator(self, value: str) -> None:
        """Apply health note to coordinator data."""
        try:
            if value.strip():
                # Add note to health history
                await self.hass.services.async_call(
                    DOMAIN,
                    SERVICE_LOG_HEALTH,
                    {
                        "dog_id": self.dog_id,
                        "note": value,
                    },
                    blocking=False,
                )
        except Exception as err:
            _LOGGER.debug("Failed to apply health note to coordinator: %s", err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return health note information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})
            
            attributes.update({
                "note_type": "health",
                "last_vet_visit": health_data.get("last_vet_visit"),
                "current_weight": health_data.get("weight_kg"),
                "health_history_count": len(health_data.get("health_notes", [])),
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting health notes attributes: %s", err)
            return super().extra_state_attributes


class MedicationNotesText(PawControlTextWithStorage):
    """Text entity for medication-related notes."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the medication notes text entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="medication_notes",
            translation_key="medication_notes",
            field_config=TEXT_FIELD_CONFIGS["medication_notes"],
            default_value="",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return medication information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})
            
            attributes.update({
                "note_type": "medication",
                "current_medication": health_data.get("medication_name"),
                "current_dose": health_data.get("medication_dose"),
                "medications_today": health_data.get("medications_today", 0),
                "last_medication": health_data.get("last_medication"),
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting medication notes attributes: %s", err)
            return super().extra_state_attributes


class VetNotesText(PawControlTextWithStorage):
    """Text entity for veterinarian visit notes."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the vet notes text entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="vet_notes",
            translation_key="vet_notes",
            field_config=TEXT_FIELD_CONFIGS["vet_notes"],
            default_value="",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return veterinarian visit information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})
            
            attributes.update({
                "note_type": "veterinary",
                "last_vet_visit": health_data.get("last_vet_visit"),
                "vaccination_status": len(health_data.get("vaccine_status", {})),
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting vet notes attributes: %s", err)
            return super().extra_state_attributes


class VeterinarianContactText(PawControlTextWithStorage):
    """Text entity for veterinarian contact information."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the veterinarian contact text entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="veterinarian_contact",
            translation_key="veterinarian_contact",
            field_config=TEXT_FIELD_CONFIGS["veterinarian_contact"],
            default_value="",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return veterinarian contact information."""
        try:
            attributes = super().extra_state_attributes or {}
            attributes.update({
                "contact_type": "veterinarian",
                "importance": "high",
                "usage": "Regular check-ups and health concerns",
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting veterinarian contact attributes: %s", err)
            return super().extra_state_attributes

# ==============================================================================
# TRAINING TEXT ENTITIES
# ==============================================================================

class TrainingNotesText(PawControlTextWithStorage):
    """Text entity for training session notes and progress.
    
    Stores training observations, progress notes, behavioral changes,
    and training session summaries.
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
        """Initialize the training notes text entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="training_notes",
            translation_key="training_notes",
            field_config=TEXT_FIELD_CONFIGS["training_notes"],
            default_value="",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return training information."""
        try:
            attributes = super().extra_state_attributes or {}
            training_data = self.dog_data.get("training", {})
            
            attributes.update({
                "note_type": "training",
                "last_training": training_data.get("last_training"),
                "sessions_today": training_data.get("training_sessions_today", 0),
                "last_topic": training_data.get("last_topic"),
                "training_history_count": len(training_data.get("training_history", [])),
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting training notes attributes: %s", err)
            return super().extra_state_attributes

# ==============================================================================
# GROOMING TEXT ENTITIES
# ==============================================================================

class GroomingNotesText(PawControlTextWithStorage):
    """Text entity for grooming session notes and observations."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        store: Store,
        stored_values: dict[str, str],
    ) -> None:
        """Initialize the grooming notes text entity."""
        super().__init__(
            hass=hass,
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            store=store,
            stored_values=stored_values,
            entity_key="grooming_notes",
            translation_key="grooming_notes",
            field_config=TEXT_FIELD_CONFIGS["grooming_notes"],
            default_value="",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return grooming information."""
        try:
            attributes = super().extra_state_attributes or {}
            grooming_data = self.dog_data.get("grooming", {})
            
            attributes.update({
                "note_type": "grooming",
                "last_grooming": grooming_data.get("last_grooming"),
                "grooming_type": grooming_data.get("grooming_type"),
                "needs_grooming": grooming_data.get("needs_grooming", False),
                "grooming_history_count": len(grooming_data.get("grooming_history", [])),
            })
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting grooming notes attributes: %s", err)
            return super().extra_state_attributes

# ==============================================================================
# SYSTEM TEXT ENTITIES
# ==============================================================================

class ExportPathText(TextEntity):
    """Text entity for configuring data export path.
    
    System-wide setting that determines where exported data files
    and reports are saved.
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
        """Initialize the export path text entity."""
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._store = store
        self._attr_unique_id = f"{entry.entry_id}_global_export_path"
        self._attr_translation_key = "export_path"
        
        # Configure text field properties
        field_config = TEXT_FIELD_CONFIGS["export_path"]
        self._attr_icon = field_config["icon"]
        self._attr_mode = field_config["mode"]
        self._attr_native_max = field_config["max_length"]
        
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
        """Return the name of the entity."""
        return "Export Path"

    @property
    def native_value(self) -> str | None:
        """Return the current export path."""
        return self.entry.options.get("export_path", "")

    async def async_set_value(self, value: str) -> None:
        """Update the export path.
        
        Args:
            value: New export path to set
        """
        try:
            # Validate and sanitize the path
            validated_path = self._validate_path(value)
            
            _LOGGER.info("Export path set to: %s", validated_path)
            
            # In a production environment, this would update the config entry
            # For now, we just log the change and update state
            self.async_write_ha_state()
            
        except Exception as err:
            _LOGGER.error("Failed to set export path: %s", err)

    def _validate_path(self, path: str) -> str:
        """Validate and sanitize the export path.
        
        Args:
            path: Path to validate
            
        Returns:
            Validated path
        """
        try:
            if not isinstance(path, str):
                path = str(path)
            
            # Trim whitespace
            path = path.strip()
            
            # Basic path validation
            if path and not path.startswith(("/", "C:", "D:", "E:", "F:")):
                _LOGGER.warning("Invalid path format: %s", path)
            
            return path
        except Exception:
            return ""

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return export path configuration."""
        try:
            current_path = self.native_value
            return {
                "configured": bool(current_path),
                "export_format": self.entry.options.get("export_format", "csv"),
                "auto_export": self.entry.options.get("daily_report", False),
                "path_length": len(current_path) if current_path else 0,
            }
        except Exception as err:
            _LOGGER.debug("Error getting export path attributes: %s", err)
            return {}
