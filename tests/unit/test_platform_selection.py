"""Tests for platform selection helpers."""

from collections.abc import Mapping
from unittest.mock import AsyncMock, Mock

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import pytest

import custom_components.pawcontrol as pawcontrol_init
from custom_components.pawcontrol.const import (
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_NOTIFICATIONS,
  MODULE_WALK,
)
from custom_components.pawcontrol.types import DogConfigData


def _build_dog_config(
  modules: Mapping[str, bool],
  *,
  dog_id: str = "buddy",
  dog_name: str = "Buddy",
) -> DogConfigData:
  return {  # noqa: E111
    "dog_id": dog_id,
    "dog_name": dog_name,
    "modules": dict(modules),
  }


def _expected_platforms(*platforms: Platform) -> tuple[Platform, ...]:
  return tuple(sorted(platforms, key=lambda platform: platform.value))  # noqa: E111


@pytest.fixture(autouse=True)
def _clear_platform_cache() -> None:
  pawcontrol_init._PLATFORM_CACHE.clear()  # noqa: E111
  yield  # noqa: E111
  pawcontrol_init._PLATFORM_CACHE.clear()  # noqa: E111


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
      "standard",
      {MODULE_GPS: True, "unknown_module": True},
      _expected_platforms(
        Platform.SENSOR,
        Platform.BUTTON,
        Platform.SWITCH,
        Platform.DEVICE_TRACKER,
        Platform.NUMBER,
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
  dogs = [_build_dog_config(modules)]  # noqa: E111

  platforms = pawcontrol_init.get_platforms_for_profile_and_modules(  # noqa: E111
    dogs,
    profile,
  )

  assert platforms == expected  # noqa: E111


def test_get_platforms_cache_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
  dogs = [_build_dog_config({MODULE_GPS: True})]  # noqa: E111
  profile = "standard"  # noqa: E111
  cache_key = (1, profile, frozenset({MODULE_GPS}))  # noqa: E111

  now_holder: dict[str, float] = {"now": 0.0}  # noqa: E111

  def _now() -> float:  # noqa: E111
    return now_holder["now"]

  monkeypatch.setattr(pawcontrol_init.time, "time", _now)  # noqa: E111

  first_platforms = pawcontrol_init.get_platforms_for_profile_and_modules(  # noqa: E111
    dogs,
    profile,
  )

  cached_platforms, cached_timestamp = pawcontrol_init._PLATFORM_CACHE[cache_key]  # noqa: E111
  assert cached_platforms == first_platforms  # noqa: E111
  assert cached_timestamp == 0.0  # noqa: E111

  now_holder["now"] = pawcontrol_init._CACHE_TTL_SECONDS - 1  # noqa: E111
  second_platforms = pawcontrol_init.get_platforms_for_profile_and_modules(  # noqa: E111
    dogs,
    profile,
  )

  assert second_platforms == first_platforms  # noqa: E111
  _, cached_timestamp = pawcontrol_init._PLATFORM_CACHE[cache_key]  # noqa: E111
  assert cached_timestamp == 0.0  # noqa: E111

  now_holder["now"] = pawcontrol_init._CACHE_TTL_SECONDS + 1  # noqa: E111
  pawcontrol_init.get_platforms_for_profile_and_modules(dogs, profile)  # noqa: E111
  _, refreshed_timestamp = pawcontrol_init._PLATFORM_CACHE[cache_key]  # noqa: E111

  assert refreshed_timestamp == now_holder["now"]  # noqa: E111


def test_get_platforms_cache_key_ignores_unknown_modules() -> None:
  dogs = [_build_dog_config({MODULE_GPS: True, "unknown_module": True})]  # noqa: E111
  profile = "standard"  # noqa: E111

  pawcontrol_init.get_platforms_for_profile_and_modules(dogs, profile)  # noqa: E111

  assert pawcontrol_init._PLATFORM_CACHE  # noqa: E111
  assert list(pawcontrol_init._PLATFORM_CACHE) == [  # noqa: E111
    (1, profile, frozenset({MODULE_GPS}))
  ]


def test_get_platforms_for_empty_dogs_config() -> None:
  platforms = pawcontrol_init.get_platforms_for_profile_and_modules(  # noqa: E111
    [],
    "standard",
  )

  assert platforms == pawcontrol_init._DEFAULT_PLATFORMS  # noqa: E111


def test_get_platforms_for_multiple_dogs() -> None:
  dogs = [  # noqa: E111
    _build_dog_config({MODULE_GPS: True}, dog_id="buddy"),
    _build_dog_config({MODULE_HEALTH: True}, dog_id="lady"),
  ]
  profile = "standard"  # noqa: E111

  platforms = pawcontrol_init.get_platforms_for_profile_and_modules(  # noqa: E111
    dogs,
    profile,
  )

  expected = _expected_platforms(  # noqa: E111
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.DEVICE_TRACKER,
    Platform.NUMBER,
    Platform.DATE,
    Platform.TEXT,
    Platform.BINARY_SENSOR,
  )

  assert platforms == expected  # noqa: E111


def test_platform_cache_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
  max_size = pawcontrol_init._MAX_CACHE_SIZE  # noqa: E111
  ttl = pawcontrol_init._CACHE_TTL_SECONDS  # noqa: E111
  now = 1000.0  # noqa: E111

  monkeypatch.setattr(pawcontrol_init.time, "monotonic", lambda: now)  # noqa: E111

  for idx in range(max_size + 5):  # noqa: E111
    timestamp = now - ttl - 1 if idx < 2 else now - ttl + idx
    cache_key = (idx, "standard", frozenset({f"module_{idx}"}))
    pawcontrol_init._PLATFORM_CACHE[cache_key] = (
      (Platform.SENSOR,),
      timestamp,
    )

  pawcontrol_init._cleanup_platform_cache()  # noqa: E111

  expired_key_one = (0, "standard", frozenset({"module_0"}))  # noqa: E111
  expired_key_two = (1, "standard", frozenset({"module_1"}))  # noqa: E111

  assert expired_key_one not in pawcontrol_init._PLATFORM_CACHE  # noqa: E111
  assert expired_key_two not in pawcontrol_init._PLATFORM_CACHE  # noqa: E111
  assert len(pawcontrol_init._PLATFORM_CACHE) == max_size  # noqa: E111
  for idx in range(2, 5):  # noqa: E111
    cache_key = (idx, "standard", frozenset({f"module_{idx}"}))
    assert cache_key not in pawcontrol_init._PLATFORM_CACHE


@pytest.mark.asyncio
async def test_async_unload_entry_clears_platform_cache(
  hass: HomeAssistant,
) -> None:
  dogs = [_build_dog_config({MODULE_HEALTH: True})]  # noqa: E111
  entry = ConfigEntry(  # noqa: E111
    domain="pawcontrol",
    data={"dogs": dogs},
    options={"entity_profile": "health_focus"},
    title="Test Entry",
  )

  hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)  # noqa: E111
  hass.config_entries.async_get_entry = Mock(return_value=entry)  # noqa: E111

  pawcontrol_init._PLATFORM_CACHE[(1, "health_focus", frozenset({MODULE_HEALTH}))] = (  # noqa: E111
    (Platform.SENSOR,),
    0.0,
  )

  assert pawcontrol_init._PLATFORM_CACHE  # noqa: E111

  result = await pawcontrol_init.async_unload_entry(hass, entry)  # noqa: E111
  assert result is True  # noqa: E111
  assert pawcontrol_init._PLATFORM_CACHE == {}  # noqa: E111
