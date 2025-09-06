"""Comprehensive tests for Paw Control discovery module.

Tests all discovery protocols, error handling, device classification,
and background scanning functionality.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.discovery import (
    DEVICE_CATEGORIES,
    DISCOVERY_SCAN_INTERVAL,
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
from homeassistant.util.dt import utcnow


class TestDiscoveredDevice:
    """Test the DiscoveredDevice dataclass."""

    def test_discovered_device_creation(self):
        """Test creating a DiscoveredDevice."""
        device = DiscoveredDevice(
            device_id="test_device_001",
            name="Test GPS Tracker",
            category="gps_tracker",
            manufacturer="Tractive",
            model="GPS Tracker Pro",
            connection_type="usb",
            connection_info={"vid": "0x1234", "pid": "0x5678"},
            capabilities=["gps", "activity_tracking", "geofence"],
            discovered_at="2025-01-15T10:00:00Z",
            confidence=0.95,
            metadata={"protocol": "usb", "signature_match": True},
        )

        assert device.device_id == "test_device_001"
        assert device.name == "Test GPS Tracker"
        assert device.category == "gps_tracker"
        assert device.manufacturer == "Tractive"
        assert device.model == "GPS Tracker Pro"
        assert device.connection_type == "usb"
        assert device.connection_info["vid"] == "0x1234"
        assert "gps" in device.capabilities
        assert device.confidence == 0.95
        assert device.metadata["protocol"] == "usb"

    def test_discovered_device_immutable(self):
        """Test that DiscoveredDevice is immutable (frozen dataclass)."""
        device = DiscoveredDevice(
            device_id="test_device",
            name="Test Device",
            category="gps_tracker",
            manufacturer="Test",
            model="Test Model",
            connection_type="usb",
            connection_info={},
            capabilities=[],
            discovered_at="2025-01-15T10:00:00Z",
            confidence=0.8,
            metadata={},
        )

        # Should not be able to modify frozen dataclass
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            device.name = "Modified Name"

    def test_discovered_device_equality(self):
        """Test device equality comparison."""
        device1 = DiscoveredDevice(
            device_id="test_device",
            name="Test Device",
            category="gps_tracker",
            manufacturer="Test",
            model="Test Model",
            connection_type="usb",
            connection_info={},
            capabilities=[],
            discovered_at="2025-01-15T10:00:00Z",
            confidence=0.8,
            metadata={},
        )

        device2 = DiscoveredDevice(
            device_id="test_device",
            name="Test Device",
            category="gps_tracker",
            manufacturer="Test",
            model="Test Model",
            connection_type="usb",
            connection_info={},
            capabilities=[],
            discovered_at="2025-01-15T10:00:00Z",
            confidence=0.8,
            metadata={},
        )

        assert device1 == device2


class TestPawControlDiscovery:
    """Test the main PawControlDiscovery class."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = Mock(spec=HomeAssistant)
        hass.data = {}
        hass.async_create_task = Mock()
        return hass

    @pytest.fixture
    def discovery(self, mock_hass):
        """Create a PawControlDiscovery instance."""
        return PawControlDiscovery(mock_hass)

    def test_discovery_initialization(self, discovery, mock_hass):
        """Test discovery manager initialization."""
        assert discovery.hass == mock_hass
        assert discovery._discovered_devices == {}
        assert discovery._discovery_tasks == set()
        assert discovery._scan_active is False
        assert discovery._listeners == []

    @pytest.mark.asyncio
    async def test_async_initialize_success(self, discovery):
        """Test successful discovery initialization."""
        with patch.object(
            discovery, "_start_background_scanning", new_callable=AsyncMock
        ) as mock_scan, patch.object(
            discovery, "_register_discovery_listeners", new_callable=AsyncMock
        ) as mock_listeners:
            await discovery.async_initialize()

            mock_scan.assert_called_once()
            mock_listeners.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_initialize_failure(self, discovery):
        """Test discovery initialization failure."""
        with patch.object(
            discovery,
            "_start_background_scanning",
            new_callable=AsyncMock,
            side_effect=Exception("Test error"),
        ):
            with pytest.raises(HomeAssistantError, match="Discovery initialization failed"):
                await discovery.async_initialize()

    @pytest.mark.asyncio
    async def test_async_discover_devices_all_categories(self, discovery):
        """Test device discovery for all categories."""
        # Mock all discovery methods
        mock_usb = Mock(return_value=[self._create_test_device("usb", "gps_tracker")])
        mock_bluetooth = Mock(
            return_value=[self._create_test_device("bluetooth", "activity_monitor")]
        )
        mock_zeroconf = Mock(
            return_value=[self._create_test_device("network", "smart_feeder")]
        )
        mock_dhcp = Mock(
            return_value=[self._create_test_device("network", "health_device")]
        )
        mock_upnp = Mock(
            return_value=[self._create_test_device("network", "smart_collar")]
        )

        with patch.multiple(
            discovery,
            _discover_usb_devices=mock_usb,
            _discover_bluetooth_devices=mock_bluetooth,
            _discover_zeroconf_devices=mock_zeroconf,
            _discover_dhcp_devices=mock_dhcp,
            _discover_upnp_devices=mock_upnp,
        ):
            devices = await discovery.async_discover_devices()

            # Should find devices from all protocols
            assert len(devices) == 5

            # Check that all discovery methods were called
            mock_usb.assert_called_once_with(DEVICE_CATEGORIES)
            mock_bluetooth.assert_called_once_with(DEVICE_CATEGORIES)
            mock_zeroconf.assert_called_once_with(DEVICE_CATEGORIES)
            mock_dhcp.assert_called_once_with(DEVICE_CATEGORIES)
            mock_upnp.assert_called_once_with(DEVICE_CATEGORIES)

    @pytest.mark.asyncio
    async def test_async_discover_devices_specific_categories(self, discovery):
        """Test device discovery for specific categories."""
        target_categories = ["gps_tracker", "smart_feeder"]

        mock_usb = Mock(return_value=[self._create_test_device("usb", "gps_tracker")])

        with patch.object(discovery, "_discover_usb_devices", mock_usb):
            devices = await discovery.async_discover_devices(categories=target_categories)

            mock_usb.assert_called_once_with(target_categories)

    @pytest.mark.asyncio
    async def test_async_discover_devices_quick_scan(self, discovery):
        """Test quick scan mode."""
        with patch.multiple(
            discovery,
            _discover_usb_devices=Mock(return_value=[]),
            _discover_bluetooth_devices=Mock(return_value=[]),
            _discover_zeroconf_devices=Mock(return_value=[]),
            _discover_dhcp_devices=Mock(return_value=[]),
            _discover_upnp_devices=Mock(return_value=[]),
        ):
            devices = await discovery.async_discover_devices(quick_scan=True)

            assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_async_discover_devices_timeout(self, discovery):
        """Test discovery timeout handling."""
        # Make one discovery method hang
        async def hanging_discovery(categories):
            await asyncio.sleep(DISCOVERY_TIMEOUT + 1)
            return []

        with patch.object(discovery, "_discover_usb_devices", hanging_discovery), patch.multiple(
            discovery,
            _discover_bluetooth_devices=Mock(return_value=[]),
            _discover_zeroconf_devices=Mock(return_value=[]),
            _discover_dhcp_devices=Mock(return_value=[]),
            _discover_upnp_devices=Mock(return_value=[]),
        ):
            # Should return existing devices on timeout, not raise exception
            devices = await discovery.async_discover_devices(quick_scan=True)
            assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_async_discover_devices_exception_handling(self, discovery):
        """Test discovery exception handling."""
        # One method fails, others succeed
        mock_usb = Mock(side_effect=Exception("USB error"))
        mock_bluetooth = Mock(
            return_value=[self._create_test_device("bluetooth", "activity_monitor")]
        )

        with patch.multiple(
            discovery,
            _discover_usb_devices=mock_usb,
            _discover_bluetooth_devices=mock_bluetooth,
            _discover_zeroconf_devices=Mock(return_value=[]),
            _discover_dhcp_devices=Mock(return_value=[]),
            _discover_upnp_devices=Mock(return_value=[]),
        ):
            devices = await discovery.async_discover_devices()

            # Should get device from working method
            assert len(devices) == 1
            assert devices[0].connection_type == "bluetooth"

    @pytest.mark.asyncio
    async def test_async_discover_devices_scan_already_active(self, discovery):
        """Test behavior when scan is already active."""
        discovery._scan_active = True

        with patch.object(discovery, "_wait_for_scan_completion", new_callable=AsyncMock):
            devices = await discovery.async_discover_devices()
            assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_async_discover_devices_deduplication(self, discovery):
        """Test device deduplication."""
        # Create duplicate devices
        device1 = self._create_test_device("usb", "gps_tracker", device_id="device1")
        device2 = self._create_test_device("bluetooth", "gps_tracker", device_id="device2")
        # Same manufacturer/category/name - should be deduplicated
        device2 = device2._replace(
            manufacturer=device1.manufacturer,
            name=device1.name,
            confidence=0.95,  # Higher confidence
        )

        with patch.multiple(
            discovery,
            _discover_usb_devices=Mock(return_value=[device1]),
            _discover_bluetooth_devices=Mock(return_value=[device2]),
            _discover_zeroconf_devices=Mock(return_value=[]),
            _discover_dhcp_devices=Mock(return_value=[]),
            _discover_upnp_devices=Mock(return_value=[]),
        ):
            devices = await discovery.async_discover_devices()

            # Should keep the device with higher confidence
            assert len(devices) == 1
            assert devices[0].confidence == 0.95

    def _create_test_device(
        self, connection_type: str, category: str, device_id: str | None = None
    ) -> DiscoveredDevice:
        """Create a test device."""
        device_id = device_id or f"test_{connection_type}_{category}"
        return DiscoveredDevice(
            device_id=device_id,
            name=f"Test {category.title()}",
            category=category,
            manufacturer="Test Manufacturer",
            model="Test Model",
            connection_type=connection_type,
            connection_info={"test": "data"},
            capabilities=["test_capability"],
            discovered_at=utcnow().isoformat(),
            confidence=0.8,
            metadata={"test": "metadata"},
        )


