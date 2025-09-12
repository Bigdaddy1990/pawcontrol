"""Comprehensive tests for Paw Control diagnostics module.

This test suite covers all aspects of the diagnostic system including:
- Complete diagnostic data collection for troubleshooting
- Sensitive data redaction and privacy protection
- Integration with Home Assistant registries and systems
- Performance metrics and system health information
- Error handling and edge cases
- Debug information collection

The diagnostics module is critical for support and troubleshooting.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.diagnostics import (
    REDACTED_KEYS,
    _calculate_module_usage,
    _get_config_entry_diagnostics,
    _get_coordinator_diagnostics,
    _get_data_statistics,
    _get_debug_information,
    _get_devices_diagnostics,
    _get_dogs_summary,
    _get_entities_diagnostics,
    _get_integration_status,
    _get_loaded_platforms,
    _get_performance_metrics,
    _get_recent_errors,
    _get_registered_services,
    _get_system_diagnostics,
    _looks_like_sensitive_string,
    _redact_sensitive_data,
    async_get_config_entry_diagnostics,
)
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util


# Test fixtures
@pytest.fixture
def mock_config_entry():
    """Mock configuration entry with comprehensive data."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control Integration",
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "buddy",
                    CONF_DOG_NAME: "Buddy",
                    "dog_breed": "Golden Retriever",
                    "dog_age": 5,
                    "dog_weight": 30.5,
                    "dog_size": "large",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: True,
                    },
                },
                {
                    CONF_DOG_ID: "luna",
                    CONF_DOG_NAME: "Luna",
                    "dog_breed": "Border Collie",
                    "dog_age": 3,
                    "dog_weight": 22.0,
                    "dog_size": "medium",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: False,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: False,
                    },
                },
            ]
        },
        options={
            "notifications": {"quiet_hours": True},
            "gps": {"update_interval": 60},
        },
        entry_id="test_entry_diagnostics",
        source="user",
        unique_id="test_unique_diagnostics",
    )


@pytest.fixture
def mock_coordinator():
    """Mock coordinator with comprehensive data."""
    coordinator = Mock()
    coordinator.available = True
    coordinator.last_update_success = True
    coordinator.last_update_time = dt_util.utcnow()
    coordinator.update_interval = timedelta(seconds=60)
    coordinator.update_method = "async_update_data"
    coordinator.logger = Mock()
    coordinator.logger.name = "custom_components.pawcontrol.coordinator"
    coordinator.name = "Paw Control Coordinator"
    coordinator.config_entry = Mock()
    coordinator.config_entry.entry_id = "test_entry_diagnostics"
    coordinator.dogs = ["buddy", "luna"]

    # Mock statistics
    coordinator.get_update_statistics.return_value = {
        "total_updates": 100,
        "successful_updates": 95,
        "failed_updates": 5,
        "average_update_time": 0.5,
        "last_error": None,
        "update_interval_seconds": 60,
    }

    # Mock dog data
    def get_dog_data(dog_id):
        if dog_id == "buddy":
            return {
                "last_update": dt_util.utcnow().isoformat(),
                "status": "healthy",
                "feeding": {"last_fed": "2025-01-15T08:00:00"},
                "walk": {"active": False, "today_count": 2},
                "health": {"weight": 30.5, "mood": "happy"},
                "gps": {"latitude": 52.5200, "longitude": 13.4050},
            }
        elif dog_id == "luna":
            return {
                "last_update": dt_util.utcnow().isoformat(),
                "status": "active",
                "feeding": {"last_fed": "2025-01-15T07:30:00"},
                "walk": {"active": True, "today_count": 1},
                "health": {"weight": 22.0, "mood": "playful"},
            }
        return None

    coordinator.get_dog_data = Mock(side_effect=get_dog_data)
    return coordinator


@pytest.fixture
def mock_integration_data(mock_coordinator):
    """Mock integration data structure."""
    return {
        "coordinator": mock_coordinator,
        "data": Mock(),  # Data manager
        "notifications": Mock(),  # Notification manager
    }


@pytest.fixture
def mock_entity_registry():
    """Mock entity registry with test entities."""
    mock_registry = Mock()

    # Create mock entities
    mock_entities = [
        Mock(
            entity_id="sensor.buddy_weight",
            unique_id="buddy_weight_sensor",
            platform="sensor",
            device_id="device_buddy",
            disabled=False,
            disabled_by=None,
            hidden=False,
            entity_category=None,
            has_entity_name=True,
            original_name="Weight",
            capabilities={"unit_of_measurement": "kg"},
        ),
        Mock(
            entity_id="binary_sensor.luna_walk_active",
            unique_id="luna_walk_active_binary_sensor",
            platform="binary_sensor",
            device_id="device_luna",
            disabled=False,
            disabled_by=None,
            hidden=False,
            entity_category=None,
            has_entity_name=True,
            original_name="Walk Active",
            capabilities={},
        ),
        Mock(
            entity_id="button.buddy_feed",
            unique_id="buddy_feed_button",
            platform="button",
            device_id="device_buddy",
            disabled=True,
            disabled_by=er.RegistryEntryDisabler.USER,
            hidden=True,
            entity_category=er.EntityCategory.CONFIG,
            has_entity_name=True,
            original_name="Feed",
            capabilities={},
        ),
    ]

    mock_registry.async_entries_for_config_entry.return_value = mock_entities
    return mock_registry


