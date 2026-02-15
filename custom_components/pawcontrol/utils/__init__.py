"""Utility modules for PawControl integration.

Provides common utilities for serialization, normalization, and data processing.
"""

from __future__ import annotations

from importlib.util import module_from_spec
from importlib.util import spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType
from functools import lru_cache

from .serialize import (
  serialize_dataclass,
  serialize_datetime,
  serialize_entity_attributes,
  serialize_timedelta,
)

_LEGACY_UTILS_MODULE_NAME = "custom_components.pawcontrol._legacy_utils"
_LEGACY_UTILS_PATH = Path(__file__).resolve().parent.parent / "utils.py"

_legacy_utils_spec = spec_from_file_location(
    _LEGACY_UTILS_MODULE_NAME,
    _LEGACY_UTILS_PATH,
)

@lru_cache(maxsize=1)
def _get_legacy_utils() -> ModuleType:
    """Load and return the legacy utils module, caching the result."""
    if _legacy_utils_spec is None or _legacy_utils_spec.loader is None:
        raise ImportError(f"Cannot load legacy utils module from {_LEGACY_UTILS_PATH}")
    module = module_from_spec(_legacy_utils_spec)
    sys.modules[_LEGACY_UTILS_MODULE_NAME] = module
    _legacy_utils_spec.loader.exec_module(module)
    return module


def __getattr__(name: str):
    """Provide compatibility attributes from the legacy utils module.

    This allows existing imports from the old ``utils.py`` module
    to keep working via attribute forwarding.
    """
    legacy_module = _get_legacy_utils()
    if hasattr(legacy_module, name):
        return getattr(legacy_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Return available attributes for static tooling and introspection."""
    return __all__


def _build_all() -> list[str]:
    """Build ``__all__`` with package-native and compatibility exports."""
    legacy_module = _get_legacy_utils()

    package_exports = {
        "serialize_datetime",
        "serialize_timedelta",
        "serialize_dataclass",
        "serialize_entity_attributes",
    }

    legacy_exports = {
        name
        for name, value in vars(legacy_module).items()
        if not name.startswith("_") and not isinstance(value, ModuleType)
    }

    return sorted(package_exports | legacy_exports)

__all__ = _build_all()
