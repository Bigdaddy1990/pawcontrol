"""Base manager class for PawControl managers.

This module provides a standardized base class for all PawControl managers,
ensuring consistent lifecycle management, error handling, and coordinator integration.

Quality Scale: Platinum target
Home Assistant: 2026.2.1+
Python: 3.14+
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import suppress  # noqa: F401
import logging
import time
from typing import TYPE_CHECKING, Any

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

    Provides standardized lifecycle management, error handling, and coordinator
    integration for all manager implementations.

    Subclasses must implement:
        - async_setup(): Initialize manager resources
        - async_shutdown(): Clean up manager resources
        - get_diagnostics(): Return diagnostic information

    Lifecycle:
        1. __init__(hass, coordinator) - Create instance
        2. async_setup() - Initialize resources
        3. [Runtime operations]
        4. async_shutdown() - Clean up resources
    """

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

        A manager is ready if it has been set up and not yet shut down.
        """
        return self._is_setup and not self._is_shutdown

    @abstractmethod
    async def async_setup(self) -> None:
        """Set up the manager.

        Subclasses must implement this to initialize manager-specific resources.

        Raises:
            ManagerLifecycleError: If setup fails.
        """

    @abstractmethod
    async def async_shutdown(self) -> None:
        """Shut down the manager.

        Subclasses must implement this to clean up manager-specific resources.

        Raises:
            ManagerLifecycleError: If shutdown fails.
        """

    @abstractmethod
    def get_diagnostics(self) -> JSONMapping:
        """Return diagnostic information about the manager.

        Returns:
            Dictionary with diagnostic data.
        """

    async def async_initialize(self) -> None:
        """Initialize the manager with lifecycle tracking.

        Call this instead of async_setup() directly; it tracks state and
        surfaces errors uniformly.

        Raises:
            ManagerLifecycleError: If the manager is already set up or setup fails.
        """
        if self._is_setup:
            raise ManagerLifecycleError(
                self.MANAGER_NAME,
                "setup",
                "Manager is already set up",
            )

        try:
            start = time.monotonic()
            await self.async_setup()
            self._setup_timestamp = time.time()
            self._is_setup = True

            duration_ms = (time.monotonic() - start) * 1000
            self._logger.info(
                "%s setup completed (duration_ms=%.2f)",
                self.MANAGER_NAME,
                duration_ms,
            )
        except Exception as exc:
            self._logger.error(
                "%s setup failed: %s (%s)",
                self.MANAGER_NAME,
                exc,
                exc.__class__.__name__,
            )
            raise ManagerLifecycleError(
                self.MANAGER_NAME,
                "setup",
                str(exc),
            ) from exc

    async def async_teardown(self) -> None:
        """Tear down the manager with lifecycle tracking.

        Call this instead of async_shutdown() directly; it tracks state and
        surfaces errors uniformly.

        Raises:
            ManagerLifecycleError: If shutdown fails and ``ignore_errors`` is False.
        """
        if self._is_shutdown:
            self._logger.debug(
                "%s already shut down, skipping teardown",
                self.MANAGER_NAME,
            )
            return

        try:
            start = time.monotonic()
            await self.async_shutdown()
            self._shutdown_timestamp = time.time()
            self._is_shutdown = True

            duration_ms = (time.monotonic() - start) * 1000
            self._logger.info(
                "%s shutdown completed (duration_ms=%.2f)",
                self.MANAGER_NAME,
                duration_ms,
            )
        except Exception as exc:
            self._logger.error(
                "%s shutdown failed: %s (%s)",
                self.MANAGER_NAME,
                exc,
                exc.__class__.__name__,
            )
            raise ManagerLifecycleError(
                self.MANAGER_NAME,
                "shutdown",
                str(exc),
            ) from exc

    def get_lifecycle_diagnostics(self) -> JSONMapping:
        """Return lifecycle diagnostic information.

        Returns:
            Dictionary with lifecycle state.
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
            ManagerLifecycleError: If manager is not ready.
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
            Coordinator instance.

        Raises:
            ManagerLifecycleError: If coordinator is not available.
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
            Dictionary with health status.
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
            Dictionary with metrics.
        """
        metrics: dict[str, Any] = {
            "manager_name": self.MANAGER_NAME,
            "manager_version": self.MANAGER_VERSION,
            "is_ready": self.is_ready,
        }

        if self._setup_timestamp is not None:
            metrics["uptime_seconds"] = time.time() - self._setup_timestamp

        return metrics

    def __repr__(self) -> str:
        """Return string representation of the manager."""
        return (
            f"<{self.__class__.__name__}"
            f"(ready={self.is_ready}, "
            f"has_coordinator={self._coordinator is not None})>"
        )



# ---------------------------------------------------------------------------
# Concrete manager subclasses
# ---------------------------------------------------------------------------


class DataManager(BaseManager):
    """Manager for data operations with integrated caching support.

    Provides a lightweight in-memory cache that concrete subclasses can
    populate from coordinator data or external API calls.  Cache entries
    are arbitrary JSON-compatible values keyed by string identifiers.

    Subclasses must still implement :meth:`async_setup`,
    :meth:`async_shutdown`, and :meth:`get_diagnostics`.
    """

    MANAGER_NAME: str = "DataManager"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator | None = None,
    ) -> None:
        """Initialize the data manager with an empty cache.

        Args:
            hass: Home Assistant instance.
            coordinator: Optional PawControl coordinator.
        """
        super().__init__(hass, coordinator)
        self._cache: dict[str, Any] = {}

    def get_cache_size(self) -> int:
        """Return the number of entries currently held in the cache.

        Returns:
            Integer count of cached keys.
        """
        return len(self._cache)

    def clear_cache(self) -> None:
        """Remove all entries from the in-memory cache."""
        self._cache.clear()


class EventManager(BaseManager):
    """Manager for event handling with listener registration.

    Maintains a mapping of event names to ordered lists of callables.
    Concrete subclasses use :meth:`_register_listener` and
    :meth:`_unregister_listener` to manage their own event subscriptions.
    """

    MANAGER_NAME: str = "EventManager"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PawControlCoordinator | None = None,
    ) -> None:
        """Initialize the event manager with an empty listener registry.

        Args:
            hass: Home Assistant instance.
            coordinator: Optional PawControl coordinator.
        """
        super().__init__(hass, coordinator)
        self._listeners: dict[str, list[Callable[..., Any]]] = {}

    def _register_listener(self, event: str, callback: Callable[..., Any]) -> None:
        """Append *callback* to the listener list for *event*.

        Args:
            event: Event name string to subscribe to.
            callback: Callable invoked when the event fires.
        """
        self._listeners.setdefault(event, []).append(callback)

    def _unregister_listener(self, event: str, callback: Callable[..., Any]) -> None:
        """Remove *callback* from the listener list for *event*.

        Silently ignores the call when the callback is not registered.

        Args:
            event: Event name string to unsubscribe from.
            callback: Callable to remove from the listener list.
        """
        if event in self._listeners:
            with suppress(ValueError):
                self._listeners[event].remove(callback)


# ---------------------------------------------------------------------------
# Manager registration system
# ---------------------------------------------------------------------------

_REGISTERED_MANAGERS: dict[str, type[BaseManager]] = {}


def register_manager(cls: type[BaseManager]) -> type[BaseManager]:
    """Class decorator that registers *cls* in the global manager registry.

    The class is keyed under ``cls.MANAGER_NAME``.  Applying the decorator
    twice with the same name overwrites the previous registration.

    Args:
        cls: Manager class to register.

    Returns:
        The unchanged *cls* so the decorator is transparent.
    """
    _REGISTERED_MANAGERS[cls.MANAGER_NAME] = cls
    return cls


def get_registered_managers() -> dict[str, type[BaseManager]]:
    """Return a snapshot copy of the global manager registry.

    Returns:
        Mapping of manager name → manager class for all registered managers.
    """
    return dict(_REGISTERED_MANAGERS)


# ---------------------------------------------------------------------------
# Batch lifecycle helpers
# ---------------------------------------------------------------------------


async def setup_managers(
    *managers: BaseManager,
    stop_on_error: bool = False,
) -> list[BaseManager]:
    """Initialize multiple managers, collecting the successful ones.

    When *stop_on_error* is ``False`` (the default) each manager is attempted
    independently and only successfully initialized managers are returned.
    When *stop_on_error* is ``True`` the first failure tears down all
    previously successful managers and re-raises the error.

    Args:
        *managers: Manager instances to initialize in order.
        stop_on_error: If ``True``, abort and roll back on the first failure.

    Returns:
        List of managers that completed :meth:`~BaseManager.async_initialize`
        without error.

    Raises:
        ManagerLifecycleError: Only when *stop_on_error* is ``True`` and a
            manager fails to initialize.
    """
    successful: list[BaseManager] = []
    for manager in managers:
        try:
            await manager.async_initialize()
            successful.append(manager)
        except Exception:  # noqa: BLE001
            if stop_on_error:
                for m in reversed(successful):
                    with suppress(Exception):
                        await m.async_teardown()
                raise
    return successful


async def shutdown_managers(
    *managers: BaseManager,
    ignore_errors: bool = True,
) -> None:
    """Tear down multiple managers in order.

    Args:
        *managers: Manager instances to tear down.
        ignore_errors: When ``True`` (default) errors from individual managers
            are suppressed so that all managers receive their teardown call.
            When ``False`` the first error is re-raised immediately.

    Raises:
        ManagerLifecycleError: Only when *ignore_errors* is ``False`` and a
            manager's :meth:`~BaseManager.async_teardown` raises.
    """
    for manager in managers:
        try:
            await manager.async_teardown()
        except Exception:  # noqa: BLE001
            if not ignore_errors:
                raise
