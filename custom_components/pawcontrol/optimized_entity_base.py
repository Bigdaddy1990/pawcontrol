"""Optimized base entity classes for PawControl integration.

This module provides high-performance base entity classes that implement
Platinum-level optimizations including advanced caching, memory management,
async performance enhancements, and comprehensive error handling.

All platform entities should inherit from these optimized base classes to ensure
consistent performance characteristics and maintain Platinum quality standards.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+

Features:
- Multi-level caching with intelligent TTL management
- Memory-efficient state management with __slots__ optimization
- Profile-aware entity creation and lifecycle management
- Advanced async performance optimizations
- Comprehensive error handling and recovery
- Real-time performance monitoring and metrics
- Optimized device information management
- Intelligent state restoration and persistence
"""

from __future__ import annotations

import asyncio
import logging
import sys
import weakref
from abc import abstractmethod
from datetime import datetime, timedelta
from typing import Any, ClassVar, Final

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTR_DOG_ID, ATTR_DOG_NAME, DOMAIN
from .coordinator import PawControlCoordinator
from .utils import ensure_utc_datetime

_LOGGER = logging.getLogger(__name__)

# Performance optimization constants
CACHE_TTL_SECONDS: Final[dict[str, int]] = {
    "state": 30,  # Entity state cache TTL
    "attributes": 60,  # Attribute cache TTL
    "device_info": 300,  # Device info cache TTL (5 minutes)
    "availability": 10,  # Availability cache TTL
}

MEMORY_OPTIMIZATION: Final[dict[str, Any]] = {
    "max_cache_entries": 1000,  # Maximum cache entries per entity type
    "cache_cleanup_threshold": 0.8,  # When to trigger aggressive cleanup
    "weak_ref_cleanup_interval": 300,  # Seconds between weak reference cleanup
    "performance_sample_size": 100,  # Number of operations to track for performance
}

# Global caches with memory management
_STATE_CACHE: dict[str, tuple[Any, float]] = {}
_ATTRIBUTES_CACHE: dict[str, tuple[dict[str, Any], float]] = {}
_DEVICE_INFO_CACHE: dict[str, tuple[DeviceInfo, float]] = {}
_AVAILABILITY_CACHE: dict[str, tuple[bool, float]] = {}

# Performance tracking with weak references to prevent memory leaks
_PERFORMANCE_METRICS: dict[str, list[float]] = {}
_ENTITY_REGISTRY: set[weakref.ref] = set()


