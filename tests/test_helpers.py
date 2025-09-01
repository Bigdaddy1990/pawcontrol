"""Comprehensive tests for Paw Control helpers module.

This test suite covers all aspects of the helper classes including:
- Data storage and persistence management
- High-level data operations (walks, feedings, health)
- Notification management with priority and quiet hours
- Error handling and data integrity
- Performance characteristics

The helpers module is critical for data management and requires thorough testing.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    DATA_FILE_FEEDINGS,
    DATA_FILE_HEALTH,
    DATA_FILE_ROUTES,
    DATA_FILE_STATS,
    DATA_FILE_WALKS,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    EVENT_HEALTH_LOGGED,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
)
from custom_components.pawcontrol.helpers import (
    STORAGE_VERSION,
    PawControlData,
    PawControlDataStorage,
    PawControlNotificationManager,
    _data_encoder,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import storage
from homeassistant.util import dt as dt_util


# Test fixtures
@pytest.fixture
def mock_config_entry():
    """Mock configuration entry."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    "dog_name": "Test Dog",
                },
                {
                    CONF_DOG_ID: "second_dog",
                    "dog_name": "Second Dog",
                },
            ]
        },
        options={
            CONF_NOTIFICATIONS: {
                CONF_QUIET_HOURS: True,
                CONF_QUIET_START: "22:00:00",
                CONF_QUIET_END: "07:00:00",
            }
        },
        entry_id="test_entry_id",
        source="test",
        unique_id="test_unique_id",
    )


@pytest.fixture
def mock_storage():
    """Mock storage.Store."""
    with patch("homeassistant.helpers.storage.Store") as mock_store_class:
        # Create a mock store instance
        mock_store = AsyncMock()
        mock_store.async_load.return_value = {}
        mock_store.async_save = AsyncMock()

        # Make the Store class return our mock instance
        mock_store_class.return_value = mock_store

        yield {
            "class": mock_store_class,
            "instance": mock_store,
        }


@pytest.fixture
def data_storage(hass: HomeAssistant, mock_config_entry, mock_storage):
    """Create data storage instance."""
    return PawControlDataStorage(hass, mock_config_entry)


@pytest.fixture
def data_manager(hass: HomeAssistant, mock_config_entry):
    """Create data manager instance."""
    return PawControlData(hass, mock_config_entry)


@pytest.fixture
def notification_manager(hass: HomeAssistant, mock_config_entry):
    """Create notification manager instance."""
    with patch("homeassistant.helpers.event.async_track_time_interval"):
        return PawControlNotificationManager(hass, mock_config_entry)


@pytest.fixture
def sample_feeding_data():
    """Sample feeding data for tests."""
    return {
        "meal_type": "breakfast",
        "portion_size": 200.0,
        "food_type": "dry_food",
        "notes": "Normal eating behavior",
    }


@pytest.fixture
def sample_walk_data():
    """Sample walk data for tests."""
    return {
        "start_time": dt_util.utcnow().isoformat(),
        "label": "Morning walk",
        "location": "Park",
        "planned_duration": 30,
    }


@pytest.fixture
def sample_health_data():
    """Sample health data for tests."""
    return {
        "weight": 25.5,
        "temperature": 38.5,
        "mood": "happy",
        "notes": "Regular checkup",
    }