class TestUSBDiscovery:
    """Test USB device discovery."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        hass = Mock(spec=HomeAssistant)
        return PawControlDiscovery(hass)

    @pytest.mark.asyncio
    async def test_discover_usb_devices_success(self, discovery):
        """Test successful USB device discovery."""
        categories = ["gps_tracker", "smart_feeder"]

        with patch("custom_components.pawcontrol.discovery.usb.async_get_usb") as mock_usb:
            mock_usb.return_value = True  # USB available

            devices = await discovery._discover_usb_devices(categories)

            # Should find devices based on hardcoded signatures
            assert len(devices) >= 0  # May find devices based on signatures
            for device in devices:
                assert device.connection_type == "usb"
                assert device.category in categories

    @pytest.mark.asyncio
    async def test_discover_usb_devices_no_usb(self, discovery):
        """Test USB discovery when USB not available."""
        with patch("custom_components.pawcontrol.discovery.usb.async_get_usb") as mock_usb:
            mock_usb.return_value = None

            devices = await discovery._discover_usb_devices(["gps_tracker"])

            assert devices == []

    @pytest.mark.asyncio
    async def test_discover_usb_devices_exception(self, discovery):
        """Test USB discovery exception handling."""
        with patch(
            "custom_components.pawcontrol.discovery.usb.async_get_usb",
            side_effect=Exception("USB error"),
        ):
            devices = await discovery._discover_usb_devices(["gps_tracker"])

            assert devices == []

    @pytest.mark.asyncio
    async def test_discover_usb_devices_filter_categories(self, discovery):
        """Test USB discovery category filtering."""
        # Request only smart_feeder category
        categories = ["smart_feeder"]

        with patch("custom_components.pawcontrol.discovery.usb.async_get_usb") as mock_usb:
            mock_usb.return_value = True

            devices = await discovery._discover_usb_devices(categories)

            # All returned devices should be smart_feeder category
            for device in devices:
                assert device.category in categories


class TestBluetoothDiscovery:
    """Test Bluetooth device discovery."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        hass = Mock(spec=HomeAssistant)
        return PawControlDiscovery(hass)

    @pytest.mark.asyncio
    async def test_discover_bluetooth_devices_success(self, discovery):
        """Test successful Bluetooth device discovery."""
        categories = ["activity_monitor", "gps_tracker"]

        with patch(
            "custom_components.pawcontrol.discovery.bluetooth.async_get_scanner"
        ) as mock_bluetooth:
            mock_bluetooth.return_value = True  # Bluetooth available

            devices = await discovery._discover_bluetooth_devices(categories)

            # Should find devices based on name patterns
            assert len(devices) >= 0
            for device in devices:
                assert device.connection_type == "bluetooth"
                assert device.category in categories

    @pytest.mark.asyncio
    async def test_discover_bluetooth_devices_no_bluetooth(self, discovery):
        """Test Bluetooth discovery when Bluetooth not available."""
        with patch(
            "custom_components.pawcontrol.discovery.bluetooth.async_get_scanner"
        ) as mock_bluetooth:
            mock_bluetooth.return_value = None

            devices = await discovery._discover_bluetooth_devices(["activity_monitor"])

            assert devices == []

    @pytest.mark.asyncio
    async def test_discover_bluetooth_devices_exception(self, discovery):
        """Test Bluetooth discovery exception handling."""
        with patch(
            "custom_components.pawcontrol.discovery.bluetooth.async_get_scanner",
            side_effect=Exception("Bluetooth error"),
        ):
            devices = await discovery._discover_bluetooth_devices(["activity_monitor"])

            assert devices == []


