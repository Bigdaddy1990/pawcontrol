"""Tests for exception helper utilities."""

from custom_components.pawcontrol.exceptions import (
    DogNotFoundError,
    PawControlError,
    wrap_exception,
)


def test_pawcontrol_error_to_dict() -> None:
    """PawControlError exposes structured data."""
    err = PawControlError(
        "base error",
        error_code="BASE",
        details={"foo": "bar"},
        recoverable=True,
    )
    assert err.to_dict() == {
        "type": "PawControlError",
        "message": "base error",
        "error_code": "BASE",
        "details": {"foo": "bar"},
        "recoverable": True,
    }


def test_dog_not_found_to_dict() -> None:
    """Subclass includes specific structured fields."""
    err = DogNotFoundError("abc123")
    data = err.to_dict()
    assert data["error_code"] == "DOG_NOT_FOUND"
    assert data["details"] == {"dog_id": "abc123"}


def test_wrap_exception_preserves_cause() -> None:
    """wrap_exception links back to original exception."""
    original = ValueError("boom")
    wrapped = wrap_exception("do_stuff", original)
    assert wrapped.__cause__ is original
