"""Tests for the PawControl repair issue helpers.

The Home Assistant integration test suite is intentionally lightweight in this
kata-style repository.  We provide focused coverage for the repair helpers to
ensure they gracefully handle unexpected severity values even without the real
Home Assistant runtime.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timezone
from enum import StrEnum
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, call

import pytest

from custom_components.pawcontrol.types import (
  CacheRepairAggregate,
  ConfigEntryDataPayload,
  PawControlOptionsData,
)
from tests.helpers import homeassistant_test_stubs

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_package(name: str, path: Path) -> ModuleType:
  """Ensure a namespace package exists for dynamic imports."""  # noqa: E111

  module = sys.modules.get(name)  # noqa: E111
  if module is None:  # noqa: E111
    module = ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = module
  return module  # noqa: E111


def _load_module(name: str, path: Path) -> ModuleType:
  """Import ``name`` from ``path`` without executing package ``__init__`` files."""  # noqa: E111

  spec = importlib.util.spec_from_file_location(name, path)  # noqa: E111
  if spec is None or spec.loader is None:  # noqa: E111
    raise RuntimeError(f"Cannot load module {name} from {path}")
  module = importlib.util.module_from_spec(spec)  # noqa: E111
  sys.modules[name] = module  # noqa: E111
  spec.loader.exec_module(module)  # noqa: E111
  return module  # noqa: E111


def _make_runtime_data(
  summary: CacheRepairAggregate | None = None,
  notification_manager: object | None = None,
) -> SimpleNamespace:
  return SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: summary),
    coordinator=SimpleNamespace(last_update_success=True),
    notification_manager=notification_manager,
  )


def _make_basic_entry(module: Any) -> SimpleNamespace:
  return SimpleNamespace(  # noqa: E111
    entry_id="entry",
    data={
      module.CONF_DOGS: [
        {
          module.CONF_DOG_ID: "dog",
          module.CONF_DOG_NAME: "Dog",
          "modules": {},
        },
      ],
    },
    options={},
    version=1,
  )


def _make_reconfigure_entry(
  module: Any,
  *,
  compatibility_warnings: list[str],
  health_summary: Mapping[str, object],
) -> SimpleNamespace:
  return SimpleNamespace(  # noqa: E111
    entry_id="entry",
    data={
      module.CONF_DOGS: [
        {
          module.CONF_DOG_ID: "dog",
          module.CONF_DOG_NAME: "Dog",
          "modules": {},
        },
      ],
    },
    options={
      "last_reconfigure": "2024-01-02T03:04:05+00:00",
      "reconfigure_telemetry": {
        "timestamp": "2024-01-02T03:04:05+00:00",
        "requested_profile": "balanced",
        "previous_profile": "advanced",
        "dogs_count": 1,
        "estimated_entities": 8,
        "compatibility_warnings": compatibility_warnings,
        "health_summary": health_summary,
      },
    },
    version=1,
  )


def _install_homeassistant_stubs() -> tuple[AsyncMock, type[StrEnum], AsyncMock]:
  """Register Home Assistant stubs required by repairs.py."""  # noqa: E111

  homeassistant_test_stubs.install_homeassistant_stubs()  # noqa: E111

  from homeassistant.components import repairs as repairs_component  # noqa: E111
  from homeassistant.helpers import issue_registry  # noqa: E111
  from homeassistant.util import dt as dt_util  # noqa: E111

  async_create_issue = AsyncMock()  # noqa: E111
  async_delete_issue = AsyncMock()  # noqa: E111

  class _RepairsFlowStub:  # noqa: E111
    """Minimal replacement for Home Assistant's repairs flow base class."""

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: Mapping[str, object] | None = None,
      description_placeholders: Mapping[str, object] | None = None,
      errors: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
      return {  # noqa: E111
        "type": "form",
        "step_id": step_id,
        "data_schema": data_schema,
        "description_placeholders": dict(description_placeholders or {}),
        "errors": dict(errors or {}),
      }

    def async_external_step(self, *, step_id: str, url: str) -> dict[str, object]:
      return {"type": "external", "step_id": step_id, "url": url}  # noqa: E111

    def async_create_entry(
      self,
      *,
      title: str,
      data: Mapping[str, object],
    ) -> dict[str, object]:
      return {"type": "create_entry", "title": title, "data": dict(data)}  # noqa: E111

    def async_abort(self, *, reason: str) -> dict[str, object]:
      return {"type": "abort", "reason": reason}  # noqa: E111

  repairs_component.RepairsFlow = _RepairsFlowStub  # noqa: E111

  class IssueSeverity(StrEnum):  # noqa: E111
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

  issue_registry.IssueSeverity = IssueSeverity  # noqa: E111
  issue_registry.async_create_issue = async_create_issue  # noqa: E111
  issue_registry.async_delete_issue = async_delete_issue  # noqa: E111

  # Ensure datetime helpers return timezone-aware values during tests.  # noqa: E114
  dt_util.utcnow = lambda: datetime.now(UTC)  # noqa: E111

  return async_create_issue, IssueSeverity, async_delete_issue  # noqa: E111


def _build_hass(*, domain: str | None = None) -> SimpleNamespace:
  hass = SimpleNamespace()  # noqa: E111
  if domain is not None:  # noqa: E111
    hass.data = {domain: {}}
  hass.services = SimpleNamespace(has_service=lambda *args, **kwargs: True)  # noqa: E111
  return hass  # noqa: E111


def _build_entry(
  module: Any,
  *,
  options: Mapping[str, Any] | None = None,
) -> SimpleNamespace:
  return SimpleNamespace(  # noqa: E111
    entry_id="entry",
    data={
      module.CONF_DOGS: [
        {
          module.CONF_DOG_ID: "dog",
          module.CONF_DOG_NAME: "Dog",
          "modules": {},
        },
      ],
    },
    options=dict(options or {}),
    version=1,
  )


