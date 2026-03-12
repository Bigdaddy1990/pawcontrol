"""Coverage-focused tests for flow helper utilities."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import voluptuous as vol

from custom_components.pawcontrol.flow_helpers import (
    build_boolean_schema,
    build_number_schema,
    build_select_schema,
    build_text_schema,
    clear_flow_data,
    coerce_bool,
    coerce_optional_float,
    coerce_optional_int,
    coerce_optional_str,
    coerce_str,
    create_abort_result,
    create_form_result,
    create_menu_result,
    create_progress_result,
    get_flow_data,
    has_errors,
    merge_errors,
    store_flow_data,
    validate_entity_exists,
    validate_min_max,
    validate_required_field,
)


def test_create_menu_abort_and_progress_delegate_to_flow_methods() -> None:
    """Flow helper wrappers should call through to flow methods when provided."""
    flow = MagicMock()
    flow.async_show_menu.return_value = {"type": "menu"}
    flow.async_abort.return_value = {"type": "abort"}
    flow.async_show_progress.return_value = {"type": "progress"}

    menu_result = create_menu_result(
        ["dogs", "modules"],
        flow=flow,
        step_id="menu_step",
        description_placeholders={"name": "Luna"},
    )
    abort_result = create_abort_result(
        "already_configured",
        flow=flow,
        description_placeholders={"dog": "Luna"},
    )
    progress_result = create_progress_result(
        "validate",
        "validating",
        flow=flow,
        description_placeholders={"dog": "Luna"},
    )

    assert menu_result == {"type": "menu"}
    flow.async_show_menu.assert_called_once_with(
        step_id="menu_step",
        menu_options=["dogs", "modules"],
        description_placeholders={"name": "Luna"},
    )
    assert abort_result == {"type": "abort"}
    flow.async_abort.assert_called_once_with(
        reason="already_configured",
        description_placeholders={"dog": "Luna"},
    )
    assert progress_result == {"type": "progress"}
    flow.async_show_progress.assert_called_once_with(
        step_id="validate",
        progress_action="validating",
        description_placeholders={"dog": "Luna"},
    )


def test_validate_required_field_legacy_argument_validation() -> None:
    """Legacy API should raise when required positional values are omitted."""
    with pytest.raises(TypeError, match="legacy validate_required_field requires"):
        validate_required_field({}, "field")


def test_validate_required_field_modern_argument_validation() -> None:
    """Modern API should require field name and value positional arguments."""
    with pytest.raises(TypeError, match="requires field_name and value"):
        validate_required_field("field")


def test_validate_entity_exists_rejects_invalid_and_unavailable_states() -> None:
    """Entity validation should flag invalid IDs and unavailable states."""
    hass = MagicMock()
    hass.states.get.side_effect = [
        None,
        SimpleNamespace(state="unknown"),
        SimpleNamespace(state="unavailable"),
        SimpleNamespace(state="on"),
    ]

    assert validate_entity_exists(hass=hass, field="sensor", entity_id="") == {
        "sensor": "entity_not_found"
    }
    assert validate_entity_exists(hass=hass, field="sensor", entity_id="sensor.a") == {
        "sensor": "entity_not_found"
    }
    assert validate_entity_exists(hass=hass, field="sensor", entity_id="sensor.b") == {
        "sensor": "entity_not_found"
    }
    assert validate_entity_exists(hass=hass, field="sensor", entity_id="sensor.c") == {
        "sensor": "entity_not_found"
    }
    assert (
        validate_entity_exists(hass=hass, field="sensor", entity_id="sensor.ok") == {}
    )


def test_clear_flow_data_handles_non_mapping_payload() -> None:
    """clear_flow_data should no-op when _flow_data is not a dictionary."""
    flow = MagicMock()
    flow._flow_data = "invalid"

    clear_flow_data(flow)

    assert flow._flow_data == "invalid"


def test_build_key_defaults_include_and_exclude_default_values() -> None:
    """Schema builders should support required and optional key variants."""
    required_key = next(iter(build_select_schema("mode", ["a", "b"], required=True)))
    optional_with_default = next(
        iter(build_number_schema("weight", min_value=1, max_value=5, default=3))
    )

    assert isinstance(required_key, vol.Required)
    assert isinstance(optional_with_default, vol.Optional)


def test_coerce_helpers_cover_edge_cases() -> None:
    """Coercion helpers should normalize booleans, strings, and numbers."""
    assert coerce_bool(True) is True
    assert coerce_bool(" enabled ") is True
    assert coerce_bool("disabled") is False
    assert coerce_bool(None, default=True) is True
    assert coerce_bool(0) is False
    assert coerce_bool([]) is False

    assert coerce_str("  fido  ") == "fido"
    assert coerce_str(None, default="fallback") == "fallback"
    assert coerce_str(123) == "123"

    assert coerce_optional_str("  ") is None
    assert coerce_optional_str("luna") == "luna"
    assert coerce_optional_str(10) is None

    assert coerce_optional_float(5) == 5.0
    assert coerce_optional_float(" 2.5 ") == 2.5
    assert coerce_optional_float("bad") is None
    assert coerce_optional_float(object()) is None

    assert coerce_optional_int(4) == 4
    assert coerce_optional_int(4.8) == 4
    assert coerce_optional_int(" 8 ") == 8
    assert coerce_optional_int("oops") is None
    assert coerce_optional_int(object()) is None


def test_validate_required_field_legacy_success_and_error_assignment() -> None:
    """Legacy validation API should return bool and mutate the passed errors map."""
    errors: dict[str, str] = {}

    assert validate_required_field(errors, "name", "") is False
    assert errors == {"name": "required"}

    other_errors: dict[str, str] = {}
    assert validate_required_field(other_errors, "name", "Buddy") is True
    assert other_errors == {}


def test_create_form_result_without_flow_and_validation_error() -> None:
    """Form helper should build raw results and reject missing schema."""
    schema = vol.Schema({vol.Required("name"): str})
    result = create_form_result(
        "user",
        data_schema=schema,
        errors={"base": "invalid_auth"},
        description_placeholders={"host": "paw.local"},
        last_step=True,
    )

    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}
    assert result["last_step"] is True

    alias_result = create_form_result("user", schema=schema)
    assert alias_result["data_schema"] is schema

    with pytest.raises(ValueError, match="data_schema or schema must be provided"):
        create_form_result("user")


def test_create_form_result_delegates_to_flow() -> None:
    """Flow-backed form helper should call async_show_form with defaults."""
    flow = MagicMock()
    flow.async_show_form.return_value = {"type": "form"}
    schema = vol.Schema({vol.Optional("name"): str})

    result = create_form_result("user", data_schema=schema, flow=flow)

    assert result == {"type": "form"}
    flow.async_show_form.assert_called_once_with(
        step_id="user",
        data_schema=schema,
        errors={},
        description_placeholders=None,
        last_step=False,
    )


def test_result_helpers_without_flow_return_raw_payloads() -> None:
    """Menu, abort, and progress helpers should emit plain dictionaries."""
    menu = create_menu_result(["dogs"], step_id="menu")
    abort = create_abort_result("already_configured")
    progress = create_progress_result("validate", "running")

    assert menu["step_id"] == "menu"
    assert abort["reason"] == "already_configured"
    assert progress["progress_action"] == "running"


def test_validation_and_error_helpers() -> None:
    """Validation helpers should merge and report errors deterministically."""
    assert validate_required_field("name", "", errors={}) == {"name": "required"}
    assert validate_min_max("age", 2, min_value=3, max_value=10) == {
        "age": "out_of_range"
    }
    assert validate_min_max("age", 11, min_value=3, max_value=10) == {
        "age": "out_of_range"
    }

    merged = merge_errors(
        {"base": "invalid"},
        base_errors={"name": "required"},
        new_errors={"age": "invalid"},
    )
    assert merged == {"name": "required", "age": "invalid", "base": "invalid"}
    assert has_errors(merged) is True
    assert has_errors({}) is False


def test_store_get_clear_flow_data_and_schema_helpers() -> None:
    """Flow state and schema builders should support optional branches."""
    flow = MagicMock()

    store_flow_data(flow, "dog_id", "abc")
    store_flow_data(flow, "size", "large")

    assert get_flow_data(flow, "dog_id") == "abc"
    assert get_flow_data(flow, "missing", default="default") == "default"

    clear_flow_data(flow, key="dog_id")
    assert get_flow_data(flow, "dog_id") is None
    assert get_flow_data(flow, "size") == "large"

    clear_flow_data(flow)
    assert get_flow_data(flow, "size") is None

    text_key = next(
        iter(
            build_text_schema(
                "name",
                required=True,
                default="Buddy",
                autocomplete="name",
                multiline=True,
            )
        )
    )
    bool_key = next(iter(build_boolean_schema("enabled", default=True)))

    assert isinstance(text_key, vol.Required)
    assert isinstance(bool_key, vol.Optional)


def test_schema_builders_cover_required_variants_without_defaults() -> None:
    """Schema helpers should create required keys when no default is provided."""
    select_key = next(iter(build_select_schema("mode", ["a", "b"], required=True)))
    number_key = next(
        iter(
            build_number_schema(
                "weight", min_value=1, max_value=10, required=True, unit="kg"
            )
        )
    )
    text_key = next(iter(build_text_schema("nickname", required=True)))

    assert isinstance(select_key, vol.Required)
    assert isinstance(number_key, vol.Required)
    assert isinstance(text_key, vol.Required)


def test_schema_builders_cover_optional_and_legacy_custom_error_paths() -> None:
    """Schema helpers should cover optional default and legacy custom branches."""
    legacy_errors: dict[str, str] = {}

    assert validate_required_field(legacy_errors, "name", "", "missing_value") is False
    assert legacy_errors["name"] == "missing_value"

    select_key = next(iter(build_select_schema("mode", ["a", "b"], default="a")))
    number_key = next(
        iter(build_number_schema("walk_goal", min_value=1, max_value=10, default=5))
    )
    text_key = next(iter(build_text_schema("nickname", default="Luna")))

    assert isinstance(select_key, vol.Optional)
    assert isinstance(number_key, vol.Optional)
    assert isinstance(text_key, vol.Optional)
    assert select_key.default() == "a"
    assert number_key.default() == 5
    assert text_key.default() == "Luna"


def test_schema_builders_cover_required_defaults() -> None:
    """Schema helpers should support required selectors with explicit defaults."""
    select_key = next(
        iter(build_select_schema("mode", ["a", "b"], required=True, default="a"))
    )
    number_key = next(
        iter(
            build_number_schema(
                "walk_goal",
                min_value=1,
                max_value=10,
                required=True,
                default=5,
            )
        )
    )
    text_key = next(iter(build_text_schema("nickname", required=True, default="Luna")))

    assert isinstance(select_key, vol.Required)
    assert isinstance(number_key, vol.Required)
    assert isinstance(text_key, vol.Required)
    assert select_key.default() == "a"
    assert number_key.default() == 5
    assert text_key.default() == "Luna"


def test_build_select_schema_applies_translation_key_to_selector_config() -> None:
    """Select schema helper should forward translation metadata."""
    _key, select_selector = next(
        iter(
            build_select_schema(
                "mode",
                ["a", "b"],
                required=True,
                translation_key="mode",
            ).items()
        )
    )

    assert select_selector.config.get("translation_key") == "mode"


def test_get_flow_data_returns_default_when_internal_state_is_not_mapping() -> None:
    """Reading flow data should gracefully fallback when _flow_data is invalid."""
    flow = MagicMock()
    flow._flow_data = "broken"

    assert get_flow_data(flow, "dog_id", default="fallback") == "fallback"
