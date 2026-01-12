"""Shared validation helpers for config and options flows."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .config_flow_base import DOG_ID_PATTERN
from .const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    DOG_SIZES,
    MAX_DOG_AGE,
    MAX_DOG_NAME_LENGTH,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_NAME_LENGTH,
    MIN_DOG_WEIGHT,
)
from .exceptions import FlowValidationError, ValidationError
from .health_calculator import HealthMetrics
from .types import DogConfigData, DogSetupStepInput, validate_dog_weight_for_size

MAX_BREED_NAME_LENGTH = 100


def _coerce_int(field: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValidationError(field, value, "Must be a whole number")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValidationError(field, value, "Must be a whole number")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValidationError(field, value, "Must be a whole number")
        try:
            return int(stripped)
        except ValueError as err:
            raise ValidationError(field, value, "Must be a whole number") from err
    raise ValidationError(field, value, "Must be a whole number")


def _coerce_float(field: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValidationError(field, value, "Must be numeric")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValidationError(field, value, "Must be numeric")
        try:
            return float(stripped)
        except ValueError as err:
            raise ValidationError(field, value, "Must be numeric") from err
    raise ValidationError(field, value, "Must be numeric")


def _validate_breed(raw_breed: Any) -> str | None:
    if raw_breed is None:
        return None
    if not isinstance(raw_breed, str):
        raise ValidationError(CONF_DOG_BREED, raw_breed, "Must be a string")
    breed = raw_breed.strip()
    if not breed:
        return None
    if len(breed) > MAX_BREED_NAME_LENGTH:
        raise ValidationError(CONF_DOG_BREED, breed, "Breed name too long")
    try:
        return HealthMetrics._validate_breed(breed)
    except (TypeError, ValueError) as err:
        raise ValidationError(
            CONF_DOG_BREED,
            breed,
            "Breed contains invalid characters",
        ) from err


def validate_dog_setup_input(
    user_input: Mapping[str, Any],
    *,
    existing_ids: set[str],
    existing_names: set[str] | None = None,
    current_dog_count: int,
    max_dogs: int,
) -> DogSetupStepInput:
    """Validate and normalize dog setup input for flows."""

    field_errors: dict[str, str] = {}
    base_errors: list[str] = []

    raw_id = user_input.get(CONF_DOG_ID, "")
    dog_id_raw = str(raw_id).strip().lower() if raw_id is not None else ""
    dog_id = re.sub(r"\s+", "_", dog_id_raw)
    if not dog_id:
        field_errors[CONF_DOG_ID] = "invalid_dog_id_format"
    elif len(dog_id) < 2:
        field_errors[CONF_DOG_ID] = "dog_id_too_short"
    elif len(dog_id) > 30:
        field_errors[CONF_DOG_ID] = "dog_id_too_long"
    elif not DOG_ID_PATTERN.match(dog_id):
        field_errors[CONF_DOG_ID] = "invalid_dog_id_format"
    elif dog_id in existing_ids:
        field_errors[CONF_DOG_ID] = "dog_id_already_exists"

    raw_name = user_input.get(CONF_DOG_NAME, "")
    dog_name = str(raw_name).strip() if raw_name is not None else ""
    if not dog_name:
        field_errors[CONF_DOG_NAME] = "dog_name_required"
    elif len(dog_name) < MIN_DOG_NAME_LENGTH:
        field_errors[CONF_DOG_NAME] = "dog_name_too_short"
    elif len(dog_name) > MAX_DOG_NAME_LENGTH:
        field_errors[CONF_DOG_NAME] = "dog_name_too_long"
    else:
        normalized_names = {
            name.strip().lower()
            for name in (existing_names or set())
            if isinstance(name, str) and name.strip()
        }
        if dog_name.lower() in normalized_names:
            field_errors[CONF_DOG_NAME] = "dog_name_already_exists"

    if current_dog_count >= max_dogs:
        base_errors.append("max_dogs_reached")

    raw_size = user_input.get(CONF_DOG_SIZE, "medium")
    dog_size = str(raw_size).strip() if raw_size is not None else "medium"
    if dog_size not in DOG_SIZES:
        field_errors[CONF_DOG_SIZE] = "invalid_dog_size"

    raw_weight = user_input.get(CONF_DOG_WEIGHT, 20.0)
    try:
        dog_weight = _coerce_float(CONF_DOG_WEIGHT, raw_weight)
    except ValidationError:
        field_errors[CONF_DOG_WEIGHT] = "invalid_weight_format"
        dog_weight = 20.0
    else:
        if dog_weight < MIN_DOG_WEIGHT or dog_weight > MAX_DOG_WEIGHT:
            field_errors[CONF_DOG_WEIGHT] = "weight_out_of_range"
        elif dog_size in DOG_SIZES and not validate_dog_weight_for_size(
            dog_weight, dog_size
        ):
            field_errors[CONF_DOG_WEIGHT] = "weight_size_mismatch"

    raw_age = user_input.get(CONF_DOG_AGE, 3)
    try:
        dog_age = _coerce_int(CONF_DOG_AGE, raw_age)
    except ValidationError:
        field_errors[CONF_DOG_AGE] = "invalid_age_format"
        dog_age = 3
    else:
        if dog_age < MIN_DOG_AGE or dog_age > MAX_DOG_AGE:
            field_errors[CONF_DOG_AGE] = "age_out_of_range"

    try:
        dog_breed = _validate_breed(user_input.get(CONF_DOG_BREED))
    except ValidationError as err:
        if err.constraint == "Breed name too long":
            field_errors[CONF_DOG_BREED] = "breed_name_too_long"
        else:
            field_errors[CONF_DOG_BREED] = "invalid_dog_breed"
        dog_breed = None

    if field_errors or base_errors:
        raise FlowValidationError(field_errors=field_errors, base_errors=base_errors)

    validated: DogSetupStepInput = {
        "dog_id": dog_id,
        "dog_name": dog_name,
        "dog_weight": dog_weight,
        "dog_size": dog_size,
        "dog_age": dog_age,
    }
    if dog_breed is not None:
        validated["dog_breed"] = dog_breed
    return validated


def validate_dog_update_input(
    current_dog: DogConfigData,
    user_input: Mapping[str, Any],
    *,
    existing_names: set[str] | None = None,
) -> DogConfigData:
    """Validate updates for an existing dog configuration."""

    field_errors: dict[str, str] = {}

    candidate: DogConfigData = dict(current_dog)

    raw_name = user_input.get(CONF_DOG_NAME, candidate.get(CONF_DOG_NAME, ""))
    dog_name = str(raw_name).strip() if raw_name is not None else ""
    if not dog_name:
        field_errors[CONF_DOG_NAME] = "dog_name_required"
    elif len(dog_name) < MIN_DOG_NAME_LENGTH:
        field_errors[CONF_DOG_NAME] = "dog_name_too_short"
    elif len(dog_name) > MAX_DOG_NAME_LENGTH:
        field_errors[CONF_DOG_NAME] = "dog_name_too_long"
    else:
        normalized_names = {
            name.strip().lower()
            for name in (existing_names or set())
            if isinstance(name, str) and name.strip()
        }
        if dog_name.lower() in normalized_names:
            field_errors[CONF_DOG_NAME] = "dog_name_already_exists"
        candidate[CONF_DOG_NAME] = dog_name

    raw_breed = user_input.get(CONF_DOG_BREED, candidate.get(CONF_DOG_BREED))
    if raw_breed is None:
        candidate.pop(CONF_DOG_BREED, None)
    else:
        try:
            normalized_breed = _validate_breed(raw_breed)
        except ValidationError as err:
            if err.constraint == "Breed name too long":
                field_errors[CONF_DOG_BREED] = "breed_name_too_long"
            else:
                field_errors[CONF_DOG_BREED] = "invalid_dog_breed"
        else:
            if normalized_breed is None:
                candidate.pop(CONF_DOG_BREED, None)
            else:
                candidate[CONF_DOG_BREED] = normalized_breed

    raw_age = user_input.get(CONF_DOG_AGE, candidate.get(CONF_DOG_AGE))
    if raw_age is None:
        candidate.pop(CONF_DOG_AGE, None)
        dog_age = None
    else:
        try:
            dog_age = _coerce_int(CONF_DOG_AGE, raw_age)
        except ValidationError:
            field_errors[CONF_DOG_AGE] = "invalid_age_format"
            dog_age = None
        else:
            if dog_age < MIN_DOG_AGE or dog_age > MAX_DOG_AGE:
                field_errors[CONF_DOG_AGE] = "age_out_of_range"
            else:
                candidate[CONF_DOG_AGE] = dog_age

    raw_weight = user_input.get(CONF_DOG_WEIGHT, candidate.get(CONF_DOG_WEIGHT))
    if raw_weight is None:
        candidate.pop(CONF_DOG_WEIGHT, None)
        dog_weight = None
    else:
        try:
            dog_weight = _coerce_float(CONF_DOG_WEIGHT, raw_weight)
        except ValidationError:
            field_errors[CONF_DOG_WEIGHT] = "invalid_weight_format"
            dog_weight = None
        else:
            if dog_weight < MIN_DOG_WEIGHT or dog_weight > MAX_DOG_WEIGHT:
                field_errors[CONF_DOG_WEIGHT] = "weight_out_of_range"
            else:
                candidate[CONF_DOG_WEIGHT] = dog_weight

    raw_size = user_input.get(CONF_DOG_SIZE, candidate.get(CONF_DOG_SIZE))
    if raw_size is None:
        candidate.pop(CONF_DOG_SIZE, None)
        dog_size = None
    else:
        dog_size = str(raw_size).strip()
        if not dog_size:
            candidate.pop(CONF_DOG_SIZE, None)
            dog_size = None
        elif dog_size not in DOG_SIZES:
            field_errors[CONF_DOG_SIZE] = "invalid_dog_size"
            dog_size = None
        else:
            candidate[CONF_DOG_SIZE] = dog_size

    if (
        dog_weight is not None
        and dog_size is not None
        and not validate_dog_weight_for_size(dog_weight, dog_size)
    ):
        field_errors[CONF_DOG_WEIGHT] = "weight_size_mismatch"

    if field_errors:
        raise FlowValidationError(field_errors=field_errors)

    if dog_age is None and CONF_DOG_AGE in candidate:
        candidate.pop(CONF_DOG_AGE, None)
    if dog_weight is None and CONF_DOG_WEIGHT in candidate:
        candidate.pop(CONF_DOG_WEIGHT, None)
    return candidate
