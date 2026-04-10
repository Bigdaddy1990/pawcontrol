"""Targeted branch coverage for validation helper edge paths."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
    clamp_float_range,
    clamp_int_range,
    validate_entity_id,
    validate_expires_in_hours,
    validate_float_range,
    validate_gps_accuracy_value,
    validate_gps_source,
    validate_int_range,
    validate_interval,
    validate_notify_service,
    validate_sensor_entity_id,
)


def _build_hass(
    *,
    states: dict[str, object] | None = None,
    notify_services: dict[str, object] | None = None,
) -> SimpleNamespace:
    """Create a small Home Assistant stub for validation tests."""
    return SimpleNamespace(
        states=SimpleNamespace(get=lambda entity_id: (states or {}).get(entity_id)),
        services=SimpleNamespace(
            async_services=lambda: {"notify": notify_services or {}}
        ),
    )


@pytest.mark.parametrize(
    ("entity_id", "expected"),
    [
        ("sensor.garden_temp", "sensor.garden_temp"),
        ("  binary_sensor.door  ", "binary_sensor.door"),
    ],
)
def test_validate_entity_id_accepts_valid_values(entity_id: str, expected: str) -> None:
    """Entity IDs should be normalized for valid domain/object pairs."""
    assert validate_entity_id(entity_id) == expected


@pytest.mark.parametrize(
    "entity_id",
    [
        42,
        "sensor",
        "sensor.",
        ".garden",
        "Sensor.garden",
        "sensor.garden-temp",
    ],
)
def test_validate_entity_id_rejects_invalid_values(entity_id: object) -> None:
    """Entity IDs outside domain.object format should fail validation."""
    with pytest.raises(ValidationError, match="Invalid entity_id format"):
        validate_entity_id(entity_id)


def test_validate_gps_source_checks_missing_and_unavailable_states() -> None:
    """GPS source should reject missing entities and unavailable states."""
    hass = _build_hass(
        states={
            "device_tracker.available": SimpleNamespace(state="home"),
            "device_tracker.unavailable": SimpleNamespace(state="unavailable"),
        }
    )

    assert validate_gps_source(hass, "manual") == "manual"
    assert validate_gps_source(hass, "webhook") == "webhook"
    assert (
        validate_gps_source(hass, "device_tracker.available")
        == "device_tracker.available"
    )

    with pytest.raises(ValidationError, match="gps_source_not_found"):
        validate_gps_source(hass, "device_tracker.missing")

    with pytest.raises(ValidationError, match="gps_source_unavailable"):
        validate_gps_source(hass, "device_tracker.unavailable")


def test_validate_gps_source_rejects_non_strings_blank_and_manual_override() -> None:
    """GPS source validation should enforce string input and manual policy."""
    hass = _build_hass(states={"device_tracker.rover": SimpleNamespace(state="home")})

    with pytest.raises(ValidationError, match="gps_source_required"):
        validate_gps_source(hass, 42)

    with pytest.raises(ValidationError, match="gps_source_required"):
        validate_gps_source(hass, "   ")

    with pytest.raises(ValidationError, match="gps_source_not_found"):
        validate_gps_source(hass, "manual", allow_manual=False)

    assert validate_gps_source(hass, "mqtt") == "mqtt"


@pytest.mark.parametrize(
    ("notify_service", "message"),
    [
        (42, "notify_service_invalid"),
        ("   ", "notify_service_invalid"),
        ("notify", "notify_service_invalid"),
        ("light.kitchen", "notify_service_invalid"),
        ("notify.mobile_missing", "notify_service_not_found"),
    ],
)
def test_validate_notify_service_rejects_invalid_targets(
    notify_service: object,
    message: str,
) -> None:
    """Notify service validator should reject invalid format and unknown targets."""
    hass = _build_hass(notify_services={"mobile_app": object()})

    with pytest.raises(ValidationError, match=message):
        validate_notify_service(hass, notify_service)


def test_validate_notify_service_accepts_known_notify_services() -> None:
    """Valid notify services should pass and preserve trimmed value."""
    hass = _build_hass(notify_services={"mobile_app": object()})

    assert validate_notify_service(hass, "notify.mobile_app") == "notify.mobile_app"
    assert validate_notify_service(hass, "  notify.mobile_app  ") == "notify.mobile_app"


@pytest.mark.parametrize(
    ("value", "kwargs", "expected"),
    [
        (None, {"minimum": 5, "maximum": 20, "clamp": True}, 5),
        (None, {"minimum": 5, "maximum": 20, "default": 11}, 11),
        (3, {"minimum": 5, "maximum": 20, "clamp": True}, 5),
        (30, {"minimum": 5, "maximum": 20, "clamp": True}, 20),
        (12, {"minimum": 5, "maximum": 20}, 12),
    ],
)
def test_validate_interval_clamp_and_default_branches(
    value: object,
    kwargs: dict[str, object],
    expected: int,
) -> None:
    """Interval validator should support defaulting and clamp branches."""
    assert validate_interval(value, field="interval", **kwargs) == expected


@pytest.mark.parametrize(
    ("value", "minimum", "maximum", "default", "expected"),
    [
        ("bad", 1, 10, 4, 4),
        (50, 1, 10, 4, 10),
        (-2, -1.5, 2.0, 0.5, -1.5),
    ],
)
def test_clamp_ranges_return_default_or_bounds(
    value: object,
    minimum: int | float,
    maximum: int | float,
    default: int | float,
    expected: int | float,
) -> None:
    """Clamp helpers should handle coercion failures and bound violations."""
    if isinstance(default, int):
        assert (
            clamp_int_range(
                value,
                field="interval",
                minimum=int(minimum),
                maximum=int(maximum),
                default=default,
            )
            == expected
        )
    else:
        assert (
            clamp_float_range(
                value,
                field="ratio",
                minimum=float(minimum),
                maximum=float(maximum),
                default=float(default),
            )
            == expected
        )


def test_validate_sensor_entity_id_checks_domain_and_device_class() -> None:
    """Sensor entity validation should enforce domain and class constraints."""
    state = SimpleNamespace(state="on", attributes={"device_class": "motion"})
    hass = _build_hass(states={"binary_sensor.door": state})

    assert (
        validate_sensor_entity_id(
            hass,
            "binary_sensor.door",
            field="door_sensor",
            domain="binary_sensor",
            device_classes={"motion", "door"},
            required=True,
        )
        == "binary_sensor.door"
    )

    with pytest.raises(ValidationError, match="sensor_not_found"):
        validate_sensor_entity_id(
            hass,
            "sensor.door",
            field="door_sensor",
            domain="binary_sensor",
        )

    with pytest.raises(ValidationError, match="sensor_not_found"):
        validate_sensor_entity_id(
            hass,
            "binary_sensor.door",
            field="door_sensor",
            device_classes={"humidity"},
        )


def test_validate_sensor_entity_id_optional_and_required_empty_paths() -> None:
    """Empty sensor IDs should respect required flag and custom constraints."""
    hass = _build_hass()

    assert (
        validate_sensor_entity_id(
            hass,
            None,
            field="door_sensor",
            required=False,
        )
        is None
    )

    with pytest.raises(ValidationError, match="door_sensor_required"):
        validate_sensor_entity_id(
            hass,
            "   ",
            field="door_sensor",
            required=True,
            required_constraint="door_sensor_required",
        )


def test_validate_sensor_entity_id_rejects_unavailable_and_non_string_values() -> None:
    """Unavailable and malformed sensor IDs should fail with not-found constraints."""
    hass = _build_hass(
        states={
            "binary_sensor.unknown_state": SimpleNamespace(state="unknown", attributes={}),
            "binary_sensor.unavailable_state": SimpleNamespace(
                state="unavailable",
                attributes={},
            ),
        }
    )

    with pytest.raises(ValidationError, match="sensor_not_found"):
        validate_sensor_entity_id(
            hass,
            123,
            field="door_sensor",
        )

    with pytest.raises(ValidationError, match="sensor_not_found"):
        validate_sensor_entity_id(
            hass,
            "binary_sensor.unknown_state",
            field="door_sensor",
        )

    with pytest.raises(ValidationError, match="sensor_not_found"):
        validate_sensor_entity_id(
            hass,
            "binary_sensor.unavailable_state",
            field="door_sensor",
        )


@pytest.mark.parametrize(
    ("value", "kwargs", "expected"),
    [
        (None, {"minimum": 1.5, "maximum": 6.0, "required": False}, None),
        ("2.5", {"minimum": 1.5, "maximum": 6.0}, 2.5),
    ],
)
def test_validate_expires_in_hours_accepts_optional_and_numeric_input(
    value: object,
    kwargs: dict[str, object],
    expected: float | None,
) -> None:
    """Expiry hours should accept empty optional values and valid numbers."""
    assert validate_expires_in_hours(value, **kwargs) == expected


@pytest.mark.parametrize(
    ("value", "kwargs", "message"),
    [
        (None, {"required": True}, "expires_in_hours_required"),
        ("bad", {}, "expires_in_hours_not_numeric"),
        (0, {"minimum": 0.0}, "expires_in_hours_out_of_range"),
        (9, {"minimum": 0.0, "maximum": 8.0}, "expires_in_hours_out_of_range"),
    ],
)
def test_validate_expires_in_hours_rejects_invalid_values(
    value: object,
    kwargs: dict[str, object],
    message: str,
) -> None:
    """Expiry validator should enforce required, numeric, and bounds rules."""
    with pytest.raises(ValidationError, match=message):
        validate_expires_in_hours(value, **kwargs)


def test_validate_gps_accuracy_value_handles_default_clamp_and_range_errors() -> None:
    """GPS accuracy should support defaults, clamping, and out-of-range failures."""
    assert validate_gps_accuracy_value("", default=5.0) == 5.0
    assert (
        validate_gps_accuracy_value(-2, min_value=0.0, max_value=10.0, clamp=True)
        == 0.0
    )
    assert (
        validate_gps_accuracy_value(50, min_value=0.0, max_value=10.0, clamp=True)
        == 10.0
    )

    with pytest.raises(ValidationError, match="gps_accuracy_required"):
        validate_gps_accuracy_value(None, required=True)

    with pytest.raises(ValidationError, match="gps_accuracy_not_numeric"):
        validate_gps_accuracy_value("oops")

    with pytest.raises(ValidationError, match="gps_accuracy_out_of_range"):
        validate_gps_accuracy_value(11, min_value=0.0, max_value=10.0)


def test_validate_int_and_float_range_cover_default_clamp_and_required_branches() -> (
    None
):
    """Range validators should exercise defaulting, clamp, and required branches."""
    assert (
        validate_int_range(None, field="interval", minimum=1, maximum=10, default=4)
        == 4
    )
    assert (
        validate_int_range(12, field="interval", minimum=1, maximum=10, clamp=True)
        == 10
    )
    assert validate_float_range(None, minimum=1.0, maximum=5.0, default=1.5) == 1.5
    assert validate_float_range(0.2, minimum=1.0, maximum=5.0, clamp=True) == 1.0

    with pytest.raises(ValidationError, match="value_required"):
        validate_int_range(None, field="interval", minimum=1, maximum=10, required=True)

    with pytest.raises(ValidationError, match="value_not_numeric"):
        validate_int_range("bad", field="interval", minimum=1, maximum=10)

    with pytest.raises(ValidationError, match="value_out_of_range"):
        validate_int_range(99, field="interval", minimum=1, maximum=10)

    with pytest.raises(ValidationError, match="Value is required"):
        validate_float_range(None, minimum=1.0, maximum=5.0, required=True)

    with pytest.raises(ValidationError, match="Must be numeric"):
        validate_float_range("bad", minimum=1.0, maximum=5.0)

    with pytest.raises(ValidationError, match="Maximum value is 5.0"):
        validate_float_range(8.0, minimum=1.0, maximum=5.0)
