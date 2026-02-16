"""Cleanup and shutdown logic for PawControl.

Extracted from __init__.py to isolate resource cleanup.
Handles manager shutdown, listener removal, and background task cancellation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from homeassistant.core import HomeAssistant  # noqa: E111

  from ..types import PawControlConfigEntry, PawControlRuntimeData  # noqa: E111

_LOGGER = logging.getLogger(__name__)

# Timeout for cleanup operations
_CLEANUP_TIMEOUT: int = 10  # seconds per manager


async def async_cleanup_runtime_data(runtime_data: PawControlRuntimeData) -> None:
  """Release all resources held by runtime data.

  Args:
      runtime_data: Runtime data to clean up

  Example:
      >>> await async_cleanup_runtime_data(runtime_data)
      # All managers shut down, listeners removed, tasks cancelled
  """  # noqa: E111
  cleanup_start = time.monotonic()  # noqa: E111

  # Cancel background monitoring task  # noqa: E114
  await _async_cancel_background_monitor(runtime_data)  # noqa: E111

  # Clean up managers  # noqa: E114
  await _async_cleanup_managers(runtime_data)  # noqa: E111

  # Remove listeners  # noqa: E114
  _remove_listeners(runtime_data)  # noqa: E111

  # Shutdown core managers  # noqa: E114
  await _async_shutdown_core_managers(runtime_data)  # noqa: E111

  # Clear coordinator references  # noqa: E114
  _clear_coordinator_references(runtime_data)  # noqa: E111

  cleanup_duration = time.monotonic() - cleanup_start  # noqa: E111
  _LOGGER.debug(  # noqa: E111
    "Runtime data cleanup completed in %.2f seconds",
    cleanup_duration,
  )


async def async_register_cleanup(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
  runtime_data: PawControlRuntimeData,
) -> None:
  """Register cleanup handlers for the entry.

  Args:
      hass: Home Assistant instance
      entry: Config entry
      runtime_data: Runtime data
  """  # noqa: E111
  # Add reload listener  # noqa: E114
  reload_unsub = entry.add_update_listener(_async_reload_entry_wrapper(hass))  # noqa: E111
  if callable(reload_unsub):  # noqa: E111
    runtime_data.reload_unsub = reload_unsub
    if hasattr(entry, "async_on_unload"):
      entry.async_on_unload(reload_unsub)  # noqa: E111

  _LOGGER.debug("Registered cleanup handlers for entry %s", entry.entry_id)  # noqa: E111


def _async_reload_entry_wrapper(
  hass: HomeAssistant,
) -> Callable[[HomeAssistant, PawControlConfigEntry], Any]:
  """Create a wrapper for async_reload_entry to match expected signature.

  Args:
      hass: Home Assistant instance

  Returns:
      Async function that reloads the entry
  """  # noqa: E111

  async def _reload(  # noqa: E111
    hass_inner: HomeAssistant,
    entry: PawControlConfigEntry,
  ) -> None:
    """Reload the config entry."""
    from .. import async_reload_entry

    await async_reload_entry(hass_inner, entry)

  return _reload  # noqa: E111


async def _async_cancel_background_monitor(runtime_data: PawControlRuntimeData) -> None:
  """Cancel background monitoring task.

  Args:
      runtime_data: Runtime data
  """  # noqa: E111
  monitor_task = getattr(runtime_data, "background_monitor_task", None)  # noqa: E111
  if monitor_task:  # noqa: E111
    monitor_task.cancel()
    try:
      await monitor_task  # noqa: E111
    except asyncio.CancelledError:
      _LOGGER.debug("Background monitor task cancelled")  # noqa: E111
    except Exception as err:
      _LOGGER.warning(  # noqa: E111
        "Error while awaiting background monitor task: %s",
        err,
      )
    finally:
      runtime_data.background_monitor_task = None  # noqa: E111


async def _async_cleanup_managers(runtime_data: PawControlRuntimeData) -> None:
  """Clean up optional managers.

  Args:
      runtime_data: Runtime data
  """  # noqa: E111
  managers = [  # noqa: E111
    ("door_sensor_manager", getattr(runtime_data, "door_sensor_manager", None)),
    ("geofencing_manager", getattr(runtime_data, "geofencing_manager", None)),
    ("garden_manager", getattr(runtime_data, "garden_manager", None)),
    ("helper_manager", getattr(runtime_data, "helper_manager", None)),
    ("script_manager", getattr(runtime_data, "script_manager", None)),
  ]

  for manager_name, manager in managers:  # noqa: E111
    if manager is not None:
      await _async_run_manager_method(  # noqa: E111
        manager,
        "async_cleanup",
        f"{manager_name} cleanup",
        timeout=_CLEANUP_TIMEOUT,
      )


def _remove_listeners(runtime_data: PawControlRuntimeData) -> None:
  """Remove event listeners.

  Args:
      runtime_data: Runtime data
  """  # noqa: E111
  # Remove daily reset scheduler  # noqa: E114
  if getattr(runtime_data, "daily_reset_unsub", None):  # noqa: E111
    try:
      runtime_data.daily_reset_unsub()  # noqa: E111
    except Exception as err:
      _LOGGER.warning("Error canceling daily reset scheduler: %s", err)  # noqa: E111

  # Remove reload listener  # noqa: E114
  reload_unsub = getattr(runtime_data, "reload_unsub", None)  # noqa: E111
  if callable(reload_unsub):  # noqa: E111
    try:
      reload_unsub()  # noqa: E111
    except Exception as err:
      _LOGGER.warning("Error removing config entry listener: %s", err)  # noqa: E111


async def _async_shutdown_core_managers(runtime_data: PawControlRuntimeData) -> None:
  """Shut down core managers.

  Args:
      runtime_data: Runtime data
  """  # noqa: E111
  core_managers = [  # noqa: E111
    ("Coordinator", runtime_data.coordinator),
    ("Data manager", runtime_data.data_manager),
    ("Notification manager", runtime_data.notification_manager),
    ("Feeding manager", runtime_data.feeding_manager),
    ("Walk manager", runtime_data.walk_manager),
  ]

  for manager_name, manager in core_managers:  # noqa: E111
    await _async_run_manager_method(
      manager,
      "async_shutdown",
      f"{manager_name} shutdown",
      timeout=_CLEANUP_TIMEOUT,
    )


def _clear_coordinator_references(runtime_data: PawControlRuntimeData) -> None:
  """Clear coordinator manager references.

  Args:
      runtime_data: Runtime data
  """  # noqa: E111
  try:  # noqa: E111
    runtime_data.coordinator.clear_runtime_managers()
  except Exception as err:  # noqa: E111
    _LOGGER.warning("Error clearing coordinator references: %s", err)


async def _async_run_manager_method(
  manager: Any,
  method_name: str,
  description: str,
  *,
  timeout: float,
) -> None:
  """Invoke manager method and await result if necessary.

  Args:
      manager: Manager instance
      method_name: Name of method to invoke
      description: Description for logging
      timeout: Timeout in seconds
  """  # noqa: E111
  if manager is None:  # noqa: E111
    return

  method = getattr(manager, method_name, None)  # noqa: E111
  if method is None:  # noqa: E111
    return

  try:  # noqa: E111
    result = method()
  except Exception as err:  # noqa: E111
    _LOGGER.warning(
      "Error starting %s: %s",
      description,
      err,
      exc_info=True,
    )
    return

  try:  # noqa: E111
    # Check if result is awaitable
    if hasattr(result, "__await__"):
      await asyncio.wait_for(result, timeout=timeout)  # noqa: E111
    _LOGGER.debug("%s completed", description)
  except TimeoutError:  # noqa: E111
    _LOGGER.warning("%s timed out", description)
  except Exception as err:  # noqa: E111
    _LOGGER.warning("Error during %s: %s", description, err, exc_info=True)
