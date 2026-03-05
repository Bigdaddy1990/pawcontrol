"""Coverage-focused tests for flow helper utilities."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import voluptuous as vol

from custom_components.pawcontrol.flow_helpers import (
    build_number_schema,
    build_select_schema,
    clear_flow_data,
    create_abort_result,
    create_menu_result,
    create_progress_result,
    validate_entity_exists,
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
