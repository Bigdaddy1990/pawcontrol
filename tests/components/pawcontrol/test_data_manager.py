from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol import data_manager
from custom_components.pawcontrol.const import CACHE_TIMESTAMP_STALE_THRESHOLD
from custom_components.pawcontrol.data_manager import (
    AdaptiveCache,
    DogProfile,
    PawControlDataManager,
    _coerce_health_payload,
    _coerce_mapping,
    _coerce_medication_payload,
    _CoordinatorModuleCacheMonitor,
    _default_session_id_generator,
    _deserialize_datetime,
    _EntityBudgetMonitor,
    _estimate_namespace_entries,
    _find_namespace_timestamp,
    _history_sort_key,
    _limit_entries,
    _merge_dicts,
    _namespace_has_timestamp_field,
    _normalise_history_entries,
    _serialize_datetime,
    _serialize_timestamp,
    _StorageNamespaceCacheMonitor,
)
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    DailyStats,
    HealthData,
    WalkData,
)


@dataclass
class _BudgetSnapshot:
    dog_id: str
    profile: str
    requested_entities: tuple[str, ...]
    denied_requests: tuple[str, ...]
    recorded_at: datetime | str | None
    capacity: float
    base_allocation: float
    dynamic_allocation: float


class _BudgetTracker:
    def snapshots(self) -> list[_BudgetSnapshot]:
        return [
            _BudgetSnapshot(
                dog_id="buddy",
                profile="default",
                requested_entities=("sensor.a",),
                denied_requests=("sensor.b",),
                recorded_at=datetime(2025, 1, 1, tzinfo=UTC),
                capacity=10,
                base_allocation=5,
                dynamic_allocation=2,
            ),
        ]

    def summary(self) -> dict[str, int]:
        return {"tracked": 1}

    def saturation(self) -> float:
        return 0.5


@pytest.mark.asyncio
async def test_adaptive_cache_cleanup_and_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(data_manager, "_utcnow", lambda: now)

    cache = AdaptiveCache[int](default_ttl=10)
    await cache.set("a", 1, base_ttl=20)
    await cache.set("b", 2, base_ttl=1)

    monkeypatch.setattr(data_manager, "_utcnow", lambda: now + timedelta(seconds=2))
    expired = await cache.cleanup_expired(ttl_seconds=1)

    assert expired == 2
    assert cache.get_stats()["size"] == 0
    diagnostics = cache.get_diagnostics()
    assert diagnostics["expired_entries"] == 2
    assert diagnostics["expired_via_override"] == 1


@pytest.mark.asyncio
async def test_adaptive_cache_get_handles_future_created_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(data_manager, "_utcnow", lambda: now)

    cache = AdaptiveCache[str](default_ttl=10)
    cache._data["future"] = "value"
    cache._metadata["future"] = {
        "created_at": now + timedelta(hours=1),
        "ttl": 10,
        "override_applied": False,
    }

    value, hit = await cache.get("future")

    assert hit is True
    assert value == "value"
    assert cache._metadata["future"]["created_at"] == now


def test_entity_budget_monitor_payload() -> None:
    monitor = _EntityBudgetMonitor(_BudgetTracker())

    snapshot = monitor.coordinator_snapshot()

    assert snapshot["stats"]["tracked_dogs"] == 1
    diagnostics = snapshot["diagnostics"]
    assert diagnostics["summary"] == {"tracked": 1}
    assert diagnostics["snapshots"][0]["recorded_at"] == "2025-01-01T00:00:00+00:00"


def test_coordinator_module_cache_monitor_snapshots_and_errors() -> None:
    class _AdapterWithSnapshot:
        def cache_snapshot(self) -> dict[str, int]:
            return {"entries": 2}

    class _AdapterWithMetrics:
        def cache_metrics(self) -> SimpleNamespace:
            return SimpleNamespace(entries=3, hits=2, misses=1, hit_rate=66.666)

    class _AdapterWithFailure:
        def cache_snapshot(self) -> dict[str, int]:
            raise RuntimeError("boom")

    class _Modules:
        feeding = _AdapterWithSnapshot()
        walk = _AdapterWithMetrics()
        health = _AdapterWithFailure()

        def cache_metrics(self) -> SimpleNamespace:
            return SimpleNamespace(entries=9, hits=8, misses=1, hit_rate=88.889)

    monitor = _CoordinatorModuleCacheMonitor(_Modules())

    snapshot = monitor.coordinator_snapshot()

    assert snapshot["stats"]["entries"] == 9
    per_module = snapshot["diagnostics"]["per_module"]
    assert per_module["feeding"] == {"entries": 2}
    assert per_module["walk"]["hit_rate"] == 66.67
    assert per_module["health"] == {"error": "boom"}


