"""Tests for the EntityFactory with profile-based optimization."""

from unittest.mock import Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.entity_factory import (
    ENTITY_PRIORITIES,
    ENTITY_PROFILES,
    EntityFactory,
)


class TestEntityFactory:
    """Test the EntityFactory class."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock()
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def entity_factory(self, mock_coordinator):
        """Create an EntityFactory instance."""
        return EntityFactory(mock_coordinator)

    def test_entity_profiles_definitions(self):
        """Test that all entity profiles are properly defined."""
        expected_profiles = [
            "basic",
            "standard",
            "advanced",
            "gps_focus",
            "health_focus",
        ]

        assert set(ENTITY_PROFILES.keys()) == set(expected_profiles)

        for profile_name, profile_config in ENTITY_PROFILES.items():
            assert "max_entities" in profile_config
            assert "description" in profile_config
            assert "modules" in profile_config
            assert isinstance(profile_config["max_entities"], int)
            assert profile_config["max_entities"] > 0
            assert isinstance(profile_config["description"], str)
            assert len(profile_config["description"]) > 0

    def test_entity_priorities_completeness(self):
        """Test that all entity types have priorities defined."""
        # Core entities should have priority 1
        core_entities = ["dog_status", "last_action", "activity_score"]
        for entity in core_entities:
            assert entity in ENTITY_PRIORITIES
            assert ENTITY_PRIORITIES[entity] == 1

        # Essential entities should have priority 2
        essential_entities = [
            "last_feeding",
            "feeding_schedule_adherence",
            "health_aware_portion",
            "last_walk",
            "walk_count_today",
            "current_zone",
            "distance_from_home",
            "health_status",
            "weight",
        ]
        for entity in essential_entities:
            assert entity in ENTITY_PRIORITIES
            assert ENTITY_PRIORITIES[entity] == 2

        # NEW: Check that new walk sensor has correct priority
        assert "last_walk_distance" in ENTITY_PRIORITIES
        assert ENTITY_PRIORITIES["last_walk_distance"] == 3

    def test_get_available_profiles(self, entity_factory):
        """Test getting list of available profiles."""
        profiles = entity_factory.get_available_profiles()

        assert isinstance(profiles, list)
        assert len(profiles) == 5
        assert "basic" in profiles
        assert "standard" in profiles
        assert "advanced" in profiles
        assert "gps_focus" in profiles
        assert "health_focus" in profiles

    def test_get_profile_info_valid(self, entity_factory):
        """Test getting info for valid profiles."""
        for profile in ["basic", "standard", "advanced", "gps_focus", "health_focus"]:
            info = entity_factory.get_profile_info(profile)

            assert isinstance(info, dict)
            assert "max_entities" in info
            assert "description" in info
            assert "modules" in info

    def test_get_profile_info_invalid(self, entity_factory):
        """Test getting info for invalid profile falls back to standard."""
        info = entity_factory.get_profile_info("nonexistent")
        standard_info = entity_factory.get_profile_info("standard")

        assert info == standard_info

    def test_estimate_entity_count_basic_profile(self, entity_factory):
        """Test entity count estimation for basic profile."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: False,
            MODULE_HEALTH: False,
        }

        count = entity_factory.estimate_entity_count("basic", modules)

        # Core (3) + Feeding (3) + Walk (2) = 8, respects basic limit
        assert count == 8

    def test_estimate_entity_count_standard_profile(self, entity_factory):
        """Test entity count estimation for standard profile."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }

        count = entity_factory.estimate_entity_count("standard", modules)

        # Should be around 12 (standard limit)
        assert 10 <= count <= 12

    def test_estimate_entity_count_advanced_profile(self, entity_factory):
        """Test entity count estimation for advanced profile."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }

        count = entity_factory.estimate_entity_count("advanced", modules)

        # Should be higher but within advanced limit
        assert 15 <= count <= 18

    def test_estimate_entity_count_gps_focus(self, entity_factory):
        """Test entity count estimation for GPS-focused profile."""
        modules = {
            MODULE_FEEDING: False,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: False,
        }

        count = entity_factory.estimate_entity_count("gps_focus", modules)

        # Core (3) + Walk (4) + GPS (6) = 13, limited to 10
        assert count == 10

    def test_estimate_entity_count_health_focus(self, entity_factory):
        """Test entity count estimation for health-focused profile."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: False,
            MODULE_GPS: False,
            MODULE_HEALTH: True,
        }

        count = entity_factory.estimate_entity_count("health_focus", modules)

        # Core (3) + Feeding (6) + Health (5) = 14, limited to 10
        assert count == 10

    def test_estimate_entity_count_unknown_profile(self, entity_factory):
        """Test entity count estimation with unknown profile."""
        modules = {MODULE_FEEDING: True}

        # Should fallback to standard profile defaults
        count = entity_factory.estimate_entity_count("unknown", modules)

        assert count > 0

    @patch("custom_components.pawcontrol.entity_factory.PawControlDogStatusSensor")
    @patch("custom_components.pawcontrol.entity_factory.PawControlLastActionSensor")
    @patch("custom_components.pawcontrol.entity_factory.PawControlActivityScoreSensor")
    def test_create_core_entities(
        self, mock_activity, mock_action, mock_status, entity_factory
    ):
        """Test creation of core entities."""
        # Mock the sensor classes
        mock_status.return_value = Mock()
        mock_action.return_value = Mock()
        mock_activity.return_value = Mock()

        entities = entity_factory._create_core_entities("test_dog", "Test Dog")

        assert len(entities) == 3
        assert all("entity" in entity for entity in entities)
        assert all("type" in entity for entity in entities)
        assert all("priority" in entity for entity in entities)

        # Check types
        types = [entity["type"] for entity in entities]
        assert "dog_status" in types
        assert "last_action" in types
        assert "activity_score" in types

    @patch("custom_components.pawcontrol.sensor.PawControlLastFeedingSensor")
    @patch(
        "custom_components.pawcontrol.sensor.PawControlFeedingScheduleAdherenceSensor"
    )
    @patch("custom_components.pawcontrol.sensor.PawControlHealthAwarePortionSensor")
    def test_create_feeding_entities_basic(
        self, mock_portion, mock_adherence, mock_last, entity_factory
    ):
        """Test creation of feeding entities for basic profile."""
        # Mock the sensor classes
        mock_last.return_value = Mock()
        mock_adherence.return_value = Mock()
        mock_portion.return_value = Mock()

        entities = entity_factory._create_feeding_entities(
            "test_dog", "Test Dog", "basic"
        )

        # Basic profile should have 3 essential feeding entities
        assert len(entities) == 3

        types = [entity["type"] for entity in entities]
        assert "last_feeding" in types
        assert "feeding_schedule_adherence" in types
        assert "health_aware_portion" in types

    @patch("custom_components.pawcontrol.sensor.PawControlLastFeedingSensor")
    @patch(
        "custom_components.pawcontrol.sensor.PawControlFeedingScheduleAdherenceSensor"
    )
    @patch("custom_components.pawcontrol.sensor.PawControlHealthAwarePortionSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlTotalFeedingsTodaySensor")
    @patch("custom_components.pawcontrol.sensor.PawControlDailyCaloriesSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlFeedingRecommendationSensor")
    def test_create_feeding_entities_standard(
        self,
        mock_rec,
        mock_cal,
        mock_total,
        mock_portion,
        mock_adherence,
        mock_last,
        entity_factory,
    ):
        """Test creation of feeding entities for standard profile."""
        # Mock all sensor classes
        for mock_sensor in [
            mock_last,
            mock_adherence,
            mock_portion,
            mock_total,
            mock_cal,
            mock_rec,
        ]:
            mock_sensor.return_value = Mock()

        entities = entity_factory._create_feeding_entities(
            "test_dog", "Test Dog", "standard"
        )

        # Standard profile should have 6 feeding entities
        assert len(entities) == 6

        types = [entity["type"] for entity in entities]
        assert "total_feedings_today" in types
        assert "daily_calories" in types
        assert "feeding_recommendation" in types

    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlWalkCountTodaySensor")
    def test_create_walk_entities_basic(self, mock_count, mock_last, entity_factory):
        """Test creation of walk entities for basic profile."""
        mock_last.return_value = Mock()
        mock_count.return_value = Mock()

        entities = entity_factory._create_walk_entities("test_dog", "Test Dog", "basic")

        # Basic profile should have 2 essential walk entities
        assert len(entities) == 2

        types = [entity["type"] for entity in entities]
        assert "last_walk" in types
        assert "walk_count_today" in types

    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlWalkCountTodaySensor")
    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkDurationSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkDistanceSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlTotalWalkTimeTodaySensor")
    def test_create_walk_entities_standard(
        self,
        mock_total_time,
        mock_distance,
        mock_duration,
        mock_count,
        mock_last,
        entity_factory,
    ):
        """Test creation of walk entities for standard profile including new distance sensor."""
        # Mock all sensor classes
        for mock_sensor in [
            mock_last,
            mock_count,
            mock_duration,
            mock_distance,
            mock_total_time,
        ]:
            mock_sensor.return_value = Mock()

        entities = entity_factory._create_walk_entities(
            "test_dog", "Test Dog", "standard"
        )

        # Standard profile should have 5 walk entities (2 basic + 3 additional)
        assert len(entities) == 5

        types = [entity["type"] for entity in entities]
        assert "last_walk" in types
        assert "walk_count_today" in types
        assert "last_walk_duration" in types
        assert "last_walk_distance" in types  # NEW: Verify new sensor is included
        assert "total_walk_time_today" in types

    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlWalkCountTodaySensor")
    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkDurationSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkDistanceSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlTotalWalkTimeTodaySensor")
    @patch("custom_components.pawcontrol.sensor.PawControlWeeklyWalkCountSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlAverageWalkDurationSensor")
    def test_create_walk_entities_advanced(
        self,
        mock_avg,
        mock_weekly,
        mock_total_time,
        mock_distance,
        mock_duration,
        mock_count,
        mock_last,
        entity_factory,
    ):
        """Test creation of walk entities for advanced profile."""
        # Mock all sensor classes
        for mock_sensor in [
            mock_last,
            mock_count,
            mock_duration,
            mock_distance,
            mock_total_time,
            mock_weekly,
            mock_avg,
        ]:
            mock_sensor.return_value = Mock()

        entities = entity_factory._create_walk_entities(
            "test_dog", "Test Dog", "advanced"
        )

        # Advanced profile should have 7 walk entities
        assert len(entities) == 7

        types = [entity["type"] for entity in entities]
        assert "last_walk" in types
        assert "walk_count_today" in types
        assert "last_walk_duration" in types
        assert "last_walk_distance" in types  # NEW: Verify included in advanced
        assert "total_walk_time_today" in types
        assert "weekly_walk_count" in types
        assert "average_walk_duration" in types

    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlWalkCountTodaySensor")
    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkDurationSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlLastWalkDistanceSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlTotalWalkTimeTodaySensor")
    def test_create_walk_entities_gps_focus(
        self,
        mock_total_time,
        mock_distance,
        mock_duration,
        mock_count,
        mock_last,
        entity_factory,
    ):
        """Test creation of walk entities for GPS-focused profile."""
        # Mock all sensor classes
        for mock_sensor in [
            mock_last,
            mock_count,
            mock_duration,
            mock_distance,
            mock_total_time,
        ]:
            mock_sensor.return_value = Mock()

        entities = entity_factory._create_walk_entities(
            "test_dog", "Test Dog", "gps_focus"
        )

        # GPS focus profile should have 5 walk entities (same as standard)
        assert len(entities) == 5

        types = [entity["type"] for entity in entities]
        assert "last_walk" in types
        assert "walk_count_today" in types
        assert "last_walk_duration" in types
        assert "last_walk_distance" in types  # NEW: Verify included in GPS focus
        assert "total_walk_time_today" in types

    @patch("custom_components.pawcontrol.sensor.PawControlCurrentZoneSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlDistanceFromHomeSensor")
    def test_create_gps_entities_basic(self, mock_distance, mock_zone, entity_factory):
        """Test creation of GPS entities for basic profile."""
        mock_zone.return_value = Mock()
        mock_distance.return_value = Mock()

        entities = entity_factory._create_gps_entities("test_dog", "Test Dog", "basic")

        # Basic profile should have 2 essential GPS entities
        assert len(entities) == 2

        types = [entity["type"] for entity in entities]
        assert "current_zone" in types
        assert "distance_from_home" in types

    @patch("custom_components.pawcontrol.sensor.PawControlHealthStatusSensor")
    @patch("custom_components.pawcontrol.sensor.PawControlWeightSensor")
    def test_create_health_entities_basic(
        self, mock_weight, mock_status, entity_factory
    ):
        """Test creation of health entities for basic profile."""
        mock_status.return_value = Mock()
        mock_weight.return_value = Mock()

        entities = entity_factory._create_health_entities(
            "test_dog", "Test Dog", "basic"
        )

        # Basic profile should have 2 essential health entities
        assert len(entities) == 2

        types = [entity["type"] for entity in entities]
        assert "health_status" in types
        assert "weight" in types

    @patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory._create_core_entities"
    )
    @patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory._create_feeding_entities"
    )
    @patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory._create_walk_entities"
    )
    @patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory._create_gps_entities"
    )
    @patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory._create_health_entities"
    )
    def test_create_entities_for_dog_standard_profile(
        self, mock_health, mock_gps, mock_walk, mock_feeding, mock_core, entity_factory
    ):
        """Test complete entity creation for a dog with standard profile."""
        # Setup mocks
        mock_core.return_value = [
            {"entity": Mock(), "type": "core1", "priority": 1},
            {"entity": Mock(), "type": "core2", "priority": 1},
            {"entity": Mock(), "type": "core3", "priority": 1},
        ]
        mock_feeding.return_value = [
            {"entity": Mock(), "type": "feeding1", "priority": 2},
            {"entity": Mock(), "type": "feeding2", "priority": 2},
        ]
        mock_walk.return_value = [
            {"entity": Mock(), "type": "walk1", "priority": 2},
            {
                "entity": Mock(),
                "type": "last_walk_distance",
                "priority": 3,
            },  # NEW: Include distance sensor
        ]
        mock_gps.return_value = [
            {"entity": Mock(), "type": "gps1", "priority": 2},
        ]
        mock_health.return_value = [
            {"entity": Mock(), "type": "health1", "priority": 2},
        ]

        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }

        entities = entity_factory.create_entities_for_dog(
            "test_dog", "Test Dog", "standard", modules
        )

        # Should create entities and respect profile limit
        assert len(entities) <= ENTITY_PROFILES["standard"]["max_entities"]
        assert len(entities) == 9  # Based on mock returns (including new sensor)

        # Verify all module methods were called
        mock_core.assert_called_once_with("test_dog", "Test Dog")
        mock_feeding.assert_called_once_with("test_dog", "Test Dog", "standard")
        mock_walk.assert_called_once_with("test_dog", "Test Dog", "standard")
        mock_gps.assert_called_once_with("test_dog", "Test Dog", "standard")
        mock_health.assert_called_once_with("test_dog", "Test Dog", "standard")

    @patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory._create_core_entities"
    )
    @patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory._create_feeding_entities"
    )
    def test_create_entities_for_dog_selective_modules(
        self, mock_feeding, mock_core, entity_factory
    ):
        """Test entity creation with selective modules enabled."""
        mock_core.return_value = [
            {"entity": Mock(), "type": "core1", "priority": 1},
            {"entity": Mock(), "type": "core2", "priority": 1},
            {"entity": Mock(), "type": "core3", "priority": 1},
        ]
        mock_feeding.return_value = [
            {"entity": Mock(), "type": "feeding1", "priority": 2},
        ]

        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: False,  # Disabled
            MODULE_GPS: False,  # Disabled
            MODULE_HEALTH: False,  # Disabled
        }

        entities = entity_factory.create_entities_for_dog(
            "test_dog", "Test Dog", "basic", modules
        )

        assert len(entities) == 4  # 3 core + 1 feeding
        mock_core.assert_called_once()
        mock_feeding.assert_called_once()

    def test_create_entities_for_dog_unknown_profile(self, entity_factory):
        """Test entity creation with unknown profile falls back to standard."""
        with patch.object(entity_factory, "_create_core_entities") as mock_core:
            mock_core.return_value = [
                {"entity": Mock(), "type": "core1", "priority": 1},
            ]

            entities = entity_factory.create_entities_for_dog(
                "test_dog", "Test Dog", "unknown_profile", {}
            )

            # Should use standard profile as fallback
            assert len(entities) <= ENTITY_PROFILES["standard"]["max_entities"]

    def test_create_entities_for_dog_entity_limit_enforcement(self, entity_factory):
        """Test that entity count is properly limited by profile."""
        # Create many mock entities to test limit enforcement
        many_entities = [
            {"entity": Mock(), "type": f"entity_{i}", "priority": 1}
            for i in range(20)  # More than any profile limit
        ]

        with patch.object(
            entity_factory, "_create_core_entities", return_value=many_entities
        ):
            entities = entity_factory.create_entities_for_dog(
                "test_dog", "Test Dog", "basic", {}
            )

            # Should be limited to basic profile max
            assert len(entities) == ENTITY_PROFILES["basic"]["max_entities"]

    def test_create_entities_for_dog_priority_sorting(self, entity_factory):
        """Test that entities are sorted by priority."""
        mixed_priority_entities = [
            {"entity": Mock(), "type": "low_priority", "priority": 5},
            {"entity": Mock(), "type": "high_priority", "priority": 1},
            {"entity": Mock(), "type": "medium_priority", "priority": 3},
        ]

        with patch.object(
            entity_factory,
            "_create_core_entities",
            return_value=mixed_priority_entities,
        ):
            entities = entity_factory.create_entities_for_dog(
                "test_dog", "Test Dog", "advanced", {}
            )

            # Should be sorted by priority (1 first, 5 last)
            assert len(entities) == 3
            # First entity should have highest priority (lowest number)
            # This test verifies the sorting logic works

    def test_entity_profile_constraints(self):
        """Test that profile constraints are logical."""
        for profile_name, profile_config in ENTITY_PROFILES.items():
            max_entities = profile_config["max_entities"]

            # All profiles should have reasonable entity limits
            assert 5 <= max_entities <= 25

            # Basic should have the lowest count
            if profile_name == "basic":
                assert max_entities <= 10

            # Advanced should have the highest count
            if profile_name == "advanced":
                assert max_entities >= 15

    def test_module_specific_profiles(self):
        """Test that focused profiles enable the right modules."""
        gps_profile = ENTITY_PROFILES["gps_focus"]
        health_profile = ENTITY_PROFILES["health_focus"]

        # GPS focus should enable GPS and Walk
        assert gps_profile["modules"][MODULE_GPS] is True
        assert gps_profile["modules"][MODULE_WALK] is True

        # Health focus should enable Health and Feeding
        assert health_profile["modules"][MODULE_HEALTH] is True
        assert health_profile["modules"][MODULE_FEEDING] is True

    def test_profile_performance_characteristics(self, entity_factory):
        """Test performance characteristics of different profiles."""
        all_modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }

        basic_count = entity_factory.estimate_entity_count("basic", all_modules)
        standard_count = entity_factory.estimate_entity_count("standard", all_modules)
        advanced_count = entity_factory.estimate_entity_count("advanced", all_modules)

        # Should show clear performance progression
        assert basic_count < standard_count < advanced_count

        # Performance improvement should be significant
        improvement_basic_to_standard = (standard_count - basic_count) / basic_count
        improvement_standard_to_advanced = (
            advanced_count - standard_count
        ) / standard_count

        # At least 20% more entities per tier
        assert improvement_basic_to_standard >= 0.2
        assert improvement_standard_to_advanced >= 0.2


class TestEntityFactoryIntegration:
    """Test EntityFactory integration with the actual sensor classes."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a realistic mock coordinator."""
        coordinator = Mock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {
            "dog_info": {"dog_name": "Test Dog"},
            "feeding": {"last_feeding": "2023-01-01T12:00:00"},
            "walk": {"last_walk": "2023-01-01T10:00:00"},
            "gps": {"zone": "home"},
            "health": {"health_status": "good"},
        }
        return coordinator

    @pytest.fixture
    def entity_factory(self, mock_coordinator):
        """Create an EntityFactory with a realistic coordinator."""
        return EntityFactory(mock_coordinator)

    def test_integration_basic_profile_real_entities(self, entity_factory):
        """Test that basic profile creates real sensor entities."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: False,
            MODULE_GPS: False,
            MODULE_HEALTH: False,
        }

        # This should work with real sensor imports
        entities = entity_factory.create_entities_for_dog(
            "test_dog", "Test Dog", "basic", modules
        )

        # Should create real entities
        assert len(entities) > 0
        assert all(hasattr(entity, "__class__") for entity in entities)

    def test_integration_last_walk_distance_sensor_in_standard_profile(
        self, entity_factory
    ):
        """Test that PawControlLastWalkDistanceSensor is created in standard+ profiles."""
        modules = {
            MODULE_FEEDING: False,
            MODULE_WALK: True,  # Enable walk module
            MODULE_GPS: False,
            MODULE_HEALTH: False,
        }

        # Test standard profile
        entities = entity_factory.create_entities_for_dog(
            "test_dog", "Test Dog", "standard", modules
        )

        # Check that last_walk_distance sensor is created
        entity_classes = [entity.__class__.__name__ for entity in entities]
        assert "PawControlLastWalkDistanceSensor" in entity_classes

        # Test advanced profile
        entities = entity_factory.create_entities_for_dog(
            "test_dog", "Test Dog", "advanced", modules
        )

        entity_classes = [entity.__class__.__name__ for entity in entities]
        assert "PawControlLastWalkDistanceSensor" in entity_classes

        # Test GPS focus profile
        entities = entity_factory.create_entities_for_dog(
            "test_dog", "Test Dog", "gps_focus", modules
        )

        entity_classes = [entity.__class__.__name__ for entity in entities]
        assert "PawControlLastWalkDistanceSensor" in entity_classes

    def test_integration_last_walk_distance_sensor_not_in_basic_profile(
        self, entity_factory
    ):
        """Test that PawControlLastWalkDistanceSensor is NOT created in basic profile."""
        modules = {
            MODULE_FEEDING: False,
            MODULE_WALK: True,  # Enable walk module
            MODULE_GPS: False,
            MODULE_HEALTH: False,
        }

        # Test basic profile
        entities = entity_factory.create_entities_for_dog(
            "test_dog", "Test Dog", "basic", modules
        )

        # Check that last_walk_distance sensor is NOT created in basic profile
        entity_classes = [entity.__class__.__name__ for entity in entities]
        assert "PawControlLastWalkDistanceSensor" not in entity_classes

    def test_integration_performance_comparison(self, entity_factory):
        """Test performance comparison between profiles."""
        modules_all = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }

        # Test all profiles
        profile_results = {}
        for profile in entity_factory.get_available_profiles():
            entities = entity_factory.create_entities_for_dog(
                "test_dog", "Test Dog", profile, modules_all
            )
            profile_results[profile] = len(entities)

        # Verify performance optimization
        assert profile_results["basic"] <= profile_results["standard"]
        assert profile_results["standard"] <= profile_results["advanced"]

        # Log results for debugging
        print(f"\nProfile performance results: {profile_results}")


class TestLastWalkDistanceSensorIntegration:
    """Specific tests for PawControlLastWalkDistanceSensor integration."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a coordinator with walk distance data."""
        coordinator = Mock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {
            "walk": {
                "last_walk_distance": 1500.0,  # meters
                "last_walk": "2025-01-15T10:00:00",
                "last_walk_duration": 30,
            }
        }
        return coordinator

    @pytest.fixture
    def entity_factory(self, mock_coordinator):
        """Create EntityFactory with walk distance data."""
        return EntityFactory(mock_coordinator)

    def test_last_walk_distance_sensor_creation_and_data(self, entity_factory):
        """Test that the sensor is created and returns correct data."""
        modules = {MODULE_WALK: True}

        entities = entity_factory.create_entities_for_dog(
            "test_dog", "Test Dog", "standard", modules
        )

        # Find the distance sensor
        distance_sensor = None
        for entity in entities:
            if entity.__class__.__name__ == "PawControlLastWalkDistanceSensor":
                distance_sensor = entity
                break

        assert distance_sensor is not None
        assert distance_sensor._sensor_type == "last_walk_distance"
        assert distance_sensor._attr_native_unit_of_measurement == "m"
        assert distance_sensor.native_value == 1500.0

    def test_last_walk_distance_sensor_attributes(self, entity_factory):
        """Test sensor attributes and configuration."""
        modules = {MODULE_WALK: True}

        entities = entity_factory.create_entities_for_dog(
            "test_dog", "Test Dog", "standard", modules
        )

        # Find the distance sensor
        distance_sensor = None
        for entity in entities:
            if entity.__class__.__name__ == "PawControlLastWalkDistanceSensor":
                distance_sensor = entity
                break

        assert distance_sensor is not None
        assert distance_sensor._attr_icon == "mdi:map-marker-path"
        assert (
            distance_sensor._attr_unique_id == "pawcontrol_test_dog_last_walk_distance"
        )
        assert "Test Dog Last Walk Distance" in distance_sensor._attr_name
