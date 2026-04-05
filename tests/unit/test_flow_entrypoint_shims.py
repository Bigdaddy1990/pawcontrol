"""Coverage tests for lightweight flow entrypoint shims."""

from importlib import import_module
import sys
from types import ModuleType


def _import_with_stub(
    module_name: str,
    dependency_name: str,
    **attrs: object,
) -> ModuleType:
    """Import ``module_name`` while stubbing one dependency module."""
    sys.modules.pop(module_name, None)
    stub = ModuleType(dependency_name)
    for key, value in attrs.items():
        setattr(stub, key, value)
    sys.modules[dependency_name] = stub
    return import_module(module_name)


def test_config_flow_exports_expected_symbols() -> None:
    """config_flow shim should re-export canonical flow classes."""

    class FakeConfigFlow: ...

    class FakePawControlConfigFlow: ...

    module = _import_with_stub(
        "custom_components.pawcontrol.config_flow",
        "custom_components.pawcontrol.config_flow_main",
        ConfigFlow=FakeConfigFlow,
        PawControlConfigFlow=FakePawControlConfigFlow,
    )

    assert module.__all__ == ("ConfigFlow", "PawControlConfigFlow")
    assert module.ConfigFlow is FakeConfigFlow
    assert module.PawControlConfigFlow is FakePawControlConfigFlow


def test_options_flow_exports_expected_symbol() -> None:
    """options_flow shim should re-export canonical options flow class."""

    class FakePawControlOptionsFlow: ...

    module = _import_with_stub(
        "custom_components.pawcontrol.options_flow",
        "custom_components.pawcontrol.options_flow_main",
        PawControlOptionsFlow=FakePawControlOptionsFlow,
    )

    assert module.__all__ == ("PawControlOptionsFlow",)
    assert module.PawControlOptionsFlow is FakePawControlOptionsFlow
