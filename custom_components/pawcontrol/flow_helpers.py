"""Shared helper functions for config and options flows.

This module provides reusable utilities for config and options flows to reduce
code duplication and standardize flow patterns across the integration.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.data_entry_flow import FlowResult

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlow, OptionsFlow


# Type aliases for flow step results
FlowStepResult = ConfigFlowResult | FlowResult


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
    return default


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
    return default


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
    flow: ConfigFlow | OptionsFlow,
    step_id: str,
    data_schema: vol.Schema,
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
        ...     flow=self,
        ...     step_id="user",
        ...     data_schema=USER_SCHEMA,
        ...     errors={"base": "invalid_input"},
        ... )
    """
    return flow.async_show_form(
        step_id=step_id,
        data_schema=data_schema,
        errors=errors or {},
        description_placeholders=description_placeholders,
        last_step=last_step,
    )


def create_menu_result(
    flow: ConfigFlow | OptionsFlow,
    step_id: str,
    menu_options: list[str],
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
        ...     flow=self, step_id="init", menu_options=["dogs", "modules", "settings"]
        ... )
    """
    return flow.async_show_menu(
        step_id=step_id,
        menu_options=menu_options,
        description_placeholders=description_placeholders,
    )


def create_abort_result(
    flow: ConfigFlow | OptionsFlow,
    reason: str,
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
    return flow.async_abort(
        reason=reason,
        description_placeholders=description_placeholders,
    )


def create_progress_result(
    flow: ConfigFlow | OptionsFlow,
    step_id: str,
    progress_action: str,
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
        ...     flow=self, step_id="validate", progress_action="validating"
        ... )
    """
    return flow.async_show_progress(
        step_id=step_id,
        progress_action=progress_action,
        description_placeholders=description_placeholders,
    )


# Error handling helpers


def validate_required_field(
    errors: dict[str, str],
    field_name: str,
    value: Any,
    error_key: str = "required",
) -> bool:
    """Validate that a required field has a value.

    Args:
        errors: Error dictionary to update
        field_name: Name of the field
        value: Field value to check
        error_key: Error key for translation

    Returns:
        True if field is valid, False otherwise

    Examples:
        >>> errors = {}
        >>> validate_required_field(errors, "name", "")
        False
        >>> errors
        {'name': 'required'}
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        errors[field_name] = error_key
        return False
    return True


def validate_min_max(
    errors: dict[str, str],
    field_name: str,
    value: float | int,
    min_value: float | int,
    max_value: float | int,
    error_key: str = "out_of_range",
) -> bool:
    """Validate that a numeric value is within range.

    Args:
        errors: Error dictionary to update
        field_name: Name of the field
        value: Numeric value to check
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        error_key: Error key for translation

    Returns:
        True if value is in range, False otherwise

    Examples:
        >>> errors = {}
        >>> validate_min_max(errors, "age", 150, 1, 25)
        False
        >>> errors
        {'age': 'out_of_range'}
    """
    if value < min_value or value > max_value:
        errors[field_name] = error_key
        return False
    return True


def validate_entity_exists(
    errors: dict[str, str],
    field_name: str,
    entity_id: str,
    hash: Any,  # HomeAssistant type
    error_key: str = "entity_not_found",
) -> bool:
    """Validate that an entity exists in Home Assistant.

    Args:
        errors: Error dictionary to update
        field_name: Name of the field
        entity_id: Entity ID to check
        hash: Home Assistant instance
        error_key: Error key for translation

    Returns:
        True if entity exists, False otherwise

    Examples:
        >>> errors = {}
        >>> validate_entity_exists(errors, "gps_source", "device_tracker.phone", hash)
        True
    """
    if not entity_id or not isinstance(entity_id, str):
        errors[field_name] = error_key
        return False

    state = hash.states.get(entity_id)
    if state is None or state.state in {"unknown", "unavailable"}:
        errors[field_name] = error_key
        return False
    return True


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
            vol.Optional(key, default=default)
            if default is not None
            else vol.Optional(key)
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
        ...     "weight", min_value=0.5, max_value=100, unit="kg"
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
            vol.Optional(key, default=default)
            if default is not None
            else vol.Optional(key)
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
            vol.Optional(key, default=default)
            if default is not None
            else vol.Optional(key)
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
    base_errors: dict[str, str],
    new_errors: dict[str, str],
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
    return {**base_errors, **new_errors}


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
    if not hasattr(flow, "_flow_data"):
        flow._flow_data = {}  # type: ignore[attr-defined]
    flow._flow_data[key] = value  # type: ignore[attr-defined]


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
    if not hasattr(flow, "_flow_data"):
        return default
    return flow._flow_data.get(key, default)  # type: ignore[attr-defined]


def clear_flow_data(flow: ConfigFlow | OptionsFlow) -> None:
    """Clear all flow context data.

    Args:
        flow: Flow instance

    Examples:
        >>> clear_flow_data(self)
    """
    if hasattr(flow, "_flow_data"):
        flow._flow_data = {}  # type: ignore[attr-defined]