# PawControlDataStorage Tests
class TestPawControlDataStorage:
    """Test data storage functionality."""

    def test_initialization(self, hass: HomeAssistant, mock_config_entry, mock_storage):
        """Test storage initialization."""
        storage_manager = PawControlDataStorage(hass, mock_config_entry)

        assert storage_manager.hass is hass
        assert storage_manager.config_entry is mock_config_entry
        assert (
            len(storage_manager._stores) == 5
        )  # walks, feedings, health, routes, stats

        # Verify stores were created with correct parameters
        expected_stores = ["walks", "feedings", "health", "routes", "statistics"]
        assert set(storage_manager._stores.keys()) == set(expected_stores)

    def test_initialize_stores(
        self, hass: HomeAssistant, mock_config_entry, mock_storage
    ):
        """Test store initialization with correct parameters."""
        PawControlDataStorage(hass, mock_config_entry)

        # Should have created 5 store instances
        assert mock_storage["class"].call_count == 5

        # Check store creation parameters
        calls = mock_storage["class"].call_args_list
        for call_args in calls:
            args, kwargs = call_args
            assert args[0] is hass  # Home Assistant instance
            assert args[1] == STORAGE_VERSION  # Version
            assert args[2].startswith(
                f"{DOMAIN}_{mock_config_entry.entry_id}"
            )  # Key format
            assert kwargs["encoder"] == _data_encoder
            assert kwargs["atomic_writes"] is True

    async def test_load_all_data_success(self, data_storage, mock_storage):
        """Test successful loading of all data."""
        # Mock different data for each store
        mock_data = {
            "walks": {"test_dog": {"active": None, "history": []}},
            "feedings": {"test_dog": [{"meal": "breakfast"}]},
            "health": {"test_dog": [{"weight": 25.0}]},
            "routes": {"test_dog": []},
            "statistics": {"test_dog": {"daily": {}}},
        }

        mock_storage["instance"].async_load.side_effect = lambda: mock_data.get(
            # Extract store key from the call context - simplified approach
            "walks",
            {},
        )

        data = await data_storage.async_load_all_data()

        assert isinstance(data, dict)
        assert len(data) == 5
        assert all(
            store_key in data
            for store_key in ["walks", "feedings", "health", "routes", "statistics"]
        )

    async def test_load_all_data_partial_failure(self, data_storage, mock_storage):
        """Test loading data with some stores failing."""

        def mock_load():
            if mock_load.call_count <= 2:
                mock_load.call_count += 1
                return {"test": "data"}
            else:
                raise Exception("Storage error")

        mock_load.call_count = 0
        mock_storage["instance"].async_load.side_effect = mock_load

        data = await data_storage.async_load_all_data()

        # Should return data structure even with failures
        assert isinstance(data, dict)
        assert len(data) == 5

        # Failed stores should have empty dicts
        failed_stores = [k for k, v in data.items() if v == {}]
        assert len(failed_stores) >= 2  # At least 2 stores should have failed

    async def test_load_all_data_complete_failure(self, data_storage, mock_storage):
        """Test handling when all data loading fails."""
        mock_storage["instance"].async_load.side_effect = Exception("Complete failure")

        with pytest.raises(HomeAssistantError) as exc_info:
            await data_storage.async_load_all_data()

        assert "Data loading failed" in str(exc_info.value)

    async def test_load_store_data_success(self, data_storage, mock_storage):
        """Test loading data from specific store."""
        test_data = {"test": "data"}
        mock_storage["instance"].async_load.return_value = test_data

        data = await data_storage._load_store_data("walks")

        assert data == test_data
        mock_storage["instance"].async_load.assert_called_once()

    async def test_load_store_data_no_data(self, data_storage, mock_storage):
        """Test loading from store with no data."""
        mock_storage["instance"].async_load.return_value = None

        data = await data_storage._load_store_data("walks")

        assert data == {}

    async def test_load_store_data_invalid_store(self, data_storage):
        """Test loading from non-existent store."""
        data = await data_storage._load_store_data("invalid_store")

        assert data == {}

    async def test_save_data_success(self, data_storage, mock_storage):
        """Test successful data saving."""
        test_data = {"test": "data"}

        await data_storage.async_save_data("walks", test_data)

        mock_storage["instance"].async_save.assert_called_once_with(test_data)

    async def test_save_data_invalid_store(self, data_storage):
        """Test saving to invalid store."""
        with pytest.raises(HomeAssistantError) as exc_info:
            await data_storage.async_save_data("invalid_store", {})

        assert "Store invalid_store not found" in str(exc_info.value)

    async def test_save_data_storage_error(self, data_storage, mock_storage):
        """Test handling storage errors during save."""
        mock_storage["instance"].async_save.side_effect = Exception("Storage error")

        with pytest.raises(HomeAssistantError) as exc_info:
            await data_storage.async_save_data("walks", {})

        assert "Failed to save walks data" in str(exc_info.value)

    async def test_cleanup_old_data(self, data_storage, mock_storage):
        """Test cleanup of old data."""
        # Create test data with timestamps
        old_timestamp = (dt_util.utcnow() - timedelta(days=100)).isoformat()
        recent_timestamp = (dt_util.utcnow() - timedelta(days=1)).isoformat()

        test_data = {
            "old_entry": {"timestamp": old_timestamp, "data": "old"},
            "recent_entry": {"timestamp": recent_timestamp, "data": "recent"},
            "no_timestamp": {"data": "keep_this"},
        }

        mock_storage["instance"].async_load.return_value = test_data

        await data_storage.async_cleanup_old_data(retention_days=90)

        # Should have saved cleaned data
        assert mock_storage["instance"].async_save.call_count == 5  # One for each store

        # Check the data that was saved (last call for walks store)
        saved_calls = mock_storage["instance"].async_save.call_args_list
        assert len(saved_calls) > 0

    def test_cleanup_store_data(self, data_storage):
        """Test cleanup logic for store data."""
        cutoff_date = dt_util.utcnow() - timedelta(days=90)
        old_timestamp = (cutoff_date - timedelta(days=1)).isoformat()
        recent_timestamp = (cutoff_date + timedelta(days=1)).isoformat()

        test_data = {
            "old_entry": {"timestamp": old_timestamp, "data": "old"},
            "recent_entry": {"timestamp": recent_timestamp, "data": "recent"},
            "no_timestamp": {"data": "keep"},
            "invalid_timestamp": {"timestamp": "invalid", "data": "keep"},
        }

        cleaned_data = data_storage._cleanup_store_data(test_data, cutoff_date)

        # Should keep recent, no timestamp, and invalid timestamp entries
        assert "old_entry" not in cleaned_data
        assert "recent_entry" in cleaned_data
        assert "no_timestamp" in cleaned_data
        assert "invalid_timestamp" in cleaned_data

    def test_cleanup_store_data_non_dict(self, data_storage):
        """Test cleanup with non-dict data."""
        test_data = "not a dict"
        cutoff_date = dt_util.utcnow()

        result = data_storage._cleanup_store_data(test_data, cutoff_date)

        assert result == "not a dict"


