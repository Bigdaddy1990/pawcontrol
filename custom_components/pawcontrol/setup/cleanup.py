"""Cleanup and shutdown logic for PawControl.

Extracted from __init__.py to isolate resource cleanup.
Handles manager shutdown, listener removal, and background task cancellation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    
    from ..types import PawControlConfigEntry, PawControlRuntimeData

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
    """
    cleanup_start = time.monotonic()
    
    # Cancel background monitoring task
    await _async_cancel_background_monitor(runtime_data)
    
    # Clean up managers
    await _async_cleanup_managers(runtime_data)
    
    # Remove listeners
    _remove_listeners(runtime_data)
    
    # Shutdown core managers
    await _async_shutdown_core_managers(runtime_data)
    
    # Clear coordinator references
    _clear_coordinator_references(runtime_data)
    
    cleanup_duration = time.monotonic() - cleanup_start
    _LOGGER.debug(
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
    """
    # Add reload listener
    reload_unsub = entry.add_update_listener(_async_reload_entry_wrapper(hass))
    if callable(reload_unsub):
        runtime_data.reload_unsub = reload_unsub
        if hasattr(entry, "async_on_unload"):
            entry.async_on_unload(reload_unsub)
    
    _LOGGER.debug("Registered cleanup handlers for entry %s", entry.entry_id)


def _async_reload_entry_wrapper(
    hass: HomeAssistant,
) -> Callable[[HomeAssistant, PawControlConfigEntry], Any]:
    """Create a wrapper for async_reload_entry to match expected signature.
    
    Args:
        hass: Home Assistant instance
        
    Returns:
        Async function that reloads the entry
    """
    async def _reload(
        hass_inner: HomeAssistant,
        entry: PawControlConfigEntry,
    ) -> None:
        """Reload the config entry."""
        from .. import async_reload_entry
        await async_reload_entry(hass_inner, entry)
    
    return _reload


async def _async_cancel_background_monitor(runtime_data: PawControlRuntimeData) -> None:
    """Cancel background monitoring task.
    
    Args:
        runtime_data: Runtime data
    """
    monitor_task = getattr(runtime_data, "background_monitor_task", None)
    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            _LOGGER.debug("Background monitor task cancelled")
        except Exception as err:
            _LOGGER.warning(
                "Error while awaiting background monitor task: %s",
                err,
            )
        finally:
            runtime_data.background_monitor_task = None


async def _async_cleanup_managers(runtime_data: PawControlRuntimeData) -> None:
    """Clean up optional managers.
    
    Args:
        runtime_data: Runtime data
    """
    managers = [
        ("door_sensor_manager", getattr(runtime_data, "door_sensor_manager", None)),
        ("geofencing_manager", getattr(runtime_data, "geofencing_manager", None)),
        ("garden_manager", getattr(runtime_data, "garden_manager", None)),
        ("helper_manager", getattr(runtime_data, "helper_manager", None)),
        ("script_manager", getattr(runtime_data, "script_manager", None)),
    ]
    
    for manager_name, manager in managers:
        if manager is not None:
            await _async_run_manager_method(
                manager,
                "async_cleanup",
                f"{manager_name} cleanup",
                timeout=_CLEANUP_TIMEOUT,
            )


def _remove_listeners(runtime_data: PawControlRuntimeData) -> None:
    """Remove event listeners.
    
    Args:
        runtime_data: Runtime data
    """
    # Remove daily reset scheduler
    if getattr(runtime_data, "daily_reset_unsub", None):
        try:
            runtime_data.daily_reset_unsub()
        except Exception as err:
            _LOGGER.warning("Error canceling daily reset scheduler: %s", err)
    
    # Remove reload listener
    reload_unsub = getattr(runtime_data, "reload_unsub", None)
    if callable(reload_unsub):
        try:
            reload_unsub()
        except Exception as err:
            _LOGGER.warning("Error removing config entry listener: %s", err)


async def _async_shutdown_core_managers(runtime_data: PawControlRuntimeData) -> None:
    """Shut down core managers.
    
    Args:
        runtime_data: Runtime data
    """
    core_managers = [
        ("Coordinator", runtime_data.coordinator),
        ("Data manager", runtime_data.data_manager),
        ("Notification manager", runtime_data.notification_manager),
        ("Feeding manager", runtime_data.feeding_manager),
        ("Walk manager", runtime_data.walk_manager),
    ]
    
    for manager_name, manager in core_managers:
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
    """
    try:
        runtime_data.coordinator.clear_runtime_managers()
    except Exception as err:
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
    """
    if manager is None:
        return
    
    method = getattr(manager, method_name, None)
    if method is None:
        return
    
    try:
        result = method()
    except Exception as err:
        _LOGGER.warning(
            "Error starting %s: %s",
            description,
            err,
            exc_info=True,
        )
        return
    
    try:
        # Check if result is awaitable
        if hasattr(result, "__await__"):
            await asyncio.wait_for(result, timeout=timeout)
        _LOGGER.debug("%s completed", description)
    except TimeoutError:
        _LOGGER.warning("%s timed out", description)
    except Exception as err:
        _LOGGER.warning("Error during %s: %s", description, err, exc_info=True)
