"""Configuration flow for Paw Control integration with entity profile optimization.

This module provides a comprehensive configuration flow that meets Home Assistant's
Platinum quality standards. It uses a modular architecture with separate mixins
for different functionality areas to maintain code organization and readability.

NEW: Includes entity profile selection for performance optimization (54→8-18 entities per dog).

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import time
from functools import lru_cache
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import callback

from .config_flow_base import INTEGRATION_SCHEMA, PawControlBaseConfigFlow
from .config_flow_dashboard_extension import DashboardFlowMixin
from .config_flow_dogs import DogManagementMixin
from .config_flow_external import ExternalEntityConfigurationMixin
from .config_flow_modules import ModuleConfigurationMixin
from .const import (
    CONF_DOGS,
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT_MIN,
    CONF_RESET_TIME,
    CONF_SOURCES,
    DEFAULT_DASHBOARD_MODE,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_REMINDER_REPEAT_MIN,
    DEFAULT_RESET_TIME,
    MODULE_GPS,
)
from .options_flow import PawControlOptionsFlow
from .types import is_dog_config_valid

_LOGGER = logging.getLogger(__name__)

# Performance optimization constants
VALIDATION_CACHE_TTL = 60  # Cache validation results for 60 seconds
MAX_CONCURRENT_VALIDATIONS = 3
VALIDATION_TIMEOUT = 10  # Maximum time for validation operations

# Entity profile definitions with performance impact
ENTITY_PROFILES = {
    "basic": {
        "name": "Basic (8 entities)",
        "description": "Essential monitoring only - Best performance",
        "max_entities": 8,
        "performance_impact": "minimal",
        "recommended_for": "Single dog, basic monitoring",
    },
    "standard": {
        "name": "Standard (12 entities)",
        "description": "Balanced monitoring with GPS - Good performance",
        "max_entities": 12,
        "performance_impact": "low",
        "recommended_for": "Most users, balanced functionality",
    },
    "advanced": {
        "name": "Advanced (18 entities)",
        "description": "Comprehensive monitoring - Higher resource usage",
        "max_entities": 18,
        "performance_impact": "medium",
        "recommended_for": "Power users, detailed analytics",
    },
    "gps_focus": {
        "name": "GPS Focus (10 entities)",
        "description": "GPS tracking optimized - Good for active dogs",
        "max_entities": 10,
        "performance_impact": "low",
        "recommended_for": "Active dogs, outdoor adventures",
    },
    "health_focus": {
        "name": "Health Focus (10 entities)",
        "description": "Health monitoring optimized - Good for senior dogs",
        "max_entities": 10,
        "performance_impact": "low",
        "recommended_for": "Senior dogs, health conditions",
    },
}

# Profile schema for validation
PROFILE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_profile", default="standard"): vol.In(
            list(ENTITY_PROFILES.keys())
        )
    }
)


class ValidationCache:
    """Thread-safe validation cache with TTL support."""

    def __init__(self, ttl: int = VALIDATION_CACHE_TTL) -> None:
        """Initialize validation cache with TTL.

        Args:
            ttl: Time-to-live for cache entries in seconds
        """
        self._cache: dict[str, tuple[float, Any]] = {}
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Get cached validation result if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
        async with self._lock:
            if key in self._cache:
                timestamp, value = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    return value
                # Clean up expired entry
                del self._cache[key]
        return None

    async def set(self, key: str, value: Any) -> None:
        """Cache validation result with current timestamp.

        Args:
            key: Cache key
            value: Value to cache
        """
        async with self._lock:
            self._cache[key] = (time.time(), value)

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()


class PawControlConfigFlow(
    DashboardFlowMixin,
    ExternalEntityConfigurationMixin,
    ModuleConfigurationMixin,
    DogManagementMixin,
    PawControlBaseConfigFlow,
):
    """Handle configuration flow for Paw Control integration.

    This config flow provides a comprehensive setup experience that guides
    users through configuring their dogs and initial settings. It uses a
    modular architecture with separate mixins for different functionality
    areas while maintaining extensive validation and user-friendly interface.

    NEW: Includes entity profile selection for performance optimization.
    Reduces entity count from 54+ to 8-18 per dog based on user needs.

    Designed for Home Assistant 2025.9.0+ with Platinum quality standards.
    Optimized for Python 3.13+ with improved async performance and caching.
    """

    def __init__(self) -> None:
        """Initialize the configuration flow with enhanced state management."""
        super().__init__()
        self._step_stack: list[str] = []
        self._enabled_modules: dict[str, bool] = {}
        self._external_entities: dict[str, str] = {}
        self._validation_cache = ValidationCache()
        self._validation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_VALIDATIONS)

        # Entity profile configuration
        self._entity_profile: str = "standard"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step with enhanced validation.

        This is the entry point for the configuration flow. It collects
        basic integration information and validates uniqueness.

        Args:
            user_input: User-provided configuration data

        Returns:
            Configuration flow result for next step or completion
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                integration_name = user_input["name"].strip()

                # Check validation cache first
                cache_key = f"integration_name_{integration_name}"
                cached_result = await self._validation_cache.get(cache_key)

                if cached_result is None:
                    # Enhanced validation with async checking and timeout
                    async with self._validation_semaphore:
                        try:
                            async with asyncio.timeout(VALIDATION_TIMEOUT):
                                validation_result = (
                                    await self._async_validate_integration_name(
                                        integration_name
                                    )
                                )
                            await self._validation_cache.set(
                                cache_key, validation_result
                            )
                        except asyncio.TimeoutError:
                            _LOGGER.error(
                                "Validation timeout for integration name: %s",
                                integration_name,
                            )
                            errors["base"] = "validation_timeout"
                            validation_result = {"valid": False, "errors": errors}
                else:
                    validation_result = cached_result

                if validation_result["valid"]:
                    # Set unique ID with enhanced collision detection
                    unique_id = self._generate_unique_id(integration_name)
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    self._integration_name = integration_name
                    return await self.async_step_add_dog()
                else:
                    errors = validation_result["errors"]

            except Exception as err:
                _LOGGER.error("Error processing user input: %s", err, exc_info=True)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=INTEGRATION_SCHEMA,
            errors=errors,
            description_placeholders={
                "integration_name": "Paw Control",
                "docs_url": "https://github.com/BigDaddy1990/pawcontrol",
                "version": "2.0.0",  # Updated for profile system
                "ha_version": "2025.9.0+",
                "features": self._get_feature_summary_cached(),
                "performance_note": "New: Entity profile selection for optimized performance",
            },
        )

    async def async_step_entity_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle entity profile selection for performance optimization.

        This step allows users to choose their entity profile based on their
        monitoring needs and system performance requirements.

        Args:
            user_input: Profile selection data

        Returns:
            Configuration flow result for next step
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                profile = user_input["entity_profile"]

                # Validate profile exists
                if profile not in ENTITY_PROFILES:
                    errors["entity_profile"] = "invalid_profile"
                else:
                    self._entity_profile = profile
                    _LOGGER.info(
                        "Selected entity profile '%s' for %d dogs - max %d entities per dog",
                        profile,
                        len(self._dogs),
                        ENTITY_PROFILES[profile]["max_entities"],
                    )

                    # Check if dashboard configuration is needed
                    if (
                        hasattr(self, "_needs_dashboard_config")
                        and self._needs_dashboard_config
                    ):
                        return await self.async_step_dashboard()
                    else:
                        return await self.async_step_final_setup()

            except Exception as err:
                _LOGGER.error(
                    "Error processing profile selection: %s", err, exc_info=True
                )
                errors["base"] = "unknown"

        # Calculate estimated entity counts for each profile
        profile_estimates = self._calculate_profile_estimates()

        # Determine recommended profile based on configuration
        recommended_profile = self._get_recommended_profile()

        return self.async_show_form(
            step_id="entity_profile",
            data_schema=PROFILE_SCHEMA,
            errors=errors,
            description_placeholders={
                "dog_count": str(len(self._dogs)),
                "current_estimate": str(profile_estimates.get("standard", 12)),
                "recommended_profile": ENTITY_PROFILES[recommended_profile]["name"],
                "performance_info": self._get_performance_comparison(),
                "legacy_count": "54",  # Legacy entity count
                "improvement": f"{int((1 - profile_estimates.get('standard', 12) / 54) * 100)}%",
            },
        )

    def _calculate_profile_estimates(self) -> dict[str, int]:
        """Calculate estimated entity counts for each profile based on current dogs.

        Returns:
            Dictionary mapping profile names to estimated entity counts
        """
        estimates = {}

        for profile_name, profile_config in ENTITY_PROFILES.items():
            # Estimate based on enabled modules and profile limits
            base_entities = 3  # Core entities always present

            # Count module-based entities for first dog (representative)
            if self._dogs:
                dog = self._dogs[0]
                modules = dog.get("modules", {})

                # Estimate feeding entities
                if modules.get("feeding", False):
                    feeding_entities = {
                        "basic": 3,
                        "standard": 6,
                        "advanced": 10,
                        "health_focus": 4,
                    }.get(profile_name, 3)
                    base_entities += feeding_entities

                # Estimate walk entities
                if modules.get("walk", False):
                    walk_entities = {
                        "basic": 2,
                        "standard": 4,
                        "advanced": 6,
                        "gps_focus": 4,
                    }.get(profile_name, 2)
                    base_entities += walk_entities

                # Estimate GPS entities
                if modules.get("gps", False):
                    gps_entities = {
                        "basic": 2,
                        "standard": 4,
                        "advanced": 5,
                        "gps_focus": 5,
                    }.get(profile_name, 2)
                    base_entities += gps_entities

                # Estimate health entities
                if modules.get("health", False):
                    health_entities = {
                        "basic": 2,
                        "standard": 4,
                        "advanced": 6,
                        "health_focus": 6,
                    }.get(profile_name, 2)
                    base_entities += health_entities

            # Apply profile limit
            estimates[profile_name] = min(base_entities, profile_config["max_entities"])

        return estimates

    def _get_recommended_profile(self) -> str:
        """Get recommended profile based on current configuration.

        Returns:
            Recommended profile name
        """
        if not self._dogs:
            return "standard"

        # Analyze configuration complexity
        has_multiple_dogs = len(self._dogs) > 1
        has_gps = any(dog.get("modules", {}).get("gps", False) for dog in self._dogs)
        has_health = any(
            dog.get("modules", {}).get("health", False) for dog in self._dogs
        )
        has_complex_feeding = any(
            len(dog.get("modules", {}).get("special_diet", [])) > 2
            for dog in self._dogs
        )

        # Recommendation logic
        if has_multiple_dogs and (has_gps or has_complex_feeding):
            return "advanced"
        elif has_gps and not has_health:
            return "gps_focus"
        elif has_health and not has_gps:
            return "health_focus"
        elif has_gps or has_health:
            return "standard"
        else:
            return "basic"

    def _get_performance_comparison(self) -> str:
        """Get performance comparison text for the UI.

        Returns:
            Formatted performance comparison string
        """
        estimates = self._calculate_profile_estimates()

        comparison_lines = []
        for profile_name, estimate in estimates.items():
            profile_config = ENTITY_PROFILES[profile_name]
            reduction = int((1 - estimate / 54) * 100)
            comparison_lines.append(
                f"• {profile_config['name']}: {estimate} entities (-{reduction}%) - {profile_config['description']}"
            )

        return "\n".join(comparison_lines)

    async def async_step_final_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete the configuration setup with profile integration.

        This final step creates the config entry with all collected
        data including the selected entity profile.

        Args:
            user_input: Final confirmation from user

        Returns:
            Configuration entry creation result
        """
        # Validate that we have at least one dog
        if not self._dogs:
            _LOGGER.error("No dogs configured during setup")
            return self.async_abort(reason="no_dogs_configured")

        try:
            # Create comprehensive configuration data with profile
            config_data = {
                "name": self._integration_name,
                CONF_DOGS: self._dogs,
                "setup_version": self.VERSION,
                "setup_timestamp": time.time(),
                "entity_profile": self._entity_profile,  # NEW: Include profile in config
            }

            # Add external entities configuration if configured
            if self._external_entities:
                config_data[CONF_SOURCES] = self._external_entities

            # Create intelligent default options based on configuration and profile
            options_data = await self._create_intelligent_options(config_data)
            if hasattr(self, "_dashboard_config"):
                options_data.update(self._dashboard_config)

            # Add profile to options for easy access
            options_data["entity_profile"] = self._entity_profile

            # Validate configuration integrity with proper async handling
            if self._dogs:
                try:
                    async with asyncio.timeout(5):
                        is_valid = await self._validate_dog_config_async(self._dogs[0])
                        if not is_valid:
                            raise ValueError("Invalid dog configuration detected")
                except asyncio.TimeoutError:
                    _LOGGER.warning(
                        "Dog config validation timeout, proceeding with caution"
                    )

            # Calculate final entity estimates for logging
            estimates = self._calculate_profile_estimates()
            total_estimated_entities = estimates.get(self._entity_profile, 12) * len(
                self._dogs
            )
            legacy_entities = 54 * len(self._dogs)
            reduction_percent = int(
                (1 - total_estimated_entities / legacy_entities) * 100
            )

            _LOGGER.info(
                "Creating Paw Control config entry '%s' with %d dogs, profile '%s' "
                "- Estimated %d entities (-%d%% vs legacy %d entities)",
                self._integration_name,
                len(self._dogs),
                self._entity_profile,
                total_estimated_entities,
                reduction_percent,
                legacy_entities,
            )

            # Clear validation cache after successful setup
            await self._validation_cache.clear()

            return self.async_create_entry(
                title=f"{self._integration_name} ({ENTITY_PROFILES[self._entity_profile]['name']})",
                data=config_data,
                options=options_data,
            )

        except Exception as err:
            _LOGGER.error("Failed to create config entry: %s", err, exc_info=True)
            return self.async_abort(reason="setup_failed")

    async def _create_intelligent_options(
        self, config_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create intelligent default options based on configuration and profile.

        Optimized with better performance analysis and profile awareness.

        Args:
            config_data: Complete configuration data

        Returns:
            Optimized options dictionary
        """
        dogs = config_data[CONF_DOGS]
        profile = config_data.get("entity_profile", "standard")

        # Analyze configuration for intelligent defaults with optimized checks
        has_gps = any(
            dog.get("modules", {}).get(MODULE_GPS, False) or bool(dog.get("gps_config"))
            for dog in dogs
        )
        has_multiple_dogs = len(dogs) > 1
        has_large_dogs = any(dog.get("dog_size") in ("large", "giant") for dog in dogs)

        # Performance mode based on profile and complexity
        performance_mode = self._calculate_performance_mode_with_profile(
            profile, has_gps, has_multiple_dogs, has_large_dogs
        )

        # Update interval based on profile and features
        update_interval = self._calculate_update_interval_with_profile(
            profile, has_gps, has_multiple_dogs
        )

        return {
            CONF_RESET_TIME: DEFAULT_RESET_TIME,
            CONF_NOTIFICATIONS: {
                CONF_QUIET_HOURS: True,
                CONF_QUIET_START: "22:00:00",
                CONF_QUIET_END: "07:00:00",
                CONF_REMINDER_REPEAT_MIN: DEFAULT_REMINDER_REPEAT_MIN,
                "priority_notifications": has_large_dogs,
                "summary_notifications": has_multiple_dogs,
            },
            CONF_GPS_UPDATE_INTERVAL: update_interval,
            CONF_GPS_ACCURACY_FILTER: DEFAULT_GPS_ACCURACY_FILTER,
            CONF_GPS_DISTANCE_FILTER: DEFAULT_GPS_DISTANCE_FILTER,
            "dashboard_mode": DEFAULT_DASHBOARD_MODE if has_multiple_dogs else "cards",
            "performance_mode": performance_mode,
            "data_retention_days": 90,
            "auto_backup": has_multiple_dogs,
            "debug_logging": False,
            # Profile-specific optimizations
            "batch_updates": profile in ["basic", "standard"],
            "cache_aggressive": profile == "basic",
            "entity_polling": profile != "basic",
        }

    @staticmethod
    def _calculate_performance_mode_with_profile(
        profile: str, has_gps: bool, has_multiple_dogs: bool, has_large_dogs: bool
    ) -> str:
        """Calculate optimal performance mode based on profile and features.

        Args:
            profile: Selected entity profile
            has_gps: Whether GPS tracking is enabled
            has_multiple_dogs: Whether multiple dogs are configured
            has_large_dogs: Whether large/giant dogs are configured

        Returns:
            Performance mode string
        """
        # Profile-aware performance mode calculation
        if profile == "basic":
            return "minimal"
        elif profile == "advanced" and (has_multiple_dogs or has_gps):
            return "full"
        elif has_multiple_dogs and (has_gps or has_large_dogs):
            return "balanced"
        elif has_gps or has_multiple_dogs:
            return "balanced"
        else:
            return "minimal"

    @staticmethod
    def _calculate_update_interval_with_profile(
        profile: str, has_gps: bool, has_multiple_dogs: bool
    ) -> int:
        """Calculate optimal update interval based on profile and features.

        Args:
            profile: Selected entity profile
            has_gps: Whether GPS tracking is enabled
            has_multiple_dogs: Whether multiple dogs are configured

        Returns:
            Update interval in seconds
        """
        # Profile-aware update interval calculation
        if profile == "basic":
            return 180  # Longer intervals for basic profile
        elif profile == "gps_focus" and has_gps:
            return 30  # Faster updates for GPS focus
        elif has_gps:
            return 60 if has_multiple_dogs else 45
        elif profile == "advanced":
            return 60  # Standard for advanced monitoring
        else:
            return 120  # Conservative for other profiles

    async def _validate_dog_config_async(self, dog_config: dict[str, Any]) -> bool:
        """Async validation of dog configuration with improved error handling.

        Args:
            dog_config: Dog configuration to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check if synchronous validation function exists and wrap it
            if hasattr(self, "is_dog_config_valid"):
                # Run synchronous validation in executor to avoid blocking
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, is_dog_config_valid, dog_config)
            else:
                # Fallback to simple validation
                return is_dog_config_valid(dog_config)
        except Exception as err:
            _LOGGER.error("Error validating dog config: %s", err)
            return False

    @lru_cache(maxsize=1)
    def _get_feature_summary_cached(self) -> str:
        """Get cached feature summary for better performance.

        Uses LRU cache to avoid regenerating the same static content.

        Returns:
            Formatted feature list string
        """
        return self._get_feature_summary()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PawControlOptionsFlow:
        """Create the options flow for post-setup configuration.

        Args:
            config_entry: The config entry to create options flow for

        Returns:
            Enhanced options flow instance for advanced configuration
        """
        return PawControlOptionsFlow(config_entry)

    async def __aenter__(self) -> "PawControlConfigFlow":
        """Async context manager entry for resource management.

        Returns:
            Self for context management
        """
        # Initialize any async resources if needed
        _LOGGER.debug("Entering PawControl config flow context")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit for cleanup.

        Args:
            exc_type: Exception type if any
            exc_val: Exception value if any
            exc_tb: Exception traceback if any
        """
        # Clean up resources
        await self._validation_cache.clear()
        _LOGGER.debug("Exiting PawControl config flow context")
