"""Tests for the async_fire_event helper."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import inspect
import logging
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.pawcontrol.utils import async_fire_event


@pytest.mark.asyncio
async def test_async_fire_event_awaits_async_bus() -> None:
  """Ensure async_fire_event awaits coroutine returning bus calls."""  # noqa: E111

  hass = Mock()  # noqa: E111
  hass.bus = Mock()  # noqa: E111
  hass.bus.async_fire = AsyncMock(return_value=None)  # noqa: E111

  result = await async_fire_event(hass, "pawcontrol_test", {"value": 1})  # noqa: E111

  hass.bus.async_fire.assert_awaited_once()  # noqa: E111
  args, kwargs = hass.bus.async_fire.await_args  # noqa: E111
  assert args == ("pawcontrol_test", {"value": 1})  # noqa: E111
  assert kwargs == {}  # noqa: E111
  assert result is None  # noqa: E111


@pytest.mark.asyncio
async def test_async_fire_event_handles_sync_bus() -> None:
  """Ensure async_fire_event supports synchronous Home Assistant bus APIs."""  # noqa: E111

  hass = Mock()  # noqa: E111
  hass.bus = Mock()  # noqa: E111
  hass.bus.async_fire = Mock(return_value=None)  # noqa: E111

  result = await async_fire_event(hass, "pawcontrol_test", None)  # noqa: E111

  hass.bus.async_fire.assert_called_once_with("pawcontrol_test", None)  # noqa: E111
  assert result is None  # noqa: E111


@pytest.mark.asyncio
async def test_async_fire_event_forwards_kwargs_and_returns_value() -> None:
  """Ensure optional parameters are forwarded and return values are preserved."""  # noqa: E111

  hass = Mock()  # noqa: E111
  hass.bus = Mock()  # noqa: E111
  hass.bus.async_fire = AsyncMock(return_value={"fired": True})  # noqa: E111

  context = object()  # noqa: E111
  origin = object()  # noqa: E111
  fired_at = datetime(2024, 1, 1)  # noqa: E111

  result = await async_fire_event(  # noqa: E111
    hass,
    "pawcontrol_test",
    {"value": 1},
    context=context,
    origin=origin,
    time_fired=fired_at,
  )

  hass.bus.async_fire.assert_awaited_once()  # noqa: E111
  args, kwargs = hass.bus.async_fire.await_args  # noqa: E111
  assert args == ("pawcontrol_test", {"value": 1})  # noqa: E111
  assert kwargs["context"] is context  # noqa: E111
  assert kwargs["origin"] is origin  # noqa: E111
  assert kwargs["time_fired"].tzinfo is UTC  # noqa: E111
  assert kwargs["time_fired"].replace(tzinfo=None) == fired_at  # noqa: E111
  assert result == {"fired": True}  # noqa: E111


@pytest.mark.asyncio
async def test_async_fire_event_normalises_time_fired() -> None:
  """Ensure time metadata is normalised to UTC when forwarded."""  # noqa: E111

  hass = Mock()  # noqa: E111
  hass.bus = Mock()  # noqa: E111
  hass.bus.async_fire = AsyncMock(return_value=None)  # noqa: E111

  naive_timestamp = datetime(2024, 1, 1, 12, 0, 0)  # noqa: E111

  await async_fire_event(  # noqa: E111
    hass,
    "pawcontrol_test",
    {"value": 1},
    time_fired=naive_timestamp,
  )

  hass.bus.async_fire.assert_awaited_once()  # noqa: E111
  _, kwargs = hass.bus.async_fire.await_args  # noqa: E111
  assert kwargs["time_fired"].tzinfo is UTC  # noqa: E111
  assert kwargs["time_fired"].hour == naive_timestamp.hour  # noqa: E111


@pytest.mark.asyncio
async def test_async_fire_event_handles_legacy_signature() -> None:
  """Ensure metadata is skipped when the bus does not support keyword args."""  # noqa: E111

  class LegacyBus:  # noqa: E111
    def __init__(self) -> None:
      self.calls: list[tuple[str, Mapping[str, object] | None]] = []  # noqa: E111

    async def async_fire(
      self, event_type: str, event_data: Mapping[str, object] | None = None
    ) -> str:
      self.calls.append((event_type, event_data))  # noqa: E111
      return "legacy"  # noqa: E111

  hass = Mock()  # noqa: E111
  hass.bus = LegacyBus()  # noqa: E111

  result = await async_fire_event(  # noqa: E111
    hass,
    "pawcontrol_test",
    None,
    context=object(),
    origin=object(),
    time_fired=datetime(2024, 1, 1),
  )

  assert result == "legacy"  # noqa: E111
  assert hass.bus.calls == [("pawcontrol_test", None)]  # noqa: E111


@pytest.mark.asyncio
async def test_async_fire_event_caches_signature(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Ensure repeated calls reuse cached signature inspection."""  # noqa: E111

  hass = Mock()  # noqa: E111
  hass.bus = Mock()  # noqa: E111
  hass.bus.async_fire = AsyncMock(return_value=None)  # noqa: E111

  signature_calls = 0  # noqa: E111
  original_signature = inspect.signature  # noqa: E111

  def _counting_signature(target: object, /):  # noqa: E111
    nonlocal signature_calls
    signature_calls += 1
    return original_signature(target)

  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.utils.inspect.signature", _counting_signature
  )

  for _ in range(3):  # noqa: E111
    await async_fire_event(hass, "pawcontrol_test", None)

  assert signature_calls == 1  # noqa: E111


