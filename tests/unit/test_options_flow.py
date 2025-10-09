from __future__ import annotations

import json
from datetime import time
from typing import cast
from unittest.mock import Mock

import pytest
from custom_components.pawcontrol.const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DASHBOARD_MODE,
    CONF_DOGS,
    CONF_EXTERNAL_INTEGRATIONS,
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_MODULES,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT_MIN,
    CONF_RESET_TIME,
    CONF_WEATHER_ENTITY,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow
from custom_components.pawcontrol.types import (
    AdvancedOptions,
    DashboardOptions,
    DogConfigData,
    DogOptionsMap,
    FeedingOptions,
    GeofenceOptions,
    GPSOptions,
    HealthOptions,
    NotificationOptions,
    OptionsExportPayload,
    PawControlOptionsData,
    SystemOptions,
    WeatherOptions,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


@pytest.mark.asyncio
async def test_geofence_settings_coercion(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Geofence options should be normalised into typed payloads."""

    hass.config.latitude = 12.34
    hass.config.longitude = 56.78

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_geofence_settings(
        {
            "geofencing_enabled": True,
            "geofence_radius_m": "120",
            "geofence_lat": "41.8899",
            "geofence_lon": 12.4923,
            "geofence_alerts_enabled": False,
            "safe_zone_alerts": False,
            "restricted_zone_alerts": True,
            "zone_entry_notifications": True,
            "zone_exit_notifications": False,
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])
    geofence = cast(GeofenceOptions, options["geofence_settings"])

    assert geofence["geofence_radius_m"] == 120
    assert geofence["geofence_lat"] == pytest.approx(41.8899)
    assert geofence["geofence_lon"] == pytest.approx(12.4923)
    assert geofence["geofence_alerts_enabled"] is False
    assert geofence["safe_zone_alerts"] is False
    assert geofence["restricted_zone_alerts"] is True
    assert geofence["zone_entry_notifications"] is True
    assert geofence["zone_exit_notifications"] is False


@pytest.mark.asyncio
async def test_notification_settings_structured(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Notification settings should store typed quiet-hour metadata."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_notifications(
        {
            "quiet_hours": False,
            "quiet_start": "21:30:00",
            "quiet_end": "06:45:00",
            "reminder_repeat_min": "45",
            "priority_notifications": True,
            "mobile_notifications": False,
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])
    notifications = cast(NotificationOptions, options[CONF_NOTIFICATIONS])

    assert notifications[CONF_QUIET_HOURS] is False
    assert notifications[CONF_QUIET_START] == "21:30:00"
    assert notifications[CONF_QUIET_END] == "06:45:00"
    assert notifications[CONF_REMINDER_REPEAT_MIN] == 45
    assert notifications["priority_notifications"] is True
    assert notifications["mobile_notifications"] is False


@pytest.mark.asyncio
async def test_performance_settings_normalisation(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Performance settings normalise mixed input types into typed options."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_performance_settings(
        {
            "entity_profile": "advanced",
            "performance_mode": "FAST",
            "batch_size": 25.0,
            "cache_ttl": "900",
            "selective_refresh": "0",
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])

    assert options["entity_profile"] == "advanced"
    assert options["performance_mode"] == "balanced"
    assert options["batch_size"] == 25
    assert options["cache_ttl"] == 900
    assert options["selective_refresh"] is False


@pytest.mark.asyncio
async def test_entity_profile_placeholders_expose_reconfigure_telemetry(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Entity profile form should surface the latest reconfigure telemetry."""

    mock_config_entry.options.update(
        {
            "entity_profile": "standard",
            "last_reconfigure": "2024-01-02T03:04:05+00:00",
            "reconfigure_telemetry": {
                "timestamp": "2024-01-02T03:04:05+00:00",
                "requested_profile": "balanced",
                "previous_profile": "advanced",
                "dogs_count": 2,
                "estimated_entities": 12,
                "compatibility_warnings": ["GPS disabled for dog"],
                "health_summary": {
                    "healthy": False,
                    "issues": ["Missing GPS source"],
                    "warnings": ["Reauth recommended"],
                },
            },
        }
    )

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_entity_profiles()

    placeholders = result["description_placeholders"]
    assert placeholders["reconfigure_requested_profile"] == "balanced"
    assert placeholders["reconfigure_previous_profile"] == "advanced"
    assert placeholders["reconfigure_dogs"] == "2"
    assert placeholders["reconfigure_entities"] == "12"
    assert "Missing GPS source" in placeholders["reconfigure_health"]
    assert "GPS disabled" in placeholders["reconfigure_warnings"]


@pytest.mark.asyncio
async def test_weather_settings_normalisation(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Weather options should clamp intervals and clean override payloads."""

    hass.states.async_set(
        "weather.home", "sunny", {"friendly_name": "Home", "temperature": 21}
    )

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_weather_settings(
        {
            "weather_entity": "weather.home",
            "weather_health_monitoring": False,
            "weather_alerts": True,
            "weather_update_interval": "5",
            "temperature_alerts": "1",
            "uv_alerts": 0,
            "humidity_alerts": "yes",
            "wind_alerts": "on",
            "storm_alerts": "false",
            "breed_specific_recommendations": "",
            "health_condition_adjustments": True,
            "auto_activity_adjustments": "1",
            "notification_threshold": "EXTREME",
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])
    weather = cast(WeatherOptions, options["weather_settings"])

    assert options[CONF_WEATHER_ENTITY] == "weather.home"
    assert weather[CONF_WEATHER_ENTITY] == "weather.home"
    assert weather["weather_update_interval"] == 15
    assert weather["weather_health_monitoring"] is False
    assert weather["weather_alerts"] is True
    assert weather["temperature_alerts"] is True
    assert weather["uv_alerts"] is False
    assert weather["humidity_alerts"] is True
    assert weather["wind_alerts"] is True
    assert weather["storm_alerts"] is False
    assert weather["breed_specific_recommendations"] is False
    assert weather["auto_activity_adjustments"] is True
    assert weather["notification_threshold"] == "moderate"


@pytest.mark.asyncio
async def test_feeding_settings_coercion(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Feeding options should normalise numeric ranges and booleans."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_feeding_settings(
        {
            "meals_per_day": "7",
            "feeding_reminders": "0",
            "portion_tracking": True,
            "calorie_tracking": "False",
            "auto_schedule": "yes",
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])
    feeding = cast(FeedingOptions, options["feeding_settings"])

    assert feeding["default_meals_per_day"] == 6
    assert feeding["feeding_reminders"] is False
    assert feeding["portion_tracking"] is True
    assert feeding["calorie_tracking"] is False
    assert feeding["auto_schedule"] is True


@pytest.mark.asyncio
async def test_health_settings_coercion(hass: HomeAssistant, mock_config_entry) -> None:
    """Health options should coerce truthy strings to booleans."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_health_settings(
        {
            "weight_tracking": "no",
            "medication_reminders": "on",
            "vet_reminders": "true",
            "grooming_reminders": "0",
            "health_alerts": "yes",
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])
    health = cast(HealthOptions, options["health_settings"])

    assert health["weight_tracking"] is False
    assert health["medication_reminders"] is True
    assert health["vet_reminders"] is True
    assert health["grooming_reminders"] is False
    assert health["health_alerts"] is True


@pytest.mark.asyncio
async def test_system_settings_normalisation(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """System options should clamp retention and normalise times."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_system_settings(
        {
            "reset_time": time(4, 30),
            "data_retention_days": "10",
            "auto_backup": "true",
            "performance_mode": "FULL",
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])
    system = cast(SystemOptions, options["system_settings"])

    assert options[CONF_RESET_TIME] == "04:30:00"
    assert system["data_retention_days"] == 30
    assert system["auto_backup"] is True
    assert system["performance_mode"] == "full"


@pytest.mark.asyncio
async def test_dashboard_settings_normalisation(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Dashboard options should normalise modes and booleans."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_dashboard_settings(
        {
            "dashboard_mode": "CARDS",
            "show_statistics": "0",
            "show_alerts": True,
            "compact_mode": "1",
            "show_maps": "off",
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])
    dashboard = cast(DashboardOptions, options["dashboard_settings"])

    assert options[CONF_DASHBOARD_MODE] == "cards"
    assert dashboard["show_statistics"] is False
    assert dashboard["show_alerts"] is True
    assert dashboard["compact_mode"] is True
    assert dashboard["show_maps"] is False


@pytest.mark.asyncio
async def test_advanced_settings_structured(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Advanced options should normalise ranges and mirror root fields."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_advanced_settings(
        {
            "performance_mode": "ULTRA",
            "debug_logging": "true",
            "data_retention_days": "500",
            "auto_backup": "1",
            "experimental_features": "on",
            CONF_EXTERNAL_INTEGRATIONS: "yes",
            CONF_API_ENDPOINT: " https://demo.local ",
            CONF_API_TOKEN: "  secret  ",
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])
    advanced = cast(AdvancedOptions, options["advanced_settings"])

    assert options["performance_mode"] == "balanced"
    assert options["debug_logging"] is True
    assert options["data_retention_days"] == 365
    assert options[CONF_EXTERNAL_INTEGRATIONS] is True
    assert options[CONF_API_ENDPOINT] == "https://demo.local"
    assert options[CONF_API_TOKEN] == "secret"

    assert advanced["performance_mode"] == "balanced"
    assert advanced["debug_logging"] is True
    assert advanced["data_retention_days"] == 365
    assert advanced["auto_backup"] is True
    assert advanced["experimental_features"] is True
    assert advanced[CONF_EXTERNAL_INTEGRATIONS] is True
    assert advanced[CONF_API_ENDPOINT] == "https://demo.local"
    assert advanced[CONF_API_TOKEN] == "secret"


@pytest.mark.asyncio
async def test_gps_settings_structured(hass: HomeAssistant, mock_config_entry) -> None:
    """GPS settings should be stored as typed payloads with validation."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_gps_settings(
        {
            CONF_GPS_UPDATE_INTERVAL: "45",
            CONF_GPS_ACCURACY_FILTER: "12.5",
            CONF_GPS_DISTANCE_FILTER: 30,
            "gps_enabled": False,
            "route_recording": False,
            "route_history_days": "14",
            "auto_track_walks": True,
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    options = cast(PawControlOptionsData, result["data"])
    gps_options = cast(GPSOptions, options["gps_settings"])

    assert options[CONF_GPS_UPDATE_INTERVAL] == 45
    assert options[CONF_GPS_ACCURACY_FILTER] == 12.5
    assert options[CONF_GPS_DISTANCE_FILTER] == 30.0
    assert gps_options[CONF_GPS_UPDATE_INTERVAL] == 45
    assert gps_options[CONF_GPS_ACCURACY_FILTER] == 12.5
    assert gps_options[CONF_GPS_DISTANCE_FILTER] == 30.0
    assert gps_options["gps_enabled"] is False
    assert gps_options["route_recording"] is False
    assert gps_options["route_history_days"] == 14
    assert gps_options["auto_track_walks"] is True


@pytest.mark.asyncio
async def test_dog_module_overrides_recorded(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Dog module configuration should persist typed overrides in options."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)
    flow.hass.config_entries.async_update_entry = Mock()

    dog_config = cast(DogConfigData, mock_config_entry.data[CONF_DOGS][0])
    flow._current_dog = dog_config

    result = await flow.async_step_configure_dog_modules(
        {
            "module_feeding": False,
            "module_walk": True,
            "module_gps": True,
            "module_garden": False,
            "module_health": True,
            "module_notifications": False,
            "module_dashboard": True,
            "module_visitor": True,
            "module_grooming": True,
            "module_medication": False,
            "module_training": True,
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    flow.hass.config_entries.async_update_entry.assert_called_once()

    options = cast(PawControlOptionsData, result["data"])
    dog_options = cast(DogOptionsMap, options["dog_options"])

    dog_entry = dog_options[dog_config["dog_id"]]
    modules = dog_entry["modules"]

    assert modules[MODULE_GPS] is True
    assert modules[MODULE_WALK] is True
    assert modules[MODULE_HEALTH] is True
    assert modules.get("notifications") is False
    assert modules.get("grooming") is True


@pytest.mark.asyncio
async def test_import_export_export_flow(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Export step should surface a JSON payload with current settings."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    menu = await flow.async_step_import_export()
    assert menu["type"] == FlowResultType.FORM
    assert menu["step_id"] == "import_export"

    export_form = await flow.async_step_import_export({"action": "export"})
    assert export_form["type"] == FlowResultType.FORM
    assert export_form["step_id"] == "import_export_export"

    export_blob = export_form["description_placeholders"]["export_blob"]
    payload = cast(OptionsExportPayload, json.loads(export_blob))

    assert payload["version"] == 1
    assert (
        payload["options"]["entity_profile"]
        == mock_config_entry.options["entity_profile"]
    )
    assert (
        payload["dogs"][0]["dog_id"] == mock_config_entry.data[CONF_DOGS][0]["dog_id"]
    )

    finished = await flow.async_step_import_export_export({})
    assert finished["type"] == FlowResultType.MENU
    assert finished["step_id"] == "init"


@pytest.mark.asyncio
async def test_import_export_import_flow(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Import step should apply settings and update config entry data."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)
    flow.hass.config_entries.async_update_entry = Mock()

    baseline = flow._build_export_payload()
    baseline["options"]["entity_profile"] = "advanced"
    baseline["options"]["external_integrations"] = True
    baseline["dogs"][0]["dog_name"] = "Imported Pup"
    baseline["dogs"][0]["modules"] = {
        MODULE_GPS: True,
        MODULE_HEALTH: False,
    }

    payload_blob = json.dumps(baseline)

    import_form = await flow.async_step_import_export({"action": "import"})
    assert import_form["type"] == FlowResultType.FORM
    assert import_form["step_id"] == "import_export_import"

    result = await flow.async_step_import_export_import({"payload": payload_blob})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    flow.hass.config_entries.async_update_entry.assert_called_once()

    options = cast(PawControlOptionsData, result["data"])
    assert options["entity_profile"] == "advanced"
    assert options["external_integrations"] is True

    update_call = flow.hass.config_entries.async_update_entry.call_args
    assert update_call is not None
    update_kwargs = update_call.kwargs
    assert update_kwargs["data"][CONF_DOGS][0]["dog_name"] == "Imported Pup"


@pytest.mark.asyncio
async def test_import_export_import_duplicate_dog(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Duplicate dog IDs should surface a dedicated error code."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    duplicate_payload = flow._build_export_payload()
    duplicate_payload["dogs"].append(dict(duplicate_payload["dogs"][0]))
    payload_blob = json.dumps(duplicate_payload)

    await flow.async_step_import_export({"action": "import"})
    result = await flow.async_step_import_export_import({"payload": payload_blob})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"payload": "dog_duplicate"}


@pytest.mark.asyncio
async def test_import_export_import_invalid_modules(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Non-mapping modules payloads should be rejected during import."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    payload = flow._build_export_payload()
    payload["dogs"][0][CONF_MODULES] = ["not", "valid"]
    payload_blob = json.dumps(payload)

    await flow.async_step_import_export({"action": "import"})
    result = await flow.async_step_import_export_import({"payload": payload_blob})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"payload": "dog_invalid_modules"}


def test_validate_import_payload_sanitises_modules(mock_config_entry) -> None:
    """Dog module flags should be coerced to booleans when importing."""

    flow = PawControlOptionsFlow()
    flow.initialize_from_config_entry(mock_config_entry)

    payload = flow._build_export_payload()
    payload["dogs"][0][CONF_MODULES] = {"gps": "yes", "health": 0}

    validated = flow._validate_import_payload(payload)

    modules = cast(DogConfigData, validated["dogs"][0])[CONF_MODULES]
    assert modules["gps"] is True
    assert modules["health"] is False


@pytest.mark.asyncio
async def test_import_export_import_unsupported_version(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Unsupported export versions should surface a specific error."""

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    payload = flow._build_export_payload()
    payload["version"] = 99  # type: ignore[assignment]
    payload_blob = json.dumps(payload)

    await flow.async_step_import_export({"action": "import"})
    result = await flow.async_step_import_export_import({"payload": payload_blob})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"payload": "unsupported_version"}