def test_storage_namespace_cache_monitor_timestamp_anomalies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2025, 1, 10, tzinfo=UTC)
    monkeypatch.setattr(data_manager, "_utcnow", lambda: now)

    stale = (now - CACHE_TIMESTAMP_STALE_THRESHOLD - timedelta(seconds=1)).isoformat()
    manager = SimpleNamespace(
        _namespace_state={
            "test": {
                "dog-stale": {"timestamp": stale},
                "dog-missing": {"timestamp": None, "nested": {"recorded_at": None}},
                "dog-future": {
                    "timestamp": (now + timedelta(days=1)).isoformat(),
                },
            },
        },
        _namespace_path=lambda namespace: Path(f"/tmp/{namespace}.json"),
    )
    monitor = _StorageNamespaceCacheMonitor(manager, "test", "Test")

    diagnostics = monitor.get_diagnostics()

    anomalies = diagnostics["timestamp_anomalies"]
    assert anomalies["dog-stale"] == "stale"
    assert anomalies["dog-missing"] == "missing"
    assert anomalies["dog-future"] == "future"


def test_namespace_helper_functions() -> None:
    payload = {"a": [1, 2], "b": {"updated_at": "2025-01-01T00:00:00+00:00"}}

    assert _estimate_namespace_entries(payload) == 3
    assert _find_namespace_timestamp(payload) == "2025-01-01T00:00:00+00:00"
    assert _namespace_has_timestamp_field(payload) is True
    assert _namespace_has_timestamp_field({"k": [{"n": 1}]}) is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (datetime(2025, 1, 1, tzinfo=UTC), "2025-01-01T00:00:00+00:00"),
    ],
)
def test_datetime_serialization_helpers(
    value: datetime | None,
    expected: str | None,
) -> None:
    assert _serialize_datetime(value) == expected
    if expected is not None:
        assert _deserialize_datetime(expected) == value


def test_serialize_timestamp_falls_back_to_utcnow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(data_manager, "_utcnow", lambda: now)

    assert _serialize_timestamp(None) == now.isoformat()


def test_mapping_and_list_helpers() -> None:
    merged = _merge_dicts({"a": {"x": 1}, "b": 1}, {"a": {"y": 2}, "c": 3})

    assert merged == {"a": {"x": 1, "y": 2}, "b": 1, "c": 3}
    assert _coerce_mapping(None) == {}
    assert _limit_entries([{"a": 1}, {"b": 2}, {"c": 3}], limit=2) == [
        {"b": 2},
        {"c": 3},
    ]
    assert _normalise_history_entries([{"x": 1}, "bad", b"raw"]) == [{"x": 1}]


def test_payload_coercion_helpers() -> None:
    health_data = HealthData(timestamp=datetime(2025, 1, 1, tzinfo=UTC), mood="normal")
    health_payload = _coerce_health_payload(health_data)
    medication_payload = _coerce_medication_payload({"name": "pill"})

    assert health_payload["timestamp"] == "2025-01-01T00:00:00+00:00"
    assert medication_payload["name"] == "pill"
    assert "administration_time" in medication_payload
    assert "logged_at" in medication_payload


def test_dog_profile_serialization_round_trip() -> None:
    config = {DOG_ID_FIELD: "dog_1", DOG_NAME_FIELD: "Buddy"}
    stored = {
        "daily_stats": {"feedings_count": 2},
        "feeding_history": [{"timestamp": "2025-01-01T00:00:00+00:00", "amount": 120}],
    }
    profile = DogProfile.from_storage(config, stored)
    profile.current_walk = WalkData(start_time=datetime(2025, 1, 1, tzinfo=UTC))

    data = profile.as_dict()

    assert isinstance(profile.daily_stats, DailyStats)
    assert data["config"][DOG_NAME_FIELD] == "Buddy"
    assert data["feeding_history"][0]["amount"] == 120
    assert data["current_walk"]["start_time"] == "2025-01-01T00:00:00+00:00"


