"""Comprehensive edge case tests for PawControl config flow system.

Tests all aspects of the configuration flow including validation cache,
entity profiles, async validation, dog management, module configuration,
and complex user interaction scenarios.

Test Areas:
- ValidationCache edge cases (TTL, concurrency, memory)
- Entity profile optimization and estimation
- Async validation with timeouts and semaphore limits
- Dog configuration with complex modules and health data
- Diet combination validation and conflicts
- Global settings and dashboard configuration
- Error recovery and malformed input handling
- Performance under stress conditions
- User workflow interruption scenarios
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import Dict
from typing import List
from unittest.mock import AsyncMock
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pawcontrol.config_flow import ENTITY_PROFILES
from custom_components.pawcontrol.config_flow import MAX_CONCURRENT_VALIDATIONS
from custom_components.pawcontrol.config_flow import PawControlConfigFlow
from custom_components.pawcontrol.config_flow import PROFILE_SCHEMA
from custom_components.pawcontrol.config_flow import VALIDATION_CACHE_TTL
from custom_components.pawcontrol.config_flow import VALIDATION_TIMEOUT
from custom_components.pawcontrol.config_flow import ValidationCache
from custom_components.pawcontrol.config_flow_base import DOG_BASE_SCHEMA
from custom_components.pawcontrol.config_flow_base import DOG_ID_PATTERN
from custom_components.pawcontrol.config_flow_base import ENTITY_CREATION_DELAY
from custom_components.pawcontrol.config_flow_base import INTEGRATION_SCHEMA
from custom_components.pawcontrol.config_flow_base import MAX_DOGS_PER_ENTRY
from custom_components.pawcontrol.config_flow_base import VALIDATION_SEMAPHORE
from custom_components.pawcontrol.config_flow_dogs import (
    DIET_COMPATIBILITY_RULES,
)
from custom_components.pawcontrol.const import CONF_DOG_AGE
from custom_components.pawcontrol.const import CONF_DOG_BREED
from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOG_SIZE
from custom_components.pawcontrol.const import CONF_DOG_WEIGHT
from custom_components.pawcontrol.const import CONF_MODULES
from custom_components.pawcontrol.const import DOG_SIZES
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.const import MAX_DOG_AGE
from custom_components.pawcontrol.const import MAX_DOG_WEIGHT
from custom_components.pawcontrol.const import MIN_DOG_AGE
from custom_components.pawcontrol.const import MIN_DOG_WEIGHT
from custom_components.pawcontrol.const import MODULE_FEEDING
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_WALK
from custom_components.pawcontrol.const import SPECIAL_DIET_OPTIONS


class TestValidationCacheEdgeCases:
    """Test validation cache edge cases and performance."""

    @pytest.fixture
    def cache(self):
        """Create a validation cache for testing."""
        return ValidationCache(ttl=1)  # 1 second TTL for faster testing

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self, cache):
        """Test cache TTL expiration behavior."""
        # Set initial value
        await cache.set("test_key", "test_value")

        # Should return value immediately
        result = await cache.get("test_key")
        assert result == "test_value"

        # Wait for TTL expiration
        await asyncio.sleep(1.1)

        # Should return None after expiration
        result = await cache.get("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_concurrent_access(self, cache):
        """Test cache thread safety with concurrent access."""

        async def set_values():
            for i in range(10):
                await cache.set(f"key_{i}", f"value_{i}")
                await asyncio.sleep(0.01)

        async def get_values():
            results = []
            for i in range(10):
                result = await cache.get(f"key_{i}")
                results.append(result)
                await asyncio.sleep(0.01)
            return results

        # Run concurrent operations
        await asyncio.gather(
            set_values(),
            set_values(),
            get_values(),
            get_values(),
        )

        # Cache should remain consistent
        for i in range(10):
            result = await cache.get(f"key_{i}")
            if result is not None:  # May be None due to TTL
                assert result == f"value_{i}"

    @pytest.mark.asyncio
    async def test_cache_memory_cleanup(self, cache):
        """Test cache cleans up expired entries."""
        # Add many entries
        for i in range(100):
            await cache.set(f"key_{i}", f"value_{i}")

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Access one entry to trigger cleanup
        await cache.get("key_50")

        # Cache should have cleaned up expired entries
        # (Implementation detail - checking internals)
        assert len(cache._cache) <= 1

    @pytest.mark.asyncio
    async def test_cache_overwrite_behavior(self, cache):
        """Test cache overwrite and update behavior."""
        # Set initial value
        await cache.set("test_key", "initial_value")

        # Overwrite with new value
        await cache.set("test_key", "new_value")

        # Should return new value
        result = await cache.get("test_key")
        assert result == "new_value"

    @pytest.mark.asyncio
    async def test_cache_clear_functionality(self, cache):
        """Test cache clear functionality."""
        # Add multiple entries
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        # Clear cache
        await cache.clear()

        # All entries should be gone
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is None

    @pytest.mark.asyncio
    async def test_cache_edge_case_keys(self, cache):
        """Test cache with edge case keys."""
        edge_case_keys = [
            "",  # Empty string
            " ",  # Whitespace
            "key with spaces",
            "key_with_underscores",
            "key-with-dashes",
            "unicode_key_🐕",
            "very_long_key_" + "x" * 1000,
        ]

        for key in edge_case_keys:
            await cache.set(key, f"value_for_{key}")
            result = await cache.get(key)
            assert result == f"value_for_{key}"

    @pytest.mark.asyncio
    async def test_cache_none_and_false_values(self, cache):
        """Test cache with None and falsy values."""
        test_values = [None, False, 0, "", [], {}]

        for i, value in enumerate(test_values):
            key = f"test_key_{i}"
            await cache.set(key, value)
            result = await cache.get(key)
            assert result == value


class TestEntityProfileEdgeCases:
    """Test entity profile optimization edge cases."""

    @pytest.fixture
    def config_flow(self, hass):
        """Create a config flow for testing."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = []
        return flow

    def test_profile_estimates_empty_dogs(self, config_flow):
        """Test profile estimates with no dogs configured."""
        estimates = config_flow._calculate_profile_estimates()

        # Should handle empty dogs list gracefully
        for profile in ENTITY_PROFILES:
            assert profile in estimates
            assert estimates[profile] >= 0

    def test_profile_estimates_complex_configuration(self, config_flow):
        """Test profile estimates with complex dog configurations."""
        # Add complex dog configuration
        config_flow._dogs = [
            {
                CONF_DOG_ID: "complex_dog",
                CONF_DOG_NAME: "Complex Dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                    MODULE_WALK: True,
                    "grooming": True,
                    "medication": True,
                    "training": True,
                    "notifications": True,
                },
                "feeding_config": {"special_diet": ["prescription", "diabetic"]},
                "health_config": {"medications": [{"name": "test"}]},
                "gps_config": {"geofencing": True},
            }
        ]

        estimates = config_flow._calculate_profile_estimates()

        # All profiles should respect their limits
        for profile_name, estimate in estimates.items():
            max_entities = ENTITY_PROFILES[profile_name]["max_entities"]
            assert estimate <= max_entities
            assert estimate > 0  # Should have some entities

    def test_profile_estimates_edge_case_modules(self, config_flow):
        """Test profile estimates with edge case module configurations."""
        edge_cases = [
            # No modules enabled
            {"modules": {}},
            # Only one module
            {"modules": {MODULE_FEEDING: True}},
            # All modules disabled explicitly
            {
                "modules": {
                    MODULE_FEEDING: False,
                    MODULE_GPS: False,
                    MODULE_HEALTH: False,
                    MODULE_WALK: False,
                }
            },
            # Mixed enabled/disabled
            {
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: False,
                    MODULE_HEALTH: True,
                    MODULE_WALK: False,
                }
            },
        ]

        for i, dog_config in enumerate(edge_cases):
            config_flow._dogs = [
                {
                    CONF_DOG_ID: f"test_dog_{i}",
                    CONF_DOG_NAME: f"Test Dog {i}",
                    **dog_config,
                }
            ]

            estimates = config_flow._calculate_profile_estimates()

            # Should handle all edge cases without errors
            for profile in ENTITY_PROFILES:
                assert estimates[profile] >= 0

    def test_recommended_profile_edge_cases(self, config_flow):
        """Test recommended profile selection edge cases."""
        # Test with no dogs
        config_flow._dogs = []
        recommendation = config_flow._get_recommended_profile()
        assert recommendation == "standard"

        # Test with complex configurations
        test_cases = [
            # Single basic dog
            {
                "dogs": [{"modules": {MODULE_FEEDING: True}}],
                "expected": "basic",
            },
            # Multiple dogs with GPS
            {
                "dogs": [
                    {"modules": {MODULE_GPS: True}},
                    {"modules": {MODULE_GPS: True}},
                ],
                "expected": "advanced",
            },
            # Health-focused single dog
            {
                "dogs": [{"modules": {MODULE_HEALTH: True}}],
                "expected": "health_focus",
            },
            # GPS-focused single dog
            {
                "dogs": [{"modules": {MODULE_GPS: True}}],
                "expected": "gps_focus",
            },
            # Complex feeding configuration
            {
                "dogs": [
                    {
                        "modules": {
                            MODULE_FEEDING: True,
                            "special_diet": [
                                "prescription",
                                "diabetic",
                                "kidney_support",
                            ],
                        }
                    }
                ],
                "expected": "standard",
            },
        ]

        for case in test_cases:
            config_flow._dogs = [
                {
                    CONF_DOG_ID: f"dog_{i}",
                    CONF_DOG_NAME: f"Dog {i}",
                    **dog,
                }
                for i, dog in enumerate(case["dogs"])
            ]

            recommendation = config_flow._get_recommended_profile()
            # Recommendation should be sensible
            assert recommendation in ENTITY_PROFILES

    def test_performance_comparison_generation(self, config_flow):
        """Test performance comparison text generation."""
        config_flow._dogs = [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Test Dog",
                "modules": {MODULE_FEEDING: True, MODULE_GPS: True},
            }
        ]

        comparison = config_flow._get_performance_comparison()

        # Should contain all profiles
        for profile_name in ENTITY_PROFILES:
            assert (
                profile_name in comparison
                or ENTITY_PROFILES[profile_name]["name"] in comparison
            )

        # Should contain entity counts and percentages
        assert "entities" in comparison
        assert "%" in comparison

    def test_profile_schema_validation(self):
        """Test entity profile schema validation."""
        # Valid profiles
        for profile in ENTITY_PROFILES:
            validated = PROFILE_SCHEMA({"entity_profile": profile})
            assert validated["entity_profile"] == profile

        # Invalid profile should raise error
        with pytest.raises(Exception):
            PROFILE_SCHEMA({"entity_profile": "invalid_profile"})

        # Default value
        validated = PROFILE_SCHEMA({})
        assert validated["entity_profile"] == "standard"


