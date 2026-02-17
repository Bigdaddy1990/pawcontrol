"""Unit coverage for the PawControl data manager instrumentation."""

import asyncio
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from homeassistant import const as ha_const
from homeassistant.components.script.const import CONF_FIELDS
from homeassistant.const import CONF_ALIAS, CONF_DEFAULT, STATE_OFF, STATE_ON
from homeassistant.core import Event
from homeassistant.util import dt as dt_util, slugify as ha_slugify
import pytest

from custom_components.pawcontrol.const import (  # noqa: E111
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

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant  # noqa: E111

    from custom_components.pawcontrol.feeding_manager import FeedingManager  # noqa: E111
    from custom_components.pawcontrol.garden_manager import GardenManager  # noqa: E111
    from custom_components.pawcontrol.gps_manager import GPSGeofenceManager  # noqa: E111
    from custom_components.pawcontrol.walk_manager import WalkManager  # noqa: E111
    from custom_components.pawcontrol.weather_manager import (  # noqa: E111
        WeatherHealthManager,  # noqa: E111
    )


if hasattr(ha_slugify, "slugify"):
    ha_slugify = ha_slugify.slugify  # noqa: E111


CONF_SEQUENCE = getattr(ha_const, "CONF_SEQUENCE", "sequence")
CONF_DESCRIPTION = "description"


class StubDataManager(PawControlDataManager):
    """Minimal data manager that exercises visitor profiling without HA deps."""  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
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

    async def _get_namespace_data(self, namespace: str) -> JSONMutableMapping:  # noqa: E111
        """Return empty namespace data for tests."""

        assert namespace == "visitor_mode"
        return cast(JSONMutableMapping, {})

    async def _save_namespace(self, namespace: str, data: JSONMutableMapping) -> None:  # noqa: E111
        """Capture writes instead of hitting Home Assistant storage."""

        assert namespace == "visitor_mode"
        self.saved_payload = data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_set_visitor_mode_records_metrics() -> None:
    """Visitor workflows should record runtime samples and update metrics."""  # noqa: E111

    manager = StubDataManager()  # noqa: E111
    metrics_sink = CoordinatorMetrics()  # noqa: E111
    manager.set_metrics_sink(metrics_sink)  # noqa: E111

    await manager.async_set_visitor_mode("buddy", {"enabled": True})  # noqa: E111

    assert manager.saved_payload == {"buddy": {"enabled": True}}  # noqa: E111
    assert manager._visitor_timings  # at least one sample captured  # noqa: E111
    assert manager._metrics["visitor_mode_last_runtime_ms"] < 3.0  # noqa: E111
    assert manager._metrics["visitor_mode_avg_runtime_ms"] < 3.0  # noqa: E111
    assert metrics_sink.visitor_mode_timings  # noqa: E111
    assert metrics_sink.average_visitor_runtime_ms < 3.0  # noqa: E111


@dataclass(slots=True)
class _DummyMetrics:
    entries: int  # noqa: E111
    hits: int  # noqa: E111
    misses: int  # noqa: E111

    @property  # noqa: E111
    def hit_rate(self) -> float:  # noqa: E111
        total = self.hits + self.misses
        return (self.hits / total * 100.0) if total else 0.0


class _DummyAdapter:
    """Return static cache metrics for module adapters."""  # noqa: E111

    def __init__(self, entries: int, hits: int, misses: int) -> None:  # noqa: E111
        self._metrics = _DummyMetrics(entries, hits, misses)

    def cache_metrics(self) -> _DummyMetrics:  # noqa: E111
        return self._metrics


class _DummyModules:
    """Expose per-module cache metrics for coordinator diagnostics."""  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        self.feeding = _DummyAdapter(2, 5, 1)
        self.walk = _DummyAdapter(1, 1, 2)
        self.geofencing = _DummyAdapter(0, 0, 0)
        self.health = _DummyAdapter(3, 4, 0)
        self.weather = _DummyAdapter(0, 0, 0)
        self.garden = _DummyAdapter(0, 0, 0)

    def cache_metrics(self) -> _DummyMetrics:  # noqa: E111
        total = _DummyMetrics(0, 0, 0)
        for adapter in (
            self.feeding,
            self.walk,
            self.geofencing,
            self.health,
            self.weather,
            self.garden,
        ):
            metrics = adapter.cache_metrics()  # noqa: E111
            total.entries += metrics.entries  # noqa: E111
            total.hits += metrics.hits  # noqa: E111
            total.misses += metrics.misses  # noqa: E111
        return total


ManualEventCallback = Callable[[Event], None]


class _RecordingRegistrar(CacheMonitorRegistrar):
    """Capture cache monitor registrations for assertions."""  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        self.monitors: dict[str, CacheMonitorTarget] = {}

    def register_cache_monitor(self, name: str, cache: CacheMonitorTarget) -> None:  # noqa: E111
        self.monitors[name] = cache


@dataclass(slots=True)
class _DummySnapshot:
    dog_id: str  # noqa: E111
    profile: str  # noqa: E111
    capacity: int  # noqa: E111
    base_allocation: int  # noqa: E111
    dynamic_allocation: int  # noqa: E111
    requested_entities: tuple[str, ...]  # noqa: E111
    denied_requests: tuple[str, ...]  # noqa: E111
    recorded_at: datetime  # noqa: E111


class _DummyTracker:
    """Expose entity budget tracker statistics for diagnostics tests."""  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
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

    def snapshots(self) -> tuple[_DummySnapshot, ...]:  # noqa: E111
        return self._snapshots

    def summary(self) -> JSONMutableMapping:  # noqa: E111
        return cast(
            JSONMutableMapping,
            {"peak_utilization": 75.0, "tracked": len(self._snapshots)},
        )

    def saturation(self) -> float:  # noqa: E111
        return 0.5


class _ErrorSummaryTracker(_DummyTracker):
    """Tracker that raises when building a summary to exercise fallbacks."""  # noqa: E111

    def summary(self) -> JSONMutableMapping:  # type: ignore[override]  # noqa: E111
        raise RuntimeError("tracker summary failed")


@pytest.mark.unit
def test_auto_registered_cache_monitors(tmp_path: Path) -> None:
    """Data manager should surface coordinator caches via diagnostics snapshots."""  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    modules = _DummyModules()  # noqa: E111
    tracker = _DummyTracker()  # noqa: E111
    coordinator = SimpleNamespace(  # noqa: E111
        hass=hass,
        config_entry=SimpleNamespace(entry_id="test-entry"),
        _modules=modules,
        _entity_budget=tracker,
    )

    manager = PawControlDataManager(  # noqa: E111
        hass=hass,
        coordinator=coordinator,
        dogs_config=[],
    )

    snapshots = manager.cache_snapshots()  # noqa: E111

    assert "coordinator_modules" in snapshots  # noqa: E111
    module_snapshot = snapshots["coordinator_modules"]  # noqa: E111
    assert module_snapshot["stats"]["entries"] == modules.cache_metrics().entries  # noqa: E111
    per_module = module_snapshot["diagnostics"]["per_module"]  # noqa: E111
    assert per_module["feeding"]["hits"] == 5  # noqa: E111
    assert per_module["walk"]["misses"] == 2  # noqa: E111

    assert "entity_budget_tracker" in snapshots  # noqa: E111
    budget_snapshot = snapshots["entity_budget_tracker"]  # noqa: E111
    assert budget_snapshot["stats"]["tracked_dogs"] == 2  # noqa: E111
    assert budget_snapshot["stats"]["saturation_percent"] == 50.0  # noqa: E111
    assert budget_snapshot["diagnostics"]["summary"]["peak_utilization"] == 75.0  # noqa: E111
    dog_ids = {entry["dog_id"] for entry in budget_snapshot["diagnostics"]["snapshots"]}  # noqa: E111
    assert dog_ids == {"buddy", "max"}  # noqa: E111

    for name in (  # noqa: E111
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
    """Entity budget diagnostics should expose serialised error payloads."""  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    modules = _DummyModules()  # noqa: E111
    tracker = _ErrorSummaryTracker()  # noqa: E111
    coordinator = SimpleNamespace(  # noqa: E111
        hass=hass,
        config_entry=SimpleNamespace(entry_id="test-entry"),
        _modules=modules,
        _entity_budget=tracker,
    )

    manager = PawControlDataManager(  # noqa: E111
        hass=hass,
        coordinator=coordinator,
        dogs_config=[],
    )

    snapshots = manager.cache_snapshots()  # noqa: E111
    diagnostics = snapshots["entity_budget_tracker"]["diagnostics"]  # noqa: E111

    summary = diagnostics["summary"]  # noqa: E111
    assert summary["error"] == "tracker summary failed"  # noqa: E111
    summary["extra"] = (  # noqa: E111
        True  # ensure mapping is mutable for downstream updates
    )
    assert summary["extra"] is True  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_storage_namespace_monitors_track_updates(tmp_path: Path) -> None:
    """Namespace cache monitors should reflect persisted updates."""  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    manager = PawControlDataManager(  # noqa: E111
        hass=hass,
        entry_id="storage-test",
        dogs_config=[{"dog_id": "buddy"}],
    )

    await manager.async_initialize()  # noqa: E111
    await manager.async_set_visitor_mode("buddy", {"enabled": True})  # noqa: E111
    await manager.async_set_dog_power_state("buddy", True)  # noqa: E111

    snapshots = manager.cache_snapshots()  # noqa: E111

    visitor_snapshot = snapshots["storage_visitor_mode"]  # noqa: E111
    assert visitor_snapshot["stats"]["dogs"] == 1  # noqa: E111
    assert visitor_snapshot["diagnostics"]["per_dog"]["buddy"]["entries"] >= 1  # noqa: E111
    assert "timestamp_issue" not in visitor_snapshot["diagnostics"]["per_dog"]["buddy"]  # noqa: E111
    assert "timestamp_anomalies" not in visitor_snapshot["diagnostics"]  # noqa: E111

    module_state_snapshot = snapshots["storage_module_state"]  # noqa: E111
    assert module_state_snapshot["diagnostics"]["per_dog"]["buddy"]["entries"] >= 1  # noqa: E111


@pytest.mark.unit
def test_storage_namespace_timestamp_anomalies(tmp_path: Path) -> None:
    """Namespace monitors should flag missing or stale timestamps."""  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    manager = PawControlDataManager(  # noqa: E111
        hass=hass,
        entry_id="storage-test",
        dogs_config=[{"dog_id": "buddy"}],
    )

    manager._namespace_state["visitor_mode"] = {  # noqa: E111
        "buddy": {"enabled": True, "timestamp": None},
        "max": {
            "enabled": True,
            "timestamp": (dt_util.utcnow() + timedelta(hours=1)).isoformat(),
        },
    }

    snapshots = manager.cache_snapshots()  # noqa: E111
    diagnostics = snapshots["storage_visitor_mode"]["diagnostics"]  # noqa: E111
    anomalies = diagnostics["timestamp_anomalies"]  # noqa: E111
    assert anomalies["buddy"] == "missing"  # noqa: E111
    assert anomalies["max"] == "future"  # noqa: E111


@pytest.mark.unit
def test_helper_manager_register_cache_monitor() -> None:
    """Helper manager should expose diagnostics through the cache registrar."""  # noqa: E111

    hass = SimpleNamespace()  # noqa: E111
    entry = SimpleNamespace(entry_id="entry", data={}, options={})  # noqa: E111
    helper_manager = PawControlHelperManager(hass, entry)  # noqa: E111
    helper_manager._created_helpers.add("input_boolean.pawcontrol_buddy_breakfast_fed")  # noqa: E111
    helper_manager._dog_helpers = {  # noqa: E111
        "buddy": ["input_boolean.pawcontrol_buddy_breakfast_fed"],
    }
    helper_manager._managed_entities = {  # noqa: E111
        "input_boolean.pawcontrol_buddy_breakfast_fed": cast(
            HelperEntityMetadata, {"domain": "input_boolean"}
        )
    }
    helper_manager._cleanup_listeners = [lambda: None]  # noqa: E111
    helper_manager._daily_reset_configured = True  # noqa: E111

    registrar = _RecordingRegistrar()  # noqa: E111
    helper_manager.register_cache_monitors(registrar, prefix="helper_manager")  # noqa: E111

    assert "helper_manager_cache" in registrar.monitors  # noqa: E111
    snapshot = registrar.monitors["helper_manager_cache"].coordinator_snapshot()  # noqa: E111
    assert snapshot["stats"]["helpers"] == 1  # noqa: E111
    diagnostics = snapshot["diagnostics"]  # noqa: E111
    assert diagnostics["per_dog_helpers"]["buddy"] == 1  # noqa: E111
    assert diagnostics["entity_domains"]["input_boolean"] == 1  # noqa: E111
    assert diagnostics["daily_reset_configured"] is True  # noqa: E111
    guard_metrics = diagnostics["service_guard_metrics"]  # noqa: E111
    assert guard_metrics == {  # noqa: E111
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
    """Helper manager should short-circuit helper creation when hass services missing."""  # noqa: E111

    hass = SimpleNamespace(data={}, states=SimpleNamespace(get=lambda entity_id: None))  # noqa: E111
    entry = SimpleNamespace(entry_id="entry", data={}, options={})  # noqa: E111
    helper_manager = PawControlHelperManager(hass, entry)  # noqa: E111

    class _DummyRegistry:  # noqa: E111
        def async_get(self, entity_id: str) -> None:
            return None  # noqa: E111

    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.helper_manager.er.async_get",
        lambda hass_instance: _DummyRegistry(),
    )

    # Simulate Home Assistant instance without the services API.  # noqa: E114
    helper_manager._hass = None  # noqa: E111

    await helper_manager._async_create_input_boolean(  # noqa: E111
        "input_boolean.pawcontrol_test_breakfast_fed",
        "Test Helper",
        initial=True,
    )

    assert (  # noqa: E111
        "input_boolean.pawcontrol_test_breakfast_fed"
        not in helper_manager._created_helpers
    )

    guard_metrics = helper_manager.guard_metrics  # noqa: E111
    assert guard_metrics["executed"] == 0  # noqa: E111
    assert guard_metrics["skipped"] == 1  # noqa: E111
    assert guard_metrics["reasons"]["missing_instance"] == 1  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_helper_manager_guard_metrics_accumulate_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Helper manager should aggregate guard skips across lifecycle services."""  # noqa: E111

    hass = SimpleNamespace(data={})  # noqa: E111
    entry = SimpleNamespace(entry_id="entry", data={}, options={})  # noqa: E111
    helper_manager = PawControlHelperManager(hass, entry)  # noqa: E111

    class _DummyRegistry:  # noqa: E111
        def async_get(self, entity_id: str) -> None:
            return None  # noqa: E111

    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.helper_manager.er.async_get",
        lambda hass_instance: _DummyRegistry(),
    )

    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.helper_manager.slugify",
        lambda value: value,
    )

    helper_manager._hass = None  # noqa: E111

    await helper_manager._async_create_input_boolean(  # noqa: E111
        "input_boolean.pawcontrol_buddy_breakfast_fed",
        "Buddy Breakfast",
        initial=False,
    )

    helper_manager._created_helpers = {  # noqa: E111
        "input_boolean.pawcontrol_buddy_breakfast_fed",
    }
    helper_manager._managed_entities = {  # noqa: E111
        "input_boolean.pawcontrol_buddy_breakfast_fed": cast(
            HelperEntityMetadata, {"domain": "input_boolean"}
        ),
    }

    await helper_manager.async_remove_dog_helpers("buddy")  # noqa: E111

    guard_metrics = helper_manager.guard_metrics  # noqa: E111
    assert guard_metrics["executed"] == 0  # noqa: E111
    assert guard_metrics["skipped"] == 2  # noqa: E111
    assert guard_metrics["reasons"]["missing_instance"] == 2  # noqa: E111
    assert len(guard_metrics["last_results"]) == 2  # noqa: E111


@pytest.mark.unit
def test_script_manager_register_cache_monitor() -> None:
    """Script manager should expose created script diagnostics."""  # noqa: E111

    hass = SimpleNamespace(data={})  # noqa: E111
    entry = SimpleNamespace(entry_id="entry", data={}, options={})  # noqa: E111
    script_manager = PawControlScriptManager(hass, entry)  # noqa: E111
    script_manager._created_entities.update({  # noqa: E111
        "script.pawcontrol_buddy_reset",
        "script.pawcontrol_max_reset",
        "script.pawcontrol_entry_resilience_escalation",
    })
    script_manager._dog_scripts = {  # noqa: E111
        "buddy": ["script.pawcontrol_buddy_reset"],
        "max": ["script.pawcontrol_max_reset"],
    }
    script_manager._entry_scripts = ["script.pawcontrol_entry_resilience_escalation"]  # noqa: E111

    registrar = _RecordingRegistrar()  # noqa: E111
    script_manager.register_cache_monitors(registrar, prefix="script_manager")  # noqa: E111

    assert "script_manager_cache" in registrar.monitors  # noqa: E111
    snapshot = registrar.monitors["script_manager_cache"].coordinator_snapshot()  # noqa: E111
    assert snapshot["stats"]["scripts"] == 3  # noqa: E111
    assert snapshot["stats"]["entry_scripts"] == 1  # noqa: E111
    diagnostics = snapshot["diagnostics"]  # noqa: E111
    assert diagnostics["per_dog"]["buddy"]["count"] == 1  # noqa: E111
    assert diagnostics["entry_scripts"] == [  # noqa: E111
        "script.pawcontrol_entry_resilience_escalation"
    ]
    assert diagnostics["created_entities"] == sorted(diagnostics["created_entities"])  # noqa: E111


@pytest.mark.unit
def test_script_manager_timestamp_anomaly() -> None:
    """Script manager diagnostics should flag stale generations."""  # noqa: E111

    hass = SimpleNamespace(data={})  # noqa: E111
    entry = SimpleNamespace(entry_id="entry", data={}, options={})  # noqa: E111
    script_manager = PawControlScriptManager(hass, entry)  # noqa: E111
    script_manager._created_entities.add("script.pawcontrol_buddy_reset")  # noqa: E111
    script_manager._dog_scripts = {"buddy": ["script.pawcontrol_buddy_reset"]}  # noqa: E111
    script_manager._last_generation = dt_util.utcnow() - (  # noqa: E111
        CACHE_TIMESTAMP_STALE_THRESHOLD + timedelta(hours=1)
    )

    registrar = _RecordingRegistrar()  # noqa: E111
    script_manager.register_cache_monitors(registrar, prefix="script_manager")  # noqa: E111

    snapshot = registrar.monitors["script_manager_cache"].coordinator_snapshot()  # noqa: E111
    diagnostics = snapshot["diagnostics"]  # noqa: E111
    anomalies = diagnostics["timestamp_anomalies"]  # noqa: E111
    assert anomalies["manager"] == "stale"  # noqa: E111
    assert diagnostics["last_generated"] is not None  # noqa: E111


@pytest.mark.unit
def test_script_manager_resilience_escalation_definition() -> None:
    """Entry-level resilience escalation script should expose guard thresholds."""  # noqa: E111

    hass = SimpleNamespace(data={})  # noqa: E111
    entry = SimpleNamespace(  # noqa: E111
        entry_id="entry-id",
        data={},
        options={},
        title="Canine Ops",
    )
    script_manager = PawControlScriptManager(hass, entry)  # noqa: E111

    object_id, config = script_manager._build_resilience_escalation_script()  # noqa: E111

    expected_slug = ha_slugify("Canine Ops")  # noqa: E111
    assert object_id == f"pawcontrol_{expected_slug}_resilience_escalation"  # noqa: E111
    assert config[CONF_ALIAS] == "Canine Ops resilience escalation"  # noqa: E111
    assert "guard skips" in config[CONF_DESCRIPTION]  # noqa: E111

    sequence = config[CONF_SEQUENCE]  # noqa: E111
    assert isinstance(sequence, list) and len(sequence) == 2  # noqa: E111
    variables = sequence[0]["variables"]  # noqa: E111
    assert "guard_reason_text" in variables  # noqa: E111
    assert "open_breakers_text" in variables  # noqa: E111

    guard_branch, breaker_branch = sequence[1]["choose"]  # noqa: E111
    guard_service = guard_branch["sequence"][0]["action"]  # noqa: E111
    assert (  # noqa: E111
        guard_service
        == "{{ escalation_service | default('persistent_notification.create') }}"
    )
    guard_followup = guard_branch["sequence"][1]["choose"][0]["sequence"][0]  # noqa: E111
    assert guard_followup["action"] == "script.turn_on"  # noqa: E111
    assert guard_followup["data"]["variables"]["trigger_reason"] == "guard"  # noqa: E111

    breaker_service = breaker_branch["sequence"][0]["action"]  # noqa: E111
    assert (  # noqa: E111
        breaker_service
        == "{{ escalation_service | default('persistent_notification.create') }}"
    )

    fields = config[CONF_FIELDS]  # noqa: E111
    assert fields["skip_threshold"][CONF_DEFAULT] == 3  # noqa: E111
    assert fields["breaker_threshold"][CONF_DEFAULT] == 1  # noqa: E111
    assert (
        fields["statistics_entity_id"][CONF_DEFAULT] == "sensor.pawcontrol_statistics"
    )  # noqa: E111
    guard_message = fields["guard_message"][CONF_DEFAULT]  # noqa: E111
    breaker_message = fields["breaker_message"][CONF_DEFAULT]  # noqa: E111
    assert "{{ guard_reason_text }}" in guard_message  # noqa: E111
    assert "{{ open_breakers_text }}" in breaker_message  # noqa: E111
    assert "entity" in fields["followup_script"]["selector"]  # noqa: E111

    snapshot = script_manager.get_resilience_escalation_snapshot()  # noqa: E111
    assert snapshot is not None  # noqa: E111
    assert snapshot["available"] is True  # noqa: E111
    assert snapshot["state_available"] is False  # noqa: E111
    assert snapshot["thresholds"]["skip_threshold"]["default"] == 3  # noqa: E111
    assert snapshot["thresholds"]["breaker_threshold"]["default"] == 1  # noqa: E111
    manual = snapshot["manual_events"]  # noqa: E111
    assert manual["available"] is False  # noqa: E111
    assert manual["automations"] == []  # noqa: E111
    assert manual["event_history"] == []  # noqa: E111


@pytest.mark.unit
def test_script_manager_resilience_threshold_overrides() -> None:
    """Config entry options should override default resilience thresholds."""  # noqa: E111

    hass = SimpleNamespace(data={})  # noqa: E111
    entry = SimpleNamespace(  # noqa: E111
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

    script_manager = PawControlScriptManager(hass, entry)  # noqa: E111

    _object_id, config = script_manager._build_resilience_escalation_script()  # noqa: E111
    fields = config[CONF_FIELDS]  # noqa: E111
    assert fields["skip_threshold"][CONF_DEFAULT] == 9  # noqa: E111
    assert fields["breaker_threshold"][CONF_DEFAULT] == 4  # noqa: E111

    snapshot = script_manager.get_resilience_escalation_snapshot()  # noqa: E111
    assert snapshot is not None  # noqa: E111
    assert snapshot["thresholds"]["skip_threshold"]["default"] == 9  # noqa: E111
    assert snapshot["thresholds"]["breaker_threshold"]["default"] == 4  # noqa: E111
    manual = snapshot["manual_events"]  # noqa: E111
    assert manual["available"] is False  # noqa: E111
    assert manual["system_guard_event"] is None  # noqa: E111
    assert manual["system_breaker_event"] is None  # noqa: E111
    assert manual["listener_events"] == {}  # noqa: E111
    assert manual["listener_sources"] == {}  # noqa: E111
    assert manual["last_trigger"] is None  # noqa: E111
    assert manual["event_history"] == []  # noqa: E111
    counters = manual["event_counters"]  # noqa: E111
    assert counters["total"] == 0  # noqa: E111
    assert counters["by_event"] == {}  # noqa: E111
    assert counters["by_reason"] == {}  # noqa: E111


@pytest.mark.unit
def test_script_manager_resilience_manual_event_snapshot() -> None:
    """Manual blueprint triggers should be surfaced in diagnostics snapshots."""  # noqa: E111

    hass = SimpleNamespace(  # noqa: E111
        data={},
        states=SimpleNamespace(get=lambda entity_id: None),
        config_entries=SimpleNamespace(
            async_entries=lambda domain: (
                [
                    SimpleNamespace(
                        entry_id="automation-id",
                        title="Resilience follow-up",
                        data={
                            "use_blueprint": {
                                "path": "blueprints/automation/pawcontrol/resilience_escalation_followup.yaml",  # noqa: E501
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
            )
        ),
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={}, title="Ops")  # noqa: E111

    script_manager = PawControlScriptManager(hass, entry)  # noqa: E111
    script_manager._build_resilience_escalation_script()  # noqa: E111

    snapshot = script_manager.get_resilience_escalation_snapshot()  # noqa: E111
    assert snapshot is not None  # noqa: E111
    manual = snapshot["manual_events"]  # noqa: E111
    assert manual["available"] is True  # noqa: E111
    assert manual["configured_guard_events"] == ["pawcontrol_manual_guard"]  # noqa: E111
    assert manual["configured_breaker_events"] == ["pawcontrol_manual_breaker"]  # noqa: E111
    assert manual["configured_check_events"] == ["pawcontrol_resilience_check"]  # noqa: E111
    assert manual["system_guard_event"] is None  # noqa: E111
    assert manual["system_breaker_event"] is None  # noqa: E111
    assert manual["listener_events"]["pawcontrol_manual_guard"] == ["guard"]  # noqa: E111
    assert manual["listener_events"]["pawcontrol_manual_breaker"] == ["breaker"]  # noqa: E111
    assert manual["listener_events"]["pawcontrol_resilience_check"] == ["check"]  # noqa: E111
    assert manual["listener_sources"]["pawcontrol_manual_guard"] == ["blueprint"]  # noqa: E111
    assert manual["listener_sources"]["pawcontrol_manual_breaker"] == ["blueprint"]  # noqa: E111
    assert manual["listener_sources"]["pawcontrol_resilience_check"] == ["blueprint"]  # noqa: E111
    assert manual["last_trigger"] is None  # noqa: E111
    counters = manual["event_counters"]  # noqa: E111
    assert counters["total"] == 0  # noqa: E111
    assert counters["by_event"] == {  # noqa: E111
        "pawcontrol_manual_breaker": 0,
        "pawcontrol_manual_guard": 0,
        "pawcontrol_resilience_check": 0,
    }
    assert counters["by_reason"] == {}  # noqa: E111
    automation_entry = manual["automations"][0]  # noqa: E111
    assert automation_entry["configured_guard"] is True  # noqa: E111
    assert automation_entry["configured_breaker"] is True  # noqa: E111
    assert manual["preferred_guard_event"] == "pawcontrol_manual_guard"  # noqa: E111
    assert manual["preferred_breaker_event"] == "pawcontrol_manual_breaker"  # noqa: E111
    assert manual["preferred_check_event"] == "pawcontrol_resilience_check"  # noqa: E111
    assert manual["preferred_events"] == {  # noqa: E111
        "manual_check_event": "pawcontrol_resilience_check",
        "manual_guard_event": "pawcontrol_manual_guard",
        "manual_breaker_event": "pawcontrol_manual_breaker",
    }
    assert manual["active_listeners"] == [  # noqa: E111
        "pawcontrol_manual_breaker",
        "pawcontrol_manual_guard",
        "pawcontrol_resilience_check",
    ]
    assert manual["last_event"] is None  # noqa: E111
    assert manual["event_history"] == []  # noqa: E111
    listener_metadata = manual["listener_metadata"]  # noqa: E111
    assert listener_metadata["pawcontrol_manual_guard"]["sources"] == [  # noqa: E111
        "blueprint",
        "default",
    ]
    assert listener_metadata["pawcontrol_manual_guard"]["primary_source"] == "blueprint"  # noqa: E111
    assert listener_metadata["pawcontrol_manual_breaker"]["sources"] == [  # noqa: E111
        "blueprint",
        "default",
    ]
    assert (
        listener_metadata["pawcontrol_manual_breaker"]["primary_source"] == "blueprint"
    )  # noqa: E111
    assert listener_metadata["pawcontrol_resilience_check"]["sources"] == [  # noqa: E111
        "blueprint",
        "default",
    ]
    assert (  # noqa: E111
        listener_metadata["pawcontrol_resilience_check"]["primary_source"]
        == "blueprint"
    )


@pytest.mark.unit
def test_script_manager_manual_snapshot_combines_system_and_blueprint_sources() -> None:
    """System settings should appear alongside blueprint suggestions."""  # noqa: E111

    hass = SimpleNamespace(  # noqa: E111
        data={},
        states=SimpleNamespace(get=lambda entity_id: None),
        config_entries=SimpleNamespace(
            async_entries=lambda domain: (
                [
                    SimpleNamespace(
                        entry_id="automation-id",
                        title="Resilience follow-up",
                        data={
                            "use_blueprint": {
                                "path": "blueprints/automation/pawcontrol/resilience_escalation_followup.yaml",  # noqa: E501
                                "input": {
                                    "manual_guard_event": "pawcontrol_manual_guard",
                                },
                            }
                        },
                    )
                ]
                if domain == "automation"
                else []
            )
        ),
    )

    entry = SimpleNamespace(  # noqa: E111
        entry_id="entry-id",
        data={},
        options={"system_settings": {"manual_guard_event": "pawcontrol_manual_guard"}},
        title="Ops",
    )

    script_manager = PawControlScriptManager(hass, entry)  # noqa: E111
    script_manager._build_resilience_escalation_script()  # noqa: E111

    snapshot = script_manager.get_resilience_escalation_snapshot()  # noqa: E111
    assert snapshot is not None  # noqa: E111
    manual = snapshot["manual_events"]  # noqa: E111
    assert manual["listener_sources"]["pawcontrol_manual_guard"] == [  # noqa: E111
        "blueprint",
        "system_options",
    ]
    metadata = manual["listener_metadata"]["pawcontrol_manual_guard"]  # noqa: E111
    assert metadata["sources"] == ["blueprint", "default", "system_settings"]  # noqa: E111
    assert metadata["primary_source"] == "system_settings"  # noqa: E111


@pytest.mark.unit
def test_script_manager_records_manual_event_trigger() -> None:
    """Manual event listeners should capture trigger metadata."""  # noqa: E111

    class DummyBus:  # noqa: E111
        def __init__(self) -> None:
            self.listeners: dict[str, list[ManualEventCallback]] = {}  # noqa: E111

        def async_listen(
            self, event_type: str, callback: ManualEventCallback
        ) -> Callable[[], None]:
            listeners = self.listeners.setdefault(event_type, [])  # noqa: E111
            listeners.append(callback)  # noqa: E111

            def _remove() -> None:  # noqa: E111
                listeners.remove(callback)

            return _remove  # noqa: E111

        def fire(
            self,
            event_type: str,
            *,
            context_id: str = "ctx",
            user_id: str | None = "user",
            origin: str = "LOCAL",
            data: Mapping[str, object] | None = None,
        ) -> None:
            event = SimpleNamespace(  # noqa: E111
                event_type=event_type,
                time_fired=dt_util.utcnow(),
                origin=origin,
                context=SimpleNamespace(id=context_id, user_id=user_id),
                data=data,
            )
            for callback in list(self.listeners.get(event_type, [])):  # noqa: E111
                callback(event)

    bus = DummyBus()  # noqa: E111
    hass = SimpleNamespace(  # noqa: E111
        data={},
        bus=bus,
        states=SimpleNamespace(get=lambda entity_id: None),
        config_entries=SimpleNamespace(async_entries=lambda domain: []),
    )
    entry = SimpleNamespace(  # noqa: E111
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

    script_manager = PawControlScriptManager(hass, entry)  # noqa: E111
    script_manager._build_resilience_escalation_script()  # noqa: E111
    script_manager._refresh_manual_event_listeners()  # noqa: E111

    assert set(script_manager._manual_event_sources) == {  # noqa: E111
        "pawcontrol_manual_guard",
        "pawcontrol_manual_check",
        "pawcontrol_manual_breaker",
    }

    bus.fire(  # noqa: E111
        "pawcontrol_manual_guard",
        context_id="ctx-1",
        user_id="user-1",
        data={"reason": "test"},
    )

    snapshot = script_manager.get_resilience_escalation_snapshot()  # noqa: E111
    assert snapshot is not None  # noqa: E111
    manual = snapshot["manual_events"]  # noqa: E111
    last_event = manual["last_event"]  # noqa: E111
    assert last_event is not None  # noqa: E111
    assert last_event["event_type"] == "pawcontrol_manual_guard"  # noqa: E111
    assert last_event["category"] == "guard"  # noqa: E111
    assert last_event["matched_preference"] == "manual_guard_event"  # noqa: E111
    assert last_event["origin"] == "LOCAL"  # noqa: E111
    assert last_event["context_id"] == "ctx-1"  # noqa: E111
    assert last_event["user_id"] == "user-1"  # noqa: E111
    assert last_event["data"] == {"reason": "test"}  # noqa: E111
    assert last_event["time_fired"] is not None  # noqa: E111
    assert last_event["time_fired_age_seconds"] is not None  # noqa: E111
    assert last_event["sources"] == ["system_settings", "default"]  # noqa: E111
    assert last_event["reasons"] == ["guard"]  # noqa: E111
    assert manual["active_listeners"] == [  # noqa: E111
        "pawcontrol_manual_breaker",
        "pawcontrol_manual_check",
        "pawcontrol_manual_guard",
    ]
    history = manual["event_history"]  # noqa: E111
    assert isinstance(history, list) and history  # noqa: E111
    assert history[0]["event_type"] == "pawcontrol_manual_guard"  # noqa: E111
    assert history[0]["sources"] == ["system_options"]  # noqa: E111


@pytest.mark.asyncio
async def test_script_manager_sync_manual_events_updates_blueprint() -> None:
    """Manual event preferences should update resilience blueprint inputs."""  # noqa: E111

    @dataclass(slots=True)  # noqa: E111
    class _ConfigEntryUpdateRecord:  # noqa: E111
        entry: object
        data: ConfigEntryDataPayload | None
        options: PawControlOptionsData | None

    blueprint_inputs = {  # noqa: E111
        "manual_check_event": "pawcontrol_resilience_check",
        "manual_guard_event": "pawcontrol_manual_guard",
        "manual_breaker_event": "",
    }

    updated_payloads: list[_ConfigEntryUpdateRecord] = []  # noqa: E111

    def _async_update_entry(  # noqa: E111
        entry: object,
        *,
        data: ConfigEntryDataPayload | None = None,
        options: PawControlOptionsData | None = None,
    ) -> None:
        updated_payloads.append(
            _ConfigEntryUpdateRecord(entry=entry, data=data, options=options)
        )

    hass = SimpleNamespace(  # noqa: E111
        data={},
        config_entries=SimpleNamespace(
            async_entries=lambda domain: (
                [
                    SimpleNamespace(
                        entry_id="automation-id",
                        data={
                            "use_blueprint": {
                                "path": "blueprints/automation/pawcontrol/resilience_escalation_followup.yaml",  # noqa: E501
                                "input": dict(blueprint_inputs),
                            }
                        },
                    )
                ]
                if domain == "automation"
                else []
            ),
            async_update_entry=_async_update_entry,
        ),
    )

    entry = SimpleNamespace(entry_id="entry-id", data={}, options={}, title="Ops")  # noqa: E111

    manager = PawControlScriptManager(hass, entry)  # noqa: E111

    await manager.async_sync_manual_resilience_events({  # noqa: E111
        "manual_check_event": " pawcontrol_resilience_check_custom ",
        "manual_guard_event": "  ",
        "manual_breaker_event": "pawcontrol_manual_breaker",
    })

    assert len(updated_payloads) == 1  # noqa: E111
    payload = updated_payloads[0]  # noqa: E111
    assert payload.entry.entry_id == "automation-id"  # noqa: E111
    assert payload.data is not None  # noqa: E111
    blueprint_data = payload.data["use_blueprint"]  # noqa: E111
    assert blueprint_data["path"].endswith("resilience_escalation_followup.yaml")  # noqa: E111
    inputs = blueprint_data["input"]  # noqa: E111
    assert inputs["manual_check_event"] == "pawcontrol_resilience_check_custom"  # noqa: E111
    assert inputs["manual_guard_event"] == ""  # noqa: E111
    assert inputs["manual_breaker_event"] == "pawcontrol_manual_breaker"  # noqa: E111


@pytest.mark.unit
def test_script_manager_manual_event_listener_records_last_trigger() -> None:
    """Manual event listeners should record the latest trigger metadata."""  # noqa: E111

    class DummyBus:  # noqa: E111
        def __init__(self) -> None:
            self.listeners: dict[str, Callable[[Event], None]] = {}  # noqa: E111

        def async_listen(
            self, event_type: str, callback: Callable[[Event], None]
        ) -> Callable[[], None]:
            self.listeners[event_type] = callback  # noqa: E111

            def _unsub() -> None:  # noqa: E111
                self.listeners.pop(event_type, None)

            return _unsub  # noqa: E111

    bus = DummyBus()  # noqa: E111
    hass = SimpleNamespace(  # noqa: E111
        data={},
        states=SimpleNamespace(get=lambda entity_id: None),
        config_entries=SimpleNamespace(async_entries=lambda domain: []),
        bus=bus,
    )
    entry = SimpleNamespace(  # noqa: E111
        entry_id="entry-id",
        data={},
        options={"system_settings": {"manual_guard_event": "pawcontrol_manual_guard"}},
        title="Ops",
    )

    script_manager = PawControlScriptManager(hass, entry)  # noqa: E111
    asyncio.run(script_manager.async_initialize())  # noqa: E111
    script_manager._build_resilience_escalation_script()  # noqa: E111

    assert "pawcontrol_manual_guard" in bus.listeners  # noqa: E111

    bus.listeners["pawcontrol_manual_guard"](Event("pawcontrol_manual_guard", {}))  # noqa: E111

    snapshot = script_manager.get_resilience_escalation_snapshot()  # noqa: E111
    assert snapshot is not None  # noqa: E111
    manual = snapshot["manual_events"]  # noqa: E111
    last_trigger = manual["last_trigger"]  # noqa: E111
    assert last_trigger is not None  # noqa: E111
    assert last_trigger["event_type"] == "pawcontrol_manual_guard"  # noqa: E111
    assert last_trigger["matched_preference"] == "manual_guard_event"  # noqa: E111
    assert last_trigger["category"] == "guard"  # noqa: E111
    assert last_trigger["sources"] == ["system_options"]  # noqa: E111
    assert last_trigger["reasons"] == ["guard"]  # noqa: E111
    assert last_trigger["sources"] == ["system_settings", "default"]  # noqa: E111
    assert manual["listener_sources"]["pawcontrol_manual_guard"] == ["system_options"]  # noqa: E111
    listener_metadata = manual["listener_metadata"]["pawcontrol_manual_guard"]  # noqa: E111
    assert listener_metadata["sources"] == ["default", "system_settings"]  # noqa: E111
    assert listener_metadata["primary_source"] == "system_settings"  # noqa: E111
    assert isinstance(last_trigger["recorded_age_seconds"], int)  # noqa: E111
    history = manual["event_history"]  # noqa: E111
    assert isinstance(history, list) and history  # noqa: E111
    assert history[0]["event_type"] == "pawcontrol_manual_guard"  # noqa: E111
    counters = manual["event_counters"]  # noqa: E111
    assert counters["total"] == 1  # noqa: E111
    assert counters["by_event"] == {"pawcontrol_manual_guard": 1}  # noqa: E111
    assert counters["by_reason"] == {"guard": 1}  # noqa: E111


@pytest.mark.unit
def test_script_manager_manual_history_size_respects_options() -> None:
    """Manual event history length should be configurable via options."""  # noqa: E111

    hass = SimpleNamespace(  # noqa: E111
        data={},
        states=SimpleNamespace(get=lambda entity_id: None),
        config_entries=SimpleNamespace(async_entries=lambda domain: []),
    )
    entry = SimpleNamespace(  # noqa: E111
        entry_id="entry-id",
        data={},
        options={"system_settings": {"manual_event_history_size": 7}},
        title="Ops",
    )

    manager = PawControlScriptManager(hass, entry)  # noqa: E111
    assert manager._manual_event_history.maxlen == 7  # noqa: E111

    async def _record_events() -> None:  # noqa: E111
        await manager.async_initialize()
        event = Event("pawcontrol_manual_guard", {})
        for _ in range(9):
            manager._handle_manual_event(event)  # noqa: E111

    asyncio.run(_record_events())  # noqa: E111

    assert len(manager._manual_event_history) == 7  # noqa: E111

    entry.options["system_settings"]["manual_event_history_size"] = 3  # noqa: E111
    asyncio.run(manager.async_initialize())  # noqa: E111
    assert manager._manual_event_history.maxlen == 3  # noqa: E111
    assert len(manager._manual_event_history) <= 3  # noqa: E111


@pytest.mark.unit
def test_resilience_followup_blueprint_manual_events() -> None:
    """Manual blueprint triggers should drive escalation and follow-up paths."""  # noqa: E111

    blueprint_path = Path(  # noqa: E111
        "blueprints/automation/pawcontrol/resilience_escalation_followup.yaml"
    )
    blueprint_source = blueprint_path.read_text(encoding="utf-8")  # noqa: E111

    assert "id: manual_guard_event" in blueprint_source  # noqa: E111
    assert "id: manual_breaker_event" in blueprint_source  # noqa: E111
    assert "trigger.id in valid_trigger_ids" in blueprint_source  # noqa: E111
    assert "trigger.id in guard_trigger_ids" in blueprint_source  # noqa: E111
    assert "trigger.id in breaker_trigger_ids" in blueprint_source  # noqa: E111
    assert "- manual_event" in blueprint_source  # noqa: E111
    assert "- manual_guard_event" in blueprint_source  # noqa: E111
    assert "- manual_breaker_event" in blueprint_source  # noqa: E111


@pytest.mark.unit
def test_door_sensor_manager_register_cache_monitor() -> None:
    """Door sensor manager should publish detection diagnostics."""  # noqa: E111

    hass = SimpleNamespace()  # noqa: E111
    manager = DoorSensorManager(hass, "entry")  # noqa: E111
    now = dt_util.utcnow()  # noqa: E111
    manager._sensor_configs = {  # noqa: E111
        "buddy": DoorSensorConfig(
            entity_id="binary_sensor.front_door",
            dog_id="buddy",
            dog_name="Buddy",
        )
    }
    manager._detection_states = {  # noqa: E111
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
    manager._detection_stats = {  # noqa: E111
        "total_detections": 3,
        "successful_walks": 2,
        "false_positives": 1,
        "false_negatives": 0,
        "average_confidence": 0.72,
    }

    registrar = _RecordingRegistrar()  # noqa: E111
    manager.register_cache_monitors(registrar, prefix="door_sensor")  # noqa: E111

    assert "door_sensor_cache" in registrar.monitors  # noqa: E111
    snapshot = registrar.monitors["door_sensor_cache"].coordinator_snapshot()  # noqa: E111
    stats = snapshot["stats"]  # noqa: E111
    assert stats["configured_sensors"] == 1  # noqa: E111
    assert stats["active_detections"] == 1  # noqa: E111
    diagnostics = snapshot["diagnostics"]  # noqa: E111
    assert diagnostics["per_dog"]["buddy"]["entity_id"] == "binary_sensor.front_door"  # noqa: E111
    assert diagnostics["detection_stats"]["successful_walks"] == 2  # noqa: E111
    assert diagnostics["cleanup_task_active"] is False  # noqa: E111


@pytest.mark.unit
def test_door_sensor_manager_timestamp_anomaly() -> None:
    """Door sensor diagnostics should surface stale activity timestamps."""  # noqa: E111

    hass = SimpleNamespace()  # noqa: E111
    manager = DoorSensorManager(hass, "entry")  # noqa: E111
    old = dt_util.utcnow() - (CACHE_TIMESTAMP_STALE_THRESHOLD + timedelta(hours=2))  # noqa: E111
    manager._sensor_configs = {  # noqa: E111
        "buddy": DoorSensorConfig(
            entity_id="binary_sensor.front_door",
            dog_id="buddy",
            dog_name="Buddy",
        )
    }
    manager._detection_states = {  # noqa: E111
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
    manager._detection_stats = {  # noqa: E111
        "total_detections": 1,
        "successful_walks": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "average_confidence": 0.42,
    }
    manager._last_activity = old  # noqa: E111

    registrar = _RecordingRegistrar()  # noqa: E111
    manager.register_cache_monitors(registrar, prefix="door_sensor")  # noqa: E111

    snapshot = registrar.monitors["door_sensor_cache"].coordinator_snapshot()  # noqa: E111
    diagnostics = snapshot["diagnostics"]  # noqa: E111
    anomalies = diagnostics["timestamp_anomalies"]  # noqa: E111
    assert anomalies["manager"] == "stale"  # noqa: E111
    assert anomalies["buddy"] == "stale"  # noqa: E111


@pytest.mark.unit
def test_auto_registers_helper_manager_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Data manager should register helper manager caches when available."""  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    entry = SimpleNamespace(entry_id="entry", data={}, options={})  # noqa: E111
    helper_manager = PawControlHelperManager(hass, entry)  # noqa: E111
    helper_manager._created_helpers.add("input_boolean.pawcontrol_helper_created")  # noqa: E111
    script_manager = PawControlScriptManager(SimpleNamespace(data={}), entry)  # noqa: E111
    script_manager._created_entities.add("script.pawcontrol_helper_created")  # noqa: E111
    door_manager = DoorSensorManager(SimpleNamespace(), "entry")  # noqa: E111
    assert callable(door_manager.register_cache_monitors)  # noqa: E111

    modules = _DummyModules()  # noqa: E111
    tracker = _DummyTracker()  # noqa: E111
    coordinator = SimpleNamespace(  # noqa: E111
        hass=hass,
        config_entry=SimpleNamespace(entry_id="entry"),
        _modules=modules,
        _entity_budget=tracker,
    )
    coordinator.helper_manager = helper_manager  # noqa: E111
    coordinator.script_manager = script_manager  # noqa: E111
    coordinator.door_sensor_manager = door_manager  # noqa: E111

    manager = PawControlDataManager(  # noqa: E111
        hass=hass,
        coordinator=coordinator,
        dogs_config=[],
    )

    script_manager.register_cache_monitors(manager, prefix="script_manager")  # noqa: E111
    door_manager.register_cache_monitors(manager, prefix="door_sensor")  # noqa: E111

    snapshots = manager.cache_snapshots()  # noqa: E111
    assert "helper_manager_cache" in snapshots  # noqa: E111
    assert "script_manager_cache" in snapshots  # noqa: E111
    assert "door_sensor_cache" in snapshots  # noqa: E111


@pytest.mark.unit
def test_register_runtime_cache_monitors_adds_helper_cache(tmp_path: Path) -> None:
    """Runtime cache registration should pick up helper manager monitors."""  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    entry = SimpleNamespace(entry_id="entry", data={}, options={})  # noqa: E111
    helper_manager = PawControlHelperManager(hass, entry)  # noqa: E111

    manager = PawControlDataManager(  # noqa: E111
        hass=hass,
        entry_id="entry",
        dogs_config=[],
    )

    assert "helper_manager_cache" not in manager.cache_snapshots()  # noqa: E111

    runtime = SimpleNamespace(  # noqa: E111
        notification_manager=None,
        person_manager=None,
        helper_manager=helper_manager,
    )

    manager.register_runtime_cache_monitors(runtime)  # noqa: E111
    snapshots = manager.cache_snapshots()  # noqa: E111

    assert "helper_manager_cache" in snapshots  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_get_module_history_respects_limit(tmp_path: Path) -> None:
    """Module history lookups should return sorted entries with optional limits."""  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    manager = PawControlDataManager(  # noqa: E111
        hass=hass,
        entry_id="history-test",
        dogs_config=[{"dog_id": "buddy", "modules": {MODULE_HEALTH: True}}],
    )

    await manager.async_initialize()  # noqa: E111

    earlier = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)  # noqa: E111
    later = datetime(2024, 1, 2, 8, 30, tzinfo=UTC)  # noqa: E111

    await manager.async_log_health_data(  # noqa: E111
        "buddy",
        {"timestamp": earlier, "weight": 12.5, "health_status": "good"},
    )
    await manager.async_log_health_data(  # noqa: E111
        "buddy",
        {"timestamp": later, "weight": 11.8, "health_status": "excellent"},
    )

    entries = await manager.async_get_module_history(MODULE_HEALTH, "buddy")  # noqa: E111
    assert len(entries) == 2  # noqa: E111
    assert entries[0]["weight"] == 11.8  # noqa: E111
    assert entries[1]["weight"] == 12.5  # noqa: E111
    assert entries[0]["timestamp"] > entries[1]["timestamp"]  # noqa: E111

    limited = await manager.async_get_module_history(MODULE_HEALTH, "buddy", limit=1)  # noqa: E111
    assert limited == entries[:1]  # noqa: E111

    recent_only = await manager.async_get_module_history(  # noqa: E111
        MODULE_HEALTH, "buddy", since=later - timedelta(hours=1)
    )
    assert len(recent_only) == 1  # noqa: E111
    assert recent_only[0]["weight"] == 11.8  # noqa: E111

    older_only = await manager.async_get_module_history(  # noqa: E111
        MODULE_HEALTH, "buddy", until=earlier + timedelta(minutes=1)
    )
    assert len(older_only) == 1  # noqa: E111
    assert older_only[0]["weight"] == 12.5  # noqa: E111

    assert await manager.async_get_module_history("unknown", "buddy") == []  # noqa: E111
    assert await manager.async_get_module_history(MODULE_HEALTH, "unknown") == []  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_weekly_health_report_filters_old_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Weekly health reports should ignore entries outside the seven-day window."""  # noqa: E111

    from custom_components.pawcontrol import data_manager as dm  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    manager = PawControlDataManager(  # noqa: E111
        hass=hass,
        entry_id="weekly-health",
        dogs_config=[{"dog_id": "buddy", "modules": {MODULE_HEALTH: True}}],
    )

    base_time = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)  # noqa: E111
    monkeypatch.setattr(dm, "_utcnow", lambda: base_time)  # noqa: E111

    await manager.async_initialize()  # noqa: E111

    older = base_time - timedelta(days=12)  # noqa: E111
    recent = base_time - timedelta(days=2)  # noqa: E111

    await manager.async_log_health_data(  # noqa: E111
        "buddy",
        {
            "timestamp": older,
            "weight": 12.0,
            "temperature": 38.0,
            "health_status": "ok",
        },
    )
    await manager.async_log_health_data(  # noqa: E111
        "buddy",
        {
            "timestamp": recent,
            "weight": 11.5,
            "temperature": 37.8,
            "health_status": "excellent",
        },
    )

    await manager.async_log_medication(  # noqa: E111
        "buddy",
        {"medication_name": "pain-relief", "dose": "5ml", "administration_time": older},
    )
    await manager.async_log_medication(  # noqa: E111
        "buddy",
        {
            "medication_name": "vitamin",
            "dose": "2ml",
            "administration_time": recent,
        },
    )

    report = await manager.async_generate_weekly_health_report("buddy")  # noqa: E111

    assert report["entries"] == 1  # noqa: E111
    assert report["recent_weights"] == [11.5]  # noqa: E111
    assert report["recent_temperatures"] == [37.8]  # noqa: E111
    assert report["medication"]["entries"] == 1  # noqa: E111
    assert report["medication"]["latest"]["medication_name"] == "vitamin"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analyze_patterns_uses_filtered_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pattern analysis should rely on the shared history helpers."""  # noqa: E111

    from custom_components.pawcontrol import data_manager as dm  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    manager = PawControlDataManager(  # noqa: E111
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

    current_time = datetime(2024, 2, 1, 8, 0, tzinfo=UTC)  # noqa: E111

    def _now() -> datetime:  # noqa: E111
        return current_time

    monkeypatch.setattr(dm, "_utcnow", _now)  # noqa: E111

    await manager.async_initialize()  # noqa: E111

    older_feed = current_time - timedelta(days=10)  # noqa: E111
    recent_feed = current_time - timedelta(days=3)  # noqa: E111

    await manager.async_log_feeding(  # noqa: E111
        "buddy",
        FeedingData(
            meal_type="breakfast",
            portion_size=120.0,
            food_type="dry_food",
            timestamp=older_feed,
        ),
    )
    await manager.async_log_feeding(  # noqa: E111
        "buddy",
        FeedingData(
            meal_type="dinner",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=recent_feed,
        ),
    )

    older_health = current_time - timedelta(days=9)  # noqa: E111
    recent_health = current_time - timedelta(days=2)  # noqa: E111

    await manager.async_log_health_data(  # noqa: E111
        "buddy", {"timestamp": older_health, "weight": 12.3, "health_status": "ok"}
    )
    await manager.async_log_health_data(  # noqa: E111
        "buddy",
        {"timestamp": recent_health, "weight": 11.9, "health_status": "great"},
    )

    older_walk_start = current_time - timedelta(days=8, hours=1)  # noqa: E111
    older_walk_end = current_time - timedelta(days=8)  # noqa: E111
    recent_walk_start = current_time - timedelta(days=1, hours=2)  # noqa: E111
    recent_walk_end = current_time - timedelta(days=1, hours=1, minutes=30)  # noqa: E111

    current_time = older_walk_start  # noqa: E111
    await manager.async_start_walk("buddy")  # noqa: E111
    current_time = older_walk_end  # noqa: E111
    await manager.async_end_walk("buddy", distance=2.5, rating=4)  # noqa: E111

    current_time = recent_walk_start  # noqa: E111
    await manager.async_start_walk("buddy")  # noqa: E111
    current_time = recent_walk_end  # noqa: E111
    await manager.async_end_walk("buddy", distance=3.2, rating=5)  # noqa: E111

    current_time = datetime(2024, 2, 1, 18, 0, tzinfo=UTC)  # noqa: E111

    result = await manager.async_analyze_patterns("buddy", "comprehensive", days=7)  # noqa: E111

    feeding = result["feeding"]  # noqa: E111
    assert feeding["entries"] == 1  # noqa: E111
    assert feeding["total_portion_size"] == 200.0  # noqa: E111
    assert feeding["first_entry"]["portion_size"] == 200.0  # noqa: E111
    assert feeding["last_entry"]["portion_size"] == 200.0  # noqa: E111

    walking = result["walking"]  # noqa: E111
    assert walking["entries"] == 1  # noqa: E111
    assert walking["total_distance"] == 3.2  # noqa: E111

    health = result["health"]  # noqa: E111
    assert health["entries"] == 1  # noqa: E111
    assert health["latest"]["weight"] == 11.9  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_data_uses_history_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exports should reuse history filters and maintain chronological ordering."""  # noqa: E111

    from custom_components.pawcontrol import data_manager as dm  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    manager = PawControlDataManager(  # noqa: E111
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

    base_time = datetime(2024, 3, 15, 12, 0, tzinfo=UTC)  # noqa: E111

    def _now() -> datetime:  # noqa: E111
        return base_time

    monkeypatch.setattr(dm, "_utcnow", _now)  # noqa: E111

    await manager.async_initialize()  # noqa: E111

    older_feed = base_time - timedelta(days=5)  # noqa: E111
    first_recent_feed = base_time - timedelta(days=1, hours=3)  # noqa: E111
    second_recent_feed = base_time - timedelta(hours=4)  # noqa: E111

    await manager.async_log_feeding(  # noqa: E111
        "buddy",
        FeedingData(
            meal_type="breakfast",
            portion_size=110.0,
            food_type="dry_food",
            timestamp=older_feed,
        ),
    )
    await manager.async_log_feeding(  # noqa: E111
        "buddy",
        FeedingData(
            meal_type="lunch",
            portion_size=150.0,
            food_type="wet_food",
            timestamp=first_recent_feed,
        ),
    )
    await manager.async_log_feeding(  # noqa: E111
        "buddy",
        FeedingData(
            meal_type="dinner",
            portion_size=90.0,
            food_type="dry_food",
            timestamp=second_recent_feed,
        ),
    )

    older_medication = base_time - timedelta(days=4)  # noqa: E111
    recent_medication = base_time - timedelta(hours=6)  # noqa: E111

    await manager.async_log_medication(  # noqa: E111
        "buddy",
        {
            "medication_name": "pain-relief",
            "dose": "5ml",
            "administration_time": older_medication,
        },
    )
    await manager.async_log_medication(  # noqa: E111
        "buddy",
        {
            "medication_name": "vitamin",
            "dose": "2ml",
            "administration_time": recent_medication,
        },
    )

    feeding_export = await manager.async_export_data(  # noqa: E111
        "buddy", "feeding", format="json", days=2
    )
    feeding_payload = json.loads(feeding_export.read_text(encoding="utf-8"))  # noqa: E111
    assert feeding_payload["data_type"] == "feeding"  # noqa: E111
    feeding_entries = feeding_payload["entries"]  # noqa: E111
    assert len(feeding_entries) == 2  # noqa: E111
    feeding_timestamps = [entry["timestamp"] for entry in feeding_entries]  # noqa: E111
    assert feeding_timestamps == [  # noqa: E111
        first_recent_feed.isoformat(),
        second_recent_feed.isoformat(),
    ]

    medication_export = await manager.async_export_data(  # noqa: E111
        "buddy",
        "medication",
        format="json",
        date_from=(base_time - timedelta(days=1, hours=1)).isoformat(),
        date_to=(base_time - timedelta(minutes=30)).isoformat(),
    )
    medication_payload = json.loads(medication_export.read_text(encoding="utf-8"))  # noqa: E111
    medication_entries = medication_payload["entries"]  # noqa: E111
    assert len(medication_entries) == 1  # noqa: E111
    medication_entry = medication_entries[0]  # noqa: E111
    assert medication_entry["medication_name"] == "vitamin"  # noqa: E111
    assert medication_entry["administration_time"] == recent_medication.isoformat()  # noqa: E111
    assert medication_entry["logged_at"] == base_time.isoformat()  # noqa: E111


class _StaticCache:
    """Return a static coordinator snapshot for diagnostics registration tests."""  # noqa: E111

    def __init__(self, marker: str) -> None:  # noqa: E111
        self._marker = marker

    def coordinator_snapshot(self) -> JSONMutableMapping:  # noqa: E111
        return cast(
            JSONMutableMapping,
            {
                "stats": {"marker": self._marker},
                "diagnostics": {"marker": self._marker},
            },
        )


class _DummyNotificationManager:
    """Expose cache registration hooks for coordinator wiring tests."""  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        self.person_manager = _DummyPersonManager()

    def register_cache_monitors(self, registrar: CacheMonitorRegistrar) -> None:  # noqa: E111
        registrar.register_cache_monitor("notification_cache", _StaticCache("notif"))
        self.person_manager.register_cache_monitors(registrar, prefix="person_entity")


class _DummyPersonManager:
    """Expose a registrar hook compatible with PersonEntityManager."""  # noqa: E111

    def register_cache_monitors(  # noqa: E111
        self, registrar: CacheMonitorRegistrar, *, prefix: str
    ) -> None:
        registrar.register_cache_monitor(f"{prefix}_targets", _StaticCache("person"))


class _DummyCoordinator:
    """Coordinator stub implementing the binding protocol for tests."""  # noqa: E111

    def __init__(self, hass: HomeAssistant) -> None:  # noqa: E111
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
    """Adapter stub satisfying the module binding protocol."""  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        self.attached = False
        self.detached = False

    def attach_managers(  # noqa: E111
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

    def detach_managers(self) -> None:  # noqa: E111
        self.detached = True


@pytest.mark.unit
def test_notification_person_caches_register_via_binding(tmp_path: Path) -> None:
    """Coordinator binding should surface notification and person cache snapshots."""  # noqa: E111

    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))  # noqa: E111
    coordinator = _DummyCoordinator(hass)  # noqa: E111
    modules = _DummyModulesAdapter()  # noqa: E111
    manager = PawControlDataManager(  # noqa: E111
        hass=hass,
        coordinator=coordinator,
        dogs_config=[],
    )
    notification_manager = _DummyNotificationManager()  # noqa: E111

    bind_runtime_managers(  # noqa: E111
        coordinator,
        modules,
        CoordinatorRuntimeManagers(
            data_manager=manager,
            notification_manager=notification_manager,
        ),
    )

    snapshots = manager.cache_snapshots()  # noqa: E111

    assert "notification_cache" in snapshots  # noqa: E111
    assert snapshots["notification_cache"]["stats"]["marker"] == "notif"  # noqa: E111
    assert "person_entity_targets" in snapshots  # noqa: E111
    assert snapshots["person_entity_targets"]["stats"]["marker"] == "person"  # noqa: E111