def test_misc_helpers() -> None:
    session_a = _default_session_id_generator()
    session_b = _default_session_id_generator()

    assert session_a != session_b
    assert len(session_a) == 32
    assert _history_sort_key({"timestamp": "2025-01-01"}, "timestamp") == "2025-01-01"
    assert _history_sort_key({"timestamp": 123}, "timestamp") == ""


@pytest.mark.asyncio
async def test_adaptive_cache_diagnostics_and_snapshot_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(data_manager, "_utcnow", lambda: now)
    cache = AdaptiveCache[str](default_ttl=5)
    await cache.set("alive", "ok", base_ttl=0)

    value, hit = await cache.get("alive")
    miss_value, miss_hit = await cache.get("missing")

    assert value == "ok"
    assert hit is True
    assert miss_value is None
    assert miss_hit is False
    assert cache.get_stats() == {
        "size": 1,
        "hits": 1,
        "misses": 1,
        "hit_rate": 50.0,
        "memory_mb": 0.0,
    }
    diagnostics = cache.get_diagnostics()
    assert diagnostics["last_cleanup"] is None
    assert diagnostics["active_override_entries"] == 0
    assert diagnostics["tracked_entries"] == 1
    snapshot = cache.coordinator_snapshot()
    assert snapshot["stats"]["size"] == 1
    assert snapshot["diagnostics"]["tracked_entries"] == 1


def test_entity_budget_monitor_handles_tracker_failures() -> None:
    class _FailingTracker:
        def snapshots(self) -> list[_BudgetSnapshot]:
            raise RuntimeError("snapshot error")

        def saturation(self) -> float:
            raise RuntimeError("saturation error")

    monitor = _EntityBudgetMonitor(_FailingTracker())

    assert monitor.get_stats() == {"tracked_dogs": 0, "saturation_percent": 0.0}
    assert monitor.get_diagnostics()["summary"] == {"error": "snapshot error"}


def test_coordinator_module_cache_monitor_collects_aggregate_errors() -> None:
    class _BrokenModules:
        feeding = object()

        def cache_metrics(self) -> SimpleNamespace:
            raise RuntimeError("aggregate boom")

    monitor = _CoordinatorModuleCacheMonitor(_BrokenModules())

    assert monitor.get_stats() == {
        "entries": 0,
        "hits": 0,
        "misses": 0,
        "hit_rate": 0.0,
    }
    diagnostics = monitor.get_diagnostics()
    assert diagnostics["per_module"] == {}
    assert diagnostics["errors"] == ["aggregate boom"]


def test_storage_namespace_cache_monitor_snapshot_with_unparseable_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2025, 1, 10, tzinfo=UTC)
    monkeypatch.setattr(data_manager, "_utcnow", lambda: now)
    manager = SimpleNamespace(
        _namespace_state={
            "test": {
                "dog-unparseable": {"timestamp": "not-a-date"},
            },
        },
        _namespace_path=lambda namespace: Path(f"/tmp/{namespace}.json"),
    )
    monitor = _StorageNamespaceCacheMonitor(manager, "test", "Test")

    payload = monitor.coordinator_snapshot()

    assert payload["snapshot"]["per_dog"]["dog-unparseable"]["entries"] == 1
    assert (
        payload["diagnostics"]["timestamp_anomalies"]["dog-unparseable"]
        == "unparseable"
    )


async def _init_data_manager_for_export_tests(
    mock_hass: object,
    tmp_path: Path,
) -> PawControlDataManager:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-1",
        dogs_config=[{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
    )
    manager._async_load_storage = AsyncMock(return_value={})  # type: ignore[method-assign]
    manager._write_storage = AsyncMock()  # type: ignore[method-assign]
    await manager.async_initialize()
    return manager


@pytest.mark.asyncio
async def test_async_export_data_routes_json_falls_back_for_invalid_json_content(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)
    runtime_data = SimpleNamespace(
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(
                return_value={
                    "filename": "routes.json",
                    "content": "{invalid json",
                },
            ),
        ),
    )
    manager._get_runtime_data = lambda: runtime_data  # type: ignore[method-assign]

    export_path = await manager.async_export_data("buddy", "routes", format="json")
    exported_payload = json.loads(export_path.read_text(encoding="utf-8"))

    assert exported_payload == {"raw_content": "{invalid json"}


