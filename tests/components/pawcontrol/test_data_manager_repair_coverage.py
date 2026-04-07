"""Focused repair/report coverage for PawControlDataManager."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD


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


def test_cache_repair_summary_uses_provider_and_returns_warning_without_errors(
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


@pytest.mark.asyncio
async def test_async_generate_report_defaults_sections_and_handles_notification_failure(
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
    assert report["feeding"]["entries"] == 1
    assert report["walks"]["entries"] == 1
    assert report["health"]["entries"] == 1
    assert "detailed_report" not in report["health"]
    assert isinstance(report["recommendations"], list)

    reports = await manager._get_namespace_data("reports")
    assert reports["buddy"]["weekly"]["report_type"] == "weekly"
    runtime.notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_generate_report_consistent_with_invalid_entries(
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
