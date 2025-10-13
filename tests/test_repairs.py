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
from custom_components.pawcontrol.types import CacheRepairAggregate

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
    result = asyncio.run(flow.async_step_coordinator_error({"action": "reload"}))

    assert reload_mock.await_count == 1
    assert delete_issue_mock.await_count == 1
    assert result["type"] == "create_entry"


def test_coordinator_error_flow_handles_failed_reload(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Coordinator repair should keep the issue when reload fails."""

    module, _, _, delete_issue_mock = repairs_module
    entry = module.ConfigEntry("entry")
    entry.data = {module.CONF_DOGS: []}
    entry.options = {}
    config_entries, _, reload_mock = _build_config_entries(entry)

    reload_mock.return_value = False

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
    result = asyncio.run(flow.async_step_coordinator_error({"action": "reload"}))

    assert reload_mock.await_count == 1
    cache_delete_calls = [
        call
        for call in delete_issue_mock.await_args_list
        if call.args and str(call.args[-1]).endswith("_cache_health")
    ]
    assert not cache_delete_calls
    assert result["type"] == "form"
    assert result["errors"]["base"] == "reload_failed"


def test_async_check_for_issues_checks_coordinator_health(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any]],
) -> None:
    """Coordinator health should be validated when scanning for issues."""

    module, create_issue_mock, _, _ = repairs_module

    hass = SimpleNamespace()
    hass.services = SimpleNamespace(has_service=lambda *args, **kwargs: True)

    entry = SimpleNamespace(
        entry_id="entry",
        data={
            module.CONF_DOGS: [
                {
                    module.CONF_DOG_ID: "dog_alpha",
                    module.CONF_DOG_NAME: "Dog Alpha",
                    "modules": {},
                }
            ]
        },
        options={},
        version=1,
    )

    original_get_runtime_data = module.get_runtime_data
    module.get_runtime_data = lambda _hass, _entry: None

    try:
        asyncio.run(module.async_check_for_issues(hass, entry))
    finally:
        module.get_runtime_data = original_get_runtime_data

    assert create_issue_mock.await_count == 1
    kwargs = create_issue_mock.await_args.kwargs
    assert kwargs["translation_key"] == module.ISSUE_COORDINATOR_ERROR
    assert kwargs["data"]["error"] == "coordinator_not_initialized"


def test_async_check_for_issues_publishes_cache_health_issue(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Aggregated cache anomalies should surface as repairs issues."""

    module, create_issue_mock, _, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    hass = SimpleNamespace()
    hass.services = SimpleNamespace(has_service=lambda *args, **kwargs: True)

    summary = CacheRepairAggregate(
        total_caches=1,
        anomaly_count=1,
        severity="warning",
        generated_at="2024-01-01T00:00:00+00:00",
        issues=[
            {
                "cache": "adaptive_cache",
                "entries": 5,
                "hits": 3,
                "misses": 2,
                "hit_rate": 60.0,
                "expired_entries": 1,
            }
        ],
        caches_with_expired_entries=["adaptive_cache"],
    )

    class _DataManager:
        def cache_repair_summary(self) -> CacheRepairAggregate:
            return summary

    runtime_data = SimpleNamespace(
        data_manager=_DataManager(),
        coordinator=SimpleNamespace(last_update_success=True),
    )

    entry = SimpleNamespace(
        entry_id="entry",
        data={
            module.CONF_DOGS: [
                {
                    module.CONF_DOG_ID: "dog",
                    module.CONF_DOG_NAME: "Dog",
                    "modules": {},
                }
            ]
        },
        options={},
        version=1,
    )

    original_get_runtime_data = module.get_runtime_data
    module.get_runtime_data = lambda _hass, _entry: runtime_data

    try:
        asyncio.run(module.async_check_for_issues(hass, entry))
    finally:
        module.get_runtime_data = original_get_runtime_data

    assert create_issue_mock.await_count == 1
    kwargs = create_issue_mock.await_args.kwargs
    assert kwargs["translation_key"] == module.ISSUE_CACHE_HEALTH_SUMMARY
    assert kwargs["data"]["summary"] == summary.to_mapping()
    cache_delete_calls = [
        call
        for call in delete_issue_mock.await_args_list
        if call.args and str(call.args[-1]).endswith("_cache_health")
    ]
    assert not cache_delete_calls


def test_async_check_for_issues_clears_cache_issue_without_anomalies(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Repairs should clear cache issues when anomalies disappear."""

    module, create_issue_mock, _, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    hass = SimpleNamespace()
    hass.services = SimpleNamespace(has_service=lambda *args, **kwargs: True)

    summary = CacheRepairAggregate(
        total_caches=1,
        anomaly_count=0,
        severity="info",
        generated_at="2024-01-01T00:00:00+00:00",
    )

    class _DataManager:
        def cache_repair_summary(self) -> CacheRepairAggregate:
            return summary

    runtime_data = SimpleNamespace(
        data_manager=_DataManager(),
        coordinator=SimpleNamespace(last_update_success=True),
    )

    entry = SimpleNamespace(
        entry_id="entry",
        data={
            module.CONF_DOGS: [
                {
                    module.CONF_DOG_ID: "dog",
                    module.CONF_DOG_NAME: "Dog",
                    "modules": {},
                }
            ]
        },
        options={},
        version=1,
    )

    original_get_runtime_data = module.get_runtime_data
    module.get_runtime_data = lambda _hass, _entry: runtime_data

    try:
        asyncio.run(module.async_check_for_issues(hass, entry))
    finally:
        module.get_runtime_data = original_get_runtime_data

    assert create_issue_mock.await_count == 0
    cache_delete_calls = [
        call
        for call in delete_issue_mock.await_args_list
        if call.args and str(call.args[-1]).endswith("_cache_health")
    ]
    assert len(cache_delete_calls) == 1


def test_async_check_for_issues_surfaces_reconfigure_warnings(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Reconfigure telemetry warnings should surface as repair issues."""

    module, create_issue_mock, _, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    hass = SimpleNamespace()
    hass.services = SimpleNamespace(has_service=lambda *args, **kwargs: True)

    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
        coordinator=SimpleNamespace(last_update_success=True),
    )

    entry = SimpleNamespace(
        entry_id="entry",
        data={
            module.CONF_DOGS: [
                {
                    module.CONF_DOG_ID: "dog",
                    module.CONF_DOG_NAME: "Dog",
                    "modules": {},
                }
            ]
        },
        options={
            "last_reconfigure": "2024-01-02T03:04:05+00:00",
            "reconfigure_telemetry": {
                "timestamp": "2024-01-02T03:04:05+00:00",
                "requested_profile": "balanced",
                "previous_profile": "advanced",
                "dogs_count": 1,
                "estimated_entities": 8,
                "compatibility_warnings": [
                    "GPS module disabled for configured dog",
                ],
                "health_summary": {"healthy": True, "issues": [], "warnings": []},
            },
        },
        version=1,
    )

    original_get_runtime_data = module.get_runtime_data
    module.get_runtime_data = lambda _hass, _entry: runtime_data

    try:
        asyncio.run(module.async_check_for_issues(hass, entry))
    finally:
        module.get_runtime_data = original_get_runtime_data

    assert any(
        call.kwargs["translation_key"] == module.ISSUE_RECONFIGURE_WARNINGS
        for call in create_issue_mock.await_args_list
    )


def test_async_check_for_issues_surfaces_reconfigure_health_issue(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Health summaries from reconfigure telemetry should raise issues."""

    module, create_issue_mock, _, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    hass = SimpleNamespace()
    hass.services = SimpleNamespace(has_service=lambda *args, **kwargs: True)

    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
        coordinator=SimpleNamespace(last_update_success=True),
    )

    entry = SimpleNamespace(
        entry_id="entry",
        data={
            module.CONF_DOGS: [
                {
                    module.CONF_DOG_ID: "dog",
                    module.CONF_DOG_NAME: "Dog",
                    "modules": {},
                }
            ]
        },
        options={
            "last_reconfigure": "2024-01-02T03:04:05+00:00",
            "reconfigure_telemetry": {
                "timestamp": "2024-01-02T03:04:05+00:00",
                "requested_profile": "balanced",
                "previous_profile": "advanced",
                "dogs_count": 1,
                "estimated_entities": 8,
                "compatibility_warnings": [],
                "health_summary": {
                    "healthy": False,
                    "issues": ["profile missing GPS support"],
                    "warnings": ["consider reauth"],
                },
            },
        },
        version=1,
    )

    original_get_runtime_data = module.get_runtime_data
    module.get_runtime_data = lambda _hass, _entry: runtime_data

    try:
        asyncio.run(module.async_check_for_issues(hass, entry))
    finally:
        module.get_runtime_data = original_get_runtime_data

    assert any(
        call.kwargs["translation_key"] == module.ISSUE_RECONFIGURE_HEALTH
        for call in create_issue_mock.await_args_list
    )


def test_async_check_for_issues_clears_reconfigure_issues_when_clean(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Reconfigure telemetry without warnings should clear existing issues."""

    module, create_issue_mock, _, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    hass = SimpleNamespace()
    hass.services = SimpleNamespace(has_service=lambda *args, **kwargs: True)

    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
        coordinator=SimpleNamespace(last_update_success=True),
    )

    entry = SimpleNamespace(
        entry_id="entry",
        data={
            module.CONF_DOGS: [
                {
                    module.CONF_DOG_ID: "dog",
                    module.CONF_DOG_NAME: "Dog",
                    "modules": {},
                }
            ]
        },
        options={
            "last_reconfigure": "2024-01-02T03:04:05+00:00",
            "reconfigure_telemetry": {
                "timestamp": "2024-01-02T03:04:05+00:00",
                "requested_profile": "balanced",
                "previous_profile": "advanced",
                "dogs_count": 1,
                "estimated_entities": 8,
                "compatibility_warnings": [],
                "health_summary": {"healthy": True, "issues": [], "warnings": []},
            },
        },
        version=1,
    )

    original_get_runtime_data = module.get_runtime_data
    module.get_runtime_data = lambda _hass, _entry: runtime_data

    try:
        asyncio.run(module.async_check_for_issues(hass, entry))
    finally:
        module.get_runtime_data = original_get_runtime_data

    assert not any(
        call.kwargs["translation_key"]
        in {module.ISSUE_RECONFIGURE_WARNINGS, module.ISSUE_RECONFIGURE_HEALTH}
        for call in create_issue_mock.await_args_list
    )
    assert any(
        call.args and str(call.args[-1]).endswith("reconfigure_warnings")
        for call in delete_issue_mock.await_args_list
    )
    assert any(
        call.args and str(call.args[-1]).endswith("reconfigure_health")
        for call in delete_issue_mock.await_args_list
    )


def test_notification_check_accepts_mobile_app_service_prefix(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any]],
) -> None:
    """Notification checks should detect mobile_app_* notify services."""

    module, create_issue_mock, _, _ = repairs_module

    hass = SimpleNamespace()

    hass.services = SimpleNamespace(
        has_service=lambda domain, service: False,
        async_services=lambda: {"notify": {"mobile_app_jane": object()}},
    )

    entry = SimpleNamespace(
        entry_id="entry",
        data={
            module.CONF_DOGS: [
                {
                    module.CONF_DOG_ID: "dog_alpha",
                    module.CONF_DOG_NAME: "Dog Alpha",
                    "modules": {module.MODULE_NOTIFICATIONS: True},
                }
            ]
        },
        options={"notifications": {"mobile_notifications": True}},
        version=1,
    )

    asyncio.run(module._check_notification_configuration_issues(hass, entry))

    assert create_issue_mock.await_count == 0