def _run_check_for_issues(
  module: Any,
  hass: SimpleNamespace,
  entry: SimpleNamespace,
  runtime_data: SimpleNamespace,
) -> None:
  original_require_runtime_data = module.require_runtime_data  # noqa: E111
  module.require_runtime_data = lambda _hass, _entry: runtime_data  # noqa: E111

  try:  # noqa: E111
    asyncio.run(module.async_check_for_issues(hass, entry))
  finally:  # noqa: E111
    module.require_runtime_data = original_require_runtime_data


@pytest.fixture
def repairs_module() -> tuple[Any, AsyncMock, type[StrEnum], AsyncMock]:
  """Return the loaded repairs module alongside the issue registry mock."""  # noqa: E111

  async_create_issue, issue_severity_cls, async_delete_issue = (  # noqa: E111
    _install_homeassistant_stubs()
  )

  _ensure_package("custom_components", PROJECT_ROOT / "custom_components")  # noqa: E111
  _ensure_package(  # noqa: E111
    "custom_components.pawcontrol",
    PROJECT_ROOT / "custom_components" / "pawcontrol",
  )

  module_name = "custom_components.pawcontrol.repairs"  # noqa: E111
  sys.modules.pop(module_name, None)  # noqa: E111
  module = cast(  # noqa: E111
    Any,
    _load_module(
      module_name,
      PROJECT_ROOT / "custom_components" / "pawcontrol" / "repairs.py",
    ),
  )

  return module, async_create_issue, issue_severity_cls, async_delete_issue  # noqa: E111


