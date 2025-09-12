"""Comprehensive tests for Paw Control repairs module.

This test suite covers all aspects of the repairs system including:
- Issue detection for all configuration types
- Repair flow handling for various scenarios
- Edge cases and error conditions
- Integration with Home Assistant's repair system

The repairs module is critical for automatic problem detection and
user-guided repair flows, so comprehensive testing is essential.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_NOTIFICATIONS
from custom_components.pawcontrol.repairs import _check_coordinator_health
from custom_components.pawcontrol.repairs import _check_dog_configuration_issues
from custom_components.pawcontrol.repairs import _check_gps_configuration_issues
from custom_components.pawcontrol.repairs import (
    _check_notification_configuration_issues,
)
from custom_components.pawcontrol.repairs import _check_outdated_configuration
from custom_components.pawcontrol.repairs import _check_performance_issues
from custom_components.pawcontrol.repairs import _check_storage_issues
from custom_components.pawcontrol.repairs import async_check_for_issues
from custom_components.pawcontrol.repairs import async_create_issue
from custom_components.pawcontrol.repairs import async_create_repair_flow
from custom_components.pawcontrol.repairs import ISSUE_COORDINATOR_ERROR
from custom_components.pawcontrol.repairs import ISSUE_DUPLICATE_DOG_IDS
from custom_components.pawcontrol.repairs import ISSUE_INVALID_DOG_DATA
from custom_components.pawcontrol.repairs import ISSUE_INVALID_GPS_CONFIG
from custom_components.pawcontrol.repairs import ISSUE_MISSING_DOG_CONFIG
from custom_components.pawcontrol.repairs import ISSUE_MISSING_NOTIFICATIONS
from custom_components.pawcontrol.repairs import ISSUE_MODULE_CONFLICT
from custom_components.pawcontrol.repairs import ISSUE_OUTDATED_CONFIG
from custom_components.pawcontrol.repairs import ISSUE_PERFORMANCE_WARNING
from custom_components.pawcontrol.repairs import ISSUE_STORAGE_WARNING
from custom_components.pawcontrol.repairs import PawControlRepairsFlow
from custom_components.pawcontrol.repairs import REPAIR_FLOW_CONFIG_MIGRATION
from custom_components.pawcontrol.repairs import REPAIR_FLOW_DOG_CONFIG
from custom_components.pawcontrol.repairs import REPAIR_FLOW_GPS_SETUP
from custom_components.pawcontrol.repairs import REPAIR_FLOW_NOTIFICATION_SETUP
from custom_components.pawcontrol.repairs import REPAIR_FLOW_PERFORMANCE_OPTIMIZATION


# Test fixtures
@pytest.fixture
def mock_issue_registry():
    """Mock issue registry for testing."""
    with (
        patch("homeassistant.helpers.issue_registry.async_create_issue") as mock_create,
        patch("homeassistant.helpers.issue_registry.async_delete_issue") as mock_delete,
        patch("homeassistant.helpers.issue_registry.IssueSeverity") as mock_severity,
    ):
        mock_severity.return_value = "warning"
        yield {"create": mock_create, "delete": mock_delete, "severity": mock_severity}


@pytest.fixture
def minimal_config_entry():
    """Config entry with minimal configuration."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={CONF_DOGS: []},
        options={},
        entry_id="test_entry_minimal",
        source="test",
        unique_id="test_unique_minimal",
    )


@pytest.fixture
def config_entry_duplicate_dogs():
    """Config entry with duplicate dog IDs."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "First Dog",
                    "modules": {"feeding": True},
                },
                {
                    CONF_DOG_ID: "test_dog",  # Duplicate ID
                    CONF_DOG_NAME: "Second Dog",
                    "modules": {"feeding": True},
                },
                {
                    CONF_DOG_ID: "another_dog",
                    CONF_DOG_NAME: "Third Dog",
                    "modules": {"feeding": True},
                },
            ]
        },
        options={},
        entry_id="test_entry_duplicates",
        source="test",
        unique_id="test_unique_duplicates",
    )


@pytest.fixture
def config_entry_invalid_dogs():
    """Config entry with invalid dog data."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "",  # Empty ID
                    CONF_DOG_NAME: "Invalid Dog 1",
                },
                {
                    CONF_DOG_ID: "valid_dog",
                    CONF_DOG_NAME: "",  # Empty name
                },
                {
                    # Missing both ID and name
                    "dog_breed": "Unknown",
                },
            ]
        },
        options={},
        entry_id="test_entry_invalid",
        source="test",
        unique_id="test_unique_invalid",
    )


