"""Tests for platform selection helpers."""

from collections.abc import Mapping
import logging
from types import SimpleNamespace
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
    return {
        "dog_id": dog_id,
        "dog_name": dog_name,
        "modules": dict(modules),
    }


def _expected_platforms(*platforms: Platform) -> tuple[Platform, ...]:
    return tuple(sorted(platforms, key=lambda platform: platform.value))


@pytest.fixture(autouse=True)
def _clear_platform_cache() -> None:
    pawcontrol_init._PLATFORM_CACHE.clear()
    yield
    pawcontrol_init._PLATFORM_CACHE.clear()


@pytest.fixture(autouse=True)
def _reset_debug_logging_state() -> None:
    logger = logging.getLogger(pawcontrol_init.__package__)
    original_level = logger.level
    original_default = pawcontrol_init._DEFAULT_LOGGER_LEVEL
    pawcontrol_init._DEBUG_LOGGER_ENTRIES.clear()
    yield
    pawcontrol_init._DEBUG_LOGGER_ENTRIES.clear()
    pawcontrol_init._DEFAULT_LOGGER_LEVEL = original_default
    logger.setLevel(original_level)


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


def test_get_platforms_cache_key_ignores_unknown_modules() -> None:
    dogs = [_build_dog_config({MODULE_GPS: True, "unknown_module": True})]
    profile = "standard"

    pawcontrol_init.get_platforms_for_profile_and_modules(dogs, profile)

    assert pawcontrol_init._PLATFORM_CACHE
    assert list(pawcontrol_init._PLATFORM_CACHE) == [
        (1, profile, frozenset({MODULE_GPS}))
    ]


def test_get_platforms_for_empty_dogs_config() -> None:
    platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
        [],
        "standard",
    )

    assert platforms == pawcontrol_init._DEFAULT_PLATFORMS


def test_get_platforms_for_multiple_dogs() -> None:
    dogs = [
        _build_dog_config({MODULE_GPS: True}, dog_id="buddy"),
        _build_dog_config({MODULE_HEALTH: True}, dog_id="lady"),
    ]
    profile = "standard"

    platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
        dogs,
        profile,
    )

    expected = _expected_platforms(
        Platform.SENSOR,
        Platform.BUTTON,
        Platform.SWITCH,
        Platform.DEVICE_TRACKER,
        Platform.NUMBER,
        Platform.DATE,
        Platform.TEXT,
        Platform.BINARY_SENSOR,
    )

    assert platforms == expected


def test_platform_cache_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    max_size = pawcontrol_init._MAX_CACHE_SIZE
    ttl = pawcontrol_init._CACHE_TTL_SECONDS
    now = 1000.0

    monkeypatch.setattr(pawcontrol_init.time, "monotonic", lambda: now)

    for idx in range(max_size + 5):
        timestamp = now - ttl - 1 if idx < 2 else now - ttl + idx
        cache_key = (idx, "standard", frozenset({f"module_{idx}"}))
        pawcontrol_init._PLATFORM_CACHE[cache_key] = (
            (Platform.SENSOR,),
            timestamp,
        )

    pawcontrol_init._cleanup_platform_cache()

    expired_key_one = (0, "standard", frozenset({"module_0"}))
    expired_key_two = (1, "standard", frozenset({"module_1"}))

    assert expired_key_one not in pawcontrol_init._PLATFORM_CACHE
    assert expired_key_two not in pawcontrol_init._PLATFORM_CACHE
    assert len(pawcontrol_init._PLATFORM_CACHE) == max_size
    for idx in range(2, 5):
        cache_key = (idx, "standard", frozenset({f"module_{idx}"}))
        assert cache_key not in pawcontrol_init._PLATFORM_CACHE


def test_platform_cache_cleanup_short_circuits_below_half_capacity() -> None:
    half_capacity = pawcontrol_init._MAX_CACHE_SIZE // 2
    cache_key = (1, "standard", frozenset({MODULE_GPS}))
    pawcontrol_init._PLATFORM_CACHE[cache_key] = ((Platform.SENSOR,), 0.0)

    assert len(pawcontrol_init._PLATFORM_CACHE) < half_capacity
    pawcontrol_init._cleanup_platform_cache()
    assert cache_key in pawcontrol_init._PLATFORM_CACHE


def test_platform_cache_cleanup_uses_wall_clock_for_large_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_wall = 2_000_000_000.0
    now_monotonic = 1_000.0
    ttl = pawcontrol_init._CACHE_TTL_SECONDS

    monkeypatch.setattr(pawcontrol_init.time, "time", lambda: now_wall)
    monkeypatch.setattr(pawcontrol_init.time, "monotonic", lambda: now_monotonic)

    for idx in range(pawcontrol_init._MAX_CACHE_SIZE // 2):
        key = (idx, "standard", frozenset({f"module_{idx}"}))
        pawcontrol_init._PLATFORM_CACHE[key] = ((Platform.SENSOR,), now_monotonic)

    wall_expired_key = (9999, "standard", frozenset({"wall_expired"}))
    pawcontrol_init._PLATFORM_CACHE[wall_expired_key] = (
        (Platform.SWITCH,),
        now_wall - ttl - 1,
    )

    pawcontrol_init._cleanup_platform_cache()

    assert wall_expired_key not in pawcontrol_init._PLATFORM_CACHE


def test_enable_and_disable_debug_logging_restores_logger_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_logger = Mock()
    package_logger.level = logging.INFO

    monkeypatch.setattr(
        pawcontrol_init.logging, "getLogger", lambda *_args: package_logger
    )

    entry = SimpleNamespace(entry_id="entry-debug", options={"debug_logging": True})

    assert pawcontrol_init._enable_debug_logging(entry) is True
    assert package_logger.setLevel.call_args_list[0].args == (logging.DEBUG,)

    pawcontrol_init._disable_debug_logging(entry)
    assert package_logger.setLevel.call_args_list[-1].args == (logging.INFO,)


def test_disable_debug_logging_keeps_debug_when_other_entries_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_logger = Mock()
    package_logger.level = logging.WARNING

    monkeypatch.setattr(
        pawcontrol_init.logging, "getLogger", lambda *_args: package_logger
    )

    first_entry = SimpleNamespace(entry_id="entry-1", options={"debug_logging": True})
    second_entry = SimpleNamespace(entry_id="entry-2", options={"debug_logging": True})

    assert pawcontrol_init._enable_debug_logging(first_entry) is True
    assert pawcontrol_init._enable_debug_logging(second_entry) is True

    pawcontrol_init._disable_debug_logging(first_entry)
    assert package_logger.setLevel.call_args_list[-1].args == (logging.DEBUG,)

    pawcontrol_init._disable_debug_logging(second_entry)
    assert package_logger.setLevel.call_args_list[-1].args == (logging.WARNING,)


@pytest.mark.asyncio
async def test_async_unload_entry_clears_platform_cache(
    hass: HomeAssistant,
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