def test_async_publish_feeding_compliance_issue_creates_alert(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Feeding compliance issues should create repair alerts with metadata."""

    module, create_issue_mock, issue_severity_cls, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)

    payload = {
        "dog_id": "buddy",
        "dog_name": "Buddy",
        "days_to_check": 5,
        "notify_on_issues": True,
        "notification_sent": True,
        "notification_id": "notif-1",
        "result": {
            "status": "completed",
            "compliance_score": 65,
            "compliance_rate": 65.0,
            "days_analyzed": 5,
            "days_with_issues": 2,
            "checked_at": "2024-05-05T10:00:00+00:00",
            "compliance_issues": [
                {
                    "date": "2024-05-04",
                    "issues": ["Missed breakfast"],
                    "severity": "high",
                }
            ],
            "missed_meals": [{"date": "2024-05-03", "actual": 1, "expected": 2}],
            "recommendations": ["Schedule a vet visit"],
        },
    }

    asyncio.run(
        module.async_publish_feeding_compliance_issue(
            hass,
            entry,
            payload,
            context_metadata={"context_id": "ctx-1"},
        )
    )

    assert create_issue_mock.await_count == 1
    kwargs = create_issue_mock.await_args.kwargs
    assert kwargs["translation_key"] == module.ISSUE_FEEDING_COMPLIANCE_ALERT
    assert kwargs["severity"] == issue_severity_cls.CRITICAL
    data = kwargs["data"]
    assert data["dog_id"] == "buddy"
    assert data["issue_count"] == 1
    assert data["missed_meal_count"] == 1
    assert data["context_metadata"]["context_id"] == "ctx-1"
    assert data["notification_sent"] is True
    summary = data["localized_summary"]
    assert summary["title"].startswith("🍽️ Feeding compliance alert")
    assert summary["score_line"].startswith("Score: 65")
    assert data["notification_title"] == summary["title"]
    assert data["notification_message"] is not None
    assert data["issue_summary"] == ["2024-05-04: Missed breakfast"]
    assert data["missed_meal_summary"] == ["2024-05-03: 1/2 meals"]
    assert data["recommendations_summary"] == ["Schedule a vet visit"]


def test_async_publish_feeding_compliance_issue_falls_back_without_critical(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Severity should fall back when CRITICAL is unavailable."""

    module, create_issue_mock, _, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    class LimitedSeverity(StrEnum):
        ERROR = "error"
        WARNING = "warning"

    monkeypatch.setattr(module.ir, "IssueSeverity", LimitedSeverity, raising=False)
    monkeypatch.setattr(
        module.ir, "async_create_issue", create_issue_mock, raising=False
    )

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)

    payload = {
        "dog_id": "buddy",
        "dog_name": "Buddy",
        "days_to_check": 5,
        "notify_on_issues": True,
        "notification_sent": False,
        "result": {
            "status": "completed",
            "compliance_score": 65,
            "compliance_rate": 65.0,
            "days_analyzed": 5,
            "days_with_issues": 2,
            "compliance_issues": [
                {
                    "date": "2024-05-04",
                    "issues": ["Missed breakfast"],
                    "severity": "high",
                }
            ],
            "missed_meals": [
                {"date": "2024-05-03", "actual": 1, "expected": 2},
            ],
            "recommendations": ["Schedule a vet visit"],
        },
    }

    asyncio.run(
        module.async_publish_feeding_compliance_issue(
            hass,
            entry,
            payload,
            context_metadata=None,
        )
    )

    assert create_issue_mock.await_count == 1
    kwargs = create_issue_mock.await_args.kwargs
    assert kwargs["severity"] == LimitedSeverity.ERROR


