"""Additional coverage for data manager export executor code paths."""

from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD


async def _inline_executor(func, *args):
    return func(*args)


async def _create_manager(mock_hass: object, tmp_path: Path) -> PawControlDataManager:
    mock_hass.config.config_dir = str(tmp_path)  # type: ignore[attr-defined]
    manager = PawControlDataManager(
        mock_hass,  # type: ignore[arg-type]
        entry_id="entry-1",
        dogs_config=[{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
    )
    manager._async_load_storage = AsyncMock(return_value={})  # type: ignore[method-assign]
    manager._write_storage = AsyncMock()  # type: ignore[method-assign]
    manager._async_add_executor_job = _inline_executor  # type: ignore[method-assign]
    await manager.async_initialize()
    return manager


@pytest.mark.asyncio
async def test_async_export_data_routes_json_serializes_sequence_content(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(
                return_value={
                    "filename": "routes.json",
                    "content": [
                        {"lat": 45.0, "lon": 19.0},
                        {"lat": 45.1, "lon": 19.1},
                    ],
                },
            ),
        ),
    )

    export_path = await manager.async_export_data("buddy", "routes", format="json")

    assert export_path.name == "routes.json"
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload[0]["lat"] == 45.0
    assert payload[1]["lon"] == 19.1


@pytest.mark.asyncio
async def test_async_export_data_routes_json_wraps_none_content_with_raw_null(
    mock_hass: object,
    tmp_path: Path,
) -> None:
    manager = await _create_manager(mock_hass, tmp_path)
    manager._get_runtime_data = lambda: SimpleNamespace(  # type: ignore[method-assign]
        gps_geofence_manager=SimpleNamespace(
            async_export_routes=AsyncMock(
                return_value={
                    "filename": "routes.json",
                    "content": None,
                },
            ),
        ),
    )

    export_path = await manager.async_export_data(
        "buddy",
        "routes",
        format="json",
        date_from=datetime(2026, 1, 1, tzinfo=UTC),
        date_to=datetime(2026, 1, 2, tzinfo=UTC),
    )

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload == {"raw_content": None}
