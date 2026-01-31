"""Unit tests for config flow placeholder builders."""

from __future__ import annotations

from types import MappingProxyType

import pytest
from custom_components.pawcontrol.config_flow_placeholders import (
  _build_add_another_placeholders,
  _build_add_dog_summary_placeholders,
  _build_dog_modules_form_placeholders,
)
from custom_components.pawcontrol.config_flow_dogs import (
  _build_add_another_summary_placeholders,
  _build_add_dog_placeholders,
  _build_dog_feeding_placeholders,
  _build_dog_modules_placeholders,
  _build_module_setup_placeholders,
)
from custom_components.pawcontrol.flows.gps_helpers import build_dog_gps_placeholders
from custom_components.pawcontrol.flows.health_helpers import build_dog_health_placeholders


@pytest.mark.unit
def test_build_add_dog_placeholders_returns_mapping_proxy() -> None:
  """The add-dog helper should return an immutable mapping with typed values."""

  placeholders = _build_add_dog_placeholders(
    dog_count=2,
    max_dogs=5,
    current_dogs="Buddy, Luna",
    remaining_spots=3,
  )

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["dog_count"] == 2
  assert placeholders["max_dogs"] == 5
  assert placeholders["current_dogs"] == "Buddy, Luna"
  assert placeholders["remaining_spots"] == 3


@pytest.mark.unit
def test_build_dog_modules_placeholders_is_immutable() -> None:
  """The module placeholder helper should expose dog metadata as-is."""

  placeholders = _build_dog_modules_placeholders(
    dog_name="Buddy",
    dog_size="large",
    dog_age=7,
  )

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["dog_name"] == "Buddy"
  assert placeholders["dog_size"] == "large"
  assert placeholders["dog_age"] == 7


@pytest.mark.unit
def test_build_add_dog_summary_placeholders_normalises_counts() -> None:
  """Counts should be rendered as strings for translation placeholders."""

  placeholders = _build_add_dog_summary_placeholders(
    dogs_configured=1,
    max_dogs=4,
    discovery_hint="gps_discovered",
  )

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["dogs_configured"] == "1"
  assert placeholders["max_dogs"] == "4"
  assert placeholders["discovery_hint"] == "gps_discovered"


@pytest.mark.unit
def test_build_dog_modules_form_placeholders_returns_strings() -> None:
  """Module placeholders should coerce counts to strings and keep defaults."""

  placeholders = _build_dog_modules_form_placeholders(
    dog_name="Luna",
    dogs_configured=3,
    smart_defaults="GPS enabled",
  )

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["dog_name"] == "Luna"
  assert placeholders["dogs_configured"] == "3"
  assert placeholders["smart_defaults"] == "GPS enabled"


@pytest.mark.unit
def test_build_add_another_placeholders_encodes_flags() -> None:
  """The add-another helper should encode boolean flags consistently."""

  placeholders = _build_add_another_placeholders(
    dogs_configured=2,
    dogs_list="Buddy, Luna",
    can_add_more=False,
    max_dogs=6,
    performance_note="note",
  )

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["dogs_configured"] == "2"
  assert placeholders["dogs_list"] == "Buddy, Luna"
  assert placeholders["can_add_more"] == "no"
  assert placeholders["max_dogs"] == "6"
  assert placeholders["performance_note"] == "note"


@pytest.mark.unit
def test_build_dog_gps_placeholders_returns_mapping_proxy() -> None:
  """GPS placeholders should expose the active dog name immutably."""

  placeholders = build_dog_gps_placeholders(dog_name="Buddy")

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["dog_name"] == "Buddy"


@pytest.mark.unit
def test_build_dog_feeding_placeholders_normalises_strings() -> None:
  """Feeding placeholders should coerce numeric values into strings."""

  placeholders = _build_dog_feeding_placeholders(
    dog_name="Luna",
    dog_weight="21.5",
    suggested_amount="320",
    portion_info="Automatic portion calculation: 320g per day",
  )

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["dog_name"] == "Luna"
  assert placeholders["dog_weight"] == "21.5"
  assert placeholders["suggested_amount"] == "320"
  assert placeholders["portion_info"] == "Automatic portion calculation: 320g per day"


@pytest.mark.unit
def test_build_dog_health_placeholders_encodes_metadata() -> None:
  """Health placeholders should carry the computed guidance strings."""

  placeholders = build_dog_health_placeholders(
    dog_name="Buddy",
    dog_age="5",
    dog_weight="24.0",
    suggested_ideal_weight="23.5",
    suggested_activity="moderate",
    medication_enabled="yes",
    bcs_info="Body Condition Score: 1=Emaciated, 5=Ideal, 9=Obese",
    special_diet_count="12",
    health_diet_info="Select diets",
  )

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["dog_name"] == "Buddy"
  assert placeholders["dog_age"] == "5"
  assert placeholders["dog_weight"] == "24.0"
  assert placeholders["suggested_ideal_weight"] == "23.5"
  assert placeholders["suggested_activity"] == "moderate"
  assert placeholders["medication_enabled"] == "yes"
  assert (
    placeholders["bcs_info"] == "Body Condition Score: 1=Emaciated, 5=Ideal, 9=Obese"
  )
  assert placeholders["special_diet_count"] == "12"
  assert placeholders["health_diet_info"] == "Select diets"


@pytest.mark.unit
def test_build_add_another_summary_placeholders_tracks_capacity() -> None:
  """The summary helper should expose counts and capacity flags."""

  placeholders = _build_add_another_summary_placeholders(
    dogs_list="Buddy, Luna",
    dog_count="2",
    max_dogs=6,
    remaining_spots=4,
    at_limit="false",
  )

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["dogs_list"] == "Buddy, Luna"
  assert placeholders["dog_count"] == "2"
  assert placeholders["max_dogs"] == 6
  assert placeholders["remaining_spots"] == 4
  assert placeholders["at_limit"] == "false"


@pytest.mark.unit
def test_build_module_setup_placeholders_is_immutable() -> None:
  """Module overview placeholders should return a mapping proxy."""

  placeholders = _build_module_setup_placeholders(
    total_dogs="2",
    gps_dogs="1",
    health_dogs="2",
    suggested_performance="balanced",
    complexity_info="info",
    next_step_info="Next",
  )

  assert isinstance(placeholders, MappingProxyType)
  assert placeholders["total_dogs"] == "2"
  assert placeholders["gps_dogs"] == "1"
  assert placeholders["health_dogs"] == "2"
  assert placeholders["suggested_performance"] == "balanced"
  assert placeholders["complexity_info"] == "info"
  assert placeholders["next_step_info"] == "Next"
