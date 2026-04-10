"""Tests for API validation helpers and health status mapping."""

import asyncio
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.api_validator import (
    APIValidationResult,
    APIValidator,
    _extract_api_version,
    _extract_capabilities,
)


class _FakeSession:
    """Minimal aiohttp-compatible session for unit tests."""

    closed = False

    async def request(self, *_args: Any, **_kwargs: Any) -> None:
        """Provide coroutine signature expected by session validation."""


@pytest.fixture
def validator() -> APIValidator:
    """Create an API validator with a fake shared session."""
    return APIValidator(SimpleNamespace(), _FakeSession())


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("", False),
        ("pawcontrol.local", False),
        ("https://", False),
        ("http://pawcontrol.local", True),
        ("https://example.com/api", True),
    ],
)
def test_validate_endpoint_format_rejects_invalid_urls(
    validator: APIValidator,
    endpoint: str,
    expected: bool,
) -> None:
    """Endpoint validation should accept only HTTP(S) URLs with a host."""
    assert validator._validate_endpoint_format(endpoint) is expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"version": "2026.4.0"}, "2026.4.0"),
        ({"version": 12}, None),
        ({}, None),
    ],
)
def test_extract_api_version_handles_typed_and_untyped_payloads(
    payload: Mapping[str, Any],
    expected: str | None,
) -> None:
    """Version extraction should return only string versions."""
    assert _extract_api_version(payload) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"capabilities": ["gps", "feeding"]}, ["gps", "feeding"]),
        ({"capabilities": ["gps", 3, None]}, ["gps"]),
        ({"capabilities": []}, []),
        ({"capabilities": "gps"}, None),
        ({}, None),
    ],
)
def test_extract_capabilities_normalizes_capability_sequences(
    payload: Mapping[str, Any],
    expected: list[str] | None,
) -> None:
    """Capability extraction should keep string items and preserve empty lists."""
    assert _extract_capabilities(payload) == expected


@pytest.mark.parametrize(
    ("validation", "token", "expected_status"),
    [
        (
            APIValidationResult(True, True, True, 30.0, None, "v1", ["gps"]),
            "token",
            "healthy",
        ),
        (
            APIValidationResult(False, False, False, None, "down", None, None),
            "token",
            "unreachable",
        ),
        (
            APIValidationResult(False, True, False, 40.0, "bad token", None, None),
            "token",
            "authentication_failed",
        ),
        (
            APIValidationResult(False, True, False, 50.0, "degraded", None, None),
            None,
            "degraded",
        ),
    ],
)
def test_async_test_api_health_maps_status_from_validation_result(
    validator: APIValidator,
    validation: APIValidationResult,
    token: str | None,
    expected_status: str,
) -> None:
    """Health status should map from validation outcomes and token presence."""
    validator.async_validate_api_connection = AsyncMock(return_value=validation)

    result = asyncio.run(validator.async_test_api_health("https://example.com", token))

    assert result["status"] == expected_status
    assert result["healthy"] is validation.valid
    assert result["reachable"] is validation.reachable
