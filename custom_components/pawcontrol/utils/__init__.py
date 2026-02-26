"""Utility package for PawControl integration.

This package keeps ``custom_components.pawcontrol.utils`` backward compatible
while exposing focused utility submodules such as ``serialize``.
"""

from . import _legacy as _legacy_utils, serialize as _serialize_module
from ._legacy import (
    DateTimeConvertible,
    ErrorContext,
    JSONMappingLike,
    JSONMutableMapping,
    Number,
    PawControlDeviceLinkMixin,
    _coerce_json_mutable,
    async_call_add_entities,
    async_call_hass_service_if_available,
    async_capture_service_guard_results,
    async_fire_event,
    build_error_context,
    deep_merge_dicts,
    ensure_local_datetime,
    ensure_utc_datetime,
    is_number,
    normalise_entity_attributes,
    normalize_value,
    resolve_default_feeding_amount,
    sanitize_dog_id,
)
from .serialize import (
    serialize_dataclass,
    serialize_datetime,
    serialize_entity_attributes,
    serialize_timedelta,
)

_SERIALIZE_SYMBOLS = (
    serialize_datetime,
    serialize_timedelta,
    serialize_dataclass,
    serialize_entity_attributes,
)

_SERIALIZE_EXPORTS = {symbol.__name__ for symbol in _SERIALIZE_SYMBOLS}

_EXPLICIT_LEGACY_EXPORTS = {
    "ErrorContext",
    "DateTimeConvertible",
    "JSONMutableMapping",
    "JSONMappingLike",
    "Number",
    "PawControlDeviceLinkMixin",
    "_coerce_json_mutable",
    "async_call_add_entities",
    "async_call_hass_service_if_available",
    "async_capture_service_guard_results",
    "async_fire_event",
    "build_error_context",
    "deep_merge_dicts",
    "ensure_local_datetime",
    "ensure_utc_datetime",
    "is_number",
    "normalise_entity_attributes",
    "normalize_value",
    "resolve_default_feeding_amount",
    "sanitize_dog_id",
}

_LEGACY_EXPORTS = {name for name in vars(_legacy_utils) if not name.startswith("_")}

# Populate this module's namespace with the legacy public symbols explicitly,
# instead of using "from ._legacy import *".
for _name in _LEGACY_EXPORTS:
    if _name in _SERIALIZE_EXPORTS:
        continue
    globals()[_name] = getattr(_legacy_utils, _name)

# Rebind serialize helpers after legacy export population so package-level
# symbols always resolve to the serialize submodule implementations.
serialize_datetime = _serialize_module.serialize_datetime
serialize_timedelta = _serialize_module.serialize_timedelta
serialize_dataclass = _serialize_module.serialize_dataclass
serialize_entity_attributes = _serialize_module.serialize_entity_attributes
__all__ = sorted(_LEGACY_EXPORTS | _SERIALIZE_EXPORTS | _EXPLICIT_LEGACY_EXPORTS)
