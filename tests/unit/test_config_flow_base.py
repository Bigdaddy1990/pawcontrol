"""Regression tests for the shared config flow helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import CONF_NAME
import pytest

from custom_components.pawcontrol.config_flow_base import PawControlBaseConfigFlow
from custom_components.pawcontrol.types import (
  FeedingSizeDefaults,
  IntegrationNameValidationResult,
)


class _TestFlow(PawControlBaseConfigFlow):
  """Minimal flow subclass exposing the base utilities for testing."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
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
  """Reserved integration names surface a typed validation error payload."""  # noqa: E111

  flow = _TestFlow()  # noqa: E111

  result: IntegrationNameValidationResult = await flow._async_validate_integration_name(  # noqa: E111
    "Home Assistant"
  )

  assert result["valid"] is False  # noqa: E111
  assert result["errors"] == {CONF_NAME: "reserved_integration_name"}  # noqa: E111


@pytest.mark.asyncio
async def test_validate_integration_name_accepts_trimmed() -> None:
  """Whitespace-trimmed names are accepted and return an empty error map."""  # noqa: E111

  flow = _TestFlow()  # noqa: E111

  result: IntegrationNameValidationResult = await flow._async_validate_integration_name(  # noqa: E111
    "  Paw Control  "
  )

  assert result["valid"] is True  # noqa: E111
  assert result["errors"] == {}  # noqa: E111


def test_get_feeding_defaults_by_size_returns_structured_payload() -> None:
  """Feeding defaults expose the typed size payload for scheduler setup."""  # noqa: E111

  flow = _TestFlow()  # noqa: E111

  defaults: FeedingSizeDefaults = flow._get_feeding_defaults_by_size("toy")  # noqa: E111

  assert defaults["meals_per_day"] == 3  # noqa: E111
  assert defaults["daily_food_amount"] == 150  # noqa: E111
  assert defaults["feeding_times"] == ["07:00:00", "12:00:00", "18:00:00"]  # noqa: E111
  assert defaults["portion_size"] == 50  # noqa: E111

  fallback: FeedingSizeDefaults = flow._get_feeding_defaults_by_size("unknown")  # noqa: E111

  assert fallback == flow._get_feeding_defaults_by_size("medium")  # noqa: E111
