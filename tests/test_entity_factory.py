"""Tests for the entity factory with profile-based optimization.

Tests the entity factory functionality including profile management,
entity count estimation, and platform prioritization.

Home Assistant: 2025.9.1+
Python: 3.13+
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES, EntityFactory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator for testing."""
    coordinator = Mock(spec=PawControlCoordinator)
    coordinator.hass = Mock(spec=HomeAssistant)
    coordinator.config_entry = Mock()
    return coordinator


@pytest.fixture
def entity_factory(mock_coordinator):
    """Create an entity factory instance for testing."""
    return EntityFactory(mock_coordinator)


class TestEntityProfiles:
    """Test entity profile definitions and management."""

    def test_all_profiles_defined(self):
        """Test that all expected profiles are defined."""
        expected_profiles = [
            "basic",
            "standard",
            "advanced",
            "gps_focus",
            "health_focus",
        ]
        assert all(profile in ENTITY_PROFILES for profile in expected_profiles)

    def test_profile_structure(self):
        """Test that each profile has required fields."""
        required_fields = [
            "name",
            "description",
            "max_entities",
            "performance_impact",
            "recommended_for",
        ]

        for profile_name, profile_data in ENTITY_PROFILES.items():
            for field in required_fields:
                assert field in profile_data, (
                    f"Profile {profile_name} missing field {field}"
                )

    def test_profile_max_entities(self):
        """Test that max entities are within expected ranges."""
        assert ENTITY_PROFILES["basic"]["max_entities"] == 8
        assert ENTITY_PROFILES["standard"]["max_entities"] == 12
        assert ENTITY_PROFILES["advanced"]["max_entities"] == 18
        assert ENTITY_PROFILES["gps_focus"]["max_entities"] == 10
        assert ENTITY_PROFILES["health_focus"]["max_entities"] == 10

    def test_profile_platforms(self):
        """Test that each profile has appropriate platforms defined."""
        # Basic should have minimal platforms
        assert len(ENTITY_PROFILES["basic"]["platforms"]) == 3

        # Advanced should have all platforms
        assert len(ENTITY_PROFILES["advanced"]["platforms"]) == len(Platform)

        # GPS focus should include device tracker
        assert Platform.DEVICE_TRACKER in ENTITY_PROFILES["gps_focus"]["platforms"]

        # Health focus should include date and text for medication tracking
        assert Platform.DATE in ENTITY_PROFILES["health_focus"]["platforms"]
        assert Platform.TEXT in ENTITY_PROFILES["health_focus"]["platforms"]


