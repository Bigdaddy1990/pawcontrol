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


_REGISTERED_MANAGERS: dict[str, type[BaseManager]] = {}


def register_manager(manager_cls: type[BaseManager]) -> type[BaseManager]:
    """Register a manager class for compatibility with legacy tests."""
    _REGISTERED_MANAGERS[manager_cls.MANAGER_NAME] = manager_cls
    return manager_cls


def get_registered_managers() -> dict[str, type[BaseManager]]:
    """Return a shallow copy of registered manager classes."""
    return dict(_REGISTERED_MANAGERS)


@register_manager
class DataManager(BaseManager):
    """Legacy compatibility manager exposing cache helper methods."""

    MANAGER_NAME = "DataManager"

    def __init__(
        self, hass: HomeAssistant, coordinator: PawControlCoordinator | None = None
    ) -> None:
        """Initialise the data manager compatibility shell."""
        super().__init__(hass, coordinator)
        self._cache: dict[str, Any] = {}

    async def async_setup(self) -> None:
        """Set up manager resources."""

    async def async_shutdown(self) -> None:
        """Tear down manager resources."""

    def get_diagnostics(self) -> JSONMapping:
        """Return diagnostics for the compatibility data manager."""
        return {
            "cache_size": len(self._cache),
        }

    def get_cache_size(self) -> int:
        """Return current cache item count."""
        return len(self._cache)

    def clear_cache(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()


@register_manager
class EventManager(BaseManager):
    """Legacy compatibility manager exposing listener helper methods."""

    MANAGER_NAME = "EventManager"

    def __init__(
        self, hass: HomeAssistant, coordinator: PawControlCoordinator | None = None
    ) -> None:
        """Initialise the event manager compatibility shell."""
        super().__init__(hass, coordinator)
        self._listeners: dict[str, list[Callable[..., Any]]] = {}

    async def async_setup(self) -> None:
        """Set up manager resources."""

    async def async_shutdown(self) -> None:
        """Tear down manager resources."""
        self._listeners.clear()

    def get_diagnostics(self) -> JSONMapping:
        """Return diagnostics for the compatibility event manager."""
        return {
            "listener_count": sum(
                len(callbacks) for callbacks in self._listeners.values()
            ),
        }

    def _register_listener(self, event: str, callback: Callable[..., Any]) -> None:
        """Register an event listener callback."""
        self._listeners.setdefault(event, []).append(callback)

    def _unregister_listener(self, event: str, callback: Callable[..., Any]) -> None:
        """Unregister an event listener callback."""
        callbacks = self._listeners.get(event)
        if callbacks is None:
            return
        with suppress(ValueError):
            callbacks.remove(callback)


async def setup_managers(
    *managers: BaseManager,
    stop_on_error: bool = True,
) -> list[BaseManager]:
    """Initialise managers and return successfully started instances."""
    initialized: list[BaseManager] = []

    for manager in managers:
        try:
            await manager.async_initialize()
            initialized.append(manager)
        except ManagerLifecycleError:
            if not stop_on_error:
                continue
            await shutdown_managers(*reversed(initialized), ignore_errors=True)
            raise

    return initialized


async def shutdown_managers(
    *managers: BaseManager,
    ignore_errors: bool = True,
) -> None:
    """Shutdown managers in order and optionally propagate failures."""
    errors: list[ManagerLifecycleError] = []

    for manager in managers:
        try:
            await manager.async_teardown()
        except ManagerLifecycleError as err:
            if ignore_errors:
                continue
            errors.append(err)

    if errors:
        raise errors[0]
