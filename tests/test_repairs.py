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


def _install_homeassistant_stubs() -> tuple[AsyncMock, type[Any], AsyncMock]:
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

    class RepairsFlow:  # pragma: no cover - minimal flow helpers
        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any | None = None,
            description_placeholders: dict[str, Any] | None = None,
            errors: dict[str, Any] | None = None,
        ) -> FlowResult:
            return FlowResult(
                {
                    "type": "form",
                    "step_id": step_id,
                    "data_schema": data_schema,
                    "description_placeholders": description_placeholders or {},
                    "errors": errors or {},
                }
            )

        def async_external_step(
            self, *, step_id: str, url: str
        ) -> FlowResult:  # pragma: no cover - passthrough helper
            return FlowResult({"type": "external", "step_id": step_id, "url": url})

        def async_create_entry(
            self, *, title: str, data: dict[str, Any]
        ) -> FlowResult:  # pragma: no cover - passthrough helper
            return FlowResult({"type": "create_entry", "title": title, "data": data})

        def async_abort(
            self, *, reason: str
        ) -> FlowResult:  # pragma: no cover - passthrough helper
            return FlowResult({"type": "abort", "reason": reason})

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
    async_delete_issue = AsyncMock()
    issue_registry.IssueSeverity = IssueSeverity
    issue_registry.DOMAIN = "issues"
    issue_registry.async_create_issue = async_create_issue
    issue_registry.async_delete_issue = async_delete_issue
    sys.modules[issue_registry.__name__] = issue_registry
    helpers.issue_registry = issue_registry

    dt_module = ModuleType("homeassistant.util.dt")
    dt_module.utcnow = lambda: datetime.now(UTC)
    sys.modules[dt_module.__name__] = dt_module
    util.dt = dt_module

    return async_create_issue, IssueSeverity, async_delete_issue


@pytest.fixture
def repairs_module() -> tuple[ModuleType, AsyncMock, type[Any], AsyncMock]:
    """Return the loaded repairs module alongside the issue registry mock."""

    async_create_issue, issue_severity_cls, async_delete_issue = (
        _install_homeassistant_stubs()
    )

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

    return module, async_create_issue, issue_severity_cls, async_delete_issue


