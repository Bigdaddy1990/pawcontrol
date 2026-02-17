"""Config entry migrations for the PawControl integration."""

from collections.abc import Mapping, Sequence
import logging
from typing import Any, Final, cast

from homeassistant.core import HomeAssistant

from .const import CONF_DOG_OPTIONS, CONF_DOGS, CONF_MODULES, CONFIG_ENTRY_VERSION
from .exceptions import ValidationError
from .types import (
  DOG_ID_FIELD,
  DOG_MODULES_FIELD,
  DOG_NAME_FIELD,
  MODULE_TOGGLE_KEYS,
  DogConfigData,
  DogModulesConfig,
  DogOptionsEntry,
  ModuleToggleKey,
  ensure_dog_modules_config,
  ensure_dog_options_entry,
)
from .validation import InputCoercionError, normalize_dog_id, validate_dog_name

_LOGGER = logging.getLogger(__name__)

_LEGACY_ID_KEYS: Final[tuple[str, ...]] = (
  DOG_ID_FIELD,
  "id",
  "dogId",
  "dog_identifier",
  "identifier",
  "unique_id",
  "uniqueId",
)


def _coerce_legacy_toggle(value: Any) -> bool:
  """Best-effort coercion for legacy module toggle payloads."""  # noqa: E111

  if value is None:  # noqa: E111
    return True
  if isinstance(value, bool):  # noqa: E111
    return value
  if isinstance(value, int | float):  # noqa: E111
    return value != 0
  if isinstance(value, str):  # noqa: E111
    text = value.strip().lower()
    if not text:
      return True  # noqa: E111
    if text in {"0", "false", "no", "n", "off", "disabled"}:
      return False  # noqa: E111
    return text in {"1", "true", "yes", "y", "on", "enabled"}
  return bool(value)  # noqa: E111


def _coerce_modules_payload(payload: Any) -> DogModulesConfig | None:
  """Coerce legacy module payloads into a config mapping."""  # noqa: E111

  if isinstance(payload, Mapping):  # noqa: E111
    return ensure_dog_modules_config(cast(Mapping[str, object], payload))

  if isinstance(payload, Sequence) and not isinstance(  # noqa: E111
    payload,
    str | bytes | bytearray,
  ):
    modules: DogModulesConfig = {}
    for item in payload:
      if isinstance(item, str):  # noqa: E111
        key = item.strip()
        if key in MODULE_TOGGLE_KEYS:
          modules[cast(ModuleToggleKey, key)] = True  # noqa: E111
        continue

      if not isinstance(item, Mapping):  # noqa: E111
        continue

      legacy_key = None  # noqa: E111
      for key_name in ("module", "key", "name"):  # noqa: E111
        raw_key = item.get(key_name)
        if isinstance(raw_key, str) and raw_key.strip():
          legacy_key = raw_key.strip()  # noqa: E111
          break  # noqa: E111
      if legacy_key is None or legacy_key not in MODULE_TOGGLE_KEYS:  # noqa: E111
        continue

      enabled_value = item.get("enabled")  # noqa: E111
      if "value" in item:  # noqa: E111
        enabled_value = item["value"]
      modules[cast(ModuleToggleKey, legacy_key)] = _coerce_legacy_toggle(  # noqa: E111
        enabled_value,
      )

    return modules or None

  return None  # noqa: E111


def _resolve_dog_identifier(
  candidate: Mapping[str, object],
  fallback_id: str | None,
) -> str | None:
  """Return a normalized dog identifier."""  # noqa: E111

  for key in _LEGACY_ID_KEYS:  # noqa: E111
    raw_value = candidate.get(key)
    if isinstance(raw_value, str) and raw_value.strip():
      try:  # noqa: E111
        normalized = normalize_dog_id(raw_value)
      except InputCoercionError:  # noqa: E111
        continue
      if normalized:  # noqa: E111
        return normalized

  if isinstance(fallback_id, str) and fallback_id.strip():  # noqa: E111
    try:
      normalized_fallback = normalize_dog_id(fallback_id)  # noqa: E111
    except InputCoercionError:
      return fallback_id.strip()  # noqa: E111
    return normalized_fallback or fallback_id.strip()

  return None  # noqa: E111


def _normalize_dog_entry(
  raw: Any,
  *,
  fallback_id: str | None = None,
) -> DogConfigData | None:
  """Normalize legacy dog payloads into ``DogConfigData`` mappings."""  # noqa: E111

  if not isinstance(raw, Mapping):  # noqa: E111
    return None

  candidate: dict[str, Any] = {  # noqa: E111
    str(key): value for key, value in raw.items() if isinstance(key, str)
  }

  dog_id = _resolve_dog_identifier(candidate, fallback_id)  # noqa: E111
  if dog_id is None:  # noqa: E111
    return None
  candidate[DOG_ID_FIELD] = dog_id  # noqa: E111

  resolved_name: str | None = None  # noqa: E111
  for raw_name in (  # noqa: E111
    candidate.get(DOG_NAME_FIELD),
    candidate.get("name"),
  ):
    try:
      resolved_name = validate_dog_name(raw_name, required=False)  # noqa: E111
    except ValidationError:
      resolved_name = None  # noqa: E111
    if resolved_name:
      break  # noqa: E111
  candidate[DOG_NAME_FIELD] = resolved_name or dog_id  # noqa: E111

  modules_payload = candidate.get(DOG_MODULES_FIELD)  # noqa: E111
  coerced_modules = _coerce_modules_payload(modules_payload)  # noqa: E111
  if coerced_modules:  # noqa: E111
    candidate[DOG_MODULES_FIELD] = coerced_modules
  elif modules_payload is not None:  # noqa: E111
    candidate.pop(DOG_MODULES_FIELD, None)

  return cast(DogConfigData, candidate)  # noqa: E111


