"""Unit tests for base_manager module.

Tests base manager classes, lifecycle management, error handling,
and manager registration system.
"""
from __future__ import annotations


from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.base_manager import BaseManager
from custom_components.pawcontrol.base_manager import DataManager
from custom_components.pawcontrol.base_manager import EventManager
from custom_components.pawcontrol.base_manager import get_registered_managers
from custom_components.pawcontrol.base_manager import ManagerLifecycleError
from custom_components.pawcontrol.base_manager import register_manager
from custom_components.pawcontrol.base_manager import setup_managers
from custom_components.pawcontrol.base_manager import shutdown_managers


class DummyManager(BaseManager):
    """Test manager implementation."""

    MANAGER_NAME = "DummyManager"
    MANAGER_VERSION = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_called = False
        self.shutdown_called = False
        self.setup_should_fail = False
        self.shutdown_should_fail = False

    async def async_setup(self) -> None:
        """Set up the test manager."""
        if self.setup_should_fail:
            raise RuntimeError("Setup failed")
        self.setup_called = True

    async def async_shutdown(self) -> None:
        """Shut down the test manager."""
        if self.shutdown_should_fail:
            raise RuntimeError("Shutdown failed")
        self.shutdown_called = True

    def get_diagnostics(self) -> dict:
        """Return diagnostics."""
        return {
            "setup_called": self.setup_called,
            "shutdown_called": self.shutdown_called,
        }


class TestBaseManager:
    """Test BaseManager class."""

    def test_base_manager_initialization(self) -> None:
        """Test manager initialization."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        assert manager.hass == mock_hass
        assert not manager.is_setup
        assert not manager.is_shutdown
        assert not manager.is_ready

    def test_base_manager_with_coordinator(self) -> None:
        """Test manager with coordinator."""
        mock_hass = MagicMock()
        mock_coordinator = MagicMock()
        manager = DummyManager(mock_hass, mock_coordinator)

        assert manager.coordinator == mock_coordinator

    @pytest.mark.asyncio
    async def test_manager_lifecycle(self) -> None:
        """Test manager lifecycle."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        # Initially not ready
        assert not manager.is_ready

        # After setup
        await manager.async_initialize()
        assert manager.is_ready
        assert manager.is_setup
        assert manager.setup_called

        # After shutdown
        await manager.async_teardown()
        assert not manager.is_ready
        assert manager.is_shutdown
        assert manager.shutdown_called

    @pytest.mark.asyncio
    async def test_manager_double_setup_raises(self) -> None:
        """Test that double setup raises error."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        await manager.async_initialize()

        with pytest.raises(ManagerLifecycleError) as exc_info:
            await manager.async_initialize()

        assert "already set up" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_manager_double_shutdown_is_safe(self) -> None:
        """Test that double shutdown is safe."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        await manager.async_initialize()
        await manager.async_teardown()
        await manager.async_teardown()  # Should not raise

        assert manager.is_shutdown

    @pytest.mark.asyncio
    async def test_manager_setup_failure(self) -> None:
        """Test manager setup failure handling."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)
        manager.setup_should_fail = True

        with pytest.raises(ManagerLifecycleError) as exc_info:
            await manager.async_initialize()

        assert "setup failed" in str(exc_info.value).lower()
        assert not manager.is_setup

    @pytest.mark.asyncio
    async def test_manager_shutdown_failure(self) -> None:
        """Test manager shutdown failure handling."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)
        manager.shutdown_should_fail = True

        await manager.async_initialize()

        with pytest.raises(ManagerLifecycleError) as exc_info:
            await manager.async_teardown()

        assert "shutdown failed" in str(exc_info.value).lower()

    def test_require_ready_before_setup(self) -> None:
        """Test require_ready raises before setup."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        with pytest.raises(ManagerLifecycleError):
            manager._require_ready()

    @pytest.mark.asyncio
    async def test_require_ready_after_setup(self) -> None:
        """Test require_ready works after setup."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        await manager.async_initialize()
        manager._require_ready()  # Should not raise

    @pytest.mark.asyncio
    async def test_require_ready_after_shutdown(self) -> None:
        """Test require_ready raises after shutdown."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        await manager.async_initialize()
        await manager.async_teardown()

        with pytest.raises(ManagerLifecycleError):
            manager._require_ready()

    def test_require_coordinator_with_coordinator(self) -> None:
        """Test require_coordinator with coordinator present."""
        mock_hass = MagicMock()
        mock_coordinator = MagicMock()
        manager = DummyManager(mock_hass, mock_coordinator)

        coordinator = manager._require_coordinator()
        assert coordinator == mock_coordinator

    def test_require_coordinator_without_coordinator(self) -> None:
        """Test require_coordinator without coordinator."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        with pytest.raises(ManagerLifecycleError):
            manager._require_coordinator()

    def test_get_lifecycle_diagnostics(self) -> None:
        """Test lifecycle diagnostics."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        diagnostics = manager.get_lifecycle_diagnostics()

        assert diagnostics["manager_name"] == "DummyManager"
        assert diagnostics["manager_version"] == "1.0.0"
        assert diagnostics["is_setup"] is False
        assert diagnostics["is_shutdown"] is False
        assert diagnostics["is_ready"] is False

    def test_manager_repr(self) -> None:
        """Test manager string representation."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        repr_str = repr(manager)
        assert "DummyManager" in repr_str
        assert "ready=False" in repr_str
        assert "has_coordinator=False" in repr_str


