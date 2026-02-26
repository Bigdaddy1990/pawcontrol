"""Unit tests for flow validation normalization helpers."""

import pytest

from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_MODULES,
)
from custom_components.pawcontrol.exceptions import FlowValidationError, ValidationError
from custom_components.pawcontrol.flow_validation import (
    _validate_breed,
    _validate_dog_id,
    is_dog_config_payload_valid,
    validate_dog_config_payload,
    validate_dog_import_input,
    validate_dog_setup_input,
    validate_dog_update_input,
)


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


def test_validate_dog_setup_rejects_invalid_weight() -> None:
    user_input = _valid_dog_input()
    user_input[CONF_DOG_WEIGHT] = "heavy"

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.field_errors[CONF_DOG_WEIGHT] == "invalid_weight_format"


def test_validate_dog_setup_rejects_duplicate_name() -> None:
    user_input = _valid_dog_input()
    user_input[CONF_DOG_NAME] = "Buddy"

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids=set(),
            existing_names={"buddy"},
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_already_exists"


@pytest.mark.parametrize(
    ("dog_id", "expected_error"),
    [
        ("a", "dog_id_too_short"),
        ("x" * 31, "dog_id_too_long"),
        ("buddy!", "invalid_dog_id_format"),
    ],
)
def test_validate_dog_id_reports_length_and_pattern_errors(
    dog_id: str,
    expected_error: str,
) -> None:
    normalized, error = _validate_dog_id(dog_id)

    assert normalized
    assert error == expected_error


def test_validate_dog_id_rejects_duplicate_values() -> None:
    normalized, error = _validate_dog_id("buddy", existing_ids={"buddy"})

    assert normalized == "buddy"
    assert error == "dog_id_already_exists"


@pytest.mark.parametrize(
    "breed",
    [123, "x" * 101, "a"],
)
def test_validate_breed_rejects_invalid_values(breed: object) -> None:
    with pytest.raises(ValidationError):
        _validate_breed(breed)


def test_validate_dog_config_payload_coerces_optional_fields() -> None:
    payload = {
        CONF_DOG_ID: "Buddy",
        CONF_DOG_NAME: " Buddy ",
        CONF_DOG_WEIGHT: "22.5",
        CONF_DOG_SIZE: "large",
        CONF_DOG_AGE: "5",
        CONF_MODULES: {"gps": "yes", "health": 0},
    }

    result = validate_dog_config_payload(payload, existing_ids=set())

    assert result[CONF_DOG_ID] == "buddy"
    assert result[CONF_DOG_NAME] == "Buddy"
    assert result[CONF_DOG_WEIGHT] == 22.5
    assert result[CONF_DOG_AGE] == 5
    modules = result[CONF_MODULES]
    assert modules["gps"] is True
    assert modules["health"] is False


def test_validate_dog_config_payload_rejects_invalid_modules() -> None:
    payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_MODULES: ["invalid"],
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_config_payload(payload, existing_ids=set())

    assert err.value.field_errors[CONF_MODULES] == "dog_invalid_modules"


def test_is_dog_config_payload_valid_false_for_invalid_payload() -> None:
    assert (
        is_dog_config_payload_valid({CONF_DOG_ID: "", CONF_DOG_NAME: "Buddy"}) is False
    )


def test_validate_dog_config_payload_reports_max_dogs_reached() -> None:
    payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_config_payload(payload, current_dog_count=1, max_dogs=1)

    assert "max_dogs_reached" in err.value.base_errors


def test_validate_dog_config_payload_defaults_count_when_only_max_set() -> None:
    payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
    }

    result = validate_dog_config_payload(payload, max_dogs=2)

    assert result[CONF_DOG_ID] == "buddy"


def test_validate_dog_config_payload_removes_optional_fields_when_null() -> None:
    payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_BREED: None,
        CONF_DOG_AGE: None,
        CONF_DOG_WEIGHT: None,
        CONF_DOG_SIZE: None,
    }

    result = validate_dog_config_payload(payload)

    assert CONF_DOG_BREED not in result
    assert CONF_DOG_AGE not in result
    assert CONF_DOG_WEIGHT not in result
    assert CONF_DOG_SIZE not in result
    assert CONF_MODULES not in result


