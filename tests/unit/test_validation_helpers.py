"""Unit tests for shared validation helpers."""

from datetime import time as dt_time
from enum import Enum
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.exceptions import (
    InvalidCoordinatesError,
    ValidationError,
)
from custom_components.pawcontrol.validation import (
    InputCoercionError,
    NotificationTargets,
    _is_empty,
    _parse_time_string,
    coerce_float,
    coerce_int,
    normalize_dog_id,
    validate_coordinate,
    validate_dog_name,
    validate_entity_id,
    validate_float_range,
    validate_gps_coordinates,
    validate_gps_source,
    validate_gps_update_interval,
    validate_interval,
    validate_name,
    validate_notification_targets,
    validate_notify_service,
    validate_sensor_entity_id,
    validate_time_window,
)


class _NotificationTarget(Enum):
    APP = "app"
    SMS = "sms"


class _StateMachine:
    def __init__(self, states: dict[str, object]) -> None:
        self._states = states

    def get(self, entity_id: str) -> object | None:
        return self._states.get(entity_id)


class _ServiceRegistry:
    def __init__(self, services: dict[str, dict[str, object]]) -> None:
        self._services = services

    def async_services(self) -> dict[str, dict[str, object]]:
        return self._services


def _build_hass(
    *,
    states: dict[str, object] | None = None,
    services: dict[str, dict[str, object]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        states=_StateMachine(states or {}),
        services=_ServiceRegistry(services or {}),
    )


def _build_state(state: str = "ok", **attributes: object) -> SimpleNamespace:
    return SimpleNamespace(state=state, attributes=attributes)


def test_validate_dog_name_trims_and_accepts() -> None:
    assert validate_dog_name("  Luna ") == "Luna"


def test_validate_dog_name_rejects_non_string() -> None:
    with pytest.raises(ValidationError) as err:
        validate_dog_name(123)

    assert err.value.field == "dog_name"


def test_validate_coordinate_bounds() -> None:
    assert validate_coordinate(
        52.52, field="latitude", minimum=-90.0, maximum=90.0
    ) == pytest.approx(52.52)
    assert (
        validate_coordinate(
            None,
            field="longitude",
            minimum=-180.0,
            maximum=180.0,
            required=False,
        )
        is None
    )

    with pytest.raises(ValidationError) as err:
        validate_coordinate(181, field="longitude", minimum=-180.0, maximum=180.0)

    assert err.value.field == "longitude"

    with pytest.raises(ValidationError) as not_numeric:
        validate_coordinate("bad", field="longitude", minimum=-180.0, maximum=180.0)

    assert not_numeric.value.constraint == "coordinate_not_numeric"


def test_validate_interval_clamps() -> None:
    assert (
        validate_interval(2, field="interval", minimum=5, maximum=10, clamp=True) == 5
    )
    assert (
        validate_interval(12, field="interval", minimum=5, maximum=10, clamp=True) == 10
    )


def test_validate_float_range_defaults_and_rejects() -> None:
    assert validate_float_range(
        None,
        field="accuracy",
        minimum=1.0,
        maximum=10.0,
        default=5.0,
    ) == pytest.approx(5.0)

    with pytest.raises(ValidationError):
        validate_float_range(
            "bad",
            field="accuracy",
            minimum=1.0,
            maximum=10.0,
        )


def test_normalize_dog_id_normalizes_and_handles_none() -> None:
    assert normalize_dog_id(None) == ""
    assert normalize_dog_id("  Luna Bella ") == "luna_bella"


def test_normalize_dog_id_rejects_non_strings() -> None:
    with pytest.raises(InputCoercionError) as err:
        normalize_dog_id(42)

    assert err.value.field == "dog_id"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", True),
        ("   ", True),
        (None, True),
        ("ready", False),
    ],
)
def test_is_empty(value: object, expected: bool) -> None:
    assert _is_empty(value) is expected


def test_parse_time_string_normalizes_multiple_input_types() -> None:
    assert _parse_time_string("start", None, "invalid") is None
    assert _parse_time_string("start", "  ", "invalid") is None
    assert _parse_time_string("start", dt_time(6, 30), "invalid") == "06:30:00"
    assert _parse_time_string("start", "06:30", "invalid") == "06:30:00"


@pytest.mark.parametrize("value", [42, "invalid-time"])
def test_parse_time_string_rejects_invalid_input(value: object) -> None:
    with pytest.raises(ValidationError) as err:
        _parse_time_string("start", value, "invalid_time")

    assert err.value.field == "start"


def test_coerce_float_handles_numeric_and_strips_strings() -> None:
    assert coerce_float("weight", 7) == pytest.approx(7.0)
    assert coerce_float("weight", " 7.5 ") == pytest.approx(7.5)


@pytest.mark.parametrize("value", [True, "", "dog", object()])
def test_coerce_float_rejects_non_numeric_values(value: object) -> None:
    with pytest.raises(InputCoercionError):
        coerce_float("weight", value)


