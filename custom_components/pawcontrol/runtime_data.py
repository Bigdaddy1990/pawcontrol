"""Runtime data helpers for the PawControl integration."""

from collections.abc import Mapping, MutableMapping
import logging
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
  """Return the entry identifier for ``entry_or_id``."""  # noqa: E111

  return entry_or_id if isinstance(entry_or_id, str) else entry_or_id.entry_id  # noqa: E111


def _get_entry(
  hass: HomeAssistant,
  entry_or_id: PawControlConfigEntry | str,
) -> PawControlConfigEntry | None:
  """Resolve a config entry from ``entry_or_id`` when available."""  # noqa: E111

  if isinstance(entry_or_id, str):  # noqa: E111
    entry = hass.config_entries.async_get_entry(entry_or_id)
    if entry is None or entry.domain != DOMAIN:
      return None  # noqa: E111
    return cast(PawControlConfigEntry, entry)

  return entry_or_id  # noqa: E111


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
  """Return the PawControl storage dictionary from ``hass.data``."""  # noqa: E111

  data_obj = getattr(hass, "data", None)  # noqa: E111
  if not isinstance(data_obj, MutableMapping):  # noqa: E111
    if not create:
      return None  # noqa: E111
    data_obj = {}
    hass.data = data_obj

  domain_data: object  # noqa: E111
  domain_data = (  # noqa: E111
    data_obj.setdefault(
      DOMAIN,
      {},
    )
    if create
    else data_obj.get(DOMAIN)
  )

  if not isinstance(domain_data, MutableMapping):  # noqa: E111
    if not create:
      data_obj.pop(DOMAIN, None)  # noqa: E111
      return None  # noqa: E111
    domain_data = {}
    data_obj[DOMAIN] = domain_data

  return cast(DomainRuntimeStore, domain_data)  # noqa: E111


def _as_runtime_data(value: object | None) -> PawControlRuntimeData | None:
  """Return ``value`` when it looks like runtime data, otherwise ``None``."""  # noqa: E111

  if isinstance(value, PawControlRuntimeData):  # noqa: E111
    return value

  if value is None:  # noqa: E111
    return None

  value_cls = getattr(value, "__class__", None)  # noqa: E111
  if value_cls is None:  # noqa: E111
    return None

  if getattr(value_cls, "__name__", "") != "PawControlRuntimeData":  # noqa: E111
    return None

  if getattr(value_cls, "__module__", "") != PawControlRuntimeData.__module__:  # noqa: E111
    return None

  return cast(PawControlRuntimeData, value)  # noqa: E111


def _coerce_version(candidate: object | None) -> int | None:
  """Return a positive integer version extracted from ``candidate``."""  # noqa: E111

  if isinstance(candidate, bool):  # noqa: E111
    return None
  if isinstance(candidate, int) and candidate > 0:  # noqa: E111
    return candidate
  return None  # noqa: E111


def _stamp_runtime_schema(
  entry_id: str,
  runtime_data: PawControlRuntimeData,
) -> tuple[int, int]:
  """Ensure runtime payloads carry compatible schema metadata."""  # noqa: E111

  schema_version = _coerce_version(  # noqa: E111
    getattr(runtime_data, "schema_version", None),
  )
  created_schema_version = _coerce_version(  # noqa: E111
    getattr(runtime_data, "schema_created_version", None),
  )

  if schema_version is None:  # noqa: E111
    schema_version = DomainRuntimeStoreEntry.CURRENT_VERSION
  if created_schema_version is None:  # noqa: E111
    created_schema_version = schema_version

  if schema_version > DomainRuntimeStoreEntry.CURRENT_VERSION or (  # noqa: E111
    created_schema_version > DomainRuntimeStoreEntry.CURRENT_VERSION
  ):
    raise RuntimeDataIncompatibleError(
      "Future runtime schema detected for "
      f"{entry_id} (got schema={schema_version} "
      f"created={created_schema_version}, "
      f"current={DomainRuntimeStoreEntry.CURRENT_VERSION})",
    )

  if created_schema_version < DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION:  # noqa: E111
    _LOGGER.debug(
      "Upgrading runtime schema origin for %s from %s to %s",
      entry_id,
      created_schema_version,
      DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION,
    )
    created_schema_version = DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION

  if schema_version < DomainRuntimeStoreEntry.CURRENT_VERSION:  # noqa: E111
    _LOGGER.debug(
      "Upgrading runtime schema version for %s from %s to %s",
      entry_id,
      schema_version,
      DomainRuntimeStoreEntry.CURRENT_VERSION,
    )
    schema_version = DomainRuntimeStoreEntry.CURRENT_VERSION

  runtime_data.schema_created_version = created_schema_version  # noqa: E111
  runtime_data.schema_version = schema_version  # noqa: E111

  return schema_version, created_schema_version  # noqa: E111


