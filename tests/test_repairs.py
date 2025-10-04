"""Tests for the PawControl repair issue helpers.

The Home Assistant integration test suite is intentionally lightweight in this
kata-style repository.  We provide focused coverage for the repair helpers to
ensure they gracefully handle unexpected severity values even without the real
Home Assistant runtime.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import UTC, datetime, timezone
from enum import StrEnum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_package(name: str, path: Path) -> ModuleType:
    """Ensure a namespace package exists for dynamic imports."""

    module = sys.modules.get(name)
    if module is None:
        module = ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module
    return module


def _load_module(name: str, path: Path) -> ModuleType:
    """Import ``name`` from ``path`` without executing package ``__init__`` files."""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _install_homeassistant_stubs() -> tuple[AsyncMock, type[Any]]:
    """Register minimal Home Assistant stubs required by repairs.py."""

    sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    helpers = sys.modules.setdefault(
        "homeassistant.helpers", ModuleType("homeassistant.helpers")
    )
    components = sys.modules.setdefault(
        "homeassistant.components", ModuleType("homeassistant.components")
    )
    util = sys.modules.setdefault(
        "homeassistant.util", ModuleType("homeassistant.util")
    )
    data_entry_flow = ModuleType("homeassistant.data_entry_flow")

    class FlowResult(dict[str, Any]):  # pragma: no cover - simple mapping alias
        pass

    data_entry_flow.FlowResult = FlowResult
    sys.modules[data_entry_flow.__name__] = data_entry_flow

    core = ModuleType("homeassistant.core")

    class HomeAssistant:  # pragma: no cover - minimal attribute container
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}

    core.HomeAssistant = HomeAssistant

    def callback(func):  # pragma: no cover - synchronous passthrough decorator
        return func

    core.callback = callback
    sys.modules[core.__name__] = core

    config_entries = ModuleType("homeassistant.config_entries")

    class ConfigEntry:  # pragma: no cover - simple stand-in for tests
        def __init__(self, entry_id: str) -> None:
            self.entry_id = entry_id
            self.data: dict[str, Any] = {}
            self.options: dict[str, Any] = {}
            self.version = 1

    config_entries.ConfigEntry = ConfigEntry
    sys.modules[config_entries.__name__] = config_entries

    repairs_component = ModuleType("homeassistant.components.repairs")

    class RepairsFlow:  # pragma: no cover - unused base class placeholder
        pass

    repairs_component.RepairsFlow = RepairsFlow
    sys.modules[repairs_component.__name__] = repairs_component
    components.repairs = repairs_component

    selector_module = ModuleType("homeassistant.helpers.selector")

    def selector(
        schema: dict[str, Any],
    ) -> dict[str, Any]:  # pragma: no cover - pass-through helper
        return schema

    selector_module.selector = selector
    sys.modules[selector_module.__name__] = selector_module
    helpers.selector = selector_module

    device_registry = ModuleType("homeassistant.helpers.device_registry")

    class DeviceInfo:  # pragma: no cover - placeholder structure
        def __init__(self, **_: Any) -> None:
            pass

    class DeviceEntry:  # pragma: no cover - placeholder structure
        pass

    class _DummyDeviceRegistry:  # pragma: no cover - minimal helper implementation
        def async_get_or_create(self, **_: Any) -> DeviceEntry:
            return DeviceEntry()

        def async_update_device(self, *args: Any, **kwargs: Any) -> DeviceEntry | None:
            return DeviceEntry() if kwargs else None

    device_registry.DeviceInfo = DeviceInfo
    device_registry.DeviceEntry = DeviceEntry
    device_registry.async_get = lambda hass: _DummyDeviceRegistry()
    sys.modules[device_registry.__name__] = device_registry
    helpers.device_registry = device_registry

    entity_registry = ModuleType("homeassistant.helpers.entity_registry")

    class _DummyEntityRegistry:  # pragma: no cover - minimal helper implementation
        def async_get(self, _entity_id: str) -> None:
            return None

        def async_update_entity(self, *args: Any, **kwargs: Any) -> None:
            return None

    entity_registry.async_get = lambda hass: _DummyEntityRegistry()
    sys.modules[entity_registry.__name__] = entity_registry
    helpers.entity_registry = entity_registry

    issue_registry = ModuleType("homeassistant.helpers.issue_registry")

    class IssueSeverity(
        StrEnum
    ):  # pragma: no cover - mirrors Home Assistant enum semantics
        CRITICAL = "critical"
        ERROR = "error"
        WARNING = "warning"

    async_create_issue = AsyncMock()
    issue_registry.IssueSeverity = IssueSeverity
    issue_registry.async_create_issue = async_create_issue
    sys.modules[issue_registry.__name__] = issue_registry
    helpers.issue_registry = issue_registry

    dt_module = ModuleType("homeassistant.util.dt")
    dt_module.utcnow = lambda: datetime.now(UTC)
    sys.modules[dt_module.__name__] = dt_module
    util.dt = dt_module

    return async_create_issue, IssueSeverity


@pytest.fixture
def repairs_module() -> tuple[ModuleType, AsyncMock, type[Any]]:
    """Return the loaded repairs module alongside the issue registry mock."""

    async_create_issue, issue_severity_cls = _install_homeassistant_stubs()

    _ensure_package("custom_components", PROJECT_ROOT / "custom_components")
    _ensure_package(
        "custom_components.pawcontrol",
        PROJECT_ROOT / "custom_components" / "pawcontrol",
    )

    module_name = "custom_components.pawcontrol.repairs"
    sys.modules.pop(module_name, None)
    module = _load_module(
        module_name, PROJECT_ROOT / "custom_components" / "pawcontrol" / "repairs.py"
    )

    return module, async_create_issue, issue_severity_cls


def test_async_create_issue_normalises_unknown_severity(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Severity values outside the registry should fall back to warnings."""

    module, create_issue_mock, issue_severity_cls = repairs_module
    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)

    caplog.set_level("WARNING")

    asyncio.run(
        module.async_create_issue(
            hass,
            entry,
            "entry_unknown",
            "test_issue",
            severity="info",
            data={"foo": "bar"},
        )
    )

    assert create_issue_mock.await_count == 1
    kwargs = create_issue_mock.await_args.kwargs
    assert kwargs["severity"] == issue_severity_cls.WARNING
    assert (
        kwargs["translation_placeholders"]["severity"]
        == issue_severity_cls.WARNING.value
    )
    assert "Unsupported issue severity 'info'" in caplog.text


def test_async_create_issue_accepts_issue_severity_instances(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any]],
) -> None:
    """Passing an IssueSeverity instance should be preserved."""

    module, create_issue_mock, issue_severity_cls = repairs_module
    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)

    asyncio.run(
        module.async_create_issue(
            hass,
            entry,
            "entry_error",
            "test_issue",
            severity=issue_severity_cls.ERROR,
        )
    )

    assert create_issue_mock.await_count == 1
    kwargs = create_issue_mock.await_args.kwargs
    assert kwargs["severity"] == issue_severity_cls.ERROR
    assert (
        kwargs["translation_placeholders"]["severity"] == issue_severity_cls.ERROR.value
    )