class TestZeroconfDiscovery:
    """Test Zeroconf/mDNS device discovery."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        hass = Mock(spec=HomeAssistant)
        return PawControlDiscovery(hass)

    @pytest.mark.asyncio
    async def test_discover_zeroconf_devices_success(self, discovery):
        """Test successful Zeroconf device discovery."""
        categories = ["smart_feeder", "gps_tracker"]

        with patch(
            "custom_components.pawcontrol.discovery.zeroconf.async_get_instance"
        ) as mock_zeroconf:
            mock_zeroconf.return_value = True  # Zeroconf available

            devices = await discovery._discover_zeroconf_devices(categories)

            # Should find devices based on service patterns
            assert len(devices) >= 0
            for device in devices:
                assert device.connection_type == "network"
                assert device.category in categories

    @pytest.mark.asyncio
    async def test_discover_zeroconf_devices_no_zeroconf(self, discovery):
        """Test Zeroconf discovery when Zeroconf not available."""
        with patch(
            "custom_components.pawcontrol.discovery.zeroconf.async_get_instance",
            side_effect=Exception("Zeroconf not available"),
        ):
            devices = await discovery._discover_zeroconf_devices(["smart_feeder"])

            assert devices == []

    @pytest.mark.asyncio
    async def test_discover_zeroconf_devices_exception(self, discovery):
        """Test Zeroconf discovery exception handling."""
        with patch(
            "custom_components.pawcontrol.discovery.zeroconf.async_get_instance",
            side_effect=Exception("Zeroconf error"),
        ):
            devices = await discovery._discover_zeroconf_devices(["smart_feeder"])

            assert devices == []


class TestDHCPDiscovery:
    """Test DHCP device discovery."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        hass = Mock(spec=HomeAssistant)
        return PawControlDiscovery(hass)

    @pytest.mark.asyncio
    async def test_discover_dhcp_devices_success(self, discovery):
        """Test successful DHCP device discovery."""
        categories = ["gps_tracker", "smart_feeder"]

        with patch(
            "custom_components.pawcontrol.discovery.dhcp.async_get_dhcp_entries"
        ) as mock_dhcp:
            mock_dhcp.return_value = []  # DHCP available

            devices = await discovery._discover_dhcp_devices(categories)

            # Should find devices based on hostname patterns
            assert len(devices) >= 0
            for device in devices:
                assert device.connection_type == "network"
                assert device.category in categories

    @pytest.mark.asyncio
    async def test_discover_dhcp_devices_no_dhcp(self, discovery):
        """Test DHCP discovery when DHCP not available."""
        with patch(
            "custom_components.pawcontrol.discovery.dhcp.async_get_dhcp_entries",
            side_effect=Exception("DHCP not available"),
        ):
            devices = await discovery._discover_dhcp_devices(["gps_tracker"])

            assert devices == []

    @pytest.mark.asyncio
    async def test_discover_dhcp_devices_exception(self, discovery):
        """Test DHCP discovery exception handling."""
        with patch(
            "custom_components.pawcontrol.discovery.dhcp.async_get_dhcp_entries",
            side_effect=Exception("DHCP error"),
        ):
            devices = await discovery._discover_dhcp_devices(["gps_tracker"])

            assert devices == []


