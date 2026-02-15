"""Utility modules for PawControl integration.

Provides common utilities for serialization, normalization, and data processing.
"""

from __future__ import annotations

from importlib.util import module_from_spec
from importlib.util import spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

from .serialize import (
    serialize_datetime,
    serialize_dataclass,
    serialize_entity_attributes,
    serialize_timedelta,
)

_LEGACY_UTILS_MODULE_NAME = "custom_components.pawcontrol._legacy_utils"
_LEGACY_UTILS_PATH = Path(__file__).resolve().parent.parent / "utils.py"

_legacy_utils_spec = spec_from_file_location(
    _LEGACY_UTILS_MODULE_NAME,
    _LEGACY_UTILS_PATH,
)

if _legacy_utils_spec is None or _legacy_utils_spec.loader is None:
    raise ImportError(f"Unable to load legacy utils module from {_LEGACY_UTILS_PATH}")

_legacy_utils_module = module_from_spec(_legacy_utils_spec)
sys.modules[_LEGACY_UTILS_MODULE_NAME] = _legacy_utils_module
_legacy_utils_spec.loader.exec_module(_legacy_utils_module)
_legacy_utils = _legacy_utils_module


def __getattr__(name: str) -> object:
    """Provide backwards-compatible access to symbols from ``utils.py``."""

    if hasattr(_legacy_utils, name):
        return getattr(_legacy_utils, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Return available attributes for static tooling and introspection."""

    return sorted(set(__all__) | set(vars(_legacy_utils)))


def _build_all() -> list[str]:
    """Build ``__all__`` with package-native and compatibility exports."""

    package_exports = {
        "serialize_datetime",
        "serialize_timedelta",
        "serialize_dataclass",
        "serialize_entity_attributes",
    }

    legacy_exports = {
        name
        for name, value in vars(_legacy_utils).items()
        if not name.startswith("_") and not isinstance(value, ModuleType)
    }

    return sorted(package_exports | legacy_exports)

__all__ = _build_all()