def test_async_create_issue_normalises_unknown_severity(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Severity values outside the registry should fall back to warnings."""

    module, create_issue_mock, issue_severity_cls, _ = repairs_module
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
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Passing an IssueSeverity instance should be preserved."""

    module, create_issue_mock, issue_severity_cls, _ = repairs_module
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


def _build_config_entries(
    entry: Any,
) -> tuple[Any, list[tuple[Any | None, Any | None]], AsyncMock]:
    """Return a config entries namespace with tracking mocks."""

    updates: list[tuple[Any | None, Any | None]] = []
    reload_mock = AsyncMock(return_value=True)

    def async_get_entry(entry_id: str) -> Any | None:
        return entry if entry.entry_id == entry_id else None

    def async_update_entry(
        entry_obj: Any, data: Any | None = None, options: Any | None = None
    ) -> None:
        if data is not None:
            entry_obj.data = data
        if options is not None:
            entry_obj.options = options
        updates.append((data, options))

    config_entries = SimpleNamespace(
        async_get_entry=async_get_entry,
        async_update_entry=async_update_entry,
        async_reload=reload_mock,
    )

    return config_entries, updates, reload_mock


def _create_flow(module: ModuleType, hass: Any, issue_id: str) -> Any:
    """Instantiate the repairs flow with the provided Home Assistant stub."""

    flow = module.PawControlRepairsFlow()
    flow.hass = hass
    flow.issue_id = issue_id
    return flow


def test_storage_warning_flow_reduces_retention(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Storage warning repair should lower retention and resolve the issue."""

    module, _, _, delete_issue_mock = repairs_module
    entry = module.ConfigEntry("entry")
    entry.data = {module.CONF_DOGS: []}
    entry.options = {"data_retention_days": 400}
    config_entries, updates, _ = _build_config_entries(entry)

    issue_id = "entry_storage_warning"
    issue_data = {
        "config_entry_id": entry.entry_id,
        "issue_type": module.ISSUE_STORAGE_WARNING,
        "current_retention": 400,
        "recommended_max": 365,
        "suggestion": "Consider reducing data retention period",
    }

    hass = SimpleNamespace(
        data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
        config_entries=config_entries,
    )

    flow = _create_flow(module, hass, issue_id)

    result = asyncio.run(flow.async_step_init())
    assert result["type"] == "form"
    assert result["step_id"] == "storage_warning"

    delete_issue_mock.reset_mock()
    updates.clear()
    asyncio.run(flow.async_step_storage_warning({"action": "reduce_retention"}))

    assert entry.options["data_retention_days"] == 365
    assert updates[-1][1]["data_retention_days"] == 365
    assert delete_issue_mock.await_count == 1


def test_module_conflict_flow_disables_extra_gps_modules(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Module conflict repair should disable GPS for dogs beyond the limit."""

    module, _, _, delete_issue_mock = repairs_module
    entry = module.ConfigEntry("entry")
    entry.data = {
        module.CONF_DOGS: [
            {
                module.CONF_DOG_ID: f"dog{i}",
                module.CONF_DOG_NAME: f"Dog {i}",
                "modules": {module.MODULE_GPS: True, module.MODULE_HEALTH: True},
            }
            for i in range(6)
        ]
    }
    entry.options = {}
    config_entries, _, _ = _build_config_entries(entry)

    issue_id = "entry_module_conflict"
    issue_data = {
        "config_entry_id": entry.entry_id,
        "issue_type": module.ISSUE_MODULE_CONFLICT,
        "intensive_dogs": 6,
        "total_dogs": 6,
        "suggestion": "Consider selective module enabling",
    }

    hass = SimpleNamespace(
        data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
        config_entries=config_entries,
    )

    flow = _create_flow(module, hass, issue_id)
    asyncio.run(flow.async_step_init())

    delete_issue_mock.reset_mock()
    asyncio.run(flow.async_step_module_conflict({"action": "reduce_load"}))

    disabled = [
        dog
        for dog in entry.data[module.CONF_DOGS]
        if dog["modules"].get(module.MODULE_GPS) is False
    ]
    assert disabled, "Expected at least one dog to have GPS disabled"
    assert delete_issue_mock.await_count == 1


def test_invalid_dog_data_flow_removes_entries(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Invalid dog data repair should remove malformed entries."""

    module, _, _, delete_issue_mock = repairs_module
    entry = module.ConfigEntry("entry")
    entry.data = {
        module.CONF_DOGS: [
            {
                module.CONF_DOG_ID: "valid",
                module.CONF_DOG_NAME: "Valid Dog",
            },
            {module.CONF_DOG_ID: "invalid", module.CONF_DOG_NAME: ""},
        ]
    }
    entry.options = {}
    config_entries, _, _ = _build_config_entries(entry)

    issue_id = "entry_invalid_dogs"
    issue_data = {
        "config_entry_id": entry.entry_id,
        "issue_type": module.ISSUE_INVALID_DOG_DATA,
        "invalid_dogs": ["invalid"],
        "total_dogs": 2,
    }

    hass = SimpleNamespace(
        data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
        config_entries=config_entries,
    )

    flow = _create_flow(module, hass, issue_id)
    asyncio.run(flow.async_step_init())

    delete_issue_mock.reset_mock()
    asyncio.run(flow.async_step_invalid_dog_data({"action": "clean_up"}))

    dogs = entry.data[module.CONF_DOGS]
    assert len(dogs) == 1 and dogs[0][module.CONF_DOG_ID] == "valid"
    assert delete_issue_mock.await_count == 1


def test_coordinator_error_flow_triggers_reload(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Coordinator repair should reload the config entry and resolve the issue."""

    module, _, _, delete_issue_mock = repairs_module
    entry = module.ConfigEntry("entry")
    entry.data = {module.CONF_DOGS: []}
    entry.options = {}
    config_entries, _, reload_mock = _build_config_entries(entry)

    issue_id = "entry_coordinator_error"
    issue_data = {
        "config_entry_id": entry.entry_id,
        "issue_type": module.ISSUE_COORDINATOR_ERROR,
        "error": "coordinator_not_initialized",
        "suggestion": "Try reloading the integration",
    }

    hass = SimpleNamespace(
        data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
        config_entries=config_entries,
    )

    flow = _create_flow(module, hass, issue_id)
    asyncio.run(flow.async_step_init())

    delete_issue_mock.reset_mock()
    reload_mock.reset_mock()
    asyncio.run(flow.async_step_coordinator_error({"action": "reload"}))

    assert reload_mock.await_count == 1
    assert delete_issue_mock.await_count == 1
