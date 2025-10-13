"""Unit tests for the dashboard shared helpers."""

from __future__ import annotations

import asyncio
import logging

import pytest
from custom_components.pawcontrol.dashboard_shared import unwrap_async_result


@pytest.fixture(name="test_logger")
def fixture_test_logger() -> logging.Logger:
    """Return a dedicated logger for test assertions."""

    logger = logging.getLogger("tests.pawcontrol.dashboard_shared")
    return logger


def test_unwrap_async_result_returns_success_payload(test_logger: logging.Logger) -> None:
    """Ensure successful gather results are returned unchanged."""

    payload = {"card": "overview"}

    assert (
        unwrap_async_result(payload, context="overview", logger=test_logger)
        == payload
    )


def test_unwrap_async_result_logs_exceptions(
    caplog: pytest.LogCaptureFixture, test_logger: logging.Logger
) -> None:
    """Gather exceptions should be logged and converted to ``None``."""

    failure = RuntimeError("boom")

    with caplog.at_level(logging.WARNING):
        assert (
            unwrap_async_result(
                failure,
                context="card generation",
                logger=test_logger,
            )
            is None
        )

    assert "card generation" in caplog.text
    assert "boom" in caplog.text


@pytest.mark.parametrize("suppress", [False, True])
def test_unwrap_async_result_cancelled_behaviour(
    caplog: pytest.LogCaptureFixture,
    suppress: bool,
    test_logger: logging.Logger,
) -> None:
    """Verify cancellation handling honours the suppression flag."""

    cancelled = asyncio.CancelledError()

    if suppress:
        with caplog.at_level(logging.DEBUG):
            assert (
                unwrap_async_result(
                    cancelled,
                    context="renderer job",
                    logger=test_logger,
                    level=logging.DEBUG,
                    suppress_cancelled=True,
                )
                is None
            )
        assert "renderer job" in caplog.text
        assert "task cancelled" in caplog.text
        return

    with pytest.raises(asyncio.CancelledError):
        unwrap_async_result(
            cancelled,
            context="renderer job",
            logger=test_logger,
        )

