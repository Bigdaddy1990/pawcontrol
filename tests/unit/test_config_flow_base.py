"""Regression tests for the shared config flow helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.const import CONF_NAME
import pytest

from custom_components.pawcontrol.config_flow_base import PawControlBaseConfigFlow
from custom_components.pawcontrol.const import MODULE_FEEDING, MODULE_GPS, MODULE_HEALTH
from custom_components.pawcontrol.types import (
    DOG_AGE_FIELD,
    DOG_BREED_FIELD,
    DOG_FEEDING_CONFIG_FIELD,
    DOG_GPS_CONFIG_FIELD,
    DOG_HEALTH_CONFIG_FIELD,
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DOG_SIZE_FIELD,
    DOG_WEIGHT_FIELD,
    FeedingSizeDefaults,
    IntegrationNameValidationResult,
)


class _TestFlow(PawControlBaseConfigFlow):
    """Minimal flow subclass exposing the base utilities for testing."""

    def __init__(self) -> None:
        super().__init__()
        # The config flow only needs ``hass`` for entity lookups, so we provide a
        # lightweight mock that satisfies the attribute contract without touching
        # Home Assistant internals.
        self.hass = MagicMock()
        self.hass.states.async_entity_ids.return_value = []
        self.hass.states.get.return_value = None
        self.hass.services.async_services.return_value = {}


@pytest.mark.asyncio
async def test_validate_integration_name_rejects_reserved() -> None:
    """Reserved integration names surface a typed validation error payload."""
    flow = _TestFlow()

    result: IntegrationNameValidationResult = (
        await flow._async_validate_integration_name("Home Assistant")
    )

    assert result["valid"] is False
    assert result["errors"] == {CONF_NAME: "reserved_integration_name"}


@pytest.mark.asyncio
async def test_validate_integration_name_accepts_trimmed() -> None:
    """Whitespace-trimmed names are accepted and return an empty error map."""
    flow = _TestFlow()

    result: IntegrationNameValidationResult = (
        await flow._async_validate_integration_name("  Paw Control  ")
    )

    assert result["valid"] is True
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_validate_integration_name_handles_empty_and_too_long() -> None:
    """Validation surfaces required and length errors for invalid names."""
    flow = _TestFlow()

    empty_result: IntegrationNameValidationResult = (
        await flow._async_validate_integration_name("   ")
    )
    assert empty_result["valid"] is False
    assert empty_result["errors"] == {CONF_NAME: "integration_name_required"}

    too_long_result: IntegrationNameValidationResult = (
        await flow._async_validate_integration_name("x" * 51)
    )
    assert too_long_result["valid"] is False
    assert too_long_result["errors"] == {CONF_NAME: "integration_name_too_long"}


def test_get_feeding_defaults_by_size_returns_structured_payload() -> None:
    """Feeding defaults expose the typed size payload for scheduler setup."""
    flow = _TestFlow()

    defaults: FeedingSizeDefaults = flow._get_feeding_defaults_by_size("toy")

    assert defaults["meals_per_day"] == 3
    assert defaults["daily_food_amount"] == 150
    assert defaults["feeding_times"] == ["07:00:00", "12:00:00", "18:00:00"]
    assert defaults["portion_size"] == 50

    fallback: FeedingSizeDefaults = flow._get_feeding_defaults_by_size("unknown")

    assert fallback == flow._get_feeding_defaults_by_size("medium")


def test_generate_unique_id_sanitizes_and_prefixes() -> None:
    """Unique IDs are URL-safe and always begin with an alphabetic prefix."""
    flow = _TestFlow()

    assert flow._generate_unique_id("Paw Control-Pro") == "paw_control_pro"
    assert flow._generate_unique_id("123#Dog") == "paw_control_123dog"


def test_feature_summary_and_weight_compatibility_are_consistent() -> None:
    """Feature list text and size-weight compatibility ranges remain stable."""
    flow = _TestFlow()

    feature_summary = flow._get_feature_summary()
    assert "🐕 Multi-dog management with individual settings" in feature_summary
    assert "📱 Mobile app integration" in feature_summary

    assert flow._is_weight_size_compatible(14.0, "toy") is True
    assert flow._is_weight_size_compatible(40.0, "toy") is False
    assert flow._is_weight_size_compatible(95.0, "unknown") is False


def test_format_dogs_list_without_dogs_returns_empty_state_hint() -> None:
    """Empty dog state uses the onboarding hint string."""
    flow = _TestFlow()

    assert flow._format_dogs_list() == (
        "No dogs configured yet. Add your first dog to get started!"
    )


def test_format_dogs_list_and_module_summary_include_special_config() -> None:
    """Dog formatting and summary output include module counts and special flags."""
    flow = _TestFlow()
    flow._dogs = [
        {
            DOG_ID_FIELD: "luna",
            DOG_NAME_FIELD: "Luna",
            DOG_BREED_FIELD: "",
            DOG_SIZE_FIELD: "giant",
            DOG_AGE_FIELD: 7,
            DOG_WEIGHT_FIELD: 42,
            DOG_GPS_CONFIG_FIELD: {"enabled": True},
            DOG_FEEDING_CONFIG_FIELD: {"enabled": True},
            DOG_HEALTH_CONFIG_FIELD: {"enabled": True},
            DOG_MODULES_FIELD: {
                MODULE_GPS: True,
                MODULE_FEEDING: True,
                MODULE_HEALTH: False,
            },
        },
    ]

    formatted = flow._format_dogs_list()
    assert "🐺 **Luna** (luna)" in formatted
    assert "Mixed Breed" in formatted
    assert "📍 GPS | 🍽️ Feeding | 🏥 Health" in formatted

    summary = flow._get_dogs_module_summary()
    assert summary == "• Luna: feeding, gps"


def test_dashboard_setup_info_reports_enabled_modules_and_multi_dog() -> None:
    """Dashboard setup details include optional module blocks and dog count hints."""
    flow = _TestFlow()
    flow._dogs = [
        {
            DOG_ID_FIELD: "max",
            DOG_NAME_FIELD: "Max",
            DOG_MODULES_FIELD: {
                MODULE_GPS: True,
                MODULE_FEEDING: False,
                MODULE_HEALTH: True,
            },
        },
        {
            DOG_ID_FIELD: "bella",
            DOG_NAME_FIELD: "Bella",
            DOG_MODULES_FIELD: {
                MODULE_GPS: False,
                MODULE_FEEDING: True,
                MODULE_HEALTH: False,
            },
        },
    ]

    assert "GPS Maps" in flow._get_dashboard_features_string(has_gps=True)
    setup_info = flow._get_dashboard_setup_info()
    assert "🗺️ GPS maps and location tracking" in setup_info
    assert "🍽️ Feeding schedules and meal tracking" in setup_info
    assert "📈 Health charts and medication reminders" in setup_info
    assert "🐕 Individual dashboards for 2 dogs available" in setup_info


@pytest.mark.asyncio
async def test_breed_and_id_suggestions_handle_name_patterns_and_conflicts() -> None:
    """Breed and ID helpers return deterministic suggestions and resolve conflicts."""
    flow = _TestFlow()
    flow._dogs = [{DOG_ID_FIELD: "max"}, {DOG_ID_FIELD: "max_2"}]

    assert (
        await flow._suggest_dog_breed({
            DOG_NAME_FIELD: "Maximus",
            DOG_SIZE_FIELD: "small",
        })
        == "German Shepherd"
    )
    assert (
        await flow._suggest_dog_breed({
            DOG_NAME_FIELD: "Unknown",
            DOG_SIZE_FIELD: "toy",
        })
        == "Chihuahua"
    )
    assert await flow._suggest_dog_breed(None) == ""

    assert (
        await flow._generate_smart_dog_id_suggestion({DOG_NAME_FIELD: "Max"}) == "max_3"
    )
    assert (
        await flow._generate_smart_dog_id_suggestion({DOG_NAME_FIELD: "123 Lucky"})
        == "dog_123_l"
    )
    assert await flow._generate_smart_dog_id_suggestion(None) == ""


def test_entity_and_service_discovery_filters_invalid_sources() -> None:
    """Entity/service discovery methods keep only supported and available entries."""
    flow = _TestFlow()

    flow.hass.states.async_entity_ids.side_effect = lambda domain: {
        "device_tracker": ["device_tracker.phone", "device_tracker.home_assistant_app"],
        "person": ["person.alex", "person.sam"],
        "binary_sensor": ["binary_sensor.front_door", "binary_sensor.motion"],
    }[domain]
    flow.hass.states.get.side_effect = lambda entity_id: {
        "device_tracker.phone": SimpleNamespace(
            state="home",
            attributes={"friendly_name": "Alex Phone"},
        ),
        "device_tracker.home_assistant_app": SimpleNamespace(
            state="home",
            attributes={"friendly_name": "App Tracker"},
        ),
        "person.alex": SimpleNamespace(
            state="home", attributes={"friendly_name": "Alex"}
        ),
        "person.sam": None,
        "binary_sensor.front_door": SimpleNamespace(
            state="off",
            attributes={"device_class": "door", "friendly_name": "Front Door"},
        ),
        "binary_sensor.motion": SimpleNamespace(
            state="off",
            attributes={"device_class": "motion", "friendly_name": "Motion"},
        ),
    }.get(entity_id)
    flow.hass.services.async_services.return_value = {
        "notify": {"mobile_app_pixel": object(), "persistent_notification": object()}
    }

    assert flow._get_available_device_trackers() == {
        "device_tracker.phone": "Alex Phone"
    }
    assert flow._get_available_person_entities() == {"person.alex": "Alex"}
    assert flow._get_available_door_sensors() == {
        "binary_sensor.front_door": "Front Door"
    }
    assert flow._get_available_notify_services() == {
        "notify.mobile_app_pixel": "Mobile App Pixel"
    }
