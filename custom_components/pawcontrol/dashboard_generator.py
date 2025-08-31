"""Dashboard Generator for Paw Control integration.

This module provides automatic dashboard creation and management for the
Paw Control integration. It creates comprehensive dashboards with cards
for all dog management features including monitoring, feeding, walks, health,
and GPS tracking. Supports full customization via configuration options.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.json import save_json
from homeassistant.helpers.storage import Store
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

_LOGGER = logging.getLogger(__name__)

# Dashboard configuration constants
DASHBOARD_STORAGE_KEY = f"{DOMAIN}_dashboards"
DASHBOARD_STORAGE_VERSION = 1
DEFAULT_DASHBOARD_TITLE = "🐕 Paw Control"
DEFAULT_DASHBOARD_ICON = "mdi:dog"
DEFAULT_DASHBOARD_URL = "paw-control"

# Card types for modular dashboard creation
CARD_TYPES = {
    "overview": "Overview Card",
    "feeding": "Feeding Management",
    "walk": "Walk Tracker",
    "health": "Health Monitor",
    "gps": "GPS Tracking",
    "notifications": "Notifications",
    "grooming": "Grooming Schedule",
    "medication": "Medication Tracker",
    "training": "Training Progress",
    "visitor": "Visitor Mode",
    "statistics": "Statistics",
    "history": "Activity History",
}

# Default theme colors for dog cards
DOG_CARD_THEMES = [
    {"primary": "#4CAF50", "accent": "#8BC34A"},  # Green
    {"primary": "#2196F3", "accent": "#03A9F4"},  # Blue
    {"primary": "#FF9800", "accent": "#FFC107"},  # Orange
    {"primary": "#9C27B0", "accent": "#E91E63"},  # Purple
    {"primary": "#00BCD4", "accent": "#009688"},  # Cyan
    {"primary": "#795548", "accent": "#607D8B"},  # Brown
]


class PawControlDashboardGenerator:
    """Generate and manage dashboards for Paw Control integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the dashboard generator.

        Args:
            hass: Home Assistant instance
            entry: Config entry for this integration instance
        """
        self.hass = hass
        self.entry = entry
        self._store = Store(
            hass,
            DASHBOARD_STORAGE_VERSION,
            f"{DASHBOARD_STORAGE_KEY}_{entry.entry_id}",
        )
        self._dashboards: Dict[str, Dict[str, Any]] = {}
        self._entity_registry = er.async_get(hass)
        self._initialized = False

    async def async_initialize(self) -> None:
        """Initialize the dashboard generator and load existing dashboards."""
        if self._initialized:
            return

        try:
            # Load existing dashboard configurations
            stored_data = await self._store.async_load()
            if stored_data:
                self._dashboards = stored_data.get("dashboards", {})
                _LOGGER.debug(
                    "Loaded %d existing dashboards for entry %s",
                    len(self._dashboards),
                    self.entry.entry_id,
                )
        except Exception as err:
            _LOGGER.error("Failed to load dashboard storage: %s", err)
            self._dashboards = {}

        self._initialized = True

    async def async_create_dashboard(
        self,
        dogs_config: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create the main Paw Control dashboard.

        Args:
            dogs_config: List of dog configurations
            options: Optional dashboard customization options

        Returns:
            URL path to the created dashboard
        """
        if not self._initialized:
            await self.async_initialize()

        options = options or {}

        # Generate dashboard configuration
        dashboard_config = await self._generate_main_dashboard_config(
            dogs_config, options
        )

        # Create unique dashboard URL
        dashboard_url = options.get("url", DEFAULT_DASHBOARD_URL)
        dashboard_url = f"{dashboard_url}-{self.entry.entry_id[:8]}"
        dashboard_url = slugify(dashboard_url)

        # Dashboard title with customization
        dashboard_title = options.get("title", DEFAULT_DASHBOARD_TITLE)

        try:
            # Create the dashboard using Lovelace API
            dashboard_path = await self._create_lovelace_dashboard(
                dashboard_url,
                dashboard_title,
                dashboard_config,
                options.get("icon", DEFAULT_DASHBOARD_ICON),
                options.get("show_in_sidebar", True),
            )

            # Store dashboard info
            self._dashboards[dashboard_url] = {
                "url": dashboard_url,
                "title": dashboard_title,
                "path": dashboard_path,
                "created": datetime.now().isoformat(),
                "type": "main",
                "dogs": [dog[CONF_DOG_ID] for dog in dogs_config],
                "options": options,
            }

            await self._save_dashboards()

            _LOGGER.info(
                "Created main dashboard '%s' at /%s for %d dogs",
                dashboard_title,
                dashboard_url,
                len(dogs_config),
            )

            return f"/{dashboard_url}"

        except Exception as err:
            _LOGGER.error("Failed to create main dashboard: %s", err)
            raise HomeAssistantError(f"Dashboard creation failed: {err}") from err

    async def async_create_dog_dashboard(
        self,
        dog_config: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create an individual dashboard for a specific dog.

        Args:
            dog_config: Dog configuration
            options: Optional dashboard customization options

        Returns:
            URL path to the created dashboard
        """
        if not self._initialized:
            await self.async_initialize()

        options = options or {}
        dog_id = dog_config[CONF_DOG_ID]
        dog_name = dog_config[CONF_DOG_NAME]

        # Generate dog-specific dashboard configuration
        dashboard_config = await self._generate_dog_dashboard_config(
            dog_config, options
        )

        # Create unique dashboard URL for this dog
        dashboard_url = f"paw-{slugify(dog_id)}"
        dashboard_title = f"🐕 {dog_name}"

        try:
            # Create the dashboard
            dashboard_path = await self._create_lovelace_dashboard(
                dashboard_url,
                dashboard_title,
                dashboard_config,
                "mdi:dog-side",
                options.get("show_in_sidebar", False),
            )

            # Store dashboard info
            self._dashboards[dashboard_url] = {
                "url": dashboard_url,
                "title": dashboard_title,
                "path": dashboard_path,
                "created": datetime.now().isoformat(),
                "type": "dog",
                "dog_id": dog_id,
                "dog_name": dog_name,
                "options": options,
            }

            await self._save_dashboards()

            _LOGGER.info(
                "Created dog dashboard for '%s' at /%s",
                dog_name,
                dashboard_url,
            )

            return f"/{dashboard_url}"

        except Exception as err:
            _LOGGER.error("Failed to create dog dashboard for %s: %s", dog_name, err)
            raise HomeAssistantError(f"Dog dashboard creation failed: {err}") from err

    async def async_update_dashboard(
        self,
        dashboard_url: str,
        dogs_config: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update an existing dashboard with new configuration.

        Args:
            dashboard_url: URL of the dashboard to update
            dogs_config: Updated list of dog configurations
            options: Optional dashboard customization options

        Returns:
            True if update was successful
        """
        if dashboard_url not in self._dashboards:
            _LOGGER.warning("Dashboard %s not found for update", dashboard_url)
            return False

        dashboard_info = self._dashboards[dashboard_url]

        try:
            # Generate updated configuration
            if dashboard_info["type"] == "main":
                dashboard_config = await self._generate_main_dashboard_config(
                    dogs_config, options or dashboard_info.get("options", {})
                )
            else:
                # Find the specific dog config for dog dashboard
                dog_id = dashboard_info.get("dog_id")
                dog_config = next(
                    (d for d in dogs_config if d[CONF_DOG_ID] == dog_id), None
                )
                if not dog_config:
                    _LOGGER.warning("Dog %s not found for dashboard update", dog_id)
                    return False

                dashboard_config = await self._generate_dog_dashboard_config(
                    dog_config, options or dashboard_info.get("options", {})
                )

            # Update the dashboard
            await self._update_lovelace_dashboard(
                dashboard_info["path"], dashboard_config
            )

            # Update stored info
            dashboard_info["updated"] = datetime.now().isoformat()
            if options:
                dashboard_info["options"] = options

            await self._save_dashboards()

            _LOGGER.info("Updated dashboard %s", dashboard_url)
            return True

        except Exception as err:
            _LOGGER.error("Failed to update dashboard %s: %s", dashboard_url, err)
            return False

    async def async_delete_dashboard(self, dashboard_url: str) -> bool:
        """Delete a dashboard.

        Args:
            dashboard_url: URL of the dashboard to delete

        Returns:
            True if deletion was successful
        """
        if dashboard_url not in self._dashboards:
            _LOGGER.warning("Dashboard %s not found for deletion", dashboard_url)
            return False

        try:
            # Remove from Lovelace
            await self._delete_lovelace_dashboard(dashboard_url)

            # Remove from storage
            del self._dashboards[dashboard_url]
            await self._save_dashboards()

            _LOGGER.info("Deleted dashboard %s", dashboard_url)
            return True

        except Exception as err:
            _LOGGER.error("Failed to delete dashboard %s: %s", dashboard_url, err)
            return False

    async def async_cleanup(self) -> None:
        """Clean up all dashboards created by this generator."""
        _LOGGER.debug("Cleaning up dashboards for entry %s", self.entry.entry_id)

        # Delete all dashboards
        dashboard_urls = list(self._dashboards.keys())
        for dashboard_url in dashboard_urls:
            await self.async_delete_dashboard(dashboard_url)

        # Clear storage
        await self._store.async_remove()

    async def _generate_main_dashboard_config(
        self, dogs_config: List[Dict[str, Any]], options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate the main dashboard configuration.

        Args:
            dogs_config: List of dog configurations
            options: Dashboard customization options

        Returns:
            Dashboard configuration dictionary
        """
        views = []

        # Main overview view
        overview_view = {
            "title": "Overview",
            "path": "overview",
            "icon": "mdi:view-dashboard",
            "cards": await self._generate_overview_cards(dogs_config, options),
        }
        views.append(overview_view)

        # Individual dog views
        for idx, dog_config in enumerate(dogs_config):
            dog_view = {
                "title": dog_config[CONF_DOG_NAME],
                "path": slugify(dog_config[CONF_DOG_ID]),
                "icon": "mdi:dog",
                "theme": options.get("theme", "default"),
                "cards": await self._generate_dog_cards(
                    dog_config, DOG_CARD_THEMES[idx % len(DOG_CARD_THEMES)], options
                ),
            }
            views.append(dog_view)

        # Statistics view if enabled
        if options.get("show_statistics", True):
            stats_view = {
                "title": "Statistics",
                "path": "statistics",
                "icon": "mdi:chart-line",
                "cards": await self._generate_statistics_cards(dogs_config, options),
            }
            views.append(stats_view)

        # Settings view if enabled
        if options.get("show_settings", True):
            settings_view = {
                "title": "Settings",
                "path": "settings",
                "icon": "mdi:cog",
                "cards": await self._generate_settings_cards(dogs_config, options),
            }
            views.append(settings_view)

        return {
            "views": views,
        }

    async def _generate_dog_dashboard_config(
        self, dog_config: Dict[str, Any], options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate individual dog dashboard configuration.

        Args:
            dog_config: Dog configuration
            options: Dashboard customization options

        Returns:
            Dashboard configuration dictionary
        """
        views = []
        theme = DOG_CARD_THEMES[0]  # Use first theme for individual dashboards

        # Main view for the dog
        main_view = {
            "title": "Overview",
            "path": "overview",
            "icon": "mdi:dog",
            "cards": await self._generate_dog_cards(dog_config, theme, options),
        }
        views.append(main_view)

        # Module-specific views based on enabled modules
        modules = dog_config.get("modules", {})

        if modules.get(MODULE_FEEDING):
            feeding_view = {
                "title": "Feeding",
                "path": "feeding",
                "icon": "mdi:food-drumstick",
                "cards": await self._generate_feeding_cards(dog_config, options),
            }
            views.append(feeding_view)

        if modules.get(MODULE_WALK):
            walk_view = {
                "title": "Walks",
                "path": "walks",
                "icon": "mdi:walk",
                "cards": await self._generate_walk_cards(dog_config, options),
            }
            views.append(walk_view)

        if modules.get(MODULE_HEALTH):
            health_view = {
                "title": "Health",
                "path": "health",
                "icon": "mdi:heart-pulse",
                "cards": await self._generate_health_cards(dog_config, options),
            }
            views.append(health_view)

        if modules.get(MODULE_GPS):
            gps_view = {
                "title": "Location",
                "path": "location",
                "icon": "mdi:map-marker",
                "cards": await self._generate_gps_cards(dog_config, options),
            }
            views.append(gps_view)

        return {
            "views": views,
        }

    async def _generate_overview_cards(
        self, dogs_config: List[Dict[str, Any]], options: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate overview cards for the main dashboard."""
        cards = []

        # Welcome card
        cards.append(
            {
                "type": "markdown",
                "content": (
                    f"# {options.get('title', DEFAULT_DASHBOARD_TITLE)}\n\n"
                    f"Managing **{len(dogs_config)}** dogs with Paw Control\n\n"
                    f"Last updated: {{{{ now().strftime('%H:%M') }}}}"
                ),
            }
        )

        # Dog status grid
        dog_cards = []
        for dog in dogs_config:
            dog_id = dog[CONF_DOG_ID]
            dog_name = dog[CONF_DOG_NAME]

            dog_cards.append(
                {
                    "type": "button",
                    "entity": f"sensor.{dog_id}_status",
                    "name": dog_name,
                    "icon": "mdi:dog",
                    "tap_action": {
                        "action": "navigate",
                        "navigation_path": f"/{DEFAULT_DASHBOARD_URL}-{self.entry.entry_id[:8]}/{slugify(dog_id)}",
                    },
                }
            )

        if dog_cards:
            cards.append(
                {
                    "type": "grid",
                    "columns": 3,
                    "cards": dog_cards,
                }
            )

        # Quick actions
        cards.append(
            {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "button",
                        "name": "Feed All",
                        "icon": "mdi:food-drumstick",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.feed_dog",
                            "service_data": {
                                "dog_id": "all",
                                "meal_type": "regular",
                            },
                        },
                    },
                    {
                        "type": "button",
                        "name": "Start Walks",
                        "icon": "mdi:walk",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.start_walk",
                            "service_data": {
                                "dog_id": "all",
                            },
                        },
                    },
                    {
                        "type": "button",
                        "name": "Daily Reset",
                        "icon": "mdi:refresh",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.daily_reset",
                        },
                    },
                ],
            }
        )

        # Activity summary
        if options.get("show_activity_summary", True):
            cards.append(
                {
                    "type": "history-graph",
                    "title": "Activity Summary",
                    "entities": [
                        f"sensor.{dog[CONF_DOG_ID]}_activity_level"
                        for dog in dogs_config
                    ],
                    "hours_to_show": 24,
                }
            )

        return cards

    async def _generate_dog_cards(
        self, dog_config: Dict[str, Any], theme: Dict[str, str], options: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate cards for a specific dog."""
        cards = []
        dog_id = dog_config[CONF_DOG_ID]
        dog_name = dog_config[CONF_DOG_NAME]
        modules = dog_config.get("modules", {})

        # Dog header card
        cards.append(
            {
                "type": "picture-entity",
                "entity": f"sensor.{dog_id}_status",
                "name": dog_name,
                "image": dog_config.get(
                    "dog_image", "/local/paw_control/default_dog.jpg"
                ),
                "show_state": True,
                "show_name": True,
                "camera_view": "auto",
            }
        )

        # Status card with key metrics
        status_entities = [
            f"sensor.{dog_id}_status",
            f"sensor.{dog_id}_last_fed",
            f"sensor.{dog_id}_last_walk",
            f"sensor.{dog_id}_activity_level",
        ]

        if modules.get(MODULE_HEALTH):
            status_entities.extend(
                [
                    f"sensor.{dog_id}_weight",
                    f"sensor.{dog_id}_health_status",
                ]
            )

        cards.append(
            {
                "type": "entities",
                "title": "Status",
                "entities": status_entities,
                "state_color": True,
            }
        )

        # Quick actions for this dog
        action_buttons = []

        if modules.get(MODULE_FEEDING):
            action_buttons.append(
                {
                    "type": "button",
                    "name": "Feed",
                    "icon": "mdi:food-drumstick",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.feed_dog",
                        "service_data": {
                            "dog_id": dog_id,
                            "meal_type": "regular",
                        },
                    },
                }
            )

        if modules.get(MODULE_WALK):
            action_buttons.append(
                {
                    "type": "button",
                    "name": "Walk",
                    "icon": "mdi:walk",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.start_walk",
                        "service_data": {
                            "dog_id": dog_id,
                        },
                    },
                }
            )

        if modules.get(MODULE_HEALTH):
            action_buttons.append(
                {
                    "type": "button",
                    "name": "Health Check",
                    "icon": "mdi:heart-pulse",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.log_health",
                        "service_data": {
                            "dog_id": dog_id,
                        },
                    },
                }
            )

        if action_buttons:
            cards.append(
                {
                    "type": "horizontal-stack",
                    "cards": action_buttons,
                }
            )

        # GPS map if enabled
        if modules.get(MODULE_GPS):
            cards.append(
                {
                    "type": "map",
                    "entities": [f"device_tracker.{dog_id}_location"],
                    "default_zoom": 15,
                    "dark_mode": options.get("dark_mode", False),
                }
            )

        # Activity graph
        cards.append(
            {
                "type": "history-graph",
                "title": "24h Activity",
                "entities": [
                    f"sensor.{dog_id}_activity_level",
                    f"binary_sensor.{dog_id}_is_walking",
                ],
                "hours_to_show": 24,
            }
        )

        return cards

    async def _generate_feeding_cards(
        self, dog_config: Dict[str, Any], options: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate feeding-specific cards."""
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # Feeding schedule
        cards.append(
            {
                "type": "entities",
                "title": "Feeding Schedule",
                "entities": [
                    f"sensor.{dog_id}_next_meal_time",
                    f"sensor.{dog_id}_meals_today",
                    f"sensor.{dog_id}_calories_today",
                    f"select.{dog_id}_meal_type",
                    f"number.{dog_id}_portion_size",
                ],
            }
        )

        # Feeding history graph
        cards.append(
            {
                "type": "history-graph",
                "title": "Feeding History",
                "entities": [
                    f"sensor.{dog_id}_meals_today",
                    f"sensor.{dog_id}_calories_today",
                ],
                "hours_to_show": 168,  # 1 week
            }
        )

        # Feeding controls
        cards.append(
            {
                "type": "vertical-stack",
                "title": "Feeding Controls",
                "cards": [
                    {
                        "type": "entities",
                        "entities": [
                            f"button.{dog_id}_feed_breakfast",
                            f"button.{dog_id}_feed_lunch",
                            f"button.{dog_id}_feed_dinner",
                            f"button.{dog_id}_feed_snack",
                        ],
                    },
                    {
                        "type": "button",
                        "name": "Custom Feeding",
                        "icon": "mdi:food",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.feed_dog",
                            "service_data": {
                                "dog_id": dog_id,
                            },
                        },
                    },
                ],
            }
        )

        return cards

    async def _generate_walk_cards(
        self, dog_config: Dict[str, Any], options: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate walk-specific cards."""
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # Walk status
        cards.append(
            {
                "type": "entities",
                "title": "Walk Status",
                "entities": [
                    f"binary_sensor.{dog_id}_is_walking",
                    f"sensor.{dog_id}_current_walk_duration",
                    f"sensor.{dog_id}_walks_today",
                    f"sensor.{dog_id}_walk_distance_today",
                    f"sensor.{dog_id}_last_walk_time",
                ],
            }
        )

        # Walk controls
        cards.append(
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
                    "icon_height": "40px",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.start_walk",
                        "service_data": {
                            "dog_id": dog_id,
                        },
                    },
                },
            }
        )

        cards.append(
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
                    "icon_height": "40px",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.end_walk",
                        "service_data": {
                            "dog_id": dog_id,
                        },
                    },
                },
            }
        )

        # Walk history
        cards.append(
            {
                "type": "history-graph",
                "title": "Walk History",
                "entities": [
                    f"sensor.{dog_id}_walks_today",
                    f"sensor.{dog_id}_walk_distance_today",
                ],
                "hours_to_show": 168,  # 1 week
            }
        )

        return cards

    async def _generate_health_cards(
        self, dog_config: Dict[str, Any], options: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate health-specific cards."""
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # Health metrics
        cards.append(
            {
                "type": "entities",
                "title": "Health Metrics",
                "entities": [
                    f"sensor.{dog_id}_health_status",
                    f"sensor.{dog_id}_weight",
                    f"sensor.{dog_id}_temperature",
                    f"sensor.{dog_id}_mood",
                    f"sensor.{dog_id}_energy_level",
                ],
            }
        )

        # Weight tracking graph
        cards.append(
            {
                "type": "history-graph",
                "title": "Weight Tracking",
                "entities": [f"sensor.{dog_id}_weight"],
                "hours_to_show": 720,  # 30 days
            }
        )

        # Health controls
        cards.append(
            {
                "type": "entities",
                "title": "Health Management",
                "entities": [
                    f"button.{dog_id}_log_health",
                    f"button.{dog_id}_schedule_vet_visit",
                    f"date.{dog_id}_next_vet_visit",
                    f"date.{dog_id}_next_vaccination",
                ],
            }
        )

        return cards

    async def _generate_gps_cards(
        self, dog_config: Dict[str, Any], options: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate GPS-specific cards."""
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # GPS map
        cards.append(
            {
                "type": "map",
                "entities": [f"device_tracker.{dog_id}_location"],
                "default_zoom": 16,
                "dark_mode": options.get("dark_mode", False),
            }
        )

        # GPS status
        cards.append(
            {
                "type": "entities",
                "title": "GPS Status",
                "entities": [
                    f"device_tracker.{dog_id}_location",
                    f"sensor.{dog_id}_gps_accuracy",
                    f"sensor.{dog_id}_distance_from_home",
                    f"sensor.{dog_id}_speed",
                ],
            }
        )

        # Geofence alerts
        cards.append(
            {
                "type": "entities",
                "title": "Geofence",
                "entities": [
                    f"binary_sensor.{dog_id}_at_home",
                    f"binary_sensor.{dog_id}_at_park",
                    f"number.{dog_id}_safe_zone_radius",
                ],
            }
        )

        return cards

    async def _generate_statistics_cards(
        self, dogs_config: List[Dict[str, Any]], options: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate statistics cards."""
        cards = []

        # Overall statistics
        cards.append(
            {
                "type": "statistics-graph",
                "title": "Activity Statistics",
                "entities": [
                    f"sensor.{dog[CONF_DOG_ID]}_activity_level" for dog in dogs_config
                ],
                "stat_types": ["mean", "min", "max"],
                "days_to_show": 30,
            }
        )

        # Feeding statistics
        cards.append(
            {
                "type": "statistics-graph",
                "title": "Feeding Statistics",
                "entities": [
                    f"sensor.{dog[CONF_DOG_ID]}_meals_today" for dog in dogs_config
                ],
                "stat_types": ["sum", "mean"],
                "days_to_show": 30,
            }
        )

        # Walk statistics
        cards.append(
            {
                "type": "statistics-graph",
                "title": "Walk Statistics",
                "entities": [
                    f"sensor.{dog[CONF_DOG_ID]}_walk_distance_today"
                    for dog in dogs_config
                ],
                "stat_types": ["sum", "mean", "max"],
                "days_to_show": 30,
            }
        )

        return cards

    async def _generate_settings_cards(
        self, dogs_config: List[Dict[str, Any]], options: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate settings cards."""
        cards = []

        # Integration settings
        cards.append(
            {
                "type": "entities",
                "title": "Integration Settings",
                "entities": [
                    f"switch.{DOMAIN}_notifications_enabled",
                    f"select.{DOMAIN}_performance_mode",
                    f"number.{DOMAIN}_data_retention_days",
                ],
            }
        )

        # Per-dog settings
        for dog in dogs_config:
            dog_id = dog[CONF_DOG_ID]
            dog_name = dog[CONF_DOG_NAME]

            cards.append(
                {
                    "type": "entities",
                    "title": f"{dog_name} Settings",
                    "entities": [
                        f"switch.{dog_id}_notifications_enabled",
                        f"switch.{dog_id}_gps_tracking_enabled",
                        f"switch.{dog_id}_visitor_mode",
                    ],
                }
            )

        # Maintenance actions
        cards.append(
            {
                "type": "vertical-stack",
                "title": "Maintenance",
                "cards": [
                    {
                        "type": "button",
                        "name": "Export Data",
                        "icon": "mdi:download",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.export_data",
                            "service_data": {
                                "data_type": "all",
                            },
                        },
                    },
                    {
                        "type": "button",
                        "name": "Reload Integration",
                        "icon": "mdi:reload",
                        "tap_action": {
                            "action": "call-service",
                            "service": "homeassistant.reload_config_entry",
                            "service_data": {
                                "entry_id": self.entry.entry_id,
                            },
                        },
                    },
                ],
            }
        )

        return cards

    async def _create_lovelace_dashboard(
        self,
        url_path: str,
        title: str,
        config: Dict[str, Any],
        icon: str,
        show_in_sidebar: bool,
    ) -> str:
        """Create a Lovelace dashboard.

        Args:
            url_path: URL path for the dashboard
            title: Dashboard title
            config: Dashboard configuration
            icon: Dashboard icon
            show_in_sidebar: Whether to show in sidebar

        Returns:
            Path to the created dashboard
        """
        # Store dashboard configuration
        dashboard_path = self.hass.config.path(f".storage/lovelace.{url_path}")

        dashboard_data = {
            "version": 1,
            "minor_version": 1,
            "key": f"lovelace.{url_path}",
            "data": {
                "config": config,
            },
        }

        try:
            # Save dashboard configuration
            await save_json(dashboard_path, dashboard_data)

            # Register dashboard with Lovelace
            if show_in_sidebar:
                # This would require integration with Lovelace component
                # For now, we just save the configuration
                pass

            return dashboard_path

        except Exception as err:
            _LOGGER.error("Failed to create Lovelace dashboard: %s", err)
            raise

    async def _update_lovelace_dashboard(
        self, dashboard_path: str, config: Dict[str, Any]
    ) -> None:
        """Update an existing Lovelace dashboard.

        Args:
            dashboard_path: Path to the dashboard file
            config: New dashboard configuration
        """
        try:
            # Load existing dashboard
            dashboard_data = json.loads(Path(dashboard_path).read_text())

            # Update configuration
            dashboard_data["data"]["config"] = config

            # Save updated dashboard
            await save_json(dashboard_path, dashboard_data)

        except Exception as err:
            _LOGGER.error("Failed to update Lovelace dashboard: %s", err)
            raise

    async def _delete_lovelace_dashboard(self, url_path: str) -> None:
        """Delete a Lovelace dashboard.

        Args:
            url_path: URL path of the dashboard to delete
        """
        dashboard_path = self.hass.config.path(f".storage/lovelace.{url_path}")

        try:
            Path(dashboard_path).unlink(missing_ok=True)
        except Exception as err:
            _LOGGER.error("Failed to delete Lovelace dashboard: %s", err)
            raise

    async def _save_dashboards(self) -> None:
        """Save dashboard configurations to storage."""
        try:
            await self._store.async_save(
                {
                    "dashboards": self._dashboards,
                    "updated": datetime.now().isoformat(),
                }
            )
        except Exception as err:
            _LOGGER.error("Failed to save dashboard storage: %s", err)

    @callback
    def get_dashboard_info(self, dashboard_url: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific dashboard.

        Args:
            dashboard_url: URL of the dashboard

        Returns:
            Dashboard information or None if not found
        """
        return self._dashboards.get(dashboard_url)

    @callback
    def get_all_dashboards(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all dashboards.

        Returns:
            Dictionary of all dashboard information
        """
        return self._dashboards.copy()