@pytest.fixture
def config_entry_gps_issues():
    """Config entry with GPS configuration issues."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "gps_dog",
                    CONF_DOG_NAME: "GPS Dog",
                    "modules": {MODULE_GPS: True},
                }
            ]
        },
        options={
            "gps": {
                # Missing gps_source
                "gps_update_interval": 5,  # Too frequent
            }
        },
        entry_id="test_entry_gps",
        source="test",
        unique_id="test_unique_gps",
    )


@pytest.fixture
def config_entry_notification_issues():
    """Config entry with notification issues."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "notify_dog",
                    CONF_DOG_NAME: "Notify Dog",
                    "modules": {MODULE_NOTIFICATIONS: True},
                }
            ]
        },
        options={
            "notifications": {
                "mobile_notifications": True,
            }
        },
        entry_id="test_entry_notify",
        source="test",
        unique_id="test_unique_notify",
    )


@pytest.fixture
def config_entry_performance_issues():
    """Config entry with performance issues."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: f"dog_{i}",
                    CONF_DOG_NAME: f"Dog {i}",
                    "modules": {
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: True,
                    },
                }
                for i in range(12)  # More than 10 dogs
            ]
        },
        options={},
        entry_id="test_entry_performance",
        source="test",
        unique_id="test_unique_performance",
    )


@pytest.fixture
def config_entry_storage_issues():
    """Config entry with storage issues."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={CONF_DOGS: [{"dog_id": "test", "dog_name": "Test"}]},
        options={
            "data_retention_days": 400  # More than recommended 365
        },
        entry_id="test_entry_storage",
        source="test",
        unique_id="test_unique_storage",
    )


@pytest.fixture
def outdated_config_entry():
    """Outdated config entry."""
    return ConfigEntry(
        version=0,  # Outdated version
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={CONF_DOGS: [{"dog_id": "test", "dog_name": "Test"}]},
        options={},
        entry_id="test_entry_outdated",
        source="test",
        unique_id="test_unique_outdated",
    )


