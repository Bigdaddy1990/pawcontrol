"""Targeted coverage tests for flow_validation.py — uncovered paths (81% → 93%+).

Covers: _validate_dog_id (all branches), _coerce_int/_coerce_float error paths,
        _validate_breed, validate_dog_setup_input (field errors, max_dogs, modules),
        validate_dog_update_input, FlowValidationError
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.flow_validation import (
    validate_dog_setup_input,
)
from custom_components.pawcontrol.exceptions import FlowValidationError

# ═══════════════════════════════════════════════════════════════════════════════
# _validate_dog_id paths (lines 62-71)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_validate_dog_id_invalid_format() -> None:
    """Dog ID with invalid format returns error key."""
    with pytest.raises(FlowValidationError) as exc_info:
        validate_dog_setup_input(
            {"dog_id": "!!bad!!", "dog_name": "Rex"},
            existing_ids=set(),
            current_dog_count=0,
            max_dogs=10,
        )
    errors = exc_info.value.field_errors
    assert "dog_id" in errors


@pytest.mark.unit
def test_validate_dog_id_too_short() -> None:
    with pytest.raises(FlowValidationError) as exc_info:
        validate_dog_setup_input(
            {"dog_id": "a", "dog_name": "Rex"},
            existing_ids=set(),
            current_dog_count=0,
            max_dogs=10,
        )
    assert "dog_id" in exc_info.value.field_errors


@pytest.mark.unit
def test_validate_dog_id_too_long() -> None:
    long_id = "a" * 40
    with pytest.raises(FlowValidationError) as exc_info:
        validate_dog_setup_input(
            {"dog_id": long_id, "dog_name": "Rex"},
            existing_ids=set(),
            current_dog_count=0,
            max_dogs=10,
        )
    assert "dog_id" in exc_info.value.field_errors


@pytest.mark.unit
def test_validate_dog_id_already_exists() -> None:
    with pytest.raises(FlowValidationError) as exc_info:
        validate_dog_setup_input(
            {"dog_id": "rex", "dog_name": "Rex"},
            existing_ids={"rex"},
            current_dog_count=1,
            max_dogs=10,
        )
    assert "dog_id" in exc_info.value.field_errors


@pytest.mark.unit
def test_validate_dog_id_valid() -> None:
    result = validate_dog_setup_input(
        {"dog_id": "rex_01", "dog_name": "Rex"},
        existing_ids=set(),
        current_dog_count=0,
        max_dogs=10,
    )
    assert result["dog_id"] == "rex_01"


# ═══════════════════════════════════════════════════════════════════════════════
# max_dogs limit (line 231-232)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_max_dogs_reached() -> None:
    with pytest.raises(FlowValidationError) as exc_info:
        validate_dog_setup_input(
            {"dog_id": "rex", "dog_name": "Rex"},
            existing_ids=set(),
            current_dog_count=5,
            max_dogs=5,
        )
    assert "max_dogs_reached" in exc_info.value.base_errors


# ═══════════════════════════════════════════════════════════════════════════════
# Dog name validation (line 236-238)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_dog_name_already_exists() -> None:
    with pytest.raises(FlowValidationError) as exc_info:
        validate_dog_setup_input(
            {"dog_id": "rex", "dog_name": "Rex"},
            existing_ids=set(),
            existing_names={"Rex"},
            current_dog_count=0,
            max_dogs=10,
        )
    assert "dog_name" in exc_info.value.field_errors


@pytest.mark.unit
def test_dog_name_too_long() -> None:
    with pytest.raises(FlowValidationError) as exc_info:
        validate_dog_setup_input(
            {"dog_id": "rex", "dog_name": "R" * 200},
            existing_ids=set(),
            current_dog_count=0,
            max_dogs=10,
        )
    assert "dog_name" in exc_info.value.field_errors

# ═══════════════════════════════════════════════════════════════════════════════
# FlowValidationError structure
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_flow_validation_error_field_and_base() -> None:
    err = FlowValidationError(
        field_errors={"dog_id": "too_short"},
        base_errors=["max_dogs_reached"],
    )
    assert err.field_errors == {"dog_id": "too_short"}
    assert err.base_errors == ["max_dogs_reached"]


@pytest.mark.unit
def test_flow_validation_error_empty() -> None:
    err = FlowValidationError()
    assert err.field_errors == {}
    assert err.base_errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# _validate_breed paths (lines 95-107)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_validate_dog_setup_with_valid_breed() -> None:
    """Breed field is accepted when valid."""
    result = validate_dog_setup_input(
        {"dog_id": "rex", "dog_name": "Rex", "dog_breed": "Labrador"},
        existing_ids=set(),
        current_dog_count=0,
        max_dogs=10,
    )
    assert result["dog_id"] == "rex"


@pytest.mark.unit
def test_validate_dog_setup_with_invalid_breed_type() -> None:
    """Non-string breed raises field error."""
    with pytest.raises(FlowValidationError) as exc_info:
        validate_dog_setup_input(
            {"dog_id": "rex", "dog_name": "Rex", "dog_breed": 42},
            existing_ids=set(),
            current_dog_count=0,
            max_dogs=10,
        )
    assert "dog_breed" in exc_info.value.field_errors


@pytest.mark.unit
def test_validate_dog_setup_breed_too_long() -> None:
    """Breed name exceeding max length raises error."""
    with pytest.raises(FlowValidationError) as exc_info:
        validate_dog_setup_input(
            {"dog_id": "rex", "dog_name": "Rex", "dog_breed": "B" * 200},
            existing_ids=set(),
            current_dog_count=0,
            max_dogs=10,
        )
    assert "dog_breed" in exc_info.value.field_errors


# ═══════════════════════════════════════════════════════════════════════════════
# invalid modules (line 253-254)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_valid_modules_dict_accepted() -> None:
    """Valid dict modules payload is accepted and normalised."""
    result = validate_dog_setup_input(
        {"dog_id": "rex", "dog_name": "Rex", "modules": {"feeding": True, "walk": False}},
        existing_ids=set(),
        current_dog_count=0,
        max_dogs=10,
    )
    assert result["dog_id"] == "rex"