def _normalize_dog_options(
  payload: Any,
) -> dict[str, DogOptionsEntry]:
  """Return a normalized dog options mapping."""  # noqa: E111

  normalized: dict[str, DogOptionsEntry] = {}  # noqa: E111

  if isinstance(payload, Mapping):  # noqa: E111
    for raw_id, raw_entry in payload.items():
      if not isinstance(raw_entry, Mapping):  # noqa: E111
        continue
      dog_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else None  # noqa: E111
      if dog_id is not None:  # noqa: E111
        dog_id = normalize_dog_id(dog_id)
      entry = ensure_dog_options_entry(  # noqa: E111
        cast(dict[str, Any], dict(raw_entry)),
        dog_id=dog_id,
      )
      if entry:  # noqa: E111
        normalized[entry.get("dog_id", dog_id or "")] = entry
    return {key: value for key, value in normalized.items() if key}

  if isinstance(payload, Sequence) and not isinstance(  # noqa: E111
    payload,
    str | bytes | bytearray,
  ):
    for raw_entry in payload:
      if not isinstance(raw_entry, Mapping):  # noqa: E111
        continue
      raw_id = raw_entry.get(DOG_ID_FIELD)  # noqa: E111
      dog_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else None  # noqa: E111
      if dog_id is not None:  # noqa: E111
        dog_id = normalize_dog_id(dog_id)
      entry = ensure_dog_options_entry(  # noqa: E111
        cast(dict[str, Any], dict(raw_entry)),
        dog_id=dog_id,
      )
      if entry and entry.get("dog_id"):  # noqa: E111
        normalized[entry["dog_id"]] = entry

  return normalized  # noqa: E111


def _migrate_v1_to_v2(
  data: dict[str, Any],
  options: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
  """Migrate configuration data from version 1 to 2."""  # noqa: E111

  raw_dogs = data.get(CONF_DOGS)  # noqa: E111
  normalized_dogs: list[DogConfigData] = []  # noqa: E111

  if isinstance(raw_dogs, Mapping):  # noqa: E111
    for raw_id, raw_entry in raw_dogs.items():
      normalized = _normalize_dog_entry(raw_entry, fallback_id=str(raw_id))  # noqa: E111
      if normalized is not None:  # noqa: E111
        normalized_dogs.append(normalized)
  elif isinstance(raw_dogs, Sequence) and not isinstance(  # noqa: E111
    raw_dogs,
    str | bytes | bytearray,
  ):
    for raw_entry in raw_dogs:
      normalized = _normalize_dog_entry(raw_entry)  # noqa: E111
      if normalized is not None:  # noqa: E111
        normalized_dogs.append(normalized)

  if normalized_dogs:  # noqa: E111
    data[CONF_DOGS] = normalized_dogs

  modules_payload = data.pop(CONF_MODULES, None)  # noqa: E111
  modules_config = _coerce_modules_payload(modules_payload)  # noqa: E111
  if modules_config:  # noqa: E111
    for dog in normalized_dogs:
      if DOG_MODULES_FIELD not in dog:  # noqa: E111
        dog[DOG_MODULES_FIELD] = dict(modules_config)  # type: ignore[typeddict-item]

  data_dog_options = data.pop(CONF_DOG_OPTIONS, None)  # noqa: E111
  merged_options = _normalize_dog_options(data_dog_options)  # noqa: E111
  merged_options.update(_normalize_dog_options(options.get(CONF_DOG_OPTIONS)))  # noqa: E111
  if merged_options:  # noqa: E111
    options[CONF_DOG_OPTIONS] = merged_options

  return data, options  # noqa: E111


async def async_migrate_entry(hass: HomeAssistant, entry: Any) -> bool:
  """Migrate old entries to new versions."""  # noqa: E111

  if entry.version > CONFIG_ENTRY_VERSION:  # noqa: E111
    _LOGGER.error(
      "Cannot migrate entry %s from version %s to %s",
      entry.entry_id,
      entry.version,
      CONFIG_ENTRY_VERSION,
    )
    return False

  data = dict(entry.data)  # noqa: E111
  options = dict(entry.options)  # noqa: E111
  version = entry.version  # noqa: E111

  if version < 1:  # noqa: E111
    version = 1

  if version == 1:  # noqa: E111
    data, options = _migrate_v1_to_v2(data, options)
    version = 2

  if version != entry.version:  # noqa: E111
    _LOGGER.info(
      "Migrated PawControl entry %s to version %s",
      entry.entry_id,
      version,
    )
    hass.config_entries.async_update_entry(
      entry,
      data=data,
      options=options,
      version=version,
    )

  return True  # noqa: E111
