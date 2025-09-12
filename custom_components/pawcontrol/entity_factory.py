"""Entity factory for PawControl with profile-based optimization.

This module provides centralized entity creation with profile-based
optimization to reduce entity count and improve performance.

Quality Scale: Platinum
Home Assistant: 2025.9.1+
Python: 3.13+
"""
from __future__ import annotations

import logging
from typing import Any
from typing import Final
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.entity import Entity

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Entity profile definitions with performance impact
ENTITY_PROFILES: Final[dict[str, dict[str, Any]]] = {
    "basic": {
        "name": "Basic (8 entities)",
        "description": "Essential monitoring only - Best performance",
        "max_entities": 8,
        "performance_impact": "minimal",
        "recommended_for": "Single dog, basic monitoring",
        "platforms": [Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR],
    },
    "standard": {
        "name": "Standard (12 entities)",
        "description": "Balanced monitoring with GPS - Good performance",
        "max_entities": 12,
        "performance_impact": "low",
        "recommended_for": "Most users, balanced functionality",
        "platforms": [
            Platform.SENSOR,
            Platform.BUTTON,
            Platform.BINARY_SENSOR,
            Platform.SELECT,
            Platform.SWITCH,
        ],
    },
    "advanced": {
        "name": "Advanced (18 entities)",
        "description": "Comprehensive monitoring - Higher resource usage",
        "max_entities": 18,
        "performance_impact": "medium",
        "recommended_for": "Power users, detailed analytics",
        "platforms": list(Platform),  # All platforms
    },
    "gps_focus": {
        "name": "GPS Focus (10 entities)",
        "description": "GPS tracking optimized - Good for active dogs",
        "max_entities": 10,
        "performance_impact": "low",
        "recommended_for": "Active dogs, outdoor adventures",
        "platforms": [
            Platform.SENSOR,
            Platform.BUTTON,
            Platform.BINARY_SENSOR,
            Platform.DEVICE_TRACKER,
            Platform.NUMBER,
        ],
    },
    "health_focus": {
        "name": "Health Focus (10 entities)",
        "description": "Health monitoring optimized - Good for senior dogs",
        "max_entities": 10,
        "performance_impact": "low",
        "recommended_for": "Senior dogs, health conditions",
        "platforms": [
            Platform.SENSOR,
            Platform.BUTTON,
            Platform.BINARY_SENSOR,
            Platform.NUMBER,
            Platform.DATE,
            Platform.TEXT,
        ],
    },
}


