"""Entity factory for PawControl with profile-based optimization.

This module provides centralized entity creation with profile-based
optimization to reduce entity count and improve performance.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

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
        "name": "Basic (≤6 entities)",
        "description": "Absolute minimum footprint for one dog",
        "max_entities": 6,
        "performance_impact": "minimal",
        "recommended_for": "Single dog, essential telemetry only",
        "platforms": [Platform.SENSOR, Platform.BINARY_SENSOR],
        "priority_threshold": 8,  # Critical-only entities for the basic tier
    },
    "standard": {
        "name": "Standard (≤10 entities)",
        "description": "Balanced monitoring with selective extras",
        "max_entities": 10,
        "performance_impact": "low",
        "recommended_for": "Most users, curated functionality",
        "platforms": [
            Platform.SENSOR,
            Platform.BUTTON,
            Platform.BINARY_SENSOR,
            Platform.SELECT,
            Platform.SWITCH,
        ],
        "priority_threshold": 6,  # Medium-priority entities and above
    },
    "advanced": {
        "name": "Advanced (≤16 entities)",
        "description": "Comprehensive monitoring - higher resource usage",
        "max_entities": 16,
        "performance_impact": "medium",
        "recommended_for": "Power users, detailed analytics",
        "platforms": ALL_AVAILABLE_PLATFORMS,
        "priority_threshold": 3,  # Most entities included
    },
    "gps_focus": {
        "name": "GPS Focus (≤10 entities)",
        "description": "GPS tracking optimised for active dogs",
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
        "priority_threshold": 6,  # Keep non-critical GPS sensors out
        "preferred_modules": ["gps", "walk", "visitor"],
    },
    "health_focus": {
        "name": "Health Focus (≤10 entities)",
        "description": "Health monitoring optimised for senior dogs",
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
        "priority_threshold": 6,
        "preferred_modules": ["health", "feeding", "medication"],
    },
}

# Pre-computed module entity estimates to avoid rebuilding dictionaries during
# performance-critical calculations.
MODULE_ENTITY_ESTIMATES: Final[dict[str, dict[str, int]]] = {
    "feeding": {
        "basic": 2,  # last feeding + critical schedule helper
        "standard": 5,  # adds calories/portions without diagnostics
        "advanced": 8,  # detailed nutrition insights
        "health_focus": 5,  # curated for health automations
        "gps_focus": 2,  # minimal feeding context for GPS builds
    },
    "walk": {
        "basic": 2,  # last walk + count today
        "standard": 4,  # adds duration and weekly rollups
        "advanced": 6,  # full history/analytics
        "gps_focus": 5,  # GPS-centric walk metrics
        "health_focus": 3,  # walk data that feeds health scoring
    },
    "gps": {
        "basic": 1,  # location state only
        "standard": 3,  # adds accuracy/battery context
        "advanced": 5,  # altitude, heading, etc.
        "gps_focus": 6,  # full GPS feature set
        "health_focus": 2,  # minimal health context from GPS
    },
    "health": {
        "basic": 2,  # status + weight
        "standard": 3,  # adds trend scoring
        "advanced": 6,  # deep health analytics
        "health_focus": 8,  # full dedicated health set
        "gps_focus": 3,  # minimal health overlay
    },
    "notifications": {
        "basic": 1,
        "standard": 2,
        "advanced": 3,
        "gps_focus": 2,
        "health_focus": 2,
    },
    "dashboard": {
        "basic": 0,
        "standard": 1,
        "advanced": 2,
        "gps_focus": 1,
        "health_focus": 1,
    },
    "visitor": {
        "basic": 1,
        "standard": 2,
        "advanced": 3,
        "gps_focus": 2,
        "health_focus": 1,
    },
    "medication": {
        "basic": 1,
        "standard": 2,
        "advanced": 4,
        "health_focus": 5,
        "gps_focus": 1,
    },
    "training": {
        "basic": 1,
        "standard": 2,
        "advanced": 4,
        "gps_focus": 2,
        "health_focus": 2,
    },
    "grooming": {
        "basic": 1,
        "standard": 2,
        "advanced": 3,
        "health_focus": 3,
        "gps_focus": 1,
    },
    "garden": {
        "basic": 2,  # time + sessions only
        "standard": 5,  # adds poop + recent duration/summary
        "advanced": 8,  # statistics suite
        "gps_focus": 5,
        "health_focus": 6,
    },
}

_ESTIMATE_CACHE_MAX_SIZE: Final[int] = 128

_COMMON_PROFILE_PRESETS: Final[tuple[tuple[str, Mapping[str, bool]], ...]] = (
    (
        "standard",
        MappingProxyType(
            {
                "feeding": True,
                "walk": True,
                "notifications": True,
            }
        ),
    ),
    (
        "standard",
        MappingProxyType(
            {
                "feeding": True,
                "walk": True,
                "health": True,
                "garden": True,
                "notifications": True,
                "dashboard": True,
            }
        ),
    ),
    (
        "gps_focus",
        MappingProxyType(
            {
                "feeding": True,
                "walk": True,
                "gps": True,
                "notifications": True,
                "visitor": True,
            }
        ),
    ),
    (
        "health_focus",
        MappingProxyType(
            {
                "feeding": True,
                "health": True,
                "notifications": True,
                "medication": True,
                "grooming": True,
            }
        ),
    ),
    (
        "advanced",
        MappingProxyType(dict.fromkeys(MODULE_ENTITY_ESTIMATES, True)),
    ),
)


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
        self._performance_metrics_cache: OrderedDict[
            tuple[str, tuple[tuple[str, bool], ...]], dict[str, Any]
        ] = OrderedDict()
        self._last_estimate_key: tuple[str, tuple[tuple[str, bool], ...]] | None = None
        self._last_module_weights: dict[str, int] = {}
        self._last_synergy_score: int = 0
        self._last_triad_score: int = 0
        self._prewarm_caches()

    def _prewarm_caches(self) -> None:
        """Warm up internal caches for consistent performance."""

        default_modules = self._get_default_modules()
        default_estimate = self._get_entity_estimate(
            "standard", default_modules, log_invalid_inputs=False
        )

        default_module_dict = dict(default_modules)
        self.estimate_entity_count("standard", default_module_dict)
        self.get_performance_metrics("standard", default_module_dict)
        for priority in (3, 5, 7, 9):
            self.should_create_entity("standard", "sensor", "feeding", priority)

        for profile, modules in _COMMON_PROFILE_PRESETS:
            module_dict = dict(modules)
            self._get_entity_estimate(profile, module_dict, log_invalid_inputs=False)
            self.estimate_entity_count(profile, module_dict)
            self.get_performance_metrics(profile, module_dict)
            for priority in (3, 5, 7, 9):
                self.should_create_entity(profile, "sensor", "feeding", priority)

        # Ensure the default combination remains the active baseline after warming
        self._update_last_estimate_state(default_estimate)

    def _update_last_estimate_state(self, estimate: EntityEstimate) -> None:
        """Cache metadata derived from the most recent estimate."""

        module_weights = {
            module: index + 1
            for index, (module, enabled) in enumerate(estimate.module_signature)
            if enabled
        }

        self._last_estimate_key = (
            estimate.profile,
            estimate.module_signature,
        )
        self._last_module_weights = module_weights
        self._last_synergy_score = sum(
            module_weights[a] + module_weights[b]
            for a, b in combinations(module_weights, 2)
        )
        self._last_triad_score = sum(
            module_weights[a] + module_weights[b] + module_weights[c]
            for a, b, c in combinations(module_weights, 3)
        )

    def _enforce_metrics_runtime(self) -> None:
        """Yield control to the event loop after intensive calculations."""

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if loop.is_running():
            loop.call_soon(self._yield_control)

    @staticmethod
    def _yield_control() -> None:
        """No-op callback scheduled to allow the event loop to run."""

        return

    def _get_entity_estimate(
        self,
        profile: str,
        modules: Mapping[str, bool] | None,
        *,
        log_invalid_inputs: bool,
    ) -> EntityEstimate:
        """Return cached entity estimate for a profile and module set."""

        normalized_profile = self._normalize_profile(profile, log=log_invalid_inputs)
        normalized_modules = self._normalize_modules(modules, log=log_invalid_inputs)

        module_signature = tuple(sorted(normalized_modules.items()))
        cache_key = (
            normalized_profile,
            module_signature,
        )

        cached_estimate = self._estimate_cache.get(cache_key)
        if cached_estimate is not None:
            # Move the cached entry to the end to maintain LRU semantics
            self._estimate_cache.move_to_end(cache_key)
            return cached_estimate

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
                _LOGGER.warning("Invalid modules configuration, using defaults")
            return self._get_default_modules()

        module_dict = dict(modules)
        if not self._validate_modules(module_dict):
            if log:
                _LOGGER.warning("Invalid modules configuration, using defaults")
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

        estimate = self._get_entity_estimate(profile, modules, log_invalid_inputs=True)
        if estimate.raw_total > estimate.capacity:
            _LOGGER.debug(
                "Entity count capped from %d to %d for profile %s",  # pragma: no cover - log only
                estimate.raw_total,
                estimate.capacity,
                estimate.profile,
            )

        self._update_last_estimate_state(estimate)

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
            "notifications": True,
            "health": False,
            "garden": False,
            "gps": False,
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
        estimate = self._get_entity_estimate(profile, modules, log_invalid_inputs=False)
        cache_key = (estimate.profile, estimate.module_signature)

        cached_metrics = self._performance_metrics_cache.get(cache_key)
        if cached_metrics is not None:
            self._performance_metrics_cache.move_to_end(cache_key)
            self._enforce_metrics_runtime()
            return dict(cached_metrics)

        profile_config = ENTITY_PROFILES[estimate.profile]

        capacity = estimate.capacity
        utilization = 0.0 if capacity <= 0 else (estimate.final_count / capacity) * 100

        if self._last_estimate_key == cache_key and self._last_module_weights:
            module_weights = dict(self._last_module_weights)
            synergy_score = self._last_synergy_score
            triad_score = self._last_triad_score
        else:
            module_weights = {
                module: index + 1
                for index, (module, enabled) in enumerate(estimate.module_signature)
                if enabled
            }
            synergy_score = sum(
                module_weights[a] + module_weights[b]
                for a, b in combinations(module_weights, 2)
            )
            triad_score = sum(
                module_weights[a] + module_weights[b] + module_weights[c]
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

        metrics = {
            "profile": estimate.profile,
            "estimated_entities": estimate.final_count,
            "max_entities": profile_config["max_entities"],
            "performance_impact": profile_config["performance_impact"],
            "utilization_percentage": utilization,
            "enabled_modules": estimate.enabled_modules,
            "total_modules": estimate.total_modules,
        }

        self._performance_metrics_cache[cache_key] = metrics
        if len(self._performance_metrics_cache) > _ESTIMATE_CACHE_MAX_SIZE:
            self._performance_metrics_cache.popitem(last=False)

        self._enforce_metrics_runtime()
        return dict(metrics)
