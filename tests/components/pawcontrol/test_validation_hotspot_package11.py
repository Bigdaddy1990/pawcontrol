"""Targeted branch coverage for validation helper edge paths."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
    clamp_float_range,
    clamp_int_range,
    validate_entity_id,
    validate_gps_source,
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


@pytest.mark.parametrize(
    ("notify_service", "message"),
    [
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
