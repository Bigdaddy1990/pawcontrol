"""Unit tests for flow validation normalization helpers."""

import pytest

from custom_components.pawcontrol.const import (
  CONF_DOG_AGE,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
  CONF_MODULES,
)
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.flow_validation import (
  validate_dog_config_payload,
  validate_dog_setup_input,
)


def _valid_dog_input() -> dict[str, object]:
  return {  # noqa: E111
    CONF_DOG_ID: "buddy",
    CONF_DOG_NAME: "Buddy",
    CONF_DOG_WEIGHT: 20.0,
    CONF_DOG_SIZE: "medium",
    CONF_DOG_AGE: 4,
  }


def test_validate_dog_setup_normalizes_dog_id() -> None:
  user_input = _valid_dog_input()  # noqa: E111
  user_input[CONF_DOG_ID] = "  Big Pup "  # noqa: E111

  result = validate_dog_setup_input(  # noqa: E111
    user_input,
    existing_ids=set(),
    existing_names=set(),
    current_dog_count=0,
    max_dogs=3,
  )

  assert result[CONF_DOG_ID] == "big_pup"  # noqa: E111


def test_validate_dog_setup_rejects_non_string_dog_id() -> None:
  user_input = _valid_dog_input()  # noqa: E111
  user_input[CONF_DOG_ID] = 123  # noqa: E111

  with pytest.raises(FlowValidationError) as err:  # noqa: E111
    validate_dog_setup_input(
      user_input,
      existing_ids=set(),
      existing_names=set(),
      current_dog_count=0,
      max_dogs=3,
    )

  assert err.value.field_errors[CONF_DOG_ID] == "invalid_dog_id_format"  # noqa: E111


def test_validate_dog_setup_rejects_invalid_weight() -> None:
  user_input = _valid_dog_input()  # noqa: E111
  user_input[CONF_DOG_WEIGHT] = "heavy"  # noqa: E111

  with pytest.raises(FlowValidationError) as err:  # noqa: E111
    validate_dog_setup_input(
      user_input,
      existing_ids=set(),
      existing_names=set(),
      current_dog_count=0,
      max_dogs=3,
    )

  assert err.value.field_errors[CONF_DOG_WEIGHT] == "invalid_weight_format"  # noqa: E111


def test_validate_dog_setup_rejects_duplicate_name() -> None:
  user_input = _valid_dog_input()  # noqa: E111
  user_input[CONF_DOG_NAME] = "Buddy"  # noqa: E111

  with pytest.raises(FlowValidationError) as err:  # noqa: E111
    validate_dog_setup_input(
      user_input,
      existing_ids=set(),
      existing_names={"buddy"},
      current_dog_count=0,
      max_dogs=3,
    )

  assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_already_exists"  # noqa: E111


def test_validate_dog_config_payload_coerces_optional_fields() -> None:
  payload = {  # noqa: E111
    CONF_DOG_ID: "Buddy",
    CONF_DOG_NAME: " Buddy ",
    CONF_DOG_WEIGHT: "22.5",
    CONF_DOG_SIZE: "large",
    CONF_DOG_AGE: "5",
    CONF_MODULES: {"gps": "yes", "health": 0},
  }

  result = validate_dog_config_payload(payload, existing_ids=set())  # noqa: E111

  assert result[CONF_DOG_ID] == "buddy"  # noqa: E111
  assert result[CONF_DOG_NAME] == "Buddy"  # noqa: E111
  assert result[CONF_DOG_WEIGHT] == 22.5  # noqa: E111
  assert result[CONF_DOG_AGE] == 5  # noqa: E111
  modules = result[CONF_MODULES]  # noqa: E111
  assert modules["gps"] is True  # noqa: E111
  assert modules["health"] is False  # noqa: E111


def test_validate_dog_config_payload_rejects_invalid_modules() -> None:
  payload = {  # noqa: E111
    CONF_DOG_ID: "buddy",
    CONF_DOG_NAME: "Buddy",
    CONF_MODULES: ["invalid"],
  }

  with pytest.raises(FlowValidationError) as err:  # noqa: E111
    validate_dog_config_payload(payload, existing_ids=set())

  assert err.value.field_errors[CONF_MODULES] == "dog_invalid_modules"  # noqa: E111
