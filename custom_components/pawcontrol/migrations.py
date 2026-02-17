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
    """Best-effort coercion for legacy module toggle payloads."""
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled"}:
            return False
        return text in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(value)


def _coerce_modules_payload(payload: Any) -> DogModulesConfig | None:
    """Coerce legacy module payloads into a config mapping."""
    if isinstance(payload, Mapping):
        return ensure_dog_modules_config(cast(Mapping[str, object], payload))

    if isinstance(payload, Sequence) and not isinstance(
        payload,
        str | bytes | bytearray,
    ):
        modules: DogModulesConfig = {}
        for item in payload:
            if isinstance(item, str):
                key = item.strip()
                if key in MODULE_TOGGLE_KEYS:
                    modules[cast(ModuleToggleKey, key)] = True
                continue

            if not isinstance(item, Mapping):
                continue

            legacy_key = None
            for key_name in ("module", "key", "name"):
                raw_key = item.get(key_name)
                if isinstance(raw_key, str) and raw_key.strip():
                    legacy_key = raw_key.strip()
                    break
            if legacy_key is None or legacy_key not in MODULE_TOGGLE_KEYS:
                continue

            enabled_value = item.get("enabled")
            if "value" in item:
                enabled_value = item["value"]
            modules[cast(ModuleToggleKey, legacy_key)] = _coerce_legacy_toggle(
                enabled_value,
            )

        return modules or None

    return None


def _resolve_dog_identifier(
    candidate: Mapping[str, object],
    fallback_id: str | None,
) -> str | None:
    """Return a normalized dog identifier."""
    for key in _LEGACY_ID_KEYS:
        raw_value = candidate.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            try:
                normalized = normalize_dog_id(raw_value)
            except InputCoercionError:
                continue
            if normalized:
                return normalized

    if isinstance(fallback_id, str) and fallback_id.strip():
        try:
            normalized_fallback = normalize_dog_id(fallback_id)
        except InputCoercionError:
            return fallback_id.strip()
        return normalized_fallback or fallback_id.strip()

    return None


def _normalize_dog_entry(
    raw: Any,
    *,
    fallback_id: str | None = None,
) -> DogConfigData | None:
    """Normalize legacy dog payloads into ``DogConfigData`` mappings."""
    if not isinstance(raw, Mapping):
        return None

    candidate: dict[str, Any] = {
        str(key): value for key, value in raw.items() if isinstance(key, str)
    }

    dog_id = _resolve_dog_identifier(candidate, fallback_id)
    if dog_id is None:
        return None
    candidate[DOG_ID_FIELD] = dog_id
    resolved_name: str | None = None
    for raw_name in (
        candidate.get(DOG_NAME_FIELD),
        candidate.get("name"),
    ):
        try:
            resolved_name = validate_dog_name(raw_name, required=False)
        except ValidationError:
            resolved_name = None
        if resolved_name:
            break
    candidate[DOG_NAME_FIELD] = resolved_name or dog_id
    modules_payload = candidate.get(DOG_MODULES_FIELD)
    coerced_modules = _coerce_modules_payload(modules_payload)
    if coerced_modules:
        candidate[DOG_MODULES_FIELD] = coerced_modules
    elif modules_payload is not None:
        candidate.pop(DOG_MODULES_FIELD, None)

    return cast(DogConfigData, candidate)


def _normalize_dog_options(
    payload: Any,
) -> dict[str, DogOptionsEntry]:
    """Return a normalized dog options mapping."""
    normalized: dict[str, DogOptionsEntry] = {}
    if isinstance(payload, Mapping):
        for raw_id, raw_entry in payload.items():
            if not isinstance(raw_entry, Mapping):
                continue
            dog_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else None
            if dog_id is not None:
                dog_id = normalize_dog_id(dog_id)
            entry = ensure_dog_options_entry(
                cast(dict[str, Any], dict(raw_entry)),
                dog_id=dog_id,
            )
            if entry:
                normalized[entry.get("dog_id", dog_id or "")] = entry
        return {key: value for key, value in normalized.items() if key}

    if isinstance(payload, Sequence) and not isinstance(
        payload,
        str | bytes | bytearray,
    ):
        for raw_entry in payload:
            if not isinstance(raw_entry, Mapping):
                continue
            raw_id = raw_entry.get(DOG_ID_FIELD)
            dog_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else None
            if dog_id is not None:
                dog_id = normalize_dog_id(dog_id)
            entry = ensure_dog_options_entry(
                cast(dict[str, Any], dict(raw_entry)),
                dog_id=dog_id,
            )
            if entry and entry.get("dog_id"):
                normalized[entry["dog_id"]] = entry

    return normalized


def _migrate_v1_to_v2(
    data: dict[str, Any],
    options: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Migrate configuration data from version 1 to 2."""
    raw_dogs = data.get(CONF_DOGS)
    normalized_dogs: list[DogConfigData] = []
    if isinstance(raw_dogs, Mapping):
        for raw_id, raw_entry in raw_dogs.items():
            normalized = _normalize_dog_entry(raw_entry, fallback_id=str(raw_id))
            if normalized is not None:
                normalized_dogs.append(normalized)
    elif isinstance(raw_dogs, Sequence) and not isinstance(
        raw_dogs,
        str | bytes | bytearray,
    ):
        for raw_entry in raw_dogs:
            normalized = _normalize_dog_entry(raw_entry)
            if normalized is not None:
                normalized_dogs.append(normalized)

    if normalized_dogs:
        data[CONF_DOGS] = normalized_dogs

    modules_payload = data.pop(CONF_MODULES, None)
    modules_config = _coerce_modules_payload(modules_payload)
    if modules_config:
        for dog in normalized_dogs:
            if DOG_MODULES_FIELD not in dog:
                dog[DOG_MODULES_FIELD] = dict(modules_config)  # type: ignore[typeddict-item]

    data_dog_options = data.pop(CONF_DOG_OPTIONS, None)
    merged_options = _normalize_dog_options(data_dog_options)
    merged_options.update(_normalize_dog_options(options.get(CONF_DOG_OPTIONS)))
    if merged_options:
        options[CONF_DOG_OPTIONS] = merged_options

    return data, options


async def async_migrate_entry(hass: HomeAssistant, entry: Any) -> bool:
    """Migrate old entries to new versions."""
    if entry.version > CONFIG_ENTRY_VERSION:
        _LOGGER.error(
            "Cannot migrate entry %s from version %s to %s",
            entry.entry_id,
            entry.version,
            CONFIG_ENTRY_VERSION,
        )
        return False

    data = dict(entry.data)
    options = dict(entry.options)
    version = entry.version
    if version < 1:
        version = 1

    if version == 1:
        data, options = _migrate_v1_to_v2(data, options)
        version = 2

    if version != entry.version:
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

    return True
