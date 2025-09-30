"""Runtime data helpers for the PawControl integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .types import PawControlConfigEntry, PawControlRuntimeData


def store_runtime_data(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    runtime_data: PawControlRuntimeData,
) -> None:
    """Store runtime data in ``hass.data`` for the given config entry."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = runtime_data


def get_runtime_data(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlRuntimeData | None:
    """Return the runtime data associated with a config entry."""

    entry_id = entry_or_id if isinstance(entry_or_id, str) else entry_or_id.entry_id
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return None

    data: Any = domain_data.get(entry_id)
    if isinstance(data, PawControlRuntimeData):
        return data

    if isinstance(data, dict):
        candidate = data.get("runtime_data")
        if isinstance(candidate, PawControlRuntimeData):
            return candidate

    return None


def pop_runtime_data(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlRuntimeData | None:
    """Remove and return runtime data for a config entry if present."""

    entry_id = entry_or_id if isinstance(entry_or_id, str) else entry_or_id.entry_id
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return None

    data: Any = domain_data.pop(entry_id, None)
    if isinstance(data, PawControlRuntimeData):
        return data

    if isinstance(data, dict):
        candidate = data.get("runtime_data")
        if isinstance(candidate, PawControlRuntimeData):
            return candidate

    return None