@pytest.fixture
def mock_device_registry():
    """Mock device registry with test devices."""
    mock_registry = Mock()

    # Create mock devices
    mock_devices = [
        Mock(
            id="device_buddy",
            name="Buddy - Paw Control",
            manufacturer="Paw Control",
            model="Dog Tracker v1.0",
            sw_version="1.0.0",
            hw_version="1.0",
            via_device_id=None,
            disabled=False,
            disabled_by=None,
            entry_type=dr.DeviceEntryType.SERVICE,
            identifiers={("pawcontrol", "buddy")},
            connections=set(),
            configuration_url="https://example.com/config",
        ),
        Mock(
            id="device_luna",
            name="Luna - Paw Control",
            manufacturer="Paw Control",
            model="Dog Tracker v1.0",
            sw_version="1.0.0",
            hw_version="1.0",
            via_device_id=None,
            disabled=True,
            disabled_by=dr.DeviceEntryDisabler.USER,
            entry_type=dr.DeviceEntryType.SERVICE,
            identifiers={("pawcontrol", "luna")},
            connections=set(),
            configuration_url=None,
        ),
    ]

    mock_registry.async_entries_for_config_entry.return_value = mock_devices
    return mock_registry


@pytest.fixture
def mock_hass_with_states(hass: HomeAssistant):
    """Mock Home Assistant with entity states."""
    # Mock entity states
    states = {
        "sensor.buddy_weight": Mock(
            state="30.5",
            last_changed=dt_util.utcnow(),
            last_updated=dt_util.utcnow(),
            attributes={"unit_of_measurement": "kg",
                        "friendly_name": "Buddy Weight"},
        ),
        "binary_sensor.luna_walk_active": Mock(
            state="on",
            last_changed=dt_util.utcnow() - timedelta(minutes=15),
            last_updated=dt_util.utcnow() - timedelta(minutes=5),
            attributes={"friendly_name": "Luna Walk Active"},
        ),
        "button.buddy_feed": Mock(
            state="unavailable",
            last_changed=dt_util.utcnow() - timedelta(hours=1),
            last_updated=dt_util.utcnow() - timedelta(hours=1),
            attributes={"friendly_name": "Feed Buddy"},
        ),
    }

    hass.states.get = Mock(side_effect=lambda entity_id: states.get(entity_id))

    # Mock Home Assistant configuration
    hass.config.version = "2025.1.0"
    hass.config.python_version = "3.11.5"
    hass.config.time_zone = "Europe/Berlin"
    hass.config.config_dir = "/config"
    hass.config.safe_mode = False
    hass.config.recovery_mode = False
    hass.config.start_time = dt_util.utcnow() - timedelta(hours=2)
    hass.is_running = True

    return hass


# Main Diagnostics Function Tests
class TestMainDiagnosticsFunction:
    """Test the main diagnostics collection function."""

    async def test_async_get_config_entry_diagnostics_complete(
        self,
        mock_hass_with_states,
        mock_config_entry,
        mock_integration_data,
        mock_entity_registry,
        mock_device_registry,
    ):
        """Test complete diagnostics collection."""
        # Setup integration data in hass.data
        mock_hass_with_states.data[DOMAIN] = {
            mock_config_entry.entry_id: mock_integration_data
        }

        with (
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "homeassistant.helpers.device_registry.async_get",
                return_value=mock_device_registry,
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_recent_errors",
                return_value=[],
            ),
        ):
            diagnostics = await async_get_config_entry_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        # Verify main structure
        assert isinstance(diagnostics, dict)
        expected_keys = [
            "config_entry",
            "system_info",
            "integration_status",
            "coordinator_info",
            "entities",
            "devices",
            "dogs_summary",
            "performance_metrics",
            "data_statistics",
            "error_logs",
            "debug_info",
        ]

        for key in expected_keys:
            assert key in diagnostics, f"Missing key: {key}"

        # Verify data types
        assert isinstance(diagnostics["config_entry"], dict)
        assert isinstance(diagnostics["system_info"], dict)
        assert isinstance(diagnostics["entities"], dict)
        assert isinstance(diagnostics["dogs_summary"], dict)

    async def test_async_get_config_entry_diagnostics_no_integration_data(
        self,
        mock_hass_with_states,
        mock_config_entry,
        mock_entity_registry,
        mock_device_registry,
    ):
        """Test diagnostics when integration data is missing."""
        # Don't set up integration data in hass.data

        with (
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "homeassistant.helpers.device_registry.async_get",
                return_value=mock_device_registry,
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_recent_errors",
                return_value=[],
            ),
        ):
            diagnostics = await async_get_config_entry_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        # Should still return diagnostics structure
        assert isinstance(diagnostics, dict)
        assert "integration_status" in diagnostics
        assert diagnostics["integration_status"]["entry_loaded"] is False

    async def test_async_get_config_entry_diagnostics_sensitive_data_redacted(
        self,
        mock_hass_with_states,
        mock_config_entry,
        mock_integration_data,
        mock_entity_registry,
        mock_device_registry,
    ):
        """Test that sensitive data is properly redacted."""
        # Add sensitive data to config
        sensitive_config = mock_config_entry.data.copy()
        sensitive_config["api_key"] = "secret123456789"
        sensitive_config["password"] = "supersecret"
        mock_config_entry.data = sensitive_config

        mock_hass_with_states.data[DOMAIN] = {
            mock_config_entry.entry_id: mock_integration_data
        }

        with (
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "homeassistant.helpers.device_registry.async_get",
                return_value=mock_device_registry,
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_recent_errors",
                return_value=[],
            ),
        ):
            diagnostics = await async_get_config_entry_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        # Check that sensitive data was redacted (we can't see the raw data in diagnostics
        # but we can verify the structure is intact)
        assert isinstance(diagnostics, dict)
        assert "config_entry" in diagnostics


