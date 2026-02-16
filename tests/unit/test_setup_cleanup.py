"""Tests for setup.cleanup module.

Tests cleanup logic extracted from __init__.py
"""

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
  """Create mock runtime data for testing."""  # noqa: E111
  runtime_data = MagicMock(spec=PawControlRuntimeData)  # noqa: E111
  runtime_data.coordinator = MagicMock()  # noqa: E111
  runtime_data.data_manager = MagicMock()  # noqa: E111
  runtime_data.notification_manager = MagicMock()  # noqa: E111
  runtime_data.feeding_manager = MagicMock()  # noqa: E111
  runtime_data.walk_manager = MagicMock()  # noqa: E111
  runtime_data.helper_manager = MagicMock()  # noqa: E111
  runtime_data.script_manager = MagicMock()  # noqa: E111
  runtime_data.door_sensor_manager = MagicMock()  # noqa: E111
  runtime_data.geofencing_manager = MagicMock()  # noqa: E111
  runtime_data.garden_manager = MagicMock()  # noqa: E111
  runtime_data.background_monitor_task = None  # noqa: E111
  runtime_data.daily_reset_unsub = None  # noqa: E111
  runtime_data.reload_unsub = None  # noqa: E111
  return runtime_data  # noqa: E111


@pytest.mark.asyncio
async def test_async_run_manager_method_success():
  """Test successful manager method invocation."""  # noqa: E111
  manager = MagicMock()  # noqa: E111
  manager.test_method = AsyncMock(return_value=None)  # noqa: E111

  await _async_run_manager_method(  # noqa: E111
    manager,
    "test_method",
    "test description",
    timeout=10,
  )

  manager.test_method.assert_called_once()  # noqa: E111


@pytest.mark.asyncio
async def test_async_run_manager_method_none_manager():
  """Test manager method invocation with None manager."""  # noqa: E111
  await _async_run_manager_method(  # noqa: E111
    None,
    "test_method",
    "test description",
    timeout=10,
  )
  # Should not raise  # noqa: E114


@pytest.mark.asyncio
async def test_async_run_manager_method_missing_method():
  """Test manager method invocation with missing method."""  # noqa: E111
  manager = MagicMock()  # noqa: E111
  # Method doesn't exist  # noqa: E114

  await _async_run_manager_method(  # noqa: E111
    manager,
    "nonexistent_method",
    "test description",
    timeout=10,
  )
  # Should not raise  # noqa: E114


@pytest.mark.asyncio
async def test_async_run_manager_method_timeout():
  """Test manager method invocation with timeout."""  # noqa: E111
  manager = MagicMock()  # noqa: E111

  async def slow_method():  # noqa: E111
    await asyncio.sleep(10)

  manager.test_method = slow_method  # noqa: E111

  # Should timeout but not raise  # noqa: E114
  await _async_run_manager_method(  # noqa: E111
    manager,
    "test_method",
    "test description",
    timeout=0.1,
  )


@pytest.mark.asyncio
async def test_async_cancel_background_monitor_success(mock_runtime_data):
  """Test successful background monitor cancellation."""  # noqa: E111
  mock_task = AsyncMock()  # noqa: E111
  mock_task.cancel = MagicMock()  # noqa: E111
  mock_task.done = MagicMock(return_value=False)  # noqa: E111
  mock_runtime_data.background_monitor_task = mock_task  # noqa: E111

  await _async_cancel_background_monitor(mock_runtime_data)  # noqa: E111

  mock_task.cancel.assert_called_once()  # noqa: E111
  assert mock_runtime_data.background_monitor_task is None  # noqa: E111


@pytest.mark.asyncio
async def test_async_cancel_background_monitor_none_task(mock_runtime_data):
  """Test background monitor cancellation with None task."""  # noqa: E111
  mock_runtime_data.background_monitor_task = None  # noqa: E111

  await _async_cancel_background_monitor(mock_runtime_data)  # noqa: E111
  # Should not raise  # noqa: E114


@pytest.mark.asyncio
async def test_async_cleanup_managers_success(mock_runtime_data):
  """Test successful manager cleanup."""  # noqa: E111
  mock_runtime_data.door_sensor_manager.async_cleanup = AsyncMock()  # noqa: E111
  mock_runtime_data.geofencing_manager.async_cleanup = AsyncMock()  # noqa: E111
  mock_runtime_data.garden_manager.async_cleanup = AsyncMock()  # noqa: E111
  mock_runtime_data.helper_manager.async_cleanup = AsyncMock()  # noqa: E111
  mock_runtime_data.script_manager.async_cleanup = AsyncMock()  # noqa: E111

  await _async_cleanup_managers(mock_runtime_data)  # noqa: E111

  mock_runtime_data.door_sensor_manager.async_cleanup.assert_called_once()  # noqa: E111
  mock_runtime_data.geofencing_manager.async_cleanup.assert_called_once()  # noqa: E111
  mock_runtime_data.garden_manager.async_cleanup.assert_called_once()  # noqa: E111


