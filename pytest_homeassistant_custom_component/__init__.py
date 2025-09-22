"""Compatibility shim for pytest-homeassistant-custom-component on Python 3.13.

The upstream package depends on `freezegun`, which still reaches into
private CPython UUID helpers that were removed in Python 3.13.  Importing
the real package would fail before our tests run.  We patch the `uuid`
module first and then load the actual distribution from site-packages.
"""

from __future__ import annotations

import importlib
import pathlib
import sys
import types
import uuid

_PACKAGE_NAME = __name__
_SHIM_PARENT = pathlib.Path(__file__).resolve().parent.parent


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


def _is_shim_path(entry: str) -> bool:
    """Return ``True`` if a ``sys.path`` entry points to this shim package."""

    path = pathlib.Path(entry or ".")
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == _SHIM_PARENT


def _load_real_package() -> types.ModuleType:
    """Load the real distribution from site-packages.

    We temporarily remove the shim's parent directory from ``sys.path`` so the
    import machinery locates the installed package instead of this compatibility
    module.
    """

    shim_module = sys.modules[_PACKAGE_NAME]
    original_sys_path = list(sys.path)
    filtered_path = [entry for entry in sys.path if not _is_shim_path(entry)]

    sys.modules.pop(_PACKAGE_NAME, None)
    try:
        sys.path[:] = filtered_path
        return importlib.import_module(_PACKAGE_NAME)
    except ModuleNotFoundError as err:  # pragma: no cover - exercised in CI
        raise ModuleNotFoundError(
            f"Could not locate the real {_PACKAGE_NAME} distribution for compatibility shim"
        ) from err
    finally:
        sys.path[:] = original_sys_path
        sys.modules[_PACKAGE_NAME] = shim_module


_ensure_uuid_compatibility()
_real_module = _load_real_package()

globals().update({key: getattr(_real_module, key) for key in dir(_real_module)})
__all__ = getattr(_real_module, "__all__", [])
__path__ = getattr(_real_module, "__path__", [])
sys.modules[_PACKAGE_NAME] = _real_module