# PawControlData Tests
class TestPawControlData:
    """Test high-level data management functionality."""

    async def test_initialization(self, hass: HomeAssistant, mock_config_entry):
        """Test data manager initialization."""
        data_manager = PawControlData(hass, mock_config_entry)

        assert data_manager.hass is hass
        assert data_manager.config_entry is mock_config_entry
        assert isinstance(data_manager.storage, PawControlDataStorage)
        assert len(data_manager._dogs) == 2

    async def test_load_data_success(self, data_manager):
        """Test successful data loading."""
        test_data = {
            "walks": {},
            "feedings": {},
            "health": {},
            "routes": {},
            "statistics": {},
        }

        with patch.object(
            data_manager.storage, "async_load_all_data", return_value=test_data
        ):
            await data_manager.async_load_data()

            assert data_manager._data == test_data

    async def test_load_data_failure(self, data_manager):
        """Test data loading with storage failure."""
        with patch.object(
            data_manager.storage,
            "async_load_all_data",
            side_effect=Exception("Storage error"),
        ):
            await data_manager.async_load_data()

            # Should initialize with empty data
            expected_keys = ["walks", "feedings", "health", "routes", "statistics"]
            assert all(key in data_manager._data for key in expected_keys)
            assert all(
                isinstance(data_manager._data[key], dict) for key in expected_keys
            )

    async def test_log_feeding_success(
        self, hass: HomeAssistant, data_manager, sample_feeding_data
    ):
        """Test successful feeding logging."""
        with patch.object(data_manager.storage, "async_save_data") as mock_save:
            await data_manager.async_log_feeding("test_dog", sample_feeding_data)

            # Check data structure
            assert "feedings" in data_manager._data
            assert "test_dog" in data_manager._data["feedings"]
            assert len(data_manager._data["feedings"]["test_dog"]) == 1

            # Check feeding data
            logged_feeding = data_manager._data["feedings"]["test_dog"][0]
            assert logged_feeding["meal_type"] == "breakfast"
            assert "timestamp" in logged_feeding

            # Check storage was called
            mock_save.assert_called_once_with(
                "feedings", data_manager._data["feedings"]
            )

    async def test_log_feeding_invalid_dog(self, data_manager, sample_feeding_data):
        """Test feeding logging with invalid dog ID."""
        with pytest.raises(HomeAssistantError) as exc_info:
            await data_manager.async_log_feeding("invalid_dog", sample_feeding_data)

        assert "Invalid dog ID" in str(exc_info.value)

    async def test_log_feeding_with_timestamp(self, data_manager, sample_feeding_data):
        """Test feeding logging with provided timestamp."""
        custom_timestamp = "2025-01-15T12:00:00+00:00"
        sample_feeding_data["timestamp"] = custom_timestamp

        with patch.object(data_manager.storage, "async_save_data"):
            await data_manager.async_log_feeding("test_dog", sample_feeding_data)

            logged_feeding = data_manager._data["feedings"]["test_dog"][0]
            assert logged_feeding["timestamp"] == custom_timestamp

    async def test_log_feeding_fires_event(
        self, hass: HomeAssistant, data_manager, sample_feeding_data
    ):
        """Test that feeding logging fires the correct event."""
        events = []

        def capture_event(event):
            events.append(event)

        hass.bus.async_fire = capture_event

        with patch.object(data_manager.storage, "async_save_data"):
            await data_manager.async_log_feeding("test_dog", sample_feeding_data)

        assert len(events) == 1
        assert events[0] == EVENT_FEEDING_LOGGED
        # Event data would be the second argument in real implementation

    async def test_start_walk_success(
        self, hass: HomeAssistant, data_manager, sample_walk_data
    ):
        """Test successful walk start."""
        with patch.object(data_manager.storage, "async_save_data") as mock_save:
            await data_manager.async_start_walk("test_dog", sample_walk_data)

            # Check data structure
            assert "walks" in data_manager._data
            assert "test_dog" in data_manager._data["walks"]
            assert data_manager._data["walks"]["test_dog"]["active"] == sample_walk_data
            assert "history" in data_manager._data["walks"]["test_dog"]

            # Check storage was called
            mock_save.assert_called_once_with("walks", data_manager._data["walks"])

    async def test_start_walk_already_active(self, data_manager, sample_walk_data):
        """Test starting walk when one is already active."""
        # Set up data with active walk
        data_manager._data = {
            "walks": {
                "test_dog": {
                    "active": {"start_time": "2025-01-15T10:00:00"},
                    "history": [],
                }
            }
        }

        with pytest.raises(HomeAssistantError) as exc_info:
            await data_manager.async_start_walk("test_dog", sample_walk_data)

        assert "Walk already active" in str(exc_info.value)

    async def test_start_walk_invalid_dog(self, data_manager, sample_walk_data):
        """Test starting walk with invalid dog ID."""
        with pytest.raises(HomeAssistantError) as exc_info:
            await data_manager.async_start_walk("invalid_dog", sample_walk_data)

        assert "Invalid dog ID" in str(exc_info.value)

    async def test_end_walk_success(self, hass: HomeAssistant, data_manager):
        """Test successful walk end."""
        # Set up active walk
        start_time = dt_util.utcnow().isoformat()
        active_walk = {
            "start_time": start_time,
            "label": "Test walk",
        }

        data_manager._data = {
            "walks": {"test_dog": {"active": active_walk, "history": []}}
        }

        with patch.object(data_manager.storage, "async_save_data") as mock_save:
            completed_walk = await data_manager.async_end_walk("test_dog")

            assert completed_walk is not None
            assert "end_time" in completed_walk
            assert "duration" in completed_walk
            assert completed_walk["start_time"] == start_time
            assert completed_walk["label"] == "Test walk"

            # Check walk moved to history
            assert data_manager._data["walks"]["test_dog"]["active"] is None
            assert len(data_manager._data["walks"]["test_dog"]["history"]) == 1
            assert (
                data_manager._data["walks"]["test_dog"]["history"][0] == completed_walk
            )

            # Check storage was called
            mock_save.assert_called_once_with("walks", data_manager._data["walks"])

    async def test_end_walk_no_active_walk(self, data_manager):
        """Test ending walk when none is active."""
        data_manager._data = {"walks": {"test_dog": {"active": None, "history": []}}}

        completed_walk = await data_manager.async_end_walk("test_dog")

        assert completed_walk is None

    async def test_end_walk_invalid_dog(self, data_manager):
        """Test ending walk with invalid dog ID."""
        with pytest.raises(HomeAssistantError) as exc_info:
            await data_manager.async_end_walk("invalid_dog")

        assert "Invalid dog ID" in str(exc_info.value)

    async def test_end_walk_duration_calculation(self, data_manager):
        """Test walk duration calculation."""
        start_time = dt_util.utcnow() - timedelta(minutes=30)
        active_walk = {"start_time": start_time.isoformat()}

        data_manager._data = {
            "walks": {"test_dog": {"active": active_walk, "history": []}}
        }

        with patch.object(data_manager.storage, "async_save_data"):
            completed_walk = await data_manager.async_end_walk("test_dog")

            # Duration should be approximately 30 minutes
            assert 25 <= completed_walk["duration"] <= 35

    async def test_log_health_success(
        self, hass: HomeAssistant, data_manager, sample_health_data
    ):
        """Test successful health data logging."""
        with patch.object(data_manager.storage, "async_save_data") as mock_save:
            await data_manager.async_log_health("test_dog", sample_health_data)

            # Check data structure
            assert "health" in data_manager._data
            assert "test_dog" in data_manager._data["health"]
            assert len(data_manager._data["health"]["test_dog"]) == 1

            # Check health data
            logged_health = data_manager._data["health"]["test_dog"][0]
            assert logged_health["weight"] == 25.5
            assert "timestamp" in logged_health

            # Check storage was called
            mock_save.assert_called_once_with("health", data_manager._data["health"])

    async def test_log_health_invalid_dog(self, data_manager, sample_health_data):
        """Test health logging with invalid dog ID."""
        with pytest.raises(HomeAssistantError) as exc_info:
            await data_manager.async_log_health("invalid_dog", sample_health_data)

        assert "Invalid dog ID" in str(exc_info.value)

    async def test_daily_reset_success(self, data_manager):
        """Test successful daily reset."""
        # Set up existing statistics
        data_manager._data = {
            "statistics": {
                "test_dog": {
                    "daily": {
                        "feedings": 3,
                        "walks": 2,
                        "distance": 5.5,
                    }
                }
            }
        }

        with patch.object(data_manager.storage, "async_save_data") as mock_save:
            await data_manager.async_daily_reset()

            # Check statistics were reset
            stats = data_manager._data["statistics"]["test_dog"]
            assert stats["daily"]["feedings"] == 0
            assert stats["daily"]["walks"] == 0
            assert stats["daily"]["distance"] == 0
            assert "reset_time" in stats["daily"]

            # Check history was created
            assert "history" in stats

            # Check storage was called
            mock_save.assert_called_once()

    async def test_daily_reset_all_dogs(self, data_manager):
        """Test daily reset affects all configured dogs."""
        with patch.object(data_manager.storage, "async_save_data"):
            await data_manager.async_daily_reset()

            # Should create statistics for all dogs
            stats = data_manager._data["statistics"]
            assert "test_dog" in stats
            assert "second_dog" in stats

            for dog_id in ["test_dog", "second_dog"]:
                assert "daily" in stats[dog_id]
                assert stats[dog_id]["daily"]["feedings"] == 0

    def test_is_valid_dog_id(self, data_manager):
        """Test dog ID validation."""
        assert data_manager._is_valid_dog_id("test_dog") is True
        assert data_manager._is_valid_dog_id("second_dog") is True
        assert data_manager._is_valid_dog_id("invalid_dog") is False
        assert data_manager._is_valid_dog_id("") is False


