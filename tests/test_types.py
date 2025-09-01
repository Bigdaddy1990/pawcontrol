"""Tests for type definitions and validation."""

from datetime import datetime

import pytest
from custom_components.pawcontrol.types import (
    VALID_ACTIVITY_LEVELS,
    VALID_DOG_SIZES,
    VALID_FOOD_TYPES,
    VALID_GEOFENCE_TYPES,
    VALID_GPS_SOURCES,
    VALID_HEALTH_STATUS,
    VALID_MEAL_TYPES,
    VALID_MOOD_OPTIONS,
    VALID_NOTIFICATION_PRIORITIES,
    DailyStats,
    DogConfigData,
    DogProfile,
    FeedingData,
    GeofenceZone,
    GPSLocation,
    HealthData,
    NotificationData,
    WalkData,
    is_dog_config_valid,
    is_feeding_data_valid,
    is_gps_location_valid,
)
from homeassistant.config_entries import ConfigEntry


class TestDataStructures:
    """Test data structure classes."""

    def test_feeding_data_creation(self):
        """Test FeedingData dataclass creation."""
        feeding = FeedingData(
            meal_type="breakfast",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=datetime.now(),
            notes="Test feeding",
            calories=300.0,
        )

        assert feeding.meal_type == "breakfast"
        assert feeding.portion_size == 200.0
        assert feeding.food_type == "dry_food"
        assert feeding.notes == "Test feeding"
        assert feeding.calories == 300.0
        assert isinstance(feeding.timestamp, datetime)

    def test_feeding_data_defaults(self):
        """Test FeedingData with default values."""
        feeding = FeedingData(
            meal_type="lunch",
            portion_size=150.0,
            food_type="wet_food",
            timestamp=datetime.now(),
        )

        assert feeding.notes == ""
        assert feeding.logged_by == ""
        assert feeding.calories is None

    def test_walk_data_creation(self):
        """Test WalkData dataclass creation."""
        start_time = datetime.now()

        walk = WalkData(
            start_time=start_time,
            label="Morning walk",
            location="Park",
        )

        assert walk.start_time == start_time
        assert walk.label == "Morning walk"
        assert walk.location == "Park"
        assert walk.end_time is None
        assert walk.duration is None
        assert walk.distance is None
        assert walk.route == []

    def test_health_data_creation(self):
        """Test HealthData dataclass creation."""
        timestamp = datetime.now()

        health = HealthData(
            timestamp=timestamp,
            weight=25.5,
            temperature=38.5,
            mood="happy",
            activity_level="normal",
        )

        assert health.timestamp == timestamp
        assert health.weight == 25.5
        assert health.temperature == 38.5
        assert health.mood == "happy"
        assert health.activity_level == "normal"
        assert health.health_status == ""
        assert health.symptoms == ""

    def test_gps_location_creation(self):
        """Test GPSLocation dataclass creation."""
        timestamp = datetime.now()

        location = GPSLocation(
            latitude=52.5200,
            longitude=13.4050,
            accuracy=10.0,
            timestamp=timestamp,
            source="test",
        )

        assert location.latitude == 52.5200
        assert location.longitude == 13.4050
        assert location.accuracy == 10.0
        assert location.timestamp == timestamp
        assert location.source == "test"
        assert location.altitude is None

    def test_geofence_zone_creation(self):
        """Test GeofenceZone dataclass creation."""
        zone = GeofenceZone(
            name="Home Zone",
            latitude=52.5200,
            longitude=13.4050,
            radius=100.0,
            zone_type="safe_zone",
        )

        assert zone.name == "Home Zone"
        assert zone.latitude == 52.5200
        assert zone.longitude == 13.4050
        assert zone.radius == 100.0
        assert zone.zone_type == "safe_zone"
        assert zone.notifications
        assert zone.auto_actions == []

    def test_notification_data_creation(self):
        """Test NotificationData dataclass creation."""
        timestamp = datetime.now()

        notification = NotificationData(
            title="Test Notification",
            message="This is a test",
            priority="high",
            timestamp=timestamp,
        )

        assert notification.title == "Test Notification"
        assert notification.message == "This is a test"
        assert notification.priority == "high"
        assert notification.timestamp == timestamp
        assert notification.channel == "mobile"
        assert not notification.persistent
        assert notification.actions == []

    def test_daily_stats_creation(self):
        """Test DailyStats dataclass creation."""
        date = datetime.now()

        stats = DailyStats(
            date=date,
            feedings_count=3,
            total_food_amount=600.0,
            walks_count=2,
            total_walk_time=3600,
            total_walk_distance=5000.0,
        )

        assert stats.date == date
        assert stats.feedings_count == 3
        assert stats.total_food_amount == 600.0
        assert stats.walks_count == 2
        assert stats.total_walk_time == 3600
        assert stats.total_walk_distance == 5000.0
        assert stats.health_logs_count == 0
        assert stats.last_feeding_time is None

    def test_dog_profile_creation(self):
        """Test DogProfile dataclass creation."""
        dog_config = {
            "dog_id": "test_dog",
            "dog_name": "Test Dog",
            "dog_breed": "Test Breed",
        }

        daily_stats = DailyStats(date=datetime.now())

        profile = DogProfile(
            dog_id="test_dog",
            dog_name="Test Dog",
            config=dog_config,
            daily_stats=daily_stats,
        )

        assert profile.dog_id == "test_dog"
        assert profile.dog_name == "Test Dog"
        assert profile.config == dog_config
        assert profile.daily_stats == daily_stats
        assert profile.current_walk is None
        assert profile.last_location is None
        assert not profile.is_visitor_mode


