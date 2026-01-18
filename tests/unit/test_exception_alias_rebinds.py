"""Verify exception aliases stay bound to active Home Assistant classes."""

from __future__ import annotations

import gc
import sys
from types import ModuleType

import pytest
from custom_components.pawcontrol import button, compat, validation
from custom_components.pawcontrol.validation import ValidationError


def _install_sentinel_exceptions() -> tuple[ModuleType | None, ModuleType]:
  original_module = sys.modules.get("homeassistant.exceptions")
  sentinel_module = ModuleType("homeassistant.exceptions")

  base_error = type("_SentinelHomeAssistantError", (Exception,), {})
  entry_error = type("_SentinelConfigEntryError", (base_error,), {})
  auth_failed = type("_SentinelConfigEntryAuthFailed", (entry_error,), {})
  not_ready = type("_SentinelConfigEntryNotReady", (entry_error,), {})
  service_validation = type("_SentinelServiceValidationError", (base_error,), {})

  sentinel_module.HomeAssistantError = base_error
  sentinel_module.ConfigEntryError = entry_error
  sentinel_module.ConfigEntryAuthFailed = auth_failed
  sentinel_module.ConfigEntryNotReady = not_ready
  sentinel_module.ServiceValidationError = service_validation

  sys.modules["homeassistant.exceptions"] = sentinel_module
  compat.ensure_homeassistant_exception_symbols()
  return original_module, sentinel_module


def _restore_exceptions(original: ModuleType | None) -> None:
  if original is None:
    sys.modules.pop("homeassistant.exceptions", None)
  else:
    sys.modules["homeassistant.exceptions"] = original
  compat.ensure_homeassistant_exception_symbols()


def test_validation_service_error_alias_tracks_rebind() -> None:
  """Validation helpers should emit the latest ServiceValidationError class."""

  original_module, sentinel_module = _install_sentinel_exceptions()
  try:
    error = validation.convert_validation_error_to_service_error(
      ValidationError("field", "value", "constraint")
    )
    assert type(error) is sentinel_module.ServiceValidationError
  finally:
    _restore_exceptions(original_module)


def test_button_homeassistant_error_alias_tracks_rebind() -> None:
  """Button helpers should raise the rebound HomeAssistantError type."""

  original_module, sentinel_module = _install_sentinel_exceptions()
  try:
    with pytest.raises(sentinel_module.HomeAssistantError):
      raise button.HomeAssistantError("boom")
  finally:
    _restore_exceptions(original_module)


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
