"""Tests for GPS defaults in the config flow."""

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from tests.helpers.homeassistant_test_stubs import MutableFlowResultDict

from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.flow_steps.gps import (
  DogGPSFlowMixin,
  GPSModuleDefaultsMixin,
)
from custom_components.pawcontrol.types import DOG_NAME_FIELD, DogConfigData


class _GPSDefaultsFlow(GPSModuleDefaultsMixin):
  def __init__(self, discovery_info: dict[str, str] | None) -> None:  # noqa: E111
    self._discovery_info = discovery_info or {}


class _DogGPSFlow(DogGPSFlowMixin):
  def __init__(self) -> None:  # noqa: E111
    self.hass = MagicMock()
    self._current_dog_config = {DOG_NAME_FIELD: "Buddy"}
    self._dogs = []
    self.shown_forms: list[MutableFlowResultDict] = []

  def _get_available_device_trackers(self) -> dict[str, str]:  # noqa: E111
    return {}

  def _get_available_person_entities(self) -> dict[str, str]:  # noqa: E111
    return {}

  async def async_step_add_dog(  # noqa: E111
    self,
    user_input: dict[str, Any] | None = None,
  ) -> MutableFlowResultDict:
    return cast(MutableFlowResultDict, {"type": "step_add_dog", "data": user_input})

  async def async_step_dog_feeding(  # noqa: E111
    self,
    user_input: dict[str, Any] | None = None,
  ) -> MutableFlowResultDict:
    return cast(MutableFlowResultDict, {"type": "step_dog_feeding", "data": user_input})

  async def async_step_dog_health(  # noqa: E111
    self,
    user_input: dict[str, Any] | None = None,
  ) -> MutableFlowResultDict:
    return cast(MutableFlowResultDict, {"type": "step_dog_health", "data": user_input})

  async def async_step_add_another_dog(  # noqa: E111
    self,
    user_input: dict[str, Any] | None = None,
  ) -> MutableFlowResultDict:
    return cast(
      MutableFlowResultDict,
      {"type": "step_add_another_dog", "data": user_input},
    )

  def async_show_form(  # noqa: E111
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
  """Discovery info should enable GPS defaults."""  # noqa: E111

  flow = _GPSDefaultsFlow({"source": "zeroconf"})  # noqa: E111
  assert flow._should_enable_gps(cast(DogConfigData, {})) is True  # noqa: E111


def test_should_enable_gps_for_large_dog() -> None:
  """Large dogs should enable GPS defaults."""  # noqa: E111

  flow = _GPSDefaultsFlow({})  # noqa: E111
  assert flow._should_enable_gps({"dog_size": "large"}) is True  # noqa: E111


def test_enhanced_modules_schema_sets_gps_default() -> None:
  """Schema defaults should reflect GPS enablement."""  # noqa: E111

  flow = _GPSDefaultsFlow({})  # noqa: E111
  schema = flow._get_enhanced_modules_schema({"dog_size": "giant"})  # noqa: E111
  result = schema({})  # noqa: E111
  assert result[MODULE_GPS] is True  # noqa: E111


@pytest.mark.asyncio
async def test_dog_gps_rejects_invalid_accuracy_type() -> None:
  """GPS config should flag invalid accuracy inputs."""  # noqa: E111

  flow = _DogGPSFlow()  # noqa: E111

  result = await flow.async_step_dog_gps({  # noqa: E111
    "gps_source": "manual",
    "gps_update_interval": 60,
    "gps_accuracy_filter": "fast",
    "enable_geofencing": True,
    "home_zone_radius": 50,
  })

  assert result["type"] == "form"  # noqa: E111
  assert result["errors"]["gps_accuracy_filter"] == "gps_accuracy_not_numeric"  # noqa: E111


@pytest.mark.asyncio
async def test_dog_gps_rejects_invalid_update_interval_type() -> None:
  """GPS config should flag invalid update interval inputs."""  # noqa: E111

  flow = _DogGPSFlow()  # noqa: E111

  result = await flow.async_step_dog_gps({  # noqa: E111
    "gps_source": "manual",
    "gps_update_interval": "fast",
    "gps_accuracy_filter": 20,
    "enable_geofencing": True,
    "home_zone_radius": 50,
  })

  assert result["type"] == "form"  # noqa: E111
  assert result["errors"]["gps_update_interval"] == "gps_update_interval_not_numeric"  # noqa: E111


@pytest.mark.asyncio
async def test_dog_gps_rejects_update_interval_out_of_range() -> None:
  """GPS config should flag update interval range violations."""  # noqa: E111

  flow = _DogGPSFlow()  # noqa: E111

  result = await flow.async_step_dog_gps({  # noqa: E111
    "gps_source": "manual",
    "gps_update_interval": 999,
    "gps_accuracy_filter": 20,
    "enable_geofencing": True,
    "home_zone_radius": 50,
  })

  assert result["type"] == "form"  # noqa: E111
  assert result["errors"]["gps_update_interval"] == "gps_update_interval_out_of_range"  # noqa: E111


@pytest.mark.asyncio
async def test_dog_gps_requires_home_zone_radius() -> None:
  """GPS config should require a geofence radius."""  # noqa: E111

  flow = _DogGPSFlow()  # noqa: E111

  result = await flow.async_step_dog_gps({  # noqa: E111
    "gps_source": "manual",
    "gps_update_interval": 60,
    "gps_accuracy_filter": 5,
    "enable_geofencing": True,
    "home_zone_radius": " ",
  })

  assert result["type"] == "form"  # noqa: E111
  assert result["errors"]["home_zone_radius"] == "geofence_radius_required"  # noqa: E111


@pytest.mark.asyncio
async def test_dog_gps_rejects_home_zone_radius_out_of_range() -> None:
  """GPS config should flag geofence radius range violations."""  # noqa: E111

  flow = _DogGPSFlow()  # noqa: E111

  result = await flow.async_step_dog_gps({  # noqa: E111
    "gps_source": "manual",
    "gps_update_interval": 60,
    "gps_accuracy_filter": 5,
    "enable_geofencing": True,
    "home_zone_radius": 2,
  })

  assert result["type"] == "form"  # noqa: E111
  assert result["errors"]["home_zone_radius"] == "geofence_radius_out_of_range"  # noqa: E111


@pytest.mark.asyncio
async def test_dog_gps_accepts_boundary_values() -> None:
  """GPS config should accept min/max boundaries."""  # noqa: E111

  flow = _DogGPSFlow()  # noqa: E111

  result = await flow.async_step_dog_gps({  # noqa: E111
    "gps_source": "manual",
    "gps_update_interval": 5,
    "gps_accuracy_filter": 5,
    "enable_geofencing": True,
    "home_zone_radius": 10,
  })

  assert result["type"] == "step_dog_feeding"  # noqa: E111
