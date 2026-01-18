"""Tests for the async_fire_event helper."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from custom_components.pawcontrol.utils import async_fire_event


@pytest.mark.asyncio
async def test_async_fire_event_awaits_async_bus() -> None:
  """Ensure async_fire_event awaits coroutine returning bus calls."""

  hass = Mock()
  hass.bus = Mock()
  hass.bus.async_fire = AsyncMock(return_value=None)

  result = await async_fire_event(hass, "pawcontrol_test", {"value": 1})

  hass.bus.async_fire.assert_awaited_once()
  args, kwargs = hass.bus.async_fire.await_args
  assert args == ("pawcontrol_test", {"value": 1})
  assert kwargs == {}
  assert result is None


@pytest.mark.asyncio
async def test_async_fire_event_handles_sync_bus() -> None:
  """Ensure async_fire_event supports synchronous Home Assistant bus APIs."""

  hass = Mock()
  hass.bus = Mock()
  hass.bus.async_fire = Mock(return_value=None)

  result = await async_fire_event(hass, "pawcontrol_test", None)

  hass.bus.async_fire.assert_called_once_with("pawcontrol_test", None)
  assert result is None


@pytest.mark.asyncio
async def test_async_fire_event_forwards_kwargs_and_returns_value() -> None:
  """Ensure optional parameters are forwarded and return values are preserved."""

  hass = Mock()
  hass.bus = Mock()
  hass.bus.async_fire = AsyncMock(return_value={"fired": True})

  context = object()
  origin = object()
  fired_at = datetime(2024, 1, 1)

  result = await async_fire_event(
    hass,
    "pawcontrol_test",
    {"value": 1},
    context=context,
    origin=origin,
    time_fired=fired_at,
  )

  hass.bus.async_fire.assert_awaited_once()
  args, kwargs = hass.bus.async_fire.await_args
  assert args == ("pawcontrol_test", {"value": 1})
  assert kwargs["context"] is context
  assert kwargs["origin"] is origin
  assert kwargs["time_fired"].tzinfo is UTC
  assert kwargs["time_fired"].replace(tzinfo=None) == fired_at
  assert result == {"fired": True}


@pytest.mark.asyncio
async def test_async_fire_event_normalises_time_fired() -> None:
  """Ensure time metadata is normalised to UTC when forwarded."""

  hass = Mock()
  hass.bus = Mock()
  hass.bus.async_fire = AsyncMock(return_value=None)

  naive_timestamp = datetime(2024, 1, 1, 12, 0, 0)

  await async_fire_event(
    hass,
    "pawcontrol_test",
    {"value": 1},
    time_fired=naive_timestamp,
  )

  hass.bus.async_fire.assert_awaited_once()
  _, kwargs = hass.bus.async_fire.await_args
  assert kwargs["time_fired"].tzinfo is UTC
  assert kwargs["time_fired"].hour == naive_timestamp.hour


@pytest.mark.asyncio
async def test_async_fire_event_handles_legacy_signature() -> None:
  """Ensure metadata is skipped when the bus does not support keyword args."""

  class LegacyBus:
    def __init__(self) -> None:
      self.calls: list[tuple[str, Mapping[str, object] | None]] = []

    async def async_fire(
      self, event_type: str, event_data: Mapping[str, object] | None = None
    ) -> str:
      self.calls.append((event_type, event_data))
      return "legacy"

  hass = Mock()
  hass.bus = LegacyBus()

  result = await async_fire_event(
    hass,
    "pawcontrol_test",
    None,
    context=object(),
    origin=object(),
    time_fired=datetime(2024, 1, 1),
  )

  assert result == "legacy"
  assert hass.bus.calls == [("pawcontrol_test", None)]


@pytest.mark.asyncio
async def test_async_fire_event_caches_signature(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Ensure repeated calls reuse cached signature inspection."""

  hass = Mock()
  hass.bus = Mock()
  hass.bus.async_fire = AsyncMock(return_value=None)

  signature_calls = 0
  original_signature = inspect.signature

  def _counting_signature(target: object, /):
    nonlocal signature_calls
    signature_calls += 1
    return original_signature(target)

  monkeypatch.setattr(
    "custom_components.pawcontrol.utils.inspect.signature", _counting_signature
  )

  for _ in range(3):
    await async_fire_event(hass, "pawcontrol_test", None)

  assert signature_calls == 1


@pytest.mark.asyncio
async def test_async_fire_event_accepts_iso_timestamp() -> None:
  """Ensure ISO formatted strings are normalised and forwarded."""

  hass = Mock()
  hass.bus = Mock()
  hass.bus.async_fire = AsyncMock(return_value=None)

  iso_timestamp = "2024-01-01T08:30:00+00:00"

  await async_fire_event(
    hass,
    "pawcontrol_test",
    {"value": 1},
    time_fired=iso_timestamp,
  )

  hass.bus.async_fire.assert_awaited_once()
  _, kwargs = hass.bus.async_fire.await_args
  assert kwargs["time_fired"].tzinfo is UTC
  assert kwargs["time_fired"].isoformat().startswith("2024-01-01T08:30:00")


@pytest.mark.asyncio
async def test_async_fire_event_accepts_epoch_timestamp() -> None:
  """Ensure Unix epoch seconds are converted to UTC datetimes."""

  hass = Mock()
  hass.bus = Mock()
  hass.bus.async_fire = AsyncMock(return_value=None)

  epoch_seconds = 1_700_000_000

  await async_fire_event(
    hass,
    "pawcontrol_test",
    None,
    time_fired=epoch_seconds,
  )

  hass.bus.async_fire.assert_awaited_once()
  _, kwargs = hass.bus.async_fire.await_args
  assert kwargs["time_fired"].tzinfo is UTC
  assert kwargs["time_fired"].timestamp() == pytest.approx(epoch_seconds)


@pytest.mark.asyncio
async def test_async_fire_event_logs_invalid_time_payload(
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Ensure invalid timestamp metadata is ignored with a breadcrumb."""

  hass = Mock()
  hass.bus = Mock()
  hass.bus.async_fire = AsyncMock(return_value=None)

  with caplog.at_level(logging.DEBUG, logger="custom_components.pawcontrol.utils"):
    await async_fire_event(
      hass,
      "pawcontrol_test",
      None,
      time_fired="not-a-timestamp",
    )

  hass.bus.async_fire.assert_awaited_once()
  _, kwargs = hass.bus.async_fire.await_args
  assert "time_fired" not in kwargs
  assert "Dropping invalid time_fired" in caplog.text
