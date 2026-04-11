"""Coverage-focused tests for flow validation helpers."""

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
    assert _validate_dog_id("   ") == ("", "invalid_dog_id_format")
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


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        (CONF_DOG_WEIGHT, 0.1, "weight_out_of_range"),
        (CONF_DOG_AGE, 99, "age_out_of_range"),
    ],
)
def test_validate_dog_setup_input_rejects_out_of_range_values(
    field: str,
    value: float | int,
    expected: str,
) -> None:
    """Setup validation should reject numeric values outside configured bounds."""
    payload = _valid_dog_input()
    payload[field] = value

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            payload,
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=5,
        )

    assert err.value.field_errors[field] == expected


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


def test_validate_dog_setup_input_reports_weight_size_mismatch() -> None:
    """Setup validation should reject inconsistent weight/size combinations."""
    payload = {
        **_valid_dog_input(),
        CONF_DOG_WEIGHT: 70,
        CONF_DOG_SIZE: "small",
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            payload,
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=5,
        )

    assert err.value.field_errors[CONF_DOG_WEIGHT] == "weight_size_mismatch"


def test_validate_dog_setup_input_maps_invalid_breed_to_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup validation should map non-length breed errors to invalid_dog_breed."""

    def _raise_value_error(_: str) -> str:
        raise ValueError("invalid")

    monkeypatch.setattr(
        "custom_components.pawcontrol.flow_validation.HealthMetrics._validate_breed",
        _raise_value_error,
    )

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            {
                **_valid_dog_input(),
                CONF_DOG_BREED: "bad-breed",
            },
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=5,
        )

    assert err.value.field_errors[CONF_DOG_BREED] == "invalid_dog_breed"


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


def test_validate_dog_config_payload_propagates_update_field_errors() -> None:
    """Config payload validation should surface update validation errors."""
    with pytest.raises(FlowValidationError) as err:
        validate_dog_config_payload(
            {
                CONF_DOG_ID: "luna_cfg",
                CONF_DOG_NAME: "Milo",
            },
            existing_names={"milo"},
        )

    assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_already_exists"


def test_validate_dog_config_payload_omits_modules_when_absent() -> None:
    """Config payloads without module overrides should not emit module keys."""
    validated = validate_dog_config_payload({
        CONF_DOG_ID: "luna_nomod",
        CONF_DOG_NAME: "Luna NoMod",
    })

    assert validated[CONF_DOG_ID] == "luna_nomod"
    assert validated[CONF_DOG_NAME] == "Luna NoMod"
    assert CONF_MODULES not in validated


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


def test_validate_dog_update_input_reports_format_and_size_errors() -> None:
    """Update validation should report non-numeric input and invalid sizes."""
    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            {
                CONF_DOG_ID: "luna",
                CONF_DOG_NAME: "Luna",
                CONF_DOG_AGE: 4,
                CONF_DOG_WEIGHT: 20,
                CONF_DOG_SIZE: "medium",
            },
            {
                CONF_DOG_AGE: "not-a-number",
                CONF_DOG_WEIGHT: "not-a-number",
                CONF_DOG_SIZE: "not-a-size",
            },
        )

    assert err.value.field_errors[CONF_DOG_AGE] == "invalid_age_format"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "invalid_weight_format"
    assert err.value.field_errors[CONF_DOG_SIZE] == "invalid_dog_size"


def test_validate_dog_update_input_reports_breed_length_and_weight_range_errors() -> (
    None
):
    """Update validation should reject oversized breed names and out-of-range weight."""
    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            {
                CONF_DOG_ID: "luna",
                CONF_DOG_NAME: "Luna",
                CONF_DOG_WEIGHT: 20,
                CONF_DOG_SIZE: "medium",
            },
            {
                CONF_DOG_BREED: "x" * 101,
                CONF_DOG_WEIGHT: 500,
                CONF_DOG_SIZE: None,
            },
        )

    assert err.value.field_errors[CONF_DOG_BREED] == "breed_name_too_long"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "weight_out_of_range"


def test_validate_dog_update_input_maps_invalid_breed_type_to_field_error() -> None:
    """Update validation should map non-string breeds to invalid_dog_breed."""
    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            {
                CONF_DOG_ID: "luna",
                CONF_DOG_NAME: "Luna",
                CONF_DOG_WEIGHT: 20,
                CONF_DOG_SIZE: "medium",
            },
            {
                CONF_DOG_BREED: 123,
            },
        )

    assert err.value.field_errors[CONF_DOG_BREED] == "invalid_dog_breed"


def test_validate_dog_update_input_reports_weight_size_mismatch_for_valid_range() -> (
    None
):
    """Update validation should report mismatch when weight/size are both present."""
    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            {
                CONF_DOG_ID: "luna",
                CONF_DOG_NAME: "Luna",
                CONF_DOG_WEIGHT: 20,
                CONF_DOG_SIZE: "medium",
            },
            {
                CONF_DOG_WEIGHT: 70,
                CONF_DOG_SIZE: "small",
            },
        )

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


def test_validate_dog_import_input_treats_none_modules_as_empty_mapping() -> None:
    """Import validation should normalize explicit null modules to an empty mapping."""
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


def test_validate_dog_update_input_rejects_duplicate_name_when_names_are_provided() -> (
    None
):
    """Update validation should reject duplicate names from existing profile set."""
    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            {
                CONF_DOG_ID: "luna",
                CONF_DOG_NAME: "Luna",
                CONF_DOG_AGE: 4,
                CONF_DOG_WEIGHT: 20,
                CONF_DOG_SIZE: "medium",
            },
            {
                CONF_DOG_NAME: "Milo",
            },
            existing_names={"milo"},
        )

    assert err.value.field_errors[CONF_DOG_NAME] == "dog_name_already_exists"


def test_validate_dog_update_input_keeps_existing_optional_values() -> None:
    """Update validation should preserve optional values when they are omitted."""
    updated = validate_dog_update_input(
        {
            CONF_DOG_ID: "luna",
            CONF_DOG_NAME: "Luna",
            CONF_DOG_BREED: "Beagle",
            CONF_DOG_AGE: 5,
            CONF_DOG_WEIGHT: 20,
            CONF_DOG_SIZE: "medium",
        },
        {},
    )

    assert updated[CONF_DOG_BREED] == "Beagle"
    assert updated[CONF_DOG_AGE] == 5
    assert updated[CONF_DOG_WEIGHT] == 20.0
    assert updated[CONF_DOG_SIZE] == "medium"
