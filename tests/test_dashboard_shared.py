"""Tests for shared dashboard helper utilities."""

from __future__ import annotations

import asyncio
import logging

import pytest

from custom_components.pawcontrol.dashboard_shared import (
    coerce_dog_config,
    coerce_dog_configs,
    unwrap_async_result,
)


def test_coerce_dog_config_returns_typed_mapping_for_valid_payload() -> None:
    """Valid mapping payloads should be normalized into dog config data."""
    result = coerce_dog_config({"dog_id": "luna", "dog_name": "Luna", "dog_age": 3})

    assert result is not None
    assert result["dog_id"] == "luna"
    assert result["dog_name"] == "Luna"
    assert result["dog_age"] == 3


def test_coerce_dog_config_rejects_non_mapping_payload() -> None:
    """Non-mapping raw payloads should be rejected."""
    assert coerce_dog_config("not-a-dog-config") is None


@pytest.mark.parametrize(
    ("dogs_config", "expected_ids"),
    [
        ([{"dog_id": "luna", "dog_name": "Luna"}], ["luna"]),
        (
            [
                {"dog_id": "luna", "dog_name": "Luna"},
                "invalid",
                {"dog_id": "", "dog_name": "Nope"},
                {"dog_id": "milo", "dog_name": "Milo"},
            ],
            ["luna", "milo"],
        ),
    ],
)
def test_coerce_dog_configs_filters_invalid_entries(
    dogs_config: list[object],
    expected_ids: list[str],
) -> None:
    """Only valid entries should survive batch coercion."""
    result = coerce_dog_configs(dogs_config)

    assert [dog["dog_id"] for dog in result] == expected_ids


def test_unwrap_async_result_returns_plain_payload() -> None:
    """Successful gather payloads should pass through unchanged."""
    payload = {"status": "ok"}

    assert unwrap_async_result(payload, context="sync", logger=logging.getLogger(__name__)) == payload


def test_unwrap_async_result_logs_non_cancelled_exception(caplog: pytest.LogCaptureFixture) -> None:
    """Regular exceptions should be logged and converted to None."""
    caplog.set_level(logging.ERROR)
    logger = logging.getLogger("test.dashboard_shared")

    result = unwrap_async_result(
        ValueError("invalid state"),
        context="dashboard refresh",
        logger=logger,
        level=logging.ERROR,
    )

    assert result is None
    assert "dashboard refresh: invalid state" in caplog.text


def test_unwrap_async_result_reraises_cancelled_error_by_default() -> None:
    """Cancelled tasks should be re-raised unless explicitly suppressed."""
    cancelled = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        unwrap_async_result(cancelled, context="refresh", logger=logging.getLogger(__name__))


def test_unwrap_async_result_can_suppress_cancelled(caplog: pytest.LogCaptureFixture) -> None:
    """Suppressed cancellations should be logged and return None."""
    caplog.set_level(logging.WARNING)
    logger = logging.getLogger("test.dashboard_shared.cancelled")

    result = unwrap_async_result(
        asyncio.CancelledError(),
        context="refresh",
        logger=logger,
        suppress_cancelled=True,
    )

    assert result is None
    assert "refresh: task cancelled" in caplog.text
