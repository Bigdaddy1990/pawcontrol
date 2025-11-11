"""Runtime data helpers for the PawControl integration."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import cast

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .types import (
    DomainRuntimeStore,
    DomainRuntimeStoreEntry,
    PawControlConfigEntry,
    PawControlRuntimeData,
)


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

    domain_data: object
    domain_data = hass.data.setdefault(DOMAIN, {}) if create else hass.data.get(DOMAIN)

    if not isinstance(domain_data, MutableMapping):
        if not create:
            hass.data.pop(DOMAIN, None)
            return None
        domain_data = {}
        hass.data[DOMAIN] = domain_data

    return cast(DomainRuntimeStore, domain_data)


def _as_runtime_data(value: object | None) -> PawControlRuntimeData | None:
    """Return ``value`` when it looks like runtime data, otherwise ``None``."""

    if isinstance(value, PawControlRuntimeData):
        return value

    if value is None:
        return None

    value_cls = getattr(value, "__class__", None)
    if value_cls is None:
        return None

    if getattr(value_cls, "__name__", "") != "PawControlRuntimeData":
        return None

    if getattr(value_cls, "__module__", "") != PawControlRuntimeData.__module__:
        return None

    return cast(PawControlRuntimeData, value)


def _coerce_version(candidate: object | None) -> int | None:
    """Return a positive integer version extracted from ``candidate``."""

    if isinstance(candidate, bool):
        return None
    if isinstance(candidate, int) and candidate > 0:
        return candidate
    return None


def _as_store_entry(value: object | None) -> DomainRuntimeStoreEntry | None:
    """Return a :class:`DomainRuntimeStoreEntry` if ``value`` resembles one."""

    if isinstance(value, DomainRuntimeStoreEntry):
        return value.ensure_current()

    if value is None:
        return None

    runtime_data = _as_runtime_data(value)
    if runtime_data is not None:
        return DomainRuntimeStoreEntry(runtime_data=runtime_data)

    value_cls = getattr(value, "__class__", None)
    if value_cls is None:
        return None

    if getattr(value_cls, "__name__", "") != "DomainRuntimeStoreEntry":
        if isinstance(value, Mapping):
            mapping_value: Mapping[str, object]
            mapping_value = cast(Mapping[str, object], value)
            runtime_candidate = mapping_value.get("runtime_data")
            runtime_data = _as_runtime_data(runtime_candidate)
            if runtime_data is None:
                return None

            version = _coerce_version(mapping_value.get("version"))
            if version is None:
                return DomainRuntimeStoreEntry(runtime_data=runtime_data)
            return DomainRuntimeStoreEntry(runtime_data=runtime_data, version=version)

        return None

    if getattr(value_cls, "__module__", "") != DomainRuntimeStoreEntry.__module__:
        return None

    runtime_candidate = getattr(value, "runtime_data", None)
    runtime_data = _as_runtime_data(runtime_candidate)
    if runtime_data is None:
        return None

    version = _coerce_version(getattr(value, "version", None))
    if version is None:
        return DomainRuntimeStoreEntry(runtime_data=runtime_data)
    return DomainRuntimeStoreEntry(runtime_data=runtime_data, version=version)


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
    return _as_runtime_data(runtime)


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

    store = _get_domain_store(hass, create=True)
    store[entry.entry_id] = DomainRuntimeStoreEntry(
        runtime_data=runtime_data
    ).ensure_current()


def get_runtime_data(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlRuntimeData | None:
    """Return the runtime data associated with a config entry."""

    entry = _get_entry(hass, entry_or_id)
    runtime = _get_runtime_from_entry(entry)
    if runtime is not None:
        if entry is not None:
            store = _get_domain_store(hass, create=True)
            if store is not None:
                current_entry = DomainRuntimeStoreEntry(
                    runtime_data=runtime
                ).ensure_current()
                existing_entry = _as_store_entry(store.get(entry.entry_id))
                if (
                    existing_entry is None
                    or existing_entry.unwrap() is not runtime
                    or existing_entry.version != current_entry.version
                ):
                    store[entry.entry_id] = current_entry
        return runtime

    entry_id = _resolve_entry_id(entry_or_id)
    store = _get_domain_store(hass, create=False)
    if store is None:
        return None

    store_entry = _as_store_entry(store.get(entry_id))
    if store_entry is None:
        if store.pop(entry_id, None) is not None:
            _cleanup_domain_store(hass, store)
        return None

    current_entry = store_entry.ensure_current()
    store[entry_id] = current_entry

    runtime_data = current_entry.unwrap()
    if entry is not None:
        entry.runtime_data = runtime_data
    return runtime_data


def pop_runtime_data(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlRuntimeData | None:
    """Remove and return runtime data for a config entry if present."""

    entry = _get_entry(hass, entry_or_id)
    runtime_data = _get_runtime_from_entry(entry)
    if runtime_data is not None:
        _detach_runtime_from_entry(entry)
        store = _get_domain_store(hass, create=False)
        if store is not None and entry is not None:
            entry_id = entry.entry_id
            if store.pop(entry_id, None) is not None:
                _cleanup_domain_store(hass, store)
        return runtime_data

    entry_id = _resolve_entry_id(entry_or_id)
    store = _get_domain_store(hass, create=False)
    store_runtime: PawControlRuntimeData | None = None
    if store is not None:
        value = store.pop(entry_id, None)
        store_entry = _as_store_entry(value)
        if store_entry is not None:
            store_runtime = store_entry.ensure_current().unwrap()
        _cleanup_domain_store(hass, store)

    return store_runtime


class RuntimeDataUnavailableError(HomeAssistantError):
    """Raised when PawControl runtime data cannot be resolved."""


def require_runtime_data(
    hass: HomeAssistant, entry_or_id: PawControlConfigEntry | str
) -> PawControlRuntimeData:
    """Return runtime data or raise when unavailable."""

    runtime = get_runtime_data(hass, entry_or_id)
    if runtime is None:
        entry_id = (
            entry_or_id
            if isinstance(entry_or_id, str)
            else getattr(entry_or_id, "entry_id", "unknown")
        )
        raise RuntimeDataUnavailableError(
            f"Runtime data unavailable for PawControl entry {entry_id}"
        )
    return runtime
