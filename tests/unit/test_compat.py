from collections.abc import Iterator
from contextlib import contextmanager
import importlib
import sys
from types import ModuleType


@contextmanager
def _reload_compat_with_stub(
    stub: ModuleType | None,
    *,
    const_stub: ModuleType | None = None,
) -> Iterator[ModuleType]:
    """Reload the compat module with an optional Home Assistant stub."""  # noqa: E111

    module_name = "custom_components.pawcontrol.compat"  # noqa: E111
    original_compat = sys.modules.pop(module_name, None)  # noqa: E111
    original_exceptions = sys.modules.pop("homeassistant.exceptions", None)  # noqa: E111
    original_const = sys.modules.pop("homeassistant.const", None)  # noqa: E111

    if stub is not None:  # noqa: E111
        sys.modules["homeassistant.exceptions"] = stub
    if const_stub is not None:  # noqa: E111
        sys.modules["homeassistant.const"] = const_stub

    try:  # noqa: E111
        yield importlib.import_module(module_name)
    finally:  # noqa: E111
        sys.modules.pop(module_name, None)
        if original_compat is not None:
            sys.modules[module_name] = original_compat  # noqa: E111
        if original_exceptions is not None:
            sys.modules["homeassistant.exceptions"] = original_exceptions  # noqa: E111
        else:
            sys.modules.pop("homeassistant.exceptions", None)  # noqa: E111
        if original_const is not None:
            sys.modules["homeassistant.const"] = original_const  # noqa: E111
        else:
            sys.modules.pop("homeassistant.const", None)  # noqa: E111


def test_config_entry_auth_failed_fallback_accepts_auth_migration() -> None:
    """ConfigEntryAuthFailed fallback should accept auth_migration flag."""  # noqa: E111

    stub = ModuleType("homeassistant.exceptions")  # noqa: E111

    class HomeAssistantError(Exception):  # noqa: E111
        """Stub HomeAssistantError base."""

    class ConfigEntryError(HomeAssistantError):  # noqa: E111
        """Stub ConfigEntryError base."""

    class ConfigEntryNotReady(ConfigEntryError):  # noqa: E111
        """Stub ConfigEntryNotReady error."""

    class ServiceValidationError(HomeAssistantError):  # noqa: E111
        """Stub ServiceValidationError."""

    stub.HomeAssistantError = HomeAssistantError  # noqa: E111
    stub.ConfigEntryError = ConfigEntryError  # noqa: E111
    stub.ConfigEntryNotReady = ConfigEntryNotReady  # noqa: E111
    stub.ServiceValidationError = ServiceValidationError  # noqa: E111

    with _reload_compat_with_stub(stub) as compat:  # noqa: E111
        exc = compat.ConfigEntryAuthFailed("boom", auth_migration=True)
        assert exc.args == ("boom",)
        assert exc.auth_migration is True
        assert issubclass(compat.ConfigEntryAuthFailed, stub.ConfigEntryError)


def test_config_entry_auth_failed_fallback_without_config_entry_error() -> None:
    """Fallback should inherit from HomeAssistantError when ConfigEntryError missing."""  # noqa: E111

    stub = ModuleType("homeassistant.exceptions")  # noqa: E111

    class HomeAssistantError(Exception):  # noqa: E111
        """Stub HomeAssistantError base."""

    stub.HomeAssistantError = HomeAssistantError  # noqa: E111

    with _reload_compat_with_stub(stub) as compat:  # noqa: E111
        assert issubclass(compat.ConfigEntryAuthFailed, HomeAssistantError)
        exc = compat.ConfigEntryAuthFailed("boom")
        assert exc.auth_migration is None


def test_config_entry_auth_failed_fallback_without_home_assistant_error() -> None:
    """Fallback should still work when Home Assistant exceptions module is empty."""  # noqa: E111

    stub = ModuleType("homeassistant.exceptions")  # noqa: E111

    with _reload_compat_with_stub(stub) as compat:  # noqa: E111
        assert issubclass(compat.ConfigEntryAuthFailed, RuntimeError)


def test_unit_of_mass_fallback_uses_default_units() -> None:
    """Compat should supply a UnitOfMass fallback when HA consts are missing."""  # noqa: E111

    const_stub = ModuleType("homeassistant.const")  # noqa: E111

    with _reload_compat_with_stub(None, const_stub=const_stub) as compat:  # noqa: E111
        assert compat.UnitOfMass.GRAMS == "g"
        assert compat.UnitOfMass.KILOGRAMS == "kg"
        assert compat.MASS_GRAMS == "g"
        assert compat.MASS_KILOGRAMS == "kg"


def test_unit_of_mass_prefers_homeassistant_enum() -> None:
    """Compat should prefer UnitOfMass from Home Assistant when available."""  # noqa: E111

    const_stub = ModuleType("homeassistant.const")  # noqa: E111

    class UnitOfMass:  # noqa: E111
        GRAMS = "g"
        KILOGRAMS = "kg"

    const_stub.UnitOfMass = UnitOfMass  # noqa: E111

    with _reload_compat_with_stub(None, const_stub=const_stub) as compat:  # noqa: E111
        assert compat.UnitOfMass is UnitOfMass
        assert compat.MASS_GRAMS == UnitOfMass.GRAMS
        assert compat.MASS_KILOGRAMS == UnitOfMass.KILOGRAMS