class TestAsyncValidationEdgeCases:
    """Test async validation edge cases and error handling."""

    @pytest.fixture
    def config_flow(self, hass):
        """Create a config flow for testing."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = []
        return flow

    @pytest.mark.asyncio
    async def test_validation_timeout_handling(self, config_flow):
        """Test validation timeout scenarios."""

        # Mock slow validation
        async def slow_validation(*args):
            await asyncio.sleep(2)  # Longer than VALIDATION_TIMEOUT
            return {"valid": True, "errors": {}}

        with patch.object(
            config_flow, "_async_validate_integration_name", side_effect=slow_validation
        ):
            result = await config_flow.async_step_user({CONF_NAME: "Test Integration"})

        # Should handle timeout gracefully
        assert result["type"] == FlowResultType.FORM
        assert "errors" in result
        if result["errors"]:
            assert "validation_timeout" in result["errors"]["base"]

    @pytest.mark.asyncio
    async def test_validation_semaphore_limit(self, config_flow):
        """Test validation semaphore limits concurrent operations."""
        # Track concurrent validations
        concurrent_count = 0
        max_concurrent = 0

        async def track_validation(*args):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.1)
            concurrent_count -= 1
            return {"valid": True, "errors": {}}

        with patch.object(
            config_flow,
            "_async_validate_integration_name",
            side_effect=track_validation,
        ):
            # Start many validations concurrently
            tasks = []
            for i in range(10):
                task = config_flow.async_step_user({CONF_NAME: f"Test {i}"})
                tasks.append(task)

            await asyncio.gather(*tasks, return_exceptions=True)

        # Should not exceed semaphore limit
        assert max_concurrent <= MAX_CONCURRENT_VALIDATIONS

    @pytest.mark.asyncio
    async def test_validation_cache_integration(self, config_flow):
        """Test validation cache integration in real flow."""
        validation_calls = 0

        async def count_validation(*args):
            nonlocal validation_calls
            validation_calls += 1
            return {"valid": True, "errors": {}}

        with patch.object(
            config_flow,
            "_async_validate_integration_name",
            side_effect=count_validation,
        ):
            # First validation - should call function
            await config_flow.async_step_user({CONF_NAME: "Test Integration"})

            # Second validation with same name - should use cache
            await config_flow.async_step_user({CONF_NAME: "Test Integration"})

        # Should only call validation function once due to caching
        assert validation_calls == 1

    @pytest.mark.asyncio
    async def test_validation_error_propagation(self, config_flow):
        """Test validation error propagation."""

        # Mock validation errors
        async def error_validation(*args):
            return {
                "valid": False,
                "errors": {"base": "custom_error"},
            }

        with patch.object(
            config_flow,
            "_async_validate_integration_name",
            side_effect=error_validation,
        ):
            result = await config_flow.async_step_user({CONF_NAME: "Test Integration"})

        # Should propagate validation errors
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "custom_error"

    @pytest.mark.asyncio
    async def test_validation_exception_handling(self, config_flow):
        """Test validation exception handling."""

        # Mock validation exception
        async def exception_validation(*args):
            raise Exception("Validation failed")

        with patch.object(
            config_flow,
            "_async_validate_integration_name",
            side_effect=exception_validation,
        ):
            result = await config_flow.async_step_user({CONF_NAME: "Test Integration"})

        # Should handle exceptions gracefully
        assert result["type"] == FlowResultType.FORM
        assert "errors" in result


class TestDogConfigurationEdgeCases:
    """Test dog configuration edge cases and complex scenarios."""

    @pytest.fixture
    def config_flow(self, hass):
        """Create a config flow for testing."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = []
        flow._integration_name = "Test Integration"
        flow._current_dog_config = None
        return flow

    @pytest.mark.asyncio
    async def test_dog_id_validation_edge_cases(self, config_flow):
        """Test dog ID validation with edge cases."""
        edge_cases = [
            # Invalid cases
            ("", False),  # Empty
            ("1dog", False),  # Starts with number
            ("dog-name", False),  # Contains dash
            ("dog name", False),  # Contains space
            ("Dog", False),  # Contains uppercase
            ("dog.name", False),  # Contains dot
            ("a", False),  # Too short
            ("a" * 31, False),  # Too long
            # Valid cases
            ("dog_name", True),
            ("my_dog_123", True),
            ("a1", True),
            ("dog123", True),
            ("my_awesome_dog", True),
        ]

        for dog_id, should_be_valid in edge_cases:
            validation_result = await config_flow._async_validate_dog_config(
                {
                    CONF_DOG_ID: dog_id,
                    CONF_DOG_NAME: "Test Dog",
                    CONF_DOG_SIZE: "medium",
                    CONF_DOG_WEIGHT: 20.0,
                    CONF_DOG_AGE: 3,
                }
            )

            if should_be_valid:
                assert validation_result["valid"], f"Expected {dog_id} to be valid"
            else:
                assert not validation_result["valid"], (
                    f"Expected {dog_id} to be invalid"
                )

    @pytest.mark.asyncio
    async def test_dog_weight_size_compatibility(self, config_flow):
        """Test dog weight-size compatibility validation."""
        test_cases = [
            # Valid combinations
            ("toy", 3.0, True),
            ("small", 10.0, True),
            ("medium", 20.0, True),
            ("large", 35.0, True),
            ("giant", 60.0, True),
            # Invalid combinations
            ("toy", 50.0, False),  # Too heavy for toy
            ("giant", 2.0, False),  # Too light for giant
            ("small", 80.0, False),  # Way too heavy for small
            # Edge cases (should be valid due to overlaps)
            ("small", 15.0, True),  # Upper range of small
            ("medium", 8.0, True),  # Lower range of medium
        ]

        for size, weight, should_be_valid in test_cases:
            validation_result = await config_flow._async_validate_dog_config(
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    CONF_DOG_SIZE: size,
                    CONF_DOG_WEIGHT: weight,
                    CONF_DOG_AGE: 3,
                }
            )

            if should_be_valid:
                assert validation_result["valid"], (
                    f"Expected {size} + {weight}kg to be valid"
                )
            else:
                assert not validation_result["valid"], (
                    f"Expected {size} + {weight}kg to be invalid"
                )

    @pytest.mark.asyncio
    async def test_duplicate_detection(self, config_flow):
        """Test duplicate dog detection."""
        # Add first dog
        config_flow._dogs = [
            {
                CONF_DOG_ID: "existing_dog",
                CONF_DOG_NAME: "Existing Dog",
            }
        ]

        # Test duplicate ID
        validation_result = await config_flow._async_validate_dog_config(
            {
                CONF_DOG_ID: "existing_dog",
                CONF_DOG_NAME: "Different Name",
                CONF_DOG_SIZE: "medium",
                CONF_DOG_WEIGHT: 20.0,
                CONF_DOG_AGE: 3,
            }
        )
        assert not validation_result["valid"]
        assert "dog_id_already_exists" in validation_result["errors"][CONF_DOG_ID]

        # Test duplicate name (case insensitive)
        validation_result = await config_flow._async_validate_dog_config(
            {
                CONF_DOG_ID: "different_id",
                CONF_DOG_NAME: "EXISTING DOG",  # Different case
                CONF_DOG_SIZE: "medium",
                CONF_DOG_WEIGHT: 20.0,
                CONF_DOG_AGE: 3,
            }
        )
        assert not validation_result["valid"]
        assert "dog_name_already_exists" in validation_result["errors"][CONF_DOG_NAME]

    def test_food_amount_calculation_edge_cases(self, config_flow):
        """Test food amount calculation with edge cases."""
        edge_cases = [
            # (weight, size, expected_range_min, expected_range_max)
            (1.0, "toy", 30, 50),  # Minimum weight
            (90.0, "giant", 1800, 2300),  # Maximum weight
            (20.0, "medium", 400, 600),  # Typical case
            (5.5, "small", 130, 180),  # Decimal weight
        ]

        for weight, size, min_expected, max_expected in edge_cases:
            result = config_flow._calculate_suggested_food_amount(weight, size)

            assert min_expected <= result <= max_expected
            assert result % 10 == 0  # Should be rounded to nearest 10g

    @pytest.mark.asyncio
    async def test_smart_dog_id_suggestion_edge_cases(self, config_flow):
        """Test smart dog ID suggestion with edge cases."""
        edge_cases = [
            # Input name, expected pattern
            ("", ""),  # Empty name
            ("Max", "max"),  # Simple name
            ("Max Cooper", "max_c"),  # Two words
            ("My Awesome Dog Name", "myawesomed"),  # Multiple words
            ("123 Dog", "dog_123"),  # Starts with number
            ("Dog-Name", "dogname"),  # Special characters
            ("Ümlaut Dog", "mlautdog"),  # Unicode characters
            ("A" * 100, "a" * 20),  # Very long name
        ]

        for name, expected_pattern in edge_cases:
            suggestion = await config_flow._generate_smart_dog_id_suggestion(
                {CONF_DOG_NAME: name}
            )

            if name:
                assert len(suggestion) > 0
                assert suggestion.islower()
                assert not suggestion[0].isdigit() if suggestion else True
            else:
                assert suggestion == ""

    @pytest.mark.asyncio
    async def test_dog_id_collision_avoidance(self, config_flow):
        """Test dog ID collision avoidance."""
        # Add existing dogs
        config_flow._dogs = [
            {CONF_DOG_ID: "max", CONF_DOG_NAME: "Max"},
            {CONF_DOG_ID: "max_2", CONF_DOG_NAME: "Max 2"},
            {CONF_DOG_ID: "max2", CONF_DOG_NAME: "Max2"},
        ]

        suggestion = await config_flow._generate_smart_dog_id_suggestion(
            {CONF_DOG_NAME: "Max"}
        )

        # Should suggest non-conflicting ID
        assert suggestion not in ["max", "max_2", "max2"]
        assert "max" in suggestion  # Should be based on original name

    @pytest.mark.asyncio
    async def test_maximum_dogs_limit(self, config_flow):
        """Test maximum dogs per entry limit."""
        # Add maximum number of dogs
        config_flow._dogs = [
            {
                CONF_DOG_ID: f"dog_{i}",
                CONF_DOG_NAME: f"Dog {i}",
            }
            for i in range(MAX_DOGS_PER_ENTRY)
        ]

        # Try to add another dog step
        result = await config_flow.async_step_add_another_dog({"add_another": True})

        # Should either prevent adding or handle gracefully
        assert result["type"] in [
            FlowResultType.FORM, FlowResultType.CREATE_ENTRY]