class TestEntityFactory:
    """Test entity factory functionality."""

    def test_estimate_entity_count_basic_profile(self, entity_factory):
        """Test entity count estimation for basic profile."""
        modules = {
            "feeding": True,
            "walk": True,
            "gps": False,
            "health": False,
        }

        count = entity_factory.estimate_entity_count("basic", modules)
        assert count <= 8  # Should not exceed basic profile limit
        assert count >= 3  # Should have at least core entities

    def test_estimate_entity_count_advanced_profile(self, entity_factory):
        """Test entity count estimation for advanced profile with all modules."""
        modules = {
            "feeding": True,
            "walk": True,
            "gps": True,
            "health": True,
            "notifications": True,
            "dashboard": True,
            "visitor": True,
            "medication": True,
            "training": True,
        }

        count = entity_factory.estimate_entity_count("advanced", modules)
        assert count == 18  # Should reach advanced profile limit

    def test_estimate_entity_count_gps_focus(self, entity_factory):
        """Test entity count estimation for GPS focus profile."""
        modules = {
            "gps": True,
            "walk": True,
            "feeding": False,
            "health": False,
        }

        count = entity_factory.estimate_entity_count("gps_focus", modules)
        assert count <= 10  # Should not exceed GPS focus limit
        assert count >= 7  # Should have GPS-related entities

    def test_estimate_entity_count_invalid_profile(self, entity_factory):
        """Test entity count estimation with invalid profile falls back to standard."""
        modules = {"feeding": True}

        count = entity_factory.estimate_entity_count("invalid_profile", modules)
        assert count > 0  # Should still return a valid count

    def test_should_create_entity_critical_priority(self, entity_factory):
        """Test that critical priority entities are always created."""
        # Critical entities (priority >= 9) should always be created
        should_create = entity_factory.should_create_entity(
            "basic", "sensor", "feeding", priority=9
        )
        assert should_create is True

        should_create = entity_factory.should_create_entity(
            "basic", "exotic_type", "unknown_module", priority=10
        )
        assert should_create is True

    def test_should_create_entity_basic_profile(self, entity_factory):
        """Test entity creation rules for basic profile."""
        # Essential entities should be created
        assert (
            entity_factory.should_create_entity(
                "basic", "sensor", "feeding", priority=5
            )
            is True
        )

        # Low priority entities should not be created
        assert (
            entity_factory.should_create_entity(
                "basic", "text", "notifications", priority=2
            )
            is False
        )

        # Non-essential modules should not create entities
        assert (
            entity_factory.should_create_entity(
                "basic", "switch", "visitor", priority=5
            )
            is False
        )

    def test_should_create_entity_gps_focus(self, entity_factory):
        """Test entity creation rules for GPS focus profile."""
        # GPS-related entities should be prioritized
        assert (
            entity_factory.should_create_entity(
                "gps_focus", "device_tracker", "gps", priority=5
            )
            is True
        )

        assert (
            entity_factory.should_create_entity(
                "gps_focus", "sensor", "walk", priority=5
            )
            is True
        )

        # Non-GPS entities with low priority should not be created
        assert (
            entity_factory.should_create_entity(
                "gps_focus", "text", "medication", priority=4
            )
            is False
        )

    def test_should_create_entity_health_focus(self, entity_factory):
        """Test entity creation rules for health focus profile."""
        # Health-related entities should be prioritized
        assert (
            entity_factory.should_create_entity(
                "health_focus", "sensor", "health", priority=5
            )
            is True
        )

        assert (
            entity_factory.should_create_entity(
                "health_focus", "number", "feeding", priority=5
            )
            is True
        )

        assert (
            entity_factory.should_create_entity(
                "health_focus", "date", "medication", priority=5
            )
            is True
        )

    def test_should_create_entity_advanced_profile(self, entity_factory):
        """Test entity creation rules for advanced profile."""
        # Almost all entities with priority >= 3 should be created
        assert (
            entity_factory.should_create_entity(
                "advanced", "sensor", "any_module", priority=3
            )
            is True
        )

        assert (
            entity_factory.should_create_entity(
                "advanced", "switch", "any_module", priority=4
            )
            is True
        )

        # Very low priority might still be excluded
        assert (
            entity_factory.should_create_entity(
                "advanced", "text", "any_module", priority=1
            )
            is False
        )

    def test_get_platform_priority_basic(self, entity_factory):
        """Test platform loading priority for basic profile."""
        assert entity_factory.get_platform_priority(Platform.SENSOR, "basic") == 1
        assert entity_factory.get_platform_priority(Platform.BUTTON, "basic") == 2
        assert (
            entity_factory.get_platform_priority(Platform.BINARY_SENSOR, "basic") == 3
        )

        # Platforms not in basic profile should have low priority
        assert (
            entity_factory.get_platform_priority(Platform.DEVICE_TRACKER, "basic") == 99
        )

    def test_get_platform_priority_gps_focus(self, entity_factory):
        """Test platform loading priority for GPS focus profile."""
        assert (
            entity_factory.get_platform_priority(Platform.DEVICE_TRACKER, "gps_focus")
            == 1
        )
        assert entity_factory.get_platform_priority(Platform.SENSOR, "gps_focus") == 2

        # Non-GPS platforms should have lower priority
        assert entity_factory.get_platform_priority(Platform.DATE, "gps_focus") == 99

    def test_create_entity_config_filtered(self, entity_factory):
        """Test that entity config is filtered based on profile."""
        # Low priority entity in basic profile should return None
        config = entity_factory.create_entity_config(
            "dog_1", "text", "notifications", "basic", priority=2
        )
        assert config is None

        # High priority entity should return config
        config = entity_factory.create_entity_config(
            "dog_1", "sensor", "feeding", "basic", priority=7
        )
        assert config is not None
        assert config["dog_id"] == "dog_1"
        assert config["entity_type"] == "sensor"
        assert config["module"] == "feeding"
        assert config["profile"] == "basic"

    def test_create_entity_config_with_kwargs(self, entity_factory):
        """Test entity config creation with additional kwargs."""
        config = entity_factory.create_entity_config(
            "dog_1",
            "sensor",
            "health",
            "standard",
            priority=5,
            name="Health Status",
            icon="mdi:heart",
            unit_of_measurement="bpm",
        )

        assert config is not None
        assert config["name"] == "Health Status"
        assert config["icon"] == "mdi:heart"
        assert config["unit_of_measurement"] == "bpm"
        assert "priority" not in config  # Priority should be removed from kwargs

    def test_get_profile_info(self, entity_factory):
        """Test getting profile information."""
        info = entity_factory.get_profile_info("basic")
        assert info["name"] == "Basic (8 entities)"
        assert info["max_entities"] == 8

        # Invalid profile should return standard
        info = entity_factory.get_profile_info("invalid")
        assert info["name"] == "Standard (12 entities)"

    def test_get_available_profiles(self, entity_factory):
        """Test getting list of available profiles."""
        profiles = entity_factory.get_available_profiles()
        assert "basic" in profiles
        assert "standard" in profiles
        assert "advanced" in profiles
        assert "gps_focus" in profiles
        assert "health_focus" in profiles
        assert len(profiles) == 5