def test_coerce_int_accepts_integer_like_inputs() -> None:
    assert coerce_int("count", 4) == 4
    assert coerce_int("count", 4.0) == 4
    assert coerce_int("count", " 4 ") == 4
    assert coerce_int("count", "4.0") == 4


@pytest.mark.parametrize("value", [True, 4.2, "", "4.2", "dog", object()])
def test_coerce_int_rejects_fractional_or_non_numeric(value: object) -> None:
    with pytest.raises(InputCoercionError):
        coerce_int("count", value)


def test_validate_notification_targets_normalizes_values_and_tracks_invalids() -> None:
    result = validate_notification_targets(
        ["app", _NotificationTarget.SMS, "app", "fax", 123],
        enum_type=_NotificationTarget,
    )

    assert result == NotificationTargets(
        targets=[_NotificationTarget.APP, _NotificationTarget.SMS],
        invalid=["fax", "123"],
    )

    assert validate_notification_targets(None, enum_type=_NotificationTarget) == (
        NotificationTargets(targets=[], invalid=[])
    )
    assert validate_notification_targets(
        "sms", enum_type=_NotificationTarget
    ).targets == [_NotificationTarget.SMS]
    assert validate_notification_targets(
        123, enum_type=_NotificationTarget
    ).invalid == ["123"]
    assert validate_notification_targets(
        [[]], enum_type=_NotificationTarget
    ).invalid == ["[]"]


def test_validate_time_window_uses_defaults_and_rejects_missing_values() -> None:
    assert validate_time_window(
        "06:00",
        None,
        start_field="quiet_start",
        end_field="quiet_end",
        default_end="22:00",
    ) == ("06:00:00", "22:00:00")

    with pytest.raises(ValidationError) as err:
        validate_time_window(
            None,
            None,
            start_field="quiet_start",
            end_field="quiet_end",
        )

    assert err.value.field == "quiet_start"
    assert err.value.constraint == "time_required"

    with pytest.raises(ValidationError) as missing_end:
        validate_time_window(
            "06:00",
            None,
            start_field="quiet_start",
            end_field="quiet_end",
        )

    assert missing_end.value.field == "quiet_end"


@pytest.mark.parametrize(
    ("value", "required", "constraint"),
    [
        (None, True, "dog_name_required"),
        (None, False, None),
        ("   ", False, None),
        ("x", True, "dog_name_too_short"),
        ("x" * 100, True, "dog_name_too_long"),
    ],
)
def test_validate_dog_name_handles_optional_and_boundary_cases(
    value: object, required: bool, constraint: str | None
) -> None:
    if constraint is None:
        assert validate_dog_name(value, required=required) is None
        return

    with pytest.raises(ValidationError) as err:
        validate_dog_name(value, required=required)

    assert err.value.constraint == constraint


def test_validate_name_trims_valid_values_and_rejects_invalid_input() -> None:
    assert validate_name("  Bella  ") == "Bella"

    with pytest.raises(ValidationError) as invalid_type:
        validate_name(42)
    assert invalid_type.value.constraint == "name_invalid_type"

    with pytest.raises(ValidationError) as required:
        validate_name("   ")
    assert required.value.constraint == "name_required"

    with pytest.raises(ValidationError) as too_short:
        validate_name("A")
    assert too_short.value.constraint == "name_too_short"

    with pytest.raises(ValidationError) as too_long:
        validate_name("x" * 100)
    assert too_long.value.constraint == "name_too_long"


def test_validate_gps_source_accepts_known_sources_and_rejects_missing_states() -> None:
    hass = _build_hass(
        states={
            "device_tracker.fido": _build_state("home"),
            "device_tracker.sleepy": _build_state("unavailable"),
        }
    )

    assert validate_gps_source(hass, "manual") == "manual"
    assert validate_gps_source(hass, "webhook") == "webhook"
    assert validate_gps_source(hass, "mqtt") == "mqtt"
    assert validate_gps_source(hass, " device_tracker.fido ") == "device_tracker.fido"

    with pytest.raises(ValidationError) as invalid_type:
        validate_gps_source(hass, 42)
    assert invalid_type.value.constraint == "gps_source_required"

    with pytest.raises(ValidationError) as blank:
        validate_gps_source(hass, "   ")
    assert blank.value.constraint == "gps_source_required"

    with pytest.raises(ValidationError) as missing:
        validate_gps_source(hass, "device_tracker.ghost")
    assert missing.value.constraint == "gps_source_not_found"

    with pytest.raises(ValidationError) as unavailable:
        validate_gps_source(hass, "device_tracker.sleepy")
    assert unavailable.value.constraint == "gps_source_unavailable"

    with pytest.raises(ValidationError) as disabled_manual:
        validate_gps_source(hass, "manual", allow_manual=False)
    assert disabled_manual.value.constraint == "gps_source_not_found"


