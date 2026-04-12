import pytest

"""Additional branch coverage for ``custom_components.pawcontrol.exceptions``."""

from custom_components.pawcontrol.exceptions import (
    DataExportError,
    DataImportError,
    ErrorSeverity,
    FlowValidationError,
    InvalidWeightError,
    NetworkError,
    NotificationError,
    PawControlError,
    RateLimitError,
    ReauthRequiredError,
    ReconfigureRequiredError,
    RepairRequiredError,
    ServiceUnavailableError,
    StorageError,
    handle_exception_gracefully,
    raise_from_error_code,
)


def test_flow_validation_error_as_form_errors_branching() -> None:
    """FlowValidationError should prioritize field, base, then default errors."""
    field_error = FlowValidationError(field_errors={"name": "required"})
    assert field_error.as_form_errors() == {"name": "required"}

    base_error = FlowValidationError(base_errors=["invalid_combo"])
    assert base_error.as_form_errors() == {"base": "invalid_combo"}

    default_error = FlowValidationError()
    assert default_error.as_form_errors() == {"base": "validation_error"}


def test_storage_error_retry_toggle_affects_suggestions() -> None:
    """StorageError should include retry guidance only when retries are possible."""
    retryable = StorageError("write", retry_possible=True)
    non_retryable = StorageError("write", retry_possible=False)

    assert "Retry the operation" in retryable.recovery_suggestions
    assert "Retry the operation" not in non_retryable.recovery_suggestions


def test_rate_limit_error_message_branches() -> None:
    """RateLimitError should tailor messages for limit/retry combinations."""
    both = RateLimitError("sync", limit="10/min", retry_after=30)
    only_limit = RateLimitError("sync", limit="10/min")
    only_retry = RateLimitError("sync", retry_after=15)
    plain = RateLimitError("sync")

    assert "(10/min). Retry after 30 seconds" in str(both)
    assert "(10/min)" in str(only_limit)
    assert "Retry after 15 seconds" in str(only_retry)
    assert str(plain) == "Rate limit exceeded for sync"


def test_network_and_service_unavailable_error_metadata() -> None:
    """Network-derived errors should expose expected severity/context metadata."""
    network = NetworkError(
        "network down",
        endpoint="https://api.example",
        operation="fetch",
        retryable=False,
    )
    assert network.severity is ErrorSeverity.HIGH
    assert network.context["endpoint"] == "https://api.example"
    assert network.context["operation"] == "fetch"

    unavailable = ServiceUnavailableError(
        "service offline",
        service_name="backend",
        endpoint="https://api.example",
        operation="fetch",
    )
    assert unavailable.error_code == "service_unavailable"
    assert unavailable.context["service_name"] == "backend"


def test_notification_error_fallback_changes_severity_and_suggestions() -> None:
    """Fallback-capable notifications should lower severity and mention fallback."""
    with_fallback = NotificationError("push", fallback_available=True)
    without_fallback = NotificationError("push", fallback_available=False)

    assert with_fallback.severity is ErrorSeverity.LOW
    assert without_fallback.severity is ErrorSeverity.MEDIUM
    assert any(
        "Fallback notification method" in s for s in with_fallback.recovery_suggestions
    )


def test_data_import_error_includes_line_number_when_available() -> None:
    """DataImportError should annotate the failing line number when provided."""
    with_line = DataImportError("history", reason="bad format", line_number=27)
    without_line = DataImportError("history", reason="bad format")

    assert "at line 27" in str(with_line)
    assert "at line" not in str(without_line)


def test_optional_reason_and_context_fields_use_default_messages() -> None:
    """Optional exception inputs should keep default message/context branches."""
    default_weight = InvalidWeightError(2.5)
    unavailable_without_service = ServiceUnavailableError("service offline")
    export_without_reason = DataExportError("history")
    import_without_reason = DataImportError("history")

    assert "weight" in str(default_weight)
    assert "Weight must be a positive number" in str(default_weight)
    assert "service_name" not in unavailable_without_service.context
    assert str(export_without_reason) == "Failed to export history data"
    assert str(import_without_reason) == "Failed to import history data"


def test_reconfiguration_related_errors_have_expected_codes() -> None:
    """Recovery flow exceptions should expose stable error codes/user messages."""
    reauth = ReauthRequiredError("reauth needed", context={"step": "token"})
    reconfigure = ReconfigureRequiredError("reconfigure needed")
    repair = RepairRequiredError("repair needed")

    assert reauth.error_code == "reauth_required"
    assert reauth.context["step"] == "token"
    assert reconfigure.error_code == "reconfigure_required"
    assert repair.error_code == "repair_required"


def test_gps_error_variants_cover_missing_message_branches() -> None:
    """GPS-related exceptions should expose fallback messages and details branches."""
    from custom_components.pawcontrol.exceptions import (
        GPSUnavailableError,
        InvalidCoordinatesError,
    )

    without_coordinates = InvalidCoordinatesError()
    assert str(without_coordinates) == "Invalid GPS coordinates provided"
    assert (
        without_coordinates.technical_details
        == "GPS coordinates are missing or malformed"
    )

    without_reason = GPSUnavailableError("dog-123")
    assert str(without_reason) == "GPS data is not available for dog 'dog-123'"


def test_storage_and_notification_error_reasonless_message_branches() -> None:
    """Storage/notification errors should use default messages without a reason."""
    no_reason_storage = StorageError("archive")
    no_reason_notification = NotificationError("email")

    assert str(no_reason_storage) == "Storage archive failed"
    assert str(no_reason_notification) == "Failed to send email notification"


def test_raise_from_error_code_with_context_only_path() -> None:
    """raise_from_error_code should support the context-only constructor branch."""
    with pytest.raises(PawControlError) as exc_info:
        raise_from_error_code(
            "custom_error",
            "context branch",
            context={"source": "test"},
        )

    assert exc_info.value.context["source"] == "test"


def test_raise_from_error_code_with_category_only_path() -> None:
    """raise_from_error_code should support the category-only constructor branch."""
    from custom_components.pawcontrol.exceptions import ErrorCategory

    with pytest.raises(PawControlError) as exc_info:
        raise_from_error_code(
            "custom_error",
            "category branch",
            category=ErrorCategory.NETWORK,
        )

    assert exc_info.value.category is ErrorCategory.NETWORK


def test_handle_exception_gracefully_logs_and_reraises_unexpected() -> None:
    """Unexpected exceptions should be logged and reraised when configured."""

    def _raise_unexpected() -> None:
        raise RuntimeError("boom")

    wrapped = handle_exception_gracefully(
        _raise_unexpected,
        log_errors=True,
        reraise_critical=True,
    )

    with pytest.raises(RuntimeError, match="boom"):
        wrapped()


def test_handle_exception_gracefully_unexpected_without_reraise_and_logging() -> None:
    """Unexpected errors can be swallowed when reraising/logging are disabled."""

    def _raise_unexpected() -> None:
        raise RuntimeError("silent boom")

    wrapped = handle_exception_gracefully(
        _raise_unexpected,
        default_return="fallback",
        log_errors=False,
        reraise_critical=False,
    )

    assert wrapped() == "fallback"


def test_handle_exception_gracefully_logs_non_critical_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Handled PawControlError instances should still be logged when requested."""

    def _raise_non_critical() -> None:
        raise PawControlError("recoverable")

    wrapped = handle_exception_gracefully(
        _raise_non_critical,
        default_return="fallback",
        log_errors=True,
    )

    with caplog.at_level("ERROR"):
        result = wrapped()

    assert result == "fallback"
    assert "PawControl error in _raise_non_critical" in caplog.text
