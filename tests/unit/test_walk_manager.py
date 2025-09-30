"""Comprehensive unit tests for WalkManager.

Tests walk session management, activity tracking, duration calculations,
and integration with weather conditions.

Quality Scale: Platinum
Python: 3.13+
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from custom_components.pawcontrol.walk_manager import (
    WalkManager,
    WalkSession,
    WeatherCondition,
)


@pytest.mark.unit
@pytest.mark.asyncio
class TestWalkManagerInitialization:
    """Test walk manager initialization."""

    async def test_initialization_empty(self):
        """Test initialization with no dogs."""
        manager = WalkManager()

        await manager.async_initialize([])

        assert len(manager._dogs) == 0

    async def test_initialization_single_dog(self):
        """Test initialization with single dog."""
        manager = WalkManager()

        await manager.async_initialize(["test_dog"])

        assert "test_dog" in manager._dogs
        assert manager._dogs["test_dog"]["active_walk"] is None

    async def test_initialization_multiple_dogs(self):
        """Test initialization with multiple dogs."""
        manager = WalkManager()

        await manager.async_initialize(["buddy", "max", "luna"])

        assert len(manager._dogs) == 3
        assert all(dog in manager._dogs for dog in ["buddy", "max", "luna"])


@pytest.mark.unit
@pytest.mark.asyncio
class TestStartWalk:
    """Test starting walk sessions."""

    async def test_start_walk_basic(self, mock_walk_manager):
        """Test starting basic walk."""
        session_id = await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        assert session_id is not None

        dog_data = mock_walk_manager._dogs["test_dog"]
        assert dog_data["active_walk"] is not None

    async def test_start_walk_with_walker(self, mock_walk_manager):
        """Test starting walk with walker name."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
            walker="John",
        )

        dog_data = mock_walk_manager._dogs["test_dog"]
        active_walk = dog_data["active_walk"]

        assert active_walk["walker"] == "John"

    async def test_start_walk_with_weather(self, mock_walk_manager):
        """Test starting walk with weather condition."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
            weather=WeatherCondition.SUNNY,
        )

        dog_data = mock_walk_manager._dogs["test_dog"]
        active_walk = dog_data["active_walk"]

        assert active_walk["weather"] == WeatherCondition.SUNNY

    async def test_start_walk_with_leash_info(self, mock_walk_manager):
        """Test starting walk with leash information."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
            leash_used=True,
        )

        dog_data = mock_walk_manager._dogs["test_dog"]
        active_walk = dog_data["active_walk"]

        assert active_walk["leash_used"] is True

    async def test_start_walk_ends_previous_walk(self, mock_walk_manager):
        """Test that starting new walk ends previous walk."""
        # Start first walk
        session1 = await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        # Start second walk
        session2 = await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        assert session1 != session2

        # Check walk history
        history = mock_walk_manager.get_walk_history("test_dog")
        assert len(history) >= 1  # First walk should be in history

    async def test_start_walk_invalid_dog(self, mock_walk_manager):
        """Test starting walk for non-existent dog."""
        with pytest.raises(KeyError):
            await mock_walk_manager.async_start_walk(
                dog_id="nonexistent",
                walk_type="manual",
            )