class DummyDataManager(DataManager):
    """Concrete DataManager used by tests."""

    async def async_setup(self) -> None:
        """Set up the dummy data manager."""

    async def async_shutdown(self) -> None:
        """Shut down the dummy data manager."""

    def get_diagnostics(self) -> dict:
        """Return diagnostics for tests."""
        return {}


class DummyEventManager(EventManager):
    """Concrete EventManager used by tests."""

    async def async_setup(self) -> None:
        """Set up the dummy event manager."""

    async def async_shutdown(self) -> None:
        """Shut down the dummy event manager."""

    def get_diagnostics(self) -> dict:
        """Return diagnostics for tests."""
        return {}


class TestDataManager:
    """Test DataManager class."""

    def test_data_manager_initialization(self) -> None:
        """Test data manager initialization."""
        mock_hass = MagicMock()
        manager = DummyDataManager(mock_hass)

        assert manager.MANAGER_NAME == "DataManager"
        assert manager.get_cache_size() == 0

    def test_data_manager_cache(self) -> None:
        """Test data manager cache operations."""
        mock_hass = MagicMock()
        manager = DummyDataManager(mock_hass)

        # Add to cache
        manager._cache["key1"] = "value1"
        manager._cache["key2"] = "value2"

        assert manager.get_cache_size() == 2

        # Clear cache
        manager.clear_cache()
        assert manager.get_cache_size() == 0


class TestEventManager:
    """Test EventManager class."""

    def test_event_manager_initialization(self) -> None:
        """Test event manager initialization."""
        mock_hass = MagicMock()
        manager = DummyEventManager(mock_hass)

        assert manager.MANAGER_NAME == "EventManager"
        assert len(manager._listeners) == 0

    def test_event_manager_register_listener(self) -> None:
        """Test registering event listeners."""
        mock_hass = MagicMock()
        manager = DummyEventManager(mock_hass)

        callback = MagicMock()
        manager._register_listener("test_event", callback)

        assert "test_event" in manager._listeners
        assert callback in manager._listeners["test_event"]

    def test_event_manager_unregister_listener(self) -> None:
        """Test unregistering event listeners."""
        mock_hass = MagicMock()
        manager = DummyEventManager(mock_hass)

        callback = MagicMock()
        manager._register_listener("test_event", callback)
        manager._unregister_listener("test_event", callback)

        assert len(manager._listeners["test_event"]) == 0

    def test_event_manager_multiple_listeners(self) -> None:
        """Test multiple listeners for same event."""
        mock_hass = MagicMock()
        manager = DummyEventManager(mock_hass)

        callback1 = MagicMock()
        callback2 = MagicMock()

        manager._register_listener("test_event", callback1)
        manager._register_listener("test_event", callback2)

        assert len(manager._listeners["test_event"]) == 2


class TestManagerRegistration:
    """Test manager registration system."""

    def test_register_manager(self) -> None:
        """Test registering a manager."""

        @register_manager
        class CustomManager(BaseManager):
            MANAGER_NAME = "CustomManager"

            async def async_setup(self) -> None:
                pass

            async def async_shutdown(self) -> None:
                pass

            def get_diagnostics(self) -> dict:
                return {}

        managers = get_registered_managers()
        assert "CustomManager" in managers
        assert managers["CustomManager"] == CustomManager

    def test_get_registered_managers(self) -> None:
        """Test getting registered managers."""
        managers = get_registered_managers()
        assert isinstance(managers, dict)
        # At least DataManager and EventManager should be registered
        assert len(managers) >= 0


