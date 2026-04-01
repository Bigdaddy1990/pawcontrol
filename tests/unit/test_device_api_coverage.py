"""Coverage tests for device_api.py — (0% → 28%+).

Covers: DeviceEndpoint, NetworkError, RateLimitError, validate_device_endpoint
"""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.device_api import (
    DeviceEndpoint,
    NetworkError,
    RateLimitError,
    validate_device_endpoint,
)

# ─── validate_device_endpoint ────────────────────────────────────────────────


@pytest.mark.unit
def test_validate_device_endpoint_valid_url() -> None:
    result = validate_device_endpoint("http://192.168.1.100:8080")
    assert result is not None


@pytest.mark.unit
def test_validate_device_endpoint_https() -> None:
    result = validate_device_endpoint("https://pawcontrol.local")
    assert result is not None


@pytest.mark.unit
def test_validate_device_endpoint_invalid_raises() -> None:
    with pytest.raises(Exception):  # noqa: B017
        validate_device_endpoint("not_a_url")


@pytest.mark.unit
def test_validate_device_endpoint_empty_raises() -> None:
    with pytest.raises(Exception):  # noqa: B017
        validate_device_endpoint("")


# ─── DeviceEndpoint ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_device_endpoint_init() -> None:
    url = validate_device_endpoint("http://192.168.1.1:8080")
    ep = DeviceEndpoint(base_url=url)
    assert ep.base_url is not None
    assert ep.api_key is None


@pytest.mark.unit
def test_device_endpoint_with_api_key() -> None:
    url = validate_device_endpoint("http://192.168.1.1:8080")
    ep = DeviceEndpoint(base_url=url, api_key="secret_key")
    assert ep.api_key == "secret_key"


# ─── NetworkError ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_network_error_basic() -> None:
    err = NetworkError("connection failed")
    assert isinstance(err, Exception)
    assert err.retryable is True


@pytest.mark.unit
def test_network_error_with_endpoint() -> None:
    err = NetworkError("timeout", endpoint="http://192.168.1.1", operation="fetch")
    assert err.endpoint == "http://192.168.1.1"
    assert err.operation == "fetch"


@pytest.mark.unit
def test_network_error_not_retryable() -> None:
    err = NetworkError("bad request", retryable=False)
    assert err.retryable is False


@pytest.mark.unit
def test_network_error_is_exception() -> None:
    with pytest.raises(NetworkError):
        raise NetworkError("test error")


# ─── RateLimitError ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_rate_limit_error_basic() -> None:
    err = RateLimitError("walk_start")
    assert isinstance(err, Exception)
    assert err.action == "walk_start"


@pytest.mark.unit
def test_rate_limit_error_with_limit() -> None:
    err = RateLimitError("feeding", limit="10/min", retry_after=60)
    assert err.limit == "10/min"
    assert err.retry_after == 60


@pytest.mark.unit
def test_rate_limit_error_with_counts() -> None:
    err = RateLimitError("push", current_count=11, max_count=10)
    assert err.current_count == 11
    assert err.max_count == 10


@pytest.mark.unit
def test_rate_limit_error_raise() -> None:
    with pytest.raises(RateLimitError):
        raise RateLimitError("test_action")
