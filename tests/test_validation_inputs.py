"""Unit tests for PawControl input validation helpers."""

from __future__ import annotations

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
validate_json_schema_payload = schemas.validate_json_schema_payload
GPS_DOG_CONFIG_JSON_SCHEMA = schemas.GPS_DOG_CONFIG_JSON_SCHEMA
GPS_OPTIONS_JSON_SCHEMA = schemas.GPS_OPTIONS_JSON_SCHEMA
validate_sensor_entity_id = validation.validate_sensor_entity_id


class _FakeStates(dict[str, SimpleNamespace]):
  """Minimal state registry for validation tests."""


class _FakeHomeAssistant:
  """Minimal Home Assistant stub for validation tests."""

  def __init__(self, states: _FakeStates) -> None:
    self.states = states


class _NotificationChannel(Enum):
  MOBILE = "mobile"
  EMAIL = "email"


def test_validate_gps_coordinates_success() -> None:
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
def test_validate_gps_coordinates_invalid(
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
def test_validate_geofence_radius_bounds(radius: float, field: str) -> None:
  assert InputValidator.validate_geofence_radius(50) == pytest.approx(50)

  with pytest.raises(ValidationError) as err:
    InputValidator.validate_geofence_radius(radius)

  assert err.value.field == field


def test_validate_gps_json_schema_accepts_config() -> None:
  payload = {
    "gps_source": "manual",
    "gps_update_interval": 60,
    "gps_accuracy_filter": 25.0,
    "enable_geofencing": True,
    "home_zone_radius": 50.0,
  }

  assert validate_json_schema_payload(payload, GPS_DOG_CONFIG_JSON_SCHEMA) == []


def test_validate_gps_json_schema_rejects_invalid_payload() -> None:
  payload = {
    "gps_source": "",
    "gps_update_interval": 2,
  }

  violations = validate_json_schema_payload(payload, GPS_OPTIONS_JSON_SCHEMA)
  assert violations


def test_normalize_dog_id_strips_and_normalizes() -> None:
  assert normalize_dog_id("  My Pup  ") == "my_pup"


def test_normalize_dog_id_rejects_non_string() -> None:
  with pytest.raises(InputCoercionError):
    normalize_dog_id(123)


def test_coerce_helpers_reject_invalid_types() -> None:
  assert coerce_int("age", "7") == 7
  assert coerce_float("weight", "2.5") == pytest.approx(2.5)

  with pytest.raises(InputCoercionError):
    coerce_int("age", 2.5)

  with pytest.raises(InputCoercionError):
    coerce_float("weight", "")


def test_validate_sensor_entity_id_accepts_valid_entity() -> None:
  hass = _FakeHomeAssistant(
    _FakeStates(
      {
        "binary_sensor.front_door": SimpleNamespace(
          state="on",
          attributes={"device_class": "door"},
        )
      }
    )
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


def test_validate_sensor_entity_id_rejects_wrong_device_class() -> None:
  hass = _FakeHomeAssistant(
    _FakeStates(
      {
        "binary_sensor.front_door": SimpleNamespace(
          state="on",
          attributes={"device_class": "motion"},
        )
      }
    )
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


def test_validate_dog_name_rejects_invalid_types() -> None:
  with pytest.raises(ValidationError) as err:
    validate_dog_name(123)

  assert err.value.constraint == "dog_name_invalid"


def test_validate_dog_name_enforces_length() -> None:
  with pytest.raises(ValidationError) as err:
    validate_dog_name(" ")

  assert err.value.constraint == "dog_name_required"


def test_validate_gps_interval_rejects_non_numeric() -> None:
  with pytest.raises(ValidationError) as err:
    validate_gps_interval(
      "fast",
      minimum=5,
      maximum=600,
      required=True,
    )

  assert err.value.constraint == "gps_update_interval_not_numeric"


def test_validate_notification_targets_normalises_values() -> None:
  result = validate_notification_targets(
    ["mobile", "pager", _NotificationChannel.EMAIL, "mobile"],
    enum_type=_NotificationChannel,
  )

  assert result.targets == [
    _NotificationChannel.MOBILE,
    _NotificationChannel.EMAIL,
  ]
  assert result.invalid == ["pager"]


def test_validate_time_window_rejects_invalid_time() -> None:
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
