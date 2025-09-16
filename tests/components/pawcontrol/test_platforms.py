"""Tests for platform resolution logic in the PawControl integration."""

from __future__ import annotations

import importlib

import custom_components.pawcontrol as pawcontrol_module
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from homeassistant.const import Platform


def test_get_platforms_sorted_deterministically() -> None:
    """Ensure the helper returns platforms in deterministic sorted order."""
    importlib.reload(pawcontrol_module)
    pawcontrol_module._PLATFORM_CACHE.clear()

    dogs_config = [
        {
            CONF_DOG_ID: "alpha",
            "modules": {
                MODULE_NOTIFICATIONS: True,
                MODULE_GPS: True,
                MODULE_WALK: True,
                MODULE_FEEDING: True,
                MODULE_HEALTH: True,
            },
        },
        {
            CONF_DOG_ID: "beta",
            "modules": {
                MODULE_WALK: True,
                MODULE_GPS: True,
                MODULE_HEALTH: True,
            },
        },
    ]

    result = pawcontrol_module.get_platforms_for_profile_and_modules(
        dogs_config, "advanced"
    )

    expected_platforms = {
        Platform.BUTTON,
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.SWITCH,
        Platform.SELECT,
        Platform.DEVICE_TRACKER,
        Platform.NUMBER,
        Platform.DATE,
        Platform.DATETIME,
        Platform.TEXT,
    }
    expected_order = tuple(
        sorted(expected_platforms, key=lambda platform: platform.value)
    )

    assert result == expected_order
