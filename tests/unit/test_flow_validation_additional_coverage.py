"""Additional branch coverage tests for flow validation helpers."""

import pytest

from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_MODULES,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
)
from custom_components.pawcontrol.exceptions import FlowValidationError, ValidationError


def test_validate_dog_id_reports_invalid_format_when_normalizer_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalization failures should map to the flow-level format error."""
    from custom_components.pawcontrol import flow_validation

    def _raise_input_coercion(raw_id: object) -> str:
        raise flow_validation.InputCoercionError("dog_id", raw_id, "boom")

    monkeypatch.setattr(flow_validation, "normalize_dog_id", _raise_input_coercion)

    dog_id, error = flow_validation._validate_dog_id(object())

    assert dog_id == ""
    assert error == "invalid_dog_id_format"


def test_validate_dog_setup_input_uses_empty_name_when_validator_returns_non_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-string validator return should be normalized to an empty name."""
    from custom_components.pawcontrol import flow_validation

    monkeypatch.setattr(
        flow_validation,
        "validate_unique_dog_name",
        lambda *args, **kwargs: 42,
    )

    result = flow_validation.validate_dog_setup_input(
        {
            CONF_DOG_ID: "buddy",
            CONF_DOG_NAME: "Buddy",
            CONF_DOG_WEIGHT: 20.0,
            CONF_DOG_SIZE: "medium",
            CONF_DOG_AGE: 3,
        },
        existing_ids=set(),
        existing_names=set(),
        current_dog_count=0,
        max_dogs=3,
    )

    assert result[CONF_DOG_NAME] == ""


def test_validate_dog_config_payload_skips_update_validation_when_id_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ID validation already failed, update validation should not run."""
    from custom_components.pawcontrol import flow_validation

    called = False

    def _mark_called(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {CONF_DOG_ID: "ignored", CONF_DOG_NAME: "ignored"}

    monkeypatch.setattr(flow_validation, "validate_dog_update_input", _mark_called)

    with pytest.raises(FlowValidationError) as err:
        flow_validation.validate_dog_config_payload(
            {
                CONF_DOG_ID: "a",  # too short -> field error path
                CONF_DOG_NAME: "Buddy",
            },
            existing_ids=set(),
        )

    assert err.value.field_errors[CONF_DOG_ID] == "dog_id_too_short"
    assert called is False


def test_validate_dog_setup_input_reports_age_and_weight_out_of_range() -> None:
    """Out-of-range primitives must surface dedicated field errors."""
    from custom_components.pawcontrol import flow_validation

    with pytest.raises(FlowValidationError) as err:
        flow_validation.validate_dog_setup_input(
            {
                CONF_DOG_ID: "buddy",
                CONF_DOG_NAME: "Buddy",
                CONF_DOG_WEIGHT: 0.1,
                CONF_DOG_SIZE: "medium",
                CONF_DOG_AGE: 99,
            },
            existing_ids=set(),
            current_dog_count=0,
            max_dogs=2,
        )

    assert err.value.field_errors[CONF_DOG_WEIGHT] == "weight_out_of_range"
    assert err.value.field_errors[CONF_DOG_AGE] == "age_out_of_range"


def test_validate_dog_update_input_maps_format_and_range_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Update validation should map coercion and range failures predictably."""
    from custom_components.pawcontrol import flow_validation

    def _breed_too_long(_raw_breed: object) -> str:
        raise ValidationError(CONF_DOG_BREED, "x" * 101, "Breed name too long")

    monkeypatch.setattr(flow_validation, "_validate_breed", _breed_too_long)

    with pytest.raises(FlowValidationError) as err:
        flow_validation.validate_dog_update_input(
            {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"},
            {
                CONF_DOG_BREED: "x" * 101,
                CONF_DOG_AGE: "old",
                CONF_DOG_WEIGHT: "heavy",
                CONF_DOG_SIZE: "not-a-size",
            },
        )

    assert err.value.field_errors[CONF_DOG_BREED] == "breed_name_too_long"
    assert err.value.field_errors[CONF_DOG_AGE] == "invalid_age_format"
    assert err.value.field_errors[CONF_DOG_WEIGHT] == "invalid_weight_format"
    assert err.value.field_errors[CONF_DOG_SIZE] == "invalid_dog_size"

    with pytest.raises(FlowValidationError) as range_err:
        flow_validation.validate_dog_update_input(
            {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"},
            {
                CONF_DOG_WEIGHT: 500.0,
                CONF_DOG_SIZE: None,
            },
        )

    assert range_err.value.field_errors[CONF_DOG_WEIGHT] == "weight_out_of_range"


def test_validate_dog_import_input_normalizes_none_modules() -> None:
    """YAML imports may omit module maps by explicitly passing null."""
    from custom_components.pawcontrol import flow_validation

    validated = flow_validation.validate_dog_import_input(
        {
            CONF_DOG_ID: "buddy",
            CONF_DOG_NAME: "Buddy",
            CONF_DOG_WEIGHT: 20.0,
            CONF_DOG_SIZE: "medium",
            CONF_DOG_AGE: 4,
            CONF_MODULES: None,
        },
        existing_ids=set(),
        current_dog_count=0,
        max_dogs=3,
    )

    assert validated[CONF_MODULES] == {}