class TestTypeGuards:
    """Test type guard functions."""

    def test_is_dog_config_valid_true(self):
        """Test valid dog configurations."""
        valid_configs = [
            {
                "dog_id": "test_dog",
                "dog_name": "Test Dog",
            },
            {
                "dog_id": "my_dog_123",
                "dog_name": "My Dog",
                "dog_breed": "Golden Retriever",
                "dog_age": 5,
            },
        ]

        for config in valid_configs:
            assert is_dog_config_valid(config), f"Expected {config} to be valid"

    def test_is_dog_config_valid_false(self):
        """Test invalid dog configurations."""
        invalid_configs = [
            {},  # Empty
            {"dog_id": "test"},  # Missing dog_name
            {"dog_name": "Test"},  # Missing dog_id
            {"dog_id": "", "dog_name": "Test"},  # Empty dog_id
            {"dog_id": "test", "dog_name": ""},  # Empty dog_name
            {"dog_id": 123, "dog_name": "Test"},  # Wrong type for dog_id
            {"dog_id": "test", "dog_name": 123},  # Wrong type for dog_name
            "not_a_dict",  # Not a dict
            None,  # None
        ]

        for config in invalid_configs:
            assert not is_dog_config_valid(config), f"Expected {config} to be invalid"

    def test_is_gps_location_valid_true(self):
        """Test valid GPS locations."""
        valid_locations = [
            {"latitude": 0.0, "longitude": 0.0},
            {"latitude": 52.5200, "longitude": 13.4050},
            {"latitude": -33.8688, "longitude": 151.2093},
            {"latitude": 90.0, "longitude": 180.0},
            {"latitude": -90.0, "longitude": -180.0},
        ]

        for location in valid_locations:
            assert is_gps_location_valid(location), f"Expected {location} to be valid"

    def test_is_gps_location_valid_false(self):
        """Test invalid GPS locations."""
        invalid_locations = [
            {},  # Empty
            {"latitude": 0.0},  # Missing longitude
            {"longitude": 0.0},  # Missing latitude
            {"latitude": 91.0, "longitude": 0.0},  # Invalid latitude
            {"latitude": 0.0, "longitude": 181.0},  # Invalid longitude
            {"latitude": "invalid", "longitude": 0.0},  # Wrong type
            {"latitude": 0.0, "longitude": "invalid"},  # Wrong type
            "not_a_dict",  # Not a dict
            None,  # None
        ]

        for location in invalid_locations:
            assert not is_gps_location_valid(location), (
                f"Expected {location} to be invalid"
            )

    def test_is_feeding_data_valid_true(self):
        """Test valid feeding data."""
        valid_data = [
            {"meal_type": "breakfast", "portion_size": 200.0},
            {"meal_type": "lunch", "portion_size": 150},
            {"meal_type": "dinner", "portion_size": 0},  # Zero is valid
            {"meal_type": "snack", "portion_size": 50.5},
        ]

        for data in valid_data:
            assert is_feeding_data_valid(data), f"Expected {data} to be valid"

    def test_is_feeding_data_valid_false(self):
        """Test invalid feeding data."""
        invalid_data = [
            {},  # Empty
            {"meal_type": "breakfast"},  # Missing portion_size
            {"portion_size": 200.0},  # Missing meal_type
            {"meal_type": 123, "portion_size": 200.0},  # Wrong type for meal_type
            {
                "meal_type": "breakfast",
                "portion_size": "invalid",
            },  # Wrong type for portion_size
            {"meal_type": "breakfast", "portion_size": -10.0},  # Negative portion_size
            "not_a_dict",  # Not a dict
            None,  # None
        ]

        for data in invalid_data:
            assert not is_feeding_data_valid(data), f"Expected {data} to be invalid"


