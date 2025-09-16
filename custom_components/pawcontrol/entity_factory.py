"""Entity factory for PawControl with profile-based optimization.

This module provides centralized entity creation with profile-based
optimization to reduce entity count and improve performance.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING, Any, Final, Mapping

from homeassistant.const import Platform
from homeassistant.helpers.entity import Entity

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# All available platforms for advanced profile - fixed enum conversion
ALL_AVAILABLE_PLATFORMS: Final[tuple[Platform, ...]] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
    Platform.DEVICE_TRACKER,
    Platform.DATE,
    Platform.DATETIME,
)

_ENTITY_TYPE_TO_PLATFORM: Final[dict[str, Platform]] = {
    platform.value: platform for platform in ALL_AVAILABLE_PLATFORMS
}

# Entity profile definitions with performance impact
ENTITY_PROFILES: Final[dict[str, dict[str, Any]]] = {
    "basic": {
        "name": "Basic (8 entities)",
        "description": "Essential monitoring only - Best performance",
        "max_entities": 8,
        "performance_impact": "minimal",
        "recommended_for": "Single dog, basic monitoring",
        "platforms": [Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR],
        "priority_threshold": 7,  # Only high-priority entities
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
        "priority_threshold": 4,  # Medium-priority entities and above
    },
    "advanced": {
        "name": "Advanced (18 entities)",
        "description": "Comprehensive monitoring - Higher resource usage",
        "max_entities": 18,
        "performance_impact": "medium",
        "recommended_for": "Power users, detailed analytics",
        "platforms": ALL_AVAILABLE_PLATFORMS,  # All platforms available
        "priority_threshold": 3,  # Most entities included
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
        "priority_threshold": 5,  # GPS-focused entities
        "preferred_modules": ["gps", "walk", "visitor"],
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
        "priority_threshold": 5,  # Health-focused entities
        "preferred_modules": ["health", "feeding", "medication"],
    },
}

# Pre-computed module entity estimates to avoid rebuilding dictionaries during
# performance-critical calculations.
MODULE_ENTITY_ESTIMATES: Final[dict[str, dict[str, int]]] = {
    "feeding": {
        "basic": 3,  # feeding_status, last_feeding, next_feeding
        "standard": 5,  # + portion_today, schedule_active, food_level
        "advanced": 10,  # + nutrition_tracking, feeding_history, alerts
        "health_focus": 6,  # Health-optimized feeding entities
        "gps_focus": 3,  # Minimal feeding for GPS focus
    },
    "walk": {
        "basic": 2,  # walk_status, daily_walks
        "standard": 3,  # + current_walk_duration, last_walk_distance
        "advanced": 6,  # + walk_history, activity_score, route_map
        "gps_focus": 5,  # GPS-optimized walk tracking
        "health_focus": 4,  # Health metrics from walks
    },
    "gps": {
        "basic": 2,  # location, battery
        "standard": 3,  # + accuracy, zone_status
        "advanced": 5,  # + altitude, speed, heading
        "gps_focus": 6,  # All GPS features optimized
        "health_focus": 3,  # Basic GPS for health context
    },
    "health": {
        "basic": 2,  # health_status, weight
        "standard": 3,  # + mood, activity_level
        "advanced": 6,  # + detailed_metrics, trends, alerts
        "health_focus": 8,  # Comprehensive health monitoring
        "gps_focus": 3,  # Basic health for GPS context
    },
    "notifications": {
        "basic": 1,  # notification_status
        "standard": 2,  # + pending_notifications
        "advanced": 3,  # + notification_history
        "gps_focus": 2,  # GPS-related notifications
        "health_focus": 2,  # Health-related notifications
    },
    "dashboard": {
        "basic": 0,  # No dashboard entities
        "standard": 1,  # dashboard_status
        "advanced": 2,  # + dashboard_config
        "gps_focus": 1,  # GPS dashboard
        "health_focus": 1,  # Health dashboard
    },
    "visitor": {
        "basic": 1,  # visitor_mode
        "standard": 2,  # + visitor_schedule
        "advanced": 3,  # + visitor_history
        "gps_focus": 2,  # GPS-enhanced visitor mode
        "health_focus": 1,  # Basic visitor mode
    },
    "medication": {
        "basic": 2,  # medication_due, last_dose
        "standard": 3,  # + medication_schedule
        "advanced": 5,  # + medication_history, side_effects
        "health_focus": 6,  # Comprehensive medication tracking
        "gps_focus": 2,  # Basic medication for GPS users
    },
    "training": {
        "basic": 1,  # training_status
        "standard": 3,  # + training_progress, sessions_today
        "advanced": 5,  # + training_history, skill_levels
        "gps_focus": 2,  # Location-based training
        "health_focus": 3,  # Health-integrated training
    },
    "grooming": {
        "basic": 1,  # grooming_due
        "standard": 2,  # + last_grooming
        "advanced": 3,  # + grooming_schedule
        "health_focus": 3,  # Health-integrated grooming
        "gps_focus": 1,  # Basic grooming status
    },
}

_ESTIMATE_CACHE_MAX_SIZE: Final[int] = 128


@dataclass(slots=True, frozen=True)
class EntityEstimate:
    """Container for cached entity estimation results."""

    profile: str
    final_count: int
    raw_total: int
    capacity: int
    enabled_modules: int
    total_modules: int
    module_signature: tuple[tuple[str, bool], ...]


class EntityFactory:
    """Factory for creating entities based on profile and configuration.

    Provides centralized entity creation with performance optimization
    based on selected profile and module configuration.
    """

    def __init__(self, coordinator: PawControlCoordinator | None) -> None:
        """Initialize entity factory.

        Args:
            coordinator: PawControl coordinator instance (can be None for estimation)
        """
        self.coordinator = coordinator
        self._entity_cache: dict[str, Entity] = {}
        self._profile_cache: dict[str, dict[str, Any]] = {}
        self._estimate_cache: OrderedDict[
            tuple[str, tuple[tuple[str, bool], ...]], EntityEstimate
        ] = OrderedDict()
        self._last_estimate_key: (
            tuple[str, tuple[tuple[str, bool], ...]] | None
        ) = None
        self._last_module_weights: dict[str, int] = {}
        self._last_synergy_score: int = 0
        self._last_triad_score: int = 0
        self._prewarm_caches()

    def _prewarm_caches(self) -> None:
        """Warm up internal caches for consistent performance."""

        default_modules = self._get_default_modules()
        module_signature = tuple(sorted(default_modules.items()))
        estimate = self._compute_entity_estimate(
            "standard", default_modules, module_signature
        )
        self._estimate_cache[("standard", module_signature)] = estimate
        self._last_estimate_key = ("standard", module_signature)
        self._last_module_weights = {
            module: index + 1
            for index, (module, enabled) in enumerate(module_signature)
            if enabled
        }
        self._last_synergy_score = sum(
            self._last_module_weights[a] + self._last_module_weights[b]
            for a, b in combinations(self._last_module_weights, 2)
        )
        self._last_triad_score = sum(
            self._last_module_weights[a]
            + self._last_module_weights[b]
            + self._last_module_weights[c]
            for a, b, c in combinations(self._last_module_weights, 3)
        )

    def _get_entity_estimate(
        self,
        profile: str,
        modules: Mapping[str, bool] | None,
        *,
        log_invalid_inputs: bool,
    ) -> EntityEstimate:
        """Return cached entity estimate for a profile and module set."""

        normalized_profile = self._normalize_profile(
            profile, log=log_invalid_inputs
        )
        normalized_modules = self._normalize_modules(
            modules, log=log_invalid_inputs
        )

        module_signature = tuple(sorted(normalized_modules.items()))
        cache_key = (
            normalized_profile,
            module_signature,
        )

        cached_estimate = self._estimate_cache.get(cache_key)
        if cached_estimate is not None:
            self._estimate_cache.move_to_end(cache_key)

        estimate = self._compute_entity_estimate(
            normalized_profile, normalized_modules, module_signature
        )
        self._estimate_cache[cache_key] = estimate

        if len(self._estimate_cache) > _ESTIMATE_CACHE_MAX_SIZE:
            self._estimate_cache.popitem(last=False)

        return estimate

    def _normalize_profile(self, profile: str, *, log: bool) -> str:
        """Normalize profile name and optionally log when invalid."""

        if self._validate_profile(profile):
            return profile

        if log:
            _LOGGER.warning("Invalid profile %s, using standard", profile)

        return "standard"

    def _normalize_modules(
        self, modules: Mapping[str, bool] | None, *, log: bool
    ) -> dict[str, bool]:
        """Normalize module configuration and optionally log when invalid."""

        if modules is None or not isinstance(modules, Mapping):
            if log:
                _LOGGER.warning(
                    "Invalid modules configuration, using defaults"
                )
            return self._get_default_modules()

        module_dict = dict(modules)
        if not self._validate_modules(module_dict):
            if log:
                _LOGGER.warning(
                    "Invalid modules configuration, using defaults"
                )
            return self._get_default_modules()

        return module_dict

    def _compute_entity_estimate(
        self,
        profile: str,
        modules: dict[str, bool],
        module_signature: tuple[tuple[str, bool], ...],
    ) -> EntityEstimate:
        """Compute entity estimation details for caching."""

        base_entities = 3
        module_entities = 0
        enabled_modules = 0

        for module, enabled in modules.items():
            if not enabled:
                continue

            enabled_modules += 1
            profile_estimates = MODULE_ENTITY_ESTIMATES.get(module)
            if not profile_estimates:
                continue

            module_entities += profile_estimates.get(
                profile, profile_estimates.get("standard", 2)
            )

        raw_total = base_entities + module_entities
        capacity = ENTITY_PROFILES[profile]["max_entities"]
        final_count = max(base_entities, min(raw_total, capacity))

        return EntityEstimate(
            profile=profile,
            final_count=final_count,
            raw_total=raw_total,
            capacity=capacity,
            enabled_modules=enabled_modules,
            total_modules=len(modules),
            module_signature=module_signature,
        )

    def estimate_entity_count(self, profile: str, modules: dict[str, bool]) -> int:
        """Estimate entity count for a profile and module configuration.

        Args:
            profile: Entity profile name
            modules: Dictionary of enabled modules

        Returns:
            Estimated entity count
        """

        estimate = self._get_entity_estimate(
            profile, modules, log_invalid_inputs=True
        )
        if estimate.raw_total > estimate.capacity:
            _LOGGER.debug(
                "Entity count capped from %d to %d for profile %s",  # pragma: no cover - log only
                estimate.raw_total,
                estimate.capacity,
                estimate.profile,
            )

        self._last_estimate_key = (
            estimate.profile,
            estimate.module_signature,
        )
        self._last_module_weights = {
            module: index + 1
            for index, (module, enabled) in enumerate(estimate.module_signature)
            if enabled
        }
        self._last_synergy_score = sum(
            self._last_module_weights[a] + self._last_module_weights[b]
            for a, b in combinations(self._last_module_weights, 2)
        )
        self._last_triad_score = sum(
            self._last_module_weights[a]
            + self._last_module_weights[b]
            + self._last_module_weights[c]
            for a, b, c in combinations(self._last_module_weights, 3)
        )

        return estimate.final_count

    def should_create_entity(
        self,
        profile: str,
        entity_type: str,
        module: str,
        priority: int = 5,
        **kwargs: Any,
    ) -> bool:
        """Determine if an entity should be created based on profile.

        Args:
            profile: Entity profile name
            entity_type: Type of entity (sensor, button, etc.)
            module: Module requesting the entity
            priority: Entity priority (1-10, higher = more important)
            **kwargs: Additional validation parameters

        Returns:
            True if entity should be created
        """
        if not self._validate_profile(profile):
            profile = "standard"

        profile_config = ENTITY_PROFILES[profile]
        priority_threshold = profile_config.get("priority_threshold", 5)

        # Critical entities always created (priority >= 9)
        if priority >= 9:
            return True

        # Apply priority threshold
        if priority < priority_threshold:
            return False

        # Profile-specific entity filtering
        return self._apply_profile_specific_rules(
            profile, entity_type, module, priority, **kwargs
        )

    def _apply_profile_specific_rules(
        self,
        profile: str,
        entity_type: str,
        module: str,
        priority: int,
        **kwargs: Any,
    ) -> bool:
        """Apply profile-specific rules for entity creation.

        Args:
            profile: Entity profile name
            entity_type: Type of entity
            module: Module name
            priority: Entity priority
            **kwargs: Additional parameters

        Returns:
            True if entity should be created
        """
        profile_config = ENTITY_PROFILES[profile]

        # Check if platform is supported by profile
        platform = _ENTITY_TYPE_TO_PLATFORM.get(entity_type.lower())
        if platform is None:
            _LOGGER.warning("Invalid entity type: %s", entity_type)
            return False

        if platform not in profile_config["platforms"]:
            return False

        if profile == "basic":
            # Only essential entities
            essential_types = {"sensor", "button", "binary_sensor"}
            essential_modules = {"feeding", "health", "walk"}
            return (
                entity_type in essential_types
                and module in essential_modules
                and priority >= 7
            )

        elif profile == "gps_focus":
            # GPS-related entities prioritized
            preferred_modules = profile_config.get("preferred_modules", [])
            gps_types = {"device_tracker", "sensor", "binary_sensor", "number"}
            return entity_type in gps_types and (
                module in preferred_modules or priority >= 7
            )

        elif profile == "health_focus":
            # Health-related entities prioritized
            preferred_modules = profile_config.get("preferred_modules", [])
            health_types = {"sensor", "number", "date", "text", "binary_sensor"}
            return entity_type in health_types and (
                module in preferred_modules or priority >= 7
            )

        elif profile == "advanced":
            # Almost all entities created, minimal filtering
            return priority >= 3

        else:  # standard profile
            # Balanced approach with moderate filtering
            return priority >= 4

    def get_platform_priority(self, platform: Platform, profile: str) -> int:
        """Get platform loading priority based on profile.

        Args:
            platform: Home Assistant platform
            profile: Entity profile name

        Returns:
            Priority (1-10, lower = load first)
        """
        if not self._validate_profile(profile):
            profile = "standard"

        priority_maps = {
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
                Platform.NUMBER: 6,
                Platform.DEVICE_TRACKER: 7,
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
                Platform.BUTTON: 6,
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

        profile_priorities = priority_maps.get(profile, priority_maps["standard"])
        return profile_priorities.get(platform, 99)  # Default to lowest priority

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

        # Validate inputs
        if not dog_id or not entity_type or not module:
            _LOGGER.error(
                "Missing required parameters: dog_id=%s, entity_type=%s, module=%s",
                dog_id,
                entity_type,
                module,
            )
            return None

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
            "priority": priority,
            "coordinator": self.coordinator,
            **kwargs,
        }

        # Add profile-specific optimizations
        profile_config = ENTITY_PROFILES.get(profile, ENTITY_PROFILES["standard"])
        config["performance_impact"] = profile_config["performance_impact"]

        return config

    def get_profile_info(self, profile: str) -> dict[str, Any]:
        """Get information about an entity profile.

        Args:
            profile: Profile name

        Returns:
            Profile information dictionary
        """
        if profile in self._profile_cache:
            return self._profile_cache[profile]

        info = ENTITY_PROFILES.get(profile, ENTITY_PROFILES["standard"]).copy()
        self._profile_cache[profile] = info
        return info

    def get_available_profiles(self) -> list[str]:
        """Get list of available entity profiles.

        Returns:
            List of profile names sorted by performance impact
        """
        # Sort profiles by performance impact and max entities
        profiles = list(ENTITY_PROFILES.keys())

        # Custom sort order: basic, standard, focused profiles, advanced
        sort_order = ["basic", "standard", "gps_focus", "health_focus", "advanced"]
        return sorted(
            profiles, key=lambda p: sort_order.index(p) if p in sort_order else 99
        )

    def validate_profile_for_modules(
        self, profile: str, modules: dict[str, bool]
    ) -> bool:
        """Validate if a profile is suitable for the given modules.

        Args:
            profile: Profile name to validate
            modules: Dictionary of enabled modules

        Returns:
            True if profile is suitable
        """
        if not self._validate_profile(profile) or not self._validate_modules(modules):
            return False

        profile_config = ENTITY_PROFILES[profile]

        # Check for preferred modules alignment
        preferred_modules = profile_config.get("preferred_modules", [])
        if preferred_modules:
            enabled_preferred = sum(
                1 for mod in preferred_modules if modules.get(mod, False)
            )
            enabled_total = sum(1 for enabled in modules.values() if enabled)

            # At least 50% of enabled modules should align with preferred modules
            if enabled_total > 0 and (enabled_preferred / enabled_total) < 0.5:
                return False

        return True

    def _validate_profile(self, profile: str) -> bool:
        """Validate profile name.

        Args:
            profile: Profile name to validate

        Returns:
            True if profile is valid
        """
        return isinstance(profile, str) and profile in ENTITY_PROFILES

    def _validate_modules(self, modules: Mapping[str, bool]) -> bool:
        """Validate modules configuration.

        Args:
            modules: Modules dictionary to validate

        Returns:
            True if modules configuration is valid
        """
        if not isinstance(modules, Mapping):
            return False

        # Check that all values are boolean
        return all(isinstance(enabled, bool) for enabled in modules.values())

    def _get_default_modules(self) -> dict[str, bool]:
        """Get default modules configuration.

        Returns:
            Default modules configuration
        """
        return {
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": False,
            "notifications": True,
        }

    def get_performance_metrics(
        self, profile: str, modules: dict[str, bool]
    ) -> dict[str, Any]:
        """Get performance metrics for a profile and module combination.

        Args:
            profile: Profile name
            modules: Enabled modules

        Returns:
            Performance metrics dictionary
        """
        estimate = self._get_entity_estimate(
            profile, modules, log_invalid_inputs=False
        )
        profile_config = ENTITY_PROFILES[estimate.profile]

        capacity = estimate.capacity
        utilization = 0.0 if capacity <= 0 else (estimate.final_count / capacity) * 100

        cache_key = (estimate.profile, estimate.module_signature)
        if (
            self._last_estimate_key == cache_key
            and self._last_module_weights
        ):
            module_weights = dict(self._last_module_weights)
            synergy_score = self._last_synergy_score
            triad_score = self._last_triad_score
        else:
            module_weights = {
                module: index + 1
                for index, (module, enabled) in enumerate(
                    estimate.module_signature
                )
                if enabled
            }
            synergy_score = sum(
                module_weights[a] + module_weights[b]
                for a, b in combinations(module_weights, 2)
            )
            triad_score = sum(
                module_weights[a]
                + module_weights[b]
                + module_weights[c]
                for a, b, c in combinations(module_weights, 3)
            )

        complexity_score = sum(module_weights.values())

        if estimate.raw_total > capacity and capacity > 0:
            overflow = estimate.raw_total - capacity
            penalty = min(30.0, (overflow / capacity) * 100)
            if complexity_score:
                penalty *= min(1.5, 1 + complexity_score / (10 * capacity))
            if synergy_score:
                penalty *= min(1.4, 1 + synergy_score / (75 * capacity))
            if triad_score:
                penalty *= min(1.3, 1 + triad_score / (120 * capacity))
            penalty = min(penalty, 45.0)
            utilization = max(0.0, utilization - penalty)

        utilization = max(0.0, min(utilization, 100.0))

        return {
            "profile": estimate.profile,
            "estimated_entities": estimate.final_count,
            "max_entities": profile_config["max_entities"],
            "performance_impact": profile_config["performance_impact"],
            "utilization_percentage": utilization,
            "enabled_modules": estimate.enabled_modules,
            "total_modules": estimate.total_modules,
        }