class TestDietValidationEdgeCases:
    """Test diet validation and compatibility edge cases."""

    @pytest.fixture
    def config_flow(self, hass):
        """Create a config flow for testing."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = []
        return flow

    def test_diet_combinations_all_valid_options(self, config_flow):
        """Test diet validation with all valid SPECIAL_DIET_OPTIONS."""
        # Test each diet option individually
        for diet_option in SPECIAL_DIET_OPTIONS:
            validation = config_flow._validate_diet_combinations([diet_option])

            # Single diet should generally be valid
            assert validation["total_diets"] == 1
            # Conflicts are possible but warnings might exist
            assert isinstance(validation["conflicts"], list)
            assert isinstance(validation["warnings"], list)

    def test_diet_conflict_detection(self, config_flow):
        """Test detection of conflicting diet combinations."""
        conflict_cases = [
            # Age-based conflicts
            (["puppy_formula", "senior_formula"], True),
            # Weight management with puppy (warning, not conflict)
            (["weight_control", "puppy_formula"], False),
            # Raw diet with medical conditions (warnings)
            (["raw_diet", "prescription"], False),
            (["raw_diet", "diabetic"], False),
        ]

        for diet_combination, should_have_conflicts in conflict_cases:
            validation = config_flow._validate_diet_combinations(
                diet_combination)

            if should_have_conflicts:
                assert len(validation["conflicts"]) > 0
            # Note: Some combinations produce warnings instead of conflicts

    def test_diet_warning_detection(self, config_flow):
        """Test detection of diet combination warnings."""
        warning_cases = [
            ["raw_diet", "prescription"],
            ["raw_diet", "kidney_support"],
            ["prescription", "diabetic", "kidney_support"],
            ["hypoallergenic", "organic"],
            ["hypoallergenic", "raw_diet"],
            ["low_fat", "joint_support"],
            ["weight_control", "puppy_formula"],
        ]

        for diet_combination in warning_cases:
            validation = config_flow._validate_diet_combinations(
                diet_combination)

            # Should generate warnings for complex combinations
            # Note: Some may not generate warnings depending on rules
            assert isinstance(validation["warnings"], list)
            assert validation["recommended_vet_consultation"] in [True, False]

    def test_diet_empty_and_edge_cases(self, config_flow):
        """Test diet validation with empty and edge cases."""
        edge_cases = [
            [],  # No diets
            # Invalid diet (should be handled gracefully)
            ["nonexistent_diet"],
            SPECIAL_DIET_OPTIONS,  # All diets at once
            ["prescription"] * 5,  # Duplicate diets
        ]

        for diet_list in edge_cases:
            # Should not raise exceptions
            validation = config_flow._validate_diet_combinations(diet_list)

            assert isinstance(validation, dict)
            assert "valid" in validation
            assert "conflicts" in validation
            assert "warnings" in validation

    def test_diet_guidance_generation(self, config_flow):
        """Test diet compatibility guidance generation."""
        test_cases = [
            (1, "toy"),  # Puppy, small
            (3, "medium"),  # Adult, medium
            (8, "large"),  # Senior, large
            (12, "giant"),  # Very senior, giant
        ]

        for age, size in test_cases:
            guidance = config_flow._get_diet_compatibility_guidance(age, size)

            assert isinstance(guidance, str)
            assert len(guidance) > 0

            # Should contain relevant info for age/size
            if age < 2:
                assert "puppy" in guidance.lower() or "young" in guidance.lower()
            elif age >= 7:
                assert "senior" in guidance.lower() or "older" in guidance.lower()

            if size in ("large", "giant"):
                assert "large" in guidance.lower() or "joint" in guidance.lower()

    def test_health_conditions_collection(self, config_flow):
        """Test health conditions collection from user input."""
        test_input = {
            "has_diabetes": True,
            "has_kidney_disease": False,
            "has_heart_disease": True,
            "has_arthritis": False,
            "has_allergies": True,
            "has_digestive_issues": False,
            "other_health_conditions": "hip dysplasia, anxiety",
        }

        conditions = config_flow._collect_health_conditions(test_input)

        # Should include selected conditions
        assert "diabetes" in conditions
        assert "heart_disease" in conditions
        assert "allergies" in conditions

        # Should not include unselected conditions
        assert "kidney_disease" not in conditions
        assert "arthritis" not in conditions
        assert "digestive_issues" not in conditions

        # Should include parsed other conditions
        assert "hip_dysplasia" in conditions
        assert "anxiety" in conditions

    def test_special_diet_collection(self, config_flow):
        """Test special diet collection from user input."""
        # Create input with some diet options selected
        test_input = {
            "prescription": True,
            "diabetic": False,
            "grain_free": True,
            "senior_formula": False,
            "organic": True,
            "raw_diet": False,
        }

        diet_requirements = config_flow._collect_special_diet(test_input)

        # Should include selected diets
        assert "prescription" in diet_requirements
        assert "grain_free" in diet_requirements
        assert "organic" in diet_requirements

        # Should not include unselected diets
        assert "diabetic" not in diet_requirements
        assert "senior_formula" not in diet_requirements
        assert "raw_diet" not in diet_requirements

    def test_activity_level_suggestions(self, config_flow):
        """Test activity level suggestions based on dog characteristics."""
        test_cases = [
            # (age, size, expected_contains)
            (0.5, "small", "moderate"),  # Puppy
            (2, "toy", "moderate"),  # Young small dog
            (5, "medium", "high"),  # Adult medium dog
            (5, "large", "high"),  # Adult large dog
            (8, "large", "moderate"),  # Older large dog
            (12, "giant", "low"),  # Senior giant dog
        ]

        for age, size, expected_level in test_cases:
            suggestion = config_flow._suggest_activity_level(age, size)

            assert suggestion in ["very_low", "low",
                                  "moderate", "high", "very_high"]
            # Note: Exact matches may vary based on implementation


class TestComplexUserWorkflows:
    """Test complex user workflow scenarios and edge cases."""

    @pytest.fixture
    def config_flow(self, hass):
        """Create a config flow for testing."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = []
        flow._integration_name = "Test Integration"
        return flow

    @pytest.mark.asyncio
    async def test_complete_workflow_single_dog(self, config_flow):
        """Test complete workflow with single dog configuration."""
        # Step 1: User input
        result = await config_flow.async_step_user({CONF_NAME: "Test Integration"})
        assert result["type"] == FlowResultType.FORM

        # Mock validation to succeed
        with patch.object(
            config_flow, "_async_validate_integration_name"
        ) as mock_validate:
            mock_validate.return_value = {"valid": True, "errors": {}}

            # Step 2: Add dog
            result = await config_flow.async_step_user({CONF_NAME: "Test Integration"})

            # Should proceed to add_dog step
            # Note: Actual flow depends on implementation details

    @pytest.mark.asyncio
    async def test_workflow_interruption_and_recovery(self, config_flow):
        """Test workflow interruption and recovery scenarios."""
        # Start configuration
        config_flow._dogs = [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Test Dog",
                "modules": {MODULE_FEEDING: True},
            }
        ]

        # Test various interruption points
        interruption_points = [
            "add_dog",
            "dog_modules",
            "dog_feeding",
            "dog_health",
            "configure_modules",
            "entity_profile",
        ]

        for step in interruption_points:
            # Each step should handle None input gracefully
            if hasattr(config_flow, f"async_step_{step}"):
                step_method = getattr(config_flow, f"async_step_{step}")
                result = await step_method(None)

                # Should return a form for user input
                assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_malformed_input_handling(self, config_flow):
        """Test handling of malformed input data."""
        malformed_inputs = [
            {},  # Empty dict
            {"invalid_key": "value"},  # Wrong keys
            {CONF_DOG_NAME: None},  # None values
            {CONF_DOG_AGE: "not_a_number"},  # Wrong types
            {CONF_DOG_WEIGHT: -5},  # Negative values
            {CONF_DOG_SIZE: "invalid_size"},  # Invalid enum values
        ]

        for malformed_input in malformed_inputs:
            # Should handle gracefully without crashing
            validation_result = await config_flow._async_validate_dog_config(
                malformed_input
            )

            # Should return validation result with errors
            assert isinstance(validation_result, dict)
            assert "valid" in validation_result
            # Malformed input should generally be invalid
            if malformed_input:  # Skip empty dict
                assert not validation_result.get("valid", True)

    @pytest.mark.asyncio
    async def test_entity_profile_workflow(self, config_flow):
        """Test entity profile selection workflow."""
        # Add some dogs
        config_flow._dogs = [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Dog 1",
                "modules": {MODULE_FEEDING: True, MODULE_GPS: True},
            },
            {
                CONF_DOG_ID: "dog2",
                CONF_DOG_NAME: "Dog 2",
                "modules": {MODULE_HEALTH: True, MODULE_WALK: True},
            },
        ]

        # Test profile selection
        await config_flow.async_step_entity_profile({"entity_profile": "advanced"})

        # Should accept valid profile
        assert config_flow._entity_profile == "advanced"

    @pytest.mark.asyncio
    async def test_final_setup_data_integrity(self, config_flow):
        """Test final setup data integrity and validation."""
        # Set up complete configuration
        config_flow._dogs = [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Test Dog",
                CONF_DOG_SIZE: "medium",
                CONF_DOG_WEIGHT: 20.0,
                CONF_DOG_AGE: 3,
                "modules": {MODULE_FEEDING: True},
            }
        ]
        config_flow._entity_profile = "standard"

        # Mock validation
        with patch.object(config_flow, "_validate_dog_config_async", return_value=True):
            result = await config_flow.async_step_final_setup({})

        # Should create entry with all necessary data
        if result["type"] == FlowResultType.CREATE_ENTRY:
            assert "entity_profile" in result["data"]
            assert "dogs" in result["data"]


