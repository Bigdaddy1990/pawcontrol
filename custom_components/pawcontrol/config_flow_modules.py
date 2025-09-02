"""Module configuration steps for Paw Control configuration flow.

This module handles the configuration of global settings and dashboard preferences
after individual dog configuration is complete. The per-dog module selection
is now handled in config_flow_dogs.py for better granularity.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DASHBOARD_MODE,
    CONF_DOG_AGE,
    CONF_DOG_SIZE,
    CONF_DOGS,
    CONF_MODULES,
    DEFAULT_DASHBOARD_ENABLED,
    MODULE_DASHBOARD,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
)

_LOGGER = logging.getLogger(__name__)


class ModuleConfigurationMixin:
    """Mixin for global module configuration after per-dog setup.

    This mixin now handles global settings and dashboard configuration
    after individual dogs have been configured with their specific modules.
    Per-dog module selection has been moved to config_flow_dogs.py.
    """

    async def async_step_configure_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure global settings after per-dog configuration.

        This step now focuses on global integration settings since
        modules are configured per-dog in the dog setup flow.

        Args:
            user_input: Global configuration choices

        Returns:
            Configuration flow result for next step or completion
        """
        if user_input is not None:
            # Store global settings
            self._global_settings = {
                "performance_mode": user_input.get("performance_mode", "balanced"),
                "enable_analytics": user_input.get("enable_analytics", False),
                "enable_cloud_backup": user_input.get("enable_cloud_backup", False),
                "data_retention_days": user_input.get("data_retention_days", 90),
                "debug_logging": user_input.get("debug_logging", False),
            }
            
            # Check if any dog has dashboard enabled
            dashboard_enabled = any(
                dog.get(CONF_MODULES, {}).get(MODULE_DASHBOARD, True)
                for dog in self._dogs
            )
            
            if dashboard_enabled:
                return await self.async_step_configure_dashboard()
            
            # Check if we need external entity configuration
            gps_enabled = any(
                dog.get(CONF_MODULES, {}).get(MODULE_GPS, False)
                for dog in self._dogs
            )
            
            if gps_enabled:
                return await self.async_step_configure_external_entities()
            
            return await self.async_step_final_setup()

        # Only show this step if we have dogs configured
        if not self._dogs:
            return await self.async_step_final_setup()

        # Analyze configured modules across all dogs
        module_summary = self._analyze_configured_modules()
        
        # Determine performance mode suggestion based on complexity
        suggested_mode = self._suggest_performance_mode(module_summary)

        schema = vol.Schema(
            {
                vol.Optional(
                    "performance_mode", default=suggested_mode
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "minimal",
                                "label": "⚡ Minimal - Lowest resource usage",
                            },
                            {
                                "value": "balanced",
                                "label": "⚖️ Balanced - Good performance",
                            },
                            {
                                "value": "full",
                                "label": "🚀 Full - Maximum features",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "enable_analytics", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_cloud_backup", default=len(self._dogs) > 1
                ): selector.BooleanSelector(),
                vol.Optional(
                    "data_retention_days", default=90
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=365,
                        step=30,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "debug_logging", default=False
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="configure_modules",
            data_schema=schema,
            description_placeholders={
                "dog_count": len(self._dogs),
                "module_summary": module_summary["description"],
                "total_modules": module_summary["total"],
                "gps_dogs": module_summary["gps_dogs"],
                "health_dogs": module_summary["health_dogs"],
            },
        )

    async def async_step_configure_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure dashboard settings after per-dog setup.

        This step configures global dashboard settings and themes
        for all dogs that have the dashboard module enabled.

        Args:
            user_input: Dashboard configuration choices

        Returns:
            Configuration flow result for next step
        """
        if user_input is not None:
            # Determine which dogs have dashboard enabled
            dashboard_dogs = [
                dog for dog in self._dogs
                if dog.get(CONF_MODULES, {}).get(MODULE_DASHBOARD, True)
            ]
            
            # Store dashboard configuration
            self._dashboard_config = {
                "dashboard_enabled": True,
                "dashboard_auto_create": user_input.get("auto_create_dashboard", True),
                "dashboard_per_dog": user_input.get(
                    "create_per_dog_dashboards", len(dashboard_dogs) > 1
                ),
                "dashboard_theme": user_input.get("dashboard_theme", "modern"),
                "dashboard_template": user_input.get("dashboard_template", "cards"),
                "dashboard_mode": user_input.get(
                    "dashboard_mode", "full" if len(dashboard_dogs) > 1 else "cards"
                ),
                "show_statistics": user_input.get("show_statistics", True),
                "show_maps": user_input.get("show_maps", self._has_gps_dogs()),
                "show_health_charts": user_input.get("show_health_charts", True),
                "show_feeding_schedule": user_input.get("show_feeding_schedule", True),
                "show_alerts": user_input.get("show_alerts", True),
                "compact_mode": user_input.get("compact_mode", False),
                "auto_refresh": user_input.get("auto_refresh", True),
                "refresh_interval": user_input.get("refresh_interval", 60),
            }

            # Continue to external entities if GPS is enabled
            if self._has_gps_dogs():
                return await self.async_step_configure_external_entities()
            
            return await self.async_step_final_setup()

        # Count dogs with dashboard enabled
        dashboard_dogs = [
            dog for dog in self._dogs
            if dog.get(CONF_MODULES, {}).get(MODULE_DASHBOARD, True)
        ]
        
        has_multiple_dogs = len(dashboard_dogs) > 1
        has_gps = self._has_gps_dogs()
        has_health = self._has_health_dogs()
        has_feeding = self._has_feeding_dogs()

        schema = vol.Schema(
            {
                vol.Optional(
                    "auto_create_dashboard", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "create_per_dog_dashboards", default=has_multiple_dogs
                ): selector.BooleanSelector(),
                vol.Optional(
                    "dashboard_theme", default="modern"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "modern",
                                "label": "🎨 Modern - Clean and sophisticated",
                            },
                            {
                                "value": "playful",
                                "label": "🎉 Playful - Colorful and fun",
                            },
                            {
                                "value": "minimal",
                                "label": "⚡ Minimal - Simple and fast",
                            },
                            {
                                "value": "dark",
                                "label": "🌙 Dark - Night-friendly theme",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "dashboard_template", default="cards"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "cards",
                                "label": "🃏 Cards - Organized card layout",
                            },
                            {
                                "value": "panels",
                                "label": "📊 Panels - Side-by-side panels",
                            },
                            {
                                "value": "grid",
                                "label": "⚡ Grid - Compact grid view",
                            },
                            {
                                "value": "timeline",
                                "label": "📅 Timeline - Activity timeline",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "dashboard_mode", default="full" if has_multiple_dogs else "cards"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "full",
                                "label": "📊 Full - Complete dashboard with all features",
                            },
                            {
                                "value": "cards",
                                "label": "🃏 Cards - Organized card-based layout",
                            },
                            {
                                "value": "minimal",
                                "label": "⚡ Minimal - Essential information only",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "show_statistics", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_maps", default=has_gps
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_health_charts", default=has_health
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_feeding_schedule", default=has_feeding
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_alerts", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "compact_mode", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "auto_refresh", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "refresh_interval", default=60
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=300,
                        step=30,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="configure_dashboard",
            data_schema=schema,
            description_placeholders={
                "dog_count": len(dashboard_dogs),
                "dashboard_info": self._get_dashboard_setup_info(),
                "features": self._get_dashboard_features_string(has_gps),
            },
        )

    def _analyze_configured_modules(self) -> dict[str, Any]:
        """Analyze which modules are configured across all dogs.

        Returns:
            Summary of configured modules
        """
        module_counts = {}
        total_modules = 0
        
        for dog in self._dogs:
            modules = dog.get(CONF_MODULES, {})
            for module_name, enabled in modules.items():
                if enabled:
                    module_counts[module_name] = module_counts.get(module_name, 0) + 1
                    total_modules += 1
        
        gps_dogs = module_counts.get(MODULE_GPS, 0)
        health_dogs = module_counts.get(MODULE_HEALTH, 0)
        feeding_dogs = module_counts.get("feeding", 0)
        
        description_parts = []
        if gps_dogs > 0:
            description_parts.append(f"{gps_dogs} dogs with GPS")
        if health_dogs > 0:
            description_parts.append(f"{health_dogs} dogs with health monitoring")
        if feeding_dogs > 0:
            description_parts.append(f"{feeding_dogs} dogs with feeding tracking")
        
        return {
            "total": total_modules,
            "gps_dogs": gps_dogs,
            "health_dogs": health_dogs,
            "feeding_dogs": feeding_dogs,
            "counts": module_counts,
            "description": ", ".join(description_parts) if description_parts else "Basic monitoring",
        }

    def _suggest_performance_mode(self, module_summary: dict[str, Any]) -> str:
        """Suggest performance mode based on module complexity.

        Args:
            module_summary: Summary of configured modules

        Returns:
            Suggested performance mode
        """
        total_dogs = len(self._dogs)
        gps_dogs = module_summary["gps_dogs"]
        total_modules = module_summary["total"]
        
        # High complexity: many dogs with GPS or many modules
        if gps_dogs >= 3 or total_modules >= 15:
            return "full"
        # Medium complexity
        elif gps_dogs > 0 or total_dogs > 2 or total_modules >= 8:
            return "balanced"
        # Low complexity
        else:
            return "minimal"

    def _has_gps_dogs(self) -> bool:
        """Check if any dog has GPS enabled."""
        return any(
            dog.get(CONF_MODULES, {}).get(MODULE_GPS, False)
            for dog in self._dogs
        )

    def _has_health_dogs(self) -> bool:
        """Check if any dog has health monitoring enabled."""
        return any(
            dog.get(CONF_MODULES, {}).get(MODULE_HEALTH, False)
            for dog in self._dogs
        )

    def _has_feeding_dogs(self) -> bool:
        """Check if any dog has feeding tracking enabled."""
        return any(
            dog.get(CONF_MODULES, {}).get("feeding", False)
            for dog in self._dogs
        )

    def _get_dashboard_setup_info(self) -> str:
        """Get dashboard setup information string.

        Returns:
            Dashboard setup information
        """
        module_summary = self._analyze_configured_modules()
        
        if module_summary["total"] == 0:
            return "Basic dashboard with core monitoring features"
        
        features = []
        if module_summary["gps_dogs"] > 0:
            features.append("live location tracking")
        if module_summary["health_dogs"] > 0:
            features.append("health charts")
        if module_summary["feeding_dogs"] > 0:
            features.append("feeding schedules")
        
        if features:
            return f"Dashboard will include: {', '.join(features)}"
        
        return "Standard dashboard with monitoring features"

    def _get_dashboard_features_string(self, has_gps: bool) -> str:
        """Get dashboard features string.

        Args:
            has_gps: Whether GPS is enabled

        Returns:
            Features description
        """
        features = ["status cards", "activity tracking", "quick actions"]
        
        if has_gps:
            features.append("location maps")
        
        if len(self._dogs) > 1:
            features.append("multi-dog overview")
        
        return ", ".join(features)

    def _get_dogs_module_summary(self) -> str:
        """Get summary of dogs and their modules.

        Returns:
            Formatted summary string
        """
        if not self._dogs:
            return "No dogs configured yet"
        
        summary_parts = []
        for dog in self._dogs[:3]:  # Show first 3 dogs
            dog_name = dog.get("dog_name", "Unknown")
            modules = dog.get(CONF_MODULES, {})
            enabled_count = sum(1 for enabled in modules.values() if enabled)
            summary_parts.append(f"{dog_name}: {enabled_count} modules")
        
        if len(self._dogs) > 3:
            summary_parts.append(f"...and {len(self._dogs) - 3} more")
        
        return " | ".join(summary_parts)
