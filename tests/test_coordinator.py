"""Tests for the Paw Control coordinator module."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiofiles
import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_GPS_UPDATE_INTERVAL,
    DEFAULT_GPS_UPDATE_INTERVAL,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    UPDATE_INTERVALS,
)
from custom_components.pawcontrol.coordinator import (
    PawControlCoordinator,
)
from custom_components.pawcontrol.exceptions import (
    DogNotFoundError,
    GPSUnavailableError,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util


class TestPawControlCoordinator:
    """Test the PawControl coordinator."""

    @pytest.fixture
    def mock_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_GPS: True,
                    },
                }
            ]
        }
        entry.options = {CONF_GPS_UPDATE_INTERVAL: 60}
        return entry

    @pytest.fixture
    def coordinator(self, hass: HomeAssistant, mock_entry):
        """Create a coordinator instance without starting background tasks."""
        # Avoid creating asyncio tasks during tests where no loop is running
        with patch.object(PawControlCoordinator, "_start_background_tasks"):
            return PawControlCoordinator(hass, mock_entry)

    @pytest.mark.asyncio
    async def test_coordinator_initialization(self, hass: HomeAssistant, mock_entry):
        """Test coordinator initialization."""
        coordinator = PawControlCoordinator(hass, mock_entry)

        assert coordinator.hass == hass
        assert coordinator.config_entry == mock_entry
        assert coordinator.name == "Paw Control Data"
        assert coordinator.update_interval.total_seconds() == 60
        assert isinstance(coordinator._dogs_config, list)
        assert len(coordinator._dogs_config) == 1
        assert coordinator._dogs_config[0][CONF_DOG_ID] == "test_dog"

    @pytest.mark.asyncio
    async def test_coordinator_initialization_default_interval(
        self, hass: HomeAssistant
    ):
        """Test coordinator initialization with default interval."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {CONF_DOGS: []}
        entry.options = {}  # No GPS interval specified

        coordinator = PawControlCoordinator(hass, entry)

        assert (
            coordinator.update_interval.total_seconds() == DEFAULT_GPS_UPDATE_INTERVAL
        )

    @pytest.mark.asyncio
    async def test_coordinator_initialization_no_dogs(self, hass: HomeAssistant):
        """Test coordinator initialization with no dogs."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {}  # No dogs
        entry.options = {}

        coordinator = PawControlCoordinator(hass, entry)

        assert coordinator._dogs_config == []

    @pytest.mark.asyncio
    async def test_get_dog_config_found(self, coordinator):
        """Test getting dog configuration when dog exists."""
        config = coordinator.get_dog_config("test_dog")

        assert config is not None
        assert config[CONF_DOG_ID] == "test_dog"
        assert config[CONF_DOG_NAME] == "Test Dog"

    @pytest.mark.asyncio
    async def test_get_dog_config_not_found(self, coordinator):
        """Test getting dog configuration when dog doesn't exist."""
        config = coordinator.get_dog_config("nonexistent_dog")

        assert config is None

    @pytest.mark.asyncio
    async def test_get_enabled_modules(self, coordinator):
        """Test getting enabled modules for a dog."""
        modules = coordinator.get_enabled_modules("test_dog")

        expected_modules = {MODULE_FEEDING, MODULE_WALK, MODULE_HEALTH, MODULE_GPS}
        assert modules == expected_modules

    @pytest.mark.asyncio
    async def test_get_enabled_modules_dog_not_found(self, coordinator):
        """Test getting enabled modules for non-existent dog."""
        modules = coordinator.get_enabled_modules("nonexistent_dog")

        assert modules == set()

    @pytest.mark.asyncio
    async def test_is_module_enabled_true(self, coordinator):
        """Test checking if module is enabled (true case)."""
        assert coordinator.is_module_enabled("test_dog", MODULE_GPS) is True
        assert coordinator.is_module_enabled("test_dog", MODULE_FEEDING) is True

    @pytest.mark.asyncio
    async def test_is_module_enabled_false(self, coordinator):
        """Test checking if module is enabled (false case)."""
        # Add a dog with GPS disabled
        coordinator._dogs_config.append(
            {
                CONF_DOG_ID: "dog_no_gps",
                CONF_DOG_NAME: "Dog No GPS",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: False,
                },
            }
        )

        assert coordinator.is_module_enabled("dog_no_gps", MODULE_GPS) is False
        assert (
            coordinator.is_module_enabled("dog_no_gps", MODULE_HEALTH) is False
        )  # Not in modules

    @pytest.mark.asyncio
    async def test_is_module_enabled_dog_not_found(self, coordinator):
        """Test checking if module is enabled for non-existent dog."""
        assert coordinator.is_module_enabled("nonexistent_dog", MODULE_GPS) is False

    @pytest.mark.asyncio
    async def test_get_dog_ids(self, coordinator):
        """Test getting list of dog IDs."""
        dog_ids = coordinator.get_dog_ids()

        assert dog_ids == ["test_dog"]

    @pytest.mark.asyncio
    async def test_get_dog_ids_multiple_dogs(self, coordinator):
        """Test getting list of dog IDs with multiple dogs."""
        coordinator._dogs_config.append(
            {CONF_DOG_ID: "second_dog", CONF_DOG_NAME: "Second Dog", "modules": {}}
        )

        dog_ids = coordinator.get_dog_ids()

        assert "test_dog" in dog_ids
        assert "second_dog" in dog_ids
        assert len(dog_ids) == 2

    @pytest.mark.asyncio
    async def test_async_update_data_success(self, coordinator):
        """Test successful data update."""
        mock_result = {"test_dog": {"status": "good"}}
        with patch.object(
            coordinator,
            "_process_dog_batch",
            AsyncMock(return_value=mock_result),
        ) as mock_process:
            data = await coordinator._async_update_data()

            assert "test_dog" in data
            assert data["test_dog"]["status"] == "good"
            mock_process.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_update_data_multiple_dogs(self, coordinator):
        """Test data update with multiple dogs."""
        coordinator._dogs_config.append(
            {
                CONF_DOG_ID: "second_dog",
                CONF_DOG_NAME: "Second Dog",
                "modules": {MODULE_FEEDING: True},
            }
        )

        async def mock_fetch(dog_id):
            return {"dog_id": dog_id, "status": "ok"}

        with patch.object(coordinator, "_fetch_dog_data", side_effect=mock_fetch):
            data = await coordinator._async_update_data()

            assert "test_dog" in data
            assert "second_dog" in data
            assert data["test_dog"]["dog_id"] == "test_dog"
            assert data["second_dog"]["dog_id"] == "second_dog"

    @pytest.mark.asyncio
    async def test_async_update_data_parallel_processing(self, coordinator):
        """Test that data updates are processed in parallel."""
        # Add multiple dogs to test parallel processing
        for i in range(3):
            coordinator._dogs_config.append(
                {
                    CONF_DOG_ID: f"dog_{i}",
                    CONF_DOG_NAME: f"Dog {i}",
                    "modules": {MODULE_FEEDING: True},
                }
            )

        call_times = []

        async def mock_fetch(dog_id):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)  # Simulate async work
            return {"dog_id": dog_id}

        with patch.object(coordinator, "_fetch_dog_data", side_effect=mock_fetch):
            start_time = asyncio.get_event_loop().time()
            await coordinator._async_update_data()
            end_time = asyncio.get_event_loop().time()

            # All calls should start nearly simultaneously (parallel processing)
            call_time_spread = max(call_times) - min(call_times)
            assert call_time_spread < 0.05  # Should all start within 50ms

            # Total time should be close to single operation time (0.1s), not sum
            total_time = end_time - start_time
            assert total_time < 0.2  # Much less than 4 * 0.1s

    @pytest.mark.asyncio
    async def test_async_update_data_error_handling(self, coordinator):
        """Test error handling during data update."""

        async def mock_fetch_error(dog_id):
            if dog_id == "test_dog":
                raise Exception("Fetch failed")
            return {"status": "ok"}

        # Add another dog to test partial success
        coordinator._dogs_config.append(
            {
                CONF_DOG_ID: "good_dog",
                CONF_DOG_NAME: "Good Dog",
                "modules": {MODULE_FEEDING: True},
            }
        )

        with patch.object(coordinator, "_fetch_dog_data", side_effect=mock_fetch_error):
            with pytest.raises(UpdateFailed, match="Failed to update data"):
                await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_fetch_dog_data_all_modules(self, coordinator):
        """Test fetching data for dog with all modules enabled."""
        with (
            patch.object(
                coordinator,
                "_fetch_feeding_data",
                return_value={"last_meal": "breakfast"},
            ) as mock_feeding,
            patch.object(
                coordinator, "_fetch_walk_data", return_value={"in_progress": False}
            ) as mock_walk,
            patch.object(
                coordinator, "_fetch_health_data", return_value={"weight": 25.0}
            ) as mock_health,
            patch.object(
                coordinator, "_fetch_gps_data", return_value={"lat": 52.5, "lon": 13.4}
            ) as mock_gps,
        ):
            data = await coordinator._fetch_dog_data("test_dog")

            assert "dog_info" in data
            assert "feeding" in data
            assert "walk" in data
            assert "health" in data
            assert "gps" in data

            assert data["dog_info"]["dog_id"] == "test_dog"
            assert data["feeding"]["last_meal"] == "breakfast"
            assert data["walk"]["in_progress"] is False
            assert data["health"]["weight"] == 25.0
            assert data["gps"]["lat"] == 52.5

            mock_feeding.assert_called_once_with("test_dog")
            mock_walk.assert_called_once_with("test_dog")
            mock_health.assert_called_once_with("test_dog")
            mock_gps.assert_called_once_with("test_dog")

    @pytest.mark.asyncio
    async def test_fetch_dog_data_selective_modules(self, coordinator):
        """Test fetching data for dog with only some modules enabled."""
        # Add dog with only feeding module
        coordinator._dogs_config.append(
            {
                CONF_DOG_ID: "feeding_only_dog",
                CONF_DOG_NAME: "Feeding Only Dog",
                "modules": {MODULE_FEEDING: True},
            }
        )

        with (
            patch.object(
                coordinator, "_fetch_feeding_data", return_value={"meals": 3}
            ) as mock_feeding,
            patch.object(coordinator, "_fetch_walk_data") as mock_walk,
            patch.object(coordinator, "_fetch_health_data") as mock_health,
            patch.object(coordinator, "_fetch_gps_data") as mock_gps,
        ):
            data = await coordinator._fetch_dog_data("feeding_only_dog")

            assert "feeding" in data
            assert "walk" not in data
            assert "health" not in data
            assert "gps" not in data

            mock_feeding.assert_called_once_with("feeding_only_dog")
            mock_walk.assert_not_called()
            mock_health.assert_not_called()
            mock_gps.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_feeding_data_success(self, coordinator):
        """Test successful feeding data fetch."""
        mock_data_manager = AsyncMock()
        mock_data_manager.async_get_dog_data.return_value = {
            "feeding": {
                "last_feeding": "2025-01-15T10:00:00",
                "meals_today": 2,
                "daily_calories": 800,
            }
        }

        coordinator._data_manager = mock_data_manager

        data = await coordinator._fetch_feeding_data("test_dog")

        assert data["last_feeding"] == "2025-01-15T10:00:00"
        assert data["meals_today"] == 2
        assert data["daily_calories"] == 800
        mock_data_manager.async_get_dog_data.assert_called_once_with("test_dog")

    @pytest.mark.asyncio
    async def test_fetch_feeding_data_no_data(self, coordinator):
        """Test feeding data fetch when no data exists."""
        mock_data_manager = AsyncMock()
        mock_data_manager.async_get_dog_data.return_value = None

        coordinator._data_manager = mock_data_manager

        data = await coordinator._fetch_feeding_data("test_dog")

        assert data["last_feeding"] is None
        assert data["meals_today"] == 0
        assert data["daily_calories"] == 0

    @pytest.mark.asyncio
    async def test_fetch_walk_data_success(self, coordinator):
        """Test successful walk data fetch."""
        mock_data_manager = AsyncMock()
        mock_data_manager.async_get_current_walk.return_value = {
            "walk_id": "walk_123",
            "start_time": "2025-01-15T09:00:00",
            "distance": 1500.0,
        }
        mock_data_manager.async_get_dog_data.return_value = {
            "walk": {"walks_today": 1, "daily_distance": 1500.0}
        }

        coordinator._data_manager = mock_data_manager

        data = await coordinator._fetch_walk_data("test_dog")

        assert data["walk_in_progress"] is True
        assert data["current_walk"]["walk_id"] == "walk_123"
        assert data["walks_today"] == 1
        assert data["daily_distance"] == 1500.0

    @pytest.mark.asyncio
    async def test_fetch_walk_data_no_current_walk(self, coordinator):
        """Test walk data fetch when no current walk."""
        mock_data_manager = AsyncMock()
        mock_data_manager.async_get_current_walk.return_value = None
        mock_data_manager.async_get_dog_data.return_value = {"walk": {"walks_today": 2}}

        coordinator._data_manager = mock_data_manager

        data = await coordinator._fetch_walk_data("test_dog")

        assert data["walk_in_progress"] is False
        assert data["current_walk"] is None
        assert data["walks_today"] == 2

    @pytest.mark.asyncio
    async def test_fetch_health_data_success(self, coordinator):
        """Test successful health data fetch."""
        mock_data_manager = AsyncMock()
        mock_data_manager.async_get_dog_data.return_value = {
            "health": {
                "current_weight": 25.5,
                "health_status": "good",
                "mood": "happy",
                "last_vet_visit": "2024-12-01",
            }
        }

        coordinator._data_manager = mock_data_manager

        data = await coordinator._fetch_health_data("test_dog")

        assert data["current_weight"] == 25.5
        assert data["health_status"] == "good"
        assert data["mood"] == "happy"
        assert data["last_vet_visit"] == "2024-12-01"

    @pytest.mark.asyncio
    async def test_fetch_gps_data_success(self, coordinator):
        """Test successful GPS data fetch."""
        mock_data_manager = AsyncMock()
        mock_data_manager.async_get_current_gps_data.return_value = {
            "latitude": 52.5200,
            "longitude": 13.4050,
            "accuracy": 10.0,
            "last_seen": "2025-01-15T11:00:00",
            "source": "device_tracker",
        }

        coordinator._data_manager = mock_data_manager

        data = await coordinator._fetch_gps_data("test_dog")

        assert data["latitude"] == 52.5200
        assert data["longitude"] == 13.4050
        assert data["accuracy"] == 10.0
        assert data["available"] is True
        assert data["source"] == "device_tracker"

    @pytest.mark.asyncio
    async def test_fetch_gps_data_no_manager(self, coordinator):
        """Test GPS data fetch when no data manager is configured."""

        data = await coordinator._fetch_gps_data("test_dog")

        assert data["available"] is False
        assert data["error"] == "GPS data not available"

    @pytest.mark.asyncio
    async def test_fetch_gps_data_unavailable(self, coordinator):
        """Test GPS data fetch when GPS is unavailable."""
        mock_data_manager = AsyncMock()
        mock_data_manager.async_get_current_gps_data.return_value = None

        coordinator._data_manager = mock_data_manager

        data = await coordinator._fetch_gps_data("test_dog")

        assert data["latitude"] is None
        assert data["longitude"] is None
        assert data["available"] is False
        assert data["error"] == "GPS data not available"

    @pytest.mark.asyncio
    async def test_fetch_gps_data_error(self, coordinator):
        """Test GPS data fetch with error."""
        mock_data_manager = AsyncMock()
        mock_data_manager.async_get_current_gps_data.side_effect = GPSUnavailableError(
            "test_dog", "Device offline"
        )

        coordinator._data_manager = mock_data_manager

        data = await coordinator._fetch_gps_data("test_dog")

        assert data["available"] is False
        assert "Device offline" in data["error"]

    @pytest.mark.asyncio
    async def test_async_shutdown(self, coordinator):
        """Test coordinator shutdown."""
        # Mock some background tasks
        coordinator._background_tasks = [AsyncMock(), AsyncMock()]
        coordinator._performance_monitor_task = AsyncMock()
        coordinator._cache_cleanup_task = AsyncMock()

        await coordinator.async_shutdown()

        # Verify all tasks were cancelled and awaited
        for task in coordinator._background_tasks:
            task.cancel.assert_called_once()

        coordinator._performance_monitor_task.cancel.assert_called_once()
        coordinator._cache_cleanup_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_shutdown_with_exceptions(self, coordinator):
        """Test coordinator shutdown with task exceptions."""
        # Mock tasks that raise exceptions when cancelled
        error_task = AsyncMock()
        error_task.cancel.side_effect = Exception("Cancel failed")
        coordinator._background_tasks = [error_task]

        # Should not raise exception even if task cancellation fails
        await coordinator.async_shutdown()

        error_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_interval_calculation(self, hass: HomeAssistant):
        """Test update interval calculation based on dog count and modules."""
        # Test with single dog, basic modules
        entry_single = Mock(spec=ConfigEntry)
        entry_single.data = {
            CONF_DOGS: [{CONF_DOG_ID: "dog1", "modules": {MODULE_FEEDING: True}}]
        }
        entry_single.options = {}

        coordinator_single = PawControlCoordinator(hass, entry_single)
        assert (
            coordinator_single.update_interval.total_seconds()
            == DEFAULT_GPS_UPDATE_INTERVAL
        )

        # Test with multiple dogs and GPS
        entry_multi = Mock(spec=ConfigEntry)
        entry_multi.data = {
            CONF_DOGS: [
                {CONF_DOG_ID: "dog1", "modules": {MODULE_GPS: True}},
                {CONF_DOG_ID: "dog2", "modules": {MODULE_GPS: True}},
                {CONF_DOG_ID: "dog3", "modules": {MODULE_GPS: True}},
            ]
        }
        entry_multi.options = {}

        coordinator_multi = PawControlCoordinator(hass, entry_multi)
        # Should have longer interval for multiple dogs with GPS
        assert (
            coordinator_multi.update_interval.total_seconds()
            >= DEFAULT_GPS_UPDATE_INTERVAL
        )

    @pytest.mark.asyncio
    async def test_data_caching(self, coordinator):
        """Test data caching functionality."""
        # First call should fetch data
        with patch.object(
            coordinator, "_fetch_dog_data", return_value={"cached": True}
        ) as mock_fetch:
            data1 = await coordinator._async_update_data()

            assert mock_fetch.call_count == 1
            assert data1["test_dog"]["cached"] is True

        # Mock cache to test cache hit
        coordinator._cache = {
            "test_dog": {"cached": True, "timestamp": dt_util.utcnow()}
        }
        coordinator._cache_ttl = timedelta(minutes=5)

        with patch.object(coordinator, "_fetch_dog_data"):
            # This should use cached data if caching is implemented
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_performance_optimization(self, coordinator):
        """Test performance optimization features."""
        # Add multiple dogs
        for i in range(5):
            coordinator._dogs_config.append(
                {
                    CONF_DOG_ID: f"dog_{i}",
                    CONF_DOG_NAME: f"Dog {i}",
                    "modules": {MODULE_FEEDING: True, MODULE_GPS: True},
                }
            )

        # Mock fetch to track concurrent execution
        fetch_starts = []
        fetch_ends = []

        async def mock_fetch(dog_id):
            fetch_starts.append((dog_id, asyncio.get_event_loop().time()))
            await asyncio.sleep(0.1)  # Simulate work
            fetch_ends.append((dog_id, asyncio.get_event_loop().time()))
            return {"dog_id": dog_id}

        with patch.object(coordinator, "_fetch_dog_data", side_effect=mock_fetch):
            start_time = asyncio.get_event_loop().time()
            await coordinator._async_update_data()
            end_time = asyncio.get_event_loop().time()

            # Verify parallel execution
            total_time = end_time - start_time
            assert total_time < 0.3  # Should be much less than 6 * 0.1s (sequential)

            # Verify all dogs were processed
            assert len(fetch_starts) == 6  # 1 original + 5 added
            assert len(fetch_ends) == 6

    @pytest.mark.asyncio
    async def test_error_recovery(self, coordinator):
        """Test error recovery mechanisms."""
        error_count = 0

        async def mock_fetch_with_errors(dog_id):
            nonlocal error_count
            error_count += 1
            if error_count <= 2:  # First two calls fail
                raise Exception(f"Temporary error {error_count}")
            return {"recovered": True}

        # Test that errors are properly handled and don't crash the coordinator
        with patch.object(
            coordinator, "_fetch_dog_data", side_effect=mock_fetch_with_errors
        ):
            # First call should fail
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()

            # Second call should also fail
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()

            # Third call should succeed (recovery)
            data = await coordinator._async_update_data()
            assert data["test_dog"]["recovered"] is True

    @pytest.mark.asyncio
    async def test_data_manager_integration(self, coordinator):
        """Test integration with data manager."""
        mock_data_manager = AsyncMock()

        # Set up mock data manager
        coordinator._data_manager = mock_data_manager

        # Test that coordinator properly uses data manager
        mock_data_manager.async_get_dog_data.return_value = {"test": "data"}
        mock_data_manager.async_get_current_walk.return_value = None
        mock_data_manager.async_get_current_gps_data.return_value = None

        await coordinator._fetch_dog_data("test_dog")

        # Verify data manager methods were called
        mock_data_manager.async_get_dog_data.assert_called()
        mock_data_manager.async_get_current_walk.assert_called()
        mock_data_manager.async_get_current_gps_data.assert_called()

    def test_get_update_interval_from_config(self, hass: HomeAssistant):
        """Test getting update interval from configuration."""
        # Test with custom interval
        entry = Mock(spec=ConfigEntry)
        entry.data = {CONF_DOGS: []}
        entry.options = {CONF_GPS_UPDATE_INTERVAL: 90}

        coordinator = PawControlCoordinator(hass, entry)
        assert coordinator.update_interval.total_seconds() == 90

        # Test with interval from UPDATE_INTERVALS
        entry.options = {CONF_GPS_UPDATE_INTERVAL: UPDATE_INTERVALS["frequent"]}
        coordinator = PawControlCoordinator(hass, entry)
        assert (
            coordinator.update_interval.total_seconds() == UPDATE_INTERVALS["frequent"]
        )

    @pytest.mark.asyncio
    async def test_module_data_aggregation(self, coordinator):
        """Test aggregation of data from different modules."""
        # Mock all module fetch methods
        with (
            patch.object(coordinator, "_fetch_feeding_data", return_value={"meals": 3}),
            patch.object(coordinator, "_fetch_walk_data", return_value={"walks": 2}),
            patch.object(
                coordinator, "_fetch_health_data", return_value={"weight": 25.0}
            ),
            patch.object(coordinator, "_fetch_gps_data", return_value={"lat": 52.5}),
        ):
            data = await coordinator._fetch_dog_data("test_dog")

            # Verify all module data is present and properly structured
            assert "dog_info" in data
            assert "feeding" in data
            assert "walk" in data
            assert "health" in data
            assert "gps" in data

            assert data["feeding"]["meals"] == 3
            assert data["walk"]["walks"] == 2
            assert data["health"]["weight"] == 25.0
            assert data["gps"]["lat"] == 52.5

    @pytest.mark.asyncio
    async def test_concurrent_updates(self, coordinator):
        """Test handling of concurrent update requests."""
        update_count = 0

        async def slow_fetch(dog_id):
            nonlocal update_count
            update_count += 1
            await asyncio.sleep(0.1)
            return {"update": update_count}

        with patch.object(coordinator, "_fetch_dog_data", side_effect=slow_fetch):
            # Start multiple concurrent updates
            tasks = [
                coordinator._async_update_data(),
                coordinator._async_update_data(),
                coordinator._async_update_data(),
            ]

            results = await asyncio.gather(*tasks)

            # All updates should complete
            assert len(results) == 3
            for result in results:
                assert "test_dog" in result

    @pytest.mark.asyncio
    async def test_coordinator_context_manager(self, coordinator):
        """Test coordinator can be used as context manager."""
        # Test that coordinator supports async context manager protocol if implemented
        if hasattr(coordinator, "__aenter__"):
            async with coordinator:
                data = await coordinator._async_update_data()
                assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_memory_management(self, coordinator):
        """Test memory management and cleanup."""
        # Add a large number of dogs to test memory handling
        for i in range(100):
            coordinator._dogs_config.append(
                {
                    CONF_DOG_ID: f"stress_dog_{i}",
                    CONF_DOG_NAME: f"Stress Dog {i}",
                    "modules": {MODULE_FEEDING: True},
                }
            )

        # Mock fetch to return data for all dogs
        async def mock_fetch(dog_id):
            return {"dog_id": dog_id, "large_data": "x" * 1000}  # 1KB per dog

        with patch.object(coordinator, "_fetch_dog_data", side_effect=mock_fetch):
            data = await coordinator._async_update_data()

            # Verify all dogs processed
            assert len(data) == 101  # 1 original + 100 added

            # Verify memory usage is reasonable (this is a basic check)
            import sys

            total_size = sys.getsizeof(data)
            assert total_size > 0  # Basic sanity check

    def test_coordinator_string_representation(self, coordinator):
        """Test coordinator string representation."""
        str_repr = str(coordinator)
        assert "PawControlCoordinator" in str_repr
        assert "test_entry" in str_repr or "Test Dog" in str_repr
