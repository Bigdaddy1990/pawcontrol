from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType


@contextmanager
def _reload_compat_with_stub(stub: ModuleType | None) -> Iterator[ModuleType]:
    """Reload the compat module with an optional Home Assistant stub."""

    module_name = "custom_components.pawcontrol.compat"
    original_compat = sys.modules.pop(module_name, None)
    original_exceptions = sys.modules.pop("homeassistant.exceptions", None)

    if stub is not None:
        sys.modules["homeassistant.exceptions"] = stub

    try:
        yield importlib.import_module(module_name)
    finally:
        sys.modules.pop(module_name, None)
        if original_compat is not None:
            sys.modules[module_name] = original_compat
        if original_exceptions is not None:
            sys.modules["homeassistant.exceptions"] = original_exceptions
        else:
            sys.modules.pop("homeassistant.exceptions", None)


def test_config_entry_auth_failed_fallback_accepts_auth_migration():
    """ConfigEntryAuthFailed fallback should accept auth_migration flag."""

    stub = ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """Stub HomeAssistantError base."""

    class ConfigEntryError(HomeAssistantError):
        """Stub ConfigEntryError base."""

    class ConfigEntryNotReady(ConfigEntryError):
        """Stub ConfigEntryNotReady error."""

    class ServiceValidationError(HomeAssistantError):
        """Stub ServiceValidationError."""

    stub.HomeAssistantError = HomeAssistantError
    stub.ConfigEntryError = ConfigEntryError
    stub.ConfigEntryNotReady = ConfigEntryNotReady
    stub.ServiceValidationError = ServiceValidationError

    with _reload_compat_with_stub(stub) as compat:
        exc = compat.ConfigEntryAuthFailed("boom", auth_migration=True)
        assert exc.args == ("boom",)
        assert exc.auth_migration is True
        assert issubclass(compat.ConfigEntryAuthFailed, stub.ConfigEntryError)


def test_config_entry_auth_failed_fallback_without_config_entry_error():
    """Fallback should inherit from HomeAssistantError when ConfigEntryError missing."""

    stub = ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """Stub HomeAssistantError base."""

    stub.HomeAssistantError = HomeAssistantError

    with _reload_compat_with_stub(stub) as compat:
        assert issubclass(compat.ConfigEntryAuthFailed, HomeAssistantError)
        exc = compat.ConfigEntryAuthFailed("boom")
        assert exc.auth_migration is None


def test_config_entry_auth_failed_fallback_without_home_assistant_error():
    """Fallback should still work when Home Assistant exceptions module is empty."""

    stub = ModuleType("homeassistant.exceptions")

    with _reload_compat_with_stub(stub) as compat:
        assert issubclass(compat.ConfigEntryAuthFailed, RuntimeError)
