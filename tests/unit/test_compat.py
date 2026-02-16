import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType


@contextmanager
def _reload_compat_with_stub(
    stub: ModuleType | None,
    *,
    const_stub: ModuleType | None = None,
) -> Iterator[ModuleType]:
    """Reload the compat module with an optional Home Assistant stub."""

    module_name = "custom_components.pawcontrol.compat"
    original_compat = sys.modules.pop(module_name, None)
    original_exceptions = sys.modules.pop("homeassistant.exceptions", None)
    original_const = sys.modules.pop("homeassistant.const", None)

    if stub is not None:
        sys.modules["homeassistant.exceptions"] = stub
    if const_stub is not None:
        sys.modules["homeassistant.const"] = const_stub

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
        if original_const is not None:
            sys.modules["homeassistant.const"] = original_const
        else:
            sys.modules.pop("homeassistant.const", None)


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


def test_unit_of_mass_fallback_uses_default_units() -> None:
    """Compat should supply a UnitOfMass fallback when HA consts are missing."""

    const_stub = ModuleType("homeassistant.const")

    with _reload_compat_with_stub(None, const_stub=const_stub) as compat:
        assert compat.UnitOfMass.GRAMS == "g"
        assert compat.UnitOfMass.KILOGRAMS == "kg"
        assert compat.MASS_GRAMS == "g"
        assert compat.MASS_KILOGRAMS == "kg"


def test_unit_of_mass_prefers_homeassistant_enum() -> None:
    """Compat should prefer UnitOfMass from Home Assistant when available."""

    const_stub = ModuleType("homeassistant.const")

    class UnitOfMass:
        GRAMS = "g"
        KILOGRAMS = "kg"

    const_stub.UnitOfMass = UnitOfMass

    with _reload_compat_with_stub(None, const_stub=const_stub) as compat:
        assert compat.UnitOfMass is UnitOfMass
        assert compat.MASS_GRAMS == UnitOfMass.GRAMS
        assert compat.MASS_KILOGRAMS == UnitOfMass.KILOGRAMS
