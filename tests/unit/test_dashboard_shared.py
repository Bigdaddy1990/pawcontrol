"""Unit tests for the dashboard shared helpers."""

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
    """Return a dedicated logger for test assertions."""  # noqa: E111

    logger = logging.getLogger("tests.pawcontrol.dashboard_shared")  # noqa: E111
    return logger  # noqa: E111


def test_unwrap_async_result_returns_success_payload(
    test_logger: logging.Logger,
) -> None:
    """Ensure successful gather results are returned unchanged."""  # noqa: E111

    payload = {"card": "overview"}  # noqa: E111

    assert (
        unwrap_async_result(payload, context="overview", logger=test_logger) == payload
    )  # noqa: E111


def test_unwrap_async_result_logs_exceptions(
    caplog: pytest.LogCaptureFixture, test_logger: logging.Logger
) -> None:
    """Gather exceptions should be logged and converted to ``None``."""  # noqa: E111

    failure = RuntimeError("boom")  # noqa: E111

    with caplog.at_level(logging.WARNING):  # noqa: E111
        assert (
            unwrap_async_result(
                failure,
                context="card generation",
                logger=test_logger,
            )
            is None
        )

    assert "card generation" in caplog.text  # noqa: E111
    assert "boom" in caplog.text  # noqa: E111


@pytest.mark.parametrize("suppress", [False, True])
def test_unwrap_async_result_cancelled_behaviour(
    caplog: pytest.LogCaptureFixture,
    suppress: bool,
    test_logger: logging.Logger,
) -> None:
    """Verify cancellation handling honours the suppression flag."""  # noqa: E111

    cancelled = asyncio.CancelledError()  # noqa: E111

    if suppress:  # noqa: E111
        with caplog.at_level(logging.DEBUG):
            assert (  # noqa: E111
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

    with pytest.raises(asyncio.CancelledError):  # noqa: E111
        unwrap_async_result(
            cancelled,
            context="renderer job",
            logger=test_logger,
        )


def test_coerce_dog_config_returns_typed_payload() -> None:
    """Raw dog dictionaries should be converted into typed configs."""  # noqa: E111

    raw_config = {  # noqa: E111
        CONF_DOG_ID: "alpha",
        CONF_DOG_NAME: "Alpha",
        "modules": {MODULE_WALK: True},
    }

    typed = coerce_dog_config(raw_config)  # noqa: E111

    assert typed is not None  # noqa: E111
    assert typed[CONF_DOG_ID] == "alpha"  # noqa: E111
    modules = typed["modules"]  # noqa: E111
    assert modules[MODULE_WALK] is True  # noqa: E111


def test_coerce_dog_configs_filters_invalid_payloads() -> None:
    """Helper should ignore payloads missing identifiers."""  # noqa: E111

    valid = {  # noqa: E111
        CONF_DOG_ID: "bravo",
        CONF_DOG_NAME: "Bravo",
    }

    typed = coerce_dog_configs([valid, {CONF_DOG_NAME: "No ID"}, object()])  # noqa: E111

    assert len(typed) == 1  # noqa: E111
    assert typed[0][CONF_DOG_ID] == "bravo"  # noqa: E111


def test_coerce_dog_config_preserves_profile_metadata() -> None:
    """Optional profile metadata should survive repeated coercion."""  # noqa: E111

    raw_config = {  # noqa: E111
        CONF_DOG_ID: "charlie",
        CONF_DOG_NAME: "Charlie",
        CONF_DOG_COLOR: "golden",
        "microchip_id": "ABC123",
        "vet_contact": "Dr. Smith",
        "emergency_contact": "555-0101",
    }

    first_pass = coerce_dog_config(raw_config)  # noqa: E111
    assert first_pass is not None  # noqa: E111
    assert first_pass[CONF_DOG_COLOR] == "golden"  # noqa: E111
    assert first_pass["microchip_id"] == "ABC123"  # noqa: E111
    assert first_pass["vet_contact"] == "Dr. Smith"  # noqa: E111
    assert first_pass["emergency_contact"] == "555-0101"  # noqa: E111

    second_pass = coerce_dog_config(first_pass)  # noqa: E111
    assert second_pass is not None  # noqa: E111
    # The optional metadata should still be present after re-coercion.  # noqa: E114
    assert second_pass[CONF_DOG_COLOR] == "golden"  # noqa: E111
    assert second_pass["microchip_id"] == "ABC123"  # noqa: E111
    assert second_pass["vet_contact"] == "Dr. Smith"  # noqa: E111
    assert second_pass["emergency_contact"] == "555-0101"  # noqa: E111


def test_coerce_dog_config_accepts_module_projection() -> None:
    """Dog module projections should retain toggles during coercion."""  # noqa: E111

    projection = DogModulesProjection(  # noqa: E111
        config={MODULE_WALK: True}, mapping={MODULE_WALK: True}
    )

    raw_config = {  # noqa: E111
        CONF_DOG_ID: "delta",
        CONF_DOG_NAME: "Delta",
        "modules": projection,
    }

    typed = coerce_dog_config(raw_config)  # noqa: E111
    assert typed is not None  # noqa: E111
    modules = typed["modules"]  # noqa: E111
    assert modules[MODULE_WALK] is True  # noqa: E111
