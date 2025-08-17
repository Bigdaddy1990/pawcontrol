"""Compatibility helpers for optional Home Assistant features.

This module provides local fallbacks for enums and data classes that are
available in Home Assistant but may be absent in the minimal test environment.
"""

from __future__ import annotations

try:  # pragma: no cover - Python 3.11+
    from enum import StrEnum
except Exception:  # pragma: no cover - Python <3.11 fallback
    from enum import Enum

    class StrEnum(str, Enum):
        """Minimal ``StrEnum`` backport for older Python versions."""

        pass

from typing import Any

# EntityCategory -------------------------------------------------------------------------
try:  # pragma: no cover - exercised in Home Assistant runtime
    from homeassistant.helpers import entity as ha_entity
except Exception:  # pragma: no cover - used in tests without Home Assistant
    ha_entity = None

if ha_entity and hasattr(ha_entity, "EntityCategory"):
    EntityCategory = ha_entity.EntityCategory  # type: ignore[assignment]
else:  # pragma: no cover - fallback for tests

    class _EntityCategory(StrEnum):
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    EntityCategory = _EntityCategory
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


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
#
# Newer versions of Home Assistant remove a number of constants from
# ``homeassistant.const``.  The integration under test still imports these
# names, and the tests exercise the fallback behaviour when they are not
# provided by Home Assistant.  To keep the modules importable in this minimal
# environment we provide local definitions and, when possible, inject them back
# into ``homeassistant.const`` so that submodules importing from there continue
# to work.  Only the small subset used in tests is implemented here.

try:  # pragma: no cover - exercised when Home Assistant is installed
    from homeassistant import const as ha_const
except Exception:  # pragma: no cover - used in tests without Home Assistant
    ha_const = None  # type: ignore[assignment]


def _ensure_const(name: str, value: StrEnum | str) -> Any:
    """Return ``getattr(ha_const, name)`` or ``value`` if missing.

    When Home Assistant is available we also write the fallback value back to
    ``homeassistant.const`` so that any module importing the constant from
    there sees the same value.
    """

    if ha_const is not None and hasattr(ha_const, name):  # pragma: no cover
        return getattr(ha_const, name)
    if ha_const is not None:  # pragma: no cover - runtime fallback
        setattr(ha_const, name, value)
    return value


# Common string constants used throughout the integration
_STRING_CONSTS: dict[str, StrEnum | str] = {
    "CONF_DEVICE_ID": "device_id",
    "CONF_EVENT_DATA": "event_data",
    "CONF_PLATFORM": "platform",
    "CONF_DOMAIN": "domain",
    "CONF_TYPE": "type",
    "EVENT_STATE_REPORTED": "state_reported",
}

globals().update({name: _ensure_const(name, value) for name, value in _STRING_CONSTS.items()})

__all__ = [
    "EntityCategory",
    "DeviceInfo",
    *list(_STRING_CONSTS.keys()),
    "UnitOfLength",
    "UnitOfMass",
    "UnitOfTime",
]


# ``UnitOfLength`` was converted to an enum in newer Home Assistant versions.
try:  # pragma: no cover - Home Assistant provides the enum
    UnitOfLength = ha_const.UnitOfLength  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - tests without Home Assistant

    class _UnitOfLength(StrEnum):
        METERS = "m"

    UnitOfLength = _UnitOfLength
    if ha_const is not None:  # type: ignore[truthy-bool]
        ha_const.UnitOfLength = UnitOfLength  # type: ignore[attr-defined]

# ``UnitOfMass`` was converted to an enum in newer Home Assistant versions.
try:  # pragma: no cover - Home Assistant provides the enum
    UnitOfMass = ha_const.UnitOfMass  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - tests without Home Assistant

    class _UnitOfMass(StrEnum):
        GRAMS = "g"
        KILOGRAMS = "kg"

    UnitOfMass = _UnitOfMass
    if ha_const is not None:  # type: ignore[truthy-bool]
        ha_const.UnitOfMass = UnitOfMass  # type: ignore[attr-defined]

# ``UnitOfTime`` was converted to an enum in newer Home Assistant versions.
try:  # pragma: no cover - Home Assistant provides the enum
    UnitOfTime = ha_const.UnitOfTime  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - tests without Home Assistant

    class _UnitOfTime(StrEnum):
        SECONDS = "s"
        MINUTES = "min"
        HOURS = "h"

    UnitOfTime = _UnitOfTime
    if ha_const is not None:  # type: ignore[truthy-bool]
        ha_const.UnitOfTime = UnitOfTime  # type: ignore[attr-defined]
