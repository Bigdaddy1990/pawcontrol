"""Compatibility helpers for optional Home Assistant features.

This module provides local fallbacks for enums and data classes that are
available in Home Assistant but may be absent in the minimal test environment.
"""

from __future__ import annotations

from enum import StrEnum

# EntityCategory -------------------------------------------------------------------------
try:  # pragma: no cover - exercised in Home Assistant runtime
    from homeassistant.helpers import entity as ha_entity
except Exception:  # pragma: no cover - used in tests without Home Assistant
    ha_entity = None

if ha_entity and hasattr(ha_entity, "EntityCategory"):
    EntityCategory = ha_entity.EntityCategory  # type: ignore[assignment]
else:  # pragma: no cover - fallback for tests

    class EntityCategory(StrEnum):
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    if ha_entity is not None:
        ha_entity.EntityCategory = EntityCategory  # type: ignore[attr-defined]


# DeviceInfo ----------------------------------------------------------------------------
try:  # pragma: no cover - exercised in Home Assistant runtime
    from homeassistant.helpers import device_registry as ha_dr
except Exception:  # pragma: no cover - used in tests without Home Assistant
    ha_dr = None


class DeviceInfo(dict):
    """Device info container with attribute access."""

    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


if ha_dr is not None and not hasattr(ha_dr, "DeviceInfo"):
    ha_dr.DeviceInfo = DeviceInfo  # type: ignore[attr-defined]
