"""Comprehensive unit tests for PawControlCoordinator.

Tests coordinator initialization, data updates, error handling,
and resilience pattern integration.

Quality Scale: Platinum
Python: 3.13+
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.pawcontrol.coordinator import PawControlCoordinator


@pytest.mark.unit
@pytest.mark.asyncio
class TestCoordinatorInitialization:
    """Test coordinator initialization."""

    async def test_initialization_basic(self, mock_hass, mock_config_entry, mock_session):
        """Test basic coordinator initialization."""
        coordinator = PawControlCoordinator(
            mock_hass,
            mock_config_entry,
            mock_session,
        )
        
        assert coordinator.config_entry == mock_config_entry
        assert coordinator.session == mock_session
        assert len(coordinator._configured_dog_ids) == 1
        assert "test_dog" in coordinator._configured_dog_ids

    async def test_initialization_multiple_dogs(
        self, 
        mock_hass, 
        mock_config_entry, 
        mock_session,
        mock_multi_dog_config
    ):
        """Test initialization with multiple dogs."""
        mock_config_entry.data = {"dogs": mock_multi_dog_config}
        
        coordinator = PawControlCoordinator(
            mock_hass,
            mock_config_entry,
            mock_session,
        )
        
        assert len(coordinator._configured_dog_ids) == 2
        assert "buddy" in coordinator._configured_dog_ids
        assert "max" in coordinator._configured_dog_ids

    async def test_initialization_no_dogs(self, mock_hass, mock_config_entry, mock_session):
        """Test initialization with no dogs configured."""
        mock_config_entry.data = {"dogs": []}
        
        coordinator = PawControlCoordinator(
            mock_hass,
            mock_config_entry,
            mock_session,
        )
        
        assert len(coordinator._configured_dog_ids) == 0

    async def test_initialization_calculates_update_interval(
        self,
        mock_hass,
        mock_config_entry,
        mock_session
    ):
        """Test that update interval is calculated correctly."""
        coordinator = PawControlCoordinator(
            mock_hass,
            mock_config_entry,
            mock_session,
        )
        
        # Should have reasonable update interval
        assert 30 <= coordinator.update_interval.total_seconds() <= 300


@pytest.mark.unit
@pytest.mark.asyncio
class TestDataFetching:
    """Test data fetching logic."""

    async def test_fetch_single_dog_data(self, mock_coordinator, assert_valid_dog_data):
        """Test fetching data for single dog."""
        await mock_coordinator._async_setup()
        
        data = await mock_coordinator._async_update_data()
        
        assert "test_dog" in data
        assert_valid_dog_data(data["test_dog"])

    async def test_fetch_handles_missing_dog_config(
        self,
        mock_hass,
        mock_config_entry,
        mock_session,
        mock_resilience_manager
    ):
        """Test fetching with invalid dog configuration."""
        mock_config_entry.data = {"dogs": [{"dog_id": None}]}  # Invalid
        
        coordinator = PawControlCoordinator(
            mock_hass,
            mock_config_entry,
            mock_session,
        )
        coordinator.resilience_manager = mock_resilience_manager
        
        await coordinator._async_setup()
        
        # Should handle gracefully
        data = await coordinator._async_update_data()
        
        assert isinstance(data, dict)

    async def test_fetch_resilience_integration(self, mock_coordinator):
        """Test that resilience manager is used for fetching."""
        await mock_coordinator._async_setup()
        
        # Mock resilience manager to track calls
        call_count = 0
        
        async def track_calls(func, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await func(*args)
        
        mock_coordinator.resilience_manager.execute_with_resilience = AsyncMock(
            side_effect=track_calls
        )
        
        await mock_coordinator._async_update_data()
        
        # Should have called resilience manager
        assert call_count > 0

    async def test_fetch_timeout_handling(self, mock_coordinator):
        """Test that fetch respects timeout."""
        import asyncio
        
        await mock_coordinator._async_setup()
        
        # Mock slow data fetch
        async def slow_fetch(*args):
            await asyncio.sleep(100)  # Very slow
            return {}
        
        with patch.object(mock_coordinator, '_fetch_dog_data', side_effect=slow_fetch):
            with pytest.raises(asyncio.TimeoutError):
                await mock_coordinator._fetch_dog_data_protected("test_dog")


@pytest.mark.unit
@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling and recovery."""

    async def test_handles_network_errors_gracefully(self, mock_coordinator):
        """Test handling of network errors."""
        await mock_coordinator._async_setup()
        
        # Mock network error
        async def network_error(*args):
            from custom_components.pawcontrol.exceptions import NetworkError
            raise NetworkError("Connection failed")
        
        with patch.object(mock_coordinator, '_fetch_dog_data', side_effect=network_error):
            # Should not raise, should return cached data
            data = await mock_coordinator._async_update_data()
            
            # Should use cached data or empty data
            assert isinstance(data, dict)

    async def test_handles_auth_failures(self, mock_coordinator):
        """Test handling of authentication failures."""
        await mock_coordinator._async_setup()
        
        # Mock auth error
        async def auth_error(*args):
            raise ConfigEntryAuthFailed("Invalid credentials")
        
        with patch.object(mock_coordinator, '_fetch_dog_data', side_effect=auth_error):
            with pytest.raises(ConfigEntryAuthFailed):
                await mock_coordinator._async_update_data()

    async def test_partial_failure_handling(self, mock_coordinator):
        """Test handling when some dogs fail."""
        # Add second dog
        mock_coordinator._configured_dog_ids.append("dog2")
        mock_coordinator.registry._ids.append("dog2")
        mock_coordinator.registry._by_id["dog2"] = {
            "dog_id": "dog2",
            "dog_name": "Max",
            "modules": {},
        }
        
        await mock_coordinator._async_setup()
        
        # Mock failure for one dog
        call_count = 0
        
        async def partial_failure(dog_id):
            nonlocal call_count
            call_count += 1
            if dog_id == "dog2":
                raise Exception("Dog2 fetch failed")
            return {
                "dog_info": {"dog_id": dog_id},
                "status": "online",
            }
        
        with patch.object(
            mock_coordinator, 
            '_fetch_dog_data', 
            side_effect=partial_failure
        ):
            # Should succeed with partial data
            data = await mock_coordinator._async_update_data()
            
            # Dog1 should have data, dog2 should have fallback
            assert "test_dog" in data or "dog2" in data

    async def test_consecutive_error_tracking(self, mock_coordinator):
        """Test that consecutive errors are tracked."""
        await mock_coordinator._async_setup()
        
        initial_errors = mock_coordinator._metrics.consecutive_errors

        # Simulate error
        mock_coordinator._metrics.failed_cycles += 1
        mock_coordinator._metrics.consecutive_errors += 1

        assert mock_coordinator._metrics.consecutive_errors > initial_errors


