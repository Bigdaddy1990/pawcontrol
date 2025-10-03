"""Module configuration steps for Paw Control configuration flow.

This module handles the configuration of global settings and dashboard
preferences after individual dog configuration is complete. The per-dog module
selection is now handled in ``config_flow_dogs.py`` for better granularity.

The original implementation relied heavily on dynamically created attributes
defined in :class:`~custom_components.pawcontrol.config_flow_base.PawControlBaseConfigFlow`.
While that works at runtime, static type checkers (notably mypy with
``disallow_untyped_defs`` enabled) cannot see those attributes. The result was
dozens of ``attr-defined`` errors that blocked the "strict typing" milestone in
``quality_scale.yaml``. This file now declares the required attributes in a
``TYPE_CHECKING`` block and introduces structured return types to help mypy
understand the control flow. The runtime behaviour is unchanged, but type
analysis is now sound and deterministic.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_MODULES,
    FEEDING_SCHEDULE_TYPES,
    FOOD_TYPES,
    MODULE_DASHBOARD,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    SPECIAL_DIET_OPTIONS,
)
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)


if TYPE_CHECKING:

    class ModuleFlowHost(Protocol):
        """Type-checking protocol describing the module flow host."""

        _dogs: list[DogConfigData]
        _global_settings: dict[str, Any]
        _dashboard_config: dict[str, Any]
        _feeding_config: dict[str, Any]

        async def async_step_configure_external_entities(
            self, user_input: dict[str, Any] | None = None
        ) -> ConfigFlowResult:
            """Type-checking stub for the external entity step."""
            ...

        async def async_step_configure_feeding_details(
            self, user_input: dict[str, Any] | None = None
        ) -> ConfigFlowResult:
            """Type-checking stub for the feeding configuration step."""
            ...

        async def async_step_configure_dashboard(
            self, user_input: dict[str, Any] | None = None
        ) -> ConfigFlowResult:
            """Type-checking stub for the dashboard configuration step."""
            ...

        async def async_step_final_setup(
            self, user_input: dict[str, Any] | None = None
        ) -> ConfigFlowResult:
            """Type-checking stub for the final setup step."""
            ...

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: vol.Schema,
            description_placeholders: dict[str, Any] | None = None,
            errors: dict[str, str] | None = None,
        ) -> ConfigFlowResult:
            """Type-checking stub for form rendering within the flow."""
            ...


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
        flow = cast("ModuleFlowHost", self)

        if user_input is not None:
            # Store global settings
            flow._global_settings = {
                "performance_mode": user_input.get("performance_mode", "balanced"),
                "enable_analytics": user_input.get("enable_analytics", False),
                "enable_cloud_backup": user_input.get("enable_cloud_backup", False),
                "data_retention_days": user_input.get("data_retention_days", 90),
                "debug_logging": user_input.get("debug_logging", False),
            }

            # Check if any dog has dashboard enabled
            dashboard_enabled = any(
                cast(dict[str, Any], dog.get(CONF_MODULES, {})).get(
                    MODULE_DASHBOARD, True
                )
                for dog in flow._dogs
            )

            if dashboard_enabled:
                return await flow.async_step_configure_dashboard()

            # Check if feeding details need configuration
            feeding_enabled = any(
                cast(dict[str, Any], dog.get(CONF_MODULES, {})).get(
                    MODULE_FEEDING, False
                )
                for dog in flow._dogs
            )

            if feeding_enabled:
                return await flow.async_step_configure_feeding_details()

            # Check if we need external entity configuration
            gps_enabled = any(
                cast(dict[str, Any], dog.get(CONF_MODULES, {})).get(MODULE_GPS, False)
                for dog in flow._dogs
            )

            if gps_enabled:
                return await flow.async_step_configure_external_entities()

            return await flow.async_step_final_setup()

        # Only show this step if we have dogs configured
        if not flow._dogs:
            return await flow.async_step_final_setup()

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
                    "enable_cloud_backup", default=len(flow._dogs) > 1
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

        return flow.async_show_form(
            step_id="configure_modules",
            data_schema=schema,
            description_placeholders={
                "dog_count": len(flow._dogs),
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
        flow = cast("ModuleFlowHost", self)

        if user_input is not None:
            # Determine which dogs have dashboard enabled
            dashboard_dogs = [
                dog
                for dog in flow._dogs
                if cast(dict[str, Any], dog.get(CONF_MODULES, {})).get(
                    MODULE_DASHBOARD, True
                )
            ]

            # Store dashboard configuration
            flow._dashboard_config = {
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
                return await flow.async_step_configure_external_entities()

            return await flow.async_step_final_setup()

        # Count dogs with dashboard enabled
        dashboard_dogs = [
            dog
            for dog in flow._dogs
            if cast(dict[str, Any], dog.get(CONF_MODULES, {})).get(
                MODULE_DASHBOARD, True
            )
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
                vol.Optional("show_maps", default=has_gps): selector.BooleanSelector(),
                vol.Optional(
                    "show_health_charts", default=has_health
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_feeding_schedule", default=has_feeding
                ): selector.BooleanSelector(),
                vol.Optional("show_alerts", default=True): selector.BooleanSelector(),
                vol.Optional("compact_mode", default=False): selector.BooleanSelector(),
                vol.Optional("auto_refresh", default=True): selector.BooleanSelector(),
                vol.Optional("refresh_interval", default=60): selector.NumberSelector(
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

        return flow.async_show_form(
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
        flow = cast("ModuleFlowHost", self)

        module_counts: dict[str, int] = {}
        total_modules = 0

        for dog in flow._dogs:
            modules = cast(dict[str, Any], dog.get(CONF_MODULES, {}))
            for module_name, enabled in modules.items():
                if enabled:
                    module_counts[module_name] = module_counts.get(module_name, 0) + 1
                    total_modules += 1

        gps_dogs = module_counts.get(MODULE_GPS, 0)
        health_dogs = module_counts.get(MODULE_HEALTH, 0)
        feeding_dogs = module_counts.get(MODULE_FEEDING, 0)

        description_parts: list[str] = []
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
            "description": ", ".join(description_parts)
            if description_parts
            else "Basic monitoring",
        }

    def _suggest_performance_mode(self, module_summary: dict[str, Any]) -> str:
        """Suggest performance mode based on module complexity.

        Args:
            module_summary: Summary of configured modules

        Returns:
            Suggested performance mode
        """
        flow = cast("ModuleFlowHost", self)

        total_dogs = len(flow._dogs)
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
        flow = cast("ModuleFlowHost", self)

        return any(
            cast(dict[str, Any], dog.get(CONF_MODULES, {})).get(MODULE_GPS, False)
            for dog in flow._dogs
        )

    def _has_health_dogs(self) -> bool:
        """Check if any dog has health monitoring enabled."""
        flow = cast("ModuleFlowHost", self)

        return any(
            cast(dict[str, Any], dog.get(CONF_MODULES, {})).get(MODULE_HEALTH, False)
            for dog in flow._dogs
        )

    def _has_feeding_dogs(self) -> bool:
        """Check if any dog has feeding tracking enabled."""
        flow = cast("ModuleFlowHost", self)

        return any(
            cast(dict[str, Any], dog.get(CONF_MODULES, {})).get(MODULE_FEEDING, False)
            for dog in flow._dogs
        )

    def _get_dashboard_setup_info(self) -> str:
        """Get dashboard setup information string.

        Returns:
            Dashboard setup information
        """
        module_summary = self._analyze_configured_modules()

        if module_summary["total"] == 0:
            return "Basic dashboard with core monitoring features"

        features: list[str] = []
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
        flow = cast("ModuleFlowHost", self)

        features: list[str] = ["status cards", "activity tracking", "quick actions"]

        if has_gps:
            features.append("location maps")

        if len(flow._dogs) > 1:
            features.append("multi-dog overview")

        return ", ".join(features)

    async def async_step_configure_feeding_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure detailed feeding settings when feeding module is enabled.

        Args:
            user_input: Feeding configuration choices

        Returns:
            Configuration flow result for next step
        """
        flow = cast("ModuleFlowHost", self)

        if user_input is not None:
            # Store feeding configuration
            flow._feeding_config = {
                "default_daily_food_amount": user_input.get("daily_food_amount", 500.0),
                "default_meals_per_day": user_input.get("meals_per_day", 2),
                "default_food_type": user_input.get("food_type", "dry_food"),
                "default_special_diet": user_input.get("special_diet", []),
                "default_feeding_schedule_type": user_input.get(
                    "feeding_schedule_type", "flexible"
                ),
                "auto_portion_calculation": user_input.get("portion_calculation", True),
                "medication_with_meals": user_input.get("medication_with_meals", False),
                "feeding_reminders": user_input.get("feeding_reminders", True),
                "portion_tolerance": user_input.get(
                    "portion_tolerance", 10
                ),  # percentage
            }

            # Continue to GPS configuration if needed
            if self._has_gps_dogs():
                return await flow.async_step_configure_external_entities()

            return await flow.async_step_final_setup()

        # Get feeding dogs for context
        feeding_dogs: list[DogConfigData] = [
            dog
            for dog in flow._dogs
            if cast(dict[str, Any], dog.get(CONF_MODULES, {})).get(
                MODULE_FEEDING, False
            )
        ]

        schema = vol.Schema(
            {
                vol.Optional(
                    "daily_food_amount", default=500.0
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=50.0,
                        max=2000.0,
                        step=10.0,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="g",
                    )
                ),
                vol.Optional("meals_per_day", default=2): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=6,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional("food_type", default="dry_food"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": ft, "label": ft.replace("_", " ").title()}
                            for ft in FOOD_TYPES
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("special_diet", default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": sd, "label": sd.replace("_", " ").title()}
                            for sd in SPECIAL_DIET_OPTIONS
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    "feeding_schedule_type", default="flexible"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": fst, "label": fst.title()}
                            for fst in FEEDING_SCHEDULE_TYPES
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "portion_calculation", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "medication_with_meals", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "feeding_reminders", default=True
                ): selector.BooleanSelector(),
                vol.Optional("portion_tolerance", default=10): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=25,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="%",
                    )
                ),
            }
        )

        return flow.async_show_form(
            step_id="configure_feeding_details",
            data_schema=schema,
            description_placeholders={
                "dog_count": len(feeding_dogs),
                "feeding_summary": self._get_feeding_summary(feeding_dogs),
            },
        )

    def _get_feeding_summary(self, feeding_dogs: list[DogConfigData]) -> str:
        """Get summary of dogs with feeding enabled.

        Args:
            feeding_dogs: List of dogs with feeding module enabled

        Returns:
            Feeding summary string
        """
        if not feeding_dogs:
            return "No dogs with feeding tracking"

        if len(feeding_dogs) == 1:
            dog_name = feeding_dogs[0].get("dog_name", "Unknown")
            return f"Feeding configuration for {dog_name}"

        dog_names = [dog.get("dog_name", "Unknown") for dog in feeding_dogs[:3]]
        if len(feeding_dogs) > 3:
            dog_names.append(f"...and {len(feeding_dogs) - 3} more")

        return f"Feeding configuration for: {', '.join(dog_names)}"

    def _get_dogs_module_summary(self) -> str:
        """Get summary of dogs and their modules.

        Returns:
            Formatted summary string
        """
        flow = cast("ModuleFlowHost", self)

        if not flow._dogs:
            return "No dogs configured yet"

        summary_parts: list[str] = []
        for dog in flow._dogs[:3]:  # Show first 3 dogs
            dog_name = dog.get("dog_name", "Unknown")
            modules = cast(dict[str, Any], dog.get(CONF_MODULES, {}))
            enabled_count = sum(1 for enabled in modules.values() if bool(enabled))
            summary_parts.append(f"{dog_name}: {enabled_count} modules")

        if len(flow._dogs) > 3:
            summary_parts.append(f"...and {len(flow._dogs) - 3} more")

        return " | ".join(summary_parts)
