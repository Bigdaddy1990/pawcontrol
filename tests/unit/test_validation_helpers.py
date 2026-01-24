"""Unit tests for shared validation helpers."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
  validate_coordinate,
  validate_dog_name,
  validate_float_range,
  validate_interval,
)


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

  with pytest.raises(ValidationError) as err:
    validate_coordinate(181, field="longitude", minimum=-180.0, maximum=180.0)

  assert err.value.field == "longitude"


def test_validate_interval_clamps() -> None:
  assert validate_interval(2, field="interval", minimum=5, maximum=10, clamp=True) == 5
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