class EntityFactory:
    """Factory for creating entities based on profile and configuration."""

    def __init__(self, coordinator: PawControlCoordinator) -> None:
        """Initialize entity factory.

        Args:
            coordinator: PawControl coordinator instance
        """
        self.coordinator = coordinator
        self._entity_cache: dict[str, Entity] = {}

    def estimate_entity_count(self, profile: str, modules: dict[str, bool]) -> int:
        """Estimate entity count for a profile and module configuration.

        Args:
            profile: Entity profile name
            modules: Dictionary of enabled modules

        Returns:
            Estimated entity count
        """
        if profile not in ENTITY_PROFILES:
            profile = "standard"

        profile_config = ENTITY_PROFILES[profile]
        base_entities = 3  # Core entities always present

        # Module-based estimates
        module_estimates = {
            "feeding": {"basic": 3, "standard": 6, "advanced": 10, "health_focus": 4},
            "walk": {"basic": 2, "standard": 4, "advanced": 6, "gps_focus": 4},
            "gps": {"basic": 2, "standard": 4, "advanced": 5, "gps_focus": 5},
            "health": {"basic": 2, "standard": 4, "advanced": 6, "health_focus": 6},
            "notifications": {"basic": 1, "standard": 2, "advanced": 3},
            "dashboard": {"basic": 0, "standard": 1, "advanced": 2},
            "visitor": {"basic": 1, "standard": 2, "advanced": 3},
            "medication": {"basic": 2, "standard": 3, "advanced": 5, "health_focus": 4},
            "training": {"basic": 1, "standard": 3, "advanced": 5},
        }

        for module, enabled in modules.items():
            if enabled and module in module_estimates:
                profile_estimates = module_estimates[module]
                base_entities += profile_estimates.get(profile, 2)

        # Apply profile limit
        return min(base_entities, profile_config["max_entities"])

    def should_create_entity(
        self,
        profile: str,
        entity_type: str,
        module: str,
        priority: int = 5,
    ) -> bool:
        """Determine if an entity should be created based on profile.

        Args:
            profile: Entity profile name
            entity_type: Type of entity (sensor, button, etc.)
            module: Module requesting the entity
            priority: Entity priority (1-10, higher = more important)

        Returns:
            True if entity should be created
        """
        if profile not in ENTITY_PROFILES:
            profile = "standard"

        # Priority-based rules
        if priority >= 9:  # Critical entities always created
            return True
        elif priority <= 2 and profile == "basic":  # Low priority excluded in basic
            return False

        # Profile-specific rules
        if profile == "basic":
            # Only essential entities
            essential_types = ["sensor", "button", "binary_sensor"]
            essential_modules = ["feeding", "health", "walk"]
            return entity_type in essential_types and module in essential_modules

        elif profile == "gps_focus":
            # GPS-related entities prioritized
            gps_types = ["device_tracker", "sensor", "binary_sensor", "number"]
            gps_modules = ["gps", "walk", "visitor"]
            return (entity_type in gps_types and module in gps_modules) or priority >= 7

        elif profile == "health_focus":
            # Health-related entities prioritized
            health_types = ["sensor", "number", "date", "text", "binary_sensor"]
            health_modules = ["health", "feeding", "medication"]
            return (
                entity_type in health_types and module in health_modules
            ) or priority >= 7

        elif profile == "advanced":
            # Almost all entities created
            return priority >= 3

        else:  # standard profile
            # Balanced approach
            return priority >= 4

    def get_platform_priority(self, platform: Platform, profile: str) -> int:
        """Get platform loading priority based on profile.

        Args:
            platform: Home Assistant platform
            profile: Entity profile name

        Returns:
            Priority (1-10, lower = load first)
        """
        priority_map = {
            "basic": {
                Platform.SENSOR: 1,
                Platform.BUTTON: 2,
                Platform.BINARY_SENSOR: 3,
            },
            "standard": {
                Platform.SENSOR: 1,
                Platform.BINARY_SENSOR: 2,
                Platform.BUTTON: 3,
                Platform.SELECT: 4,
                Platform.SWITCH: 5,
            },
            "gps_focus": {
                Platform.DEVICE_TRACKER: 1,
                Platform.SENSOR: 2,
                Platform.BINARY_SENSOR: 3,
                Platform.NUMBER: 4,
                Platform.BUTTON: 5,
            },
            "health_focus": {
                Platform.SENSOR: 1,
                Platform.NUMBER: 2,
                Platform.DATE: 3,
                Platform.BINARY_SENSOR: 4,
                Platform.TEXT: 5,
            },
            "advanced": {
                Platform.SENSOR: 1,
                Platform.BINARY_SENSOR: 2,
                Platform.DEVICE_TRACKER: 3,
                Platform.BUTTON: 4,
                Platform.SELECT: 5,
                Platform.SWITCH: 6,
                Platform.NUMBER: 7,
                Platform.TEXT: 8,
                Platform.DATE: 9,
                Platform.DATETIME: 10,
            },
        }

        profile_priorities = priority_map.get(profile, priority_map["standard"])
        return profile_priorities.get(platform, 99)

    def create_entity_config(
        self,
        dog_id: str,
        entity_type: str,
        module: str,
        profile: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Create entity configuration based on profile.

        Args:
            dog_id: Dog identifier
            entity_type: Type of entity
            module: Module creating the entity
            profile: Entity profile
            **kwargs: Additional entity configuration

        Returns:
            Entity configuration or None if should not be created
        """
        priority = kwargs.pop("priority", 5)

        if not self.should_create_entity(profile, entity_type, module, priority):
            _LOGGER.debug(
                "Skipping %s entity for %s/%s (profile: %s, priority: %d)",
                entity_type,
                dog_id,
                module,
                profile,
                priority,
            )
            return None

        # Build entity configuration
        config = {
            "dog_id": dog_id,
            "entity_type": entity_type,
            "module": module,
            "profile": profile,
            "coordinator": self.coordinator,
            **kwargs,
        }

        return config

    def get_profile_info(self, profile: str) -> dict[str, Any]:
        """Get information about an entity profile.

        Args:
            profile: Profile name

        Returns:
            Profile information dictionary
        """
        return ENTITY_PROFILES.get(profile, ENTITY_PROFILES["standard"])

    def get_available_profiles(self) -> list[str]:
        """Get list of available entity profiles.

        Returns:
            List of profile names
        """
        return list(ENTITY_PROFILES.keys())