@pytest.mark.asyncio
async def test_async_cleanup_managers_with_none_managers():
  """Test manager cleanup with None managers."""  # noqa: E111
  runtime_data = MagicMock(spec=PawControlRuntimeData)  # noqa: E111
  runtime_data.door_sensor_manager = None  # noqa: E111
  runtime_data.geofencing_manager = None  # noqa: E111
  runtime_data.garden_manager = None  # noqa: E111
  runtime_data.helper_manager = None  # noqa: E111
  runtime_data.script_manager = None  # noqa: E111

  await _async_cleanup_managers(runtime_data)  # noqa: E111
  # Should not raise  # noqa: E114


def test_remove_listeners_success(mock_runtime_data):
  """Test successful listener removal."""  # noqa: E111
  mock_runtime_data.daily_reset_unsub = MagicMock()  # noqa: E111
  mock_runtime_data.reload_unsub = MagicMock()  # noqa: E111

  _remove_listeners(mock_runtime_data)  # noqa: E111

  mock_runtime_data.daily_reset_unsub.assert_called_once()  # noqa: E111
  mock_runtime_data.reload_unsub.assert_called_once()  # noqa: E111


def test_remove_listeners_with_none(mock_runtime_data):
  """Test listener removal with None listeners."""  # noqa: E111
  mock_runtime_data.daily_reset_unsub = None  # noqa: E111
  mock_runtime_data.reload_unsub = None  # noqa: E111

  _remove_listeners(mock_runtime_data)  # noqa: E111
  # Should not raise  # noqa: E114


@pytest.mark.asyncio
async def test_async_shutdown_core_managers_success(mock_runtime_data):
  """Test successful core manager shutdown."""  # noqa: E111
  mock_runtime_data.coordinator.async_shutdown = AsyncMock()  # noqa: E111
  mock_runtime_data.data_manager.async_shutdown = AsyncMock()  # noqa: E111
  mock_runtime_data.notification_manager.async_shutdown = AsyncMock()  # noqa: E111
  mock_runtime_data.feeding_manager.async_shutdown = AsyncMock()  # noqa: E111
  mock_runtime_data.walk_manager.async_shutdown = AsyncMock()  # noqa: E111

  await _async_shutdown_core_managers(mock_runtime_data)  # noqa: E111

  mock_runtime_data.coordinator.async_shutdown.assert_called_once()  # noqa: E111
  mock_runtime_data.data_manager.async_shutdown.assert_called_once()  # noqa: E111


def test_clear_coordinator_references_success(mock_runtime_data):
  """Test successful coordinator reference clearing."""  # noqa: E111
  mock_runtime_data.coordinator.clear_runtime_managers = MagicMock()  # noqa: E111

  _clear_coordinator_references(mock_runtime_data)  # noqa: E111

  mock_runtime_data.coordinator.clear_runtime_managers.assert_called_once()  # noqa: E111


def test_clear_coordinator_references_error(mock_runtime_data):
  """Test coordinator reference clearing with error."""  # noqa: E111
  mock_runtime_data.coordinator.clear_runtime_managers = MagicMock(  # noqa: E111
    side_effect=Exception("Test error"),
  )

  _clear_coordinator_references(mock_runtime_data)  # noqa: E111
  # Should not raise  # noqa: E114


@pytest.mark.asyncio
async def test_async_cleanup_runtime_data_full_flow(mock_runtime_data):
  """Test full cleanup flow."""  # noqa: E111
  # Setup mock methods  # noqa: E114
  mock_runtime_data.background_monitor_task = None  # noqa: E111
  mock_runtime_data.door_sensor_manager.async_cleanup = AsyncMock()  # noqa: E111
  mock_runtime_data.coordinator.async_shutdown = AsyncMock()  # noqa: E111
  mock_runtime_data.coordinator.clear_runtime_managers = MagicMock()  # noqa: E111
  mock_runtime_data.daily_reset_unsub = MagicMock()  # noqa: E111
  mock_runtime_data.reload_unsub = MagicMock()  # noqa: E111

  await async_cleanup_runtime_data(mock_runtime_data)  # noqa: E111

  # Verify cleanup was called  # noqa: E114
  mock_runtime_data.door_sensor_manager.async_cleanup.assert_called_once()  # noqa: E111
  mock_runtime_data.coordinator.async_shutdown.assert_called_once()  # noqa: E111
  mock_runtime_data.coordinator.clear_runtime_managers.assert_called_once()  # noqa: E111
  mock_runtime_data.daily_reset_unsub.assert_called_once()  # noqa: E111
  mock_runtime_data.reload_unsub.assert_called_once()  # noqa: E111
