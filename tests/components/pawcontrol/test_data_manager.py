from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import data_manager
from custom_components.pawcontrol.const import CACHE_TIMESTAMP_STALE_THRESHOLD
from custom_components.pawcontrol.data_manager import (
    AdaptiveCache,
    DogProfile,
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
