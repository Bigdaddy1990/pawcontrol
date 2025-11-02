"""Tests for config flow module typed helpers."""

from __future__ import annotations

from custom_components.pawcontrol.config_flow_modules import (
    _build_dashboard_placeholders,
    _build_feeding_placeholders,
    _build_module_placeholders,
    _coerce_dashboard_configuration,
    _coerce_feeding_configuration,
    _coerce_module_global_settings,
)
from custom_components.pawcontrol.types import (
    DashboardConfigurationStepInput,
    FeedingConfigurationStepInput,
    ModuleConfigurationStepInput,
    ModuleConfigurationSummary,
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
