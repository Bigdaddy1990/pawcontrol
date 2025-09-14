"""Comprehensive tests for PawControl services.

Tests all service handlers including health-aware feeding, walks,
medications, and error handling to achieve 95%+ test coverage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_MEAL_TYPE,
    ATTR_PORTION_SIZE,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    EVENT_HEALTH_LOGGED,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
    SERVICE_DAILY_RESET,
    SERVICE_END_WALK,
    SERVICE_FEED_DOG,
    SERVICE_LOG_HEALTH,
    SERVICE_LOG_MEDICATION,
    SERVICE_NOTIFY_TEST,
    SERVICE_START_GROOMING,
    SERVICE_START_WALK,
)
from custom_components.pawcontrol.services import PawControlServiceManager
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util


@pytest.fixture
def service_manager(hass: HomeAssistant) -> PawControlServiceManager:
    """Create a service manager for testing."""
    return PawControlServiceManager(hass)


@pytest.fixture
def mock_service_call() -> ServiceCall:
    """Create a mock service call."""
    call = MagicMock(spec=ServiceCall)
    call.data = {
        ATTR_DOG_ID: "buddy",
        ATTR_MEAL_TYPE: "breakfast",
        ATTR_PORTION_SIZE: 250,
    }
    return call


async def test_service_manager_initialization(
    hass: HomeAssistant, service_manager: PawControlServiceManager
) -> None:
    """Test service manager initialization."""
    assert service_manager.hass == hass
    assert len(service_manager._registered_services) == 0
    assert len(service_manager._runtime_cache) == 0
    assert service_manager._cache_hits == 0
    assert service_manager._cache_misses == 0


async def test_service_registration(
    hass: HomeAssistant, service_manager: PawControlServiceManager
) -> None:
    """Test service registration."""
    with patch.object(hass.services, "async_register") as mock_register:
        await service_manager.async_register_services()

    # Verify all services were registered
    assert mock_register.call_count == len(service_manager._service_registry)
    assert len(service_manager._registered_services) == len(service_manager._service_registry)

    # Verify service names
    registered_names = {call[0][1] for call in mock_register.call_args_list}
    expected_names = set(service_manager._service_registry.keys())
    assert registered_names == expected_names


async def test_service_registration_idempotent(
    hass: HomeAssistant, service_manager: PawControlServiceManager
) -> None:
    """Test that service registration is idempotent."""
    with patch.object(hass.services, "async_register") as mock_register:
        await service_manager.async_register_services()
        # Try to register again
        await service_manager.async_register_services()

    # Should only register once
    assert mock_register.call_count == len(service_manager._service_registry)


async def test_service_registration_failure(
    hass: HomeAssistant, service_manager: PawControlServiceManager
) -> None:
    """Test service registration failure handling."""
    with patch.object(
        hass.services, "async_register", side_effect=Exception("Registration failed")
    ), pytest.raises(Exception):  # noqa: B017
        await service_manager.async_register_services()

    # Services should be unregistered on failure
    assert len(service_manager._registered_services) == 0


async def test_service_unregistration(
    hass: HomeAssistant, service_manager: PawControlServiceManager
) -> None:
    """Test service unregistration."""
    # Register services first
    service_manager._registered_services = {"test_service1", "test_service2"}

    with patch.object(hass.services, "async_remove") as mock_remove:
        await service_manager.async_unregister_services()

    assert mock_remove.call_count == 2
    assert len(service_manager._registered_services) == 0
    assert len(service_manager._runtime_cache) == 0


async def test_service_unregistration_with_error(
    hass: HomeAssistant, service_manager: PawControlServiceManager
) -> None:
    """Test service unregistration with errors."""
    service_manager._registered_services = {"test_service"}

    with patch.object(
        hass.services, "async_remove", side_effect=Exception("Remove failed")
    ):
        # Should not raise, just log warning
        await service_manager.async_unregister_services()

    assert len(service_manager._registered_services) == 0


async def test_runtime_data_cache(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_runtime_data,
) -> None:
    """Test runtime data caching."""
    dog_id = "buddy"

    # Mock the data retrieval
    with patch.object(
        service_manager, "_get_runtime_data_for_dog", return_value=mock_runtime_data
    ):
        # First call - cache miss
        data1 = service_manager._get_runtime_data_cached(dog_id, priority=5)
        assert service_manager._cache_misses == 1
        assert service_manager._cache_hits == 0

        # Second call - cache hit
        data2 = service_manager._get_runtime_data_cached(dog_id, priority=5)
        assert service_manager._cache_misses == 1
        assert service_manager._cache_hits == 1

        assert data1 == data2


async def test_cache_cleanup(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_runtime_data,
) -> None:
    """Test cache cleanup for expired entries."""
    # Fill cache with many entries
    for i in range(25):
        service_manager._runtime_cache[f"dog_{i}"] = (
            mock_runtime_data,
            dt_util.utcnow().timestamp() - 1000,  # Old timestamp
            5,
        )

    # Trigger cleanup
    with patch.object(
        service_manager, "_get_runtime_data_for_dog", return_value=mock_runtime_data
    ):
        service_manager._get_runtime_data_cached("new_dog", priority=5)

    # Old entries should be cleaned
    assert len(service_manager._runtime_cache) < 25


async def test_feed_dog_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test feed_dog service handler."""
    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_feed_dog_service(mock_service_call)

    # Verify data manager was called
    mock_runtime_data.data_manager.async_feed_dog.assert_called_once_with("buddy", 250)
    mock_runtime_data.data_manager.async_log_feeding.assert_called_once()

    # Verify event was fired
    # Note: In real test, we'd check hass.bus.async_fire was called