def test_validate_notify_service_requires_notify_domain_and_registered_service() -> (
    None
):
    hass = _build_hass(services={"notify": {"mobile_app_phone": object()}})

    assert validate_notify_service(hass, " notify.mobile_app_phone ") == (
        "notify.mobile_app_phone"
    )

    with pytest.raises(ValidationError) as invalid_type:
        validate_notify_service(hass, 42)
    assert invalid_type.value.constraint == "notify_service_invalid"

    with pytest.raises(ValidationError) as blank:
        validate_notify_service(hass, "   ")
    assert blank.value.constraint == "notify_service_invalid"

    with pytest.raises(ValidationError) as invalid_format:
        validate_notify_service(hass, "mobile_app_phone")
    assert invalid_format.value.constraint == "notify_service_invalid"

    with pytest.raises(ValidationError) as missing:
        validate_notify_service(hass, "notify.living_room")
    assert missing.value.constraint == "notify_service_not_found"


def test_validate_entity_id_enforces_domain_object_structure() -> None:
    assert validate_entity_id("sensor.back_door") == "sensor.back_door"

    for value in (
        None,
        123,
        "sensor",
        "sensor.",
        ".missing",
        "Sensor.bad",
        "sensor.bad-id",
    ):
        with pytest.raises(ValidationError):
            validate_entity_id(value)


def test_validate_sensor_entity_id_checks_state_domain_and_device_class() -> None:
    hass = _build_hass(
        states={
            "binary_sensor.door": _build_state("on", device_class="door"),
            "sensor.temperature": _build_state("20", device_class="temperature"),
            "binary_sensor.offline": _build_state("unknown", device_class="door"),
        }
    )

    assert (
        validate_sensor_entity_id(
            hass,
            " binary_sensor.door ",
            field="door_sensor",
            required=True,
            domain="binary_sensor",
            device_classes={"door"},
        )
        == "binary_sensor.door"
    )

    assert validate_sensor_entity_id(hass, None, field="door_sensor") is None
    assert validate_sensor_entity_id(hass, " ", field="door_sensor") is None

    with pytest.raises(ValidationError) as required:
        validate_sensor_entity_id(hass, " ", field="door_sensor", required=True)
    assert required.value.constraint == "sensor_required"

    for value in (
        123,
        "sensor.temperature",
        "binary_sensor.offline",
        "binary_sensor.door",
    ):
        kwargs = {
            "field": "door_sensor",
            "domain": "binary_sensor",
            "device_classes": {"motion"},
        }
        if value == "sensor.temperature" or value == "binary_sensor.offline":
            kwargs = {"field": "door_sensor", "domain": "binary_sensor"}
        with pytest.raises(ValidationError) as err:
            validate_sensor_entity_id(hass, value, **kwargs)
        assert err.value.constraint == "sensor_not_found"


@pytest.mark.parametrize(
    ("value", "kwargs", "expected"),
    [
        (None, {"default": 8}, 8),
        (None, {"clamp": True}, 5),
        (7, {}, 7),
    ],
)
def test_validate_interval_returns_defaults_and_valid_values(
    value: object, kwargs: dict[str, object], expected: int
) -> None:
    assert (
        validate_interval(
            value,
            field="interval",
            minimum=5,
            maximum=10,
            **kwargs,
        )
        == expected
    )


def test_validate_interval_rejects_required_invalid_and_out_of_range_values() -> None:
    with pytest.raises(ValidationError) as required:
        validate_interval(
            None,
            field="interval",
            minimum=5,
            maximum=10,
            required=True,
        )
    assert required.value.constraint == "Interval is required"

    with pytest.raises(ValidationError) as not_numeric:
        validate_interval("bad", field="interval", minimum=5, maximum=10)
    assert not_numeric.value.constraint == "Must be a whole number"

    with pytest.raises(ValidationError) as too_small:
        validate_interval(3, field="interval", minimum=5, maximum=10)
    assert too_small.value.constraint == "Minimum interval is 5"

    with pytest.raises(ValidationError) as too_large:
        validate_interval(12, field="interval", minimum=5, maximum=10)
    assert too_large.value.constraint == "Maximum interval is 10"


def test_validate_gps_coordinates_handles_fast_path_and_wraps_validation_errors() -> (
    None
):
    assert validate_gps_coordinates(52, -7) == (52.0, -7.0)

    with pytest.raises(InvalidCoordinatesError):
        validate_gps_coordinates(True, 10)


def test_validate_gps_update_interval_delegates_to_gps_interval_constraints() -> None:
    assert (
        validate_gps_update_interval(
            15,
            minimum=10,
            maximum=30,
        )
        == 15
    )

    with pytest.raises(ValidationError) as required:
        validate_gps_update_interval(
            None,
            minimum=10,
            maximum=30,
            required=True,
        )
    assert required.value.constraint == "gps_update_interval_required"
