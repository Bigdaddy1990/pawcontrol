"""Extended coverage tests for PawControl exception constructors and helpers."""

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataExportError,
    DataImportError,
    DogNotFoundError,
    ErrorCategory,
    ErrorSeverity,
    FlowValidationError,
    GPSUnavailableError,
    InvalidCoordinatesError,
    InvalidMealTypeError,
    InvalidWeightError,
    NetworkError,
    NotificationError,
    PawControlSetupError,
    RateLimitError,
    ReauthRequiredError,
    ReconfigureRequiredError,
    RepairRequiredError,
    ServiceUnavailableError,
    StorageError,
    ValidationError,
    WalkAlreadyInProgressError,
    WalkNotInProgressError,
    create_error_context,
    raise_from_error_code,
)
from custom_components.pawcontrol.types import GPSLocation


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"setting": "mode", "value": "x", "reason": "bad"}, "(value: x): bad"),
        ({"setting": "mode", "value": "x"}, ": x"),
        ({"setting": "mode", "reason": "bad"}, ": bad"),
        ({"setting": "mode"}, "Invalid configuration for 'mode'"),
    ],
)
def test_configuration_error_message_variants(
    kwargs: dict[str, object], expected: str
) -> None:
    """ConfigurationError should format all message branches."""
    error = ConfigurationError(**kwargs)

    assert expected in str(error)
    assert error.error_code == "configuration_error"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {"field": "age", "value": 5, "constraint": "too young"},
            "(value: 5): too young",
        ),
        ({"field": "age", "value": 5}, "invalid value 5"),
        ({"field": "age", "constraint": "too young"}, ": too young"),
        ({"field": "age"}, "Validation failed for 'age'"),
    ],
)
def test_validation_error_message_variants(
    kwargs: dict[str, object], expected: str
) -> None:
    """ValidationError should format all message branches."""
    error = ValidationError(**kwargs)

    assert expected in str(error)
    assert error.error_code == "validation_error"


def test_domain_specific_error_contexts_and_severities() -> None:
    """Domain-specific exceptions should carry stable context and severity."""
    gps_error = InvalidCoordinatesError(latitude=123.0, longitude=3.0, dog_id="rex")
    assert gps_error.context["latitude_valid"] is False
    assert gps_error.category is ErrorCategory.GPS

    location = GPSLocation(latitude=52.5, longitude=13.4, accuracy=3.2, timestamp=None)
    unavailable = GPSUnavailableError(
        "rex", reason="offline", last_known_location=location
    )
    assert unavailable.context["dog_id"] == "rex"
    assert unavailable.context["location"]["latitude"] == 52.5

    walk_start = datetime(2026, 1, 1, tzinfo=UTC)
    walk_running = WalkAlreadyInProgressError(
        "rex", walk_id="walk-1", start_time=walk_start
    )
    assert walk_running.context["current_walk_id"] == "walk-1"
    assert walk_running.context["start_time"] == walk_start.isoformat()

    walk_idle = WalkNotInProgressError("rex", last_walk_time=walk_start)
    assert walk_idle.context["last_walk_time"] == walk_start.isoformat()


@pytest.mark.parametrize(
    ("error", "expected_severity"),
    [
        (
            StorageError("save", reason="denied", retry_possible=False),
            ErrorSeverity.HIGH,
        ),
        (RateLimitError("sync", limit="10/min", retry_after=3), ErrorSeverity.LOW),
        (NetworkError("timeout", retryable=False), ErrorSeverity.HIGH),
        (
            NotificationError("push", reason="service down", fallback_available=True),
            ErrorSeverity.LOW,
        ),
        (AuthenticationError("auth", service="api"), ErrorSeverity.HIGH),
        (DataExportError("history", reason="io"), ErrorSeverity.MEDIUM),
        (DataImportError("history", reason="bad", line_number=7), ErrorSeverity.MEDIUM),
        (PawControlSetupError("boom"), ErrorSeverity.CRITICAL),
        (ReauthRequiredError("reauth"), ErrorSeverity.HIGH),
        (ReconfigureRequiredError("reconfigure"), ErrorSeverity.MEDIUM),
        (RepairRequiredError("repair"), ErrorSeverity.MEDIUM),
    ],
)
def test_specialized_exceptions_have_expected_severity(
    error: Exception, expected_severity: ErrorSeverity
) -> None:
    """Specialized exception constructors should set severity defaults."""
    assert isinstance(error, Exception)
    assert error.severity is expected_severity


