"""Compatibility shim for pytest-homeassistant-custom-component on Python 3.13.

The upstream package depends on `freezegun`, which still reaches into
private CPython UUID helpers that were removed in Python 3.13.  Importing
the real package would fail before our tests run.  We patch the `uuid`
module first and then load the actual distribution from site-packages.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import uuid

_PACKAGE_NAME = __name__


def _ensure_uuid_compatibility() -> None:
    """Provide the private UUID helpers expected by older dependencies."""

    if not hasattr(uuid, "_uuid_generate_time"):
        def _uuid_generate_time() -> bytes:
            generated = uuid._generate_time_safe()  # type: ignore[attr-defined]
            return generated[0]

        uuid._uuid_generate_time = _uuid_generate_time  # type: ignore[attr-defined]

    if not hasattr(uuid, "_load_system_functions"):
        def _load_system_functions() -> None:
            if not hasattr(uuid, "_uuid_generate_time"):
                uuid._uuid_generate_time = _uuid_generate_time  # type: ignore[attr-defined]

        uuid._load_system_functions = _load_system_functions  # type: ignore[attr-defined]

    if not hasattr(uuid, "_UuidCreate"):
        uuid._UuidCreate = types.SimpleNamespace  # type: ignore[attr-defined]


def _load_real_package() -> types.ModuleType:
    """Load the real distribution from site-packages.

    We temporarily skip the project root (the first entry on ``sys.path``)
    so that the import machinery can locate the installed package instead
    of this shim module.
    """

    for base in sys.path[1:]:
        candidate = pathlib.Path(base) / _PACKAGE_NAME / "__init__.py"
        if candidate.exists():
            spec = importlib.util.spec_from_file_location(
                f"{_PACKAGE_NAME}.__real__",
                candidate,
                submodule_search_locations=[str(candidate.parent)],
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules.setdefault(spec.name, module)
                spec.loader.exec_module(module)
                return module
    raise ModuleNotFoundError(
        f"Could not locate the real {_PACKAGE_NAME} distribution for compatibility shim"
    )


_ensure_uuid_compatibility()
_real_module = _load_real_package()

globals().update({key: getattr(_real_module, key) for key in dir(_real_module)})
__all__ = getattr(_real_module, "__all__", [])
__path__ = getattr(_real_module, "__path__", [])
sys.modules[_PACKAGE_NAME] = _real_module
