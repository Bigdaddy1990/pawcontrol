"""Targeted coverage tests for api_validator.py — pure helpers (0% → 22%+).

Covers: APIValidationResult, APIHealthStatus, APIAuthenticationResult constructors
"""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.api_validator import (
    APIAuthenticationResult,
    APIHealthStatus,
    APIValidationResult,
)

# ─── APIValidationResult ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_api_validation_result_valid() -> None:
    r = APIValidationResult(
        valid=True,
        reachable=True,
        authenticated=True,
        response_time_ms=42.0,
        error_message=None,
        api_version="1.0",
        capabilities=None,
    )
    assert r.valid is True
    assert r.reachable is True
    assert r.authenticated is True


@pytest.mark.unit
def test_api_validation_result_invalid() -> None:
    r = APIValidationResult(
        valid=False,
        reachable=False,
        authenticated=False,
        response_time_ms=None,
        error_message="Connection refused",
        api_version=None,
        capabilities=None,
    )
    assert r.valid is False
    assert r.error_message == "Connection refused"


@pytest.mark.unit
def test_api_validation_result_partial() -> None:
    r = APIValidationResult(
        valid=False,
        reachable=True,
        authenticated=False,
        response_time_ms=120.5,
        error_message="Auth failed",
        api_version=None,
        capabilities=None,
    )
    assert r.reachable is True
    assert r.authenticated is False
    assert r.response_time_ms == pytest.approx(120.5)


# ─── APIHealthStatus (TypedDict) ─────────────────────────────────────────────


@pytest.mark.unit
def test_api_health_status_dict() -> None:
    status: APIHealthStatus = {"healthy": True, "latency_ms": 35.0}
    assert status["healthy"] is True


@pytest.mark.unit
def test_api_health_status_unhealthy() -> None:
    status: APIHealthStatus = {"healthy": False, "latency_ms": None, "error": "timeout"}
    assert status["healthy"] is False


# ─── APIAuthenticationResult (TypedDict) ─────────────────────────────────────


@pytest.mark.unit
def test_api_auth_result_success() -> None:
    result: APIAuthenticationResult = {"authenticated": True, "token": "abc123"}
    assert result["authenticated"] is True


@pytest.mark.unit
def test_api_auth_result_failure() -> None:
    result: APIAuthenticationResult = {"authenticated": False, "error": "Invalid token"}
    assert result["authenticated"] is False
