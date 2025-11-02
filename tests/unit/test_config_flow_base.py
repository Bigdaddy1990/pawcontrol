"""Regression tests for the shared config flow helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from custom_components.pawcontrol.config_flow_base import PawControlBaseConfigFlow
from custom_components.pawcontrol.types import (
    FeedingSizeDefaults,
    IntegrationNameValidationResult,
)
from homeassistant.const import CONF_NAME


class _TestFlow(PawControlBaseConfigFlow):
    """Minimal flow subclass exposing the base utilities for testing."""

    def __init__(self) -> None:
        super().__init__()
        # The config flow only needs ``hass`` for entity lookups, so we provide a
        # lightweight mock that satisfies the attribute contract without touching
        # Home Assistant internals.
        self.hass = MagicMock()
        self.hass.states.async_entity_ids.return_value = []
        self.hass.states.get.return_value = None
        self.hass.services.async_services.return_value = {}


@pytest.mark.asyncio
async def test_validate_integration_name_rejects_reserved() -> None:
    """Reserved integration names surface a typed validation error payload."""

    flow = _TestFlow()

    result: IntegrationNameValidationResult = (
        await flow._async_validate_integration_name("Home Assistant")
    )

    assert result["valid"] is False
    assert result["errors"] == {CONF_NAME: "reserved_integration_name"}


@pytest.mark.asyncio
async def test_validate_integration_name_accepts_trimmed() -> None:
    """Whitespace-trimmed names are accepted and return an empty error map."""

    flow = _TestFlow()

    result: IntegrationNameValidationResult = (
        await flow._async_validate_integration_name("  Paw Control  ")
    )

    assert result["valid"] is True
    assert result["errors"] == {}


def test_get_feeding_defaults_by_size_returns_structured_payload() -> None:
    """Feeding defaults expose the typed size payload for scheduler setup."""

    flow = _TestFlow()

    defaults: FeedingSizeDefaults = flow._get_feeding_defaults_by_size("toy")

    assert defaults["meals_per_day"] == 3
    assert defaults["daily_food_amount"] == 150
    assert defaults["feeding_times"] == ["07:00:00", "12:00:00", "18:00:00"]
    assert defaults["portion_size"] == 50

    fallback: FeedingSizeDefaults = flow._get_feeding_defaults_by_size("unknown")

    assert fallback == flow._get_feeding_defaults_by_size("medium")