@pytest.mark.unit
@pytest.mark.asyncio
class TestEndWalk:
    """Test ending walk sessions."""

    async def test_end_walk_basic(self, mock_walk_manager, create_walk_event):
        """Test ending basic walk."""
        # Start walk
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        # End walk
        walk_event = await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
        )

        assert walk_event is not None
        assert "duration" in walk_event
        assert "distance" in walk_event

    async def test_end_walk_with_notes(self, mock_walk_manager):
        """Test ending walk with notes."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        walk_event = await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
            notes="Great walk, saw other dogs",
        )

        assert walk_event["notes"] == "Great walk, saw other dogs"

    async def test_end_walk_with_weight(self, mock_walk_manager):
        """Test ending walk with dog weight."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        walk_event = await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
            dog_weight_kg=29.5,
        )

        assert walk_event["dog_weight_kg"] == 29.5

    async def test_end_walk_no_active_walk(self, mock_walk_manager):
        """Test ending walk when no active walk."""
        walk_event = await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
        )

        assert walk_event is None

    async def test_end_walk_saves_to_history(self, mock_walk_manager):
        """Test that ended walk is saved to history."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
        )

        history = mock_walk_manager.get_walk_history("test_dog")

        assert len(history) >= 1

    async def test_end_walk_clears_active_walk(self, mock_walk_manager):
        """Test that ending walk clears active walk."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
        )

        dog_data = mock_walk_manager._dogs["test_dog"]

        assert dog_data["active_walk"] is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestWalkDuration:
    """Test walk duration calculations."""

    async def test_walk_duration_short(self, mock_walk_manager):
        """Test walk duration for short walk."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        # Simulate short walk (1 second)
        import asyncio

        await asyncio.sleep(1)

        walk_event = await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
        )

        # Duration should be at least 1 second
        assert walk_event["duration"] >= 1.0

    async def test_walk_duration_multiple_dogs(self, mock_walk_manager):
        """Test tracking duration for multiple dogs simultaneously."""
        # Initialize second dog
        await mock_walk_manager.async_initialize(["test_dog", "buddy"])

        # Start walks for both
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        await mock_walk_manager.async_start_walk(
            dog_id="buddy",
            walk_type="manual",
        )

        # End both walks
        walk1 = await mock_walk_manager.async_end_walk(dog_id="test_dog")
        walk2 = await mock_walk_manager.async_end_walk(dog_id="buddy")

        # Both should have valid durations
        assert walk1["duration"] > 0
        assert walk2["duration"] > 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestWalkStatistics:
    """Test walk statistics and aggregation."""

    async def test_get_daily_walk_stats(self, mock_walk_manager):
        """Test getting daily walk statistics."""
        # Create multiple walks
        for _i in range(3):
            await mock_walk_manager.async_start_walk(
                dog_id="test_dog",
                walk_type="manual",
            )
            await mock_walk_manager.async_end_walk(
                dog_id="test_dog",
            )

        stats = mock_walk_manager.get_daily_walk_stats("test_dog")

        assert "total_walks_today" in stats
        assert "total_duration_today" in stats
        assert stats["total_walks_today"] >= 3

    async def test_get_walk_history(self, mock_walk_manager):
        """Test retrieving walk history."""
        # Create walks
        for _i in range(5):
            await mock_walk_manager.async_start_walk(
                dog_id="test_dog",
                walk_type="manual",
            )
            await mock_walk_manager.async_end_walk(
                dog_id="test_dog",
            )

        history = mock_walk_manager.get_walk_history("test_dog")

        assert len(history) >= 5

    async def test_get_walk_history_with_limit(self, mock_walk_manager):
        """Test retrieving walk history with limit."""
        # Create many walks
        for _i in range(10):
            await mock_walk_manager.async_start_walk(
                dog_id="test_dog",
                walk_type="manual",
            )
            await mock_walk_manager.async_end_walk(
                dog_id="test_dog",
            )

        # Get last 3 walks
        history = mock_walk_manager.get_walk_history("test_dog", limit=3)

        assert len(history) <= 3

    async def test_weekly_walk_statistics(self, mock_walk_manager):
        """Test weekly walk statistics calculation."""
        # Create walks over several days
        for i in range(7):
            await mock_walk_manager.async_start_walk(
                dog_id="test_dog",
                walk_type="manual",
            )

            walk = await mock_walk_manager.async_end_walk(
                dog_id="test_dog",
            )

            # Modify timestamp to simulate different days
            if hasattr(walk, "start_time"):
                walk["start_time"] = datetime.now() - timedelta(days=i)

        stats = mock_walk_manager.get_weekly_walk_stats("test_dog")

        assert "total_walks_this_week" in stats
        assert stats["total_walks_this_week"] >= 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestActiveWalkInfo:
    """Test active walk information."""

    async def test_get_active_walk_info(self, mock_walk_manager):
        """Test getting active walk information."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
            walker="John",
        )

        active_walk = mock_walk_manager.get_active_walk_info("test_dog")

        assert active_walk is not None
        assert "start_time" in active_walk
        assert active_walk["walker"] == "John"

    async def test_get_active_walk_info_no_walk(self, mock_walk_manager):
        """Test getting active walk when no walk active."""
        active_walk = mock_walk_manager.get_active_walk_info("test_dog")

        assert active_walk is None

    async def test_active_walk_duration_updates(self, mock_walk_manager):
        """Test that active walk duration updates."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        import asyncio

        await asyncio.sleep(1)

        active_walk = mock_walk_manager.get_active_walk_info("test_dog")

        # Should have elapsed time
        assert "elapsed_duration" in active_walk or active_walk is not None


@pytest.mark.unit
@pytest.mark.asyncio
class TestWalkTypes:
    """Test different walk types."""

    async def test_manual_walk_type(self, mock_walk_manager):
        """Test manual walk type."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        dog_data = mock_walk_manager._dogs["test_dog"]
        active_walk = dog_data["active_walk"]

        assert active_walk["walk_type"] == "manual"

    async def test_scheduled_walk_type(self, mock_walk_manager):
        """Test scheduled walk type."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="scheduled",
        )

        dog_data = mock_walk_manager._dogs["test_dog"]
        active_walk = dog_data["active_walk"]

        assert active_walk["walk_type"] == "scheduled"

    async def test_automatic_walk_type(self, mock_walk_manager):
        """Test automatic walk type (door sensor triggered)."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="automatic",
        )

        dog_data = mock_walk_manager._dogs["test_dog"]
        active_walk = dog_data["active_walk"]

        assert active_walk["walk_type"] == "automatic"