def test_async_publish_feeding_compliance_issue_clears_resolved_alert(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Resolved compliance checks should clear existing repair issues."""

    module, create_issue_mock, _, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)

    payload = {
        "dog_id": "buddy",
        "dog_name": "Buddy",
        "days_to_check": 5,
        "notify_on_issues": True,
        "notification_sent": False,
        "result": {
            "status": "completed",
            "compliance_score": 100,
            "compliance_rate": 100.0,
            "days_analyzed": 5,
            "days_with_issues": 0,
            "compliance_issues": [],
            "missed_meals": [],
            "recommendations": [],
        },
    }

    asyncio.run(
        module.async_publish_feeding_compliance_issue(
            hass,
            entry,
            payload,
            context_metadata=None,
        )
    )

    assert create_issue_mock.await_count == 0
    assert delete_issue_mock.await_count == 1
    args = delete_issue_mock.await_args.args
    assert args[0] == hass
    assert args[1] == module.DOMAIN


def test_async_publish_feeding_compliance_issue_handles_no_data(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """No-data results should raise a warning issue."""

    module, create_issue_mock, issue_severity_cls, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)

    payload = {
        "dog_id": "buddy",
        "dog_name": None,
        "days_to_check": 3,
        "notify_on_issues": False,
        "notification_sent": False,
        "result": {
            "status": "no_data",
            "message": "Telemetry unavailable",
        },
    }

    asyncio.run(
        module.async_publish_feeding_compliance_issue(
            hass,
            entry,
            payload,
            context_metadata={"context_id": None},
        )
    )

    assert create_issue_mock.await_count == 1
    kwargs = create_issue_mock.await_args.kwargs
    assert kwargs["translation_key"] == module.ISSUE_FEEDING_COMPLIANCE_NO_DATA
    assert kwargs["severity"] == issue_severity_cls.WARNING
    data = kwargs["data"]
    assert data["dog_name"] == "buddy"
    assert data["message"] == "Telemetry unavailable"
    summary = data["localized_summary"]
    assert summary["title"].startswith("🍽️ Feeding telemetry missing")
    assert summary["message"] == "Telemetry unavailable"
    assert data["issue_summary"] == []
    assert delete_issue_mock.await_count == 0


def test_async_publish_feeding_compliance_issue_sanitises_mapping_message(
    repairs_module: tuple[ModuleType, AsyncMock, type[Any], AsyncMock],
) -> None:
    """Structured messages should fall back to the localised summary text."""

    module, create_issue_mock, _issue_severity_cls, delete_issue_mock = repairs_module
    create_issue_mock.reset_mock()
    delete_issue_mock.reset_mock()

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)

    payload = {
        "dog_id": "buddy",
        "dog_name": None,
        "days_to_check": 2,
        "notify_on_issues": False,
        "notification_sent": False,
        "result": {
            "status": "no_data",
            "message": {"description": "Telemetry offline"},
        },
        "localized_summary": {
            "title": "🍽️ Feeding telemetry missing for Buddy",
            "message": "Telemetry offline",
            "score_line": None,
            "missed_meals": [],
            "issues": [],
            "recommendations": [],
        },
    }

    asyncio.run(
        module.async_publish_feeding_compliance_issue(
            hass,
            entry,
            payload,
            context_metadata=None,
        )
    )

    data = create_issue_mock.await_args.kwargs["data"]
    assert data["message"] == "Telemetry offline"
    assert data["localized_summary"]["message"] == "Telemetry offline"
