"""Comprehensive edge case tests for PawControl options flow.

Tests all aspects of the options flow including entity profile management,
dog CRUD operations, performance settings, validation, error handling,
and complex navigation scenarios.

Test Areas:
- Entity profile management and preview functionality
- Dog management CRUD operations with validation
- Per-dog module configuration and entity estimation
- Performance settings integration with profiles
- All settings categories (GPS, notifications, feeding, health, etc.)
- Schema validation and error handling
- Navigation flow edge cases and state management
- Configuration persistence and rollback scenarios
- Performance under stress conditions
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from typing import Dict
from typing import List
from unittest.mock import AsyncMock
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pawcontrol.const import CONF_DASHBOARD_MODE
from custom_components.pawcontrol.const import CONF_DOG_AGE
from custom_components.pawcontrol.const import CONF_DOG_BREED
from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOG_SIZE
from custom_components.pawcontrol.const import CONF_DOG_WEIGHT
from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.const import CONF_GPS_ACCURACY_FILTER
from custom_components.pawcontrol.const import CONF_GPS_DISTANCE_FILTER
from custom_components.pawcontrol.const import CONF_GPS_UPDATE_INTERVAL
from custom_components.pawcontrol.const import CONF_MODULES
from custom_components.pawcontrol.const import CONF_NOTIFICATIONS
from custom_components.pawcontrol.const import CONF_QUIET_END
from custom_components.pawcontrol.const import CONF_QUIET_HOURS
from custom_components.pawcontrol.const import CONF_QUIET_START
from custom_components.pawcontrol.const import CONF_REMINDER_REPEAT_MIN
from custom_components.pawcontrol.const import CONF_RESET_TIME
from custom_components.pawcontrol.const import DEFAULT_GPS_ACCURACY_FILTER
from custom_components.pawcontrol.const import DEFAULT_GPS_DISTANCE_FILTER
from custom_components.pawcontrol.const import DEFAULT_GPS_UPDATE_INTERVAL
from custom_components.pawcontrol.const import DEFAULT_REMINDER_REPEAT_MIN
from custom_components.pawcontrol.const import DEFAULT_RESET_TIME
from custom_components.pawcontrol.const import MODULE_FEEDING
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_WALK
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry for testing."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {
        CONF_DOGS: [
            {
                CONF_DOG_ID: "test_dog_1",
                CONF_DOG_NAME: "Test Dog 1",
                CONF_DOG_SIZE: "medium",
                CONF_DOG_WEIGHT: 20.0,
                CONF_DOG_AGE: 3,
                CONF_DOG_BREED: "Test Breed",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: False,
                    MODULE_WALK: True,
                    "notifications": True,
                    "dashboard": True,
                },
            },
            {
                CONF_DOG_ID: "test_dog_2",
                CONF_DOG_NAME: "Test Dog 2",
                CONF_DOG_SIZE: "large",
                CONF_DOG_WEIGHT: 35.0,
                CONF_DOG_AGE: 7,
                CONF_DOG_BREED: "Large Breed",
                "modules": {
                    MODULE_FEEDING: False,
                    MODULE_GPS: False,
                    MODULE_HEALTH: True,
                    MODULE_WALK: False,
                },
            },
        ]
    }
    entry.options = {
        "entity_profile": "standard",
        "performance_mode": "balanced",
        CONF_GPS_UPDATE_INTERVAL: DEFAULT_GPS_UPDATE_INTERVAL,
        CONF_GPS_ACCURACY_FILTER: DEFAULT_GPS_ACCURACY_FILTER,
        CONF_NOTIFICATIONS: {
            CONF_QUIET_HOURS: True,
            CONF_QUIET_START: "22:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_REMINDER_REPEAT_MIN: DEFAULT_REMINDER_REPEAT_MIN,
        },
    }
    return entry


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = AsyncMock()
    return hass


@pytest.fixture
def options_flow(mock_hass, mock_config_entry):
    """Create an options flow for testing."""
    flow = PawControlOptionsFlow(mock_config_entry)
    flow.hass = mock_hass
    return flow


class TestEntityProfileManagement:
    """Test entity profile management and optimization."""

    @pytest.mark.asyncio
    async def test_entity_profiles_step_valid_selection(self, options_flow):
        """Test entity profile selection with valid profiles."""
        for profile_name in ENTITY_PROFILES.keys():
            result = await options_flow.async_step_entity_profiles(
                {"entity_profile": profile_name}
            )

            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert result["data"]["entity_profile"] == profile_name

    @pytest.mark.asyncio
    async def test_entity_profiles_step_preview_request(self, options_flow):
        """Test entity profile preview functionality."""
        result = await options_flow.async_step_entity_profiles(
            {"entity_profile": "advanced", "preview_estimate": True}
        )

        # Should redirect to preview step
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "profile_preview"

    @pytest.mark.asyncio
    async def test_entity_profiles_step_no_input(self, options_flow):
        """Test entity profile step with no input."""
        result = await options_flow.async_step_entity_profiles(None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "entity_profiles"
        assert "data_schema" in result

    @pytest.mark.asyncio
    async def test_entity_profiles_step_error_handling(self, options_flow):
        """Test entity profile step with errors."""
        # Mock error during processing
        with patch.object(
            options_flow, "async_create_entry", side_effect=Exception("Test error")
        ):
            result = await options_flow.async_step_entity_profiles(
                {"entity_profile": "standard"}
            )

            assert result["type"] == FlowResultType.FORM
            assert "errors" in result
            assert result["errors"]["base"] == "profile_update_failed"

    def test_profile_description_placeholders(self, options_flow):
        """Test profile description placeholder generation."""
        placeholders = options_flow._get_profile_description_placeholders()

        required_keys = [
            "current_profile",
            "current_description",
            "dogs_count",
            "estimated_entities",
            "max_entities_per_dog",
            "performance_impact",
        ]

        for key in required_keys:
            assert key in placeholders
            assert isinstance(placeholders[key], str)

    def test_performance_impact_description_all_profiles(self, options_flow):
        """Test performance impact descriptions for all profiles."""
        for profile in ENTITY_PROFILES.keys():
            description = options_flow._get_performance_impact_description(
                profile)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_performance_impact_description_unknown_profile(self, options_flow):
        """Test performance impact description for unknown profile."""
        description = options_flow._get_performance_impact_description(
            "unknown_profile"
        )
        assert description == "Balanced performance"

    @pytest.mark.asyncio
    async def test_profile_preview_apply(self, options_flow):
        """Test applying profile from preview step."""
        result = await options_flow.async_step_profile_preview(
            {"profile": "advanced", "apply_profile": True}
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["entity_profile"] == "advanced"

    @pytest.mark.asyncio
    async def test_profile_preview_go_back(self, options_flow):
        """Test going back from profile preview."""
        result = await options_flow.async_step_profile_preview(
            {"profile": "advanced", "apply_profile": False}
        )

        # Should redirect back to entity profiles step
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "entity_profiles"

    @pytest.mark.asyncio
    async def test_profile_preview_detailed_breakdown(self, options_flow):
        """Test profile preview with detailed entity breakdown."""
        result = await options_flow.async_step_profile_preview({"profile": "advanced"})

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "profile_preview"

        placeholders = result["description_placeholders"]
        assert "entity_breakdown" in placeholders
        assert "total_entities" in placeholders
        assert "entity_difference" in placeholders


class TestPerformanceSettings:
    """Test performance settings integration with entity profiles."""

    @pytest.mark.asyncio
    async def test_performance_settings_valid_update(self, options_flow):
        """Test valid performance settings update."""
        test_settings = {
            "entity_profile": "advanced",
            "performance_mode": "full",
            "batch_size": 25,
            "cache_ttl": 600,
            "selective_refresh": False,
        }

        result = await options_flow.async_step_performance_settings(test_settings)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        for key, value in test_settings.items():
            assert result["data"][key] == value

    @pytest.mark.asyncio
    async def test_performance_settings_no_input(self, options_flow):
        """Test performance settings step with no input."""
        result = await options_flow.async_step_performance_settings(None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "performance_settings"

    @pytest.mark.asyncio
    async def test_performance_settings_error_handling(self, options_flow):
        """Test performance settings with error handling."""
        with patch.object(
            options_flow, "async_create_entry", side_effect=Exception("Test error")
        ):
            result = await options_flow.async_step_performance_settings(
                {"entity_profile": "standard"}
            )

            assert result["type"] == FlowResultType.FORM
            assert "errors" in result
            assert result["errors"]["base"] == "performance_update_failed"

    def test_performance_settings_schema_defaults(self, options_flow):
        """Test performance settings schema with default values."""
        schema = options_flow._get_performance_settings_schema()

        # Check that schema contains expected fields
        schema_fields = list(schema.schema.keys())
        expected_fields = [
            "entity_profile",
            "performance_mode",
            "batch_size",
            "cache_ttl",
            "selective_refresh",
        ]

        for field in expected_fields:
            field_names = [str(f) for f in schema_fields]
            assert any(field in fname for fname in field_names)

    def test_performance_settings_schema_validation(self, options_flow):
        """Test performance settings schema validation."""
        schema = options_flow._get_performance_settings_schema()

        # Test valid data
        valid_data = {
            "entity_profile": "standard",
            "performance_mode": "balanced",
            "batch_size": 15,
            "cache_ttl": 300,
            "selective_refresh": True,
        }

        validated = schema(valid_data)
        assert validated == valid_data

    def test_performance_settings_schema_edge_values(self, options_flow):
        """Test performance settings schema with edge values."""
        schema = options_flow._get_performance_settings_schema()

        # Test minimum values
        min_data = {
            "entity_profile": "basic",
            "performance_mode": "minimal",
            "batch_size": 5,  # Minimum
            "cache_ttl": 60,  # Minimum
            "selective_refresh": False,
        }

        validated = schema(min_data)
        assert validated["batch_size"] == 5
        assert validated["cache_ttl"] == 60

        # Test maximum values
        max_data = {
            "entity_profile": "advanced",
            "performance_mode": "full",
            "batch_size": 50,  # Maximum
            "cache_ttl": 3600,  # Maximum
            "selective_refresh": True,
        }

        validated = schema(max_data)
        assert validated["batch_size"] == 50
        assert validated["cache_ttl"] == 3600


class TestDogManagementOperations:
    """Test dog management CRUD operations."""

    @pytest.mark.asyncio
    async def test_manage_dogs_navigation(self, options_flow):
        """Test dog management navigation menu."""
        # Test each action option
        actions = ["add_dog", "edit_dog",
                   "configure_modules", "remove_dog", "back"]

        for action in actions:
            result = await options_flow.async_step_manage_dogs({"action": action})

            if action == "back":
                # Should show menu (implementation may vary)
                assert result["type"] in [
                    FlowResultType.FORM, FlowResultType.MENU]
            else:
                # Should redirect to appropriate step
                assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_manage_dogs_no_input(self, options_flow):
        """Test manage dogs step with no input."""
        result = await options_flow.async_step_manage_dogs(None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manage_dogs"

        # Should show current dogs in description
        assert "description_placeholders" in result
        assert "current_dogs_count" in result["description_placeholders"]

    @pytest.mark.asyncio
    async def test_add_new_dog_valid_data(self, options_flow):
        """Test adding a new dog with valid data."""
        new_dog_data = {
            CONF_DOG_ID: "new_test_dog",
            CONF_DOG_NAME: "New Test Dog",
            CONF_DOG_BREED: "Test Breed",
            CONF_DOG_AGE: 2,
            CONF_DOG_WEIGHT: 15.0,
            CONF_DOG_SIZE: "small",
        }

        result = await options_flow.async_step_add_new_dog(new_dog_data)

        # Should update config entry and redirect
        assert result["type"] == FlowResultType.FORM
        options_flow.hass.config_entries.async_update_entry.assert_called()

    @pytest.mark.asyncio
    async def test_add_new_dog_no_input(self, options_flow):
        """Test add new dog step with no input."""
        result = await options_flow.async_step_add_new_dog(None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "add_new_dog"

    @pytest.mark.asyncio
    async def test_add_new_dog_error_handling(self, options_flow):
        """Test add new dog with error handling."""
        options_flow.hass.config_entries.async_update_entry.side_effect = Exception(
            "Update failed"
        )

        result = await options_flow.async_step_add_new_dog(
            {
                CONF_DOG_ID: "error_dog",
                CONF_DOG_NAME: "Error Dog",
            }
        )

        assert result["type"] == FlowResultType.FORM
        assert "errors" in result
        assert result["errors"]["base"] == "add_dog_failed"

    def test_add_dog_schema_validation(self, options_flow):
        """Test add dog schema validation."""
        schema = options_flow._get_add_dog_schema()

        # Test valid data
        valid_data = {
            CONF_DOG_ID: "valid_dog_id",
            CONF_DOG_NAME: "Valid Dog Name",
            CONF_DOG_BREED: "Valid Breed",
            CONF_DOG_AGE: 5,
            CONF_DOG_WEIGHT: 25.5,
            CONF_DOG_SIZE: "medium",
        }

        validated = schema(valid_data)
        assert validated[CONF_DOG_ID] == "valid_dog_id"
        assert validated[CONF_DOG_WEIGHT] == 25.5

    def test_add_dog_schema_defaults(self, options_flow):
        """Test add dog schema with default values."""
        schema = options_flow._get_add_dog_schema()

        # Test with minimal required data
        minimal_data = {
            CONF_DOG_ID: "minimal_dog",
            CONF_DOG_NAME: "Minimal Dog",
        }

        validated = schema(minimal_data)
        assert validated[CONF_DOG_AGE] == 3  # Default
        assert validated[CONF_DOG_WEIGHT] == 20.0  # Default
        assert validated[CONF_DOG_SIZE] == "medium"  # Default

    @pytest.mark.asyncio
    async def test_select_dog_to_edit_valid_selection(self, options_flow):
        """Test selecting a valid dog to edit."""
        result = await options_flow.async_step_select_dog_to_edit(
            {"dog_id": "test_dog_1"}
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "edit_dog"
        assert options_flow._current_dog is not None
        assert options_flow._current_dog[CONF_DOG_ID] == "test_dog_1"

    @pytest.mark.asyncio
    async def test_select_dog_to_edit_invalid_selection(self, options_flow):
        """Test selecting an invalid dog to edit."""
        result = await options_flow.async_step_select_dog_to_edit(
            {"dog_id": "nonexistent_dog"}
        )

        # Should redirect back to init
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_select_dog_to_edit_no_dogs(self, options_flow):
        """Test selecting dog to edit when no dogs exist."""
        # Mock empty dogs list
        options_flow._config_entry.data = {CONF_DOGS: []}

        result = await options_flow.async_step_select_dog_to_edit(None)

        # Should redirect back to init
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_edit_dog_valid_update(self, options_flow):
        """Test editing a dog with valid data."""
        # Set current dog
        options_flow._current_dog = options_flow._config_entry.data[CONF_DOGS][0]

        update_data = {
            CONF_DOG_NAME: "Updated Dog Name",
            CONF_DOG_AGE: 4,
            CONF_DOG_WEIGHT: 22.0,
        }

        await options_flow.async_step_edit_dog(update_data)

        options_flow.hass.config_entries.async_update_entry.assert_called()

    @pytest.mark.asyncio
    async def test_edit_dog_no_current_dog(self, options_flow):
        """Test editing dog when no current dog is set."""
        options_flow._current_dog = None

        result = await options_flow.async_step_edit_dog({})

        # Should redirect back to init
        assert result["type"] == FlowResultType.FORM

    def test_edit_dog_schema_current_values(self, options_flow):
        """Test edit dog schema with current values pre-filled."""
        options_flow._current_dog = {
            CONF_DOG_NAME: "Current Name",
            CONF_DOG_BREED: "Current Breed",
            CONF_DOG_AGE: 5,
            CONF_DOG_WEIGHT: 25.0,
            CONF_DOG_SIZE: "large",
        }

        schema = options_flow._get_edit_dog_schema()

        # Schema should be valid and contain fields
        assert schema is not None

    @pytest.mark.asyncio
    async def test_select_dog_to_remove_confirmation(self, options_flow):
        """Test dog removal with confirmation."""
        await options_flow.async_step_select_dog_to_remove(
            {"dog_id": "test_dog_1", "confirm_remove": True}
        )

        # Should update config entry to remove dog
        options_flow.hass.config_entries.async_update_entry.assert_called()

    @pytest.mark.asyncio
    async def test_select_dog_to_remove_no_confirmation(self, options_flow):
        """Test dog removal without confirmation."""
        result = await options_flow.async_step_select_dog_to_remove(
            {"dog_id": "test_dog_1", "confirm_remove": False}
        )

        # Should redirect back without removing
        assert result["type"] == FlowResultType.FORM


class TestModuleConfiguration:
    """Test per-dog module configuration."""

    @pytest.mark.asyncio
    async def test_select_dog_for_modules_valid_selection(self, options_flow):
        """Test selecting a valid dog for module configuration."""
        result = await options_flow.async_step_select_dog_for_modules(
            {"dog_id": "test_dog_1"}
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "configure_dog_modules"
        assert options_flow._current_dog is not None

    @pytest.mark.asyncio
    async def test_select_dog_for_modules_no_dogs(self, options_flow):
        """Test selecting dog for modules when no dogs exist."""
        options_flow._config_entry.data = {CONF_DOGS: []}

        result = await options_flow.async_step_select_dog_for_modules(None)

        # Should redirect to manage dogs
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_configure_dog_modules_valid_update(self, options_flow):
        """Test configuring dog modules with valid data."""
        options_flow._current_dog = options_flow._config_entry.data[CONF_DOGS][0]

        module_config = {
            "module_feeding": True,
            "module_walk": False,
            "module_gps": True,
            "module_health": True,
            "module_notifications": False,
            "module_dashboard": True,
            "module_visitor": False,
            "module_grooming": True,
            "module_medication": False,
            "module_training": True,
        }

        await options_flow.async_step_configure_dog_modules(module_config)

        options_flow.hass.config_entries.async_update_entry.assert_called()

    @pytest.mark.asyncio
    async def test_configure_dog_modules_no_current_dog(self, options_flow):
        """Test configuring modules when no current dog is set."""
        options_flow._current_dog = None

        result = await options_flow.async_step_configure_dog_modules({})

        # Should redirect to manage dogs
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_configure_dog_modules_error_handling(self, options_flow):
        """Test module configuration with error handling."""
        options_flow._current_dog = options_flow._config_entry.data[CONF_DOGS][0]
        options_flow.hass.config_entries.async_update_entry.side_effect = Exception(
            "Update failed"
        )

        result = await options_flow.async_step_configure_dog_modules(
            {"module_feeding": True}
        )

        assert result["type"] == FlowResultType.FORM
        assert "errors" in result
        assert result["errors"]["base"] == "module_config_failed"

    def test_dog_modules_schema_current_values(self, options_flow):
        """Test dog modules schema with current values."""
        options_flow._current_dog = {
            "modules": {
                MODULE_FEEDING: True,
                MODULE_GPS: False,
                MODULE_HEALTH: True,
                "notifications": False,
            }
        }

        schema = options_flow._get_dog_modules_schema()
        assert schema is not None

    def test_dog_modules_schema_no_current_dog(self, options_flow):
        """Test dog modules schema when no current dog is set."""
        options_flow._current_dog = None

        schema = options_flow._get_dog_modules_schema()

        # Should return empty schema
        assert len(schema.schema) == 0

    def test_module_description_placeholders(self, options_flow):
        """Test module description placeholder generation."""
        options_flow._current_dog = {
            CONF_DOG_NAME: "Test Dog",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_GPS: True,
                MODULE_HEALTH: False,
            },
        }

        placeholders = options_flow._get_module_description_placeholders()

        assert "dog_name" in placeholders
        assert "current_profile" in placeholders
        assert "current_entities" in placeholders
        assert "enabled_modules" in placeholders

    def test_module_description_placeholders_no_current_dog(self, options_flow):
        """Test module description placeholders when no current dog is set."""
        options_flow._current_dog = None

        placeholders = options_flow._get_module_description_placeholders()

        # Should return empty dict
        assert placeholders == {}


class TestSettingsCategories:
    """Test various settings categories (GPS, notifications, etc.)."""

    @pytest.mark.asyncio
    async def test_gps_settings_valid_update(self, options_flow):
        """Test GPS settings update with valid data."""
        gps_settings = {
            "gps_enabled": True,
            "gps_update_interval": 30,
            "gps_accuracy_filter": 50,
            "gps_distance_filter": 10,
        }

        result = await options_flow.async_step_gps_settings(gps_settings)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert CONF_GPS_UPDATE_INTERVAL in result["data"]

    @pytest.mark.asyncio
    async def test_gps_settings_error_handling(self, options_flow):
        """Test GPS settings with error handling."""
        with patch.object(
            options_flow, "async_create_entry", side_effect=Exception("Test error")
        ):
            result = await options_flow.async_step_gps_settings({"gps_enabled": True})

            assert result["type"] == FlowResultType.FORM
            assert "errors" in result

    def test_gps_settings_schema_validation(self, options_flow):
        """Test GPS settings schema validation."""
        schema = options_flow._get_gps_settings_schema()

        # Test valid data within bounds
        valid_data = {
            "gps_enabled": True,
            "gps_update_interval": 60,
            "gps_accuracy_filter": 100,
            "gps_distance_filter": 5,
        }

        validated = schema(valid_data)
        assert validated == valid_data

    def test_gps_settings_schema_bounds(self, options_flow):
        """Test GPS settings schema boundary values."""
        schema = options_flow._get_gps_settings_schema()

        # Test minimum values
        min_data = {
            "gps_update_interval": 30,  # Minimum
            "gps_accuracy_filter": 5,  # Minimum
            "gps_distance_filter": 1,  # Minimum
        }

        validated = schema(min_data)
        assert validated["gps_update_interval"] == 30

        # Test maximum values
        max_data = {
            "gps_update_interval": 600,  # Maximum
            "gps_accuracy_filter": 500,  # Maximum
            "gps_distance_filter": 100,  # Maximum
        }

        validated = schema(max_data)
        assert validated["gps_update_interval"] == 600

    @pytest.mark.asyncio
    async def test_notifications_settings_valid_update(self, options_flow):
        """Test notifications settings update."""
        notification_settings = {
            "quiet_hours": True,
            "quiet_start": "23:00:00",
            "quiet_end": "06:00:00",
            "reminder_repeat_min": 30,
            "priority_notifications": False,
            "mobile_notifications": True,
        }

        result = await options_flow.async_step_notifications(notification_settings)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert CONF_NOTIFICATIONS in result["data"]

    def test_notifications_schema_time_validation(self, options_flow):
        """Test notifications schema with time validation."""
        schema = options_flow._get_notifications_schema()

        # Test valid time format
        valid_data = {
            "quiet_start": "22:30:00",
            "quiet_end": "07:15:00",
            "reminder_repeat_min": 15,
        }

        validated = schema(valid_data)
        assert validated["quiet_start"] == "22:30:00"

    @pytest.mark.asyncio
    async def test_feeding_settings_valid_update(self, options_flow):
        """Test feeding settings update."""
        feeding_settings = {
            "meals_per_day": 3,
            "feeding_reminders": True,
            "portion_tracking": False,
            "calorie_tracking": True,
            "auto_schedule": False,
        }

        result = await options_flow.async_step_feeding_settings(feeding_settings)

        assert result["type"] == FlowResultType.CREATE_ENTRY

    def test_feeding_settings_schema_bounds(self, options_flow):
        """Test feeding settings schema boundary values."""
        schema = options_flow._get_feeding_settings_schema()

        # Test valid meals per day range
        valid_data = {
            "meals_per_day": 1,  # Minimum
        }
        validated = schema(valid_data)
        assert validated["meals_per_day"] == 1

        valid_data = {
            "meals_per_day": 6,  # Maximum
        }
        validated = schema(valid_data)
        assert validated["meals_per_day"] == 6

    @pytest.mark.asyncio
    async def test_health_settings_valid_update(self, options_flow):
        """Test health settings update."""
        health_settings = {
            "weight_tracking": True,
            "medication_reminders": False,
            "vet_reminders": True,
            "grooming_reminders": False,
            "health_alerts": True,
        }

        result = await options_flow.async_step_health_settings(health_settings)

        assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_system_settings_valid_update(self, options_flow):
        """Test system settings update."""
        system_settings = {
            "reset_time": "00:00:00",
            "data_retention_days": 180,
            "auto_backup": True,
            "performance_mode": "full",
        }

        result = await options_flow.async_step_system_settings(system_settings)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert CONF_RESET_TIME in result["data"]

    def test_system_settings_schema_data_retention_bounds(self, options_flow):
        """Test system settings data retention boundary values."""
        schema = options_flow._get_system_settings_schema()

        # Test minimum retention
        min_data = {"data_retention_days": 30}
        validated = schema(min_data)
        assert validated["data_retention_days"] == 30

        # Test maximum retention
        max_data = {"data_retention_days": 365}
        validated = schema(max_data)
        assert validated["data_retention_days"] == 365

    @pytest.mark.asyncio
    async def test_dashboard_settings_valid_update(self, options_flow):
        """Test dashboard settings update."""
        dashboard_settings = {
            "dashboard_mode": "cards",
            "show_statistics": False,
            "show_alerts": True,
            "compact_mode": True,
            "show_maps": False,
        }

        result = await options_flow.async_step_dashboard_settings(dashboard_settings)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert CONF_DASHBOARD_MODE in result["data"]

    @pytest.mark.asyncio
    async def test_advanced_settings_valid_update(self, options_flow):
        """Test advanced settings update."""
        advanced_settings = {
            "performance_mode": "minimal",
            "debug_logging": True,
            "data_retention_days": 60,
            "auto_backup": False,
            "experimental_features": True,
        }

        with patch.object(options_flow, "_async_save_options") as mock_save:
            mock_save.return_value = AsyncMock(
                return_value={"type": FlowResultType.CREATE_ENTRY, "data": {}}
            )()

            await options_flow.async_step_advanced_settings(advanced_settings)

            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_export_placeholder(self, options_flow):
        """Test import/export placeholder functionality."""
        result = await options_flow.async_step_import_export({})

        # Should redirect to init (placeholder implementation)
        assert result["type"] == FlowResultType.FORM


class TestNavigationAndStateManagement:
    """Test navigation flow and state management."""

    @pytest.mark.asyncio
    async def test_init_menu_display(self, options_flow):
        """Test initial menu display."""
        result = await options_flow.async_step_init(None)

        assert result["type"] == FlowResultType.MENU
        assert "menu_options" in result

        expected_options = [
            "entity_profiles",
            "manage_dogs",
            "performance_settings",
            "gps_settings",
            "notifications",
            "feeding_settings",
            "health_settings",
            "system_settings",
            "dashboard_settings",
            "advanced_settings",
            "import_export",
        ]

        for option in expected_options:
            assert option in result["menu_options"]

    def test_navigation_stack_initialization(self, options_flow):
        """Test navigation stack initialization."""
        assert hasattr(options_flow, "_navigation_stack")
        assert isinstance(options_flow._navigation_stack, list)

    def test_unsaved_changes_tracking(self, options_flow):
        """Test unsaved changes tracking."""
        assert hasattr(options_flow, "_unsaved_changes")
        assert isinstance(options_flow._unsaved_changes, dict)

    def test_current_dog_state_management(self, options_flow):
        """Test current dog state management."""
        assert hasattr(options_flow, "_current_dog")

        # Initially should be None
        assert options_flow._current_dog is None

    def test_dogs_list_copy_independence(self, options_flow):
        """Test that dogs list is copied independently."""
        # Modify the flow's dogs list
        if options_flow._dogs:
            original_name = options_flow._dogs[0][CONF_DOG_NAME]
            options_flow._dogs[0][CONF_DOG_NAME] = "Modified Name"

            # Original config entry should be unchanged
            assert (
                options_flow._config_entry.data[CONF_DOGS][0][CONF_DOG_NAME]
                == original_name
            )

    @pytest.mark.asyncio
    async def test_save_options_success(self, options_flow):
        """Test successful options saving."""
        options_flow._unsaved_changes = {
            "test_setting": "test_value",
            "another_setting": 123,
        }

        result = await options_flow._async_save_options()

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert options_flow._unsaved_changes == {}  # Should be cleared

    @pytest.mark.asyncio
    async def test_save_options_error_handling(self, options_flow):
        """Test options saving with error handling."""
        options_flow._unsaved_changes = {"test": "value"}

        with patch.object(
            options_flow, "async_create_entry", side_effect=Exception("Save failed")
        ):
            result = await options_flow._async_save_options()

            # Should redirect to init on error
            assert result["type"] == FlowResultType.FORM


class TestSchemaValidationEdgeCases:
    """Test schema validation edge cases across all settings."""

    def test_entity_profiles_schema_all_profiles(self, options_flow):
        """Test entity profiles schema accepts all valid profiles."""
        schema = options_flow._get_entity_profiles_schema()

        for profile_name in ENTITY_PROFILES.keys():
            test_data = {"entity_profile": profile_name}
            validated = schema(test_data)
            assert validated["entity_profile"] == profile_name

    def test_entity_profiles_schema_preview_option(self, options_flow):
        """Test entity profiles schema with preview option."""
        schema = options_flow._get_entity_profiles_schema()

        test_data = {
            "entity_profile": "standard",
            "preview_estimate": True,
        }

        validated = schema(test_data)
        assert validated["preview_estimate"] is True

    def test_performance_settings_schema_all_modes(self, options_flow):
        """Test performance settings schema with all performance modes."""
        schema = options_flow._get_performance_settings_schema()

        modes = ["minimal", "balanced", "full"]
        for mode in modes:
            test_data = {"performance_mode": mode}
            validated = schema(test_data)
            assert validated["performance_mode"] == mode

    def test_all_schemas_handle_none_input(self, options_flow):
        """Test that all schema methods handle None input gracefully."""
        schema_methods = [
            options_flow._get_entity_profiles_schema,
            options_flow._get_performance_settings_schema,
            options_flow._get_add_dog_schema,
            options_flow._get_gps_settings_schema,
            options_flow._get_notifications_schema,
            options_flow._get_feeding_settings_schema,
            options_flow._get_health_settings_schema,
            options_flow._get_system_settings_schema,
            options_flow._get_dashboard_settings_schema,
            options_flow._get_advanced_settings_schema,
        ]

        for schema_method in schema_methods:
            # Should not raise exceptions
            schema = schema_method(None)
            assert schema is not None

    def test_numeric_field_boundaries(self, options_flow):
        """Test numeric field boundaries across schemas."""
        # GPS settings boundaries
        gps_schema = options_flow._get_gps_settings_schema()

        # Test minimum values
        min_gps = {
            "gps_update_interval": 30,
            "gps_accuracy_filter": 5,
            "gps_distance_filter": 1,
        }
        validated = gps_schema(min_gps)
        assert validated["gps_update_interval"] == 30

        # Test maximum values
        max_gps = {
            "gps_update_interval": 600,
            "gps_accuracy_filter": 500,
            "gps_distance_filter": 100,
        }
        validated = gps_schema(max_gps)
        assert validated["gps_update_interval"] == 600

    def test_boolean_field_validation(self, options_flow):
        """Test boolean field validation across schemas."""
        schemas_with_booleans = [
            (options_flow._get_gps_settings_schema(), "gps_enabled"),
            (options_flow._get_notifications_schema(), "quiet_hours"),
            (options_flow._get_feeding_settings_schema(), "feeding_reminders"),
            (options_flow._get_health_settings_schema(), "weight_tracking"),
        ]

        for schema, field_name in schemas_with_booleans:
            # Test both True and False
            for bool_value in [True, False]:
                test_data = {field_name: bool_value}
                validated = schema(test_data)
                assert validated[field_name] == bool_value

    def test_time_field_validation(self, options_flow):
        """Test time field validation."""
        notifications_schema = options_flow._get_notifications_schema()

        # Test valid time formats
        time_values = ["00:00:00", "12:30:45", "23:59:59"]

        for time_value in time_values:
            test_data = {"quiet_start": time_value}
            validated = notifications_schema(test_data)
            assert validated["quiet_start"] == time_value


class TestPerformanceAndStressScenarios:
    """Test performance characteristics and stress scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_dog_operations_performance(self, options_flow):
        """Test performance with multiple dog operations."""
        # Add many dogs to test performance
        many_dogs = []
        for i in range(20):
            many_dogs.append(
                {
                    CONF_DOG_ID: f"stress_dog_{i}",
                    CONF_DOG_NAME: f"Stress Dog {i}",
                    CONF_DOG_SIZE: "medium",
                    CONF_DOG_WEIGHT: 20.0 + i,
                    CONF_DOG_AGE: 3 + (i % 10),
                    "modules": {
                        MODULE_FEEDING: i % 2 == 0,
                        MODULE_GPS: i % 3 == 0,
                        MODULE_HEALTH: i % 4 == 0,
                    },
                }
            )

        options_flow._config_entry.data = {CONF_DOGS: many_dogs}
        options_flow._dogs = many_dogs.copy()

        # Test profile description generation performance
        start_time = time.time()
        placeholders = options_flow._get_profile_description_placeholders()
        generation_time = time.time() - start_time

        # Should complete quickly even with many dogs
        assert generation_time < 1.0
        assert "dogs_count" in placeholders
        assert placeholders["dogs_count"] == "20"

    @pytest.mark.asyncio
    async def test_concurrent_settings_updates(self, options_flow):
        """Test concurrent settings updates."""
        # Create multiple update tasks
        update_tasks = []

        settings_data = [
            ("gps_settings", {"gps_enabled": True}),
            ("notifications", {"quiet_hours": False}),
            ("feeding_settings", {"meals_per_day": 3}),
            ("health_settings", {"weight_tracking": True}),
        ]

        for step_name, data in settings_data:
            if hasattr(options_flow, f"async_step_{step_name}"):
                step_method = getattr(options_flow, f"async_step_{step_name}")
                task = step_method(data)
                update_tasks.append(task)

        # Run all updates concurrently
        results = await asyncio.gather(*update_tasks, return_exceptions=True)

        # All should complete without exceptions
        for result in results:
            assert not isinstance(result, Exception)

    @pytest.mark.asyncio
    async def test_large_configuration_handling(self, options_flow):
        """Test handling of large configuration data."""
        # Create large configuration
        large_config = {
            CONF_DOGS: [],
            "large_data": "x" * 10000,  # Large string
            "complex_structure": {"nested": {"deep": {"data": ["item"] * 1000}}},
        }

        # Add many dogs with complex configurations
        for i in range(50):
            dog = {
                CONF_DOG_ID: f"complex_dog_{i}",
                CONF_DOG_NAME: f"Complex Dog {i}",
                CONF_DOG_SIZE: "medium",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                },
                "complex_config": {
                    "feeding": {
                        "schedule": [f"meal_{j}" for j in range(10)],
                        "portions": [100 + j for j in range(10)],
                    },
                    "health": {
                        "medications": [f"med_{j}" for j in range(5)],
                        "vaccinations": [f"vax_{j}" for j in range(8)],
                    },
                },
            }
            large_config[CONF_DOGS].append(dog)

        options_flow._config_entry.data = large_config
        options_flow._dogs = large_config[CONF_DOGS].copy()

        # Test that operations still work with large config
        result = await options_flow.async_step_manage_dogs(None)
        assert result["type"] == FlowResultType.FORM

    def test_memory_usage_with_deep_copying(self, options_flow):
        """Test memory usage with deep copying of dog configurations."""
        # Create dogs with nested configurations
        complex_dogs = []
        for i in range(10):
            dog = {
                CONF_DOG_ID: f"memory_dog_{i}",
                CONF_DOG_NAME: f"Memory Dog {i}",
                "nested_data": {
                    f"level_{j}": {
                        f"sublevel_{k}": f"data_{i}_{j}_{k}" for k in range(10)
                    }
                    for j in range(10)
                },
            }
            complex_dogs.append(dog)

        options_flow._config_entry.data = {CONF_DOGS: complex_dogs}

        # Create new options flow to test copying
        new_flow = PawControlOptionsFlow(options_flow._config_entry)

        # Verify independent copies
        assert len(new_flow._dogs) == len(complex_dogs)

        # Modify original - should not affect copy
        complex_dogs[0][CONF_DOG_NAME] = "Modified Name"
        assert new_flow._dogs[0][CONF_DOG_NAME] != "Modified Name"

    @pytest.mark.asyncio
    async def test_error_recovery_mechanisms(self, options_flow):
        """Test error recovery mechanisms under various failure conditions."""
        error_scenarios = [
            ("network_error", ConnectionError("Network failed")),
            ("timeout_error", asyncio.TimeoutError()),
            ("value_error", ValueError("Invalid value")),
            ("type_error", TypeError("Wrong type")),
            ("generic_error", Exception("Generic failure")),
        ]

        for error_name, error in error_scenarios:
            # Test error handling in add_new_dog
            options_flow.hass.config_entries.async_update_entry.side_effect = error

            result = await options_flow.async_step_add_new_dog(
                {
                    CONF_DOG_ID: f"error_dog_{error_name}",
                    CONF_DOG_NAME: f"Error Dog {error_name}",
                }
            )

            # Should handle error gracefully
            assert result["type"] == FlowResultType.FORM
            assert "errors" in result

            # Reset mock
            options_flow.hass.config_entries.async_update_entry.side_effect = None
            options_flow.hass.config_entries.async_update_entry.return_value = None