def test_async_create_issue_normalises_unknown_severity(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Severity values outside the registry should fall back to warnings."""  # noqa: E111

  module, create_issue_mock, issue_severity_cls, _ = repairs_module  # noqa: E111
  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111

  caplog.set_level("WARNING")  # noqa: E111

  asyncio.run(  # noqa: E111
    module.async_create_issue(
      hass,
      entry,
      "entry_unknown",
      "test_issue",
      severity="info",
      data={"foo": "bar"},
    ),
  )

  assert create_issue_mock.await_count == 1  # noqa: E111
  await_args = create_issue_mock.await_args  # noqa: E111
  assert await_args is not None  # noqa: E111
  kwargs = await_args.kwargs  # noqa: E111
  severity_enum = cast(Any, issue_severity_cls)  # noqa: E111
  assert kwargs["severity"] == severity_enum.WARNING  # noqa: E111
  assert kwargs["translation_placeholders"]["severity"] == severity_enum.WARNING.value  # noqa: E111
  assert "Unsupported issue severity 'info'" in caplog.text  # noqa: E111


def test_async_create_issue_accepts_issue_severity_instances(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Passing an IssueSeverity instance should be preserved."""  # noqa: E111

  module, create_issue_mock, issue_severity_cls, _ = repairs_module  # noqa: E111
  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111

  asyncio.run(  # noqa: E111
    module.async_create_issue(
      hass,
      entry,
      "entry_error",
      "test_issue",
      severity=cast(Any, issue_severity_cls).ERROR,
    ),
  )

  assert create_issue_mock.await_count == 1  # noqa: E111
  await_args = create_issue_mock.await_args  # noqa: E111
  assert await_args is not None  # noqa: E111
  kwargs = await_args.kwargs  # noqa: E111
  severity_enum = cast(Any, issue_severity_cls)  # noqa: E111
  assert kwargs["severity"] == severity_enum.ERROR  # noqa: E111
  assert kwargs["translation_placeholders"]["severity"] == severity_enum.ERROR.value  # noqa: E111


def test_async_create_issue_passes_learn_more_url(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Learn-more URLs should be forwarded to the issue registry when supported."""  # noqa: E111

  module, create_issue_mock, _, _ = repairs_module  # noqa: E111
  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111

  asyncio.run(  # noqa: E111
    module.async_create_issue(
      hass,
      entry,
      "entry_warning",
      "test_issue",
      learn_more_url="https://example.com/learn-more",
    ),
  )

  assert create_issue_mock.await_count == 1  # noqa: E111
  await_args = create_issue_mock.await_args  # noqa: E111
  assert await_args is not None  # noqa: E111
  kwargs = await_args.kwargs  # noqa: E111
  assert kwargs["learn_more_url"] == "https://example.com/learn-more"  # noqa: E111


def _build_config_entries(
  entry: Any,
) -> tuple[Any, list[tuple[Any | None, Any | None]], AsyncMock]:
  """Return a config entries namespace with tracking mocks."""  # noqa: E111

  updates: list[tuple[Any | None, Any | None]] = []  # noqa: E111
  reload_mock = AsyncMock(return_value=True)  # noqa: E111

  def async_get_entry(entry_id: str) -> Any | None:  # noqa: E111
    return entry if entry.entry_id == entry_id else None

  def async_update_entry(  # noqa: E111
    entry_obj: Any,
    data: Any | None = None,
    options: Any | None = None,
  ) -> None:
    if data is not None:
      entry_obj.data = data  # noqa: E111
    if options is not None:
      entry_obj.options = options  # noqa: E111
    updates.append((data, options))

  config_entries = SimpleNamespace(  # noqa: E111
    async_get_entry=async_get_entry,
    async_update_entry=async_update_entry,
    async_reload=reload_mock,
  )

  return config_entries, updates, reload_mock  # noqa: E111


def _create_flow(module: ModuleType, hass: Any, issue_id: str) -> Any:
  """Instantiate the repairs flow with the provided Home Assistant stub."""  # noqa: E111

  flow = module.PawControlRepairsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.issue_id = issue_id  # noqa: E111
  return flow  # noqa: E111


def test_storage_warning_flow_reduces_retention(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Storage warning repair should lower retention and resolve the issue."""  # noqa: E111

  module, _, _, delete_issue_mock = repairs_module  # noqa: E111
  entry = module.ConfigEntry("entry")  # noqa: E111
  entry.data = {module.CONF_DOGS: []}  # noqa: E111
  entry.options = {"data_retention_days": 400}  # noqa: E111
  config_entries, updates, _ = _build_config_entries(entry)  # noqa: E111

  issue_id = "entry_storage_warning"  # noqa: E111
  issue_data = {  # noqa: E111
    "config_entry_id": entry.entry_id,
    "issue_type": module.ISSUE_STORAGE_WARNING,
    "current_retention": 400,
    "recommended_max": 365,
    "suggestion": "Consider reducing data retention period",
  }

  hass = SimpleNamespace(  # noqa: E111
    data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
    config_entries=config_entries,
  )

  flow = _create_flow(module, hass, issue_id)  # noqa: E111

  result = asyncio.run(flow.async_step_init())  # noqa: E111
  assert result["type"] == "form"  # noqa: E111
  assert result["step_id"] == "storage_warning"  # noqa: E111

  delete_issue_mock.reset_mock()  # noqa: E111
  updates.clear()  # noqa: E111
  asyncio.run(  # noqa: E111
    flow.async_step_storage_warning(
      {"action": "reduce_retention"},
    ),
  )

  assert entry.options["data_retention_days"] == 365  # noqa: E111
  _, options_payload = updates[-1]  # noqa: E111
  assert options_payload is not None  # noqa: E111
  assert options_payload["data_retention_days"] == 365  # noqa: E111
  assert delete_issue_mock.await_count == 1  # noqa: E111


def test_notification_auth_error_flow_shows_guidance(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Notification auth error repairs should guide users to credentials."""  # noqa: E111

  module, _, _, _ = repairs_module  # noqa: E111

  issue_id = "entry_notification_auth_error"  # noqa: E111
  issue_data = {  # noqa: E111
    "config_entry_id": "entry",
    "issue_type": module.ISSUE_NOTIFICATION_AUTH_ERROR,
    "services": "notify.mobile_app_phone",
    "service_count": 1,
    "total_failures": 4,
    "consecutive_failures": 3,
    "last_error_reasons": "unauthorized",
  }

  hass = SimpleNamespace(  # noqa: E111
    data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
  )

  flow = _create_flow(module, hass, issue_id)  # noqa: E111
  result = asyncio.run(flow.async_step_init())  # noqa: E111

  assert result["type"] == "form"  # noqa: E111
  assert result["step_id"] == "notification_auth_error"  # noqa: E111
  assert result["description_placeholders"]["service_count"] == 1  # noqa: E111


def test_notification_device_unreachable_flow_shows_guidance(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Notification unreachable repairs should guide users to device checks."""  # noqa: E111

  module, _, _, _ = repairs_module  # noqa: E111

  issue_id = "entry_notification_device_unreachable"  # noqa: E111
  issue_data = {  # noqa: E111
    "config_entry_id": "entry",
    "issue_type": module.ISSUE_NOTIFICATION_DEVICE_UNREACHABLE,
    "services": "notify.mobile_app_watch",
    "service_count": 1,
    "total_failures": 3,
    "consecutive_failures": 3,
    "last_error_reasons": "device offline",
  }

  hass = SimpleNamespace(  # noqa: E111
    data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
  )

  flow = _create_flow(module, hass, issue_id)  # noqa: E111
  result = asyncio.run(flow.async_step_init())  # noqa: E111

  assert result["type"] == "form"  # noqa: E111
  assert result["step_id"] == "notification_device_unreachable"  # noqa: E111
  assert result["description_placeholders"]["service_count"] == 1  # noqa: E111


def test_notification_missing_service_flow_shows_guidance(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Missing notification service repairs should guide users to setup."""  # noqa: E111

  module, _, _, _ = repairs_module  # noqa: E111

  issue_id = "entry_notification_missing_service"  # noqa: E111
  issue_data = {  # noqa: E111
    "config_entry_id": "entry",
    "issue_type": module.ISSUE_NOTIFICATION_MISSING_SERVICE,
    "services": "notify.mobile_app_phone",
    "service_count": 1,
    "total_failures": 3,
    "consecutive_failures": 3,
    "last_error_reasons": "missing_notify_service",
    "recommended_steps": "Verify notify service configuration",
  }

  hass = SimpleNamespace(  # noqa: E111
    data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
  )

  flow = _create_flow(module, hass, issue_id)  # noqa: E111
  result = asyncio.run(flow.async_step_init())  # noqa: E111

  assert result["type"] == "form"  # noqa: E111
  assert result["step_id"] == "notification_missing_service"  # noqa: E111
  assert result["description_placeholders"]["service_count"] == 1  # noqa: E111


def test_module_conflict_flow_disables_extra_gps_modules(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Module conflict repair should disable GPS for dogs beyond the limit."""  # noqa: E111

  module, _, _, delete_issue_mock = repairs_module  # noqa: E111
  entry = module.ConfigEntry("entry")  # noqa: E111
  entry.data = {  # noqa: E111
    module.CONF_DOGS: [
      {
        module.CONF_DOG_ID: f"dog{i}",
        module.CONF_DOG_NAME: f"Dog {i}",
        "modules": {module.MODULE_GPS: True, module.MODULE_HEALTH: True},
      }
      for i in range(6)
    ],
  }
  entry.options = {}  # noqa: E111
  config_entries, _, _ = _build_config_entries(entry)  # noqa: E111

  issue_id = "entry_module_conflict"  # noqa: E111
  issue_data = {  # noqa: E111
    "config_entry_id": entry.entry_id,
    "issue_type": module.ISSUE_MODULE_CONFLICT,
    "intensive_dogs": 6,
    "total_dogs": 6,
    "suggestion": "Consider selective module enabling",
  }

  hass = SimpleNamespace(  # noqa: E111
    data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
    config_entries=config_entries,
  )

  flow = _create_flow(module, hass, issue_id)  # noqa: E111
  asyncio.run(flow.async_step_init())  # noqa: E111

  delete_issue_mock.reset_mock()  # noqa: E111
  asyncio.run(flow.async_step_module_conflict({"action": "reduce_load"}))  # noqa: E111

  disabled = [  # noqa: E111
    dog
    for dog in entry.data[module.CONF_DOGS]
    if dog["modules"].get(module.MODULE_GPS) is False
  ]
  assert disabled, "Expected at least one dog to have GPS disabled"  # noqa: E111
  assert delete_issue_mock.await_count == 1  # noqa: E111


def test_invalid_dog_data_flow_removes_entries(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Invalid dog data repair should remove malformed entries."""  # noqa: E111

  module, _, _, delete_issue_mock = repairs_module  # noqa: E111
  entry = module.ConfigEntry("entry")  # noqa: E111
  entry.data = {  # noqa: E111
    module.CONF_DOGS: [
      {
        module.CONF_DOG_ID: "valid",
        module.CONF_DOG_NAME: "Valid Dog",
      },
      {module.CONF_DOG_ID: "invalid", module.CONF_DOG_NAME: ""},
    ],
  }
  entry.options = {}  # noqa: E111
  config_entries, _, _ = _build_config_entries(entry)  # noqa: E111

  issue_id = "entry_invalid_dogs"  # noqa: E111
  issue_data = {  # noqa: E111
    "config_entry_id": entry.entry_id,
    "issue_type": module.ISSUE_INVALID_DOG_DATA,
    "invalid_dogs": ["invalid"],
    "total_dogs": 2,
  }

  hass = SimpleNamespace(  # noqa: E111
    data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
    config_entries=config_entries,
  )

  flow = _create_flow(module, hass, issue_id)  # noqa: E111
  asyncio.run(flow.async_step_init())  # noqa: E111

  delete_issue_mock.reset_mock()  # noqa: E111
  asyncio.run(flow.async_step_invalid_dog_data({"action": "clean_up"}))  # noqa: E111

  dogs = entry.data[module.CONF_DOGS]  # noqa: E111
  assert len(dogs) == 1 and dogs[0][module.CONF_DOG_ID] == "valid"  # noqa: E111
  assert delete_issue_mock.await_count == 1  # noqa: E111


def test_coordinator_error_flow_triggers_reload(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Coordinator repair should reload the config entry and resolve the issue."""  # noqa: E111

  module, _, _, delete_issue_mock = repairs_module  # noqa: E111
  entry = module.ConfigEntry("entry")  # noqa: E111
  entry.data = {module.CONF_DOGS: []}  # noqa: E111
  entry.options = {}  # noqa: E111
  config_entries, _, reload_mock = _build_config_entries(entry)  # noqa: E111

  issue_id = "entry_coordinator_error"  # noqa: E111
  issue_data = {  # noqa: E111
    "config_entry_id": entry.entry_id,
    "issue_type": module.ISSUE_COORDINATOR_ERROR,
    "error": "coordinator_not_initialized",
    "suggestion": "Try reloading the integration",
  }

  hass = SimpleNamespace(  # noqa: E111
    data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
    config_entries=config_entries,
  )

  flow = _create_flow(module, hass, issue_id)  # noqa: E111
  asyncio.run(flow.async_step_init())  # noqa: E111

  delete_issue_mock.reset_mock()  # noqa: E111
  reload_mock.reset_mock()  # noqa: E111
  result = asyncio.run(  # noqa: E111
    flow.async_step_coordinator_error({"action": "reload"}),
  )

  assert reload_mock.await_count == 1  # noqa: E111
  assert delete_issue_mock.await_count == 1  # noqa: E111
  assert result["type"] == "create_entry"  # noqa: E111


def test_coordinator_error_flow_handles_failed_reload(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Coordinator repair should keep the issue when reload fails."""  # noqa: E111

  module, _, _, delete_issue_mock = repairs_module  # noqa: E111
  entry = module.ConfigEntry("entry")  # noqa: E111
  entry.data = {module.CONF_DOGS: []}  # noqa: E111
  entry.options = {}  # noqa: E111
  config_entries, _, reload_mock = _build_config_entries(entry)  # noqa: E111

  reload_mock.return_value = False  # noqa: E111

  issue_id = "entry_coordinator_error"  # noqa: E111
  issue_data = {  # noqa: E111
    "config_entry_id": entry.entry_id,
    "issue_type": module.ISSUE_COORDINATOR_ERROR,
    "error": "coordinator_not_initialized",
    "suggestion": "Try reloading the integration",
  }

  hass = SimpleNamespace(  # noqa: E111
    data={module.ir.DOMAIN: {issue_id: SimpleNamespace(data=issue_data)}},
    config_entries=config_entries,
  )

  flow = _create_flow(module, hass, issue_id)  # noqa: E111
  asyncio.run(flow.async_step_init())  # noqa: E111

  delete_issue_mock.reset_mock()  # noqa: E111
  reload_mock.reset_mock()  # noqa: E111
  result = asyncio.run(  # noqa: E111
    flow.async_step_coordinator_error({"action": "reload"}),
  )

  assert reload_mock.await_count == 1  # noqa: E111
  cache_delete_calls = [  # noqa: E111
    invocation
    for invocation in delete_issue_mock.await_args_list
    if invocation.args and str(invocation.args[-1]).endswith("_cache_health")
  ]
  assert not cache_delete_calls  # noqa: E111
  assert result["type"] == "form"  # noqa: E111
  assert result["errors"]["base"] == "reload_failed"  # noqa: E111


def test_async_check_for_issues_checks_coordinator_health(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Coordinator health should be validated when scanning for issues."""  # noqa: E111

  module, create_issue_mock, _, delete_issue_mock = repairs_module  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111
  hass.data = {module.DOMAIN: {}}  # noqa: E111
  hass.services = SimpleNamespace(has_service=lambda *args, **kwargs: True)  # noqa: E111

  entry = SimpleNamespace(  # noqa: E111
    entry_id="entry",
    data={
      module.CONF_DOGS: [
        {
          module.CONF_DOG_ID: "dog_alpha",
          module.CONF_DOG_NAME: "Dog Alpha",
          "modules": {},
        },
      ],
    },
    options={},
    version=1,
  )

  original_require_runtime_data = module.require_runtime_data  # noqa: E111

  def _raise_runtime_error(*_: Any, **__: Any) -> Any:  # noqa: E111
    raise module.RuntimeDataUnavailableError("runtime missing")

  module.require_runtime_data = _raise_runtime_error  # noqa: E111

  try:  # noqa: E111
    asyncio.run(module.async_check_for_issues(hass, entry))
  finally:  # noqa: E111
    module.require_runtime_data = original_require_runtime_data

  assert create_issue_mock.await_count == 1  # noqa: E111
  await_args = create_issue_mock.await_args  # noqa: E111
  assert await_args is not None  # noqa: E111
  kwargs = await_args.kwargs  # noqa: E111
  assert kwargs["translation_key"] == module.ISSUE_COORDINATOR_ERROR  # noqa: E111
  assert kwargs["data"]["error"] == "coordinator_not_initialized"  # noqa: E111

  cache_delete_calls = [  # noqa: E111
    invocation
    for invocation in delete_issue_mock.await_args_list
    if invocation.args and str(invocation.args[-1]).endswith("_cache_health")
  ]
  assert len(cache_delete_calls) == 1  # noqa: E111


def test_async_check_for_issues_publishes_cache_health_issue(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Aggregated cache anomalies should surface as repairs issues."""  # noqa: E111

  module, create_issue_mock, _, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = _build_hass(domain=module.DOMAIN)  # noqa: E111

  summary = CacheRepairAggregate(  # noqa: E111
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
      },
    ],
    caches_with_expired_entries=["adaptive_cache"],
  )

  runtime_data = _make_runtime_data(summary)  # noqa: E111
  entry = _make_basic_entry(module)  # noqa: E111

  module.require_runtime_data = lambda _hass, _entry: runtime_data  # noqa: E111

  _run_check_for_issues(module, hass, entry, runtime_data)  # noqa: E111

  assert create_issue_mock.await_count == 1  # noqa: E111
  await_args = create_issue_mock.await_args  # noqa: E111
  assert await_args is not None  # noqa: E111
  kwargs = await_args.kwargs  # noqa: E111
  assert kwargs["translation_key"] == module.ISSUE_CACHE_HEALTH_SUMMARY  # noqa: E111
  assert kwargs["data"]["summary"] == summary.to_mapping()  # noqa: E111
  cache_delete_calls = [  # noqa: E111
    invocation
    for invocation in delete_issue_mock.await_args_list
    if invocation.args and str(invocation.args[-1]).endswith("_cache_health")
  ]
  assert not cache_delete_calls  # noqa: E111


def test_async_check_for_issues_clears_cache_issue_without_anomalies(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Repairs should clear cache issues when anomalies disappear."""  # noqa: E111

  module, create_issue_mock, _, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = _build_hass(domain=module.DOMAIN)  # noqa: E111

  summary = CacheRepairAggregate(  # noqa: E111
    total_caches=1,
    anomaly_count=0,
    severity="info",
    generated_at="2024-01-01T00:00:00+00:00",
  )

  runtime_data = _make_runtime_data(summary)  # noqa: E111
  entry = _make_basic_entry(module)  # noqa: E111

  _run_check_for_issues(module, hass, entry, runtime_data)  # noqa: E111

  assert create_issue_mock.await_count == 0  # noqa: E111
  cache_delete_calls = [  # noqa: E111
    invocation
    for invocation in delete_issue_mock.await_args_list
    if invocation.args and str(invocation.args[-1]).endswith("_cache_health")
  ]
  assert len(cache_delete_calls) == 1  # noqa: E111


def test_async_check_for_issues_surfaces_reconfigure_warnings(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Reconfigure telemetry warnings should surface as repair issues."""  # noqa: E111

  module, create_issue_mock, _, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = _build_hass()  # noqa: E111

  runtime_data = _make_runtime_data()  # noqa: E111
  entry = _make_reconfigure_entry(  # noqa: E111
    module,
    compatibility_warnings=["GPS module disabled for configured dog"],
    health_summary={"healthy": True, "issues": [], "warnings": []},
  )

  _run_check_for_issues(module, hass, entry, runtime_data)  # noqa: E111

  assert any(  # noqa: E111
    invocation.kwargs["translation_key"] == module.ISSUE_RECONFIGURE_WARNINGS
    for invocation in create_issue_mock.await_args_list
  )


def test_async_check_for_issues_surfaces_reconfigure_health_issue(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Health summaries from reconfigure telemetry should raise issues."""  # noqa: E111

  module, create_issue_mock, _, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = _build_hass()  # noqa: E111

  runtime_data = _make_runtime_data()  # noqa: E111
  entry = _make_reconfigure_entry(  # noqa: E111
    module,
    compatibility_warnings=[],
    health_summary={
      "healthy": False,
      "issues": ["profile missing GPS support"],
      "warnings": ["consider reauth"],
    },
  )

  _run_check_for_issues(module, hass, entry, runtime_data)  # noqa: E111

  assert any(  # noqa: E111
    invocation.kwargs["translation_key"] == module.ISSUE_RECONFIGURE_HEALTH
    for invocation in create_issue_mock.await_args_list
  )


def test_check_runtime_store_duration_alerts_creates_issue(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Guard alerts should create a runtime store repair issue."""  # noqa: E111

  module, create_issue_mock, issue_severity_cls, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111
  runtime_data = SimpleNamespace()  # noqa: E111

  original_require_runtime_data = module.require_runtime_data  # noqa: E111
  original_get_runtime_store_health = module.get_runtime_store_health  # noqa: E111
  module.require_runtime_data = lambda _hass, _entry: runtime_data  # noqa: E111
  module.get_runtime_store_health = lambda _runtime: {  # noqa: E111
    "assessment_timeline_summary": {
      "level_duration_guard_alerts": [
        {
          "level": "watch",
          "percentile_label": "p95",
          "percentile_rank": 0.95,
          "percentile_seconds": 28800.0,
          "guard_limit_seconds": 21600.0,
          "severity": "warning",
          "recommended_action": "Repair",
        },
      ],
      "timeline_window_days": 1.0,
      "last_event_timestamp": "2024-01-02T00:00:00+00:00",
    },
  }

  try:  # noqa: E111
    asyncio.run(module._check_runtime_store_duration_alerts(hass, entry))
  finally:  # noqa: E111
    module.require_runtime_data = original_require_runtime_data
    module.get_runtime_store_health = original_get_runtime_store_health

  assert create_issue_mock.await_count == 1  # noqa: E111
  kwargs = create_issue_mock.await_args.kwargs  # noqa: E111
  assert kwargs["translation_key"] == module.ISSUE_RUNTIME_STORE_DURATION_ALERT  # noqa: E111
  assert kwargs["severity"] == issue_severity_cls.WARNING  # noqa: E111
  data = kwargs["data"]  # noqa: E111
  assert data["alert_count"] == 1  # noqa: E111
  assert data["triggered_levels"] == "watch"  # noqa: E111
  assert "alert_summaries" in data  # noqa: E111


def test_check_runtime_store_duration_alerts_clears_issue_without_alerts(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Existing issues should be cleared when no guard alerts remain."""  # noqa: E111

  module, create_issue_mock, _, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111
  runtime_data = SimpleNamespace()  # noqa: E111

  original_require_runtime_data = module.require_runtime_data  # noqa: E111
  original_get_runtime_store_health = module.get_runtime_store_health  # noqa: E111
  module.require_runtime_data = lambda _hass, _entry: runtime_data  # noqa: E111
  module.get_runtime_store_health = lambda _runtime: {  # noqa: E111
    "assessment_timeline_summary": {"level_duration_guard_alerts": []},
  }

  try:  # noqa: E111
    asyncio.run(module._check_runtime_store_duration_alerts(hass, entry))
  finally:  # noqa: E111
    module.require_runtime_data = original_require_runtime_data
    module.get_runtime_store_health = original_get_runtime_store_health

  assert create_issue_mock.await_count == 0  # noqa: E111
  assert delete_issue_mock.await_count == 1  # noqa: E111


def test_async_check_for_issues_clears_reconfigure_issues_when_clean(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Reconfigure telemetry without warnings should clear existing issues."""  # noqa: E111

  module, create_issue_mock, _, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = _build_hass()  # noqa: E111

  runtime_data = _make_runtime_data()  # noqa: E111
  entry = _make_reconfigure_entry(  # noqa: E111
    module,
    compatibility_warnings=[],
    health_summary={"healthy": True, "issues": [], "warnings": []},
  )

  _run_check_for_issues(module, hass, entry, runtime_data)  # noqa: E111

  assert not any(  # noqa: E111
    invocation.kwargs["translation_key"]
    in {module.ISSUE_RECONFIGURE_WARNINGS, module.ISSUE_RECONFIGURE_HEALTH}
    for invocation in create_issue_mock.await_args_list
  )
  assert any(  # noqa: E111
    invocation.args
    and str(
      invocation.args[-1],
    ).endswith("reconfigure_warnings")
    for invocation in delete_issue_mock.await_args_list
  )
  assert any(  # noqa: E111
    invocation.args
    and str(
      invocation.args[-1],
    ).endswith("reconfigure_health")
    for invocation in delete_issue_mock.await_args_list
  )


def test_notification_check_accepts_mobile_app_service_prefix(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Notification checks should detect mobile_app_* notify services."""  # noqa: E111

  module, create_issue_mock, _, _ = repairs_module  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111

  hass.services = SimpleNamespace(  # noqa: E111
    has_service=lambda domain, service: False,
    async_services=lambda: {"notify": {"mobile_app_jane": object()}},
  )

  entry = SimpleNamespace(  # noqa: E111
    entry_id="entry",
    data={
      module.CONF_DOGS: [
        {
          module.CONF_DOG_ID: "dog_alpha",
          module.CONF_DOG_NAME: "Dog Alpha",
          "modules": {module.MODULE_NOTIFICATIONS: True},
        },
      ],
    },
    options={"notifications": {"mobile_notifications": True}},
    version=1,
  )

  asyncio.run(module._check_notification_configuration_issues(hass, entry))  # noqa: E111

  assert create_issue_mock.await_count == 0  # noqa: E111


def test_notification_delivery_errors_create_issues(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Recurring notification failures should surface repair issues."""  # noqa: E111

  module, create_issue_mock, issue_severity_cls, _ = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111

  hass = _build_hass(domain=module.DOMAIN)  # noqa: E111
  entry = _build_entry(module)  # noqa: E111

  notification_manager = SimpleNamespace(  # noqa: E111
    get_delivery_status_snapshot=lambda: {
      "services": {
        "notify.mobile_app_phone": {
          "total_failures": 4,
          "consecutive_failures": 3,
          "last_error_reason": "exception",
          "last_error": "Unauthorized",
        },
        "notify.mobile_app_watch": {
          "total_failures": 3,
          "consecutive_failures": 3,
          "last_error_reason": "exception",
          "last_error": "Device unreachable",
        },
        "notify.mobile_app_tablet": {
          "total_failures": 3,
          "consecutive_failures": 3,
          "last_error_reason": "missing_notify_service",
          "last_error": "missing_notify_service",
        },
        "notify.mobile_app_display": {
          "total_failures": 3,
          "consecutive_failures": 3,
          "last_error_reason": "exception",
          "last_error": "Request timeout",
        },
      }
    }
  )
  runtime_data = _make_runtime_data(notification_manager=notification_manager)  # noqa: E111

  _run_check_for_issues(module, hass, entry, runtime_data)  # noqa: E111

  keys = {  # noqa: E111
    invocation.kwargs["translation_key"]
    for invocation in create_issue_mock.await_args_list
  }
  assert module.ISSUE_NOTIFICATION_AUTH_ERROR in keys  # noqa: E111
  assert module.ISSUE_NOTIFICATION_DEVICE_UNREACHABLE in keys  # noqa: E111
  assert module.ISSUE_NOTIFICATION_MISSING_SERVICE in keys  # noqa: E111
  assert module.ISSUE_NOTIFICATION_DELIVERY_REPEATED in keys  # noqa: E111
  assert module.ISSUE_NOTIFICATION_TIMEOUT in keys  # noqa: E111

  for invocation in create_issue_mock.await_args_list:  # noqa: E111
    if invocation.kwargs["translation_key"] == module.ISSUE_NOTIFICATION_AUTH_ERROR:
      assert invocation.kwargs["severity"] == issue_severity_cls.ERROR  # noqa: E111


def test_notification_delivery_errors_clears_issues_when_clean(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Notification error issues should clear when delivery recovers."""  # noqa: E111

  module, _, _, delete_issue_mock = repairs_module  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = _build_hass(domain=module.DOMAIN)  # noqa: E111
  entry = _build_entry(module)  # noqa: E111

  notification_manager = SimpleNamespace(  # noqa: E111
    get_delivery_status_snapshot=lambda: {
      "services": {
        "notify.mobile_app_phone": {
          "total_failures": 1,
          "consecutive_failures": 1,
          "last_error_reason": "exception",
          "last_error": "Temporary error",
        },
      }
    }
  )
  runtime_data = _make_runtime_data(notification_manager=notification_manager)  # noqa: E111

  _run_check_for_issues(module, hass, entry, runtime_data)  # noqa: E111

  # Use a different variable name to avoid shadowing the imported ``call`` from ``unittest.mock``  # noqa: E114, E501
  deleted = [args.args[-1] for args in delete_issue_mock.await_args_list]  # noqa: E111
  assert any(str(name).endswith("notification_auth_error") for name in deleted)  # noqa: E111
  assert any(str(name).endswith("notification_device_unreachable") for name in deleted)  # noqa: E111
  assert any(str(name).endswith("notification_missing_service") for name in deleted)  # noqa: E111
  assert any(str(name).endswith("notification_timeout") for name in deleted)  # noqa: E111
  assert any(  # noqa: E111
    str(name).endswith("notification_delivery_error_exception") for name in deleted
  )
  assert any(str(name).endswith("notification_delivery_repeated") for name in deleted)  # noqa: E111


def test_async_publish_feeding_compliance_issue_creates_alert(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Feeding compliance issues should create repair alerts with metadata."""  # noqa: E111

  module, create_issue_mock, issue_severity_cls, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111

  payload = cast(  # noqa: E111
    dict[str, object],
    {
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
          },
        ],
        "missed_meals": [{"date": "2024-05-03", "actual": 1, "expected": 2}],
        "recommendations": ["Schedule a vet visit"],
      },
    },
  )

  asyncio.run(  # noqa: E111
    module.async_publish_feeding_compliance_issue(
      hass,
      entry,
      payload,
      context_metadata={"context_id": "ctx-1"},
    ),
  )

  assert create_issue_mock.await_count == 1  # noqa: E111
  await_args = create_issue_mock.await_args  # noqa: E111
  assert await_args is not None  # noqa: E111
  kwargs = await_args.kwargs  # noqa: E111
  assert kwargs["translation_key"] == module.ISSUE_FEEDING_COMPLIANCE_ALERT  # noqa: E111
  severity_enum = cast(Any, issue_severity_cls)  # noqa: E111
  assert kwargs["severity"] == severity_enum.CRITICAL  # noqa: E111
  data = kwargs["data"]  # noqa: E111
  assert data["dog_id"] == "buddy"  # noqa: E111
  assert data["issue_count"] == 1  # noqa: E111
  assert data["missed_meal_count"] == 1  # noqa: E111
  assert data["context_metadata"]["context_id"] == "ctx-1"  # noqa: E111
  assert data["notification_sent"] is True  # noqa: E111
  summary = data["localized_summary"]  # noqa: E111
  assert summary["title"] in {"alert_title", "🍽️ Feeding compliance alert"}  # noqa: E111
  assert summary["score_line"] in {"score_line", "Score: 65%"}  # noqa: E111
  assert data["notification_title"] == summary["title"]  # noqa: E111
  assert data["notification_message"] is not None  # noqa: E111
  assert data["issue_summary"] in (["issue_item"], ["2024-05-04: Missed breakfast"])  # noqa: E111
  assert data["missed_meal_summary"] in (  # noqa: E111
    ["missed_meal_item"],
    ["2024-05-03: 1/2 meals"],
  )
  assert data["recommendations_summary"] in (  # noqa: E111
    ["recommendation_item"],
    ["Schedule a vet visit"],
  )


def test_async_publish_feeding_compliance_issue_falls_back_without_critical(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Severity should fall back when CRITICAL is unavailable."""  # noqa: E111

  module, create_issue_mock, _, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  class LimitedSeverity(StrEnum):  # noqa: E111
    ERROR = "error"
    WARNING = "warning"

  monkeypatch.setattr(  # noqa: E111
    module.ir,
    "IssueSeverity",
    LimitedSeverity,
    raising=False,
  )
  monkeypatch.setattr(  # noqa: E111
    module.ir,
    "async_create_issue",
    create_issue_mock,
    raising=False,
  )

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111

  payload = cast(  # noqa: E111
    dict[str, object],
    {
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
          },
        ],
        "missed_meals": [
          {"date": "2024-05-03", "actual": 1, "expected": 2},
        ],
        "recommendations": ["Schedule a vet visit"],
      },
    },
  )

  asyncio.run(  # noqa: E111
    module.async_publish_feeding_compliance_issue(
      hass,
      entry,
      payload,
      context_metadata=None,
    ),
  )

  assert create_issue_mock.await_count == 1  # noqa: E111
  await_args = create_issue_mock.await_args  # noqa: E111
  assert await_args is not None  # noqa: E111
  kwargs = await_args.kwargs  # noqa: E111
  assert kwargs["severity"] == LimitedSeverity.ERROR  # noqa: E111


def test_async_publish_feeding_compliance_issue_clears_resolved_alert(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Resolved compliance checks should clear existing repair issues."""  # noqa: E111

  module, create_issue_mock, _, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111

  payload = cast(  # noqa: E111
    dict[str, object],
    {
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
    },
  )

  asyncio.run(  # noqa: E111
    module.async_publish_feeding_compliance_issue(
      hass,
      entry,
      payload,
      context_metadata=None,
    ),
  )

  assert create_issue_mock.await_count == 0  # noqa: E111
  assert delete_issue_mock.await_count == 1  # noqa: E111
  delete_args = delete_issue_mock.await_args  # noqa: E111
  assert delete_args is not None  # noqa: E111
  args = delete_args.args  # noqa: E111
  assert len(args) >= 2  # noqa: E111
  assert args[0] == hass  # noqa: E111
  assert args[1] == module.DOMAIN  # noqa: E111


def test_async_publish_feeding_compliance_issue_handles_no_data(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """No-data results should raise a warning issue."""  # noqa: E111

  module, create_issue_mock, issue_severity_cls, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111

  payload = cast(  # noqa: E111
    dict[str, object],
    {
      "dog_id": "buddy",
      "dog_name": None,
      "days_to_check": 3,
      "notify_on_issues": False,
      "notification_sent": False,
      "result": {
        "status": "no_data",
        "message": "Telemetry unavailable",
      },
    },
  )

  asyncio.run(  # noqa: E111
    module.async_publish_feeding_compliance_issue(
      hass,
      entry,
      payload,
      context_metadata={"context_id": None},
    ),
  )

  assert create_issue_mock.await_count == 1  # noqa: E111
  await_args = create_issue_mock.await_args  # noqa: E111
  assert await_args is not None  # noqa: E111
  kwargs = await_args.kwargs  # noqa: E111
  assert kwargs["translation_key"] == module.ISSUE_FEEDING_COMPLIANCE_NO_DATA  # noqa: E111
  severity_enum = cast(Any, issue_severity_cls)  # noqa: E111
  assert kwargs["severity"] == severity_enum.WARNING  # noqa: E111
  data = kwargs["data"]  # noqa: E111
  assert data["dog_name"] == "buddy"  # noqa: E111
  assert data["message"] == "Telemetry unavailable"  # noqa: E111
  summary = data["localized_summary"]  # noqa: E111
  assert summary["title"] in {"no_data_title", "🍽️ Feeding telemetry missing"}  # noqa: E111
  assert summary["message"] == "Telemetry unavailable"  # noqa: E111
  assert data["issue_summary"] == []  # noqa: E111
  assert delete_issue_mock.await_count == 0  # noqa: E111


def test_async_publish_feeding_compliance_issue_sanitises_mapping_message(
  repairs_module: tuple[Any, AsyncMock, type[StrEnum], AsyncMock],
) -> None:
  """Structured messages should fall back to the localised summary text."""  # noqa: E111

  module, create_issue_mock, _issue_severity_cls, delete_issue_mock = repairs_module  # noqa: E111
  create_issue_mock.reset_mock()  # noqa: E111
  delete_issue_mock.reset_mock()  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="entry", data={}, options={}, version=1)  # noqa: E111

  payload = cast(  # noqa: E111
    dict[str, object],
    {
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
    },
  )

  asyncio.run(  # noqa: E111
    module.async_publish_feeding_compliance_issue(
      hass,
      entry,
      payload,
      context_metadata=None,
    ),
  )

  await_args = create_issue_mock.await_args  # noqa: E111
  assert await_args is not None  # noqa: E111
  data = await_args.kwargs["data"]  # noqa: E111
  assert data["message"] == "Telemetry offline"  # noqa: E111
  assert data["localized_summary"]["message"] == "Telemetry offline"  # noqa: E111
