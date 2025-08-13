"""Dashboard generator for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
    MODULE_WALK,
)

_LOGGER = logging.getLogger(__name__)


class DashboardGenerator:
    """Generate dashboard configuration for Paw Control."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize dashboard generator."""
        self.hass = hass
        self.entry = entry
        self._entity_registry = er.async_get(hass)

    def generate_dashboard_config(self) -> Dict[str, Any]:
        """Generate complete dashboard configuration."""
        dogs = self.entry.options.get(CONF_DOGS, [])

        if not dogs:
            return self._generate_empty_dashboard()

        cards = []

        # Add header
        cards.append(self._generate_header_card())

        # Add system status
        cards.append(self._generate_system_status_card())

        # Add cards for each dog
        for dog in dogs:
            dog_cards = self._generate_dog_cards(dog)
            cards.extend(dog_cards)

        # Add footer with actions
        cards.append(self._generate_footer_card())

        return {
            "title": "Paw Control",
            "icon": "mdi:dog",
            "path": "pawcontrol",
            "type": "panel",
            "cards": [{"type": "vertical-stack", "cards": cards}],
        }

    def _generate_empty_dashboard(self) -> Dict[str, Any]:
        """Generate dashboard when no dogs are configured."""
        return {
            "title": "Paw Control",
            "icon": "mdi:dog",
            "path": "pawcontrol",
            "cards": [
                {
                    "type": "markdown",
                    "content": "# 🐾 Paw Control\n\nNo dogs configured yet.\n\nGo to Settings → Devices & Services → Paw Control to configure your dogs.",
                }
            ],
        }

    def _generate_header_card(self) -> Dict[str, Any]:
        """Generate header card."""
        return {
            "type": "custom:mushroom-title-card",
            "title": "🐾 Paw Control",
            "subtitle": "Smart Dog Management System",
        }

    def _generate_system_status_card(self) -> Dict[str, Any]:
        """Generate system status card."""
        return {
            "type": "horizontal-stack",
            "cards": [
                {
                    "type": "custom:mushroom-chips-card",
                    "chips": [
                        {
                            "type": "entity",
                            "entity": f"binary_sensor.{DOMAIN}_global_visitor_mode",
                            "icon": "mdi:account-group",
                            "content_info": "name",
                        },
                        {
                            "type": "entity",
                            "entity": f"binary_sensor.{DOMAIN}_global_emergency_mode",
                            "icon": "mdi:alert-circle",
                            "content_info": "name",
                        },
                        {
                            "type": "action",
                            "icon": "mdi:sync",
                            "tap_action": {
                                "action": "call-service",
                                "service": f"{DOMAIN}.sync_setup",
                            },
                        },
                        {
                            "type": "action",
                            "icon": "mdi:file-document",
                            "tap_action": {
                                "action": "call-service",
                                "service": f"{DOMAIN}.generate_report",
                                "service_data": {
                                    "scope": "daily",
                                    "target": "notification",
                                    "format": "text",
                                },
                            },
                        },
                    ],
                }
            ],
        }

    def _generate_dog_cards(self, dog: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate cards for a specific dog."""
        dog_id = dog.get(CONF_DOG_ID)
        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})
        cards = []

        # Main dog status card
        cards.append(self._generate_dog_status_card(dog_id, dog_name))

        # Quick actions
        cards.append(self._generate_quick_actions_card(dog_id, dog_name, modules))

        # Statistics
        if modules.get(MODULE_WALK) or modules.get(MODULE_FEEDING):
            cards.append(self._generate_statistics_card(dog_id, modules))

        # Feeding status
        if modules.get(MODULE_FEEDING):
            cards.append(self._generate_feeding_card(dog_id))

        # Health status
        if modules.get(MODULE_HEALTH) or modules.get(MODULE_GROOMING):
            cards.append(self._generate_health_card(dog_id, modules))

        # Training status
        if modules.get(MODULE_TRAINING):
            cards.append(self._generate_training_card(dog_id))

        return cards

    def _generate_dog_status_card(self, dog_id: str, dog_name: str) -> Dict[str, Any]:
        """Generate main status card for a dog."""
        return {
            "type": "custom:mushroom-template-card",
            "primary": f"🐕 {dog_name}",
            "secondary": """
                {{% set activity = states('sensor.{0}_{1}_activity_level') %}}
                {{% if is_state('binary_sensor.{0}_{1}_walk_in_progress', 'on') %}}
                  🚶 Walking Now
                {{% elif is_state('binary_sensor.{0}_{1}_needs_walk', 'on') %}}
                  ⚠️ Needs walk
                {{% elif is_state('binary_sensor.{0}_{1}_is_hungry', 'on') %}}
                  🍽️ Hungry
                {{% else %}}
                  ✅ {{{{ activity | title }}}} activity
                {{% endif %}}
            """.format(DOMAIN, dog_id).strip(),
            "icon": "mdi:dog-side",
            "icon_color": """
                {{% if is_state('binary_sensor.{0}_{1}_walk_in_progress', 'on') %}}
                  green
                {{% elif is_state('binary_sensor.{0}_{1}_needs_walk', 'on') %}}
                  orange
                {{% else %}}
                  blue
                {{% endif %}}
            """.format(DOMAIN, dog_id).strip(),
            "tap_action": {"action": "more-info"},
        }

    def _generate_quick_actions_card(
        self, dog_id: str, dog_name: str, modules: Dict
    ) -> Dict[str, Any]:
        """Generate quick actions card."""
        cards = []

        if modules.get(MODULE_WALK):
            cards.append(
                {
                    "type": "custom:mushroom-template-card",
                    "primary": "Walk",
                    "secondary": """
                    {{% if is_state('binary_sensor.{0}_{1}_walk_in_progress', 'on') %}}
                      In Progress
                    {{% else %}}
                      Start Walk
                    {{% endif %}}
                """.format(DOMAIN, dog_id).strip(),
                    "icon": "mdi:walk",
                    "icon_color": """
                    {{% if is_state('binary_sensor.{0}_{1}_walk_in_progress', 'on') %}}
                      green
                    {{% else %}}
                      grey
                    {{% endif %}}
                """.format(DOMAIN, dog_id).strip(),
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.start_walk",
                        "service_data": {"dog_id": dog_id, "source": "manual"},
                    },
                }
            )

        if modules.get(MODULE_FEEDING):
            cards.append(
                {
                    "type": "custom:mushroom-template-card",
                    "primary": "Feed",
                    "secondary": """
                    {{% if is_state('binary_sensor.{0}_{1}_is_hungry', 'on') %}}
                      Hungry!
                    {{% else %}}
                      Quick Feed
                    {{% endif %}}
                """.format(DOMAIN, dog_id).strip(),
                    "icon": "mdi:food",
                    "icon_color": """
                    {{% if is_state('binary_sensor.{0}_{1}_is_hungry', 'on') %}}
                      orange
                    {{% else %}}
                      grey
                    {{% endif %}}
                """.format(DOMAIN, dog_id).strip(),
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.feed_dog",
                        "service_data": {
                            "dog_id": dog_id,
                            "meal_type": "snack",
                            "portion_g": 100,
                            "food_type": "dry",
                        },
                    },
                }
            )

        return (
            {"type": "horizontal-stack", "cards": cards}
            if cards
            else {"type": "markdown", "content": ""}
        )

    def _generate_statistics_card(self, dog_id: str, modules: Dict) -> Dict[str, Any]:
        """Generate statistics card."""
        cards = []

        if modules.get(MODULE_WALK):
            cards.extend(
                [
                    {
                        "type": "custom:mushroom-entity-card",
                        "entity": f"sensor.{DOMAIN}_{dog_id}_walks_today",
                        "name": "Walks Today",
                        "icon": "mdi:counter",
                    },
                    {
                        "type": "custom:mushroom-entity-card",
                        "entity": f"sensor.{DOMAIN}_{dog_id}_total_distance_today",
                        "name": "Distance",
                        "icon": "mdi:map-marker-distance",
                    },
                    {
                        "type": "custom:mushroom-entity-card",
                        "entity": f"sensor.{DOMAIN}_{dog_id}_calories_burned_today",
                        "name": "Calories",
                        "icon": "mdi:fire",
                    },
                ]
            )

        return (
            {"type": "grid", "columns": 3, "cards": cards}
            if cards
            else {"type": "markdown", "content": ""}
        )

    def _generate_feeding_card(self, dog_id: str) -> Dict[str, Any]:
        """Generate feeding status card."""
        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "custom:mushroom-title-card",
                    "title": "🍽️ Feeding",
                    "subtitle": "Today's Meals",
                },
                {
                    "type": "grid",
                    "columns": 4,
                    "cards": [
                        self._generate_meal_card(dog_id, "breakfast", "mdi:food-apple"),
                        self._generate_meal_card(dog_id, "lunch", "mdi:food"),
                        self._generate_meal_card(dog_id, "dinner", "mdi:food-variant"),
                        self._generate_meal_card(dog_id, "snack", "mdi:cookie"),
                    ],
                },
            ],
        }

    def _generate_meal_card(
        self, dog_id: str, meal_type: str, icon: str
    ) -> Dict[str, Any]:
        """Generate individual meal card."""
        return {
            "type": "custom:mushroom-template-card",
            "primary": meal_type.capitalize(),
            "secondary": f"{{{{ states('sensor.{DOMAIN}_{dog_id}_feeding_{meal_type}') }}}}x",
            "icon": icon,
            "icon_color": f"""
                {{% if states('sensor.{DOMAIN}_{dog_id}_feeding_{meal_type}') | int > 0 %}}
                  green
                {{% else %}}
                  grey
                {{% endif %}}
            """.strip(),
            "tap_action": {
                "action": "call-service",
                "service": f"{DOMAIN}.feed_dog",
                "service_data": {
                    "dog_id": dog_id,
                    "meal_type": meal_type,
                    "portion_g": 200 if meal_type != "snack" else 50,
                    "food_type": "dry",
                },
            },
        }

    def _generate_health_card(self, dog_id: str, modules: Dict) -> Dict[str, Any]:
        """Generate health status card."""
        cards = []

        if modules.get(MODULE_HEALTH):
            cards.append(
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"sensor.{DOMAIN}_{dog_id}_weight",
                    "name": "Weight",
                    "icon": "mdi:weight",
                }
            )

        if modules.get(MODULE_GROOMING):
            cards.append(
                {
                    "type": "custom:mushroom-template-card",
                    "primary": "Grooming",
                    "secondary": """
                    {{% set days = states('sensor.{0}_{1}_days_since_grooming') | int %}}
                    {{% if days == 0 %}}
                      Today
                    {{% elif days == 1 %}}
                      Yesterday
                    {{% else %}}
                      {{{{ days }}}} days ago
                    {{% endif %}}
                """.format(DOMAIN, dog_id).strip(),
                    "icon": "mdi:content-cut",
                    "icon_color": """
                    {{% if is_state('binary_sensor.{0}_{1}_needs_grooming', 'on') %}}
                      orange
                    {{% else %}}
                      green
                    {{% endif %}}
                """.format(DOMAIN, dog_id).strip(),
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.start_grooming_session",
                        "service_data": {
                            "dog_id": dog_id,
                            "type": "brush",
                            "notes": "Regular grooming",
                        },
                    },
                }
            )

        return (
            {
                "type": "vertical-stack",
                "cards": [
                    {
                        "type": "custom:mushroom-title-card",
                        "title": "🏥 Health & Care",
                        "subtitle": "Medical and Grooming Status",
                    },
                    {"type": "horizontal-stack", "cards": cards},
                ],
            }
            if cards
            else {"type": "markdown", "content": ""}
        )

    def _generate_training_card(self, dog_id: str) -> Dict[str, Any]:
        """Generate training status card."""
        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "custom:mushroom-title-card",
                    "title": "🎓 Training",
                    "subtitle": "Progress and Sessions",
                },
                {
                    "type": "horizontal-stack",
                    "cards": [
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": f"sensor.{DOMAIN}_{dog_id}_training_sessions_today",
                            "name": "Sessions Today",
                            "icon": "mdi:school",
                        },
                        {
                            "type": "button",
                            "entity": f"button.{DOMAIN}_{dog_id}_start_training",
                            "name": "Start Training",
                            "icon": "mdi:play",
                            "tap_action": {
                                "action": "call-service",
                                "service": f"{DOMAIN}.start_training_session",
                                "service_data": {
                                    "dog_id": dog_id,
                                    "topic": "Basic Commands",
                                    "duration_min": 15,
                                    "notes": "Practice session",
                                },
                            },
                        },
                    ],
                },
            ],
        }

    def _generate_footer_card(self) -> Dict[str, Any]:
        """Generate footer card with global actions."""
        return {
            "type": "horizontal-stack",
            "cards": [
                {
                    "type": "button",
                    "name": "Daily Reset",
                    "icon": "mdi:restart",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.daily_reset",
                    },
                },
                {
                    "type": "button",
                    "name": "Generate Report",
                    "icon": "mdi:file-document",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.generate_report",
                        "service_data": {
                            "scope": "daily",
                            "target": "notification",
                            "format": "text",
                        },
                    },
                },
            ],
        }

    async def apply_dashboard(self) -> bool:
        """Apply the generated dashboard to Lovelace."""
        try:
            dashboard_config = self.generate_dashboard_config()

            # This would require accessing the Lovelace storage
            # For now, we'll just log the intent
            _LOGGER.info("Generated dashboard configuration for Paw Control")

            # Store dashboard config for manual application
            self.hass.data[DOMAIN][self.entry.entry_id]["dashboard_config"] = (
                dashboard_config
            )

            return True

        except Exception as err:
            _LOGGER.error(f"Failed to generate dashboard: {err}")
            return False