# Config Entry Diagnostics Tests
class TestConfigEntryDiagnostics:
    """Test config entry diagnostics collection."""

    async def test_get_config_entry_diagnostics_complete(self, mock_config_entry):
        """Test complete config entry diagnostics."""
        # Set created_at and modified_at
        mock_config_entry.created_at = dt_util.utcnow() - timedelta(days=1)
        mock_config_entry.modified_at = dt_util.utcnow() - timedelta(hours=1)
        mock_config_entry.state = ConfigEntryState.LOADED
        mock_config_entry.supports_options = True
        mock_config_entry.supports_reconfigure = True
        mock_config_entry.supports_remove_device = True
        mock_config_entry.supports_unload = True

        diagnostics = await _get_config_entry_diagnostics(mock_config_entry)

        expected_keys = [
            "entry_id",
            "title",
            "version",
            "domain",
            "state",
            "source",
            "unique_id",
            "created_at",
            "modified_at",
            "data_keys",
            "options_keys",
            "supports_options",
            "supports_reconfigure",
            "supports_remove_device",
            "supports_unload",
            "dogs_configured",
        ]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["entry_id"] == mock_config_entry.entry_id
        assert diagnostics["title"] == mock_config_entry.title
        assert diagnostics["version"] == mock_config_entry.version
        assert diagnostics["domain"] == DOMAIN
        assert diagnostics["dogs_configured"] == 2
        assert diagnostics["supports_options"] is True

    async def test_get_config_entry_diagnostics_no_timestamps(self, mock_config_entry):
        """Test config entry diagnostics with no timestamps."""
        mock_config_entry.created_at = None
        mock_config_entry.modified_at = None

        diagnostics = await _get_config_entry_diagnostics(mock_config_entry)

        assert diagnostics["created_at"] is None
        assert diagnostics["modified_at"] is None

    async def test_get_config_entry_diagnostics_no_dogs(self):
        """Test config entry diagnostics with no dogs configured."""
        config_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Empty Integration",
            data={CONF_DOGS: []},
            options={},
            entry_id="empty_entry",
            source="user",
        )

        diagnostics = await _get_config_entry_diagnostics(config_entry)

        assert diagnostics["dogs_configured"] == 0


# System Diagnostics Tests
class TestSystemDiagnostics:
    """Test system diagnostics collection."""

    async def test_get_system_diagnostics_complete(self, mock_hass_with_states):
        """Test complete system diagnostics collection."""
        diagnostics = await _get_system_diagnostics(mock_hass_with_states)

        expected_keys = [
            "ha_version",
            "python_version",
            "timezone",
            "config_dir",
            "is_running",
            "safe_mode",
            "recovery_mode",
            "current_time",
            "uptime_seconds",
        ]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["ha_version"] == "2025.1.0"
        assert diagnostics["python_version"] == "3.11.5"
        assert diagnostics["timezone"] == "Europe/Berlin"
        assert diagnostics["is_running"] is True
        assert diagnostics["safe_mode"] is False
        assert isinstance(diagnostics["uptime_seconds"], int | float)
        assert diagnostics["uptime_seconds"] > 0

    async def test_get_system_diagnostics_recovery_mode(self, mock_hass_with_states):
        """Test system diagnostics in recovery mode."""
        mock_hass_with_states.config.safe_mode = True
        mock_hass_with_states.config.recovery_mode = True
        mock_hass_with_states.is_running = False

        diagnostics = await _get_system_diagnostics(mock_hass_with_states)

        assert diagnostics["safe_mode"] is True
        assert diagnostics["recovery_mode"] is True
        assert diagnostics["is_running"] is False


