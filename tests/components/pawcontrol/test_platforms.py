"""Tests for platform resolution logic in the PawControl integration."""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from typing import cast

import custom_components.pawcontrol as pawcontrol_module
import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_MODULES,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.types import DogConfigData, DogModulesConfig
from homeassistant.const import Platform


def _build_dogs_config(
    modules_per_dog: Iterable[Iterable[str]],
) -> list[DogConfigData]:
    """Create a dogs configuration payload from enabled module sets."""
    return [
        {
            CONF_DOG_ID: f"dog_{index}",
            CONF_DOG_NAME: f"Dog {index}",
            CONF_MODULES: cast(DogModulesConfig, {module: True for module in modules}),
        }
        for index, modules in enumerate(modules_per_dog, start=1)
    ]


@pytest.fixture(autouse=True)
def reload_and_clear_platform_cache() -> None:
    """Reload the module and clear its platform cache before each test."""
    importlib.reload(pawcontrol_module)
    pawcontrol_module._PLATFORM_CACHE.clear()
    yield


@pytest.mark.parametrize(
    ("profile", "modules_per_dog", "expected_platforms"),
    [
        ("advanced", [], {Platform.BUTTON, Platform.SENSOR}),
        ("basic", [set()], {Platform.BUTTON, Platform.SENSOR}),
        (
            "basic",
            [{MODULE_WALK}],
            {Platform.BUTTON, Platform.SENSOR, Platform.BINARY_SENSOR},
        ),
        (
            "basic",
            [{MODULE_NOTIFICATIONS}],
            {Platform.BUTTON, Platform.SENSOR, Platform.SWITCH},
        ),
        (
            "standard",
            [{MODULE_GPS}],
            {
                Platform.BUTTON,
                Platform.SENSOR,
                Platform.SWITCH,
                Platform.BINARY_SENSOR,
                Platform.DEVICE_TRACKER,
                Platform.NUMBER,
            },
        ),
        (
            "standard",
            [{MODULE_HEALTH}],
            {
                Platform.BUTTON,
                Platform.SENSOR,
                Platform.SWITCH,
                Platform.DATE,
                Platform.NUMBER,
                Platform.TEXT,
            },
        ),
        (
            "advanced",
            [
                {MODULE_NOTIFICATIONS, MODULE_GPS},
                {MODULE_WALK, MODULE_FEEDING, MODULE_HEALTH},
            ],
            {
                Platform.BUTTON,
                Platform.SENSOR,
                Platform.SWITCH,
                Platform.BINARY_SENSOR,
                Platform.SELECT,
                Platform.DEVICE_TRACKER,
                Platform.NUMBER,
                Platform.DATE,
                Platform.DATETIME,
                Platform.TEXT,
            },
        ),
        (
            "gps_focus",
            [set()],
            {
                Platform.BUTTON,
                Platform.SENSOR,
                Platform.NUMBER,
            },
        ),
        (
            "health_focus",
            [set()],
            {
                Platform.BUTTON,
                Platform.SENSOR,
                Platform.DATE,
                Platform.NUMBER,
                Platform.TEXT,
            },
        ),
        (
            "mystery",
            [{MODULE_NOTIFICATIONS}],
            {Platform.BUTTON, Platform.SENSOR, Platform.SWITCH},
        ),
    ],
)
def test_get_platforms_for_profile_and_modules(
    profile: str,
    modules_per_dog: Iterable[Iterable[str]],
    expected_platforms: set[Platform],
) -> None:
    """Ensure the helper returns deterministically sorted platforms per scenario."""
    dogs_config = _build_dogs_config(modules_per_dog)

    result = pawcontrol_module.get_platforms_for_profile_and_modules(
        dogs_config, profile
    )

    expected_order = tuple(
        sorted(expected_platforms, key=lambda platform: platform.value)
    )
    assert result == expected_order
