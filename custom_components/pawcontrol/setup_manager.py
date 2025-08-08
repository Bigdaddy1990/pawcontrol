"""Setup manager for PawControl integration with complete lifecycle management."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.const import STATE_ON, STATE_OFF

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    CONF_DOG_BREED,
    CONF_DOG_AGE,
    CONF_DOG_WEIGHT,
    CONF_DOG_SIZE,
    CONF_DOGS,
    CONF_MODULES,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    MODULE_NOTIFICATIONS,
    MODULE_AUTOMATION,
    MODULE_DASHBOARD,
    MODULE_TRAINING,
    MODULE_GROOMING,
    MODULE_VISITOR,
)
from .dashboard_manager import DashboardManager

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = "pawcontrol_setup"


class PawControlSetupManager:
    """Complete setup manager for PawControl integration."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the setup manager."""
        self.hass = hass
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._setup_status: Dict[str, Any] = {}
        self._created_entities: Dict[str, List[str]] = {}
        self._dashboard_manager = DashboardManager(hass)
        
    async def async_setup_complete_system(self) -> bool:
        """
        Complete setup flow for all dogs and modules.
        
        This is the main entry point that orchestrates the entire setup process.
        """
        _LOGGER.info("Starting PawControl complete system setup")
        
        try:
            # Load existing setup status
            await self._load_setup_status()
            
            # Get dogs configuration
            dogs_config = self.entry.data.get(CONF_DOGS, [])
            
            if not dogs_config:
                _LOGGER.error("No dogs configured in entry data")
                return False
            
            # Process each dog sequentially
            for dog_config in dogs_config:
                dog_name = dog_config.get(CONF_DOG_NAME)
                if not dog_name:
                    _LOGGER.error("Dog configuration missing name")
                    continue
                
                _LOGGER.info(f"Setting up dog: {dog_name}")
                
                # Create device for this dog
                device_id = await self._create_dog_device(dog_name, dog_config)
                
                # Track created entities for this dog
                self._created_entities[dog_name] = []
                
                # Setup modules for this dog
                await self._setup_dog_modules(dog_name, dog_config, device_id)
                
                # Update setup status
                self._setup_status[dog_name] = {
                    "setup_complete": True,
                    "device_id": device_id,
                    "timestamp": datetime.now().isoformat(),
                    "modules": dog_config.get(CONF_MODULES, {}),
                    "entities": self._created_entities.get(dog_name, []),
                }
            
            # Save setup status
            await self._save_setup_status()
            
            # Create dashboards for dogs with dashboard module enabled
            for dog_config in dogs_config:
                dog_name = dog_config.get(CONF_DOG_NAME)
                modules = dog_config.get(CONF_MODULES, {})
                if modules.get(MODULE_DASHBOARD, {}).get("enabled", False):
                    _LOGGER.info(f"Creating dashboard for {dog_name}")
                    await self._dashboard_manager.async_create_dog_dashboard(
                        dog_name,
                        dog_config,
                        modules
                    )
            
            _LOGGER.info("PawControl complete system setup finished successfully")
            return True
            
        except Exception as err:
            _LOGGER.error(f"Failed to complete system setup: {err}", exc_info=True)
            # Cleanup on failure
            await self.async_cleanup_failed_setup()
            return False
    
    async def _create_dog_device(self, dog_name: str, config: dict) -> str:
        """Create a device for the dog."""
        device_registry = dr.async_get(self.hass)
        
        device = device_registry.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, f"dog_{dog_name.lower().replace(' ', '_')}")},
            name=f"PawControl - {dog_name}",
            manufacturer="PawControl",
            model=config.get(CONF_DOG_BREED, "Dog"),
            sw_version="1.0.0",
        )
        
        _LOGGER.info(f"Created device for {dog_name}: {device.id}")
        return device.id
    
    async def _setup_dog_modules(
        self,
        dog_name: str,
        dog_config: dict,
        device_id: str
    ) -> None:
        """Setup all enabled modules for a dog."""
        modules = dog_config.get(CONF_MODULES, {})
        
        # Define setup order (dependencies)
        setup_order = [
            MODULE_FEEDING,
            MODULE_HEALTH,
            MODULE_WALK,
            MODULE_GPS,
            MODULE_TRAINING,
            MODULE_GROOMING,
            MODULE_VISITOR,
            MODULE_NOTIFICATIONS,
            MODULE_AUTOMATION,
            MODULE_DASHBOARD,
        ]
        
        for module_id in setup_order:
            module_config = modules.get(module_id, {})
            if module_config.get("enabled", False):
                _LOGGER.info(f"Setting up module {module_id} for {dog_name}")
                
                try:
                    await self._setup_single_module(
                        dog_name,
                        module_id,
                        module_config,
                        device_id
                    )
                    
                    # Small delay between modules to avoid overwhelming the system
                    await asyncio.sleep(0.1)
                    
                except Exception as err:
                    _LOGGER.error(
                        f"Failed to setup module {module_id} for {dog_name}: {err}",
                        exc_info=True
                    )
                    # Continue with other modules even if one fails
    
    async def _setup_single_module(
        self,
        dog_name: str,
        module_id: str,
        module_config: dict,
        device_id: str
    ) -> None:
        """Setup a single module with all its components."""
        
        # Store helper data for entity platforms to use
        if "helper_configs" not in self.hass.data.get(DOMAIN, {}):
            if DOMAIN not in self.hass.data:
                self.hass.data[DOMAIN] = {}
            self.hass.data[DOMAIN]["helper_configs"] = {}
        
        dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        
        # Module-specific setup
        if module_id == MODULE_FEEDING:
            await self._setup_feeding_helpers(dog_name, dog_id, device_id)
        elif module_id == MODULE_GPS:
            await self._setup_gps_helpers(dog_name, dog_id, device_id)
        elif module_id == MODULE_HEALTH:
            await self._setup_health_helpers(dog_name, dog_id, device_id)
        elif module_id == MODULE_WALK:
            await self._setup_walk_helpers(dog_name, dog_id, device_id)
        elif module_id == MODULE_TRAINING:
            await self._setup_training_helpers(dog_name, dog_id, device_id)
        elif module_id == MODULE_GROOMING:
            await self._setup_grooming_helpers(dog_name, dog_id, device_id)
        elif module_id == MODULE_VISITOR:
            await self._setup_visitor_helpers(dog_name, dog_id, device_id)
        elif module_id == MODULE_NOTIFICATIONS:
            await self._setup_notification_helpers(dog_name, dog_id, device_id)
        elif module_id == MODULE_AUTOMATION:
            await self._setup_automation_helpers(dog_name, dog_id, device_id)
    
    async def _create_virtual_helper(
        self,
        domain: str,
        entity_id: str,
        name: str,
        config: dict,
        dog_name: str
    ) -> bool:
        """Create a virtual helper entity by setting its state."""
        try:
            full_entity_id = f"{domain}.pawcontrol_{entity_id}"
            
            # Determine initial state based on domain and config
            if domain == "input_boolean":
                initial_state = config.get("initial", STATE_OFF)
            elif domain == "input_number":
                initial_state = str(config.get("initial", config.get("min", 0)))
            elif domain == "input_text":
                initial_state = config.get("initial", "")
            elif domain == "input_datetime":
                initial_state = config.get("initial", "")
            elif domain == "input_select":
                options = config.get("options", [])
                initial_state = config.get("initial", options[0] if options else "")
            elif domain == "counter":
                initial_state = str(config.get("initial", 0))
            else:
                initial_state = ""
            
            # Set the state with attributes
            attributes = {
                "friendly_name": name,
                "icon": config.get("icon", self._get_default_icon(domain, entity_id)),
                "editable": True,
            }
            
            # Add domain-specific attributes
            if domain == "input_number":
                attributes.update({
                    "min": config.get("min", 0),
                    "max": config.get("max", 100),
                    "step": config.get("step", 1),
                    "mode": config.get("mode", "slider"),
                })
                if "unit_of_measurement" in config:
                    attributes["unit_of_measurement"] = config["unit_of_measurement"]
            elif domain == "input_text":
                attributes.update({
                    "min": config.get("min", 0),
                    "max": config.get("max", 100),
                    "mode": config.get("mode", "text"),
                })
            elif domain == "input_datetime":
                attributes.update({
                    "has_date": config.get("has_date", False),
                    "has_time": config.get("has_time", False),
                })
            elif domain == "input_select":
                attributes["options"] = config.get("options", [])
            elif domain == "counter":
                attributes.update({
                    "step": config.get("step", 1),
                    "initial": config.get("initial", 0),
                })
                if "minimum" in config:
                    attributes["minimum"] = config["minimum"]
                if "maximum" in config:
                    attributes["maximum"] = config["maximum"]
            
            # Set the state
            self.hass.states.async_set(full_entity_id, initial_state, attributes)
            
            # Store in virtual helpers registry
            if DOMAIN not in self.hass.data:
                self.hass.data[DOMAIN] = {}
            if "virtual_helpers" not in self.hass.data[DOMAIN]:
                self.hass.data[DOMAIN]["virtual_helpers"] = {}
            
            self.hass.data[DOMAIN]["virtual_helpers"][full_entity_id] = {
                "domain": domain,
                "entity_id": entity_id,
                "friendly_name": name,
                "state": initial_state,
                "attributes": attributes,
                "config": config,
            }
            
            # Track created entity
            if dog_name in self._created_entities:
                self._created_entities[dog_name].append(full_entity_id)
            
            _LOGGER.info(f"Created virtual helper: {full_entity_id}")
            return True
            
        except Exception as err:
            _LOGGER.error(f"Failed to create virtual helper {domain}.pawcontrol_{entity_id}: {err}")
            return False
    
    def _get_default_icon(self, domain: str, entity_id: str) -> str:
        """Get default icon for helper entity."""
        # Icon mapping based on entity_id patterns
        if "fed_" in entity_id or "feeding" in entity_id:
            return "mdi:food"
        elif "walk" in entity_id:
            return "mdi:dog-service"
        elif "outside" in entity_id:
            return "mdi:dog-side"
        elif "gps" in entity_id:
            return "mdi:crosshairs-gps"
        elif "health" in entity_id or "medication" in entity_id:
            return "mdi:medical-bag"
        elif "visitor" in entity_id:
            return "mdi:account-group"
        elif "notification" in entity_id or "reminder" in entity_id:
            return "mdi:bell"
        elif "automation" in entity_id:
            return "mdi:robot"
        elif "training" in entity_id:
            return "mdi:whistle"
        elif "grooming" in entity_id:
            return "mdi:content-cut"
        elif "temperature" in entity_id:
            return "mdi:thermometer"
        elif "weight" in entity_id:
            return "mdi:weight-kilogram"
        elif "location" in entity_id:
            return "mdi:map-marker"
        elif "symptom" in entity_id:
            return "mdi:stethoscope"
        else:
            # Default icons by domain
            if domain == "input_boolean":
                return "mdi:toggle-switch"
            elif domain == "input_number":
                return "mdi:numeric"
            elif domain == "input_text":
                return "mdi:text"
            elif domain == "input_datetime":
                return "mdi:calendar-clock"
            elif domain == "counter":
                return "mdi:counter"
            else:
                return "mdi:help-circle"
    
    async def _setup_feeding_helpers(self, dog_name: str, dog_id: str, device_id: str) -> None:
        """Setup feeding module helpers."""
        helpers = [
            ("input_boolean", f"{dog_id}_fed_breakfast", "Frühstück gefüttert", {"icon": "mdi:food-apple"}),
            ("input_boolean", f"{dog_id}_fed_lunch", "Mittagessen gefüttert", {"icon": "mdi:food"}),
            ("input_boolean", f"{dog_id}_fed_dinner", "Abendessen gefüttert", {"icon": "mdi:food-variant"}),
            ("input_datetime", f"{dog_id}_last_feeding", "Letzte Fütterung", {"has_date": True, "has_time": True}),
            ("input_number", f"{dog_id}_daily_food_amount", "Tägliche Futtermenge", {
                "min": 50, "max": 2000, "step": 10, "unit_of_measurement": "g", "icon": "mdi:weight"
            }),
            ("counter", f"{dog_id}_meals_today", "Mahlzeiten heute", {"icon": "mdi:counter"}),
        ]
        
        for helper_type, entity_id, friendly_name, config in helpers:
            await self._create_virtual_helper(
                helper_type,
                entity_id,
                f"{dog_name} - {friendly_name}",
                config,
                dog_name
            )
    
    async def _setup_gps_helpers(self, dog_name: str, dog_id: str, device_id: str) -> None:
        """Setup GPS module helpers."""
        helpers = [
            ("input_boolean", f"{dog_id}_gps_tracking", "GPS-Tracking aktiv", {"icon": "mdi:crosshairs-gps"}),
            ("input_boolean", f"{dog_id}_is_outside", "Ist draußen", {"icon": "mdi:dog-side"}),
            ("input_boolean", f"{dog_id}_walk_in_progress", "Spaziergang läuft", {"icon": "mdi:walk"}),
            ("input_number", f"{dog_id}_gps_signal", "GPS-Signalstärke", {
                "min": 0, "max": 100, "step": 1, "unit_of_measurement": "%", "icon": "mdi:signal"
            }),
            ("input_text", f"{dog_id}_current_location", "Aktueller Standort", {"max": 100, "icon": "mdi:map-marker"}),
        ]
        
        for helper_type, entity_id, friendly_name, config in helpers:
            await self._create_virtual_helper(
                helper_type,
                entity_id,
                f"{dog_name} - {friendly_name}",
                config,
                dog_name
            )
    
    async def _setup_health_helpers(self, dog_name: str, dog_id: str, device_id: str) -> None:
        """Setup health module helpers."""
        helpers = [
            ("input_boolean", f"{dog_id}_needs_medication", "Benötigt Medikation", {"icon": "mdi:pill"}),
            ("input_boolean", f"{dog_id}_health_alert", "Gesundheitsalarm", {"icon": "mdi:alert-circle"}),
            ("input_number", f"{dog_id}_temperature", "Temperatur", {
                "min": 35.0, "max": 42.0, "step": 0.1, "unit_of_measurement": "°C", "icon": "mdi:thermometer"
            }),
            ("input_number", f"{dog_id}_weight", "Gewicht", {
                "min": 0.5, "max": 100, "step": 0.1, "unit_of_measurement": "kg", "icon": "mdi:weight-kilogram"
            }),
            ("input_text", f"{dog_id}_symptoms", "Symptome", {"max": 255, "icon": "mdi:stethoscope"}),
        ]
        
        for helper_type, entity_id, friendly_name, config in helpers:
            await self._create_virtual_helper(
                helper_type,
                entity_id,
                f"{dog_name} - {friendly_name}",
                config,
                dog_name
            )
    
    async def _setup_walk_helpers(self, dog_name: str, dog_id: str, device_id: str) -> None:
        """Setup walk module helpers."""
        helpers = [
            ("input_boolean", f"{dog_id}_needs_walk", "Braucht Spaziergang", {"icon": "mdi:dog-service"}),
            ("input_boolean", f"{dog_id}_walk_completed", "Spaziergang erledigt", {"icon": "mdi:check-circle"}),
            ("input_boolean", f"{dog_id}_is_outside", "Ist draußen", {"icon": "mdi:dog-side"}),  # Important!
            ("input_boolean", f"{dog_id}_walk_in_progress", "Spaziergang läuft", {"icon": "mdi:walk"}),
            ("input_datetime", f"{dog_id}_last_walk", "Letzter Spaziergang", {"has_date": True, "has_time": True}),
            ("input_number", f"{dog_id}_walk_distance_today", "Spaziergang-Distanz heute", {
                "min": 0, "max": 100, "step": 0.1, "unit_of_measurement": "km", "icon": "mdi:map-marker-path"
            }),
            ("counter", f"{dog_id}_walks_today", "Spaziergänge heute", {"icon": "mdi:counter"}),
        ]
        
        for helper_type, entity_id, friendly_name, config in helpers:
            await self._create_virtual_helper(
                helper_type,
                entity_id,
                f"{dog_name} - {friendly_name}",
                config,
                dog_name
            )
    
    async def _setup_training_helpers(self, dog_name: str, dog_id: str, device_id: str) -> None:
        """Setup training module helpers."""
        helpers = [
            ("input_boolean", f"{dog_id}_training_session", "Trainingseinheit", {"icon": "mdi:whistle"}),
            ("input_datetime", f"{dog_id}_last_training", "Letztes Training", {"has_date": True, "has_time": True}),
            ("counter", f"{dog_id}_training_sessions_week", "Trainingseinheiten diese Woche", {"icon": "mdi:counter"}),
        ]
        
        for helper_type, entity_id, friendly_name, config in helpers:
            await self._create_virtual_helper(
                helper_type,
                entity_id,
                f"{dog_name} - {friendly_name}",
                config,
                dog_name
            )
    
    async def _setup_grooming_helpers(self, dog_name: str, dog_id: str, device_id: str) -> None:
        """Setup grooming module helpers."""
        helpers = [
            ("input_datetime", f"{dog_id}_last_grooming", "Letzte Pflege", {"has_date": True}),
            ("input_datetime", f"{dog_id}_last_bath", "Letztes Bad", {"has_date": True}),
        ]
        
        for helper_type, entity_id, friendly_name, config in helpers:
            await self._create_virtual_helper(
                helper_type,
                entity_id,
                f"{dog_name} - {friendly_name}",
                config,
                dog_name
            )
    
    async def _setup_visitor_helpers(self, dog_name: str, dog_id: str, device_id: str) -> None:
        """Setup visitor module helpers."""
        helpers = [
            ("input_boolean", f"{dog_id}_visitor_mode", "Besuchermodus", {"icon": "mdi:account-group"}),
            ("input_text", f"{dog_id}_visitor_name", "Besuchername", {"max": 100, "icon": "mdi:account"}),
        ]
        
        for helper_type, entity_id, friendly_name, config in helpers:
            await self._create_virtual_helper(
                helper_type,
                entity_id,
                f"{dog_name} - {friendly_name}",
                config,
                dog_name
            )
    
    async def _setup_notification_helpers(self, dog_name: str, dog_id: str, device_id: str) -> None:
        """Setup notification module helpers."""
        helpers = [
            ("input_boolean", f"{dog_id}_notifications_enabled", "Benachrichtigungen aktiv", {"icon": "mdi:bell", "initial": STATE_ON}),
            ("input_boolean", f"{dog_id}_feeding_reminders", "Fütterungs-Erinnerungen", {"icon": "mdi:bell-ring", "initial": STATE_ON}),
            ("input_boolean", f"{dog_id}_walk_reminders", "Spaziergang-Erinnerungen", {"icon": "mdi:bell-alert", "initial": STATE_ON}),
        ]
        
        for helper_type, entity_id, friendly_name, config in helpers:
            await self._create_virtual_helper(
                helper_type,
                entity_id,
                f"{dog_name} - {friendly_name}",
                config,
                dog_name
            )
    
    async def _setup_automation_helpers(self, dog_name: str, dog_id: str, device_id: str) -> None:
        """Setup automation module helpers."""
        helpers = [
            ("input_boolean", f"{dog_id}_automation_enabled", "Automatisierung aktiv", {"icon": "mdi:robot", "initial": STATE_ON}),
            ("input_boolean", f"{dog_id}_auto_walk_detection", "Auto Spaziergang-Erkennung", {"icon": "mdi:motion-sensor"}),
        ]
        
        for helper_type, entity_id, friendly_name, config in helpers:
            await self._create_virtual_helper(
                helper_type,
                entity_id,
                f"{dog_name} - {friendly_name}",
                config,
                dog_name
            )
    
    async def async_cleanup_dog(self, dog_name: str) -> None:
        """
        Complete cleanup when a dog is removed.
        
        This removes all entities, helpers, automations, and dashboards for a specific dog.
        """
        _LOGGER.info(f"Starting cleanup for dog: {dog_name}")
        
        dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        
        # Get list of entities from setup status
        if dog_name in self._setup_status:
            entities_to_remove = self._setup_status[dog_name].get("entities", [])
            
            # Remove all tracked entities
            for entity_id in entities_to_remove:
                # Remove from states
                self.hass.states.async_remove(entity_id)
                # Remove from registry if exists
                if entity_registry.async_get(entity_id):
                    entity_registry.async_remove(entity_id)
                _LOGGER.debug(f"Removed entity: {entity_id}")
        
        # Clean up virtual helpers
        if DOMAIN in self.hass.data and "virtual_helpers" in self.hass.data[DOMAIN]:
            virtual_helpers = self.hass.data[DOMAIN]["virtual_helpers"]
            helpers_to_remove = []
            for full_entity_id in virtual_helpers:
                if f"pawcontrol_{dog_id}" in full_entity_id:
                    helpers_to_remove.append(full_entity_id)
            
            for full_entity_id in helpers_to_remove:
                # Remove state
                self.hass.states.async_remove(full_entity_id)
                # Remove from virtual helpers
                del virtual_helpers[full_entity_id]
                _LOGGER.debug(f"Removed virtual helper: {full_entity_id}")
        
        # Remove device
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, f"dog_{dog_id}")}
        )
        if device:
            device_registry.async_remove_device(device.id)
            _LOGGER.debug(f"Removed device: {device.id}")
        
        # Remove dashboard if it exists
        await self._dashboard_manager.async_remove_dog_dashboard(dog_name)
        
        # Remove from setup status
        if dog_name in self._setup_status:
            del self._setup_status[dog_name]
            await self._save_setup_status()
        
        _LOGGER.info(f"Cleanup complete for dog: {dog_name}")
    
    async def async_cleanup_failed_setup(self) -> None:
        """Cleanup after a failed setup."""
        _LOGGER.info("Cleaning up failed setup")
        
        # Remove any partially created entities
        entity_registry = er.async_get(self.hass)
        
        entities_to_remove = []
        for entity_id, entity_entry in entity_registry.entities.items():
            if entity_id.startswith("pawcontrol_") or "pawcontrol_" in entity_id:
                entities_to_remove.append(entity_id)
        
        for entity_id in entities_to_remove:
            self.hass.states.async_remove(entity_id)
            entity_registry.async_remove(entity_id)
            _LOGGER.debug(f"Removed entity: {entity_id}")
        
        # Clear virtual helpers
        if DOMAIN in self.hass.data and "virtual_helpers" in self.hass.data[DOMAIN]:
            for entity_id in list(self.hass.data[DOMAIN]["virtual_helpers"].keys()):
                self.hass.states.async_remove(entity_id)
            self.hass.data[DOMAIN]["virtual_helpers"].clear()
        
        # Clear setup status
        self._setup_status.clear()
        await self._save_setup_status()
        
        # Remove all dashboards
        await self._dashboard_manager.async_remove_all_dashboards()
        
        _LOGGER.info("Failed setup cleanup complete")
    
    async def _load_setup_status(self) -> None:
        """Load setup status from storage."""
        data = await self._store.async_load()
        if data:
            self._setup_status = data.get("setup_status", {})
            _LOGGER.debug(f"Loaded setup status for {len(self._setup_status)} dogs")
    
    async def _save_setup_status(self) -> None:
        """Save setup status to storage."""
        await self._store.async_save({
            "setup_status": self._setup_status,
            "version": STORAGE_VERSION,
        })
        _LOGGER.debug(f"Saved setup status for {len(self._setup_status)} dogs")
    
    async def async_restore_virtual_helpers(self) -> None:
        """Restore virtual helpers on startup."""
        if DOMAIN not in self.hass.data:
            return
        
        virtual_helpers = self.hass.data[DOMAIN].get("virtual_helpers", {})
        
        for full_entity_id, helper_data in virtual_helpers.items():
            # Restore the state
            self.hass.states.async_set(
                full_entity_id,
                helper_data.get("state", ""),
                helper_data.get("attributes", {})
            )
        
        if virtual_helpers:
            _LOGGER.info(f"Restored {len(virtual_helpers)} virtual helpers")
