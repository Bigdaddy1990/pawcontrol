"""Unit coverage for the PawControl data manager instrumentation."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from custom_components.pawcontrol.const import (
  CACHE_TIMESTAMP_STALE_THRESHOLD,
  MODULE_FEEDING,
  MODULE_HEALTH,
  MODULE_MEDICATION,
  MODULE_WALK,
)
from custom_components.pawcontrol.coordinator_support import (
  CacheMonitorRegistrar,
  CacheMonitorTarget,
  CoordinatorMetrics,
  bind_runtime_managers,
)
from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.door_sensor_manager import (
  WALK_STATE_ACTIVE,
  DoorSensorConfig,
  DoorSensorManager,
  WalkDetectionState,
)
from custom_components.pawcontrol.helper_manager import PawControlHelperManager
from custom_components.pawcontrol.script_manager import PawControlScriptManager
from custom_components.pawcontrol.types import (
  ConfigEntryDataPayload,
  CoordinatorRuntimeManagers,
  FeedingData,
  HelperEntityMetadata,
  JSONMutableMapping,
  PawControlOptionsData,
)
from homeassistant import const as ha_const
from homeassistant.components.script.const import CONF_FIELDS
from homeassistant.const import (
  CONF_ALIAS,
  CONF_DEFAULT,
  STATE_OFF,
  STATE_ON,
)
from homeassistant.core import Event
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify as ha_slugify

if TYPE_CHECKING:
  from custom_components.pawcontrol.feeding_manager import FeedingManager
  from custom_components.pawcontrol.garden_manager import GardenManager
  from custom_components.pawcontrol.gps_manager import GPSGeofenceManager
  from custom_components.pawcontrol.notifications import PawControlNotificationManager
  from custom_components.pawcontrol.walk_manager import WalkManager
  from custom_components.pawcontrol.weather_manager import WeatherHealthManager
  from homeassistant.core import HomeAssistant


if hasattr(ha_slugify, "slugify"):
  ha_slugify = ha_slugify.slugify


CONF_SEQUENCE = getattr(ha_const, "CONF_SEQUENCE", "sequence")
CONF_DESCRIPTION = "description"


class StubDataManager(PawControlDataManager):
  """Minimal data manager that exercises visitor profiling without HA deps."""

  def __init__(self) -> None:
    self._metrics: JSONMutableMapping = {
      "operations": 0,
      "saves": 0,
      "errors": 0,
      "last_cleanup": None,
      "performance_score": 100.0,
    }
    self._visitor_timings: deque[float] = deque(maxlen=50)
    self._metrics_sink: CoordinatorMetrics | None = None
    self.saved_payload: JSONMutableMapping | None = None

  async def _get_namespace_data(self, namespace: str) -> JSONMutableMapping:
    """Return empty namespace data for tests."""

    assert namespace == "visitor_mode"
    return cast(JSONMutableMapping, {})

  async def _save_namespace(self, namespace: str, data: JSONMutableMapping) -> None:
    """Capture writes instead of hitting Home Assistant storage."""

    assert namespace == "visitor_mode"
    self.saved_payload = data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_set_visitor_mode_records_metrics() -> None:
  """Visitor workflows should record runtime samples and update metrics."""

  manager = StubDataManager()
  metrics_sink = CoordinatorMetrics()
  manager.set_metrics_sink(metrics_sink)

  await manager.async_set_visitor_mode("buddy", {"enabled": True})

  assert manager.saved_payload == {"buddy": {"enabled": True}}
  assert manager._visitor_timings  # at least one sample captured
  assert manager._metrics["visitor_mode_last_runtime_ms"] < 3.0
  assert manager._metrics["visitor_mode_avg_runtime_ms"] < 3.0
  assert metrics_sink.visitor_mode_timings
  assert metrics_sink.average_visitor_runtime_ms < 3.0


@dataclass(slots=True)
class _DummyMetrics:
  entries: int
  hits: int
  misses: int

  @property
  def hit_rate(self) -> float:
    total = self.hits + self.misses
    return (self.hits / total * 100.0) if total else 0.0


class _DummyAdapter:
  """Return static cache metrics for module adapters."""

  def __init__(self, entries: int, hits: int, misses: int) -> None:
    self._metrics = _DummyMetrics(entries, hits, misses)

  def cache_metrics(self) -> _DummyMetrics:
    return self._metrics


class _DummyModules:
  """Expose per-module cache metrics for coordinator diagnostics."""

  def __init__(self) -> None:
    self.feeding = _DummyAdapter(2, 5, 1)
    self.walk = _DummyAdapter(1, 1, 2)
    self.geofencing = _DummyAdapter(0, 0, 0)
    self.health = _DummyAdapter(3, 4, 0)
    self.weather = _DummyAdapter(0, 0, 0)
    self.garden = _DummyAdapter(0, 0, 0)

  def cache_metrics(self) -> _DummyMetrics:
    total = _DummyMetrics(0, 0, 0)
    for adapter in (
      self.feeding,
      self.walk,
      self.geofencing,
      self.health,
      self.weather,
      self.garden,
    ):
      metrics = adapter.cache_metrics()
      total.entries += metrics.entries
      total.hits += metrics.hits
      total.misses += metrics.misses
    return total


ManualEventCallback = Callable[[Event], None]


class _RecordingRegistrar(CacheMonitorRegistrar):
  """Capture cache monitor registrations for assertions."""

  def __init__(self) -> None:
    self.monitors: dict[str, CacheMonitorTarget] = {}

  def register_cache_monitor(self, name: str, cache: CacheMonitorTarget) -> None:
    self.monitors[name] = cache


@dataclass(slots=True)
class _DummySnapshot:
  dog_id: str
  profile: str
  capacity: int
  base_allocation: int
  dynamic_allocation: int
  requested_entities: tuple[str, ...]
  denied_requests: tuple[str, ...]
  recorded_at: datetime


class _DummyTracker:
  """Expose entity budget tracker statistics for diagnostics tests."""

  def __init__(self) -> None:
    now = datetime.now(UTC)
    self._snapshots = (
      _DummySnapshot(
        "buddy",
        "standard",
        6,
        4,
        1,
        ("sensor.feeder",),
        (),
        now,
      ),
      _DummySnapshot(
        "max",
        "standard",
        5,
        3,
        1,
        ("sensor.walk",),
        ("switch.denied",),
        now,
      ),
    )

  def snapshots(self) -> tuple[_DummySnapshot, ...]:
    return self._snapshots

  def summary(self) -> JSONMutableMapping:
    return cast(
      JSONMutableMapping,
      {"peak_utilization": 75.0, "tracked": len(self._snapshots)},
    )

  def saturation(self) -> float:
    return 0.5


class _ErrorSummaryTracker(_DummyTracker):
  """Tracker that raises when building a summary to exercise fallbacks."""

  def summary(self) -> JSONMutableMapping:  # type: ignore[override]
    raise RuntimeError("tracker summary failed")


@pytest.mark.unit
def test_auto_registered_cache_monitors(tmp_path: Path) -> None:
  """Data manager should surface coordinator caches via diagnostics snapshots."""

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  modules = _DummyModules()
  tracker = _DummyTracker()
  coordinator = SimpleNamespace(
    hass=hass,
    config_entry=SimpleNamespace(entry_id="test-entry"),
    _modules=modules,
    _entity_budget=tracker,
  )

  manager = PawControlDataManager(
    hass=hass,
    coordinator=coordinator,
    dogs_config=[],
  )

  snapshots = manager.cache_snapshots()

  assert "coordinator_modules" in snapshots
  module_snapshot = snapshots["coordinator_modules"]
  assert module_snapshot["stats"]["entries"] == modules.cache_metrics().entries
  per_module = module_snapshot["diagnostics"]["per_module"]
  assert per_module["feeding"]["hits"] == 5
  assert per_module["walk"]["misses"] == 2

  assert "entity_budget_tracker" in snapshots
  budget_snapshot = snapshots["entity_budget_tracker"]
  assert budget_snapshot["stats"]["tracked_dogs"] == 2
  assert budget_snapshot["stats"]["saturation_percent"] == 50.0
  assert budget_snapshot["diagnostics"]["summary"]["peak_utilization"] == 75.0
  dog_ids = {entry["dog_id"] for entry in budget_snapshot["diagnostics"]["snapshots"]}
  assert dog_ids == {"buddy", "max"}

  for name in (
    "storage_visitor_mode",
    "storage_module_state",
    "storage_analysis_cache",
    "storage_reports",
    "storage_health_reports",
  ):
    assert name in snapshots
    storage_snapshot = snapshots[name]
    assert storage_snapshot["stats"]["entries"] == 0
    assert storage_snapshot["stats"]["dogs"] == 0


@pytest.mark.unit
def test_entity_budget_tracker_handles_summary_errors(tmp_path: Path) -> None:
  """Entity budget diagnostics should expose serialised error payloads."""

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  modules = _DummyModules()
  tracker = _ErrorSummaryTracker()
  coordinator = SimpleNamespace(
    hass=hass,
    config_entry=SimpleNamespace(entry_id="test-entry"),
    _modules=modules,
    _entity_budget=tracker,
  )

  manager = PawControlDataManager(
    hass=hass,
    coordinator=coordinator,
    dogs_config=[],
  )

  snapshots = manager.cache_snapshots()
  diagnostics = snapshots["entity_budget_tracker"]["diagnostics"]

  summary = diagnostics["summary"]
  assert summary["error"] == "tracker summary failed"
  summary["extra"] = True  # ensure mapping is mutable for downstream updates
  assert summary["extra"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_storage_namespace_monitors_track_updates(tmp_path: Path) -> None:
  """Namespace cache monitors should reflect persisted updates."""

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  manager = PawControlDataManager(
    hass=hass,
    entry_id="storage-test",
    dogs_config=[{"dog_id": "buddy"}],
  )

  await manager.async_initialize()
  await manager.async_set_visitor_mode("buddy", {"enabled": True})
  await manager.async_set_dog_power_state("buddy", True)

  snapshots = manager.cache_snapshots()

  visitor_snapshot = snapshots["storage_visitor_mode"]
  assert visitor_snapshot["stats"]["dogs"] == 1
  assert visitor_snapshot["diagnostics"]["per_dog"]["buddy"]["entries"] >= 1
  assert "timestamp_issue" not in visitor_snapshot["diagnostics"]["per_dog"]["buddy"]
  assert "timestamp_anomalies" not in visitor_snapshot["diagnostics"]

  module_state_snapshot = snapshots["storage_module_state"]
  assert module_state_snapshot["diagnostics"]["per_dog"]["buddy"]["entries"] >= 1


@pytest.mark.unit
def test_storage_namespace_timestamp_anomalies(tmp_path: Path) -> None:
  """Namespace monitors should flag missing or stale timestamps."""

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  manager = PawControlDataManager(
    hass=hass,
    entry_id="storage-test",
    dogs_config=[{"dog_id": "buddy"}],
  )

  manager._namespace_state["visitor_mode"] = {
    "buddy": {"enabled": True, "timestamp": None},
    "max": {
      "enabled": True,
      "timestamp": (dt_util.utcnow() + timedelta(hours=1)).isoformat(),
    },
  }

  snapshots = manager.cache_snapshots()
  diagnostics = snapshots["storage_visitor_mode"]["diagnostics"]
  anomalies = diagnostics["timestamp_anomalies"]
  assert anomalies["buddy"] == "missing"
  assert anomalies["max"] == "future"


@pytest.mark.unit
def test_helper_manager_register_cache_monitor() -> None:
  """Helper manager should expose diagnostics through the cache registrar."""

  hass = SimpleNamespace()
  entry = SimpleNamespace(entry_id="entry", data={}, options={})
  helper_manager = PawControlHelperManager(hass, entry)
  helper_manager._created_helpers.add("input_boolean.pawcontrol_buddy_breakfast_fed")
  helper_manager._dog_helpers = {
    "buddy": ["input_boolean.pawcontrol_buddy_breakfast_fed"],
  }
  helper_manager._managed_entities = {
    "input_boolean.pawcontrol_buddy_breakfast_fed": cast(
      HelperEntityMetadata, {"domain": "input_boolean"}
    )
  }
  helper_manager._cleanup_listeners = [lambda: None]
  helper_manager._daily_reset_configured = True

  registrar = _RecordingRegistrar()
  helper_manager.register_cache_monitors(registrar, prefix="helper_manager")

  assert "helper_manager_cache" in registrar.monitors
  snapshot = registrar.monitors["helper_manager_cache"].coordinator_snapshot()
  assert snapshot["stats"]["helpers"] == 1
  diagnostics = snapshot["diagnostics"]
  assert diagnostics["per_dog_helpers"]["buddy"] == 1
  assert diagnostics["entity_domains"]["input_boolean"] == 1
  assert diagnostics["daily_reset_configured"] is True
  guard_metrics = diagnostics["service_guard_metrics"]
  assert guard_metrics == {
    "executed": 0,
    "skipped": 0,
    "reasons": {},
    "last_results": [],
  }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_helper_manager_skips_helper_creation_without_services(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Helper manager should short-circuit helper creation when hass services missing."""

  hass = SimpleNamespace(data={}, states=SimpleNamespace(get=lambda entity_id: None))
  entry = SimpleNamespace(entry_id="entry", data={}, options={})
  helper_manager = PawControlHelperManager(hass, entry)

  class _DummyRegistry:
    def async_get(self, entity_id: str) -> None:
      return None

  monkeypatch.setattr(
    "custom_components.pawcontrol.helper_manager.er.async_get",
    lambda hass_instance: _DummyRegistry(),
  )

  # Simulate Home Assistant instance without the services API.
  helper_manager._hass = None

  await helper_manager._async_create_input_boolean(
    "input_boolean.pawcontrol_test_breakfast_fed",
    "Test Helper",
    initial=True,
  )

  assert (
    "input_boolean.pawcontrol_test_breakfast_fed" not in helper_manager._created_helpers
  )

  guard_metrics = helper_manager.guard_metrics
  assert guard_metrics["executed"] == 0
  assert guard_metrics["skipped"] == 1
  assert guard_metrics["reasons"]["missing_instance"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_helper_manager_guard_metrics_accumulate_skips(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Helper manager should aggregate guard skips across lifecycle services."""

  hass = SimpleNamespace(data={})
  entry = SimpleNamespace(entry_id="entry", data={}, options={})
  helper_manager = PawControlHelperManager(hass, entry)

  class _DummyRegistry:
    def async_get(self, entity_id: str) -> None:
      return None

  monkeypatch.setattr(
    "custom_components.pawcontrol.helper_manager.er.async_get",
    lambda hass_instance: _DummyRegistry(),
  )

  monkeypatch.setattr(
    "custom_components.pawcontrol.helper_manager.slugify",
    lambda value: value,
  )

  helper_manager._hass = None

  await helper_manager._async_create_input_boolean(
    "input_boolean.pawcontrol_buddy_breakfast_fed",
    "Buddy Breakfast",
    initial=False,
  )

  helper_manager._created_helpers = {
    "input_boolean.pawcontrol_buddy_breakfast_fed",
  }
  helper_manager._managed_entities = {
    "input_boolean.pawcontrol_buddy_breakfast_fed": cast(
      HelperEntityMetadata, {"domain": "input_boolean"}
    ),
  }

  await helper_manager.async_remove_dog_helpers("buddy")

  guard_metrics = helper_manager.guard_metrics
  assert guard_metrics["executed"] == 0
  assert guard_metrics["skipped"] == 2
  assert guard_metrics["reasons"]["missing_instance"] == 2
  assert len(guard_metrics["last_results"]) == 2


@pytest.mark.unit
def test_script_manager_register_cache_monitor() -> None:
  """Script manager should expose created script diagnostics."""

  hass = SimpleNamespace(data={})
  entry = SimpleNamespace(entry_id="entry", data={}, options={})
  script_manager = PawControlScriptManager(hass, entry)
  script_manager._created_entities.update(
    {
      "script.pawcontrol_buddy_reset",
      "script.pawcontrol_max_reset",
      "script.pawcontrol_entry_resilience_escalation",
    }
  )
  script_manager._dog_scripts = {
    "buddy": ["script.pawcontrol_buddy_reset"],
    "max": ["script.pawcontrol_max_reset"],
  }
  script_manager._entry_scripts = ["script.pawcontrol_entry_resilience_escalation"]

  registrar = _RecordingRegistrar()
  script_manager.register_cache_monitors(registrar, prefix="script_manager")

  assert "script_manager_cache" in registrar.monitors
  snapshot = registrar.monitors["script_manager_cache"].coordinator_snapshot()
  assert snapshot["stats"]["scripts"] == 3
  assert snapshot["stats"]["entry_scripts"] == 1
  diagnostics = snapshot["diagnostics"]
  assert diagnostics["per_dog"]["buddy"]["count"] == 1
  assert diagnostics["entry_scripts"] == [
    "script.pawcontrol_entry_resilience_escalation"
  ]
  assert diagnostics["created_entities"] == sorted(diagnostics["created_entities"])


@pytest.mark.unit
def test_script_manager_timestamp_anomaly() -> None:
  """Script manager diagnostics should flag stale generations."""

  hass = SimpleNamespace(data={})
  entry = SimpleNamespace(entry_id="entry", data={}, options={})
  script_manager = PawControlScriptManager(hass, entry)
  script_manager._created_entities.add("script.pawcontrol_buddy_reset")
  script_manager._dog_scripts = {"buddy": ["script.pawcontrol_buddy_reset"]}
  script_manager._last_generation = dt_util.utcnow() - (
    CACHE_TIMESTAMP_STALE_THRESHOLD + timedelta(hours=1)
  )

  registrar = _RecordingRegistrar()
  script_manager.register_cache_monitors(registrar, prefix="script_manager")

  snapshot = registrar.monitors["script_manager_cache"].coordinator_snapshot()
  diagnostics = snapshot["diagnostics"]
  anomalies = diagnostics["timestamp_anomalies"]
  assert anomalies["manager"] == "stale"
  assert diagnostics["last_generated"] is not None


@pytest.mark.unit
def test_script_manager_resilience_escalation_definition() -> None:
  """Entry-level resilience escalation script should expose guard thresholds."""

  hass = SimpleNamespace(data={})
  entry = SimpleNamespace(
    entry_id="entry-id",
    data={},
    options={},
    title="Canine Ops",
  )
  script_manager = PawControlScriptManager(hass, entry)

  object_id, config = script_manager._build_resilience_escalation_script()

  expected_slug = ha_slugify("Canine Ops")
  assert object_id == f"pawcontrol_{expected_slug}_resilience_escalation"
  assert config[CONF_ALIAS] == "Canine Ops resilience escalation"
  assert "guard skips" in config[CONF_DESCRIPTION]

  sequence = config[CONF_SEQUENCE]
  assert isinstance(sequence, list) and len(sequence) == 2
  variables = sequence[0]["variables"]
  assert "guard_reason_text" in variables
  assert "open_breakers_text" in variables

  guard_branch, breaker_branch = sequence[1]["choose"]
  guard_service = guard_branch["sequence"][0]["service"]
  assert (
    guard_service
    == "{{ escalation_service | default('persistent_notification.create') }}"
  )
  guard_followup = guard_branch["sequence"][1]["choose"][0]["sequence"][0]
  assert guard_followup["service"] == "script.turn_on"
  assert guard_followup["data"]["variables"]["trigger_reason"] == "guard"

  breaker_service = breaker_branch["sequence"][0]["service"]
  assert (
    breaker_service
    == "{{ escalation_service | default('persistent_notification.create') }}"
  )

  fields = config[CONF_FIELDS]
  assert fields["skip_threshold"][CONF_DEFAULT] == 3
  assert fields["breaker_threshold"][CONF_DEFAULT] == 1
  assert fields["statistics_entity_id"][CONF_DEFAULT] == "sensor.pawcontrol_statistics"
  guard_message = fields["guard_message"][CONF_DEFAULT]
  breaker_message = fields["breaker_message"][CONF_DEFAULT]
  assert "{{ guard_reason_text }}" in guard_message
  assert "{{ open_breakers_text }}" in breaker_message
  assert "entity" in fields["followup_script"]["selector"]

  snapshot = script_manager.get_resilience_escalation_snapshot()
  assert snapshot is not None
  assert snapshot["available"] is True
  assert snapshot["state_available"] is False
  assert snapshot["thresholds"]["skip_threshold"]["default"] == 3
  assert snapshot["thresholds"]["breaker_threshold"]["default"] == 1
  manual = snapshot["manual_events"]
  assert manual["available"] is False
  assert manual["automations"] == []
  assert manual["event_history"] == []


@pytest.mark.unit
def test_script_manager_resilience_threshold_overrides() -> None:
  """Config entry options should override default resilience thresholds."""

  hass = SimpleNamespace(data={})
  entry = SimpleNamespace(
    entry_id="entry-id",
    data={},
    options={
      "system_settings": {
        "resilience_skip_threshold": 9,
        "resilience_breaker_threshold": 4,
      }
    },
    title="Canine Ops",
  )

  script_manager = PawControlScriptManager(hass, entry)

  _object_id, config = script_manager._build_resilience_escalation_script()
  fields = config[CONF_FIELDS]
  assert fields["skip_threshold"][CONF_DEFAULT] == 9
  assert fields["breaker_threshold"][CONF_DEFAULT] == 4

  snapshot = script_manager.get_resilience_escalation_snapshot()
  assert snapshot is not None
  assert snapshot["thresholds"]["skip_threshold"]["default"] == 9
  assert snapshot["thresholds"]["breaker_threshold"]["default"] == 4
  manual = snapshot["manual_events"]
  assert manual["available"] is False
  assert manual["system_guard_event"] is None
  assert manual["system_breaker_event"] is None
  assert manual["listener_events"] == {}
  assert manual["listener_sources"] == {}
  assert manual["last_trigger"] is None
  assert manual["event_history"] == []
  counters = manual["event_counters"]
  assert counters["total"] == 0
  assert counters["by_event"] == {}
  assert counters["by_reason"] == {}


@pytest.mark.unit
def test_script_manager_resilience_manual_event_snapshot() -> None:
  """Manual blueprint triggers should be surfaced in diagnostics snapshots."""

  hass = SimpleNamespace(
    data={},
    states=SimpleNamespace(get=lambda entity_id: None),
    config_entries=SimpleNamespace(
      async_entries=lambda domain: [
        SimpleNamespace(
          entry_id="automation-id",
          title="Resilience follow-up",
          data={
            "use_blueprint": {
              "path": "blueprints/automation/pawcontrol/resilience_escalation_followup.yaml",
              "input": {
                "manual_guard_event": "pawcontrol_manual_guard",
                "manual_breaker_event": "pawcontrol_manual_breaker",
                "manual_check_event": "pawcontrol_resilience_check",
              },
            }
          },
        )
      ]
      if domain == "automation"
      else []
    ),
  )
  entry = SimpleNamespace(entry_id="entry-id", data={}, options={}, title="Ops")

  script_manager = PawControlScriptManager(hass, entry)
  script_manager._build_resilience_escalation_script()

  snapshot = script_manager.get_resilience_escalation_snapshot()
  assert snapshot is not None
  manual = snapshot["manual_events"]
  assert manual["available"] is True
  assert manual["configured_guard_events"] == ["pawcontrol_manual_guard"]
  assert manual["configured_breaker_events"] == ["pawcontrol_manual_breaker"]
  assert manual["configured_check_events"] == ["pawcontrol_resilience_check"]
  assert manual["system_guard_event"] is None
  assert manual["system_breaker_event"] is None
  assert manual["listener_events"]["pawcontrol_manual_guard"] == ["guard"]
  assert manual["listener_events"]["pawcontrol_manual_breaker"] == ["breaker"]
  assert manual["listener_events"]["pawcontrol_resilience_check"] == ["check"]
  assert manual["listener_sources"]["pawcontrol_manual_guard"] == ["blueprint"]
  assert manual["listener_sources"]["pawcontrol_manual_breaker"] == ["blueprint"]
  assert manual["listener_sources"]["pawcontrol_resilience_check"] == ["blueprint"]
  assert manual["last_trigger"] is None
  counters = manual["event_counters"]
  assert counters["total"] == 0
  assert counters["by_event"] == {
    "pawcontrol_manual_breaker": 0,
    "pawcontrol_manual_guard": 0,
    "pawcontrol_resilience_check": 0,
  }
  assert counters["by_reason"] == {}
  automation_entry = manual["automations"][0]
  assert automation_entry["configured_guard"] is True
  assert automation_entry["configured_breaker"] is True
  assert manual["preferred_guard_event"] == "pawcontrol_manual_guard"
  assert manual["preferred_breaker_event"] == "pawcontrol_manual_breaker"
  assert manual["preferred_check_event"] == "pawcontrol_resilience_check"
  assert manual["preferred_events"] == {
    "manual_check_event": "pawcontrol_resilience_check",
    "manual_guard_event": "pawcontrol_manual_guard",
    "manual_breaker_event": "pawcontrol_manual_breaker",
  }
  assert manual["active_listeners"] == [
    "pawcontrol_manual_breaker",
    "pawcontrol_manual_guard",
    "pawcontrol_resilience_check",
  ]
  assert manual["last_event"] is None
  assert manual["event_history"] == []
  listener_metadata = manual["listener_metadata"]
  assert listener_metadata["pawcontrol_manual_guard"]["sources"] == [
    "blueprint",
    "default",
  ]
  assert listener_metadata["pawcontrol_manual_guard"]["primary_source"] == "blueprint"
  assert listener_metadata["pawcontrol_manual_breaker"]["sources"] == [
    "blueprint",
    "default",
  ]
  assert listener_metadata["pawcontrol_manual_breaker"]["primary_source"] == "blueprint"
  assert listener_metadata["pawcontrol_resilience_check"]["sources"] == [
    "blueprint",
    "default",
  ]
  assert (
    listener_metadata["pawcontrol_resilience_check"]["primary_source"] == "blueprint"
  )


@pytest.mark.unit
def test_script_manager_manual_snapshot_combines_system_and_blueprint_sources() -> None:
  """System settings should appear alongside blueprint suggestions."""

  hass = SimpleNamespace(
    data={},
    states=SimpleNamespace(get=lambda entity_id: None),
    config_entries=SimpleNamespace(
      async_entries=lambda domain: [
        SimpleNamespace(
          entry_id="automation-id",
          title="Resilience follow-up",
          data={
            "use_blueprint": {
              "path": "blueprints/automation/pawcontrol/resilience_escalation_followup.yaml",
              "input": {
                "manual_guard_event": "pawcontrol_manual_guard",
              },
            }
          },
        )
      ]
      if domain == "automation"
      else []
    ),
  )

  entry = SimpleNamespace(
    entry_id="entry-id",
    data={},
    options={"system_settings": {"manual_guard_event": "pawcontrol_manual_guard"}},
    title="Ops",
  )

  script_manager = PawControlScriptManager(hass, entry)
  script_manager._build_resilience_escalation_script()

  snapshot = script_manager.get_resilience_escalation_snapshot()
  assert snapshot is not None
  manual = snapshot["manual_events"]
  assert manual["listener_sources"]["pawcontrol_manual_guard"] == [
    "blueprint",
    "system_options",
  ]
  metadata = manual["listener_metadata"]["pawcontrol_manual_guard"]
  assert metadata["sources"] == ["blueprint", "default", "system_settings"]
  assert metadata["primary_source"] == "system_settings"


@pytest.mark.unit
def test_script_manager_records_manual_event_trigger() -> None:
  """Manual event listeners should capture trigger metadata."""

  class DummyBus:
    def __init__(self) -> None:
      self.listeners: dict[str, list[ManualEventCallback]] = {}

    def async_listen(
      self, event_type: str, callback: ManualEventCallback
    ) -> Callable[[], None]:
      listeners = self.listeners.setdefault(event_type, [])
      listeners.append(callback)

      def _remove() -> None:
        listeners.remove(callback)

      return _remove

    def fire(
      self,
      event_type: str,
      *,
      context_id: str = "ctx",
      user_id: str | None = "user",
      origin: str = "LOCAL",
      data: Mapping[str, object] | None = None,
    ) -> None:
      event = SimpleNamespace(
        event_type=event_type,
        time_fired=dt_util.utcnow(),
        origin=origin,
        context=SimpleNamespace(id=context_id, user_id=user_id),
        data=data,
      )
      for callback in list(self.listeners.get(event_type, [])):
        callback(event)

  bus = DummyBus()
  hass = SimpleNamespace(
    data={},
    bus=bus,
    states=SimpleNamespace(get=lambda entity_id: None),
    config_entries=SimpleNamespace(async_entries=lambda domain: []),
  )
  entry = SimpleNamespace(
    entry_id="entry-id",
    data={},
    options={
      "system_settings": {
        "manual_guard_event": "pawcontrol_manual_guard",
        "manual_check_event": "pawcontrol_manual_check",
      }
    },
    title="Ops",
  )

  script_manager = PawControlScriptManager(hass, entry)
  script_manager._build_resilience_escalation_script()
  script_manager._refresh_manual_event_listeners()

  assert set(script_manager._manual_event_sources) == {
    "pawcontrol_manual_guard",
    "pawcontrol_manual_check",
    "pawcontrol_manual_breaker",
  }

  bus.fire(
    "pawcontrol_manual_guard",
    context_id="ctx-1",
    user_id="user-1",
    data={"reason": "test"},
  )

  snapshot = script_manager.get_resilience_escalation_snapshot()
  assert snapshot is not None
  manual = snapshot["manual_events"]
  last_event = manual["last_event"]
  assert last_event is not None
  assert last_event["event_type"] == "pawcontrol_manual_guard"
  assert last_event["category"] == "guard"
  assert last_event["matched_preference"] == "manual_guard_event"
  assert last_event["origin"] == "LOCAL"
  assert last_event["context_id"] == "ctx-1"
  assert last_event["user_id"] == "user-1"
  assert last_event["data"] == {"reason": "test"}
  assert last_event["time_fired"] is not None
  assert last_event["time_fired_age_seconds"] is not None
  assert last_event["sources"] == ["system_settings", "default"]
  assert last_event["reasons"] == ["guard"]
  assert manual["active_listeners"] == [
    "pawcontrol_manual_breaker",
    "pawcontrol_manual_check",
    "pawcontrol_manual_guard",
  ]
  history = manual["event_history"]
  assert isinstance(history, list) and history
  assert history[0]["event_type"] == "pawcontrol_manual_guard"
  assert history[0]["sources"] == ["system_options"]


@pytest.mark.asyncio
async def test_script_manager_sync_manual_events_updates_blueprint() -> None:
  """Manual event preferences should update resilience blueprint inputs."""

  @dataclass(slots=True)
  class _ConfigEntryUpdateRecord:
    entry: object
    data: ConfigEntryDataPayload | None
    options: PawControlOptionsData | None

  blueprint_inputs = {
    "manual_check_event": "pawcontrol_resilience_check",
    "manual_guard_event": "pawcontrol_manual_guard",
    "manual_breaker_event": "",
  }

  updated_payloads: list[_ConfigEntryUpdateRecord] = []

  def _async_update_entry(
    entry: object,
    *,
    data: ConfigEntryDataPayload | None = None,
    options: PawControlOptionsData | None = None,
  ) -> None:
    updated_payloads.append(
      _ConfigEntryUpdateRecord(entry=entry, data=data, options=options)
    )

  hass = SimpleNamespace(
    data={},
    config_entries=SimpleNamespace(
      async_entries=lambda domain: [
        SimpleNamespace(
          entry_id="automation-id",
          data={
            "use_blueprint": {
              "path": "blueprints/automation/pawcontrol/resilience_escalation_followup.yaml",
              "input": dict(blueprint_inputs),
            }
          },
        )
      ]
      if domain == "automation"
      else [],
      async_update_entry=_async_update_entry,
    ),
  )

  entry = SimpleNamespace(entry_id="entry-id", data={}, options={}, title="Ops")

  manager = PawControlScriptManager(hass, entry)

  await manager.async_sync_manual_resilience_events(
    {
      "manual_check_event": " pawcontrol_resilience_check_custom ",
      "manual_guard_event": "  ",
      "manual_breaker_event": "pawcontrol_manual_breaker",
    }
  )

  assert len(updated_payloads) == 1
  payload = updated_payloads[0]
  assert payload.entry.entry_id == "automation-id"
  assert payload.data is not None
  blueprint_data = payload.data["use_blueprint"]
  assert blueprint_data["path"].endswith("resilience_escalation_followup.yaml")
  inputs = blueprint_data["input"]
  assert inputs["manual_check_event"] == "pawcontrol_resilience_check_custom"
  assert inputs["manual_guard_event"] == ""
  assert inputs["manual_breaker_event"] == "pawcontrol_manual_breaker"


@pytest.mark.unit
def test_script_manager_manual_event_listener_records_last_trigger() -> None:
  """Manual event listeners should record the latest trigger metadata."""

  class DummyBus:
    def __init__(self) -> None:
      self.listeners: dict[str, Callable[[Event], None]] = {}

    def async_listen(
      self, event_type: str, callback: Callable[[Event], None]
    ) -> Callable[[], None]:
      self.listeners[event_type] = callback

      def _unsub() -> None:
        self.listeners.pop(event_type, None)

      return _unsub

  bus = DummyBus()
  hass = SimpleNamespace(
    data={},
    states=SimpleNamespace(get=lambda entity_id: None),
    config_entries=SimpleNamespace(async_entries=lambda domain: []),
    bus=bus,
  )
  entry = SimpleNamespace(
    entry_id="entry-id",
    data={},
    options={"system_settings": {"manual_guard_event": "pawcontrol_manual_guard"}},
    title="Ops",
  )

  script_manager = PawControlScriptManager(hass, entry)
  asyncio.run(script_manager.async_initialize())
  script_manager._build_resilience_escalation_script()

  assert "pawcontrol_manual_guard" in bus.listeners

  bus.listeners["pawcontrol_manual_guard"](Event("pawcontrol_manual_guard", {}))

  snapshot = script_manager.get_resilience_escalation_snapshot()
  assert snapshot is not None
  manual = snapshot["manual_events"]
  last_trigger = manual["last_trigger"]
  assert last_trigger is not None
  assert last_trigger["event_type"] == "pawcontrol_manual_guard"
  assert last_trigger["matched_preference"] == "manual_guard_event"
  assert last_trigger["category"] == "guard"
  assert last_trigger["sources"] == ["system_options"]
  assert last_trigger["reasons"] == ["guard"]
  assert last_trigger["sources"] == ["system_settings", "default"]
  assert manual["listener_sources"]["pawcontrol_manual_guard"] == ["system_options"]
  listener_metadata = manual["listener_metadata"]["pawcontrol_manual_guard"]
  assert listener_metadata["sources"] == ["default", "system_settings"]
  assert listener_metadata["primary_source"] == "system_settings"
  assert isinstance(last_trigger["recorded_age_seconds"], int)
  history = manual["event_history"]
  assert isinstance(history, list) and history
  assert history[0]["event_type"] == "pawcontrol_manual_guard"
  counters = manual["event_counters"]
  assert counters["total"] == 1
  assert counters["by_event"] == {"pawcontrol_manual_guard": 1}
  assert counters["by_reason"] == {"guard": 1}


@pytest.mark.unit
def test_script_manager_manual_history_size_respects_options() -> None:
  """Manual event history length should be configurable via options."""

  hass = SimpleNamespace(
    data={},
    states=SimpleNamespace(get=lambda entity_id: None),
    config_entries=SimpleNamespace(async_entries=lambda domain: []),
  )
  entry = SimpleNamespace(
    entry_id="entry-id",
    data={},
    options={"system_settings": {"manual_event_history_size": 7}},
    title="Ops",
  )

  manager = PawControlScriptManager(hass, entry)
  assert manager._manual_event_history.maxlen == 7

  async def _record_events() -> None:
    await manager.async_initialize()
    event = Event("pawcontrol_manual_guard", {})
    for _ in range(9):
      manager._handle_manual_event(event)

  asyncio.run(_record_events())

  assert len(manager._manual_event_history) == 7

  entry.options["system_settings"]["manual_event_history_size"] = 3
  asyncio.run(manager.async_initialize())
  assert manager._manual_event_history.maxlen == 3
  assert len(manager._manual_event_history) <= 3


@pytest.mark.unit
def test_resilience_followup_blueprint_manual_events() -> None:
  """Manual blueprint triggers should drive escalation and follow-up paths."""

  blueprint_path = Path(
    "blueprints/automation/pawcontrol/resilience_escalation_followup.yaml"
  )
  blueprint_source = blueprint_path.read_text(encoding="utf-8")

  assert "id: manual_guard_event" in blueprint_source
  assert "id: manual_breaker_event" in blueprint_source
  assert "trigger.id in valid_trigger_ids" in blueprint_source
  assert "trigger.id in guard_trigger_ids" in blueprint_source
  assert "trigger.id in breaker_trigger_ids" in blueprint_source
  assert "- manual_event" in blueprint_source
  assert "- manual_guard_event" in blueprint_source
  assert "- manual_breaker_event" in blueprint_source


@pytest.mark.unit
def test_door_sensor_manager_register_cache_monitor() -> None:
  """Door sensor manager should publish detection diagnostics."""

  hass = SimpleNamespace()
  manager = DoorSensorManager(hass, "entry")
  now = dt_util.utcnow()
  manager._sensor_configs = {
    "buddy": DoorSensorConfig(
      entity_id="binary_sensor.front_door",
      dog_id="buddy",
      dog_name="Buddy",
    )
  }
  manager._detection_states = {
    "buddy": WalkDetectionState(
      dog_id="buddy",
      current_state=WALK_STATE_ACTIVE,
      door_opened_at=now - timedelta(seconds=30),
      door_closed_at=now,
      potential_walk_start=now - timedelta(minutes=5),
      confidence_score=0.85,
      state_history=[(now - timedelta(seconds=30), STATE_ON), (now, STATE_OFF)],
    )
  }
  manager._detection_stats = {
    "total_detections": 3,
    "successful_walks": 2,
    "false_positives": 1,
    "false_negatives": 0,
    "average_confidence": 0.72,
  }

  registrar = _RecordingRegistrar()
  manager.register_cache_monitors(registrar, prefix="door_sensor")

  assert "door_sensor_cache" in registrar.monitors
  snapshot = registrar.monitors["door_sensor_cache"].coordinator_snapshot()
  stats = snapshot["stats"]
  assert stats["configured_sensors"] == 1
  assert stats["active_detections"] == 1
  diagnostics = snapshot["diagnostics"]
  assert diagnostics["per_dog"]["buddy"]["entity_id"] == "binary_sensor.front_door"
  assert diagnostics["detection_stats"]["successful_walks"] == 2
  assert diagnostics["cleanup_task_active"] is False


@pytest.mark.unit
def test_door_sensor_manager_timestamp_anomaly() -> None:
  """Door sensor diagnostics should surface stale activity timestamps."""

  hass = SimpleNamespace()
  manager = DoorSensorManager(hass, "entry")
  old = dt_util.utcnow() - (CACHE_TIMESTAMP_STALE_THRESHOLD + timedelta(hours=2))
  manager._sensor_configs = {
    "buddy": DoorSensorConfig(
      entity_id="binary_sensor.front_door",
      dog_id="buddy",
      dog_name="Buddy",
    )
  }
  manager._detection_states = {
    "buddy": WalkDetectionState(
      dog_id="buddy",
      current_state=WALK_STATE_ACTIVE,
      door_opened_at=old,
      door_closed_at=old,
      potential_walk_start=old,
      confidence_score=0.42,
      state_history=[(old, STATE_ON)],
    )
  }
  manager._detection_stats = {
    "total_detections": 1,
    "successful_walks": 0,
    "false_positives": 0,
    "false_negatives": 0,
    "average_confidence": 0.42,
  }
  manager._last_activity = old

  registrar = _RecordingRegistrar()
  manager.register_cache_monitors(registrar, prefix="door_sensor")

  snapshot = registrar.monitors["door_sensor_cache"].coordinator_snapshot()
  diagnostics = snapshot["diagnostics"]
  anomalies = diagnostics["timestamp_anomalies"]
  assert anomalies["manager"] == "stale"
  assert anomalies["buddy"] == "stale"


@pytest.mark.unit
def test_auto_registers_helper_manager_cache(
  monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
  """Data manager should register helper manager caches when available."""

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  entry = SimpleNamespace(entry_id="entry", data={}, options={})
  helper_manager = PawControlHelperManager(hass, entry)
  helper_manager._created_helpers.add("input_boolean.pawcontrol_helper_created")
  script_manager = PawControlScriptManager(SimpleNamespace(data={}), entry)
  script_manager._created_entities.add("script.pawcontrol_helper_created")
  door_manager = DoorSensorManager(SimpleNamespace(), "entry")
  assert callable(door_manager.register_cache_monitors)

  modules = _DummyModules()
  tracker = _DummyTracker()
  coordinator = SimpleNamespace(
    hass=hass,
    config_entry=SimpleNamespace(entry_id="entry"),
    _modules=modules,
    _entity_budget=tracker,
  )
  coordinator.helper_manager = helper_manager
  coordinator.script_manager = script_manager
  coordinator.door_sensor_manager = door_manager

  manager = PawControlDataManager(
    hass=hass,
    coordinator=coordinator,
    dogs_config=[],
  )

  script_manager.register_cache_monitors(manager, prefix="script_manager")
  door_manager.register_cache_monitors(manager, prefix="door_sensor")

  snapshots = manager.cache_snapshots()
  assert "helper_manager_cache" in snapshots
  assert "script_manager_cache" in snapshots
  assert "door_sensor_cache" in snapshots


@pytest.mark.unit
def test_register_runtime_cache_monitors_adds_helper_cache(tmp_path: Path) -> None:
  """Runtime cache registration should pick up helper manager monitors."""

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  entry = SimpleNamespace(entry_id="entry", data={}, options={})
  helper_manager = PawControlHelperManager(hass, entry)

  manager = PawControlDataManager(
    hass=hass,
    entry_id="entry",
    dogs_config=[],
  )

  assert "helper_manager_cache" not in manager.cache_snapshots()

  runtime = SimpleNamespace(
    notification_manager=None,
    person_manager=None,
    helper_manager=helper_manager,
  )

  manager.register_runtime_cache_monitors(runtime)
  snapshots = manager.cache_snapshots()

  assert "helper_manager_cache" in snapshots


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_get_module_history_respects_limit(tmp_path: Path) -> None:
  """Module history lookups should return sorted entries with optional limits."""

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  manager = PawControlDataManager(
    hass=hass,
    entry_id="history-test",
    dogs_config=[{"dog_id": "buddy", "modules": {MODULE_HEALTH: True}}],
  )

  await manager.async_initialize()

  earlier = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
  later = datetime(2024, 1, 2, 8, 30, tzinfo=UTC)

  await manager.async_log_health_data(
    "buddy",
    {"timestamp": earlier, "weight": 12.5, "health_status": "good"},
  )
  await manager.async_log_health_data(
    "buddy",
    {"timestamp": later, "weight": 11.8, "health_status": "excellent"},
  )

  entries = await manager.async_get_module_history(MODULE_HEALTH, "buddy")
  assert len(entries) == 2
  assert entries[0]["weight"] == 11.8
  assert entries[1]["weight"] == 12.5
  assert entries[0]["timestamp"] > entries[1]["timestamp"]

  limited = await manager.async_get_module_history(MODULE_HEALTH, "buddy", limit=1)
  assert limited == entries[:1]

  recent_only = await manager.async_get_module_history(
    MODULE_HEALTH, "buddy", since=later - timedelta(hours=1)
  )
  assert len(recent_only) == 1
  assert recent_only[0]["weight"] == 11.8

  older_only = await manager.async_get_module_history(
    MODULE_HEALTH, "buddy", until=earlier + timedelta(minutes=1)
  )
  assert len(older_only) == 1
  assert older_only[0]["weight"] == 12.5

  assert await manager.async_get_module_history("unknown", "buddy") == []
  assert await manager.async_get_module_history(MODULE_HEALTH, "unknown") == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_weekly_health_report_filters_old_entries(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  """Weekly health reports should ignore entries outside the seven-day window."""

  from custom_components.pawcontrol import data_manager as dm

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  manager = PawControlDataManager(
    hass=hass,
    entry_id="weekly-health",
    dogs_config=[{"dog_id": "buddy", "modules": {MODULE_HEALTH: True}}],
  )

  base_time = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
  monkeypatch.setattr(dm, "_utcnow", lambda: base_time)

  await manager.async_initialize()

  older = base_time - timedelta(days=12)
  recent = base_time - timedelta(days=2)

  await manager.async_log_health_data(
    "buddy",
    {
      "timestamp": older,
      "weight": 12.0,
      "temperature": 38.0,
      "health_status": "ok",
    },
  )
  await manager.async_log_health_data(
    "buddy",
    {
      "timestamp": recent,
      "weight": 11.5,
      "temperature": 37.8,
      "health_status": "excellent",
    },
  )

  await manager.async_log_medication(
    "buddy",
    {"medication_name": "pain-relief", "dose": "5ml", "administration_time": older},
  )
  await manager.async_log_medication(
    "buddy",
    {
      "medication_name": "vitamin",
      "dose": "2ml",
      "administration_time": recent,
    },
  )

  report = await manager.async_generate_weekly_health_report("buddy")

  assert report["entries"] == 1
  assert report["recent_weights"] == [11.5]
  assert report["recent_temperatures"] == [37.8]
  assert report["medication"]["entries"] == 1
  assert report["medication"]["latest"]["medication_name"] == "vitamin"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analyze_patterns_uses_filtered_history(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  """Pattern analysis should rely on the shared history helpers."""

  from custom_components.pawcontrol import data_manager as dm

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  manager = PawControlDataManager(
    hass=hass,
    entry_id="analysis",
    dogs_config=[
      {
        "dog_id": "buddy",
        "modules": {
          MODULE_FEEDING: True,
          MODULE_HEALTH: True,
          MODULE_WALK: True,
        },
      }
    ],
  )

  current_time = datetime(2024, 2, 1, 8, 0, tzinfo=UTC)

  def _now() -> datetime:
    return current_time

  monkeypatch.setattr(dm, "_utcnow", _now)

  await manager.async_initialize()

  older_feed = current_time - timedelta(days=10)
  recent_feed = current_time - timedelta(days=3)

  await manager.async_log_feeding(
    "buddy",
    FeedingData(
      meal_type="breakfast",
      portion_size=120.0,
      food_type="dry_food",
      timestamp=older_feed,
    ),
  )
  await manager.async_log_feeding(
    "buddy",
    FeedingData(
      meal_type="dinner",
      portion_size=200.0,
      food_type="dry_food",
      timestamp=recent_feed,
    ),
  )

  older_health = current_time - timedelta(days=9)
  recent_health = current_time - timedelta(days=2)

  await manager.async_log_health_data(
    "buddy", {"timestamp": older_health, "weight": 12.3, "health_status": "ok"}
  )
  await manager.async_log_health_data(
    "buddy",
    {"timestamp": recent_health, "weight": 11.9, "health_status": "great"},
  )

  older_walk_start = current_time - timedelta(days=8, hours=1)
  older_walk_end = current_time - timedelta(days=8)
  recent_walk_start = current_time - timedelta(days=1, hours=2)
  recent_walk_end = current_time - timedelta(days=1, hours=1, minutes=30)

  current_time = older_walk_start
  await manager.async_start_walk("buddy")
  current_time = older_walk_end
  await manager.async_end_walk("buddy", distance=2.5, rating=4)

  current_time = recent_walk_start
  await manager.async_start_walk("buddy")
  current_time = recent_walk_end
  await manager.async_end_walk("buddy", distance=3.2, rating=5)

  current_time = datetime(2024, 2, 1, 18, 0, tzinfo=UTC)

  result = await manager.async_analyze_patterns("buddy", "comprehensive", days=7)

  feeding = result["feeding"]
  assert feeding["entries"] == 1
  assert feeding["total_portion_size"] == 200.0
  assert feeding["first_entry"]["portion_size"] == 200.0
  assert feeding["last_entry"]["portion_size"] == 200.0

  walking = result["walking"]
  assert walking["entries"] == 1
  assert walking["total_distance"] == 3.2

  health = result["health"]
  assert health["entries"] == 1
  assert health["latest"]["weight"] == 11.9


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_data_uses_history_helper(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  """Exports should reuse history filters and maintain chronological ordering."""

  from custom_components.pawcontrol import data_manager as dm

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  manager = PawControlDataManager(
    hass=hass,
    entry_id="export-history",
    dogs_config=[
      {
        "dog_id": "buddy",
        "modules": {
          MODULE_FEEDING: True,
          MODULE_MEDICATION: True,
        },
      }
    ],
  )

  base_time = datetime(2024, 3, 15, 12, 0, tzinfo=UTC)

  def _now() -> datetime:
    return base_time

  monkeypatch.setattr(dm, "_utcnow", _now)

  await manager.async_initialize()

  older_feed = base_time - timedelta(days=5)
  first_recent_feed = base_time - timedelta(days=1, hours=3)
  second_recent_feed = base_time - timedelta(hours=4)

  await manager.async_log_feeding(
    "buddy",
    FeedingData(
      meal_type="breakfast",
      portion_size=110.0,
      food_type="dry_food",
      timestamp=older_feed,
    ),
  )
  await manager.async_log_feeding(
    "buddy",
    FeedingData(
      meal_type="lunch",
      portion_size=150.0,
      food_type="wet_food",
      timestamp=first_recent_feed,
    ),
  )
  await manager.async_log_feeding(
    "buddy",
    FeedingData(
      meal_type="dinner",
      portion_size=90.0,
      food_type="dry_food",
      timestamp=second_recent_feed,
    ),
  )

  older_medication = base_time - timedelta(days=4)
  recent_medication = base_time - timedelta(hours=6)

  await manager.async_log_medication(
    "buddy",
    {
      "medication_name": "pain-relief",
      "dose": "5ml",
      "administration_time": older_medication,
    },
  )
  await manager.async_log_medication(
    "buddy",
    {
      "medication_name": "vitamin",
      "dose": "2ml",
      "administration_time": recent_medication,
    },
  )

  feeding_export = await manager.async_export_data(
    "buddy", "feeding", format="json", days=2
  )
  feeding_payload = json.loads(feeding_export.read_text(encoding="utf-8"))
  assert feeding_payload["data_type"] == "feeding"
  feeding_entries = feeding_payload["entries"]
  assert len(feeding_entries) == 2
  feeding_timestamps = [entry["timestamp"] for entry in feeding_entries]
  assert feeding_timestamps == [
    first_recent_feed.isoformat(),
    second_recent_feed.isoformat(),
  ]

  medication_export = await manager.async_export_data(
    "buddy",
    "medication",
    format="json",
    date_from=(base_time - timedelta(days=1, hours=1)).isoformat(),
    date_to=(base_time - timedelta(minutes=30)).isoformat(),
  )
  medication_payload = json.loads(medication_export.read_text(encoding="utf-8"))
  medication_entries = medication_payload["entries"]
  assert len(medication_entries) == 1
  medication_entry = medication_entries[0]
  assert medication_entry["medication_name"] == "vitamin"
  assert medication_entry["administration_time"] == recent_medication.isoformat()
  assert medication_entry["logged_at"] == base_time.isoformat()


class _StaticCache:
  """Return a static coordinator snapshot for diagnostics registration tests."""

  def __init__(self, marker: str) -> None:
    self._marker = marker

  def coordinator_snapshot(self) -> JSONMutableMapping:
    return cast(
      JSONMutableMapping,
      {
        "stats": {"marker": self._marker},
        "diagnostics": {"marker": self._marker},
      },
    )


class _DummyNotificationManager:
  """Expose cache registration hooks for coordinator wiring tests."""

  def __init__(self) -> None:
    self.person_manager = _DummyPersonManager()

  def register_cache_monitors(self, registrar: CacheMonitorRegistrar) -> None:
    registrar.register_cache_monitor("notification_cache", _StaticCache("notif"))
    self.person_manager.register_cache_monitors(registrar, prefix="person_entity")


class _DummyPersonManager:
  """Expose a registrar hook compatible with PersonEntityManager."""

  def register_cache_monitors(
    self, registrar: CacheMonitorRegistrar, *, prefix: str
  ) -> None:
    registrar.register_cache_monitor(f"{prefix}_targets", _StaticCache("person"))


class _DummyCoordinator:
  """Coordinator stub implementing the binding protocol for tests."""

  def __init__(self, hass: HomeAssistant) -> None:
    self.hass = hass
    self.config_entry = SimpleNamespace(entry_id="coordinator-test")
    self.data_manager = None
    self.feeding_manager = None
    self.walk_manager = None
    self.notification_manager = None
    self.gps_geofence_manager = None
    self.geofencing_manager = None
    self.weather_health_manager = None
    self.garden_manager = None
    self._modules = _DummyModules()
    self._entity_budget = _DummyTracker()


class _DummyModulesAdapter:
  """Adapter stub satisfying the module binding protocol."""

  def __init__(self) -> None:
    self.attached = False
    self.detached = False

  def attach_managers(
    self,
    *,
    data_manager: PawControlDataManager | None,
    feeding_manager: FeedingManager | None,
    walk_manager: WalkManager | None,
    gps_geofence_manager: GPSGeofenceManager | None,
    weather_health_manager: WeatherHealthManager | None,
    garden_manager: GardenManager | None,
  ) -> None:
    self.attached = True

  def detach_managers(self) -> None:
    self.detached = True


@pytest.mark.unit
def test_notification_person_caches_register_via_binding(tmp_path: Path) -> None:
  """Coordinator binding should surface notification and person cache snapshots."""

  hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
  coordinator = _DummyCoordinator(hass)
  modules = _DummyModulesAdapter()
  manager = PawControlDataManager(
    hass=hass,
    coordinator=coordinator,
    dogs_config=[],
  )
  notification_manager = _DummyNotificationManager()

  bind_runtime_managers(
    coordinator,
    modules,
    CoordinatorRuntimeManagers(
      data_manager=manager,
      notification_manager=notification_manager,
    ),
  )

  snapshots = manager.cache_snapshots()

  assert "notification_cache" in snapshots
  assert snapshots["notification_cache"]["stats"]["marker"] == "notif"
  assert "person_entity_targets" in snapshots
  assert snapshots["person_entity_targets"]["stats"]["marker"] == "person"