def _as_store_entry(value: object | None) -> DomainRuntimeStoreEntry | None:
  """Return a :class:`DomainRuntimeStoreEntry` if ``value`` resembles one."""  # noqa: E111

  if isinstance(value, DomainRuntimeStoreEntry):  # noqa: E111
    return value

  if value is None:  # noqa: E111
    return None

  runtime_data = _as_runtime_data(value)  # noqa: E111
  if runtime_data is not None:  # noqa: E111
    return DomainRuntimeStoreEntry(runtime_data=runtime_data)

  value_cls = getattr(value, "__class__", None)  # noqa: E111
  if value_cls is None:  # noqa: E111
    return None

  if getattr(value_cls, "__name__", "") != "DomainRuntimeStoreEntry":  # noqa: E111
    if isinstance(value, Mapping):
      mapping_value: Mapping[str, object]  # noqa: E111
      mapping_value = cast(Mapping[str, object], value)  # noqa: E111
      runtime_candidate = mapping_value.get("runtime_data")  # noqa: E111
      runtime_data = _as_runtime_data(runtime_candidate)  # noqa: E111
      if runtime_data is None:  # noqa: E111
        return None

      version = _coerce_version(mapping_value.get("version"))  # noqa: E111
      created_version = _coerce_version(  # noqa: E111
        mapping_value.get("created_version"),
      )
      if version is None:  # noqa: E111
        return DomainRuntimeStoreEntry(runtime_data=runtime_data)
      if created_version is None:  # noqa: E111
        created_version = version
      return DomainRuntimeStoreEntry(  # noqa: E111
        runtime_data=runtime_data,
        version=version,
        created_version=created_version,
      )

    return None

  if getattr(value_cls, "__module__", "") != DomainRuntimeStoreEntry.__module__:  # noqa: E111
    return None

  runtime_candidate = getattr(value, "runtime_data", None)  # noqa: E111
  runtime_data = _as_runtime_data(runtime_candidate)  # noqa: E111
  if runtime_data is None:  # noqa: E111
    return None

  version = _coerce_version(getattr(value, "version", None))  # noqa: E111
  created_version = _coerce_version(getattr(value, "created_version", None))  # noqa: E111
  if version is None:  # noqa: E111
    return DomainRuntimeStoreEntry(runtime_data=runtime_data)
  if created_version is None:  # noqa: E111
    created_version = version
  return DomainRuntimeStoreEntry(  # noqa: E111
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
  """Return a :class:`RuntimeStoreEntryStatus` for runtime metadata."""  # noqa: E111

  if not available:  # noqa: E111
    return "missing"

  if version is None or created_version is None:  # noqa: E111
    return "unstamped"

  if version > DomainRuntimeStoreEntry.CURRENT_VERSION or (  # noqa: E111
    created_version is not None
    and created_version > DomainRuntimeStoreEntry.CURRENT_VERSION
  ):
    return "future_incompatible"

  if created_version < DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION:  # noqa: E111
    return "legacy_upgrade_required"

  if version != DomainRuntimeStoreEntry.CURRENT_VERSION:  # noqa: E111
    return "upgrade_pending"

  return "current"  # noqa: E111


def _build_runtime_store_snapshot(
  *,
  available: bool,
  version: int | None,
  created_version: int | None,
) -> RuntimeStoreEntrySnapshot:
  """Create a snapshot dictionary for runtime store metadata."""  # noqa: E111

  status = _resolve_entry_status(  # noqa: E111
    available=available,
    version=version,
    created_version=created_version,
  )
  snapshot: RuntimeStoreEntrySnapshot = {  # noqa: E111
    "available": available,
    "version": version,
    "created_version": created_version,
    "status": status,
  }
  return snapshot  # noqa: E111


def _cleanup_domain_store(
  hass: HomeAssistant,
  store: DomainRuntimeStore | None,
) -> None:
  """Remove the PawControl domain store when it no longer holds entries."""  # noqa: E111

  if store is not None and not store:  # noqa: E111
    hass.data.pop(DOMAIN, None)


def _get_store_entry_from_entry(
  entry: PawControlConfigEntry | None,
) -> DomainRuntimeStoreEntry | None:
  """Return a runtime store entry reconstructed from the config entry."""  # noqa: E111

  if entry is None:  # noqa: E111
    return None

  runtime = getattr(entry, "runtime_data", None)  # noqa: E111
  runtime_data = _as_runtime_data(runtime)  # noqa: E111
  if runtime_data is None:  # noqa: E111
    return None

  schema_version, schema_created_version = _stamp_runtime_schema(  # noqa: E111
    entry.entry_id,
    runtime_data,
  )
  version = _coerce_version(getattr(entry, _ENTRY_VERSION_ATTR, None))  # noqa: E111
  if version is None:  # noqa: E111
    version = schema_version

  created_version = _coerce_version(  # noqa: E111
    getattr(entry, _ENTRY_CREATED_VERSION_ATTR, None),
  )
  if created_version is None:  # noqa: E111
    created_version = schema_created_version

  return DomainRuntimeStoreEntry(  # noqa: E111
    runtime_data=runtime_data,
    version=version,
    created_version=created_version,
  )


def _apply_entry_metadata(
  entry: PawControlConfigEntry,
  store_entry: DomainRuntimeStoreEntry,
) -> None:
  """Persist runtime metadata on the config entry."""  # noqa: E111

  entry.runtime_data = store_entry.unwrap()  # noqa: E111
  setattr(entry, _ENTRY_VERSION_ATTR, store_entry.version)  # noqa: E111
  setattr(entry, _ENTRY_CREATED_VERSION_ATTR, store_entry.created_version)  # noqa: E111


def _detach_runtime_from_entry(entry: PawControlConfigEntry | None) -> None:
  """Remove runtime data from an entry to avoid stale references."""  # noqa: E111

  if entry is None:  # noqa: E111
    return

  if hasattr(entry, "runtime_data"):  # noqa: E111
    entry.runtime_data = None
  if hasattr(entry, _ENTRY_VERSION_ATTR):  # noqa: E111
    setattr(entry, _ENTRY_VERSION_ATTR, None)
  if hasattr(entry, _ENTRY_CREATED_VERSION_ATTR):  # noqa: E111
    setattr(entry, _ENTRY_CREATED_VERSION_ATTR, None)


def _normalise_store_entry(
  entry_id: str,
  store_entry: DomainRuntimeStoreEntry,
) -> DomainRuntimeStoreEntry:
  """Ensure ``store_entry`` aligns with the supported schema version."""  # noqa: E111

  if store_entry.is_future_version():  # noqa: E111
    raise RuntimeDataIncompatibleError(
      "Future runtime store schema detected for "
      f"{entry_id} (got version={store_entry.version} "
      f"created={store_entry.created_version}, "
      f"current={DomainRuntimeStoreEntry.CURRENT_VERSION})",
    )

  schema_version, schema_created_version = _stamp_runtime_schema(  # noqa: E111
    entry_id,
    store_entry.runtime_data,
  )

  created_version = max(store_entry.created_version, schema_created_version)  # noqa: E111
  if created_version < DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION:  # noqa: E111
    _LOGGER.debug(
      "Upgrading legacy runtime store entry for %s from schema %s",
      entry_id,
      created_version,
    )
    created_version = DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION

  version = max(store_entry.version, schema_version)  # noqa: E111
  if version < DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION:  # noqa: E111
    version = DomainRuntimeStoreEntry.MINIMUM_COMPATIBLE_VERSION

  upgraded_entry = DomainRuntimeStoreEntry(  # noqa: E111
    runtime_data=store_entry.runtime_data,
    version=version,
    created_version=created_version,
  )

  return upgraded_entry.ensure_current()  # noqa: E111


def store_runtime_data(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
  runtime_data: PawControlRuntimeData,
) -> None:
  """Attach runtime data to the config entry and update compatibility caches."""  # noqa: E111

  _stamp_runtime_schema(entry.entry_id, runtime_data)  # noqa: E111
  store_entry = DomainRuntimeStoreEntry(  # noqa: E111
    runtime_data=runtime_data,
  ).ensure_current()
  _apply_entry_metadata(entry, store_entry)  # noqa: E111

  store = _get_domain_store(hass, create=True)  # noqa: E111
  store[entry.entry_id] = store_entry  # noqa: E111


def get_runtime_data(
  hass: HomeAssistant,
  entry_or_id: PawControlConfigEntry | str,
  *,
  raise_on_incompatible: bool = False,
) -> PawControlRuntimeData | None:
  """Return the runtime data associated with a config entry."""  # noqa: E111

  entry = _get_entry(hass, entry_or_id)  # noqa: E111
  entry_id = _resolve_entry_id(entry_or_id)  # noqa: E111

  try:  # noqa: E111
    entry_store_entry = _get_store_entry_from_entry(entry)
  except RuntimeDataIncompatibleError as err:  # noqa: E111
    _LOGGER.error(
      "Runtime data incompatible for entry %s: %s",
      entry_id,
      err,
    )
    _detach_runtime_from_entry(entry)
    if raise_on_incompatible:
      raise  # noqa: E111
    return None

  if entry_store_entry is not None:  # noqa: E111
    try:
      current_entry = _normalise_store_entry(entry_id, entry_store_entry)  # noqa: E111
    except RuntimeDataIncompatibleError as err:
      _LOGGER.error(  # noqa: E111
        "Runtime data incompatible for entry %s: %s",
        entry_id,
        err,
      )
      _detach_runtime_from_entry(entry)  # noqa: E111
      if raise_on_incompatible:  # noqa: E111
        raise
      return None  # noqa: E111

    if entry is not None:
      _apply_entry_metadata(entry, current_entry)  # noqa: E111
      store = _get_domain_store(hass, create=True)  # noqa: E111
      if store is not None:  # noqa: E111
        store_entry = _as_store_entry(store.get(entry_id))
        if (
          store_entry is None
          or store_entry.unwrap() is not current_entry.unwrap()
          or store_entry.version != current_entry.version
          or store_entry.created_version != current_entry.created_version
        ):
          store[entry_id] = current_entry  # noqa: E111
    return current_entry.unwrap()

  existing_store = _get_domain_store(hass, create=False)  # noqa: E111
  if existing_store is None:  # noqa: E111
    return None

  store_entry = _as_store_entry(existing_store.get(entry_id))  # noqa: E111
  if store_entry is None:  # noqa: E111
    if existing_store.pop(entry_id, None) is not None:
      _cleanup_domain_store(hass, existing_store)  # noqa: E111
    return None

  try:  # noqa: E111
    current_entry = _normalise_store_entry(entry_id, store_entry)
  except RuntimeDataIncompatibleError as err:  # noqa: E111
    _LOGGER.error(
      "Runtime data incompatible for entry %s: %s",
      entry_id,
      err,
    )
    if existing_store.pop(entry_id, None) is not None:
      _cleanup_domain_store(hass, existing_store)  # noqa: E111
    _detach_runtime_from_entry(entry)
    if raise_on_incompatible:
      raise  # noqa: E111
    return None

  existing_store[entry_id] = current_entry  # noqa: E111

  runtime_data = current_entry.unwrap()  # noqa: E111
  if entry is not None:  # noqa: E111
    _apply_entry_metadata(entry, current_entry)
  return runtime_data  # noqa: E111


def describe_runtime_store_status(
  hass: HomeAssistant,
  entry_or_id: PawControlConfigEntry | str,
) -> RuntimeStoreCompatibilitySnapshot:
  """Return a compatibility summary for runtime store metadata."""  # noqa: E111

  entry = _get_entry(hass, entry_or_id)  # noqa: E111
  entry_id = _resolve_entry_id(entry_or_id)  # noqa: E111

  entry_runtime = _as_runtime_data(getattr(entry, "runtime_data", None))  # noqa: E111
  entry_version = (  # noqa: E111
    _coerce_version(getattr(entry, _ENTRY_VERSION_ATTR, None))
    if entry is not None
    else None
  )
  entry_created_version = (  # noqa: E111
    _coerce_version(getattr(entry, _ENTRY_CREATED_VERSION_ATTR, None))
    if entry is not None
    else None
  )

  entry_snapshot = _build_runtime_store_snapshot(  # noqa: E111
    available=entry_runtime is not None,
    version=entry_version,
    created_version=entry_created_version,
  )

  store_runtime: PawControlRuntimeData | None = None  # noqa: E111
  store_version: int | None = None  # noqa: E111
  store_created_version: int | None = None  # noqa: E111

  store = _get_domain_store(hass, create=False)  # noqa: E111
  store_value: object | None = None  # noqa: E111
  if store is not None:  # noqa: E111
    store_value = store.get(entry_id)

  if isinstance(store_value, DomainRuntimeStoreEntry):  # noqa: E111
    store_runtime = store_value.runtime_data
    store_version = store_value.version
    store_created_version = store_value.created_version
  elif isinstance(store_value, Mapping):  # noqa: E111
    mapping_value = cast(Mapping[str, object], store_value)
    store_runtime = _as_runtime_data(mapping_value.get("runtime_data"))
    store_version = _coerce_version(mapping_value.get("version"))
    store_created_version = _coerce_version(
      mapping_value.get("created_version"),
    )
  else:  # noqa: E111
    store_runtime = _as_runtime_data(store_value)

  store_snapshot = _build_runtime_store_snapshot(  # noqa: E111
    available=store_runtime is not None,
    version=store_version,
    created_version=store_created_version,
  )

  divergence_detected = (  # noqa: E111
    entry_snapshot.get("available")
    and store_snapshot.get("available")
    and entry_runtime is not None
    and store_runtime is not None
    and entry_runtime is not store_runtime
  )

  entry_status = entry_snapshot["status"]  # noqa: E111
  store_status = store_snapshot["status"]  # noqa: E111

  statuses: set[RuntimeStoreEntryStatus] = {entry_status, store_status}  # noqa: E111
  entry_available = bool(entry_snapshot.get("available"))  # noqa: E111
  store_available = bool(store_snapshot.get("available"))  # noqa: E111

  overall_status: RuntimeStoreOverallStatus  # noqa: E111
  if "future_incompatible" in statuses:  # noqa: E111
    overall_status = "future_incompatible"
  elif {  # noqa: E111
    "legacy_upgrade_required",
    "upgrade_pending",
    "unstamped",
  } & statuses:
    overall_status = "needs_migration"
  elif divergence_detected:  # noqa: E111
    overall_status = "diverged"
  elif entry_available and not store_available:  # noqa: E111
    overall_status = "detached_store"
  elif store_available and not entry_available:  # noqa: E111
    overall_status = "detached_entry"
  elif not entry_available and not store_available:  # noqa: E111
    overall_status = "missing"
  else:  # noqa: E111
    overall_status = "current"

  return {  # noqa: E111
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
  """Remove and return runtime data for a config entry if present."""  # noqa: E111

  entry = _get_entry(hass, entry_or_id)  # noqa: E111
  entry_id = _resolve_entry_id(entry_or_id)  # noqa: E111
  try:  # noqa: E111
    entry_store_entry = _get_store_entry_from_entry(entry)
  except RuntimeDataIncompatibleError:  # noqa: E111
    entry_store_entry = None
  if entry_store_entry is not None:  # noqa: E111
    try:
      current_entry = _normalise_store_entry(entry_id, entry_store_entry)  # noqa: E111
    except RuntimeDataIncompatibleError:
      current_entry = None  # noqa: E111
    else:
      assert current_entry is not None  # noqa: E111
      runtime_data = current_entry.unwrap()  # noqa: E111
      _detach_runtime_from_entry(entry)  # noqa: E111
      store = _get_domain_store(hass, create=False)  # noqa: E111
      if (  # noqa: E111
        store is not None
        and entry is not None
        and store.pop(entry.entry_id, None) is not None
      ):
        _cleanup_domain_store(hass, store)
      return runtime_data  # noqa: E111
    _detach_runtime_from_entry(entry)

  store = _get_domain_store(hass, create=False)  # noqa: E111
  store_runtime: PawControlRuntimeData | None = None  # noqa: E111
  if store is not None:  # noqa: E111
    value = store.pop(entry_id, None)
    store_entry = _as_store_entry(value)
    if store_entry is not None:
      try:  # noqa: E111
        current_entry = _normalise_store_entry(entry_id, store_entry)
      except RuntimeDataIncompatibleError:  # noqa: E111
        current_entry = None
      else:  # noqa: E111
        store_runtime = current_entry.unwrap()
    _cleanup_domain_store(hass, store)

  return store_runtime  # noqa: E111


class RuntimeDataUnavailableError(HomeAssistantError):
  """Raised when PawControl runtime data cannot be resolved."""  # noqa: E111


class RuntimeDataIncompatibleError(RuntimeDataUnavailableError):
  """Raised when a runtime payload targets an unsupported schema version."""  # noqa: E111


def require_runtime_data(
  hass: HomeAssistant,
  entry_or_id: PawControlConfigEntry | str,
) -> PawControlRuntimeData:
  """Return runtime data or raise when unavailable."""  # noqa: E111

  runtime = get_runtime_data(hass, entry_or_id, raise_on_incompatible=True)  # noqa: E111
  if runtime is None:  # noqa: E111
    entry_id = (
      entry_or_id
      if isinstance(entry_or_id, str)
      else getattr(entry_or_id, "entry_id", "unknown")
    )
    raise RuntimeDataUnavailableError(
      f"Runtime data unavailable for PawControl entry {entry_id}",
    )
  return runtime  # noqa: E111
