"""Coverage-focused tests for flow step schema builders."""

from datetime import datetime

import pytest
import voluptuous as vol

from custom_components.pawcontrol.const import CONF_GPS_SOURCE, MODULE_MEDICATION
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.flow_steps.gps_schemas import (
    build_dog_gps_schema,
    build_geofence_settings_schema,
    build_gps_settings_schema,
)
from custom_components.pawcontrol.flow_steps.health_schemas import (
    build_dog_health_schema,
    build_health_settings_schema,
)
from custom_components.pawcontrol.flow_steps.notifications_helpers import (
    _bool_default,
    _string_default,
    _validate_time_input,
    build_notification_settings_payload,
)
from custom_components.pawcontrol.flow_steps.notifications_schemas import (
    build_notifications_schema,
)
from custom_components.pawcontrol.flows.walk_schemas import (
    build_auto_end_walks_field,
    build_walk_timing_schema_fields,
)
from custom_components.pawcontrol.types import (
    GEOFENCE_RADIUS_FIELD,
    GPS_ENABLED_FIELD,
    GPS_UPDATE_INTERVAL_FIELD,
    NOTIFICATION_MOBILE_FIELD,
    NOTIFICATION_PRIORITY_FIELD,
    NOTIFICATION_QUIET_END_FIELD,
    NOTIFICATION_QUIET_HOURS_FIELD,
    NOTIFICATION_QUIET_START_FIELD,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
    DoorSensorSettingsConfig,
)


def _default(schema: vol.Schema, key_name: str):
    for marker in schema.schema:
        if isinstance(marker, vol.Marker) and marker.schema == key_name:
            value = marker.default
            return value() if callable(value) else value
    raise AssertionError(f"Missing marker {key_name}")


def test_gps_and_geofence_schema_defaults_are_built() -> None:  # noqa: D103
    dog_schema = build_dog_gps_schema({"device_tracker.fido": "Fido"})
    assert _default(dog_schema, CONF_GPS_SOURCE) is vol.UNDEFINED

    settings_schema = build_gps_settings_schema({GPS_ENABLED_FIELD: False})
    assert _default(settings_schema, GPS_ENABLED_FIELD) is False
    assert isinstance(_default(settings_schema, GPS_UPDATE_INTERVAL_FIELD), int)

    geofence_schema = build_geofence_settings_schema({GEOFENCE_RADIUS_FIELD: 150.7})
    assert _default(geofence_schema, GEOFENCE_RADIUS_FIELD) == 150


def test_health_and_walk_schemas_cover_dynamic_defaults() -> None:  # noqa: D103
    health_schema = build_dog_health_schema(
        dog_age=8,
        dog_size="large",
        suggested_ideal_weight=20.5,
        suggested_activity="moderate",
        modules={MODULE_MEDICATION: True},
    )
    assert _default(health_schema, "senior_formula") is True
    assert _default(health_schema, "joint_support") is True
    assert _default(health_schema, "medication_1_frequency") == "daily"

    settings_schema = build_health_settings_schema({}, None)
    assert _default(settings_schema, "weight_tracking") is True

    defaults = DoorSensorSettingsConfig(
        walk_detection_timeout=600,
        minimum_walk_duration=300,
        maximum_walk_duration=3600,
        auto_end_walks=True,
    )
    walk_fields = build_walk_timing_schema_fields({}, defaults)
    auto_end_field = build_auto_end_walks_field({}, defaults)
    assert len(walk_fields) == 3
    assert _default(vol.Schema(auto_end_field), "auto_end_walks") is True


def test_notification_helpers_validate_and_coerce_values() -> None:  # noqa: D103
    _validate_time_input(None, NOTIFICATION_QUIET_START_FIELD)
    _validate_time_input(0, NOTIFICATION_QUIET_START_FIELD)
    _validate_time_input("   ", NOTIFICATION_QUIET_START_FIELD)
    _validate_time_input(datetime(2025, 1, 1, 22, 0), NOTIFICATION_QUIET_START_FIELD)
    _validate_time_input("22:30", NOTIFICATION_QUIET_START_FIELD)

    with pytest.raises(FlowValidationError):
        _validate_time_input("not-a-time", NOTIFICATION_QUIET_START_FIELD)

    payload = build_notification_settings_payload(
        {
            NOTIFICATION_QUIET_HOURS_FIELD: True,
            NOTIFICATION_QUIET_START_FIELD: "23:00",
            NOTIFICATION_QUIET_END_FIELD: "07:00",
            NOTIFICATION_REMINDER_REPEAT_FIELD: "30",
        },
        {},
        coerce_bool=lambda value, default: default if value is None else bool(value),
        coerce_time_string=lambda value, default: (
            default if value in (None, "") else str(value)
        ),
    )

    assert payload[NOTIFICATION_REMINDER_REPEAT_FIELD] == 30

    with pytest.raises(FlowValidationError):
        build_notification_settings_payload(
            {
                NOTIFICATION_REMINDER_REPEAT_FIELD: "not-a-number",
            },
            {},
            coerce_bool=lambda value, default: (
                default if value is None else bool(value)
            ),
            coerce_time_string=lambda value, default: (
                default if value in (None, "") else str(value)
            ),
        )


