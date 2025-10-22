"""Dashboard template caching system for Paw Control with multiple themes.

This module provides efficient template caching and management for dashboard
card generation with multiple visual themes and layouts. It implements LRU
caching, template validation, and async template loading with various styles.

Quality Scale: Bronze target
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from functools import lru_cache
from math import isfinite
from typing import Any, Final, NotRequired, TypedDict, cast

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from .coordinator_tasks import derive_rejection_metrics
from .dashboard_shared import CardCollection, CardConfig, coerce_dog_configs
from .types import (
    CoordinatorRejectionMetrics,
    CoordinatorStatisticsPayload,
    DogModulesConfig,
    RawDogConfig,
    coerce_dog_modules_config,
)


class WeatherThemeConfig(TypedDict):
    """Color palette for weather dashboards."""

    primary_color: str
    accent_color: str
    success_color: str
    warning_color: str
    danger_color: str


class CardModConfig(TypedDict, total=False):
    """card-mod styling payload shared across templates."""

    style: str


class ThemeIconStyle(TypedDict, total=False):
    """Icon styling flags used by themed dashboards."""

    style: str
    animated: bool
    bounce: bool
    glow: bool


class ThemeColorPalette(TypedDict):
    """Named colors exposed to templates and helper methods."""

    primary: str
    accent: str
    background: str
    text: str


class ThemeStyles(TypedDict):
    """Theme metadata applied to generated card templates."""

    colors: ThemeColorPalette
    card_mod: NotRequired[CardModConfig]
    icons: NotRequired[ThemeIconStyle]


class TemplateCacheStats(TypedDict):
    """Statistics returned by the in-memory template cache."""

    hits: int
    misses: int
    hit_rate: str
    cached_items: int
    max_size: int


class MapCardOptions(TypedDict, total=False):
    """Options that adjust the generated map card template."""

    zoom: int
    default_zoom: int
    dark_mode: bool
    hours_to_show: int


type _MapOptionPairs = Iterable[tuple[str, object]]
type MapOptionsInput = MapCardOptions | Mapping[str, object] | _MapOptionPairs | None


class NotificationLastEvent(TypedDict, total=False):
    """Details about the most recent notification sent for a dog."""

    type: str
    priority: str
    sent_at: str
    title: str
    message: str
    channel: str
    status: str


class NotificationDogOverview(TypedDict, total=False):
    """Per-dog delivery metrics tracked by the notifications dashboard."""

    sent_today: int
    quiet_hours_active: bool
    channels: list[str]
    last_notification: NotRequired[NotificationLastEvent]


class NotificationPerformanceMetrics(TypedDict, total=False):
    """High-level delivery metrics exported by the notifications sensor."""

    notifications_failed: int


class NotificationOverviewAttributes(TypedDict, total=False):
    """Attributes exposed by ``sensor.pawcontrol_notifications``."""

    performance_metrics: NotificationPerformanceMetrics
    per_dog: dict[str, NotificationDogOverview]


_LOGGER = logging.getLogger(__name__)

# Weather dashboard constants
WEATHER_THEMES: Final[dict[str, WeatherThemeConfig]] = {
    "modern": {
        "primary_color": "#2196F3",
        "accent_color": "#FF5722",
        "success_color": "#4CAF50",
        "warning_color": "#FF9800",
        "danger_color": "#F44336",
    },
    "playful": {
        "primary_color": "#FF6B6B",
        "accent_color": "#4ECDC4",
        "success_color": "#95E1D3",
        "warning_color": "#FFE66D",
        "danger_color": "#FF8B94",
    },
    "minimal": {
        "primary_color": "#000000",
        "accent_color": "#666666",
        "success_color": "#333333",
        "warning_color": "#999999",
        "danger_color": "#CCCCCC",
    },
    "dark": {
        "primary_color": "#0F3460",
        "accent_color": "#E94560",
        "success_color": "#16213E",
        "warning_color": "#0F4C75",
        "danger_color": "#3282B8",
    },
}

WEATHER_CARD_TYPES: Final[list[str]] = [
    "weather_status",
    "weather_alerts",
    "weather_recommendations",
    "weather_chart",
    "weather_breed_advisory",
    "weather_action_buttons",
    "weather_dashboard_layout",
]

# Cache configuration
TEMPLATE_CACHE_SIZE: Final[int] = 128
TEMPLATE_TTL_SECONDS: Final[int] = 300  # 5 minutes
MAX_TEMPLATE_SIZE: Final[int] = 1024 * 1024  # 1MB per template

MAP_ZOOM_MIN: Final[int] = 1
MAP_ZOOM_MAX: Final[int] = 20
DEFAULT_MAP_ZOOM: Final[int] = 15
DEFAULT_MAP_HOURS_TO_SHOW: Final[int] = 2
MAP_HISTORY_MIN_HOURS: Final[int] = 1
MAP_HISTORY_MAX_HOURS: Final[int] = 168
MAP_OPTION_KEYS: Final[frozenset[str]] = frozenset(
    {"zoom", "default_zoom", "dark_mode", "hours_to_show"}
)


type CardTemplatePayload = CardConfig | CardCollection


def _clone_template(template: CardTemplatePayload) -> CardTemplatePayload:
    """Return a shallow copy of a cached template payload."""

    if isinstance(template, list):
        return [card.copy() for card in template]
    return template.copy()


class TemplateCache:
    """High-performance template cache with LRU eviction and TTL.

    Provides memory-efficient caching of dashboard card templates with
    automatic expiration and memory management.
    """

    def __init__(self, maxsize: int = TEMPLATE_CACHE_SIZE) -> None:
        """Initialize template cache.

        Args:
            maxsize: Maximum number of templates to cache
        """
        self._cache: dict[str, CardTemplatePayload] = {}
        self._access_times: dict[str, float] = {}
        self._maxsize = maxsize
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> CardTemplatePayload | None:
        """Get template from cache.

        Args:
            key: Template cache key

        Returns:
            Cached template or None if not found/expired
        """
        async with self._lock:
            current_time = dt_util.utcnow().timestamp()

            if key not in self._cache:
                self._misses += 1
                return None

            # Check TTL
            if current_time - self._access_times[key] > TEMPLATE_TTL_SECONDS:
                del self._cache[key]
                del self._access_times[key]
                self._misses += 1
                return None

            # Update access time
            self._access_times[key] = current_time
            self._hits += 1

            return _clone_template(self._cache[key])

    async def set(self, key: str, template: CardTemplatePayload) -> None:
        """Store template in cache.

        Args:
            key: Template cache key
            template: Template to cache
        """
        async with self._lock:
            # Check template size to prevent memory bloat
            template_size = len(json.dumps(template, separators=(",", ":")))
            if template_size > MAX_TEMPLATE_SIZE:
                _LOGGER.warning(
                    "Template %s too large (%d bytes), not caching", key, template_size
                )
                return

            current_time = dt_util.utcnow().timestamp()

            # Evict LRU items if needed
            while len(self._cache) >= self._maxsize:
                await self._evict_lru()

            self._cache[key] = _clone_template(template)
            self._access_times[key] = current_time

    async def _evict_lru(self) -> None:
        """Evict least recently used template."""
        if not self._access_times:
            return

        lru_key = min(self._access_times, key=lambda key: self._access_times[key])
        del self._cache[lru_key]
        del self._access_times[lru_key]

    async def clear(self) -> None:
        """Clear all cached templates."""
        async with self._lock:
            self._cache.clear()
            self._access_times.clear()

    @callback
    def get_stats(self) -> TemplateCacheStats:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        stats: TemplateCacheStats = {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "cached_items": len(self._cache),
            "max_size": self._maxsize,
        }

        return stats


class DashboardTemplates:
    """Dashboard template manager with caching, themes, and multiple layouts.

    Provides efficient template generation and caching for dashboard cards
    with automatic optimization based on usage patterns and multiple visual themes.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize template manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._cache = TemplateCache()

    @lru_cache(maxsize=64)  # noqa: B019
    def _get_base_card_template(self, card_type: str) -> CardConfig:
        """Get base template for card type with LRU caching.

        Args:
            card_type: Type of card to get template for

        Returns:
            Base card template
        """
        base_templates: dict[str, CardConfig] = {
            "status": {
                "type": "entities",
                "state_color": True,
                "show_header_toggle": False,
            },
            "button": {
                "type": "button",
                "show_state": True,
                "show_icon": True,
            },
            "horizontal_stack": {
                "type": "horizontal-stack",
                "cards": [],
            },
            "vertical_stack": {
                "type": "vertical-stack",
                "cards": [],
            },
            "grid": {
                "type": "grid",
                "columns": 2,
                "cards": [],
            },
            "map": {
                "type": "map",
                "default_zoom": DEFAULT_MAP_ZOOM,
                "dark_mode": False,
                "hours_to_show": DEFAULT_MAP_HOURS_TO_SHOW,
            },
            "history_graph": {
                "type": "history-graph",
                "hours_to_show": 24,
                "refresh_interval": 0,
            },
            "statistics_graph": {
                "type": "statistics-graph",
                "stat_types": ["mean", "min", "max"],
                "days_to_show": 30,
            },
            "markdown": {
                "type": "markdown",
                "content": "",
            },
            "conditional": {
                "type": "conditional",
                "conditions": [],
                "card": {},
            },
            "gauge": {
                "type": "gauge",
                "min": 0,
                "max": 100,
                "unit": "%",
            },
            "picture_elements": {
                "type": "picture-elements",
                "elements": [],
            },
            "custom:mushroom-entity": {
                "type": "custom:mushroom-entity",
                "icon_color": "blue",
                "fill_container": True,
            },
            "custom:mini-graph-card": {
                "type": "custom:mini-graph-card",
                "hours_to_show": 24,
                "points_per_hour": 2,
                "line_width": 2,
            },
        }

        template = base_templates.get(card_type)
        if template is None:
            return {"type": card_type}

        return template.copy()

    def _get_theme_styles(self, theme: str = "modern") -> ThemeStyles:
        """Get theme-specific styling options.

        Args:
            theme: Theme name (modern, playful, minimal, dark)

        Returns:
            Theme styling dictionary
        """
        themes: dict[str, ThemeStyles] = {
            "modern": {
                "card_mod": {
                    "style": """
                        ha-card {
                            background: linear-gradient(135deg, rgba(255,255,255,0.9) 0%, rgba(250,250,250,0.95) 100%);
                            border-radius: 16px;
                            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                            transition: all 0.3s ease;
                        }
                        ha-card:hover {
                            transform: translateY(-2px);
                            box-shadow: 0 8px 30px rgba(0,0,0,0.12);
                        }
                    """
                },
                "colors": {
                    "primary": "#2196F3",
                    "accent": "#FF5722",
                    "background": "#FAFAFA",
                    "text": "#212121",
                },
                "icons": {
                    "style": "rounded",
                    "animated": True,
                },
            },
            "playful": {
                "card_mod": {
                    "style": """
                        ha-card {
                            background: linear-gradient(45deg, #FF6B6B 0%, #4ECDC4 100%);
                            border-radius: 24px;
                            border: 3px solid white;
                            box-shadow: 0 8px 32px rgba(31,38,135,0.37);
                            backdrop-filter: blur(4px);
                            animation: float 6s ease-in-out infinite;
                        }
                        @keyframes float {
                            0% { transform: translateY(0px); }
                            50% { transform: translateY(-10px); }
                            100% { transform: translateY(0px); }
                        }
                    """
                },
                "colors": {
                    "primary": "#FF6B6B",
                    "accent": "#4ECDC4",
                    "background": "#FFE66D",
                    "text": "#292F36",
                },
                "icons": {
                    "style": "emoji",
                    "animated": True,
                    "bounce": True,
                },
            },
            "minimal": {
                "card_mod": {
                    "style": """
                        ha-card {
                            background: white;
                            border-radius: 4px;
                            border: 1px solid #E0E0E0;
                            box-shadow: none;
                        }
                    """
                },
                "colors": {
                    "primary": "#000000",
                    "accent": "#666666",
                    "background": "#FFFFFF",
                    "text": "#000000",
                },
                "icons": {
                    "style": "outlined",
                    "animated": False,
                },
            },
            "dark": {
                "card_mod": {
                    "style": """
                        ha-card {
                            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                            border-radius: 12px;
                            border: 1px solid rgba(255,255,255,0.1);
                            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
                        }
                    """
                },
                "colors": {
                    "primary": "#0F3460",
                    "accent": "#E94560",
                    "background": "#1A1A2E",
                    "text": "#FFFFFF",
                },
                "icons": {
                    "style": "filled",
                    "animated": True,
                    "glow": True,
                },
            },
        }

        return themes.get(theme, themes["modern"])

    def _card_mod(self, theme_styles: ThemeStyles) -> CardModConfig:
        """Return a mutable card-mod payload for template assembly."""

        card_mod = theme_styles.get("card_mod")
        if card_mod is None:
            return cast(CardModConfig, {})
        return cast(CardModConfig, card_mod.copy())

    @staticmethod
    def _parse_int(value: object, *, default: int = 0) -> int:
        """Return an integer coerced from ``value`` with ``default`` fallback."""

        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return default
        return default

    @staticmethod
    def _parse_bool(value: object) -> bool:
        """Return a boolean coerced from arbitrary payloads."""

        if isinstance(value, bool):
            return value
        if isinstance(value, int | float):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    @staticmethod
    def _parse_channels(value: object) -> list[str]:
        """Return a list of channel labels extracted from ``value``."""

        if isinstance(value, str):
            return [
                chunk for chunk in (part.strip() for part in value.split(",")) if chunk
            ]

        if isinstance(value, Sequence) and not isinstance(
            value, str | bytes | bytearray
        ):
            channels: list[str] = []
            for item in value:
                candidate = item.strip() if isinstance(item, str) else str(item).strip()
                if candidate:
                    channels.append(candidate)
            return channels

        return []

    @staticmethod
    def _parse_last_notification(value: object) -> NotificationLastEvent | None:
        """Return a structured notification payload extracted from ``value``."""

        if not isinstance(value, Mapping):
            return None

        event: NotificationLastEvent = {}

        for key in ("type", "priority", "title", "message", "channel", "status"):
            raw = value.get(key)
            if raw is None:
                continue
            event[key] = str(raw)

        sent_at = value.get("sent_at")
        if isinstance(sent_at, str):
            event["sent_at"] = sent_at
        elif sent_at is not None:
            event["sent_at"] = str(sent_at)

        return event or None

    @staticmethod
    def _normalise_notifications_state(
        state: State | None,
    ) -> tuple[NotificationPerformanceMetrics, dict[str, NotificationDogOverview]]:
        """Return typed metrics extracted from ``sensor.pawcontrol_notifications``."""

        metrics: NotificationPerformanceMetrics = {"notifications_failed": 0}
        per_dog: dict[str, NotificationDogOverview] = {}

        if state is None:
            return metrics, per_dog

        attributes = getattr(state, "attributes", None)
        if not isinstance(attributes, Mapping):
            return metrics, per_dog

        raw_metrics = attributes.get("performance_metrics")
        if isinstance(raw_metrics, Mapping):
            metrics["notifications_failed"] = DashboardTemplates._parse_int(
                raw_metrics.get("notifications_failed"),
                default=0,
            )

        raw_per_dog = attributes.get("per_dog")
        if isinstance(raw_per_dog, Mapping):
            for dog_id, raw_stats in raw_per_dog.items():
                if not isinstance(dog_id, str) or not isinstance(raw_stats, Mapping):
                    continue

                dog_overview: NotificationDogOverview = {
                    "sent_today": DashboardTemplates._parse_int(
                        raw_stats.get("sent_today"),
                        default=0,
                    ),
                    "quiet_hours_active": DashboardTemplates._parse_bool(
                        raw_stats.get("quiet_hours_active")
                    ),
                    "channels": DashboardTemplates._parse_channels(
                        raw_stats.get("channels")
                    ),
                }

                last_notification = DashboardTemplates._parse_last_notification(
                    raw_stats.get("last_notification")
                )
                if last_notification is not None:
                    dog_overview["last_notification"] = last_notification

                per_dog[dog_id] = dog_overview

        return metrics, per_dog

    async def get_dog_status_card_template(
        self,
        dog_id: str,
        dog_name: str,
        modules: DogModulesConfig,
        theme: str = "modern",
    ) -> CardConfig:
        """Get themed dog status card template.

        Args:
            dog_id: Dog identifier
            dog_name: Dog display name
            modules: Enabled modules for the dog
            theme: Visual theme to apply

        Returns:
            Complete status card template with theme
        """
        cache_key = f"dog_status_{dog_id}_{hash(frozenset(modules.items()))}_{theme}"

        # Try cache first
        cached = await self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        # Generate template
        template = await self._generate_dog_status_template(
            dog_id, dog_name, modules, theme
        )

        # Cache for future use
        await self._cache.set(cache_key, template)

        return template

    async def _generate_dog_status_template(
        self,
        dog_id: str,
        dog_name: str,
        modules: DogModulesConfig,
        theme: str = "modern",
    ) -> CardConfig:
        """Generate themed dog status card template.

        Args:
            dog_id: Dog identifier
            dog_name: Dog display name
            modules: Enabled modules
            theme: Visual theme

        Returns:
            Status card template with theme styling
        """
        base_template = self._get_base_card_template("status")
        theme_styles = self._get_theme_styles(theme)

        # Core entities - always present
        entities = [
            f"sensor.{dog_id}_status",
            f"sensor.{dog_id}_last_activity",
        ]

        # Add module-specific entities
        if modules.get("feeding"):
            entities.extend(
                [
                    f"sensor.{dog_id}_last_fed",
                    f"sensor.{dog_id}_meals_today",
                    f"sensor.{dog_id}_daily_food_consumed",
                ]
            )

        if modules.get("walk"):
            entities.extend(
                [
                    f"binary_sensor.{dog_id}_is_walking",
                    f"sensor.{dog_id}_last_walk",
                    f"sensor.{dog_id}_daily_walk_time",
                ]
            )

        if modules.get("health"):
            entities.extend(
                [
                    f"sensor.{dog_id}_weight",
                    f"sensor.{dog_id}_health_status",
                    f"sensor.{dog_id}_health_score",
                ]
            )

        if modules.get("gps"):
            entities.extend(
                [
                    f"device_tracker.{dog_id}_location",
                    f"sensor.{dog_id}_distance_from_home",
                    f"sensor.{dog_id}_current_speed",
                ]
            )

        # Build template with theme
        template = {
            **base_template,
            "title": f"{self._get_dog_emoji(theme)} {dog_name} Status",
            "entities": entities,
            "card_mod": self._card_mod(theme_styles),
        }

        # Add theme-specific enhancements
        if theme == "playful":
            template["icon"] = "mdi:dog-side"
            template["icon_color"] = theme_styles["colors"]["primary"]
        elif theme == "modern":
            template["show_state"] = True
            template["state_color"] = True

        return template

    def _get_dog_emoji(self, theme: str) -> str:
        """Get theme-appropriate dog emoji.

        Args:
            theme: Theme name

        Returns:
            Dog emoji for the theme
        """
        emojis = {
            "modern": "🐕",
            "playful": "🐶",
            "minimal": "•",
            "dark": "🌙",
        }
        return emojis.get(theme, "🐕")

    async def get_action_buttons_template(
        self,
        dog_id: str,
        modules: DogModulesConfig,
        theme: str = "modern",
        layout: str = "cards",
    ) -> CardCollection:
        """Get themed action buttons template for dog."""
        cache_key = f"action_buttons_{dog_id}_{hash(frozenset(modules.items()))}_{theme}_{layout}"

        cached = await self._cache.get(cache_key)
        if isinstance(cached, list):
            return cached

        base_button = self._get_base_card_template("button")
        theme_styles = self._get_theme_styles(theme)
        button_style = self._get_button_style(theme)

        buttons: CardCollection = []
        if modules.get("feeding"):
            buttons.append(
                self._create_feeding_button(
                    dog_id, base_button, button_style, theme_styles, theme
                )
            )

        if modules.get("walk"):
            buttons.extend(
                self._create_walk_buttons(
                    dog_id, base_button, button_style, theme_styles, theme
                )
            )

        if modules.get("health"):
            buttons.append(
                self._create_health_button(
                    dog_id, base_button, button_style, theme_styles, theme
                )
            )

        result = self._wrap_buttons_layout(buttons, layout)
        if result is None:
            result = buttons

        await self._cache.set(cache_key, result)
        return result

    def _gradient_style(self, primary: str, secondary: str) -> CardConfig:
        """Return gradient card_mod style with provided colors."""
        return {
            "card_mod": {
                "style": f"""
                    ha-card {{
                        background: linear-gradient(135deg, {primary} 0%, {secondary} 100%);
                        color: white;
                        border-radius: 12px;
                        transition: all 0.3s;
                    }}
                    ha-card:hover {{
                        transform: scale(1.05);
                    }}
                """,
            }
        }

    def _get_button_style(self, theme: str) -> CardConfig:
        """Return card style based on theme."""
        if theme == "modern":
            return self._gradient_style("#667eea", "#764ba2")
        elif theme == "playful":
            return {
                "card_mod": {
                    "style": """
                        ha-card {
                            background: linear-gradient(45deg, #f093fb 0%, #f5576c 100%);
                            color: white;
                            border-radius: 50px;
                            animation: pulse 2s infinite;
                        }
                        @keyframes pulse {
                            0% { box-shadow: 0 0 0 0 rgba(245,87,108,0.7); }
                            70% { box-shadow: 0 0 0 10px rgba(245,87,108,0); }
                            100% { box-shadow: 0 0 0 0 rgba(245,87,108,0); }
                        }
                    """,
                }
            }
        return {}

    def _create_feeding_button(
        self,
        dog_id: str,
        base_button: CardConfig,
        button_style: CardConfig,
        theme_styles: ThemeStyles,
        theme: str,
    ) -> CardConfig:
        """Create feeding button card."""
        return {
            **base_button,
            **button_style,
            "name": "Feed",
            "icon": "mdi:food-drumstick" if theme != "playful" else "mdi:bone",
            "icon_color": theme_styles["colors"]["accent"],
            "tap_action": {
                "action": "call-service",
                "service": f"{DOMAIN}.feed_dog",
                "service_data": {"dog_id": dog_id, "meal_type": "regular"},
            },
        }

    def _create_walk_buttons(
        self,
        dog_id: str,
        base_button: CardConfig,
        button_style: CardConfig,
        theme_styles: ThemeStyles,
        theme: str,
    ) -> CardCollection:
        """Create start/end walk buttons."""
        walk_style = (
            self._gradient_style("#00bfa5", "#00acc1")
            if theme == "modern"
            else button_style
        )

        return [
            {
                "type": "conditional",
                "conditions": [
                    {"entity": f"binary_sensor.{dog_id}_is_walking", "state": "off"}
                ],
                "card": {
                    **base_button,
                    **walk_style,
                    "name": "Start Walk",
                    "icon": "mdi:walk",
                    "icon_color": theme_styles["colors"]["primary"],
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
                    {"entity": f"binary_sensor.{dog_id}_is_walking", "state": "on"}
                ],
                "card": {
                    **base_button,
                    **walk_style,
                    "name": "End Walk",
                    "icon": "mdi:stop",
                    "icon_color": "red",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.end_walk",
                        "service_data": {"dog_id": dog_id},
                    },
                },
            },
        ]

    def _create_health_button(
        self,
        dog_id: str,
        base_button: CardConfig,
        button_style: CardConfig,
        theme_styles: ThemeStyles,
        theme: str,
    ) -> CardConfig:
        """Create health check button."""
        health_style = (
            self._gradient_style("#e91e63", "#f06292")
            if theme == "modern"
            else button_style
        )

        return {
            **base_button,
            **health_style,
            "name": "Health Check",
            "icon": "mdi:heart-pulse",
            "icon_color": theme_styles["colors"]["accent"],
            "tap_action": {
                "action": "call-service",
                "service": f"{DOMAIN}.log_health",
                "service_data": {"dog_id": dog_id},
            },
        }

    def _wrap_buttons_layout(
        self, buttons: CardCollection, layout: str
    ) -> CardCollection | None:
        """Wrap buttons in layout-specific containers."""
        if layout == "grid":
            return [{"type": "grid", "columns": 3, "cards": buttons}]
        if layout == "panels":
            return [{"type": "horizontal-stack", "cards": buttons[:3]}]
        return None

    @staticmethod
    def _normalise_map_options(
        options: MapOptionsInput,
    ) -> MapCardOptions:
        """Return a typed ``MapCardOptions`` payload extracted from ``options``."""

        resolved: MapCardOptions = {
            "zoom": DEFAULT_MAP_ZOOM,
            "default_zoom": DEFAULT_MAP_ZOOM,
            "hours_to_show": DEFAULT_MAP_HOURS_TO_SHOW,
        }

        if not options:
            return resolved

        options_mapping: Mapping[str, object]

        if isinstance(options, Mapping):
            filtered_options: dict[str, object] = {}
            for key, value in options.items():
                if not isinstance(key, str):
                    _LOGGER.debug(
                        "Skipping map option entry with non-string key from mapping: %r",
                        key,
                    )
                    continue

                if key not in MAP_OPTION_KEYS:
                    _LOGGER.debug(
                        "Ignoring unsupported map option key '%s' from mapping payload",
                        key,
                    )
                    continue

                filtered_options[key] = value

            if not filtered_options:
                _LOGGER.debug(
                    "Ignoring map options mapping payload without supported entries: %s",
                    type(options).__name__,
                )
                return resolved

            options_mapping = filtered_options
        elif isinstance(options, Iterable) and not isinstance(options, str | bytes):
            candidate_pairs: list[tuple[str, object]] = []
            for item in options:
                if isinstance(item, Mapping):
                    for key, value in item.items():
                        if not isinstance(key, str):
                            _LOGGER.debug(
                                "Skipping map option entry with non-string key from mapping: %r",
                                key,
                            )
                            continue

                        if key not in MAP_OPTION_KEYS:
                            _LOGGER.debug(
                                "Ignoring unsupported map option key '%s' from iterable mapping",
                                key,
                            )
                            continue

                        candidate_pairs.append((key, value))
                    continue

                if (
                    isinstance(item, Sequence)
                    and not isinstance(item, str | bytes)
                    and len(item) == 2
                ):
                    key, value = item
                    if isinstance(key, str):
                        if key not in MAP_OPTION_KEYS:
                            _LOGGER.debug(
                                "Ignoring unsupported map option key '%s' from iterable pair",
                                key,
                            )
                            continue

                        candidate_pairs.append((key, value))
                    else:
                        _LOGGER.debug(
                            "Skipping map option entry with non-string key: %r", key
                        )
                else:
                    _LOGGER.debug(
                        "Skipping unsupported map option entry: %s", type(item).__name__
                    )

            if not candidate_pairs:
                _LOGGER.debug(
                    "Ignoring map options iterable payload without usable entries: %s",
                    type(options).__name__,
                )
                return resolved

            options_mapping = dict(candidate_pairs)
        else:
            _LOGGER.debug(
                "Ignoring map options payload with unsupported type: %s",
                type(options).__name__,
            )
            return resolved

        def _coerce_int(candidate: object | None) -> int | None:
            """Convert ``candidate`` to ``int`` when possible."""

            if candidate is None:
                return None
            if isinstance(candidate, bool):
                return None
            if isinstance(candidate, int):
                return candidate
            if isinstance(candidate, float):
                if not isfinite(candidate):
                    return None
                return int(candidate)
            if isinstance(candidate, str):
                stripped = candidate.strip()
                if not stripped:
                    return None
                try:
                    numeric = float(stripped)
                except ValueError:
                    return None
                if not isfinite(numeric):
                    return None
                return int(numeric)
            return None

        zoom_candidate = options_mapping.get("zoom")
        zoom_value = _coerce_int(zoom_candidate)
        if zoom_value is not None:
            resolved_zoom = max(MAP_ZOOM_MIN, min(MAP_ZOOM_MAX, zoom_value))
            resolved["zoom"] = resolved_zoom

        default_zoom_candidate = options_mapping.get("default_zoom")
        default_zoom_value = _coerce_int(default_zoom_candidate)
        if default_zoom_value is not None:
            resolved_default_zoom = max(
                MAP_ZOOM_MIN, min(MAP_ZOOM_MAX, default_zoom_value)
            )
            resolved["default_zoom"] = resolved_default_zoom
            if zoom_value is None:
                resolved["zoom"] = resolved_default_zoom
        elif zoom_value is not None:
            # Mirror the explicitly provided zoom when no default override exists.
            resolved["default_zoom"] = resolved["zoom"]

        dark_mode = options_mapping.get("dark_mode")
        if isinstance(dark_mode, bool):
            resolved["dark_mode"] = dark_mode
        elif isinstance(dark_mode, int | float):
            resolved["dark_mode"] = bool(dark_mode)
        elif isinstance(dark_mode, str):
            lowered = dark_mode.strip().casefold()
            if lowered in {"1", "true", "yes", "on"}:
                resolved["dark_mode"] = True
            elif lowered in {"0", "false", "no", "off"}:
                resolved["dark_mode"] = False

        hours_candidate = options_mapping.get("hours_to_show")
        hours_value = _coerce_int(hours_candidate)
        if hours_value is not None:
            resolved["hours_to_show"] = max(
                MAP_HISTORY_MIN_HOURS, min(MAP_HISTORY_MAX_HOURS, hours_value)
            )

        return resolved

    async def get_map_card_template(
        self,
        dog_id: str,
        options: MapOptionsInput = None,
        theme: str = "modern",
    ) -> CardConfig:
        """Get themed GPS map card template.

        Args:
            dog_id: Dog identifier
            options: Map display options
            theme: Visual theme

        Returns:
            Map card template with theme styling
        """
        resolved_options = self._normalise_map_options(options)
        self._get_theme_styles(theme)

        resolved_zoom = resolved_options.get("zoom")
        resolved_default_zoom = resolved_options.get("default_zoom")

        if resolved_zoom is None and resolved_default_zoom is not None:
            resolved_zoom = resolved_default_zoom
        elif resolved_zoom is not None and resolved_default_zoom is None:
            resolved_default_zoom = resolved_zoom

        final_zoom = resolved_zoom if resolved_zoom is not None else DEFAULT_MAP_ZOOM
        final_default_zoom = (
            resolved_default_zoom if resolved_default_zoom is not None else final_zoom
        )

        dark_mode_override = resolved_options.get("dark_mode")
        dark_mode_enabled = (
            theme == "dark" if dark_mode_override is None else dark_mode_override
        )

        template = {
            **self._get_base_card_template("map"),
            "entities": [f"device_tracker.{dog_id}_location"],
            "default_zoom": final_default_zoom,
            "zoom": final_zoom,
            "dark_mode": dark_mode_enabled,
            "hours_to_show": resolved_options.get(
                "hours_to_show", DEFAULT_MAP_HOURS_TO_SHOW
            ),
        }

        # Add theme-specific map styling
        if theme == "modern":
            template["card_mod"] = {
                "style": """
                    ha-card {
                        border-radius: 16px;
                        overflow: hidden;
                    }
                """
            }
        elif theme == "playful":
            template["card_mod"] = {
                "style": """
                    ha-card {
                        border-radius: 24px;
                        border: 4px solid #4ECDC4;
                    }
                """
            }

        return template

    async def get_statistics_card_template(
        self,
        dog_id: str,
        dog_name: str,
        modules: DogModulesConfig,
        theme: str = "modern",
    ) -> CardConfig:
        """Get themed statistics card template.

        Args:
            dog_id: Dog identifier
            dog_name: Dog name
            modules: Enabled modules
            theme: Visual theme

        Returns:
            Statistics card template
        """
        theme_styles = self._get_theme_styles(theme)

        # Build statistics based on enabled modules
        stats_content = f"## 📊 {dog_name} Statistics\n\n"

        if modules.get("feeding"):
            stats_content += f"""
### 🍖 Feeding
- **Today's Meals**: {{{{ states('sensor.{dog_id}_meals_today') }}}}
- **Daily Amount**: {{{{ states('sensor.{dog_id}_daily_food_consumed') }}}}g
- **Schedule Adherence**: {{{{ states('sensor.{dog_id}_feeding_schedule_adherence') }}}}%
"""

        if modules.get("walk"):
            stats_content += f"""
### 🚶 Walking
- **Daily Walk Time**: {{{{ states('sensor.{dog_id}_daily_walk_time') }}}} min
- **Daily Distance**: {{{{ states('sensor.{dog_id}_daily_walk_distance') }}}} km
- **Walk Goal**: {{{{ states('sensor.{dog_id}_walk_goal_progress') }}}}%
"""

        if modules.get("health"):
            stats_content += f"""
### ❤️ Health
- **Weight**: {{{{ states('sensor.{dog_id}_weight') }}}} kg
- **Health Score**: {{{{ states('sensor.{dog_id}_health_score') }}}}/100
- **Activity Level**: {{{{ states('sensor.{dog_id}_activity_level') }}}}
"""

        template: CardConfig = {
            "type": "markdown",
            "content": stats_content,
            "card_mod": self._card_mod(theme_styles),
        }

        return template

    async def get_statistics_graph_template(
        self,
        title: str,
        entities: Sequence[str],
        stat_types: Sequence[str],
        *,
        days_to_show: int,
        theme: str = "modern",
    ) -> CardConfig | None:
        """Return a typed statistics-graph card for analytics dashboards."""

        if not entities:
            return None

        theme_styles = self._get_theme_styles(theme)
        card_mod = self._card_mod(theme_styles)

        template: CardConfig = {
            "type": "statistics-graph",
            "title": title,
            "entities": list(entities),
            "stat_types": list(stat_types),
            "days_to_show": days_to_show,
        }

        if card_mod:
            template["card_mod"] = card_mod

        return template

    def get_statistics_summary_template(
        self,
        dogs: Sequence[RawDogConfig],
        theme: str = "modern",
        *,
        coordinator_statistics: CoordinatorStatisticsPayload
        | Mapping[str, Any]
        | None = None,
    ) -> CardConfig:
        """Return a summary markdown card for analytics dashboards."""

        typed_dogs = coerce_dog_configs(dogs)

        module_counts = {
            MODULE_FEEDING: 0,
            MODULE_WALK: 0,
            MODULE_HEALTH: 0,
            MODULE_GPS: 0,
            MODULE_NOTIFICATIONS: 0,
        }

        for dog in typed_dogs:
            modules = coerce_dog_modules_config(dog.get("modules"))
            for module_name in module_counts:
                if modules.get(module_name):
                    module_counts[module_name] += 1

        content_lines = [
            "## Paw Control Statistics",
            "",
            f"**Dogs managed:** {len(typed_dogs)}",
            "",
            "**Active modules:**",
            f"- Feeding: {module_counts[MODULE_FEEDING]}",
            f"- Walks: {module_counts[MODULE_WALK]}",
            f"- Health: {module_counts[MODULE_HEALTH]}",
            f"- GPS: {module_counts[MODULE_GPS]}",
            f"- Notifications: {module_counts[MODULE_NOTIFICATIONS]}",
            "",
            "*Last updated: {{ now().strftime('%Y-%m-%d %H:%M') }}*",
        ]

        metrics_payload: CoordinatorRejectionMetrics | None = None
        if isinstance(coordinator_statistics, Mapping):
            raw_metrics = coordinator_statistics.get("rejection_metrics")
            if isinstance(raw_metrics, Mapping):
                metrics_payload = derive_rejection_metrics(
                    cast(Mapping[str, Any], raw_metrics)
                )

        if metrics_payload is not None:
            rejection_rate = metrics_payload["rejection_rate"]
            if rejection_rate is not None and isfinite(rejection_rate):
                rate_display = f"{rejection_rate * 100:.2f}%"
            else:
                rate_display = "n/a"

            last_rejection_value = metrics_payload["last_rejection_time"]
            if last_rejection_value is not None:
                try:
                    last_rejection_iso = datetime.fromtimestamp(
                        float(last_rejection_value),
                        tz=UTC,
                    ).isoformat()
                except Exception:  # pragma: no cover - defensive guard
                    last_rejection_iso = str(last_rejection_value)
            else:
                last_rejection_iso = "never"

            breaker_label = (
                metrics_payload["last_rejection_breaker_name"]
                or metrics_payload["last_rejection_breaker_id"]
                or "n/a"
            )

            content_lines.extend(
                [
                    "",
                    "### Resilience metrics",
                    (f"- Rejected calls: {metrics_payload['rejected_call_count']}"),
                    (
                        "- Rejecting breakers: "
                        f"{metrics_payload['rejection_breaker_count']}"
                    ),
                    f"- Rejection rate: {rate_display}",
                    f"- Last rejection: {last_rejection_iso}",
                ]
            )

            if breaker_label != "n/a":
                content_lines.append(f"- Last rejecting breaker: {breaker_label}")

        theme_styles = self._get_theme_styles(theme)

        return {
            "type": "markdown",
            "title": "Summary",
            "content": "\n".join(content_lines),
            "card_mod": self._card_mod(theme_styles),
        }

    async def get_notification_settings_card_template(
        self,
        dog_id: str,
        dog_name: str,
        entities: Sequence[str],
        theme: str = "modern",
    ) -> CardConfig | None:
        """Return the notification control entities card."""

        if not entities:
            return None

        theme_styles = self._get_theme_styles(theme)

        return {
            "type": "entities",
            "title": f"🔔 {dog_name} Notification Controls",
            "entities": list(entities),
            "state_color": True,
            "card_mod": self._card_mod(theme_styles),
        }

    async def get_notifications_overview_card_template(
        self,
        dog_id: str,
        dog_name: str,
        theme: str = "modern",
    ) -> CardConfig:
        """Return a markdown overview for the notification dashboard."""

        theme_styles = self._get_theme_styles(theme)
        card_mod = self._card_mod(theme_styles)

        notifications_state = self.hass.states.get("sensor.pawcontrol_notifications")
        metrics, per_dog = self._normalise_notifications_state(notifications_state)

        default_overview: NotificationDogOverview = {
            "sent_today": 0,
            "quiet_hours_active": False,
            "channels": [],
        }
        dog_overview = per_dog.get(dog_id, default_overview)

        sent_today = dog_overview.get("sent_today", 0)
        failed_deliveries = metrics.get("notifications_failed", 0)
        quiet_hours_active = dog_overview.get("quiet_hours_active", False)
        channels = dog_overview.get("channels", [])
        last_notification = dog_overview.get("last_notification")

        quiet_hours_display = "✅" if quiet_hours_active else "❌"

        content_lines = [
            f"## 🔔 Notification Overview for {dog_name}",
            "",
            f"**Notifications Sent Today:** {sent_today}",
            f"**Failed Deliveries:** {failed_deliveries}",
            f"**Quiet Hours Active:** {quiet_hours_display}",
            "",
            "### Preferred Channels",
        ]

        if channels:
            content_lines.extend(f"• {channel.capitalize()}" for channel in channels)
        else:
            content_lines.append("• Using default integration channels")

        content_lines.append("")
        content_lines.append("### Recent Notification")
        if last_notification:
            notification_type = str(
                last_notification.get("type", "unknown") or "unknown"
            )
            priority_raw = last_notification.get("priority", "normal")
            priority = (
                str(priority_raw).capitalize() if priority_raw is not None else "Normal"
            )
            sent_at_raw = last_notification.get("sent_at", "unknown")
            sent_at = str(sent_at_raw) if sent_at_raw is not None else "unknown"

            content_lines.extend(
                [
                    f"- **Type:** {notification_type}",
                    f"- **Priority:** {priority}",
                    f"- **Sent:** {sent_at}",
                ]
            )
        else:
            content_lines.append("No notifications recorded for this dog yet.")

        content = "\n".join(content_lines)

        return {
            "type": "markdown",
            "content": content,
            "card_mod": card_mod,
        }

    async def get_notifications_actions_card_template(
        self,
        dog_id: str,
        theme: str = "modern",
    ) -> CardConfig:
        """Return quick action buttons for notification workflows."""

        theme_styles = self._get_theme_styles(theme)
        base_button = self._get_base_card_template("button")

        buttons: CardCollection = [
            {
                **base_button,
                "name": "Send Test Notification",
                "icon": "mdi:bell-check",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.send_notification",
                    "service_data": {
                        "dog_id": dog_id,
                        "notification_type": "system_info",
                        "title": "PawControl Diagnostics",
                        "message": "Test notification from dashboard",
                    },
                },
            },
            {
                **base_button,
                "name": "Reset Quiet Hours",
                "icon": "mdi:weather-night",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.configure_alerts",
                    "service_data": {
                        "dog_id": dog_id,
                        "feeding_alerts": True,
                        "walk_alerts": True,
                        "health_alerts": True,
                        "gps_alerts": True,
                    },
                },
            },
        ]

        return {
            "type": "horizontal-stack",
            "cards": buttons,
            "card_mod": self._card_mod(theme_styles),
        }

    async def get_feeding_schedule_template(
        self, dog_id: str, theme: str = "modern"
    ) -> CardConfig:
        """Get themed feeding schedule template.

        Args:
            dog_id: Dog identifier
            theme: Visual theme

        Returns:
            Feeding schedule card template
        """
        theme_styles = self._get_theme_styles(theme)

        template: CardConfig
        if theme == "modern":
            # Use a clean timeline view
            template = {
                "type": "custom:scheduler-card",
                "title": "🍽️ Feeding Schedule",
                "discover_existing": False,
                "standard_configuration": True,
                "entities": [f"sensor.{dog_id}_feeding_schedule"],
                "card_mod": self._card_mod(theme_styles),
            }
        elif theme == "playful":
            # Use colorful meal buttons
            template = await self.get_feeding_controls_template(dog_id, theme)
        else:
            # Minimal text-based schedule
            template = {
                "type": "entities",
                "title": "Feeding Schedule",
                "entities": [
                    f"sensor.{dog_id}_breakfast_time",
                    f"sensor.{dog_id}_lunch_time",
                    f"sensor.{dog_id}_dinner_time",
                ],
            }

        return template

    async def get_feeding_controls_template(
        self, dog_id: str, theme: str = "modern"
    ) -> CardConfig:
        """Get themed feeding control buttons template.

        Args:
            dog_id: Dog identifier
            theme: Visual theme

        Returns:
            Feeding controls template
        """
        base_button = self._get_base_card_template("button")
        self._get_theme_styles(theme)

        meal_types = [
            ("breakfast", "Breakfast", "mdi:weather-sunny", "#FFA726"),
            ("lunch", "Lunch", "mdi:weather-partly-cloudy", "#66BB6A"),
            ("dinner", "Dinner", "mdi:weather-night", "#5C6BC0"),
            ("snack", "Snack", "mdi:cookie", "#EC407A"),
        ]

        buttons: CardCollection = []
        for meal_type, name, icon, color in meal_types:
            button_style = {}

            if theme == "modern":
                button_style = {
                    "card_mod": {
                        "style": f"""
                            ha-card {{
                                background: linear-gradient(135deg, {color} 0%, {color}CC 100%);
                                color: white;
                                border-radius: 12px;
                            }}
                        """
                    }
                }
            elif theme == "playful":
                button_style = {
                    "card_mod": {
                        "style": f"""
                            ha-card {{
                                background: {color};
                                color: white;
                                border-radius: 50%;
                                width: 80px;
                                height: 80px;
                                animation: bounce 1s infinite;
                            }}
                            @keyframes bounce {{
                                0%, 100% {{ transform: translateY(0); }}
                                50% {{ transform: translateY(-10px); }}
                            }}
                        """
                    }
                }

            buttons.append(
                {
                    **base_button,
                    **button_style,
                    "name": name,
                    "icon": icon,
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.feed_dog",
                        "service_data": {
                            "dog_id": dog_id,
                            "meal_type": meal_type,
                        },
                    },
                }
            )

        # Group buttons based on theme
        if theme == "playful":
            # Circular arrangement
            return {
                "type": "horizontal-stack",
                "cards": buttons,
            }
        else:
            # Grid arrangement
            grouped_buttons: CardCollection = []
            for i in range(0, len(buttons), 2):
                button_pair = buttons[i : i + 2]
                grouped_buttons.append(
                    {
                        "type": "horizontal-stack",
                        "cards": button_pair,
                    }
                )

            return {
                "type": "vertical-stack",
                "cards": grouped_buttons,
            }

    async def get_health_charts_template(
        self, dog_id: str, theme: str = "modern"
    ) -> CardConfig:
        """Get themed health charts template.

        Args:
            dog_id: Dog identifier
            theme: Visual theme

        Returns:
            Health charts template
        """
        theme_styles = self._get_theme_styles(theme)

        template: CardConfig
        if theme in ["modern", "dark"]:
            # Use advanced graph card
            template = {
                "type": "custom:mini-graph-card",
                "name": "Health Metrics",
                "entities": [
                    {
                        "entity": f"sensor.{dog_id}_weight",
                        "name": "Weight",
                        "color": theme_styles["colors"]["primary"],
                    },
                    {
                        "entity": f"sensor.{dog_id}_health_score",
                        "name": "Health Score",
                        "color": theme_styles["colors"]["accent"],
                        "y_axis": "secondary",
                    },
                ],
                "hours_to_show": 168,  # 1 week
                "points_per_hour": 0.5,
                "line_width": 3,
                "animate": True,
                "show": {
                    "labels": True,
                    "points": True,
                    "legend": True,
                    "average": True,
                    "extrema": True,
                },
                "card_mod": self._card_mod(theme_styles),
            }
        elif theme == "playful":
            # Use colorful gauge cards
            template = {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "gauge",
                        "entity": f"sensor.{dog_id}_health_score",
                        "name": "Health",
                        "min": 0,
                        "max": 100,
                        "severity": {
                            "green": 70,
                            "yellow": 40,
                            "red": 0,
                        },
                        "card_mod": {
                            "style": """
                                ha-card {
                                    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                                    border-radius: 50%;
                                }
                            """
                        },
                    },
                    {
                        "type": "gauge",
                        "entity": f"sensor.{dog_id}_activity_level",
                        "name": "Activity",
                        "min": 0,
                        "max": 100,
                        "severity": {
                            "green": 60,
                            "yellow": 30,
                            "red": 0,
                        },
                        "card_mod": {
                            "style": """
                                ha-card {
                                    background: linear-gradient(45deg, #4ECDC4, #FFE66D);
                                    border-radius: 50%;
                                }
                            """
                        },
                    },
                ],
            }
        else:
            # Minimal line graph
            template = {
                "type": "history-graph",
                "title": "Health Trends",
                "entities": [
                    f"sensor.{dog_id}_weight",
                    f"sensor.{dog_id}_health_score",
                ],
                "hours_to_show": 168,
            }

        return template

    async def get_timeline_template(
        self, dog_id: str, dog_name: str, theme: str = "modern"
    ) -> CardConfig:
        """Get activity timeline template.

        Args:
            dog_id: Dog identifier
            dog_name: Dog name
            theme: Visual theme

        Returns:
            Timeline template
        """
        theme_styles = self._get_theme_styles(theme)

        timeline_content = f"""
## 📅 {dog_name}'s Activity Timeline

### Today
{{{{ states.sensor.{dog_id}_last_activity.attributes.timeline | default('No activities yet') }}}}

### Recent Events
- **Last Fed**: {{{{ states('sensor.{dog_id}_last_fed') }}}}
- **Last Walk**: {{{{ states('sensor.{dog_id}_last_walk') }}}}
- **Last Health Check**: {{{{ states('sensor.{dog_id}_last_health_check') }}}}
"""

        template: CardConfig = {
            "type": "markdown",
            "content": timeline_content,
            "card_mod": self._card_mod(theme_styles),
        }

        return template

    async def get_weather_status_card_template(
        self,
        dog_id: str,
        dog_name: str,
        theme: str = "modern",
        compact: bool = False,
    ) -> CardConfig:
        """Get weather status card template for dog health monitoring.

        Args:
            dog_id: Dog identifier
            dog_name: Dog display name
            theme: Visual theme to apply
            compact: Whether to use compact layout

        Returns:
            Weather status card template with health indicators
        """
        cache_key = f"weather_status_{dog_id}_{theme}_{compact}"
        cached = await self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        theme_styles = self._get_theme_styles(theme)
        weather_icon = self._get_weather_icon(theme)

        template: CardConfig
        if compact:
            # Compact card for mobile/small spaces
            template = {
                "type": "custom:mushroom-entity",
                "entity": f"sensor.{dog_id}_weather_health_score",
                "name": f"{weather_icon} Weather Health",
                "icon": "mdi:weather-partly-cloudy",
                "icon_color": self._get_weather_color_by_score(theme),
                "secondary_info": "state",
                "tap_action": {
                    "action": "more-info",
                },
                "card_mod": self._card_mod(theme_styles),
            }
        else:
            # Full weather status card
            entities = [
                {
                    "entity": f"sensor.{dog_id}_weather_health_score",
                    "name": "Health Score",
                    "icon": "mdi:heart-pulse",
                },
                {
                    "entity": f"sensor.{dog_id}_weather_temperature_risk",
                    "name": "Temperature Risk",
                    "icon": "mdi:thermometer-alert",
                },
                {
                    "entity": f"sensor.{dog_id}_weather_activity_recommendation",
                    "name": "Activity Level",
                    "icon": "mdi:run",
                },
                {
                    "entity": f"binary_sensor.{dog_id}_weather_safe_for_walks",
                    "name": "Walk Safety",
                    "icon": "mdi:walk",
                },
            ]

            template = {
                "type": "entities",
                "title": f"{weather_icon} {dog_name} Weather Health",
                "entities": entities,
                "state_color": True,
                "show_header_toggle": False,
                "card_mod": self._card_mod(theme_styles),
            }

            # Add theme-specific styling
            if theme == "modern":
                template["card_mod"]["style"] += """
                    .card-header {
                        background: linear-gradient(90deg, #2196F3, #21CBF3);
                        color: white;
                        border-radius: 16px 16px 0 0;
                    }
                """
            elif theme == "playful":
                template["card_mod"]["style"] += """
                    .card-header {
                        background: linear-gradient(45deg, #FF6B6B, #4ECDC4, #FFE66D);
                        background-size: 300% 300%;
                        animation: gradient 3s ease infinite;
                        color: white;
                    }
                    @keyframes gradient {
                        0% { background-position: 0% 50%; }
                        50% { background-position: 100% 50%; }
                        100% { background-position: 0% 50%; }
                    }
                """

        await self._cache.set(cache_key, template)
        return template

    async def get_weather_alerts_card_template(
        self,
        dog_id: str,
        dog_name: str,
        theme: str = "modern",
        max_alerts: int = 3,
    ) -> CardConfig:
        """Get weather alerts card template.

        Args:
            dog_id: Dog identifier
            dog_name: Dog display name
            theme: Visual theme
            max_alerts: Maximum number of alerts to display

        Returns:
            Weather alerts card template
        """
        theme_styles = self._get_theme_styles(theme)
        alert_icon = "⚠️" if theme == "playful" else "mdi:weather-lightning"

        # Dynamic content based on current alerts
        alerts_content = f"""
## {alert_icon} Weather Alerts for {dog_name}

{{%- set alerts = states.sensor.{dog_id}_weather_alerts.attributes.active_alerts | default([]) -%}}
{{%- if alerts | length > 0 -%}}
{{%- for alert in alerts[:3] -%}}
### {{ alert.severity | title }} Alert: {{ alert.title }}
{{ alert.message }}

**Impact:** {{ alert.impact }}
**Recommendation:** {{ alert.recommendation }}

---
{{%- endfor -%}}
{{%- else -%}}
### ✅ No Weather Alerts
{dog_name} can enjoy normal outdoor activities today!

**Current Conditions:** Perfect for walks and outdoor play.
{{%- endif -%}}

**Last Updated:** {{{{ states('sensor.{dog_id}_weather_last_update') }}}}
"""

        # Conditional styling based on alert severity
        if theme == "modern":
            card_mod_style = """
                ha-card {
                    background: linear-gradient(135deg,
                        {% if states('sensor.{dog_id}_weather_alerts') | int > 0 %}
                            rgba(244, 67, 54, 0.1) 0%, rgba(255, 152, 0, 0.1) 100%
                        {% else %}
                            rgba(76, 175, 80, 0.1) 0%, rgba(139, 195, 74, 0.1) 100%
                        {% endif %}
                    );
                    border-left: 4px solid
                        {% if states('sensor.{dog_id}_weather_alerts') | int > 0 %}
                            #FF5722
                        {% else %}
                            #4CAF50
                        {% endif %};
                }
            """.replace("{dog_id}", dog_id)
        elif theme == "playful":
            card_mod_style = """
                ha-card {
                    background: {% if states('sensor.{dog_id}_weather_alerts') | int > 0 %}
                        linear-gradient(45deg, #FF6B6B, #FF8E53)
                    {% else %}
                        linear-gradient(45deg, #4ECDC4, #44A08D)
                    {% endif %};
                    color: white;
                    animation: pulse 2s infinite;
                }
                @keyframes pulse {
                    0% { transform: scale(1); }
                    50% { transform: scale(1.02); }
                    100% { transform: scale(1); }
                }
            """.replace("{dog_id}", dog_id)
        else:
            card_mod_style = self._card_mod(theme_styles).get("style", "")

        template: CardConfig = {
            "type": "markdown",
            "content": alerts_content,
            "card_mod": {
                "style": card_mod_style,
            },
        }

        return template

    async def get_weather_recommendations_card_template(
        self,
        dog_id: str,
        dog_name: str,
        theme: str = "modern",
        include_breed_specific: bool = True,
        recommendations: Sequence[str] | None = None,
        *,
        overflow_recommendations: int = 0,
    ) -> CardConfig:
        """Get weather recommendations card template.

        Args:
            dog_id: Dog identifier
            dog_name: Dog display name
            theme: Visual theme
            include_breed_specific: Whether to include breed-specific advice
            recommendations: Sanitised recommendation strings to embed in content
            overflow_recommendations: Number of hidden recommendations to note in output

        Returns:
            Weather recommendations card template
        """

        theme_styles = self._get_theme_styles(theme)
        rec_icon = "💡" if theme == "playful" else "mdi:lightbulb-on"

        bullet_lines: list[str] = []
        if recommendations:
            for item in recommendations:
                entry = item.strip()
                if entry:
                    bullet_lines.append(f"• {entry}")

        if not bullet_lines:
            bullet_lines.extend(
                [
                    "• Perfect weather for normal activities!",
                    "• Maintain regular exercise schedule",
                    "• Keep hydration available",
                ]
            )

        if overflow_recommendations > 0:
            bullet_lines.append(
                f"*... and {overflow_recommendations} more recommendations*"
            )

        breed_section: list[str] = []
        if include_breed_specific:
            breed_section = [
                "### 🐕 Breed-Specific Advice",
                "{{%- set breed = states.sensor.{dog_id}_breed.state | default('Mixed') -%}}",
                "{{{{ states.sensor.{dog_id}_breed_weather_advice.attributes.advice | default('No specific advice available for this breed.') }}}}",
            ]

        lines = [
            f"## {rec_icon} Weather Recommendations for {dog_name}",
            "",
            "### 🌡️ Temperature Guidance",
            f"**Current Feel:** {{{{ states('sensor.{dog_id}_weather_feels_like') }}}}°C",
            f"**Recommendation:** {{{{ states('sensor.{dog_id}_weather_activity_recommendation') }}}}",
            "",
            "### 🚶 Activity Suggestions",
            *bullet_lines,
        ]

        if breed_section:
            lines.extend(["", *breed_section])

        lines.extend(
            [
                "",
                "### ⏰ Best Activity Times",
                f"**Optimal Walk Time:** {{{{ states('sensor.{dog_id}_optimal_walk_time') }}}}",
                f"**Avoid Outdoors:** {{{{ states('sensor.{dog_id}_weather_avoid_times') }}}}",
                "",
                f"**Last Updated:** {{{{ states('sensor.{dog_id}_weather_last_update') }}}}",
            ]
        )

        recommendations_content = "\n".join(lines).replace("{dog_id}", dog_id)

        template: CardConfig = {
            "type": "markdown",
            "content": recommendations_content,
            "card_mod": self._card_mod(theme_styles),
        }

        if theme == "modern":
            card_mod = template.setdefault("card_mod", {})
            style = card_mod.get("style", "")
            style += """
                .card-content {
                    padding-bottom: 60px;
                }
                .card-content::after {
                    content: '';
                    position: absolute;
                    bottom: 10px;
                    left: 10px;
                    right: 10px;
                    height: 40px;
                    background: linear-gradient(90deg, #2196F3, #21CBF3);
                    border-radius: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
            """
            card_mod["style"] = style

        return template

    async def get_weather_chart_template(
        self,
        dog_id: str,
        chart_type: str = "health_score",
        theme: str = "modern",
        time_range: str = "24h",
    ) -> CardConfig:
        """Get weather impact chart template.

        Args:
            dog_id: Dog identifier
            chart_type: Type of chart (health_score, temperature, activity)
            theme: Visual theme
            time_range: Time range (24h, 7d, 30d)

        Returns:
            Weather chart template
        """
        theme_styles = self._get_theme_styles(theme)

        hours_map = {
            "24h": 24,
            "7d": 168,
            "30d": 720,
        }
        hours_to_show = hours_map.get(time_range, 24)

        entities: list[dict[str, Any]]

        if chart_type == "health_score":
            entities = [
                {
                    "entity": f"sensor.{dog_id}_weather_health_score",
                    "name": "Weather Health Score",
                    "color": theme_styles["colors"]["primary"],
                },
                {
                    "entity": f"sensor.{dog_id}_outdoor_temperature",
                    "name": "Temperature",
                    "color": theme_styles["colors"]["accent"],
                    "y_axis": "secondary",
                },
            ]
            chart_title = "Weather Health Impact"
        elif chart_type == "temperature":
            entities = [
                {
                    "entity": f"sensor.{dog_id}_outdoor_temperature",
                    "name": "Temperature",
                    "color": "#FF5722",
                },
                {
                    "entity": f"sensor.{dog_id}_feels_like_temperature",
                    "name": "Feels Like",
                    "color": "#FF9800",
                },
                {
                    "entity": f"sensor.{dog_id}_temperature_comfort_zone",
                    "name": "Comfort Zone",
                    "color": "#4CAF50",
                    "show_fill": True,
                },
            ]
            chart_title = "Temperature Trends"
        else:  # activity
            entities = [
                {
                    "entity": f"sensor.{dog_id}_weather_activity_level",
                    "name": "Recommended Activity",
                    "color": theme_styles["colors"]["primary"],
                },
                {
                    "entity": f"sensor.{dog_id}_actual_activity_level",
                    "name": "Actual Activity",
                    "color": theme_styles["colors"]["accent"],
                },
            ]
            chart_title = "Activity vs Weather"

        template: CardConfig
        if theme in ["modern", "dark"]:
            template = {
                "type": "custom:mini-graph-card",
                "name": chart_title,
                "entities": entities,
                "hours_to_show": hours_to_show,
                "points_per_hour": 2 if hours_to_show <= 24 else 1,
                "line_width": 3,
                "animate": True,
                "show": {
                    "labels": True,
                    "points": True,
                    "legend": True,
                    "average": True,
                    "extrema": True,
                    "fill": "fade",
                },
                "color_thresholds": [
                    {"value": 30, "color": "#4CAF50"},
                    {"value": 60, "color": "#FF9800"},
                    {"value": 80, "color": "#F44336"},
                ],
                "card_mod": self._card_mod(theme_styles),
            }
        else:
            # Fallback to simple history graph
            template = {
                "type": "history-graph",
                "title": chart_title,
                "entities": [entity["entity"] for entity in entities],
                "hours_to_show": hours_to_show,
                "card_mod": self._card_mod(theme_styles),
            }

        return template

    async def get_weather_breed_advisory_template(
        self,
        dog_id: str,
        dog_name: str,
        breed: str,
        theme: str = "modern",
    ) -> CardConfig:
        """Get breed-specific weather advisory template.

        Args:
            dog_id: Dog identifier
            dog_name: Dog display name
            breed: Dog breed
            theme: Visual theme

        Returns:
            Breed-specific weather advisory template
        """
        theme_styles = self._get_theme_styles(theme)
        breed_icon = self._get_breed_emoji(breed, theme)

        advisory_content = f"""
## {breed_icon} {breed} Weather Advisory for {dog_name}

{{%- set breed_advice = states.sensor.{dog_id}_breed_weather_advice.attributes -%}}
{{%- set current_temp = states('sensor.{dog_id}_outdoor_temperature') | float -%}}
{{%- set breed_comfort_min = breed_advice.comfort_range.min | default(10) -%}}
{{%- set breed_comfort_max = breed_advice.comfort_range.max | default(25) -%}}

### 🌡️ Breed Comfort Zone
**Optimal Range:** {{ breed_comfort_min }}°C - {{ breed_comfort_max }}°C
**Current:** {{ current_temp }}°C

{{%- if current_temp < breed_comfort_min -%}}
### ❄️ Cold Weather Precautions
{{ breed_advice.cold_weather_advice | default('Monitor for signs of cold stress') }}
{{%- elif current_temp > breed_comfort_max -%}}
### 🔥 Hot Weather Precautions
{{ breed_advice.hot_weather_advice | default('Provide shade and fresh water') }}
{{%- else -%}}
### ✅ Perfect Weather for {{ breed }}s
{{ breed_advice.optimal_weather_advice | default('Great conditions for normal activities') }}
{{%- endif -%}}

### 🔍 Breed-Specific Monitoring
{{%- for warning in breed_advice.breed_warnings | default([]) -%}}
• {{ warning }}
{{%- endfor -%}}

### 💡 Activity Adjustments
**Exercise Modifications:** {{ breed_advice.exercise_modifications | default('No modifications needed') }}
**Special Considerations:** {{ breed_advice.special_considerations | default('Standard care applies') }}

**Breed Profile Last Updated:** {{{{ states('sensor.{dog_id}_breed_profile_updated') }}}}
"""

        breed_advice_state = self.hass.states.get(
            f"sensor.{dog_id}_breed_weather_advice"
        )
        breed_advice_attrs: Mapping[str, object] = {}
        if breed_advice_state is not None:
            attrs = getattr(breed_advice_state, "attributes", {})
            if isinstance(attrs, Mapping):
                breed_advice_attrs = attrs

        comfort_range_obj = breed_advice_attrs.get("comfort_range", {})
        comfort_range: Mapping[str, object]
        if isinstance(comfort_range_obj, Mapping):
            comfort_range = comfort_range_obj
        else:
            comfort_range = {}

        def _coerce_temperature(value: object, fallback: float) -> float:
            if isinstance(value, int | float):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return fallback
            return fallback

        comfort_min_value = _coerce_temperature(comfort_range.get("min"), 10.0)
        comfort_max_value = _coerce_temperature(comfort_range.get("max"), 25.0)

        # Breed-specific styling
        if theme == "modern":
            card_style = (
                """
                ha-card {
                    background: linear-gradient(135deg,
                        {% if states('sensor.{dog_id}_outdoor_temperature') | float < breed_comfort_min %}
                            rgba(33, 150, 243, 0.1) 0%, rgba(3, 169, 244, 0.1) 100%
                        {% elif states('sensor.{dog_id}_outdoor_temperature') | float > breed_comfort_max %}
                            rgba(255, 87, 34, 0.1) 0%, rgba(255, 152, 0, 0.1) 100%
                        {% else %}
                            rgba(76, 175, 80, 0.1) 0%, rgba(139, 195, 74, 0.1) 100%
                        {% endif %}
                    );
                    border-left: 6px solid
                        {% if states('sensor.{dog_id}_outdoor_temperature') | float < breed_comfort_min %}
                            #2196F3
                        {% elif states('sensor.{dog_id}_outdoor_temperature') | float > breed_comfort_max %}
                            #FF5722
                        {% else %}
                            #4CAF50
                        {% endif %};
                }
            """.replace("{dog_id}", dog_id)
                .replace("breed_comfort_min", str(comfort_min_value))
                .replace("breed_comfort_max", str(comfort_max_value))
            )
        else:
            card_style = self._card_mod(theme_styles).get("style", "")

        template: CardConfig = {
            "type": "markdown",
            "content": advisory_content,
            "card_mod": {
                "style": card_style,
            },
        }

        return template

    async def get_weather_action_buttons_template(
        self,
        dog_id: str,
        theme: str = "modern",
        layout: str = "horizontal",
    ) -> CardConfig:
        """Get weather action buttons template.

        Args:
            dog_id: Dog identifier
            theme: Visual theme
            layout: Button layout (horizontal, vertical, grid)

        Returns:
            Weather action buttons template
        """
        base_button = self._get_base_card_template("button")
        theme_styles = self._get_theme_styles(theme)

        # Weather update button
        update_button = {
            **base_button,
            "name": "Update Weather",
            "icon": "mdi:weather-cloudy-arrow-right",
            "icon_color": theme_styles["colors"]["primary"],
            "tap_action": {
                "action": "call-service",
                "service": f"{DOMAIN}.update_weather",
                "service_data": {"force_update": True},
            },
        }

        # Get weather alerts button
        alerts_button = {
            **base_button,
            "name": "Check Alerts",
            "icon": "mdi:weather-lightning",
            "icon_color": "orange",
            "tap_action": {
                "action": "call-service",
                "service": f"{DOMAIN}.get_weather_alerts",
                "service_data": {"dog_id": dog_id},
            },
        }

        # Get recommendations button
        recommendations_button = {
            **base_button,
            "name": "Get Advice",
            "icon": "mdi:lightbulb-on",
            "icon_color": theme_styles["colors"]["accent"],
            "tap_action": {
                "action": "call-service",
                "service": f"{DOMAIN}.get_weather_recommendations",
                "service_data": {
                    "dog_id": dog_id,
                    "include_breed_specific": True,
                },
            },
        }

        buttons: CardCollection = [update_button, alerts_button, recommendations_button]

        # Apply theme styling to buttons
        if theme == "modern":
            for i, button in enumerate(buttons):
                colors = ["#2196F3", "#FF9800", "#4CAF50"]
                button["card_mod"] = {
                    "style": f"""
                        ha-card {{
                            background: linear-gradient(135deg, {colors[i]}, {colors[i]}CC);
                            color: white;
                            border-radius: 12px;
                            transition: all 0.3s ease;
                        }}
                        ha-card:hover {{
                            transform: translateY(-2px);
                            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
                        }}
                    """
                }
        elif theme == "playful":
            for button in buttons:
                button["card_mod"] = {
                    "style": """
                        ha-card {
                            background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                            color: white;
                            border-radius: 50px;
                            animation: wiggle 2s ease-in-out infinite;
                        }
                        @keyframes wiggle {
                            0%, 100% { transform: rotate(0deg); }
                            25% { transform: rotate(-1deg); }
                            75% { transform: rotate(1deg); }
                        }
                    """
                }

        # Layout buttons according to specified layout
        if layout == "vertical":
            return {
                "type": "vertical-stack",
                "cards": buttons,
            }
        elif layout == "grid":
            return {
                "type": "grid",
                "columns": 3,
                "cards": buttons,
            }
        else:  # horizontal (default)
            return {
                "type": "horizontal-stack",
                "cards": buttons,
            }

    def _get_weather_icon(self, theme: str) -> str:
        """Get theme-appropriate weather icon.

        Args:
            theme: Theme name

        Returns:
            Weather icon for the theme
        """
        icons = {
            "modern": "🌤️",
            "playful": "☀️",
            "minimal": "○",
            "dark": "🌙",
        }
        return icons.get(theme, "🌤️")

    def _get_weather_color_by_score(self, theme: str) -> str:
        """Get weather health score color by theme.

        Args:
            theme: Theme name

        Returns:
            Color for weather health score
        """
        theme_styles = self._get_theme_styles(theme)
        return theme_styles["colors"]["primary"]

    def _get_breed_emoji(self, breed: str, theme: str) -> str:
        """Get breed-specific emoji.

        Args:
            breed: Dog breed name
            theme: Theme name

        Returns:
            Breed-appropriate emoji
        """
        if theme != "playful":
            return "🐕"

        # Breed-specific emojis for playful theme
        breed_emojis = {
            "husky": "🐺",
            "golden retriever": "🦮",
            "bulldog": "🐶",
            "poodle": "🐩",
            "german shepherd": "🦮",
            "labrador": "🦮",
            "chihuahua": "🐕‍🦺",
            "beagle": "🐕",
        }

        breed_lower = breed.lower().strip()
        for breed_key, emoji in breed_emojis.items():
            if breed_key in breed_lower:
                return emoji

        return "🐶"  # Default playful dog emoji

    async def get_history_graph_template(
        self,
        entities: list[str],
        title: str,
        hours_to_show: int = 24,
        theme: str = "modern",
    ) -> CardConfig:
        """Get themed history graph template.

        Args:
            entities: Entity IDs to display
            title: Graph title
            hours_to_show: Hours of history to show
            theme: Visual theme

        Returns:
            History graph template
        """
        # Filter entities that likely exist
        valid_entities = await self._filter_valid_entities(entities)

        if not valid_entities:
            # Return empty markdown card if no valid entities
            return {
                "type": "markdown",
                "content": f"**{title}**\n\nNo data available",
            }

        theme_styles = self._get_theme_styles(theme)

        template = {
            **self._get_base_card_template("history_graph"),
            "title": title,
            "entities": valid_entities,
            "hours_to_show": hours_to_show,
            "card_mod": self._card_mod(theme_styles),
        }

        return template

    async def _filter_valid_entities(self, entities: list[str]) -> list[str]:
        """Filter entities to only include those that exist.

        Args:
            entities: List of entity IDs to check

        Returns:
            List of existing entity IDs
        """
        valid_entities = []

        for entity_id in entities:
            state = self.hass.states.get(entity_id)
            if state and state.state != STATE_UNKNOWN:
                valid_entities.append(entity_id)

        return valid_entities

    async def cleanup(self) -> None:
        """Clean up template cache and resources."""
        await self._cache.clear()

    async def get_weather_dashboard_layout_template(
        self,
        dog_id: str,
        dog_name: str,
        breed: str,
        theme: str = "modern",
        layout: str = "full",
    ) -> CardConfig:
        """Get complete weather dashboard layout template.

        Args:
            dog_id: Dog identifier
            dog_name: Dog display name
            breed: Dog breed
            theme: Visual theme
            layout: Layout type (full, compact, mobile)

        Returns:
            Complete weather dashboard layout
        """
        if layout == "compact":
            # Compact layout for smaller screens
            compact_cards: CardCollection = [
                await self.get_weather_status_card_template(
                    dog_id, dog_name, theme, compact=True
                ),
                await self.get_weather_alerts_card_template(
                    dog_id, dog_name, theme, max_alerts=1
                ),
                await self.get_weather_action_buttons_template(
                    dog_id, theme, layout="horizontal"
                ),
            ]

            return {
                "type": "vertical-stack",
                "cards": compact_cards,
            }

        elif layout == "mobile":
            # Mobile-optimized layout
            mobile_cards: CardCollection = [
                await self.get_weather_status_card_template(
                    dog_id, dog_name, theme, compact=True
                ),
                await self.get_weather_chart_template(
                    dog_id, "health_score", theme, "24h"
                ),
                await self.get_weather_action_buttons_template(
                    dog_id, theme, layout="grid"
                ),
            ]

            return {
                "type": "vertical-stack",
                "cards": mobile_cards,
            }

        else:  # full layout
            # Full desktop layout with all weather components
            full_cards: CardCollection = [
                # Top row: Status and alerts
                {
                    "type": "horizontal-stack",
                    "cards": [
                        await self.get_weather_status_card_template(
                            dog_id, dog_name, theme
                        ),
                        await self.get_weather_alerts_card_template(
                            dog_id, dog_name, theme
                        ),
                    ],
                },
                # Second row: Charts
                {
                    "type": "horizontal-stack",
                    "cards": [
                        await self.get_weather_chart_template(
                            dog_id, "health_score", theme, "24h"
                        ),
                        await self.get_weather_chart_template(
                            dog_id, "temperature", theme, "24h"
                        ),
                    ],
                },
                # Third row: Recommendations and breed advice
                {
                    "type": "horizontal-stack",
                    "cards": [
                        await self.get_weather_recommendations_card_template(
                            dog_id, dog_name, theme
                        ),
                        await self.get_weather_breed_advisory_template(
                            dog_id, dog_name, breed, theme
                        ),
                    ],
                },
                # Bottom row: Action buttons
                await self.get_weather_action_buttons_template(
                    dog_id, theme, layout="horizontal"
                ),
            ]

            return {
                "type": "vertical-stack",
                "cards": full_cards,
            }

    @callback
    def get_cache_stats(self) -> TemplateCacheStats:
        """Get template cache statistics."""
        return self._cache.get_stats()
