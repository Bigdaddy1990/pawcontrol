"""Dashboard template caching system for Paw Control.

This module provides efficient template caching and management for dashboard
card generation. It implements LRU caching, template validation, and async
template loading to significantly improve dashboard generation performance.

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
from typing import Any, Final

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
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
            template_size = len(json.dumps(template, separators=(',', ':')))
            if template_size > MAX_TEMPLATE_SIZE:
                _LOGGER.warning(
                    "Template %s too large (%d bytes), not caching", 
                    key, template_size
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
    """Dashboard template manager with caching and lazy loading.
    
    Provides efficient template generation and caching for dashboard cards
    with automatic optimization based on usage patterns.
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
        }
        
        return base_templates.get(card_type, {"type": card_type})

    async def get_dog_status_card_template(
        self, dog_id: str, dog_name: str, modules: dict[str, bool]
    ) -> dict[str, Any]:
        """Get optimized dog status card template.
        
        Args:
            dog_id: Dog identifier
            dog_name: Dog display name
            modules: Enabled modules for the dog
            
        Returns:
            Complete status card template
        """
        cache_key = f"dog_status_{dog_id}_{hash(frozenset(modules.items()))}"
        
        # Try cache first
        cached = await self._cache.get(cache_key)
        if cached:
            return cached
            
        # Generate template
        template = await self._generate_dog_status_template(dog_id, dog_name, modules)
        
        # Cache for future use
        await self._cache.set(cache_key, template)
        
        return template

    async def _generate_dog_status_template(
        self, dog_id: str, dog_name: str, modules: dict[str, bool]
    ) -> dict[str, Any]:
        """Generate dog status card template.
        
        Args:
            dog_id: Dog identifier
            dog_name: Dog display name  
            modules: Enabled modules
            
        Returns:
            Status card template
        """
        base_template = self._get_base_card_template("status")
        
        # Core entities - always present
        entities = [
            f"sensor.{dog_id}_status",
            f"sensor.{dog_id}_last_activity",
        ]
        
        # Add module-specific entities
        if modules.get("feeding"):
            entities.extend([
                f"sensor.{dog_id}_last_fed",
                f"sensor.{dog_id}_meals_today",
            ])
            
        if modules.get("walk"):
            entities.extend([
                f"binary_sensor.{dog_id}_is_walking",
                f"sensor.{dog_id}_last_walk",
            ])
            
        if modules.get("health"):
            entities.extend([
                f"sensor.{dog_id}_weight",
                f"sensor.{dog_id}_health_status",
            ])
            
        if modules.get("gps"):
            entities.extend([
                f"device_tracker.{dog_id}_location",
                f"sensor.{dog_id}_distance_from_home",
            ])

        template = {
            **base_template,
            "title": f"{dog_name} Status",
            "entities": entities,
        }
        
        return template

    async def get_action_buttons_template(
        self, dog_id: str, modules: dict[str, bool]
    ) -> list[dict[str, Any]]:
        """Get action buttons template for dog.
        
        Args:
            dog_id: Dog identifier
            modules: Enabled modules
            
        Returns:
            List of button card templates
        """
        cache_key = f"action_buttons_{dog_id}_{hash(frozenset(modules.items()))}"
        
        # Try cache first
        cached = await self._cache.get(cache_key)
        if cached:
            return cached.get("buttons", [])
            
        buttons = []
        base_button = self._get_base_card_template("button")
        
        # Feeding button
        if modules.get("feeding"):
            buttons.append({
                **base_button,
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
            })
            
        # Walk buttons (conditional based on walking state)
        if modules.get("walk"):
            buttons.extend([
                {
                    "type": "conditional",
                    "conditions": [
                        {
                            "entity": f"binary_sensor.{dog_id}_is_walking",
                            "state": "off",
                        }
                    ],
                    "card": {
                        **base_button,
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
                        **base_button,
                        "name": "End Walk",
                        "icon": "mdi:stop",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.end_walk",
                            "service_data": {"dog_id": dog_id},
                        },
                    },
                },
            ])
            
        # Health button
        if modules.get("health"):
            buttons.append({
                **base_button,
                "name": "Log Health",
                "icon": "mdi:heart-pulse",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.log_health",
                    "service_data": {"dog_id": dog_id},
                },
            })

        template = {"buttons": buttons}
        await self._cache.set(cache_key, template)
        
        return buttons

    async def get_map_card_template(
        self, dog_id: str, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Get GPS map card template.
        
        Args:
            dog_id: Dog identifier
            options: Map display options
            
        Returns:
            Map card template
        """
        options = options or {}
        
        template = {
            **self._get_base_card_template("map"),
            "entities": [f"device_tracker.{dog_id}_location"],
            "default_zoom": options.get("zoom", 15),
            "dark_mode": options.get("dark_mode", False),
            "hours_to_show": options.get("hours_to_show", 2),
        }
        
        return template

    async def get_history_graph_template(
        self, entities: list[str], title: str, hours_to_show: int = 24
    ) -> dict[str, Any]:
        """Get history graph template.
        
        Args:
            entities: Entity IDs to display
            title: Graph title
            hours_to_show: Hours of history to show
            
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
            
        template = {
            **self._get_base_card_template("history_graph"),
            "title": title,
            "entities": valid_entities,
            "hours_to_show": hours_to_show,
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

    async def get_feeding_controls_template(self, dog_id: str) -> dict[str, Any]:
        """Get feeding control buttons template.
        
        Args:
            dog_id: Dog identifier
            
        Returns:
            Feeding controls template
        """
        base_button = self._get_base_card_template("button")
        
        meal_types = [
            ("breakfast", "Breakfast", "mdi:weather-sunny"),
            ("lunch", "Lunch", "mdi:weather-partly-cloudy"),
            ("dinner", "Dinner", "mdi:weather-night"),
            ("snack", "Snack", "mdi:cookie"),
        ]
        
        buttons = []
        for meal_type, name, icon in meal_types:
            buttons.append({
                **base_button,
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
            })
            
        # Group buttons in pairs for better layout
        grouped_buttons = []
        for i in range(0, len(buttons), 2):
            button_pair = buttons[i:i+2]
            grouped_buttons.append({
                "type": "horizontal-stack",
                "cards": button_pair,
            })
            
        return {
            "type": "vertical-stack",
            "cards": grouped_buttons,
        }

    async def cleanup(self) -> None:
        """Clean up template cache and resources."""
        await self._cache.clear()
        self._weak_refs.clear()

    @callback
    def get_cache_stats(self) -> dict[str, Any]:
        """Get template cache statistics."""
        return self._cache.get_stats()