class TestBatchOperations:
    """Test batch manager operations."""

    @pytest.mark.asyncio
    async def test_setup_managers_success(self) -> None:
        """Test setting up multiple managers."""
        mock_hass = MagicMock()
        manager1 = DummyManager(mock_hass)
        manager2 = DummyManager(mock_hass)

        managers = await setup_managers(manager1, manager2)

        assert len(managers) == 2
        assert all(m.is_ready for m in managers)

    @pytest.mark.asyncio
    async def test_setup_managers_with_failure(self) -> None:
        """Test setup with one manager failing."""
        mock_hass = MagicMock()
        manager1 = DummyManager(mock_hass)
        manager2 = DummyManager(mock_hass)
        manager2.setup_should_fail = True

        # With stop_on_error=False
        managers = await setup_managers(manager1, manager2, stop_on_error=False)
        assert len(managers) == 1  # Only successful manager

    @pytest.mark.asyncio
    async def test_setup_managers_stop_on_error(self) -> None:
        """Test setup stops on error."""
        mock_hass = MagicMock()
        manager1 = DummyManager(mock_hass)
        manager2 = DummyManager(mock_hass)
        manager2.setup_should_fail = True

        with pytest.raises(ManagerLifecycleError):
            await setup_managers(manager1, manager2, stop_on_error=True)

        # Manager1 should be cleaned up
        assert manager1.is_shutdown

    @pytest.mark.asyncio
    async def test_shutdown_managers(self) -> None:
        """Test shutting down multiple managers."""
        mock_hass = MagicMock()
        manager1 = DummyManager(mock_hass)
        manager2 = DummyManager(mock_hass)

        await manager1.async_initialize()
        await manager2.async_initialize()

        await shutdown_managers(manager1, manager2)

        assert manager1.is_shutdown
        assert manager2.is_shutdown

    @pytest.mark.asyncio
    async def test_shutdown_managers_ignore_errors(self) -> None:
        """Test shutdown ignores errors by default."""
        mock_hass = MagicMock()
        manager1 = DummyManager(mock_hass)
        manager2 = DummyManager(mock_hass)
        manager1.shutdown_should_fail = True

        await manager1.async_initialize()
        await manager2.async_initialize()

        # Should not raise despite manager1 failure
        await shutdown_managers(manager1, manager2, ignore_errors=True)

        assert manager2.is_shutdown

    @pytest.mark.asyncio
    async def test_shutdown_managers_raise_errors(self) -> None:
        """Test shutdown raises errors when configured."""
        mock_hass = MagicMock()
        manager1 = DummyManager(mock_hass)
        manager1.shutdown_should_fail = True

        await manager1.async_initialize()

        with pytest.raises(ManagerLifecycleError):
            await shutdown_managers(manager1, ignore_errors=False)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_manager_diagnostics_after_setup(self) -> None:
        """Test diagnostics after setup."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        await manager.async_initialize()

        diagnostics = manager.get_diagnostics()
        assert diagnostics["setup_called"] is True

    @pytest.mark.asyncio
    async def test_manager_diagnostics_after_shutdown(self) -> None:
        """Test diagnostics after shutdown."""
        mock_hass = MagicMock()
        manager = DummyManager(mock_hass)

        await manager.async_initialize()
        await manager.async_teardown()

        diagnostics = manager.get_diagnostics()
        assert diagnostics["shutdown_called"] is True

    def test_manager_lifecycle_error_attributes(self) -> None:
        """Test ManagerLifecycleError attributes."""
        error = ManagerLifecycleError("DummyManager", "setup", "Test reason")

        assert error.manager_name == "DummyManager"
        assert error.operation == "setup"
        assert error.reason == "Test reason"
        assert "DummyManager" in str(error)
        assert "setup" in str(error)

    @pytest.mark.asyncio
    async def test_empty_setup_managers(self) -> None:
        """Test setup_managers with no managers."""
        managers = await setup_managers()
        assert len(managers) == 0

    @pytest.mark.asyncio
    async def test_empty_shutdown_managers(self) -> None:
        """Test shutdown_managers with no managers."""
        await shutdown_managers()  # Should not raise

    def test_data_manager_extends_base_manager(self) -> None:
        """Test DataManager extends BaseManager."""
        assert issubclass(DataManager, BaseManager)

    def test_event_manager_extends_base_manager(self) -> None:
        """Test EventManager extends BaseManager."""
        assert issubclass(EventManager, BaseManager)