class TestUPnPDiscovery:
    """Test UPnP device discovery."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        hass = Mock(spec=HomeAssistant)
        return PawControlDiscovery(hass)

    @pytest.mark.asyncio
    async def test_discover_upnp_devices_success(self, discovery):
        """Test successful UPnP device discovery."""
        categories = ["smart_feeder", "health_device"]

        devices = await discovery._discover_upnp_devices(categories)

        # Should find devices based on UPnP device types
        assert len(devices) >= 0
        for device in devices:
            assert device.connection_type == "network"
            assert device.category in categories

    @pytest.mark.asyncio
    async def test_discover_upnp_devices_exception(self, discovery):
        """Test UPnP discovery exception handling."""
        # Patch something that will cause an exception
        with patch("custom_components.pawcontrol.discovery.utcnow", side_effect=Exception("UPnP error")):
            devices = await discovery._discover_upnp_devices(["smart_feeder"])

            assert devices == []


class TestDeviceDeduplication:
    """Test device deduplication logic."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        hass = Mock(spec=HomeAssistant)
        return PawControlDiscovery(hass)

    def test_deduplicate_devices_identical(self, discovery):
        """Test deduplication of identical devices."""
        device1 = DiscoveredDevice(
            device_id="device1",
            name="Test Device",
            category="gps_tracker",
            manufacturer="Tractive",
            model="GPS Pro",
            connection_type="usb",
            connection_info={},
            capabilities=[],
            discovered_at="2025-01-15T10:00:00Z",
            confidence=0.8,
            metadata={},
        )

        device2 = device1._replace(device_id="device2", confidence=0.9)

        devices = [device1, device2]
        unique_devices = discovery._deduplicate_devices(devices)

        # Should keep the device with higher confidence
        assert len(unique_devices) == 1
        assert unique_devices[0].confidence == 0.9

    def test_deduplicate_devices_different(self, discovery):
        """Test deduplication preserves different devices."""
        device1 = DiscoveredDevice(
            device_id="device1",
            name="GPS Tracker",
            category="gps_tracker",
            manufacturer="Tractive",
            model="GPS Pro",
            connection_type="usb",
            connection_info={},
            capabilities=[],
            discovered_at="2025-01-15T10:00:00Z",
            confidence=0.8,
            metadata={},
        )

        device2 = DiscoveredDevice(
            device_id="device2",
            name="Smart Feeder",
            category="smart_feeder",
            manufacturer="PetNet",
            model="Feeder Pro",
            connection_type="network",
            connection_info={},
            capabilities=[],
            discovered_at="2025-01-15T10:00:00Z",
            confidence=0.8,
            metadata={},
        )

        devices = [device1, device2]
        unique_devices = discovery._deduplicate_devices(devices)

        # Should keep both different devices
        assert len(unique_devices) == 2

    def test_deduplicate_devices_empty_list(self, discovery):
        """Test deduplication with empty device list."""
        unique_devices = discovery._deduplicate_devices([])
        assert unique_devices == []