def test_service_unavailable_extends_network_context() -> None:
    """ServiceUnavailableError should enrich context.

    The network defaults should stay intact.
    """
    error = ServiceUnavailableError(
        "upstream unavailable",
        service_name="cloud",
        endpoint="https://api.example.invalid",
        operation="sync",
    )

    assert error.error_code == "service_unavailable"
    assert error.context["service_name"] == "cloud"
    assert error.context["retryable"] is True


def test_flow_validation_error_form_errors_branches() -> None:
    """FlowValidationError should emit field, base, and default form errors."""
    field_error = FlowValidationError(field_errors={"name": "required"})
    base_error = FlowValidationError(base_errors=["invalid"])
    empty_error = FlowValidationError()

    assert field_error.as_form_errors() == {"name": "required"}
    assert base_error.as_form_errors() == {"base": "invalid"}
    assert empty_error.as_form_errors() == {"base": "validation_error"}


@pytest.mark.parametrize(
    ("kwargs", "expected_substring"),
    [
        (
            {"action": "sync", "limit": "5/min", "retry_after": 2},
            "Retry after 2 seconds",
        ),
        ({"action": "sync", "limit": "5/min"}, "(5/min)"),
        ({"action": "sync", "retry_after": 2}, "Retry after 2 seconds"),
        ({"action": "sync"}, "Rate limit exceeded for sync"),
    ],
)
def test_rate_limit_error_message_variants(
    kwargs: dict[str, object], expected_substring: str
) -> None:
    """RateLimitError should build messages for all conditional branches."""
    error = RateLimitError(**kwargs)

    assert expected_substring in str(error)


def test_dog_not_found_error_with_and_without_available_ids() -> None:
    """DogNotFoundError should include optional available dog context."""
    with_available = DogNotFoundError("unknown", available_dogs=["rex", "luna"])
    without_available = DogNotFoundError("unknown")

    assert "available: rex, luna" in str(with_available)
    assert with_available.context["available_dogs"] == ["rex", "luna"]
    assert without_available.context["available_dogs"] == []


def test_raise_from_error_code_selects_known_classes_and_overrides() -> None:
    """raise_from_error_code should use mapped classes and keep fallback path."""
    with pytest.raises(TypeError):
        raise_from_error_code(
            "validation_error",
            "bad value",
            category=ErrorCategory.DATA,
        )

    with pytest.raises(PawControlSetupError):
        raise_from_error_code("setup_failed", "setup failed")


def test_create_error_context_skips_none_and_serializes_collections() -> None:
    """create_error_context should keep only JSON-safe serialised values."""
    context = create_error_context(
        dog_id="rex",
        operation="sync",
        empty=None,
        tags=("a", "b"),
        details={"at": datetime(2026, 1, 1, tzinfo=UTC)},
    )

    assert context["dog_id"] == "rex"
    assert context["operation"] == "sync"
    assert "empty" not in context
    assert context["tags"] == ["a", "b"]
    assert context["details"]["at"] == "2026-01-01T00:00:00+00:00"


def test_invalid_meal_type_and_weight_specializations() -> None:
    """Validation specializations should retain provided constraint metadata."""
    meal = InvalidMealTypeError("x", valid_types=["breakfast", "dinner"])
    weight_min = InvalidWeightError(1.0, min_weight=3.0)
    weight_max = InvalidWeightError(10.0, max_weight=8.0)
    weight_range = InvalidWeightError(9.0, min_weight=3.0, max_weight=8.0)

    assert meal.valid_types == ["breakfast", "dinner"]
    assert "at least 3.0kg" in str(weight_min)
    assert "at most 8.0kg" in str(weight_max)
    assert "between 3.0kg and 8.0kg" in str(weight_range)
