"""Targeted coverage tests for exceptions.py — uncovered constructors (60% → 78%+).

Covers: DogNotFoundError, GPSError, WalkError, WalkAlreadyInProgressError,
        WalkNotInProgressError, ConfigurationError, ServiceUnavailableError,
        NetworkError, NotificationError, ValidationError, PawControlError,
        RateLimitError, InvalidWeightError, InvalidMealTypeError
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.exceptions import (
    ConfigurationError,
    DogNotFoundError,
    GPSError,
    GPSUnavailableError,
    InvalidCoordinatesError,
    InvalidMealTypeError,
    InvalidWeightError,
    NetworkError,
    NotificationError,
    PawControlError,
    PawControlSetupError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
    WalkAlreadyInProgressError,
    WalkError,
    WalkNotInProgressError,
)


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlError (base)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_pawcontrol_error_basic() -> None:
    from custom_components.pawcontrol.exceptions import ErrorSeverity, ErrorCategory
    err = PawControlError(
        "Something went wrong",
        error_code="err_001",
        severity=ErrorSeverity.HIGH,
        category=ErrorCategory.NETWORK,
        recovery_suggestions=["Retry", "Check config"],
    )
    assert "Something" in str(err)
    assert err.error_code == "err_001"


@pytest.mark.unit
def test_pawcontrol_setup_error() -> None:
    err = PawControlSetupError("Setup failed", error_code="setup_001")
    assert "Setup" in str(err)


# ═══════════════════════════════════════════════════════════════════════════════
# DogNotFoundError
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_dog_not_found_no_available() -> None:
    err = DogNotFoundError("rex")
    assert "rex" in str(err)
    assert err.dog_id == "rex"
    assert err.available_dogs == []


@pytest.mark.unit
def test_dog_not_found_with_available() -> None:
    err = DogNotFoundError("ghost", available_dogs=["rex", "buddy"])
    assert "rex" in str(err)
    assert err.available_dogs == ["rex", "buddy"]


# ═══════════════════════════════════════════════════════════════════════════════
# WalkError, WalkAlreadyInProgressError, WalkNotInProgressError
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_walk_error() -> None:
    err = WalkError("Something broke", dog_id="rex")
    assert "Something" in str(err)


@pytest.mark.unit
def test_walk_error_with_walk_id() -> None:
    err = WalkError("Paused", dog_id="rex", walk_id="w_001")
    assert err is not None


@pytest.mark.unit
def test_walk_already_in_progress() -> None:
    err = WalkAlreadyInProgressError("rex", walk_id="w_001")
    assert "rex" in str(err)


@pytest.mark.unit
def test_walk_not_in_progress() -> None:
    err = WalkNotInProgressError("rex")
    assert err is not None


# ═══════════════════════════════════════════════════════════════════════════════
# GPSError, GPSUnavailableError, InvalidCoordinatesError
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_gps_error_basic() -> None:
    err = GPSError("GPS lost", dog_id="rex")
    assert "GPS" in str(err)


@pytest.mark.unit
def test_gps_error_no_dog_id() -> None:
    err = GPSError("No signal")
    assert err is not None


@pytest.mark.unit
def test_gps_unavailable() -> None:
    err = GPSUnavailableError("rex", reason="timeout")
    assert err is not None


@pytest.mark.unit
def test_invalid_coordinates() -> None:
    err = InvalidCoordinatesError(latitude=200.0, longitude=300.0, dog_id="rex")
    assert err is not None


# ═══════════════════════════════════════════════════════════════════════════════
# ConfigurationError
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_configuration_error() -> None:
    err = ConfigurationError("api_key", value="bad_key", reason="Too short")
    assert err is not None


@pytest.mark.unit
def test_configuration_error_minimal() -> None:
    err = ConfigurationError("reset_time")
    assert err is not None


# ═══════════════════════════════════════════════════════════════════════════════
# ServiceUnavailableError, NetworkError, NotificationError
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_service_unavailable() -> None:
    err = ServiceUnavailableError("Circuit open", service_name="api")
    assert "Circuit" in str(err)


@pytest.mark.unit
def test_network_error() -> None:
    err = NetworkError("Timeout", endpoint="/api/dogs", retryable=True)
    assert "Timeout" in str(err)


@pytest.mark.unit
def test_notification_error() -> None:
    err = NotificationError("push", reason="Token expired", channel="mobile")
    assert err is not None


# ═══════════════════════════════════════════════════════════════════════════════
# ValidationError
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_validation_error_full() -> None:
    err = ValidationError("weight", -5, "weight_too_low", min_value=0, max_value=200)
    assert err.field == "weight"
    assert err.value == -5
    assert err.constraint == "weight_too_low"


@pytest.mark.unit
def test_validation_error_minimal() -> None:
    err = ValidationError("dog_id")
    assert err.field == "dog_id"


# ═══════════════════════════════════════════════════════════════════════════════
# RateLimitError, InvalidWeightError, InvalidMealTypeError
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_rate_limit_error() -> None:
    err = RateLimitError("feeding", limit="10/hour", retry_after=60)
    assert err is not None


@pytest.mark.unit
def test_invalid_weight_error() -> None:
    err = InvalidWeightError(-1.0, min_weight=0.1, max_weight=200.0)
    assert err is not None


@pytest.mark.unit
def test_invalid_meal_type_error() -> None:
    err = InvalidMealTypeError("teatime", valid_types=["breakfast", "dinner"])
    assert err is not None
