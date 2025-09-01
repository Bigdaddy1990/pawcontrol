"""Specialized card generators for Paw Control dashboards.

This module provides high-performance, specialized card generators for different
dashboard components. Each generator is optimized for its specific use case
with lazy loading, validation, and async operations.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .dashboard_templates import DashboardTemplates

_LOGGER = logging.getLogger(__name__)


class BaseCardGenerator:
    """Base class for card generators with common functionality."""

    def __init__(self, hass: HomeAssistant, templates: DashboardTemplates) -> None:
        """Initialize card generator.

        Args:
            hass: Home Assistant instance
            templates: Template manager
        """
        self.hass = hass
        self.templates = templates

    async def _validate_entities(self, entities: list[str]) -> list[str]:
        """Validate and filter entities that exist and are available.

        Args:
            entities: List of entity IDs to validate

        Returns:
            List of valid entity IDs
        """
        valid_entities = []

        for entity_id in entities:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                valid_entities.append(entity_id)
            else:
                _LOGGER.debug("Entity %s not available, skipping", entity_id)

        return valid_entities

    async def _entity_exists(self, entity_id: str) -> bool:
        """Check if entity exists and is available.

        Args:
            entity_id: Entity ID to check

        Returns:
            True if entity exists and is available
        """
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in (
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        )


class OverviewCardGenerator(BaseCardGenerator):
    """Generator for overview dashboard cards."""

    async def generate_welcome_card(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate welcome/summary card.

        Args:
            dogs_config: List of dog configurations
            options: Dashboard options

        Returns:
            Welcome card configuration
        """
        dog_count = len(dogs_config)
        title = options.get("title", "Paw Control")

        # Generate dynamic content based on current status
        content_parts = [
            f"# {title}",
            f"Managing **{dog_count}** {'dog' if dog_count == 1 else 'dogs'} with Paw Control",
        ]

        # Add quick stats if available
        if dog_count > 0:
            active_dogs = await self._count_active_dogs(dogs_config)
            if active_dogs != dog_count:
                content_parts.append(f"**{active_dogs}** currently active")

        content_parts.extend(
            [
                "",
                "Last updated: {{ now().strftime('%H:%M') }}",
            ]
        )

        return {
            "type": "markdown",
            "content": "\n".join(content_parts),
        }

    async def _count_active_dogs(self, dogs_config: list[dict[str, Any]]) -> int:
        """Count dogs that are currently active/available.

        Args:
            dogs_config: List of dog configurations

        Returns:
            Number of active dogs
        """
        active_count = 0

        for dog in dogs_config:
            dog_id = dog.get(CONF_DOG_ID)
            if dog_id and await self._entity_exists(f"sensor.{dog_id}_status"):
                active_count += 1

        return active_count

    async def generate_dogs_grid(
        self, dogs_config: list[dict[str, Any]], dashboard_url: str
    ) -> dict[str, Any] | None:
        """Generate grid of dog navigation buttons.

        Args:
            dogs_config: List of dog configurations
            dashboard_url: Base dashboard URL for navigation

        Returns:
            Dog grid card or None if no valid dogs
        """
        dog_cards = []

        for dog in dogs_config:
            dog_id = dog.get(CONF_DOG_ID)
            dog_name = dog.get(CONF_DOG_NAME)

            if not dog_id or not dog_name:
                continue

            # Only add if dog's status sensor exists
            if not await self._entity_exists(f"sensor.{dog_id}_status"):
                continue

            dog_cards.append(
                {
                    "type": "button",
                    "entity": f"sensor.{dog_id}_status",
                    "name": dog_name,
                    "icon": "mdi:dog",
                    "show_state": True,
                    "tap_action": {
                        "action": "navigate",
                        "navigation_path": f"{dashboard_url}/{slugify(dog_id)}",
                    },
                }
            )

        if not dog_cards:
            return None

        # Optimize grid columns based on number of dogs
        columns = min(3, max(1, len(dog_cards)))

        return {
            "type": "grid",
            "columns": columns,
            "cards": dog_cards,
        }

    async def generate_quick_actions(
        self, dogs_config: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Generate quick action buttons.

        Args:
            dogs_config: List of dog configurations

        Returns:
            Quick actions card or None if no actions available
        """
        actions = []

        # Check which modules are enabled across all dogs
        has_feeding = any(
            dog.get("modules", {}).get(MODULE_FEEDING) for dog in dogs_config
        )
        has_walking = any(
            dog.get("modules", {}).get(MODULE_WALK) for dog in dogs_config
        )

        # Feed all button
        if has_feeding and await self._entity_exists(f"button.{DOMAIN}_feed_all_dogs"):
            actions.append(
                {
                    "type": "button",
                    "name": "Feed All",
                    "icon": "mdi:food-drumstick",
                    "tap_action": {
                        "action": "more-info",
                        "entity": f"button.{DOMAIN}_feed_all_dogs",
                    },
                }
            )

        # Walk status button
        if has_walking and await self._entity_exists(f"sensor.{DOMAIN}_dogs_walking"):
            actions.append(
                {
                    "type": "button",
                    "name": "Walk Status",
                    "icon": "mdi:walk",
                    "tap_action": {
                        "action": "more-info",
                        "entity": f"sensor.{DOMAIN}_dogs_walking",
                    },
                }
            )

        # Daily reset button (always available)
        actions.append(
            {
                "type": "button",
                "name": "Daily Reset",
                "icon": "mdi:refresh",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.daily_reset",
                },
            }
        )

        if not actions:
            return None

        return {
            "type": "horizontal-stack",
            "cards": actions,
        }


class DogCardGenerator(BaseCardGenerator):
    """Generator for individual dog dashboard cards."""

    async def generate_dog_overview_cards(
        self, dog_config: dict[str, Any], theme: dict[str, str], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate overview cards for a specific dog.

        Args:
            dog_config: Dog configuration
            theme: Theme colors
            options: Display options

        Returns:
            List of overview cards
        """
        cards = []
        dog_id = dog_config[CONF_DOG_ID]
        dog_name = dog_config[CONF_DOG_NAME]
        modules = dog_config.get("modules", {})

        # Dog header card with picture
        header_card = await self._generate_dog_header_card(dog_config, options)
        if header_card:
            cards.append(header_card)

        # Status card with key metrics
        status_card = await self.templates.get_dog_status_card_template(
            dog_id, dog_name, modules
        )
        cards.append(status_card)

        # Action buttons
        action_buttons = await self.templates.get_action_buttons_template(
            dog_id, modules
        )
        if action_buttons:
            # Group regular and conditional buttons appropriately
            regular_buttons = [
                b for b in action_buttons if b.get("type") != "conditional"
            ]
            conditional_cards = [
                b for b in action_buttons if b.get("type") == "conditional"
            ]

            # Add regular buttons as horizontal stack
            if regular_buttons:
                cards.append(
                    {
                        "type": "horizontal-stack",
                        "cards": regular_buttons,
                    }
                )

            # Add conditional cards individually
            cards.extend(conditional_cards)

        # GPS map if enabled and available
        if modules.get(MODULE_GPS):
            map_card = await self._generate_gps_map_card(dog_id, options)
            if map_card:
                cards.append(map_card)

        # Activity graph
        activity_card = await self._generate_activity_graph_card(dog_config, options)
        if activity_card:
            cards.append(activity_card)

        return cards

    async def _generate_dog_header_card(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Generate dog header card with picture.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            Header card or None if not applicable
        """
        dog_id = dog_config[CONF_DOG_ID]
        dog_name = dog_config[CONF_DOG_NAME]

        # Check if status sensor exists
        if not await self._entity_exists(f"sensor.{dog_id}_status"):
            return None

        # Use custom image if provided, otherwise default
        dog_image = dog_config.get("dog_image", f"/local/paw_control/{dog_id}.jpg")

        return {
            "type": "picture-entity",
            "entity": f"sensor.{dog_id}_status",
            "name": dog_name,
            "image": dog_image,
            "show_state": True,
            "show_name": True,
            "aspect_ratio": "16:9",
        }

    async def _generate_gps_map_card(
        self, dog_id: str, options: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Generate GPS map card for dog.

        Args:
            dog_id: Dog identifier
            options: Display options

        Returns:
            Map card or None if GPS not available
        """
        tracker_entity = f"device_tracker.{dog_id}_location"

        if not await self._entity_exists(tracker_entity):
            return None

        return await self.templates.get_map_card_template(dog_id, options)

    async def _generate_activity_graph_card(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Generate activity graph card.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            Activity graph card or None if no data
        """
        if not options.get("show_activity_graph", True):
            return None

        dog_id = dog_config[CONF_DOG_ID]
        modules = dog_config.get("modules", {})

        # Collect activity-related entities
        activity_entities = [f"sensor.{dog_id}_activity_level"]

        if modules.get(MODULE_WALK):
            activity_entities.append(f"binary_sensor.{dog_id}_is_walking")

        # Filter to only existing entities
        valid_entities = await self._validate_entities(activity_entities)

        if not valid_entities:
            return None

        return await self.templates.get_history_graph_template(
            valid_entities, "24h Activity", 24
        )


class ModuleCardGenerator(BaseCardGenerator):
    """Generator for module-specific dashboard cards."""

    async def generate_feeding_cards(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate feeding module cards.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            List of feeding cards
        """
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # Feeding schedule status
        schedule_entities = [
            f"sensor.{dog_id}_next_meal_time",
            f"sensor.{dog_id}_meals_today",
            f"sensor.{dog_id}_calories_today",
            f"sensor.{dog_id}_last_fed",
        ]

        valid_entities = await self._validate_entities(schedule_entities)
        if valid_entities:
            cards.append(
                {
                    "type": "entities",
                    "title": "Feeding Schedule",
                    "entities": valid_entities,
                    "state_color": True,
                }
            )

        # Feeding controls
        feeding_controls = await self.templates.get_feeding_controls_template(dog_id)
        cards.append(feeding_controls)

        # Feeding history graph
        history_entities = [
            f"sensor.{dog_id}_meals_today",
            f"sensor.{dog_id}_calories_today",
        ]

        history_card = await self.templates.get_history_graph_template(
            history_entities, "Feeding History (7 days)", 168
        )
        if history_card.get("entities"):  # Only add if has valid entities
            cards.append(history_card)

        return cards

    async def generate_walk_cards(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate walk module cards.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            List of walk cards
        """
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # Walk status
        status_entities = [
            f"binary_sensor.{dog_id}_is_walking",
            f"sensor.{dog_id}_current_walk_duration",
            f"sensor.{dog_id}_walks_today",
            f"sensor.{dog_id}_walk_distance_today",
            f"sensor.{dog_id}_last_walk_time",
        ]

        valid_entities = await self._validate_entities(status_entities)
        if valid_entities:
            cards.append(
                {
                    "type": "entities",
                    "title": "Walk Status",
                    "entities": valid_entities,
                    "state_color": True,
                }
            )

        # Walk control buttons (conditional based on walking state)
        if await self._entity_exists(f"binary_sensor.{dog_id}_is_walking"):
            cards.extend(
                [
                    {
                        "type": "conditional",
                        "conditions": [
                            {
                                "entity": f"binary_sensor.{dog_id}_is_walking",
                                "state": "off",
                            }
                        ],
                        "card": {
                            "type": "button",
                            "name": "Start Walk",
                            "icon": "mdi:walk",
                            "icon_height": "60px",
                            "tap_action": {
                                "action": "call-service",
                                "service": f"{DOMAIN}.start_walk",
                                "service_data": {"dog_id": dog_id},
                            },
                        },
                    },
                    {
                        "type": "conditional",
                        "conditions": [
                            {
                                "entity": f"binary_sensor.{dog_id}_is_walking",
                                "state": "on",
                            }
                        ],
                        "card": {
                            "type": "button",
                            "name": "End Walk",
                            "icon": "mdi:stop",
                            "icon_height": "60px",
                            "tap_action": {
                                "action": "call-service",
                                "service": f"{DOMAIN}.end_walk",
                                "service_data": {"dog_id": dog_id},
                            },
                        },
                    },
                ]
            )

        # Walk history graph
        history_entities = [
            f"sensor.{dog_id}_walks_today",
            f"sensor.{dog_id}_walk_distance_today",
        ]

        history_card = await self.templates.get_history_graph_template(
            history_entities, "Walk History (7 days)", 168
        )
        if history_card.get("entities"):
            cards.append(history_card)

        return cards

    async def generate_health_cards(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate health module cards.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            List of health cards
        """
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # Health metrics
        metrics_entities = [
            f"sensor.{dog_id}_health_status",
            f"sensor.{dog_id}_weight",
            f"sensor.{dog_id}_temperature",
            f"sensor.{dog_id}_mood",
            f"sensor.{dog_id}_energy_level",
        ]

        valid_entities = await self._validate_entities(metrics_entities)
        if valid_entities:
            cards.append(
                {
                    "type": "entities",
                    "title": "Health Metrics",
                    "entities": valid_entities,
                    "state_color": True,
                }
            )

        # Health management buttons
        health_buttons = [
            {
                "type": "button",
                "name": "Log Health",
                "icon": "mdi:heart-pulse",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.log_health",
                    "service_data": {"dog_id": dog_id},
                },
            },
            {
                "type": "button",
                "name": "Log Medication",
                "icon": "mdi:pill",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.log_medication",
                    "service_data": {
                        "dog_id": dog_id,
                        "medication_name": "Daily Supplement",
                        "dosage": "1 tablet",
                    },
                },
            },
        ]

        cards.append(
            {
                "type": "horizontal-stack",
                "cards": health_buttons,
            }
        )

        # Weight tracking graph
        weight_entity = f"sensor.{dog_id}_weight"
        if await self._entity_exists(weight_entity):
            weight_card = await self.templates.get_history_graph_template(
                [weight_entity], "Weight Tracking (30 days)", 720
            )
            cards.append(weight_card)

        # Important health dates
        date_entities = [
            f"date.{dog_id}_next_vet_visit",
            f"date.{dog_id}_next_vaccination",
            f"date.{dog_id}_next_grooming",
        ]

        valid_dates = await self._validate_entities(date_entities)
        if valid_dates:
            cards.append(
                {
                    "type": "entities",
                    "title": "Health Schedule",
                    "entities": valid_dates,
                }
            )

        return cards

    async def generate_gps_cards(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate GPS module cards.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            List of GPS cards
        """
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # Check if GPS tracker exists
        tracker_entity = f"device_tracker.{dog_id}_location"
        if not await self._entity_exists(tracker_entity):
            return cards

        # Main GPS map
        map_card = await self.templates.get_map_card_template(dog_id, options)
        cards.append(map_card)

        # GPS status and metrics
        gps_entities = [
            tracker_entity,
            f"sensor.{dog_id}_gps_accuracy",
            f"sensor.{dog_id}_distance_from_home",
            f"sensor.{dog_id}_speed",
            f"sensor.{dog_id}_battery_level",
        ]

        valid_entities = await self._validate_entities(gps_entities)
        if valid_entities:
            cards.append(
                {
                    "type": "entities",
                    "title": "GPS Status",
                    "entities": valid_entities,
                    "state_color": True,
                }
            )

        # Geofence status
        geofence_entities = [
            f"binary_sensor.{dog_id}_at_home",
            f"binary_sensor.{dog_id}_at_park",
            f"binary_sensor.{dog_id}_in_safe_zone",
            f"switch.{dog_id}_gps_tracking_enabled",
        ]

        valid_geofence = await self._validate_entities(geofence_entities)
        if valid_geofence:
            cards.append(
                {
                    "type": "entities",
                    "title": "Geofence & Safety",
                    "entities": valid_geofence,
                }
            )

        # Location history graph
        history_entities = [
            f"sensor.{dog_id}_distance_from_home",
            f"sensor.{dog_id}_speed",
        ]

        history_card = await self.templates.get_history_graph_template(
            history_entities, "Location History", 24
        )
        if history_card.get("entities"):
            cards.append(history_card)

        return cards


class StatisticsCardGenerator(BaseCardGenerator):
    """Generator for statistics dashboard cards."""

    async def generate_statistics_cards(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate statistics cards for all dogs.

        Args:
            dogs_config: List of dog configurations
            options: Display options

        Returns:
            List of statistics cards
        """
        cards = []

        # Overall activity statistics
        activity_card = await self._generate_activity_statistics(dogs_config)
        if activity_card:
            cards.append(activity_card)

        # Feeding statistics
        feeding_card = await self._generate_feeding_statistics(dogs_config)
        if feeding_card:
            cards.append(feeding_card)

        # Walk statistics
        walk_card = await self._generate_walk_statistics(dogs_config)
        if walk_card:
            cards.append(walk_card)

        # Health trends
        health_card = await self._generate_health_statistics(dogs_config)
        if health_card:
            cards.append(health_card)

        # Summary card
        summary_card = self._generate_summary_card(dogs_config)
        cards.append(summary_card)

        return cards

    async def _generate_activity_statistics(
        self, dogs_config: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Generate activity statistics card."""
        activity_entities = []

        for dog in dogs_config:
            dog_id = dog.get(CONF_DOG_ID)
            if dog_id:
                entity_id = f"sensor.{dog_id}_activity_level"
                if await self._entity_exists(entity_id):
                    activity_entities.append(entity_id)

        if not activity_entities:
            return None

        return {
            "type": "statistics-graph",
            "title": "Activity Statistics (30 days)",
            "entities": activity_entities,
            "stat_types": ["mean", "min", "max"],
            "days_to_show": 30,
        }

    async def _generate_feeding_statistics(
        self, dogs_config: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Generate feeding statistics card."""
        feeding_entities = []

        for dog in dogs_config:
            dog_id = dog.get(CONF_DOG_ID)
            if dog_id and dog.get("modules", {}).get(MODULE_FEEDING):
                entity_id = f"sensor.{dog_id}_meals_today"
                if await self._entity_exists(entity_id):
                    feeding_entities.append(entity_id)

        if not feeding_entities:
            return None

        return {
            "type": "statistics-graph",
            "title": "Feeding Statistics (30 days)",
            "entities": feeding_entities,
            "stat_types": ["sum", "mean"],
            "days_to_show": 30,
        }

    async def _generate_walk_statistics(
        self, dogs_config: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Generate walk statistics card."""
        walk_entities = []

        for dog in dogs_config:
            dog_id = dog.get(CONF_DOG_ID)
            if dog_id and dog.get("modules", {}).get(MODULE_WALK):
                entity_id = f"sensor.{dog_id}_walk_distance_today"
                if await self._entity_exists(entity_id):
                    walk_entities.append(entity_id)

        if not walk_entities:
            return None

        return {
            "type": "statistics-graph",
            "title": "Walk Statistics (30 days)",
            "entities": walk_entities,
            "stat_types": ["sum", "mean", "max"],
            "days_to_show": 30,
        }

    async def _generate_health_statistics(
        self, dogs_config: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Generate health statistics card."""
        weight_entities = []

        for dog in dogs_config:
            dog_id = dog.get(CONF_DOG_ID)
            if dog_id and dog.get("modules", {}).get(MODULE_HEALTH):
                entity_id = f"sensor.{dog_id}_weight"
                if await self._entity_exists(entity_id):
                    weight_entities.append(entity_id)

        if not weight_entities:
            return None

        return {
            "type": "statistics-graph",
            "title": "Weight Trends (60 days)",
            "entities": weight_entities,
            "stat_types": ["mean", "min", "max"],
            "days_to_show": 60,
        }

    def _generate_summary_card(
        self, dogs_config: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Generate statistics summary card."""
        module_counts = {
            MODULE_FEEDING: 0,
            MODULE_WALK: 0,
            MODULE_HEALTH: 0,
            MODULE_GPS: 0,
        }

        for dog in dogs_config:
            modules = dog.get("modules", {})
            for module_name in module_counts:
                if modules.get(module_name):
                    module_counts[module_name] += 1

        content = [
            "## Paw Control Statistics",
            "",
            f"**Dogs managed:** {len(dogs_config)}",
            "",
            "**Active modules:**",
            f"- Feeding: {module_counts[MODULE_FEEDING]}",
            f"- Walks: {module_counts[MODULE_WALK]}",
            f"- Health: {module_counts[MODULE_HEALTH]}",
            f"- GPS: {module_counts[MODULE_GPS]}",
            "",
            "*Last updated: {{ now().strftime('%Y-%m-%d %H:%M') }}*",
        ]

        return {
            "type": "markdown",
            "title": "Summary",
            "content": "\n".join(content),
        }
