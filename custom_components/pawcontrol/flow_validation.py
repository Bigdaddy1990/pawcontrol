"""Shared validation helpers for config and options flows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from .const import (
  CONF_DOG_AGE,
  CONF_DOG_BREED,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
  CONF_MODULES,
  DOG_ID_PATTERN,
  DOG_SIZES,
  MAX_DOG_AGE,
  MAX_DOG_WEIGHT,
  MIN_DOG_AGE,
  MIN_DOG_WEIGHT,
)
from .exceptions import FlowValidationError, ValidationError
from .health_calculator import HealthMetrics
from .types import (
  DOG_AGE_FIELD,
  DOG_BREED_FIELD,
  DOG_ID_FIELD,
  DOG_MODULES_FIELD,
  DOG_NAME_FIELD,
  DOG_SIZE_FIELD,
  DOG_WEIGHT_FIELD,
  DogConfigData,
  DogSetupStepInput,
  FlowInputMapping,
  ensure_dog_modules_config,
  ensure_json_mapping,
  validate_dog_weight_for_size,
)
from .validation import InputCoercionError, coerce_float, coerce_int, normalize_dog_id
from .validation_helpers import validate_unique_dog_name

MAX_BREED_NAME_LENGTH = 100
DOG_IMPORT_FIELDS: frozenset[str] = frozenset(
  {
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_BREED,
    CONF_DOG_AGE,
    CONF_DOG_WEIGHT,
    CONF_DOG_SIZE,
    CONF_MODULES,
  },
)


def _validate_dog_id(
  raw_id: object,
  *,
  existing_ids: set[str] | None = None,
) -> tuple[str, str | None]:
  try:
    dog_id = normalize_dog_id(raw_id)
  except InputCoercionError:
    return "", "invalid_dog_id_format"
  if not dog_id:
    return "", "invalid_dog_id_format"
  if len(dog_id) < 2:
    return dog_id, "dog_id_too_short"
  if len(dog_id) > 30:
    return dog_id, "dog_id_too_long"
  if not DOG_ID_PATTERN.match(dog_id):
    return dog_id, "invalid_dog_id_format"
  if existing_ids and dog_id in existing_ids:
    return dog_id, "dog_id_already_exists"
  return dog_id, None


def _coerce_int(field: str, value: object) -> int:
  try:
    return coerce_int(field, value)
  except InputCoercionError as err:
    raise ValidationError(field, value, "Must be a whole number") from err


def _coerce_float(field: str, value: object) -> float:
  try:
    return coerce_float(field, value)
  except InputCoercionError as err:
    raise ValidationError(field, value, "Must be numeric") from err


def _validate_breed(raw_breed: object) -> str | None:
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
  user_input: FlowInputMapping,
  *,
  existing_ids: set[str],
  existing_names: set[str] | None = None,
  current_dog_count: int,
  max_dogs: int,
) -> DogSetupStepInput:
  """Validate and normalize dog setup input for flows."""

  field_errors: dict[str, str] = {}
  base_errors: list[str] = []

  dog_id, dog_id_error = _validate_dog_id(
    user_input.get(CONF_DOG_ID, ""),
    existing_ids=existing_ids,
  )
  if dog_id_error:
    field_errors[CONF_DOG_ID] = dog_id_error

  raw_name = user_input.get(CONF_DOG_NAME, "")
  try:
    dog_name = validate_unique_dog_name(
      raw_name,
      existing_names=existing_names,
      field=CONF_DOG_NAME,
    )

  except ValidationError as err:
    field_errors[CONF_DOG_NAME] = err.constraint or "dog_name_invalid"
    dog_name = ""

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
      dog_weight,
      dog_size,
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
    raise FlowValidationError(
      field_errors=field_errors,
      base_errors=base_errors,
    )

  validated: DogSetupStepInput = {
    "dog_id": dog_id,
    "dog_name": dog_name if isinstance(dog_name, str) else "",
    "dog_weight": dog_weight,
    "dog_size": dog_size,
    "dog_age": dog_age,
  }
  if dog_breed is not None:
    validated["dog_breed"] = dog_breed
  return validated


def is_dog_config_payload_valid(dog: Mapping[str, object]) -> bool:
  """Return whether a dog configuration payload is structurally valid."""

  try:
    validate_dog_config_payload(
      ensure_json_mapping(dog),
      existing_ids=None,
      existing_names=None,
    )
  except FlowValidationError:
    return False
  return True


def validate_dog_config_payload(
  user_input: FlowInputMapping,
  *,
  existing_ids: set[str] | None = None,
  existing_names: set[str] | None = None,
  current_dog_count: int | None = None,
  max_dogs: int | None = None,
) -> DogConfigData:
  """Validate and normalize dog payloads from imports or stored entry data."""

  field_errors: dict[str, str] = {}
  base_errors: list[str] = []

  dog_id, dog_id_error = _validate_dog_id(
    user_input.get(CONF_DOG_ID, ""),
    existing_ids=existing_ids,
  )
  if dog_id_error:
    field_errors[CONF_DOG_ID] = dog_id_error

  if max_dogs is not None:
    if current_dog_count is None:
      current_dog_count = 0
    if current_dog_count >= max_dogs:
      base_errors.append("max_dogs_reached")

  raw_name = user_input.get(CONF_DOG_NAME)
  candidate_name = raw_name if isinstance(raw_name, str) else ""
  current_dog: DogConfigData = {
    DOG_ID_FIELD: dog_id,
    DOG_NAME_FIELD: candidate_name,
  }

  validated_candidate: DogConfigData = current_dog
  if not field_errors:
    try:
      validated_candidate = validate_dog_update_input(
        current_dog,
        user_input,
        existing_names=existing_names,
      )
    except FlowValidationError as err:
      field_errors.update(err.field_errors)

  modules_raw = user_input.get(CONF_MODULES)
  if modules_raw is not None and not isinstance(modules_raw, Mapping):
    field_errors[CONF_MODULES] = "dog_invalid_modules"

  if field_errors or base_errors:
    raise FlowValidationError(
      field_errors=field_errors,
      base_errors=base_errors,
    )

  modules = ensure_dog_modules_config(
    cast(Mapping[str, object], user_input),
  )

  normalized_payload = dict(user_input)
  normalized_payload[DOG_ID_FIELD] = dog_id
  normalized_payload[DOG_NAME_FIELD] = validated_candidate.get(
    DOG_NAME_FIELD,
    candidate_name,
  )

  for field in (DOG_BREED_FIELD, DOG_AGE_FIELD, DOG_WEIGHT_FIELD, DOG_SIZE_FIELD):
    if field in validated_candidate:
      normalized_payload[field] = validated_candidate[field]
    else:
      normalized_payload.pop(field, None)

  if modules or CONF_MODULES in user_input:
    normalized_payload[DOG_MODULES_FIELD] = {
      key: bool(enabled) for key, enabled in modules.items()
    }
  else:
    normalized_payload.pop(DOG_MODULES_FIELD, None)

  return cast(DogConfigData, normalized_payload)


def validate_dog_update_input(
  current_dog: DogConfigData,
  user_input: FlowInputMapping,
  *,
  existing_names: set[str] | None = None,
) -> DogConfigData:
  """Validate updates for an existing dog configuration."""

  field_errors: dict[str, str] = {}

  candidate: DogConfigData = cast(DogConfigData, dict(current_dog))

  raw_name = user_input.get(CONF_DOG_NAME, candidate.get(CONF_DOG_NAME, ""))
  try:
    dog_name = validate_unique_dog_name(
      raw_name,
      existing_names=existing_names,
      field=CONF_DOG_NAME,
    )

  except ValidationError as err:
    field_errors[CONF_DOG_NAME] = err.constraint or "dog_name_invalid"
  else:
    if isinstance(dog_name, str):
      candidate[DOG_NAME_FIELD] = dog_name

  raw_breed = user_input.get(CONF_DOG_BREED, candidate.get(CONF_DOG_BREED))
  if raw_breed is None:
    candidate.pop(DOG_BREED_FIELD, None)
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
        candidate.pop(DOG_BREED_FIELD, None)
      else:
        candidate[DOG_BREED_FIELD] = normalized_breed

  raw_age = user_input.get(CONF_DOG_AGE, candidate.get(CONF_DOG_AGE))
  if raw_age is None:
    candidate.pop(DOG_AGE_FIELD, None)
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
        candidate[DOG_AGE_FIELD] = dog_age

  raw_weight = user_input.get(
    CONF_DOG_WEIGHT,
    candidate.get(CONF_DOG_WEIGHT),
  )
  if raw_weight is None:
    candidate.pop(DOG_WEIGHT_FIELD, None)
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
        candidate[DOG_WEIGHT_FIELD] = dog_weight

  raw_size = user_input.get(CONF_DOG_SIZE, candidate.get(CONF_DOG_SIZE))
  if raw_size is None:
    candidate.pop(DOG_SIZE_FIELD, None)
    dog_size = None
  else:
    dog_size = str(raw_size).strip()
    if not dog_size:
      candidate.pop(DOG_SIZE_FIELD, None)
      dog_size = None
    elif dog_size not in DOG_SIZES:
      field_errors[CONF_DOG_SIZE] = "invalid_dog_size"
      dog_size = None
    else:
      candidate[DOG_SIZE_FIELD] = dog_size

  if (
    dog_weight is not None
    and dog_size is not None
    and not validate_dog_weight_for_size(dog_weight, dog_size)
  ):
    field_errors[CONF_DOG_WEIGHT] = "weight_size_mismatch"

  if field_errors:
    raise FlowValidationError(field_errors=field_errors)

  if dog_age is None and DOG_AGE_FIELD in candidate:
    candidate.pop(DOG_AGE_FIELD, None)
  if dog_weight is None and DOG_WEIGHT_FIELD in candidate:
    candidate.pop(DOG_WEIGHT_FIELD, None)
  return candidate


def validate_dog_import_input(
  user_input: FlowInputMapping,
  *,
  existing_ids: set[str],
  existing_names: set[str] | None = None,
  current_dog_count: int,
  max_dogs: int,
) -> DogConfigData:
  """Validate and normalize dog configuration imported from YAML."""

  extra_fields = set(user_input) - DOG_IMPORT_FIELDS
  if extra_fields:
    raise ValidationError(
      "dog_config",
      value=", ".join(sorted(extra_fields)),
      constraint="Unexpected keys in dog configuration",
    )

  validated = validate_dog_setup_input(
    user_input,
    existing_ids=existing_ids,
    existing_names=existing_names,
    current_dog_count=current_dog_count,
    max_dogs=max_dogs,
  )

  modules_raw = user_input.get(CONF_MODULES, {})
  if modules_raw is None:
    modules_raw = {}
  if not isinstance(modules_raw, Mapping):
    raise ValidationError(
      CONF_MODULES,
      value=modules_raw,
      constraint="Modules must be a mapping",
    )
  modules = ensure_dog_modules_config(
    cast(Mapping[str, object], modules_raw),
  )

  dog_config: DogConfigData = {
    DOG_ID_FIELD: validated["dog_id"],
    DOG_NAME_FIELD: validated["dog_name"],
    DOG_WEIGHT_FIELD: validated["dog_weight"],
    DOG_SIZE_FIELD: validated["dog_size"],
    DOG_AGE_FIELD: int(validated["dog_age"]) if validated["dog_age"] is not None else None,
    DOG_MODULES_FIELD: modules,
  }
  if (breed := validated.get("dog_breed")) is not None:
    dog_config[DOG_BREED_FIELD] = breed
  return dog_config