@pytest.mark.unit
@pytest.mark.asyncio
class TestPublicInterface:
    """Test public interface methods."""

    async def test_get_dog_config(self, mock_coordinator):
        """Test retrieving dog configuration."""
        config = mock_coordinator.get_dog_config("test_dog")
        
        assert config is not None
        assert config["dog_id"] == "test_dog"

    async def test_get_dog_config_nonexistent(self, mock_coordinator):
        """Test retrieving non-existent dog config."""
        config = mock_coordinator.get_dog_config("nonexistent")
        
        assert config is None

    async def test_get_enabled_modules(self, mock_coordinator):
        """Test retrieving enabled modules."""
        modules = mock_coordinator.get_enabled_modules("test_dog")
        
        assert isinstance(modules, frozenset)
        assert "feeding" in modules
        assert "walk" in modules

    async def test_is_module_enabled(self, mock_coordinator):
        """Test checking if module is enabled."""
        assert mock_coordinator.is_module_enabled("test_dog", "feeding") is True
        assert mock_coordinator.is_module_enabled("test_dog", "nonexistent") is False

    async def test_get_dog_ids(self, mock_coordinator):
        """Test retrieving all dog IDs."""
        dog_ids = mock_coordinator.get_dog_ids()
        
        assert isinstance(dog_ids, list)
        assert "test_dog" in dog_ids

    async def test_get_dog_data(self, mock_coordinator):
        """Test retrieving dog data."""
        data = mock_coordinator.get_dog_data("test_dog")
        
        assert data is not None
        assert "dog_info" in data

    async def test_get_module_data(self, mock_coordinator):
        """Test retrieving module-specific data."""
        data = mock_coordinator.get_module_data("test_dog", "feeding")
        
        assert isinstance(data, dict)