def test_validate_dog_import_input_rejects_unexpected_keys() -> None:
    payload = {
        **_valid_dog_input(),
        "unexpected": True,
    }

    with pytest.raises(ValidationError) as err:
        validate_dog_import_input(
            payload,
            existing_ids=set(),
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.constraint == "Unexpected keys in dog configuration"


def test_validate_dog_import_input_rejects_non_mapping_modules() -> None:
    payload = {
        **_valid_dog_input(),
        CONF_MODULES: ["gps"],
    }

    with pytest.raises(ValidationError) as err:
        validate_dog_import_input(
            payload,
            existing_ids=set(),
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.constraint == "Modules must be a mapping"


def test_validate_dog_import_input_accepts_none_modules() -> None:
    payload = {
        **_valid_dog_input(),
        CONF_MODULES: None,
    }

    result = validate_dog_import_input(
        payload,
        existing_ids=set(),
        current_dog_count=0,
        max_dogs=3,
    )

    assert result[CONF_MODULES] == {}


def test_validate_dog_import_input_normalizes_payload() -> None:
    payload = {
        CONF_DOG_ID: "  Buddy Pup  ",
        CONF_DOG_NAME: " Buddy  ",
        CONF_DOG_WEIGHT: "9.5",
        CONF_DOG_SIZE: "small",
        CONF_DOG_AGE: "2",
        CONF_DOG_BREED: " corgi ",
        CONF_MODULES: {"gps": 1, "feeding": 0},
    }

    result = validate_dog_import_input(
        payload,
        existing_ids=set(),
        current_dog_count=0,
        max_dogs=3,
    )

    assert result[CONF_DOG_ID] == "buddy_pup"
    assert result[CONF_DOG_NAME] == "Buddy"
    assert result[CONF_DOG_WEIGHT] == 9.5
    assert result[CONF_DOG_AGE] == 2
    assert result[CONF_DOG_BREED] == "corgi"
    assert result[CONF_MODULES]["gps"] is True
    assert result[CONF_MODULES]["feeding"] is False


def test_validate_dog_setup_input_collects_field_and_base_errors() -> None:
    user_input = {
        CONF_DOG_ID: "a",
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_SIZE: "mega",
        CONF_DOG_WEIGHT: "heavy",
        CONF_DOG_AGE: "old",
        CONF_DOG_BREED: 7,
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids=set(),
            existing_names={"buddy"},
            current_dog_count=2,
            max_dogs=2,
        )

    assert err.value.field_errors[CONF_DOG_ID] == "dog_id_too_short"
    assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_already_exists"
    assert err.value.field_errors[CONF_DOG_SIZE] == "invalid_dog_size"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "invalid_weight_format"
    assert err.value.field_errors[CONF_DOG_AGE] == "invalid_age_format"
    assert err.value.field_errors[CONF_DOG_BREED] == "invalid_dog_breed"
    assert "max_dogs_reached" in err.value.base_errors


def test_validate_dog_setup_input_reports_range_and_mismatch_errors() -> None:
    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            {
                CONF_DOG_ID: "buddy",
                CONF_DOG_NAME: "Buddy",
                CONF_DOG_SIZE: "small",
                CONF_DOG_WEIGHT: 40,
                CONF_DOG_AGE: 99,
                CONF_DOG_BREED: "x" * 101,
            },
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.field_errors[CONF_DOG_WEIGHT] == "weight_size_mismatch"
    assert err.value.field_errors[CONF_DOG_AGE] == "age_out_of_range"
    assert err.value.field_errors[CONF_DOG_BREED] == "breed_name_too_long"


def test_validate_dog_setup_input_reports_weight_out_of_range() -> None:
    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            {
                CONF_DOG_ID: "buddy",
                CONF_DOG_NAME: "Buddy",
                CONF_DOG_SIZE: "medium",
                CONF_DOG_WEIGHT: 999,
                CONF_DOG_AGE: 3,
            },
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.field_errors[CONF_DOG_WEIGHT] == "weight_out_of_range"


def test_validate_dog_update_input_covers_optional_field_paths() -> None:
    current_dog = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_BREED: "corgi",
        CONF_DOG_AGE: 5,
        CONF_DOG_WEIGHT: 12.0,
        CONF_DOG_SIZE: "medium",
    }

    result = validate_dog_update_input(
        current_dog,
        {
            CONF_DOG_NAME: "Buddy Prime",
            CONF_DOG_BREED: "   ",
            CONF_DOG_AGE: None,
            CONF_DOG_WEIGHT: None,
            CONF_DOG_SIZE: "   ",
        },
    )

    assert result[CONF_DOG_NAME] == "Buddy Prime"
    assert CONF_DOG_BREED not in result
    assert CONF_DOG_AGE not in result
    assert CONF_DOG_WEIGHT not in result
    assert CONF_DOG_SIZE not in result


def test_validate_dog_update_input_reports_multiple_errors() -> None:
    current_dog = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            current_dog,
            {
                CONF_DOG_NAME: "Buddy",
                CONF_DOG_BREED: 42,
                CONF_DOG_AGE: "old",
                CONF_DOG_WEIGHT: "heavy",
                CONF_DOG_SIZE: "invalid-size",
            },
            existing_names={"buddy"},
        )

    assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_already_exists"
    assert err.value.field_errors[CONF_DOG_BREED] == "invalid_dog_breed"
    assert err.value.field_errors[CONF_DOG_AGE] == "invalid_age_format"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "invalid_weight_format"
    assert err.value.field_errors[CONF_DOG_SIZE] == "invalid_dog_size"


def test_validate_dog_update_input_reports_weight_range_and_size_mismatch() -> None:
    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"},
            {
                CONF_DOG_WEIGHT: 0.1,
                CONF_DOG_SIZE: "large",
            },
        )

    assert err.value.field_errors[CONF_DOG_WEIGHT] == "weight_size_mismatch"


def test_validate_dog_update_input_reports_weight_range_without_size() -> None:
    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"},
            {
                CONF_DOG_WEIGHT: 0.1,
                CONF_DOG_SIZE: None,
            },
        )

    assert err.value.field_errors[CONF_DOG_WEIGHT] == "weight_out_of_range"


def test_validate_dog_update_input_reports_breed_and_age_range_errors() -> None:
    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"},
            {
                CONF_DOG_BREED: "x" * 101,
                CONF_DOG_AGE: 99,
            },
        )

    assert err.value.field_errors[CONF_DOG_BREED] == "breed_name_too_long"
    assert err.value.field_errors[CONF_DOG_AGE] == "age_out_of_range"


def test_validate_dog_config_payload_surfaces_update_validation_errors() -> None:
    with pytest.raises(FlowValidationError) as err:
        validate_dog_config_payload(
            {
                CONF_DOG_ID: "buddy",
                CONF_DOG_NAME: "Buddy",
                CONF_DOG_BREED: "x" * 101,
            },
            existing_ids=set(),
        )

    assert err.value.field_errors[CONF_DOG_BREED] == "breed_name_too_long"