def test_notification_default_helpers_fallback_for_type_mismatches() -> None:
    """Default extractors should ignore wrong incoming value types."""
    current = {
        NOTIFICATION_QUIET_HOURS_FIELD: "yes",
        NOTIFICATION_QUIET_START_FIELD: 2200,
    }

    assert _bool_default(current, NOTIFICATION_QUIET_HOURS_FIELD, False) is False
    assert _string_default(current, NOTIFICATION_QUIET_START_FIELD, "22:00:00") == (
        "22:00:00"
    )


def test_notification_payload_uses_current_defaults_when_input_missing() -> None:
    """Payload builder should preserve current values when no new value is sent."""
    current = {
        NOTIFICATION_QUIET_HOURS_FIELD: False,
        NOTIFICATION_QUIET_START_FIELD: "21:30:00",
        NOTIFICATION_QUIET_END_FIELD: "06:45:00",
        NOTIFICATION_PRIORITY_FIELD: False,
        NOTIFICATION_MOBILE_FIELD: True,
    }

    payload = build_notification_settings_payload(
        {
            NOTIFICATION_REMINDER_REPEAT_FIELD: "15",
        },
        current,
        coerce_bool=lambda value, default: default if value is None else bool(value),
        coerce_time_string=lambda value, default: (
            default if value in (None, "") else str(value)
        ),
    )

    assert payload[NOTIFICATION_QUIET_HOURS_FIELD] is False
    assert payload[NOTIFICATION_QUIET_START_FIELD] == "21:30:00"
    assert payload[NOTIFICATION_QUIET_END_FIELD] == "06:45:00"
    assert payload[NOTIFICATION_PRIORITY_FIELD] is False
    assert payload[NOTIFICATION_MOBILE_FIELD] is True


def test_notifications_schema_uses_current_defaults_without_user_input() -> None:
    """Notification schema should fallback to current notification defaults."""
    current = {
        NOTIFICATION_QUIET_HOURS_FIELD: False,
        NOTIFICATION_QUIET_START_FIELD: "21:00:00",
        NOTIFICATION_QUIET_END_FIELD: "06:00:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: 25,
        NOTIFICATION_PRIORITY_FIELD: False,
        NOTIFICATION_MOBILE_FIELD: True,
    }

    schema = build_notifications_schema(current, None)

    assert _default(schema, NOTIFICATION_QUIET_HOURS_FIELD) is False
    assert _default(schema, NOTIFICATION_QUIET_START_FIELD) == "21:00:00"
    assert _default(schema, NOTIFICATION_QUIET_END_FIELD) == "06:00:00"
    assert _default(schema, NOTIFICATION_REMINDER_REPEAT_FIELD) == 25
    assert _default(schema, NOTIFICATION_PRIORITY_FIELD) is False
    assert _default(schema, NOTIFICATION_MOBILE_FIELD) is True


def test_notifications_schema_prefers_user_input_over_current_defaults() -> None:
    """Notification schema should prefer staged user input values."""
    current = {
        NOTIFICATION_QUIET_HOURS_FIELD: False,
        NOTIFICATION_QUIET_START_FIELD: "21:00:00",
        NOTIFICATION_QUIET_END_FIELD: "06:00:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: 25,
        NOTIFICATION_PRIORITY_FIELD: False,
        NOTIFICATION_MOBILE_FIELD: True,
    }
    user_input = {
        NOTIFICATION_QUIET_HOURS_FIELD: True,
        NOTIFICATION_QUIET_START_FIELD: "22:15:00",
        NOTIFICATION_QUIET_END_FIELD: "07:15:00",
        NOTIFICATION_REMINDER_REPEAT_FIELD: 45,
        NOTIFICATION_PRIORITY_FIELD: True,
        NOTIFICATION_MOBILE_FIELD: False,
    }

    schema = build_notifications_schema(current, user_input)

    assert _default(schema, NOTIFICATION_QUIET_HOURS_FIELD) is True
    assert _default(schema, NOTIFICATION_QUIET_START_FIELD) == "22:15:00"
    assert _default(schema, NOTIFICATION_QUIET_END_FIELD) == "07:15:00"
    assert _default(schema, NOTIFICATION_REMINDER_REPEAT_FIELD) == 45
    assert _default(schema, NOTIFICATION_PRIORITY_FIELD) is True
    assert _default(schema, NOTIFICATION_MOBILE_FIELD) is False