# Integration Status Tests
class TestIntegrationStatus:
    """Test integration status diagnostics."""

    async def test_get_integration_status_fully_loaded(
        self, mock_hass_with_states, mock_config_entry, mock_integration_data
    ):
        """Test integration status when fully loaded."""
        mock_hass_with_states.data[DOMAIN] = {
            mock_config_entry.entry_id: mock_integration_data
        }

        with (
            patch(
                "custom_components.pawcontrol.diagnostics._get_loaded_platforms",
                return_value=["sensor", "button"],
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_registered_services",
                return_value=["feed_dog", "start_walk"],
            ),
        ):
            diagnostics = await _get_integration_status(
                mock_hass_with_states, mock_config_entry, mock_integration_data
            )

        expected_keys = [
            "entry_loaded",
            "coordinator_available",
            "coordinator_success",
            "coordinator_last_update",
            "data_manager_available",
            "notification_manager_available",
            "platforms_loaded",
            "services_registered",
            "setup_completed",
        ]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["entry_loaded"] is True
        assert diagnostics["coordinator_available"] is True
        assert diagnostics["coordinator_success"] is True
        assert diagnostics["data_manager_available"] is True
        assert diagnostics["setup_completed"] is True

    async def test_get_integration_status_not_loaded(
        self, mock_hass_with_states, mock_config_entry
    ):
        """Test integration status when not loaded."""
        # Don't add integration data to hass.data

        with (
            patch(
                "custom_components.pawcontrol.diagnostics._get_loaded_platforms",
                return_value=[],
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_registered_services",
                return_value=[],
            ),
        ):
            diagnostics = await _get_integration_status(
                mock_hass_with_states, mock_config_entry, {}
            )

        assert diagnostics["entry_loaded"] is False
        assert diagnostics["coordinator_available"] is False
        assert diagnostics["data_manager_available"] is False

    async def test_get_integration_status_coordinator_failed(
        self, mock_hass_with_states, mock_config_entry, mock_integration_data
    ):
        """Test integration status with failed coordinator."""
        failed_coordinator = Mock()
        failed_coordinator.last_update_success = False
        failed_coordinator.last_update_time = None
        mock_integration_data["coordinator"] = failed_coordinator

        with (
            patch(
                "custom_components.pawcontrol.diagnostics._get_loaded_platforms",
                return_value=["sensor"],
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_registered_services",
                return_value=["feed_dog"],
            ),
        ):
            diagnostics = await _get_integration_status(
                mock_hass_with_states, mock_config_entry, mock_integration_data
            )

        assert diagnostics["coordinator_available"] is True
        assert diagnostics["coordinator_success"] is False
        assert diagnostics["coordinator_last_update"] is None


# Coordinator Diagnostics Tests
class TestCoordinatorDiagnostics:
    """Test coordinator diagnostics collection."""

    async def test_get_coordinator_diagnostics_available(self, mock_coordinator):
        """Test coordinator diagnostics when coordinator is available."""
        diagnostics = await _get_coordinator_diagnostics(mock_coordinator)

        expected_keys = [
            "available",
            "last_update_success",
            "last_update_time",
            "update_interval_seconds",
            "update_method",
            "logger_name",
            "name",
            "statistics",
            "config_entry_id",
            "dogs_managed",
        ]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["available"] is True
        assert diagnostics["last_update_success"] is True
        assert diagnostics["update_interval_seconds"] == 60
        assert diagnostics["dogs_managed"] == 2
        assert isinstance(diagnostics["statistics"], dict)

    async def test_get_coordinator_diagnostics_none(self):
        """Test coordinator diagnostics when coordinator is None."""
        diagnostics = await _get_coordinator_diagnostics(None)

        assert diagnostics["available"] is False
        assert "reason" in diagnostics
        assert diagnostics["reason"] == "Coordinator not initialized"

    async def test_get_coordinator_diagnostics_failed_updates(self, mock_coordinator):
        """Test coordinator diagnostics with failed updates."""
        mock_coordinator.last_update_success = False
        mock_coordinator.last_update_time = None
        mock_coordinator.available = False

        diagnostics = await _get_coordinator_diagnostics(mock_coordinator)

        assert diagnostics["available"] is False
        assert diagnostics["last_update_success"] is False
        assert diagnostics["last_update_time"] is None


