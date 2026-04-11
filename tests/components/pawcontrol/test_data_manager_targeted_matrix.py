from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD


async def _create_manager(mock_hass: object, tmp_path: Path) -> PawControlDataManager:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-targeted",
        dogs_config=[{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
    )
    manager._async_load_storage = AsyncMock(return_value={})  # type: ignore[method-assign]
    manager._write_storage = AsyncMock()  # type: ignore[method-assign]
    await manager.async_initialize()

    async def _run_inline(func: object, *args: object) -> object:
        return func(*args)  # type: ignore[misc]

    manager._async_add_executor_job = _run_inline  # type: ignore[method-assign]
    return manager


@pytest.mark.asyncio
async def test_async_get_module_history_filters_sorts_and_limits(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [
        {"timestamp": "2026-01-03T10:00:00+00:00", "portion_size": 20},
        {"timestamp": "2026-01-01T10:00:00+00:00", "portion_size": 10},
        {"timestamp": "2026-01-02T10:00:00+00:00", "portion_size": 15},
    ]

    history = await manager.async_get_module_history(
        "feeding",
        "buddy",
        since=datetime(2026, 1, 2, tzinfo=UTC),
        until=datetime(2026, 1, 3, 23, 59, tzinfo=UTC),
        limit=1,
    )

    assert len(history) == 1
    assert history[0]["timestamp"] == "2026-01-03T10:00:00+00:00"
    assert history[0]["portion_size"] == 20


@pytest.mark.asyncio
async def test_async_get_module_history_handles_inconsistent_entries(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.walk_history = [
        {"end_time": "not-a-date", "distance": 1.0},
        {"end_time": 9_999_999_999_999_999_999, "distance": 3.0},
        "invalid-entry",
        {"end_time": "2026-01-02T10:00:00+00:00", "distance": 2.0},
    ]

    history = await manager.async_get_module_history("walk", "buddy")

    assert len(history) == 3
    assert history[0]["distance"] == 2.0
    assert sorted(item["distance"] for item in history[1:]) == [1.0, 3.0]


@pytest.mark.asyncio
async def test_async_get_module_history_returns_empty_for_unknown_module_or_profile(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    assert await manager.async_get_module_history("unknown", "buddy") == []
    assert await manager.async_get_module_history("feeding", "missing-dog") == []


@pytest.mark.asyncio
async def test_async_get_module_history_returns_empty_when_profile_payload_not_list(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = cast(list[dict[str, object]], "not-a-list")

    history = await manager.async_get_module_history("feeding", "buddy")

    assert history == []


@pytest.mark.asyncio
async def test_async_get_module_history_filters_bad_entries_with_bounds(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [
        {"timestamp": "2026-01-04T09:00:00+00:00", "portion_size": 45},
        {"timestamp": "not-a-date", "portion_size": 15},
        {"timestamp": None, "portion_size": 10},
    ]

    history = await manager.async_get_module_history(
        "feeding",
        "buddy",
        since="2026-01-03T00:00:00+00:00",
        until="2026-01-05T00:00:00+00:00",
    )

    assert history == [
        {"timestamp": "2026-01-04T09:00:00+00:00", "portion_size": 45},
    ]


@pytest.mark.asyncio
async def test_async_export_data_json_path_returns_business_payload(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].feeding_history = [
        {"timestamp": "2026-01-01T08:00:00+00:00", "portion_size": 10.0},
        {"timestamp": "2026-01-02T08:00:00+00:00", "portion_size": 20.0},
    ]

    export_path = await manager.async_export_data(
        "buddy",
        "feeding",
        format="json",
        date_from="2026-01-02T00:00:00+00:00",
        date_to="2026-01-02T23:59:00+00:00",
    )

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["dog_id"] == "buddy"
    assert payload["data_type"] == "feeding"
    assert [entry["portion_size"] for entry in payload["entries"]] == [20.0]


@pytest.mark.asyncio
async def test_async_export_data_routes_adapter_failures_and_fallback(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    export_mock = AsyncMock(return_value={"content": "<gpx />"})
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        gps_geofence_manager=SimpleNamespace(async_export_routes=export_mock),
    )

    route_path = await manager.async_export_data("buddy", "routes", format="invalid")

    assert route_path.suffix == ".gpx"
    kwargs = export_mock.await_args.kwargs
    assert kwargs["export_format"] == "gpx"

    manager._get_runtime_data = lambda: SimpleNamespace()  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError, match="GPS manager not available"):
        await manager.async_export_data("buddy", "routes")


@pytest.mark.asyncio
async def test_async_generate_report_tolerates_adapter_exceptions_and_persists(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    now = datetime(2026, 1, 5, tzinfo=UTC)
    profile = manager._dog_profiles["buddy"]
    profile.feeding_history = [
        {"timestamp": (now - timedelta(days=1)).isoformat(), "portion_size": 42.0},
    ]
    profile.walk_history = [{"end_time": "invalid", "distance": 3.5}]
    profile.health_history = [{"timestamp": "invalid", "status": "ok"}]
    runtime = SimpleNamespace(
        feeding_manager=SimpleNamespace(
            async_generate_health_report=AsyncMock(
                side_effect=RuntimeError("adapter down")
            ),
        ),
        notification_manager=SimpleNamespace(
            async_send_notification=AsyncMock(side_effect=RuntimeError("notify down")),
        ),
    )
    manager._get_runtime_data = lambda: runtime  # type: ignore[method-assign]

    report = await manager.async_generate_report(
        "buddy",
        "weekly",
        start_date=(now - timedelta(days=2)).isoformat(),
        end_date=now.isoformat(),
        include_recommendations=True,
        send_notification=True,
    )

    assert report["feeding"]["entries"] == 1
    assert report["walks"]["entries"] == 0
    assert report["health"]["entries"] == 0
    assert "detailed_report" not in report["health"]
    assert (
        "Schedule regular walks to maintain activity levels."
        in report["recommendations"]
    )
    reports_namespace = manager._namespace_state.get("reports")
    assert isinstance(reports_namespace, dict)
    reports_dump = json.dumps(reports_namespace)
    assert '"report_type": "weekly"' in reports_dump


@pytest.mark.asyncio
async def test_async_export_data_all_allow_partial_captures_homeassistant_and_io_errors(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].feeding_history = [
        {"timestamp": "2026-01-02T08:00:00+00:00", "portion_size": 10.0},
    ]
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(side_effect=OSError("disk offline")),
        ),
    )

    manifest_path = await manager.async_export_data(
        "buddy",
        "all",
        allow_partial=True,
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["data_type"] == "all"
    assert "feeding" in payload["exports"]
    assert "walks" in payload["exports"]
    assert payload["errors"]["garden"] == "Garden manager not available for export"
    assert payload["errors"]["routes"].startswith("I/O error: disk offline")


@pytest.mark.asyncio
async def test_async_export_data_all_allow_partial_raises_when_every_export_fails(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    """allow_partial should still fail when no export artifact can be produced."""
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace()  # type: ignore[method-assign]
    manager._async_add_executor_job = AsyncMock(  # type: ignore[method-assign]
        side_effect=OSError("disk full"),
    )

    with pytest.raises(
        HomeAssistantError,
        match="Failed to export any data type while allow_partial=True",
    ):
        await manager.async_export_data(
            "buddy",
            "all",
            allow_partial=True,
        )


@pytest.mark.asyncio
async def test_async_export_data_rejects_unsupported_data_type(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    """Unknown export types should raise a user-facing validation error."""
    manager = await _create_manager(mock_hass, tmp_path)

    with pytest.raises(HomeAssistantError, match="Unsupported export data type"):
        await manager.async_export_data("buddy", "sleeping")


def test_cache_repair_summary_classifies_normal_corrupt_and_error_states(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-targeted",
        dogs_config=[],
    )

    summary = manager.cache_repair_summary(
        {
            "healthy": {
                "stats": {"entries": 2, "hits": 8, "misses": 2},
                "diagnostics": {},
            },
            "corrupt": {
                "stats": {"entries": "bad", "hits": "3", "misses": "2"},
                "diagnostics": {
                    "expired_entries": "5",
                    "pending_expired_entries": "x",
                    "errors": "adapter-timeout",
                    "timestamp_anomalies": {"buddy": 123},
                },
            },
        },
    )

    assert summary is not None
    assert summary["severity"] == "error"
    assert summary["totals"]["hits"] == 11
    assert summary["totals"]["misses"] == 4
    assert summary["totals"]["expired_entries"] == 5
    assert summary["caches_with_errors"] == ["corrupt"]
    issues = summary["issues"]
    assert issues is not None
    assert issues[0]["errors"] == ["adapter-timeout"]
    assert issues[0]["timestamp_anomalies"] == {"buddy": "123"}
