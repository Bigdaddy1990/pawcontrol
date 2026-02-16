"""Verify exception aliases stay bound to active Home Assistant classes."""
from __future__ import annotations


import gc
import sys
from types import ModuleType

import pytest

from custom_components.pawcontrol import compat


def test_bind_exception_alias_infers_calling_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bindings should succeed without explicitly passing a module handle."""

    module_name = "tests.unit.dynamic_alias_module"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name
    monkeypatch.setitem(sys.modules, module_name, dynamic_module)

    try:
        exec(
            "from custom_components.pawcontrol.compat import "
            "HomeAssistantError as _HAError, bind_exception_alias\n"
            "bind_exception_alias('HomeAssistantError')\n",
            dynamic_module.__dict__,
        )
        assert dynamic_module.HomeAssistantError is compat.HomeAssistantError
    finally:
        monkeypatch.delitem(sys.modules, module_name, raising=False)


def test_bind_exception_alias_traverses_call_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bindings should resolve the module even when called from helpers."""

    module_name = "tests.unit.dynamic_alias_module_nested"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name
    monkeypatch.setitem(sys.modules, module_name, dynamic_module)

    try:
        exec(
            "from custom_components.pawcontrol.compat import bind_exception_alias\n"
            "def apply_binding():\n"
            "    bind_exception_alias('HomeAssistantError')\n"
            "apply_binding()\n",
            dynamic_module.__dict__,
        )
        assert dynamic_module.HomeAssistantError is compat.HomeAssistantError
    finally:
        monkeypatch.delitem(sys.modules, module_name, raising=False)


def test_bind_exception_alias_accepts_module_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bindings should allow passing the module name directly."""

    module_name = "tests.unit.dynamic_alias_module_named"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name
    monkeypatch.setitem(sys.modules, module_name, dynamic_module)

    try:
        compat.bind_exception_alias("HomeAssistantError", module=module_name)
        assert dynamic_module.HomeAssistantError is compat.HomeAssistantError
    finally:
        monkeypatch.delitem(sys.modules, module_name, raising=False)


def test_bind_exception_alias_recovers_after_module_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bindings should refresh when the target module is reloaded."""

    module_name = "tests.unit.dynamic_alias_module_reload"
    first_module = ModuleType(module_name)
    first_module.__dict__["__name__"] = module_name
    monkeypatch.setitem(sys.modules, module_name, first_module)

    compat.bind_exception_alias("HomeAssistantError", module=module_name)
    assert first_module.HomeAssistantError is compat.HomeAssistantError

    monkeypatch.delitem(sys.modules, module_name, raising=False)
    del first_module
    gc.collect()

    second_module = ModuleType(module_name)
    second_module.__dict__["__name__"] = module_name
    monkeypatch.setitem(sys.modules, module_name, second_module)

    compat.ensure_homeassistant_exception_symbols()
    assert second_module.HomeAssistantError is compat.HomeAssistantError
