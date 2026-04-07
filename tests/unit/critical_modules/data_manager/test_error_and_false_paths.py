"""Focused error-path unit tests for ``data_manager.py``."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.data_manager import DogProfile, PawControlDataManager
from custom_components.pawcontrol.exceptions import HomeAssistantError
from custom_components.pawcontrol.types import FeedingData


@pytest.mark.asyncio
async def test_async_initialize_raises_homeassistant_error_on_storage_oserror(
    hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Storage directory errors should surface as deterministic HomeAssistantError."""
    hass.config = SimpleNamespace(config_dir="/tmp")
    manager = PawControlDataManager(
        hass,
        entry_id="entry-1",
        dogs_config=[{"dog_id": "buddy", "dog_name": "Buddy"}],
    )
    monkeypatch.setattr(
        "pathlib.Path.mkdir",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("permission denied")),
    )

    with pytest.raises(HomeAssistantError, match="Unable to prepare PawControl storage"):
        await manager.async_initialize()


@pytest.mark.asyncio
async def test_async_log_feeding_returns_false_when_save_raises(
    hass: SimpleNamespace,
) -> None:
    """Persist failures should follow the documented ``return False`` branch."""
    hass.config = SimpleNamespace(config_dir="/tmp")
    manager = PawControlDataManager(
        hass,
        entry_id="entry-1",
        dogs_config=[{"dog_id": "buddy", "dog_name": "Buddy"}],
    )
    manager._dog_profiles["buddy"] = DogProfile.from_storage(
        manager._dogs_config["buddy"],
        None,
    )
    manager._async_save_dog_data = AsyncMock(side_effect=HomeAssistantError("disk"))

    result = await manager.async_log_feeding(
        "buddy",
        FeedingData(
            meal_type="breakfast",
            portion_size=100.0,
            food_type="dry_food",
            timestamp=datetime.now(UTC),
            notes="",
            logged_by="test",
            calories=350.0,
            automatic=False,
        ),
    )

    assert result is False
