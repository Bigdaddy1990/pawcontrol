"""Tests for GPS defaults in the config flow."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.flows.gps import DogGPSFlowMixin, GPSModuleDefaultsMixin
from custom_components.pawcontrol.types import DOG_NAME_FIELD, DogConfigData
from tests.helpers.homeassistant_test_stubs import MutableFlowResultDict


class _GPSDefaultsFlow(GPSModuleDefaultsMixin):
  def __init__(self, discovery_info: dict[str, str] | None) -> None:
    self._discovery_info = discovery_info or {}


class _DogGPSFlow(DogGPSFlowMixin):
  def __init__(self) -> None:
    self.hass = MagicMock()
    self._current_dog_config = {DOG_NAME_FIELD: "Buddy"}
    self._dogs = []
    self.shown_forms: list[MutableFlowResultDict] = []

  def _get_available_device_trackers(self) -> dict[str, str]:
    return {}

  def _get_available_person_entities(self) -> dict[str, str]:
    return {}

  async def async_step_add_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> MutableFlowResultDict:
    return cast(MutableFlowResultDict, {"type": "step_add_dog", "data": user_input})

  async def async_step_dog_feeding(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> MutableFlowResultDict:
    return cast(MutableFlowResultDict, {"type": "step_dog_feeding", "data": user_input})

  async def async_step_dog_health(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> MutableFlowResultDict:
    return cast(MutableFlowResultDict, {"type": "step_dog_health", "data": user_input})

  async def async_step_add_another_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> MutableFlowResultDict:
    return cast(
      MutableFlowResultDict,
      {"type": "step_add_another_dog", "data": user_input},
    )

  def async_show_form(
    self,
    *,
    step_id: str,
    data_schema: Any,
    errors: dict[str, str] | None = None,
    description_placeholders: dict[str, str] | None = None,
  ) -> MutableFlowResultDict:
    form_record = cast(
      MutableFlowResultDict,
      {
        "step_id": step_id,
        "schema": data_schema,
        "errors": errors or {},
        "description_placeholders": description_placeholders or {},
      },
    )
    self.shown_forms.append(form_record)
    return cast(MutableFlowResultDict, {"type": "form", **form_record})


def test_should_enable_gps_when_discovered() -> None:
  """Discovery info should enable GPS defaults."""

  flow = _GPSDefaultsFlow({"source": "zeroconf"})
  assert flow._should_enable_gps(cast(DogConfigData, {})) is True


def test_should_enable_gps_for_large_dog() -> None:
  """Large dogs should enable GPS defaults."""

  flow = _GPSDefaultsFlow({})
  assert flow._should_enable_gps({"dog_size": "large"}) is True


def test_enhanced_modules_schema_sets_gps_default() -> None:
  """Schema defaults should reflect GPS enablement."""

  flow = _GPSDefaultsFlow({})
  schema = flow._get_enhanced_modules_schema({"dog_size": "giant"})
  result = schema({})
  assert result[MODULE_GPS] is True


@pytest.mark.asyncio
async def test_dog_gps_rejects_invalid_accuracy_type() -> None:
  """GPS config should flag invalid accuracy inputs."""

  flow = _DogGPSFlow()

  result = await flow.async_step_dog_gps(
    {
      "gps_source": "manual",
      "gps_update_interval": 60,
      "gps_accuracy_filter": "fast",
      "enable_geofencing": True,
      "home_zone_radius": 50,
    }
  )

  assert result["type"] == "form"
  assert result["errors"]["gps_accuracy_filter"] == "gps_accuracy_not_numeric"


@pytest.mark.asyncio
async def test_dog_gps_requires_home_zone_radius() -> None:
  """GPS config should require a geofence radius."""

  flow = _DogGPSFlow()

  result = await flow.async_step_dog_gps(
    {
      "gps_source": "manual",
      "gps_update_interval": 60,
      "gps_accuracy_filter": 5,
      "enable_geofencing": True,
      "home_zone_radius": " ",
    }
  )

  assert result["type"] == "form"
  assert result["errors"]["home_zone_radius"] == "geofence_radius_required"


@pytest.mark.asyncio
async def test_dog_gps_accepts_boundary_values() -> None:
  """GPS config should accept min/max boundaries."""

  flow = _DogGPSFlow()

  result = await flow.async_step_dog_gps(
    {
      "gps_source": "manual",
      "gps_update_interval": 5,
      "gps_accuracy_filter": 5,
      "enable_geofencing": True,
      "home_zone_radius": 10,
    }
  )

  assert result["type"] == "step_dog_feeding"
