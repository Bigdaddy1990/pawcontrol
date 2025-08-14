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


# ---------------------------------------------------------------------------
# Event loop compatibility
# ---------------------------------------------------------------------------
#
# Some of the tests exercise Home Assistant using ``pytest-anyio`` which
# creates a new running loop per test.  Home Assistant's default
# ``async_add_executor_job`` implementation schedules work on ``self.loop``
# which was created when the ``HomeAssistant`` instance was initialised and can
# therefore differ from the currently running loop.  Awaiting the resulting
# future from a different loop raises ``RuntimeError: Task ... got Future ...
# attached to a different loop``.  To keep the tests lightweight we replace the
# method with a version that always targets the running loop.
try:  # pragma: no cover - Home Assistant available in the test environment
    import asyncio

    from homeassistant.core import HomeAssistant

    if not hasattr(HomeAssistant, "_pawcontrol_executor_patch"):
        async def async_add_executor_job(self, func, *args):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, func, *args)

        HomeAssistant.async_add_executor_job = async_add_executor_job  # type: ignore[assignment]
        HomeAssistant._pawcontrol_executor_patch = True  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - Home Assistant not available
    pass


# Register the config flow class directly with Home Assistant's flow handler
# registry to avoid expensive integration discovery during tests.  This keeps
# ``hass.config_entries.flow.async_init("pawcontrol")`` working even when the
# loader cannot resolve the custom component from the filesystem in the minimal
# test environment.
try:  # pragma: no cover - import may fail when Home Assistant is absent
    from custom_components.pawcontrol import config_flow as paw_config_flow
    from homeassistant import config_entries

    if "pawcontrol" not in config_entries.HANDLERS:
        config_entries.HANDLERS["pawcontrol"] = paw_config_flow.PawControlConfigFlow
except Exception:  # pragma: no cover - ignore if either import fails
    pass
