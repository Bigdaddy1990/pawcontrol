"""Base manager class for PawControl managers.

This module provides a standardized base class for all PawControl managers,
ensuring consistent lifecycle management, error handling, and coordinator integration.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations


import logging
from abc import ABC
from abc import abstractmethod
from contextlib import suppress
from typing import Any
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
  from .coordinator import PawControlCoordinator
  from .types import JSONMapping


class ManagerLifecycleError(Exception):
  """Exception raised when manager lifecycle operations fail."""

  def __init__(self, manager_name: str, operation: str, reason: str) -> None:
    """Initialize lifecycle error.

    Args:
        manager_name: Name of the manager
        operation: Lifecycle operation (setup, shutdown, etc.)
        reason: Reason for failure
    """
    super().__init__(f"{manager_name} {operation} failed: {reason}")
    self.manager_name = manager_name
    self.operation = operation
    self.reason = reason


class BaseManager(ABC):
  """Abstract base class for all PawControl managers.

  This class provides standardized lifecycle management, error handling,
  and coordinator integration for all manager implementations.

  Subclasses must implement:
      - async_setup(): Initialize manager resources
      - async_shutdown(): Clean up manager resources
      - get_diagnostics(): Return diagnostic information

  Lifecycle:
      1. __init__(hass, coordinator) - Create instance
      2. async_setup() - Initialize resources
      3. [Runtime operations]
      4. async_shutdown() - Clean up resources

  Examples:
      >>> class MyManager(BaseManager):
      ...   async def async_setup(self):
      ...     self._data = {}
      ...
      ...   async def async_shutdown(self):
      ...     self._data.clear()
      ...
      ...   def get_diagnostics(self):
      ...     return {"data_count": len(self._data)}
  """

  # Class-level constants
  MANAGER_NAME: str = "BaseManager"
  MANAGER_VERSION: str = "1.0.0"

  def __init__(
    self,
    hass: HomeAssistant,
    coordinator: PawControlCoordinator | None = None,
  ) -> None:
    """Initialize the base manager.

    Args:
        hass: Home Assistant instance
        coordinator: Optional coordinator instance
    """
    self._hass = hass
    self._coordinator = coordinator
    self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    self._is_setup = False
    self._is_shutdown = False
    self._setup_timestamp: float | None = None
    self._shutdown_timestamp: float | None = None

    self._logger.debug(
      "%s initialized (version=%s)",
      self.MANAGER_NAME,
      self.MANAGER_VERSION,
    )

  @property
  def hass(self) -> HomeAssistant:
    """Return Home Assistant instance."""
    return self._hass

  @property
  def coordinator(self) -> PawControlCoordinator | None:
    """Return coordinator instance if available."""
    return self._coordinator

  @property
  def logger(self) -> logging.Logger:
    """Return manager-specific logger."""
    return self._logger

  @property
  def is_setup(self) -> bool:
    """Return True if manager has been set up."""
    return self._is_setup

  @property
  def is_shutdown(self) -> bool:
    """Return True if manager has been shut down."""
    return self._is_shutdown

  @property
  def is_ready(self) -> bool:
    """Return True if manager is ready for operations.

    A manager is ready if it's been set up and not shut down.
    """
    return self._is_setup and not self._is_shutdown

  @abstractmethod
  async def async_setup(self) -> None:
    """Set up the manager.

    This method must be implemented by subclasses to initialize
    manager-specific resources.

    Raises:
        ManagerLifecycleError: If setup fails
    """

  @abstractmethod
  async def async_shutdown(self) -> None:
    """Shut down the manager.

    This method must be implemented by subclasses to clean up
    manager-specific resources.

    Raises:
        ManagerLifecycleError: If shutdown fails
    """

  @abstractmethod
  def get_diagnostics(self) -> JSONMapping:
    """Return diagnostic information about the manager.

    Returns:
        Dictionary with diagnostic data

    Examples:
        >>> diagnostics = manager.get_diagnostics()
        >>> print(diagnostics["manager_name"])
        'MyManager'
    """

  async def async_initialize(self) -> None:
    """Initialize the manager (wrapper for async_setup with lifecycle tracking).

    This method should be called instead of async_setup() directly.
    It handles lifecycle state tracking and error handling.

    Raises:
        ManagerLifecycleError: If manager is already set up
        ManagerLifecycleError: If setup fails
    """
    if self._is_setup:
      raise ManagerLifecycleError(
        self.MANAGER_NAME,
        "setup",
        "Manager is already set up",
      )

    try:
      import time

      start = time.time()
      await self.async_setup()
      self._setup_timestamp = time.time()
      self._is_setup = True

      duration_ms = (self._setup_timestamp - start) * 1000
      self._logger.info(
        "%s setup completed (duration_ms=%.2f)",
        self.MANAGER_NAME,
        duration_ms,
      )
    except Exception as e:
      self._logger.error(
        "%s setup failed: %s (%s)",
        self.MANAGER_NAME,
        e,
        e.__class__.__name__,
      )
      raise ManagerLifecycleError(
        self.MANAGER_NAME,
        "setup",
        str(e),
      ) from e

  async def async_teardown(self) -> None:
    """Tear down the manager (wrapper for async_shutdown with lifecycle tracking).

    This method should be called instead of async_shutdown() directly.
    It handles lifecycle state tracking and error handling.

    Raises:
        ManagerLifecycleError: If manager is already shut down
        ManagerLifecycleError: If shutdown fails
    """
    if self._is_shutdown:
      self._logger.debug(
        "%s already shut down, skipping teardown",
        self.MANAGER_NAME,
      )
      return

    try:
      import time

      start = time.time()
      await self.async_shutdown()
      self._shutdown_timestamp = time.time()
      self._is_shutdown = True

      duration_ms = (self._shutdown_timestamp - start) * 1000
      self._logger.info(
        "%s shutdown completed (duration_ms=%.2f)",
        self.MANAGER_NAME,
        duration_ms,
      )
    except Exception as e:
      self._logger.error(
        "%s shutdown failed: %s (%s)",
        self.MANAGER_NAME,
        e,
        e.__class__.__name__,
      )
      raise ManagerLifecycleError(
        self.MANAGER_NAME,
        "shutdown",
        str(e),
      ) from e

  def get_lifecycle_diagnostics(self) -> JSONMapping:
    """Return lifecycle diagnostic information.

    Returns:
        Dictionary with lifecycle state

    Examples:
        >>> diagnostics = manager.get_lifecycle_diagnostics()
        >>> print(diagnostics["is_ready"])
        True
    """
    return {
      "manager_name": self.MANAGER_NAME,
      "manager_version": self.MANAGER_VERSION,
      "is_setup": self._is_setup,
      "is_shutdown": self._is_shutdown,
      "is_ready": self.is_ready,
      "setup_timestamp": self._setup_timestamp,
      "shutdown_timestamp": self._shutdown_timestamp,
      "has_coordinator": self._coordinator is not None,
    }

  def _require_ready(self) -> None:
    """Ensure manager is ready for operations.

    Raises:
        ManagerLifecycleError: If manager is not ready
    """
    if not self.is_ready:
      if not self._is_setup:
        raise ManagerLifecycleError(
          self.MANAGER_NAME,
          "operation",
          "Manager has not been set up",
        )
      if self._is_shutdown:
        raise ManagerLifecycleError(
          self.MANAGER_NAME,
          "operation",
          "Manager has been shut down",
        )

  def _require_coordinator(self) -> PawControlCoordinator:
    """Ensure coordinator is available.

    Returns:
        Coordinator instance

    Raises:
        ManagerLifecycleError: If coordinator is not available
    """
    if self._coordinator is None:
      raise ManagerLifecycleError(
        self.MANAGER_NAME,
        "coordinator_access",
        "Coordinator is not available",
      )
    return self._coordinator

  async def async_health_check(self) -> dict[str, Any]:
    """Perform health check on the manager.

    Returns:
        Dictionary with health status

    Examples:
        >>> health = await manager.async_health_check()
        >>> print(health["status"])
        'healthy'
    """
    return {
      "status": "healthy" if self.is_ready else "not_ready",
      "is_ready": self.is_ready,
      "is_setup": self._is_setup,
      "is_shutdown": self._is_shutdown,
      "manager_name": self.MANAGER_NAME,
    }

  def get_metrics(self) -> dict[str, Any]:
    """Return manager-specific metrics.

    Subclasses can override this to provide custom metrics.

    Returns:
        Dictionary with metrics

    Examples:
        >>> metrics = manager.get_metrics()
        >>> print(metrics["uptime_seconds"])
        120.5
    """
    metrics: dict[str, Any] = {
      "manager_name": self.MANAGER_NAME,
      "manager_version": self.MANAGER_VERSION,
      "is_ready": self.is_ready,
    }

    if self._setup_timestamp is not None:
      import time

      metrics["uptime_seconds"] = time.time() - self._setup_timestamp

    return metrics

  def __repr__(self) -> str:
    """Return string representation of manager.

    Returns:
        String representation

    Examples:
        >>> manager = MyManager(hass)
        >>> repr(manager)
        '<MyManager(ready=False, has_coordinator=False)>'
    """
    return (
      f"<{self.__class__.__name__}"
      f"(ready={self.is_ready}, "
      f"has_coordinator={self._coordinator is not None})>"
    )


class DataManager(BaseManager):
  """Base class for managers that handle data storage and retrieval.

  This class extends BaseManager with data-specific functionality like
  caching, validation, and persistence.

  Examples:
      >>> class MyDataManager(DataManager):
      ...   async def async_setup(self):
      ...     self._data = {}
      ...
      ...   async def async_save_data(self, key, value):
      ...     self._require_ready()
      ...     self._data[key] = value
  """

  MANAGER_NAME: str = "DataManager"

  def __init__(
    self,
    hass: HomeAssistant,
    coordinator: PawControlCoordinator | None = None,
  ) -> None:
    """Initialize the data manager."""
    super().__init__(hass, coordinator)
    self._cache: dict[str, Any] = {}

  def clear_cache(self) -> None:
    """Clear all cached data."""
    self._cache.clear()
    self._logger.debug("%s cache cleared", self.MANAGER_NAME)

  def get_cache_size(self) -> int:
    """Return number of items in cache."""
    return len(self._cache)


class EventManager(BaseManager):
  """Base class for managers that handle events and notifications.

  This class extends BaseManager with event-specific functionality like
  event registration, dispatching, and listener management.

  Examples:
      >>> class MyEventManager(EventManager):
      ...   async def async_setup(self):
      ...     await super().async_setup()
      ...     self._register_listener("my_event", self._handle_event)
  """

  MANAGER_NAME: str = "EventManager"

  def __init__(
    self,
    hass: HomeAssistant,
    coordinator: PawControlCoordinator | None = None,
  ) -> None:
    """Initialize the event manager."""
    super().__init__(hass, coordinator)
    self._listeners: dict[str, list[Any]] = {}

  def _register_listener(self, event: str, callback: Any) -> None:
    """Register an event listener.

    Args:
        event: Event name
        callback: Callback function
    """
    if event not in self._listeners:
      self._listeners[event] = []
    self._listeners[event].append(callback)
    self._logger.debug(
      "Registered listener for %s (total=%d)",
      event,
      len(self._listeners[event]),
    )

  def _unregister_listener(self, event: str, callback: Any) -> None:
    """Unregister an event listener.

    Args:
        event: Event name
        callback: Callback function
    """
    if event in self._listeners:
      try:
        self._listeners[event].remove(callback)
        self._logger.debug(
          "Unregistered listener for %s (remaining=%d)",
          event,
          len(self._listeners[event]),
        )
      except ValueError:
        pass


# Manager registry for tracking all active managers

_MANAGER_REGISTRY: dict[str, type[BaseManager]] = {}


def register_manager(manager_class: type[BaseManager]) -> type[BaseManager]:
  """Register a manager class in the global registry.

  Args:
      manager_class: Manager class to register

  Returns:
      The registered manager class (for decorator usage)

  Examples:
      >>> @register_manager
      ... class MyManager(BaseManager):
      ...   MANAGER_NAME = "MyManager"
  """
  _MANAGER_REGISTRY[manager_class.MANAGER_NAME] = manager_class
  return manager_class


def get_registered_managers() -> dict[str, type[BaseManager]]:
  """Return dictionary of all registered managers.

  Returns:
      Dictionary mapping manager names to classes

  Examples:
      >>> managers = get_registered_managers()
      >>> print(list(managers.keys()))
      ['DataManager', 'EventManager', 'MyManager']
  """
  return dict(_MANAGER_REGISTRY)


# Lifecycle management utilities


async def setup_managers(
  *managers: BaseManager,
  stop_on_error: bool = False,
) -> list[BaseManager]:
  """Set up multiple managers in parallel.

  Args:
      *managers: Managers to set up
      stop_on_error: If True, stop setup on first error

  Returns:
      List of successfully set up managers

  Raises:
      ManagerLifecycleError: If stop_on_error=True and setup fails

  Examples:
      >>> managers = await setup_managers(data_manager, event_manager)
      >>> print(len(managers))
      2
  """
  successful: list[BaseManager] = []

  for manager in managers:
    try:
      await manager.async_initialize()
      successful.append(manager)
    except ManagerLifecycleError as e:
      if stop_on_error:
        # Clean up successful managers
        for m in successful:
          with suppress(Exception):
            await m.async_teardown()
        raise
      manager.logger.error("Failed to set up manager: %s", e)

  return successful


async def shutdown_managers(
  *managers: BaseManager,
  ignore_errors: bool = True,
) -> None:
  """Shut down multiple managers in parallel.

  Args:
      *managers: Managers to shut down
      ignore_errors: If True, continue shutdown even if errors occur

  Examples:
      >>> await shutdown_managers(data_manager, event_manager)
  """
  for manager in managers:
    try:
      await manager.async_teardown()
    except ManagerLifecycleError as e:
      if not ignore_errors:
        raise
      manager.logger.error("Failed to shut down manager: %s", e)
