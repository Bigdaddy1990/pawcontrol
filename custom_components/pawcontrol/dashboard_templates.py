"""Dashboard template caching system for Paw Control with multiple themes.

This module provides efficient template caching and management for dashboard
card generation with multiple visual themes and layouts. It implements LRU
caching, template validation, and async template loading with various styles.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import json
import logging
import weakref
from functools import lru_cache
from typing import Any
from typing import Final

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Cache configuration
TEMPLATE_CACHE_SIZE: Final[int] = 128
TEMPLATE_TTL_SECONDS: Final[int] = 300  # 5 minutes
MAX_TEMPLATE_SIZE: Final[int] = 1024 * 1024  # 1MB per template


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
        self._cache: dict[str, dict[str, Any]] = {}
        self._access_times: dict[str, float] = {}
        self._maxsize = maxsize
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> dict[str, Any] | None:
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

            return self._cache[key].copy()  # Return copy to prevent mutation

    async def set(self, key: str, template: dict[str, Any]) -> None:
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

            self._cache[key] = template.copy()
            self._access_times[key] = current_time

    async def _evict_lru(self) -> None:
        """Evict least recently used template."""
        if not self._access_times:
            return

        lru_key = min(self._access_times, key=self._access_times.get)
        del self._cache[lru_key]
        del self._access_times[lru_key]

    async def clear(self) -> None:
        """Clear all cached templates."""
        async with self._lock:
            self._cache.clear()
            self._access_times.clear()

    @callback
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "cached_items": len(self._cache),
            "max_size": self._maxsize,
        }


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
        self._weak_refs: dict[str, Any] = weakref.WeakValueDictionary()

    @lru_cache(maxsize=64)
    def _get_base_card_template(self, card_type: str) -> dict[str, Any]:
        """Get base template for card type with LRU caching.

        Args:
            card_type: Type of card to get template for

        Returns:
            Base card template
        """
        base_templates = {
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
                "default_zoom": 15,
                "dark_mode": False,
                "hours_to_show": 2,
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

        return base_templates.get(card_type, {"type": card_type})

    def _get_theme_styles(self, theme: str = "modern") -> dict[str, Any]:
        """Get theme-specific styling options.

        Args:
            theme: Theme name (modern, playful, minimal, dark)

        Returns:
            Theme styling dictionary
        """
        themes = {
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

    async def get_dog_status_card_template(
        self,
        dog_id: str,
        dog_name: str,
        modules: dict[str, bool],
        theme: str = "modern",
    ) -> dict[str, Any]:
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
        if cached:
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
        modules: dict[str, bool],
        theme: str = "modern",
    ) -> dict[str, Any]:
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
            "card_mod": theme_styles.get("card_mod", {}),
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
        modules: dict[str, bool],
        theme: str = "modern",
        layout: str = "cards",
    ) -> list[dict[str, Any]]:
        """Get themed action buttons template for dog."""
        cache_key = f"action_buttons_{dog_id}_{hash(frozenset(modules.items()))}_{theme}_{layout}"

        cached = await self._cache.get(cache_key)
        if cached:
            return cached.get("buttons", [])

        base_button = self._get_base_card_template("button")
        theme_styles = self._get_theme_styles(theme)
        button_style = self._get_button_style(theme)

        buttons: list[dict[str, Any]] = []
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

        await self._cache.set(cache_key, {"buttons": result})
        return result

    def _gradient_style(self, primary: str, secondary: str) -> dict[str, Any]:
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

    def _get_button_style(self, theme: str) -> dict[str, Any]:
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
        base_button: dict[str, Any],
        button_style: dict[str, Any],
        theme_styles: dict[str, Any],
        theme: str,
    ) -> dict[str, Any]:
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
        base_button: dict[str, Any],
        button_style: dict[str, Any],
        theme_styles: dict[str, Any],
        theme: str,
    ) -> list[dict[str, Any]]:
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
        base_button: dict[str, Any],
        button_style: dict[str, Any],
        theme_styles: dict[str, Any],
        theme: str,
    ) -> dict[str, Any]:
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
        self, buttons: list[dict[str, Any]], layout: str
    ) -> list[dict[str, Any]] | None:
        """Wrap buttons in layout-specific containers."""
        if layout == "grid":
            return [{"type": "grid", "columns": 3, "cards": buttons}]
        if layout == "panels":
            return [{"type": "horizontal-stack", "cards": buttons[:3]}]
        return None

    async def get_map_card_template(
        self, dog_id: str, options: dict[str, Any] | None = None, theme: str = "modern"
    ) -> dict[str, Any]:
        """Get themed GPS map card template.

        Args:
            dog_id: Dog identifier
            options: Map display options
            theme: Visual theme

        Returns:
            Map card template with theme styling
        """
        options = options or {}
        self._get_theme_styles(theme)

        template = {
            **self._get_base_card_template("map"),
            "entities": [f"device_tracker.{dog_id}_location"],
            "default_zoom": options.get("zoom", 15),
            "dark_mode": theme == "dark" or options.get("dark_mode", False),
            "hours_to_show": options.get("hours_to_show", 2),
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
        modules: dict[str, bool],
        theme: str = "modern",
    ) -> dict[str, Any]:
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

        template = {
            "type": "markdown",
            "content": stats_content,
            "card_mod": theme_styles.get("card_mod", {}),
        }

        return template

    async def get_feeding_schedule_template(
        self, dog_id: str, theme: str = "modern"
    ) -> dict[str, Any]:
        """Get themed feeding schedule template.

        Args:
            dog_id: Dog identifier
            theme: Visual theme

        Returns:
            Feeding schedule card template
        """
        theme_styles = self._get_theme_styles(theme)

        if theme == "modern":
            # Use a clean timeline view
            template = {
                "type": "custom:scheduler-card",
                "title": "🍽️ Feeding Schedule",
                "discover_existing": False,
                "standard_configuration": True,
                "entities": [f"sensor.{dog_id}_feeding_schedule"],
                "card_mod": theme_styles.get("card_mod", {}),
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
    ) -> dict[str, Any]:
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

        buttons = []
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
            grouped_buttons = []
            for i in range(0, len(buttons), 2):
                button_pair = buttons[i: i + 2]
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
    ) -> dict[str, Any]:
        """Get themed health charts template.

        Args:
            dog_id: Dog identifier
            theme: Visual theme

        Returns:
            Health charts template
        """
        theme_styles = self._get_theme_styles(theme)

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
                "card_mod": theme_styles.get("card_mod", {}),
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
    ) -> dict[str, Any]:
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

        template = {
            "type": "markdown",
            "content": timeline_content,
            "card_mod": theme_styles.get("card_mod", {}),
        }

        return template

    async def get_history_graph_template(
        self,
        entities: list[str],
        title: str,
        hours_to_show: int = 24,
        theme: str = "modern",
    ) -> dict[str, Any]:
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
            "card_mod": theme_styles.get("card_mod", {}),
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
        self._weak_refs.clear()

    @callback
    def get_cache_stats(self) -> dict[str, Any]:
        """Get template cache statistics."""
        return self._cache.get_stats()