@pytest.mark.asyncio
async def test_async_export_data_all_raises_on_partial_failure_without_silent_crash(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)
    manager.async_get_module_history = AsyncMock(return_value=[])  # type: ignore[method-assign]
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        garden_manager=None,
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(
                return_value={"filename": "routes.gpx", "content": "<gpx />"},
            ),
        ),
    )

    with pytest.raises(HomeAssistantError, match="Garden manager not available"):
        await manager.async_export_data("buddy", "all", format="json")

    exports_dir = tmp_path / "pawcontrol" / "exports"
    manifest_files = list(exports_dir.glob("*_all_*.json"))
    assert manifest_files == []


@pytest.mark.asyncio
async def test_async_generate_report_ignores_invalid_timestamps_and_persists_report(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [{"timestamp": "not-a-date", "portion_size": 10}]
    profile.walk_history = [{"end_time": "also-not-a-date", "distance": 2.5}]
    profile.health_history = [{"timestamp": "still-invalid", "mood": "ok"}]

    report = await manager.async_generate_report(
        "buddy",
        "monthly",
        include_recommendations=True,
    )

    assert report["feeding"]["entries"] == 0
    assert report["walks"]["entries"] == 0
    assert report["health"]["entries"] == 0
    assert report["recommendations"] == [
        "Log feeding events to improve analysis accuracy.",
        "Schedule regular walks to maintain activity levels.",
    ]
    reports_namespace = await manager._get_namespace_data("reports")
    assert reports_namespace["buddy"]["monthly"]["report_type"] == "monthly"


@pytest.mark.asyncio
async def test_async_generate_report_propagates_persist_errors(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)
    manager._save_namespace = AsyncMock(side_effect=HomeAssistantError("persist boom"))  # type: ignore[method-assign]

    with pytest.raises(HomeAssistantError, match="persist boom"):
        await manager.async_generate_report("buddy", "weekly")

    assert manager._namespace_state.get("reports") is None


@pytest.mark.asyncio
async def test_async_export_data_defaults_to_json_when_format_is_invalid(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [
        {"timestamp": "2026-01-01T10:00:00+00:00", "portion_size": 42.0},
    ]

    export_path = await manager.async_export_data(
        "buddy",
        "feeding",
        format="invalid-format",
    )
    payload = json.loads(export_path.read_text(encoding="utf-8"))

    assert export_path.suffix == ".json"
    assert payload["dog_id"] == "buddy"
    assert payload["data_type"] == "feeding"
    assert isinstance(payload["entries"], list)


@pytest.mark.asyncio
async def test_async_export_data_raises_for_unknown_export_type(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)

    with pytest.raises(HomeAssistantError, match="Unsupported export data type"):
        await manager.async_export_data("buddy", "unknown-module")


@pytest.mark.asyncio
async def test_async_export_data_propagates_boundary_io_errors(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [
        {"timestamp": "2026-01-01T10:00:00+00:00", "portion_size": 10.0},
    ]
    manager._async_add_executor_job = AsyncMock(side_effect=OSError("disk full"))  # type: ignore[method-assign]

    with pytest.raises(OSError, match="disk full"):
        await manager.async_export_data("buddy", "feeding", format="csv")


@pytest.mark.asyncio
async def test_async_generate_report_full_payload_with_best_effort_integrations(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [
        {"timestamp": "2026-01-01T10:00:00+00:00", "portion_size": 100.0},
    ]
    profile.walk_history = [
        {"end_time": "2026-01-01T11:00:00+00:00", "distance": 2.5},
    ]
    profile.health_history = [
        {"timestamp": "2026-01-01T12:00:00+00:00", "mood": "great"},
    ]
    runtime_data = SimpleNamespace(
        feeding_manager=SimpleNamespace(
            async_generate_health_report=AsyncMock(return_value={"score": 93}),
        ),
        notification_manager=SimpleNamespace(
            async_send_notification=AsyncMock(side_effect=RuntimeError("notify boom")),
        ),
    )
    manager._get_runtime_data = lambda: runtime_data  # type: ignore[method-assign]

    report = await manager.async_generate_report(
        "buddy",
        "monthly",
        include_recommendations=True,
        start_date="2025-12-31T00:00:00+00:00",
        end_date="2026-01-03T00:00:00+00:00",
        include_sections=["feeding", "walks", "health"],
        send_notification=True,
    )

    assert report["feeding"]["entries"] == 1
    assert report["walks"]["entries"] == 1
    assert report["health"]["entries"] == 1
    assert report["health"]["detailed_report"] == {"score": 93}
    assert report["recommendations"] == []
    runtime_data.notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_generate_report_handles_optional_fields_and_manager_exceptions(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        feeding_manager=SimpleNamespace(
            async_generate_health_report=AsyncMock(side_effect=ValueError("boom")),
        ),
    )

    report = await manager.async_generate_report(
        "buddy",
        "weekly",
        include_recommendations=False,
        include_sections=None,
    )

    assert sorted(report["sections"]) == ["feeding", "health", "walks"]
    assert "recommendations" not in report
    assert report["health"]["latest"] is None
    assert "detailed_report" not in report["health"]


@pytest.mark.asyncio
async def test_async_generate_report_rejects_unknown_dog(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _init_data_manager_for_export_tests(mock_hass, tmp_path)

    with pytest.raises(HomeAssistantError, match="Unknown PawControl dog"):
        await manager.async_generate_report("missing", "weekly")


def test_cache_repair_summary_handles_corrupt_snapshot_payloads() -> None:
    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir="/tmp"),
        async_add_executor_job=None,
    )
    manager = PawControlDataManager(
        hass,  # type: ignore[arg-type]
        entry_id="entry-1",
        dogs_config=[],
    )
    summary = manager.cache_repair_summary(
        {
            "cache-a": {
                "stats": {"entries": "nan", "hits": "4", "misses": "2"},
                "diagnostics": {
                    "errors": "boom",
                    "expired_entries": "x",
                    "pending_expired_entries": 1,
                    "active_override_flags": "2",
                    "timestamp_anomalies": {"buddy": "future"},
                },
            },
            "cache-b": object(),
            "": {"stats": {"hits": 1}},  # ignored invalid cache name
        },
    )

    assert summary is not None
    assert summary["severity"] == "error"
    assert summary["totals"]["hits"] == 4
    assert summary["totals"]["misses"] == 2
    assert summary["totals"]["active_override_flags"] == 2
    assert summary["caches_with_errors"] == ["cache-a"]
    assert summary["caches_with_pending_expired_entries"] == ["cache-a"]


def test_cache_repair_summary_stable_defaults_for_missing_and_invalid_fields() -> None:
    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir="/tmp"),
        async_add_executor_job=None,
    )
    manager = PawControlDataManager(
        hass,  # type: ignore[arg-type]
        entry_id="entry-1",
        dogs_config=[],
    )

    assert manager.cache_repair_summary({}) is None

    summary = manager.cache_repair_summary(
        {
            "cache-typed-errors": {
                "stats": {"entries": object(), "hits": "2", "misses": "3"},
                "diagnostics": {
                    "errors": 7,
                    "expired_entries": None,
                    "pending_override_candidates": "invalid",
                    "timestamp_anomalies": {"buddy": 123},
                },
            },
            "cache-no-issues": {"stats": {"entries": 1, "hits": 1, "misses": 0}},
        },
    )

    assert summary is not None
    assert summary["severity"] == "error"
    assert summary["totals"]["entries"] == 1
    assert summary["totals"]["hits"] == 3
    assert summary["totals"]["misses"] == 3
    assert summary["totals"]["expired_entries"] == 0
    assert summary["issues"] is not None
    issue = summary["issues"][0]
    assert issue["errors"] == ["7"]
    assert issue["timestamp_anomalies"] == {"buddy": "123"}