class TestEntityReduction:
    """Test entity count reduction calculations."""

    def test_entity_reduction_basic_vs_legacy(self, entity_factory):
        """Test entity reduction from legacy (54) to basic profile."""
        modules = {"feeding": True, "walk": True}
        basic_count = entity_factory.estimate_entity_count("basic", modules)

        legacy_count = 54
        reduction_percent = (1 - basic_count / legacy_count) * 100

        assert reduction_percent >= 70  # Should achieve at least 70% reduction
        assert reduction_percent <= 90  # Should not exceed 90% reduction

    def test_entity_reduction_standard_vs_legacy(self, entity_factory):
        """Test entity reduction from legacy to standard profile."""
        modules = {
            "feeding": True,
            "walk": True,
            "gps": True,
            "health": True,
        }
        standard_count = entity_factory.estimate_entity_count("standard", modules)

        legacy_count = 54
        reduction_percent = (1 - standard_count / legacy_count) * 100

        assert reduction_percent >= 60  # Should achieve at least 60% reduction
        assert reduction_percent <= 80  # Should not exceed 80% reduction

    def test_entity_reduction_advanced_vs_legacy(self, entity_factory):
        """Test entity reduction from legacy to advanced profile."""
        modules = {
            "feeding": True,
            "walk": True,
            "gps": True,
            "health": True,
            "notifications": True,
            "medication": True,
        }
        advanced_count = entity_factory.estimate_entity_count("advanced", modules)

        legacy_count = 54
        reduction_percent = (1 - advanced_count / legacy_count) * 100

        assert reduction_percent >= 50  # Should still achieve 50% reduction
        assert reduction_percent <= 70  # Should not exceed 70% reduction


class TestProfileMigration:
    """Test profile migration scenarios."""

    def test_profile_upgrade_path(self, entity_factory):
        """Test recommended upgrade path from basic to advanced."""
        # Start with basic profile
        basic_modules = {"feeding": True, "walk": True}
        basic_count = entity_factory.estimate_entity_count("basic", basic_modules)

        # Add GPS module - should consider GPS focus
        gps_modules = {**basic_modules, "gps": True}
        gps_count = entity_factory.estimate_entity_count("gps_focus", gps_modules)

        # Add health module - should consider standard
        standard_modules = {**gps_modules, "health": True}
        standard_count = entity_factory.estimate_entity_count(
            "standard", standard_modules
        )

        # Add all modules - should use advanced
        all_modules = {
            **standard_modules,
            "notifications": True,
            "medication": True,
            "training": True,
        }
        advanced_count = entity_factory.estimate_entity_count("advanced", all_modules)

        # Verify progressive increase
        assert basic_count < gps_count < standard_count < advanced_count
        assert basic_count <= 8
        assert advanced_count <= 18

    def test_profile_specialization(self, entity_factory):
        """Test that specialized profiles are more efficient for their use case."""
        # GPS-focused setup
        gps_modules = {"gps": True, "walk": True}

        gps_focus_count = entity_factory.estimate_entity_count("gps_focus", gps_modules)
        standard_count = entity_factory.estimate_entity_count("standard", gps_modules)

        # GPS focus should be more efficient for GPS-only setup
        assert gps_focus_count <= standard_count

        # Health-focused setup
        health_modules = {"health": True, "medication": True, "feeding": True}

        health_focus_count = entity_factory.estimate_entity_count(
            "health_focus", health_modules
        )
        standard_count = entity_factory.estimate_entity_count(
            "standard", health_modules
        )

        # Health focus should be optimized for health monitoring
        assert health_focus_count <= standard_count
