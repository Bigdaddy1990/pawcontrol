"""Shared imports and fixtures for select edge case tests."""

from __future__ import annotations

import asyncio
import gc
import json
import weakref
from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import Optional
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.const import ACTIVITY_LEVELS
from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOG_SIZE
from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.const import DOG_SIZES
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.const import FOOD_TYPES
from custom_components.pawcontrol.const import GPS_SOURCES
from custom_components.pawcontrol.const import HEALTH_STATUS_OPTIONS
from custom_components.pawcontrol.const import MEAL_TYPES
from custom_components.pawcontrol.const import MODULE_FEEDING
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_WALK
from custom_components.pawcontrol.const import MOOD_OPTIONS
from custom_components.pawcontrol.const import PERFORMANCE_MODES
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.select import _async_add_entities_in_batches
from custom_components.pawcontrol.select import _create_base_selects
from custom_components.pawcontrol.select import _create_feeding_selects
from custom_components.pawcontrol.select import _create_gps_selects
from custom_components.pawcontrol.select import _create_health_selects
from custom_components.pawcontrol.select import _create_walk_selects
from custom_components.pawcontrol.select import async_setup_entry
from custom_components.pawcontrol.select import PawControlActivityLevelSelect
from custom_components.pawcontrol.select import PawControlDefaultMealTypeSelect
from custom_components.pawcontrol.select import PawControlDogSizeSelect
from custom_components.pawcontrol.select import PawControlFeedingModeSelect
from custom_components.pawcontrol.select import PawControlFeedingScheduleSelect
from custom_components.pawcontrol.select import PawControlFoodTypeSelect
from custom_components.pawcontrol.select import PawControlGPSSourceSelect
from custom_components.pawcontrol.select import PawControlGroomingTypeSelect
from custom_components.pawcontrol.select import PawControlHealthStatusSelect
from custom_components.pawcontrol.select import PawControlLocationAccuracySelect
from custom_components.pawcontrol.select import PawControlMoodSelect
from custom_components.pawcontrol.select import PawControlNotificationPrioritySelect
from custom_components.pawcontrol.select import PawControlPerformanceModeSelect
from custom_components.pawcontrol.select import PawControlSelectBase
from custom_components.pawcontrol.select import PawControlTrackingModeSelect
from custom_components.pawcontrol.select import PawControlWalkIntensitySelect
from custom_components.pawcontrol.select import PawControlWalkModeSelect
from custom_components.pawcontrol.select import PawControlWeatherPreferenceSelect


@pytest.fixture
def mock_coordinator() -> PawControlCoordinator:
    """Create a mock coordinator for testing."""
    coordinator = MagicMock()
    coordinator.available = True
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.entry_id = "test_entry"
    coordinator.get_dog_data.return_value = {
        "dog_info": {
            "dog_name": "TestDog",
            "dog_breed": "TestBreed",
            "dog_age": 3,
            "dog_size": "medium",
        },
        "modules": {
            MODULE_FEEDING: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
            MODULE_WALK: True,
        },
    }
    coordinator.get_module_data.return_value = {
        "health_status": "good",
        "activity_level": "normal",
    }
    coordinator.async_refresh_dog = AsyncMock()
    return coordinator


@pytest.fixture
def mock_entry() -> ConfigEntry:
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {
        CONF_DOGS: [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "TestDog1",
                CONF_DOG_SIZE: "large",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: False,
                    MODULE_WALK: True,
                },
            }
        ]
    }
    entry.version = 1
    entry.minor_version = 1
    return entry


__all__ = [
    # constants
    "ACTIVITY_LEVELS",
    "CONF_DOGS",
    "CONF_DOG_ID",
    "CONF_DOG_NAME",
    "CONF_DOG_SIZE",
    "DOG_SIZES",
    "DOMAIN",
    "FOOD_TYPES",
    "GPS_SOURCES",
    "HEALTH_STATUS_OPTIONS",
    "MEAL_TYPES",
    "MODULE_FEEDING",
    "MODULE_GPS",
    "MODULE_HEALTH",
    "MODULE_WALK",
    "MOOD_OPTIONS",
    "PERFORMANCE_MODES",
    "STATE_UNAVAILABLE",
    "STATE_UNKNOWN",
    "AddEntitiesCallback",
    "Any",
    "AsyncMock",
    # homeassistant helpers
    "ConfigEntry",
    "ConfigEntryNotReady",
    "DeviceRegistry",
    "EntityRegistry",
    "HomeAssistant",
    "HomeAssistantError",
    "MagicMock",
    "Mock",
    "Optional",
    "PawControlActivityLevelSelect",
    # classes and helpers
    "PawControlCoordinator",
    "PawControlDefaultMealTypeSelect",
    "PawControlDogSizeSelect",
    "PawControlFeedingModeSelect",
    "PawControlFeedingScheduleSelect",
    "PawControlFoodTypeSelect",
    "PawControlGPSSourceSelect",
    "PawControlGroomingTypeSelect",
    "PawControlHealthStatusSelect",
    "PawControlLocationAccuracySelect",
    "PawControlMoodSelect",
    "PawControlNotificationPrioritySelect",
    "PawControlPerformanceModeSelect",
    "PawControlSelectBase",
    "PawControlTrackingModeSelect",
    "PawControlWalkIntensitySelect",
    "PawControlWalkModeSelect",
    "PawControlWeatherPreferenceSelect",
    "_async_add_entities_in_batches",
    "_create_base_selects",
    "_create_feeding_selects",
    "_create_gps_selects",
    "_create_health_selects",
    "_create_walk_selects",
    "async_setup_entry",
    # standard modules and typing helpers
    "asyncio",
    "contextmanager",
    "datetime",
    "dt_util",
    "gc",
    "json",
    # fixtures
    "mock_coordinator",
    "mock_entry",
    "patch",
    "pytest",
    "timedelta",
    "weakref",
]
