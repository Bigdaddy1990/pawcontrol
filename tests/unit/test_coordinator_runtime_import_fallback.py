"""Tests for coordinator_runtime import fallbacks."""

from datetime import datetime
import importlib
import sys
from types import ModuleType

import pytest


@pytest.mark.asyncio
async def test_coordinator_runtime_uses_datetime_fallback_when_dt_util_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The module should expose a UTC helper even without HA datetime utilities."""
    original_import = __import__

    def _fake_import(
        name: str,
        globals_: dict[str, object] | None = None,
        locals_: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> ModuleType:
        caller = globals_.get("__name__") if globals_ else None
        if name == "homeassistant.util" and "dt" in fromlist and caller == module_name:
            msg = "simulated missing homeassistant.util.dt"
            raise ImportError(msg)
        return original_import(name, globals_, locals_, fromlist, level)

    module_name = "custom_components.pawcontrol.coordinator_runtime"
    previous_module = sys.modules.pop(module_name, None)
    monkeypatch.setattr("builtins.__import__", _fake_import)

    try:
        module = importlib.import_module(module_name)
    finally:
        sys.modules.pop(module_name, None)
        if previous_module is not None:
            sys.modules[module_name] = previous_module

    generated = module.dt_util.utcnow()
    assert isinstance(generated, datetime)
    assert generated.tzinfo is not None
