from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol.const import DOMAIN
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


@pytest.mark.asyncio
async def test_async_export_data_writes_markdown_for_export_single(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].feeding_history = [
        {
            "timestamp": datetime(2026, 1, 5, tzinfo=UTC).isoformat(),
            "portion_size": 42,
        },
    ]

    export_path = await manager.async_export_data("buddy", "feeding", format="markdown")

    assert export_path.suffix == ".md"
    exported = export_path.read_text(encoding="utf-8")
    assert "# Feeding export for buddy" in exported
    assert "portion_size: 42" in exported


@pytest.mark.asyncio
async def test_async_export_data_routes_uses_gpx_fallback_and_default_filename(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(
                return_value={
                    "content": "<gpx />",
                },
            ),
        ),
    )

    export_path = await manager.async_export_data("buddy", "routes", format="invalid")

    assert export_path.suffix == ".gpx"
    assert export_path.read_text(encoding="utf-8") == "<gpx />"


@pytest.mark.asyncio
async def test_async_export_data_all_manifest_is_consistent_on_success(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].feeding_history = [
        {"timestamp": "2026-01-01T10:00:00+00:00", "portion_size": 10.0},
    ]
    manager._dog_profiles["buddy"].walk_history = [
        {"end_time": "2026-01-01T11:00:00+00:00", "distance": 1.0},
    ]
    manager._dog_profiles["buddy"].health_history = [
        {"timestamp": "2026-01-01T12:00:00+00:00", "status": "ok"},
    ]
    manager._dog_profiles["buddy"].medication_history = [
        {
            "administration_time": "2026-01-01T13:00:00+00:00",
            "name": "sample",
        },
    ]
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        garden_manager=SimpleNamespace(
            async_export_sessions=AsyncMock(
                return_value=tmp_path / DOMAIN / "exports" / "garden.json",
            ),
        ),
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(
                return_value={"filename": "routes.json", "content": "{}"},
            ),
        ),
    )

    manifest_path = await manager.async_export_data("buddy", "all", format="json")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["dog_id"] == "buddy"
    assert payload["data_type"] == "all"
    assert sorted(payload["exports"]) == [
        "feeding",
        "garden",
        "health",
        "medication",
        "routes",
        "walks",
    ]


@pytest.mark.asyncio
async def test_async_export_data_routes_rejects_missing_payload(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(return_value=None),
        ),
    )

    with pytest.raises(HomeAssistantError, match="No GPS routes available"):
        await manager.async_export_data("buddy", "routes", format="json")


@pytest.mark.asyncio
async def test_async_export_data_supports_csv_export_single(mock_hass: object, tmp_path: Path) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].feeding_history = [
        {"timestamp": "2026-01-05T07:30:00+00:00", "portion_size": 50.0, "meal_type": "breakfast"},
    ]

    export_path = await manager.async_export_data("buddy", "feeding", format="csv")

    text = export_path.read_text(encoding="utf-8")
    assert export_path.suffix == ".csv"
    assert "meal_type" in text
    assert "breakfast" in text


@pytest.mark.asyncio
async def test_async_export_data_falls_back_to_json_for_unknown_format(mock_hass: object, tmp_path: Path) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].health_history = [
        {"timestamp": "2026-01-05T07:30:00+00:00", "status": "ok"},
    ]

    export_path = await manager.async_export_data("buddy", "health", format="xml")
    payload = json.loads(export_path.read_text(encoding="utf-8"))

    assert export_path.suffix == ".json"
    assert payload["data_type"] == "health"
    assert payload["entries"][0]["status"] == "ok"


@pytest.mark.asyncio
async def test_async_export_data_routes_json_wraps_invalid_content(mock_hass: object, tmp_path: Path) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(
                return_value={"filename": "routes.json", "content": object()},
            ),
        ),
    )

    export_path = await manager.async_export_data("buddy", "routes", format="json")
    payload = json.loads(export_path.read_text(encoding="utf-8"))

    assert "raw_content" in payload


@pytest.mark.asyncio
async def test_async_export_data_raises_when_export_single_receives_unsupported_type(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)

    with pytest.raises(HomeAssistantError, match="Unsupported export data type"):
        await manager.async_export_data("buddy", "unknown-module")


@pytest.mark.asyncio
async def test_async_export_data_raises_without_garden_manager(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace()  # type: ignore[method-assign]

    with pytest.raises(HomeAssistantError, match="Garden manager not available"):
        await manager.async_export_data("buddy", "garden")


@pytest.mark.asyncio
async def test_async_export_data_raises_without_routes_manager(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace()  # type: ignore[method-assign]

    with pytest.raises(HomeAssistantError, match="GPS manager not available"):
        await manager.async_export_data("buddy", "routes")


@pytest.mark.asyncio
async def test_async_export_data_routes_bubbles_type_error_from_bad_filename(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(
                return_value={"filename": 1234, "content": "{}"},
            ),
        ),
    )

    with pytest.raises(TypeError):
        await manager.async_export_data("buddy", "routes", format="json")


@pytest.mark.asyncio
async def test_async_export_data_all_propagates_export_exception(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._dog_profiles["buddy"].feeding_history = []
    manager._dog_profiles["buddy"].walk_history = []
    manager._dog_profiles["buddy"].health_history = []
    manager._dog_profiles["buddy"].medication_history = []
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        garden_manager=SimpleNamespace(
            async_export_sessions=AsyncMock(side_effect=RuntimeError("garden boom")),
        ),
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(return_value={"content": "<gpx />"}),
        ),
    )

    with pytest.raises(RuntimeError, match="garden boom"):
        await manager.async_export_data("buddy", "all")
