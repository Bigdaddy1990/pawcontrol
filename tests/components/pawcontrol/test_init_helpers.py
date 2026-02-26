"""Coverage tests for PawControl integration helper functions."""

from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.const import Platform
import pytest

from custom_components.pawcontrol import (
    _DEBUG_LOGGER_ENTRIES,
    _MAX_CACHE_SIZE,
    _PLATFORM_CACHE,
    _WALL_CLOCK_HEURISTIC_THRESHOLD,
    _cleanup_platform_cache,
    _disable_debug_logging,
    _enable_debug_logging,
    get_platforms_for_profile_and_modules,
)


@dataclass
class _DummyEntry:
    entry_id: str
    options: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def _reset_global_state() -> None:
    _PLATFORM_CACHE.clear()
    _DEBUG_LOGGER_ENTRIES.clear()
    logger = logging.getLogger("custom_components.pawcontrol")
    original_level = logger.level
    yield
    _PLATFORM_CACHE.clear()
    _DEBUG_LOGGER_ENTRIES.clear()
    logger.setLevel(original_level)


def test_get_platforms_returns_default_without_dogs(_reset_global_state: None) -> None:
    platforms = get_platforms_for_profile_and_modules([], "standard")

    assert platforms == (
        Platform.BUTTON,
        Platform.SENSOR,
        Platform.SWITCH,
    )


def test_get_platforms_merges_profile_modules_and_uses_cache(
    _reset_global_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 1_000.0
    monkeypatch.setattr("custom_components.pawcontrol.time.time", lambda: now)

    dogs = [
        {
            "modules": {
                "gps": True,
                "health": True,
                "unknown": True,
            }
        }
    ]

    resolved = get_platforms_for_profile_and_modules(dogs, "advanced")

    assert resolved == (
        Platform.BINARY_SENSOR,
        Platform.BUTTON,
        Platform.DATE,
        Platform.DATETIME,
        Platform.DEVICE_TRACKER,
        Platform.NUMBER,
        Platform.SENSOR,
        Platform.TEXT,
    )
    assert len(_PLATFORM_CACHE) == 1

    now += 100.0
    second = get_platforms_for_profile_and_modules(dogs, "advanced")

    assert second is resolved


def test_cleanup_platform_cache_expires_monotonic_and_wall_entries(
    _reset_global_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("custom_components.pawcontrol.time.monotonic", lambda: 900.0)
    monkeypatch.setattr("custom_components.pawcontrol.time.time", lambda: 2_000_000.0)

    # Add enough entries to avoid the short-circuit and trigger cleanup logic.
    for idx in range(_MAX_CACHE_SIZE // 2 + 1):
        _PLATFORM_CACHE[(idx, "profile", frozenset())] = ((Platform.SWITCH,), 850.0)

    # Force one wall-clock-style cache entry older than TTL.
    old_wall_timestamp = _WALL_CLOCK_HEURISTIC_THRESHOLD + 1.0
    _PLATFORM_CACHE[(999, "profile", frozenset({"gps"}))] = (
        (Platform.BUTTON,),
        old_wall_timestamp,
    )

    _cleanup_platform_cache()

    assert (999, "profile", frozenset({"gps"})) not in _PLATFORM_CACHE
    assert len(_PLATFORM_CACHE) <= _MAX_CACHE_SIZE


def test_disable_debug_logging_restores_default_level(
    _reset_global_state: None,
) -> None:
    logger = logging.getLogger("custom_components.pawcontrol")
    logger.setLevel(logging.INFO)

    entry_one = _DummyEntry("entry-one", {"debug_logging": True})
    entry_two = _DummyEntry("entry-two", {"debug_logging": True})

    assert _enable_debug_logging(entry_one) is True
    assert logger.level == logging.DEBUG
    assert "entry-one" in _DEBUG_LOGGER_ENTRIES

    assert _enable_debug_logging(entry_two) is True
    assert "entry-two" in _DEBUG_LOGGER_ENTRIES

    _disable_debug_logging(entry_one)
    assert logger.level == logging.DEBUG

    _disable_debug_logging(entry_two)
    assert logger.level == logging.INFO
    assert not _DEBUG_LOGGER_ENTRIES


def test_enable_debug_logging_returns_false_when_disabled(
    _reset_global_state: None,
) -> None:
    logger = logging.getLogger("custom_components.pawcontrol")
    logger.setLevel(logging.WARNING)

    disabled_entry = _DummyEntry("entry-disabled", {"debug_logging": False})

    assert _enable_debug_logging(disabled_entry) is False
    assert logger.level == logging.WARNING