class TestEntityFactoryIntegration:
    """Test integration with EntityFactory for entity estimation."""

    def test_entity_factory_initialization(self, options_flow):
        """Test EntityFactory initialization in options flow."""
        assert hasattr(options_flow, "_entity_factory")
        assert isinstance(options_flow._entity_factory, EntityFactory)

    def test_entity_estimation_with_different_profiles(self, options_flow):
        """Test entity estimation with different profiles."""
        test_modules = {
            MODULE_FEEDING: True,
            MODULE_GPS: True,
            MODULE_HEALTH: False,
            MODULE_WALK: True,
        }

        # Test estimation for each profile
        for profile_name in ENTITY_PROFILES.keys():
            estimate = options_flow._entity_factory.estimate_entity_count(
                profile_name, test_modules
            )

            assert isinstance(estimate, int)
            assert estimate > 0
            assert estimate <= ENTITY_PROFILES[profile_name]["max_entities"]

    def test_entity_estimation_edge_cases(self, options_flow):
        """Test entity estimation edge cases."""
        edge_cases = [
            {},  # No modules
            {MODULE_FEEDING: False, MODULE_GPS: False},  # All disabled
            {
                MODULE_FEEDING: True,
                MODULE_GPS: True,
                MODULE_HEALTH: True,
                MODULE_WALK: True,
            },  # All enabled
        ]

        for modules in edge_cases:
            for profile_name in ENTITY_PROFILES.keys():
                estimate = options_flow._entity_factory.estimate_entity_count(
                    profile_name, modules
                )

                assert isinstance(estimate, int)
                assert estimate >= 0


if __name__ == "__main__":
    pytest.main([__file__])
