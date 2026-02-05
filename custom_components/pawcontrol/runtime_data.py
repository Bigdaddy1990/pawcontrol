"""Runtime data helpers for the PawControl integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping
from typing import Literal, cast, overload

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .types import (
  DomainRuntimeStore,
  DomainRuntimeStoreEntry,
  PawControlConfigEntry,
  PawControlRuntimeData,
  RuntimeStoreCompatibilitySnapshot,
  RuntimeStoreEntrySnapshot,
  RuntimeStoreEntryStatus,
  RuntimeStoreOverallStatus,
)

_LOGGER = logging.getLogger(__name__)

_ENTRY_VERSION_ATTR = "_pawcontrol_runtime_store_version"
_ENTRY_CREATED_VERSION_ATTR = "_pawcontrol_runtime_store_created_version"


def _resolve_entry_id(entry_or_id: PawControlConfigEntry | str) -> str:
  """Return the entry identifier for ``entry_or_id``."""

  return entry_or_id if isinstance(entry_or_id, str) else entry_or_id.entry_id


def _get_entry(
  hass: HomeAssistant,
  entry_or_id: PawControlConfigEntry | str,
) -> PawControlConfigEntry | None:
  """Resolve a config entry from ``entry_or_id`` when available."""

  if isinstance(entry_or_id, str):
    entry = hass.config_entries.async_get_entry(entry_or_id)
    if entry is None or entry.domain != DOMAIN:
      return None
    return cast(PawControlConfigEntry, entry)

  return entry_or_id


@overload
def _get_domain_store(
  hass: HomeAssistant,
  *,
  create: Literal[True],
) -> DomainRuntimeStore: ...


@overload
def _get_domain_store(
  hass: HomeAssistant,
  *,
  create: Literal[False],
) -> DomainRuntimeStore | None: ...


def _get_domain_store(
  hass: HomeAssistant,
  *,
  create: bool,
) -> DomainRuntimeStore | None:
  """Return the PawControl storage dictionary from ``hass.data``."""

  domain_data: object
  domain_data = (
    hass.data.setdefault(
      DOMAIN,
      {},
    )
    if create
    else hass.data.get(DOMAIN)
  )

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


def _stamp_runtime_schema(
  entry_id: str,
  runtime_data: PawControlRuntimeData,
) -> tuple[int, int]:
  """Ensure runtime payloads carry compatible schema metadata."""

  schema_version = _coerce_version(
    getattr(runtime_data, "schema_version", None),
  )
  created_schema_version = _coerce_version(
    getattr(runtime_data, "schema_created_version", None),
  )

  if schema_version is None:
    schema_version = DomainRuntimeStoreEntry.CURRENT_VERSION
  if created_schema_version is None:
    created_schema_version = schema_version

  if schema_version > DomainRuntimeStoreEntry.CURRENT_VERSION or (
    created_schema_version > DomainRuntimeStoreEntry.CURRENT_VERSION
  ):
    raise RuntimeDataIncompatibleError(
      "Future runtime schema detected for "
      f"{entry_id} (got schema={schema_version} "
      f"created={created_schema_version}, "
      f"current={DomainRuntimeStoreEntry.CURRENT_VERSION})",
    )

  if created_schema_version < DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION:
    _LOGGER.debug(
      "Upgrading runtime schema origin for %s from %s to %s",
      entry_id,
      created_schema_version,
      DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION,
    )
    created_schema_version = DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION

  if schema_version < DomainRuntimeStoreEntry.CURRENT_VERSION:
    _LOGGER.debug(
      "Upgrading runtime schema version for %s from %s to %s",
      entry_id,
      schema_version,
      DomainRuntimeStoreEntry.CURRENT_VERSION,
    )
    schema_version = DomainRuntimeStoreEntry.CURRENT_VERSION

  runtime_data.schema_created_version = created_schema_version
  runtime_data.schema_version = schema_version

  return schema_version, created_schema_version


def _as_store_entry(value: object | None) -> DomainRuntimeStoreEntry | None:
  """Return a :class:`DomainRuntimeStoreEntry` if ``value`` resembles one."""

  if isinstance(value, DomainRuntimeStoreEntry):
    return value

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
      created_version = _coerce_version(
        mapping_value.get("created_version"),
      )
      if version is None:
        return DomainRuntimeStoreEntry(runtime_data=runtime_data)
      if created_version is None:
        created_version = version
      return DomainRuntimeStoreEntry(
        runtime_data=runtime_data,
        version=version,
        created_version=created_version,
      )

    return None

  if getattr(value_cls, "__module__", "") != DomainRuntimeStoreEntry.__module__:
    return None

  runtime_candidate = getattr(value, "runtime_data", None)
  runtime_data = _as_runtime_data(runtime_candidate)
  if runtime_data is None:
    return None

  version = _coerce_version(getattr(value, "version", None))
  created_version = _coerce_version(getattr(value, "created_version", None))
  if version is None:
    return DomainRuntimeStoreEntry(runtime_data=runtime_data)
  if created_version is None:
    created_version = version
  return DomainRuntimeStoreEntry(
    runtime_data=runtime_data,
    version=version,
    created_version=created_version,
  )


def _resolve_entry_status(
  *,
  available: bool,
  version: int | None,
  created_version: int | None,
) -> RuntimeStoreEntryStatus:
  """Return a :class:`RuntimeStoreEntryStatus` for runtime metadata."""

  if not available:
    return "missing"

  if version is None or created_version is None:
    return "unstamped"

  if version > DomainRuntimeStoreEntry.CURRENT_VERSION or (
    created_version is not None
    and created_version > DomainRuntimeStoreEntry.CURRENT_VERSION
  ):
    return "future_incompatible"

  if created_version < DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION:
    return "legacy_upgrade_required"

  if version != DomainRuntimeStoreEntry.CURRENT_VERSION:
    return "upgrade_pending"

  return "current"


def _build_runtime_store_snapshot(
  *,
  available: bool,
  version: int | None,
  created_version: int | None,
) -> RuntimeStoreEntrySnapshot:
  """Create a snapshot dictionary for runtime store metadata."""

  status = _resolve_entry_status(
    available=available,
    version=version,
    created_version=created_version,
  )
  snapshot: RuntimeStoreEntrySnapshot = {
    "available": available,
    "version": version,
    "created_version": created_version,
    "status": status,
  }
  return snapshot


def _cleanup_domain_store(
  hass: HomeAssistant,
  store: DomainRuntimeStore | None,
) -> None:
  """Remove the PawControl domain store when it no longer holds entries."""

  if store is not None and not store:
    hass.data.pop(DOMAIN, None)


def _get_store_entry_from_entry(
  entry: PawControlConfigEntry | None,
) -> DomainRuntimeStoreEntry | None:
  """Return a runtime store entry reconstructed from the config entry."""

  if entry is None:
    return None

  runtime = getattr(entry, "runtime_data", None)
  runtime_data = _as_runtime_data(runtime)
  if runtime_data is None:
    return None

  schema_version, schema_created_version = _stamp_runtime_schema(
    entry.entry_id,
    runtime_data,
  )
  version = _coerce_version(getattr(entry, _ENTRY_VERSION_ATTR, None))
  if version is None:
    version = schema_version

  created_version = _coerce_version(
    getattr(entry, _ENTRY_CREATED_VERSION_ATTR, None),
  )
  if created_version is None:
    created_version = schema_created_version

  return DomainRuntimeStoreEntry(
    runtime_data=runtime_data,
    version=version,
    created_version=created_version,
  )


def _apply_entry_metadata(
  entry: PawControlConfigEntry,
  store_entry: DomainRuntimeStoreEntry,
) -> None:
  """Persist runtime metadata on the config entry."""

  entry.runtime_data = store_entry.unwrap()
  setattr(entry, _ENTRY_VERSION_ATTR, store_entry.version)
  setattr(entry, _ENTRY_CREATED_VERSION_ATTR, store_entry.created_version)


def _detach_runtime_from_entry(entry: PawControlConfigEntry | None) -> None:
  """Remove runtime data from an entry to avoid stale references."""

  if entry is None:
    return

  if hasattr(entry, "runtime_data"):
    entry.runtime_data = None
  if hasattr(entry, _ENTRY_VERSION_ATTR):
    setattr(entry, _ENTRY_VERSION_ATTR, None)
  if hasattr(entry, _ENTRY_CREATED_VERSION_ATTR):
    setattr(entry, _ENTRY_CREATED_VERSION_ATTR, None)


def _normalise_store_entry(
  entry_id: str,
  store_entry: DomainRuntimeStoreEntry,
) -> DomainRuntimeStoreEntry:
  """Ensure ``store_entry`` aligns with the supported schema version."""

  if store_entry.is_future_version():
    raise RuntimeDataIncompatibleError(
      "Future runtime store schema detected for "
      f"{entry_id} (got version={store_entry.version} "
      f"created={store_entry.created_version}, "
      f"current={DomainRuntimeStoreEntry.CURRENT_VERSION})",
    )

  schema_version, schema_created_version = _stamp_runtime_schema(
    entry_id,
    store_entry.runtime_data,
  )

  created_version = max(store_entry.created_version, schema_created_version)
  if created_version < DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION:
    _LOGGER.debug(
      "Upgrading legacy runtime store entry for %s from schema %s",
      entry_id,
      created_version,
    )
    created_version = DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION

  version = max(store_entry.version, schema_version)
  if version < DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION:
    version = DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION

  upgraded_entry = DomainRuntimeStoreEntry(
    runtime_data=store_entry.runtime_data,
    version=version,
    created_version=created_version,
  )

  return upgraded_entry.ensure_current()


def store_runtime_data(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
  runtime_data: PawControlRuntimeData,
) -> None:
  """Attach runtime data to the config entry and hass.data store."""

  entry.runtime_data = runtime_data
  store = _get_domain_store(hass, create=True)
  store[entry.entry_id] = DomainRuntimeStoreEntry(runtime_data=runtime_data)


def get_runtime_data(
  hass: HomeAssistant,
  entry_or_id: PawControlConfigEntry | str,
  *,
  raise_on_incompatible: bool = False,
) -> PawControlRuntimeData | None:
  """Return the runtime data associated with a config entry."""

  del raise_on_incompatible
  entry = _get_entry(hass, entry_or_id)
  entry_id = _resolve_entry_id(entry_or_id)

  if entry is not None:
    runtime_data = _as_runtime_data(getattr(entry, "runtime_data", None))
    if runtime_data is not None:
      store = _get_domain_store(hass, create=True)
      store[entry.entry_id] = DomainRuntimeStoreEntry(runtime_data=runtime_data)
      return runtime_data

  store = _get_domain_store(hass, create=False)
  if store is None:
    return None

  store_entry = _as_store_entry(store.get(entry_id))
  if store_entry is None:
    return None

  runtime_data = store_entry.runtime_data
  if entry is not None:
    entry.runtime_data = runtime_data
  return runtime_data


def describe_runtime_store_status(
  hass: HomeAssistant,
  entry_or_id: PawControlConfigEntry | str,
) -> RuntimeStoreCompatibilitySnapshot:
  """Return a compatibility summary for runtime store metadata."""

  entry = _get_entry(hass, entry_or_id)
  entry_id = _resolve_entry_id(entry_or_id)

  entry_runtime = _as_runtime_data(getattr(entry, "runtime_data", None))
  entry_version = (
    _coerce_version(getattr(entry, _ENTRY_VERSION_ATTR, None))
    if entry is not None
    else None
  )
  entry_created_version = (
    _coerce_version(getattr(entry, _ENTRY_CREATED_VERSION_ATTR, None))
    if entry is not None
    else None
  )

  entry_snapshot = _build_runtime_store_snapshot(
    available=entry_runtime is not None,
    version=entry_version,
    created_version=entry_created_version,
  )

  store_runtime: PawControlRuntimeData | None = None
  store_version: int | None = None
  store_created_version: int | None = None

  store = _get_domain_store(hass, create=False)
  store_value: object | None = None
  if store is not None:
    store_value = store.get(entry_id)

  if isinstance(store_value, DomainRuntimeStoreEntry):
    store_runtime = store_value.runtime_data
    store_version = store_value.version
    store_created_version = store_value.created_version
  elif isinstance(store_value, Mapping):
    mapping_value = cast(Mapping[str, object], store_value)
    store_runtime = _as_runtime_data(mapping_value.get("runtime_data"))
    store_version = _coerce_version(mapping_value.get("version"))
    store_created_version = _coerce_version(
      mapping_value.get("created_version"),
    )
  else:
    store_runtime = _as_runtime_data(store_value)

  store_snapshot = _build_runtime_store_snapshot(
    available=store_runtime is not None,
    version=store_version,
    created_version=store_created_version,
  )

  divergence_detected = (
    entry_snapshot.get("available")
    and store_snapshot.get("available")
    and entry_runtime is not None
    and store_runtime is not None
    and entry_runtime is not store_runtime
  )

  entry_status = cast(RuntimeStoreEntryStatus, entry_snapshot["status"])
  store_status = cast(RuntimeStoreEntryStatus, store_snapshot["status"])

  statuses: set[RuntimeStoreEntryStatus] = {entry_status, store_status}
  entry_available = bool(entry_snapshot.get("available"))
  store_available = bool(store_snapshot.get("available"))

  overall_status: RuntimeStoreOverallStatus
  if "future_incompatible" in statuses:
    overall_status = "future_incompatible"
  elif {
    "legacy_upgrade_required",
    "upgrade_pending",
    "unstamped",
  } & statuses:
    overall_status = "needs_migration"
  elif divergence_detected:
    overall_status = "diverged"
  elif entry_available and not store_available:
    overall_status = "detached_store"
  elif store_available and not entry_available:
    overall_status = "detached_entry"
  elif not entry_available and not store_available:
    overall_status = "missing"
  else:
    overall_status = "current"

  return {
    "entry_id": entry_id,
    "status": overall_status,
    "current_version": DomainRuntimeStoreEntry.CURRENT_VERSION,
    "minimum_compatible_version": (DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION),
    "entry": entry_snapshot,
    "store": store_snapshot,
    "divergence_detected": bool(divergence_detected),
  }


def pop_runtime_data(
  hass: HomeAssistant,
  entry_or_id: PawControlConfigEntry | str,
) -> PawControlRuntimeData | None:
  """Remove and return runtime data for a config entry if present."""

  entry = _get_entry(hass, entry_or_id)
  entry_id = _resolve_entry_id(entry_or_id)

  runtime_data = (
    _as_runtime_data(getattr(entry, "runtime_data", None)) if entry else None
  )
  if entry is not None:
    _detach_runtime_from_entry(entry)

  store = _get_domain_store(hass, create=False)
  if store is not None:
    store_entry = _as_store_entry(store.pop(entry_id, None))
    _cleanup_domain_store(hass, store)
    if runtime_data is None and store_entry is not None:
      runtime_data = store_entry.runtime_data

  return runtime_data


class RuntimeDataUnavailableError(HomeAssistantError):
  """Raised when PawControl runtime data cannot be resolved."""


class RuntimeDataIncompatibleError(RuntimeDataUnavailableError):
  """Raised when a runtime payload targets an unsupported schema version."""


def require_runtime_data(
  hass: HomeAssistant,
  entry_or_id: PawControlConfigEntry | str,
) -> PawControlRuntimeData:
  """Return runtime data or raise when unavailable."""

  runtime = get_runtime_data(hass, entry_or_id, raise_on_incompatible=True)
  if runtime is None:
    entry_id = (
      entry_or_id
      if isinstance(entry_or_id, str)
      else getattr(entry_or_id, "entry_id", "unknown")
    )
    raise RuntimeDataUnavailableError(
      f"Runtime data unavailable for PawControl entry {entry_id}",
    )
  return runtime
