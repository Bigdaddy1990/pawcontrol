"""Gate-oriented tests for ``data_manager.py`` error, false and recovery paths."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.data_manager import (
    DogProfile,
    PawControlDataManager,
    _namespace_has_timestamp_field,
)
from custom_components.pawcontrol.exceptions import HomeAssistantError
from custom_components.pawcontrol.types import FeedingData


def _build_manager(hass: SimpleNamespace) -> PawControlDataManager:
    hass.config = SimpleNamespace(config_dir="/tmp")
    return PawControlDataManager(
        hass,
        entry_id="entry-1",
        dogs_config=[{"dog_id": "buddy", "dog_name": "Buddy"}],
    )


def _feeding_payload() -> FeedingData:
    return FeedingData(
        meal_type="breakfast",
        portion_size=100.0,
        food_type="dry_food",
        timestamp=datetime.now(UTC),
        notes="",
        logged_by="test",
        calories=350.0,
        automatic=False,
    )


# Validation cluster


def test_namespace_has_timestamp_field_returns_false_for_scalars() -> None:
    """Non-mapping/sequence payloads should hit the terminal ``return False`` branch."""
    assert _namespace_has_timestamp_field(42) is False


@pytest.mark.asyncio
async def test_async_log_feeding_returns_false_for_unknown_dog(
    hass: SimpleNamespace,
) -> None:
    """Unknown dogs must not trigger persistence side effects."""
    manager = _build_manager(hass)
    assert await manager.async_log_feeding("ghost", _feeding_payload()) is False


# Error-path cluster


@pytest.mark.asyncio
async def test_async_initialize_raises_homeassistant_error_on_storage_oserror(
    hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Storage directory errors should surface as deterministic HomeAssistantError."""
    manager = _build_manager(hass)
    monkeypatch.setattr(
        "pathlib.Path.mkdir",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("permission denied")),
    )

    with pytest.raises(
        HomeAssistantError, match="Unable to prepare PawControl storage"
    ):
        await manager.async_initialize()


@pytest.mark.asyncio
async def test_async_log_feeding_returns_false_when_save_raises(
    hass: SimpleNamespace,
) -> None:
    """Persist failures should follow the documented ``return False`` branch."""
    manager = _build_manager(hass)
    manager._dog_profiles["buddy"] = DogProfile.from_storage(
        manager._dogs_config["buddy"],
        None,
    )
    manager._async_save_dog_data = AsyncMock(side_effect=HomeAssistantError("disk"))

    result = await manager.async_log_feeding("buddy", _feeding_payload())

    assert result is False


@pytest.mark.asyncio
async def test_async_log_poop_data_returns_false_on_unknown_or_persist_error(
    hass: SimpleNamespace,
) -> None:
    """Poop log should return False for unknown dog and persistence failures."""
    manager = _build_manager(hass)
    assert await manager.async_log_poop_data("ghost", {"quality": "ok"}) is False

    manager._dog_profiles["buddy"] = DogProfile.from_storage(
        manager._dogs_config["buddy"],
        None,
    )
    manager._async_save_profile = AsyncMock(side_effect=HomeAssistantError("disk"))
    assert await manager.async_log_poop_data("buddy", {"quality": "ok"}) is False


@pytest.mark.asyncio
async def test_async_set_visitor_mode_propagates_homeassistant_error(
    hass: SimpleNamespace,
) -> None:
    """Visitor mode namespace update failures must increment error metrics and raise."""
    manager = _build_manager(hass)
    manager._update_namespace_for_dog = AsyncMock(
        side_effect=HomeAssistantError("broken")
    )

    with pytest.raises(HomeAssistantError, match="broken"):
        await manager.async_set_visitor_mode("buddy", {"enabled": True})

    assert manager._metrics["errors"] >= 1


# Recovery cluster


@pytest.mark.asyncio
async def test_async_initialize_continues_when_namespace_preload_fails(
    hass: SimpleNamespace,
) -> None:
    """Initialization should continue when namespace preload raises HomeAssistantError."""
    manager = _build_manager(hass)
    manager._async_load_storage = AsyncMock(return_value={})
    manager._get_namespace_data = AsyncMock(
        side_effect=[HomeAssistantError("cache issue"), {}, {}, {}, {}]
    )

    await manager.async_initialize()

    assert manager._initialised is True


@pytest.mark.asyncio
async def test_async_shutdown_ignores_save_errors_for_each_profile(
    hass: SimpleNamespace,
) -> None:
    """Shutdown should swallow HomeAssistantError from per-dog save attempts."""
    manager = _build_manager(hass)
    manager._initialised = True
    manager._dog_profiles["buddy"] = DogProfile.from_storage(
        manager._dogs_config["buddy"],
        None,
    )
    manager._async_save_dog_data = AsyncMock(side_effect=HomeAssistantError("io"))

    await manager.async_shutdown()

    manager._async_save_dog_data.assert_awaited_once_with("buddy")


# Result persistence cluster


@pytest.mark.asyncio
async def test_module_history_handles_unix_timestamp_parse_failures(
    hass: SimpleNamespace,
) -> None:
    """History sorting should tolerate ValueError/OverflowError timestamp conversion failures."""
    manager = _build_manager(hass)
    profile = DogProfile.from_storage(manager._dogs_config["buddy"], None)
    profile.walk_history.append({"end_time": 10**40, "distance": 1.0})
    profile.walk_history.append({"end_time": -(10**40), "distance": 2.0})
    profile.walk_history.append({
        "end_time": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "distance": 3.0,
    })
    manager._dog_profiles["buddy"] = profile

    result = await manager.async_get_module_history("walk", "buddy")

    assert len(result) == 3


@pytest.mark.asyncio
async def test_generate_report_skips_entries_with_invalid_timestamps(
    hass: SimpleNamespace,
) -> None:
    """Report generation should ignore entries that cannot be deserialized to datetimes."""
    manager = _build_manager(hass)
    profile = DogProfile.from_storage(manager._dogs_config["buddy"], None)
    profile.feeding_history.append({"timestamp": "not-a-date", "portion_size": 120.0})
    manager._dog_profiles["buddy"] = profile

    report = await manager.async_generate_report("buddy", report_type="weekly")

    assert report["feeding"]["entries"] == 0
