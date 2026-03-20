"""Tests for dashboard shared helpers."""

import asyncio
import logging
from unittest.mock import Mock

import pytest

from custom_components.pawcontrol.dashboard_shared import (
    coerce_dog_config,
    coerce_dog_configs,
    unwrap_async_result,
)


def test_coerce_dog_config_normalises_valid_mappings() -> None:
    """Dog config coercion should keep only valid typed dog mappings."""
    dog_config = {
        "dog_id": "buddy",
        "dog_name": "Buddy",
        "dog_weight": 12,
        "dog_color": "brown",
    }

    assert coerce_dog_config(dog_config) == {
        "dog_id": "buddy",
        "dog_name": "Buddy",
        "dog_weight": 12.0,
        "dog_color": "brown",
    }
    assert coerce_dog_config({"dog_id": "buddy"}) is None
    assert coerce_dog_config("not-a-mapping") is None


def test_coerce_dog_configs_filters_invalid_entries() -> None:
    """Only valid dog configurations should survive sequence coercion."""
    dogs_config = [
        {"dog_id": "buddy", "dog_name": "Buddy"},
        {"dog_id": "luna"},
        "invalid",
        {"dog_id": "milo", "dog_name": "Milo", "dog_weight": 9.5},
    ]

    assert coerce_dog_configs(dogs_config) == [
        {"dog_id": "buddy", "dog_name": "Buddy"},
        {"dog_id": "milo", "dog_name": "Milo", "dog_weight": 9.5},
    ]


def test_unwrap_async_result_returns_successful_payload() -> None:
    """Successful gather results should be returned unchanged."""
    logger = Mock()

    assert unwrap_async_result("ok", context="dashboard", logger=logger) == "ok"
    logger.log.assert_not_called()


def test_unwrap_async_result_logs_regular_exceptions() -> None:
    """Non-cancellation failures should be logged and converted to ``None``."""
    logger = Mock()
    error = RuntimeError("boom")

    assert unwrap_async_result(error, context="dashboard", logger=logger) is None

    level, message, context, result = logger.log.call_args.args[:4]
    assert level == logging.WARNING
    assert message == "%s: %s"
    assert context == "dashboard"
    assert result is error
    exc_info = logger.log.call_args.kwargs["exc_info"]
    assert exc_info[0] is RuntimeError
    assert exc_info[1] is error


def test_unwrap_async_result_handles_cancelled_tasks_when_suppressed() -> None:
    """Suppressed cancellations should log a message and return ``None``."""
    logger = Mock()
    cancelled = asyncio.CancelledError()

    assert (
        unwrap_async_result(
            cancelled,
            context="dashboard",
            logger=logger,
            level=logging.ERROR,
            suppress_cancelled=True,
        )
        is None
    )

    assert logger.log.call_args.args == (
        logging.ERROR,
        "%s: task cancelled",
        "dashboard",
    )


def test_unwrap_async_result_reraises_cancelled_tasks_by_default() -> None:
    """Unsuppressed cancellations should propagate to the caller."""
    logger = Mock()

    with pytest.raises(asyncio.CancelledError):
        unwrap_async_result(
            asyncio.CancelledError(),
            context="dashboard",
            logger=logger,
        )

    logger.log.assert_not_called()
