"""Regression tests for PawControl validation helpers."""

from __future__ import annotations

import pytest
from custom_components.pawcontrol.validation import InputValidator, ValidationError


def test_validate_age_months_rejects_fractional_string() -> None:
  """Age validation should reject fractional month strings."""

  with pytest.raises(ValidationError) as err:
    InputValidator.validate_age_months("2.5", required=True)

  assert err.value.field == "age_months"
  assert err.value.constraint == "Must be a whole number"


def test_validate_weight_rejects_boolean() -> None:
  """Weight validation should reject boolean input."""

  with pytest.raises(ValidationError) as err:
    InputValidator.validate_weight(True)

  assert err.value.field == "weight"
  assert err.value.constraint == "Must be numeric"
