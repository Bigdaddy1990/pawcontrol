"""Tests for platform selection helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.const import Platform
from homeassistant.config_entries import ConfigEntry

import custom_components.pawcontrol as pawcontrol_init
from custom_components.pawcontrol.const import (
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_NOTIFICATIONS,
  MODULE_WALK,
)
from custom_components.pawcontrol.types import DogConfigData


def _build_dog_config(modules: Mapping[str, bool]) -> DogConfigData:
  return {
    "dog_id": "buddy",
    "dog_name": "Buddy",
    "modules": dict(modules),
  }


def _expected_platforms(*platforms: Platform) -> tuple[Platform, ...]:
  return tuple(sorted(platforms, key=lambda platform: platform.value))


@pytest.fixture(autouse=True)
def _clear_platform_cache() -> None:
  pawcontrol_init._PLATFORM_CACHE.clear()
  yield
  pawcontrol_init._PLATFORM_CACHE.clear()


@pytest.mark.parametrize(
  ("profile", "modules", "expected"),
  [
    (
      "standard",
      {MODULE_GPS: True, MODULE_FEEDING: True},
      _expected_platforms(
        Platform.SENSOR,
        Platform.BUTTON,
        Platform.SWITCH,
        Platform.DEVICE_TRACKER,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.BINARY_SENSOR,
      ),
    ),
    (
      "gps_focus",
      {MODULE_WALK: True, MODULE_NOTIFICATIONS: True},
      _expected_platforms(
        Platform.SENSOR,
        Platform.BUTTON,
        Platform.NUMBER,
        Platform.SWITCH,
        Platform.BINARY_SENSOR,
      ),
    ),
    (
      "health_focus",
      {MODULE_HEALTH: True},
      _expected_platforms(
        Platform.SENSOR,
        Platform.BUTTON,
        Platform.DATE,
        Platform.NUMBER,
        Platform.TEXT,
      ),
    ),
    (
      "advanced",
      {MODULE_GPS: True, MODULE_HEALTH: True},
      _expected_platforms(
        Platform.SENSOR,
        Platform.BUTTON,
        Platform.DATETIME,
        Platform.DEVICE_TRACKER,
        Platform.NUMBER,
        Platform.BINARY_SENSOR,
        Platform.DATE,
        Platform.TEXT,
      ),
    ),
  ],
)
def test_get_platforms_for_profile_and_modules(
  profile: str,
  modules: Mapping[str, bool],
  expected: tuple[Platform, ...],
) -> None:
  dogs = [_build_dog_config(modules)]

  platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
    dogs,
    profile,
  )

  assert platforms == expected


def test_get_platforms_cache_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
  dogs = [_build_dog_config({MODULE_GPS: True})]
  profile = "standard"
  cache_key = (1, profile, frozenset({MODULE_GPS}))

  now_holder: dict[str, float] = {"now": 0.0}

  def _now() -> float:
    return now_holder["now"]

  monkeypatch.setattr(pawcontrol_init.time, "time", _now)

  first_platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
    dogs,
    profile,
  )

  cached_platforms, cached_timestamp = pawcontrol_init._PLATFORM_CACHE[cache_key]
  assert cached_platforms == first_platforms
  assert cached_timestamp == 0.0

  now_holder["now"] = pawcontrol_init._CACHE_TTL_SECONDS - 1
  second_platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
    dogs,
    profile,
  )

  assert second_platforms == first_platforms
  _, cached_timestamp = pawcontrol_init._PLATFORM_CACHE[cache_key]
  assert cached_timestamp == 0.0

  now_holder["now"] = pawcontrol_init._CACHE_TTL_SECONDS + 1
  pawcontrol_init.get_platforms_for_profile_and_modules(dogs, profile)
  _, refreshed_timestamp = pawcontrol_init._PLATFORM_CACHE[cache_key]

  assert refreshed_timestamp == now_holder["now"]


@pytest.mark.asyncio
async def test_async_unload_entry_clears_platform_cache(
  hass: Any,
) -> None:
  dogs = [_build_dog_config({MODULE_HEALTH: True})]
  entry = ConfigEntry(
    domain="pawcontrol",
    data={"dogs": dogs},
    options={"entity_profile": "health_focus"},
    title="Test Entry",
  )

  hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
  hass.config_entries.async_get_entry = Mock(return_value=entry)

  pawcontrol_init._PLATFORM_CACHE[(1, "health_focus", frozenset({MODULE_HEALTH}))] = (
    (Platform.SENSOR,),
    0.0,
  )

  assert pawcontrol_init._PLATFORM_CACHE

  result = await pawcontrol_init.async_unload_entry(hass, entry)
  assert result is True
  assert pawcontrol_init._PLATFORM_CACHE == {}