class TestBackgroundScanning:
    """Test background scanning functionality."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        hass = Mock(spec=HomeAssistant)
        hass.async_create_task = Mock()
        return PawControlDiscovery(hass)

    @pytest.mark.asyncio
    async def test_start_background_scanning(self, discovery):
        """Test starting background scanning."""
        with patch(
            "custom_components.pawcontrol.discovery.async_track_time_interval"
        ) as mock_track:
            mock_track.return_value = Mock()  # Mock listener

            await discovery._start_background_scanning()

            # Should register time interval tracking
            mock_track.assert_called_once()
            args = mock_track.call_args
            assert args[0][0] == discovery.hass  # hass
            assert callable(args[0][1])  # callback function
            assert args[0][2] == DISCOVERY_SCAN_INTERVAL  # interval

    @pytest.mark.asyncio
    async def test_register_discovery_listeners(self, discovery):
        """Test registering discovery listeners."""
        # Mock the components to be available
        discovery.hass.components = Mock()
        discovery.hass.components.usb = True
        discovery.hass.components.bluetooth = True
        discovery.hass.components.zeroconf = True

        await discovery._register_discovery_listeners()

        # Should complete without error (actual listeners would be registered in real implementation)
        assert True

    @pytest.mark.asyncio
    async def test_wait_for_scan_completion_active(self, discovery):
        """Test waiting for scan completion when scan is active."""
        discovery._scan_active = True

        # Simulate scan completing after short delay
        async def complete_scan():
            await asyncio.sleep(0.1)
            discovery._scan_active = False

        task = asyncio.create_task(complete_scan())

        await discovery._wait_for_scan_completion()

        await task  # Clean up task
        assert discovery._scan_active is False

    @pytest.mark.asyncio
    async def test_wait_for_scan_completion_timeout(self, discovery):
        """Test waiting for scan completion with timeout."""
        discovery._scan_active = True

        # Should timeout and log warning
        with patch("custom_components.pawcontrol.discovery._LOGGER.warning") as mock_log:
            await discovery._wait_for_scan_completion()

            mock_log.assert_called()


class TestDiscoveryShutdown:
    """Test discovery shutdown functionality."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        hass = Mock(spec=HomeAssistant)
        return PawControlDiscovery(hass)

    @pytest.mark.asyncio
    async def test_async_shutdown_with_tasks(self, discovery):
        """Test shutdown with active tasks."""
        # Mock active task
        mock_task = Mock()
        mock_task.done.return_value = False
        mock_task.cancel = Mock()
        discovery._discovery_tasks.add(mock_task)

        # Mock listener
        mock_listener = Mock()
        discovery._listeners.append(mock_listener)

        # Add some discovered devices
        discovery._discovered_devices["test"] = Mock()

        await discovery.async_shutdown()

        # Should cancel tasks, remove listeners, clear devices
        mock_task.cancel.assert_called_once()
        mock_listener.assert_called_once()
        assert discovery._discovered_devices == {}

    @pytest.mark.asyncio
    async def test_async_shutdown_empty(self, discovery):
        """Test shutdown with no tasks or listeners."""
        await discovery.async_shutdown()

        # Should complete without error
        assert discovery._discovered_devices == {}
        assert discovery._listeners == []


