"""GPS defaults for the PawControl config flow."""

from __future__ import annotations

from typing import Protocol

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_NOTIFICATIONS,
  MODULE_WALK,
)
from .types import ConfigFlowDiscoveryData, DogConfigData


class GPSDefaultsHost(Protocol):
  """Protocol describing the config flow host requirements."""

  _discovery_info: ConfigFlowDiscoveryData


class GPSModuleDefaultsMixin(GPSDefaultsHost):
  """Provide GPS-aware defaults for module selection."""

  def _get_enhanced_modules_schema(self, dog_config: DogConfigData) -> vol.Schema:
    """Get enhanced modules schema with smart defaults.

    Args:
        dog_config: Dog configuration

    Returns:
        Enhanced modules schema
    """
    # Smart defaults based on discovery info or dog characteristics
    defaults = {
      MODULE_FEEDING: True,
      MODULE_WALK: True,
      MODULE_HEALTH: True,
      MODULE_GPS: self._should_enable_gps(dog_config),
      MODULE_NOTIFICATIONS: True,
    }

    return vol.Schema(
      {
        vol.Optional(
          MODULE_FEEDING,
          default=defaults[MODULE_FEEDING],
        ): cv.boolean,
        vol.Optional(MODULE_WALK, default=defaults[MODULE_WALK]): cv.boolean,
        vol.Optional(
          MODULE_HEALTH,
          default=defaults[MODULE_HEALTH],
        ): cv.boolean,
        vol.Optional(MODULE_GPS, default=defaults[MODULE_GPS]): cv.boolean,
        vol.Optional(
          MODULE_NOTIFICATIONS,
          default=defaults[MODULE_NOTIFICATIONS],
        ): cv.boolean,
      },
    )

  def _should_enable_gps(self, dog_config: DogConfigData) -> bool:
    """Determine if GPS should be enabled by default.

    Args:
        dog_config: Dog configuration

    Returns:
        True if GPS should be enabled by default
    """
    # Enable GPS for discovered devices or large dogs
    if self._discovery_info:
      return True

    dog_size = dog_config.get("dog_size", "medium")
    return dog_size in {"large", "giant"}

  def _get_smart_module_defaults(self, dog_config: DogConfigData) -> str:
    """Get explanation for smart module defaults.

    Args:
        dog_config: Dog configuration

    Returns:
        Explanation text
    """
    reasons = []

    if self._discovery_info:
      reasons.append("GPS enabled due to discovered tracking device")

    dog_size = dog_config.get("dog_size", "medium")
    if dog_size in {"large", "giant"}:
      reasons.append("GPS recommended for larger dogs")

    return "; ".join(reasons) if reasons else "Standard defaults applied"
