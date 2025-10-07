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


def _get_entry(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlConfigEntry | None:
    """Resolve a config entry from ``entry_or_id`` when available."""

    if isinstance(entry_or_id, str):
        entry = hass.config_entries.async_get_entry(entry_or_id)
        if entry is None or entry.domain != DOMAIN:
            return None
        return cast(PawControlConfigEntry, entry)

    return entry_or_id


def _get_domain_store(
    hass: HomeAssistant, *, create: bool
) -> DomainRuntimeStore | None:
    """Return the PawControl storage dictionary from ``hass.data``."""

    domain_data: Any
    domain_data = hass.data.setdefault(DOMAIN, {}) if create else hass.data.get(DOMAIN)

    if not isinstance(domain_data, MutableMapping):
        if not create:
            hass.data.pop(DOMAIN, None)
            return None
        domain_data = {}
        hass.data[DOMAIN] = domain_data

    return cast(DomainRuntimeStore, domain_data)


def _coerce_runtime_data(
    value: Any,
) -> tuple[PawControlRuntimeData | None, bool]:
    """Return runtime data and whether the store needs migration."""

    match value:
        case PawControlRuntimeData() as data:
            return data, False

        case {"runtime_data": PawControlRuntimeData() as data}:
            return data, True

    return None, False


def _cleanup_domain_store(
    hass: HomeAssistant, store: DomainRuntimeStore | None
) -> None:
    """Remove the PawControl domain store when it no longer holds entries."""

    if store is not None and not store:
        hass.data.pop(DOMAIN, None)


def _get_runtime_from_entry(
    entry: PawControlConfigEntry | None,
) -> PawControlRuntimeData | None:
    """Return runtime data stored on a config entry when available."""

    if entry is None:
        return None

    runtime = getattr(entry, "runtime_data", None)
    return runtime if isinstance(runtime, PawControlRuntimeData) else None


def _detach_runtime_from_entry(entry: PawControlConfigEntry | None) -> None:
    """Remove runtime data from an entry to avoid stale references."""

    if entry is None:
        return

    if hasattr(entry, "runtime_data"):
        entry.runtime_data = None


def store_runtime_data(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    runtime_data: PawControlRuntimeData,
) -> None:
    """Attach runtime data to the config entry and update compatibility caches."""

    entry.runtime_data = runtime_data

    store = _get_domain_store(hass, create=False)
    if store is None:
        return

    # Remove the compatibility payload for the entry we just populated so
    # ``get_runtime_data`` always prefers the config entry attribute.
    store.pop(entry.entry_id, None)

    # Normalise any remaining compatibility payloads for other entries.
    for key, value in list(store.items()):
        resolved, needs_migration = _coerce_runtime_data(value)
        if resolved is None:
            if needs_migration:
                store.pop(key, None)
            continue
        if needs_migration:
            store[key] = {"runtime_data": resolved}

    _cleanup_domain_store(hass, store)



def get_runtime_data(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlRuntimeData | None:
    """Return the runtime data associated with a config entry."""

    entry = _get_entry(hass, entry_or_id)
    runtime = _get_runtime_from_entry(entry)
    if runtime is not None:
        return runtime

    entry_id = _resolve_entry_id(entry_or_id)
    store = _get_domain_store(hass, create=False)
    if store is None:
        return None

    runtime_data, needs_migration = _coerce_runtime_data(store.get(entry_id))
    if runtime_data is not None:
        store.pop(entry_id, None)
        _cleanup_domain_store(hass, store)
        if entry is not None:
            entry.runtime_data = runtime_data
        return runtime_data

    if needs_migration:
        store.pop(entry_id, None)
        _cleanup_domain_store(hass, store)

    return None


def pop_runtime_data(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlRuntimeData | None:
    """Remove and return runtime data for a config entry if present."""

    entry = _get_entry(hass, entry_or_id)
    runtime_data = _get_runtime_from_entry(entry)
    if runtime_data is not None:
        _detach_runtime_from_entry(entry)
        return runtime_data

    entry_id = _resolve_entry_id(entry_or_id)
    store = _get_domain_store(hass, create=False)
    store_runtime: PawControlRuntimeData | None = None
    if store is not None:
        value = store.pop(entry_id, None)
        resolved_runtime, _needs_migration = _coerce_runtime_data(value)
        if resolved_runtime is not None:
            store_runtime = resolved_runtime
        _cleanup_domain_store(hass, store)

    return store_runtime
