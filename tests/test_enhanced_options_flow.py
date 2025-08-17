"""Test enhanced options flow for Paw Control integration.

These tests cover the comprehensive options flow including:
- Dog management (CRUD operations)
- GPS and tracking settings
- Geofence configuration
- Data sources management
- Notification settings
- System settings
- Maintenance and backup functionality
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch
import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pawcontrol.config_flow import OptionsFlowHandler
from custom_components.pawcontrol.const import (
    DOMAIN,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_WEIGHT,
    CONF_DOG_SIZE,
    CONF_DOG_BREED,
    CONF_DOG_AGE,
    CONF_DOG_MODULES,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    SIZE_MEDIUM,
    SIZE_SMALL,
    GPS_MIN_ACCURACY,
    DEFAULT_SAFE_ZONE_RADIUS,
)


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry."""
    return Mock(
        spec=config_entries.ConfigEntry,
        entry_id="test_entry_id",
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_NAME: "Test Paw Control",
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "buddy",
                    CONF_DOG_NAME: "Buddy",
                    CONF_DOG_BREED: "Golden Retriever",
                    CONF_DOG_AGE: 3,
                    CONF_DOG_WEIGHT: 30.0,
                    CONF_DOG_SIZE: SIZE_MEDIUM,
                    CONF_DOG_MODULES: {
                        MODULE_WALK: True,
                        MODULE_FEEDING: True,
                        MODULE_HEALTH: True,
                        MODULE_GPS: True,
                    }
                }
            ]
        },
        options={
            "geofencing_enabled": True,
            "geofence_radius_m": 100,
            "notifications": {
                "enabled": True,
                "quiet_hours_enabled": False,
            },
            "modules": {
                "feeding": True,
                "gps": True,
                "health": True,
            }
        }
    )


@pytest.fixture
def mock_hass():
    """Return a mock Home Assistant instance."""
    hass = Mock(spec=HomeAssistant)
    hass.config.latitude = 52.52
    hass.config.longitude = 13.405
    hass.config.path = Mock(return_value="/config/test_backup.json")
    hass.config_entries = Mock()
    hass.config_entries.async_update_entry = AsyncMock()
    hass.services = Mock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.fixture
def options_flow(mock_hass, mock_config_entry):
    """Return an options flow handler."""
    return OptionsFlowHandler(mock_config_entry)


