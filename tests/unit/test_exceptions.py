"""Tests for the enhanced PawControl error helpers."""

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol.exceptions import (
    ErrorSeverity,
    GPSError,
    PawControlError,
    create_error_context,
    handle_exception_gracefully,
)
from custom_components.pawcontrol.types import GPSLocation


def test_paw_control_error_context_serialization() -> None:
    """PawControlError should serialise complex context payloads to JSON-safe data."""  # noqa: E111

    timestamp = datetime(2024, 1, 1, tzinfo=UTC)  # noqa: E111
    error = PawControlError(  # noqa: E111
        "failure",
        context={
            "timestamp": timestamp,
            "details": {1: ["value", timestamp]},
        },
    )

    payload = error.to_dict()  # noqa: E111
    assert payload["context"]["timestamp"] == timestamp.isoformat()  # noqa: E111

    details = payload["context"]["details"]  # noqa: E111
    assert isinstance(details, dict)  # noqa: E111
    assert details["1"][1] == timestamp.isoformat()  # noqa: E111


def test_gps_error_context_serialization() -> None:
    """GPSError should serialise GPSLocation dataclasses into JSON payloads."""  # noqa: E111

    location = GPSLocation(  # noqa: E111
        latitude=1.0, longitude=2.0, timestamp=datetime(2024, 5, 1, tzinfo=UTC)
    )
    error = GPSError("gps failure", dog_id="spot", location=location)  # noqa: E111

    location_context = error.context["location"]  # noqa: E111
    assert isinstance(location_context, dict)  # noqa: E111
    assert location_context["timestamp"] == location.timestamp.isoformat()  # noqa: E111


def test_create_error_context_filters_none_and_serialises_values() -> None:
    """create_error_context should drop ``None`` entries and serialise datetimes."""  # noqa: E111

    payload = create_error_context(  # noqa: E111
        dog_id="spot",
        operation="sync",
        extra=datetime(2023, 8, 15, tzinfo=UTC),
        optional=None,
    )

    assert payload["dog_id"] == "spot"  # noqa: E111
    assert payload["operation"] == "sync"  # noqa: E111
    assert payload["extra"] == datetime(2023, 8, 15, tzinfo=UTC).isoformat()  # noqa: E111
    assert "optional" not in payload  # noqa: E111


def test_handle_exception_gracefully_returns_default_for_non_critical() -> None:
    """Non-critical PawControlError instances should return the provided default."""  # noqa: E111

    error = PawControlError("boom", severity=ErrorSeverity.LOW)  # noqa: E111

    wrapped = handle_exception_gracefully(  # noqa: E111
        lambda: (_ for _ in ()).throw(error),
        default_return="fallback",
        log_errors=False,
    )
    assert wrapped() == "fallback"  # noqa: E111


def test_handle_exception_gracefully_reraises_critical() -> None:
    """Critical errors should bubble up when reraise_critical is enabled."""  # noqa: E111

    error = PawControlError("boom", severity=ErrorSeverity.CRITICAL)  # noqa: E111

    wrapped = handle_exception_gracefully(  # noqa: E111
        lambda: (_ for _ in ()).throw(error), log_errors=False
    )

    with pytest.raises(PawControlError):  # noqa: E111
        wrapped()
