"""Comprehensive tests for Entity Profile System in PawControl integration.

Tests cover all profile types, performance validation, and multi-dog scenarios
for entity count optimization and performance tuning.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES, EntityFactory
from homeassistant.const import Platform


class TestEntityProfiles:
    """Test Entity Profile System functionality and performance."""

    @pytest.fixture
    def entity_factory(self) -> EntityFactory:
        """Create EntityFactory instance for testing."""
        return EntityFactory(coordinator=None)  # No coordinator needed for testing

    @pytest.fixture
    def sample_modules_basic(self) -> dict[str, bool]:
        """Basic module configuration."""
        return {
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": False,
            "notifications": True,
            "dashboard": False,
            "visitor": False,
            "medication": False,
            "training": False,
            "grooming": False,
        }

    @pytest.fixture
    def sample_modules_full(self) -> dict[str, bool]:
        """Full module configuration."""
        return {
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": True,
            "notifications": True,
            "dashboard": True,
            "visitor": True,
            "medication": True,
            "training": True,
            "grooming": True,
        }

    @pytest.fixture
    def sample_modules_gps(self) -> dict[str, bool]:
        """GPS-focused module configuration."""
        return {
            "feeding": True,
            "walk": True,
            "health": False,
            "gps": True,
            "notifications": True,
            "dashboard": False,
            "visitor": True,
            "medication": False,
            "training": False,
            "grooming": False,
        }

    def test_all_profiles_available(self, entity_factory: EntityFactory) -> None:
        """Test that all expected profiles are available."""
        expected_profiles = [
            "basic",
            "standard",
            "advanced",
            "gps_focus",
            "health_focus",
        ]
        available_profiles = entity_factory.get_available_profiles()

        assert len(available_profiles) == len(expected_profiles)
        for profile in expected_profiles:
            assert profile in available_profiles

    def test_profile_info_structure(self, entity_factory: EntityFactory) -> None:
        """Test that profile information contains required fields."""
        for profile in entity_factory.get_available_profiles():
            info = entity_factory.get_profile_info(profile)

            # Required fields
            assert "name" in info
            assert "description" in info
            assert "max_entities" in info
            assert "performance_impact" in info
            assert "recommended_for" in info
            assert "platforms" in info
            assert "priority_threshold" in info

            # Value validation
            assert isinstance(info["max_entities"], int)
            assert info["max_entities"] > 0
            assert info["performance_impact"] in ["minimal", "low", "medium"]
            assert isinstance(info["platforms"], list | tuple)
            assert isinstance(info["priority_threshold"], int)

    @pytest.mark.parametrize(
        "profile,expected_max",
        [
            ("basic", 8),
            ("standard", 12),
            ("advanced", 18),
            ("gps_focus", 10),
            ("health_focus", 10),
        ],
    )
    def test_profile_entity_limits(
        self, entity_factory: EntityFactory, profile: str, expected_max: int
    ) -> None:
        """Test that profiles have correct entity limits."""
        info = entity_factory.get_profile_info(profile)
        assert info["max_entities"] == expected_max

    def test_entity_count_estimation_basic_profile(
        self, entity_factory: EntityFactory, sample_modules_basic: dict[str, bool]
    ) -> None:
        """Test entity count estimation for basic profile."""
        count = entity_factory.estimate_entity_count("basic", sample_modules_basic)

        # Basic profile should be conservative
        assert count >= 5  # Minimum essential entities
        assert count <= 8  # Profile limit
        assert isinstance(count, int)

    def test_entity_count_estimation_standard_profile(
        self, entity_factory: EntityFactory, sample_modules_basic: dict[str, bool]
    ) -> None:
        """Test entity count estimation for standard profile."""
        count = entity_factory.estimate_entity_count("standard", sample_modules_basic)

        # Standard profile should be balanced
        assert count >= 8  # More than basic
        assert count <= 12  # Profile limit
        assert isinstance(count, int)

    def test_entity_count_estimation_advanced_profile(
        self, entity_factory: EntityFactory, sample_modules_full: dict[str, bool]
    ) -> None:
        """Test entity count estimation for advanced profile."""
        count = entity_factory.estimate_entity_count("advanced", sample_modules_full)

        # Advanced profile should allow more entities
        assert count >= 12  # More than standard
        assert count <= 18  # Profile limit
        assert isinstance(count, int)

    def test_entity_count_scaling_with_modules(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test that entity count scales with enabled modules."""
        minimal_modules = {"feeding": True, "walk": False, "health": False}
        many_modules = {
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": True,
            "notifications": True,
        }

        count_minimal = entity_factory.estimate_entity_count(
            "standard", minimal_modules
        )
        count_many = entity_factory.estimate_entity_count("standard", many_modules)

        # More modules should result in more entities
        assert count_many > count_minimal

    def test_profile_specific_optimizations(
        self, entity_factory: EntityFactory, sample_modules_gps: dict[str, bool]
    ) -> None:
        """Test that GPS focus profile optimizes for GPS modules."""
        gps_count = entity_factory.estimate_entity_count(
            "gps_focus", sample_modules_gps
        )
        standard_count = entity_factory.estimate_entity_count(
            "standard", sample_modules_gps
        )

        # GPS focus should be efficient for GPS-heavy configurations
        assert gps_count <= 10  # Within profile limit
        assert isinstance(gps_count, int)
        # GPS focus might be more efficient than standard for this config
        assert gps_count <= standard_count + 2  # Allow some variance

    def test_should_create_entity_priority_filtering(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test entity creation filtering based on priority."""
        # High priority should always be created (critical entities)
        assert entity_factory.should_create_entity(
            "basic", "sensor", "feeding", priority=9
        )

        # Low priority should be filtered out in basic profile
        assert not entity_factory.should_create_entity(
            "basic", "sensor", "feeding", priority=3
        )

        # Same low priority should be created in advanced profile
        assert entity_factory.should_create_entity(
            "advanced", "sensor", "feeding", priority=3
        )

    def test_should_create_entity_platform_filtering(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test entity creation filtering based on supported platforms."""
        # Basic profile doesn't support all platforms
        basic_info = entity_factory.get_profile_info("basic")
        basic_platforms = basic_info["platforms"]

        if Platform.DATETIME not in basic_platforms:
            assert not entity_factory.should_create_entity(
                "basic", "datetime", "health", priority=8
            )

        # Advanced profile supports all platforms
        assert entity_factory.should_create_entity(
            "advanced", "datetime", "health", priority=8
        )

    def test_platform_priority_ordering(self, entity_factory: EntityFactory) -> None:
        """Test that platform priorities are correctly ordered."""
        priorities = {}
        for profile in ["basic", "standard", "advanced"]:
            for platform in [Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR]:
                priorities[(profile, platform)] = entity_factory.get_platform_priority(
                    platform, profile
                )

        # Sensor should generally have high priority (low number)
        for profile in ["basic", "standard", "advanced"]:
            sensor_priority = priorities[(profile, Platform.SENSOR)]
            assert sensor_priority <= 3  # High priority (low number)

    def test_gps_focus_platform_priorities(self, entity_factory: EntityFactory) -> None:
        """Test that GPS focus profile prioritizes GPS-related platforms."""
        device_tracker_priority = entity_factory.get_platform_priority(
            Platform.DEVICE_TRACKER, "gps_focus"
        )
        sensor_priority = entity_factory.get_platform_priority(
            Platform.SENSOR, "gps_focus"
        )

        # Device tracker should have highest priority in GPS focus
        assert device_tracker_priority == 1
        assert sensor_priority <= 3  # Also high priority

    def test_health_focus_platform_priorities(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test that health focus profile prioritizes health-related platforms."""
        sensor_priority = entity_factory.get_platform_priority(
            Platform.SENSOR, "health_focus"
        )
        number_priority = entity_factory.get_platform_priority(
            Platform.NUMBER, "health_focus"
        )
        date_priority = entity_factory.get_platform_priority(
            Platform.DATE, "health_focus"
        )

        # Health-related platforms should have high priority
        assert sensor_priority <= 2
        assert number_priority <= 3
        assert date_priority <= 4

    def test_entity_config_creation(self, entity_factory: EntityFactory) -> None:
        """Test entity configuration creation."""
        config = entity_factory.create_entity_config(
            dog_id="buddy",
            entity_type="sensor",
            module="feeding",
            profile="standard",
            priority=6,
            additional_param="test_value",
        )

        assert config is not None
        assert config["dog_id"] == "buddy"
        assert config["entity_type"] == "sensor"
        assert config["module"] == "feeding"
        assert config["profile"] == "standard"
        assert config["priority"] == 6
        assert config["additional_param"] == "test_value"
        assert "performance_impact" in config

    def test_entity_config_filtered_out(self, entity_factory: EntityFactory) -> None:
        """Test that low-priority entities are filtered out."""
        config = entity_factory.create_entity_config(
            dog_id="buddy",
            entity_type="sensor",
            module="feeding",
            profile="basic",
            priority=2,  # Too low for basic profile
        )

        assert config is None  # Should be filtered out

    def test_profile_validation_for_modules(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test profile validation for module combinations."""
        # GPS focus should be suitable for GPS-heavy modules
        gps_modules = {
            "feeding": True,
            "walk": True,
            "gps": True,
            "visitor": True,
            "health": False,
        }
        assert entity_factory.validate_profile_for_modules("gps_focus", gps_modules)

        # Health focus should be suitable for health-heavy modules
        health_modules = {
            "feeding": True,
            "health": True,
            "medication": True,
            "gps": False,
            "walk": False,
        }
        assert entity_factory.validate_profile_for_modules(
            "health_focus", health_modules
        )

    def test_invalid_profile_handling(self, entity_factory: EntityFactory) -> None:
        """Test handling of invalid profile names."""
        modules = {"feeding": True, "walk": True}

        # Should fallback to standard profile
        count = entity_factory.estimate_entity_count("invalid_profile", modules)
        standard_count = entity_factory.estimate_entity_count("standard", modules)
        assert count == standard_count

        # Should return False for validation
        assert not entity_factory.validate_profile_for_modules(
            "invalid_profile", modules
        )

    def test_invalid_modules_handling(self, entity_factory: EntityFactory) -> None:
        """Test handling of invalid module configurations."""
        # None modules
        count = entity_factory.estimate_entity_count("standard", None)  # type: ignore[arg-type]
        assert isinstance(count, int)
        assert count > 0  # Should use defaults

        # Invalid module dict
        invalid_modules = {"feeding": "yes", "walk": 1}  # type: ignore[dict-item]
        count = entity_factory.estimate_entity_count("standard", invalid_modules)
        assert isinstance(count, int)
        assert count > 0  # Should use defaults

    def test_performance_metrics_calculation(
        self, entity_factory: EntityFactory, sample_modules_basic: dict[str, bool]
    ) -> None:
        """Test performance metrics calculation."""
        metrics = entity_factory.get_performance_metrics(
            "standard", sample_modules_basic
        )

        assert "profile" in metrics
        assert "estimated_entities" in metrics
        assert "max_entities" in metrics
        assert "performance_impact" in metrics
        assert "utilization_percentage" in metrics
        assert "enabled_modules" in metrics
        assert "total_modules" in metrics

        assert metrics["profile"] == "standard"
        assert isinstance(metrics["estimated_entities"], int)
        assert isinstance(metrics["max_entities"], int)
        assert metrics["performance_impact"] in ["minimal", "low", "medium"]
        assert 0 <= metrics["utilization_percentage"] <= 100
        assert metrics["enabled_modules"] > 0
        assert metrics["total_modules"] >= metrics["enabled_modules"]

    def test_performance_scaling_single_dog(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test performance characteristics for single dog."""
        modules = {"feeding": True, "walk": True, "health": True, "gps": True}

        basic_metrics = entity_factory.get_performance_metrics("basic", modules)
        standard_metrics = entity_factory.get_performance_metrics("standard", modules)
        advanced_metrics = entity_factory.get_performance_metrics("advanced", modules)

        # Entity count should scale with profile sophistication
        assert (
            basic_metrics["estimated_entities"]
            <= standard_metrics["estimated_entities"]
        )
        assert (
            standard_metrics["estimated_entities"]
            <= advanced_metrics["estimated_entities"]
        )

        # Performance impact should be consistent with design
        assert basic_metrics["performance_impact"] == "minimal"
        assert standard_metrics["performance_impact"] == "low"
        assert advanced_metrics["performance_impact"] == "medium"

    def test_entity_estimate_uses_cache(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test that cached entity estimates are reused for identical inputs."""

        modules = {"feeding": True, "walk": True, "health": False}
        first_estimate = entity_factory.estimate_entity_count("standard", modules)
        assert first_estimate > 0

        with patch.object(
            entity_factory,
            "_compute_entity_estimate",
            side_effect=AssertionError("cache miss"),
        ):
            second_estimate = entity_factory.estimate_entity_count("standard", modules)

        assert second_estimate == first_estimate


class TestEntityProfilesEdgeCases:
    """Test edge cases and stress scenarios for Entity Profile System."""

    @pytest.fixture
    def entity_factory(self) -> EntityFactory:
        """Create EntityFactory instance for testing."""
        return EntityFactory(coordinator=None)

    def test_empty_modules(self, entity_factory: EntityFactory) -> None:
        """Test behavior with empty module configuration."""
        empty_modules = {}
        count = entity_factory.estimate_entity_count("standard", empty_modules)

        # Should still create base entities
        assert count > 0
        assert isinstance(count, int)

    def test_all_modules_disabled(self, entity_factory: EntityFactory) -> None:
        """Test behavior with all modules disabled."""
        disabled_modules = {
            module: False
            for module in [
                "feeding",
                "walk",
                "health",
                "gps",
                "notifications",
                "dashboard",
                "visitor",
                "medication",
                "training",
                "grooming",
            ]
        }
        count = entity_factory.estimate_entity_count("standard", disabled_modules)

        # Should create minimal base entities
        assert count >= 3  # Base entities
        assert count <= 6  # Very limited set

    def test_single_module_enabled(self, entity_factory: EntityFactory) -> None:
        """Test behavior with only one module enabled."""
        for module in ["feeding", "walk", "health", "gps"]:
            single_module = {
                "feeding": module == "feeding",
                "walk": module == "walk",
                "health": module == "health",
                "gps": module == "gps",
            }
            count = entity_factory.estimate_entity_count("standard", single_module)

            # Should create base entities plus module entities
            assert count >= 4  # Base + module entities
            assert isinstance(count, int)

    def test_profile_consistency_across_calls(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test that repeated calls return consistent results."""
        modules = {"feeding": True, "walk": True, "health": True}

        # Call multiple times
        counts = [
            entity_factory.estimate_entity_count("standard", modules) for _ in range(5)
        ]

        # All results should be identical
        assert all(count == counts[0] for count in counts)

    def test_module_permutations_scaling(self, entity_factory: EntityFactory) -> None:
        """Test that entity count scales predictably with module permutations."""
        base_modules = {"feeding": True}
        extended_modules = {"feeding": True, "walk": True}
        full_modules = {"feeding": True, "walk": True, "health": True, "gps": True}

        base_count = entity_factory.estimate_entity_count("standard", base_modules)
        extended_count = entity_factory.estimate_entity_count(
            "standard", extended_modules
        )
        full_count = entity_factory.estimate_entity_count("standard", full_modules)

        # Should scale predictably
        assert base_count < extended_count
        assert extended_count < full_count

    def test_profile_boundary_conditions(self, entity_factory: EntityFactory) -> None:
        """Test profiles at their maximum entity limits."""
        # Create module configuration that would exceed limits
        max_modules = {
            module: True
            for module in [
                "feeding",
                "walk",
                "health",
                "gps",
                "notifications",
                "dashboard",
                "visitor",
                "medication",
                "training",
                "grooming",
            ]
        }

        for profile in entity_factory.get_available_profiles():
            count = entity_factory.estimate_entity_count(profile, max_modules)
            max_entities = entity_factory.get_profile_info(profile)["max_entities"]

            # Should never exceed profile limit
            assert count <= max_entities

    def test_platform_priority_edge_cases(self, entity_factory: EntityFactory) -> None:
        """Test platform priority handling for edge cases."""
        # Test with invalid platform
        priority = entity_factory.get_platform_priority(
            Platform.SENSOR, "invalid_profile"
        )
        assert isinstance(priority, int)
        assert priority > 0

        # Test with all profiles
        for profile in entity_factory.get_available_profiles():
            for platform in [Platform.SENSOR, Platform.BUTTON]:
                priority = entity_factory.get_platform_priority(platform, profile)
                assert isinstance(priority, int)
                assert 1 <= priority <= 99  # Valid priority range

    def test_memory_efficiency_large_configs(
        self, entity_factory: EntityFactory
    ) -> None:
        """Test memory efficiency with large configurations."""
        # Create large module configuration
        large_modules = {f"module_{i}": i % 2 == 0 for i in range(50)}

        # Should handle gracefully without memory issues
        count = entity_factory.estimate_entity_count("standard", large_modules)
        assert isinstance(count, int)
        assert count > 0

    def test_concurrent_access_simulation(self, entity_factory: EntityFactory) -> None:
        """Simulate concurrent access patterns."""

        # Simulate multiple dogs accessing factory simultaneously
        results = []
        for dog_id in [f"dog_{i}" for i in range(10)]:
            config = entity_factory.create_entity_config(
                dog_id=dog_id,
                entity_type="sensor",
                module="feeding",
                profile="standard",
                priority=5,
            )
            results.append(config)

        # All should succeed
        assert all(config is not None for config in results)
        # Each should have unique dog_id
        dog_ids = {config["dog_id"] for config in results if config}
        assert len(dog_ids) == 10
