"""Tests for GPS defaults in the config flow."""

from __future__ import annotations

from typing import cast

from custom_components.pawcontrol.config_flow_gps import GPSModuleDefaultsMixin
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.types import DogConfigData


class _GPSDefaultsFlow(GPSModuleDefaultsMixin):
  def __init__(self, discovery_info: dict[str, str] | None) -> None:
    self._discovery_info = discovery_info or {}


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
