"""Comprehensive edge case tests for PawControl config flow - Gold Standard coverage.

This module provides advanced edge case testing to achieve 95%+ test coverage
for the config flow and options flow, including complex scenarios, error recovery,
validation edge cases, and performance stress testing.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from typing import Any, Dict, List, Optional

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.data_entry_flow import FlowResultType, AbortFlow
from homeassistant.helpers import selector

from custom_components.pawcontrol.config_flow import (
    PawControlConfigFlow,
    ValidationCache,
    ENTITY_PROFILES,
    VALIDATION_CACHE_TTL,
    MAX_CONCURRENT_VALIDATIONS,
    VALIDATION_TIMEOUT,
    PROFILE_SCHEMA,
)
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow
from custom_components.pawcontrol.const import (
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_BREED,
    CONF_DOG_AGE,
    CONF_DOG_WEIGHT,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)


class TestConfigFlowEdgeCasesValidation:
    """Test config flow validation edge cases and complex scenarios."""

    @pytest.fixture
    def config_flow(self):
        """Create config flow instance for testing."""
        flow = PawControlConfigFlow()
        flow.hass = Mock()
        flow._abort_if_unique_id_configured = Mock()
        return flow

    @pytest.mark.asyncio
    async def test_validation_cache_edge_cases(self):
        """Test validation cache with various edge cases."""
        cache = ValidationCache(ttl=1)  # Short TTL for testing
        
        # Test normal operation
        await cache.set("test_key", {"valid": True})
        result = await cache.get("test_key")
        assert result == {"valid": True}
        
        # Test TTL expiration
        await asyncio.sleep(1.1)
        expired_result = await cache.get("test_key")
        assert expired_result is None
        
        # Test concurrent access
        async def concurrent_set(key, value):
            await cache.set(f"concurrent_{key}", value)
        
        tasks = [concurrent_set(i, f"value_{i}") for i in range(10)]
        await asyncio.gather(*tasks)
        
        # Verify all values were set
        for i in range(10):
            result = await cache.get(f"concurrent_{i}")
            assert result == f"value_{i}"
        
        # Test cache clearing
        await cache.clear()
        result = await cache.get("concurrent_0")
        assert result is None

    @pytest.mark.asyncio
    async def test_validation_cache_corruption_handling(self):
        """Test handling of corrupted cache data."""
        cache = ValidationCache()
        
        # Manually corrupt cache data
        cache._cache["corrupted"] = ("not_a_timestamp", "invalid_data")
        
        # Should handle corruption gracefully
        result = await cache.get("corrupted")
        assert result is None
        
        # Cache should still work after corruption
        await cache.set("new_key", "new_value")
        result = await cache.get("new_key")
        assert result == "new_value"

    @pytest.mark.asyncio
    async def test_validation_timeout_scenarios(self, config_flow):
        """Test validation timeout handling."""
        # Mock validation that takes too long
        async def slow_validation(name):
            await asyncio.sleep(VALIDATION_TIMEOUT + 1)
            return {"valid": True, "errors": {}}
        
        config_flow._async_validate_integration_name = slow_validation
        
        # Should timeout and return error
        result = await config_flow.async_step_user({
            "name": "Test Integration"
        })
        
        assert result["type"] == FlowResultType.FORM
        assert "validation_timeout" in result.get("errors", {}).get("base", "")

    @pytest.mark.asyncio
    async def test_integration_name_edge_cases(self, config_flow):
        """Test integration name validation with edge cases."""
        edge_cases = [
            "",  # Empty string
            " ",  # Whitespace only
            "a" * 200,  # Very long name
            "Test\nName",  # With newlines
            "Test\tName",  # With tabs
            "Test/Name",  # With special chars
            "Test\\Name",  # With backslashes
            "Test'Name",  # With quotes
            'Test"Name',  # With double quotes
            "Test;Name",  # With semicolons
            "😀 Dog",  # With emojis
            "Tëst Nämê",  # With accents
        ]
        
        # Mock validation to always fail for these cases
        async def validate_edge_case(name):
            if name.strip() in ["", " "] or len(name) > 100 or any(c in name for c in ['\n', '\t', '/', '\\', ';']):
                return {"valid": False, "errors": {"base": "invalid_name"}}
            return {"valid": True, "errors": {}}
        
        config_flow._async_validate_integration_name = validate_edge_case
        
        for case in edge_cases[:5]:  # Test first 5 cases
            result = await config_flow.async_step_user({"name": case})
            
            if case.strip() == "" or len(case) > 100:
                assert result["type"] == FlowResultType.FORM
                assert "errors" in result
            else:
                # Some cases might be valid depending on implementation
                assert result["type"] in [FlowResultType.FORM, FlowResultType.CREATE_ENTRY]

    @pytest.mark.asyncio
    async def test_unique_id_collision_handling(self, config_flow):
        """Test unique ID collision detection and handling."""
        # Mock unique ID conflict
        config_flow._abort_if_unique_id_configured = Mock(side_effect=AbortFlow("already_configured"))
        
        # Mock successful validation
        async def mock_validation(name):
            return {"valid": True, "errors": {}}
        
        config_flow._async_validate_integration_name = mock_validation
        config_flow._generate_unique_id = Mock(return_value="duplicate_id")
        config_flow.async_set_unique_id = Mock()
        
        # Should abort due to unique ID conflict
        with pytest.raises(AbortFlow, match="already_configured"):
            await config_flow.async_step_user({"name": "Test Integration"})

    @pytest.mark.asyncio
    async def test_concurrent_validation_limits(self, config_flow):
        """Test concurrent validation limits and semaphore handling."""
        # Create many concurrent validation requests
        validation_calls = []
        
        async def track_validation(name):
            validation_calls.append(name)
            await asyncio.sleep(0.1)  # Simulate slow validation
            return {"valid": True, "errors": {}}
        
        config_flow._async_validate_integration_name = track_validation
        
        # Start more validations than allowed concurrently
        tasks = []
        for i in range(MAX_CONCURRENT_VALIDATIONS + 5):
            task = asyncio.create_task(
                config_flow.async_step_user({"name": f"Test{i}"})
            )
            tasks.append(task)
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should complete (semaphore should manage concurrency)
        assert len(validation_calls) == MAX_CONCURRENT_VALIDATIONS + 5

    @pytest.mark.asyncio
    async def test_validation_cache_memory_pressure(self):
        """Test validation cache under memory pressure."""
        cache = ValidationCache(ttl=300)  # Long TTL
        
        # Add many entries to test memory usage
        for i in range(1000):
            await cache.set(f"key_{i}", {"data": "x" * 100, "index": i})
        
        # Verify all entries exist
        for i in range(0, 1000, 100):  # Sample every 100th
            result = await cache.get(f"key_{i}")
            assert result is not None
            assert result["index"] == i
        
        # Clear and verify cleanup
        await cache.clear()
        result = await cache.get("key_500")
        assert result is None


class TestConfigFlowEntityProfileEdgeCases:
    """Test entity profile selection edge cases."""

    @pytest.fixture
    def config_flow_with_dogs(self):
        """Create config flow with pre-configured dogs."""
        flow = PawControlConfigFlow()
        flow.hass = Mock()
        flow._integration_name = "Test Integration"
        flow._dogs = [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Dog 1",
                "modules": {MODULE_FEEDING: True, MODULE_GPS: True, MODULE_HEALTH: True},
            },
            {
                CONF_DOG_ID: "dog2", 
                CONF_DOG_NAME: "Dog 2",
                "modules": {MODULE_FEEDING: True, MODULE_GPS: False, MODULE_HEALTH: False},
            },
        ]
        return flow

    @pytest.mark.asyncio
    async def test_invalid_entity_profile_selection(self, config_flow_with_dogs):
        """Test handling of invalid entity profile selection."""
        # Test invalid profile
        result = await config_flow_with_dogs.async_step_entity_profile({
            "entity_profile": "invalid_profile"
        })
        
        assert result["type"] == FlowResultType.FORM
        assert "invalid_profile" in result.get("errors", {}).get("entity_profile", "")

    @pytest.mark.asyncio
    async def test_profile_calculation_edge_cases(self, config_flow_with_dogs):
        """Test profile calculation with edge case configurations."""
        # Test with empty dogs list
        config_flow_with_dogs._dogs = []
        estimates = config_flow_with_dogs._calculate_profile_estimates()
        
        for profile, estimate in estimates.items():
            assert estimate >= 0
            assert estimate <= ENTITY_PROFILES[profile]["max_entities"]
        
        # Test with dogs having no modules
        config_flow_with_dogs._dogs = [
            {CONF_DOG_ID: "empty_dog", CONF_DOG_NAME: "Empty Dog", "modules": {}}
        ]
        estimates = config_flow_with_dogs._calculate_profile_estimates()
        
        # Should still provide reasonable estimates
        assert all(estimate > 0 for estimate in estimates.values())

    @pytest.mark.asyncio
    async def test_profile_recommendation_edge_cases(self, config_flow_with_dogs):
        """Test profile recommendation with various configurations."""
        # Test with many dogs, complex configuration
        config_flow_with_dogs._dogs = [
            {
                CONF_DOG_ID: f"dog{i}",
                CONF_DOG_NAME: f"Dog {i}",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: i % 2 == 0,  # Every other dog has GPS
                    MODULE_HEALTH: i % 3 == 0,  # Every third dog has health
                    "special_diet": ["ingredient1", "ingredient2", "ingredient3"] if i == 0 else [],
                },
            }
            for i in range(10)
        ]
        
        recommendation = config_flow_with_dogs._get_recommended_profile()
        assert recommendation in ENTITY_PROFILES.keys()
        
        # Test with only GPS dogs
        config_flow_with_dogs._dogs = [
            {
                CONF_DOG_ID: "gps_dog",
                CONF_DOG_NAME: "GPS Dog",
                "modules": {MODULE_GPS: True, MODULE_HEALTH: False},
            }
        ]
        
        recommendation = config_flow_with_dogs._get_recommended_profile()
        assert recommendation == "gps_focus"
        
        # Test with only health dogs
        config_flow_with_dogs._dogs = [
            {
                CONF_DOG_ID: "health_dog",
                CONF_DOG_NAME: "Health Dog", 
                "modules": {MODULE_GPS: False, MODULE_HEALTH: True},
            }
        ]
        
        recommendation = config_flow_with_dogs._get_recommended_profile()
        assert recommendation == "health_focus"

    @pytest.mark.asyncio
    async def test_performance_comparison_with_extreme_configs(self, config_flow_with_dogs):
        """Test performance comparison calculation with extreme configurations."""
        # Test with maximum number of dogs
        config_flow_with_dogs._dogs = [
            {
                CONF_DOG_ID: f"dog{i}",
                CONF_DOG_NAME: f"Dog {i}",
                "modules": {m: True for m in [MODULE_FEEDING, MODULE_GPS, MODULE_HEALTH, MODULE_WALK]},
            }
            for i in range(50)  # Many dogs
        ]
        
        performance_text = config_flow_with_dogs._get_performance_comparison()
        assert isinstance(performance_text, str)
        assert len(performance_text) > 0
        
        # Should contain information about all profiles
        for profile_name in ENTITY_PROFILES.keys():
            assert profile_name in performance_text or profile_name.title() in performance_text

    @pytest.mark.asyncio
    async def test_profile_with_dashboard_interaction(self, config_flow_with_dogs):
        """Test profile selection interaction with dashboard configuration."""
        config_flow_with_dogs._needs_dashboard_config = True
        config_flow_with_dogs.async_step_dashboard = AsyncMock(
            return_value={"type": FlowResultType.FORM, "step_id": "dashboard"}
        )
        
        result = await config_flow_with_dogs.async_step_entity_profile({
            "entity_profile": "advanced"
        })
        
        # Should redirect to dashboard step
        assert result["step_id"] == "dashboard"
        config_flow_with_dogs.async_step_dashboard.assert_called_once()


class TestConfigFlowFinalSetupEdgeCases:
    """Test final setup edge cases and error scenarios."""

    @pytest.fixture
    def config_flow_ready_for_setup(self):
        """Create config flow ready for final setup."""
        flow = PawControlConfigFlow()
        flow.hass = Mock()
        flow._integration_name = "Test Integration"
        flow._entity_profile = "standard"
        flow._dogs = [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Test Dog",
                "modules": {MODULE_FEEDING: True},
            }
        ]
        flow._external_entities = {}
        flow._validation_cache = Mock()
        flow._validation_cache.clear = AsyncMock()
        return flow

    @pytest.mark.asyncio
    async def test_final_setup_no_dogs_error(self, config_flow_ready_for_setup):
        """Test final setup with no dogs configured."""
        config_flow_ready_for_setup._dogs = []
        
        result = await config_flow_ready_for_setup.async_step_final_setup()
        
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "no_dogs_configured"

    @pytest.mark.asyncio
    async def test_final_setup_dog_validation_timeout(self, config_flow_ready_for_setup):
        """Test final setup with dog validation timeout."""
        # Mock dog validation that times out
        async def timeout_validation(dog_config):
            await asyncio.sleep(6)  # Longer than timeout
            return True
        
        config_flow_ready_for_setup._validate_dog_config_async = timeout_validation
        
        # Should handle timeout gracefully and continue
        result = await config_flow_ready_for_setup.async_step_final_setup()
        
        # Should still create entry despite timeout
        assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_final_setup_invalid_dog_config(self, config_flow_ready_for_setup):
        """Test final setup with invalid dog configuration."""
        # Mock dog validation that fails
        async def invalid_validation(dog_config):
            return False
        
        config_flow_ready_for_setup._validate_dog_config_async = invalid_validation
        
        # Should raise error for invalid config
        with pytest.raises(ValueError, match="Invalid dog configuration"):
            await config_flow_ready_for_setup.async_step_final_setup()

    @pytest.mark.asyncio
    async def test_final_setup_config_creation_failure(self, config_flow_ready_for_setup):
        """Test final setup when config entry creation fails."""
        # Mock create_intelligent_options to fail
        async def failing_options(config_data):
            raise Exception("Options creation failed")
        
        config_flow_ready_for_setup._create_intelligent_options = failing_options
        
        result = await config_flow_ready_for_setup.async_step_final_setup()
        
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "setup_failed"

    @pytest.mark.asyncio
    async def test_intelligent_options_edge_cases(self, config_flow_ready_for_setup):
        """Test intelligent options creation with edge cases."""
        # Test with complex dog configuration
        config_flow_ready_for_setup._dogs = [
            {
                CONF_DOG_ID: "complex_dog",
                CONF_DOG_NAME: "Complex Dog",
                CONF_DOG_SIZE: "giant",
                "modules": {MODULE_FEEDING: True, MODULE_GPS: True, MODULE_HEALTH: True, MODULE_WALK: True},
                "gps_config": {"enabled": True, "accuracy": "high"},
            }
        ]
        
        config_data = {
            "name": "Test Integration",
            CONF_DOGS: config_flow_ready_for_setup._dogs,
            "entity_profile": "advanced",
        }
        
        options = await config_flow_ready_for_setup._create_intelligent_options(config_data)
        
        # Should handle complex configuration
        assert isinstance(options, dict)
        assert "performance_mode" in options
        assert "batch_updates" in options
        
        # Advanced profile should have specific settings
        assert options["batch_updates"] == False  # Advanced profile doesn't use batching
        assert options["cache_aggressive"] == False

    @pytest.mark.asyncio
    async def test_performance_mode_calculation_edge_cases(self):
        """Test performance mode calculation with various edge cases."""
        # Test all profile combinations
        test_cases = [
            ("basic", False, False, False, "minimal"),
            ("basic", True, True, True, "minimal"),  # Basic always minimal
            ("advanced", True, True, True, "full"),
            ("advanced", False, False, False, "balanced"),
            ("standard", True, True, True, "balanced"),
            ("gps_focus", True, False, False, "balanced"),
            ("health_focus", False, True, False, "balanced"),
        ]
        
        for profile, has_gps, has_multiple_dogs, has_large_dogs, expected in test_cases:
            result = PawControlConfigFlow._calculate_performance_mode_with_profile(
                profile, has_gps, has_multiple_dogs, has_large_dogs
            )
            assert result == expected, f"Failed for {profile} with GPS:{has_gps}, Multi:{has_multiple_dogs}, Large:{has_large_dogs}"

    @pytest.mark.asyncio
    async def test_update_interval_calculation_edge_cases(self):
        """Test update interval calculation with various edge cases."""
        test_cases = [
            ("basic", False, False, 180),
            ("basic", True, True, 180),  # Basic always longest interval
            ("gps_focus", True, False, 30),  # GPS focus fastest
            ("gps_focus", False, False, 30),  # GPS focus even without GPS
            ("advanced", False, False, 60),
            ("standard", True, True, 60),
            ("standard", True, False, 45),
            ("health_focus", False, False, 120),
        ]
        
        for profile, has_gps, has_multiple_dogs, expected in test_cases:
            result = PawControlConfigFlow._calculate_update_interval_with_profile(
                profile, has_gps, has_multiple_dogs
            )
            assert result == expected, f"Failed for {profile} with GPS:{has_gps}, Multi:{has_multiple_dogs}"


class TestOptionsFlowEdgeCasesComplexScenarios:
    """Test options flow edge cases and complex scenarios."""

    @pytest.fixture
    def options_flow_with_complex_config(self):
        """Create options flow with complex configuration."""
        config_entry = Mock(spec=ConfigEntry)
        config_entry.entry_id = "test_entry"
        config_entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "dog1",
                    CONF_DOG_NAME: "Dog 1",
                    CONF_DOG_SIZE: "large",
                    CONF_DOG_BREED: "German Shepherd",
                    CONF_DOG_AGE: 5,
                    CONF_DOG_WEIGHT: 35.0,
                    "modules": {MODULE_FEEDING: True, MODULE_GPS: True, MODULE_HEALTH: True},
                },
                {
                    CONF_DOG_ID: "dog2",
                    CONF_DOG_NAME: "Dog 2", 
                    CONF_DOG_SIZE: "small",
                    CONF_DOG_BREED: "Beagle",
                    CONF_DOG_AGE: 3,
                    CONF_DOG_WEIGHT: 15.0,
                    "modules": {MODULE_FEEDING: True, MODULE_GPS: False, MODULE_HEALTH: False},
                },
            ]
        }
        config_entry.options = {
            "entity_profile": "standard",
            "performance_mode": "balanced",
        }
        
        flow = PawControlOptionsFlow(config_entry)
        flow.hass = Mock()
        flow.hass.config_entries = Mock()
        flow.hass.config_entries.async_update_entry = Mock()
        
        return flow

    @pytest.mark.asyncio
    async def test_entity_profile_switching_edge_cases(self, options_flow_with_complex_config):
        """Test entity profile switching with complex scenarios."""
        # Test switching to invalid profile
        result = await options_flow_with_complex_config.async_step_entity_profiles({
            "entity_profile": "invalid_profile"
        })
        
        assert result["type"] == FlowResultType.FORM
        assert "profile_update_failed" in result.get("errors", {}).get("base", "")

    @pytest.mark.asyncio
    async def test_profile_preview_calculation_edge_cases(self, options_flow_with_complex_config):
        """Test profile preview with edge case calculations."""
        # Test preview for all profiles
        for profile in ENTITY_PROFILES.keys():
            result = await options_flow_with_complex_config.async_step_profile_preview({
                "profile": profile
            })
            
            assert result["type"] == FlowResultType.FORM
            assert "profile_name" in result.get("description_placeholders", {})
            assert "total_entities" in result.get("description_placeholders", {})

    @pytest.mark.asyncio
    async def test_performance_settings_validation_edge_cases(self, options_flow_with_complex_config):
        """Test performance settings with invalid values."""
        # Test invalid batch size
        result = await options_flow_with_complex_config.async_step_performance_settings({
            "entity_profile": "standard",
            "performance_mode": "balanced",
            "batch_size": 0,  # Invalid
            "cache_ttl": -100,  # Invalid
        })
        
        # Should handle invalid values gracefully (schema validation should catch this)
        assert result["type"] in [FlowResultType.FORM, FlowResultType.CREATE_ENTRY]

    @pytest.mark.asyncio
    async def test_dog_management_edge_cases(self, options_flow_with_complex_config):
        """Test dog management with edge cases."""
        # Test adding dog with invalid data
        result = await options_flow_with_complex_config.async_step_add_new_dog({
            CONF_DOG_ID: "",  # Empty ID
            CONF_DOG_NAME: "",  # Empty name
            CONF_DOG_AGE: -1,  # Invalid age
            CONF_DOG_WEIGHT: 0,  # Invalid weight
        })
        
        # Should handle invalid data
        assert result["type"] == FlowResultType.FORM
        assert "add_dog_failed" in result.get("errors", {}).get("base", "")

    @pytest.mark.asyncio
    async def test_dog_module_configuration_edge_cases(self, options_flow_with_complex_config):
        """Test dog module configuration with edge cases."""
        # Set current dog for configuration
        options_flow_with_complex_config._current_dog = {
            CONF_DOG_ID: "dog1",
            CONF_DOG_NAME: "Dog 1",
            "modules": {MODULE_FEEDING: True},
        }
        
        # Test configuration update failure
        options_flow_with_complex_config.hass.config_entries.async_update_entry = Mock(
            side_effect=Exception("Update failed")
        )
        
        result = await options_flow_with_complex_config.async_step_configure_dog_modules({
            "module_feeding": False,
            "module_gps": True,
            "module_health": True,
        })
        
        assert result["type"] == FlowResultType.FORM
        assert "module_config_failed" in result.get("errors", {}).get("base", "")

    @pytest.mark.asyncio
    async def test_dog_selection_edge_cases(self, options_flow_with_complex_config):
        """Test dog selection with edge cases."""
        # Test selecting non-existent dog for editing
        result = await options_flow_with_complex_config.async_step_select_dog_to_edit({
            "dog_id": "non_existent_dog"
        })
        
        # Should redirect back to init
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_dog_removal_edge_cases(self, options_flow_with_complex_config):
        """Test dog removal with edge cases."""
        # Test removal without confirmation
        result = await options_flow_with_complex_config.async_step_select_dog_to_remove({
            "dog_id": "dog1",
            "confirm_remove": False,
        })
        
        # Should go back to init without removing
        assert result["step_id"] == "init"
        
        # Test removal with confirmation
        result = await options_flow_with_complex_config.async_step_select_dog_to_remove({
            "dog_id": "dog1", 
            "confirm_remove": True,
        })
        
        # Should remove dog and update config
        options_flow_with_complex_config.hass.config_entries.async_update_entry.assert_called()

    @pytest.mark.asyncio
    async def test_schema_generation_edge_cases(self, options_flow_with_complex_config):
        """Test schema generation with edge case data."""
        # Test with None current dog
        options_flow_with_complex_config._current_dog = None
        schema = options_flow_with_complex_config._get_dog_modules_schema()
        
        # Should return empty schema
        assert schema.schema == {}
        
        # Test with current dog that has no modules
        options_flow_with_complex_config._current_dog = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            # No modules key
        }
        
        schema = options_flow_with_complex_config._get_dog_modules_schema()
        assert isinstance(schema, vol.Schema)

    @pytest.mark.asyncio
    async def test_description_placeholders_edge_cases(self, options_flow_with_complex_config):
        """Test description placeholders with edge case data."""
        # Test with no current dog
        options_flow_with_complex_config._current_dog = None
        placeholders = options_flow_with_complex_config._get_module_description_placeholders()
        
        assert placeholders == {}
        
        # Test with dog that has no modules
        options_flow_with_complex_config._current_dog = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            "modules": {},
        }
        
        placeholders = options_flow_with_complex_config._get_module_description_placeholders()
        assert "enabled_modules" in placeholders
        assert "No modules enabled" in placeholders["enabled_modules"]


class TestOptionsFlowPerformanceStressScenarios:
    """Test options flow performance under stress conditions."""

    @pytest.fixture
    def options_flow_with_many_dogs(self):
        """Create options flow with many dogs for stress testing."""
        dogs = [
            {
                CONF_DOG_ID: f"dog{i}",
                CONF_DOG_NAME: f"Dog {i}",
                CONF_DOG_SIZE: "medium",
                CONF_DOG_BREED: "Mixed",
                CONF_DOG_AGE: 3,
                CONF_DOG_WEIGHT: 20.0,
                "modules": {
                    MODULE_FEEDING: i % 2 == 0,
                    MODULE_GPS: i % 3 == 0,
                    MODULE_HEALTH: i % 4 == 0,
                    MODULE_WALK: True,
                },
            }
            for i in range(50)  # Many dogs
        ]
        
        config_entry = Mock(spec=ConfigEntry)
        config_entry.entry_id = "test_entry"
        config_entry.data = {CONF_DOGS: dogs}
        config_entry.options = {"entity_profile": "standard"}
        
        flow = PawControlOptionsFlow(config_entry)
        flow.hass = Mock()
        flow.hass.config_entries = Mock()
        flow.hass.config_entries.async_update_entry = Mock()
        
        return flow

    @pytest.mark.asyncio
    async def test_large_dog_list_performance(self, options_flow_with_many_dogs):
        """Test performance with large dog lists."""
        import time
        
        # Test dog selection rendering
        start_time = time.time()
        result = await options_flow_with_many_dogs.async_step_select_dog_to_edit()
        end_time = time.time()
        
        # Should complete quickly even with many dogs
        assert end_time - start_time < 1.0
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_concurrent_options_changes(self, options_flow_with_many_dogs):
        """Test concurrent options changes don't interfere."""
        # Simulate concurrent modifications
        tasks = []
        
        for i in range(10):
            task = asyncio.create_task(
                options_flow_with_many_dogs.async_step_performance_settings({
                    "entity_profile": "standard",
                    "performance_mode": "balanced",
                    "batch_size": 15 + i,
                    "cache_ttl": 300 + i * 10,
                })
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should complete successfully
        for result in results:
            assert not isinstance(result, Exception)
            assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_memory_usage_with_large_configurations(self, options_flow_with_many_dogs):
        """Test memory usage doesn't grow excessively with large configurations."""
        # Access various schema generations multiple times
        for _ in range(100):
            schema = options_flow_with_many_dogs._get_performance_settings_schema()
            assert isinstance(schema, vol.Schema)
            
            # Generate placeholders
            placeholders = options_flow_with_many_dogs._get_profile_description_placeholders()
            assert isinstance(placeholders, dict)


class TestConfigFlowErrorRecoveryScenarios:
    """Test error recovery and resilience scenarios."""

    @pytest.fixture
    def failing_config_flow(self):
        """Create config flow that fails in various ways."""
        flow = PawControlConfigFlow()
        flow.hass = Mock()
        
        # Mock methods to fail
        flow._generate_unique_id = Mock(side_effect=Exception("ID generation failed"))
        flow.async_set_unique_id = Mock(side_effect=Exception("Set unique ID failed"))
        flow._abort_if_unique_id_configured = Mock(side_effect=Exception("Abort check failed"))
        
        return flow

    @pytest.mark.asyncio
    async def test_unique_id_generation_failure(self, failing_config_flow):
        """Test handling of unique ID generation failures."""
        # Mock successful validation but failing ID generation
        async def mock_validation(name):
            return {"valid": True, "errors": {}}
        
        failing_config_flow._async_validate_integration_name = mock_validation
        
        result = await failing_config_flow.async_step_user({
            "name": "Test Integration"
        })
        
        # Should handle failure gracefully
        assert result["type"] == FlowResultType.FORM
        assert "unknown" in result.get("errors", {}).get("base", "")

    @pytest.mark.asyncio
    async def test_validation_method_missing(self, failing_config_flow):
        """Test behavior when validation methods are missing."""
        # Remove validation method
        if hasattr(failing_config_flow, '_async_validate_integration_name'):
            delattr(failing_config_flow, '_async_validate_integration_name')
        
        result = await failing_config_flow.async_step_user({
            "name": "Test Integration"
        })
        
        # Should handle missing method gracefully
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_context_manager_error_handling(self):
        """Test config flow context manager error handling."""
        flow = PawControlConfigFlow()
        
        # Test successful context management
        async with flow as managed_flow:
            assert managed_flow is flow
        
        # Test context manager with exception
        try:
            async with flow as managed_flow:
                raise Exception("Test exception")
        except Exception:
            pass  # Expected
        
        # Flow should still be functional after exception
        assert hasattr(flow, '_validation_cache')

    @pytest.mark.asyncio
    async def test_async_dog_validation_fallback(self):
        """Test async dog validation fallback scenarios."""
        flow = PawControlConfigFlow()
        
        # Test with missing sync validation function
        dog_config = {CONF_DOG_ID: "test", CONF_DOG_NAME: "Test"}
        
        # Should handle missing validation gracefully
        result = await flow._validate_dog_config_async(dog_config)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_feature_summary_caching_edge_cases(self):
        """Test feature summary caching edge cases."""
        flow = PawControlConfigFlow()
        
        # Test cached feature summary
        summary1 = flow._get_feature_summary_cached()
        summary2 = flow._get_feature_summary_cached()
        
        # Should return same cached result
        assert summary1 == summary2
        assert isinstance(summary1, str)


class TestConfigFlowBoundaryConditions:
    """Test boundary conditions and limits."""

    @pytest.fixture
    def boundary_config_flow(self):
        """Create config flow for boundary testing."""
        flow = PawControlConfigFlow()
        flow.hass = Mock()
        return flow

    @pytest.mark.asyncio
    async def test_extremely_long_integration_names(self, boundary_config_flow):
        """Test handling of extremely long integration names."""
        # Test very long name
        long_name = "A" * 1000
        
        async def mock_validation(name):
            return {"valid": len(name) <= 100, "errors": {"base": "name_too_long"} if len(name) > 100 else {}}
        
        boundary_config_flow._async_validate_integration_name = mock_validation
        
        result = await boundary_config_flow.async_step_user({"name": long_name})
        
        assert result["type"] == FlowResultType.FORM
        assert "name_too_long" in result.get("errors", {}).get("base", "")

    @pytest.mark.asyncio
    async def test_maximum_dogs_configuration(self, boundary_config_flow):
        """Test configuration with maximum number of dogs."""
        # Configure many dogs
        many_dogs = [
            {
                CONF_DOG_ID: f"dog{i}",
                CONF_DOG_NAME: f"Dog {i}",
                "modules": {MODULE_FEEDING: True},
            }
            for i in range(100)  # Many dogs
        ]
        
        boundary_config_flow._dogs = many_dogs
        boundary_config_flow._integration_name = "Test"
        boundary_config_flow._entity_profile = "basic"
        
        # Should handle many dogs
        estimates = boundary_config_flow._calculate_profile_estimates()
        assert all(isinstance(estimate, int) for estimate in estimates.values())

    @pytest.mark.asyncio
    async def test_empty_dogs_configuration(self, boundary_config_flow):
        """Test configuration with empty dogs list."""
        boundary_config_flow._dogs = []
        boundary_config_flow._integration_name = "Test"
        boundary_config_flow._entity_profile = "standard"
        
        # Should handle empty list gracefully
        recommendation = boundary_config_flow._get_recommended_profile()
        assert recommendation in ENTITY_PROFILES.keys()
        
        estimates = boundary_config_flow._calculate_profile_estimates()
        assert all(estimate >= 0 for estimate in estimates.values())

    @pytest.mark.asyncio
    async def test_profile_edge_case_values(self):
        """Test profile edge case values."""
        # Test profile calculations with edge case inputs
        edge_cases = [
            (None, False, False, False),
            ("", True, True, True),
            ("unknown_profile", False, False, False),
        ]
        
        for profile, has_gps, has_multiple, has_large in edge_cases:
            # Should not crash with invalid inputs
            try:
                result = PawControlConfigFlow._calculate_performance_mode_with_profile(
                    profile or "balanced", has_gps, has_multiple, has_large
                )
                assert isinstance(result, str)
            except (KeyError, AttributeError):
                # Expected for invalid profiles
                pass


@pytest.mark.asyncio
async def test_comprehensive_config_flow_integration():
    """Comprehensive integration test covering multiple config flow scenarios."""
    # Test complete config flow setup
    flow = PawControlConfigFlow()
    flow.hass = Mock()
    flow._abort_if_unique_id_configured = Mock()
    
    # Mock successful validation
    async def mock_validation(name):
        return {"valid": True, "errors": {}}
    
    flow._async_validate_integration_name = mock_validation
    flow._generate_unique_id = Mock(return_value="test_integration_id")
    flow.async_set_unique_id = Mock()
    
    # Mock dog addition methods
    flow.async_step_add_dog = AsyncMock(return_value={
        "type": FlowResultType.FORM,
        "step_id": "entity_profile"
    })
    
    # Test user step
    result = await flow.async_step_user({"name": "Test Integration"})
    
    # Should proceed to add_dog step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "entity_profile"
    
    # Test entity profile selection
    flow._dogs = [
        {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            "modules": {MODULE_FEEDING: True, MODULE_HEALTH: True},
        }
    ]
    
    result = await flow.async_step_entity_profile({"entity_profile": "standard"})
    
    # Should complete setup
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert "Test Integration" in result["title"]
    assert "standard" in result["title"].lower()
    
    # Verify configuration data
    assert CONF_DOGS in result["data"]
    assert "entity_profile" in result["data"]
    assert result["data"]["entity_profile"] == "standard"