async def test_feed_dog_service_no_dog(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
) -> None:
    """Test feed_dog service with missing dog."""
    mock_service_call.data = {}  # No dog_id

    with pytest.raises(ServiceValidationError, match="dog_id is required"):
        await service_manager._handle_feed_dog_service(mock_service_call)


async def test_start_walk_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test start_walk service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "label": "Morning walk",
        "location": "Park",
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_start_walk_service(mock_service_call)

    # Verify walk was started
    mock_runtime_data.data_manager.async_get_current_walk.assert_called_once_with("buddy")
    mock_runtime_data.data_manager.async_start_walk.assert_called_once()


async def test_start_walk_service_already_active(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test start_walk service when walk is already active."""
    mock_service_call.data = {ATTR_DOG_ID: "buddy"}

    # Mock active walk
    mock_runtime_data.data_manager.async_get_current_walk.return_value = {
        "walk_id": "walk_123"
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ), pytest.raises(ServiceValidationError, match="Walk already in progress"):
        await service_manager._handle_start_walk_service(mock_service_call)


async def test_end_walk_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test end_walk service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "distance": 1500,
        "duration": 30,
        "notes": "Good walk",
    }

    # Mock active walk
    mock_runtime_data.data_manager.async_get_current_walk.return_value = {
        "walk_id": "walk_123"
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_end_walk_service(mock_service_call)

    # Verify walk was ended
    mock_runtime_data.data_manager.async_end_walk.assert_called_once()


async def test_end_walk_service_no_active_walk(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test end_walk service when no walk is active."""
    mock_service_call.data = {ATTR_DOG_ID: "buddy"}

    # No active walk
    mock_runtime_data.data_manager.async_get_current_walk.return_value = None

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ), pytest.raises(ServiceValidationError, match="No active walk"):
        await service_manager._handle_end_walk_service(mock_service_call)


async def test_log_health_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test log_health service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "weight": 30.5,
        "temperature": 38.5,
        "mood": "happy",
        "activity_level": "high",
        "health_status": "good",
        "note": "Regular checkup",
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_log_health_service(mock_service_call)

    # Verify health data was logged
    mock_runtime_data.data_manager.async_log_health.assert_called_once()
    call_args = mock_runtime_data.data_manager.async_log_health.call_args[0]
    assert call_args[0] == "buddy"
    assert "weight" in call_args[1]
    assert call_args[1]["weight"] == 30.5