class TestValidationConstants:
    """Test validation constant sets."""

    def test_valid_meal_types(self):
        """Test meal types validation set."""
        assert isinstance(VALID_MEAL_TYPES, set)
        assert "breakfast" in VALID_MEAL_TYPES
        assert "lunch" in VALID_MEAL_TYPES
        assert "dinner" in VALID_MEAL_TYPES
        assert "snack" in VALID_MEAL_TYPES
        assert len(VALID_MEAL_TYPES) > 0

    def test_valid_food_types(self):
        """Test food types validation set."""
        assert isinstance(VALID_FOOD_TYPES, set)
        assert "dry_food" in VALID_FOOD_TYPES
        assert "wet_food" in VALID_FOOD_TYPES
        assert "barf" in VALID_FOOD_TYPES
        assert len(VALID_FOOD_TYPES) > 0

    def test_valid_dog_sizes(self):
        """Test dog sizes validation set."""
        assert isinstance(VALID_DOG_SIZES, set)
        assert "toy" in VALID_DOG_SIZES
        assert "small" in VALID_DOG_SIZES
        assert "medium" in VALID_DOG_SIZES
        assert "large" in VALID_DOG_SIZES
        assert "giant" in VALID_DOG_SIZES
        assert len(VALID_DOG_SIZES) == 5

    def test_valid_health_status(self):
        """Test health status validation set."""
        assert isinstance(VALID_HEALTH_STATUS, set)
        assert "excellent" in VALID_HEALTH_STATUS
        assert "good" in VALID_HEALTH_STATUS
        assert "normal" in VALID_HEALTH_STATUS
        assert "sick" in VALID_HEALTH_STATUS
        assert len(VALID_HEALTH_STATUS) > 0

    def test_valid_mood_options(self):
        """Test mood options validation set."""
        assert isinstance(VALID_MOOD_OPTIONS, set)
        assert "happy" in VALID_MOOD_OPTIONS
        assert "neutral" in VALID_MOOD_OPTIONS
        assert "sad" in VALID_MOOD_OPTIONS
        assert len(VALID_MOOD_OPTIONS) > 0

    def test_valid_activity_levels(self):
        """Test activity levels validation set."""
        assert isinstance(VALID_ACTIVITY_LEVELS, set)
        assert "very_low" in VALID_ACTIVITY_LEVELS
        assert "low" in VALID_ACTIVITY_LEVELS
        assert "normal" in VALID_ACTIVITY_LEVELS
        assert "high" in VALID_ACTIVITY_LEVELS
        assert "very_high" in VALID_ACTIVITY_LEVELS
        assert len(VALID_ACTIVITY_LEVELS) == 5

    def test_valid_geofence_types(self):
        """Test geofence types validation set."""
        assert isinstance(VALID_GEOFENCE_TYPES, set)
        assert "safe_zone" in VALID_GEOFENCE_TYPES
        assert "restricted_area" in VALID_GEOFENCE_TYPES
        assert "point_of_interest" in VALID_GEOFENCE_TYPES
        assert len(VALID_GEOFENCE_TYPES) > 0

    def test_valid_gps_sources(self):
        """Test GPS sources validation set."""
        assert isinstance(VALID_GPS_SOURCES, set)
        assert "manual" in VALID_GPS_SOURCES
        assert "device_tracker" in VALID_GPS_SOURCES
        assert "smartphone" in VALID_GPS_SOURCES
        assert len(VALID_GPS_SOURCES) > 0

    def test_valid_notification_priorities(self):
        """Test notification priorities validation set."""
        assert isinstance(VALID_NOTIFICATION_PRIORITIES, set)
        assert "low" in VALID_NOTIFICATION_PRIORITIES
        assert "normal" in VALID_NOTIFICATION_PRIORITIES
        assert "high" in VALID_NOTIFICATION_PRIORITIES
        assert "urgent" in VALID_NOTIFICATION_PRIORITIES
        assert len(VALID_NOTIFICATION_PRIORITIES) == 4

    def test_validation_constants_are_sets(self):
        """Test that all validation constants are sets for fast lookup."""
        validation_constants = [
            VALID_MEAL_TYPES,
            VALID_FOOD_TYPES,
            VALID_DOG_SIZES,
            VALID_HEALTH_STATUS,
            VALID_MOOD_OPTIONS,
            VALID_ACTIVITY_LEVELS,
            VALID_GEOFENCE_TYPES,
            VALID_GPS_SOURCES,
            VALID_NOTIFICATION_PRIORITIES,
        ]

        for constant in validation_constants:
            assert isinstance(constant, set), f"Expected set, got {type(constant)}"
            assert len(constant) > 0, "Validation set should not be empty"

    def test_no_empty_strings_in_validation_sets(self):
        """Test that validation sets don't contain empty strings."""
        validation_constants = [
            VALID_MEAL_TYPES,
            VALID_FOOD_TYPES,
            VALID_DOG_SIZES,
            VALID_HEALTH_STATUS,
            VALID_MOOD_OPTIONS,
            VALID_ACTIVITY_LEVELS,
            VALID_GEOFENCE_TYPES,
            VALID_GPS_SOURCES,
            VALID_NOTIFICATION_PRIORITIES,
        ]

        for constant in validation_constants:
            for value in constant:
                assert isinstance(value, str), f"Expected string, got {type(value)}"
                assert len(value) > 0, "Validation values should not be empty"
                assert value.strip() == value, (
                    "Validation values should not have leading/trailing whitespace"
                )


