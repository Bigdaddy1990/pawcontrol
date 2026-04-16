"""Targeted branch coverage for PawControlDataManager storage and trend helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol import data_manager as data_manager_module
from custom_components.pawcontrol.data_manager import (
    AdaptiveCache,
    CacheDiagnosticsSnapshot,
    PawControlDataManager,
)
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    FeedingData,
    GPSLocation,
    WalkData,
)


async def _create_manager(mock_hass: object, tmp_path: Path) -> PawControlDataManager:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-storage-trends",
        dogs_config=[{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
    )
    original_load_storage = manager._async_load_storage
    original_write_storage = manager._write_storage
    manager._async_load_storage = AsyncMock(return_value={})  # type: ignore[method-assign]
    manager._write_storage = AsyncMock()  # type: ignore[method-assign]
    await manager.async_initialize()
    manager._async_load_storage = original_load_storage  # type: ignore[method-assign]
    manager._write_storage = original_write_storage  # type: ignore[method-assign]
    return manager


@pytest.mark.asyncio
async def test_get_walk_history_handles_missing_profile_sorting_and_limit(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.walk_history = [
        {"end_time": "2026-01-02T08:00:00+00:00", "distance": 2.0},
        {"end_time": "2026-01-03T08:00:00+00:00", "distance": 3.0},
        {"end_time": "2026-01-01T08:00:00+00:00", "distance": 1.0},
    ]

    assert manager.get_walk_history("missing") == []
    history = manager.get_walk_history("buddy")
    limited = manager.get_walk_history("buddy", limit=2)

    assert [entry["distance"] for entry in history] == [3.0, 2.0, 1.0]
    assert [entry["distance"] for entry in limited] == [3.0, 2.0]


@pytest.mark.asyncio
async def test_async_update_walk_route_handles_missing_dog_and_missing_walk(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    location = GPSLocation(
        latitude=52.52,
        longitude=13.40,
        timestamp=datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert await manager.async_update_walk_route("missing", location) is False
    assert await manager.async_update_walk_route("buddy", location) is False


@pytest.mark.asyncio
async def test_async_update_walk_route_returns_false_when_walk_cleared_inside_lock(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.current_walk = WalkData(start_time=datetime(2026, 1, 3, tzinfo=UTC))

    class _ClearWalkLock:
        async def __aenter__(self) -> None:
            profile.current_walk = None

        async def __aexit__(self, *_args: object) -> bool:
            return False

    manager._data_lock = _ClearWalkLock()  # type: ignore[assignment]
    location = GPSLocation(
        latitude=52.52,
        longitude=13.40,
        timestamp=datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert await manager.async_update_walk_route("buddy", location) is False


@pytest.mark.asyncio
async def test_async_update_walk_route_records_optional_fields_and_persists(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.current_walk = WalkData(start_time=datetime(2026, 1, 3, tzinfo=UTC))
    manager._async_save_dog_data = AsyncMock(return_value=None)  # type: ignore[method-assign]
    location = GPSLocation(
        latitude=52.52,
        longitude=13.40,
        accuracy=5.0,
        altitude=35.0,
        battery_level=80,
        signal_strength=90,
        source="tracker",
        timestamp=datetime(2026, 1, 3, 8, 30, tzinfo=UTC),
    )

    result = await manager.async_update_walk_route("buddy", location)

    assert result is True
    route_point = profile.current_walk.route[-1]
    assert route_point["accuracy"] == 5.0
    assert route_point["altitude"] == 35.0
    assert route_point["battery_level"] == 80
    assert route_point["signal_strength"] == 90
    assert profile.daily_stats.gps_updates_count == 1


@pytest.mark.asyncio
async def test_async_update_walk_route_returns_false_on_homeassistant_persist_error(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].current_walk = WalkData(
        start_time=datetime(2026, 1, 3, tzinfo=UTC),
    )
    manager._async_save_dog_data = AsyncMock(  # type: ignore[method-assign]
        side_effect=HomeAssistantError("persist failed"),
    )
    location = GPSLocation(
        latitude=52.52,
        longitude=13.40,
        timestamp=datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert await manager.async_update_walk_route("buddy", location) is False


@pytest.mark.asyncio
async def test_health_and_profile_update_false_paths(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    assert await manager.async_log_health_data("missing", {"weight": 22.0}) is False
    assert await manager.async_log_medication("missing", {"name": "med"}) is False
    assert (
        await manager.async_update_dog_data("missing", {"profile": {"x": 1}}) is False
    )

    manager._async_save_dog_data = AsyncMock(  # type: ignore[method-assign]
        side_effect=HomeAssistantError("save failed"),
    )
    assert await manager.async_log_health_data("buddy", {"weight": 21.0}) is False
    assert await manager.async_log_medication("buddy", {"name": "med"}) is False


@pytest.mark.asyncio
async def test_async_update_dog_data_handles_invalid_payload_and_persist_flag(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    with pytest.raises(HomeAssistantError, match="Invalid PawControl update"):
        await manager.async_update_dog_data("buddy", {DOG_ID_FIELD: 123})  # type: ignore[dict-item]

    manager._async_save_profile = AsyncMock(  # type: ignore[method-assign]
        side_effect=HomeAssistantError("persist failed"),
    )
    persisted = await manager.async_update_dog_data(
        "buddy",
        {"profile": {"nickname": "Buddy"}},
        persist=True,
    )
    assert persisted is False

    manager._async_save_profile = AsyncMock(return_value=None)  # type: ignore[method-assign]
    in_memory_only = await manager.async_update_dog_profile(
        "buddy",
        {"nickname": "Buddy"},
        persist=False,
    )
    assert in_memory_only is True
    assert manager._dog_profiles["buddy"].config["profile"]["nickname"] == "Buddy"


@pytest.mark.asyncio
async def test_get_health_history_missing_and_limit(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.health_history = [
        {"timestamp": "2026-01-01T08:00:00+00:00", "status": "old"},
        {"timestamp": "2026-01-03T08:00:00+00:00", "status": "new"},
    ]

    assert manager.get_health_history("missing") == []
    assert [entry["status"] for entry in manager.get_health_history("buddy")] == [
        "new",
        "old",
    ]
    assert [
        entry["status"] for entry in manager.get_health_history("buddy", limit=1)
    ] == [
        "new",
    ]


def test_get_health_trends_returns_none_for_unknown_dog(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass, entry_id="entry-storage-trends", dogs_config=[]
    )  # type: ignore[arg-type]
    assert manager.get_health_trends("missing") is None


@pytest.mark.asyncio
async def test_get_health_trends_returns_empty_payload_when_no_relevant_entries(
    mock_hass: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 4, tzinfo=UTC)
    monkeypatch.setattr(data_manager_module, "_utcnow", lambda: now)
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].health_history = [
        {"timestamp": "invalid", "weight": 20.0, "mood": "happy"},
        {"timestamp": (now - timedelta(days=20)).isoformat(), "weight": 21.0},
    ]

    trends = manager.get_health_trends("buddy", days=7)

    assert trends == {
        "entries": 0,
        "weight_trend": None,
        "mood_distribution": {},
    }


@pytest.mark.parametrize(
    ("weights", "direction"),
    [
        ([20.0, 21.5], "increasing"),
        ([21.5, 20.0], "decreasing"),
        ([20.0, 20.0], "stable"),
    ],
)
@pytest.mark.asyncio
async def test_get_health_trends_builds_weight_mood_and_status_sections(
    mock_hass: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    weights: list[float],
    direction: str,
) -> None:
    now = datetime(2026, 1, 4, tzinfo=UTC)
    monkeypatch.setattr(data_manager_module, "_utcnow", lambda: now)
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].health_history = [
        {
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "weight": weights[0],
            "mood": "happy",
            "health_status": "ok",
        },
        {
            "timestamp": (now - timedelta(hours=2)).isoformat(),
            "weight": "invalid",
            "mood": None,
            "health_status": 1,
        },
        {
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "weight": weights[1],
            "mood": None,
        },
    ]

    trends = manager.get_health_trends("buddy", days=7)

    assert trends is not None
    assert trends["entries"] == 3
    assert trends["mood_distribution"] == {"happy": 1, "unknown": 2}
    assert trends["health_status_progression"] == ["ok"]
    weight_trend = trends["weight_trend"]
    assert isinstance(weight_trend, dict)
    assert weight_trend["direction"] == direction
    assert len(weight_trend["data_points"]) == 2


@pytest.mark.asyncio
async def test_get_health_trends_sets_weight_trend_none_when_weights_are_non_numeric(
    mock_hass: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 4, tzinfo=UTC)
    monkeypatch.setattr(data_manager_module, "_utcnow", lambda: now)
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].health_history = [
        {
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "weight": "not-a-number",
            "mood": "calm",
        },
    ]

    trends = manager.get_health_trends("buddy", days=7)

    assert trends is not None
    assert trends["entries"] == 1
    assert trends["weight_trend"] is None
    assert trends["mood_distribution"] == {"calm": 1}


def test_get_metrics_includes_storage_and_cache_snapshots(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-storage-trends",
        dogs_config=[{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
    )
    manager.register_cache_monitor(
        "fake", type("Cache", (), {"get_stats": lambda *_: {}})()
    )

    metrics = manager.get_metrics()

    assert metrics["dogs"] == 0
    assert "entry-storage-trends_data.json" in metrics["storage_path"]
    assert "fake" in metrics["cache_diagnostics"]


@pytest.mark.asyncio
async def test_daily_feeding_stats_history_reset_and_module_data_paths(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.daily_stats.date = datetime(2026, 1, 4, tzinfo=UTC)
    profile.daily_stats.feedings_count = 2
    profile.daily_stats.total_food_amount = 120.5
    profile.feeding_history = [
        {
            "timestamp": "2026-01-04T08:00:00+00:00",
            "calories": 120,
            "portion_size": 60.0,
        },
        {
            "timestamp": datetime(2026, 1, 4, 18, tzinfo=UTC),
            "calories": "invalid",
            "portion_size": 60.5,
        },
        {
            "timestamp": "2026-01-03T08:00:00+00:00",
            "calories": 90,
            "portion_size": 45.0,
        },
    ]
    profile.config["modules"] = {"feeding": True, "gps": False}

    assert manager.get_daily_feeding_stats("missing") is None
    stats = manager.get_daily_feeding_stats("buddy")
    assert stats is not None
    assert stats["total_feedings"] == 2
    assert stats["total_food_amount"] == 120.5
    assert stats["total_calories"] == 120.0
    assert len(stats["feeding_times"]) == 1

    assert manager.get_feeding_history("missing") == []
    assert sorted(
        entry["portion_size"] for entry in manager.get_feeding_history("buddy")
    ) == [45.0, 60.0, 60.5]
    latest = manager.get_feeding_history("buddy", limit=1)
    assert len(latest) == 1
    assert latest[0]["portion_size"] in (60.0, 60.5)

    manager._get_namespace_data = AsyncMock(  # type: ignore[method-assign]
        return_value={"buddy": {"gps": {"enabled": True}}},
    )
    modules = await manager.async_get_module_data("buddy")
    assert modules["feeding"] is True
    assert modules["gps"]["enabled"] is True

    with pytest.raises(HomeAssistantError, match="Unknown PawControl dog: missing"):
        await manager.async_get_module_data("missing")

    manager._async_save_profile = AsyncMock(return_value=None)  # type: ignore[method-assign]
    await manager.async_reset_dog_daily_stats("buddy")
    manager._async_save_profile.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_shutdown_handles_uninitialized_and_persist_failures(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-storage-trends",
        dogs_config=[{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
    )
    await manager.async_shutdown()

    manager = await _create_manager(mock_hass, tmp_path)
    manager._async_save_dog_data = AsyncMock(  # type: ignore[method-assign]
        side_effect=HomeAssistantError("persist failed"),
    )
    await manager.async_shutdown()


@pytest.mark.asyncio
async def test_async_set_visitor_mode_and_status_validation_paths(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    with pytest.raises(ValueError, match="dog_id is required"):
        await manager.async_set_visitor_mode("", {"enabled": True})

    with pytest.raises(ValueError, match="Visitor mode payload is required"):
        await manager.async_set_visitor_mode("buddy")

    manager._update_namespace_for_dog = AsyncMock(return_value={"enabled": True})  # type: ignore[method-assign]
    assert (
        await manager.async_set_visitor_mode(
            "buddy",
            None,
            visitor_data={"enabled": True},
        )
        is True
    )
    assert await manager.async_set_visitor_mode("buddy", None, enabled=True) is True

    manager._update_namespace_for_dog = AsyncMock(  # type: ignore[method-assign]
        side_effect=HomeAssistantError("namespace failure"),
    )
    with pytest.raises(HomeAssistantError, match="namespace failure"):
        await manager.async_set_visitor_mode("buddy", {"enabled": True})
    assert manager._metrics["errors"] >= 1

    manager._get_namespace_data = AsyncMock(  # type: ignore[method-assign]
        return_value={"buddy": {"enabled": True}},
    )
    assert await manager.async_get_visitor_mode_status("buddy") == {"enabled": True}
    manager._get_namespace_data = AsyncMock(return_value={"buddy": "invalid"})  # type: ignore[method-assign]
    assert await manager.async_get_visitor_mode_status("buddy") == {"enabled": False}


@pytest.mark.asyncio
async def test_walk_lifecycle_false_paths_and_optional_end_walk_branches(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    assert await manager.async_start_walk("missing") is False
    manager._dog_profiles["buddy"].current_walk = WalkData(
        start_time=datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert await manager.async_start_walk("buddy") is False

    manager._dog_profiles["buddy"].current_walk = None
    manager._async_save_dog_data = AsyncMock(  # type: ignore[method-assign]
        side_effect=HomeAssistantError("persist failed"),
    )
    assert await manager.async_start_walk("buddy") is False

    assert await manager.async_end_walk("missing") is False
    manager._dog_profiles["buddy"].current_walk = None
    assert await manager.async_end_walk("buddy") is False

    manager._dog_profiles["buddy"].current_walk = WalkData(
        start_time=datetime(2026, 1, 3, tzinfo=UTC),
        duration=42,
        distance=3.5,
        rating=7,
    )
    manager._async_save_dog_data = AsyncMock(return_value=None)  # type: ignore[method-assign]
    assert await manager.async_end_walk("buddy", rating=None, distance=None) is True
    last_walk = manager._dog_profiles["buddy"].walk_history[-1]
    assert last_walk["duration"] == 42
    assert last_walk["distance"] == 3.5
    assert last_walk["rating"] == 7

    manager._dog_profiles["buddy"].current_walk = WalkData(
        start_time=datetime(2026, 1, 3, tzinfo=UTC),
    )
    manager._async_save_dog_data = AsyncMock(  # type: ignore[method-assign]
        side_effect=HomeAssistantError("persist failed"),
    )
    assert await manager.async_end_walk("buddy") is False


@pytest.mark.asyncio
async def test_async_set_gps_log_poop_and_grooming_paths(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    captured_payloads: list[dict[str, Any]] = []

    async def _capture_module_state(
        _namespace: str,
        _dog_id: str,
        updater: Any,
    ) -> dict[str, Any]:
        payload = updater({"gps": {"enabled": False}})
        captured_payloads.append(payload)
        return payload

    manager._update_namespace_for_dog = _capture_module_state  # type: ignore[method-assign]
    await manager.async_set_gps_tracking("buddy", True)
    assert captured_payloads[-1]["gps"]["enabled"] is True
    assert "updated_at" in captured_payloads[-1]["gps"]

    assert (
        await manager.async_log_poop_data("missing", {"consistency": "normal"}) is False
    )

    manager._async_save_profile = AsyncMock(return_value=None)  # type: ignore[method-assign]
    assert await manager.async_log_poop_data(
        "buddy", {"consistency": "normal"}, limit=1
    )
    assert await manager.async_log_poop_data("buddy", {"consistency": "soft"}, limit=1)
    assert len(manager._dog_profiles["buddy"].poop_history) == 1
    assert manager._dog_profiles["buddy"].poop_history[0]["consistency"] == "soft"
    assert "timestamp" in manager._dog_profiles["buddy"].poop_history[0]

    manager._async_save_profile = AsyncMock(  # type: ignore[method-assign]
        side_effect=HomeAssistantError("persist failed"),
    )
    assert await manager.async_log_poop_data("buddy", {"consistency": "firm"}) is False

    with pytest.raises(HomeAssistantError, match="Unknown PawControl dog: missing"):
        await manager.async_start_grooming_session("missing", {"action": "brush"})

    manager._async_save_profile = AsyncMock(return_value=None)  # type: ignore[method-assign]
    manager._session_id_factory = lambda: "session-1"  # type: ignore[method-assign]
    profile = manager._dog_profiles["buddy"]
    profile.grooming_sessions = [{"session_id": f"s-{idx}"} for idx in range(50)]
    session_id = await manager.async_start_grooming_session(
        "buddy", {"action": "brush"}
    )
    assert session_id == "session-1"
    assert len(profile.grooming_sessions) == 50
    assert profile.grooming_sessions[-1]["session_id"] == "session-1"
    assert "started_at" in profile.grooming_sessions[-1]


@pytest.mark.asyncio
async def test_async_analyze_patterns_comprehensive_and_advanced_paths(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    async def _history(
        module: str, _dog_id: str, **_kwargs: Any
    ) -> list[dict[str, Any]]:
        if module == "feeding":
            return [
                {"timestamp": "invalid", "portion_size": 10.0},
                {"timestamp": "2026-01-03T08:00:00+00:00", "portion_size": "x"},
                {"timestamp": "2026-01-03T09:00:00+00:00", "portion_size": 30.0},
            ]
        if module in {"walk", "walking"}:
            return [
                {"end_time": "invalid", "distance": 1.0},
                {"end_time": "2026-01-03T09:00:00+00:00", "distance": "n/a"},
                {"end_time": "2026-01-03T10:00:00+00:00", "distance": 2.5},
            ]
        return [
            {"timestamp": "invalid", "status": "ignore"},
            {"timestamp": "2026-01-03T11:00:00+00:00", "status": "ok"},
        ]

    manager.async_get_module_history = _history  # type: ignore[method-assign]
    manager._update_namespace_for_dog = AsyncMock(return_value={})  # type: ignore[method-assign]
    manager._get_runtime_data = lambda: None  # type: ignore[method-assign]

    result = await manager.async_analyze_patterns("buddy", "comprehensive", days=7)
    assert result["feeding"]["entries"] == 2
    assert result["feeding"]["total_portion_size"] == 30.0
    assert result["walking"]["entries"] == 2
    assert result["walking"]["total_distance"] == 2.5
    assert result["health"]["entries"] == 1
    assert result["health"]["latest"]["status"] == "ok"

    runtime = SimpleNamespace(
        feeding_manager=SimpleNamespace(
            async_analyze_feeding_health=AsyncMock(return_value={"score": 88}),
        ),
    )
    manager._get_runtime_data = lambda: runtime  # type: ignore[method-assign]
    feeding_result = await manager.async_analyze_patterns("buddy", "feeding", days=7)
    assert feeding_result["feeding"]["health_analysis"] == {"score": 88}

    runtime.feeding_manager.async_analyze_feeding_health = AsyncMock(
        side_effect=RuntimeError("adapter down"),
    )
    feeding_result_no_advanced = await manager.async_analyze_patterns(
        "buddy",
        "feeding",
        days=7,
    )
    assert "health_analysis" not in feeding_result_no_advanced["feeding"]


@pytest.mark.asyncio
async def test_register_cache_monitor_and_manager_registration_paths(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    with pytest.raises(
        ValueError, match="Cache monitor name must be a non-empty string"
    ):
        manager.register_cache_monitor("", object())

    class _LegacyCache:
        def coordinator_snapshot(self) -> object:
            return object()

        def get_stats(self) -> int:
            return 7

        def get_diagnostics(self) -> list[str]:
            return ["warn"]

    manager.register_cache_monitor("legacy", _LegacyCache())
    snapshot = manager.cache_snapshots()["legacy"]
    assert isinstance(snapshot, CacheDiagnosticsSnapshot)
    summary = manager.cache_repair_summary(
        {
            "legacy": CacheDiagnosticsSnapshot(
                stats={"entries": 1, "hits": 1, "misses": 0},
                diagnostics={},
            ),
        },
    )
    assert summary is not None

    class _Registrar:
        def __init__(self) -> None:
            self.called = False

        def register_cache_monitors(self, cache_manager: PawControlDataManager) -> None:
            self.called = cache_manager is manager

    registrar = _Registrar()
    manager._register_manager_cache_monitors(registrar, prefix=None, label="custom")
    assert registrar.called
    manager._register_manager_cache_monitors(
        SimpleNamespace(), prefix=None, label="none"
    )

    manager._get_runtime_data = lambda: None  # type: ignore[method-assign]
    manager.register_runtime_cache_monitors()


@pytest.mark.asyncio
async def test_adaptive_cache_expiration_and_cleanup_override_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 4, tzinfo=UTC)
    monkeypatch.setattr(data_manager_module, "_utcnow", lambda: now)

    cache = AdaptiveCache[str](default_ttl=10)
    cache._data["expired"] = "value"
    cache._metadata["expired"] = {
        "created_at": now - timedelta(seconds=20),
        "ttl": 5,
        "expiry": now - timedelta(seconds=5),
        "override_applied": True,
    }
    value, hit = await cache.get("expired")
    assert value is None
    assert hit is False
    assert cache.get_diagnostics()["expired_via_override"] == 1

    cache._data["invalid_created"] = "v"
    cache._metadata["invalid_created"] = {
        "created_at": "invalid",  # type: ignore[typeddict-item]
        "ttl": 0,
    }
    await cache.cleanup_expired(ttl_seconds=-1)
    assert cache._metadata["invalid_created"]["expiry"] is None

    cache._data["override_ttl"] = "v"
    cache._metadata["override_ttl"] = {
        "created_at": now,
        "ttl": 0,
    }
    await cache.cleanup_expired(ttl_seconds=5)
    assert cache._metadata["override_ttl"]["ttl"] == 0


@pytest.mark.asyncio
async def test_adaptive_cache_expiry_without_override_and_default_cleanup_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 4, tzinfo=UTC)
    monkeypatch.setattr(data_manager_module, "_utcnow", lambda: now)

    cache = AdaptiveCache[str](default_ttl=5)
    cache._data["expired"] = "value"
    cache._metadata["expired"] = {
        "created_at": now - timedelta(seconds=10),
        "ttl": 1,
        "expiry": now - timedelta(seconds=1),
        "override_applied": False,
    }
    value, hit = await cache.get("expired")
    assert value is None
    assert hit is False

    cache._data["cleanup"] = "value"
    cache._metadata["cleanup"] = {
        "created_at": "bad-created",  # type: ignore[typeddict-item]
        "ttl": 1,
    }
    await cache.cleanup_expired()
    assert "cleanup" in cache._metadata


@pytest.mark.asyncio
async def test_adaptive_cache_cleanup_handles_untyped_created_at_when_normalizer_is_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 4, tzinfo=UTC)
    monkeypatch.setattr(data_manager_module, "_utcnow", lambda: now)

    cache = AdaptiveCache[str](default_ttl=5)
    cache._data["raw"] = "value"
    cache._metadata["raw"] = {
        "created_at": "bad-created",  # type: ignore[typeddict-item]
        "ttl": 1,
    }
    cache._normalize_entry_locked = lambda _key, entry, _now: entry  # type: ignore[method-assign]
    await cache.cleanup_expired()
    assert "raw" in cache._metadata


def test_constructor_runtime_and_helper_fallback_branches(tmp_path: Path) -> None:
    hass = SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))
    coordinator = SimpleNamespace(config_entry=SimpleNamespace(entry_id=123))
    manager = PawControlDataManager(
        hass=hass,
        entry_id=None,
        coordinator=coordinator,
        dogs_config=[
            123,  # type: ignore[list-item]
            {DOG_ID_FIELD: "", DOG_NAME_FIELD: "Invalid"},
            {DOG_ID_FIELD: "invalid-typed", DOG_NAME_FIELD: "Bad", "modules": "nope"},
            {DOG_ID_FIELD: "buddy"},
        ],
    )

    assert manager.entry_id == "default"
    assert list(manager._dogs_config) == ["invalid-typed", "buddy"]

    original_ensure = data_manager_module.ensure_dog_config_data
    data_manager_module.ensure_dog_config_data = lambda _data: None  # type: ignore[assignment]
    try:
        forced_none = PawControlDataManager(
            hass=hass,
            entry_id="forced-none",
            dogs_config=[{DOG_ID_FIELD: "forced", DOG_NAME_FIELD: "Forced"}],
        )
    finally:
        data_manager_module.ensure_dog_config_data = original_ensure  # type: ignore[assignment]
    assert forced_none._dogs_config == {}

    manager.entry_id = ""
    assert manager._get_runtime_data() is None

    assert data_manager_module._serialize_timestamp("invalid-date").endswith("+00:00")
    mapping = MappingProxyType({"flag": True})
    assert data_manager_module._coerce_mapping(mapping) == {"flag": True}
    assert data_manager_module._limit_entries([{"a": 1}], limit=0) == [{"a": 1}]
    payload = [{"value": 1}, {"timestamp": "2026-01-01T00:00:00+00:00"}]
    assert (
        data_manager_module._find_namespace_timestamp(payload)
        == "2026-01-01T00:00:00+00:00"
    )

    original_module = sys.modules.pop("homeassistant.util.dt", None)
    try:
        assert isinstance(data_manager_module._utcnow(), datetime)
    finally:
        if original_module is not None:
            sys.modules["homeassistant.util.dt"] = original_module

    original_module = sys.modules.get("homeassistant.util.dt")
    sys.modules["homeassistant.util.dt"] = SimpleNamespace()
    try:
        assert isinstance(data_manager_module._utcnow(), datetime)
    finally:
        if original_module is None:
            sys.modules.pop("homeassistant.util.dt", None)
        else:
            sys.modules["homeassistant.util.dt"] = original_module

    original_module = sys.modules.get("homeassistant.util.dt")
    sys.modules["homeassistant.util.dt"] = SimpleNamespace(utcnow=lambda: "bad")
    try:
        assert isinstance(data_manager_module._utcnow(), datetime)
    finally:
        if original_module is None:
            sys.modules.pop("homeassistant.util.dt", None)
        else:
            sys.modules["homeassistant.util.dt"] = original_module


def test_import_alias_branch_executes_when_module_name_not_registered(
    tmp_path: Path,
) -> None:
    file_path = Path(data_manager_module.__file__)
    module_name = "custom_components.pawcontrol._temp_data_manager_alias"
    sys.modules.pop(module_name, None)
    sys.modules["pawcontrol_data_manager"] = SimpleNamespace()
    try:
        spec = importlib.util.spec_from_file_location(
            module_name,
            file_path,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
        sys.modules.pop("pawcontrol_data_manager", None)


@pytest.mark.asyncio
async def test_namespace_update_restore_and_profile_persistence_errors(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._namespace_state["reports"] = {"buddy": {"existing": True}}
    manager._get_namespace_data = AsyncMock(  # type: ignore[method-assign]
        return_value={"buddy": {"existing": True}},
    )
    manager._save_namespace = AsyncMock(side_effect=HomeAssistantError("persist"))  # type: ignore[method-assign]

    with pytest.raises(HomeAssistantError, match="persist"):
        await manager._update_namespace_for_dog(
            "reports",
            "buddy",
            lambda _current: None,
        )
    assert manager._namespace_state["reports"] == {"buddy": {"existing": True}}

    manager._save_namespace = AsyncMock(return_value=None)  # type: ignore[method-assign]
    removed = await manager._update_namespace_for_dog(
        "reports",
        "buddy",
        lambda _current: None,
    )
    assert removed is None

    with pytest.raises(HomeAssistantError, match="Invalid PawControl profile"):
        await manager._async_save_profile(
            "buddy",
            SimpleNamespace(config={"dog_name": "Buddy"}),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_async_initialize_uses_mapping_payload_and_invalid_config_raises(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-storage-trends",
        dogs_config=[{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
    )
    manager._async_load_storage = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "buddy": {
                "daily_stats": {"date": "2026-01-01T00:00:00+00:00"},
            },
        },
    )
    manager._write_storage = AsyncMock()  # type: ignore[method-assign]
    await manager.async_initialize()
    assert "buddy" in manager._dog_profiles

    profile = data_manager_module.DogProfile.from_storage(
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"},
        {"daily_stats": "invalid"},
    )
    assert profile.daily_stats is not None

    with pytest.raises(
        HomeAssistantError, match="Invalid dog configuration in storage"
    ):
        data_manager_module.DogProfile.from_storage(
            {"dog_name": "Buddy"},  # type: ignore[arg-type]
            {},
        )


@pytest.mark.asyncio
async def test_internal_monitor_payloads_cover_error_and_stats_paths(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    tracker_snapshot = SimpleNamespace(
        dog_id="buddy",
        profile="standard",
        requested_entities=["sensor.a"],
        denied_requests=[],
        capacity="bad",
        base_allocation="bad",
        dynamic_allocation="bad",
        recorded_at="not-a-date",
    )
    tracker_snapshot_parsed = SimpleNamespace(
        dog_id="max",
        profile="standard",
        requested_entities=[],
        denied_requests=[],
        recorded_at="2026-01-01T00:00:00+00:00",
    )
    tracker = SimpleNamespace(
        snapshots=lambda: [tracker_snapshot, tracker_snapshot_parsed],
        summary=lambda: {"ok": True},
        saturation=lambda: 0.5,
    )
    budget_monitor = data_manager_module._EntityBudgetMonitor(tracker)  # type: ignore[attr-defined]
    budget_snapshot = budget_monitor.coordinator_snapshot()
    assert budget_snapshot["diagnostics"]["snapshots"][0]["recorded_at"] is None
    assert budget_snapshot["diagnostics"]["snapshots"][1]["recorded_at"] is not None

    modules = SimpleNamespace(
        cache_metrics=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    modules_monitor = data_manager_module._CoordinatorModuleCacheMonitor(modules)  # type: ignore[attr-defined]
    assert "errors" in modules_monitor.coordinator_snapshot()["diagnostics"]
    assert "errors" in modules_monitor.get_diagnostics()

    metrics = SimpleNamespace(entries=1, hits=1, misses=0, hit_rate=100.0)
    modules_ok = SimpleNamespace(cache_metrics=lambda: metrics)
    modules_ok_monitor = data_manager_module._CoordinatorModuleCacheMonitor(modules_ok)  # type: ignore[attr-defined]
    assert "errors" not in modules_ok_monitor.get_diagnostics()

    storage_monitor = data_manager_module._StorageNamespaceCacheMonitor(  # type: ignore[attr-defined]
        manager,
        "reports",
        "reports",
    )
    assert storage_monitor.get_stats()["namespace"] == "reports"


@pytest.mark.asyncio
async def test_register_coordinator_and_cache_monitor_diagnostic_branches(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._register_coordinator_cache_monitors(SimpleNamespace())

    class _NoStatsCache:
        def coordinator_snapshot(self) -> object:
            return object()

        def get_diagnostics(self) -> dict[str, object]:
            return {"warning": "none"}

    class _StatsNoneCache:
        def coordinator_snapshot(self) -> object:
            return object()

        def get_stats(self) -> None:
            return None

        def get_diagnostics(self) -> list[str]:
            return ["warn"]

    manager.register_cache_monitor("nostats", _NoStatsCache())
    manager.register_cache_monitor("stats_none", _StatsNoneCache())
    snapshots = manager.cache_snapshots()
    assert "nostats" in snapshots
    assert "stats_none" in snapshots


@pytest.mark.asyncio
async def test_register_cache_monitor_diagnostics_non_mapping_branch(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    class _DiagnosticsStringCache:
        def coordinator_snapshot(self) -> object:
            return object()

        def get_stats(self) -> dict[str, int]:
            return {"entries": 1, "hits": 1, "misses": 0}

        def get_diagnostics(self) -> str:
            return "warning"

    class _DiagnosticsNoneCache:
        def coordinator_snapshot(self) -> object:
            return object()

        def get_stats(self) -> dict[str, int]:
            return {"entries": 1, "hits": 1, "misses": 0}

        def get_diagnostics(self) -> None:
            return None

    manager.register_cache_monitor("diag-string", _DiagnosticsStringCache())
    manager.register_cache_monitor("diag-none", _DiagnosticsNoneCache())
    snapshot = manager.cache_snapshots()["diag-string"]
    assert isinstance(snapshot, CacheDiagnosticsSnapshot)
    assert isinstance(manager.cache_snapshots()["diag-none"], CacheDiagnosticsSnapshot)


@pytest.mark.asyncio
async def test_module_history_generate_report_and_weekly_report_branches(
    mock_hass: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [
        {"timestamp": "2026-01-03T08:00:00+00:00", "portion_size": "bad"},
        {"timestamp": None, "portion_size": 30.0},
        {"timestamp": "2026-01-03T09:00:00+00:00", "portion_size": 10.0},
    ]
    profile.walk_history = [
        {"end_time": "2026-01-03T09:00:00+00:00", "distance": "bad"},
        {"end_time": "2026-01-03T10:00:00+00:00", "distance": 2.5},
    ]
    profile.health_history = [
        {"timestamp": "2026-01-03T11:00:00+00:00", "status": "ok"},
    ]

    manager._update_namespace_for_dog = AsyncMock(return_value={})  # type: ignore[method-assign]
    manager._get_runtime_data = lambda: SimpleNamespace()  # type: ignore[method-assign]

    report = await manager.async_generate_report(
        "buddy",
        "weekly",
        include_sections=["feeding", "walks"],
        include_recommendations=True,
        send_notification=True,
        start_date="2026-01-03T00:00:00+00:00",
        end_date="2026-01-04T00:00:00+00:00",
    )
    assert report["feeding"]["total_portion_size"] == 10.0
    assert report["walks"]["total_distance"] == 2.5
    assert "health" not in report

    manager._get_runtime_data = lambda: SimpleNamespace(
        feeding_manager=SimpleNamespace(
            async_analyze_feeding_health=AsyncMock(return_value=None),
        ),
    )  # type: ignore[method-assign]
    walking_only = await manager.async_analyze_patterns("buddy", "walking", days=7)
    assert "feeding" not in walking_only
    assert "walking" in walking_only

    original_deserialize = data_manager_module._deserialize_datetime
    monkeypatch.setattr(
        data_manager_module,
        "_deserialize_datetime",
        lambda value: (
            None if isinstance(value, datetime) else original_deserialize(value)
        ),
    )
    profile.feeding_history = [
        {"timestamp": datetime(2026, 1, 3, 8, tzinfo=UTC), "portion_size": 5.0},
        {"timestamp": object(), "portion_size": 1.0},
    ]
    history = await manager.async_get_module_history("feeding", "buddy")
    assert len(history) == 2

    manager.async_get_module_history = AsyncMock(return_value=[])  # type: ignore[method-assign]
    weekly = await manager.async_generate_weekly_health_report(
        "buddy",
        include_medication=False,
    )
    assert "medication" not in weekly

    manager.async_get_module_history = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"timestamp": datetime(2026, 1, 3, 8, tzinfo=UTC)}],
    )
    await manager.async_export_data("buddy", "feeding", format="json")


@pytest.mark.asyncio
async def test_history_and_export_sort_key_fallback_branches(
    mock_hass: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [
        {"timestamp": datetime(2026, 1, 3, 8, tzinfo=UTC), "portion_size": 1.0},
        {"timestamp": object(), "portion_size": 2.0},
    ]

    original_normalize = data_manager_module.normalize_value
    original_deserialize = data_manager_module._deserialize_datetime
    monkeypatch.setattr(data_manager_module, "normalize_value", lambda value: value)
    monkeypatch.setattr(
        data_manager_module,
        "_deserialize_datetime",
        lambda value: (
            None if not isinstance(value, str) else original_deserialize(value)
        ),
    )
    history = await manager.async_get_module_history("feeding", "buddy")
    assert len(history) == 2
    monkeypatch.setattr(data_manager_module, "normalize_value", original_normalize)

    manager.async_get_module_history = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"timestamp": object()}],
    )
    await manager.async_export_data("buddy", "feeding", format="json")


@pytest.mark.asyncio
async def test_export_route_csv_and_all_error_branches(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(
                return_value={"filename": "routes.json", "content": {"ok": True}},
            ),
        ),
    )
    route_path = await manager.async_export_data(
        "buddy",
        "routes",
        format="json",
        days=2,
    )
    assert json.loads(route_path.read_text(encoding="utf-8")) == {"ok": True}

    manager.async_get_module_history = AsyncMock(return_value=[])  # type: ignore[method-assign]
    csv_path = await manager.async_export_data("buddy", "feeding", format="csv")
    assert csv_path.suffix == ".csv"

    manager._async_add_executor_job = AsyncMock(side_effect=OSError("disk boom"))  # type: ignore[method-assign]
    with pytest.raises(OSError, match="disk boom"):
        await manager.async_export_data("buddy", "all", allow_partial=False)


@pytest.mark.asyncio
async def test_namespace_roundtrip_and_payload_guards(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    path = manager._namespace_path("reports")

    missing = await manager._get_namespace_data("reports")
    assert missing == {}
    assert manager._namespace_state["reports"] == {}

    path.write_text("", encoding="utf-8")
    assert await manager._get_namespace_data("reports") == {}

    path.write_text("{invalid", encoding="utf-8")
    assert await manager._get_namespace_data("reports") == {}

    path.write_text("[]", encoding="utf-8")
    assert await manager._get_namespace_data("reports") == {}

    path.write_text('{"buddy":{"ok":true}}', encoding="utf-8")
    loaded = await manager._get_namespace_data("reports")
    assert loaded == {"buddy": {"ok": True}}


@pytest.mark.asyncio
async def test_get_namespace_data_raises_on_oserror_and_handles_filenotfound(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    path = manager._namespace_path("reports")
    path.write_text("{}", encoding="utf-8")

    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=FileNotFoundError(),
    )
    assert await manager._get_namespace_data("reports") == {}

    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=OSError("disk failure"),
    )
    with pytest.raises(
        HomeAssistantError, match="Unable to read PawControl reports data"
    ):
        await manager._get_namespace_data("reports")


@pytest.mark.asyncio
async def test_save_namespace_updates_state_and_wraps_oserror(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    assert manager._metrics["saves"] == 0

    await manager._save_namespace("reports", {"buddy": {"count": 1}})

    assert manager._metrics["saves"] == 1
    assert manager._namespace_state["reports"] == {"buddy": {"count": 1}}

    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=OSError("read only"),
    )
    with pytest.raises(
        HomeAssistantError, match="Unable to persist PawControl reports"
    ):
        await manager._save_namespace("reports", {"buddy": {"count": 2}})


@pytest.mark.asyncio
async def test_async_add_executor_job_supports_mock_real_and_fallback_paths(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    mock_hass.async_add_executor_job = MagicMock()  # type: ignore[attr-defined]
    assert await manager._async_add_executor_job(lambda x: x + 1, 1) == 2

    async def _executor_job(func: Any, *args: Any) -> Any:
        return func(*args)

    mock_hass.async_add_executor_job = _executor_job  # type: ignore[attr-defined]
    assert await manager._async_add_executor_job(lambda x, y: x + y, 2, 3) == 5

    mock_hass.async_add_executor_job = None  # type: ignore[attr-defined]
    assert (
        await manager._async_add_executor_job(lambda text: text.upper(), "ok") == "OK"
    )


@pytest.mark.asyncio
async def test_async_load_storage_primary_paths(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    manager._async_add_executor_job = AsyncMock(return_value={"a": 1})  # type: ignore[method-assign]
    assert await manager._async_load_storage() == {"a": 1}

    manager._async_add_executor_job = AsyncMock(return_value=["not-mapping"])  # type: ignore[method-assign]
    assert await manager._async_load_storage() == {}

    manager._async_add_executor_job = AsyncMock(side_effect=FileNotFoundError())  # type: ignore[method-assign]
    assert await manager._async_load_storage() == {}

    manager._async_add_executor_job = AsyncMock(side_effect=OSError("disk failure"))  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError, match="Unable to read PawControl data"):
        await manager._async_load_storage()


@pytest.mark.asyncio
async def test_async_load_storage_backup_paths_after_corruption(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    decode_error = json.JSONDecodeError("bad json", "{}", 0)

    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=[decode_error, {"backup": 1}],
    )
    assert await manager._async_load_storage() == {"backup": 1}

    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=[decode_error, ["bad-backup"]],
    )
    assert await manager._async_load_storage() == {}

    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=[decode_error, None],
    )
    assert await manager._async_load_storage() == {}

    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=[decode_error, FileNotFoundError()],
    )
    assert await manager._async_load_storage() == {}

    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=[decode_error, json.JSONDecodeError("bad backup", "{}", 0)],
    )
    assert await manager._async_load_storage() == {}

    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=[decode_error, OSError("backup offline")],
    )
    with pytest.raises(HomeAssistantError, match="Unable to read PawControl backup"):
        await manager._async_load_storage()


@pytest.mark.asyncio
async def test_async_save_dog_data_wraps_oserror(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._async_add_executor_job = AsyncMock(side_effect=OSError("no space"))  # type: ignore[method-assign]

    with pytest.raises(HomeAssistantError, match="Failed to persist PawControl data"):
        await manager._async_save_dog_data("buddy")


def test_read_storage_payload_and_create_backup(
    tmp_path: Path, mock_hass: object
) -> None:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-storage-trends",
        dogs_config=[],
    )

    missing = tmp_path / "missing.json"
    assert PawControlDataManager._read_storage_payload(missing) is None

    source = tmp_path / "source.json"
    source.write_text('{"value": 1}', encoding="utf-8")
    assert PawControlDataManager._read_storage_payload(source) == {"value": 1}

    manager._storage_path = tmp_path / "storage.json"  # type: ignore[assignment]
    manager._backup_path = tmp_path / "backup.json"  # type: ignore[assignment]
    manager._create_backup()
    assert not manager._backup_path.exists()

    manager._storage_path.write_text('{"dog":"buddy"}', encoding="utf-8")
    manager._create_backup()
    assert manager._backup_path.read_text(encoding="utf-8") == '{"dog":"buddy"}'