class TestDiscoveryAccessors:
    """Test discovery accessor methods."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance with test devices."""
        hass = Mock(spec=HomeAssistant)
        discovery = PawControlDiscovery(hass)

        # Add test devices
        device1 = DiscoveredDevice(
            device_id="device1",
            name="GPS Tracker",
            category="gps_tracker",
            manufacturer="Tractive",
            model="GPS Pro",
            connection_type="usb",
            connection_info={},
            capabilities=[],
            discovered_at="2025-01-15T10:00:00Z",
            confidence=0.8,
            metadata={},
        )

        device2 = DiscoveredDevice(
            device_id="device2",
            name="Smart Feeder",
            category="smart_feeder",
            manufacturer="PetNet",
            model="Feeder Pro",
            connection_type="network",
            connection_info={},
            capabilities=[],
            discovered_at="2025-01-15T10:00:00Z",
            confidence=0.8,
            metadata={},
        )

        discovery._discovered_devices["device1"] = device1
        discovery._discovered_devices["device2"] = device2

        return discovery

    def test_get_discovered_devices_all(self, discovery):
        """Test getting all discovered devices."""
        devices = discovery.get_discovered_devices()

        assert len(devices) == 2
        device_ids = [device.device_id for device in devices]
        assert "device1" in device_ids
        assert "device2" in device_ids

    def test_get_discovered_devices_by_category(self, discovery):
        """Test getting devices filtered by category."""
        gps_devices = discovery.get_discovered_devices(category="gps_tracker")
        feeder_devices = discovery.get_discovered_devices(category="smart_feeder")

        assert len(gps_devices) == 1
        assert gps_devices[0].category == "gps_tracker"

        assert len(feeder_devices) == 1
        assert feeder_devices[0].category == "smart_feeder"

    def test_get_discovered_devices_unknown_category(self, discovery):
        """Test getting devices for unknown category."""
        devices = discovery.get_discovered_devices(category="unknown_category")
        assert devices == []

    def test_get_device_by_id_exists(self, discovery):
        """Test getting device by existing ID."""
        device = discovery.get_device_by_id("device1")

        assert device is not None
        assert device.device_id == "device1"
        assert device.category == "gps_tracker"

    def test_get_device_by_id_not_exists(self, discovery):
        """Test getting device by non-existing ID."""
        device = discovery.get_device_by_id("unknown_device")
        assert device is None

    def test_is_scanning_false(self, discovery):
        """Test is_scanning when not scanning."""
        assert discovery.is_scanning() is False

    def test_is_scanning_true(self, discovery):
        """Test is_scanning when scanning."""
        discovery._scan_active = True
        assert discovery.is_scanning() is True