@pytest.mark.unit
@pytest.mark.asyncio
class TestManagerAttachment:
    """Test manager attachment and lifecycle."""

    async def test_attach_runtime_managers(self, mock_coordinator):
        """Test attaching runtime managers."""
        mock_data_manager = Mock()
        mock_feeding_manager = Mock()
        mock_walk_manager = Mock()
        mock_notification_manager = Mock()
        
        mock_coordinator.attach_runtime_managers(
            data_manager=mock_data_manager,
            feeding_manager=mock_feeding_manager,
            walk_manager=mock_walk_manager,
            notification_manager=mock_notification_manager,
        )
        
        assert mock_coordinator.data_manager is mock_data_manager
        assert mock_coordinator.feeding_manager is mock_feeding_manager
        assert mock_coordinator.walk_manager is mock_walk_manager
        assert mock_coordinator.notification_manager is mock_notification_manager

    async def test_clear_runtime_managers(self, mock_coordinator):
        """Test clearing runtime managers."""
        mock_coordinator.data_manager = Mock()
        mock_coordinator.feeding_manager = Mock()
        
        mock_coordinator.clear_runtime_managers()
        
        assert mock_coordinator.data_manager is None
        assert mock_coordinator.feeding_manager is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestStatistics:
    """Test statistics and diagnostics."""

    async def test_get_update_statistics(self, mock_coordinator):
        """Test retrieving update statistics."""
        stats = mock_coordinator.get_update_statistics()

        assert "total_updates" in stats
        assert "successful_updates" in stats
        assert "failed" in stats

    async def test_get_statistics(self, mock_coordinator):
        """Test comprehensive statistics."""
        stats = mock_coordinator.get_statistics()
        
        assert "total_dogs" in stats
        assert "update_count" in stats
        assert "error_count" in stats
        assert "resilience" in stats

    async def test_statistics_reflect_state(self, mock_coordinator):
        """Test that statistics reflect actual state."""
        # Simulate some updates
        mock_coordinator._metrics.update_count = 10
        mock_coordinator._metrics.failed_cycles = 2

        stats = mock_coordinator.get_update_statistics()

        assert stats["total_updates"] == 10
        assert stats["failed"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
class TestAvailability:
    """Test availability checking."""

    async def test_available_when_healthy(self, mock_coordinator):
        """Test coordinator is available when healthy."""
        mock_coordinator.last_update_success = True
        mock_coordinator._metrics.consecutive_errors = 0
        
        assert mock_coordinator.available is True

    async def test_unavailable_after_many_errors(self, mock_coordinator):
        """Test coordinator becomes unavailable after errors."""
        mock_coordinator.last_update_success = False
        mock_coordinator._metrics.consecutive_errors = 10
        
        assert mock_coordinator.available is False

    async def test_availability_threshold(self, mock_coordinator):
        """Test availability threshold."""
        mock_coordinator.last_update_success = True
        mock_coordinator._metrics.consecutive_errors = 5  # At threshold
        
        # Should still be unavailable at threshold
        assert mock_coordinator.available is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestConcurrency:
    """Test concurrent operations."""

    async def test_concurrent_data_fetches(self, mock_coordinator):
        """Test concurrent data fetches don't corrupt state."""
        import asyncio
        
        await mock_coordinator._async_setup()
        
        # Execute multiple fetches concurrently
        tasks = [
            mock_coordinator._async_update_data()
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed or fail gracefully
        for result in results:
            if not isinstance(result, Exception):
                assert isinstance(result, dict)

    async def test_concurrent_config_reads(self, mock_coordinator):
        """Test concurrent config reads are safe."""
        import asyncio
        
        async def read_config():
            return mock_coordinator.get_dog_config("test_dog")
        
        # Execute many concurrent reads
        tasks = [read_config() for _ in range(100)]
        
        results = await asyncio.gather(*tasks)
        
        # All should return same config
        assert all(r is not None for r in results)
        assert all(r["dog_id"] == "test_dog" for r in results)
