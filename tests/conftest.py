"""Fixtures for Paw Control tests."""
from __future__ import annotations

from unittest.mock import patch
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.config_entries import ConfigEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Paw Control",
        data={},
        options={
            "dogs": [
                {
                    "dog_id": "test_dog",
                    "name": "Test Dog",
                    "breed": "Test Breed",
                    "age": 3,
                    "weight": 20,
                    "size": "medium",
                    "modules": {
                        "walk": True,
                        "feeding": True,
                        "health": True,
                        "gps": False,
                        "notifications": True,
                        "dashboard": True,
                        "grooming": True,
                        "medication": False,
                        "training": False,
                    },
                }
            ],
            "sources": {
                "door_sensor": "binary_sensor.test_door",
                "person_entities": ["person.test"],
                "device_trackers": [],
                "notify_fallback": "notify.test",
                "calendar": None,
                "weather": None,
            },
            "notifications": {
                "quiet_hours": {
                    "start": "22:00:00",
                    "end": "07:00:00",
                },
                "reminder_repeat_min": 30,
                "snooze_min": 15,
            },
            "reset_time": "23:59:00",
            "export_path": "",
            "export_format": "csv",
            "visitor_mode": False,
        },
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the Paw Control integration for testing."""
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    return mock_config_entry


@pytest.fixture
def mock_coordinator():
    """Mock the PawControlCoordinator."""
    with patch(
        "custom_components.pawcontrol.coordinator.PawControlCoordinator"
    ) as mock:
        instance = mock.return_value
        instance.get_dog_data.return_value = {
            "info": {
                "name": "Test Dog",
                "breed": "Test Breed",
                "age": 3,
                "weight": 20,
                "size": "medium",
            },
            "walk": {
                "last_walk": None,
                "walk_in_progress": False,
                "walk_duration_min": 0,
                "walk_distance_m": 0,
                "walks_today": 0,
                "total_distance_today": 0,
                "needs_walk": True,
            },
            "feeding": {
                "last_feeding": None,
                "last_meal_type": None,
                "feedings_today": {
                    "breakfast": 0,
                    "lunch": 0,
                    "dinner": 0,
                    "snack": 0,
                },
                "is_hungry": True,
            },
            "health": {
                "weight_kg": 20,
                "weight_trend": [],
                "last_medication": None,
            },
            "grooming": {
                "last_grooming": None,
                "grooming_type": None,
                "grooming_interval_days": 30,
                "needs_grooming": False,
            },
            "training": {
                "last_training": None,
                "training_sessions_today": 0,
            },
            "activity": {
                "play_duration_today_min": 0,
                "activity_level": "medium",
                "calories_burned_today": 0,
            },
            "location": {
                "is_home": True,
                "distance_from_home": 0,
            },
            "statistics": {
                "poop_count_today": 0,
                "last_action": None,
            },
        }
        yield instance


@pytest.fixture
def mock_notification_router():
    """Mock the NotificationRouter."""
    with patch(
        "custom_components.pawcontrol.helpers.notification_router.NotificationRouter"
    ) as mock:
        instance = mock.return_value
        instance.send_notification.return_value = True
        instance.send_reminder.return_value = True
        yield instance


@pytest.fixture
def mock_setup_sync():
    """Mock the SetupSync."""
    with patch(
        "custom_components.pawcontrol.helpers.setup_sync.SetupSync"
    ) as mock:
        instance = mock.return_value
        instance.sync_all.return_value = None
        instance.cleanup_all.return_value = None
        yield instance
