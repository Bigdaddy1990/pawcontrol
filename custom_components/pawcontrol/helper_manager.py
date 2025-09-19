"""Helper creation and management for PawControl integration.

Automatically creates Home Assistant helpers (input_boolean, input_datetime, etc.)
for feeding schedules, health tracking, and other dog management tasks.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)

# Helper creation templates
HELPER_TEMPLATES = {
    "feeding": {
        "breakfast_toggle": {
            "domain": "input_boolean",
            "name": "{dog_name} Breakfast Fed",
            "icon": "mdi:food-croissant",
        },
        "lunch_toggle": {
            "domain": "input_boolean", 
            "name": "{dog_name} Lunch Fed",
            "icon": "mdi:food-apple",
        },
        "dinner_toggle": {
            "domain": "input_boolean",
            "name": "{dog_name} Dinner Fed", 
            "icon": "mdi:food-turkey",
        },
        "snack_toggle": {
            "domain": "input_boolean",
            "name": "{dog_name} Snack Given",
            "icon": "mdi:food-variant",
        },
        "breakfast_time": {
            "domain": "input_datetime",
            "name": "{dog_name} Breakfast Time",
            "has_date": False,
            "has_time": True,
            "icon": "mdi:clock-time-four",
        },
        "lunch_time": {
            "domain": "input_datetime",
            "name": "{dog_name} Lunch Time",
            "has_date": False,
            "has_time": True,
            "icon": "mdi:clock-time-twelve",
        },
        "dinner_time": {
            "domain": "input_datetime",
            "name": "{dog_name} Dinner Time",
            "has_date": False,
            "has_time": True,
            "icon": "mdi:clock-time-eight",
        },
        "feeding_reminder": {
            "domain": "input_datetime",
            "name": "{dog_name} Next Feeding Reminder",
            "has_date": True,
            "has_time": True,
            "icon": "mdi:bell-alert",
        },
    },
    "health": {
        "weight_check_reminder": {
            "domain": "input_datetime",
            "name": "{dog_name} Weight Check Reminder",
            "has_date": True,
            "has_time": False,
            "icon": "mdi:scale",
        },
        "vet_appointment_reminder": {
            "domain": "input_datetime",
            "name": "{dog_name} Vet Appointment",
            "has_date": True,
            "has_time": True,
            "icon": "mdi:medical-bag",
        },
        "medication_reminder": {
            "domain": "input_datetime",
            "name": "{dog_name} Medication Time",
            "has_date": False,
            "has_time": True,
            "icon": "mdi:pill",
        },
        "grooming_due": {
            "domain": "input_boolean",
            "name": "{dog_name} Grooming Due",
            "icon": "mdi:content-cut",
        },
    },
    "visitor": {
        "visitor_mode": {
            "domain": "input_boolean",
            "name": "{dog_name} Visitor Mode",
            "icon": "mdi:account-group",
        },
        "visitor_arrival": {
            "domain": "input_datetime",
            "name": "{dog_name} Visitor Arrival",
            "has_date": True,
            "has_time": True,
            "icon": "mdi:account-plus",
        },
    },
    "walk": {
        "walk_reminder": {
            "domain": "input_datetime",
            "name": "{dog_name} Walk Reminder",
            "has_date": False,
            "has_time": True,
            "icon": "mdi:dog-side",
        },
        "needs_walk": {
            "domain": "input_boolean",
            "name": "{dog_name} Needs Walk",
            "icon": "mdi:walk",
        },
    },
    "gps": {
        "gps_tracking": {
            "domain": "input_boolean",
            "name": "{dog_name} GPS Tracking Enabled",
            "icon": "mdi:map-marker-path",
        },
    },
}

# Default values for helpers
DEFAULT_VALUES = {
    "feeding": {
        "breakfast_time": "07:00:00",
        "lunch_time": "13:00:00", 
        "dinner_time": "18:00:00",
    }
}


class PawControlHelperManager:
    """Manager for automatic Home Assistant helper creation and management."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize helper manager.
        
        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id
        
        # Storage for tracking created helpers
        self._store = Store(
            hass, 
            STORAGE_VERSION, 
            f"{DOMAIN}_{entry_id}_helpers"
        )
        
        # Track created helpers
        self._created_helpers: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Initialize helper manager and load existing helper data."""
        async with self._lock:
            try:
                stored_data = await self._store.async_load() or {}
                self._created_helpers = stored_data.get("helpers", {})
                
                _LOGGER.debug(
                    "Helper manager initialized with %d existing helpers",
                    len(self._created_helpers)
                )
                
            except Exception as err:
                _LOGGER.error("Failed to initialize helper manager: %s", err)
                self._created_helpers = {}

    async def async_create_helpers_for_dogs(
        self,
        dogs: list[DogConfigData],
        enabled_modules: frozenset[str],
    ) -> dict[str, list[str]]:
        """Create helpers for all configured dogs based on enabled modules.
        
        Args:
            dogs: List of dog configurations
            enabled_modules: Set of enabled module names
            
        Returns:
            Dictionary mapping dog_id to list of created helper entity_ids
        """
        async with self._lock:
            created_helpers = {}
            
            for dog in dogs:
                dog_id = dog["dog_id"]
                dog_name = dog["dog_name"]
                dog_modules = dog.get("modules", {})
                
                # Create helpers for each enabled module
                dog_helpers = []
                
                for module_name in enabled_modules:
                    # Check if module is enabled for this dog
                    if not dog_modules.get(module_name, False):
                        continue
                    
                    # Create helpers for this module
                    module_helpers = await self._create_helpers_for_module(
                        dog_id, dog_name, module_name
                    )
                    dog_helpers.extend(module_helpers)
                
                if dog_helpers:
                    created_helpers[dog_id] = dog_helpers
                    _LOGGER.info(
                        "Created %d helpers for %s (%s)",
                        len(dog_helpers),
                        dog_name,
                        dog_id,
                    )
            
            # Save helper tracking data
            await self._save_helper_data()
            
            return created_helpers

    async def _create_helpers_for_module(
        self,
        dog_id: str,
        dog_name: str,
        module_name: str,
    ) -> list[str]:
        """Create helpers for a specific module.
        
        Args:
            dog_id: Dog identifier
            dog_name: Dog name for display
            module_name: Module name
            
        Returns:
            List of created helper entity IDs
        """
        if module_name not in HELPER_TEMPLATES:
            _LOGGER.debug("No helper templates for module: %s", module_name)
            return []
        
        module_templates = HELPER_TEMPLATES[module_name]
        created_helpers = []
        
        for helper_key, template in module_templates.items():
            try:
                entity_id = await self._create_single_helper(
                    dog_id, dog_name, module_name, helper_key, template
                )
                if entity_id:
                    created_helpers.append(entity_id)
                    
            except Exception as err:
                _LOGGER.error(
                    "Failed to create helper %s for %s: %s",
                    helper_key,
                    dog_name,
                    err,
                )
        
        return created_helpers

    async def _create_single_helper(
        self,
        dog_id: str,
        dog_name: str,
        module_name: str,
        helper_key: str,
        template: dict[str, Any],
    ) -> str | None:
        """Create a single helper entity.
        
        Args:
            dog_id: Dog identifier
            dog_name: Dog name for display
            module_name: Module name
            helper_key: Helper key within module
            template: Helper template configuration
            
        Returns:
            Created helper entity ID or None if creation failed
        """
        domain = template["domain"]
        entity_id = f"{domain}.pawcontrol_{dog_id}_{helper_key}"
        
        # Check if helper already exists
        if entity_id in self._created_helpers:
            _LOGGER.debug("Helper %s already exists", entity_id)
            return entity_id
        
        # Format helper name
        helper_name = template["name"].format(dog_name=dog_name)
        
        # Prepare helper configuration
        helper_config = {
            "name": helper_name,
            "icon": template.get("icon"),
        }
        
        # Add domain-specific configuration
        if domain == "input_datetime":
            helper_config.update({
                "has_date": template.get("has_date", False),
                "has_time": template.get("has_time", True),
            })
            
            # Set initial value if available
            if module_name in DEFAULT_VALUES and helper_key in DEFAULT_VALUES[module_name]:
                helper_config["initial"] = DEFAULT_VALUES[module_name][helper_key]
        
        elif domain == "input_boolean":
            helper_config["initial"] = template.get("initial", False)
            
        elif domain == "input_number":
            helper_config.update({
                "min": template.get("min", 0),
                "max": template.get("max", 100),
                "step": template.get("step", 1),
                "mode": template.get("mode", "box"),
                "unit_of_measurement": template.get("unit"),
                "initial": template.get("initial", 0),
            })
        
        # Create the helper
        try:
            await self.hass.services.async_call(
                domain,
                "create",
                {
                    "entity_id": entity_id,
                    **helper_config,
                },
                blocking=True,
            )
            
            # Track the created helper
            self._created_helpers[entity_id] = {
                "dog_id": dog_id,
                "dog_name": dog_name,
                "module_name": module_name,
                "helper_key": helper_key,
                "domain": domain,
                "config": helper_config,
                "created_at": self.hass.helpers.utc_now().isoformat(),
            }
            
            _LOGGER.debug("Created helper: %s (%s)", entity_id, helper_name)
            return entity_id
            
        except Exception as err:
            _LOGGER.error(
                "Failed to create helper %s: %s",
                entity_id,
                err,
            )
            return None

    async def async_remove_helpers_for_dog(self, dog_id: str) -> int:
        """Remove all helpers for a specific dog.
        
        Args:
            dog_id: Dog identifier
            
        Returns:
            Number of helpers removed
        """
        async with self._lock:
            removed_count = 0
            helpers_to_remove = [
                entity_id for entity_id, data in self._created_helpers.items()
                if data.get("dog_id") == dog_id
            ]
            
            for entity_id in helpers_to_remove:
                try:
                    helper_data = self._created_helpers[entity_id]
                    domain = helper_data["domain"]
                    
                    # Remove the helper
                    await self.hass.services.async_call(
                        domain,
                        "delete",
                        {"entity_id": entity_id},
                        blocking=True,
                    )
                    
                    # Remove from tracking
                    del self._created_helpers[entity_id]
                    removed_count += 1
                    
                    _LOGGER.debug("Removed helper: %s", entity_id)
                    
                except Exception as err:
                    _LOGGER.error(
                        "Failed to remove helper %s: %s",
                        entity_id,
                        err,
                    )
            
            if removed_count > 0:
                await self._save_helper_data()
            
            return removed_count

    async def async_update_helpers_for_dog(
        self,
        dog_id: str,
        new_dog_name: str,
        enabled_modules: frozenset[str],
    ) -> dict[str, int]:
        """Update helpers for a dog when configuration changes.
        
        Args:
            dog_id: Dog identifier
            new_dog_name: Updated dog name
            enabled_modules: Set of currently enabled modules
            
        Returns:
            Dictionary with counts of created/removed/updated helpers
        """
        async with self._lock:
            result = {"created": 0, "removed": 0, "updated": 0}
            
            # Get current helpers for this dog
            current_helpers = {
                entity_id: data for entity_id, data in self._created_helpers.items()
                if data.get("dog_id") == dog_id
            }
            
            # Determine which modules should have helpers
            current_modules = set()
            for data in current_helpers.values():
                current_modules.add(data["module_name"])
            
            required_modules = enabled_modules
            
            # Remove helpers for disabled modules
            modules_to_remove = current_modules - required_modules
            for module_name in modules_to_remove:
                module_helpers = [
                    entity_id for entity_id, data in current_helpers.items()
                    if data["module_name"] == module_name
                ]
                for entity_id in module_helpers:
                    try:
                        await self._remove_single_helper(entity_id)
                        result["removed"] += 1
                    except Exception as err:
                        _LOGGER.error("Failed to remove helper %s: %s", entity_id, err)
            
            # Create helpers for new modules
            modules_to_add = required_modules - current_modules
            for module_name in modules_to_add:
                try:
                    new_helpers = await self._create_helpers_for_module(
                        dog_id, new_dog_name, module_name
                    )
                    result["created"] += len(new_helpers)
                except Exception as err:
                    _LOGGER.error(
                        "Failed to create helpers for module %s: %s",
                        module_name,
                        err,
                    )
            
            # Update names for existing helpers if dog name changed
            old_dog_name = None
            if current_helpers:
                old_dog_name = next(iter(current_helpers.values())).get("dog_name")
            
            if old_dog_name and old_dog_name != new_dog_name:
                for entity_id, data in current_helpers.items():
                    try:
                        await self._update_helper_name(entity_id, data, new_dog_name)
                        result["updated"] += 1
                    except Exception as err:
                        _LOGGER.error("Failed to update helper name %s: %s", entity_id, err)
            
            # Save changes
            if sum(result.values()) > 0:
                await self._save_helper_data()
                
                _LOGGER.info(
                    "Helper update for %s complete: %d created, %d removed, %d updated",
                    new_dog_name,
                    result["created"],
                    result["removed"],
                    result["updated"],
                )
            
            return result

    async def _remove_single_helper(self, entity_id: str) -> None:
        """Remove a single helper.
        
        Args:
            entity_id: Helper entity ID to remove
        """
        if entity_id not in self._created_helpers:
            return
        
        helper_data = self._created_helpers[entity_id]
        domain = helper_data["domain"]
        
        await self.hass.services.async_call(
            domain,
            "delete",
            {"entity_id": entity_id},
            blocking=True,
        )
        
        del self._created_helpers[entity_id]
        _LOGGER.debug("Removed helper: %s", entity_id)

    async def _update_helper_name(
        self,
        entity_id: str,
        helper_data: dict[str, Any],
        new_dog_name: str,
    ) -> None:
        """Update a helper's name.
        
        Args:
            entity_id: Helper entity ID
            helper_data: Current helper data
            new_dog_name: New dog name
        """
        # Get the template to rebuild the name
        module_name = helper_data["module_name"]
        helper_key = helper_data["helper_key"]
        
        if module_name in HELPER_TEMPLATES and helper_key in HELPER_TEMPLATES[module_name]:
            template = HELPER_TEMPLATES[module_name][helper_key]
            new_name = template["name"].format(dog_name=new_dog_name)
            
            # Update the helper name
            domain = helper_data["domain"]
            await self.hass.services.async_call(
                domain,
                "update",
                {
                    "entity_id": entity_id,
                    "name": new_name,
                },
                blocking=True,
            )
            
            # Update tracking data
            helper_data["dog_name"] = new_dog_name
            helper_data["config"]["name"] = new_name
            
            _LOGGER.debug("Updated helper name: %s -> %s", entity_id, new_name)

    async def _save_helper_data(self) -> None:
        """Save helper tracking data to storage."""
        try:
            await self._store.async_save({
                "helpers": self._created_helpers,
                "last_updated": self.hass.helpers.utc_now().isoformat(),
            })
        except Exception as err:
            _LOGGER.error("Failed to save helper data: %s", err)

    async def async_cleanup(self) -> None:
        """Clean up all created helpers."""
        async with self._lock:
            cleanup_count = 0
            
            for entity_id in list(self._created_helpers.keys()):
                try:
                    await self._remove_single_helper(entity_id)
                    cleanup_count += 1
                except Exception as err:
                    _LOGGER.error("Failed to cleanup helper %s: %s", entity_id, err)
            
            if cleanup_count > 0:
                await self._save_helper_data()
                _LOGGER.info("Cleaned up %d helpers", cleanup_count)

    def get_helpers_for_dog(self, dog_id: str) -> list[dict[str, Any]]:
        """Get all helpers created for a specific dog.
        
        Args:
            dog_id: Dog identifier
            
        Returns:
            List of helper information
        """
        return [
            {"entity_id": entity_id, **data}
            for entity_id, data in self._created_helpers.items()
            if data.get("dog_id") == dog_id
        ]

    def get_helper_count(self) -> int:
        """Get total number of created helpers.
        
        Returns:
            Number of helpers created
        """
        return len(self._created_helpers)

    def get_helper_stats(self) -> dict[str, Any]:
        """Get statistics about created helpers.
        
        Returns:
            Helper statistics
        """
        stats = {
            "total_helpers": len(self._created_helpers),
            "by_module": {},
            "by_domain": {},
            "by_dog": {},
        }
        
        for data in self._created_helpers.values():
            module = data.get("module_name", "unknown")
            domain = data.get("domain", "unknown")
            dog_id = data.get("dog_id", "unknown")
            
            stats["by_module"][module] = stats["by_module"].get(module, 0) + 1
            stats["by_domain"][domain] = stats["by_domain"].get(domain, 0) + 1
            stats["by_dog"][dog_id] = stats["by_dog"].get(dog_id, 0) + 1
        
        return stats

    async def async_validate_helpers(self) -> dict[str, Any]:
        """Validate that all tracked helpers still exist in Home Assistant.
        
        Returns:
            Validation results with missing/invalid helpers
        """
        async with self._lock:
            missing_helpers = []
            invalid_helpers = []
            valid_helpers = []
            
            entity_registry = er.async_get(self.hass)
            
            for entity_id, data in self._created_helpers.items():
                try:
                    # Check if entity exists in registry
                    registry_entry = entity_registry.async_get(entity_id)
                    
                    if registry_entry is None:
                        # Check if entity exists in state machine
                        state = self.hass.states.get(entity_id)
                        if state is None:
                            missing_helpers.append({
                                "entity_id": entity_id,
                                "data": data,
                            })
                        else:
                            valid_helpers.append(entity_id)
                    else:
                        valid_helpers.append(entity_id)
                        
                except Exception as err:
                    invalid_helpers.append({
                        "entity_id": entity_id,
                        "error": str(err),
                        "data": data,
                    })
            
            return {
                "valid": len(valid_helpers),
                "missing": len(missing_helpers),
                "invalid": len(invalid_helpers),
                "missing_helpers": missing_helpers,
                "invalid_helpers": invalid_helpers,
                "total_tracked": len(self._created_helpers),
            }

    async def async_repair_missing_helpers(self) -> dict[str, int]:
        """Attempt to repair missing helpers by recreating them.
        
        Returns:
            Repair results with counts
        """
        validation = await self.async_validate_helpers()
        repaired = 0
        failed = 0
        
        for missing in validation["missing_helpers"]:
            entity_id = missing["entity_id"]
            data = missing["data"]
            
            try:
                # Remove from tracking
                self._created_helpers.pop(entity_id, None)
                
                # Recreate the helper
                new_entity_id = await self._create_single_helper(
                    data["dog_id"],
                    data["dog_name"],
                    data["module_name"],
                    data["helper_key"],
                    HELPER_TEMPLATES[data["module_name"]][data["helper_key"]],
                )
                
                if new_entity_id:
                    repaired += 1
                else:
                    failed += 1
                    
            except Exception as err:
                _LOGGER.error("Failed to repair helper %s: %s", entity_id, err)
                failed += 1
        
        if repaired > 0 or failed > 0:
            await self._save_helper_data()
        
        return {
            "repaired": repaired,
            "failed": failed,
            "total_missing": len(validation["missing_helpers"]),
        }