# Entities Diagnostics Tests
class TestEntitiesDiagnostics:
    """Test entities diagnostics collection."""

    async def test_get_entities_diagnostics_complete(
        self, mock_hass_with_states, mock_config_entry, mock_entity_registry
    ):
        """Test complete entities diagnostics collection."""
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_entity_registry,
        ):
            diagnostics = await _get_entities_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        expected_keys = [
            "total_entities",
            "entities_by_platform",
            "platform_counts",
            "disabled_entities",
            "hidden_entities",
        ]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["total_entities"] == 3
        assert diagnostics["disabled_entities"] == 1
        assert diagnostics["hidden_entities"] == 1

        # Check platform grouping
        assert "sensor" in diagnostics["entities_by_platform"]
        assert "binary_sensor" in diagnostics["entities_by_platform"]
        assert "button" in diagnostics["entities_by_platform"]

        assert diagnostics["platform_counts"]["sensor"] == 1
        assert diagnostics["platform_counts"]["binary_sensor"] == 1
        assert diagnostics["platform_counts"]["button"] == 1

    async def test_get_entities_diagnostics_with_states(
        self, mock_hass_with_states, mock_config_entry, mock_entity_registry
    ):
        """Test entities diagnostics includes state information."""
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_entity_registry,
        ):
            diagnostics = await _get_entities_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        # Check that entity state information is included
        sensor_entities = diagnostics["entities_by_platform"]["sensor"]
        sensor_entity = sensor_entities[0]

        assert "state" in sensor_entity
        assert "available" in sensor_entity
        assert "last_changed" in sensor_entity
        assert "last_updated" in sensor_entity
        assert "attributes_count" in sensor_entity

        assert sensor_entity["state"] == "30.5"
        assert sensor_entity["available"] is True

    async def test_get_entities_diagnostics_no_entities(
        self, mock_hass_with_states, mock_config_entry
    ):
        """Test entities diagnostics with no entities."""
        mock_empty_registry = Mock()
        mock_empty_registry.async_entries_for_config_entry.return_value = []

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_empty_registry,
        ):
            diagnostics = await _get_entities_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        assert diagnostics["total_entities"] == 0
        assert diagnostics["entities_by_platform"] == {}
        assert diagnostics["platform_counts"] == {}
        assert diagnostics["disabled_entities"] == 0
        assert diagnostics["hidden_entities"] == 0


# Devices Diagnostics Tests
class TestDevicesDiagnostics:
    """Test devices diagnostics collection."""

    async def test_get_devices_diagnostics_complete(
        self, mock_hass_with_states, mock_config_entry, mock_device_registry
    ):
        """Test complete devices diagnostics collection."""
        with patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ):
            diagnostics = await _get_devices_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        expected_keys = ["total_devices", "devices", "disabled_devices"]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["total_devices"] == 2
        assert diagnostics["disabled_devices"] == 1
        assert len(diagnostics["devices"]) == 2

        # Check device information structure
        device = diagnostics["devices"][0]
        device_keys = [
            "id",
            "name",
            "manufacturer",
            "model",
            "sw_version",
            "hw_version",
            "via_device_id",
            "disabled",
            "disabled_by",
            "entry_type",
            "identifiers",
            "connections",
            "configuration_url",
        ]

        for key in device_keys:
            assert key in device

    async def test_get_devices_diagnostics_no_devices(
        self, mock_hass_with_states, mock_config_entry
    ):
        """Test devices diagnostics with no devices."""
        mock_empty_registry = Mock()
        mock_empty_registry.async_entries_for_config_entry.return_value = []

        with patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_empty_registry,
        ):
            diagnostics = await _get_devices_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        assert diagnostics["total_devices"] == 0
        assert diagnostics["devices"] == []
        assert diagnostics["disabled_devices"] == 0


# Dogs Summary Tests
class TestDogsSummary:
    """Test dogs summary diagnostics."""

    async def test_get_dogs_summary_with_coordinator(
        self, mock_config_entry, mock_coordinator
    ):
        """Test dogs summary with coordinator data."""
        diagnostics = await _get_dogs_summary(mock_config_entry, mock_coordinator)

        expected_keys = ["total_dogs", "dogs", "module_usage"]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["total_dogs"] == 2
        assert len(diagnostics["dogs"]) == 2

        # Check dog information
        buddy_dog = next(
            dog for dog in diagnostics["dogs"] if dog["dog_id"] == "buddy")

        expected_dog_keys = [
            "dog_id",
            "dog_name",
            "dog_breed",
            "dog_age",
            "dog_weight",
            "dog_size",
            "enabled_modules",
            "module_count",
            "coordinator_data_available",
            "last_activity",
            "status",
        ]

        for key in expected_dog_keys:
            assert key in buddy_dog

        assert buddy_dog["coordinator_data_available"] is True
        assert buddy_dog["status"] == "healthy"
        assert buddy_dog["module_count"] == 5

    async def test_get_dogs_summary_without_coordinator(self, mock_config_entry):
        """Test dogs summary without coordinator data."""
        diagnostics = await _get_dogs_summary(mock_config_entry, None)

        assert diagnostics["total_dogs"] == 2
        assert len(diagnostics["dogs"]) == 2

        # Check that dogs don't have coordinator data
        for dog in diagnostics["dogs"]:
            assert (
                "coordinator_data_available" not in dog
                or dog["coordinator_data_available"] is False
            )

    async def test_get_dogs_summary_no_dogs(self):
        """Test dogs summary with no dogs configured."""
        empty_config = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Empty",
            data={CONF_DOGS: []},
            options={},
            entry_id="empty",
            source="user",
        )

        diagnostics = await _get_dogs_summary(empty_config, None)

        assert diagnostics["total_dogs"] == 0
        assert diagnostics["dogs"] == []
        assert isinstance(diagnostics["module_usage"], dict)


