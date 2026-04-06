"""Tests for the enhanced PawControl error helpers."""

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol.exceptions import (
    AuthenticationError,
    ErrorCategory,
    ErrorSeverity,
    GPSError,
    GPSUnavailableError,
    NotificationError,
    PawControlError,
    ServiceUnavailableError,
    StorageError,
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


def test_internal_serialisation_helpers_handle_nested_payloads() -> None:
    """Private serialization helpers should normalize mixed nested structures."""
    from custom_components.pawcontrol.exceptions import (
        _ensure_error_context,
        _serialise_json_value,
    )

    timestamp = datetime(2025, 6, 1, tzinfo=UTC)
    payload = {
        "a": 1,
        "when": timestamp,
        "nested": {"flag": True, "items": [1, timestamp, {"x": object()}]},
        "drop_none": None,
    }

    serialized = _serialise_json_value(payload)
    assert isinstance(serialized, dict)
    assert serialized["when"] == timestamp.isoformat()
    nested = serialized["nested"]
    assert isinstance(nested, dict)
    assert nested["items"][1] == timestamp.isoformat()
    assert isinstance(nested["items"][2]["x"], str)

    context = _ensure_error_context(payload)
    assert context["when"] == timestamp.isoformat()
    assert "drop_none" not in context


def test_paw_control_error_to_dict_includes_chainable_user_message_override() -> None:
    """with_user_message should update serialized payload output."""
    err = PawControlError(
        "raw backend failure",
        error_code="backend_failure",
        context={"dog_id": "milo"},
    ).with_user_message("Bitte später erneut versuchen")

    payload = err.to_dict()

    assert payload["error_code"] == "backend_failure"
    assert payload["message"] == "raw backend failure"
    assert payload["user_message"] == "Bitte später erneut versuchen"
    assert payload["context"]["dog_id"] == "milo"


def test_message_builders_without_optional_reason_values() -> None:
    """Exception messages should use the fallback branch without optional reasons."""
    gps_unavailable = GPSUnavailableError("milo")
    storage_error = StorageError("write", retry_possible=False)
    notification_error = NotificationError("mobile_app")

    assert str(gps_unavailable) == "GPS data is not available for dog 'milo'"
    assert str(storage_error) == "Storage write failed"
    assert str(notification_error) == "Failed to send mobile_app notification"
    assert storage_error.recovery_suggestions == [
        "Check available disk space",
        "Verify file permissions",
        "Ensure storage directory exists",
    ]


def test_message_builders_with_optional_reason_values() -> None:
    """Exception messages should include optional reason/flag branches."""
    gps_unavailable = GPSUnavailableError("milo", reason="no signal")
    storage_error = StorageError("write", reason="readonly", retry_possible=True)
    notification_error = NotificationError(
        "mobile_app",
        reason="service offline",
        fallback_available=True,
    )

    assert str(gps_unavailable) == "GPS data is not available for dog 'milo': no signal"
    assert str(storage_error) == "Storage write failed: readonly"
    assert "Retry the operation" in storage_error.recovery_suggestions
    assert (
        str(notification_error)
        == "Failed to send mobile_app notification: service offline"
    )
    assert "Fallback notification method will be used" in notification_error.recovery_suggestions


def test_raise_from_error_code_with_context_only_branch() -> None:
    """raise_from_error_code should support context-only override paths."""
    with pytest.raises(PawControlError) as exc_info:
        raise_from_error_code("custom_only_context", "Broken", context={"step": "sync"})

    assert exc_info.value.error_code == "custom_only_context"
    assert exc_info.value.context["step"] == "sync"


def test_raise_from_error_code_with_category_only_branch() -> None:
    """raise_from_error_code should support category-only override paths."""
    with pytest.raises(PawControlError) as exc_info:
        raise_from_error_code("custom_only_category", "Broken", category=ErrorCategory.NETWORK)

    assert exc_info.value.error_code == "custom_only_category"
    assert exc_info.value.category is ErrorCategory.NETWORK


def test_handle_exception_gracefully_logs_pawcontrol_errors(caplog: pytest.LogCaptureFixture) -> None:
    """Decorator should emit logger error payload for handled PawControl errors."""
    error = PawControlError("boom", severity=ErrorSeverity.LOW)
    wrapped = handle_exception_gracefully(
        lambda: (_ for _ in ()).throw(error),
        default_return="fallback",
        log_errors=True,
        reraise_critical=False,
    )

    with caplog.at_level("ERROR"):
        assert wrapped() == "fallback"

    assert any("PawControl error in <lambda>" in record.message for record in caplog.records)


def test_handle_exception_gracefully_logs_and_reraises_unexpected_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unexpected exceptions should be logged then reraised when configured."""
    wrapped = handle_exception_gracefully(
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        log_errors=True,
        reraise_critical=True,
    )

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="boom"):
        wrapped()

    assert any("Unexpected error in <lambda>" in record.message for record in caplog.records)


def test_authentication_error_sets_service_context() -> None:
    """AuthenticationError should keep optional service context value."""
    error = AuthenticationError("auth failed", service="webhook")

    assert error.context["service"] == "webhook"
