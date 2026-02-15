"""Shared helper functions for config and options flows.

This module provides reusable utilities for config and options flows to reduce
code duplication and standardize flow patterns across the integration.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

from typing import Any
from typing import cast
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.data_entry_flow import FlowResult

if TYPE_CHECKING:
  from homeassistant.config_entries import ConfigFlow, OptionsFlow


# Type aliases for flow step results
type FlowStepResult = ConfigFlowResult | FlowResult


def coerce_bool(value: Any, *, default: bool = False) -> bool:
  """Coerce an arbitrary value into a boolean flag.

  Args:
      value: Value to coerce
      default: Default value if coercion fails

  Returns:
      Boolean value

  Examples:
      >>> coerce_bool("true")
      True
      >>> coerce_bool(1)
      True
      >>> coerce_bool("no")
      False
      >>> coerce_bool(None)
      False
  """
  if isinstance(value, bool):
    return value
  if isinstance(value, str):
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on", "enabled"}:
      return True
    if lowered in {"0", "false", "no", "off", "disabled"}:
      return False
  if isinstance(value, int | float):
    return bool(value)
  if value is None:
    return default
  return bool(value)


def coerce_str(value: Any, *, default: str = "") -> str:
  """Coerce arbitrary user input into a trimmed string.

  Args:
      value: Value to coerce
      default: Default value if coercion fails

  Returns:
      Trimmed string value

  Examples:
      >>> coerce_str("  hello  ")
      'hello'
      >>> coerce_str(123)
      ''
      >>> coerce_str(None, default="N/A")
      'N/A'
  """
  if isinstance(value, str):
    trimmed = value.strip()
    return trimmed or default
  if value is None:
    return default
  return str(value)


def coerce_optional_str(value: Any) -> str | None:
  """Return a trimmed string when available, otherwise None.

  Args:
      value: Value to coerce

  Returns:
      Trimmed string or None

  Examples:
      >>> coerce_optional_str("  hello  ")
      'hello'
      >>> coerce_optional_str("")
      None
      >>> coerce_optional_str(None)
      None
  """
  if isinstance(value, str):
    trimmed = value.strip()
    return trimmed or None
  return None


def coerce_optional_float(value: Any) -> float | None:
  """Coerce arbitrary user input into a float when possible.

  Args:
      value: Value to coerce

  Returns:
      Float value or None

  Examples:
      >>> coerce_optional_float("123.45")
      123.45
      >>> coerce_optional_float(42)
      42.0
      >>> coerce_optional_float("invalid")
      None
  """
  if isinstance(value, float | int):
    return float(value)
  if isinstance(value, str):
    try:
      return float(value.strip())
    except ValueError:
      return None
  return None


def coerce_optional_int(value: Any) -> int | None:
  """Coerce arbitrary user input into an integer when possible.

  Args:
      value: Value to coerce

  Returns:
      Integer value or None

  Examples:
      >>> coerce_optional_int("42")
      42
      >>> coerce_optional_int(3.14)
      3
      >>> coerce_optional_int("invalid")
      None
  """
  if isinstance(value, int):
    return value
  if isinstance(value, float):
    return int(value)
  if isinstance(value, str):
    try:
      return int(value.strip())
    except ValueError:
      return None
  return None


# Common form rendering helpers


def create_form_result(
  step_id: str,
  data_schema: vol.Schema | None = None,
  *,
  flow: ConfigFlow | OptionsFlow | None = None,
  schema: vol.Schema | None = None,
  errors: dict[str, str] | None = None,
  description_placeholders: dict[str, str] | None = None,
  last_step: bool = False,
) -> FlowStepResult:
  """Create a standardized form result for config/options flows.

  Args:
      flow: The config or options flow instance
      step_id: Step identifier
      data_schema: Voluptuous schema for the form
      errors: Optional error dictionary
      description_placeholders: Optional description placeholders
      last_step: Whether this is the last step

  Returns:
      Form result ready for display

  Examples:
      >>> result = create_form_result(
      ...   flow=self,
      ...   step_id="user",
      ...   data_schema=USER_SCHEMA,
      ...   errors={"base": "invalid_input"},
      ... )
  """
  resolved_schema = data_schema or schema
  if resolved_schema is None:
    msg = "data_schema or schema must be provided"
    raise ValueError(msg)

  if flow is None:
    return cast(
      FlowStepResult,
      {
        "type": data_entry_flow.FlowResultType.FORM,
        "step_id": step_id,
        "data_schema": resolved_schema,
        "errors": errors or {},
        "description_placeholders": description_placeholders,
        "last_step": last_step,
      },
    )

  return flow.async_show_form(
    step_id=step_id,
    data_schema=resolved_schema,
    errors=errors or {},
    description_placeholders=description_placeholders,
    last_step=last_step,
  )


def create_menu_result(
  menu_options: list[str],
  *,
  flow: ConfigFlow | OptionsFlow | None = None,
  step_id: str = "menu",
  description_placeholders: dict[str, str] | None = None,
) -> FlowStepResult:
  """Create a standardized menu result for config/options flows.

  Args:
      flow: The config or options flow instance
      step_id: Menu step identifier
      menu_options: List of menu option step IDs
      description_placeholders: Optional description placeholders

  Returns:
      Menu result ready for display

  Examples:
      >>> result = create_menu_result(
      ...   flow=self, step_id="init", menu_options=["dogs", "modules", "settings"]
      ... )
  """
def create_menu_result(  # noqa: F811
    menu_options: list[str],
    *,
    flow: Any | None = None,  # Make parameter optional
    step_id: str = "init",
    description_placeholders: dict[str, str] | None = None,
) -> FlowStepResult:

  return cast(
    FlowStepResult,
    flow.async_show_menu(
      step_id=step_id,
      menu_options=menu_options,
      description_placeholders=description_placeholders,
    ),
  )


def create_abort_result(
  reason: str,
  *,
  flow: ConfigFlow | OptionsFlow | None = None,
  description_placeholders: dict[str, str] | None = None,
) -> FlowStepResult:
  """Create a standardized abort result.

  Args:
      flow: The config or options flow instance
      reason: Abort reason key (for translation)
      description_placeholders: Optional description placeholders

  Returns:
      Abort result

  Examples:
      >>> result = create_abort_result(flow=self, reason="already_configured")
  """
  if flow is None:
    return cast(
      FlowStepResult,
      {
        "type": data_entry_flow.FlowResultType.ABORT,
        "reason": reason,
        "description_placeholders": description_placeholders,
      },
    )

  return cast(
    FlowStepResult,
    flow.async_abort(
      reason=reason,
      description_placeholders=description_placeholders,
    ),
  )


def create_progress_result(
  step_id: str,
  progress_action: str,
  *,
  flow: ConfigFlow | OptionsFlow | None = None,
  description_placeholders: dict[str, str] | None = None,
) -> FlowStepResult:
  """Create a standardized progress result.

  Args:
      flow: The config or options flow instance
      step_id: Progress step identifier
      progress_action: Progress action identifier
      description_placeholders: Optional description placeholders

  Returns:
      Progress result

  Examples:
      >>> result = create_progress_result(
      ...   flow=self, step_id="validate", progress_action="validating"
      ... )
  """
  if flow is None:
    return cast(
      FlowStepResult,
      {
        "type": data_entry_flow.FlowResultType.SHOW_PROGRESS,
        "step_id": step_id,
        "progress_action": progress_action,
        "description_placeholders": description_placeholders,
      },
    )

  return cast(
    FlowStepResult,
    flow.async_show_progress(
      step_id=step_id,
      progress_action=progress_action,
      description_placeholders=description_placeholders,
    ),
  )


# Error handling helpers


def validate_required_field(
  *args: Any,
  errors: dict[str, str] | None = None,
  error_key: str = "required",
) -> dict[str, str] | bool:
  """Validate that a required field has a value.

  Supports both the legacy mutation/boolean API and the newer return-errors API:

  Legacy:
      validate_required_field(errors, field_name, value, error_key="required")
      -> bool

  Current:
      validate_required_field(field_name, value, errors=errors) -> dict[str, str]
  """

  if args and isinstance(args[0], dict):
    # Backward-compatible positional API.
    if len(args) < 3:
      msg = "legacy validate_required_field requires errors, field_name, and value"
      raise TypeError(msg)
    legacy_errors = args[0]
    field_name = args[1]
    value = args[2]
    if len(args) >= 4:
      error_key = args[3]

    has_value = value is not None and (
      not isinstance(value, str) or bool(value.strip())
    )
    if not has_value:
      legacy_errors[field_name] = error_key
    return has_value

  if len(args) < 2:
    msg = "validate_required_field requires field_name and value"
    raise TypeError(msg)

  field_name = args[0]
  value = args[1]
  resolved_errors = errors or {}
  if value is None or (isinstance(value, str) and not value.strip()):
    resolved_errors[field_name] = error_key
  return resolved_errors


def validate_min_max(
  field_name: str,
  value: float | int,
  *,
  min_value: float | int | None,
  max_value: float | int | None,
  errors: dict[str, str] | None = None,
  error_key: str = "out_of_range",
) -> dict[str, str]:
  """Validate that a numeric value is within range."""

  resolved_errors = errors or {}
  if min_value is not None and value < min_value:
    resolved_errors[field_name] = error_key
  if max_value is not None and value > max_value:
    resolved_errors[field_name] = error_key
  return resolved_errors


def validate_entity_exists(
  *,
  hass: Any,  # HomeAssistant type
  field: str,
  entity_id: str,
  errors: dict[str, str] | None = None,
  error_key: str = "entity_not_found",
) -> dict[str, str]:
  """Validate that an entity exists in Home Assistant."""

  resolved_errors = errors or {}
  if not entity_id or not isinstance(entity_id, str):
    resolved_errors[field] = error_key
    return resolved_errors

  state = hass.states.get(entity_id)
  if state is None or state.state in {"unknown", "unavailable"}:
    resolved_errors[field] = error_key
  return resolved_errors


# Schema building helpers


def build_select_schema(
  key: str,
  options: list[str],
  *,
  default: str | None = None,
  required: bool = False,
  translation_key: str | None = None,
) -> dict[vol.Optional | vol.Required, Any]:
  """Build a select selector schema.

  Args:
      key: Configuration key
      options: List of available options
      default: Default value
      required: Whether field is required
      translation_key: Translation key for options

  Returns:
      Schema dictionary fragment

  Examples:
      >>> schema = build_select_schema("size", ["small", "medium", "large"])
  """
  from .selector_shim import selector

  vol_key: vol.Optional | vol.Required
  if required:
    if default is not None:
      vol_key = vol.Required(key, default=default)
    else:
      vol_key = vol.Required(key)
  else:
    vol_key = (
      vol.Optional(key, default=default) if default is not None else vol.Optional(key)
    )

  config = selector.SelectSelectorConfig(
    options=options,
    mode=selector.SelectSelectorMode.DROPDOWN,
  )
  if translation_key:
    config = selector.SelectSelectorConfig(
      options=options,
      mode=selector.SelectSelectorMode.DROPDOWN,
      translation_key=translation_key,
    )

  return {vol_key: selector.SelectSelector(config)}


def build_number_schema(
  key: str,
  *,
  min_value: float | int,
  max_value: float | int,
  step: float | int = 1,
  default: float | int | None = None,
  required: bool = False,
  unit: str | None = None,
) -> dict[vol.Optional | vol.Required, Any]:
  """Build a number selector schema.

  Args:
      key: Configuration key
      min_value: Minimum allowed value
      max_value: Maximum allowed value
      step: Step size
      default: Default value
      required: Whether field is required
      unit: Unit of measurement

  Returns:
      Schema dictionary fragment

  Examples:
      >>> schema = build_number_schema(
      ...   "weight", min_value=0.5, max_value=100, unit="kg"
      ... )
  """
  from .selector_shim import selector

  vol_key: vol.Optional | vol.Required
  if required:
    if default is not None:
      vol_key = vol.Required(key, default=default)
    else:
      vol_key = vol.Required(key)
  else:
    vol_key = (
      vol.Optional(key, default=default) if default is not None else vol.Optional(key)
    )

  config = selector.NumberSelectorConfig(
    min=min_value,
    max=max_value,
    step=step,
    mode=selector.NumberSelectorMode.BOX,
  )
  if unit:
    config = selector.NumberSelectorConfig(
      min=min_value,
      max=max_value,
      step=step,
      mode=selector.NumberSelectorMode.BOX,
      unit_of_measurement=unit,
    )

  return {vol_key: selector.NumberSelector(config)}


def build_text_schema(
  key: str,
  *,
  default: str | None = None,
  required: bool = False,
  autocomplete: str | None = None,
  multiline: bool = False,
) -> dict[vol.Optional | vol.Required, Any]:
  """Build a text selector schema.

  Args:
      key: Configuration key
      default: Default value
      required: Whether field is required
      autocomplete: Autocomplete type
      multiline: Whether to allow multiline input

  Returns:
      Schema dictionary fragment

  Examples:
      >>> schema = build_text_schema("name", required=True, autocomplete="name")
  """
  from .selector_shim import selector

  vol_key: vol.Optional | vol.Required
  if required:
    if default is not None:
      vol_key = vol.Required(key, default=default)
    else:
      vol_key = vol.Required(key)
  else:
    vol_key = (
      vol.Optional(key, default=default) if default is not None else vol.Optional(key)
    )

  config = selector.TextSelectorConfig(
    type=selector.TextSelectorType.TEXT,
    multiline=multiline,
  )
  if autocomplete:
    config = selector.TextSelectorConfig(
      type=selector.TextSelectorType.TEXT,
      multiline=multiline,
      autocomplete=autocomplete,
    )

  return {vol_key: selector.TextSelector(config)}


def build_boolean_schema(
  key: str,
  *,
  default: bool = False,
) -> dict[vol.Optional, Any]:
  """Build a boolean selector schema.

  Args:
      key: Configuration key
      default: Default value

  Returns:
      Schema dictionary fragment

  Examples:
      >>> schema = build_boolean_schema("enabled", default=True)
  """
  from .selector_shim import selector

  return {vol.Optional(key, default=default): selector.BooleanSelector()}


# Common validation patterns


def merge_errors(
  *error_maps: dict[str, str],
  base_errors: dict[str, str] | None = None,
  new_errors: dict[str, str] | None = None,
) -> dict[str, str]:
  """Merge two error dictionaries.

  Args:
      base_errors: Base error dictionary
      new_errors: New errors to merge

  Returns:
      Merged error dictionary

  Examples:
      >>> merge_errors({"name": "required"}, {"age": "invalid"})
      {'name': 'required', 'age': 'invalid'}
  """
  merged: dict[str, str] = {}
  if base_errors:
    merged.update(base_errors)
  if new_errors:
    merged.update(new_errors)
  for errors in error_maps:
    merged.update(errors)
  return merged


def has_errors(errors: dict[str, str]) -> bool:
  """Check if there are any validation errors.

  Args:
      errors: Error dictionary

  Returns:
      True if there are errors

  Examples:
      >>> has_errors({})
      False
      >>> has_errors({"name": "required"})
      True
  """
  return len(errors) > 0


# Flow state management


def store_flow_data(
  flow: ConfigFlow | OptionsFlow,
  key: str,
  value: Any,
) -> None:
  """Store data in flow context for later steps.

  Args:
      flow: Flow instance
      key: Data key
      value: Data value

  Examples:
      >>> store_flow_data(self, "dog_id", "buddy")
  """
  flow_data = getattr(flow, "_flow_data", None)
  if not isinstance(flow_data, dict):
    flow_data = {}
    flow._flow_data = flow_data
  flow_data[key] = value


def get_flow_data(
  flow: ConfigFlow | OptionsFlow,
  key: str,
  default: Any = None,
) -> Any:
  """Retrieve data from flow context.

  Args:
      flow: Flow instance
      key: Data key
      default: Default value if key not found

  Returns:
      Stored value or default

  Examples:
      >>> dog_id = get_flow_data(self, "dog_id")
  """
  flow_data = getattr(flow, "_flow_data", None)
  if not isinstance(flow_data, dict):
    return default
  return flow_data.get(key, default)


def clear_flow_data(flow: ConfigFlow | OptionsFlow, key: str | None = None) -> None:
  """Clear all flow context data.

  Args:
      flow: Flow instance

  Examples:
      >>> clear_flow_data(self)
  """
  flow_data = getattr(flow, "_flow_data", None)
  if not isinstance(flow_data, dict):
    return
  if key is None:
    flow._flow_data = {}
  else:
    flow_data.pop(key, None)