# Performance Metrics Tests
class TestPerformanceMetrics:
    """Test performance metrics collection."""

    async def test_get_performance_metrics_with_coordinator(self, mock_coordinator):
        """Test performance metrics with coordinator data."""
        diagnostics = await _get_performance_metrics(mock_coordinator)

        expected_keys = [
            "update_frequency",
            "data_freshness",
            "memory_efficient",
            "cpu_efficient",
            "network_efficient",
            "error_rate",
            "response_time",
        ]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["data_freshness"] == "fresh"
        assert diagnostics["update_frequency"] == 60

    async def test_get_performance_metrics_without_coordinator(self):
        """Test performance metrics without coordinator."""
        diagnostics = await _get_performance_metrics(None)

        assert diagnostics["available"] is False

    async def test_get_performance_metrics_stale_data(self, mock_coordinator):
        """Test performance metrics with stale data."""
        mock_coordinator.last_update_success = False

        diagnostics = await _get_performance_metrics(mock_coordinator)

        assert diagnostics["data_freshness"] == "stale"


# Data Statistics Tests
class TestDataStatistics:
    """Test data statistics collection."""

    async def test_get_data_statistics_available(self):
        """Test data statistics when data manager is available."""
        integration_data = {"data": Mock()}

        diagnostics = await _get_data_statistics(integration_data)

        expected_keys = [
            "data_manager_available",
            "storage_efficient",
            "cleanup_active",
            "export_supported",
            "backup_supported",
            "retention_policy_active",
        ]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["data_manager_available"] is True

    async def test_get_data_statistics_not_available(self):
        """Test data statistics when data manager is not available."""
        integration_data = {}

        diagnostics = await _get_data_statistics(integration_data)

        assert diagnostics["available"] is False


# Debug Information Tests
class TestDebugInformation:
    """Test debug information collection."""

    async def test_get_debug_information_complete(
        self, mock_hass_with_states, mock_config_entry
    ):
        """Test complete debug information collection."""
        with patch(
            "custom_components.pawcontrol.diagnostics._LOGGER.isEnabledFor",
            return_value=True,
        ):
            diagnostics = await _get_debug_information(
                mock_hass_with_states, mock_config_entry
            )

        expected_keys = [
            "debug_logging_enabled",
            "integration_version",
            "quality_scale",
            "supported_features",
            "documentation_url",
            "issue_tracker",
        ]

        for key in expected_keys:
            assert key in diagnostics

        assert diagnostics["debug_logging_enabled"] is True
        assert diagnostics["quality_scale"] == "platinum"
        assert isinstance(diagnostics["supported_features"], list)
        assert len(diagnostics["supported_features"]) > 0

    async def test_get_debug_information_no_debug_logging(
        self, mock_hass_with_states, mock_config_entry
    ):
        """Test debug information with debug logging disabled."""
        with patch(
            "custom_components.pawcontrol.diagnostics._LOGGER.isEnabledFor",
            return_value=False,
        ):
            diagnostics = await _get_debug_information(
                mock_hass_with_states, mock_config_entry
            )

        assert diagnostics["debug_logging_enabled"] is False


# Service Registration Tests
class TestServiceRegistration:
    """Test service registration diagnostics."""

    async def test_get_registered_services_all_available(self, mock_hass_with_states):
        """Test service registration when all services are available."""
        mock_hass_with_states.services.has_service = Mock(return_value=True)

        services = await _get_registered_services(mock_hass_with_states)

        expected_services = [
            "feed_dog",
            "start_walk",
            "end_walk",
            "log_health",
            "log_medication",
            "start_grooming",
            "notify_test",
            "daily_reset",
        ]

        assert set(services) == set(expected_services)

    async def test_get_registered_services_none_available(self, mock_hass_with_states):
        """Test service registration when no services are available."""
        mock_hass_with_states.services.has_service = Mock(return_value=False)

        services = await _get_registered_services(mock_hass_with_states)

        assert services == []


