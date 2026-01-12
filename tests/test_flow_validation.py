"""Unit tests for flow validation helpers."""

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


def test_validate_dog_setup_input_success() -> None:
    user_input = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_WEIGHT: 20.5,
        CONF_DOG_SIZE: "medium",
        CONF_DOG_AGE: 4,
    }

    result = validate_dog_setup_input(
        user_input,
        existing_ids=set(),
        current_dog_count=0,
        max_dogs=3,
    )

    assert result[CONF_DOG_ID] == "buddy"
    assert result[CONF_DOG_NAME] == "Buddy"
    assert result[CONF_DOG_WEIGHT] == pytest.approx(20.5)
    assert result[CONF_DOG_SIZE] == "medium"
    assert result[CONF_DOG_AGE] == 4


def test_validate_dog_setup_input_errors() -> None:
    user_input = {
        CONF_DOG_ID: "1",
        CONF_DOG_NAME: "",
        CONF_DOG_WEIGHT: "bad",
        CONF_DOG_SIZE: "unknown",
        CONF_DOG_AGE: "bad",
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids={"buddy"},
            current_dog_count=2,
            max_dogs=2,
        )

    assert err.value.field_errors[CONF_DOG_ID] == "dog_id_too_short"
    assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_required"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "invalid_weight_format"
    assert err.value.field_errors[CONF_DOG_SIZE] == "invalid_dog_size"
    assert err.value.field_errors[CONF_DOG_AGE] == "invalid_age_format"
    assert "max_dogs_reached" in err.value.base_errors
