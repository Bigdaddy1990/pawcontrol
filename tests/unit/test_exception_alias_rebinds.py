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
  """Bindings should succeed without explicitly passing a module handle."""  # noqa: E111

  module_name = "tests.unit.dynamic_alias_module"  # noqa: E111
  dynamic_module = ModuleType(module_name)  # noqa: E111
  dynamic_module.__dict__["__name__"] = module_name  # noqa: E111
  monkeypatch.setitem(sys.modules, module_name, dynamic_module)  # noqa: E111

  try:  # noqa: E111
    exec(
      "from custom_components.pawcontrol.compat import "
      "HomeAssistantError as _HAError, bind_exception_alias\n"
      "bind_exception_alias('HomeAssistantError')\n",
      dynamic_module.__dict__,
    )
    assert dynamic_module.HomeAssistantError is compat.HomeAssistantError
  finally:  # noqa: E111
    monkeypatch.delitem(sys.modules, module_name, raising=False)


def test_bind_exception_alias_traverses_call_stack(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Bindings should resolve the module even when called from helpers."""  # noqa: E111

  module_name = "tests.unit.dynamic_alias_module_nested"  # noqa: E111
  dynamic_module = ModuleType(module_name)  # noqa: E111
  dynamic_module.__dict__["__name__"] = module_name  # noqa: E111
  monkeypatch.setitem(sys.modules, module_name, dynamic_module)  # noqa: E111

  try:  # noqa: E111
    exec(
      "from custom_components.pawcontrol.compat import bind_exception_alias\n"
      "def apply_binding():\n"
      "    bind_exception_alias('HomeAssistantError')\n"
      "apply_binding()\n",
      dynamic_module.__dict__,
    )
    assert dynamic_module.HomeAssistantError is compat.HomeAssistantError
  finally:  # noqa: E111
    monkeypatch.delitem(sys.modules, module_name, raising=False)


def test_bind_exception_alias_accepts_module_name(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Bindings should allow passing the module name directly."""  # noqa: E111

  module_name = "tests.unit.dynamic_alias_module_named"  # noqa: E111
  dynamic_module = ModuleType(module_name)  # noqa: E111
  dynamic_module.__dict__["__name__"] = module_name  # noqa: E111
  monkeypatch.setitem(sys.modules, module_name, dynamic_module)  # noqa: E111

  try:  # noqa: E111
    compat.bind_exception_alias("HomeAssistantError", module=module_name)
    assert dynamic_module.HomeAssistantError is compat.HomeAssistantError
  finally:  # noqa: E111
    monkeypatch.delitem(sys.modules, module_name, raising=False)


def test_bind_exception_alias_recovers_after_module_reload(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Bindings should refresh when the target module is reloaded."""  # noqa: E111

  module_name = "tests.unit.dynamic_alias_module_reload"  # noqa: E111
  first_module = ModuleType(module_name)  # noqa: E111
  first_module.__dict__["__name__"] = module_name  # noqa: E111
  monkeypatch.setitem(sys.modules, module_name, first_module)  # noqa: E111

  compat.bind_exception_alias("HomeAssistantError", module=module_name)  # noqa: E111
  assert first_module.HomeAssistantError is compat.HomeAssistantError  # noqa: E111

  monkeypatch.delitem(sys.modules, module_name, raising=False)  # noqa: E111
  del first_module  # noqa: E111
  gc.collect()  # noqa: E111

  second_module = ModuleType(module_name)  # noqa: E111
  second_module.__dict__["__name__"] = module_name  # noqa: E111
  monkeypatch.setitem(sys.modules, module_name, second_module)  # noqa: E111

  compat.ensure_homeassistant_exception_symbols()  # noqa: E111
  assert second_module.HomeAssistantError is compat.HomeAssistantError  # noqa: E111
