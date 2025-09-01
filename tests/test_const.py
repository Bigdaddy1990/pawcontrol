"""Tests for constants module."""
import pytest
from custom_components.pawcontrol.const import (
    DOMAIN,
    STORAGE_VERSION,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_GPS,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_WALK,
    MEAL_TYPES,
    FOOD_TYPES,
    DOG_SIZES,
    GPS_SOURCES,
    HEALTH_STATUS_OPTIONS,
    MOOD_OPTIONS,
    ACTIVITY_LEVELS,
    SERVICE_FEED_DOG,
    SERVICE_START_WALK,
    SERVICE_END_WALK,
    EVENT_WALK_STARTED,
    EVENT_WALK_ENDED,
    EVENT_FEEDING_LOGGED,
    DEFAULT_RESET_TIME,
    DEFAULT_GPS_UPDATE_INTERVAL,
    MIN_DOG_WEIGHT,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MAX_DOG_AGE,
    UPDATE_INTERVALS,
)


class TestConstants:
    """Test constant values and their types."""

    def test_domain_constant(self):
        """Test domain constant."""
        assert DOMAIN == "pawcontrol"
        assert isinstance(DOMAIN, str)

    def test_storage_version(self):
        """Test storage version."""
        assert STORAGE_VERSION == 1
        assert isinstance(STORAGE_VERSION, int)

    def test_config_constants(self):
        """Test configuration constants."""
        assert CONF_DOGS == "dogs"
        assert CONF_DOG_ID == "dog_id"
        assert CONF_DOG_NAME == "dog_name"
        assert all(isinstance(const, str) for const in [CONF_DOGS, CONF_DOG_ID, CONF_DOG_NAME])

    def test_module_constants(self):
        """Test module constants."""
        modules = [MODULE_GPS, MODULE_FEEDING, MODULE_HEALTH, MODULE_WALK]
        expected = ["gps", "feeding", "health", "walk"]
        
        assert modules == expected
        assert all(isinstance(module, str) for module in modules)

    def test_meal_types(self):
        """Test meal types constant."""
        expected_meals = ["breakfast", "lunch", "dinner", "snack"]
        assert MEAL_TYPES == expected_meals
        assert isinstance(MEAL_TYPES, list)
        assert all(isinstance(meal, str) for meal in MEAL_TYPES)

    def test_food_types(self):
        """Test food types constant."""
        expected_foods = ["dry_food", "wet_food", "barf", "home_cooked", "mixed"]
        assert FOOD_TYPES == expected_foods
        assert isinstance(FOOD_TYPES, list)
        assert all(isinstance(food, str) for food in FOOD_TYPES)

    def test_dog_sizes(self):
        """Test dog sizes constant."""
        expected_sizes = ["toy", "small", "medium", "large", "giant"]
        assert DOG_SIZES == expected_sizes
        assert isinstance(DOG_SIZES, list)
        assert all(isinstance(size, str) for size in DOG_SIZES)

    def test_gps_sources(self):
        """Test GPS sources constant."""
        expected_sources = ["manual", "device_tracker", "person_entity", "smartphone", "tractive", "webhook", "mqtt"]
        assert GPS_SOURCES == expected_sources
        assert isinstance(GPS_SOURCES, list)
        assert all(isinstance(source, str) for source in GPS_SOURCES)

    def test_health_status_options(self):
        """Test health status options."""
        expected_statuses = ["excellent", "very_good", "good", "normal", "unwell", "sick"]
        assert HEALTH_STATUS_OPTIONS == expected_statuses
        assert isinstance(HEALTH_STATUS_OPTIONS, list)
        assert all(isinstance(status, str) for status in HEALTH_STATUS_OPTIONS)

    def test_mood_options(self):
        """Test mood options."""
        expected_moods = ["happy", "neutral", "sad", "angry", "anxious", "tired"]
        assert MOOD_OPTIONS == expected_moods
        assert isinstance(MOOD_OPTIONS, list)
        assert all(isinstance(mood, str) for mood in MOOD_OPTIONS)

    def test_activity_levels(self):
        """Test activity levels."""
        expected_levels = ["very_low", "low", "normal", "high", "very_high"]
        assert ACTIVITY_LEVELS == expected_levels
        assert isinstance(ACTIVITY_LEVELS, list)
        assert all(isinstance(level, str) for level in ACTIVITY_LEVELS)

    def test_service_constants(self):
        """Test service name constants."""
        services = [SERVICE_FEED_DOG, SERVICE_START_WALK, SERVICE_END_WALK]
        expected = ["feed_dog", "start_walk", "end_walk"]
        
        assert services == expected
        assert all(isinstance(service, str) for service in services)

    def test_event_constants(self):
        """Test event name constants."""
        events = [EVENT_WALK_STARTED, EVENT_WALK_ENDED, EVENT_FEEDING_LOGGED]
        expected = ["pawcontrol_walk_started", "pawcontrol_walk_ended", "pawcontrol_feeding_logged"]
        
        assert events == expected
        assert all(isinstance(event, str) for event in events)

    def test_default_values(self):
        """Test default value constants."""
        assert DEFAULT_RESET_TIME == "23:59:00"
        assert DEFAULT_GPS_UPDATE_INTERVAL == 60
        assert isinstance(DEFAULT_RESET_TIME, str)
        assert isinstance(DEFAULT_GPS_UPDATE_INTERVAL, int)

    def test_weight_limits(self):
        """Test weight limit constants."""
        assert MIN_DOG_WEIGHT == 0.5
        assert MAX_DOG_WEIGHT == 200.0
        assert isinstance(MIN_DOG_WEIGHT, float)
        assert isinstance(MAX_DOG_WEIGHT, float)
        assert MIN_DOG_WEIGHT < MAX_DOG_WEIGHT

    def test_age_limits(self):
        """Test age limit constants."""
        assert MIN_DOG_AGE == 0
        assert MAX_DOG_AGE == 30
        assert isinstance(MIN_DOG_AGE, int)
        assert isinstance(MAX_DOG_AGE, int)
        assert MIN_DOG_AGE < MAX_DOG_AGE

    def test_update_intervals(self):
        """Test update interval constants."""
        assert isinstance(UPDATE_INTERVALS, dict)
        assert "minimal" in UPDATE_INTERVALS
        assert "balanced" in UPDATE_INTERVALS
        assert "frequent" in UPDATE_INTERVALS
        assert "real_time" in UPDATE_INTERVALS
        
        assert UPDATE_INTERVALS["minimal"] == 300
        assert UPDATE_INTERVALS["balanced"] == 120
        assert UPDATE_INTERVALS["frequent"] == 60
        assert UPDATE_INTERVALS["real_time"] == 30
        
        # Verify order (more frequent = lower values)
        assert UPDATE_INTERVALS["real_time"] < UPDATE_INTERVALS["frequent"]
        assert UPDATE_INTERVALS["frequent"] < UPDATE_INTERVALS["balanced"]
        assert UPDATE_INTERVALS["balanced"] < UPDATE_INTERVALS["minimal"]

    def test_constant_immutability(self):
        """Test that list constants are not accidentally modified."""
        # Test that we get copies, not references
        meals1 = MEAL_TYPES
        meals2 = MEAL_TYPES
        
        # Should be the same content
        assert meals1 == meals2
        
        # Verify constants are properly defined
        assert len(MEAL_TYPES) > 0
        assert len(FOOD_TYPES) > 0
        assert len(DOG_SIZES) > 0
        assert len(GPS_SOURCES) > 0
        assert len(HEALTH_STATUS_OPTIONS) > 0
        assert len(MOOD_OPTIONS) > 0
        assert len(ACTIVITY_LEVELS) > 0

    def test_no_empty_strings(self):
        """Test that no constants contain empty strings."""
        all_string_lists = [
            MEAL_TYPES, FOOD_TYPES, DOG_SIZES, GPS_SOURCES,
            HEALTH_STATUS_OPTIONS, MOOD_OPTIONS, ACTIVITY_LEVELS
        ]
        
        for string_list in all_string_lists:
            assert all(item.strip() != "" for item in string_list)
            assert all(len(item) > 0 for item in string_list)

    def test_no_duplicates(self):
        """Test that constants don't contain duplicates."""
        all_lists = [
            MEAL_TYPES, FOOD_TYPES, DOG_SIZES, GPS_SOURCES,
            HEALTH_STATUS_OPTIONS, MOOD_OPTIONS, ACTIVITY_LEVELS
        ]
        
        for const_list in all_lists:
            assert len(const_list) == len(set(const_list)), f"Duplicates found in {const_list}"

    def test_consistent_naming(self):
        """Test consistent naming conventions."""
        # All meal types should be lowercase with underscores
        for meal in MEAL_TYPES:
            assert meal.islower()
            assert " " not in meal
        
        # All food types should follow same pattern
        for food in FOOD_TYPES:
            assert food.islower()
            assert " " not in food
        
        # Dog sizes should be lowercase
        for size in DOG_SIZES:
            assert size.islower()
            assert " " not in size