@pytest.mark.asyncio
async def test_async_fire_event_accepts_iso_timestamp() -> None:
  """Ensure ISO formatted strings are normalised and forwarded."""  # noqa: E111

  hass = Mock()  # noqa: E111
  hass.bus = Mock()  # noqa: E111
  hass.bus.async_fire = AsyncMock(return_value=None)  # noqa: E111

  iso_timestamp = "2024-01-01T08:30:00+00:00"  # noqa: E111

  await async_fire_event(  # noqa: E111
    hass,
    "pawcontrol_test",
    {"value": 1},
    time_fired=iso_timestamp,
  )

  hass.bus.async_fire.assert_awaited_once()  # noqa: E111
  _, kwargs = hass.bus.async_fire.await_args  # noqa: E111
  assert kwargs["time_fired"].tzinfo is UTC  # noqa: E111
  assert kwargs["time_fired"].isoformat().startswith("2024-01-01T08:30:00")  # noqa: E111


@pytest.mark.asyncio
async def test_async_fire_event_accepts_epoch_timestamp() -> None:
  """Ensure Unix epoch seconds are converted to UTC datetimes."""  # noqa: E111

  hass = Mock()  # noqa: E111
  hass.bus = Mock()  # noqa: E111
  hass.bus.async_fire = AsyncMock(return_value=None)  # noqa: E111

  epoch_seconds = 1_700_000_000  # noqa: E111

  await async_fire_event(  # noqa: E111
    hass,
    "pawcontrol_test",
    None,
    time_fired=epoch_seconds,
  )

  hass.bus.async_fire.assert_awaited_once()  # noqa: E111
  _, kwargs = hass.bus.async_fire.await_args  # noqa: E111
  assert kwargs["time_fired"].tzinfo is UTC  # noqa: E111
  assert kwargs["time_fired"].timestamp() == pytest.approx(epoch_seconds)  # noqa: E111


@pytest.mark.asyncio
async def test_async_fire_event_logs_invalid_time_payload(
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Ensure invalid timestamp metadata is ignored with a breadcrumb."""  # noqa: E111

  hass = Mock()  # noqa: E111
  hass.bus = Mock()  # noqa: E111
  hass.bus.async_fire = AsyncMock(return_value=None)  # noqa: E111

  with caplog.at_level(logging.DEBUG, logger="custom_components.pawcontrol.utils"):  # noqa: E111
    await async_fire_event(
      hass,
      "pawcontrol_test",
      None,
      time_fired="not-a-timestamp",
    )

  hass.bus.async_fire.assert_awaited_once()  # noqa: E111
  _, kwargs = hass.bus.async_fire.await_args  # noqa: E111
  assert "time_fired" not in kwargs  # noqa: E111
  assert "Dropping invalid time_fired" in caplog.text  # noqa: E111