class PerformanceTracker:
    """Advanced performance tracking for entity operations."""

    __slots__ = (
        "_cache_hits",
        "_cache_misses",
        "_entity_id",
        "_error_count",
        "_operation_times",
    )

    def __init__(self, entity_id: str) -> None:
        """Initialize performance tracker for an entity.

        Args:
            entity_id: Unique identifier for the entity being tracked
        """
        self._entity_id = entity_id
        self._operation_times: list[float] = []
        self._error_count = 0
        self._cache_hits = 0
        self._cache_misses = 0

    def record_operation_time(self, operation_time: float) -> None:
        """Record an operation time for performance analysis.

        Args:
            operation_time: Time taken for the operation in seconds
        """
        self._operation_times.append(operation_time)

        # Limit memory usage by keeping only recent samples
        if len(self._operation_times) > MEMORY_OPTIMIZATION["performance_sample_size"]:
            self._operation_times = self._operation_times[
                -MEMORY_OPTIMIZATION["performance_sample_size"] :
            ]

    def record_error(self) -> None:
        """Record an error occurrence."""
        self._error_count += 1

    def record_cache_hit(self) -> None:
        """Record a cache hit for performance metrics."""
        self._cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record a cache miss for performance metrics."""
        self._cache_misses += 1

    def get_performance_summary(self) -> dict[str, Any]:
        """Get comprehensive performance summary.

        Returns:
            Dictionary containing performance metrics and analysis
        """
        if not self._operation_times:
            return {"status": "no_data"}

        return {
            "avg_operation_time": sum(self._operation_times)
            / len(self._operation_times),
            "min_operation_time": min(self._operation_times),
            "max_operation_time": max(self._operation_times),
            "total_operations": len(self._operation_times),
            "error_count": self._error_count,
            "error_rate": self._error_count / len(self._operation_times)
            if self._operation_times
            else 0,
            "cache_hit_rate": self._cache_hits
            / (self._cache_hits + self._cache_misses)
            * 100
            if (self._cache_hits + self._cache_misses) > 0
            else 0,
            "total_cache_operations": self._cache_hits + self._cache_misses,
        }


@callback
def _cleanup_global_caches() -> None:
    """Clean up global caches to prevent memory leaks.

    This function is called periodically to maintain cache health and
    prevent excessive memory usage from cache growth.
    """
    now = dt_util.utcnow().timestamp()
    cleanup_stats = {"cleaned": 0, "total": 0}

    # Clean up each cache type based on TTL
    for cache_name, (cache_dict, ttl) in [
        ("state", (_STATE_CACHE, CACHE_TTL_SECONDS["state"])),
        ("attributes", (_ATTRIBUTES_CACHE, CACHE_TTL_SECONDS["attributes"])),
        ("device_info", (_DEVICE_INFO_CACHE, CACHE_TTL_SECONDS["device_info"])),
        ("availability", (_AVAILABILITY_CACHE, CACHE_TTL_SECONDS["availability"])),
    ]:
        original_size = len(cache_dict)
        expired_keys = [
            key for key, (_, timestamp) in cache_dict.items() if now - timestamp > ttl
        ]

        for key in expired_keys:
            cache_dict.pop(key, None)

        cleaned = len(expired_keys)
        cleanup_stats["cleaned"] += cleaned
        cleanup_stats["total"] += original_size

        if cleaned > 0:
            _LOGGER.debug(
                "Cleaned %d/%d expired entries from %s cache",
                cleaned,
                original_size,
                cache_name,
            )

    # Clean up dead weak references
    _ENTITY_REGISTRY.clear()
    global_dead_refs = [ref for ref in _ENTITY_REGISTRY if ref() is None]
    for dead_ref in global_dead_refs:
        _ENTITY_REGISTRY.discard(dead_ref)

    if cleanup_stats["cleaned"] > 0:
        _LOGGER.info(
            "Cache cleanup completed: %d/%d entries cleaned (%.1f%% reduction)",
            cleanup_stats["cleaned"],
            cleanup_stats["total"],
            cleanup_stats["cleaned"] / cleanup_stats["total"] * 100
            if cleanup_stats["total"] > 0
            else 0,
        )


class OptimizedEntityBase(CoordinatorEntity[PawControlCoordinator], RestoreEntity):
    """Optimized base entity with advanced performance features.

    This base class provides comprehensive optimization features including:
    - Multi-level intelligent caching with TTL management
    - Memory-efficient operations using __slots__ where beneficial
    - Advanced performance tracking and monitoring
    - Optimized async operations with proper error handling
    - Intelligent state restoration and persistence
    - Profile-aware configuration and resource management

    All PawControl entities should inherit from this base class to ensure
    consistent high performance and maintain Platinum quality standards.
    """

    # Class-level performance tracking
    _performance_registry: ClassVar[dict[str, PerformanceTracker]] = {}
    _last_cache_cleanup: ClassVar[float] = 0

    # Essential attributes for optimal memory usage
    __slots__ = (
        "_cached_attributes",
        "_cached_state",
        "_dog_id",
        "_dog_name",
        "_entity_type",
        "_initialization_time",
        "_last_updated",
        "_performance_tracker",
        "_state_change_listeners",
    )

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        entity_type: str,
        *,
        unique_id_suffix: str | None = None,
        name_suffix: str | None = None,
        device_class: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize optimized entity with comprehensive tracking.

        Args:
            coordinator: Data coordinator for the entity
            dog_id: Unique identifier for the associated dog
            dog_name: Display name for the associated dog
            entity_type: Type of entity (sensor, binary_sensor, switch, etc.)
            unique_id_suffix: Optional suffix for unique ID customization
            name_suffix: Optional suffix for display name customization
            device_class: Home Assistant device class for the entity
            entity_category: Entity category for proper organization
            icon: Material Design icon for the entity
        """
        super().__init__(coordinator)

        # Core identification and tracking
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._entity_type = entity_type
        self._initialization_time = dt_util.utcnow()

        # Performance tracking setup
        entity_key = f"{dog_id}_{entity_type}"
        if unique_id_suffix:
            entity_key += f"_{unique_id_suffix}"

        self._performance_tracker = self._get_or_create_tracker(entity_key)

        # Initialize caches
        self._cached_state: Any = None
        self._cached_attributes: dict[str, Any] = {}
        self._last_updated: datetime | None = None
        self._state_change_listeners: list[callback] = []

        # Configure entity attributes
        self._setup_entity_configuration(
            unique_id_suffix, name_suffix, device_class, entity_category, icon
        )

        # Register entity for cleanup tracking
        _ENTITY_REGISTRY.add(weakref.ref(self))

        # Periodic cache cleanup
        self._maybe_cleanup_caches()

    def _setup_entity_configuration(
        self,
        unique_id_suffix: str | None,
        name_suffix: str | None,
        device_class: str | None,
        entity_category: EntityCategory | None,
        icon: str | None,
    ) -> None:
        """Set up entity configuration attributes.

        Args:
            unique_id_suffix: Optional unique ID suffix
            name_suffix: Optional name suffix
            device_class: Home Assistant device class
            entity_category: Entity category
            icon: Material Design icon
        """
        # Generate unique ID
        unique_id_parts = ["pawcontrol", self._dog_id, self._entity_type]
        if unique_id_suffix:
            unique_id_parts.append(unique_id_suffix)
        self._attr_unique_id = "_".join(unique_id_parts)

        # Generate display name
        name_parts = [self._dog_name]
        if name_suffix:
            name_parts.append(name_suffix)
        else:
            name_parts.append(self._entity_type.replace("_", " ").title())
        self._attr_name = " ".join(name_parts)

        # Set additional attributes
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_icon = icon
        self._attr_has_entity_name = True
        self._attr_should_poll = False

    @classmethod
    def _get_or_create_tracker(cls, entity_key: str) -> PerformanceTracker:
        """Get or create a performance tracker for an entity.

        Args:
            entity_key: Unique key for the entity

        Returns:
            PerformanceTracker instance for the entity
        """
        if entity_key not in cls._performance_registry:
            cls._performance_registry[entity_key] = PerformanceTracker(entity_key)
        return cls._performance_registry[entity_key]

    @callback
    def _maybe_cleanup_caches(self) -> None:
        """Perform cache cleanup if needed based on time and memory pressure."""
        now = dt_util.utcnow().timestamp()
        cleanup_interval = MEMORY_OPTIMIZATION["weak_ref_cleanup_interval"]

        if now - self._last_cache_cleanup > cleanup_interval:
            self._last_cache_cleanup = now
            _cleanup_global_caches()

    async def async_added_to_hass(self) -> None:
        """Enhanced entity addition with state restoration and performance tracking."""
        start_time = dt_util.utcnow()

        try:
            await super().async_added_to_hass()

            # Restore previous state if available
            await self._async_restore_state()

            # Record successful initialization
            operation_time = (dt_util.utcnow() - start_time).total_seconds()
            self._performance_tracker.record_operation_time(operation_time)

            _LOGGER.debug(
                "Entity %s added successfully in %.3f seconds",
                self._attr_unique_id,
                operation_time,
            )

        except Exception as err:
            self._performance_tracker.record_error()
            _LOGGER.error("Failed to add entity %s: %s", self._attr_unique_id, err)
            raise

    async def _async_restore_state(self) -> None:
        """Restore entity state with enhanced error handling."""
        if not (last_state := await self.async_get_last_state()):
            return

        try:
            await self._handle_state_restoration(last_state)
            _LOGGER.debug(
                "Restored state for %s: %s", self._attr_unique_id, last_state.state
            )
        except Exception as err:
            _LOGGER.warning(
                "Failed to restore state for %s: %s", self._attr_unique_id, err
            )

    async def _handle_state_restoration(self, last_state) -> None:
        """Handle state restoration - override in subclasses as needed.

        Args:
            last_state: Last known state from Home Assistant
        """
        # Base implementation - subclasses can override for specific logic
        pass

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return optimized device information with caching.

        Returns:
            DeviceInfo dictionary for proper device grouping
        """
        cache_key = f"device_{self._dog_id}"
        now = dt_util.utcnow().timestamp()

        # Check cache first
        if cache_key in _DEVICE_INFO_CACHE:
            cached_info, cache_time = _DEVICE_INFO_CACHE[cache_key]
            if now - cache_time < CACHE_TTL_SECONDS["device_info"]:
                self._performance_tracker.record_cache_hit()
                return cached_info

        # Generate device info
        device_info: DeviceInfo = {
            "identifiers": {(DOMAIN, self._dog_id)},
            "name": self._dog_name,
            "manufacturer": "PawControl",
            "model": "Smart Dog Monitoring System",
            "sw_version": "2.1.0",
            "configuration_url": f"https://github.com/BigDaddy1990/pawcontrol/wiki/dog-{self._dog_id}",
        }

        # Add additional info if available
        dog_data = self._get_dog_data_cached()
        if dog_data and "dog_info" in dog_data:
            dog_info = dog_data["dog_info"]
            if dog_breed := dog_info.get("dog_breed"):
                device_info["model"] = f"Smart Dog Monitoring - {dog_breed}"
            if dog_age := dog_info.get("dog_age"):
                device_info["suggested_area"] = (
                    f"Pet Area - {self._dog_name} ({dog_age}yo)"
                )

        # Cache the result
        _DEVICE_INFO_CACHE[cache_key] = (device_info, now)
        self._performance_tracker.record_cache_miss()

        return device_info

    @property
    def available(self) -> bool:
        """Enhanced availability check with caching and error handling.

        Returns:
            True if entity is available for operations
        """
        cache_key = f"available_{self._dog_id}_{self._entity_type}"
        now = dt_util.utcnow().timestamp()

        # Check cache first
        if cache_key in _AVAILABILITY_CACHE:
            cached_available, cache_time = _AVAILABILITY_CACHE[cache_key]
            if now - cache_time < CACHE_TTL_SECONDS["availability"]:
                self._performance_tracker.record_cache_hit()
                return cached_available

        # Calculate availability
        available = self._calculate_availability()

        # Cache result
        _AVAILABILITY_CACHE[cache_key] = (available, now)
        self._performance_tracker.record_cache_miss()

        return available

    def _calculate_availability(self) -> bool:
        """Calculate entity availability with comprehensive checks.

        Returns:
            True if entity should be considered available
        """
        # Check coordinator availability
        if not self.coordinator.available:
            return False

        # Check dog data availability
        dog_data = self._get_dog_data_cached()
        if not dog_data:
            return False

        # Check for recent updates (within last 10 minutes)
        if last_update := dog_data.get("last_update"):
            last_update_dt = ensure_utc_datetime(last_update)
            if last_update_dt is None:
                return False

            time_since_update = dt_util.utcnow() - last_update_dt
            if time_since_update > timedelta(minutes=10):
                return False

        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Enhanced state attributes with caching and performance tracking.

        Returns:
            Dictionary of additional state attributes
        """
        cache_key = f"attrs_{self._attr_unique_id}"
        now = dt_util.utcnow().timestamp()

        # Check cache first
        if cache_key in _ATTRIBUTES_CACHE:
            cached_attrs, cache_time = _ATTRIBUTES_CACHE[cache_key]
            if now - cache_time < CACHE_TTL_SECONDS["attributes"]:
                self._performance_tracker.record_cache_hit()
                return cached_attrs

        # Generate attributes
        start_time = dt_util.utcnow()

        try:
            attributes = self._generate_state_attributes()

            # Record performance
            operation_time = (dt_util.utcnow() - start_time).total_seconds()
            self._performance_tracker.record_operation_time(operation_time)

            # Cache result
            _ATTRIBUTES_CACHE[cache_key] = (attributes, now)
            self._performance_tracker.record_cache_miss()

            return attributes

        except Exception as err:
            self._performance_tracker.record_error()
            _LOGGER.error(
                "Error generating attributes for %s: %s", self._attr_unique_id, err
            )
            return self._get_fallback_attributes()

    def _generate_state_attributes(self) -> dict[str, Any]:
        """Generate state attributes - can be overridden in subclasses.

        Returns:
            Dictionary of state attributes
        """
        attributes: dict[str, Any] = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "entity_type": self._entity_type,
            "last_updated": dt_util.utcnow().isoformat(),
        }

        # Add dog information if available
        if (dog_data := self._get_dog_data_cached()) and (
            dog_info := dog_data.get("dog_info", {})
        ):
            attributes.update(
                {
                    "dog_breed": dog_info.get("dog_breed"),
                    "dog_age": dog_info.get("dog_age"),
                    "dog_size": dog_info.get("dog_size"),
                    "dog_weight": dog_info.get("dog_weight"),
                }
            )

            # Add performance metrics for debugging
            if (
                performance_summary
                := self._performance_tracker.get_performance_summary()
            ) and performance_summary.get("status") != "no_data":
                attributes["performance_metrics"] = {
                    "avg_operation_ms": round(
                        performance_summary["avg_operation_time"] * 1000, 2
                    ),
                    "cache_hit_rate": round(performance_summary["cache_hit_rate"], 1),
                    "error_rate": round(performance_summary["error_rate"] * 100, 1),
                }

        return attributes

    def _get_fallback_attributes(self) -> dict[str, Any]:
        """Get minimal fallback attributes when normal generation fails.

        Returns:
            Basic attribute dictionary for error scenarios
        """
        return {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "entity_type": self._entity_type,
            "status": "error",
            "last_updated": dt_util.utcnow().isoformat(),
        }

    def _get_dog_data_cached(self) -> dict[str, Any] | None:
        """Get dog data with intelligent caching.

        Returns:
            Dog data dictionary or None if unavailable
        """
        cache_key = f"dog_data_{self._dog_id}"
        now = dt_util.utcnow().timestamp()

        # Check cache first
        if cache_key in _STATE_CACHE:
            cached_data, cache_time = _STATE_CACHE[cache_key]
            if now - cache_time < CACHE_TTL_SECONDS["state"]:
                self._performance_tracker.record_cache_hit()
                return cached_data

        # Fetch from coordinator
        dog_data = None
        if self.coordinator.available:
            dog_data = self.coordinator.get_dog_data(self._dog_id)

        # Cache result (even if None to prevent repeated failures)
        _STATE_CACHE[cache_key] = (dog_data, now)
        self._performance_tracker.record_cache_miss()

        return dog_data

    def _get_module_data_cached(self, module: str) -> dict[str, Any]:
        """Get module data with caching.

        Args:
            module: Module name to retrieve data for

        Returns:
            Module data dictionary (empty if unavailable)
        """
        cache_key = f"module_{self._dog_id}_{module}"
        now = dt_util.utcnow().timestamp()

        # Check cache first
        if cache_key in _STATE_CACHE:
            cached_data, cache_time = _STATE_CACHE[cache_key]
            if now - cache_time < CACHE_TTL_SECONDS["state"]:
                self._performance_tracker.record_cache_hit()
                return cached_data

        # Fetch from coordinator
        module_data = {}
        if self.coordinator.available:
            module_data = self.coordinator.get_module_data(self._dog_id, module)

        # Cache result
        _STATE_CACHE[cache_key] = (module_data, now)
        self._performance_tracker.record_cache_miss()

        return module_data

    async def async_update(self) -> None:
        """Enhanced update method with performance tracking and error handling."""
        start_time = dt_util.utcnow()

        try:
            await super().async_update()

            # Clear relevant caches after update
            await self._async_invalidate_caches()

            # Record performance
            operation_time = (dt_util.utcnow() - start_time).total_seconds()
            self._performance_tracker.record_operation_time(operation_time)

        except Exception as err:
            self._performance_tracker.record_error()
            _LOGGER.error("Update failed for %s: %s", self._attr_unique_id, err)
            raise

    @callback
    async def _async_invalidate_caches(self) -> None:
        """Invalidate relevant caches after update."""
        cache_keys_to_remove = [
            f"dog_data_{self._dog_id}",
            f"attrs_{self._attr_unique_id}",
            f"available_{self._dog_id}_{self._entity_type}",
        ]

        for cache_key in cache_keys_to_remove:
            _STATE_CACHE.pop(cache_key, None)
            _ATTRIBUTES_CACHE.pop(cache_key, None)
            _AVAILABILITY_CACHE.pop(cache_key, None)

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics for this entity.

        Returns:
            Dictionary containing detailed performance information
        """
        return {
            "entity_id": self._attr_unique_id,
            "dog_id": self._dog_id,
            "entity_type": self._entity_type,
            "initialization_time": self._initialization_time.isoformat(),
            "uptime_seconds": (
                dt_util.utcnow() - self._initialization_time
            ).total_seconds(),
            "performance": self._performance_tracker.get_performance_summary(),
            "memory_usage_estimate": self._estimate_memory_usage(),
        }

    def _estimate_memory_usage(self) -> dict[str, Any]:
        """Estimate memory usage for this entity.

        Returns:
            Dictionary with memory usage estimates
        """
        # Calculate rough memory estimates
        base_size = sys.getsizeof(self)
        cache_size = sum(
            sys.getsizeof(key) + sys.getsizeof(value)
            for cache in [
                _STATE_CACHE,
                _ATTRIBUTES_CACHE,
                _DEVICE_INFO_CACHE,
                _AVAILABILITY_CACHE,
            ]
            for key, value in cache.items()
            if key.startswith(self._dog_id)
        )

        return {
            "base_entity_bytes": base_size,
            "cache_contribution_bytes": cache_size,
            "estimated_total_bytes": base_size + cache_size,
        }

    @abstractmethod
    def _get_entity_state(self) -> Any:
        """Get the current entity state - must be implemented by subclasses.

        Returns:
            Current state value for the entity
        """
        pass

    @callback
    def async_invalidate_cache(self) -> asyncio.Task[None]:
        """Public method to invalidate entity caches manually.

        Returns:
            The scheduled asyncio task handling cache invalidation.
        """
        cache_invalidation_task = asyncio.create_task(self._async_invalidate_caches())
        return cache_invalidation_task


class OptimizedSensorBase(OptimizedEntityBase):
    """Optimized base class specifically for sensor entities.

    Provides sensor-specific optimizations including value caching,
    state class management, and device class handling.
    """

    __slots__ = (
        "_attr_native_unit_of_measurement",
        "_attr_native_value",
        "_attr_state_class",
    )

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        sensor_type: str,
        *,
        device_class: str | None = None,
        state_class: str | None = None,
        unit_of_measurement: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize optimized sensor entity.

        Args:
            coordinator: Data coordinator
            dog_id: Dog identifier
            dog_name: Dog name
            sensor_type: Type of sensor
            device_class: Home Assistant device class
            state_class: State class for statistics
            unit_of_measurement: Unit of measurement
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            f"sensor_{sensor_type}",
            unique_id_suffix=sensor_type,
            name_suffix=sensor_type.replace("_", " ").title(),
            device_class=device_class,
            **kwargs,
        )

        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_native_value = None

    @property
    def native_value(self) -> Any:
        """Return the native sensor value with caching."""
        return self._attr_native_value

    def _get_entity_state(self) -> Any:
        """Get sensor state from native value."""
        return self.native_value


class OptimizedBinarySensorBase(OptimizedEntityBase):
    """Optimized base class specifically for binary sensor entities.

    Provides binary sensor-specific optimizations including boolean state
    management, icon handling, and device class support.
    """

    __slots__ = ("_attr_is_on", "_icon_off", "_icon_on")

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        sensor_type: str,
        *,
        device_class: str | None = None,
        icon_on: str | None = None,
        icon_off: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize optimized binary sensor entity.

        Args:
            coordinator: Data coordinator
            dog_id: Dog identifier
            dog_name: Dog name
            sensor_type: Type of binary sensor
            device_class: Home Assistant device class
            icon_on: Icon when sensor is on
            icon_off: Icon when sensor is off
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            f"binary_sensor_{sensor_type}",
            unique_id_suffix=sensor_type,
            name_suffix=sensor_type.replace("_", " ").title(),
            device_class=device_class,
            **kwargs,
        )

        self._attr_is_on = False
        self._icon_on = icon_on
        self._icon_off = icon_off

    @property
    def is_on(self) -> bool:
        """Return binary sensor state."""
        return self._attr_is_on

    @property
    def icon(self) -> str | None:
        """Return dynamic icon based on state."""
        if self.is_on and self._icon_on:
            return self._icon_on
        elif not self.is_on and self._icon_off:
            return self._icon_off
        return super().icon

    def _get_entity_state(self) -> bool:
        """Get binary sensor state."""
        return self.is_on


class OptimizedSwitchBase(OptimizedEntityBase, RestoreEntity):
    """Optimized base class specifically for switch entities.

    Provides switch-specific optimizations including state restoration,
    turn on/off operations, and enhanced error handling.
    """

    __slots__ = ("_attr_is_on", "_last_changed")

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        switch_type: str,
        *,
        device_class: str | None = None,
        initial_state: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize optimized switch entity.

        Args:
            coordinator: Data coordinator
            dog_id: Dog identifier
            dog_name: Dog name
            switch_type: Type of switch
            device_class: Home Assistant device class
            initial_state: Initial state for the switch
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            f"switch_{switch_type}",
            unique_id_suffix=switch_type,
            name_suffix=switch_type.replace("_", " ").title(),
            device_class=device_class,
            **kwargs,
        )

        self._attr_is_on = initial_state
        self._last_changed = dt_util.utcnow()

    @property
    def is_on(self) -> bool:
        """Return switch state."""
        return self._attr_is_on

    async def _handle_state_restoration(self, last_state) -> None:
        """Restore switch state from previous session."""
        if last_state.state in ("on", "off"):
            self._attr_is_on = last_state.state == "on"
            _LOGGER.debug(
                "Restored switch state for %s: %s",
                self._attr_unique_id,
                last_state.state,
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn switch on with performance tracking."""
        start_time = dt_util.utcnow()

        try:
            await self._async_turn_on_implementation(**kwargs)
            self._attr_is_on = True
            self._last_changed = dt_util.utcnow()
            self.async_write_ha_state()

            operation_time = (dt_util.utcnow() - start_time).total_seconds()
            self._performance_tracker.record_operation_time(operation_time)

        except Exception as err:
            self._performance_tracker.record_error()
            _LOGGER.error("Failed to turn on %s: %s", self._attr_unique_id, err)
            raise HomeAssistantError("Failed to turn on switch") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn switch off with performance tracking."""
        start_time = dt_util.utcnow()

        try:
            await self._async_turn_off_implementation(**kwargs)
            self._attr_is_on = False
            self._last_changed = dt_util.utcnow()
            self.async_write_ha_state()

            operation_time = (dt_util.utcnow() - start_time).total_seconds()
            self._performance_tracker.record_operation_time(operation_time)

        except Exception as err:
            self._performance_tracker.record_error()
            _LOGGER.error("Failed to turn off %s: %s", self._attr_unique_id, err)
            raise HomeAssistantError("Failed to turn off switch") from err

    async def _async_turn_on_implementation(self, **kwargs: Any) -> None:
        """Implement turn on logic - override in subclasses."""
        pass

    async def _async_turn_off_implementation(self, **kwargs: Any) -> None:
        """Implement turn off logic - override in subclasses."""
        pass

    def _get_entity_state(self) -> bool:
        """Get switch state."""
        return self.is_on

    def _generate_state_attributes(self) -> dict[str, Any]:
        """Generate switch-specific attributes."""
        attributes = super()._generate_state_attributes()
        attributes.update(
            {
                "last_changed": self._last_changed.isoformat(),
                "switch_type": self._entity_type,
            }
        )
        return attributes


# Utility functions for entity management


async def create_optimized_entities_batched(
    entities: list[OptimizedEntityBase],
    async_add_entities_callback: Any,
    batch_size: int = 15,
    delay_between_batches: float = 0.005,
) -> None:
    """Create entities in optimized batches to prevent registry overload.

    Args:
        entities: List of entities to add
        async_add_entities_callback: Home Assistant callback for adding entities
        batch_size: Number of entities per batch
        delay_between_batches: Delay between batches in seconds
    """
    if not entities:
        return

    total_entities = len(entities)
    _LOGGER.debug(
        "Adding %d optimized entities in batches of %d", total_entities, batch_size
    )

    for i in range(0, total_entities, batch_size):
        batch = entities[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            "Processing optimized entity batch %d/%d with %d entities",
            batch_num,
            total_batches,
            len(batch),
        )

        async_add_entities_callback(batch, update_before_add=False)

        if i + batch_size < total_entities:
            await asyncio.sleep(delay_between_batches)

    _LOGGER.info(
        "Successfully added %d optimized entities in %d batches",
        total_entities,
        (total_entities + batch_size - 1) // batch_size,
    )


def get_global_performance_stats() -> dict[str, Any]:
    """Get comprehensive performance statistics for all entities.

    Returns:
        Dictionary with global performance metrics
    """
    total_entities = len(_ENTITY_REGISTRY)
    active_entities = sum(1 for ref in _ENTITY_REGISTRY if ref() is not None)

    cache_stats = {
        "state_cache_size": len(_STATE_CACHE),
        "attributes_cache_size": len(_ATTRIBUTES_CACHE),
        "device_info_cache_size": len(_DEVICE_INFO_CACHE),
        "availability_cache_size": len(_AVAILABILITY_CACHE),
    }

    performance_summaries = [
        summary
        for tracker in OptimizedEntityBase._performance_registry.values()
        if (summary := tracker.get_performance_summary())
        and summary.get("status") != "no_data"
    ]

    if performance_summaries:
        avg_operation_time = sum(
            s["avg_operation_time"] for s in performance_summaries
        ) / len(performance_summaries)
        avg_cache_hit_rate = sum(
            s["cache_hit_rate"] for s in performance_summaries
        ) / len(performance_summaries)
        total_errors = sum(s["error_count"] for s in performance_summaries)
    else:
        avg_operation_time = avg_cache_hit_rate = total_errors = 0

    return {
        "total_entities_registered": total_entities,
        "active_entities": active_entities,
        "cache_statistics": cache_stats,
        "average_operation_time_ms": round(avg_operation_time * 1000, 2),
        "average_cache_hit_rate": round(avg_cache_hit_rate, 1),
        "total_errors": total_errors,
        "entities_with_performance_data": len(performance_summaries),
    }
