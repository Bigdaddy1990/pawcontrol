"""Utility package for PawControl integration.

This package keeps ``custom_components.pawcontrol.utils`` backward compatible
while exposing focused utility submodules such as ``serialize``.
"""

from __future__ import annotations

from . import _legacy as _legacy_utils
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

_LEGACY_EXPORTS = {name for name in vars(_legacy_utils) if not name.startswith("_")}

# Populate this module's namespace with the legacy public symbols explicitly,
# instead of using "from ._legacy import *".
for _name in _LEGACY_EXPORTS:
  globals()[_name] = getattr(_legacy_utils, _name)

__all__ = sorted(_LEGACY_EXPORTS | _SERIALIZE_EXPORTS)
