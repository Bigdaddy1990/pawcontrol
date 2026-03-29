"""Tests for the enhanced PawControl error helpers."""

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol.exceptions import (
    ErrorCategory,
    ErrorSeverity,
    GPSError,
    PawControlError,
    ServiceUnavailableError,
    create_error_context,
    get_exception_class,
    handle_exception_gracefully,
    raise_from_error_code,
)
from custom_components.pawcontrol.types import GPSLocation


def test_paw_control_error_context_serialization() -> None:
    """PawControlError should serialise complex context payloads to JSON-safe data."""
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    error = PawControlError(
        "failure",
        context={
            "timestamp": timestamp,
            "details": {1: ["value", timestamp]},
        },
    )

    payload = error.to_dict()
    assert payload["context"]["timestamp"] == timestamp.isoformat()

    details = payload["context"]["details"]
    assert isinstance(details, dict)
    assert details["1"][1] == timestamp.isoformat()


def test_gps_error_context_serialization() -> None:
    """GPSError should serialise GPSLocation dataclasses into JSON payloads."""
    location = GPSLocation(
        latitude=1.0, longitude=2.0, timestamp=datetime(2024, 5, 1, tzinfo=UTC)
    )
    error = GPSError("gps failure", dog_id="spot", location=location)

    location_context = error.context["location"]
    assert isinstance(location_context, dict)
    assert location_context["timestamp"] == location.timestamp.isoformat()


def test_create_error_context_filters_none_and_serialises_values() -> None:
    """create_error_context should drop ``None`` entries and serialise datetimes."""
    payload = create_error_context(
        dog_id="spot",
        operation="sync",
        extra=datetime(2023, 8, 15, tzinfo=UTC),
        optional=None,
    )

    assert payload["dog_id"] == "spot"
    assert payload["operation"] == "sync"
    assert payload["extra"] == datetime(2023, 8, 15, tzinfo=UTC).isoformat()
    assert "optional" not in payload


def test_handle_exception_gracefully_returns_default_for_non_critical() -> None:
    """Non-critical PawControlError instances should return the provided default."""
    error = PawControlError("boom", severity=ErrorSeverity.LOW)

    wrapped = handle_exception_gracefully(
        lambda: (_ for _ in ()).throw(error),
        default_return="fallback",
        log_errors=False,
    )
    assert wrapped() == "fallback"


def test_handle_exception_gracefully_reraises_critical() -> None:
    """Critical errors should bubble up when reraise_critical is enabled."""
    error = PawControlError("boom", severity=ErrorSeverity.CRITICAL)

    wrapped = handle_exception_gracefully(
        lambda: (_ for _ in ()).throw(error), log_errors=False
    )

    with pytest.raises(PawControlError):
        wrapped()


def test_handle_exception_gracefully_swallows_unexpected_when_configured() -> None:
    """Unexpected exceptions should return default when reraise is disabled."""
    wrapped = handle_exception_gracefully(
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        default_return="fallback",
        log_errors=False,
        reraise_critical=False,
    )

    assert wrapped() == "fallback"


def test_get_exception_class_known_and_unknown_codes() -> None:
    """Exception lookup should resolve known codes and reject unknown ones."""
    assert get_exception_class("service_unavailable") is ServiceUnavailableError

    with pytest.raises(KeyError, match="Unknown error code"):
        get_exception_class("does_not_exist")


def test_raise_from_error_code_honors_context_and_category() -> None:
    """raise_from_error_code should pass custom context/category to exceptions."""
    with pytest.raises(PawControlError) as exc_info:
        raise_from_error_code(
            "custom_error",
            "Custom message",
            category=ErrorCategory.DATA,
            context={"dog_id": "spot"},
        )

    error = exc_info.value
    assert error.error_code == "custom_error"
    assert error.category is ErrorCategory.DATA
    assert error.context["dog_id"] == "spot"


def test_raise_from_error_code_known_code_with_strict_signature() -> None:
    """Known codes currently bubble constructor signature mismatches."""
    with pytest.raises(TypeError, match="unexpected keyword argument 'error_code'"):
        raise_from_error_code("service_unavailable", "api down")