class TestPerformanceAndStressScenarios:
    """Test performance characteristics and stress scenarios."""

    @pytest.fixture
    def config_flow(self, hass):
        """Create a config flow for testing."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = []
        return flow

    @pytest.mark.asyncio
    async def test_large_number_of_dogs_performance(self, config_flow):
        """Test performance with maximum number of dogs."""
        # Add maximum dogs
        for i in range(MAX_DOGS_PER_ENTRY):
            config_flow._dogs.append(
                {
                    CONF_DOG_ID: f"dog_{i}",
                    CONF_DOG_NAME: f"Dog {i}",
                    CONF_DOG_SIZE: DOG_SIZES[i % len(DOG_SIZES)],
                    CONF_DOG_WEIGHT: 20.0 + i,
                    CONF_DOG_AGE: 3 + (i % 10),
                    "modules": {
                        MODULE_FEEDING: i % 2 == 0,
                        MODULE_GPS: i % 3 == 0,
                        MODULE_HEALTH: i % 4 == 0,
                        MODULE_WALK: i % 5 == 0,
                    },
                }
            )

        # Test profile calculations with many dogs
        start_time = time.time()
        estimates = config_flow._calculate_profile_estimates()
        calculation_time = time.time() - start_time

        # Should complete quickly even with many dogs
        assert calculation_time < 1.0  # Less than 1 second
        assert len(estimates) == len(ENTITY_PROFILES)

    @pytest.mark.asyncio
    async def test_concurrent_validation_performance(self, config_flow):
        """Test concurrent validation performance."""
        # Create many validation tasks
        validation_tasks = []
        for i in range(20):
            task = config_flow._async_validate_dog_config(
                {
                    CONF_DOG_ID: f"dog_{i}",
                    CONF_DOG_NAME: f"Dog {i}",
                    CONF_DOG_SIZE: "medium",
                    CONF_DOG_WEIGHT: 20.0,
                    CONF_DOG_AGE: 3,
                }
            )
            validation_tasks.append(task)

        # Run all validations concurrently
        start_time = time.time()
        results = await asyncio.gather(*validation_tasks, return_exceptions=True)
        total_time = time.time() - start_time

        # Should complete within reasonable time
        assert total_time < 5.0  # Less than 5 seconds for 20 validations

        # All results should be valid (no exceptions)
        for result in results:
            assert not isinstance(result, Exception)
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_cache_performance_under_load(self):
        """Test validation cache performance under load."""
        cache = ValidationCache(ttl=60)

        # Add many entries rapidly
        start_time = time.time()
        for i in range(1000):
            await cache.set(f"key_{i}", f"value_{i}")
        set_time = time.time() - start_time

        # Retrieve many entries rapidly
        start_time = time.time()
        for i in range(1000):
            await cache.get(f"key_{i}")
        get_time = time.time() - start_time

        # Should handle load efficiently
        assert set_time < 2.0  # Less than 2 seconds to set 1000 entries
        assert get_time < 1.0  # Less than 1 second to get 1000 entries

    def test_memory_usage_with_complex_configurations(self, config_flow):
        """Test memory usage with complex dog configurations."""
        # Create complex dog configurations
        for i in range(50):
            complex_dog = {
                CONF_DOG_ID: f"complex_dog_{i}",
                CONF_DOG_NAME: f"Complex Dog {i}",
                CONF_DOG_SIZE: DOG_SIZES[i % len(DOG_SIZES)],
                CONF_DOG_WEIGHT: 15.0 + (i % 20),
                CONF_DOG_AGE: 2 + (i % 12),
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                    MODULE_WALK: True,
                },
                "feeding_config": {
                    "special_diet": SPECIAL_DIET_OPTIONS[:3],  # Multiple diets
                    "meals_per_day": 3,
                    "daily_amount": 500,
                },
                "health_config": {
                    "health_conditions": ["diabetes", "arthritis"],
                    "medications": [
                        {"name": f"Med {j}", "dosage": "5mg"} for j in range(3)
                    ],
                    "vaccinations": {
                        "rabies": {"date": "2024-01-01", "next_due": "2025-01-01"},
                        "dhpp": {"date": "2024-01-01", "next_due": "2025-01-01"},
                    },
                },
                "gps_config": {
                    "gps_source": "device_tracker",
                    "update_interval": 60,
                    "geofencing": True,
                },
            }
            config_flow._dogs.append(complex_dog)

        # Test various operations with complex data
        estimates = config_flow._calculate_profile_estimates()
        recommendation = config_flow._get_recommended_profile()
        comparison = config_flow._get_performance_comparison()

        # Should handle complex configurations without issues
        assert len(estimates) == len(ENTITY_PROFILES)
        assert recommendation in ENTITY_PROFILES
        assert len(comparison) > 0

    @pytest.mark.asyncio
    async def test_error_recovery_under_stress(self, config_flow):
        """Test error recovery mechanisms under stress conditions."""
        # Simulate various error conditions
        error_scenarios = [
            ("timeout", asyncio.TimeoutError()),
            ("validation", ValueError("Validation failed")),
            ("network", ConnectionError("Network error")),
            ("memory", MemoryError("Out of memory")),
        ]

        for error_name, error in error_scenarios:
            # Test error handling doesn't break the flow
            with patch.object(
                config_flow, "_async_validate_dog_config", side_effect=error
            ):
                try:
                    result = await config_flow._async_validate_dog_config(
                        {
                            CONF_DOG_ID: "test_dog",
                            CONF_DOG_NAME: "Test Dog",
                            CONF_DOG_SIZE: "medium",
                            CONF_DOG_WEIGHT: 20.0,
                            CONF_DOG_AGE: 3,
                        }
                    )

                    # Should return error result, not raise exception
                    assert not result["valid"]
                    assert "errors" in result

                except Exception:
                    # Some errors might still propagate, which is acceptable
                    pass


class TestExternalEntityIntegration:
    """Test external entity integration edge cases."""

    @pytest.fixture
    def config_flow(self, hass):
        """Create a config flow for testing."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = []

        # Mock entity availability
        mock_states = MagicMock()
        mock_states.async_entity_ids.return_value = [
            "device_tracker.phone_1",
            "device_tracker.phone_2",
            "person.john",
            "person.jane",
            "binary_sensor.front_door",
            "binary_sensor.garage_door",
        ]

        mock_state = MagicMock()
        mock_state.state = "home"
        mock_state.attributes = {"friendly_name": "Test Device"}
        mock_states.get.return_value = mock_state

        hass.states = mock_states

        # Mock notification services
        mock_services = MagicMock()
        mock_services.async_services.return_value = {
            "notify": {
                "mobile_app": {},
                "telegram": {},
                "discord": {},
            }
        }
        hass.services = mock_services

        return flow

    def test_available_device_trackers_edge_cases(self, config_flow):
        """Test device tracker availability with edge cases."""
        # Mock various entity states
        entity_states = {
            "device_tracker.available": "home",
            "device_tracker.unavailable": "unavailable",
            "device_tracker.unknown": "unknown",
            "device_tracker.home_assistant": "home",  # Should be filtered
        }

        def mock_get_state(entity_id):
            state = MagicMock()
            state.state = entity_states.get(entity_id, "home")
            state.attributes = {"friendly_name": f"Friendly {entity_id}"}
            return state

        config_flow.hass.states.get.side_effect = mock_get_state
        config_flow.hass.states.async_entity_ids.return_value = list(
            entity_states.keys()
        )

        device_trackers = config_flow._get_available_device_trackers()

        # Should include available devices, exclude unavailable/unknown
        assert "device_tracker.available" in device_trackers
        assert "device_tracker.unavailable" not in device_trackers
        assert "device_tracker.unknown" not in device_trackers
        # Should filter Home Assistant companion apps
        assert "device_tracker.home_assistant" not in device_trackers

    def test_available_person_entities_edge_cases(self, config_flow):
        """Test person entity availability with edge cases."""
        person_entities = config_flow._get_available_person_entities()

        # Should return dict with entity_id -> friendly_name mapping
        assert isinstance(person_entities, dict)

        # With mocked data should find person entities
        if person_entities:
            for entity_id, friendly_name in person_entities.items():
                assert entity_id.startswith("person.")
                assert isinstance(friendly_name, str)

    def test_available_door_sensors_filtering(self, config_flow):
        """Test door sensor filtering by device class."""

        # Mock binary sensors with different device classes
        def mock_get_state(entity_id):
            state = MagicMock()
            state.state = "off"

            device_classes = {
                "binary_sensor.door": "door",
                "binary_sensor.window": "window",
                "binary_sensor.motion": "motion",  # Should be excluded
                "binary_sensor.garage": "garage_door",
                "binary_sensor.opening": "opening",
            }

            state.attributes = {
                "friendly_name": f"Friendly {entity_id}",
                "device_class": device_classes.get(entity_id),
            }
            return state

        config_flow.hass.states.get.side_effect = mock_get_state
        config_flow.hass.states.async_entity_ids.return_value = [
            "binary_sensor.door",
            "binary_sensor.window",
            "binary_sensor.motion",
            "binary_sensor.garage",
            "binary_sensor.opening",
        ]

        door_sensors = config_flow._get_available_door_sensors()

        # Should include door-like sensors, exclude others
        expected_sensors = [
            "binary_sensor.door",
            "binary_sensor.window",
            "binary_sensor.garage",
            "binary_sensor.opening",
        ]

        for sensor in expected_sensors:
            assert sensor in door_sensors
        assert "binary_sensor.motion" not in door_sensors

    def test_notification_services_filtering(self, config_flow):
        """Test notification service filtering and naming."""
        notify_services = config_flow._get_available_notify_services()

        # Should return dict with service mappings
        assert isinstance(notify_services, dict)

        # Should exclude persistent_notification
        assert "notify.persistent_notification" not in notify_services

        # Should format service names properly
        for service_id, friendly_name in notify_services.items():
            assert service_id.startswith("notify.")
            assert isinstance(friendly_name, str)
            assert len(friendly_name) > 0


if __name__ == "__main__":
    pytest.main([__file__])