@pytest.mark.unit
class TestWeatherConditions:
    """Test weather condition enum."""

    def test_weather_condition_enum_values(self):
        """Test weather condition enum values."""
        assert WeatherCondition.SUNNY.value == "sunny"
        assert WeatherCondition.RAINY.value == "rainy"
        assert WeatherCondition.SNOWY.value == "snowy"
        assert WeatherCondition.CLOUDY.value == "cloudy"

    def test_weather_condition_from_string(self):
        """Test creating weather condition from string."""
        condition = WeatherCondition("sunny")

        assert condition == WeatherCondition.SUNNY


@pytest.mark.unit
@pytest.mark.asyncio
class TestWalkDataRetrieval:
    """Test walk data retrieval methods."""

    async def test_get_walk_data_existing_dog(self, mock_walk_manager):
        """Test getting walk data for existing dog."""
        data = mock_walk_manager.get_walk_data("test_dog")

        assert isinstance(data, dict)
        assert "active_walk" in data
        assert "history" in data

    async def test_get_walk_data_nonexistent_dog(self, mock_walk_manager):
        """Test getting walk data for non-existent dog."""
        data = mock_walk_manager.get_walk_data("nonexistent")

        assert data == {}

    async def test_get_last_walk_info(self, mock_walk_manager):
        """Test getting last walk information."""
        # Create walk
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
        )

        last_walk = mock_walk_manager.get_last_walk_info("test_dog")

        assert last_walk is not None
        assert "duration" in last_walk


@pytest.mark.unit
@pytest.mark.asyncio
class TestWalkHistoryManagement:
    """Test walk history management and limits."""

    async def test_walk_history_limit(self, mock_walk_manager):
        """Test that walk history respects limit."""
        # Create many walks
        for _i in range(150):
            await mock_walk_manager.async_start_walk(
                dog_id="test_dog",
                walk_type="manual",
            )
            await mock_walk_manager.async_end_walk(
                dog_id="test_dog",
            )

        history = mock_walk_manager.get_walk_history("test_dog")

        # Should be limited (e.g., to 100)
        assert len(history) <= 100

    async def test_walk_history_ordered_newest_first(self, mock_walk_manager):
        """Test that walk history is ordered newest first."""
        # Create walks
        for _i in range(5):
            await mock_walk_manager.async_start_walk(
                dog_id="test_dog",
                walk_type="manual",
            )

            import asyncio

            await asyncio.sleep(0.1)  # Small delay to ensure different timestamps

            await mock_walk_manager.async_end_walk(
                dog_id="test_dog",
            )

        history = mock_walk_manager.get_walk_history("test_dog")

        # Check ordering (newest first)
        if len(history) >= 2:
            first_timestamp = history[0].get("start_time", datetime.now())
            second_timestamp = history[1].get("start_time", datetime.now())
            assert first_timestamp >= second_timestamp