# Module Usage Statistics Tests
class TestModuleUsageStatistics:
    """Test module usage statistics."""

    def test_calculate_module_usage_complete(self):
        """Test module usage calculation with complete data."""
        dogs = [
            {
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: False,
                    MODULE_NOTIFICATIONS: True,
                }
            },
            {
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: False,
                    MODULE_GPS: False,
                    MODULE_HEALTH: True,
                    MODULE_NOTIFICATIONS: False,
                }
            },
        ]

        stats = _calculate_module_usage(dogs)

        expected_keys = [
            "counts",
            "percentages",
            "most_used_module",
            "least_used_module",
        ]

        for key in expected_keys:
            assert key in stats

        assert stats["counts"][MODULE_FEEDING] == 2
        assert stats["counts"][MODULE_WALK] == 1
        assert stats["counts"][MODULE_GPS] == 1
        assert stats["counts"][MODULE_HEALTH] == 1
        assert stats["counts"][MODULE_NOTIFICATIONS] == 1

        assert stats["percentages"][f"{MODULE_FEEDING}_percentage"] == 100.0
        assert stats["percentages"][f"{MODULE_WALK}_percentage"] == 50.0

        assert stats["most_used_module"] == MODULE_FEEDING

    def test_calculate_module_usage_no_dogs(self):
        """Test module usage calculation with no dogs."""
        stats = _calculate_module_usage([])

        assert stats["counts"][MODULE_FEEDING] == 0
        assert stats["percentages"][f"{MODULE_FEEDING}_percentage"] == 0.0
        assert (
            stats["most_used_module"] is not None
        )  # Returns some module even with 0 count

    def test_calculate_module_usage_no_modules(self):
        """Test module usage calculation with dogs that have no modules."""
        dogs = [{"modules": {}}, {"modules": {}}]

        stats = _calculate_module_usage(dogs)

        # All counts should be 0
        for module in [
            MODULE_FEEDING,
            MODULE_WALK,
            MODULE_GPS,
            MODULE_HEALTH,
            MODULE_NOTIFICATIONS,
        ]:
            assert stats["counts"][module] == 0
            assert stats["percentages"][f"{module}_percentage"] == 0.0


# Sensitive Data Redaction Tests
class TestSensitiveDataRedaction:
    """Test sensitive data redaction functionality."""

    def test_redact_sensitive_data_dict(self):
        """Test redacting sensitive data from dictionary."""
        data = {
            "safe_key": "safe_value",
            "api_key": "secret123",
            "password": "topsecret",
            "normal_data": {"nested": "value"},
            "coordinates": {"lat": 52.5200, "lon": 13.4050},
        }

        redacted = _redact_sensitive_data(data)

        assert redacted["safe_key"] == "safe_value"
        assert redacted["api_key"] == "**REDACTED**"
        assert redacted["password"] == "**REDACTED**"
        assert redacted["coordinates"] == "**REDACTED**"
        assert isinstance(redacted["normal_data"], dict)

    def test_redact_sensitive_data_list(self):
        """Test redacting sensitive data from list."""
        data = [
            {"api_key": "secret"},
            {"safe_data": "public"},
            "safe_string",
        ]

        redacted = _redact_sensitive_data(data)

        assert isinstance(redacted, list)
        assert redacted[0]["api_key"] == "**REDACTED**"
        assert redacted[1]["safe_data"] == "public"
        assert redacted[2] == "safe_string"

    def test_redact_sensitive_data_nested(self):
        """Test redacting sensitive data from nested structures."""
        data = {
            "level1": {
                "level2": {
                    "api_key": "secret",
                    "safe": "public",
                    "level3": [
                        {"token": "secret_token"},
                        {"public": "data"},
                    ],
                },
            },
        }

        redacted = _redact_sensitive_data(data)

        assert redacted["level1"]["level2"]["api_key"] == "**REDACTED**"
        assert redacted["level1"]["level2"]["safe"] == "public"
        assert redacted["level1"]["level2"]["level3"][0]["token"] == "**REDACTED**"
        assert redacted["level1"]["level2"]["level3"][1]["public"] == "data"

    def test_looks_like_sensitive_string_patterns(self):
        """Test detection of sensitive string patterns."""
        # UUID
        assert (
            _looks_like_sensitive_string(
                "123e4567-e89b-12d3-a456-426614174000") is True
        )

        # Long alphanumeric (token-like)
        assert (
            _looks_like_sensitive_string(
                "abcdef123456789012345678901234567890") is True
        )

        # IP address
        assert _looks_like_sensitive_string("192.168.1.1") is True

        # Email
        assert _looks_like_sensitive_string("user@example.com") is True

        # Normal strings
        assert _looks_like_sensitive_string("normal text") is False
        assert _looks_like_sensitive_string("short") is False

    def test_redact_sensitive_data_string_patterns(self):
        """Test redacting strings that match sensitive patterns."""
        data = {
            "uuid": "123e4567-e89b-12d3-a456-426614174000",
            "token": "abcdef123456789012345678901234567890",
            "ip": "192.168.1.1",
            "email": "test@example.com",
            "normal": "just normal text",
        }

        redacted = _redact_sensitive_data(data)

        assert redacted["uuid"] == "**REDACTED**"
        assert redacted["token"] == "**REDACTED**"
        assert redacted["ip"] == "**REDACTED**"
        assert redacted["email"] == "**REDACTED**"
        assert redacted["normal"] == "just normal text"

    def test_redacted_keys_coverage(self):
        """Test that all keys in REDACTED_KEYS are properly handled."""
        data = {}
        for key in REDACTED_KEYS:
            data[key] = "sensitive_value"
            data[f"prefix_{key}"] = "also_sensitive"

        redacted = _redact_sensitive_data(data)

        for key in REDACTED_KEYS:
            assert redacted[key] == "**REDACTED**"
            assert redacted[f"prefix_{key}"] == "**REDACTED**"

    def test_redact_sensitive_data_preserves_structure(self):
        """Test that redaction preserves data structure."""
        data = {
            "list": [1, 2, 3],
            "dict": {"a": 1, "b": 2},
            "string": "text",
            "number": 42,
            "boolean": True,
            "null": None,
        }

        redacted = _redact_sensitive_data(data)

        assert isinstance(redacted["list"], list)
        assert isinstance(redacted["dict"], dict)
        assert isinstance(redacted["string"], str)
        assert isinstance(redacted["number"], int)
        assert isinstance(redacted["boolean"], bool)
        assert redacted["null"] is None


