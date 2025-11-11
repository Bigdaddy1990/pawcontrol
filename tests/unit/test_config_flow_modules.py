"""Tests for config flow module typed helpers."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from typing import Any, cast

import pytest
from custom_components.pawcontrol.config_flow_modules import (
    ModuleConfigurationMixin,
    _build_dashboard_placeholders,
    _build_feeding_placeholders,
    _build_module_placeholders,
    _coerce_dashboard_configuration,
    _coerce_feeding_configuration,
    _coerce_module_global_settings,
)
from custom_components.pawcontrol.const import (
    MODULE_DASHBOARD,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
)
from custom_components.pawcontrol.types import (
    MODULE_TOGGLE_KEYS,
    ConfigFlowGlobalSettings,
    DashboardConfigurationStepInput,
    DashboardSetupConfig,
    DogConfigData,
    DogModulesConfig,
    DogModuleSelectionInput,
    ExternalEntityConfig,
    FeedingConfigurationStepInput,
    FeedingSetupConfig,
    ModuleConfigurationStepInput,
    ModuleConfigurationSummary,
    dog_modules_from_flow_input,
)


def test_coerce_module_global_settings_defaults() -> None:
    """Default module settings payload normalises to balanced analytics off."""

    payload = _coerce_module_global_settings(ModuleConfigurationStepInput())

    assert payload == {
        "performance_mode": "balanced",
        "enable_analytics": False,
        "enable_cloud_backup": False,
        "data_retention_days": 90,
        "debug_logging": False,
    }


def test_coerce_module_global_settings_normalises_alias() -> None:
    """Performance mode aliases are normalised via the shared helper."""

    payload = _coerce_module_global_settings(
        ModuleConfigurationStepInput(performance_mode="Full ")
    )

    assert payload["performance_mode"] == "full"


def test_coerce_dashboard_configuration_defaults() -> None:
    """Dashboard defaults honour context flags for maps and layout."""

    payload = _coerce_dashboard_configuration(
        DashboardConfigurationStepInput(),
        has_gps=True,
        has_health=False,
        has_feeding=True,
        per_dog_default=True,
        mode_default="cards",
    )

    assert payload["dashboard_enabled"] is True
    assert payload["dashboard_per_dog"] is True
    assert payload["show_maps"] is True
    assert payload["dashboard_mode"] == "cards"
    assert payload["show_health_charts"] is False


def test_coerce_dashboard_configuration_overrides() -> None:
    """Explicit dashboard form values are preserved."""

    payload = _coerce_dashboard_configuration(
        DashboardConfigurationStepInput(
            dashboard_theme="minimal",
            dashboard_template="panels",
            dashboard_mode="full",
            show_maps=False,
            show_statistics=False,
            auto_refresh=False,
            refresh_interval=180,
        ),
        has_gps=False,
        has_health=True,
        has_feeding=False,
        per_dog_default=False,
        mode_default="cards",
    )

    assert payload["dashboard_theme"] == "minimal"
    assert payload["dashboard_template"] == "panels"
    assert payload["dashboard_mode"] == "full"
    assert payload["show_maps"] is False
    assert payload["auto_refresh"] is False
    assert payload["refresh_interval"] == 180


def test_coerce_feeding_configuration_defaults() -> None:
    """Feeding configuration defaults to flexible scheduling with reminders."""

    payload = _coerce_feeding_configuration(FeedingConfigurationStepInput())

    assert payload["default_daily_food_amount"] == 500.0
    assert payload["default_meals_per_day"] == 2
    assert payload["default_special_diet"] == []
    assert payload["auto_portion_calculation"] is True
    assert payload["medication_with_meals"] is False


def test_build_module_placeholders() -> None:
    """Module placeholders expose summary metrics for the UI."""

    summary: ModuleConfigurationSummary = {
        "gps_dogs": 2,
        "health_dogs": 1,
        "feeding_dogs": 1,
        "counts": {"gps": 2, "health": 1, "feeding": 1},
        "total": 4,
        "description": "2 dogs with GPS, 1 with health",
    }

    placeholders = _build_module_placeholders(summary=summary, dog_count=3)

    assert placeholders == {
        "dog_count": 3,
        "module_summary": "2 dogs with GPS, 1 with health",
        "total_modules": 4,
        "gps_dogs": 2,
        "health_dogs": 1,
    }


def test_build_dashboard_and_feeding_placeholders() -> None:
    """Dashboard and feeding placeholders render typed values."""

    dashboard = _build_dashboard_placeholders(
        dog_count=2,
        dashboard_info="Standard setup",
        features="status_cards, quick_actions",
    )
    feeding = _build_feeding_placeholders(dog_count=1, summary="Doggo")

    assert dashboard == {
        "dog_count": 2,
        "dashboard_info": "Standard setup",
        "features": "status_cards, quick_actions",
    }
    assert feeding == {"dog_count": 1, "feeding_summary": "Doggo"}


def test_dog_modules_from_flow_input_flags() -> None:
    """Config-flow flag payloads normalise into module configs."""

    selection = DogModuleSelectionInput(enable_feeding=True, enable_gps=False)

    modules = dog_modules_from_flow_input(selection)

    assert set(modules) == set(MODULE_TOGGLE_KEYS)
    assert modules["feeding"] is True
    assert modules["gps"] is False
    assert all(isinstance(value, bool) for value in modules.values())


def test_dog_modules_from_flow_input_merges_existing_defaults() -> None:
    """Existing module toggles persist when flow payload omits them."""

    existing: DogModulesConfig = {
        "walk": True,
        "notifications": True,
        "garden": False,
    }
    selection = DogModuleSelectionInput()

    modules = dog_modules_from_flow_input(selection, existing=existing)

    assert set(modules) == set(MODULE_TOGGLE_KEYS)
    assert modules["walk"] is True
    assert modules["notifications"] is True
    assert modules["garden"] is False


class _ModuleFlowHarness(ModuleConfigurationMixin):
    """Harness exposing module configuration steps for UI regression tests."""

    def __init__(self, *, dogs: list[DogConfigData], language: str = "en") -> None:
        self._dogs = dogs
        self._global_settings = cast(ConfigFlowGlobalSettings, {})
        self._dashboard_config = cast(DashboardSetupConfig, {})
        self._feeding_config = cast(FeedingSetupConfig, {})
        self._enabled_modules = cast(DogModulesConfig, {})
        self._external_entities = cast(ExternalEntityConfig, {})
        self.hass = SimpleNamespace(config=SimpleNamespace(language=language))
        self.forms: list[dict[str, Any]] = []
        self.transitions: list[str] = []

    async def async_step_configure_external_entities(
        self, user_input: dict[str, object] | None = None
    ) -> dict[str, Any]:
        self.transitions.append("external_entities")
        return {"type": "form", "step_id": "configure_external_entities"}

    async def async_step_final_setup(
        self, user_input: dict[str, object] | None = None
    ) -> dict[str, Any]:
        self.transitions.append("final_setup")
        return {"type": "create_entry", "data": user_input or {}}

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: Any,
        description_placeholders: MappingProxyType[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        placeholders = (
            description_placeholders
            if description_placeholders is not None
            else MappingProxyType({})
        )
        form = {
            "step_id": step_id,
            "schema": data_schema,
            "description_placeholders": placeholders,
            "errors": errors or {},
        }
        self.forms.append(form)
        return {"type": "form", **form}


@pytest.mark.asyncio
async def test_async_step_configure_modules_routes_to_dashboard_form() -> None:
    """Module configuration stores typed settings and exposes dashboard form."""

    dogs = [
        cast(
            DogConfigData,
            {
                "dog_id": "dog-1",
                "dog_name": "Buddy",
                "modules": cast(
                    DogModulesConfig,
                    {
                        MODULE_DASHBOARD: True,
                        MODULE_FEEDING: True,
                        MODULE_GPS: False,
                        MODULE_HEALTH: False,
                    },
                ),
            },
        ),
        cast(
            DogConfigData,
            {
                "dog_id": "dog-2",
                "dog_name": "Luna",
                "modules": cast(
                    DogModulesConfig,
                    {
                        MODULE_DASHBOARD: True,
                        MODULE_FEEDING: False,
                        MODULE_GPS: False,
                        MODULE_HEALTH: True,
                    },
                ),
            },
        ),
    ]

    flow = _ModuleFlowHarness(dogs=dogs)

    module_form = await flow.async_step_configure_modules()
    assert module_form["type"] == "form"
    placeholders = module_form["description_placeholders"]
    assert isinstance(placeholders, dict)
    assert placeholders["dog_count"] == 2
    assert placeholders["total_modules"] == 4
    assert placeholders["module_summary"] == (
        "1 dogs with health monitoring, 1 dogs with feeding tracking"
    )
    assert placeholders["gps_dogs"] == 0

    result = await flow.async_step_configure_modules(
        cast(
            ModuleConfigurationStepInput,
            {
                "performance_mode": "full",
                "enable_analytics": True,
                "enable_cloud_backup": False,
                "data_retention_days": 120,
                "debug_logging": True,
            },
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "configure_dashboard"
    assert flow._global_settings == {
        "performance_mode": "full",
        "enable_analytics": True,
        "enable_cloud_backup": False,
        "data_retention_days": 120,
        "debug_logging": True,
    }


@pytest.mark.asyncio
async def test_async_step_configure_dashboard_handles_payload() -> None:
    """Dashboard step exposes localized placeholders and persists settings."""

    dogs = [
        cast(
            DogConfigData,
            {
                "dog_id": "dog-1",
                "dog_name": "Buddy",
                "modules": cast(
                    DogModulesConfig,
                    {
                        MODULE_DASHBOARD: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: False,
                        MODULE_FEEDING: False,
                    },
                ),
            },
        ),
        cast(
            DogConfigData,
            {
                "dog_id": "dog-2",
                "dog_name": "Luna",
                "modules": cast(
                    DogModulesConfig,
                    {
                        MODULE_DASHBOARD: True,
                        MODULE_GPS: False,
                        MODULE_HEALTH: True,
                        MODULE_FEEDING: True,
                    },
                ),
            },
        ),
    ]

    flow = _ModuleFlowHarness(dogs=dogs, language="de")

    form_result = await flow.async_step_configure_dashboard()
    assert form_result["type"] == "form"
    placeholders = form_result["description_placeholders"]
    assert isinstance(placeholders, dict)
    assert placeholders["dog_count"] == 2
    assert placeholders["dashboard_info"].startswith("Das Dashboard enthält")
    assert "Standortkarten" in placeholders["features"]

    transition = await flow.async_step_configure_dashboard(
        cast(
            DashboardConfigurationStepInput,
            {
                "auto_create_dashboard": False,
                "create_per_dog_dashboards": True,
                "dashboard_theme": "dark",
                "dashboard_template": "panels",
                "dashboard_mode": "timeline",
                "show_statistics": False,
                "show_maps": True,
                "show_health_charts": True,
                "show_feeding_schedule": False,
                "show_alerts": True,
                "compact_mode": True,
                "auto_refresh": False,
                "refresh_interval": 120,
            },
        )
    )

    assert transition["step_id"] == "configure_external_entities"
    assert flow.transitions[-1] == "external_entities"
    assert flow._dashboard_config == {
        "dashboard_enabled": True,
        "dashboard_auto_create": False,
        "dashboard_per_dog": True,
        "dashboard_theme": "dark",
        "dashboard_template": "panels",
        "dashboard_mode": "timeline",
        "show_statistics": False,
        "show_maps": True,
        "show_health_charts": True,
        "show_feeding_schedule": False,
        "show_alerts": True,
        "compact_mode": True,
        "auto_refresh": False,
        "refresh_interval": 120,
    }


@pytest.mark.asyncio
async def test_async_step_configure_feeding_details_roundtrip() -> None:
    """Feeding configuration captures typed payloads and reaches final step."""

    dogs = [
        cast(
            DogConfigData,
            {
                "dog_id": "dog-1",
                "dog_name": "Buddy",
                "modules": cast(
                    DogModulesConfig,
                    {
                        MODULE_DASHBOARD: False,
                        MODULE_FEEDING: True,
                        MODULE_GPS: False,
                        MODULE_HEALTH: False,
                    },
                ),
            },
        )
    ]

    flow = _ModuleFlowHarness(dogs=dogs)

    feeding_form = await flow.async_step_configure_modules(
        cast(ModuleConfigurationStepInput, {})
    )
    assert feeding_form["type"] == "form"
    assert feeding_form["step_id"] == "configure_feeding_details"
    placeholders = feeding_form["description_placeholders"]
    assert isinstance(placeholders, dict)
    assert placeholders["dog_count"] == 1
    assert placeholders["feeding_summary"].startswith("Feeding configuration for")

    final_result = await flow.async_step_configure_feeding_details(
        cast(
            FeedingConfigurationStepInput,
            {
                "daily_food_amount": 350.0,
                "meals_per_day": 3,
                "food_type": "wet_food",
                "special_diet": ["grain_free"],
                "feeding_schedule_type": "structured",
                "portion_calculation": False,
                "medication_with_meals": True,
                "feeding_reminders": False,
                "portion_tolerance": 15,
            },
        )
    )

    assert final_result["type"] == "create_entry"
    assert flow.transitions[-1] == "final_setup"
    assert flow._feeding_config == {
        "default_daily_food_amount": 350.0,
        "default_meals_per_day": 3,
        "default_food_type": "wet_food",
        "default_special_diet": ["grain_free"],
        "default_feeding_schedule_type": "structured",
        "auto_portion_calculation": False,
        "medication_with_meals": True,
        "feeding_reminders": False,
        "portion_tolerance": 15,
    }