class TestTypeAnnotations:
    """Test that type annotations work correctly."""

    def test_dog_config_data_typing(self):
        """Test DogConfigData typing."""
        # This should not raise any mypy errors when type checking is enabled
        config: DogConfigData = {
            "dog_id": "test_dog",
            "dog_name": "Test Dog",
        }

        assert config["dog_id"] == "test_dog"
        assert config["dog_name"] == "Test Dog"

    def test_optional_fields_typing(self):
        """Test optional fields in TypedDict."""
        config: DogConfigData = {
            "dog_id": "test_dog",
            "dog_name": "Test Dog",
            "dog_breed": "Golden Retriever",  # Optional field
            "dog_age": 5,  # Optional field
        }

        assert config.get("dog_breed") == "Golden Retriever"
        assert config.get("dog_age") == 5
        assert config.get("non_existent") is None


class TestDataStructureDefaults:
    """Test default values in data structures."""

    def test_daily_stats_defaults(self):
        """Test DailyStats default values."""
        stats = DailyStats(date=datetime.now())

        assert stats.feedings_count == 0
        assert stats.total_food_amount == 0.0
        assert stats.walks_count == 0
        assert stats.total_walk_time == 0
        assert stats.total_walk_distance == 0.0
        assert stats.health_logs_count == 0
        assert stats.last_feeding_time is None
        assert stats.last_walk_time is None

    def test_dog_profile_defaults(self):
        """Test DogProfile default values."""
        profile = DogProfile(
            dog_id="test",
            dog_name="Test",
            config={},
            daily_stats=DailyStats(date=datetime.now()),
        )

        assert profile.current_walk is None
        assert profile.last_location is None
        assert not profile.is_visitor_mode

    def test_geofence_zone_defaults(self):
        """Test GeofenceZone default values."""
        zone = GeofenceZone(
            name="Test Zone",
            latitude=0.0,
            longitude=0.0,
            radius=100.0,
        )

        assert zone.zone_type == "safe_zone"
        assert zone.notifications
        assert zone.auto_actions == []

    def test_notification_data_defaults(self):
        """Test NotificationData default values."""
        notification = NotificationData(
            title="Test",
            message="Test message",
        )

        assert notification.priority == "normal"
        assert notification.channel == "mobile"
        assert not notification.persistent
        assert notification.actions == []
        assert isinstance(notification.timestamp, datetime)


class TestDataStructureValidation:
    """Test data structure validation edge cases."""

    def test_gps_location_edge_cases(self):
        """Test GPS location validation edge cases."""
        # Test exact boundaries
        assert is_gps_location_valid({"latitude": 90.0, "longitude": 180.0})
        assert is_gps_location_valid({"latitude": -90.0, "longitude": -180.0})

        # Test just outside boundaries
        assert not is_gps_location_valid({"latitude": 90.1, "longitude": 0.0})
        assert not is_gps_location_valid({"latitude": 0.0, "longitude": 180.1})

    def test_feeding_data_edge_cases(self):
        """Test feeding data validation edge cases."""
        # Test zero portion size (should be valid)
        assert is_feeding_data_valid({"meal_type": "snack", "portion_size": 0.0})

        # Test float vs int portion size
        assert is_feeding_data_valid({"meal_type": "snack", "portion_size": 100})
        assert is_feeding_data_valid({"meal_type": "snack", "portion_size": 100.5})

    def test_dog_config_edge_cases(self):
        """Test dog config validation edge cases."""
        # Test with extra fields (should still be valid)
        config = {
            "dog_id": "test",
            "dog_name": "Test",
            "extra_field": "should_be_ignored",
        }
        assert is_dog_config_valid(config)

        # Test with whitespace
        config = {
            "dog_id": "  test  ",  # Should be trimmed by validator if needed
            "dog_name": "  Test  ",
        }
        # This depends on implementation - currently it's valid as strings exist
        assert is_dog_config_valid(config)
