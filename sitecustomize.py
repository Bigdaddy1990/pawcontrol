"""Test environment compatibility helpers.

This module is loaded automatically by Python before any other imports. It
ensures that optional Home Assistant helpers exist when the test environment
provides a minimal stub of the framework.
"""

from __future__ import annotations

import sys
from enum import StrEnum
from types import ModuleType

try:  # pragma: no cover - Home Assistant available
    from homeassistant.helpers import device_registry, entity
except Exception:  # pragma: no cover - create minimal stubs
    ha = sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    helpers = ModuleType("homeassistant.helpers")
    ha.helpers = helpers  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers"] = helpers
    entity = ModuleType("homeassistant.helpers.entity")
    device_registry = ModuleType("homeassistant.helpers.device_registry")
    sys.modules["homeassistant.helpers.entity"] = entity
    sys.modules["homeassistant.helpers.device_registry"] = device_registry

if not hasattr(entity, "EntityCategory"):
    class EntityCategory(StrEnum):
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    entity.EntityCategory = EntityCategory  # type: ignore[attr-defined]

if not hasattr(device_registry, "DeviceInfo"):
    class DeviceInfo(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    device_registry.DeviceInfo = DeviceInfo  # type: ignore[attr-defined]