async def test_log_medication_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test log_medication service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "medication_name": "Antibiotics",
        "dosage": "250mg",
        "notes": "Morning dose",
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_log_medication_service(mock_service_call)

    # Verify medication was logged
    mock_runtime_data.data_manager.async_log_health.assert_called_once()
    call_args = mock_runtime_data.data_manager.async_log_health.call_args[0]
    assert call_args[1]["type"] == "medication"
    assert call_args[1]["medication_name"] == "Antibiotics"


async def test_start_grooming_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test start_grooming service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "type": "full_grooming",
        "notes": "Monthly grooming",
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_start_grooming_service(mock_service_call)

    # Verify grooming was started
    mock_runtime_data.data_manager.async_start_grooming.assert_called_once_with(
        "buddy", {"type": "full_grooming", "notes": "Monthly grooming"}
    )


async def test_daily_reset_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test daily_reset service handler."""
    mock_service_call.data = {
        "force": True,
        "dog_ids": ["buddy", "max"],
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_daily_reset_service(mock_service_call)

    # Verify reset was called for each dog
    assert mock_runtime_data.data_manager.async_reset_dog_daily_stats.call_count == 2


async def test_daily_reset_service_all_dogs(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test daily_reset service for all dogs."""
    mock_service_call.data = {}  # No specific dogs

    with patch.object(
        service_manager, "_get_available_dog_ids", return_value=["buddy", "max"]
    ), patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_daily_reset_service(mock_service_call)

    # Verify reset was called for all dogs
    assert mock_runtime_data.data_manager.async_reset_dog_daily_stats.call_count == 2


async def test_notify_test_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test notify_test service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "message": "Test notification",
        "priority": "high",
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_notify_test_service(mock_service_call)

    # Verify notification was sent
    mock_runtime_data.notification_manager.async_send_notification.assert_called_once_with(
        "buddy", "Test notification", priority="high", test_mode=True
    )


async def test_recalculate_health_portions_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test recalculate_health_portions service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "trigger_reason": "weight_change",
        "force_update": True,
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_recalculate_health_portions(mock_service_call)

    # Verify cache was invalidated
    mock_runtime_data.feeding_manager._invalidate_cache.assert_called_once_with("buddy")


async def test_feed_health_aware_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test feed_health_aware service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "meal_type": "breakfast",
        "use_health_calculation": True,
        "notes": "Morning feeding",
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_feed_health_aware(mock_service_call)

    # Verify feeding was added
    mock_runtime_data.feeding_manager.async_add_feeding.assert_called_once()