# Issue Creation Tests
class TestIssueCreation:
    """Test issue creation functionality."""

    async def test_async_create_issue_basic(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test basic issue creation."""
        await async_create_issue(
            hass,
            mock_config_entry,
            "test_issue_id",
            ISSUE_MISSING_DOG_CONFIG,
            {"test_data": "value"},
            "warning",
        )

        mock_issue_registry["create"].assert_called_once()
        call_args = mock_issue_registry["create"].call_args

        # Verify the call structure
        assert call_args[0][0] is hass  # First positional arg is hass
        assert call_args[0][1] == DOMAIN  # Second is domain
        assert call_args[0][2] == "test_issue_id"  # Third is issue_id

        # Verify keyword arguments
        kwargs = call_args[1]
        assert kwargs["is_fixable"] is True
        assert kwargs["issue_domain"] == DOMAIN
        assert kwargs["translation_key"] == ISSUE_MISSING_DOG_CONFIG

    async def test_async_create_issue_with_data(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test issue creation with additional data."""
        test_data = {"dogs_count": 0, "severity": "error"}

        await async_create_issue(
            hass,
            mock_config_entry,
            "test_issue_with_data",
            ISSUE_MISSING_DOG_CONFIG,
            test_data,
            "error",
        )

        mock_issue_registry["create"].assert_called_once()
        call_args = mock_issue_registry["create"].call_args
        kwargs = call_args[1]

        # Verify translation placeholders contain our data
        assert "dogs_count" in kwargs["translation_placeholders"]
        assert kwargs["translation_placeholders"]["dogs_count"] == 0
        assert (
            kwargs["translation_placeholders"]["config_entry_id"]
            == mock_config_entry.entry_id
        )

    async def test_async_create_issue_severity_levels(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test issue creation with different severity levels."""
        severities = ["error", "warning", "info"]

        for severity in severities:
            await async_create_issue(
                hass,
                mock_config_entry,
                f"test_issue_{severity}",
                ISSUE_PERFORMANCE_WARNING,
                severity=severity,
            )

        assert mock_issue_registry["create"].call_count == len(severities)


# Dog Configuration Issue Tests
class TestDogConfigurationIssues:
    """Test dog configuration issue detection."""

    async def test_check_dog_configuration_no_dogs(
        self, hass: HomeAssistant, minimal_config_entry, mock_issue_registry
    ):
        """Test detection of missing dog configuration."""
        await _check_dog_configuration_issues(hass, minimal_config_entry)

        mock_issue_registry["create"].assert_called_once()
        call_args = mock_issue_registry["create"].call_args
        kwargs = call_args[1]

        assert kwargs["translation_key"] == ISSUE_MISSING_DOG_CONFIG
        assert kwargs["translation_placeholders"]["dogs_count"] == 0

    async def test_check_dog_configuration_duplicate_ids(
        self, hass: HomeAssistant, config_entry_duplicate_dogs, mock_issue_registry
    ):
        """Test detection of duplicate dog IDs."""
        await _check_dog_configuration_issues(hass, config_entry_duplicate_dogs)

        # Should create issue for duplicate IDs
        assert mock_issue_registry["create"].call_count >= 1

        # Find the duplicate IDs call
        calls = mock_issue_registry["create"].call_args_list
        duplicate_call = next(
            call
            for call in calls
            if call[1]["translation_key"] == ISSUE_DUPLICATE_DOG_IDS
        )

        assert (
            "test_dog" in duplicate_call[1]["translation_placeholders"]["duplicate_ids"]
        )

    async def test_check_dog_configuration_invalid_data(
        self, hass: HomeAssistant, config_entry_invalid_dogs, mock_issue_registry
    ):
        """Test detection of invalid dog data."""
        await _check_dog_configuration_issues(hass, config_entry_invalid_dogs)

        # Should create issues for both missing dogs and invalid data
        assert mock_issue_registry["create"].call_count >= 1

        # Check for invalid dog data issue
        calls = mock_issue_registry["create"].call_args_list
        invalid_call = next(
            call
            for call in calls
            if call[1]["translation_key"] == ISSUE_INVALID_DOG_DATA
        )

        assert len(
            invalid_call[1]["translation_placeholders"]["invalid_dogs"]) >= 1

    async def test_check_dog_configuration_valid(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test that no issues are created for valid configuration."""
        await _check_dog_configuration_issues(hass, mock_config_entry)

        # Should not create any issues for valid configuration
        mock_issue_registry["create"].assert_not_called()


# GPS Configuration Issue Tests
class TestGPSConfigurationIssues:
    """Test GPS configuration issue detection."""

    async def test_check_gps_no_gps_enabled(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test GPS check with no GPS-enabled dogs."""
        await _check_gps_configuration_issues(hass, mock_config_entry)

        # Should not create any issues if GPS is not enabled
        mock_issue_registry["create"].assert_not_called()

    async def test_check_gps_missing_source(
        self, hass: HomeAssistant, config_entry_gps_issues, mock_issue_registry
    ):
        """Test detection of missing GPS source configuration."""
        await _check_gps_configuration_issues(hass, config_entry_gps_issues)

        # Should create issue for missing GPS source
        mock_issue_registry["create"].assert_called()
        call_args = mock_issue_registry["create"].call_args
        kwargs = call_args[1]

        assert kwargs["translation_key"] == ISSUE_INVALID_GPS_CONFIG
        assert "missing_gps_source" in kwargs["translation_placeholders"]["issue"]

    async def test_check_gps_update_too_frequent(
        self, hass: HomeAssistant, config_entry_gps_issues, mock_issue_registry
    ):
        """Test detection of too frequent GPS updates."""
        await _check_gps_configuration_issues(hass, config_entry_gps_issues)

        # Should create performance warning for frequent updates
        calls = mock_issue_registry["create"].call_args_list
        performance_call = next(
            call
            for call in calls
            if call[1]["translation_key"] == ISSUE_PERFORMANCE_WARNING
        )

        assert (
            "gps_update_too_frequent"
            in performance_call[1]["translation_placeholders"]["issue"]
        )
        assert performance_call[1]["translation_placeholders"]["current_interval"] == 5

    async def test_check_gps_valid_config(
        self, hass: HomeAssistant, mock_issue_registry
    ):
        """Test GPS check with valid configuration."""
        config_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Test",
            data={
                CONF_DOGS: [
                    {
                        CONF_DOG_ID: "gps_dog",
                        CONF_DOG_NAME: "GPS Dog",
                        "modules": {MODULE_GPS: True},
                    }
                ]
            },
            options={
                "gps": {
                    "gps_source": "device_tracker",
                    "gps_update_interval": 60,  # Valid interval
                }
            },
            entry_id="test_valid_gps",
            source="test",
        )

        await _check_gps_configuration_issues(hass, config_entry)

        # Should not create any issues for valid configuration
        mock_issue_registry["create"].assert_not_called()


# Notification Configuration Issue Tests
class TestNotificationConfigurationIssues:
    """Test notification configuration issue detection."""

    async def test_check_notifications_no_notifications_enabled(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test notification check with no notifications enabled."""
        await _check_notification_configuration_issues(hass, mock_config_entry)

        # Should not create any issues if notifications are not enabled
        mock_issue_registry["create"].assert_not_called()

    async def test_check_notifications_missing_mobile_app(
        self, hass: HomeAssistant, config_entry_notification_issues, mock_issue_registry
    ):
        """Test detection of missing mobile app service."""
        # Mock services to not have mobile_app
        hass.services.has_service = Mock(return_value=False)

        await _check_notification_configuration_issues(
            hass, config_entry_notification_issues
        )

        mock_issue_registry["create"].assert_called_once()
        call_args = mock_issue_registry["create"].call_args
        kwargs = call_args[1]

        assert kwargs["translation_key"] == ISSUE_MISSING_NOTIFICATIONS
        assert kwargs["translation_placeholders"]["missing_service"] == "mobile_app"

    async def test_check_notifications_mobile_app_available(
        self, hass: HomeAssistant, config_entry_notification_issues, mock_issue_registry
    ):
        """Test notification check with mobile app available."""
        # Mock services to have mobile_app
        hass.services.has_service = Mock(return_value=True)

        await _check_notification_configuration_issues(
            hass, config_entry_notification_issues
        )

        # Should not create any issues if mobile app is available
        mock_issue_registry["create"].assert_not_called()


# Configuration Version Tests
class TestOutdatedConfiguration:
    """Test outdated configuration detection."""

    async def test_check_outdated_configuration(
        self, hass: HomeAssistant, outdated_config_entry, mock_issue_registry
    ):
        """Test detection of outdated configuration."""
        await _check_outdated_configuration(hass, outdated_config_entry)

        mock_issue_registry["create"].assert_called_once()
        call_args = mock_issue_registry["create"].call_args
        kwargs = call_args[1]

        assert kwargs["translation_key"] == ISSUE_OUTDATED_CONFIG
        assert kwargs["translation_placeholders"]["current_version"] == 0
        assert kwargs["translation_placeholders"]["required_version"] == 1

    async def test_check_current_configuration(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test check with current configuration version."""
        await _check_outdated_configuration(hass, mock_config_entry)

        # Should not create any issues for current version
        mock_issue_registry["create"].assert_not_called()


# Performance Issue Tests
class TestPerformanceIssues:
    """Test performance issue detection."""

    async def test_check_performance_too_many_dogs(
        self, hass: HomeAssistant, config_entry_performance_issues, mock_issue_registry
    ):
        """Test detection of too many dogs."""
        await _check_performance_issues(hass, config_entry_performance_issues)

        # Should create performance warning for too many dogs
        calls = mock_issue_registry["create"].call_args_list
        performance_call = next(
            call
            for call in calls
            if call[1]["translation_key"] == ISSUE_PERFORMANCE_WARNING
        )

        assert performance_call[1]["translation_placeholders"]["dog_count"] == 12

    async def test_check_performance_module_conflicts(
        self, hass: HomeAssistant, config_entry_performance_issues, mock_issue_registry
    ):
        """Test detection of resource-intensive module combinations."""
        await _check_performance_issues(hass, config_entry_performance_issues)

        # Should create module conflict warning
        calls = mock_issue_registry["create"].call_args_list
        conflict_call = next(
            call
            for call in calls
            if call[1]["translation_key"] == ISSUE_MODULE_CONFLICT
        )

        assert conflict_call[1]["translation_placeholders"]["intensive_dogs"] >= 5

    async def test_check_performance_normal_config(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test performance check with normal configuration."""
        await _check_performance_issues(hass, mock_config_entry)

        # Should not create any issues for normal configuration
        mock_issue_registry["create"].assert_not_called()


# Storage Issue Tests
class TestStorageIssues:
    """Test storage issue detection."""

    async def test_check_storage_high_retention(
        self, hass: HomeAssistant, config_entry_storage_issues, mock_issue_registry
    ):
        """Test detection of high data retention."""
        await _check_storage_issues(hass, config_entry_storage_issues)

        mock_issue_registry["create"].assert_called_once()
        call_args = mock_issue_registry["create"].call_args
        kwargs = call_args[1]

        assert kwargs["translation_key"] == ISSUE_STORAGE_WARNING
        assert kwargs["translation_placeholders"]["current_retention"] == 400

    async def test_check_storage_normal_retention(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test storage check with normal retention."""
        await _check_storage_issues(hass, mock_config_entry)

        # Should not create any issues for normal retention
        mock_issue_registry["create"].assert_not_called()


# Coordinator Health Tests
class TestCoordinatorHealth:
    """Test coordinator health checks."""

    async def test_check_coordinator_missing(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test detection of missing coordinator."""
        # Setup hass.data without coordinator
        hass.data[DOMAIN] = {mock_config_entry.entry_id: {}}

        await _check_coordinator_health(hass, mock_config_entry)

        mock_issue_registry["create"].assert_called_once()
        call_args = mock_issue_registry["create"].call_args
        kwargs = call_args[1]

        assert kwargs["translation_key"] == ISSUE_COORDINATOR_ERROR
        assert (
            "coordinator_not_initialized" in kwargs["translation_placeholders"]["error"]
        )

    async def test_check_coordinator_failed_update(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test detection of coordinator update failure."""
        # Setup coordinator with failed update
        coordinator = Mock()
        coordinator.last_update_success = False
        coordinator.last_update_time = dt_util.utcnow()

        hass.data[DOMAIN] = {mock_config_entry.entry_id: {
            "coordinator": coordinator}}

        await _check_coordinator_health(hass, mock_config_entry)

        mock_issue_registry["create"].assert_called_once()
        call_args = mock_issue_registry["create"].call_args
        kwargs = call_args[1]

        assert kwargs["translation_key"] == ISSUE_COORDINATOR_ERROR
        assert "last_update_failed" in kwargs["translation_placeholders"]["error"]

    async def test_check_coordinator_healthy(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test coordinator health check with healthy coordinator."""
        # Setup healthy coordinator
        coordinator = Mock()
        coordinator.last_update_success = True

        hass.data[DOMAIN] = {mock_config_entry.entry_id: {
            "coordinator": coordinator}}

        await _check_coordinator_health(hass, mock_config_entry)

        # Should not create any issues for healthy coordinator
        mock_issue_registry["create"].assert_not_called()

    async def test_check_coordinator_no_domain_data(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test coordinator health check with no domain data."""
        # Don't setup any domain data
        await _check_coordinator_health(hass, mock_config_entry)

        mock_issue_registry["create"].assert_called_once()
        call_args = mock_issue_registry["create"].call_args
        kwargs = call_args[1]

        assert kwargs["translation_key"] == ISSUE_COORDINATOR_ERROR


# Main Check Function Tests
class TestMainCheckFunction:
    """Test the main async_check_for_issues function."""

    async def test_async_check_for_issues_comprehensive(
        self, hass: HomeAssistant, config_entry_performance_issues, mock_issue_registry
    ):
        """Test comprehensive issue checking."""
        await async_check_for_issues(hass, config_entry_performance_issues)

        # Should create multiple issues for the problematic configuration
        assert mock_issue_registry["create"].call_count >= 2

    async def test_async_check_for_issues_error_handling(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test error handling in issue checking."""
        with patch(
            "custom_components.pawcontrol.repairs._check_dog_configuration_issues",
            side_effect=Exception("Test error"),
        ):
            # Should not raise exception, but log error
            await async_check_for_issues(hass, mock_config_entry)

        # Should still continue and not crash
        assert True  # If we get here, error was handled

    async def test_async_check_for_issues_clean_config(
        self, hass: HomeAssistant, mock_config_entry, mock_issue_registry
    ):
        """Test issue checking with clean configuration."""
        await async_check_for_issues(hass, mock_config_entry)

        # Should not create any issues for clean configuration
        mock_issue_registry["create"].assert_not_called()


# Repair Flow Tests
class TestPawControlRepairsFlow:
    """Test repair flow functionality."""

    @pytest.fixture
    def mock_flow(self, hass: HomeAssistant):
        """Create a mock repair flow."""
        flow = PawControlRepairsFlow()
        flow.hass = hass
        flow.issue_id = "test_issue_id"
        return flow

    @pytest.fixture
    def mock_issue_data(self):
        """Mock issue data."""
        return {
            "config_entry_id": "test_entry_id",
            "issue_type": ISSUE_MISSING_DOG_CONFIG,
            "created_at": dt_util.utcnow().isoformat(),
            "severity": "warning",
            "dogs_count": 0,
        }

    async def test_flow_init_missing_dog_config(
        self, hass: HomeAssistant, mock_flow, mock_issue_data
    ):
        """Test repair flow initialization for missing dog config."""
        # Setup mock issue data
        hass.data[ir.DOMAIN] = {"test_issue_id": Mock(data=mock_issue_data)}

        result = await mock_flow.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "missing_dog_config"

    async def test_flow_missing_dog_config_add_dog(
        self, hass: HomeAssistant, mock_flow, mock_issue_data
    ):
        """Test adding a dog through repair flow."""
        mock_flow._issue_data = mock_issue_data

        # User chooses to add a dog
        user_input = {"action": "add_dog"}
        result = await mock_flow.async_step_missing_dog_config(user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "add_first_dog"

    async def test_flow_add_first_dog_success(
        self, hass: HomeAssistant, mock_flow, mock_config_entry, mock_issue_data
    ):
        """Test successfully adding first dog."""
        mock_flow._issue_data = mock_issue_data

        # Mock config entry
        hass.config_entries.async_get_entry = Mock(
            return_value=mock_config_entry)
        hass.config_entries.async_update_entry = Mock()

        user_input = {
            "dog_id": "new_dog",
            "dog_name": "New Dog",
            "dog_breed": "Test Breed",
            "dog_age": 3,
            "dog_weight": 20.0,
            "dog_size": "medium",
        }

        result = await mock_flow.async_step_add_first_dog(user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "complete_repair"
        hass.config_entries.async_update_entry.assert_called_once()

    async def test_flow_add_first_dog_validation_error(
        self, hass: HomeAssistant, mock_flow, mock_issue_data
    ):
        """Test validation error when adding first dog."""
        mock_flow._issue_data = mock_issue_data

        # Invalid input - empty dog name
        user_input = {
            "dog_id": "test_dog",
            "dog_name": "",  # Empty name
        }

        result = await mock_flow.async_step_add_first_dog(user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "add_first_dog"
        assert "errors" in result
        assert result["errors"]["base"] == "incomplete_data"

    async def test_flow_duplicate_dog_ids_auto_fix(
        self, hass: HomeAssistant, mock_flow, config_entry_duplicate_dogs
    ):
        """Test auto-fixing duplicate dog IDs."""
        mock_flow._issue_data = {
            "config_entry_id": config_entry_duplicate_dogs.entry_id,
            "issue_type": ISSUE_DUPLICATE_DOG_IDS,
            "duplicate_ids": ["test_dog"],
        }

        # Mock config entry
        hass.config_entries.async_get_entry = Mock(
            return_value=config_entry_duplicate_dogs
        )
        hass.config_entries.async_update_entry = Mock()

        user_input = {"action": "auto_fix"}
        result = await mock_flow.async_step_duplicate_dog_ids(user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "complete_repair"
        hass.config_entries.async_update_entry.assert_called_once()

    async def test_flow_gps_configuration(
        self, hass: HomeAssistant, mock_flow, config_entry_gps_issues
    ):
        """Test GPS configuration repair flow."""
        mock_flow._issue_data = {
            "config_entry_id": config_entry_gps_issues.entry_id,
            "issue_type": ISSUE_INVALID_GPS_CONFIG,
        }

        # Mock config entry
        hass.config_entries.async_get_entry = Mock(
            return_value=config_entry_gps_issues)
        hass.config_entries.async_update_entry = Mock()

        # Configure GPS
        user_input = {
            "gps_source": "device_tracker",
            "update_interval": 60,
            "accuracy_filter": 100,
        }

        result = await mock_flow.async_step_configure_gps(user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "complete_repair"
        hass.config_entries.async_update_entry.assert_called_once()

    async def test_flow_complete_repair(
        self, hass: HomeAssistant, mock_flow, mock_issue_registry
    ):
        """Test completing a repair flow."""
        mock_flow._repair_type = ISSUE_MISSING_DOG_CONFIG

        result = await mock_flow.async_step_complete_repair()

        assert result["type"] == "create_entry"
        assert result["title"] == "Repair completed"
        assert result["data"]["repaired_issue"] == ISSUE_MISSING_DOG_CONFIG

        mock_issue_registry["delete"].assert_called_once_with(
            hass, DOMAIN, "test_issue_id"
        )

    async def test_flow_unknown_issue(self, hass: HomeAssistant, mock_flow):
        """Test handling unknown issue types."""
        result = await mock_flow.async_step_unknown_issue()

        assert result["type"] == "abort"
        assert result["reason"] == "unknown_issue_type"

    async def test_flow_helper_methods(
        self, hass: HomeAssistant, mock_flow, config_entry_duplicate_dogs
    ):
        """Test repair flow helper methods."""
        mock_flow._issue_data = {
            "config_entry_id": config_entry_duplicate_dogs.entry_id
        }

        # Mock config entry
        hass.config_entries.async_get_entry = Mock(
            return_value=config_entry_duplicate_dogs
        )
        hass.config_entries.async_update_entry = Mock()

        # Test fixing duplicate IDs
        await mock_flow._fix_duplicate_dog_ids()
        hass.config_entries.async_update_entry.assert_called_once()

        # Test disabling GPS
        await mock_flow._disable_gps_for_all_dogs()
        assert hass.config_entries.async_update_entry.call_count == 2

        # Test disabling mobile notifications
        await mock_flow._disable_mobile_notifications()
        assert hass.config_entries.async_update_entry.call_count == 3

        # Test applying performance optimizations
        await mock_flow._apply_performance_optimizations()
        assert hass.config_entries.async_update_entry.call_count == 4


# Factory Function Tests
class TestRepairFlowFactory:
    """Test repair flow factory function."""

    def test_async_create_repair_flow(self, hass: HomeAssistant):
        """Test repair flow creation."""
        flow = async_create_repair_flow(
            hass, "test_issue_id", {"test": "data"})

        assert isinstance(flow, PawControlRepairsFlow)

    def test_flow_inheritance(self):
        """Test that repair flow inherits from RepairsFlow."""
        flow = PawControlRepairsFlow()

        assert isinstance(flow, RepairsFlow)


# Integration Tests
class TestRepairsIntegration:
    """Test repairs module integration with Home Assistant."""

    async def test_full_repair_cycle(
        self, hass: HomeAssistant, minimal_config_entry, mock_issue_registry
    ):
        """Test a complete repair cycle from detection to resolution."""
        # Step 1: Detect issues
        await async_check_for_issues(hass, minimal_config_entry)

        # Verify issue was created
        mock_issue_registry["create"].assert_called_once()

        # Step 2: Create repair flow
        flow = async_create_repair_flow(
            hass, "test_issue", {
                "config_entry_id": minimal_config_entry.entry_id}
        )

        # Step 3: Complete repair
        flow._repair_type = ISSUE_MISSING_DOG_CONFIG
        result = await flow.async_step_complete_repair()

        assert result["type"] == "create_entry"
        mock_issue_registry["delete"].assert_called_once()

    async def test_multiple_issue_detection(
        self, hass: HomeAssistant, config_entry_performance_issues, mock_issue_registry
    ):
        """Test detection of multiple issues in one check."""
        await async_check_for_issues(hass, config_entry_performance_issues)

        # Should detect multiple issues
        assert mock_issue_registry["create"].call_count >= 2

        # Verify different issue types were created
        calls = mock_issue_registry["create"].call_args_list
        issue_types = [call[1]["translation_key"] for call in calls]

        assert ISSUE_PERFORMANCE_WARNING in issue_types
        assert ISSUE_MODULE_CONFLICT in issue_types

    async def test_error_resilience(self, hass: HomeAssistant, mock_config_entry):
        """Test that repairs system is resilient to errors."""
        # Test with corrupted config entry
        corrupted_entry = Mock()
        corrupted_entry.data = None  # Corrupted data
        corrupted_entry.entry_id = "corrupted"

        # Should not raise exception
        try:
            await async_check_for_issues(hass, corrupted_entry)
        except Exception as e:
            pytest.fail(f"Repairs system should handle errors gracefully: {e}")


# Performance Tests
class TestRepairsPerformance:
    """Test performance characteristics of repairs system."""

    async def test_large_configuration_performance(
        self, hass: HomeAssistant, mock_issue_registry
    ):
        """Test performance with large configurations."""
        # Create config with many dogs
        large_config = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Large Config",
            data={
                CONF_DOGS: [
                    {
                        CONF_DOG_ID: f"dog_{i}",
                        CONF_DOG_NAME: f"Dog {i}",
                        "modules": {"feeding": True, "walk": True},
                    }
                    for i in range(50)  # 50 dogs
                ]
            },
            options={},
            entry_id="large_config",
            source="test",
        )

        # Measure time
        import time

        start_time = time.time()

        await async_check_for_issues(hass, large_config)

        end_time = time.time()
        duration = end_time - start_time

        # Should complete in reasonable time (< 1 second)
        assert duration < 1.0, f"Issue checking took too long: {duration:.2f}s"

    async def test_repair_flow_responsiveness(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test that repair flows are responsive."""
        flow = PawControlRepairsFlow()
        flow.hass = hass
        flow.issue_id = "test_issue"

        # Mock issue data
        hass.data[ir.DOMAIN] = {
            "test_issue": Mock(
                data={
                    "config_entry_id": mock_config_entry.entry_id,
                    "issue_type": ISSUE_MISSING_DOG_CONFIG,
                }
            )
        }

        import time

        start_time = time.time()

        result = await flow.async_step_init()

        end_time = time.time()
        duration = end_time - start_time

        # Flow should respond quickly (< 0.1 seconds)
        assert duration < 0.1, f"Repair flow too slow: {duration:.3f}s"
        assert result["type"] == "form"


# Edge Cases and Error Handling
class TestEdgeCases:
    """Test edge cases and error conditions."""

    async def test_none_config_entry(self, hass: HomeAssistant):
        """Test handling of None config entry."""
        with pytest.raises(AttributeError):
            await async_check_for_issues(hass, None)

    async def test_corrupted_dog_data(self, hass: HomeAssistant, mock_issue_registry):
        """Test handling of corrupted dog data."""
        corrupted_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Corrupted",
            data={
                CONF_DOGS: [
                    {"corrupted": "data"},  # Missing required fields
                    None,  # Null dog
                    "invalid",  # String instead of dict
                ]
            },
            options={},
            entry_id="corrupted",
            source="test",
        )

        # Should handle gracefully and create appropriate issues
        await async_check_for_issues(hass, corrupted_entry)

        # Should detect issues with invalid data
        assert mock_issue_registry["create"].call_count >= 1

    async def test_missing_hass_data(self, hass: HomeAssistant, mock_config_entry):
        """Test handling when hass.data is missing."""
        # Clear hass.data
        if DOMAIN in hass.data:
            del hass.data[DOMAIN]

        # Should handle gracefully
        await _check_coordinator_health(hass, mock_config_entry)

    async def test_repair_flow_invalid_entry_id(self, hass: HomeAssistant, mock_flow):
        """Test repair flow with invalid config entry ID."""
        mock_flow._issue_data = {"config_entry_id": "nonexistent"}

        # Should handle gracefully when config entry doesn't exist
        hass.config_entries.async_get_entry = Mock(return_value=None)

        await mock_flow._fix_duplicate_dog_ids()
        # Should not crash, just do nothing


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
