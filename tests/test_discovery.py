"""Tests for Paw Control Discovery functionality.

Tests the comprehensive device discovery system including USB, Bluetooth,
Zeroconf, DHCP, and UPnP discovery with full async operation and error handling.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.discovery import (
    DEVICE_CATEGORIES,
    DISCOVERY_TIMEOUT,
    DiscoveredDevice,
    PawControlDiscovery,
    async_get_discovered_devices,
    async_get_discovery_manager,
    async_shutdown_discovery_manager,
    async_start_discovery,
)
from custom_components.pawcontrol.exceptions import PawControlError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


@pytest.fixture
def mock_bluetooth_scanner():
    """Mock Bluetooth scanner for testing."""
    return MagicMock()


@pytest.fixture
def mock_usb_discovery():
    """Mock USB discovery for testing."""
    return MagicMock()


@pytest.fixture
async def discovery_manager(hass: HomeAssistant):
    """Create a discovery manager for testing."""
    manager = PawControlDiscovery(hass)

    # Mock the discovery methods to avoid actual hardware scanning
    with patch.multiple(
        manager,
        _discover_usb_devices=AsyncMock(return_value=[]),
        _discover_bluetooth_devices=AsyncMock(return_value=[]),
        _discover_zeroconf_devices=AsyncMock(return_value=[]),
        _discover_dhcp_devices=AsyncMock(return_value=[]),
        _discover_upnp_devices=AsyncMock(return_value=[]),
        _start_background_scanning=AsyncMock(),
        _register_discovery_listeners=AsyncMock(),
    ):
        await manager.async_initialize()
        yield manager
        await manager.async_shutdown()


class TestDiscoveredDevice:
    """Test the DiscoveredDevice dataclass."""

    def test_discovered_device_creation(self):
        """Test creating a DiscoveredDevice."""
        device = DiscoveredDevice(
            device_id="test_device_123",
            name="Test GPS Tracker",
            category="gps_tracker",
            manufacturer="TestCorp",
            model="GPS-1000",
            connection_type="usb",
            connection_info={"vid": "1234", "pid": "5678"},
            capabilities=["gps", "activity_tracking"],
            discovered_at="2023-01-01T00:00:00",
            confidence=0.9,
            metadata={"protocol": "usb", "version": "1.0"},
        )

        assert device.device_id == "test_device_123"
        assert device.name == "Test GPS Tracker"
        assert device.category == "gps_tracker"
        assert device.manufacturer == "TestCorp"
        assert device.model == "GPS-1000"
        assert device.connection_type == "usb"
        assert device.connection_info == {"vid": "1234", "pid": "5678"}
        assert device.capabilities == ["gps", "activity_tracking"]
        assert device.confidence == 0.9
        assert device.metadata["protocol"] == "usb"

    def test_discovered_device_immutable(self):
        """Test that DiscoveredDevice is immutable (frozen dataclass)."""
        device = DiscoveredDevice(
            device_id="test",
            name="Test Device",
            category="gps_tracker",
            manufacturer="Test",
            model="Test",
            connection_type="usb",
            connection_info={},
            capabilities=[],
            discovered_at="2023-01-01T00:00:00",
            confidence=0.8,
            metadata={},
        )

        with pytest.raises(AttributeError):
            device.device_id = "new_id"


class TestPawControlDiscovery:
    """Test the PawControlDiscovery class."""

    async def test_initialization(self, hass: HomeAssistant):
        """Test discovery manager initialization."""
        discovery = PawControlDiscovery(hass)

        assert discovery.hass == hass
        assert discovery._discovered_devices == {}
        assert discovery._discovery_tasks == set()
        assert discovery._scan_active is False
        assert discovery._listeners == []

        with patch.multiple(
            discovery,
            _start_background_scanning=AsyncMock(),
            _register_discovery_listeners=AsyncMock(),
        ):
            await discovery.async_initialize()

    async def test_initialization_error_handling(self, hass: HomeAssistant):
        """Test initialization error handling."""
        discovery = PawControlDiscovery(hass)

        with patch.object(discovery, "_start_background_scanning") as mock_background:
            mock_background.side_effect = Exception("Background error")

            with pytest.raises(
                HomeAssistantError, match="Discovery initialization failed"
            ):
                await discovery.async_initialize()

    async def test_discover_devices_basic(self, discovery_manager):
        """Test basic device discovery."""
        # Mock discovery methods to return sample devices
        sample_usb_device = DiscoveredDevice(
            device_id="usb_test",
            name="Test USB Device",
            category="gps_tracker",
            manufacturer="TestCorp",
            model="USB-GPS",
            connection_type="usb",
            connection_info={"vid": "1234", "pid": "5678"},
            capabilities=["gps"],
            discovered_at="2023-01-01T00:00:00",
            confidence=0.9,
            metadata={"protocol": "usb"},
        )

        discovery_manager._discover_usb_devices.return_value = [sample_usb_device]

        devices = await discovery_manager.async_discover_devices(
            categories=["gps_tracker"]
        )

        assert len(devices) == 1
        assert devices[0].device_id == "usb_test"
        assert devices[0].category == "gps_tracker"

        # Verify device was stored
        assert "usb_test" in discovery_manager._discovered_devices

    async def test_discover_devices_all_categories(self, discovery_manager):
        """Test discovery with all device categories."""
        await discovery_manager.async_discover_devices()

        # Should call all discovery methods
        discovery_manager._discover_usb_devices.assert_called_once_with(
            DEVICE_CATEGORIES
        )
        discovery_manager._discover_bluetooth_devices.assert_called_once()
        discovery_manager._discover_zeroconf_devices.assert_called_once()
        discovery_manager._discover_dhcp_devices.assert_called_once()
        discovery_manager._discover_upnp_devices.assert_called_once()

    async def test_discover_devices_quick_scan(self, discovery_manager):
        """Test quick scan functionality."""
        await discovery_manager.async_discover_devices(quick_scan=True)

        # Should still call all methods but with shorter timeout
        assert len(discovery_manager._discovery_tasks) == 0  # Tasks should be completed

    async def test_discover_devices_concurrent_scan_protection(self, discovery_manager):
        """Test protection against concurrent scans."""
        # Start a scan
        discovery_manager._scan_active = True

        with patch.object(discovery_manager, "_wait_for_scan_completion") as mock_wait:
            await discovery_manager.async_discover_devices()
            mock_wait.assert_called_once()

    async def test_discover_devices_timeout(self, discovery_manager):
        """Test discovery timeout handling."""
        # Make one discovery method hang
        discovery_manager._discover_usb_devices.side_effect = asyncio.sleep(
            DISCOVERY_TIMEOUT * 2
        )

        # Should handle timeout gracefully and return existing devices
        devices = await discovery_manager.async_discover_devices(quick_scan=True)

        assert isinstance(devices, list)  # Should return a list even on timeout

    async def test_discover_devices_with_exceptions(self, discovery_manager):
        """Test handling of exceptions during discovery."""
        discovery_manager._discover_usb_devices.side_effect = Exception("USB error")
        discovery_manager._discover_bluetooth_devices.side_effect = Exception(
            "Bluetooth error"
        )

        # Should not raise, should continue with other methods
        devices = await discovery_manager.async_discover_devices()

        assert isinstance(devices, list)

    async def test_discover_usb_devices(self, discovery_manager):
        """Test USB device discovery."""
        categories = ["gps_tracker", "smart_feeder"]

        # Reset the mock to test actual implementation
        discovery_manager._discover_usb_devices = (
            discovery_manager.__class__._discover_usb_devices.__get__(discovery_manager)
        )

        with patch("custom_components.pawcontrol.discovery.usb") as mock_usb:
            mock_usb.async_get_usb.return_value = MagicMock()

            devices = await discovery_manager._discover_usb_devices(categories)

            assert isinstance(devices, list)

    async def test_discover_bluetooth_devices(self, discovery_manager):
        """Test Bluetooth device discovery."""
        categories = ["activity_monitor", "smart_collar"]

        # Reset the mock to test actual implementation
        discovery_manager._discover_bluetooth_devices = (
            discovery_manager.__class__._discover_bluetooth_devices.__get__(
                discovery_manager
            )
        )

        with patch(
            "custom_components.pawcontrol.discovery.bluetooth"
        ) as mock_bluetooth:
            mock_bluetooth.async_get_scanner.return_value = MagicMock()

            devices = await discovery_manager._discover_bluetooth_devices(categories)

            assert isinstance(devices, list)

    async def test_discover_zeroconf_devices(self, discovery_manager):
        """Test Zeroconf/mDNS device discovery."""
        categories = ["smart_feeder"]

        # Reset the mock to test actual implementation
        discovery_manager._discover_zeroconf_devices = (
            discovery_manager.__class__._discover_zeroconf_devices.__get__(
                discovery_manager
            )
        )

        devices = await discovery_manager._discover_zeroconf_devices(categories)

        assert isinstance(devices, list)
        # Should create devices for matching categories
        if devices:
            assert all(device.category in categories for device in devices)

    async def test_discover_dhcp_devices(self, discovery_manager):
        """Test DHCP hostname-based discovery."""
        categories = ["gps_tracker", "health_device"]

        # Reset the mock to test actual implementation
        discovery_manager._discover_dhcp_devices = (
            discovery_manager.__class__._discover_dhcp_devices.__get__(
                discovery_manager
            )
        )

        devices = await discovery_manager._discover_dhcp_devices(categories)

        assert isinstance(devices, list)

    async def test_discover_upnp_devices(self, discovery_manager):
        """Test UPnP device discovery."""
        categories = ["smart_feeder", "health_device"]

        # Reset the mock to test actual implementation
        discovery_manager._discover_upnp_devices = (
            discovery_manager.__class__._discover_upnp_devices.__get__(
                discovery_manager
            )
        )

        devices = await discovery_manager._discover_upnp_devices(categories)

        assert isinstance(devices, list)

    async def test_deduplicate_devices(self, discovery_manager):
        """Test device deduplication functionality."""
        devices = [
            DiscoveredDevice(
                device_id="device1",
                name="Test Device",
                category="gps_tracker",
                manufacturer="TestCorp",
                model="Model1",
                connection_type="usb",
                connection_info={},
                capabilities=[],
                discovered_at="2023-01-01T00:00:00",
                confidence=0.8,
                metadata={},
            ),
            DiscoveredDevice(
                device_id="device2",
                name="Test Device",  # Same name
                category="gps_tracker",  # Same category
                manufacturer="TestCorp",  # Same manufacturer
                model="Model1",
                connection_type="bluetooth",
                connection_info={},
                capabilities=[],
                discovered_at="2023-01-01T00:00:00",
                confidence=0.9,  # Higher confidence
                metadata={},
            ),
        ]

        unique_devices = discovery_manager._deduplicate_devices(devices)

        assert len(unique_devices) == 1
        assert unique_devices[0].device_id == "device2"  # Should keep higher confidence

    async def test_shutdown(self, discovery_manager):
        """Test discovery manager shutdown."""
        # Add a real asyncio task and a listener
        task = asyncio.create_task(asyncio.sleep(0))
        discovery_manager._discovery_tasks.add(task)

        mock_listener = MagicMock()
        discovery_manager._listeners.append(mock_listener)

        # Add a discovered device
        sample_device = DiscoveredDevice(
            device_id="test",
            name="Test",
            category="gps_tracker",
            manufacturer="Test",
            model="Test",
            connection_type="test",
            connection_info={},
            capabilities=[],
            discovered_at="2023-01-01T00:00:00",
            confidence=0.8,
            metadata={},
        )
        discovery_manager._discovered_devices["test"] = sample_device

        await discovery_manager.async_shutdown()

        # Verify cleanup
        assert task.cancelled()
        mock_listener.assert_called_once()
        assert len(discovery_manager._listeners) == 0
        assert len(discovery_manager._discovered_devices) == 0

    async def test_callback_methods(self, discovery_manager):
        """Test callback methods for device retrieval."""
        # Add sample devices
        devices = [
            DiscoveredDevice(
                device_id="gps1",
                name="GPS Tracker",
                category="gps_tracker",
                manufacturer="TestCorp",
                model="GPS-1",
                connection_type="usb",
                connection_info={},
                capabilities=["gps"],
                discovered_at="2023-01-01T00:00:00",
                confidence=0.9,
                metadata={},
            ),
            DiscoveredDevice(
                device_id="feeder1",
                name="Smart Feeder",
                category="smart_feeder",
                manufacturer="TestCorp",
                model="Feed-1",
                connection_type="network",
                connection_info={},
                capabilities=["feeding"],
                discovered_at="2023-01-01T00:00:00",
                confidence=0.8,
                metadata={},
            ),
        ]

        for device in devices:
            discovery_manager._discovered_devices[device.device_id] = device

        # Test get_discovered_devices (all)
        all_devices = discovery_manager.get_discovered_devices()
        assert len(all_devices) == 2

        # Test get_discovered_devices (filtered)
        gps_devices = discovery_manager.get_discovered_devices("gps_tracker")
        assert len(gps_devices) == 1
        assert gps_devices[0].category == "gps_tracker"

        # Test get_device_by_id
        device = discovery_manager.get_device_by_id("gps1")
        assert device is not None
        assert device.name == "GPS Tracker"

        nonexistent = discovery_manager.get_device_by_id("nonexistent")
        assert nonexistent is None

        # Test is_scanning
        assert discovery_manager.is_scanning() is False

        discovery_manager._scan_active = True
        assert discovery_manager.is_scanning() is True

    async def test_wait_for_scan_completion(self, discovery_manager):
        """Test waiting for scan completion."""
        # Start with scan active
        discovery_manager._scan_active = True

        # Create a task that will set scan inactive after a short delay
        async def disable_scan():
            await asyncio.sleep(0.1)
            discovery_manager._scan_active = False

        task = asyncio.create_task(disable_scan())

        # Wait for scan completion
        await discovery_manager._wait_for_scan_completion()

        assert discovery_manager._scan_active is False
        await task  # Clean up

    async def test_wait_for_scan_completion_timeout(self, discovery_manager):
        """Test scan completion timeout."""
        discovery_manager._scan_active = True

        # Don't disable scan, should timeout
        start_time = asyncio.get_event_loop().time()
        await discovery_manager._wait_for_scan_completion()
        end_time = asyncio.get_event_loop().time()

        # Should have waited for some time but not indefinitely
        assert end_time - start_time >= 0.1  # Should wait at least some time


class TestDiscoveryErrorHandling:
    """Test error handling scenarios in discovery."""

    async def test_discovery_with_paw_control_error(self, discovery_manager):
        """Test handling of PawControlError during discovery."""
        discovery_manager._discover_usb_devices.side_effect = PawControlError(
            "USB discovery failed"
        )

        # Should handle PawControlError gracefully
        devices = await discovery_manager.async_discover_devices()

        assert isinstance(devices, list)

    async def test_discovery_method_exceptions(self, discovery_manager):
        """Test individual discovery method error handling."""
        # Test each discovery method with various exceptions
        categories = ["gps_tracker"]

        for method_name in [
            "_discover_usb_devices",
            "_discover_bluetooth_devices",
            "_discover_zeroconf_devices",
            "_discover_dhcp_devices",
            "_discover_upnp_devices",
        ]:
            method = getattr(discovery_manager, method_name)
            method.side_effect = Exception(f"{method_name} error")

        # Should not raise, should continue with available methods
        devices = await discovery_manager.async_discover_devices(categories)

        assert isinstance(devices, list)

    async def test_background_scanning_errors(self, hass: HomeAssistant):
        """Test error handling in background scanning."""
        discovery = PawControlDiscovery(hass)

        with patch.object(discovery, "_register_discovery_listeners") as mock_listeners:
            mock_listeners.side_effect = Exception("Listener error")

            # Should handle listener registration errors gracefully
            with patch.object(discovery, "_start_background_scanning"):
                with pytest.raises(HomeAssistantError):
                    await discovery.async_initialize()

    @pytest.mark.skip("Pending task error simulation")
    async def test_shutdown_with_task_errors(self, discovery_manager):
        """Test shutdown with task cancellation errors."""
        pass


class TestLegacyCompatibility:
    """Test legacy compatibility functions."""

    async def test_async_get_discovered_devices(self, hass: HomeAssistant):
        """Test legacy discovery function."""
        with patch.object(PawControlDiscovery, "async_initialize") as mock_init:
            with patch.object(
                PawControlDiscovery, "async_discover_devices"
            ) as mock_discover:
                with patch.object(
                    PawControlDiscovery, "async_shutdown"
                ) as mock_shutdown:
                    sample_device = DiscoveredDevice(
                        device_id="test",
                        name="Test Device",
                        category="gps_tracker",
                        manufacturer="Test",
                        model="Test",
                        connection_type="usb",
                        connection_info={"vid": "1234"},
                        capabilities=["gps"],
                        discovered_at="2023-01-01T00:00:00",
                        confidence=0.9,
                        metadata={},
                    )

                    mock_discover.return_value = [sample_device]

                    result = await async_get_discovered_devices(hass)

                    assert len(result) == 1
                    assert result[0]["source"] == "usb"
                    assert result[0]["data"]["device_id"] == "test"
                    assert result[0]["data"]["name"] == "Test Device"

                    mock_init.assert_called_once()
                    mock_discover.assert_called_once_with(quick_scan=True)
                    mock_shutdown.assert_called_once()

    async def test_async_get_discovered_devices_error_handling(
        self, hass: HomeAssistant
    ):
        """Test legacy discovery function error handling."""
        with patch.object(PawControlDiscovery, "async_initialize") as mock_init:
            mock_init.side_effect = Exception("Init error")

            result = await async_get_discovered_devices(hass)

            assert result == []

    async def test_async_start_discovery(self):
        """Test legacy start discovery function."""
        result = await async_start_discovery()
        assert result is True

    async def test_discovery_manager_singleton(self, hass: HomeAssistant):
        """Test global discovery manager singleton pattern."""
        # First call should create manager
        with patch.object(PawControlDiscovery, "async_initialize") as mock_init:
            manager1 = await async_get_discovery_manager(hass)
            mock_init.assert_called_once()

        # Second call should return same manager
        with patch.object(PawControlDiscovery, "async_initialize") as mock_init:
            manager2 = await async_get_discovery_manager(hass)
            mock_init.assert_not_called()  # Should not initialize again

        assert manager1 is manager2

    async def test_shutdown_discovery_manager(self, hass: HomeAssistant):
        """Test global discovery manager shutdown."""
        with patch.object(PawControlDiscovery, "async_initialize"):
            manager = await async_get_discovery_manager(hass)

        with patch.object(manager, "async_shutdown") as mock_shutdown:
            await async_shutdown_discovery_manager()
            mock_shutdown.assert_called_once()

        # After shutdown, should be able to create new manager
        with patch.object(PawControlDiscovery, "async_initialize"):
            new_manager = await async_get_discovery_manager(hass)
            assert new_manager is not manager


class TestDiscoveryIntegration:
    """Test integration scenarios for discovery."""

    async def test_full_discovery_cycle(self, hass: HomeAssistant):
        """Test a complete discovery cycle."""
        discovery = PawControlDiscovery(hass)

        with patch.multiple(
            discovery,
            _start_background_scanning=AsyncMock(),
            _register_discovery_listeners=AsyncMock(),
        ):
            await discovery.async_initialize()

            # Mock discovery to return various device types
            mock_devices = [
                DiscoveredDevice(
                    device_id=f"{protocol}_device",
                    name=f"{protocol.title()} Device",
                    category="gps_tracker",
                    manufacturer="TestCorp",
                    model="Test",
                    connection_type=protocol,
                    connection_info={},
                    capabilities=["gps"],
                    discovered_at="2023-01-01T00:00:00",
                    confidence=0.8,
                    metadata={"protocol": protocol},
                )
                for protocol in ["usb", "bluetooth", "zeroconf", "dhcp", "upnp"]
            ]

            with patch.multiple(
                discovery,
                _discover_usb_devices=AsyncMock(return_value=mock_devices[:1]),
                _discover_bluetooth_devices=AsyncMock(return_value=mock_devices[1:2]),
                _discover_zeroconf_devices=AsyncMock(return_value=mock_devices[2:3]),
                _discover_dhcp_devices=AsyncMock(return_value=mock_devices[3:4]),
                _discover_upnp_devices=AsyncMock(return_value=mock_devices[4:5]),
            ):
                devices = await discovery.async_discover_devices()

                assert len(devices) == 5
                assert all(device.category == "gps_tracker" for device in devices)

                # Test retrieval methods
                all_devices = discovery.get_discovered_devices()
                assert len(all_devices) == 5

                gps_devices = discovery.get_discovered_devices("gps_tracker")
                assert len(gps_devices) == 5

                other_devices = discovery.get_discovered_devices("smart_feeder")
                assert len(other_devices) == 0

            await discovery.async_shutdown()

    async def test_discovery_with_home_assistant_components(self, hass: HomeAssistant):
        """Test discovery integration with Home Assistant components."""
        discovery = PawControlDiscovery(hass)

        # Mock Home Assistant component availability
        hass.components = MagicMock()
        hass.components.usb = MagicMock()
        hass.components.bluetooth = MagicMock()
        hass.components.zeroconf = MagicMock()

        with patch.multiple(
            discovery,
            _start_background_scanning=AsyncMock(),
            _register_discovery_listeners=AsyncMock(),
        ):
            await discovery.async_initialize()

            # Should be able to access HA components
            devices = await discovery.async_discover_devices(quick_scan=True)

            assert isinstance(devices, list)

        await discovery.async_shutdown()
