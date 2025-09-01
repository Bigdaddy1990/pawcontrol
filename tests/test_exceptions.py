"""Tests for the Paw Control exceptions module."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from custom_components.pawcontrol.exceptions import (
    EXCEPTION_MAP,
    # Specific exceptions
    ConfigurationError,
    DataExportError,
    DataImportError,
    DogNotFoundError,
    ErrorCategory,
    ErrorSeverity,
    GPSError,
    GPSUnavailableError,
    InvalidCoordinatesError,
    InvalidMealTypeError,
    InvalidWeightError,
    NotificationError,
    # Base classes and enums
    PawControlError,
    RateLimitError,
    StorageError,
    ValidationError,
    WalkAlreadyInProgressError,
    WalkError,
    WalkNotInProgressError,
    create_error_context,
    # Helper functions
    get_exception_class,
    handle_exception_gracefully,
    raise_from_error_code,
)


class TestErrorSeverity:
    """Test ErrorSeverity enum."""

    def test_error_severity_values(self):
        """Test error severity enum values."""
        assert ErrorSeverity.LOW.value == "low"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.CRITICAL.value == "critical"

    def test_error_severity_all_values(self):
        """Test all error severity values are defined."""
        expected_severities = {"low", "medium", "high", "critical"}
        actual_severities = {severity.value for severity in ErrorSeverity}
        assert actual_severities == expected_severities


class TestErrorCategory:
    """Test ErrorCategory enum."""

    def test_error_category_values(self):
        """Test error category enum values."""
        assert ErrorCategory.CONFIGURATION.value == "configuration"
        assert ErrorCategory.DATA.value == "data"
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.GPS.value == "gps"
        assert ErrorCategory.VALIDATION.value == "validation"

    def test_error_category_all_values(self):
        """Test all error category values are defined."""
        expected_categories = {
            "configuration",
            "data",
            "network",
            "gps",
            "authentication",
            "rate_limit",
            "storage",
            "validation",
            "business_logic",
            "system",
        }
        actual_categories = {category.value for category in ErrorCategory}
        assert actual_categories == expected_categories


class TestPawControlError:
    """Test the base PawControlError class."""

    def test_basic_error_creation(self):
        """Test basic error creation."""
        error = PawControlError("Test error message")

        assert str(error) == "Test error message"
        assert error.error_code == "pawcontrolerror"
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.category == ErrorCategory.SYSTEM
        assert error.user_message == "Test error message"
        assert isinstance(error.timestamp, datetime)
        assert isinstance(error.context, dict)
        assert isinstance(error.recovery_suggestions, list)
        assert isinstance(error.stack_trace, list)

    def test_error_with_all_parameters(self):
        """Test error creation with all parameters."""
        timestamp = datetime(2025, 1, 15, 12, 0, 0)
        context = {"key": "value"}
        suggestions = ["Try again", "Check settings"]

        error = PawControlError(
            "Test message",
            error_code="test_error",
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.CONFIGURATION,
            context=context,
            recovery_suggestions=suggestions,
            user_message="User friendly message",
            technical_details="Technical details",
            timestamp=timestamp,
        )

        assert error.error_code == "test_error"
        assert error.severity == ErrorSeverity.HIGH
        assert error.category == ErrorCategory.CONFIGURATION
        assert error.context == context
        assert error.recovery_suggestions == suggestions
        assert error.user_message == "User friendly message"
        assert error.technical_details == "Technical details"
        assert error.timestamp == timestamp

    def test_to_dict(self):
        """Test error serialization to dictionary."""
        error = PawControlError(
            "Test message",
            error_code="test_error",
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.DATA,
            context={"test": "value"},
            recovery_suggestions=["Fix it"],
            user_message="User message",
            technical_details="Tech details",
        )

        error_dict = error.to_dict()

        assert error_dict["error_code"] == "test_error"
        assert error_dict["message"] == "Test message"
        assert error_dict["user_message"] == "User message"
        assert error_dict["severity"] == "high"
        assert error_dict["category"] == "data"
        assert error_dict["context"] == {"test": "value"}
        assert error_dict["recovery_suggestions"] == ["Fix it"]
        assert error_dict["technical_details"] == "Tech details"
        assert "timestamp" in error_dict
        assert error_dict["exception_type"] == "PawControlError"

    def test_add_context(self):
        """Test adding context to error."""
        error = PawControlError("Test message")

        result = error.add_context("key1", "value1")
        assert result is error  # Method chaining
        assert error.context["key1"] == "value1"

        error.add_context("key2", "value2")
        assert error.context["key2"] == "value2"
        assert len(error.context) == 2

    def test_add_recovery_suggestion(self):
        """Test adding recovery suggestions."""
        error = PawControlError("Test message")

        result = error.add_recovery_suggestion("Try this")
        assert result is error  # Method chaining
        assert "Try this" in error.recovery_suggestions

        error.add_recovery_suggestion("Also try this")
        assert "Also try this" in error.recovery_suggestions
        assert len(error.recovery_suggestions) == 2

    def test_with_user_message(self):
        """Test setting user message."""
        error = PawControlError("Technical message")

        result = error.with_user_message("User friendly message")
        assert result is error  # Method chaining
        assert error.user_message == "User friendly message"

    def test_method_chaining(self):
        """Test method chaining functionality."""
        error = (
            PawControlError("Test message")
            .add_context("dog_id", "test_dog")
            .add_recovery_suggestion("Check dog configuration")
            .with_user_message("Dog configuration error")
        )

        assert error.context["dog_id"] == "test_dog"
        assert "Check dog configuration" in error.recovery_suggestions
        assert error.user_message == "Dog configuration error"


class TestConfigurationError:
    """Test ConfigurationError class."""

    def test_basic_configuration_error(self):
        """Test basic configuration error."""
        error = ConfigurationError("test_setting")

        assert "test_setting" in str(error)
        assert error.error_code == "configuration_error"
        assert error.severity == ErrorSeverity.HIGH
        assert error.category == ErrorCategory.CONFIGURATION
        assert error.setting == "test_setting"
        assert error.context["setting"] == "test_setting"

    def test_configuration_error_with_value(self):
        """Test configuration error with value."""
        error = ConfigurationError("test_setting", "invalid_value", "Too short")

        assert "test_setting" in str(error)
        assert "invalid_value" in str(error)
        assert "Too short" in str(error)
        assert error.value == "invalid_value"
        assert error.context["value"] == "invalid_value"

    def test_configuration_error_with_type(self):
        """Test configuration error with expected type."""
        error = ConfigurationError(
            "test_setting", "invalid", expected_type=int, valid_values=[1, 2, 3]
        )

        assert error.expected_type == int
        assert error.valid_values == [1, 2, 3]
        assert error.context["expected_type"] == "int"
        assert error.context["valid_values"] == [1, 2, 3]

    def test_configuration_error_recovery_suggestions(self):
        """Test configuration error includes recovery suggestions."""
        error = ConfigurationError("test_setting")

        assert len(error.recovery_suggestions) > 0
        assert any(
            "configuration" in suggestion.lower()
            for suggestion in error.recovery_suggestions
        )


class TestDogNotFoundError:
    """Test DogNotFoundError class."""

    def test_basic_dog_not_found_error(self):
        """Test basic dog not found error."""
        error = DogNotFoundError("test_dog")

        assert "test_dog" in str(error)
        assert error.error_code == "dog_not_found"
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.category == ErrorCategory.DATA
        assert error.dog_id == "test_dog"
        assert error.context["dog_id"] == "test_dog"

    def test_dog_not_found_with_available_dogs(self):
        """Test dog not found error with available dogs list."""
        available = ["dog1", "dog2", "dog3"]
        error = DogNotFoundError("missing_dog", available)

        assert error.available_dogs == available
        assert error.context["available_dogs"] == available
        assert "dog1, dog2, dog3" in error.recovery_suggestions[-1]

    def test_dog_not_found_user_message(self):
        """Test dog not found error user message."""
        error = DogNotFoundError("test_dog")

        assert "test_dog" in error.user_message
        assert "not found" in error.user_message.lower()


class TestGPSError:
    """Test GPS-related errors."""

    def test_basic_gps_error(self):
        """Test basic GPS error."""
        error = GPSError("GPS failed", dog_id="test_dog")

        assert str(error) == "GPS failed"
        assert error.category == ErrorCategory.GPS
        assert error.dog_id == "test_dog"
        assert error.context["dog_id"] == "test_dog"

    def test_gps_error_with_location(self):
        """Test GPS error with location data."""
        from custom_components.pawcontrol.types import GPSLocation

        # Mock GPSLocation since we're testing exceptions
        location = MagicMock()
        location.__dict__ = {"latitude": 52.5, "longitude": 13.4}

        error = GPSError("GPS failed", dog_id="test_dog", location=location)

        assert error.location == location
        assert error.context["location"] == location.__dict__


class TestInvalidCoordinatesError:
    """Test InvalidCoordinatesError class."""

    def test_invalid_coordinates_with_values(self):
        """Test invalid coordinates error with values."""
        error = InvalidCoordinatesError(91.0, 181.0, "test_dog")

        assert "91.0" in str(error)
        assert "181.0" in str(error)
        assert error.latitude == 91.0
        assert error.longitude == 181.0
        assert error.dog_id == "test_dog"
        assert error.context["latitude"] == 91.0
        assert error.context["longitude"] == 181.0
        assert error.context["latitude_valid"] is False
        assert error.context["longitude_valid"] is False

    def test_invalid_coordinates_without_values(self):
        """Test invalid coordinates error without values."""
        error = InvalidCoordinatesError()

        assert "missing or malformed" in error.technical_details
        assert error.latitude is None
        assert error.longitude is None

    def test_invalid_coordinates_recovery_suggestions(self):
        """Test invalid coordinates error recovery suggestions."""
        error = InvalidCoordinatesError()

        suggestions = error.recovery_suggestions
        assert any("latitude" in suggestion for suggestion in suggestions)
        assert any("longitude" in suggestion for suggestion in suggestions)
        assert any("decimal degrees" in suggestion for suggestion in suggestions)


class TestGPSUnavailableError:
    """Test GPSUnavailableError class."""

    def test_gps_unavailable_basic(self):
        """Test basic GPS unavailable error."""
        error = GPSUnavailableError("test_dog")

        assert "test_dog" in str(error)
        assert error.dog_id == "test_dog"
        assert error.reason is None
        assert error.error_code == "gps_unavailable"
        assert error.severity == ErrorSeverity.LOW

    def test_gps_unavailable_with_reason(self):
        """Test GPS unavailable error with reason."""
        error = GPSUnavailableError("test_dog", "Device offline")

        assert "Device offline" in str(error)
        assert error.reason == "Device offline"
        assert error.context["reason"] == "Device offline"

    def test_gps_unavailable_with_last_location(self):
        """Test GPS unavailable error with last known location."""
        last_location = MagicMock()
        error = GPSUnavailableError("test_dog", last_known_location=last_location)

        assert error.last_known_location == last_location
        assert error.context["has_last_known_location"] is True


class TestWalkError:
    """Test walk-related errors."""

    def test_walk_not_in_progress_error(self):
        """Test walk not in progress error."""
        error = WalkNotInProgressError("test_dog")

        assert "test_dog" in str(error)
        assert "not currently in progress" in str(error)
        assert error.dog_id == "test_dog"
        assert error.error_code == "walk_not_in_progress"
        assert error.severity == ErrorSeverity.LOW
        assert error.category == ErrorCategory.BUSINESS_LOGIC

    def test_walk_not_in_progress_with_last_walk(self):
        """Test walk not in progress error with last walk time."""
        last_walk = datetime(2025, 1, 15, 10, 0, 0)
        error = WalkNotInProgressError("test_dog", last_walk)

        assert error.last_walk_time == last_walk
        assert error.context["last_walk_time"] == last_walk.isoformat()

    def test_walk_already_in_progress_error(self):
        """Test walk already in progress error."""
        start_time = datetime(2025, 1, 15, 10, 0, 0)
        error = WalkAlreadyInProgressError("test_dog", "walk_123", start_time)

        assert "already in progress" in str(error)
        assert error.dog_id == "test_dog"
        assert error.walk_id == "walk_123"
        assert error.start_time == start_time
        assert error.error_code == "walk_already_in_progress"
        assert error.context["current_walk_id"] == "walk_123"


class TestValidationError:
    """Test ValidationError class."""

    def test_basic_validation_error(self):
        """Test basic validation error."""
        error = ValidationError("test_field", "invalid_value", "Must be positive")

        assert "test_field" in str(error)
        assert "invalid_value" in str(error)
        assert "Must be positive" in str(error)
        assert error.field == "test_field"
        assert error.value == "invalid_value"
        assert error.constraint == "Must be positive"

    def test_validation_error_with_limits(self):
        """Test validation error with min/max limits."""
        error = ValidationError(
            "age", -5, min_value=0, max_value=30, valid_values=[1, 2, 3]
        )

        assert error.min_value == 0
        assert error.max_value == 30
        assert error.valid_values == [1, 2, 3]
        assert "at least 0" in " ".join(error.recovery_suggestions)
        assert "at most 30" in " ".join(error.recovery_suggestions)

    def test_validation_error_user_message(self):
        """Test validation error user message formatting."""
        error = ValidationError("dog_weight", 0)

        assert "dog weight" in error.user_message.lower()  # Replaces underscores


class TestInvalidMealTypeError:
    """Test InvalidMealTypeError class."""

    def test_invalid_meal_type_error(self):
        """Test invalid meal type error."""
        valid_types = ["breakfast", "lunch", "dinner"]
        error = InvalidMealTypeError("brunch", valid_types)

        assert error.meal_type == "brunch"
        assert error.valid_types == valid_types
        assert error.field == "meal_type"
        assert error.value == "brunch"
        assert error.valid_values == valid_types


class TestInvalidWeightError:
    """Test InvalidWeightError class."""

    def test_invalid_weight_error_basic(self):
        """Test basic invalid weight error."""
        error = InvalidWeightError(-5.0)

        assert error.weight == -5.0
        assert error.field == "weight"
        assert error.value == -5.0
        assert "positive number" in error.constraint

    def test_invalid_weight_error_with_limits(self):
        """Test invalid weight error with limits."""
        error = InvalidWeightError(100.0, min_weight=0.5, max_weight=50.0)

        assert error.min_weight == 0.5
        assert error.max_weight == 50.0
        assert "between 0.5kg and 50.0kg" in error.constraint


class TestStorageError:
    """Test StorageError class."""

    def test_storage_error_basic(self):
        """Test basic storage error."""
        error = StorageError("save")

        assert "save failed" in str(error)
        assert error.operation == "save"
        assert error.error_code == "storage_error"
        assert error.severity == ErrorSeverity.HIGH
        assert error.category == ErrorCategory.STORAGE

    def test_storage_error_with_reason(self):
        """Test storage error with reason."""
        error = StorageError("load", "File not found", "database", False)

        assert "File not found" in str(error)
        assert error.storage_type == "database"
        assert error.retry_possible is False
        assert error.context["retry_possible"] is False

    def test_storage_error_recovery_suggestions(self):
        """Test storage error recovery suggestions."""
        error = StorageError("save", retry_possible=True)

        assert any(
            "retry" in suggestion.lower() for suggestion in error.recovery_suggestions
        )

        error_no_retry = StorageError("save", retry_possible=False)
        retry_suggestions = [
            s for s in error_no_retry.recovery_suggestions if "retry" in s.lower()
        ]
        assert len(retry_suggestions) == 0


class TestRateLimitError:
    """Test RateLimitError class."""

    def test_rate_limit_error_basic(self):
        """Test basic rate limit error."""
        error = RateLimitError("api_call")

        assert "api_call" in str(error)
        assert error.action == "api_call"
        assert error.error_code == "rate_limit_exceeded"
        assert error.severity == ErrorSeverity.LOW

    def test_rate_limit_error_with_retry_after(self):
        """Test rate limit error with retry after."""
        error = RateLimitError("api_call", "10/minute", 60, 15, 10)

        assert error.limit == "10/minute"
        assert error.retry_after == 60
        assert error.current_count == 15
        assert error.max_count == 10
        assert "60 seconds" in str(error)
        assert "Wait 60 seconds" in error.recovery_suggestions[0]


class TestNotificationError:
    """Test NotificationError class."""

    def test_notification_error_basic(self):
        """Test basic notification error."""
        error = NotificationError("email")

        assert "email notification" in str(error)
        assert error.notification_type == "email"
        assert error.error_code == "notification_send_failed"
        assert error.severity == ErrorSeverity.MEDIUM

    def test_notification_error_with_fallback(self):
        """Test notification error with fallback available."""
        error = NotificationError("sms", "Service down", "mobile", True)

        assert error.channel == "mobile"
        assert error.fallback_available is True
        assert error.severity == ErrorSeverity.LOW  # Lower severity with fallback
        assert "Fallback notification" in error.recovery_suggestions[0]


class TestDataErrors:
    """Test data import/export errors."""

    def test_data_export_error(self):
        """Test data export error."""
        error = DataExportError("walks", "Disk full", "csv", True)

        assert "export walks data" in str(error)
        assert error.export_type == "walks"
        assert error.format_type == "csv"
        assert error.partial_export is True
        assert error.error_code == "data_export_failed"

    def test_data_import_error(self):
        """Test data import error."""
        error = DataImportError("health", "Invalid format", 42, False)

        assert "import health data" in str(error)
        assert "line 42" in str(error)
        assert error.import_type == "health"
        assert error.line_number == 42
        assert error.recoverable is False
        assert error.error_code == "data_import_failed"


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_exception_class_valid(self):
        """Test getting exception class for valid error codes."""
        assert get_exception_class("configuration_error") == ConfigurationError
        assert get_exception_class("dog_not_found") == DogNotFoundError
        assert get_exception_class("validation_error") == ValidationError

    def test_get_exception_class_invalid(self):
        """Test getting exception class for invalid error code."""
        with pytest.raises(KeyError, match="Unknown error code"):
            get_exception_class("invalid_error_code")

    def test_raise_from_error_code_valid(self):
        """Test raising exception from valid error code."""
        with pytest.raises(ConfigurationError) as exc_info:
            raise_from_error_code("configuration_error", "Test message")

        assert str(exc_info.value) == "Test message"
        assert exc_info.value.error_code == "configuration_error"

    def test_raise_from_error_code_invalid(self):
        """Test raising exception from invalid error code."""
        with pytest.raises(PawControlError) as exc_info:
            raise_from_error_code("unknown_error", "Test message")

        assert str(exc_info.value) == "Test message"
        assert exc_info.value.error_code == "unknown_error"

    def test_handle_exception_gracefully_success(self):
        """Test graceful exception handling with successful function."""

        def successful_function():
            return "success"

        result = handle_exception_gracefully(successful_function)()
        assert result == "success"

    def test_handle_exception_gracefully_paw_control_error(self):
        """Test graceful exception handling with PawControlError."""

        def failing_function():
            raise ValidationError("test_field", "invalid")

        with patch("logging.getLogger") as mock_logger:
            result = handle_exception_gracefully(
                failing_function, default_return="fallback", log_errors=True
            )()

            assert result == "fallback"
            mock_logger.return_value.error.assert_called()

    def test_handle_exception_gracefully_critical_reraise(self):
        """Test graceful exception handling with critical error reraise."""

        def critical_function():
            raise PawControlError("Critical error", severity=ErrorSeverity.CRITICAL)

        with pytest.raises(PawControlError):
            handle_exception_gracefully(critical_function, reraise_critical=True)()

    def test_handle_exception_gracefully_unexpected_error(self):
        """Test graceful exception handling with unexpected error."""

        def unexpected_error_function():
            raise ValueError("Unexpected error")

        with patch("logging.getLogger") as mock_logger:
            result = handle_exception_gracefully(
                unexpected_error_function,
                default_return="fallback",
                log_errors=True,
                reraise_critical=False,
            )()

            assert result == "fallback"
            mock_logger.return_value.exception.assert_called()

    def test_create_error_context_basic(self):
        """Test creating basic error context."""
        context = create_error_context(dog_id="test_dog", operation="feeding")

        assert context["dog_id"] == "test_dog"
        assert context["operation"] == "feeding"
        assert "timestamp" in context

    def test_create_error_context_with_additional(self):
        """Test creating error context with additional data."""
        context = create_error_context(
            dog_id="test_dog", custom_field="custom_value", another_field=123
        )

        assert context["dog_id"] == "test_dog"
        assert context["custom_field"] == "custom_value"
        assert context["another_field"] == 123

    def test_create_error_context_filters_none(self):
        """Test that error context filters out None values."""
        context = create_error_context(
            dog_id="test_dog", operation=None, empty_field=None
        )

        assert "operation" not in context
        assert "empty_field" not in context
        assert "dog_id" in context


class TestExceptionMap:
    """Test exception mapping constants."""

    def test_exception_map_completeness(self):
        """Test that EXCEPTION_MAP contains all expected exceptions."""
        expected_codes = {
            "configuration_error",
            "dog_not_found",
            "invalid_coordinates",
            "gps_unavailable",
            "walk_not_in_progress",
            "walk_already_in_progress",
            "validation_error",
            "invalid_meal_type",
            "invalid_weight",
            "storage_error",
            "rate_limit_exceeded",
            "notification_send_failed",
            "data_export_failed",
            "data_import_failed",
        }

        assert set(EXCEPTION_MAP.keys()) == expected_codes

    def test_exception_map_classes(self):
        """Test that EXCEPTION_MAP maps to correct exception classes."""
        assert EXCEPTION_MAP["configuration_error"] == ConfigurationError
        assert EXCEPTION_MAP["dog_not_found"] == DogNotFoundError
        assert EXCEPTION_MAP["validation_error"] == ValidationError
        assert EXCEPTION_MAP["storage_error"] == StorageError

    def test_all_exceptions_have_mapping(self):
        """Test that all exception classes have entries in EXCEPTION_MAP."""
        exception_classes = {
            ConfigurationError,
            DogNotFoundError,
            InvalidCoordinatesError,
            GPSUnavailableError,
            WalkNotInProgressError,
            WalkAlreadyInProgressError,
            ValidationError,
            InvalidMealTypeError,
            InvalidWeightError,
            StorageError,
            RateLimitError,
            NotificationError,
            DataExportError,
            DataImportError,
        }

        mapped_classes = set(EXCEPTION_MAP.values())
        assert exception_classes.issubset(mapped_classes)


class TestExceptionHierarchy:
    """Test exception class hierarchy."""

    def test_all_exceptions_inherit_from_base(self):
        """Test that all specific exceptions inherit from PawControlError."""
        specific_exceptions = [
            ConfigurationError("test"),
            DogNotFoundError("test_dog"),
            InvalidCoordinatesError(),
            GPSUnavailableError("test_dog"),
            WalkNotInProgressError("test_dog"),
            WalkAlreadyInProgressError("test_dog", "walk_123"),
            ValidationError("field"),
            InvalidMealTypeError("invalid"),
            InvalidWeightError(-5.0),
            StorageError("save"),
            RateLimitError("action"),
            NotificationError("email"),
            DataExportError("walks"),
            DataImportError("health"),
        ]

        for exception in specific_exceptions:
            assert isinstance(exception, PawControlError)

    def test_gps_errors_inherit_from_gps_error(self):
        """Test that GPS-specific errors inherit from GPSError."""
        assert isinstance(InvalidCoordinatesError(), GPSError)
        assert isinstance(GPSUnavailableError("test_dog"), GPSError)

    def test_walk_errors_inherit_from_walk_error(self):
        """Test that walk-specific errors inherit from WalkError."""
        assert isinstance(WalkNotInProgressError("test_dog"), WalkError)
        assert isinstance(WalkAlreadyInProgressError("test_dog", "walk_123"), WalkError)

    def test_validation_errors_inherit_from_validation_error(self):
        """Test that validation-specific errors inherit from ValidationError."""
        assert isinstance(InvalidMealTypeError("invalid"), ValidationError)
        assert isinstance(InvalidWeightError(-5.0), ValidationError)
