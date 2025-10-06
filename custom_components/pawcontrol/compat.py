"""Compatibility helpers for optional Home Assistant imports."""

from __future__ import annotations

# Home Assistant's exception module has evolved over time and the lightweight test
# stubs that ship with this repository only expose a subset of the classes.  We
# import the authentic class when available but fall back to a local stand-in so
# that unit tests can run in isolation without the full Home Assistant package.

try:  # pragma: no cover - exercised when Home Assistant is installed
    from homeassistant.exceptions import ConfigEntryAuthFailed as _ConfigEntryAuthFailed
except (ImportError, ModuleNotFoundError):
    _CompatBase: type[Exception] | None = None

    try:
        from homeassistant.exceptions import ConfigEntryError as _ConfigEntryError
    except (ImportError, ModuleNotFoundError):
        _ConfigEntryError = None
    else:  # pragma: no cover - executed when ConfigEntryError is available but auth failed is not
        _CompatBase = _ConfigEntryError

    if _CompatBase is None:
        try:
            from homeassistant.exceptions import (
                HomeAssistantError as _HomeAssistantError,
            )
        except (
            ImportError,
            ModuleNotFoundError,
        ):  # pragma: no cover - optional base missing
            _HomeAssistantError = None

        if _HomeAssistantError is None:

            class _CompatConfigEntryError(RuntimeError):
                """Fallback ``ConfigEntryError`` stand-in."""

        else:  # pragma: no cover - executed when HomeAssistantError is available but ConfigEntryError is not

            class _CompatConfigEntryError(_HomeAssistantError):
                """Fallback ``ConfigEntryError`` stand-in inheriting HA base."""

        _CompatBase = _CompatConfigEntryError

    class ConfigEntryAuthFailed(_CompatBase):
        """Fallback error mirroring Home Assistant's ``ConfigEntryAuthFailed``."""

        __slots__ = ("auth_migration",)

        def __init__(
            self,
            message: str | None = None,
            *,
            auth_migration: bool | None = None,
        ) -> None:
            """Initialise the compatibility error with optional auth migration flag."""

            super().__init__(message)
            self.auth_migration = auth_migration

    del _CompatBase
    del _ConfigEntryError
    if "_HomeAssistantError" in locals():
        del _HomeAssistantError
    if "_CompatConfigEntryError" in locals():
        del _CompatConfigEntryError

else:  # pragma: no cover - executed in production Home Assistant environments
    ConfigEntryAuthFailed = _ConfigEntryAuthFailed
    del _ConfigEntryAuthFailed

__all__ = ["ConfigEntryAuthFailed"]
