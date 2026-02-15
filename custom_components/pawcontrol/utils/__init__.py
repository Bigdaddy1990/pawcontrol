"""Utility modules for PawControl integration.

Provides common utilities for serialization, normalization, and data processing.
"""

from __future__ import annotations


from importlib.util import module_from_spec
from importlib.util import spec_from_file_location
from pathlib import Path
from typing import Any

from .serialize import (
  serialize_dataclass,
  serialize_datetime,
  serialize_entity_attributes,
  serialize_timedelta,
)

__all__ = [
  "serialize_datetime",
  "serialize_timedelta",
  "serialize_dataclass",
  "serialize_entity_attributes",
]


_LEGACY_UTILS_MODULE = None


def _load_legacy_utils_module() -> Any:
  """Load the legacy ``utils.py`` module for backwards-compatible imports."""

  global _LEGACY_UTILS_MODULE

  if _LEGACY_UTILS_MODULE is not None:
    return _LEGACY_UTILS_MODULE

  legacy_path = Path(__file__).resolve().parent.parent / "utils.py"
  spec = spec_from_file_location(
    "custom_components.pawcontrol._legacy_utils", legacy_path
  )
  if spec is None or spec.loader is None:  # pragma: no cover - defensive safety guard
    raise ImportError(f"Unable to load legacy utils module from {legacy_path}")

  module = module_from_spec(spec)
  spec.loader.exec_module(module)
  _LEGACY_UTILS_MODULE = module
  return module


def __getattr__(name: str) -> Any:
  """Resolve missing attributes from the legacy ``utils.py`` module."""

  module = _load_legacy_utils_module()
  try:
    return getattr(module, name)
  except AttributeError as err:
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from err


def __dir__() -> list[str]:
  """Return module attributes including legacy utility names."""

  module = _load_legacy_utils_module()
  names = set(globals())
  names.update(dir(module))
  return sorted(names)