# PawControlNotificationManager Tests
class TestPawControlNotificationManager:
    """Test notification management functionality."""

    def test_initialization(self, hass: HomeAssistant, mock_config_entry):
        """Test notification manager initialization."""
        with patch(
            "homeassistant.helpers.event.async_track_time_interval"
        ) as mock_track:
            manager = PawControlNotificationManager(hass, mock_config_entry)

            assert manager.hass is hass
            assert manager.config_entry is mock_config_entry
            assert manager._notification_queue == []

            # Should set up notification processor
            mock_track.assert_called_once()

    async def test_send_notification_normal_priority(self, notification_manager):
        """Test sending normal priority notification."""
        with patch.object(
            notification_manager, "_should_send_notification", return_value=True
        ):
            await notification_manager.async_send_notification(
                "test_dog", "Test Title", "Test Message", priority="normal"
            )

            # Should queue notification, not send immediately
            assert len(notification_manager._notification_queue) == 1
            assert notification_manager._notification_queue[0]["title"] == "Test Title"

    async def test_send_notification_high_priority(self, notification_manager):
        """Test sending high priority notification."""
        with (
            patch.object(
                notification_manager, "_should_send_notification", return_value=True
            ),
            patch.object(notification_manager, "_send_notification_now") as mock_send,
        ):
            await notification_manager.async_send_notification(
                "test_dog", "Urgent Title", "Urgent Message", priority="high"
            )

            # Should send immediately, not queue
            mock_send.assert_called_once()
            assert len(notification_manager._notification_queue) == 0

    async def test_send_notification_urgent_priority(self, notification_manager):
        """Test sending urgent priority notification."""
        with (
            patch.object(
                notification_manager, "_should_send_notification", return_value=True
            ),
            patch.object(notification_manager, "_send_notification_now") as mock_send,
        ):
            await notification_manager.async_send_notification(
                "test_dog", "Emergency Title", "Emergency Message", priority="urgent"
            )

            # Should send immediately
            mock_send.assert_called_once()

    async def test_send_notification_suppressed_quiet_hours(self, notification_manager):
        """Test notification suppression during quiet hours."""
        with patch.object(
            notification_manager, "_should_send_notification", return_value=False
        ):
            await notification_manager.async_send_notification(
                "test_dog", "Test Title", "Test Message"
            )

            # Should not queue notification
            assert len(notification_manager._notification_queue) == 0

    async def test_send_notification_now_success(
        self, hass: HomeAssistant, notification_manager
    ):
        """Test immediate notification sending."""
        notification = {
            "dog_id": "test_dog",
            "title": "Test Title",
            "message": "Test Message",
            "priority": "normal",
            "timestamp": dt_util.utcnow().isoformat(),
        }

        hass.services.async_call = AsyncMock()

        await notification_manager._send_notification_now(notification)

        hass.services.async_call.assert_called_once()
        call_args = hass.services.async_call.call_args
        assert call_args[0][0] == "persistent_notification"
        assert call_args[0][1] == "create"

    async def test_send_notification_now_urgent_styling(
        self, hass: HomeAssistant, notification_manager
    ):
        """Test urgent notification styling."""
        notification = {
            "dog_id": "test_dog",
            "title": "Emergency",
            "message": "Help needed!",
            "priority": "urgent",
            "timestamp": dt_util.utcnow().isoformat(),
        }

        hass.services.async_call = AsyncMock()

        await notification_manager._send_notification_now(notification)

        call_args = hass.services.async_call.call_args
        service_data = call_args[0][2]
        assert "🚨 Help needed!" in service_data["message"]

    async def test_send_notification_now_high_styling(
        self, hass: HomeAssistant, notification_manager
    ):
        """Test high priority notification styling."""
        notification = {
            "dog_id": "test_dog",
            "title": "Important",
            "message": "Attention required",
            "priority": "high",
            "timestamp": dt_util.utcnow().isoformat(),
        }

        hass.services.async_call = AsyncMock()

        await notification_manager._send_notification_now(notification)

        call_args = hass.services.async_call.call_args
        service_data = call_args[0][2]
        assert "⚠️ Attention required" in service_data["message"]

    def test_should_send_notification_urgent_always(self, notification_manager):
        """Test urgent notifications always sent."""
        result = notification_manager._should_send_notification("urgent")
        assert result is True

    def test_should_send_notification_quiet_hours_disabled(self, notification_manager):
        """Test notifications when quiet hours disabled."""
        # Modify config to disable quiet hours
        notification_manager.config_entry.options[CONF_NOTIFICATIONS][
            CONF_QUIET_HOURS
        ] = False

        result = notification_manager._should_send_notification("normal")
        assert result is True

    def test_should_send_notification_quiet_hours_active(self, notification_manager):
        """Test notification suppression during quiet hours."""
        # Mock current time to be in quiet hours (e.g., 23:00)
        with patch("homeassistant.util.dt.now") as mock_now:
            mock_time = Mock()
            mock_time.time.return_value = datetime.strptime(
                "23:00:00", "%H:%M:%S"
            ).time()
            mock_now.return_value = mock_time

            result = notification_manager._should_send_notification("normal")
            assert result is False

    def test_should_send_notification_outside_quiet_hours(self, notification_manager):
        """Test notifications allowed outside quiet hours."""
        # Mock current time to be outside quiet hours (e.g., 12:00)
        with patch("homeassistant.util.dt.now") as mock_now:
            mock_time = Mock()
            mock_time.time.return_value = datetime.strptime(
                "12:00:00", "%H:%M:%S"
            ).time()
            mock_now.return_value = mock_time

            result = notification_manager._should_send_notification("normal")
            assert result is True

    def test_should_send_notification_quiet_hours_span_midnight(
        self, notification_manager
    ):
        """Test quiet hours that span midnight."""
        # Set quiet hours from 22:00 to 07:00 (spans midnight)
        notification_manager.config_entry.options[CONF_NOTIFICATIONS].update(
            {CONF_QUIET_START: "22:00:00", CONF_QUIET_END: "07:00:00"}
        )

        # Test time at 01:00 (should be in quiet hours)
        with patch("homeassistant.util.dt.now") as mock_now:
            mock_time = Mock()
            mock_time.time.return_value = datetime.strptime(
                "01:00:00", "%H:%M:%S"
            ).time()
            mock_now.return_value = mock_time

            result = notification_manager._should_send_notification("normal")
            assert result is False

    def test_should_send_notification_invalid_time_format(self, notification_manager):
        """Test handling of invalid time format in config."""
        # Set invalid time format
        notification_manager.config_entry.options[CONF_NOTIFICATIONS].update(
            {CONF_QUIET_START: "invalid_time", CONF_QUIET_END: "also_invalid"}
        )

        # Should allow notification when times are invalid
        result = notification_manager._should_send_notification("normal")
        assert result is True


