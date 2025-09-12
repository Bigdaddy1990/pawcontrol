"""Tests for utility functions."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.pawcontrol.const import DOG_SIZES
from custom_components.pawcontrol.utils import (
    async_batch_validate,
    async_calculate_haversine_distance,
    async_validate_coordinates,
    calculate_bmr_advanced,
    calculate_trend_advanced,
    deep_merge_dicts_optimized,
    format_distance_adaptive,
    format_duration_optimized,
    format_time_ago_smart,
    is_within_time_range_enhanced,
    performance_monitor,
    safe_convert,
    sanitize_filename_advanced,
    validate_dog_id,
    validate_enum_value,
    validate_weight_enhanced,
)


class TestValidationFunctions:
    """Test validation utility functions."""

    def test_validate_dog_id_valid(self):
        """Test valid dog IDs."""
        valid_ids = ["dog1", "my_dog", "test_123", "ABC_123", "a", "x" * 50]

        for dog_id in valid_ids:
            is_valid, error = validate_dog_id(dog_id)
            assert is_valid, f"Expected {dog_id} to be valid, got error: {error}"
            assert error is None

    def test_validate_dog_id_invalid(self):
        """Test invalid dog IDs."""
        invalid_cases = [
            ("", "Dog ID cannot be empty"),
            (
                "dog with spaces",
                "Dog ID can only contain letters, numbers, and underscores",
            ),
            (
                "dog-with-dashes",
                "Dog ID can only contain letters, numbers, and underscores",
            ),
            ("dog!@#", "Dog ID can only contain letters, numbers, and underscores"),
            ("x" * 51, "Dog ID must be between 1 and 50 characters"),
            (123, "Dog ID must be a string"),
            (None, "Dog ID must be a string"),
        ]

        for dog_id, expected_error_type in invalid_cases:
            is_valid, error = validate_dog_id(dog_id)
            assert not is_valid, f"Expected {dog_id} to be invalid"
            assert error is not None
            assert expected_error_type in error

    @pytest.mark.asyncio
    async def test_async_validate_coordinates_valid(self):
        """Test valid coordinates."""
        valid_coords = [
            (0.0, 0.0),
            (90.0, 180.0),
            (-90.0, -180.0),
            (52.5200, 13.4050),  # Berlin
            (-33.8688, 151.2093),  # Sydney
        ]

        for lat, lon in valid_coords:
            is_valid, error = await async_validate_coordinates(lat, lon)
            assert is_valid, f"Expected ({lat}, {lon}) to be valid, got error: {error}"
            assert error is None

    @pytest.mark.asyncio
    async def test_async_validate_coordinates_invalid(self):
        """Test invalid coordinates."""
        invalid_coords = [
            (91.0, 0.0, "Latitude must be between -90 and 90"),
            (-91.0, 0.0, "Latitude must be between -90 and 90"),
            (0.0, 181.0, "Longitude must be between -180 and 180"),
            (0.0, -181.0, "Longitude must be between -180 and 180"),
            (float("nan"), 0.0, "Coordinates cannot be NaN"),
            (0.0, float("inf"), "Coordinates cannot be infinite"),
            ("invalid", 0.0, "Invalid coordinate format"),
            (0.0, "invalid", "Invalid coordinate format"),
        ]

        for lat, lon, expected_error_type in invalid_coords:
            is_valid, error = await async_validate_coordinates(lat, lon)
            assert not is_valid, f"Expected ({lat}, {lon}) to be invalid"
            assert error is not None
            assert expected_error_type in error

    def test_validate_weight_enhanced_valid(self):
        """Test valid weight values."""
        valid_weights = [
            (10.0, None, None),
            (25.5, "medium", 5),
            (2.0, "toy", 1),
            (70.0, "giant", 8),
        ]

        for weight, size, age in valid_weights:
            is_valid, error = validate_weight_enhanced(weight, size, age)
            assert is_valid, f"Expected weight {weight} to be valid, got error: {error}"
            assert error is None

    def test_validate_weight_enhanced_invalid(self):
        """Test invalid weight values."""
        invalid_weights = [
            (0.0, None, None, "Weight must be positive"),
            (-5.0, None, None, "Weight must be positive"),
            (float("nan"), None, None, "Weight must be a valid number"),
            (250.0, None, None, "Weight must be between"),
            (50.0, "toy", None, "toy dogs should weigh between"),
            ("invalid", None, None, "Invalid weight format"),
        ]

        for weight, size, age, expected_error_type in invalid_weights:
            is_valid, error = validate_weight_enhanced(weight, size, age)
            assert not is_valid, f"Expected weight {weight} to be invalid"
            assert error is not None
            assert expected_error_type in error

    def test_validate_enum_value_valid(self):
        """Test valid enum values."""
        valid_values = ("small", "medium", "large")

        for value in valid_values:
            is_valid, error = validate_enum_value(value, valid_values, "size")
            assert is_valid, f"Expected {value} to be valid"
            assert error is None

    def test_validate_enum_value_invalid(self):
        """Test invalid enum values."""
        valid_values = ("small", "medium", "large")
        invalid_cases = [
            ("invalid", "size must be one of"),
            (123, "size must be a string"),
            ("", "size must be one of"),
        ]

        for value, expected_error_type in invalid_cases:
            is_valid, error = validate_enum_value(value, valid_values, "size")
            assert not is_valid, f"Expected {value} to be invalid"
            assert error is not None
            assert expected_error_type in error


class TestFormattingFunctions:
    """Test formatting utility functions."""

    def test_format_duration_optimized(self):
        """Test duration formatting."""
        test_cases = [
            (0, "0 seconds"),
            (30, "30 seconds"),
            (60, "1 minute"),
            (90, "1 minute and 30 seconds"),
            (3600, "1 hour"),
            (3661, "1 hour and 1 minute"),
            (7200, "2 hours"),
            (86400, "1 day"),
            (90061, "1 day and 1 hour"),
        ]

        for seconds, expected in test_cases:
            result = format_duration_optimized(seconds)
            assert result == expected, (
                f"Expected {expected}, got {result} for {seconds} seconds"
            )

    def test_format_duration_optimized_precision(self):
        """Test duration formatting with different precision."""
        # Test rounded precision
        result = format_duration_optimized(3661, precision="rounded")
        assert "1 hour" in result

        # Test exact precision
        result = format_duration_optimized(3661, precision="exact")
        assert "1 hour" in result and "1 minute" in result

    def test_format_distance_adaptive_metric(self):
        """Test distance formatting in metric units."""
        test_cases = [
            (0.0, "0 m"),
            (5.5, "5.5 m"),
            (15.0, "15 m"),
            (999.0, "999 m"),
            (1000.0, "1.0 km"),
            (1500.0, "1.5 km"),
            (15000.0, "15 km"),
        ]

        for meters, expected in test_cases:
            result = format_distance_adaptive(meters, "metric")
            assert result == expected, (
                f"Expected {expected}, got {result} for {meters}m"
            )

    def test_format_distance_adaptive_imperial(self):
        """Test distance formatting in imperial units."""
        result = format_distance_adaptive(1000.0, "imperial")
        assert "ft" in result or "mi" in result

        result = format_distance_adaptive(10000.0, "imperial")
        assert "mi" in result

    def test_format_time_ago_smart(self):
        """Test smart time ago formatting."""
        now = datetime(2025, 1, 15, 12, 0, 0)

        test_cases = [
            (now - timedelta(seconds=30), "just now"),
            (now - timedelta(minutes=5), "5 minutes ago"),
            (now - timedelta(hours=2), "2 hours ago"),
            (now - timedelta(hours=3, minutes=30), "3h 30m ago"),
            (now - timedelta(days=1), "1 day ago"),
            (now - timedelta(days=7), "1 week ago"),
            (now - timedelta(days=35), "1 month ago"),
            (now - timedelta(days=400), "1 year ago"),
            (now + timedelta(minutes=5), "in the future"),
        ]

        for timestamp, expected in test_cases:
            result = format_time_ago_smart(timestamp, now)
            assert result == expected, f"Expected {expected}, got {result}"


class TestCalculationFunctions:
    """Test calculation utility functions."""

    @pytest.mark.asyncio
    async def test_async_calculate_haversine_distance(self):
        """Test haversine distance calculation."""
        # Test same point
        distance = await async_calculate_haversine_distance((0.0, 0.0), (0.0, 0.0))
        assert distance == 0.0

        # Test known distance (approximate)
        # Berlin to Munich is roughly 504 km
        berlin = (52.5200, 13.4050)
        munich = (48.1351, 11.5820)
        distance = await async_calculate_haversine_distance(berlin, munich)
        assert 500000 < distance < 510000  # Allow some margin for rounding

    def test_calculate_bmr_advanced(self):
        """Test BMR calculation."""
        # Test typical dog
        bmr = calculate_bmr_advanced(25.0, 5, "normal", 1.0, True)
        assert isinstance(bmr, float)
        assert bmr > 0
        assert 800 < bmr < 2000  # Reasonable range for 25kg dog

        # Test puppy (higher metabolic rate)
        puppy_bmr = calculate_bmr_advanced(10.0, 0.5, "normal", 1.0, True)
        adult_bmr = calculate_bmr_advanced(10.0, 5, "normal", 1.0, True)
        assert puppy_bmr > adult_bmr

        # Test activity levels
        low_bmr = calculate_bmr_advanced(25.0, 5, "low", 1.0, True)
        high_bmr = calculate_bmr_advanced(25.0, 5, "high", 1.0, True)
        assert high_bmr > low_bmr

    def test_calculate_trend_advanced(self):
        """Test trend calculation."""
        # Test increasing trend
        increasing_values = (1.0, 2.0, 3.0, 4.0, 5.0)
        result = calculate_trend_advanced(increasing_values)
        assert result["direction"] == "increasing"
        assert result["strength"] > 0

        # Test decreasing trend
        decreasing_values = (5.0, 4.0, 3.0, 2.0, 1.0)
        result = calculate_trend_advanced(decreasing_values)
        assert result["direction"] == "decreasing"
        assert result["strength"] > 0

        # Test stable trend
        stable_values = (3.0, 3.0, 3.0, 3.0, 3.0)
        result = calculate_trend_advanced(stable_values)
        assert result["direction"] == "stable"
        assert result["strength"] == 0

        # Test insufficient data
        result = calculate_trend_advanced((1.0,))
        assert result["direction"] == "unknown"


class TestUtilityFunctions:
    """Test general utility functions."""

    def test_safe_convert_int(self):
        """Test safe integer conversion."""
        assert safe_convert("123", int, 0) == 123
        assert safe_convert("invalid", int, 0) == 0
        assert safe_convert(12.5, int, 0) == 12
        assert safe_convert(None, int, 99) == 99

    def test_safe_convert_float(self):
        """Test safe float conversion."""
        assert safe_convert("12.5", float, 0.0) == 12.5
        assert safe_convert("invalid", float, 0.0) == 0.0
        assert safe_convert(123, float, 0.0) == 123.0
        assert safe_convert(None, float, 99.9) == 99.9

    def test_safe_convert_str(self):
        """Test safe string conversion."""
        assert safe_convert(123, str, "") == "123"
        assert safe_convert(None, str, "default") == "default"
        assert safe_convert("test", str, "") == "test"

    def test_safe_convert_bool(self):
        """Test safe boolean conversion."""
        assert safe_convert("true", bool, False)
        assert not safe_convert("false", bool, True)
        assert safe_convert("yes", bool, False)
        assert safe_convert("1", bool, False)
        assert safe_convert("invalid", bool, True)
        assert not safe_convert(0, bool, True)

    def test_deep_merge_dicts_optimized(self):
        """Test deep dictionary merging."""
        dict1 = {"a": 1, "b": {"c": 2}}
        dict2 = {"b": {"d": 3}, "e": 4}

        result = deep_merge_dicts_optimized(dict1, dict2)

        expected = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
        assert result == expected

        # Test max depth protection
        deep_dict1 = {"a": {"b": {"c": {"d": 1}}}}
        deep_dict2 = {"a": {"b": {"c": {"e": 2}}}}

        result = deep_merge_dicts_optimized(deep_dict1, deep_dict2, max_depth=2)
        assert "a" in result
        assert "b" in result["a"]

    def test_is_within_time_range_enhanced(self):
        """Test time range checking."""
        current_time = time(10, 30)  # 10:30 AM

        # Test same day range
        is_within, error = is_within_time_range_enhanced(current_time, "09:00", "12:00")
        assert is_within
        assert error is None

        # Test outside range
        is_within, error = is_within_time_range_enhanced(current_time, "13:00", "15:00")
        assert not is_within
        assert error is None

        # Test overnight range
        is_within, error = is_within_time_range_enhanced(time(23, 30), "22:00", "02:00")
        assert is_within
        assert error is None

        # Test invalid time format
        is_within, error = is_within_time_range_enhanced(
            current_time, "invalid", "12:00"
        )
        assert not is_within
        assert error is not None

    def test_sanitize_filename_advanced(self):
        """Test filename sanitization."""
        test_cases = [
            ("normal_file.txt", "normal_file.txt"),
            ("file with spaces.txt", "file_with_spaces.txt"),
            ('file<>:"/\\|?*.txt', "file_________.txt"),
            ("file___multiple___underscores.txt", "file_multiple_underscores.txt"),
            ("", "file"),
            ("   .txt   ", "file.txt"),
            ("a" * 300 + ".txt", "a" * 251 + ".txt"),  # Length limit
        ]

        for input_name, expected in test_cases:
            result = sanitize_filename_advanced(input_name)
            assert result == expected, (
                f"Expected {expected}, got {result} for input {input_name}"
            )
            assert len(result) <= 255

    @pytest.mark.asyncio
    async def test_async_batch_validate(self):
        """Test batch validation."""

        def simple_validator(value):
            return (
                isinstance(value, int),
                "Must be integer" if not isinstance(value, int) else None,
            )

        items = [
            (1, simple_validator),
            (2, simple_validator),
            ("invalid", simple_validator),
            (4, simple_validator),
        ]

        results = await async_batch_validate(items)

        assert len(results) == 4
        assert results[0][0]  # Valid
        assert results[1][0]  # Valid
        assert not results[2][0]  # Invalid
        assert results[3][0]  # Valid

    @pytest.mark.asyncio
    async def test_async_batch_validate_fail_fast(self):
        """Test batch validation with fail_fast."""

        def simple_validator(value):
            return (value > 0, "Must be positive" if value <= 0 else None)

        items = [
            (1, simple_validator),
            (-1, simple_validator),  # This should cause fail_fast to stop
            (3, simple_validator),
        ]

        results = await async_batch_validate(items, fail_fast=True)

        # Should stop after first failure
        assert len(results) == 2
        assert results[0][0]
        assert not results[1][0]


class TestPerformanceMonitor:
    """Test performance monitoring decorator."""

    @pytest.mark.asyncio
    async def test_performance_monitor_async_success(self):
        """Test performance monitor with successful async function."""

        @performance_monitor(timeout=1.0)
        async def test_func():
            await asyncio.sleep(0.1)
            return "success"

        result = await test_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_performance_monitor_async_timeout(self):
        """Test performance monitor with timeout."""

        @performance_monitor(timeout=0.1)
        async def test_func():
            await asyncio.sleep(0.2)
            return "should not reach"

        with pytest.raises(asyncio.TimeoutError):
            await test_func()

    def test_performance_monitor_sync(self):
        """Test performance monitor with sync function."""

        @performance_monitor(timeout=1.0)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"


class TestLegacyCompatibility:
    """Test legacy compatibility functions."""

    def test_legacy_safe_functions(self):
        """Test legacy safe conversion functions."""
        from custom_components.pawcontrol.utils import safe_float, safe_int, safe_str

        assert safe_float("12.5", 0.0) == 12.5
        assert safe_float("invalid", 0.0) == 0.0

        assert safe_int("123", 0) == 123
        assert safe_int("invalid", 0) == 0

        assert safe_str(123, "") == "123"
        assert safe_str(None, "default") == "default"

    def test_legacy_deep_merge(self):
        """Test legacy deep merge function."""
        from custom_components.pawcontrol.utils import deep_merge_dicts

        dict1 = {"a": 1}
        dict2 = {"b": 2}
        result = deep_merge_dicts(dict1, dict2)

        assert result == {"a": 1, "b": 2}