class TestOptionsFlowInit:
    """Test the initialization and main menu of options flow."""

    async def test_init_shows_menu(self, options_flow):
        """Test that init step shows the comprehensive menu."""
        result = await options_flow.async_step_init()
        
        assert result["type"] == FlowResultType.MENU
        assert result["step_id"] == "init"
        
        menu_options = result["menu_options"]
        expected_options = {
            "dogs", "gps", "geofence", "notifications", 
            "data_sources", "modules", "system", "maintenance"
        }
        assert set(menu_options.keys()) == expected_options

    async def test_init_backward_compatibility(self, options_flow):
        """Test backward compatibility with direct option updates."""
        user_input = {"geofencing_enabled": False}
        
        result = await options_flow.async_step_init(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"] == user_input


class TestDogManagement:
    """Test dog management functionality."""

    async def test_dogs_step_shows_current_dogs(self, options_flow):
        """Test that dogs step shows current dog information."""
        result = await options_flow.async_step_dogs()
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "dogs"
        assert "Currently configured dogs: 1" in result["description_placeholders"]["dogs_info"]
        assert "Buddy (buddy)" in result["description_placeholders"]["dogs_info"]

    async def test_dogs_step_add_action(self, options_flow):
        """Test add dog action from dogs step."""
        user_input = {"action": "add_dog"}
        
        with patch.object(options_flow, 'async_step_add_dog') as mock_add:
            mock_add.return_value = {"type": FlowResultType.FORM}
            result = await options_flow.async_step_dogs(user_input)
            mock_add.assert_called_once()

    async def test_add_dog_success(self, options_flow, mock_hass):
        """Test successfully adding a new dog."""
        options_flow.hass = mock_hass
        
        user_input = {
            CONF_DOG_ID: "max",
            CONF_DOG_NAME: "Max",
            CONF_DOG_BREED: "Labrador",
            CONF_DOG_AGE: 2,
            CONF_DOG_WEIGHT: 25.0,
            CONF_DOG_SIZE: SIZE_MEDIUM,
            f"module_{MODULE_WALK}": True,
            f"module_{MODULE_FEEDING}": True,
            f"module_{MODULE_HEALTH}": False,
            f"module_{MODULE_GPS}": True,
        }
        
        result = await options_flow.async_step_add_dog(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        mock_hass.config_entries.async_update_entry.assert_called_once()

    async def test_add_dog_duplicate_id(self, options_flow):
        """Test adding dog with duplicate ID shows error."""
        user_input = {
            CONF_DOG_ID: "buddy",  # Already exists
            CONF_DOG_NAME: "Another Buddy",
        }
        
        result = await options_flow.async_step_add_dog(user_input)
        
        assert result["type"] == FlowResultType.FORM
        assert result["errors"][CONF_DOG_ID] == "duplicate_dog_id"

    async def test_add_dog_empty_name(self, options_flow):
        """Test adding dog with empty name shows error."""
        user_input = {
            CONF_DOG_ID: "newdog",
            CONF_DOG_NAME: "",  # Empty name
        }
        
        result = await options_flow.async_step_add_dog(user_input)
        
        assert result["type"] == FlowResultType.FORM
        assert result["errors"][CONF_DOG_NAME] == "invalid_dog_name"

    async def test_select_dog_edit(self, options_flow):
        """Test selecting a dog for editing."""
        user_input = {"dog_to_edit": "buddy"}
        
        with patch.object(options_flow, 'async_step_edit_dog') as mock_edit:
            mock_edit.return_value = {"type": FlowResultType.FORM}
            result = await options_flow.async_step_select_dog_edit(user_input)
            assert options_flow._editing_dog_id == "buddy"
            mock_edit.assert_called_once()

    async def test_edit_dog_success(self, options_flow, mock_hass):
        """Test successfully editing a dog."""
        options_flow.hass = mock_hass
        options_flow._editing_dog_id = "buddy"
        
        user_input = {
            CONF_DOG_NAME: "Buddy Updated",
            CONF_DOG_BREED: "Golden Retriever Mix",
            CONF_DOG_AGE: 4,
            CONF_DOG_WEIGHT: 32.0,
            f"module_{MODULE_HEALTH}": False,  # Disable health module
        }
        
        result = await options_flow.async_step_edit_dog(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        mock_hass.config_entries.async_update_entry.assert_called_once()

    async def test_remove_dog(self, options_flow, mock_hass):
        """Test removing a dog."""
        options_flow.hass = mock_hass
        user_input = {"dog_to_remove": "buddy"}
        
        result = await options_flow.async_step_select_dog_remove(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        mock_hass.config_entries.async_update_entry.assert_called_once()


class TestGPSConfiguration:
    """Test GPS and tracking configuration."""

    async def test_gps_step_shows_form(self, options_flow):
        """Test GPS step shows configuration form."""
        result = await options_flow.async_step_gps()
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "gps"
        
        # Check that schema has expected fields
        schema_keys = list(result["data_schema"].schema.keys())
        expected_keys = [
            "gps_enabled", "gps_accuracy_filter", "gps_distance_filter",
            "gps_update_interval", "auto_start_walk", "auto_end_walk",
            "route_recording", "route_history_days"
        ]
        for key in expected_keys:
            assert any(str(k).endswith(key) for k in schema_keys)

    async def test_gps_save_configuration(self, options_flow):
        """Test saving GPS configuration."""
        user_input = {
            "gps_enabled": True,
            "gps_accuracy_filter": 50,
            "gps_distance_filter": 10,
            "auto_start_walk": True,
            "route_recording": True,
            "route_history_days": 60,
        }
        
        result = await options_flow.async_step_gps(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        expected_options = dict(options_flow._options)
        expected_options["gps"] = user_input
        assert result["data"] == expected_options

    async def test_gps_load_existing_config(self, options_flow):
        """Test loading existing GPS configuration."""
        # Set existing GPS config
        options_flow._entry.options = {
            "gps": {
                "enabled": False,
                "accuracy_filter": 200,
                "auto_start_walk": False,
            }
        }
        
        result = await options_flow.async_step_gps()
        
        assert result["type"] == FlowResultType.FORM
        # Verify default values come from existing config
        # This would require inspecting the form schema defaults


class TestGeofenceConfiguration:
    """Test geofence configuration."""

    async def test_geofence_step_shows_form(self, options_flow, mock_hass):
        """Test geofence step shows configuration form."""
        options_flow.hass = mock_hass
        
        result = await options_flow.async_step_geofence()
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "geofence"
        assert "current_lat" in result["description_placeholders"]
        assert "current_lon" in result["description_placeholders"]

    async def test_geofence_save_configuration(self, options_flow):
        """Test saving geofence configuration."""
        user_input = {
            "geofencing_enabled": True,
            "geofence_lat": 52.52,
            "geofence_lon": 13.405,
            "geofence_radius_m": 200,
            "geofence_alerts_enabled": True,
            "multiple_zones": True,
            "zone_detection_mode": "both",
        }
        
        result = await options_flow.async_step_geofence(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        for key, value in user_input.items():
            assert result["data"][key] == value


class TestDataSources:
    """Test data sources configuration."""

    @patch('custom_components.pawcontrol.config_flow.er.async_get')
    async def test_data_sources_step(self, mock_entity_reg, options_flow, mock_hass):
        """Test data sources configuration step."""
        options_flow.hass = mock_hass
        
        # Mock entity registry
        mock_entities = [
            Mock(entity_id="person.john", domain="person"),
            Mock(entity_id="person.jane", domain="person"),
            Mock(entity_id="device_tracker.phone", domain="device_tracker"),
            Mock(entity_id="binary_sensor.front_door", domain="binary_sensor"),
            Mock(entity_id="weather.home", domain="weather"),
            Mock(entity_id="calendar.family", domain="calendar"),
        ]
        mock_registry = Mock()
        mock_registry.entities.values.return_value = mock_entities
        mock_entity_reg.return_value = mock_registry
        
        result = await options_flow.async_step_data_sources()
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "data_sources"

    async def test_data_sources_save_configuration(self, options_flow):
        """Test saving data sources configuration."""
        user_input = {
            "person_entities": ["person.john", "person.jane"],
            "device_trackers": ["device_tracker.phone"],
            "door_sensor": "binary_sensor.front_door",
            "auto_discovery": True,
            "fallback_tracking": False,
        }
        
        result = await options_flow.async_step_data_sources(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["data_sources"] == user_input


class TestNotifications:
    """Test notification configuration."""

    async def test_notifications_comprehensive_config(self, options_flow):
        """Test comprehensive notification configuration."""
        user_input = {
            "notifications_enabled": True,
            "quiet_hours_enabled": True,
            "quiet_start": "22:00",
            "quiet_end": "07:00",
            "reminder_repeat_min": 15,
            "snooze_min": 10,
            "priority_notifications": True,
            "summary_notifications": False,
            "notification_channels": ["mobile", "slack"],
        }
        
        result = await options_flow.async_step_notifications(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["notifications"] == user_input

    async def test_notifications_validation(self, options_flow):
        """Test notification configuration validation."""
        # Test with valid range values
        user_input = {
            "reminder_repeat_min": 5,  # Minimum value
            "snooze_min": 60,          # Maximum value
        }
        
        result = await options_flow.async_step_notifications(user_input)
        assert result["type"] == FlowResultType.CREATE_ENTRY


class TestSystemSettings:
    """Test system settings configuration."""

    async def test_system_comprehensive_config(self, options_flow):
        """Test comprehensive system configuration."""
        user_input = {
            "reset_time": "00:00:00",
            "visitor_mode": True,
            "export_format": "json",
            "export_path": "/custom/path",
            "auto_prune_devices": False,
            "performance_mode": "full",
            "log_level": "debug",
            "data_retention_days": 180,
        }
        
        result = await options_flow.async_step_system(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        for key, value in user_input.items():
            assert result["data"][key] == value

    async def test_system_validation_ranges(self, options_flow):
        """Test system settings validation for ranges."""
        user_input = {
            "data_retention_days": 30,  # Minimum value
        }
        
        result = await options_flow.async_step_system(user_input)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["data_retention_days"] == 30


class TestMaintenance:
    """Test maintenance and backup functionality."""

    async def test_maintenance_step_shows_form(self, options_flow):
        """Test maintenance step shows configuration form."""
        result = await options_flow.async_step_maintenance()
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "maintenance"

    async def test_maintenance_save_settings(self, options_flow):
        """Test saving maintenance settings."""
        user_input = {
            "auto_backup_enabled": True,
            "backup_interval_days": 14,
            "auto_cleanup_enabled": False,
            "cleanup_interval_days": 60,
            "action": "save_settings",
        }
        
        result = await options_flow.async_step_maintenance(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        expected_maintenance = {k: v for k, v in user_input.items() if k != "action"}
        assert result["data"]["maintenance"] == expected_maintenance

    @patch('builtins.open', create=True)
    async def test_maintenance_backup_success(self, mock_open, options_flow, mock_hass):
        """Test successful configuration backup."""
        options_flow.hass = mock_hass
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file
        
        user_input = {"action": "backup_config"}
        
        result = await options_flow.async_step_maintenance(user_input)
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "backup_success"
        mock_open.assert_called_once()

    @patch('builtins.open', side_effect=Exception("File error"))
    async def test_maintenance_backup_failure(self, mock_open, options_flow, mock_hass):
        """Test backup failure handling."""
        options_flow.hass = mock_hass
        
        user_input = {"action": "backup_config"}
        
        result = await options_flow.async_step_maintenance(user_input)
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "backup_error"
        assert result["errors"]["base"] == "backup_failed"

    async def test_maintenance_cleanup_success(self, options_flow, mock_hass):
        """Test successful data cleanup."""
        options_flow.hass = mock_hass
        
        user_input = {"action": "cleanup"}
        
        result = await options_flow.async_step_maintenance(user_input)
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "cleanup_success"
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            "purge_all_storage",
            {"config_entry_id": "test_entry_id"},
        )

    async def test_maintenance_cleanup_failure(self, options_flow, mock_hass):
        """Test cleanup failure handling."""
        options_flow.hass = mock_hass
        mock_hass.services.async_call.side_effect = Exception("Service error")
        
        user_input = {"action": "cleanup"}
        
        result = await options_flow.async_step_maintenance(user_input)
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "cleanup_error"
        assert result["errors"]["base"] == "cleanup_failed"


class TestModulesConfiguration:
    """Test modules configuration."""

    async def test_modules_comprehensive_config(self, options_flow):
        """Test comprehensive modules configuration."""
        user_input = {
            "module_feeding": True,
            "module_gps": False,
            "module_health": True,
            "module_walk": True,
            "module_grooming": False,
            "module_training": True,
            "module_medication": True,
            "module_analytics": False,
            "module_automation": True,
        }
        
        result = await options_flow.async_step_modules(user_input)
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["modules"] == user_input


class TestHelperMethods:
    """Test helper methods of the options flow."""

    def test_create_dog_config(self, options_flow):
        """Test creating a dog configuration."""
        user_input = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            CONF_DOG_BREED: "Test Breed",
            CONF_DOG_AGE: 2,
            CONF_DOG_WEIGHT: 15.0,
            CONF_DOG_SIZE: SIZE_SMALL,
            f"module_{MODULE_WALK}": True,
            f"module_{MODULE_FEEDING}": False,
        }
        
        config = options_flow._create_dog_config(user_input)
        
        assert config[CONF_DOG_ID] == "test_dog"
        assert config[CONF_DOG_NAME] == "Test Dog"
        assert config[CONF_DOG_MODULES][MODULE_WALK] is True
        assert config[CONF_DOG_MODULES][MODULE_FEEDING] is False

    def test_update_dog_config(self, options_flow):
        """Test updating a dog configuration."""
        existing_dog = {
            CONF_DOG_ID: "existing",
            CONF_DOG_NAME: "Old Name",
            CONF_DOG_MODULES: {MODULE_WALK: True, MODULE_FEEDING: True}
        }
        
        user_input = {
            CONF_DOG_NAME: "New Name",
            CONF_DOG_AGE: 5,
            f"module_{MODULE_WALK}": False,
            f"module_{MODULE_FEEDING}": True,
        }
        
        options_flow._update_dog_config(existing_dog, user_input)
        
        assert existing_dog[CONF_DOG_NAME] == "New Name"
        assert existing_dog[CONF_DOG_AGE] == 5
        assert existing_dog[CONF_DOG_MODULES][MODULE_WALK] is False
        assert existing_dog[CONF_DOG_MODULES][MODULE_FEEDING] is True

    @patch('custom_components.pawcontrol.config_flow.er.async_get')
    def test_get_available_entities(self, mock_entity_reg, options_flow, mock_hass):
        """Test getting available entities by domain."""
        options_flow.hass = mock_hass
        
        # Mock entity registry
        mock_entities = [
            Mock(entity_id="person.john", domain="person"),
            Mock(entity_id="device_tracker.phone", domain="device_tracker"),
            Mock(entity_id="binary_sensor.front_door", domain="binary_sensor"),
            Mock(entity_id="weather.home", domain="weather"),
            Mock(entity_id="calendar.family", domain="calendar"),
        ]
        mock_registry = Mock()
        mock_registry.entities.values.return_value = mock_entities
        
        entities = options_flow._get_available_entities(mock_registry)
        
        assert "person.john" in entities["person"]
        assert "device_tracker.phone" in entities["device_tracker"]
        assert "binary_sensor.front_door" in entities["door_sensor"]
        assert "weather.home" in entities["weather"]
        assert "calendar.family" in entities["calendar"]


class TestErrorHandling:
    """Test error handling throughout the options flow."""

    async def test_dog_config_schema_validation(self, options_flow):
        """Test dog configuration schema validation."""
        schema = options_flow._get_dog_config_schema()
        
        # Test valid data
        valid_data = {
            CONF_DOG_ID: "valid_id",
            CONF_DOG_NAME: "Valid Name",
            CONF_DOG_AGE: 5,
            CONF_DOG_WEIGHT: 25.0,
        }
        
        # This should not raise an exception
        validated = schema(valid_data)
        assert validated[CONF_DOG_ID] == "valid_id"

    async def test_edge_case_empty_dogs_list(self, options_flow):
        """Test handling of empty dogs list."""
        # Set empty dogs list
        options_flow._entry.data = {CONF_DOGS: []}
        
        result = await options_flow.async_step_select_dog_edit()
        
        # Should redirect back to dogs management
        # The exact behavior depends on implementation


# Integration test for full flow
class TestFullOptionsFlow:
    """Test complete options flow scenarios."""

    async def test_complete_dog_management_flow(self, options_flow, mock_hass):
        """Test complete dog management flow from start to finish."""
        options_flow.hass = mock_hass
        
        # 1. Start from init
        result = await options_flow.async_step_init()
        assert result["type"] == FlowResultType.MENU
        
        # 2. Navigate to dogs
        result = await options_flow.async_step_dogs()
        assert result["type"] == FlowResultType.FORM
        
        # 3. Choose to add dog
        result = await options_flow.async_step_dogs({"action": "add_dog"})
        # This would typically call async_step_add_dog()
        
        # 4. Add new dog
        new_dog_data = {
            CONF_DOG_ID: "newdog",
            CONF_DOG_NAME: "New Dog",
            CONF_DOG_BREED: "Test Breed",
            CONF_DOG_AGE: 1,
            CONF_DOG_WEIGHT: 20.0,
            CONF_DOG_SIZE: SIZE_MEDIUM,
            f"module_{MODULE_WALK}": True,
            f"module_{MODULE_FEEDING}": True,
        }
        
        result = await options_flow.async_step_add_dog(new_dog_data)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        
        # Verify the config entry was updated
        mock_hass.config_entries.async_update_entry.assert_called()

    async def test_complete_configuration_flow(self, options_flow, mock_hass):
        """Test configuring multiple sections in sequence."""
        options_flow.hass = mock_hass
        
        # Configure GPS settings
        gps_config = {
            "gps_enabled": True,
            "gps_accuracy_filter": 50,
            "auto_start_walk": True,
        }
        result = await options_flow.async_step_gps(gps_config)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        
        # Configure geofence settings
        geofence_config = {
            "geofencing_enabled": True,
            "geofence_radius_m": 150,
            "geofence_alerts_enabled": True,
        }
        result = await options_flow.async_step_geofence(geofence_config)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        
        # Configure notifications
        notification_config = {
            "notifications_enabled": True,
            "quiet_hours_enabled": True,
            "notification_channels": ["mobile", "persistent"],
        }
        result = await options_flow.async_step_notifications(notification_config)
        assert result["type"] == FlowResultType.CREATE_ENTRY


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])