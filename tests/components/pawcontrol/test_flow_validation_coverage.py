"""Coverage-focused tests for flow validation helpers."""

from __future__ import annotations

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
    _coerce_float,
    _coerce_int,
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
        CONF_DOG_ID: "luna_1",
        CONF_DOG_NAME: "Luna",
        CONF_DOG_WEIGHT: 20,
        CONF_DOG_SIZE: "medium",
        CONF_DOG_AGE: 3,
    }


def test_validate_dog_id_and_coercion_helpers_cover_error_paths() -> None:
    """Dog id and coercion helpers should map low-level coercion errors."""
    assert _validate_dog_id(123) == ("", "invalid_dog_id_format")
    assert _validate_dog_id("a") == ("a", "dog_id_too_short")
    assert _validate_dog_id("x" * 31) == ("x" * 31, "dog_id_too_long")
    assert _validate_dog_id("bad!id") == ("bad!id", "invalid_dog_id_format")
    assert _validate_dog_id("luna", existing_ids={"luna"}) == (
        "luna",
        "dog_id_already_exists",
    )

    with pytest.raises(ValidationError, match="Must be a whole number"):
        _coerce_int("age", "bad")

    with pytest.raises(ValidationError, match="Must be numeric"):
        _coerce_float("weight", object())


def test_validate_breed_handles_type_length_and_health_metric_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Breed validation should enforce type and translate calculator errors."""
    assert _validate_breed(None) is None
    assert _validate_breed("   ") is None

    with pytest.raises(ValidationError, match="Must be a string"):
        _validate_breed(10)

    with pytest.raises(ValidationError, match="Breed name too long"):
        _validate_breed("x" * 101)

    def _raise_value_error(_: str) -> str:
        raise ValueError("invalid")

    monkeypatch.setattr(
        "custom_components.pawcontrol.flow_validation.HealthMetrics._validate_breed",
        _raise_value_error,
    )
    with pytest.raises(ValidationError, match="Breed contains invalid characters"):
        _validate_breed("luna!")


def test_validate_dog_setup_input_raises_combined_flow_errors() -> None:
    """Setup validation should collect field and base errors."""
    user_input = {
        CONF_DOG_ID: "luna",
        CONF_DOG_NAME: "Luna",
        CONF_DOG_WEIGHT: "bad",
        CONF_DOG_AGE: "oops",
        CONF_DOG_SIZE: "tiny",
        CONF_DOG_BREED: "x" * 101,
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids={"luna"},
            existing_names={"luna"},
            current_dog_count=5,
            max_dogs=5,
        )

    assert err.value.base_errors == ["max_dogs_reached"]
    assert err.value.field_errors[CONF_DOG_ID] == "dog_id_already_exists"
    assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_already_exists"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "invalid_weight_format"
    assert err.value.field_errors[CONF_DOG_AGE] == "invalid_age_format"
    assert err.value.field_errors[CONF_DOG_SIZE] == "invalid_dog_size"
    assert err.value.field_errors[CONF_DOG_BREED] == "breed_name_too_long"


def test_validate_dog_setup_input_success_includes_optional_breed() -> None:
    """Successful setup validation should return normalized payload."""
    validated = validate_dog_setup_input(
        {
            **_valid_dog_input(),
            CONF_DOG_BREED: "Labrador",
        },
        existing_ids=set(),
        existing_names=set(),
        current_dog_count=0,
        max_dogs=10,
    )

    assert validated["dog_id"] == "luna_1"
    assert validated["dog_name"] == "Luna"
    assert validated["dog_size"] == "medium"
    assert validated["dog_breed"] == "Labrador"


def test_validate_dog_config_payload_reports_base_and_modules_errors() -> None:
    """Config payload validation should enforce max dog count and module mapping."""
    with pytest.raises(FlowValidationError) as err:
        validate_dog_config_payload(
            {
                CONF_DOG_ID: "luna",
                CONF_DOG_NAME: "Luna",
                CONF_MODULES: "not-a-map",
            },
            current_dog_count=None,
            max_dogs=0,
        )

    assert err.value.base_errors == ["max_dogs_reached"]
    assert err.value.field_errors[CONF_MODULES] == "dog_invalid_modules"


def test_validate_dog_config_payload_normalizes_optional_fields_and_modules() -> None:
    """Config payload should remove empty optional fields and coerce module booleans."""
    payload = {
        CONF_DOG_ID: "luna_two",
        CONF_DOG_NAME: "Luna Two",
        CONF_DOG_AGE: None,
        CONF_DOG_WEIGHT: 12,
        CONF_DOG_SIZE: "small",
        CONF_DOG_BREED: "   ",
        CONF_MODULES: {
            "gps": 1,
            "feeding": 0,
        },
    }

    validated = validate_dog_config_payload(payload)

    assert validated[CONF_DOG_ID] == "luna_two"
    assert validated[CONF_DOG_NAME] == "Luna Two"
    assert CONF_DOG_BREED not in validated
    assert CONF_DOG_AGE not in validated
    assert validated[CONF_MODULES] == {"gps": True, "feeding": False}


def test_validate_dog_update_input_removes_nullable_fields_and_validates_ranges() -> (
    None
):
    """Update validation should prune nullable values and report range failures."""
    current = {
        CONF_DOG_ID: "luna",
        CONF_DOG_NAME: "Luna",
        CONF_DOG_BREED: "Lab",
        CONF_DOG_AGE: 5,
        CONF_DOG_WEIGHT: 12,
        CONF_DOG_SIZE: "small",
    }

    cleaned = validate_dog_update_input(
        current,
        {
            CONF_DOG_BREED: None,
            CONF_DOG_AGE: None,
            CONF_DOG_WEIGHT: None,
            CONF_DOG_SIZE: " ",
        },
    )
    assert CONF_DOG_BREED not in cleaned
    assert CONF_DOG_AGE not in cleaned
    assert CONF_DOG_WEIGHT not in cleaned
    assert CONF_DOG_SIZE not in cleaned

    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            current,
            {
                CONF_DOG_AGE: 100,
                CONF_DOG_WEIGHT: 2,
                CONF_DOG_SIZE: "large",
            },
        )
    assert err.value.field_errors[CONF_DOG_AGE] == "age_out_of_range"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "weight_size_mismatch"


def test_validate_dog_import_input_rejects_unexpected_and_invalid_modules() -> None:
    """Import validation should reject unknown keys and non-mapping modules."""
    with pytest.raises(ValidationError, match="Unexpected keys"):
        validate_dog_import_input(
            {
                **_valid_dog_input(),
                "extra": True,
            },
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=2,
        )

    with pytest.raises(ValidationError, match="Modules must be a mapping"):
        validate_dog_import_input(
            {
                **_valid_dog_input(),
                CONF_MODULES: "bad",
            },
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=2,
        )


def test_validate_dog_import_input_success_and_payload_validity_helper() -> None:
    """Import validation should normalize modules and payload validity helper result."""
    imported = validate_dog_import_input(
        {
            **_valid_dog_input(),
            CONF_DOG_BREED: "Beagle",
            CONF_MODULES: {"feeding": True},
        },
        existing_ids=set(),
        existing_names=set(),
        current_dog_count=0,
        max_dogs=2,
    )

    assert imported[CONF_DOG_BREED] == "Beagle"
    assert imported[CONF_MODULES] == {"feeding": True}

    assert is_dog_config_payload_valid(imported) is True
    assert is_dog_config_payload_valid({CONF_DOG_ID: "?"}) is False


def test_validate_dog_setup_input_reports_range_and_hint_errors() -> None:
    """Setup validation should report range, mismatch, and invalid breed hint errors."""
    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            {
                CONF_DOG_ID: "   ",
                CONF_DOG_NAME: "Nova",
                CONF_DOG_WEIGHT: 5_000,
                CONF_DOG_SIZE: "small",
                CONF_DOG_AGE: 100,
                CONF_DOG_BREED: "@@@",
            },
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=10,
        )

    assert err.value.field_errors[CONF_DOG_ID] == "invalid_dog_id_format"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "weight_out_of_range"
    assert err.value.field_errors[CONF_DOG_AGE] == "age_out_of_range"
    assert err.value.field_errors[CONF_DOG_BREED] == "invalid_dog_breed"

    with pytest.raises(FlowValidationError) as mismatch_err:
        validate_dog_setup_input(
            {
                CONF_DOG_ID: "nova_1",
                CONF_DOG_NAME: "Nova",
                CONF_DOG_WEIGHT: 45,
                CONF_DOG_SIZE: "small",
                CONF_DOG_AGE: 4,
            },
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=10,
        )

    assert mismatch_err.value.field_errors[CONF_DOG_WEIGHT] == "weight_size_mismatch"


def test_validate_dog_config_payload_propagates_update_errors_and_removes_modules() -> None:
    """Config payload validation should merge update errors and prune absent modules."""
    with pytest.raises(FlowValidationError) as err:
        validate_dog_config_payload(
            {
                CONF_DOG_ID: "nova_1",
                CONF_DOG_NAME: " ",
                CONF_DOG_AGE: "oops",
            },
        )

    assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_required"
    assert err.value.field_errors[CONF_DOG_AGE] == "invalid_age_format"

    validated = validate_dog_config_payload(
        {
            CONF_DOG_ID: "nova_1",
            CONF_DOG_NAME: "Nova",
        },
    )

    assert CONF_MODULES not in validated


def test_validate_dog_update_input_covers_all_field_error_paths() -> None:
    """Update validation should emit explicit field errors for invalid updates."""
    current = {
        CONF_DOG_ID: "luna",
        CONF_DOG_NAME: "Luna",
        CONF_DOG_BREED: "Lab",
        CONF_DOG_AGE: 5,
        CONF_DOG_WEIGHT: 15,
        CONF_DOG_SIZE: "medium",
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            current,
            {
                CONF_DOG_NAME: " ",
                CONF_DOG_BREED: "@",
                CONF_DOG_AGE: "abc",
                CONF_DOG_WEIGHT: "abc",
                CONF_DOG_SIZE: "tiny",
            },
        )

    assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_required"
    assert err.value.field_errors[CONF_DOG_BREED] == "invalid_dog_breed"
    assert err.value.field_errors[CONF_DOG_AGE] == "invalid_age_format"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "invalid_weight_format"
    assert err.value.field_errors[CONF_DOG_SIZE] == "invalid_dog_size"

    cleaned = validate_dog_update_input(
        current,
        {
            CONF_DOG_AGE: 3,
            CONF_DOG_WEIGHT: 20,
        },
    )
    assert cleaned[CONF_DOG_AGE] == 3
    assert cleaned[CONF_DOG_WEIGHT] == 20

    with pytest.raises(FlowValidationError) as range_err:
        validate_dog_update_input(
            current,
            {
                CONF_DOG_AGE: 4,
                CONF_DOG_WEIGHT: 5_000,
                CONF_DOG_SIZE: None,
            },
        )

    assert range_err.value.field_errors[CONF_DOG_WEIGHT] == "weight_out_of_range"

    with pytest.raises(FlowValidationError) as breed_err:
        validate_dog_update_input(
            current,
            {
                CONF_DOG_BREED: "x" * 101,
            },
        )
    assert breed_err.value.field_errors[CONF_DOG_BREED] == "breed_name_too_long"


def test_validate_dog_import_input_allows_none_modules_mapping() -> None:
    """Import validation should treat null modules payloads as an empty mapping."""
    imported = validate_dog_import_input(
        {
            **_valid_dog_input(),
            CONF_MODULES: None,
        },
        existing_ids=set(),
        existing_names=set(),
        current_dog_count=0,
        max_dogs=2,
    )

    assert imported[CONF_MODULES] == {}
