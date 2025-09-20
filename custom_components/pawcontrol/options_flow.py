"""Options flow for Paw Control integration with profile-based entity management.

This module provides comprehensive post-setup configuration options for the
Paw Control integration. It allows users to modify all aspects of their
configuration after initial setup with organized menu-driven navigation.

UPDATED: Adds entity profile selection for performance optimization
Integrates with EntityFactory for intelligent entity management
ENHANCED: GPS and Geofencing functionality per fahrplan.txt requirements

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.helpers import selector

from .config_flow_profile import (
    DEFAULT_PROFILE,
    get_profile_selector_options,
    validate_profile_selection,
)
from .const import (
    CONF_DASHBOARD_MODE,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_EXTERNAL_INTEGRATIONS,
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT_MIN,
    CONF_RESET_TIME,
    DASHBOARD_MODE_SELECTOR_OPTIONS,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_GPS_UPDATE_INTERVAL,
    DEFAULT_REMINDER_REPEAT_MIN,
    DEFAULT_RESET_TIME,
    GPS_ACCURACY_FILTER_SELECTOR,
    GPS_UPDATE_INTERVAL_SELECTOR,
    MAX_GEOFENCE_RADIUS,
    MIN_GEOFENCE_RADIUS,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .entity_factory import ENTITY_PROFILES, EntityFactory
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)


class PawControlOptionsFlow(OptionsFlow):
    """Handle options flow for Paw Control integration with Platinum UX.

    This comprehensive options flow allows users to modify all aspects
    of their Paw Control configuration after initial setup. It provides
    organized menu-driven navigation and extensive customization options
    with modern UI patterns and enhanced validation.

    UPDATED: Includes entity profile management for performance optimization
    ENHANCED: GPS and Geofencing configuration per requirements
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow with enhanced state management.

        Args:
            config_entry: Configuration entry to modify
        """
        self._config_entry = config_entry
        self._current_dog: DogConfigData | None = None
        self._dogs: list[DogConfigData] = [
            d.copy() for d in self._config_entry.data.get(CONF_DOGS, [])
        ]
        self._navigation_stack: list[str] = []
        self._unsaved_changes: dict[str, Any] = {}

        # Initialize entity factory and caches for profile calculations
        self._entity_factory = EntityFactory(None)
        self._profile_cache: dict[str, dict[str, Any]] = {}
        self._entity_estimates_cache: dict[str, dict[str, Any]] = {}

    def _invalidate_profile_caches(self) -> None:
        """Clear cached profile data when configuration changes."""

        self._profile_cache.clear()
        self._entity_estimates_cache.clear()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the main options menu with enhanced navigation.

        Provides organized access to all configuration categories
        with clear descriptions and intelligent suggestions.

        Args:
            user_input: User menu selection

        Returns:
            Configuration flow result for selected option
        """
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "entity_profiles",  # NEW: Profile management
                "manage_dogs",
                "performance_settings",  # NEW: Performance & profiles
                "gps_settings",
                "geofence_settings",  # NEW: Geofencing configuration
                "notifications",
                "feeding_settings",
                "health_settings",
                "system_settings",
                "dashboard_settings",
                "advanced_settings",
                "import_export",
            ],
        )

    # NEW: Geofencing configuration step per requirements
    async def async_step_geofence_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure geofencing and zone settings.

        NEW: Implements missing geofencing configuration per fahrplan.txt requirements.
        Provides geofence_lat, geofence_lon, geofence_radius, and alert configuration.
        """
        if user_input is not None:
            try:
                # Validate geofence radius
                radius = user_input.get("geofence_radius_m", 50)
                if radius < MIN_GEOFENCE_RADIUS or radius > MAX_GEOFENCE_RADIUS:
                    return self.async_show_form(
                        step_id="geofence_settings",
                        data_schema=self._get_geofence_settings_schema(user_input),
                        errors={"geofence_radius_m": "radius_out_of_range"},
                    )

                # Update geofencing settings in options
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        "geofence_settings": {
                            "geofencing_enabled": user_input.get(
                                "geofencing_enabled", False
                            ),
                            "geofence_lat": user_input.get("geofence_lat"),
                            "geofence_lon": user_input.get("geofence_lon"),
                            "geofence_radius_m": radius,
                            "geofence_alerts_enabled": user_input.get(
                                "geofence_alerts_enabled", True
                            ),
                            "use_home_location": user_input.get(
                                "use_home_location", True
                            ),
                            "safe_zone_alerts": user_input.get(
                                "safe_zone_alerts", True
                            ),
                            "restricted_zone_alerts": user_input.get(
                                "restricted_zone_alerts", True
                            ),
                            "zone_exit_notifications": user_input.get(
                                "zone_exit_notifications", True
                            ),
                            "zone_entry_notifications": user_input.get(
                                "zone_entry_notifications", True
                            ),
                        }
                    }
                )

                return self.async_create_entry(title="", data=new_options)

            except Exception as err:
                _LOGGER.error("Error updating geofence settings: %s", err)
                return self.async_show_form(
                    step_id="geofence_settings",
                    data_schema=self._get_geofence_settings_schema(user_input),
                    errors={"base": "geofence_update_failed"},
                )

        return self.async_show_form(
            step_id="geofence_settings",
            data_schema=self._get_geofence_settings_schema(),
            description_placeholders=self._get_geofence_description_placeholders(),
        )

    def _get_geofence_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get geofencing settings schema with current values."""
        current_options = self._config_entry.options
        current_geofence = current_options.get("geofence_settings", {})
        current_values = user_input or {}

        # Get Home Assistant's home location as default
        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude

        return vol.Schema(
            {
                vol.Optional(
                    "geofencing_enabled",
                    default=current_values.get(
                        "geofencing_enabled",
                        current_geofence.get("geofencing_enabled", False),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "use_home_location",
                    default=current_values.get(
                        "use_home_location",
                        current_geofence.get("use_home_location", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "geofence_lat",
                    default=current_values.get(
                        "geofence_lat", current_geofence.get("geofence_lat", home_lat)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-90.0,
                        max=90.0,
                        step=0.000001,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "geofence_lon",
                    default=current_values.get(
                        "geofence_lon", current_geofence.get("geofence_lon", home_lon)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-180.0,
                        max=180.0,
                        step=0.000001,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "geofence_radius_m",
                    default=current_values.get(
                        "geofence_radius_m",
                        current_geofence.get("geofence_radius_m", 50),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_GEOFENCE_RADIUS,
                        max=MAX_GEOFENCE_RADIUS,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="meters",
                    )
                ),
                vol.Optional(
                    "geofence_alerts_enabled",
                    default=current_values.get(
                        "geofence_alerts_enabled",
                        current_geofence.get("geofence_alerts_enabled", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "safe_zone_alerts",
                    default=current_values.get(
                        "safe_zone_alerts",
                        current_geofence.get("safe_zone_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "restricted_zone_alerts",
                    default=current_values.get(
                        "restricted_zone_alerts",
                        current_geofence.get("restricted_zone_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "zone_entry_notifications",
                    default=current_values.get(
                        "zone_entry_notifications",
                        current_geofence.get("zone_entry_notifications", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "zone_exit_notifications",
                    default=current_values.get(
                        "zone_exit_notifications",
                        current_geofence.get("zone_exit_notifications", True),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    def _get_geofence_description_placeholders(self) -> dict[str, str]:
        """Get description placeholders for geofencing configuration."""
        current_options = self._config_entry.options
        current_geofence = current_options.get("geofence_settings", {})

        # Get Home Assistant's home location
        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude

        # Current configuration status
        geofencing_enabled = current_geofence.get("geofencing_enabled", False)
        current_lat = current_geofence.get("geofence_lat", home_lat)
        current_lon = current_geofence.get("geofence_lon", home_lon)
        current_radius = current_geofence.get("geofence_radius_m", 50)

        status = "Enabled" if geofencing_enabled else "Disabled"
        location_desc = f"Lat: {current_lat:.6f}, Lon: {current_lon:.6f}"

        return {
            "current_status": status,
            "current_location": location_desc,
            "current_radius": str(current_radius),
            "home_location": f"Lat: {home_lat:.6f}, Lon: {home_lon:.6f}",
            "radius_range": f"{MIN_GEOFENCE_RADIUS}-{MAX_GEOFENCE_RADIUS}",
            "dogs_with_gps": str(
                len(
                    [
                        dog
                        for dog in self._dogs
                        if dog.get("modules", {}).get(MODULE_GPS, False)
                    ]
                )
            ),
        }

    async def async_step_entity_profiles(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure entity profiles for performance optimization.

        NEW: Allows users to select entity profiles that determine
        how many entities are created per dog.
        """
        if user_input is not None:
            try:
                current_profile = validate_profile_selection(user_input)
                preview_estimate = user_input.get("preview_estimate", False)

                if preview_estimate:
                    # Show entity count preview
                    return await self.async_step_profile_preview(
                        {"profile": current_profile}
                    )

                # Save the profile selection
                new_options = {**self._config_entry.options}
                new_options["entity_profile"] = current_profile

                self._invalidate_profile_caches()

                return self.async_create_entry(title="", data=new_options)

            except vol.Invalid as err:
                _LOGGER.warning("Invalid profile selection in options flow: %s", err)
                return self.async_show_form(
                    step_id="entity_profiles",
                    data_schema=self._get_entity_profiles_schema(user_input),
                    errors={"base": "invalid_profile"},
                )
            except Exception as err:
                _LOGGER.error("Error updating entity profile: %s", err)
                return self.async_show_form(
                    step_id="entity_profiles",
                    data_schema=self._get_entity_profiles_schema(user_input),
                    errors={"base": "profile_update_failed"},
                )

        return self.async_show_form(
            step_id="entity_profiles",
            data_schema=self._get_entity_profiles_schema(),
            description_placeholders=self._get_profile_description_placeholders(),
        )

    def _get_entity_profiles_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get entity profiles schema with current values."""
        current_options = self._config_entry.options
        current_values = user_input or {}
        current_profile = current_values.get(
            "entity_profile",
            current_options.get("entity_profile", DEFAULT_PROFILE),
        )

        if current_profile not in ENTITY_PROFILES:
            current_profile = DEFAULT_PROFILE

        profile_options = get_profile_selector_options()

        return vol.Schema(
            {
                vol.Required(
                    "entity_profile", default=current_profile
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=profile_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "preview_estimate", default=False
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
            }
        )

    def _get_profile_description_placeholders_cached(self) -> dict[str, str]:
        """Get description placeholders with caching for better performance."""

        current_dogs = self._config_entry.data.get(CONF_DOGS, [])
        current_profile = self._config_entry.options.get(
            "entity_profile", DEFAULT_PROFILE
        )
        cache_key = (
            f"{current_profile}_{len(current_dogs)}_"
            f"{hash(json.dumps(current_dogs, sort_keys=True))}"
        )

        cached = self._profile_cache.get(cache_key)
        if cached is not None:
            return cached

        total_estimate = 0
        profile_compatibility_issues: list[str] = []

        profile_info = ENTITY_PROFILES.get(
            current_profile, ENTITY_PROFILES[DEFAULT_PROFILE]
        )
        max_entities = profile_info["max_entities"]

        for dog in current_dogs:
            modules = dog.get("modules", {})
            estimate = self._entity_factory.estimate_entity_count(
                current_profile, modules
            )
            total_estimate += estimate

            if not self._entity_factory.validate_profile_for_modules(
                current_profile, modules
            ):
                dog_name = dog.get(CONF_DOG_NAME, "Unknown")
                profile_compatibility_issues.append(
                    f"{dog_name} modules may not be optimal for {current_profile}"
                )

        total_capacity = max_entities * len(current_dogs)
        utilization = (
            f"{(total_estimate / total_capacity * 100):.1f}"
            if total_capacity > 0
            else "0"
        )

        placeholders = {
            "current_profile": current_profile,
            "current_description": profile_info["description"],
            "dogs_count": str(len(current_dogs)),
            "estimated_entities": str(total_estimate),
            "max_entities_per_dog": str(max_entities),
            "performance_impact": self._get_performance_impact_description(
                current_profile
            ),
            "compatibility_warnings": "; ".join(profile_compatibility_issues)
            if profile_compatibility_issues
            else "No compatibility issues",
            "utilization_percentage": utilization,
        }

        self._profile_cache[cache_key] = placeholders
        return placeholders

    def _get_profile_description_placeholders(self) -> dict[str, str]:
        """Get description placeholders for profile selection."""

        return self._get_profile_description_placeholders_cached()

    def _get_performance_impact_description(self, profile: str) -> str:
        """Get performance impact description for profile."""
        impact_descriptions = {
            "basic": "Minimal resource usage, fastest startup",
            "standard": "Balanced performance and features",
            "advanced": "Full features, higher resource usage",
            "gps_focus": "Optimized for GPS tracking",
            "health_focus": "Optimized for health monitoring",
        }
        return impact_descriptions.get(profile, "Balanced performance")

    async def _calculate_profile_preview_optimized(
        self, profile: str
    ) -> dict[str, Any]:
        """Calculate profile preview with optimized performance."""

        current_dogs = self._config_entry.data.get(CONF_DOGS, [])
        cache_key = (
            f"{profile}_{len(current_dogs)}_"
            f"{hash(json.dumps(current_dogs, sort_keys=True))}"
        )

        cached_preview = self._entity_estimates_cache.get(cache_key)
        if cached_preview is not None:
            return cached_preview

        entity_breakdown: list[dict[str, Any]] = []
        total_entities = 0
        performance_score = 100.0

        profile_info = ENTITY_PROFILES.get(profile, ENTITY_PROFILES["standard"])
        max_entities = profile_info["max_entities"]

        for dog in current_dogs:
            dog_name = dog.get(CONF_DOG_NAME, "Unknown")
            dog_id = dog.get(CONF_DOG_ID, "unknown")
            modules = dog.get("modules", {})

            estimate = self._entity_factory.estimate_entity_count(profile, modules)
            total_entities += estimate

            enabled_modules = [module for module, enabled in modules.items() if enabled]
            utilization = (estimate / max_entities) * 100 if max_entities > 0 else 0

            entity_breakdown.append(
                {
                    "dog_name": dog_name,
                    "dog_id": dog_id,
                    "entities": estimate,
                    "modules": enabled_modules,
                    "utilization": utilization,
                }
            )

            if utilization > 80:
                performance_score -= 10
            elif utilization > 60:
                performance_score -= 5

        current_profile = self._config_entry.options.get("entity_profile", "standard")
        if profile == current_profile:
            current_total = total_entities
        else:
            current_total = 0
            for dog in current_dogs:
                modules = dog.get("modules", {})
                current_total += self._entity_factory.estimate_entity_count(
                    current_profile, modules
                )

        entity_difference = total_entities - current_total

        preview = {
            "profile": profile,
            "total_entities": total_entities,
            "entity_breakdown": entity_breakdown,
            "current_total": current_total,
            "entity_difference": entity_difference,
            "performance_score": performance_score,
            "recommendation": self._get_profile_recommendation_enhanced(
                total_entities, len(current_dogs), performance_score
            ),
            "warnings": self._get_profile_warnings(profile, current_dogs),
        }

        self._entity_estimates_cache[cache_key] = preview
        return preview

    def _get_profile_recommendation_enhanced(
        self, total_entities: int, dog_count: int, performance_score: float
    ) -> str:
        """Get enhanced profile recommendation with performance considerations."""

        if performance_score < 70:
            return "⚠️ Consider 'basic' or 'standard' profile for better performance"
        if performance_score < 85:
            return "💡 'Standard' profile recommended for balanced performance"
        if dog_count == 1 and total_entities < 15:
            return "✨ 'Advanced' profile available for full features"
        return "✅ Current profile is well-suited for your configuration"

    def _get_profile_warnings(
        self, profile: str, dogs: list[dict[str, Any]]
    ) -> list[str]:
        """Get profile-specific warnings and recommendations."""

        warnings: list[str] = []

        for dog in dogs:
            modules = dog.get("modules", {})
            dog_name = dog.get(CONF_DOG_NAME, "Unknown")

            if profile == "gps_focus" and not modules.get(MODULE_GPS, False):
                warnings.append(
                    f"🛰️ {dog_name}: GPS focus profile but GPS module disabled"
                )

            if profile == "health_focus" and not modules.get(MODULE_HEALTH, False):
                warnings.append(
                    f"🏥 {dog_name}: Health focus profile but health module disabled"
                )

            if profile == "basic" and sum(modules.values()) > 3:
                warnings.append(
                    f"⚡ {dog_name}: Many modules enabled for basic profile"
                )

        return warnings

    async def async_step_profile_preview(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show entity count preview for selected profile.

        NEW: Provides detailed breakdown of entity counts per dog
        """
        profile = user_input.get("profile", "standard") if user_input else "standard"

        if user_input is not None:
            if user_input.get("apply_profile"):
                new_options = {**self._config_entry.options}
                new_options["entity_profile"] = profile
                self._invalidate_profile_caches()
                return self.async_create_entry(title="", data=new_options)

            return await self.async_step_entity_profiles()

        preview_data = await self._calculate_profile_preview_optimized(profile)
        breakdown_lines = []

        for item in preview_data["entity_breakdown"]:
            modules_display = ", ".join(item["modules"]) or "none"
            breakdown_lines.append(
                f"• {item['dog_name']}: {item['entities']} entities "
                f"(modules: {modules_display}, utilization: {item['utilization']:.1f}%)"
            )

        performance_change = (
            "same"
            if preview_data["entity_difference"] == 0
            else (
                "better"
                if preview_data["entity_difference"] < 0
                else "higher resource usage"
            )
        )

        warnings_text = (
            "\n".join(preview_data["warnings"])
            if preview_data["warnings"]
            else "No warnings"
        )

        profile_info = ENTITY_PROFILES.get(profile, ENTITY_PROFILES["standard"])

        return self.async_show_form(
            step_id="profile_preview",
            data_schema=vol.Schema(
                {
                    vol.Required("profile", default=profile): vol.In([profile]),
                    vol.Optional(
                        "apply_profile", default=False
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={
                "profile_name": preview_data["profile"],
                "total_entities": str(preview_data["total_entities"]),
                "entity_breakdown": "\n".join(breakdown_lines),
                "current_total": str(preview_data["current_total"]),
                "entity_difference": (
                    f"{preview_data['entity_difference']:+d}"
                    if preview_data["entity_difference"]
                    else "0"
                ),
                "performance_change": performance_change,
                "profile_description": profile_info["description"],
                "performance_score": f"{preview_data['performance_score']:.1f}",
                "recommendation": preview_data["recommendation"],
                "warnings": warnings_text,
            },
        )

    async def async_step_performance_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure performance and optimization settings.

        NEW: Combines entity profiles with other performance settings
        """
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        "entity_profile": user_input.get("entity_profile", "standard"),
                        "performance_mode": user_input.get(
                            "performance_mode", "balanced"
                        ),
                        "batch_size": user_input.get("batch_size", 15),
                        "cache_ttl": user_input.get("cache_ttl", 300),
                        "selective_refresh": user_input.get("selective_refresh", True),
                    }
                )

                return self.async_create_entry(title="", data=new_options)

            except Exception as err:
                _LOGGER.error("Error updating performance settings: %s", err)
                return self.async_show_form(
                    step_id="performance_settings",
                    data_schema=self._get_performance_settings_schema(user_input),
                    errors={"base": "performance_update_failed"},
                )

        return self.async_show_form(
            step_id="performance_settings",
            data_schema=self._get_performance_settings_schema(),
        )

    def _get_performance_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get performance settings schema."""
        current_options = self._config_entry.options
        current_values = user_input or {}

        # Profile options
        profile_options = []
        for profile_name, profile_config in ENTITY_PROFILES.items():
            max_entities = profile_config["max_entities"]
            description = profile_config["description"]
            profile_options.append(
                {
                    "value": profile_name,
                    "label": f"{profile_name.title()} ({max_entities}/dog) - {description}",
                }
            )

        return vol.Schema(
            {
                vol.Required(
                    "entity_profile",
                    default=current_values.get(
                        "entity_profile",
                        current_options.get("entity_profile", "standard"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=profile_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        current_options.get("performance_mode", "balanced"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "minimal",
                                "label": "Minimal - Lowest resource usage",
                            },
                            {
                                "value": "balanced",
                                "label": "Balanced - Good performance",
                            },
                            {"value": "full", "label": "Full - Maximum responsiveness"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "batch_size",
                    default=current_values.get(
                        "batch_size", current_options.get("batch_size", 15)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=50,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "cache_ttl",
                    default=current_values.get(
                        "cache_ttl", current_options.get("cache_ttl", 300)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=60,
                        max=3600,
                        step=60,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
                vol.Optional(
                    "selective_refresh",
                    default=current_values.get(
                        "selective_refresh",
                        current_options.get("selective_refresh", True),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_manage_dogs(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage dogs - add, edit, or remove dogs."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_dog":
                return await self.async_step_add_new_dog()
            elif action == "edit_dog":
                return await self.async_step_select_dog_to_edit()
            elif action == "remove_dog":
                return await self.async_step_select_dog_to_remove()
            elif action == "configure_modules":  # NEW: Module configuration
                return await self.async_step_select_dog_for_modules()
            else:
                return await self.async_step_init()

        # Show dog management menu
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        return self.async_show_form(
            step_id="manage_dogs",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="add_dog"): vol.In(
                        {
                            "add_dog": "Add new dog",
                            "edit_dog": "Edit existing dog"
                            if current_dogs
                            else "No dogs to edit",
                            "configure_modules": "Configure dog modules"  # NEW
                            if current_dogs
                            else "No dogs to configure",
                            "remove_dog": "Remove dog"
                            if current_dogs
                            else "No dogs to remove",
                            "back": "Back to main menu",
                        }
                    )
                }
            ),
            description_placeholders={
                "current_dogs_count": str(len(current_dogs)),
                "dogs_list": "\n".join(
                    [
                        f"• {dog.get(CONF_DOG_NAME, 'Unknown')} ({dog.get(CONF_DOG_ID, 'unknown')})"
                        for dog in current_dogs
                    ]
                )
                if current_dogs
                else "No dogs configured",
            },
        )

    async def async_step_select_dog_for_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which dog to configure modules for.

        NEW: Allows per-dog module configuration
        """
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        if not current_dogs:
            return await self.async_step_manage_dogs()

        if user_input is not None:
            selected_dog_id = user_input.get("dog_id")
            self._current_dog = next(
                (
                    dog
                    for dog in current_dogs
                    if dog.get(CONF_DOG_ID) == selected_dog_id
                ),
                None,
            )
            if self._current_dog:
                return await self.async_step_configure_dog_modules()
            else:
                return await self.async_step_manage_dogs()

        # Create selection options
        dog_options = [
            {
                "value": dog.get(CONF_DOG_ID),
                "label": f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})",
            }
            for dog in current_dogs
        ]

        return self.async_show_form(
            step_id="select_dog_for_modules",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=dog_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_configure_dog_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure modules for the selected dog.

        NEW: Per-dog module configuration with entity count preview
        """
        if not self._current_dog:
            return await self.async_step_manage_dogs()

        if user_input is not None:
            try:
                # Update the dog's modules in the config entry
                current_dogs = list(self._config_entry.data.get(CONF_DOGS, []))
                dog_index = next(
                    (
                        i
                        for i, dog in enumerate(current_dogs)
                        if dog.get(CONF_DOG_ID) == self._current_dog.get(CONF_DOG_ID)
                    ),
                    -1,
                )

                if dog_index >= 0:
                    # Update modules
                    updated_modules = {
                        MODULE_FEEDING: user_input.get("module_feeding", True),
                        MODULE_WALK: user_input.get("module_walk", True),
                        MODULE_GPS: user_input.get("module_gps", False),
                        MODULE_HEALTH: user_input.get("module_health", True),
                        "notifications": user_input.get("module_notifications", True),
                        "dashboard": user_input.get("module_dashboard", True),
                        "visitor": user_input.get("module_visitor", False),
                        "grooming": user_input.get("module_grooming", False),
                        "medication": user_input.get("module_medication", False),
                        "training": user_input.get("module_training", False),
                    }

                    current_dogs[dog_index]["modules"] = updated_modules

                    # Update config entry
                    new_data = {**self._config_entry.data}
                    new_data[CONF_DOGS] = current_dogs

                    self.hass.config_entries.async_update_entry(
                        self._config_entry, data=new_data
                    )

                return await self.async_step_manage_dogs()

            except Exception as err:
                _LOGGER.error("Error configuring dog modules: %s", err)
                return self.async_show_form(
                    step_id="configure_dog_modules",
                    data_schema=self._get_dog_modules_schema(),
                    errors={"base": "module_config_failed"},
                )

        return self.async_show_form(
            step_id="configure_dog_modules",
            data_schema=self._get_dog_modules_schema(),
            description_placeholders=self._get_module_description_placeholders(),
        )

    def _get_dog_modules_schema(self) -> vol.Schema:
        """Get modules configuration schema for current dog."""
        if not self._current_dog:
            return vol.Schema({})

        current_modules = self._current_dog.get("modules", {})

        return vol.Schema(
            {
                vol.Optional(
                    "module_feeding",
                    default=current_modules.get(MODULE_FEEDING, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_walk",
                    default=current_modules.get(MODULE_WALK, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_gps",
                    default=current_modules.get(MODULE_GPS, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_health",
                    default=current_modules.get(MODULE_HEALTH, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_notifications",
                    default=current_modules.get("notifications", True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_dashboard",
                    default=current_modules.get("dashboard", True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_visitor",
                    default=current_modules.get("visitor", False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_grooming",
                    default=current_modules.get("grooming", False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_medication",
                    default=current_modules.get("medication", False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_training",
                    default=current_modules.get("training", False),
                ): selector.BooleanSelector(),
            }
        )

    def _get_module_description_placeholders(self) -> dict[str, str]:
        """Get description placeholders for module configuration."""
        if not self._current_dog:
            return {}

        current_profile = self._config_entry.options.get("entity_profile", "standard")
        current_modules = self._current_dog.get("modules", {})

        # Calculate current entity count
        current_estimate = self._entity_factory.estimate_entity_count(
            current_profile, current_modules
        )

        # Module descriptions
        module_descriptions = {
            MODULE_FEEDING: "Food tracking, scheduling, portion control",
            MODULE_WALK: "Walk tracking, duration, distance monitoring",
            MODULE_GPS: "Location tracking, geofencing, route recording",
            MODULE_HEALTH: "Weight tracking, vet reminders, medication",
            "notifications": "Alerts, reminders, status notifications",
            "dashboard": "Custom dashboard generation",
            "visitor": "Visitor mode for reduced monitoring",
            "grooming": "Grooming schedule and tracking",
            "medication": "Medication reminders and tracking",
            "training": "Training progress and notes",
        }

        enabled_modules = [
            f"• {module}: {module_descriptions.get(module, 'Module functionality')}"
            for module, enabled in current_modules.items()
            if enabled
        ]

        return {
            "dog_name": self._current_dog.get(CONF_DOG_NAME, "Unknown"),
            "current_profile": current_profile,
            "current_entities": str(current_estimate),
            "enabled_modules": "\n".join(enabled_modules)
            if enabled_modules
            else "No modules enabled",
        }

    # Rest of the existing methods (add_new_dog, edit_dog, etc.) remain the same...

    async def async_step_add_new_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new dog to the configuration."""
        if user_input is not None:
            try:
                # Create the new dog config
                new_dog = {
                    CONF_DOG_ID: user_input[CONF_DOG_ID]
                    .lower()
                    .strip()
                    .replace(" ", "_"),
                    CONF_DOG_NAME: user_input[CONF_DOG_NAME].strip(),
                    CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, "").strip()
                    or "Mixed Breed",
                    CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 3),
                    CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
                    CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, "medium"),
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        "notifications": True,
                        "dashboard": True,
                        MODULE_GPS: False,
                        "visitor": False,
                        "grooming": False,
                        "medication": False,
                        "training": False,
                    },
                    "created_at": asyncio.get_running_loop().time(),
                }

                # Add to existing dogs
                current_dogs = list(self._config_entry.data.get(CONF_DOGS, []))
                current_dogs.append(new_dog)

                # Update the config entry data
                new_data = {**self._config_entry.data}
                new_data[CONF_DOGS] = current_dogs

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )

                return await self.async_step_init()
            except Exception as err:
                _LOGGER.error("Error adding new dog: %s", err)
                return self.async_show_form(
                    step_id="add_new_dog",
                    data_schema=self._get_add_dog_schema(),
                    errors={"base": "add_dog_failed"},
                )

        return self.async_show_form(
            step_id="add_new_dog", data_schema=self._get_add_dog_schema()
        )

    def _get_add_dog_schema(self) -> vol.Schema:
        """Get schema for adding a new dog."""
        return vol.Schema(
            {
                vol.Required(CONF_DOG_ID): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="off",
                    )
                ),
                vol.Required(CONF_DOG_NAME): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="name",
                    )
                ),
                vol.Optional(CONF_DOG_BREED, default=""): selector.TextSelector(),
                vol.Optional(CONF_DOG_AGE, default=3): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=30, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(CONF_DOG_WEIGHT, default=20.0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=200.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kg",
                    )
                ),
                vol.Optional(CONF_DOG_SIZE, default="medium"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "toy", "label": "Toy (1-6kg)"},
                            {"value": "small", "label": "Small (6-12kg)"},
                            {"value": "medium", "label": "Medium (12-27kg)"},
                            {"value": "large", "label": "Large (27-45kg)"},
                            {"value": "giant", "label": "Giant (45-90kg)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_select_dog_to_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which dog to edit."""
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        if not current_dogs:
            return await self.async_step_init()

        if user_input is not None:
            selected_dog_id = user_input.get("dog_id")
            self._current_dog = next(
                (
                    dog
                    for dog in current_dogs
                    if dog.get(CONF_DOG_ID) == selected_dog_id
                ),
                None,
            )
            if self._current_dog:
                return await self.async_step_edit_dog()
            else:
                return await self.async_step_init()

        # Create selection options
        dog_options = [
            {
                "value": dog.get(CONF_DOG_ID),
                "label": f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})",
            }
            for dog in current_dogs
        ]

        return self.async_show_form(
            step_id="select_dog_to_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=dog_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected dog."""
        if not self._current_dog:
            return await self.async_step_init()

        if user_input is not None:
            try:
                # Update the dog in the config entry
                current_dogs = list(self._config_entry.data.get(CONF_DOGS, []))
                dog_index = next(
                    (
                        i
                        for i, dog in enumerate(current_dogs)
                        if dog.get(CONF_DOG_ID) == self._current_dog.get(CONF_DOG_ID)
                    ),
                    -1,
                )

                if dog_index >= 0:
                    # Update the dog with new values
                    updated_dog = {**current_dogs[dog_index]}
                    updated_dog.update(user_input)
                    current_dogs[dog_index] = updated_dog

                    # Update config entry
                    new_data = {**self._config_entry.data}
                    new_data[CONF_DOGS] = current_dogs

                    self.hass.config_entries.async_update_entry(
                        self._config_entry, data=new_data
                    )

                return await self.async_step_init()
            except Exception as err:
                _LOGGER.error("Error editing dog: %s", err)
                return self.async_show_form(
                    step_id="edit_dog",
                    data_schema=self._get_edit_dog_schema(),
                    errors={"base": "edit_dog_failed"},
                )

        return self.async_show_form(
            step_id="edit_dog", data_schema=self._get_edit_dog_schema()
        )

    def _get_edit_dog_schema(self) -> vol.Schema:
        """Get schema for editing a dog with current values pre-filled."""
        if not self._current_dog:
            return vol.Schema({})

        return vol.Schema(
            {
                vol.Optional(
                    CONF_DOG_NAME, default=self._current_dog.get(CONF_DOG_NAME, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DOG_BREED, default=self._current_dog.get(CONF_DOG_BREED, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DOG_AGE, default=self._current_dog.get(CONF_DOG_AGE, 3)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=30, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_DOG_WEIGHT,
                    default=self._current_dog.get(CONF_DOG_WEIGHT, 20.0),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=200.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kg",
                    )
                ),
                vol.Optional(
                    CONF_DOG_SIZE,
                    default=self._current_dog.get(CONF_DOG_SIZE, "medium"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "toy", "label": "Toy (1-6kg)"},
                            {"value": "small", "label": "Small (6-12kg)"},
                            {"value": "medium", "label": "Medium (12-27kg)"},
                            {"value": "large", "label": "Large (27-45kg)"},
                            {"value": "giant", "label": "Giant (45-90kg)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_select_dog_to_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which dog to remove."""
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        if not current_dogs:
            return await self.async_step_init()

        if user_input is not None:
            if user_input.get("confirm_remove"):
                selected_dog_id = user_input.get("dog_id")
                # Remove the selected dog
                updated_dogs = [
                    dog
                    for dog in current_dogs
                    if dog.get(CONF_DOG_ID) != selected_dog_id
                ]

                # Update config entry
                new_data = {**self._config_entry.data}
                new_data[CONF_DOGS] = updated_dogs

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )

            return await self.async_step_init()

        # Create removal confirmation form
        dog_options = [
            {
                "value": dog.get(CONF_DOG_ID),
                "label": f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})",
            }
            for dog in current_dogs
        ]

        return self.async_show_form(
            step_id="select_dog_to_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=dog_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        "confirm_remove", default=False
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={
                "warning": "This will permanently remove the selected dog and all associated data!"
            },
        )

    # GPS Settings (existing method, enhanced with route recording)
    async def async_step_gps_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure GPS and location settings with enhanced route recording options."""
        if user_input is not None:
            try:
                # Update GPS settings in options
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_GPS_UPDATE_INTERVAL: user_input.get(
                            "gps_update_interval", DEFAULT_GPS_UPDATE_INTERVAL
                        ),
                        CONF_GPS_ACCURACY_FILTER: user_input.get(
                            "gps_accuracy_filter", DEFAULT_GPS_ACCURACY_FILTER
                        ),
                        CONF_GPS_DISTANCE_FILTER: user_input.get(
                            "gps_distance_filter", DEFAULT_GPS_DISTANCE_FILTER
                        ),
                        "gps_enabled": user_input.get("gps_enabled", True),
                        "route_recording": user_input.get("route_recording", True),
                        "route_history_days": user_input.get("route_history_days", 30),
                        "auto_track_walks": user_input.get("auto_track_walks", True),
                    }
                )

                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="gps_settings",
                    data_schema=self._get_gps_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="gps_settings", data_schema=self._get_gps_settings_schema()
        )

    def _get_gps_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get GPS settings schema with current values and enhanced route options."""
        current_options = self._config_entry.options
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "gps_enabled",
                    default=current_values.get(
                        "gps_enabled", current_options.get("gps_enabled", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "gps_update_interval",
                    default=current_values.get(
                        "gps_update_interval",
                        current_options.get(
                            CONF_GPS_UPDATE_INTERVAL, DEFAULT_GPS_UPDATE_INTERVAL
                        ),
                    ),
                ): GPS_UPDATE_INTERVAL_SELECTOR,
                vol.Optional(
                    "gps_accuracy_filter",
                    default=current_values.get(
                        "gps_accuracy_filter",
                        current_options.get(
                            CONF_GPS_ACCURACY_FILTER, DEFAULT_GPS_ACCURACY_FILTER
                        ),
                    ),
                ): GPS_ACCURACY_FILTER_SELECTOR,
                vol.Optional(
                    "gps_distance_filter",
                    default=current_values.get(
                        "gps_distance_filter",
                        current_options.get(
                            CONF_GPS_DISTANCE_FILTER, DEFAULT_GPS_DISTANCE_FILTER
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=100,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="meters",
                    )
                ),
                vol.Optional(
                    "route_recording",
                    default=current_values.get(
                        "route_recording",
                        current_options.get("route_recording", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "route_history_days",
                    default=current_values.get(
                        "route_history_days",
                        current_options.get("route_history_days", 30),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "auto_track_walks",
                    default=current_values.get(
                        "auto_track_walks",
                        current_options.get("auto_track_walks", True),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    # All other existing methods remain unchanged...
    # (notifications, feeding_settings, health_settings, system_settings, dashboard_settings, advanced_settings, import_export)

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure notification settings."""
        if user_input is not None:
            try:
                # Update notification settings
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_NOTIFICATIONS: {
                            CONF_QUIET_HOURS: user_input.get("quiet_hours", True),
                            CONF_QUIET_START: user_input.get("quiet_start", "22:00:00"),
                            CONF_QUIET_END: user_input.get("quiet_end", "07:00:00"),
                            CONF_REMINDER_REPEAT_MIN: user_input.get(
                                "reminder_repeat_min", DEFAULT_REMINDER_REPEAT_MIN
                            ),
                            "priority_notifications": user_input.get(
                                "priority_notifications", True
                            ),
                            "mobile_notifications": user_input.get(
                                "mobile_notifications", True
                            ),
                        }
                    }
                )

                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="notifications",
                    data_schema=self._get_notifications_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="notifications", data_schema=self._get_notifications_schema()
        )

    def _get_notifications_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get notifications settings schema."""
        current_options = self._config_entry.options
        current_notifications = current_options.get(CONF_NOTIFICATIONS, {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "quiet_hours",
                    default=current_values.get(
                        "quiet_hours", current_notifications.get(CONF_QUIET_HOURS, True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "quiet_start",
                    default=current_values.get(
                        "quiet_start",
                        current_notifications.get(CONF_QUIET_START, "22:00:00"),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "quiet_end",
                    default=current_values.get(
                        "quiet_end",
                        current_notifications.get(CONF_QUIET_END, "07:00:00"),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "reminder_repeat_min",
                    default=current_values.get(
                        "reminder_repeat_min",
                        current_notifications.get(
                            CONF_REMINDER_REPEAT_MIN, DEFAULT_REMINDER_REPEAT_MIN
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=180,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="minutes",
                    )
                ),
                vol.Optional(
                    "priority_notifications",
                    default=current_values.get(
                        "priority_notifications",
                        current_notifications.get("priority_notifications", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "mobile_notifications",
                    default=current_values.get(
                        "mobile_notifications",
                        current_notifications.get("mobile_notifications", True),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_feeding_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure feeding and nutrition settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        "feeding_settings": {
                            "default_meals_per_day": user_input.get("meals_per_day", 2),
                            "feeding_reminders": user_input.get(
                                "feeding_reminders", True
                            ),
                            "portion_tracking": user_input.get(
                                "portion_tracking", True
                            ),
                            "calorie_tracking": user_input.get(
                                "calorie_tracking", True
                            ),
                            "auto_schedule": user_input.get("auto_schedule", False),
                        }
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="feeding_settings",
                    data_schema=self._get_feeding_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="feeding_settings", data_schema=self._get_feeding_settings_schema()
        )

    def _get_feeding_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get feeding settings schema."""
        current_options = self._config_entry.options
        current_feeding = current_options.get("feeding_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "meals_per_day",
                    default=current_values.get(
                        "meals_per_day", current_feeding.get("default_meals_per_day", 2)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=6, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    "feeding_reminders",
                    default=current_values.get(
                        "feeding_reminders",
                        current_feeding.get("feeding_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "portion_tracking",
                    default=current_values.get(
                        "portion_tracking",
                        current_feeding.get("portion_tracking", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "calorie_tracking",
                    default=current_values.get(
                        "calorie_tracking",
                        current_feeding.get("calorie_tracking", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "auto_schedule",
                    default=current_values.get(
                        "auto_schedule", current_feeding.get("auto_schedule", False)
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_health_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure health monitoring settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        "health_settings": {
                            "weight_tracking": user_input.get("weight_tracking", True),
                            "medication_reminders": user_input.get(
                                "medication_reminders", True
                            ),
                            "vet_reminders": user_input.get("vet_reminders", True),
                            "grooming_reminders": user_input.get(
                                "grooming_reminders", True
                            ),
                            "health_alerts": user_input.get("health_alerts", True),
                        }
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="health_settings",
                    data_schema=self._get_health_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="health_settings", data_schema=self._get_health_settings_schema()
        )

    def _get_health_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get health settings schema."""
        current_options = self._config_entry.options
        current_health = current_options.get("health_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "weight_tracking",
                    default=current_values.get(
                        "weight_tracking", current_health.get("weight_tracking", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "medication_reminders",
                    default=current_values.get(
                        "medication_reminders",
                        current_health.get("medication_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "vet_reminders",
                    default=current_values.get(
                        "vet_reminders", current_health.get("vet_reminders", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "grooming_reminders",
                    default=current_values.get(
                        "grooming_reminders",
                        current_health.get("grooming_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "health_alerts",
                    default=current_values.get(
                        "health_alerts", current_health.get("health_alerts", True)
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_system_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure system and performance settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_RESET_TIME: user_input.get(
                            "reset_time", DEFAULT_RESET_TIME
                        ),
                        "system_settings": {
                            "data_retention_days": user_input.get(
                                "data_retention_days", 90
                            ),
                            "auto_backup": user_input.get("auto_backup", False),
                            "performance_mode": user_input.get(
                                "performance_mode", "balanced"
                            ),
                        },
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="system_settings",
                    data_schema=self._get_system_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="system_settings", data_schema=self._get_system_settings_schema()
        )

    def _get_system_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get system settings schema."""
        current_options = self._config_entry.options
        current_system = current_options.get("system_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "reset_time",
                    default=current_values.get(
                        "reset_time",
                        current_options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "data_retention_days",
                    default=current_values.get(
                        "data_retention_days",
                        current_system.get("data_retention_days", 90),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "auto_backup",
                    default=current_values.get(
                        "auto_backup", current_system.get("auto_backup", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        current_system.get("performance_mode", "balanced"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "minimal",
                                "label": "Minimal - Lowest resource usage",
                            },
                            {
                                "value": "balanced",
                                "label": "Balanced - Good performance and efficiency",
                            },
                            {
                                "value": "full",
                                "label": "Full - Maximum features and responsiveness",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_dashboard_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure dashboard and display settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_DASHBOARD_MODE: user_input.get("dashboard_mode", "full"),
                        "dashboard_settings": {
                            "show_statistics": user_input.get("show_statistics", True),
                            "show_alerts": user_input.get("show_alerts", True),
                            "compact_mode": user_input.get("compact_mode", False),
                            "show_maps": user_input.get("show_maps", True),
                        },
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="dashboard_settings",
                    data_schema=self._get_dashboard_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="dashboard_settings",
            data_schema=self._get_dashboard_settings_schema(),
        )

    def _get_dashboard_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get dashboard settings schema."""
        current_options = self._config_entry.options
        current_dashboard = current_options.get("dashboard_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "dashboard_mode",
                    default=current_values.get(
                        "dashboard_mode",
                        current_options.get(CONF_DASHBOARD_MODE, "full"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=DASHBOARD_MODE_SELECTOR_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "show_statistics",
                    default=current_values.get(
                        "show_statistics",
                        current_dashboard.get("show_statistics", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_alerts",
                    default=current_values.get(
                        "show_alerts",
                        current_dashboard.get("show_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "compact_mode",
                    default=current_values.get(
                        "compact_mode",
                        current_dashboard.get("compact_mode", False),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_maps",
                    default=current_values.get(
                        "show_maps",
                        current_dashboard.get("show_maps", True),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_advanced_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle advanced settings configuration."""
        if user_input is not None:
            try:
                # Update options with advanced settings
                self._unsaved_changes.update(
                    {
                        "performance_mode": user_input.get(
                            "performance_mode", "balanced"
                        ),
                        "debug_logging": user_input.get("debug_logging", False),
                        "data_retention_days": user_input.get(
                            "data_retention_days", 90
                        ),
                        "auto_backup": user_input.get("auto_backup", False),
                        "experimental_features": user_input.get(
                            "experimental_features", False
                        ),
                        CONF_EXTERNAL_INTEGRATIONS: user_input.get(
                            CONF_EXTERNAL_INTEGRATIONS, False
                        ),
                    }
                )
                # Save changes and return to main menu
                return await self._async_save_options()
            except Exception as err:
                _LOGGER.error("Error saving advanced settings: %s", err)
                return self.async_show_form(
                    step_id="advanced_settings",
                    errors={"base": "save_failed"},
                    data_schema=self._get_advanced_settings_schema(user_input),
                )

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=self._get_advanced_settings_schema(),
        )

    def _get_advanced_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get schema for advanced settings form."""
        current_options = self._config_entry.options
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        current_options.get("performance_mode", "balanced"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "minimal",
                                "label": "Minimal - Lowest resource usage",
                            },
                            {
                                "value": "balanced",
                                "label": "Balanced - Good performance and efficiency",
                            },
                            {
                                "value": "full",
                                "label": "Full - Maximum features and responsiveness",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "debug_logging",
                    default=current_values.get(
                        "debug_logging", current_options.get("debug_logging", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "data_retention_days",
                    default=current_values.get(
                        "data_retention_days",
                        current_options.get("data_retention_days", 90),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "auto_backup",
                    default=current_values.get(
                        "auto_backup", current_options.get("auto_backup", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "experimental_features",
                    default=current_values.get(
                        "experimental_features",
                        current_options.get("experimental_features", False),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_EXTERNAL_INTEGRATIONS,
                    default=current_values.get(
                        CONF_EXTERNAL_INTEGRATIONS,
                        current_options.get(CONF_EXTERNAL_INTEGRATIONS, False),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_import_export(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Placeholder handler for import/export settings.

        The import/export feature has not yet been implemented. Instead of
        raising an UnknownStep error when users navigate to this menu
        entry, we immediately redirect them back to the main options menu.

        Args:
            user_input: Not used.

        Returns:
            Flow result for the initial options step.
        """
        return await self.async_step_init()

    async def _async_save_options(self) -> ConfigFlowResult:
        """Save the current options changes.

        Returns:
            Configuration flow result indicating successful save
        """
        try:
            # Merge unsaved changes with existing options
            new_options = {**self._config_entry.options, **self._unsaved_changes}

            # Clear unsaved changes
            self._unsaved_changes.clear()

            # Update the config entry
            return self.async_create_entry(
                title="",  # Title is not used for options flow
                data=new_options,
            )
        except Exception as err:
            _LOGGER.error("Failed to save options: %s", err)
            return await self.async_step_init()
