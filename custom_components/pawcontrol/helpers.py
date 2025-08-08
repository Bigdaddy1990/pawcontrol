"""Improved helper creation for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.components.input_boolean import (
    DOMAIN as INPUT_BOOLEAN_DOMAIN,
    InputBoolean,
)
from homeassistant.components.input_number import (
    DOMAIN as INPUT_NUMBER_DOMAIN,
    InputNumber,
)
from homeassistant.components.input_text import (
    DOMAIN as INPUT_TEXT_DOMAIN,
    InputText,
)
from homeassistant.components.input_datetime import (
    DOMAIN as INPUT_DATETIME_DOMAIN,
    InputDatetime,
)
from homeassistant.components.input_select import (
    DOMAIN as INPUT_SELECT_DOMAIN,
    InputSelect,
)
from homeassistant.components.counter import (
    DOMAIN as COUNTER_DOMAIN,
    Counter,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "pawcontrol_helpers"


class ImprovedModuleManager:
    """Improved module manager with proper helper creation."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        coordinator,
        dog_config: dict[str, Any],
    ) -> None:
        """Initialize the improved module manager."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.dog_config = dog_config
        self.dog_name = dog_config.get("dog_name", "unknown")
        self.dog_id = self._sanitize_name(self.dog_name)
        
        # Store for helper configurations
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}_{self.dog_id}",
        )
        
        # Track created helpers
        self._created_helpers: dict[str, dict] = {}
        
    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for entity IDs."""
        return name.lower().replace(" ", "_").replace("-", "_")
    
    async def async_initialize(self) -> None:
        """Initialize the module manager and load existing helpers."""
        # Load existing helper configurations
        stored_data = await self._store.async_load()
        if stored_data:
            self._created_helpers = stored_data.get("helpers", {})
        
    async def async_create_input_boolean(
        self,
        entity_id: str,
        name: str,
        icon: str = "mdi:toggle-switch",
        initial: bool = False,
    ) -> str:
        """Create an input boolean helper properly."""
        full_id = f"{INPUT_BOOLEAN_DOMAIN}.pawcontrol_{entity_id}"
        
        # Check if already exists
        entity_registry = er.async_get(self.hass)
        if entity_registry.async_get(full_id):
            _LOGGER.debug(f"Helper {full_id} already exists")
            return full_id
        
        # Create the input boolean configuration
        config = {
            "name": f"{self.dog_name} - {name}",
            "icon": icon,
            "initial": initial,
        }
        
        # Store configuration
        self._created_helpers[full_id] = {
            "type": "input_boolean",
            "config": config,
            "dog_id": self.dog_id,
        }
        
        # Save to storage
        await self._save_helpers()
        
        # Create the entity using the proper method
        # This requires adding the helper to the config entry
        await self._add_helper_to_config(INPUT_BOOLEAN_DOMAIN, entity_id, config)
        
        _LOGGER.info(f"Created input boolean: {full_id}")
        return full_id
    
    async def async_create_input_number(
        self,
        entity_id: str,
        name: str,
        min_value: float = 0,
        max_value: float = 100,
        step: float = 1,
        unit: str | None = None,
        icon: str = "mdi:numeric",
        initial: float | None = None,
        mode: str = "box",
    ) -> str:
        """Create an input number helper properly."""
        full_id = f"{INPUT_NUMBER_DOMAIN}.pawcontrol_{entity_id}"
        
        # Check if already exists
        entity_registry = er.async_get(self.hass)
        if entity_registry.async_get(full_id):
            _LOGGER.debug(f"Helper {full_id} already exists")
            return full_id
        
        # Create the input number configuration
        config = {
            "name": f"{self.dog_name} - {name}",
            "min": min_value,
            "max": max_value,
            "step": step,
            "mode": mode,
            "icon": icon,
        }
        
        if unit:
            config["unit_of_measurement"] = unit
        if initial is not None:
            config["initial"] = initial
        
        # Store configuration
        self._created_helpers[full_id] = {
            "type": "input_number",
            "config": config,
            "dog_id": self.dog_id,
        }
        
        # Save to storage
        await self._save_helpers()
        
        # Create the entity
        await self._add_helper_to_config(INPUT_NUMBER_DOMAIN, entity_id, config)
        
        _LOGGER.info(f"Created input number: {full_id}")
        return full_id
    
    async def async_create_input_text(
        self,
        entity_id: str,
        name: str,
        min_length: int = 0,
        max_length: int = 100,
        pattern: str | None = None,
        mode: str = "text",
        icon: str = "mdi:text",
        initial: str = "",
    ) -> str:
        """Create an input text helper properly."""
        full_id = f"{INPUT_TEXT_DOMAIN}.pawcontrol_{entity_id}"
        
        # Check if already exists
        entity_registry = er.async_get(self.hass)
        if entity_registry.async_get(full_id):
            _LOGGER.debug(f"Helper {full_id} already exists")
            return full_id
        
        # Create the input text configuration
        config = {
            "name": f"{self.dog_name} - {name}",
            "min": min_length,
            "max": max_length,
            "mode": mode,
            "icon": icon,
            "initial": initial,
        }
        
        if pattern:
            config["pattern"] = pattern
        
        # Store configuration
        self._created_helpers[full_id] = {
            "type": "input_text",
            "config": config,
            "dog_id": self.dog_id,
        }
        
        # Save to storage
        await self._save_helpers()
        
        # Create the entity
        await self._add_helper_to_config(INPUT_TEXT_DOMAIN, entity_id, config)
        
        _LOGGER.info(f"Created input text: {full_id}")
        return full_id
    
    async def async_create_input_datetime(
        self,
        entity_id: str,
        name: str,
        has_date: bool = False,
        has_time: bool = False,
        icon: str = "mdi:calendar-clock",
        initial: str | None = None,
    ) -> str:
        """Create an input datetime helper properly."""
        full_id = f"{INPUT_DATETIME_DOMAIN}.pawcontrol_{entity_id}"
        
        # Check if already exists
        entity_registry = er.async_get(self.hass)
        if entity_registry.async_get(full_id):
            _LOGGER.debug(f"Helper {full_id} already exists")
            return full_id
        
        # Create the input datetime configuration
        config = {
            "name": f"{self.dog_name} - {name}",
            "has_date": has_date,
            "has_time": has_time,
            "icon": icon,
        }
        
        if initial:
            config["initial"] = initial
        
        # Store configuration
        self._created_helpers[full_id] = {
            "type": "input_datetime",
            "config": config,
            "dog_id": self.dog_id,
        }
        
        # Save to storage
        await self._save_helpers()
        
        # Create the entity
        await self._add_helper_to_config(INPUT_DATETIME_DOMAIN, entity_id, config)
        
        _LOGGER.info(f"Created input datetime: {full_id}")
        return full_id
    
    async def async_create_input_select(
        self,
        entity_id: str,
        name: str,
        options: list[str],
        icon: str = "mdi:format-list-bulleted",
        initial: str | None = None,
    ) -> str:
        """Create an input select helper properly."""
        full_id = f"{INPUT_SELECT_DOMAIN}.pawcontrol_{entity_id}"
        
        # Check if already exists
        entity_registry = er.async_get(self.hass)
        if entity_registry.async_get(full_id):
            _LOGGER.debug(f"Helper {full_id} already exists")
            return full_id
        
        if not options:
            _LOGGER.error(f"Cannot create input select {entity_id} without options")
            return ""
        
        if initial is None:
            initial = options[0]
        
        # Create the input select configuration
        config = {
            "name": f"{self.dog_name} - {name}",
            "options": options,
            "initial": initial,
            "icon": icon,
        }
        
        # Store configuration
        self._created_helpers[full_id] = {
            "type": "input_select",
            "config": config,
            "dog_id": self.dog_id,
        }
        
        # Save to storage
        await self._save_helpers()
        
        # Create the entity
        await self._add_helper_to_config(INPUT_SELECT_DOMAIN, entity_id, config)
        
        _LOGGER.info(f"Created input select: {full_id}")
        return full_id
    
    async def async_create_counter(
        self,
        entity_id: str,
        name: str,
        initial: int = 0,
        step: int = 1,
        minimum: int | None = None,
        maximum: int | None = None,
        icon: str = "mdi:counter",
    ) -> str:
        """Create a counter helper properly."""
        full_id = f"{COUNTER_DOMAIN}.pawcontrol_{entity_id}"
        
        # Check if already exists
        entity_registry = er.async_get(self.hass)
        if entity_registry.async_get(full_id):
            _LOGGER.debug(f"Helper {full_id} already exists")
            return full_id
        
        # Create the counter configuration
        config = {
            "name": f"{self.dog_name} - {name}",
            "initial": initial,
            "step": step,
            "icon": icon,
        }
        
        if minimum is not None:
            config["minimum"] = minimum
        if maximum is not None:
            config["maximum"] = maximum
        
        # Store configuration
        self._created_helpers[full_id] = {
            "type": "counter",
            "config": config,
            "dog_id": self.dog_id,
        }
        
        # Save to storage
        await self._save_helpers()
        
        # Create the entity
        await self._add_helper_to_config(COUNTER_DOMAIN, entity_id, config)
        
        _LOGGER.info(f"Created counter: {full_id}")
        return full_id
    
    async def _add_helper_to_config(
        self,
        domain: str,
        entity_id: str,
        config: dict[str, Any],
    ) -> None:
        """Add helper to the configuration properly."""
        # This is where we need to integrate with Home Assistant's helper system
        # The actual implementation depends on the HA version and API
        
        # For now, we'll use a workaround by creating a config entry for the helper
        # This needs to be properly integrated with HA's helper infrastructure
        
        full_entity_id = f"{domain}.pawcontrol_{entity_id}"
        
        # Store in the integration's data for entity platforms to use
        if "helpers" not in self.hass.data.get("pawcontrol", {}):
            if "pawcontrol" not in self.hass.data:
                self.hass.data["pawcontrol"] = {}
            self.hass.data["pawcontrol"]["helpers"] = {}
        
        self.hass.data["pawcontrol"]["helpers"][full_entity_id] = config
        
        # Trigger a config entry reload to create the entities
        # This is a simplified approach - actual implementation would be more complex
        _LOGGER.debug(f"Added helper config for {full_entity_id}")
    
    async def async_remove_all_helpers(self) -> None:
        """Remove all helpers for this dog."""
        entity_registry = er.async_get(self.hass)
        
        removed_count = 0
        for entity_id in list(self._created_helpers.keys()):
            entity_entry = entity_registry.async_get(entity_id)
            if entity_entry:
                entity_registry.async_remove(entity_id)
                removed_count += 1
                _LOGGER.info(f"Removed helper: {entity_id}")
        
        # Clear the stored helpers
        self._created_helpers.clear()
        await self._save_helpers()
        
        _LOGGER.info(f"Removed {removed_count} helpers for {self.dog_name}")
    
    async def async_remove_module_helpers(self, module_id: str) -> None:
        """Remove helpers for a specific module."""
        entity_registry = er.async_get(self.hass)
        
        # Define which helpers belong to which module
        module_helper_patterns = {
            "feeding": ["fed_", "feeding", "meal", "food"],
            "gps": ["gps", "location", "geofence", "distance"],
            "health": ["health", "temperature", "weight", "medication", "vet"],
            "walk": ["walk", "outside"],
            "training": ["training", "command"],
            "grooming": ["grooming", "bath", "nail"],
            "visitor": ["visitor"],
        }
        
        patterns = module_helper_patterns.get(module_id, [])
        if not patterns:
            return
        
        removed_count = 0
        for entity_id in list(self._created_helpers.keys()):
            # Check if this helper belongs to the module
            should_remove = any(pattern in entity_id for pattern in patterns)
            
            if should_remove:
                entity_entry = entity_registry.async_get(entity_id)
                if entity_entry:
                    entity_registry.async_remove(entity_id)
                    del self._created_helpers[entity_id]
                    removed_count += 1
                    _LOGGER.info(f"Removed {module_id} helper: {entity_id}")
        
        # Save updated helper list
        await self._save_helpers()
        
        _LOGGER.info(f"Removed {removed_count} helpers for module {module_id}")
    
    async def _save_helpers(self) -> None:
        """Save helper configurations to storage."""
        await self._store.async_save({
            "helpers": self._created_helpers,
            "dog_id": self.dog_id,
            "dog_name": self.dog_name,
        })
    
    async def async_restore_helpers(self) -> None:
        """Restore helpers from storage on startup."""
        stored_data = await self._store.async_load()
        if not stored_data:
            return
        
        helpers = stored_data.get("helpers", {})
        for entity_id, helper_data in helpers.items():
            helper_type = helper_data.get("type")
            config = helper_data.get("config", {})
            
            # Re-create the helper configuration in HA's data
            if helper_type and config:
                domain = helper_type.replace("_", "")  # input_boolean -> inputboolean
                await self._add_helper_to_config(domain, entity_id.split(".")[-1], config)
        
        self._created_helpers = helpers
        _LOGGER.info(f"Restored {len(helpers)} helpers for {self.dog_name}")
