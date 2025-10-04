"""Runtime data helpers for the PawControl integration."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any, cast

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .types import PawControlConfigEntry, PawControlRuntimeData

DomainRuntimeStore = MutableMapping[str, PawControlRuntimeData | Mapping[str, Any]]


def _resolve_entry_id(entry_or_id: PawControlConfigEntry | str) -> str:
    """Return the entry identifier for ``entry_or_id``."""

    return entry_or_id if isinstance(entry_or_id, str) else entry_or_id.entry_id


def _get_domain_store(
    hass: HomeAssistant, *, create: bool
) -> DomainRuntimeStore | None:
    """Return the PawControl storage dictionary from ``hass.data``."""

    domain_data: Any
    domain_data = hass.data.setdefault(DOMAIN, {}) if create else hass.data.get(DOMAIN)

    if not isinstance(domain_data, MutableMapping):
        if not create:
            return None
        domain_data = {}
        hass.data[DOMAIN] = domain_data

    return cast(DomainRuntimeStore, domain_data)


def _coerce_runtime_data(value: Any) -> PawControlRuntimeData | None:
    """Return a :class:`PawControlRuntimeData` instance if one is embedded."""

    match value:
        case PawControlRuntimeData() as data:
            return data

        case {"runtime_data": PawControlRuntimeData() as data}:
            return data

    return None


def store_runtime_data(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    runtime_data: PawControlRuntimeData,
) -> None:
    """Store runtime data in ``hass.data`` for the given config entry."""

    store = _get_domain_store(hass, create=True)
    assert store is not None  # Satisfies the type checker
    store[entry.entry_id] = runtime_data


def get_runtime_data(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlRuntimeData | None:
    """Return the runtime data associated with a config entry."""

    entry_id = _resolve_entry_id(entry_or_id)
    store = _get_domain_store(hass, create=False)
    if not store:
        return None

    return _coerce_runtime_data(store.get(entry_id))


def pop_runtime_data(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlRuntimeData | None:
    """Remove and return runtime data for a config entry if present."""

    entry_id = _resolve_entry_id(entry_or_id)
    store = _get_domain_store(hass, create=False)
    if not store:
        return None

    value = store.pop(entry_id, None)
    return _coerce_runtime_data(value)