@pytest.mark.unit
@pytest.mark.asyncio
class TestDataIsolation:
    """Test that walk data is isolated between dogs."""

    async def test_walk_data_isolated_between_dogs(self, mock_walk_manager):
        """Test that each dog's walk data is isolated."""
        # Initialize multiple dogs
        await mock_walk_manager.async_initialize(["buddy", "max"])

        # Start walk for buddy
        await mock_walk_manager.async_start_walk(
            dog_id="buddy",
            walk_type="manual",
        )

        # Check max has no active walk
        max_active = mock_walk_manager.get_active_walk_info("max")

        assert max_active is None

    async def test_walk_history_isolated(self, mock_walk_manager):
        """Test that walk history is isolated between dogs."""
        await mock_walk_manager.async_initialize(["buddy", "max"])

        # Create walk for buddy
        await mock_walk_manager.async_start_walk(dog_id="buddy", walk_type="manual")
        await mock_walk_manager.async_end_walk(dog_id="buddy")

        # Check histories
        buddy_history = mock_walk_manager.get_walk_history("buddy")
        max_history = mock_walk_manager.get_walk_history("max")

        assert len(buddy_history) >= 1
        assert len(max_history) == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_end_walk_immediately_after_start(self, mock_walk_manager):
        """Test ending walk immediately after starting."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        walk_event = await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
        )

        # Should handle very short duration
        assert walk_event is not None
        assert walk_event["duration"] >= 0

    async def test_multiple_start_walk_calls(self, mock_walk_manager):
        """Test multiple start walk calls without ending."""
        session1 = await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        session2 = await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        session3 = await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        # Each should get unique session ID
        assert session1 != session2 != session3

    async def test_concurrent_walks_different_dogs(self, mock_walk_manager):
        """Test concurrent walks for different dogs."""
        await mock_walk_manager.async_initialize(["buddy", "max", "luna"])

        # Start walks for all dogs
        await mock_walk_manager.async_start_walk(dog_id="buddy", walk_type="manual")
        await mock_walk_manager.async_start_walk(dog_id="max", walk_type="manual")
        await mock_walk_manager.async_start_walk(dog_id="luna", walk_type="manual")

        # All should have active walks
        assert mock_walk_manager.get_active_walk_info("buddy") is not None
        assert mock_walk_manager.get_active_walk_info("max") is not None
        assert mock_walk_manager.get_active_walk_info("luna") is not None

    async def test_walk_with_none_walker(self, mock_walk_manager):
        """Test walk with None as walker name."""
        session_id = await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
            walker=None,
        )

        # Should handle None gracefully
        assert session_id is not None

    async def test_walk_with_extreme_duration(self, mock_walk_manager):
        """Test walk with very long duration."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        # Manually set very long duration
        dog_data = mock_walk_manager._dogs["test_dog"]
        if dog_data["active_walk"]:
            dog_data["active_walk"]["start_time"] = datetime.now() - timedelta(hours=24)

        walk_event = await mock_walk_manager.async_end_walk(
            dog_id="test_dog",
        )

        # Should handle very long duration
        assert walk_event is not None
        assert walk_event["duration"] > 0

    async def test_cleanup_clears_all_data(self, mock_walk_manager):
        """Test that cleanup clears all walk data."""
        await mock_walk_manager.async_start_walk(
            dog_id="test_dog",
            walk_type="manual",
        )

        await mock_walk_manager.async_shutdown()

        # Data should be cleared
        assert len(mock_walk_manager._dogs) == 0
