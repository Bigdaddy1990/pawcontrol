"""Additional coverage tests for exception helpers."""

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol.exceptions import (
    ErrorCategory,
    ErrorSeverity,
    PawControlError,
    create_error_context,
    get_exception_class,
    handle_exception_gracefully,
    raise_from_error_code,
)


def test_paw_control_error_helpers_mutate_payload_and_serialize_context() -> None:
    """PawControlError should expose serialization and chainable helper methods."""
    error = PawControlError(
        "boom",
        context={"when": datetime(2026, 1, 2, 3, 4, tzinfo=UTC), "skip": None},
        technical_details="trace",
    )

    returned = error.add_context("payload", {"x": 1}).add_recovery_suggestion(
        "Retry later"
    ).with_user_message("Friendly")

    as_dict = error.to_dict()

    assert returned is error
    assert as_dict["message"] == "boom"
    assert as_dict["user_message"] == "Friendly"
    assert as_dict["technical_details"] == "trace"
    assert as_dict["context"]["when"] == "2026-01-02T03:04:00+00:00"
    assert as_dict["context"]["payload"] == {"x": 1}
    assert as_dict["recovery_suggestions"] == ["Retry later"]


class _StackCapturingError(PawControlError):
    CAPTURE_STACK = True


def test_paw_control_error_can_capture_stack_for_opt_in_subclasses() -> None:
    """Subclass CAPTURE_STACK=True should populate stack traces."""
    error = _StackCapturingError("capture")

    assert error.stack_trace is not None
    assert isinstance(error.stack_trace, list)
    assert error.stack_trace


def test_get_exception_class_and_raise_from_error_code_variants() -> None:
    """Exception helpers should resolve known codes and reject unknown codes."""
    assert get_exception_class("repair_required").__name__ == "RepairRequiredError"

    with pytest.raises(KeyError, match="Unknown error code"):
        get_exception_class("missing")

    with pytest.raises(PawControlError) as exc_info:
        raise_from_error_code(
            "unknown_code",
            "msg",
            category=ErrorCategory.DATA,
            context={"k": "v"},
            severity=ErrorSeverity.LOW,
        )

    assert exc_info.value.error_code == "unknown_code"
    assert exc_info.value.category is ErrorCategory.DATA
    assert exc_info.value.context["k"] == "v"


def test_handle_exception_gracefully_handles_non_critical_and_unexpected_errors(
) -> None:
    """Decorator should return default values for handled non-critical failures."""

    def _raise_non_critical() -> str:
        raise PawControlError("not critical")

    def _raise_unexpected() -> str:
        raise RuntimeError("oops")

    non_critical_wrapped = handle_exception_gracefully(
        _raise_non_critical,
        default_return="fallback",
        log_errors=False,
    )
    unexpected_wrapped = handle_exception_gracefully(
        _raise_unexpected,
        default_return="fallback",
        log_errors=False,
        reraise_critical=False,
    )

    assert non_critical_wrapped() == "fallback"
    assert unexpected_wrapped() == "fallback"


def test_handle_exception_gracefully_reraises_critical_errors() -> None:
    """Critical PawControlError should be reraised when configured."""

    def _raise_critical() -> None:
        raise PawControlError("fatal", severity=ErrorSeverity.CRITICAL)

    wrapped = handle_exception_gracefully(
        _raise_critical,
        default_return=None,
        log_errors=False,
    )

    with pytest.raises(PawControlError, match="fatal"):
        wrapped()


def test_create_error_context_serializes_additional_values() -> None:
    """create_error_context should normalize datetimes and nested values."""
    ctx = create_error_context(
        dog_id="dog-1",
        operation="sync",
        when=datetime(2026, 1, 1, tzinfo=UTC),
        nested={"ok": True},
        values=[1, "x"],
    )

    assert "timestamp" in ctx
    assert ctx["dog_id"] == "dog-1"
    assert ctx["operation"] == "sync"
    assert ctx["when"] == "2026-01-01T00:00:00+00:00"
    assert ctx["nested"] == {"ok": True}
    assert ctx["values"] == [1, "x"]
