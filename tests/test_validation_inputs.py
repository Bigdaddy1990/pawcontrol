"""Unit tests for PawControl input validation helpers."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.helpers import ensure_package, install_homeassistant_stubs, load_module

PROJECT_ROOT = Path(__file__).resolve().parents[1]


install_homeassistant_stubs()
ensure_package("custom_components", PROJECT_ROOT / "custom_components")
ensure_package(
    "custom_components.pawcontrol",
    PROJECT_ROOT / "custom_components" / "pawcontrol",
)

validation = load_module(
    "custom_components.pawcontrol.validation",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "validation.py",
)
schemas = load_module(
    "custom_components.pawcontrol.schemas",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "schemas.py",
)

InputValidator = validation.InputValidator
InputCoercionError = validation.InputCoercionError
ValidationError = validation.ValidationError
coerce_float = validation.coerce_float
coerce_int = validation.coerce_int
normalize_dog_id = validation.normalize_dog_id
validate_dog_name = validation.validate_dog_name
validate_gps_interval = validation.validate_gps_interval
validate_notification_targets = validation.validate_notification_targets
validate_time_window = validation.validate_time_window
validate_entity_id = validation.validate_entity_id
validate_coordinate = validation.validate_coordinate
validate_expires_in_hours = validation.validate_expires_in_hours
validate_int_range = validation.validate_int_range
validate_float_range = validation.validate_float_range
clamp_int_range = validation.clamp_int_range
clamp_float_range = validation.clamp_float_range
validate_json_schema_payload = schemas.validate_json_schema_payload
GPS_DOG_CONFIG_JSON_SCHEMA = schemas.GPS_DOG_CONFIG_JSON_SCHEMA
GPS_OPTIONS_JSON_SCHEMA = schemas.GPS_OPTIONS_JSON_SCHEMA
validate_sensor_entity_id = validation.validate_sensor_entity_id


class _FakeStates(dict[str, SimpleNamespace]):
    """Minimal state registry for validation tests."""


@dataclass(slots=True)
class _FakeHomeAssistant:
    """Minimal Home Assistant stub for validation tests."""

    states: _FakeStates


class _NotificationChannel(Enum):
    MOBILE = "mobile"
    EMAIL = "email"


def test_validate_gps_coordinates_success() -> None:  # noqa: D103
    latitude, longitude = InputValidator.validate_gps_coordinates(
        52.52,
        13.405,
    )
    assert latitude == pytest.approx(52.52)
    assert longitude == pytest.approx(13.405)


@pytest.mark.parametrize(
    ("latitude", "longitude", "field"),
    [
        (None, 13.4, "latitude"),
        (91, 13.4, "latitude"),
        (52.52, None, "longitude"),
        (52.52, 181, "longitude"),
    ],
)
def test_validate_gps_coordinates_invalid(  # noqa: D103
    latitude: float | None,
    longitude: float | None,
    field: str,
) -> None:
    with pytest.raises(ValidationError) as err:
        InputValidator.validate_gps_coordinates(latitude, longitude)

    assert err.value.field == field


@pytest.mark.parametrize(
    ("radius", "field"),
    [
        (0, "radius"),
        (5001, "radius"),
    ],
)
def test_validate_geofence_radius_bounds(radius: float, field: str) -> None:  # noqa: D103
    assert InputValidator.validate_geofence_radius(50) == pytest.approx(50)

    with pytest.raises(ValidationError) as err:
        InputValidator.validate_geofence_radius(radius)

    assert err.value.field == field


def test_validate_gps_json_schema_accepts_config() -> None:  # noqa: D103
    payload = {
        "gps_source": "manual",
        "gps_update_interval": 60,
        "gps_accuracy_filter": 25.0,
        "enable_geofencing": True,
        "home_zone_radius": 50.0,
    }

    assert validate_json_schema_payload(payload, GPS_DOG_CONFIG_JSON_SCHEMA) == []


def test_validate_gps_json_schema_rejects_invalid_payload() -> None:  # noqa: D103
    payload = {
        "gps_source": "",
        "gps_update_interval": 2,
    }

    violations = validate_json_schema_payload(payload, GPS_OPTIONS_JSON_SCHEMA)
    assert violations


def test_normalize_dog_id_strips_and_normalizes() -> None:  # noqa: D103
    assert normalize_dog_id("  My Pup  ") == "my_pup"


def test_normalize_dog_id_returns_empty_for_none() -> None:  # noqa: D103
    assert normalize_dog_id(None) == ""


def test_normalize_dog_id_rejects_non_string() -> None:  # noqa: D103
    with pytest.raises(InputCoercionError):
        normalize_dog_id(123)


def test_coerce_helpers_reject_invalid_types() -> None:  # noqa: D103
    assert coerce_int("age", "7") == 7
    assert coerce_float("weight", "2.5") == pytest.approx(2.5)
    assert coerce_int("age", "7.0") == 7

    with pytest.raises(InputCoercionError):
        coerce_int("age", 2.5)

    with pytest.raises(InputCoercionError):
        coerce_float("weight", "")

    with pytest.raises(InputCoercionError):
        coerce_float("weight", object())


@pytest.mark.parametrize(
    ("helper", "field", "value"),
    [
        (coerce_int, "age", True),
        (coerce_float, "weight", False),
    ],
)
def test_coerce_helpers_reject_boolean_values(  # noqa: D103
    helper: Callable[[str, object], object],
    field: str,
    value: bool,
) -> None:
    with pytest.raises(InputCoercionError):
        helper(field, value)


def test_validate_sensor_entity_id_accepts_valid_entity() -> None:  # noqa: D103
    hass = _FakeHomeAssistant(
        _FakeStates({
            "binary_sensor.front_door": SimpleNamespace(
                state="on",
                attributes={"device_class": "door"},
            )
        })
    )

    assert (
        validate_sensor_entity_id(
            hass,
            " binary_sensor.front_door ",
            field="door_sensor",
            domain="binary_sensor",
            device_classes={"door"},
            not_found_constraint="door_sensor_not_found",
        )
        == "binary_sensor.front_door"
    )


def test_validate_sensor_entity_id_rejects_wrong_device_class() -> None:  # noqa: D103
    hass = _FakeHomeAssistant(
        _FakeStates({
            "binary_sensor.front_door": SimpleNamespace(
                state="on",
                attributes={"device_class": "motion"},
            )
        })
    )

    with pytest.raises(ValidationError) as err:
        validate_sensor_entity_id(
            hass,
            "binary_sensor.front_door",
            field="door_sensor",
            domain="binary_sensor",
            device_classes={"door"},
            not_found_constraint="door_sensor_not_found",
        )

    assert err.value.constraint == "door_sensor_not_found"


def test_validate_dog_name_rejects_invalid_types() -> None:  # noqa: D103
    with pytest.raises(ValidationError) as err:
        validate_dog_name(123)

    assert err.value.constraint == "dog_name_invalid"


def test_validate_dog_name_enforces_length() -> None:  # noqa: D103
    with pytest.raises(ValidationError) as err:
        validate_dog_name(" ")

    assert err.value.constraint == "dog_name_required"


def test_validate_gps_interval_rejects_non_numeric() -> None:  # noqa: D103
    with pytest.raises(ValidationError) as err:
        validate_gps_interval(
            "fast",
            minimum=5,
            maximum=600,
            required=True,
        )

    assert err.value.constraint == "gps_update_interval_not_numeric"


def test_validate_notification_targets_normalises_values() -> None:  # noqa: D103
    result = validate_notification_targets(
        ["mobile", "pager", _NotificationChannel.EMAIL, "mobile"],
        enum_type=_NotificationChannel,
    )

    assert result.targets == [
        _NotificationChannel.MOBILE,
        _NotificationChannel.EMAIL,
    ]
    assert result.invalid == ["pager"]


def test_validate_notification_targets_accepts_single_values() -> None:  # noqa: D103
    single_string = validate_notification_targets(
        "mobile",
        enum_type=_NotificationChannel,
    )
    single_enum = validate_notification_targets(
        _NotificationChannel.EMAIL,
        enum_type=_NotificationChannel,
    )
    missing_targets = validate_notification_targets(
        None, enum_type=_NotificationChannel
    )

    assert single_string.targets == [_NotificationChannel.MOBILE]
    assert single_string.invalid == []
    assert single_enum.targets == [_NotificationChannel.EMAIL]
    assert single_enum.invalid == []
    assert missing_targets.targets == []
    assert missing_targets.invalid == []


def test_validate_time_window_rejects_invalid_time() -> None:  # noqa: D103
    with pytest.raises(ValidationError) as err:
        validate_time_window(
            "25:61",
            "07:00:00",
            start_field="quiet_start",
            end_field="quiet_end",
            default_start="22:00:00",
            default_end="07:00:00",
            invalid_start_constraint="quiet_start_invalid",
            invalid_end_constraint="quiet_end_invalid",
        )

    assert err.value.constraint == "quiet_start_invalid"


def test_validate_entity_id_accepts_trimmed_candidate() -> None:  # noqa: D103
    assert validate_entity_id("  sensor.garden_temperature  ") == (
        "sensor.garden_temperature"
    )


@pytest.mark.parametrize("entity_id", [None, "sensor", "sensor.", ".name", "1foo.bar"])
def test_validate_entity_id_rejects_invalid_shapes(entity_id: object) -> None:  # noqa: D103
    with pytest.raises(ValidationError):
        validate_entity_id(entity_id)


def test_validate_coordinate_handles_required_and_optional_paths() -> None:  # noqa: D103
    assert validate_coordinate("52.2", field="latitude", minimum=-90, maximum=90) == (
        pytest.approx(52.2)
    )
    assert (
        validate_coordinate(
            None, field="latitude", minimum=-90, maximum=90, required=False
        )
        is None
    )

    with pytest.raises(ValidationError) as err:
        validate_coordinate(
            "not-a-number",
            field="latitude",
            minimum=-90,
            maximum=90,
        )
    assert err.value.constraint == "coordinate_not_numeric"

    with pytest.raises(ValidationError) as range_err:
        validate_coordinate("100", field="latitude", minimum=-90, maximum=90)
    assert range_err.value.constraint == "coordinate_out_of_range"


def test_validate_expires_in_hours_supports_required_and_bounds() -> None:  # noqa: D103
    assert validate_expires_in_hours("1.5", minimum=0.0, maximum=2.0) == pytest.approx(
        1.5
    )
    assert validate_expires_in_hours("", required=False) is None

    with pytest.raises(ValidationError) as required_err:
        validate_expires_in_hours(None, required=True)
    assert required_err.value.constraint == "expires_in_hours_required"

    with pytest.raises(ValidationError) as numeric_err:
        validate_expires_in_hours("tomorrow")
    assert numeric_err.value.constraint == "expires_in_hours_not_numeric"

    with pytest.raises(ValidationError) as range_err:
        validate_expires_in_hours(0, minimum=0.0)
    assert range_err.value.constraint == "expires_in_hours_out_of_range"


def test_validate_int_and_float_range_and_clamp_helpers() -> None:  # noqa: D103
    assert (
        validate_int_range(
            "5",
            field="interval",
            minimum=1,
            maximum=10,
            required=True,
        )
        == 5
    )
    assert validate_float_range(
        "1.25",
        minimum=0.5,
        maximum=2.0,
        field="temperature",
        required=True,
    ) == pytest.approx(1.25)
    assert (
        clamp_int_range(
            "200",
            field="interval",
            minimum=1,
            maximum=120,
            default=30,
        )
        == 120
    )
    assert clamp_float_range(
        "9.5",
        field="threshold",
        minimum=0.0,
        maximum=5.0,
        default=2.0,
    ) == pytest.approx(5.0)

    with pytest.raises(ValidationError) as int_required_err:
        validate_int_range(
            None,
            field="interval",
            minimum=1,
            maximum=10,
            required=True,
            required_constraint="interval_required",
        )
    assert int_required_err.value.constraint == "interval_required"
