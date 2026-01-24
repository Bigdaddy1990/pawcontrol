"""Unit tests for flow validation normalization helpers."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.const import (
  CONF_DOG_AGE,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
)
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.flow_validation import validate_dog_setup_input


def _valid_dog_input() -> dict[str, object]:
  return {
    CONF_DOG_ID: "buddy",
    CONF_DOG_NAME: "Buddy",
    CONF_DOG_WEIGHT: 20.0,
    CONF_DOG_SIZE: "medium",
    CONF_DOG_AGE: 4,
  }


def test_validate_dog_setup_normalizes_dog_id() -> None:
  user_input = _valid_dog_input()
  user_input[CONF_DOG_ID] = "  Big Pup "

  result = validate_dog_setup_input(
    user_input,
    existing_ids=set(),
    existing_names=set(),
    current_dog_count=0,
    max_dogs=3,
  )

  assert result[CONF_DOG_ID] == "big_pup"


def test_validate_dog_setup_rejects_non_string_dog_id() -> None:
  user_input = _valid_dog_input()
  user_input[CONF_DOG_ID] = 123

  with pytest.raises(FlowValidationError) as err:
    validate_dog_setup_input(
      user_input,
      existing_ids=set(),
      existing_names=set(),
      current_dog_count=0,
      max_dogs=3,
    )

  assert err.value.field_errors[CONF_DOG_ID] == "invalid_dog_id_format"
