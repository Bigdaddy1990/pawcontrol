"""Tests for setup.cleanup module.

Tests cleanup logic extracted from __init__.py
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.setup.cleanup import (
    _async_cancel_background_monitor,
    _async_cleanup_managers,
    _async_run_manager_method,
    _async_shutdown_core_managers,
    _clear_coordinator_references,
    _remove_listeners,
    async_cleanup_runtime_data,
)
from custom_components.pawcontrol.types import PawControlRuntimeData


@pytest.fixture
def mock_runtime_data() -> PawControlRuntimeData:
    """Create mock runtime data for testing."""
    runtime_data = MagicMock(spec=PawControlRuntimeData)
    runtime_data.coordinator = MagicMock()
    runtime_data.data_manager = MagicMock()
    runtime_data.notification_manager = MagicMock()
    runtime_data.feeding_manager = MagicMock()
    runtime_data.walk_manager = MagicMock()
    runtime_data.helper_manager = MagicMock()
    runtime_data.script_manager = MagicMock()
    runtime_data.door_sensor_manager = MagicMock()
    runtime_data.geofencing_manager = MagicMock()
    runtime_data.garden_manager = MagicMock()
    runtime_data.background_monitor_task = None
    runtime_data.daily_reset_unsub = None
    runtime_data.reload_unsub = None
    return runtime_data


@pytest.mark.asyncio
async def test_async_run_manager_method_success():
    """Test successful manager method invocation."""
    manager = MagicMock()
    manager.test_method = AsyncMock(return_value=None)

    await _async_run_manager_method(
        manager,
        "test_method",
        "test description",
        timeout=10,
    )

    manager.test_method.assert_called_once()


@pytest.mark.asyncio
async def test_async_run_manager_method_none_manager():
    """Test manager method invocation with None manager."""
    await _async_run_manager_method(
        None,
        "test_method",
        "test description",
        timeout=10,
    )
    # Should not raise


@pytest.mark.asyncio
async def test_async_run_manager_method_missing_method():
    """Test manager method invocation with missing method."""
    manager = MagicMock()
    # Method doesn't exist

    await _async_run_manager_method(
        manager,
        "nonexistent_method",
        "test description",
        timeout=10,
    )
    # Should not raise


@pytest.mark.asyncio
async def test_async_run_manager_method_timeout():
    """Test manager method invocation with timeout."""
    manager = MagicMock()

    async def slow_method():
        await asyncio.sleep(10)

    manager.test_method = slow_method

    # Should timeout but not raise
    await _async_run_manager_method(
        manager,
        "test_method",
        "test description",
        timeout=0.1,
    )


@pytest.mark.asyncio
async def test_async_cancel_background_monitor_success(mock_runtime_data):
    """Test successful background monitor cancellation."""
    mock_task = AsyncMock()
    mock_task.cancel = MagicMock()
    mock_task.done = MagicMock(return_value=False)
    mock_runtime_data.background_monitor_task = mock_task

    await _async_cancel_background_monitor(mock_runtime_data)

    mock_task.cancel.assert_called_once()
    assert mock_runtime_data.background_monitor_task is None


@pytest.mark.asyncio
async def test_async_cancel_background_monitor_none_task(mock_runtime_data):
    """Test background monitor cancellation with None task."""
    mock_runtime_data.background_monitor_task = None

    await _async_cancel_background_monitor(mock_runtime_data)
    # Should not raise


@pytest.mark.asyncio
async def test_async_cleanup_managers_success(mock_runtime_data):
    """Test successful manager cleanup."""
    mock_runtime_data.door_sensor_manager.async_cleanup = AsyncMock()
    mock_runtime_data.geofencing_manager.async_cleanup = AsyncMock()
    mock_runtime_data.garden_manager.async_cleanup = AsyncMock()
    mock_runtime_data.helper_manager.async_cleanup = AsyncMock()
    mock_runtime_data.script_manager.async_cleanup = AsyncMock()

    await _async_cleanup_managers(mock_runtime_data)

    mock_runtime_data.door_sensor_manager.async_cleanup.assert_called_once()
    mock_runtime_data.geofencing_manager.async_cleanup.assert_called_once()
    mock_runtime_data.garden_manager.async_cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_async_cleanup_managers_with_none_managers():
    """Test manager cleanup with None managers."""
    runtime_data = MagicMock(spec=PawControlRuntimeData)
    runtime_data.door_sensor_manager = None
    runtime_data.geofencing_manager = None
    runtime_data.garden_manager = None
    runtime_data.helper_manager = None
    runtime_data.script_manager = None

    await _async_cleanup_managers(runtime_data)
    # Should not raise


def test_remove_listeners_success(mock_runtime_data):
    """Test successful listener removal."""
    mock_runtime_data.daily_reset_unsub = MagicMock()
    mock_runtime_data.reload_unsub = MagicMock()

    _remove_listeners(mock_runtime_data)

    mock_runtime_data.daily_reset_unsub.assert_called_once()
    mock_runtime_data.reload_unsub.assert_called_once()


def test_remove_listeners_with_none(mock_runtime_data):
    """Test listener removal with None listeners."""
    mock_runtime_data.daily_reset_unsub = None
    mock_runtime_data.reload_unsub = None

    _remove_listeners(mock_runtime_data)
    # Should not raise


@pytest.mark.asyncio
async def test_async_shutdown_core_managers_success(mock_runtime_data):
    """Test successful core manager shutdown."""
    mock_runtime_data.coordinator.async_shutdown = AsyncMock()
    mock_runtime_data.data_manager.async_shutdown = AsyncMock()
    mock_runtime_data.notification_manager.async_shutdown = AsyncMock()
    mock_runtime_data.feeding_manager.async_shutdown = AsyncMock()
    mock_runtime_data.walk_manager.async_shutdown = AsyncMock()

    await _async_shutdown_core_managers(mock_runtime_data)

    mock_runtime_data.coordinator.async_shutdown.assert_called_once()
    mock_runtime_data.data_manager.async_shutdown.assert_called_once()


def test_clear_coordinator_references_success(mock_runtime_data):
    """Test successful coordinator reference clearing."""
    mock_runtime_data.coordinator.clear_runtime_managers = MagicMock()

    _clear_coordinator_references(mock_runtime_data)

    mock_runtime_data.coordinator.clear_runtime_managers.assert_called_once()


def test_clear_coordinator_references_error(mock_runtime_data):
    """Test coordinator reference clearing with error."""
    mock_runtime_data.coordinator.clear_runtime_managers = MagicMock(
        side_effect=Exception("Test error"),
    )

    _clear_coordinator_references(mock_runtime_data)
    # Should not raise


@pytest.mark.asyncio
async def test_async_cleanup_runtime_data_full_flow(mock_runtime_data):
    """Test full cleanup flow."""
    # Setup mock methods
    mock_runtime_data.background_monitor_task = None
    mock_runtime_data.door_sensor_manager.async_cleanup = AsyncMock()
    mock_runtime_data.coordinator.async_shutdown = AsyncMock()
    mock_runtime_data.coordinator.clear_runtime_managers = MagicMock()
    mock_runtime_data.daily_reset_unsub = MagicMock()
    mock_runtime_data.reload_unsub = MagicMock()

    await async_cleanup_runtime_data(mock_runtime_data)

    # Verify cleanup was called
    mock_runtime_data.door_sensor_manager.async_cleanup.assert_called_once()
    mock_runtime_data.coordinator.async_shutdown.assert_called_once()
    mock_runtime_data.coordinator.clear_runtime_managers.assert_called_once()
    mock_runtime_data.daily_reset_unsub.assert_called_once()
    mock_runtime_data.reload_unsub.assert_called_once()
