"""Unit tests for the dashboard shared helpers."""

from __future__ import annotations

import asyncio
import logging

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_COLOR,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_WALK,
)
from custom_components.pawcontrol.dashboard_shared import (
    coerce_dog_config,
    coerce_dog_configs,
    unwrap_async_result,
)
from custom_components.pawcontrol.types import DogModulesProjection


@pytest.fixture(name="test_logger")
def fixture_test_logger() -> logging.Logger:
    """Return a dedicated logger for test assertions."""

    logger = logging.getLogger("tests.pawcontrol.dashboard_shared")
    return logger


def test_unwrap_async_result_returns_success_payload(
    test_logger: logging.Logger,
) -> None:
    """Ensure successful gather results are returned unchanged."""

    payload = {"card": "overview"}

    assert (
        unwrap_async_result(payload, context="overview", logger=test_logger) == payload
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


def test_coerce_dog_config_returns_typed_payload() -> None:
    """Raw dog dictionaries should be converted into typed configs."""

    raw_config = {
        CONF_DOG_ID: "alpha",
        CONF_DOG_NAME: "Alpha",
        "modules": {MODULE_WALK: True},
    }

    typed = coerce_dog_config(raw_config)

    assert typed is not None
    assert typed[CONF_DOG_ID] == "alpha"
    modules = typed["modules"]
    assert modules[MODULE_WALK] is True


def test_coerce_dog_configs_filters_invalid_payloads() -> None:
    """Helper should ignore payloads missing identifiers."""

    valid = {
        CONF_DOG_ID: "bravo",
        CONF_DOG_NAME: "Bravo",
    }

    typed = coerce_dog_configs([valid, {CONF_DOG_NAME: "No ID"}, object()])

    assert len(typed) == 1
    assert typed[0][CONF_DOG_ID] == "bravo"


def test_coerce_dog_config_preserves_profile_metadata() -> None:
    """Optional profile metadata should survive repeated coercion."""

    raw_config = {
        CONF_DOG_ID: "charlie",
        CONF_DOG_NAME: "Charlie",
        CONF_DOG_COLOR: "golden",
        "microchip_id": "ABC123",
        "vet_contact": "Dr. Smith",
        "emergency_contact": "555-0101",
    }

    first_pass = coerce_dog_config(raw_config)
    assert first_pass is not None
    assert first_pass[CONF_DOG_COLOR] == "golden"
    assert first_pass["microchip_id"] == "ABC123"
    assert first_pass["vet_contact"] == "Dr. Smith"
    assert first_pass["emergency_contact"] == "555-0101"

    second_pass = coerce_dog_config(first_pass)
    assert second_pass is not None
    # The optional metadata should still be present after re-coercion.
    assert second_pass[CONF_DOG_COLOR] == "golden"
    assert second_pass["microchip_id"] == "ABC123"
    assert second_pass["vet_contact"] == "Dr. Smith"
    assert second_pass["emergency_contact"] == "555-0101"


def test_coerce_dog_config_accepts_module_projection() -> None:
    """Dog module projections should retain toggles during coercion."""

    projection = DogModulesProjection(config={MODULE_WALK: True}, mapping={MODULE_WALK: True})

    raw_config = {
        CONF_DOG_ID: "delta",
        CONF_DOG_NAME: "Delta",
        "modules": projection,
    }

    typed = coerce_dog_config(raw_config)
    assert typed is not None
    modules = typed["modules"]
    assert modules[MODULE_WALK] is True