# Utility Functions Tests
class TestUtilityFunctions:
    """Test utility functions."""

    def test_data_encoder_datetime(self):
        """Test encoding datetime objects."""
        test_datetime = datetime(2025, 1, 15, 12, 0, 0)
        result = _data_encoder(test_datetime)

        assert isinstance(result, str)
        assert "2025-01-15" in result
        assert "12:00:00" in result

    def test_data_encoder_object_with_dict(self):
        """Test encoding objects with __dict__ attribute."""

        class TestObject:
            def __init__(self):
                self.name = "test"
                self.value = 42

        test_obj = TestObject()
        result = _data_encoder(test_obj)

        assert isinstance(result, dict)
        assert result["name"] == "test"
        assert result["value"] == 42

    def test_data_encoder_simple_object(self):
        """Test encoding simple objects."""
        test_obj = 12345
        result = _data_encoder(test_obj)

        assert result == "12345"

    def test_data_encoder_string_object(self):
        """Test encoding string objects."""
        test_string = "test string"
        result = _data_encoder(test_string)

        assert result == "test string"


# Integration Tests
class TestHelpersIntegration:
    """Test integration between helper classes."""

    async def test_data_manager_with_storage_integration(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test data manager integration with storage."""
        # Create data manager and load initial data
        data_manager = PawControlData(hass, mock_config_entry)

        with (
            patch.object(data_manager.storage, "async_load_all_data", return_value={}),
            patch.object(data_manager.storage, "async_save_data") as mock_save,
        ):
            await data_manager.async_load_data()

            # Log some data
            await data_manager.async_log_feeding("test_dog", {"meal": "breakfast"})
            await data_manager.async_start_walk(
                "test_dog", {"start_time": dt_util.utcnow().isoformat()}
            )
            await data_manager.async_end_walk("test_dog")

            # Should have made multiple save calls
            assert mock_save.call_count >= 3

    async def test_notification_manager_integration(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test notification manager integration with Home Assistant."""
        hass.services.async_call = AsyncMock()

        with patch("homeassistant.helpers.event.async_track_time_interval"):
            manager = PawControlNotificationManager(hass, mock_config_entry)

            # Send various types of notifications
            await manager.async_send_notification(
                "test_dog", "Normal", "Normal message", "normal"
            )
            await manager.async_send_notification(
                "test_dog", "High", "High message", "high"
            )
            await manager.async_send_notification(
                "test_dog", "Urgent", "Urgent message", "urgent"
            )

            # High and urgent should have been sent immediately
            assert hass.services.async_call.call_count == 2

            # Normal should be queued
            assert len(manager._notification_queue) == 1

    async def test_full_workflow_integration(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test full workflow with all helper classes."""
        # Create instances
        data_manager = PawControlData(hass, mock_config_entry)

        hass.services.async_call = AsyncMock()
        events_fired = []
        hass.bus.async_fire = lambda event, data: events_fired.append((event, data))

        with (
            patch.object(data_manager.storage, "async_load_all_data", return_value={}),
            patch.object(data_manager.storage, "async_save_data"),
            patch("homeassistant.helpers.event.async_track_time_interval"),
        ):
            # Initialize data manager
            await data_manager.async_load_data()

            # Create notification manager
            notification_manager = PawControlNotificationManager(
                hass, mock_config_entry
            )

            # Perform various operations
            await data_manager.async_log_feeding("test_dog", {"meal": "breakfast"})
            await data_manager.async_start_walk(
                "test_dog", {"start_time": dt_util.utcnow().isoformat()}
            )

            # Send notification
            await notification_manager.async_send_notification(
                "test_dog", "Walk Started", "Walk has begun!", "high"
            )

            # Check integration worked
            assert len(events_fired) >= 2  # Feeding and walk events
            assert (
                hass.services.async_call.call_count == 1
            )  # High priority notification


# Performance Tests
class TestHelpersPerformance:
    """Test performance characteristics of helper classes."""

    async def test_data_storage_concurrent_operations(self, data_storage):
        """Test concurrent storage operations."""
        with patch.object(data_storage, "_load_store_data", return_value={}):
            # Simulate concurrent loading
            tasks = [data_storage._load_store_data(f"store_{i}") for i in range(10)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 10
            assert all(result == {} for result in results)

    async def test_data_manager_bulk_operations(self, data_manager):
        """Test bulk data operations performance."""
        with patch.object(data_manager.storage, "async_save_data"):
            # Log many feedings
            tasks = [
                data_manager.async_log_feeding("test_dog", {"meal": f"feeding_{i}"})
                for i in range(100)
            ]

            await asyncio.gather(*tasks)

            # Should have 100 feedings logged
            assert len(data_manager._data["feedings"]["test_dog"]) == 100

    async def test_notification_queue_performance(self, notification_manager):
        """Test notification queue with many notifications."""
        # Queue many notifications
        tasks = [
            notification_manager.async_send_notification(
                "test_dog", f"Notification {i}", f"Message {i}", "normal"
            )
            for i in range(1000)
        ]

        await asyncio.gather(*tasks)

        # Should queue all notifications
        assert len(notification_manager._notification_queue) == 1000


# Error Handling and Edge Cases
class TestHelpersErrorHandling:
    """Test error handling and edge cases."""

    async def test_storage_resilience_to_corruption(self, data_storage, mock_storage):
        """Test storage handling of corrupted data."""
        mock_storage["instance"].async_load.side_effect = [
            Exception("Corrupted data"),
            {"valid": "data"},
            None,
            {"another": "valid"},
            Exception("Another error"),
        ]

        # Should handle mixed success/failure gracefully
        data = await data_storage.async_load_all_data()

        assert isinstance(data, dict)
        assert len(data) == 5

    async def test_data_manager_invalid_timestamps(self, data_manager):
        """Test data manager handling of invalid timestamps."""
        with patch.object(data_manager.storage, "async_save_data"):
            # Test with invalid timestamp format
            invalid_feeding = {
                "meal": "breakfast",
                "timestamp": "invalid_timestamp_format",
            }

            # Should not raise exception
            await data_manager.async_log_feeding("test_dog", invalid_feeding)

            # Should have been logged with invalid timestamp
            logged = data_manager._data["feedings"]["test_dog"][0]
            assert logged["timestamp"] == "invalid_timestamp_format"

    async def test_notification_manager_service_failure(
        self, hass: HomeAssistant, notification_manager
    ):
        """Test notification manager handling service failures."""
        hass.services.async_call = AsyncMock(
            side_effect=Exception("Service unavailable")
        )

        notification = {
            "dog_id": "test_dog",
            "title": "Test",
            "message": "Test message",
            "priority": "normal",
            "timestamp": dt_util.utcnow().isoformat(),
        }

        # Should not raise exception
        await notification_manager._send_notification_now(notification)

    async def test_cleanup_with_malformed_data(self, data_storage):
        """Test cleanup with malformed data structures."""
        malformed_data = {
            "valid_entry": {"timestamp": dt_util.utcnow().isoformat(), "data": "good"},
            "no_timestamp": {"data": "keep_this"},
            "null_entry": None,
            "string_entry": "just_a_string",
            "number_entry": 42,
            "malformed_timestamp": {"timestamp": {"nested": "object"}},
        }

        cutoff_date = dt_util.utcnow() - timedelta(days=30)
        cleaned_data = data_storage._cleanup_store_data(malformed_data, cutoff_date)

        # Should handle malformed data gracefully
        assert isinstance(cleaned_data, dict)
        assert "valid_entry" in cleaned_data
        assert "no_timestamp" in cleaned_data
        assert "malformed_timestamp" in cleaned_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