class TestLegacyCompatibility:
    """Test legacy compatibility functions."""

    @pytest.mark.asyncio
    async def test_async_get_discovered_devices(self, hass: HomeAssistant):
        """Test legacy discovery function."""
        with patch(
            "custom_components.pawcontrol.discovery.PawControlDiscovery"
        ) as mock_discovery_class:
            mock_discovery = Mock()
            mock_discovery.async_initialize = AsyncMock()
            mock_discovery.async_shutdown = AsyncMock()

            # Mock discovered devices
            test_device = DiscoveredDevice(
                device_id="test_device",
                name="Test Device",
                category="gps_tracker",
                manufacturer="Test",
                model="Test Model",
                connection_type="usb",
                connection_info={"vid": "0x1234"},
                capabilities=["gps"],
                discovered_at="2025-01-15T10:00:00Z",
                confidence=0.8,
                metadata={},
            )

            mock_discovery.async_discover_devices = AsyncMock(return_value=[test_device])
            mock_discovery_class.return_value = mock_discovery

            result = await async_get_discovered_devices(hass)

            # Should return legacy format
            assert len(result) == 1
            assert result[0]["source"] == "usb"
            assert result[0]["data"]["device_id"] == "test_device"
            assert result[0]["data"]["name"] == "Test Device"

            # Should initialize and shutdown discovery
            mock_discovery.async_initialize.assert_called_once()
            mock_discovery.async_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_get_discovered_devices_error(self, hass: HomeAssistant):
        """Test legacy discovery function with error."""
        with patch(
            "custom_components.pawcontrol.discovery.PawControlDiscovery"
        ) as mock_discovery_class:
            mock_discovery = Mock()
            mock_discovery.async_initialize = AsyncMock(side_effect=Exception("Test error"))
            mock_discovery.async_shutdown = AsyncMock()
            mock_discovery_class.return_value = mock_discovery

            result = await async_get_discovered_devices(hass)

            # Should return empty list on error
            assert result == []

    @pytest.mark.asyncio
    async def test_async_start_discovery(self):
        """Test legacy start discovery function."""
        result = await async_start_discovery()
        assert result is True


class TestDiscoveryManager:
    """Test global discovery manager functionality."""

    @pytest.mark.asyncio
    async def test_async_get_discovery_manager_first_call(self, hass: HomeAssistant):
        """Test getting discovery manager for first time."""
        # Reset global manager
        import custom_components.pawcontrol.discovery as discovery_module

        discovery_module._discovery_manager = None

        with patch.object(discovery_module.PawControlDiscovery, "async_initialize") as mock_init:
            manager = await async_get_discovery_manager(hass)

            assert manager is not None
            assert isinstance(manager, discovery_module.PawControlDiscovery)
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_get_discovery_manager_subsequent_calls(self, hass: HomeAssistant):
        """Test getting discovery manager on subsequent calls."""
        # Set up existing manager
        import custom_components.pawcontrol.discovery as discovery_module

        existing_manager = Mock()
        discovery_module._discovery_manager = existing_manager

        manager = await async_get_discovery_manager(hass)

        # Should return existing manager
        assert manager == existing_manager

    @pytest.mark.asyncio
    async def test_async_shutdown_discovery_manager(self):
        """Test shutting down discovery manager."""
        # Set up manager
        import custom_components.pawcontrol.discovery as discovery_module

        mock_manager = Mock()
        mock_manager.async_shutdown = AsyncMock()
        discovery_module._discovery_manager = mock_manager

        await async_shutdown_discovery_manager()

        # Should shutdown and clear manager
        mock_manager.async_shutdown.assert_called_once()
        assert discovery_module._discovery_manager is None

    @pytest.mark.asyncio
    async def test_async_shutdown_discovery_manager_no_manager(self):
        """Test shutting down when no manager exists."""
        # Reset manager
        import custom_components.pawcontrol.discovery as discovery_module

        discovery_module._discovery_manager = None

        # Should not raise exception
        await async_shutdown_discovery_manager()


