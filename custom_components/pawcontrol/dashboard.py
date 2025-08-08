"""Dashboard creation for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    MODULE_FEEDING,
    MODULE_WALK,
    MODULE_HEALTH,
    MODULE_GPS,
    MODULE_TRAINING,
    MODULE_GROOMING,
    MODULE_VISITOR,
)

_LOGGER = logging.getLogger(__name__)


class DashboardCreator:
    """Create dashboard for PawControl."""

    def __init__(self, hass: HomeAssistant, dog_name: str, modules: dict[str, Any]):
        """Initialize dashboard creator."""
        self.hass = hass
        self.dog_name = dog_name
        self.dog_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        self.modules = modules

    async def async_create_dashboard(self) -> dict[str, Any]:
        """Create complete dashboard configuration."""
        views = []
        
        # Main overview view
        views.append(self._create_overview_view())
        
        # Module-specific views
        if self.modules.get(MODULE_FEEDING, {}).get("enabled"):
            views.append(self._create_feeding_view())
        
        if self.modules.get(MODULE_WALK, {}).get("enabled"):
            views.append(self._create_walk_view())
        
        if self.modules.get(MODULE_HEALTH, {}).get("enabled"):
            views.append(self._create_health_view())
        
        if self.modules.get(MODULE_GPS, {}).get("enabled"):
            views.append(self._create_gps_view())
        
        if self.modules.get(MODULE_TRAINING, {}).get("enabled"):
            views.append(self._create_training_view())
        
        # Statistics view
        views.append(self._create_statistics_view())
        
        dashboard_config = {
            "title": f"PawControl - {self.dog_name}",
            "path": f"pawcontrol-{self.dog_id}",
            "icon": "mdi:dog",
            "views": views,
        }
        
        return dashboard_config

    def _create_overview_view(self) -> dict[str, Any]:
        """Create overview view."""
        cards = []
        
        # Status card
        cards.append({
            "type": "custom:mushroom-entity-card",
            "entity": f"sensor.pawcontrol_{self.dog_id}_status",
            "name": f"{self.dog_name} Status",
            "icon_color": "green",
            "layout": "vertical",
        })
        
        # Quick stats
        cards.append({
            "type": "horizontal-stack",
            "cards": [
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_health_score",
                    "name": "Gesundheit",
                    "icon": "mdi:heart-pulse",
                    "icon_color": "red",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_happiness_score",
                    "name": "Glück",
                    "icon": "mdi:emoticon-happy",
                    "icon_color": "yellow",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_activity_score",
                    "name": "Aktivität",
                    "icon": "mdi:run",
                    "icon_color": "blue",
                },
            ],
        })
        
        # Daily summary
        cards.append({
            "type": "custom:mushroom-entity-card",
            "entity": f"sensor.pawcontrol_{self.dog_id}_daily_summary",
            "name": "Heute",
            "icon": "mdi:calendar-today",
            "icon_color": "purple",
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
                            "type": "custom:mushroom-template-card",
                            "primary": "Füttern",
                            "icon": "mdi:food-drumstick",
                            "icon_color": "orange",
                            "tap_action": {
                                "action": "call-service",
                                "service": "pawcontrol.feed_dog",
                                "service_data": {
                                    "dog_name": self.dog_name,
                                    "meal_type": "auto",
                                },
                            },
                        },
                        {
                            "type": "custom:mushroom-template-card",
                            "primary": "Spaziergang",
                            "icon": "mdi:dog-service",
                            "icon_color": "green",
                            "tap_action": {
                                "action": "call-service",
                                "service": "pawcontrol.start_walk",
                                "service_data": {
                                    "dog_name": self.dog_name,
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
                            "type": "custom:mushroom-template-card",
                            "primary": "Spielzeit",
                            "icon": "mdi:tennis-ball",
                            "icon_color": "blue",
                            "tap_action": {
                                "action": "call-service",
                                "service": "pawcontrol.start_playtime",
                                "service_data": {
                                    "dog_name": self.dog_name,
                                },
                            },
                        },
                        {
                            "type": "custom:mushroom-template-card",
                            "primary": "Training",
                            "icon": "mdi:whistle",
                            "icon_color": "purple",
                            "tap_action": {
                                "action": "call-service",
                                "service": "pawcontrol.start_training",
                                "service_data": {
                                    "dog_name": self.dog_name,
                                },
                            },
                        },
                    ],
                },
            ],
        })
        
        # Status indicators
        cards.append({
            "type": "entities",
            "title": "Status",
            "entities": [
                f"binary_sensor.pawcontrol_{self.dog_id}_is_hungry",
                f"binary_sensor.pawcontrol_{self.dog_id}_needs_walk",
                f"binary_sensor.pawcontrol_{self.dog_id}_needs_attention",
                f"binary_sensor.pawcontrol_{self.dog_id}_is_outside",
            ],
        })
        
        # Modes
        cards.append({
            "type": "entities",
            "title": "Modi",
            "entities": [
                f"switch.pawcontrol_{self.dog_id}_emergency_mode_switch",
                f"switch.pawcontrol_{self.dog_id}_visitor_mode_switch",
            ],
        })
        
        return {
            "title": "Übersicht",
            "path": "overview",
            "icon": "mdi:view-dashboard",
            "cards": cards,
        }

    def _create_feeding_view(self) -> dict[str, Any]:
        """Create feeding view."""
        cards = []
        
        # Feeding times
        cards.append({
            "type": "entities",
            "title": "Fütterungszeiten",
            "entities": [
                f"datetime.pawcontrol_{self.dog_id}_breakfast_time",
                f"datetime.pawcontrol_{self.dog_id}_lunch_time",
                f"datetime.pawcontrol_{self.dog_id}_dinner_time",
            ],
        })
        
        # Feeding status
        cards.append({
            "type": "vertical-stack",
            "title": "Fütterungsstatus",
            "cards": [
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_meals_today",
                    "name": "Mahlzeiten heute",
                    "icon": "mdi:counter",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_last_feeding",
                    "name": "Letzte Fütterung",
                    "icon": "mdi:clock",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_next_feeding_time",
                    "name": "Nächste Fütterung",
                    "icon": "mdi:clock-alert",
                },
            ],
        })
        
        # Food management
        cards.append({
            "type": "entities",
            "title": "Futterverwaltung",
            "entities": [
                f"number.pawcontrol_{self.dog_id}_daily_food_amount",
                f"sensor.pawcontrol_{self.dog_id}_daily_food_consumed",
                f"select.pawcontrol_{self.dog_id}_food_type_select",
                f"sensor.pawcontrol_{self.dog_id}_water_level",
            ],
        })
        
        # Feeding buttons
        cards.append({
            "type": "horizontal-stack",
            "cards": [
                {
                    "type": "button",
                    "entity": f"button.pawcontrol_{self.dog_id}_feed_breakfast",
                    "name": "Frühstück",
                    "icon": "mdi:weather-sunset-up",
                },
                {
                    "type": "button",
                    "entity": f"button.pawcontrol_{self.dog_id}_feed_dinner",
                    "name": "Abendessen",
                    "icon": "mdi:weather-sunset-down",
                },
                {
                    "type": "button",
                    "entity": f"button.pawcontrol_{self.dog_id}_quick_feed",
                    "name": "Jetzt füttern",
                    "icon": "mdi:food",
                },
            ],
        })
        
        # Feeding history graph
        cards.append({
            "type": "history-graph",
            "title": "Fütterungsverlauf",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_meals_today",
                f"binary_sensor.pawcontrol_{self.dog_id}_is_hungry",
            ],
            "hours_to_show": 24,
        })
        
        return {
            "title": "Fütterung",
            "path": "feeding",
            "icon": "mdi:food-drumstick",
            "cards": cards,
        }

    def _create_walk_view(self) -> dict[str, Any]:
        """Create walk view."""
        cards = []
        
        # Walk status
        cards.append({
            "type": "vertical-stack",
            "title": "Spaziergang Status",
            "cards": [
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_walks_today",
                    "name": "Spaziergänge heute",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_walk_distance_today",
                    "name": "Distanz heute",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_last_walk",
                    "name": "Letzter Spaziergang",
                },
            ],
        })
        
        # Current walk (if active)
        cards.append({
            "type": "conditional",
            "conditions": [
                {
                    "entity": f"switch.pawcontrol_{self.dog_id}_walk_in_progress_switch",
                    "state": "on",
                },
            ],
            "card": {
                "type": "entities",
                "title": "Aktueller Spaziergang",
                "entities": [
                    f"sensor.pawcontrol_{self.dog_id}_current_walk_duration",
                    f"sensor.pawcontrol_{self.dog_id}_current_walk_distance",
                ],
            },
        })
        
        # Walk controls
        cards.append({
            "type": "entities",
            "title": "Spaziergang Kontrolle",
            "entities": [
                f"switch.pawcontrol_{self.dog_id}_walk_in_progress_switch",
                f"button.pawcontrol_{self.dog_id}_start_walk",
                f"select.pawcontrol_{self.dog_id}_preferred_walk_type_select",
                f"number.pawcontrol_{self.dog_id}_daily_walk_duration",
            ],
        })
        
        # Walk statistics
        cards.append({
            "type": "vertical-stack",
            "title": "Statistiken",
            "cards": [
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_total_walk_time_today",
                    "name": "Gesamtzeit heute",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_average_walk_duration",
                    "name": "Durchschnittsdauer",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_calories_burned_today",
                    "name": "Kalorien verbrannt",
                },
            ],
        })
        
        # Walk history
        cards.append({
            "type": "history-graph",
            "title": "Spaziergang Verlauf",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_walks_today",
                f"sensor.pawcontrol_{self.dog_id}_walk_distance_today",
            ],
            "hours_to_show": 168,  # 1 week
        })
        
        return {
            "title": "Spaziergänge",
            "path": "walks",
            "icon": "mdi:dog-service",
            "cards": cards,
        }

    def _create_health_view(self) -> dict[str, Any]:
        """Create health view."""
        cards = []
        
        # Health overview
        cards.append({
            "type": "entities",
            "title": "Gesundheitsstatus",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_health_score",
                f"select.pawcontrol_{self.dog_id}_health_status_select",
                f"select.pawcontrol_{self.dog_id}_mood_select",
                f"binary_sensor.pawcontrol_{self.dog_id}_health_alert",
            ],
        })
        
        # Vital signs
        cards.append({
            "type": "entities",
            "title": "Vitalwerte",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_weight",
                f"sensor.pawcontrol_{self.dog_id}_temperature",
                f"sensor.pawcontrol_{self.dog_id}_heart_rate",
                f"sensor.pawcontrol_{self.dog_id}_respiratory_rate",
            ],
        })
        
        # Weight tracking
        cards.append({
            "type": "vertical-stack",
            "title": "Gewichtsverlauf",
            "cards": [
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_weight",
                    "name": "Aktuelles Gewicht",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_weight_trend",
                    "name": "Gewichtstrend",
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.pawcontrol_{self.dog_id}_body_condition_score",
                    "name": "Body Condition Score",
                },
            ],
        })
        
        # Medical
        cards.append({
            "type": "entities",
            "title": "Medizinisch",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_last_vet_visit_sensor",
                f"sensor.pawcontrol_{self.dog_id}_days_since_vet",
                f"datetime.pawcontrol_{self.dog_id}_next_vet_appointment",
                f"sensor.pawcontrol_{self.dog_id}_medication_count",
                f"datetime.pawcontrol_{self.dog_id}_last_medication",
            ],
        })
        
        # Health notes
        cards.append({
            "type": "entities",
            "title": "Gesundheitsnotizen",
            "entities": [
                f"text.pawcontrol_{self.dog_id}_health_notes",
                f"text.pawcontrol_{self.dog_id}_symptoms",
                f"text.pawcontrol_{self.dog_id}_medication_notes",
                f"text.pawcontrol_{self.dog_id}_vet_contact",
            ],
        })
        
        # Health history graph
        cards.append({
            "type": "history-graph",
            "title": "Gesundheitsverlauf",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_weight",
                f"sensor.pawcontrol_{self.dog_id}_temperature",
                f"sensor.pawcontrol_{self.dog_id}_health_score",
            ],
            "hours_to_show": 720,  # 30 days
        })
        
        return {
            "title": "Gesundheit",
            "path": "health",
            "icon": "mdi:medical-bag",
            "cards": cards,
        }

    def _create_gps_view(self) -> dict[str, Any]:
        """Create GPS tracking view."""
        cards = []
        
        # Map card
        cards.append({
            "type": "map",
            "title": f"{self.dog_name} Standort",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_location",
            ],
            "default_zoom": 15,
        })
        
        # GPS status
        cards.append({
            "type": "entities",
            "title": "GPS Status",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_location",
                f"sensor.pawcontrol_{self.dog_id}_distance_from_home",
                f"sensor.pawcontrol_{self.dog_id}_gps_signal",
                f"sensor.pawcontrol_{self.dog_id}_gps_battery",
                f"binary_sensor.pawcontrol_{self.dog_id}_gps_tracking",
            ],
        })
        
        # Movement stats
        cards.append({
            "type": "entities",
            "title": "Bewegung",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_current_speed",
                f"sensor.pawcontrol_{self.dog_id}_max_speed_today",
                f"sensor.pawcontrol_{self.dog_id}_time_away_from_home",
                f"sensor.pawcontrol_{self.dog_id}_last_seen_location",
            ],
        })
        
        # GPS controls
        cards.append({
            "type": "entities",
            "title": "GPS Einstellungen",
            "entities": [
                f"button.pawcontrol_{self.dog_id}_update_gps",
                f"number.pawcontrol_{self.dog_id}_geofence_radius",
                f"number.pawcontrol_{self.dog_id}_gps_update_interval",
                f"switch.pawcontrol_{self.dog_id}_auto_walk_detection",
            ],
        })
        
        # Location history
        cards.append({
            "type": "history-graph",
            "title": "Standortverlauf",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_distance_from_home",
            ],
            "hours_to_show": 24,
        })
        
        return {
            "title": "GPS Tracking",
            "path": "gps",
            "icon": "mdi:map-marker",
            "cards": cards,
        }

    def _create_training_view(self) -> dict[str, Any]:
        """Create training view."""
        cards = []
        
        # Training overview
        cards.append({
            "type": "entities",
            "title": "Training Übersicht",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_training_sessions_today",
                f"sensor.pawcontrol_{self.dog_id}_training_sessions_week",
                f"sensor.pawcontrol_{self.dog_id}_last_training_sensor",
                f"sensor.pawcontrol_{self.dog_id}_training_streak",
            ],
        })
        
        # Training progress
        cards.append({
            "type": "entities",
            "title": "Fortschritt",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_commands_learned",
                f"sensor.pawcontrol_{self.dog_id}_training_success_rate",
                f"text.pawcontrol_{self.dog_id}_learned_commands",
            ],
        })
        
        # Training controls
        cards.append({
            "type": "entities",
            "title": "Training Kontrolle",
            "entities": [
                f"switch.pawcontrol_{self.dog_id}_training_session",
                f"datetime.pawcontrol_{self.dog_id}_last_training",
                f"datetime.pawcontrol_{self.dog_id}_next_training",
            ],
        })
        
        return {
            "title": "Training",
            "path": "training",
            "icon": "mdi:whistle",
            "cards": cards,
        }

    def _create_statistics_view(self) -> dict[str, Any]:
        """Create statistics view."""
        cards = []
        
        # Overview stats
        cards.append({
            "type": "statistics-graph",
            "title": "Gesundheitsscore Verlauf",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_health_score",
            ],
            "stat_types": ["mean", "min", "max"],
            "days_to_show": 30,
        })
        
        cards.append({
            "type": "statistics-graph",
            "title": "Aktivitätsscore Verlauf",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_activity_score",
            ],
            "stat_types": ["mean", "min", "max"],
            "days_to_show": 30,
        })
        
        # Activity statistics
        cards.append({
            "type": "statistics-graph",
            "title": "Tägliche Aktivitäten",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_walks_today",
                f"sensor.pawcontrol_{self.dog_id}_meals_today",
            ],
            "stat_types": ["sum"],
            "days_to_show": 7,
        })
        
        # Distance statistics
        cards.append({
            "type": "statistics-graph",
            "title": "Spaziergang-Distanz",
            "entities": [
                f"sensor.pawcontrol_{self.dog_id}_walk_distance_today",
            ],
            "stat_types": ["sum", "mean"],
            "days_to_show": 30,
        })
        
        return {
            "title": "Statistiken",
            "path": "statistics",
            "icon": "mdi:chart-line",
            "cards": cards,
        }


async def async_create_dashboard(
    hass: HomeAssistant,
    dog_name: str,
    modules: dict[str, Any],
) -> bool:
    """Create dashboard for a dog."""
    try:
        creator = DashboardCreator(hass, dog_name, modules)
        dashboard_config = await creator.async_create_dashboard()
        
        # Here you would integrate with Lovelace to actually create the dashboard
        # This is a simplified version - actual implementation would use
        # hass.data["lovelace"]["dashboards"] or similar
        
        _LOGGER.info(f"Dashboard configuration created for {dog_name}")
        
        # Store dashboard config for reference
        if DOMAIN not in hass.data:
            hass.data[DOMAIN] = {}
        
        if "dashboards" not in hass.data[DOMAIN]:
            hass.data[DOMAIN]["dashboards"] = {}
        
        hass.data[DOMAIN]["dashboards"][dog_name] = dashboard_config
        
        return True
        
    except Exception as err:
        _LOGGER.error(f"Failed to create dashboard for {dog_name}: {err}")
        return False


async def async_remove_dashboard(hass: HomeAssistant, dog_name: str) -> bool:
    """Remove dashboard for a dog."""
    try:
        if DOMAIN in hass.data and "dashboards" in hass.data[DOMAIN]:
            if dog_name in hass.data[DOMAIN]["dashboards"]:
                del hass.data[DOMAIN]["dashboards"][dog_name]
                _LOGGER.info(f"Dashboard removed for {dog_name}")
                return True
        
        return False
        
    except Exception as err:
        _LOGGER.error(f"Failed to remove dashboard for {dog_name}: {err}")
        return False