async def test_feed_health_aware_service_override(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test feed_health_aware service with portion override."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "meal_type": "lunch",
        "override_portion": 300,
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_feed_health_aware(mock_service_call)

    # Verify override portion was used
    call_args = mock_runtime_data.feeding_manager.async_add_feeding.call_args
    assert call_args[1]["amount"] == 300


async def test_update_health_data_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test update_health_data service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "weight": 31.0,
        "ideal_weight": 30.0,
        "body_condition_score": 5,
        "activity_level": "moderate",
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_update_health_data(mock_service_call)

    # Verify health data was updated
    mock_runtime_data.data_manager.async_log_health.assert_called_once()


async def test_update_health_data_service_no_data(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test update_health_data service with no data."""
    mock_service_call.data = {ATTR_DOG_ID: "buddy"}

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ), pytest.raises(ServiceValidationError, match="No health data provided"):
        await service_manager._handle_update_health_data(mock_service_call)


async def test_feed_with_medication_service(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test feed_with_medication service handler."""
    mock_service_call.data = {
        ATTR_DOG_ID: "buddy",
        "medication_name": "Pain Relief",
        "dosage": "100mg",
        "auto_calculate_portion": True,
        "medication_timing": "optimal",
        "notes": "With food",
    }

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ):
        await service_manager._handle_feed_with_medication(mock_service_call)

    # Verify feeding and medication were logged
    mock_runtime_data.feeding_manager.async_add_feeding.assert_called_once()
    mock_runtime_data.data_manager.async_log_health.assert_called_once()


async def test_estimate_calories(
    service_manager: PawControlServiceManager,
) -> None:
    """Test calorie estimation."""
    # Test dry food
    calories = service_manager._estimate_calories(100, "dry_food")
    assert calories == 350.0

    # Test wet food
    calories = service_manager._estimate_calories(200, "wet_food")
    assert calories == 170.0

    # Test unknown food type
    calories = service_manager._estimate_calories(100, "unknown")
    assert calories == 200.0  # Default


async def test_get_available_dog_ids(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_coordinator,
) -> None:
    """Test getting available dog IDs."""
    mock_coordinator.get_dog_ids.return_value = ["buddy", "max"]

    hass.data[DOMAIN] = {
        "entry1": {"coordinator": mock_coordinator}
    }

    dog_ids = service_manager._get_available_dog_ids()
    assert "buddy" in dog_ids
    assert "max" in dog_ids


async def test_get_cache_stats(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_runtime_data,
) -> None:
    """Test cache statistics."""
    # Generate some cache activity
    with patch.object(
        service_manager, "_get_runtime_data_for_dog", return_value=mock_runtime_data
    ):
        service_manager._get_runtime_data_cached("buddy", priority=5)
        service_manager._get_runtime_data_cached("buddy", priority=5)  # Cache hit
        service_manager._get_runtime_data_cached("max", priority=5)

    stats = service_manager.get_cache_stats()

    assert stats["cache_entries"] == 2
    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 2
    assert stats["hit_rate"] == 33.3
    assert stats["registered_services"] == 0


async def test_service_timeout(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
) -> None:
    """Test service timeout handling."""
    mock_service_call.data = {ATTR_DOG_ID: "buddy"}

    with patch.object(
        service_manager, "_get_runtime_data_cached", side_effect=TimeoutError()
    ), pytest.raises(ServiceValidationError, match="Service timed out"):
        await service_manager._handle_feed_dog_service(mock_service_call)


async def test_service_unexpected_error(
    hass: HomeAssistant,
    service_manager: PawControlServiceManager,
    mock_service_call,
    mock_runtime_data,
) -> None:
    """Test unexpected error handling."""
    mock_service_call.data = {ATTR_DOG_ID: "buddy"}

    mock_runtime_data.data_manager.async_feed_dog.side_effect = Exception("Unexpected")

    with patch.object(
        service_manager, "_get_runtime_data_cached", return_value=mock_runtime_data
    ), pytest.raises(ServiceValidationError, match="Service failed"):
        await service_manager._handle_feed_dog_service(mock_service_call)


async def test_daily_reset_scheduler(hass: HomeAssistant, mock_config_entry) -> None:
    """Test daily reset scheduler setup."""
    from custom_components.pawcontrol.services import async_setup_daily_reset_scheduler

    with patch(
        "custom_components.pawcontrol.services.async_track_time_change"
    ) as mock_track:
        await async_setup_daily_reset_scheduler(hass, mock_config_entry)

    # Verify time trigger was registered
    mock_track.assert_called_once()
    call_args = mock_track.call_args[0]
    assert call_args[0] == hass
    assert callable(call_args[1])  # Callback function


async def test_daily_reset_scheduler_invalid_time(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test daily reset scheduler with invalid time."""
    from custom_components.pawcontrol.services import async_setup_daily_reset_scheduler

    mock_config_entry.options = {"reset_time": "invalid"}

    # Should not raise, just log error
    await async_setup_daily_reset_scheduler(hass, mock_config_entry)