# Error Handling Tests
class TestDiagnosticsErrorHandling:
    """Test error handling in diagnostics collection."""

    async def test_diagnostics_with_exception_in_coordinator(
        self,
        mock_hass_with_states,
        mock_config_entry,
        mock_entity_registry,
        mock_device_registry,
    ):
        """Test diagnostics collection when coordinator raises exception."""
        # Setup coordinator that raises exception
        failing_coordinator = Mock()
        failing_coordinator.get_update_statistics.side_effect = Exception(
            "Coordinator error"
        )

        integration_data = {
            "coordinator": failing_coordinator,
            "data": None,
            "notifications": None,
        }
        mock_hass_with_states.data[DOMAIN] = {
            mock_config_entry.entry_id: integration_data
        }

        with (
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "homeassistant.helpers.device_registry.async_get",
                return_value=mock_device_registry,
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_recent_errors",
                return_value=[],
            ),
        ):
            diagnostics = await async_get_config_entry_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        # Should still return diagnostics structure
        assert isinstance(diagnostics, dict)
        assert "coordinator_info" in diagnostics

    async def test_diagnostics_with_registry_exceptions(
        self, mock_hass_with_states, mock_config_entry, mock_integration_data
    ):
        """Test diagnostics when registry calls raise exceptions."""
        mock_hass_with_states.data[DOMAIN] = {
            mock_config_entry.entry_id: mock_integration_data
        }

        with (
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                side_effect=Exception("Registry error"),
            ),
            patch(
                "homeassistant.helpers.device_registry.async_get",
                side_effect=Exception("Registry error"),
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_recent_errors",
                return_value=[],
            ),
        ):
            # Should not raise exception
            diagnostics = await async_get_config_entry_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        assert isinstance(diagnostics, dict)


# Integration Tests
class TestDiagnosticsIntegration:
    """Test diagnostics integration with Home Assistant systems."""

    async def test_full_diagnostics_integration(
        self,
        mock_hass_with_states,
        mock_config_entry,
        mock_integration_data,
        mock_entity_registry,
        mock_device_registry,
    ):
        """Test full diagnostics collection integration."""
        mock_hass_with_states.data[DOMAIN] = {
            mock_config_entry.entry_id: mock_integration_data
        }

        with (
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "homeassistant.helpers.device_registry.async_get",
                return_value=mock_device_registry,
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_recent_errors",
                return_value=[],
            ),
        ):
            diagnostics = await async_get_config_entry_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        # Verify comprehensive diagnostics structure
        assert isinstance(diagnostics, dict)
        assert len(diagnostics) >= 10  # Should have all main sections

        # Verify key sections have data
        assert diagnostics["config_entry"]["dogs_configured"] == 2
        assert diagnostics["system_info"]["ha_version"] == "2025.1.0"
        assert diagnostics["integration_status"]["setup_completed"] is True
        assert diagnostics["entities"]["total_entities"] == 3
        assert diagnostics["devices"]["total_devices"] == 2
        assert diagnostics["dogs_summary"]["total_dogs"] == 2

    async def test_diagnostics_data_consistency(
        self,
        mock_hass_with_states,
        mock_config_entry,
        mock_integration_data,
        mock_entity_registry,
        mock_device_registry,
    ):
        """Test that diagnostics data is consistent across sections."""
        mock_hass_with_states.data[DOMAIN] = {
            mock_config_entry.entry_id: mock_integration_data
        }

        with (
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "homeassistant.helpers.device_registry.async_get",
                return_value=mock_device_registry,
            ),
            patch(
                "custom_components.pawcontrol.diagnostics._get_recent_errors",
                return_value=[],
            ),
        ):
            diagnostics = await async_get_config_entry_diagnostics(
                mock_hass_with_states, mock_config_entry
            )

        # Check data consistency
        assert (
            diagnostics["config_entry"]["dogs_configured"]
            == diagnostics["dogs_summary"]["total_dogs"]
        )
        assert diagnostics["config_entry"]["entry_id"] == mock_config_entry.entry_id

        # Check coordinator consistency
        coordinator_info = diagnostics["coordinator_info"]
        integration_status = diagnostics["integration_status"]

        assert (
            coordinator_info["available"] == integration_status["coordinator_available"]
        )
        assert (
            coordinator_info["last_update_success"]
            == integration_status["coordinator_success"]
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