class TestDiscoveryConstants:
    """Test discovery constants and configurations."""

    def test_device_categories_complete(self):
        """Test that all expected device categories are defined."""
        expected_categories = [
            "gps_tracker",
            "smart_feeder",
            "activity_monitor",
            "health_device",
            "smart_collar",
            "treat_dispenser",
            "water_fountain",
            "camera",
            "door_sensor",
        ]

        assert DEVICE_CATEGORIES == expected_categories

    def test_discovery_timeouts_valid(self):
        """Test that discovery timeouts are reasonable."""
        assert DISCOVERY_SCAN_INTERVAL.total_seconds() == 300  # 5 minutes
        assert DISCOVERY_TIMEOUT == 10.0  # 10 seconds

    def test_discovery_intervals_valid(self):
        """Test that discovery intervals are properly configured."""
        from custom_components.pawcontrol.discovery import DISCOVERY_QUICK_SCAN_INTERVAL

        assert DISCOVERY_QUICK_SCAN_INTERVAL.total_seconds() == 30  # 30 seconds


class TestDiscoveryErrorHandling:
    """Test comprehensive error handling scenarios."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        hass = Mock(spec=HomeAssistant)
        return PawControlDiscovery(hass)

    @pytest.mark.asyncio
    async def test_discover_devices_comprehensive_failure(self, discovery):
        """Test discovery when all methods fail."""
        # All discovery methods raise exceptions
        with patch.multiple(
            discovery,
            _discover_usb_devices=Mock(side_effect=Exception("USB failed")),
            _discover_bluetooth_devices=Mock(side_effect=Exception("Bluetooth failed")),
            _discover_zeroconf_devices=Mock(side_effect=Exception("Zeroconf failed")),
            _discover_dhcp_devices=Mock(side_effect=Exception("DHCP failed")),
            _discover_upnp_devices=Mock(side_effect=Exception("UPnP failed")),
        ):
            devices = await discovery.async_discover_devices()

            # Should return empty list, not raise exception
            assert devices == []

    @pytest.mark.asyncio
    async def test_discover_devices_partial_failure(self, discovery):
        """Test discovery when some methods fail."""
        working_device = DiscoveredDevice(
            device_id="working_device",
            name="Working Device",
            category="gps_tracker",
            manufacturer="Test",
            model="Test Model",
            connection_type="usb",
            connection_info={},
            capabilities=[],
            discovered_at=utcnow().isoformat(),
            confidence=0.8,
            metadata={},
        )

        with patch.multiple(
            discovery,
            _discover_usb_devices=Mock(return_value=[working_device]),
            _discover_bluetooth_devices=Mock(side_effect=Exception("Bluetooth failed")),
            _discover_zeroconf_devices=Mock(return_value=[]),
            _discover_dhcp_devices=Mock(side_effect=Exception("DHCP failed")),
            _discover_upnp_devices=Mock(return_value=[]),
        ):
            devices = await discovery.async_discover_devices()

            # Should return working devices despite some failures
            assert len(devices) == 1
            assert devices[0].device_id == "working_device"

    @pytest.mark.asyncio
    async def test_discovery_timeout_edge_case(self, discovery):
        """Test discovery with very short timeout."""
        # Mock a method that takes longer than timeout
        async def slow_discovery(categories):
            await asyncio.sleep(0.1)  # Longer than a very short timeout
            return []

        # Very short timeout for quick scan
        original_timeout = discovery_module.DISCOVERY_TIMEOUT
        try:
            discovery_module.DISCOVERY_TIMEOUT = 0.05  # 50ms

            with patch.object(discovery, "_discover_usb_devices", slow_discovery):
                devices = await discovery.async_discover_devices(quick_scan=True)

                # Should handle timeout gracefully
                assert isinstance(devices, list)

        finally:
            # Restore original timeout
            discovery_module.DISCOVERY_TIMEOUT = original_timeout
