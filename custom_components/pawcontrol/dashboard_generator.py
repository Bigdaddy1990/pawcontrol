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

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Final

import aiofiles
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify
from homeassistant.util.dt import utcnow

from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
)

_LOGGER = logging.getLogger(__name__)

# Dashboard configuration constants
DASHBOARD_STORAGE_KEY: Final[str] = f"{DOMAIN}_dashboards"
DASHBOARD_STORAGE_VERSION: Final[int] = 2
DEFAULT_DASHBOARD_TITLE: Final[str] = "🐕 Paw Control"
DEFAULT_DASHBOARD_ICON: Final[str] = "mdi:dog"
DEFAULT_DASHBOARD_URL: Final[str] = "paw-control"

# Card types for modular dashboard creation
CARD_TYPES: Final[dict[str, str]] = {
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
DOG_CARD_THEMES: Final[list[dict[str, str]]] = [
    {"primary": "#4CAF50", "accent": "#8BC34A"},  # Green
    {"primary": "#2196F3", "accent": "#03A9F4"},  # Blue
    {"primary": "#FF9800", "accent": "#FFC107"},  # Orange
    {"primary": "#9C27B0", "accent": "#E91E63"},  # Purple
    {"primary": "#00BCD4", "accent": "#009688"},  # Cyan
    {"primary": "#795548", "accent": "#607D8B"},  # Brown
]


class PawControlDashboardGenerator:
    """Generate and manage dashboards for Paw Control integration.

    Provides comprehensive dashboard creation with automatic card generation,
    modular design based on enabled modules, and full async operation.
    Implements modern Home Assistant storage patterns and Lovelace integration.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the dashboard generator.

        Args:
            hass: Home Assistant instance
            entry: Config entry for this integration instance
        """
        self.hass = hass
        self.entry = entry
        self._store = Store[dict[str, Any]](
            hass,
            DASHBOARD_STORAGE_VERSION,
            f"{DASHBOARD_STORAGE_KEY}_{entry.entry_id}",
        )
        self._dashboards: dict[str, dict[str, Any]] = {}
        self._entity_registry = er.async_get(hass)
        self._initialized = False
        self._lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Initialize the dashboard generator and load existing dashboards.

        Raises:
            HomeAssistantError: If initialization fails
        """
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:  # Double-check after acquiring lock
                return

            try:
                # Load existing dashboard configurations with error handling
                stored_data = await self._store.async_load() or {}
                self._dashboards = stored_data.get("dashboards", {})

                _LOGGER.debug(
                    "Dashboard generator initialized: %d existing dashboards for entry %s",
                    len(self._dashboards),
                    self.entry.entry_id,
                )

                # Validate stored dashboards and clean up invalid ones
                await self._validate_stored_dashboards()

            except Exception as err:
                _LOGGER.error(
                    "Failed to initialize dashboard generator: %s", err, exc_info=True
                )
                self._dashboards = {}
                # Don't raise, allow initialization to continue

            finally:
                self._initialized = True

    async def async_create_dashboard(
        self,
        dogs_config: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> str:
        """Create the main Paw Control dashboard.

        Args:
            dogs_config: List of dog configurations
            options: Optional dashboard customization options

        Returns:
            URL path to the created dashboard

        Raises:
            HomeAssistantError: If dashboard creation fails
            ValueError: If dogs_config is invalid
        """
        if not self._initialized:
            await self.async_initialize()

        if not dogs_config:
            raise ValueError("At least one dog configuration is required")

        options = options or {}

        async with self._lock:
            try:
                # Generate dashboard configuration
                dashboard_config = await self._generate_main_dashboard_config(
                    dogs_config, options
                )

                # Create unique dashboard URL with fallback
                base_url = options.get("url", DEFAULT_DASHBOARD_URL)
                dashboard_url = f"{base_url}-{self.entry.entry_id[:8]}"
                dashboard_url = slugify(dashboard_url)

                # Dashboard title with validation
                dashboard_title = options.get("title", DEFAULT_DASHBOARD_TITLE)
                if not dashboard_title.strip():
                    dashboard_title = DEFAULT_DASHBOARD_TITLE

                # Create the dashboard using modern Lovelace patterns
                dashboard_path = await self._create_lovelace_dashboard(
                    dashboard_url,
                    dashboard_title,
                    dashboard_config,
                    options.get("icon", DEFAULT_DASHBOARD_ICON),
                    options.get("show_in_sidebar", True),
                )

                # Store dashboard info with comprehensive metadata
                self._dashboards[dashboard_url] = {
                    "url": dashboard_url,
                    "title": dashboard_title,
                    "path": dashboard_path,
                    "created": utcnow().isoformat(),
                    "type": "main",
                    "dogs": [
                        dog[CONF_DOG_ID] for dog in dogs_config if dog.get(CONF_DOG_ID)
                    ],
                    "options": options,
                    "entry_id": self.entry.entry_id,
                    "version": DASHBOARD_STORAGE_VERSION,
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
                _LOGGER.error("Failed to create main dashboard: %s", err, exc_info=True)
                raise HomeAssistantError(f"Dashboard creation failed: {err}") from err

    async def async_create_dog_dashboard(
        self,
        dog_config: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> str:
        """Create an individual dashboard for a specific dog.

        Args:
            dog_config: Dog configuration
            options: Optional dashboard customization options

        Returns:
            URL path to the created dashboard

        Raises:
            HomeAssistantError: If dashboard creation fails
            ValueError: If dog_config is invalid
        """
        if not self._initialized:
            await self.async_initialize()

        # Validate dog configuration
        dog_id = dog_config.get(CONF_DOG_ID)
        dog_name = dog_config.get(CONF_DOG_NAME)

        if not dog_id:
            raise ValueError("Dog ID is required in dog_config")
        if not dog_name:
            raise ValueError("Dog name is required in dog_config")

        options = options or {}

        async with self._lock:
            try:
                # Generate dog-specific dashboard configuration
                dashboard_config = await self._generate_dog_dashboard_config(
                    dog_config, options
                )

                # Create unique dashboard URL for this dog
                dashboard_url = f"paw-{slugify(dog_id)}"
                dashboard_title = f"🐕 {dog_name}"

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
                    "created": utcnow().isoformat(),
                    "type": "dog",
                    "dog_id": dog_id,
                    "dog_name": dog_name,
                    "options": options,
                    "entry_id": self.entry.entry_id,
                    "version": DASHBOARD_STORAGE_VERSION,
                }

                await self._save_dashboards()

                _LOGGER.info(
                    "Created dog dashboard for '%s' at /%s",
                    dog_name,
                    dashboard_url,
                )

                return f"/{dashboard_url}"

            except Exception as err:
                _LOGGER.error(
                    "Failed to create dog dashboard for %s: %s",
                    dog_name,
                    err,
                    exc_info=True,
                )
                raise HomeAssistantError(
                    f"Dog dashboard creation failed: {err}"
                ) from err

    async def async_update_dashboard(
        self,
        dashboard_url: str,
        dogs_config: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> bool:
        """Update an existing dashboard with new configuration.

        Args:
            dashboard_url: URL of the dashboard to update
            dogs_config: Updated list of dog configurations
            options: Optional dashboard customization options

        Returns:
            True if update was successful
        """
        if not self._initialized:
            await self.async_initialize()

        if dashboard_url not in self._dashboards:
            _LOGGER.warning("Dashboard %s not found for update", dashboard_url)
            return False

        dashboard_info = self._dashboards[dashboard_url]

        async with self._lock:
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
                        (d for d in dogs_config if d.get(CONF_DOG_ID) == dog_id), None
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
                dashboard_info["updated"] = utcnow().isoformat()
                if options:
                    dashboard_info["options"] = options

                await self._save_dashboards()

                _LOGGER.info("Updated dashboard %s", dashboard_url)
                return True

            except Exception as err:
                _LOGGER.error(
                    "Failed to update dashboard %s: %s",
                    dashboard_url,
                    err,
                    exc_info=True,
                )
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

        async with self._lock:
            try:
                dashboard_info = self._dashboards[dashboard_url]

                # Remove from Lovelace
                await self._delete_lovelace_dashboard(dashboard_info["path"])

                # Remove from storage
                del self._dashboards[dashboard_url]
                await self._save_dashboards()

                _LOGGER.info("Deleted dashboard %s", dashboard_url)
                return True

            except Exception as err:
                _LOGGER.error(
                    "Failed to delete dashboard %s: %s",
                    dashboard_url,
                    err,
                    exc_info=True,
                )
                return False

    async def async_cleanup(self) -> None:
        """Clean up all dashboards created by this generator."""
        _LOGGER.debug("Cleaning up dashboards for entry %s", self.entry.entry_id)

        async with self._lock:
            # Delete all dashboards
            dashboard_urls = list(self._dashboards.keys())
            for dashboard_url in dashboard_urls:
                try:
                    dashboard_info = self._dashboards[dashboard_url]
                    await self._delete_lovelace_dashboard(dashboard_info["path"])
                except Exception as err:
                    _LOGGER.warning(
                        "Error cleaning up dashboard %s: %s", dashboard_url, err
                    )

            # Clear storage
            try:
                await self._store.async_remove()
            except Exception as err:
                _LOGGER.warning("Error removing dashboard storage: %s", err)

            self._dashboards.clear()

    async def _generate_main_dashboard_config(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> dict[str, Any]:
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
            if not dog_config.get(CONF_DOG_ID) or not dog_config.get(CONF_DOG_NAME):
                continue

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

        return {"views": views}

    async def _generate_dog_dashboard_config(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
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

        return {"views": views}

    async def _generate_overview_cards(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
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
            if not dog.get(CONF_DOG_ID) or not dog.get(CONF_DOG_NAME):
                continue

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
        action_cards = [
            {
                "type": "button",
                "name": "Daily Reset",
                "icon": "mdi:refresh",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.daily_reset",
                },
            }
        ]

        # Add feeding/walking buttons if any dogs have those modules
        has_feeding = any(
            dog.get("modules", {}).get(MODULE_FEEDING) for dog in dogs_config
        )
        has_walking = any(
            dog.get("modules", {}).get(MODULE_WALK) for dog in dogs_config
        )

        if has_feeding:
            action_cards.insert(
                0,
                {
                    "type": "button",
                    "name": "Feed All",
                    "icon": "mdi:food-drumstick",
                    "tap_action": {
                        "action": "more-info",
                        "entity": f"button.{DOMAIN}_feed_all_dogs",
                    },
                },
            )

        if has_walking:
            action_cards.insert(
                -1,
                {
                    "type": "button",
                    "name": "Walk Status",
                    "icon": "mdi:walk",
                    "tap_action": {
                        "action": "more-info",
                        "entity": f"sensor.{DOMAIN}_dogs_walking",
                    },
                },
            )

        if action_cards:
            cards.append(
                {
                    "type": "horizontal-stack",
                    "cards": action_cards,
                }
            )

        # Activity summary if requested
        if options.get("show_activity_summary", True) and dogs_config:
            activity_entities = [
                f"sensor.{dog[CONF_DOG_ID]}_activity_level"
                for dog in dogs_config
                if dog.get(CONF_DOG_ID)
            ]

            if activity_entities:
                cards.append(
                    {
                        "type": "history-graph",
                        "title": "Activity Summary",
                        "entities": activity_entities,
                        "hours_to_show": 24,
                    }
                )

        return cards

    async def _generate_dog_cards(
        self, dog_config: dict[str, Any], theme: dict[str, str], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate cards for a specific dog."""
        cards = []
        dog_id = dog_config[CONF_DOG_ID]
        dog_name = dog_config[CONF_DOG_NAME]
        modules = dog_config.get("modules", {})

        # Dog header card
        dog_image = dog_config.get("dog_image", "/local/paw_control/default_dog.jpg")
        cards.append(
            {
                "type": "picture-entity",
                "entity": f"sensor.{dog_id}_status",
                "name": dog_name,
                "image": dog_image,
                "show_state": True,
                "show_name": True,
            }
        )

        # Status card with key metrics
        status_entities = [
            f"sensor.{dog_id}_status",
            f"sensor.{dog_id}_last_activity",
        ]

        # Add module-specific status entities
        if modules.get(MODULE_FEEDING):
            status_entities.extend(
                [
                    f"sensor.{dog_id}_last_fed",
                    f"sensor.{dog_id}_meals_today",
                ]
            )

        if modules.get(MODULE_WALK):
            status_entities.extend(
                [
                    f"sensor.{dog_id}_last_walk",
                    f"binary_sensor.{dog_id}_is_walking",
                ]
            )

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
            # Show different button based on walking state
            action_buttons.extend(
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
                            "tap_action": {
                                "action": "call-service",
                                "service": f"{DOMAIN}.end_walk",
                                "service_data": {"dog_id": dog_id},
                            },
                        },
                    },
                ]
            )

        if modules.get(MODULE_HEALTH):
            action_buttons.append(
                {
                    "type": "button",
                    "name": "Log Health",
                    "icon": "mdi:heart-pulse",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.log_health",
                        "service_data": {"dog_id": dog_id},
                    },
                }
            )

        if action_buttons:
            # Split conditional and regular buttons
            regular_buttons = [
                b for b in action_buttons if b.get("type") != "conditional"
            ]
            conditional_cards = [
                b for b in action_buttons if b.get("type") == "conditional"
            ]

            if regular_buttons:
                cards.append(
                    {
                        "type": "horizontal-stack",
                        "cards": regular_buttons,
                    }
                )

            # Add conditional cards separately
            cards.extend(conditional_cards)

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
        if options.get("show_activity_graph", True):
            activity_entities = [f"sensor.{dog_id}_activity_level"]
            if modules.get(MODULE_WALK):
                activity_entities.append(f"binary_sensor.{dog_id}_is_walking")

            cards.append(
                {
                    "type": "history-graph",
                    "title": "24h Activity",
                    "entities": activity_entities,
                    "hours_to_show": 24,
                }
            )

        return cards

    async def _generate_feeding_cards(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate feeding-specific cards."""
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # Feeding schedule and status
        cards.append(
            {
                "type": "entities",
                "title": "Feeding Schedule",
                "entities": [
                    f"sensor.{dog_id}_next_meal_time",
                    f"sensor.{dog_id}_meals_today",
                    f"sensor.{dog_id}_calories_today",
                    f"sensor.{dog_id}_last_fed",
                ],
            }
        )

        # Feeding controls
        feeding_buttons = [
            {
                "type": "button",
                "name": "Breakfast",
                "icon": "mdi:weather-sunny",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.feed_dog",
                    "service_data": {
                        "dog_id": dog_id,
                        "meal_type": "breakfast",
                    },
                },
            },
            {
                "type": "button",
                "name": "Lunch",
                "icon": "mdi:weather-partly-cloudy",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.feed_dog",
                    "service_data": {
                        "dog_id": dog_id,
                        "meal_type": "lunch",
                    },
                },
            },
            {
                "type": "button",
                "name": "Dinner",
                "icon": "mdi:weather-night",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.feed_dog",
                    "service_data": {
                        "dog_id": dog_id,
                        "meal_type": "dinner",
                    },
                },
            },
            {
                "type": "button",
                "name": "Snack",
                "icon": "mdi:cookie",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.feed_dog",
                    "service_data": {
                        "dog_id": dog_id,
                        "meal_type": "snack",
                    },
                },
            },
        ]

        cards.extend(
            [
                {
                    "type": "horizontal-stack",
                    "cards": feeding_buttons[:2],
                },
                {
                    "type": "horizontal-stack",
                    "cards": feeding_buttons[2:],
                },
            ]
        )

        # Feeding history graph
        cards.append(
            {
                "type": "history-graph",
                "title": "Feeding History (7 days)",
                "entities": [
                    f"sensor.{dog_id}_meals_today",
                    f"sensor.{dog_id}_calories_today",
                ],
                "hours_to_show": 168,  # 7 days
            }
        )

        return cards

    async def _generate_walk_cards(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
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

        # Walk controls (using conditionals for proper state-based display)
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
        cards.append(
            {
                "type": "history-graph",
                "title": "Walk History (7 days)",
                "entities": [
                    f"sensor.{dog_id}_walks_today",
                    f"sensor.{dog_id}_walk_distance_today",
                ],
                "hours_to_show": 168,  # 7 days
            }
        )

        return cards

    async def _generate_health_cards(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
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
        cards.append(
            {
                "type": "history-graph",
                "title": "Weight Tracking (30 days)",
                "entities": [f"sensor.{dog_id}_weight"],
                "hours_to_show": 720,  # 30 days
            }
        )

        # Important dates
        cards.append(
            {
                "type": "entities",
                "title": "Health Schedule",
                "entities": [
                    f"date.{dog_id}_next_vet_visit",
                    f"date.{dog_id}_next_vaccination",
                    f"date.{dog_id}_next_grooming",
                ],
            }
        )

        return cards

    async def _generate_gps_cards(
        self, dog_config: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate GPS-specific cards."""
        cards = []
        dog_id = dog_config[CONF_DOG_ID]

        # GPS map (main feature)
        cards.append(
            {
                "type": "map",
                "entities": [f"device_tracker.{dog_id}_location"],
                "default_zoom": 16,
                "dark_mode": options.get("dark_mode", False),
                "hours_to_show": 2,  # Show recent GPS trail
            }
        )

        # GPS status and metrics
        cards.append(
            {
                "type": "entities",
                "title": "GPS Status",
                "entities": [
                    f"device_tracker.{dog_id}_location",
                    f"sensor.{dog_id}_gps_accuracy",
                    f"sensor.{dog_id}_distance_from_home",
                    f"sensor.{dog_id}_speed",
                    f"sensor.{dog_id}_battery_level",
                ],
            }
        )

        # Geofence status
        cards.append(
            {
                "type": "entities",
                "title": "Geofence & Safety",
                "entities": [
                    f"binary_sensor.{dog_id}_at_home",
                    f"binary_sensor.{dog_id}_at_park",
                    f"binary_sensor.{dog_id}_in_safe_zone",
                    f"switch.{dog_id}_gps_tracking_enabled",
                ],
            }
        )

        # GPS history (if available)
        cards.append(
            {
                "type": "history-graph",
                "title": "Location History",
                "entities": [
                    f"sensor.{dog_id}_distance_from_home",
                    f"sensor.{dog_id}_speed",
                ],
                "hours_to_show": 24,
            }
        )

        return cards

    async def _generate_statistics_cards(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate statistics cards for all dogs."""
        cards = []

        # Overall activity statistics
        activity_entities = [
            f"sensor.{dog[CONF_DOG_ID]}_activity_level"
            for dog in dogs_config
            if dog.get(CONF_DOG_ID)
        ]

        if activity_entities:
            cards.append(
                {
                    "type": "statistics-graph",
                    "title": "Activity Statistics (30 days)",
                    "entities": activity_entities,
                    "stat_types": ["mean", "min", "max"],
                    "days_to_show": 30,
                }
            )

        # Feeding statistics
        feeding_entities = [
            f"sensor.{dog[CONF_DOG_ID]}_meals_today"
            for dog in dogs_config
            if dog.get(CONF_DOG_ID) and dog.get("modules", {}).get(MODULE_FEEDING)
        ]

        if feeding_entities:
            cards.append(
                {
                    "type": "statistics-graph",
                    "title": "Feeding Statistics (30 days)",
                    "entities": feeding_entities,
                    "stat_types": ["sum", "mean"],
                    "days_to_show": 30,
                }
            )

        # Walk statistics
        walk_entities = [
            f"sensor.{dog[CONF_DOG_ID]}_walk_distance_today"
            for dog in dogs_config
            if dog.get(CONF_DOG_ID) and dog.get("modules", {}).get(MODULE_WALK)
        ]

        if walk_entities:
            cards.append(
                {
                    "type": "statistics-graph",
                    "title": "Walk Statistics (30 days)",
                    "entities": walk_entities,
                    "stat_types": ["sum", "mean", "max"],
                    "days_to_show": 30,
                }
            )

        # Health trends
        weight_entities = [
            f"sensor.{dog[CONF_DOG_ID]}_weight"
            for dog in dogs_config
            if dog.get(CONF_DOG_ID) and dog.get("modules", {}).get(MODULE_HEALTH)
        ]

        if weight_entities:
            cards.append(
                {
                    "type": "statistics-graph",
                    "title": "Weight Trends (60 days)",
                    "entities": weight_entities,
                    "stat_types": ["mean", "min", "max"],
                    "days_to_show": 60,
                }
            )

        # Summary statistics card
        cards.append(
            {
                "type": "markdown",
                "title": "Summary",
                "content": (
                    f"## Paw Control Statistics\n\n"
                    f"**Dogs managed:** {len(dogs_config)}\n\n"
                    f"**Active modules:**\n"
                    f"- Feeding: {sum(1 for d in dogs_config if d.get('modules', {}).get(MODULE_FEEDING))}\n"
                    f"- Walks: {sum(1 for d in dogs_config if d.get('modules', {}).get(MODULE_WALK))}\n"
                    f"- Health: {sum(1 for d in dogs_config if d.get('modules', {}).get(MODULE_HEALTH))}\n"
                    f"- GPS: {sum(1 for d in dogs_config if d.get('modules', {}).get(MODULE_GPS))}\n\n"
                    f"*Last updated: {{{{ now().strftime('%Y-%m-%d %H:%M') }}}}*"
                ),
            }
        )

        return cards

    async def _generate_settings_cards(
        self, dogs_config: list[dict[str, Any]], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate settings cards."""
        cards = []

        # Integration-wide settings
        cards.append(
            {
                "type": "entities",
                "title": "Integration Settings",
                "entities": [
                    f"switch.{DOMAIN}_notifications_enabled",
                    f"select.{DOMAIN}_data_retention_days",
                    f"switch.{DOMAIN}_advanced_logging",
                ],
            }
        )

        # Per-dog settings
        for dog in dogs_config:
            if not dog.get(CONF_DOG_ID) or not dog.get(CONF_DOG_NAME):
                continue

            dog_id = dog[CONF_DOG_ID]
            dog_name = dog[CONF_DOG_NAME]

            dog_entities = [f"switch.{dog_id}_notifications_enabled"]

            # Add module-specific settings
            modules = dog.get("modules", {})
            if modules.get(MODULE_GPS):
                dog_entities.append(f"switch.{dog_id}_gps_tracking_enabled")
            if modules.get(MODULE_VISITOR):
                dog_entities.append(f"switch.{dog_id}_visitor_mode")
            if modules.get(MODULE_NOTIFICATIONS):
                dog_entities.append(f"select.{dog_id}_notification_priority")

            cards.append(
                {
                    "type": "entities",
                    "title": f"{dog_name} Settings",
                    "entities": dog_entities,
                }
            )

        # Maintenance and system actions
        maintenance_buttons = [
            {
                "type": "button",
                "name": "Export All Data",
                "icon": "mdi:download",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.export_data",
                    "service_data": {
                        "dog_id": "all",
                        "data_type": "all",
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
        ]

        # Split into rows of 2 buttons each
        for i in range(0, len(maintenance_buttons), 2):
            button_row = maintenance_buttons[i : i + 2]
            cards.append(
                {
                    "type": "horizontal-stack",
                    "cards": button_row,
                }
            )

        return cards

    async def _create_lovelace_dashboard(
        self,
        url_path: str,
        title: str,
        config: dict[str, Any],
        icon: str,
        show_in_sidebar: bool,
    ) -> str:
        """Create a Lovelace dashboard using modern Home Assistant storage patterns.

        Args:
            url_path: URL path for the dashboard
            title: Dashboard title
            config: Dashboard configuration
            icon: Dashboard icon
            show_in_sidebar: Whether to show in sidebar

        Returns:
            Path identifier for the created dashboard

        Raises:
            HomeAssistantError: If dashboard creation fails
        """
        try:
            # Create dashboard data structure
            dashboard_data = {
                "version": 1,
                "minor_version": 1,
                "key": f"lovelace.{url_path}",
                "data": {
                    "config": config,
                    "title": title,
                    "icon": icon,
                    "show_in_sidebar": show_in_sidebar,
                    "require_admin": False,
                },
            }

            # Use Home Assistant's storage directory
            storage_dir = Path(self.hass.config.path(".storage"))
            dashboard_file = storage_dir / f"lovelace.{url_path}"

            # Ensure storage directory exists
            storage_dir.mkdir(exist_ok=True)

            # Write dashboard configuration using async file operations
            async with aiofiles.open(dashboard_file, "w", encoding="utf-8") as file:
                await file.write(
                    json.dumps(dashboard_data, indent=2, ensure_ascii=False)
                )

            _LOGGER.debug("Created dashboard file: %s", dashboard_file)

            return str(dashboard_file)

        except Exception as err:
            _LOGGER.error(
                "Failed to create Lovelace dashboard file: %s", err, exc_info=True
            )
            raise HomeAssistantError(f"Dashboard file creation failed: {err}") from err

    async def _update_lovelace_dashboard(
        self, dashboard_path: str, config: dict[str, Any]
    ) -> None:
        """Update an existing Lovelace dashboard.

        Args:
            dashboard_path: Path to the dashboard file
            config: New dashboard configuration

        Raises:
            HomeAssistantError: If dashboard update fails
        """
        try:
            dashboard_file = Path(dashboard_path)

            if not dashboard_file.exists():
                raise HomeAssistantError(f"Dashboard file not found: {dashboard_path}")

            # Read existing dashboard data
            async with aiofiles.open(dashboard_file, "r", encoding="utf-8") as file:
                content = await file.read()
                dashboard_data = json.loads(content)

            # Update configuration
            dashboard_data["data"]["config"] = config
            dashboard_data["data"]["updated"] = utcnow().isoformat()

            # Write updated dashboard
            async with aiofiles.open(dashboard_file, "w", encoding="utf-8") as file:
                await file.write(
                    json.dumps(dashboard_data, indent=2, ensure_ascii=False)
                )

            _LOGGER.debug("Updated dashboard file: %s", dashboard_file)

        except Exception as err:
            _LOGGER.error("Failed to update Lovelace dashboard: %s", err, exc_info=True)
            raise HomeAssistantError(f"Dashboard update failed: {err}") from err

    async def _delete_lovelace_dashboard(self, dashboard_path: str) -> None:
        """Delete a Lovelace dashboard.

        Args:
            dashboard_path: Path to the dashboard file to delete
        """
        try:
            dashboard_file = Path(dashboard_path)

            # Use async file operations for deletion
            await asyncio.to_thread(dashboard_file.unlink, missing_ok=True)

            _LOGGER.debug("Deleted dashboard file: %s", dashboard_file)

        except Exception as err:
            _LOGGER.error("Failed to delete Lovelace dashboard: %s", err, exc_info=True)
            # Don't raise here - deletion failures shouldn't stop cleanup

    async def _save_dashboards(self) -> None:
        """Save dashboard configurations to storage.

        Raises:
            HomeAssistantError: If saving fails
        """
        try:
            await self._store.async_save(
                {
                    "dashboards": self._dashboards,
                    "updated": utcnow().isoformat(),
                    "version": DASHBOARD_STORAGE_VERSION,
                    "entry_id": self.entry.entry_id,
                }
            )

        except Exception as err:
            _LOGGER.error("Failed to save dashboard storage: %s", err, exc_info=True)
            raise HomeAssistantError(f"Dashboard storage save failed: {err}") from err

    async def _validate_stored_dashboards(self) -> None:
        """Validate and clean up stored dashboards."""
        invalid_dashboards = []

        for url, dashboard_info in self._dashboards.items():
            try:
                # Check if dashboard file still exists
                dashboard_path = dashboard_info.get("path")
                if dashboard_path and not Path(dashboard_path).exists():
                    invalid_dashboards.append(url)
                    continue

                # Validate required fields
                required_fields = ["title", "created", "type"]
                if not all(field in dashboard_info for field in required_fields):
                    invalid_dashboards.append(url)

            except Exception as err:
                _LOGGER.warning("Error validating dashboard %s: %s", url, err)
                invalid_dashboards.append(url)

        # Remove invalid dashboards
        for url in invalid_dashboards:
            _LOGGER.info("Removing invalid dashboard: %s", url)
            self._dashboards.pop(url, None)

        if invalid_dashboards:
            await self._save_dashboards()

    @callback
    def get_dashboard_info(self, dashboard_url: str) -> dict[str, Any] | None:
        """Get information about a specific dashboard.

        Args:
            dashboard_url: URL of the dashboard

        Returns:
            Dashboard information or None if not found
        """
        return self._dashboards.get(dashboard_url)

    @callback
    def get_all_dashboards(self) -> dict[str, dict[str, Any]]:
        """Get information about all dashboards.

        Returns:
            Dictionary of all dashboard information
        """
        return self._dashboards.copy()

    @callback
    def is_initialized(self) -> bool:
        """Check if the dashboard generator is initialized.

        Returns:
            True if initialized
        """
        return self._initialized
