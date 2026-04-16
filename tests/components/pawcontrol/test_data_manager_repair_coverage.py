"""Focused repair/report coverage for PawControlDataManager."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD, FeedingData


async def _create_manager(mock_hass: object, tmp_path: Path) -> PawControlDataManager:
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


def test_cache_repair_summary_uses_provider_and_returns_warning_without_errors(  # noqa: D103
    mock_hass: object,
    tmp_path: Path,
) -> None:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-1",
        dogs_config=[],
    )
    manager.cache_snapshots = lambda: {  # type: ignore[method-assign]
        "cache-a": {
            "stats": {"entries": 3, "hits": 1, "misses": 4},
            "diagnostics": {"expired_entries": 2},
        },
    }

    summary = manager.cache_repair_summary()

    assert summary is not None
    assert summary["severity"] == "warning"
    assert summary["anomaly_count"] == 2
    assert summary["caches_with_errors"] is None
    assert summary["caches_with_expired_entries"] == ["cache-a"]
    assert summary["caches_with_low_hit_rate"] == ["cache-a"]


def test_cache_repair_summary_handles_value_error_and_type_fallbacks(  # noqa: D103
    mock_hass: object,
    tmp_path: Path,
) -> None:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(mock_hass, entry_id="entry-1", dogs_config=[])

    snapshots = {
        "cache-main": {
            "stats": {
                "entries": "10",
                "hits": " 6 ",
                "misses": "4",
                "hit_rate": "bad-hit-rate",
            },
            "diagnostics": {
                "expired_entries": "not-number",
                "pending_expired_entries": "2",
                "active_override_flags": "1",
                "timestamp_anomalies": {"buddy": "future_timestamp"},
                "errors": ["write-failed", None],
            },
        },
        "cache-side": {
            "stats": {"entries": 5, "hits": 4, "misses": 1},
            "diagnostics": {"errors": "single-error"},
        },
        "": {"stats": {"entries": 999}},
        123: "invalid-payload",
    }

    summary = manager.cache_repair_summary(snapshots)  # type: ignore[arg-type]

    assert summary is not None
    assert summary["severity"] == "error"
    assert summary["anomaly_count"] == 2
    assert summary["totals"]["entries"] == 15
    assert summary["totals"]["hits"] == 10
    assert summary["totals"]["misses"] == 5
    assert summary["totals"]["pending_expired_entries"] == 2
    assert summary["totals"]["active_override_flags"] == 1
    assert summary["caches_with_errors"] == ["cache-main", "cache-side"]
    assert summary["caches_with_pending_expired_entries"] == ["cache-main"]
    assert summary["caches_with_override_flags"] == ["cache-main"]
    assert summary["caches_with_timestamp_anomalies"] == ["cache-main"]


def test_cache_repair_summary_returns_none_for_empty_snapshots(  # noqa: D103
    mock_hass: object,
    tmp_path: Path,
) -> None:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(mock_hass, entry_id="entry-1", dogs_config=[])

    assert manager.cache_repair_summary({}) is None


@pytest.mark.asyncio
async def test_async_generate_report_defaults_sections_and_handles_notification_failure(  # noqa: D103
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [
        {
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "portion_size": 2.0,
        },
    ]
    profile.walk_history = [
        {"end_time": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "distance": 3.0},
    ]
    profile.health_history = [
        {"timestamp": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "mood": "great"},
    ]
    runtime = SimpleNamespace(
        feeding_manager=SimpleNamespace(
            async_generate_health_report=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        notification_manager=SimpleNamespace(
            async_send_notification=AsyncMock(side_effect=RuntimeError("notify")),
        ),
    )
    manager._get_runtime_data = lambda: runtime  # type: ignore[method-assign]

    report = await manager.async_generate_report(
        "buddy",
        "weekly",
        include_sections=[],
        include_recommendations=True,
        send_notification=True,
        start_date="invalid-date",
        end_date="invalid-date",
    )

    assert sorted(report["sections"]) == ["feeding", "health", "walks"]
    assert report["feeding"]["entries"] == 0
    assert report["walks"]["entries"] == 0
    assert report["health"]["entries"] == 0
    assert "detailed_report" not in report["health"]
    assert isinstance(report["recommendations"], list)

    reports = await manager._get_namespace_data("reports")
    assert reports["buddy"]["weekly"]["report_type"] == "weekly"
    runtime.notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_generate_report_adds_detailed_health_section_when_available(  # noqa: D103
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.health_history = [
        {"timestamp": datetime(2026, 1, 2, tzinfo=UTC).isoformat(), "mood": "ok"},
    ]
    runtime = SimpleNamespace(
        feeding_manager=SimpleNamespace(
            async_generate_health_report=AsyncMock(return_value={"score": 88}),
        ),
    )
    manager._get_runtime_data = lambda: runtime  # type: ignore[method-assign]

    report = await manager.async_generate_report(
        "buddy",
        "focused-health",
        include_recommendations=False,
        include_sections=["health"],
    )

    assert report["sections"] == ["health"]
    assert report["health"]["detailed_report"] == {"score": 88}
    assert "recommendations" not in report


@pytest.mark.asyncio
async def test_async_generate_report_consistent_with_invalid_entries(  # noqa: D103
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [{"timestamp": "bad-date", "portion_size": 10}]
    profile.walk_history = [{"end_time": "bad-date", "distance": 2.5}]
    profile.health_history = [{"timestamp": "bad-date", "status": "ok"}]

    report = await manager.async_generate_report(
        "buddy", "weekly", include_recommendations=True
    )

    assert report["feeding"] == {"entries": 0, "total_portion_size": 0.0}
    assert report["walks"] == {"entries": 0, "total_distance": 0.0}
    assert report["health"]["entries"] == 0
    assert report["health"]["latest"] is None
    assert report["recommendations"] == [
        "Log feeding events to improve analysis accuracy.",
        "Schedule regular walks to maintain activity levels.",
    ]


@pytest.mark.asyncio
async def test_async_initialize_raises_error_when_storage_dir_creation_fails(
    mock_hass: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Storage folder creation failures should be surfaced as HomeAssistantError."""
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-1",
        dogs_config=[{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
    )

    def _raise_mkdir(_self: Path, *_args: object, **_kwargs: object) -> None:
        raise OSError("read-only filesystem")

    monkeypatch.setattr(
        type(manager._storage_dir),
        "mkdir",
        _raise_mkdir,
    )

    with pytest.raises(
        HomeAssistantError, match="Unable to prepare PawControl storage"
    ):
        await manager.async_initialize()


@pytest.mark.asyncio
async def test_async_initialize_continues_when_namespace_preload_fails(
    mock_hass: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initialization should continue when one namespace preload raises."""
    manager = await _create_manager(mock_hass, tmp_path)
    manager._initialised = False
    failing_namespace = "module_state"
    namespaces_seen: list[str] = []

    async def _fake_get_namespace_data(namespace: str) -> dict[str, object]:
        namespaces_seen.append(namespace)
        if namespace == failing_namespace:
            raise HomeAssistantError("simulated preload failure")
        return {}

    monkeypatch.setattr(manager, "_get_namespace_data", _fake_get_namespace_data)

    await manager.async_initialize()

    assert failing_namespace in namespaces_seen
    assert manager._initialised is True


@pytest.mark.asyncio
async def test_async_log_feeding_returns_false_for_unknown_dog(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    """Unknown dog IDs should fail fast without persistence writes."""
    manager = await _create_manager(mock_hass, tmp_path)
    manager._async_save_dog_data = AsyncMock()  # type: ignore[method-assign]

    feeding = FeedingData(
        meal_type="breakfast",
        portion_size=125.0,
        food_type="dry_food",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = await manager.async_log_feeding("unknown-dog", feeding)

    assert result is False
    manager._async_save_dog_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_log_feeding_returns_false_when_persist_fails(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    """Persistence errors should produce a False return contract."""
    manager = await _create_manager(mock_hass, tmp_path)
    manager._async_save_dog_data = AsyncMock(  # type: ignore[method-assign]
        side_effect=HomeAssistantError("disk full")
    )
    feeding = FeedingData(
        meal_type="dinner",
        portion_size=150.0,
        food_type="wet_food",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = await manager.async_log_feeding("buddy", feeding)

    assert result is False
