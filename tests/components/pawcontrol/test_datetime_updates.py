"""Tests for PawControl datetime updates and persistence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.datetime import PawControlNextFeedingDateTime
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import PawControlRuntimeData


async def _setup_runtime_data(
    hass,
    config_entry,
    coordinator,
    tmp_path,
    *,
    feeding_manager: MagicMock,
) -> PawControlDataManager:
    hass.config.config_dir = str(tmp_path)  # noqa: E111
    data_manager = PawControlDataManager(  # noqa: E111
        hass,
        coordinator=coordinator,
        dogs_config=config_entry.data["dogs"],
    )
    await data_manager.async_initialize()  # noqa: E111

    runtime_data = PawControlRuntimeData(  # noqa: E111
        coordinator=coordinator,
        data_manager=data_manager,
        notification_manager=MagicMock(),
        feeding_manager=feeding_manager,
        walk_manager=MagicMock(),
        entity_factory=EntityFactory(coordinator),
        entity_profile="standard",
        dogs=config_entry.data["dogs"],
    )
    store_runtime_data(hass, config_entry, runtime_data)  # noqa: E111
    return data_manager  # noqa: E111


@pytest.mark.asyncio
async def test_next_feeding_datetime_persists_and_refreshes(
    mock_hass,
    mock_config_entry,
    mock_coordinator,
    tmp_path,
) -> None:
    feeding_manager = MagicMock()  # noqa: E111
    feeding_manager.async_refresh_reminder = AsyncMock()  # noqa: E111
    data_manager = await _setup_runtime_data(  # noqa: E111
        mock_hass,
        mock_config_entry,
        mock_coordinator,
        tmp_path,
        feeding_manager=feeding_manager,
    )
    entity = PawControlNextFeedingDateTime(  # noqa: E111
        mock_coordinator,
        "test_dog",
        "Buddy",
    )
    entity.hass = mock_hass  # noqa: E111

    reminder_time = datetime(2024, 1, 2, 9, 30, tzinfo=UTC)  # noqa: E111
    await entity.async_set_value(reminder_time)  # noqa: E111

    assert (  # noqa: E111
        data_manager._dogs_config["test_dog"]["feeding"]["next_feeding"]
        == reminder_time.isoformat()
    )
    assert (  # noqa: E111
        mock_coordinator.data["test_dog"]["feeding"]["next_feeding"]
        == reminder_time.isoformat()
    )
    feeding_manager.async_refresh_reminder.assert_awaited_once_with("test_dog")  # noqa: E111
