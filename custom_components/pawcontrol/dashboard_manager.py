"""Advanced dashboard manager for PawControl with automatic Lovelace integration."""
from __future__ import annotations

import logging
import yaml
from typing import Any, Dict, List
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.components import lovelace
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    MODULE_FEEDING,
    MODULE_WALK,
    MODULE_HEALTH,
    MODULE_GPS,
    MODULE_TRAINING,
    MODULE_GROOMING,
    MODULE_VISITOR,
    MODULE_NOTIFICATIONS,
    MODULE_AUTOMATION,
)

_LOGGER = logging.getLogger(__name__)


class DashboardManager:
    """Manage dashboard creation and updates for PawControl."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the dashboard manager."""
        self.hass = hass
        self._dashboards_created: List[str] = []

    async def async_create_dog_dashboard(
        self,
        dog_name: str,
        dog_config: dict,
        modules: dict[str, Any],
    ) -> bool:
        """Create a complete dashboard for a dog."""
        try:
            dog_id = slugify(dog_name)
            dashboard_path = f"pawcontrol-{dog_id}"
            
            _LOGGER.info(f"Creating dashboard for {dog_name} at {dashboard_path}")
            
            # Create dashboard configuration
            dashboard_config = self._generate_dashboard_config(
                dog_name, dog_id, dog_config, modules
            )
            
            # Add dashboard to Lovelace
            success = await self._add_lovelace_dashboard(
                dashboard_path,
                f"PawControl - {dog_name}",
                dashboard_config
            )
            
            if success:
                self._dashboards_created.append(dashboard_path)
                _LOGGER.info(f"Dashboard created successfully for {dog_name}")
            else:
                _LOGGER.error(f"Failed to create dashboard for {dog_name}")
            
            return success
            
        except Exception as err:
            _LOGGER.error(f"Error creating dashboard for {dog_name}: {err}", exc_info=True)
            return False

    def _generate_dashboard_config(
        self,
        dog_name: str,
        dog_id: str,
        dog_config: dict,
        modules: dict[str, Any],
    ) -> dict:
        """Generate complete dashboard configuration."""
        views = []
        
        # Always create overview view
        views.append(self._create_overview_view(dog_name, dog_id, dog_config))
        
        # Create module-specific views based on enabled modules
        if modules.get(MODULE_FEEDING, {}).get("enabled", False):
            views.append(self._create_feeding_view(dog_name, dog_id))
        
        if modules.get(MODULE_WALK, {}).get("enabled", False):
            views.append(self._create_walk_view(dog_name, dog_id))
        
        if modules.get(MODULE_HEALTH, {}).get("enabled", False):
            views.append(self._create_health_view(dog_name, dog_id))
        
        if modules.get(MODULE_GPS, {}).get("enabled", False):
            views.append(self._create_gps_view(dog_name, dog_id))
        
        if modules.get(MODULE_TRAINING, {}).get("enabled", False):
            views.append(self._create_training_view(dog_name, dog_id))
        
        # Add statistics view if we have data to show
        if len(views) > 1:
            views.append(self._create_statistics_view(dog_name, dog_id))
        
        return {
            "title": f"PawControl - {dog_name}",
            "views": views,
        }

    def _create_overview_view(self, dog_name: str, dog_id: str, dog_config: dict) -> dict:
        """Create the main overview view."""
        cards = []
        
        # Header card with dog info
        cards.append({
            "type": "markdown",
            "content": f"""# 🐕 {dog_name}
**Rasse:** {dog_config.get('dog_breed', 'Unbekannt')}  
**Alter:** {dog_config.get('dog_age', 'Unbekannt')} Jahre  
**Gewicht:** {dog_config.get('dog_weight', 'Unbekannt')} kg  
"""
        })
        
        # Status card
        cards.append({
            "type": "entities",
            "title": "Status",
            "show_header_toggle": False,
            "entities": [
                f"sensor.pawcontrol_{dog_id}_status",
                f"sensor.pawcontrol_{dog_id}_daily_summary",
                f"select.pawcontrol_{dog_id}_mood_select",
                f"select.pawcontrol_{dog_id}_health_status_select",
            ],
        })
        
        # Quick status indicators
        cards.append({
            "type": "glance",
            "title": "Schnellstatus",
            "entities": [
                f"binary_sensor.pawcontrol_{dog_id}_is_hungry",
                f"binary_sensor.pawcontrol_{dog_id}_needs_walk",
                f"binary_sensor.pawcontrol_{dog_id}_needs_attention",
                f"binary_sensor.pawcontrol_{dog_id}_is_outside",
            ],
        })
        
        # Activity summary
        cards.append({
            "type": "horizontal-stack",
            "cards": [
                {
                    "type": "entity",
                    "entity": f"sensor.pawcontrol_{dog_id}_health_score",
                    "name": "Gesundheit",
                    "icon": "mdi:heart-pulse",
                },
                {
                    "type": "entity",
                    "entity": f"sensor.pawcontrol_{dog_id}_happiness_score",
                    "name": "Glück",
                    "icon": "mdi:emoticon-happy",
                },
                {
                    "type": "entity",
                    "entity": f"sensor.pawcontrol_{dog_id}_activity_score",
                    "name": "Aktivität",
                    "icon": "mdi:run",
                },
            ],
        })
        
        # Quick actions
        cards.append({
            "type": "vertical-stack",
            "title": "Schnellaktionen",
            "cards": [
                {
                    "type": "horizontal-stack",
                    "cards": [
                        {
                            "type": "button",
                            "name": "Füttern",
                            "icon": "mdi:food-drumstick",
                            "tap_action": {
                                "action": "call-service",
                                "service": "pawcontrol.feed_dog",
                                "service_data": {
                                    "dog_name": dog_name,
                                    "meal_type": "auto",
                                },
                            },
                        },
                        {
                            "type": "button",
                            "name": "Spaziergang",
                            "icon": "mdi:dog-service",
                            "tap_action": {
                                "action": "call-service",
                                "service": "pawcontrol.start_walk",
                                "service_data": {
                                    "dog_name": dog_name,
                                    "walk_type": "Normal",
                                },
                            },
                        },
                    ],
                },
                {
                    "type": "horizontal-stack",
                    "cards": [
                        {
                            "type": "button",
                            "entity": f"button.pawcontrol_{dog_id}_mark_poop_done",
                            "name": "Geschäft erledigt",
                            "icon": "mdi:emoticon-poop",
                        },
                        {
                            "type": "button",
                            "entity": f"button.pawcontrol_{dog_id}_emergency",
                            "name": "Notfall",
                            "icon": "mdi:alert-circle",
                        },
                    ],
                },
            ],
        })
        
        # Modes
        cards.append({
            "type": "entities",
            "title": "Modi",
            "entities": [
                f"switch.pawcontrol_{dog_id}_emergency_mode_switch",
                f"switch.pawcontrol_{dog_id}_visitor_mode_switch",
                f"switch.pawcontrol_{dog_id}_auto_walk_detection",
            ],
        })
        
        return {
            "title": "Übersicht",
            "path": "overview",
            "icon": "mdi:view-dashboard",
            "cards": cards,
        }

    def _create_feeding_view(self, dog_name: str, dog_id: str) -> dict:
        """Create feeding view."""
        cards = []
        
        # Feeding times configuration
        cards.append({
            "type": "entities",
            "title": "Fütterungszeiten",
            "entities": [
                f"input_datetime.pawcontrol_{dog_id}_breakfast_time",
                f"input_datetime.pawcontrol_{dog_id}_lunch_time",
                f"input_datetime.pawcontrol_{dog_id}_dinner_time",
            ],
        })
        
        # Feeding status
        cards.append({
            "type": "entities",
            "title": "Fütterungsstatus",
            "entities": [
                f"input_boolean.pawcontrol_{dog_id}_fed_breakfast",
                f"input_boolean.pawcontrol_{dog_id}_fed_lunch",
                f"input_boolean.pawcontrol_{dog_id}_fed_dinner",
                f"counter.pawcontrol_{dog_id}_meals_today",
                f"input_datetime.pawcontrol_{dog_id}_last_feeding",
            ],
        })
        
        # Food management
        cards.append({
            "type": "entities",
            "title": "Futterverwaltung",
            "entities": [
                f"input_number.pawcontrol_{dog_id}_daily_food_amount",
                f"input_select.pawcontrol_{dog_id}_food_type",
                f"input_text.pawcontrol_{dog_id}_feeding_notes",
            ],
        })
        
        # Quick feeding buttons
        cards.append({
            "type": "horizontal-stack",
            "cards": [
                {
                    "type": "button",
                    "name": "Frühstück",
                    "icon": "mdi:weather-sunset-up",
                    "tap_action": {
                        "action": "call-service",
                        "service": "pawcontrol.feed_dog",
                        "service_data": {
                            "dog_name": dog_name,
                            "meal_type": "breakfast",
                        },
                    },
                },
                {
                    "type": "button",
                    "name": "Mittagessen",
                    "icon": "mdi:weather-sunny",
                    "tap_action": {
                        "action": "call-service",
                        "service": "pawcontrol.feed_dog",
                        "service_data": {
                            "dog_name": dog_name,
                            "meal_type": "lunch",
                        },
                    },
                },
                {
                    "type": "button",
                    "name": "Abendessen",
                    "icon": "mdi:weather-sunset-down",
                    "tap_action": {
                        "action": "call-service",
                        "service": "pawcontrol.feed_dog",
                        "service_data": {
                            "dog_name": dog_name,
                            "meal_type": "dinner",
                        },
                    },
                },
            ],
        })
        
        # Feeding history
        cards.append({
            "type": "history-graph",
            "title": "Fütterungsverlauf",
            "entities": [
                f"counter.pawcontrol_{dog_id}_meals_today",
                f"binary_sensor.pawcontrol_{dog_id}_is_hungry",
            ],
            "hours_to_show": 24,
        })
        
        return {
            "title": "Fütterung",
            "path": "feeding",
            "icon": "mdi:food-drumstick",
            "cards": cards,
        }

    def _create_walk_view(self, dog_name: str, dog_id: str) -> dict:
        """Create walk view."""
        cards = []
        
        # Walk status
        cards.append({
            "type": "entities",
            "title": "Spaziergang Status",
            "entities": [
                f"input_boolean.pawcontrol_{dog_id}_needs_walk",
                f"input_boolean.pawcontrol_{dog_id}_walk_completed",
                f"input_boolean.pawcontrol_{dog_id}_walk_in_progress",
                f"counter.pawcontrol_{dog_id}_walks_today",
                f"input_datetime.pawcontrol_{dog_id}_last_walk",
            ],
        })
        
        # Walk metrics
        cards.append({
            "type": "entities",
            "title": "Spaziergang Metriken",
            "entities": [
                f"input_number.pawcontrol_{dog_id}_walk_distance_today",
                f"input_number.pawcontrol_{dog_id}_daily_walk_duration",
                f"number.pawcontrol_{dog_id}_calories_burned_walk",
            ],
        })
        
        # Walk preferences
        cards.append({
            "type": "entities",
            "title": "Präferenzen",
            "entities": [
                f"input_select.pawcontrol_{dog_id}_preferred_walk_type",
                f"input_text.pawcontrol_{dog_id}_walk_notes",
            ],
        })
        
        # Walk control buttons
        cards.append({
            "type": "horizontal-stack",
            "cards": [
                {
                    "type": "button",
                    "name": "Spaziergang starten",
                    "icon": "mdi:play",
                    "tap_action": {
                        "action": "call-service",
                        "service": "pawcontrol.start_walk",
                        "service_data": {
                            "dog_name": dog_name,
                            "walk_type": "Normal",
                        },
                    },
                },
                {
                    "type": "button",
                    "name": "Spaziergang beenden",
                    "icon": "mdi:stop",
                    "tap_action": {
                        "action": "call-service",
                        "service": "pawcontrol.end_walk",
                        "service_data": {
                            "dog_name": dog_name,
                            "duration": 30,
                        },
                    },
                },
            ],
        })
        
        # Walk history
        cards.append({
            "type": "history-graph",
            "title": "Spaziergang Verlauf",
            "entities": [
                f"counter.pawcontrol_{dog_id}_walks_today",
                f"input_number.pawcontrol_{dog_id}_walk_distance_today",
            ],
            "hours_to_show": 168,  # 1 week
        })
        
        return {
            "title": "Spaziergänge",
            "path": "walks",
            "icon": "mdi:dog-service",
            "cards": cards,
        }

    def _create_health_view(self, dog_name: str, dog_id: str) -> dict:
        """Create health view."""
        cards = []
        
        # Health overview
        cards.append({
            "type": "entities",
            "title": "Gesundheitsstatus",
            "entities": [
                f"input_number.pawcontrol_{dog_id}_health_score",
                f"input_select.pawcontrol_{dog_id}_health_status",
                f"input_boolean.pawcontrol_{dog_id}_health_alert",
            ],
        })
        
        # Vital signs
        cards.append({
            "type": "entities",
            "title": "Vitalwerte",
            "entities": [
                f"input_number.pawcontrol_{dog_id}_weight",
                f"input_number.pawcontrol_{dog_id}_temperature",
                f"number.pawcontrol_{dog_id}_heart_rate",
            ],
        })
        
        # Medical management
        cards.append({
            "type": "entities",
            "title": "Medizinisch",
            "entities": [
                f"input_boolean.pawcontrol_{dog_id}_needs_medication",
                f"input_datetime.pawcontrol_{dog_id}_last_medication",
                f"input_datetime.pawcontrol_{dog_id}_last_vet_visit",
                f"input_datetime.pawcontrol_{dog_id}_next_vet_appointment",
            ],
        })
        
        # Health notes
        cards.append({
            "type": "entities",
            "title": "Notizen",
            "entities": [
                f"input_text.pawcontrol_{dog_id}_symptoms",
                f"input_text.pawcontrol_{dog_id}_medication_notes",
                f"input_text.pawcontrol_{dog_id}_vet_contact",
            ],
        })
        
        # Health history
        cards.append({
            "type": "history-graph",
            "title": "Gesundheitsverlauf",
            "entities": [
                f"input_number.pawcontrol_{dog_id}_weight",
                f"input_number.pawcontrol_{dog_id}_temperature",
            ],
            "hours_to_show": 720,  # 30 days
        })
        
        return {
            "title": "Gesundheit",
            "path": "health",
            "icon": "mdi:medical-bag",
            "cards": cards,
        }

    def _create_gps_view(self, dog_name: str, dog_id: str) -> dict:
        """Create GPS tracking view."""
        cards = []
        
        # Map card
        cards.append({
            "type": "map",
            "title": f"{dog_name} Standort",
            "entities": [
                f"device_tracker.pawcontrol_{dog_id}",
            ],
            "default_zoom": 15,
        })
        
        # GPS status
        cards.append({
            "type": "entities",
            "title": "GPS Status",
            "entities": [
                f"input_boolean.pawcontrol_{dog_id}_gps_tracking",
                f"input_boolean.pawcontrol_{dog_id}_is_outside",
                f"input_number.pawcontrol_{dog_id}_gps_signal",
                f"input_number.pawcontrol_{dog_id}_distance_from_home",
            ],
        })
        
        # Location info
        cards.append({
            "type": "entities",
            "title": "Standort",
            "entities": [
                f"input_text.pawcontrol_{dog_id}_current_location",
                f"input_text.pawcontrol_{dog_id}_home_coordinates",
                f"input_number.pawcontrol_{dog_id}_geofence_radius",
            ],
        })
        
        # GPS controls
        cards.append({
            "type": "button",
            "name": "GPS aktualisieren",
            "icon": "mdi:crosshairs-gps",
            "tap_action": {
                "action": "call-service",
                "service": "pawcontrol.update_gps",
                "service_data": {
                    "dog_name": dog_name,
                    "latitude": 0,
                    "longitude": 0,
                },
            },
        })
        
        return {
            "title": "GPS Tracking",
            "path": "gps",
            "icon": "mdi:map-marker",
            "cards": cards,
        }

    def _create_training_view(self, dog_name: str, dog_id: str) -> dict:
        """Create training view."""
        cards = []
        
        # Training status
        cards.append({
            "type": "entities",
            "title": "Training Status",
            "entities": [
                f"input_boolean.pawcontrol_{dog_id}_training_session",
                f"input_datetime.pawcontrol_{dog_id}_last_training",
                f"counter.pawcontrol_{dog_id}_training_sessions_week",
            ],
        })
        
        # Training notes
        cards.append({
            "type": "entities",
            "title": "Fortschritt",
            "entities": [
                f"input_text.pawcontrol_{dog_id}_learned_commands",
            ],
        })
        
        return {
            "title": "Training",
            "path": "training",
            "icon": "mdi:whistle",
            "cards": cards,
        }

    def _create_statistics_view(self, dog_name: str, dog_id: str) -> dict:
        """Create statistics view."""
        cards = []
        
        # Activity statistics
        cards.append({
            "type": "statistics-graph",
            "title": "Aktivitäts-Statistiken",
            "entities": [
                f"counter.pawcontrol_{dog_id}_walks_today",
                f"counter.pawcontrol_{dog_id}_meals_today",
            ],
            "stat_types": ["sum", "mean"],
            "days_to_show": 7,
        })
        
        # Health statistics
        cards.append({
            "type": "statistics-graph",
            "title": "Gesundheits-Statistiken",
            "entities": [
                f"input_number.pawcontrol_{dog_id}_weight",
            ],
            "stat_types": ["mean", "min", "max"],
            "days_to_show": 30,
        })
        
        return {
            "title": "Statistiken",
            "path": "statistics",
            "icon": "mdi:chart-line",
            "cards": cards,
        }

    async def _add_lovelace_dashboard(
        self,
        url_path: str,
        title: str,
        config: dict,
    ) -> bool:
        """Add dashboard to Lovelace."""
        try:
            # Check if lovelace is available
            if not hasattr(self.hass.data, "lovelace"):
                _LOGGER.warning("Lovelace not available, storing config for manual creation")
                # Store config for manual creation
                if DOMAIN not in self.hass.data:
                    self.hass.data[DOMAIN] = {}
                if "dashboards" not in self.hass.data[DOMAIN]:
                    self.hass.data[DOMAIN]["dashboards"] = {}
                self.hass.data[DOMAIN]["dashboards"][url_path] = config
                return True
            
            # Try to add dashboard via lovelace
            lovelace_config = {
                "mode": "yaml",
                "filename": f"pawcontrol_{url_path}.yaml",
                "title": title,
                "icon": "mdi:dog",
                "show_in_sidebar": True,
                "require_admin": False,
            }
            
            # Add to lovelace dashboards
            lovelace = self.hass.data.lovelace
            if not hasattr(lovelace, "dashboards"):
                lovelace.dashboards = {}
            
            lovelace.dashboards[url_path] = lovelace_config
            
            # Save the dashboard config as YAML
            await self._save_dashboard_yaml(url_path, config)
            
            return True
            
        except Exception as err:
            _LOGGER.error(f"Failed to add Lovelace dashboard: {err}", exc_info=True)
            return False

    async def _save_dashboard_yaml(self, url_path: str, config: dict) -> None:
        """Save dashboard configuration as YAML file."""
        try:
            # Create pawcontrol dashboards directory
            dashboards_dir = Path(self.hass.config.path("pawcontrol_dashboards"))
            dashboards_dir.mkdir(exist_ok=True)
            
            # Save dashboard config as YAML
            dashboard_file = dashboards_dir / f"{url_path}.yaml"
            with open(dashboard_file, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
            _LOGGER.info(f"Dashboard config saved to {dashboard_file}")
            
        except Exception as err:
            _LOGGER.error(f"Failed to save dashboard YAML: {err}", exc_info=True)

    async def async_remove_dog_dashboard(self, dog_name: str) -> bool:
        """Remove dashboard for a specific dog."""
        try:
            dog_id = slugify(dog_name)
            dashboard_path = f"pawcontrol-{dog_id}"
            
            # Remove from lovelace if exists
            if hasattr(self.hass.data, "lovelace") and hasattr(self.hass.data.lovelace, "dashboards"):
                if dashboard_path in self.hass.data.lovelace.dashboards:
                    del self.hass.data.lovelace.dashboards[dashboard_path]
            
            # Remove from stored configs
            if DOMAIN in self.hass.data and "dashboards" in self.hass.data[DOMAIN]:
                if dashboard_path in self.hass.data[DOMAIN]["dashboards"]:
                    del self.hass.data[DOMAIN]["dashboards"][dashboard_path]
            
            # Remove YAML file
            dashboards_dir = Path(self.hass.config.path("pawcontrol_dashboards"))
            dashboard_file = dashboards_dir / f"{dashboard_path}.yaml"
            if dashboard_file.exists():
                dashboard_file.unlink()
            
            # Remove from created list
            if dashboard_path in self._dashboards_created:
                self._dashboards_created.remove(dashboard_path)
            
            _LOGGER.info(f"Dashboard removed for {dog_name}")
            return True
            
        except Exception as err:
            _LOGGER.error(f"Failed to remove dashboard for {dog_name}: {err}", exc_info=True)
            return False

    async def async_remove_all_dashboards(self) -> None:
        """Remove all created dashboards."""
        for dashboard_path in list(self._dashboards_created):
            # Extract dog name from path
            dog_name = dashboard_path.replace("pawcontrol-", "").replace("-", " ").title()
            await self.async_remove_dog_dashboard(dog_name)
