"""Regression tests for coordinator refresh lifecycle behaviour."""

from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.coordinator import (
    PawControlCoordinator,
    RuntimeCycleInfo,
)
from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed, UpdateFailed


def _cycle_info(*, success: bool = True) -> RuntimeCycleInfo:
    """Build a minimal runtime cycle summary used by refresh tests."""
    return RuntimeCycleInfo(
        dog_count=1,
        errors=0 if success else 1,
        success_rate=1.0 if success else 0.0,
        duration=0.01,
        new_interval=30.0,
        error_ratio=0.0 if success else 1.0,
        success=success,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_first_refresh_success_sets_data(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Initial successful refresh should populate coordinator cache."""
    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    payload = {"test_dog": {"status": "online", "last_update": "now"}}
    coordinator._execute_cycle = AsyncMock(return_value=(payload, _cycle_info()))
    coordinator._synchronize_module_states = AsyncMock()

    result = await coordinator._async_update_data()

    assert result == payload
    assert coordinator._data == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_timeout_marks_unavailable(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Timeout failures are wrapped and should leave coordinator unavailable."""
    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coordinator._execute_cycle = AsyncMock(side_effect=TimeoutError("timed out"))

    with pytest.raises(UpdateFailed, match="Coordinator update failed"):
        await coordinator._async_update_data()

    # DataUpdateCoordinator bookkeeping marks refresh failures as unsuccessful.
    coordinator.last_update_success = False
    assert coordinator.available is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_auth_error_triggers_auth_path(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Authentication failures must propagate as ConfigEntryAuthFailed."""
    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coordinator._execute_cycle = AsyncMock(
        side_effect=ConfigEntryAuthFailed("token invalid")
    )

    with pytest.raises(ConfigEntryAuthFailed, match="token invalid"):
        await coordinator._async_update_data()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_partial_payload_handles_missing_keys(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Refresh accepts partial payloads and keeps processing without crashes."""
    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    partial_payload = {"test_dog": {"status": "online"}}
    coordinator._execute_cycle = AsyncMock(return_value=(partial_payload, _cycle_info()))

    result = await coordinator._async_update_data()

    assert result["test_dog"]["status"] == "online"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_recovery_after_failure(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """A successful refresh after failure should restore availability."""
    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    payload = {"test_dog": {"status": "online", "last_update": "recovered"}}
    coordinator._execute_cycle = AsyncMock(
        side_effect=[UpdateFailed("network down"), (payload, _cycle_info())]
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    coordinator.last_update_success = False
    assert coordinator.available is False

    await coordinator._async_update_data()

    coordinator.last_update_success = True
    assert coordinator.available is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_state_mutation_on_failed_refresh(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Failed refreshes must not mutate the last known good payload."""
    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    previous_payload = {
        "test_dog": {"status": "online", "last_update": "previous", "walk": {}}
    }
    coordinator._data = dict(previous_payload)
    coordinator._execute_cycle = AsyncMock(side_effect=UpdateFailed("backend unavailable"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert coordinator._data == previous_payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_interval_or_manual_refresh_behavior(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Manual selective refresh should trigger subset execution and broadcast."""
    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coordinator._data = {"test_dog": {"status": "stale"}}
    refreshed_payload = {"test_dog": {"status": "online", "last_update": "manual"}}
    coordinator._execute_cycle = AsyncMock(return_value=(refreshed_payload, _cycle_info()))
    coordinator._synchronize_module_states = AsyncMock()
    coordinator.async_set_updated_data = AsyncMock()  # type: ignore[assignment]

    await coordinator.async_request_selective_refresh(["test_dog"])

    coordinator._execute_cycle.assert_awaited_once()
    coordinator.async_set_updated_data.assert_called_once()
    assert coordinator._data["test_dog"]["status"] == "online"
