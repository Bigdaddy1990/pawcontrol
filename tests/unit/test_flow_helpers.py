"""Unit tests for flow_helpers module.

Tests all utility functions for config and options flows including type coercion,
form rendering, error handling, schema building, and flow state management.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant import data_entry_flow
from homeassistant.const import CONF_NAME
from voluptuous import Schema

from custom_components.pawcontrol.flow_helpers import build_boolean_schema
from custom_components.pawcontrol.flow_helpers import build_number_schema
from custom_components.pawcontrol.flow_helpers import build_select_schema
from custom_components.pawcontrol.flow_helpers import build_text_schema
from custom_components.pawcontrol.flow_helpers import clear_flow_data
from custom_components.pawcontrol.flow_helpers import coerce_bool
from custom_components.pawcontrol.flow_helpers import coerce_optional_float
from custom_components.pawcontrol.flow_helpers import coerce_optional_int
from custom_components.pawcontrol.flow_helpers import coerce_optional_str
from custom_components.pawcontrol.flow_helpers import coerce_str
from custom_components.pawcontrol.flow_helpers import create_abort_result
from custom_components.pawcontrol.flow_helpers import create_form_result
from custom_components.pawcontrol.flow_helpers import create_menu_result
from custom_components.pawcontrol.flow_helpers import create_progress_result
from custom_components.pawcontrol.flow_helpers import get_flow_data
from custom_components.pawcontrol.flow_helpers import has_errors
from custom_components.pawcontrol.flow_helpers import merge_errors
from custom_components.pawcontrol.flow_helpers import store_flow_data
from custom_components.pawcontrol.flow_helpers import validate_entity_exists
from custom_components.pawcontrol.flow_helpers import validate_min_max
from custom_components.pawcontrol.flow_helpers import validate_required_field


class TestTypeCoercion:
  """Test type coercion functions."""

  def test_coerce_bool_true_values(self) -> None:
    """Test coerce_bool with true values."""
    assert coerce_bool(True) is True
    assert coerce_bool("true") is True
    assert coerce_bool("True") is True
    assert coerce_bool("TRUE") is True
    assert coerce_bool("yes") is True
    assert coerce_bool("Yes") is True
    assert coerce_bool("1") is True
    assert coerce_bool(1) is True

  def test_coerce_bool_false_values(self) -> None:
    """Test coerce_bool with false values."""
    assert coerce_bool(False) is False
    assert coerce_bool("false") is False
    assert coerce_bool("False") is False
    assert coerce_bool("no") is False
    assert coerce_bool("0") is False
    assert coerce_bool(0) is False
    assert coerce_bool(None) is False
    assert coerce_bool("") is False

  def test_coerce_str(self) -> None:
    """Test coerce_str function."""
    assert coerce_str("test") == "test"
    assert coerce_str("  test  ") == "test"
    assert coerce_str(123) == "123"
    assert coerce_str(True) == "True"
    assert coerce_str(None) == ""

  def test_coerce_optional_str(self) -> None:
    """Test coerce_optional_str function."""
    assert coerce_optional_str("test") == "test"
    assert coerce_optional_str("  test  ") == "test"
    assert coerce_optional_str("") is None
    assert coerce_optional_str(None) is None
    assert coerce_optional_str("  ") is None

  def test_coerce_optional_float(self) -> None:
    """Test coerce_optional_float function."""
    assert coerce_optional_float(1.5) == 1.5
    assert coerce_optional_float("1.5") == 1.5
    assert coerce_optional_float("0") == 0.0
    assert coerce_optional_float(0) == 0.0
    assert coerce_optional_float(None) is None
    assert coerce_optional_float("") is None
    assert coerce_optional_float("invalid") is None

  def test_coerce_optional_int(self) -> None:
    """Test coerce_optional_int function."""
    assert coerce_optional_int(5) == 5
    assert coerce_optional_int("5") == 5
    assert coerce_optional_int("0") == 0
    assert coerce_optional_int(0) == 0
    assert coerce_optional_int(None) is None
    assert coerce_optional_int("") is None
    assert coerce_optional_int("invalid") is None
    assert coerce_optional_int(1.5) == 1  # Truncates to int


class TestFormRendering:
  """Test form rendering functions."""

  def test_create_form_result(self) -> None:
    """Test create_form_result function."""
    schema = Schema({CONF_NAME: str})
    result = create_form_result(
      step_id="test_step",
      schema=schema,
      description_placeholders={"test": "value"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "test_step"
    assert result["data_schema"] == schema
    assert result["description_placeholders"] == {"test": "value"}
    assert result["errors"] == {}

  def test_create_form_result_with_errors(self) -> None:
    """Test create_form_result with errors."""
    schema = Schema({CONF_NAME: str})
    errors = {"base": "invalid_input"}
    result = create_form_result(
      step_id="test_step",
      schema=schema,
      errors=errors,
    )

    assert result["errors"] == errors

  def test_create_menu_result(self) -> None:
    """Test create_menu_result function."""
    menu_options = ["option1", "option2", "option3"]
    result = create_menu_result(menu_options=menu_options)

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["menu_options"] == menu_options

  def test_create_abort_result(self) -> None:
    """Test create_abort_result function."""
    result = create_abort_result(reason="test_reason")

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "test_reason"

  def test_create_progress_result(self) -> None:
    """Test create_progress_result function."""
    result = create_progress_result(
      step_id="test_step",
      progress_action="test_action",
    )

    assert result["type"] == data_entry_flow.FlowResultType.SHOW_PROGRESS
    assert result["step_id"] == "test_step"
    assert result["progress_action"] == "test_action"


class TestErrorHandling:
  """Test error handling functions."""

  def test_validate_required_field_valid(self) -> None:
    """Test validate_required_field with valid value."""
    errors = validate_required_field(
      "test_field",
      "valid_value",
      errors={},
    )
    assert errors == {}

  def test_validate_required_field_empty(self) -> None:
    """Test validate_required_field with empty value."""
    errors = validate_required_field(
      "test_field",
      "",
      errors={},
    )
    assert errors == {"test_field": "required"}

  def test_validate_required_field_none(self) -> None:
    """Test validate_required_field with None value."""
    errors = validate_required_field(
      "test_field",
      None,
      errors={},
    )
    assert errors == {"test_field": "required"}

  def test_validate_min_max_valid(self) -> None:
    """Test validate_min_max with valid value."""
    errors = validate_min_max(
      "test_field",
      5.0,
      min_value=0.0,
      max_value=10.0,
      errors={},
    )
    assert errors == {}

  def test_validate_min_max_too_low(self) -> None:
    """Test validate_min_max with value too low."""
    errors = validate_min_max(
      "test_field",
      -1.0,
      min_value=0.0,
      max_value=10.0,
      errors={},
    )
    assert errors == {"test_field": "out_of_range"}

  def test_validate_min_max_too_high(self) -> None:
    """Test validate_min_max with value too high."""
    errors = validate_min_max(
      "test_field",
      11.0,
      min_value=0.0,
      max_value=10.0,
      errors={},
    )
    assert errors == {"test_field": "out_of_range"}

  def test_validate_entity_exists_valid(self) -> None:
    """Test validate_entity_exists with valid entity."""
    mock_hass = MagicMock()
    mock_hass.states.get.return_value = MagicMock()

    errors = validate_entity_exists(
      hass=mock_hass,
      field="test_field",
      entity_id="sensor.test",
      errors={},
    )
    assert errors == {}

  def test_validate_entity_exists_invalid(self) -> None:
    """Test validate_entity_exists with invalid entity."""
    mock_hass = MagicMock()
    mock_hass.states.get.return_value = None

    errors = validate_entity_exists(
      hass=mock_hass,
      field="test_field",
      entity_id="sensor.invalid",
      errors={},
    )
    assert errors == {"test_field": "entity_not_found"}

  def test_merge_errors(self) -> None:
    """Test merge_errors function."""
    errors1 = {"field1": "error1"}
    errors2 = {"field2": "error2"}
    errors3 = {"field3": "error3"}

    merged = merge_errors(errors1, errors2, errors3)
    assert merged == {
      "field1": "error1",
      "field2": "error2",
      "field3": "error3",
    }

  def test_merge_errors_overwrite(self) -> None:
    """Test merge_errors with overlapping keys."""
    errors1 = {"field": "error1"}
    errors2 = {"field": "error2"}

    merged = merge_errors(errors1, errors2)
    assert merged == {"field": "error2"}

  def test_has_errors(self) -> None:
    """Test has_errors function."""
    assert has_errors({}) is False
    assert has_errors({"field": "error"}) is True


class TestSchemaBuilding:
  """Test schema building functions."""

  def test_build_select_schema(self) -> None:
    """Test build_select_schema function."""
    schema = build_select_schema(
      key="test_key",
      options=["option1", "option2"],
      default="option1",
    )

    # Schema should be a vol.Schema
    assert schema is not None

  def test_build_number_schema(self) -> None:
    """Test build_number_schema function."""
    schema = build_number_schema(
      key="test_key",
      min_value=0.0,
      max_value=100.0,
      default=50.0,
    )

    assert schema is not None

  def test_build_text_schema(self) -> None:
    """Test build_text_schema function."""
    schema = build_text_schema(
      key="test_key",
      default="default_value",
    )

    assert schema is not None

  def test_build_boolean_schema(self) -> None:
    """Test build_boolean_schema function."""
    schema = build_boolean_schema(
      key="test_key",
      default=True,
    )

    assert schema is not None


class TestFlowStateManagement:
  """Test flow state management functions."""

  def test_store_and_get_flow_data(self) -> None:
    """Test storing and retrieving flow data."""
    mock_flow = MagicMock()
    test_data = {"key": "value", "number": 123}

    store_flow_data(mock_flow, "test_key", test_data)
    retrieved = get_flow_data(mock_flow, "test_key")

    assert retrieved == test_data

  def test_get_flow_data_default(self) -> None:
    """Test get_flow_data with default value."""
    mock_flow = MagicMock()
    mock_flow.context = {}

    retrieved = get_flow_data(mock_flow, "nonexistent", default="default_value")
    assert retrieved == "default_value"

  def test_clear_flow_data(self) -> None:
    """Test clearing flow data."""
    mock_flow = MagicMock()
    test_data = {"key": "value"}

    store_flow_data(mock_flow, "test_key", test_data)
    clear_flow_data(mock_flow, "test_key")
    retrieved = get_flow_data(mock_flow, "test_key")

    assert retrieved is None

  def test_flow_data_isolation(self) -> None:
    """Test that flow data is isolated by key."""
    mock_flow = MagicMock()

    store_flow_data(mock_flow, "key1", {"value": 1})
    store_flow_data(mock_flow, "key2", {"value": 2})

    assert get_flow_data(mock_flow, "key1") == {"value": 1}
    assert get_flow_data(mock_flow, "key2") == {"value": 2}


class TestEdgeCases:
  """Test edge cases and error conditions."""

  def test_coerce_bool_edge_cases(self) -> None:
    """Test coerce_bool with edge cases."""
    assert coerce_bool([]) is False
    assert coerce_bool({}) is False
    assert coerce_bool([1]) is True
    assert coerce_bool({"key": "value"}) is True

  def test_validate_min_max_none_bounds(self) -> None:
    """Test validate_min_max with None bounds."""
    errors = validate_min_max(
      "test_field",
      5.0,
      min_value=None,
      max_value=None,
      errors={},
    )
    assert errors == {}

  def test_validate_entity_exists_empty_entity_id(self) -> None:
    """Test validate_entity_exists with empty entity_id."""
    mock_hass = MagicMock()
    errors = validate_entity_exists(
      hass=mock_hass,
      field="test_field",
      entity_id="",
      errors={},
    )
    assert errors == {"test_field": "entity_not_found"}

  def test_merge_errors_empty(self) -> None:
    """Test merge_errors with no arguments."""
    merged = merge_errors()
    assert merged == {}
