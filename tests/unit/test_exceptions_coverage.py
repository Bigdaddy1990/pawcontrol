"""Targeted coverage tests for exceptions.py — (0% → 35%+).

Covers: PawControlError, ValidationError, ConfigurationError,
        WalkError, DogNotFoundError, AuthenticationError,
        create_error_context, get_exception_class
"""

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol.exceptions import (
    EXCEPTION_MAP,
    AuthenticationError,
    ConfigurationError,
    DogNotFoundError,
    PawControlError,
    ValidationError,
    WalkError,
    create_error_context,
    get_exception_class,
)

# ─── PawControlError ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_pawcontrol_error_basic() -> None:  # noqa: D103
    err = PawControlError("something failed")
    assert str(err) != ""
    assert isinstance(err, Exception)


@pytest.mark.unit
def test_pawcontrol_error_with_code() -> None:  # noqa: D103
    err = PawControlError("failure", error_code="ERR_001")
    assert err.error_code == "ERR_001"


@pytest.mark.unit
def test_pawcontrol_error_default_severity() -> None:  # noqa: D103
    err = PawControlError("test")
    assert err.severity is not None


@pytest.mark.unit
def test_pawcontrol_error_is_exception() -> None:  # noqa: D103
    with pytest.raises(PawControlError):
        raise PawControlError("boom")


@pytest.mark.unit
def test_pawcontrol_error_normalizes_context_and_supports_chaining() -> None:  # noqa: D103
    now = datetime(2026, 1, 1, tzinfo=UTC)
    err = PawControlError(
        "payload error",
        context={
            "count": 3,
            "seen_at": now,
            "tags": ["a", {"nested": True}],
            "ignored": None,
        },
    )

    chained = err.add_context("new_value", {"when": now}).add_recovery_suggestion(
        "Try again"
    )

    assert chained is err
    assert "ignored" not in err.context
    assert err.context["seen_at"] == now.isoformat()
    assert err.context["tags"] == ["a", {"nested": True}]
    assert err.context["new_value"] == {"when": now.isoformat()}
    assert err.recovery_suggestions[-1] == "Try again"


@pytest.mark.unit
def test_pawcontrol_error_capture_stack_opt_in() -> None:  # noqa: D103
    class _StackError(PawControlError):
        CAPTURE_STACK = True

    err = _StackError("capture stack")

    assert err.stack_trace is not None
    assert err.stack_trace


# ─── ValidationError ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_validation_error_basic() -> None:  # noqa: D103
    err = ValidationError("weight", -1.0, "too_low")
    assert isinstance(err, PawControlError)
    assert err.field == "weight"


@pytest.mark.unit
def test_validation_error_with_bounds() -> None:  # noqa: D103
    err = ValidationError("age", 200, "out_of_range", min_value=0, max_value=30)
    assert err.min_value == 0
    assert err.max_value == 30


@pytest.mark.unit
def test_validation_error_no_value() -> None:  # noqa: D103
    err = ValidationError("name")
    assert isinstance(err, Exception)


# ─── ConfigurationError ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_configuration_error_basic() -> None:  # noqa: D103
    err = ConfigurationError("api_url")
    assert isinstance(err, PawControlError)


@pytest.mark.unit
def test_configuration_error_with_value() -> None:  # noqa: D103
    err = ConfigurationError("timeout", value=0)
    assert err.setting == "timeout"
    assert err.value == 0


# ─── WalkError ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_walk_error_basic() -> None:  # noqa: D103
    err = WalkError("walk failed", dog_id="rex")
    assert isinstance(err, PawControlError)
    assert err.dog_id == "rex"


@pytest.mark.unit
def test_walk_error_with_walk_id() -> None:  # noqa: D103
    err = WalkError("gps lost", dog_id="buddy", walk_id="walk_001")
    assert err.walk_id == "walk_001"


# ─── DogNotFoundError ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_dog_not_found_error_basic() -> None:  # noqa: D103
    err = DogNotFoundError("rex")
    assert isinstance(err, PawControlError)
    assert "rex" in str(err) or err.dog_id == "rex"


@pytest.mark.unit
def test_dog_not_found_error_with_available() -> None:  # noqa: D103
    err = DogNotFoundError("unknown_dog", available_dogs=["rex", "buddy"])
    assert err.available_dogs == ["rex", "buddy"]


# ─── AuthenticationError ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_authentication_error_basic() -> None:  # noqa: D103
    err = AuthenticationError("invalid token")
    assert isinstance(err, PawControlError)


@pytest.mark.unit
def test_authentication_error_with_service() -> None:  # noqa: D103
    err = AuthenticationError("token expired", service="pawcontrol_api")
    assert err.service == "pawcontrol_api"


# ─── create_error_context ────────────────────────────────────────────────────


@pytest.mark.unit
def test_create_error_context_empty() -> None:  # noqa: D103
    ctx = create_error_context()
    assert isinstance(ctx, dict)


@pytest.mark.unit
def test_create_error_context_with_dog() -> None:  # noqa: D103
    ctx = create_error_context(dog_id="rex", operation="walk_start")
    assert ctx.get("dog_id") == "rex"
    assert ctx.get("operation") == "walk_start"


@pytest.mark.unit
def test_create_error_context_extra_kwargs() -> None:  # noqa: D103
    ctx = create_error_context(dog_id="buddy", retry_count=3)
    assert ctx.get("retry_count") == 3


# ─── get_exception_class ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_get_exception_class_known_code() -> None:  # noqa: D103
    cls = get_exception_class("authentication_error")
    assert issubclass(cls, Exception)
    assert cls is AuthenticationError


@pytest.mark.unit
def test_get_exception_class_for_all_registered_codes() -> None:  # noqa: D103
    for error_code, expected_cls in EXCEPTION_MAP.items():
        assert get_exception_class(error_code) is expected_cls


@pytest.mark.unit
def test_get_exception_class_raises_for_unknown() -> None:  # noqa: D103
    with pytest.raises(KeyError):
        get_exception_class("COMPLETELY_UNKNOWN_CODE_XYZ_NEVER_EXISTS")
