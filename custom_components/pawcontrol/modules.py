"""Module management for PawControl integration with working helper creation."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
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
from .coordinator import PawControlCoordinator
from .helper_factory import HelperFactory

_LOGGER = logging.getLogger(__name__)


class ModuleManager:
    """Manage PawControl modules for a specific dog with proper helper creation."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: PawControlCoordinator,
        dog_config: dict[str, Any],
    ) -> None:
        """Initialize the module manager."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.dog_config = dog_config
        self.dog_name = dog_config.get(CONF_DOG_NAME, "unknown")
        self.dog_id = self._sanitize_name(self.dog_name)
        
        # Initialize helper factory
        self.helper_factory = HelperFactory(hass, self.dog_name)
        
        # Track enabled modules
        self._enabled_modules: Dict[str, Any] = {}
        
        # Track created entities
        self._created_entities: List[str] = []
        
        # Module handlers
        self._module_handlers = {
            MODULE_FEEDING: self._setup_feeding_module,
            MODULE_GPS: self._setup_gps_module,
            MODULE_HEALTH: self._setup_health_module,
            MODULE_WALK: self._setup_walk_module,
            MODULE_NOTIFICATIONS: self._setup_notifications_module,
            MODULE_AUTOMATION: self._setup_automation_module,
            MODULE_DASHBOARD: self._setup_dashboard_module,
            MODULE_TRAINING: self._setup_training_module,
            MODULE_GROOMING: self._setup_grooming_module,
            MODULE_VISITOR: self._setup_visitor_module,
        }
        
        # Initialize helper factory on creation
        hass.async_create_task(self._async_init())

    async def _async_init(self) -> None:
        """Async initialization."""
        await self.helper_factory.async_initialize()

    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for entity IDs."""
        return name.lower().replace(" ", "_").replace("-", "_")

    async def async_enable_module(
        self, module_id: str, module_config: dict[str, Any]
    ) -> bool:
        """Enable a specific module."""
        if module_id in self._enabled_modules:
            _LOGGER.warning(f"Module {module_id} already enabled for {self.dog_name}")
            return True
        
        handler = self._module_handlers.get(module_id)
        if not handler:
            _LOGGER.error(f"Unknown module: {module_id}")
            return False
        
        try:
            _LOGGER.info(f"Enabling module {module_id} for {self.dog_name}")
            await handler(module_config)
            self._enabled_modules[module_id] = module_config
            return True
        except Exception as err:
            _LOGGER.error(f"Failed to enable module {module_id}: {err}", exc_info=True)
            return False

    async def async_disable_module(self, module_id: str) -> bool:
        """Disable a specific module."""
        if module_id not in self._enabled_modules:
            _LOGGER.warning(f"Module {module_id} not enabled for {self.dog_name}")
            return True
        
        try:
            _LOGGER.info(f"Disabling module {module_id} for {self.dog_name}")
            
            # Remove module-specific entities
            await self.helper_factory.async_remove_module_helpers(module_id)
            
            del self._enabled_modules[module_id]
            return True
        except Exception as err:
            _LOGGER.error(f"Failed to disable module {module_id}: {err}", exc_info=True)
            return False

    async def async_disable_all_modules(self) -> None:
        """Disable all modules."""
        for module_id in list(self._enabled_modules.keys()):
            await self.async_disable_module(module_id)
        
        # Clean up all created entities
        await self.helper_factory.async_remove_all_helpers()

    async def _setup_feeding_module(self, config: dict[str, Any]) -> None:
        """Set up feeding module helpers and entities."""
        # Create feeding-related input entities using helper factory
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_fed_breakfast",
            "Frühstück gefüttert",
            icon="mdi:food-apple"
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_fed_lunch",
            "Mittagessen gefüttert",
            icon="mdi:food"
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_fed_dinner",
            "Abendessen gefüttert",
            icon="mdi:food-variant"
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_last_feeding",
            "Letzte Fütterung",
            has_time=True,
            has_date=True
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_breakfast_time",
            "Frühstückszeit",
            has_time=True
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_lunch_time",
            "Mittagszeit",
            has_time=True
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_dinner_time",
            "Abendessenzeit",
            has_time=True
        )
        
        await self.helper_factory.create_input_number(
            f"{self.dog_id}_daily_food_amount",
            "Tägliche Futtermenge",
            min_value=50,
            max_value=2000,
            step=10,
            unit="g",
            icon="mdi:weight"
        )
        
        await self.helper_factory.create_counter(
            f"{self.dog_id}_meals_today",
            "Mahlzeiten heute",
            icon="mdi:counter"
        )
        
        await self.helper_factory.create_input_select(
            f"{self.dog_id}_food_type",
            "Futterart",
            ["Trockenfutter", "Nassfutter", "BARF", "Selbstgekocht", "Gemischt"],
            icon="mdi:food-drumstick"
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_feeding_notes",
            "Fütterungsnotizen",
            max_length=255,
            icon="mdi:note-text"
        )
        
        _LOGGER.info(f"Feeding module setup complete for {self.dog_name}")

    async def _setup_gps_module(self, config: dict[str, Any]) -> None:
        """Set up GPS module helpers and entities."""
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_gps_tracking",
            "GPS-Tracking aktiv",
            icon="mdi:crosshairs-gps"
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_is_outside",
            "Ist draußen",
            icon="mdi:dog-side"
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_walk_in_progress",
            "Spaziergang läuft",
            icon="mdi:walk"
        )
        
        await self.helper_factory.create_input_number(
            f"{self.dog_id}_gps_signal",
            "GPS-Signalstärke",
            min_value=0,
            max_value=100,
            step=1,
            unit="%",
            icon="mdi:signal"
        )
        
        await self.helper_factory.create_input_number(
            f"{self.dog_id}_distance_from_home",
            "Entfernung von Zuhause",
            min_value=0,
            max_value=10000,
            step=1,
            unit="m",
            icon="mdi:map-marker-distance"
        )
        
        await self.helper_factory.create_input_number(
            f"{self.dog_id}_geofence_radius",
            "Geofence-Radius",
            min_value=10,
            max_value=1000,
            step=10,
            unit="m",
            initial=50,
            icon="mdi:map-marker-radius"
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_current_location",
            "Aktueller Standort",
            max_length=100,
            icon="mdi:map-marker"
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_home_coordinates",
            "Heimkoordinaten",
            max_length=50,
            icon="mdi:home-map-marker"
        )
        
        _LOGGER.info(f"GPS module setup complete for {self.dog_name}")

    async def _setup_health_module(self, config: dict[str, Any]) -> None:
        """Set up health module helpers and entities."""
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_needs_medication",
            "Benötigt Medikation",
            icon="mdi:pill"
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_health_alert",
            "Gesundheitsalarm",
            icon="mdi:alert-circle"
        )
        
        await self.helper_factory.create_input_number(
            f"{self.dog_id}_temperature",
            "Temperatur",
            min_value=35.0,
            max_value=42.0,
            step=0.1,
            unit="°C",
            initial=38.5,
            icon="mdi:thermometer"
        )
        
        await self.helper_factory.create_input_number(
            f"{self.dog_id}_weight",
            "Gewicht",
            min_value=0.5,
            max_value=100,
            step=0.1,
            unit="kg",
            icon="mdi:weight-kilogram"
        )
        
        await self.helper_factory.create_input_number(
            f"{self.dog_id}_health_score",
            "Gesundheitsscore",
            min_value=0,
            max_value=100,
            step=1,
            unit="%",
            initial=100,
            icon="mdi:heart-pulse"
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_last_vet_visit",
            "Letzter Tierarztbesuch",
            has_date=True
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_next_vet_appointment",
            "Nächster Tierarzttermin",
            has_date=True,
            has_time=True
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_last_medication",
            "Letzte Medikation",
            has_date=True,
            has_time=True
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_symptoms",
            "Symptome",
            max_length=255,
            icon="mdi:stethoscope"
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_medication_notes",
            "Medikationsnotizen",
            max_length=255,
            icon="mdi:note-medical"
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_vet_contact",
            "Tierarztkontakt",
            max_length=255,
            icon="mdi:phone"
        )
        
        await self.helper_factory.create_input_select(
            f"{self.dog_id}_health_status",
            "Gesundheitsstatus",
            ["Ausgezeichnet", "Sehr gut", "Gut", "Normal", "Unwohl", "Krank"],
            icon="mdi:medical-bag"
        )
        
        _LOGGER.info(f"Health module setup complete for {self.dog_name}")

    async def _setup_walk_module(self, config: dict[str, Any]) -> None:
        """Set up walk module helpers and entities."""
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_needs_walk",
            "Braucht Spaziergang",
            icon="mdi:dog-service",
            initial=True
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_walk_completed",
            "Spaziergang erledigt",
            icon="mdi:check-circle"
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_last_walk",
            "Letzter Spaziergang",
            has_date=True,
            has_time=True
        )
        
        await self.helper_factory.create_input_number(
            f"{self.dog_id}_daily_walk_duration",
            "Tägliche Spaziergang-Dauer",
            min_value=0,
            max_value=480,
            step=5,
            unit="min",
            icon="mdi:timer"
        )
        
        await self.helper_factory.create_input_number(
            f"{self.dog_id}_walk_distance_today",
            "Spaziergang-Distanz heute",
            min_value=0,
            max_value=100,
            step=0.1,
            unit="km",
            icon="mdi:map-marker-path"
        )
        
        await self.helper_factory.create_counter(
            f"{self.dog_id}_walks_today",
            "Spaziergänge heute",
            icon="mdi:counter"
        )
        
        await self.helper_factory.create_input_select(
            f"{self.dog_id}_preferred_walk_type",
            "Bevorzugter Spaziergang",
            ["Kurz", "Normal", "Lang", "Training", "Freilauf"],
            icon="mdi:map"
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_walk_notes",
            "Spaziergang-Notizen",
            max_length=255,
            icon="mdi:note"
        )
        
        _LOGGER.info(f"Walk module setup complete for {self.dog_name}")

    async def _setup_notifications_module(self, config: dict[str, Any]) -> None:
        """Set up notifications module helpers."""
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_notifications_enabled",
            "Benachrichtigungen aktiv",
            icon="mdi:bell",
            initial=True
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_feeding_reminders",
            "Fütterungs-Erinnerungen",
            icon="mdi:bell-ring",
            initial=True
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_walk_reminders",
            "Spaziergang-Erinnerungen",
            icon="mdi:bell-alert",
            initial=True
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_health_alerts",
            "Gesundheits-Alarme",
            icon="mdi:bell-plus",
            initial=True
        )
        
        _LOGGER.info(f"Notifications module setup complete for {self.dog_name}")

    async def _setup_automation_module(self, config: dict[str, Any]) -> None:
        """Set up automation module helpers."""
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_automation_enabled",
            "Automatisierung aktiv",
            icon="mdi:robot"
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_auto_feeding_reminder",
            "Auto Fütterungs-Erinnerung",
            icon="mdi:alarm",
            initial=True
        )
        
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_auto_walk_detection",
            "Auto Spaziergang-Erkennung",
            icon="mdi:motion-sensor"
        )
        
        _LOGGER.info(f"Automation module setup complete for {self.dog_name}")

    async def _setup_dashboard_module(self, config: dict[str, Any]) -> None:
        """Set up dashboard module (no helpers needed, handled by dashboard creation)."""
        # Dashboard creation is handled separately
        _LOGGER.info(f"Dashboard module marked for setup for {self.dog_name}")

    async def _setup_training_module(self, config: dict[str, Any]) -> None:
        """Set up training module helpers."""
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_training_session",
            "Trainingseinheit",
            icon="mdi:whistle"
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_last_training",
            "Letztes Training",
            has_date=True,
            has_time=True
        )
        
        await self.helper_factory.create_counter(
            f"{self.dog_id}_training_sessions_week",
            "Trainingseinheiten diese Woche",
            icon="mdi:counter"
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_learned_commands",
            "Gelernte Kommandos",
            max_length=255,
            icon="mdi:dog"
        )
        
        _LOGGER.info(f"Training module setup complete for {self.dog_name}")

    async def _setup_grooming_module(self, config: dict[str, Any]) -> None:
        """Set up grooming module helpers."""
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_last_grooming",
            "Letzte Pflege",
            has_date=True
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_last_bath",
            "Letztes Bad",
            has_date=True
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_last_nail_trim",
            "Letzte Krallenpflege",
            has_date=True
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_grooming_notes",
            "Pflegenotizen",
            max_length=255,
            icon="mdi:content-cut"
        )
        
        _LOGGER.info(f"Grooming module setup complete for {self.dog_name}")

    async def _setup_visitor_module(self, config: dict[str, Any]) -> None:
        """Set up visitor module helpers."""
        await self.helper_factory.create_input_boolean(
            f"{self.dog_id}_visitor_mode",
            "Besuchermodus",
            icon="mdi:account-group"
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_visitor_name",
            "Besuchername",
            max_length=100,
            icon="mdi:account"
        )
        
        await self.helper_factory.create_input_text(
            f"{self.dog_id}_visitor_instructions",
            "Besucheranweisungen",
            max_length=500,
            icon="mdi:clipboard-text"
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_visitor_start",
            "Besucherbeginn",
            has_date=True,
            has_time=True
        )
        
        await self.helper_factory.create_input_datetime(
            f"{self.dog_id}_visitor_end",
            "Besucherende",
            has_date=True,
            has_time=True
        )
        
        _LOGGER.info(f"Visitor module setup complete for {self.dog_name}")
