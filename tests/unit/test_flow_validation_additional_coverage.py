"""Additional branch coverage tests for flow validation helpers."""

import pytest

from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
)
from custom_components.pawcontrol.exceptions import FlowValidationError


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
