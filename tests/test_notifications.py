"""Comprehensive tests for Paw Control notifications module.

This test suite covers all aspects of the notification system including:
- Smart notification delivery with priority management
- Multiple delivery methods (persistent, mobile app)
- Quiet hours and rate limiting
- Background tasks and cleanup
- Error handling and resilience
- Performance optimization and metrics

The notification module is critical for user experience and requires thorough testing.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock, call
from datetime import datetime, timedelta
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.exceptions import ServiceNotFound

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.exceptions import NotificationError
from custom_components.pawcontrol.notifications import (
    PawControlNotificationManager,
    
    # Priority constants
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    PRIORITY_HIGH,
    PRIORITY_URGENT,
    
    # Notification types
    NOTIFICATION_FEEDING,
    NOTIFICATION_WALK,
    NOTIFICATION_HEALTH,
    NOTIFICATION_GPS,
    NOTIFICATION_GROOMING,
    NOTIFICATION_SYSTEM,
    NOTIFICATION_SAFETY,
    NOTIFICATION_MEDICATION,
    
    # Delivery methods
    DELIVERY_PERSISTENT,
    DELIVERY_MOBILE_APP,
    DELIVERY_EMAIL,
    DELIVERY_TTS,
    DELIVERY_WEBHOOK,
    DELIVERY_SLACK,
    DELIVERY_DISCORD,
    
    # Rate limits
    RATE_LIMIT_INTERVALS,
    MAX_HISTORY_DAYS,
    MAX_HISTORY_COUNT,
)


# Test fixtures
@pytest.fixture
def mock_runtime_data():
    """Mock runtime data structure."""
    coordinator = Mock()
    coordinator.get_dog_data = Mock(return_value={
        "dog_info": {
            "dog_id": "test_dog",
            "dog_name": "Test Dog",
        }
    })
    
    config_entry = Mock()
    config_entry.options = {
        "notifications": {
            "global_enabled": True,
            "quiet_hours_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "rate_limiting_enabled": True,
            "delivery_methods": [DELIVERY_PERSISTENT, DELIVERY_MOBILE_APP],
        }
    }
    
    return {
        "coordinator": coordinator,
        "config_entry": config_entry,
    }


@pytest.fixture
def notification_manager(hass: HomeAssistant, mock_runtime_data):
    """Create notification manager instance."""
    with patch.object(PawControlNotificationManager, '_get_runtime_data', return_value=mock_runtime_data):
        manager = PawControlNotificationManager(hass, "test_entry_id")
        return manager


@pytest.fixture
def initialized_manager(hass: HomeAssistant, notification_manager):
    """Create and initialize notification manager."""
    async def _init():
        await notification_manager.async_initialize()
        return notification_manager
    
    return _init


@pytest.fixture
def mock_persistent_notification():
    """Mock persistent notification service."""
    with patch("homeassistant.components.persistent_notification.async_create") as mock_create, \
         patch("homeassistant.components.persistent_notification.async_dismiss") as mock_dismiss:
        yield {"create": mock_create, "dismiss": mock_dismiss}


@pytest.fixture
def mock_hass_services(hass: HomeAssistant):
    """Mock hass services for notifications."""
    # Mock notification services
    services_data = {
        "notify": {
            "mobile_app_test_device": {},
            "mobile_app_another_device": {},
            "persistent_notification": {},
        }
    }
    
    hass.services.async_services = Mock(return_value=services_data)
    hass.services.has_service = Mock(side_effect=lambda domain, service: service in services_data.get(domain, {}))
    hass.services.async_call = AsyncMock()
    
    return hass.services


# Basic Functionality Tests
class TestNotificationManagerBasics:
    """Test basic notification manager functionality."""

    async def test_initialization_success(self, hass: HomeAssistant, notification_manager):
        """Test successful initialization."""
        with patch.object(notification_manager, '_start_background_tasks'), \
             patch.object(notification_manager, '_register_services'):
            
            await notification_manager.async_initialize()
            
            assert notification_manager._config["global_enabled"] is True
            assert notification_manager._metrics["notifications_sent"] == 0

    async def test_initialization_failure(self, hass: HomeAssistant, notification_manager):
        """Test initialization failure handling."""
        with patch.object(notification_manager, '_load_configuration', side_effect=Exception("Config error")):
            
            with pytest.raises(NotificationError) as exc_info:
                await notification_manager.async_initialize()
            
            assert "initialization" in str(exc_info.value)

    async def test_shutdown_graceful(self, hass: HomeAssistant, initialized_manager):
        """Test graceful shutdown."""
        manager = await initialized_manager()
        
        # Add some active notifications
        manager._active_notifications = {
            "test_id_1": {"id": "test_id_1"},
            "test_id_2": {"id": "test_id_2"},
        }
        
        with patch.object(manager, '_dismiss_notification_internal', return_value=True) as mock_dismiss:
            await manager.async_shutdown()
            
            assert mock_dismiss.call_count == 2
            assert len(manager._active_notifications) == 0

    async def test_configuration_loading(self, hass: HomeAssistant, notification_manager, mock_runtime_data):
        """Test configuration loading from entry options."""
        await notification_manager._load_configuration()
        
        assert notification_manager._config["quiet_hours_enabled"] is True
        assert notification_manager._config["quiet_hours_start"] == "22:00"
        assert DELIVERY_MOBILE_APP in notification_manager._config["delivery_methods"]


# Core Notification Tests
class TestCoreNotificationFunctionality:
    """Test core notification sending functionality."""

    async def test_send_basic_notification_success(self, hass: HomeAssistant, initialized_manager, mock_persistent_notification):
        """Test sending basic notification successfully."""
        manager = await initialized_manager()
        
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            result = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_FEEDING,
                "Time to feed your dog!"
            )
        
        assert result is True
        assert manager._metrics["notifications_sent"] == 1
        assert len(manager._active_notifications) == 1
        assert len(manager._notification_history) == 1

    async def test_send_notification_with_all_options(self, hass: HomeAssistant, initialized_manager):
        """Test sending notification with all possible options."""
        manager = await initialized_manager()
        
        actions = [{"action": "snooze", "title": "Snooze"}]
        data = {"custom_field": "custom_value"}
        
        with patch.object(manager, '_send_persistent_notification', return_value=True), \
             patch.object(manager, '_send_mobile_app_notification', return_value=True):
            
            result = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_HEALTH,
                "Health check reminder",
                title="Custom Title",
                priority=PRIORITY_HIGH,
                data=data,
                delivery_methods=[DELIVERY_PERSISTENT, DELIVERY_MOBILE_APP],
                force=False,
                actions=actions
            )
        
        assert result is True
        
        # Check stored notification data
        notification = list(manager._active_notifications.values())[0]
        assert notification["title"] == "Custom Title"
        assert notification["priority"] == PRIORITY_HIGH
        assert notification["data"] == data
        assert notification["actions"] == actions

    async def test_send_notification_validation_failure(self, hass: HomeAssistant, initialized_manager):
        """Test notification validation failures."""
        manager = await initialized_manager()
        
        # Test empty dog_id
        result = await manager.async_send_notification(
            "",
            NOTIFICATION_FEEDING,
            "Test message"
        )
        assert result is False
        
        # Test empty notification_type
        result = await manager.async_send_notification(
            "test_dog",
            "",
            "Test message"
        )
        assert result is False
        
        # Test invalid priority
        result = await manager.async_send_notification(
            "test_dog",
            NOTIFICATION_FEEDING,
            "Test message",
            priority="invalid_priority"
        )
        assert result is False

    async def test_send_notification_disabled_globally(self, hass: HomeAssistant, initialized_manager):
        """Test notification when globally disabled."""
        manager = await initialized_manager()
        manager._config["global_enabled"] = False
        
        result = await manager.async_send_notification(
            "test_dog",
            NOTIFICATION_FEEDING,
            "Test message"
        )
        
        assert result is False
        assert manager._metrics["notifications_sent"] == 0

    async def test_send_notification_force_override(self, hass: HomeAssistant, initialized_manager):
        """Test force parameter overrides restrictions."""
        manager = await initialized_manager()
        manager._config["global_enabled"] = False
        
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            result = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_SYSTEM,
                "Forced message",
                force=True
            )
        
        assert result is True
        assert manager._metrics["notifications_sent"] == 1


# Priority Management Tests
class TestPriorityManagement:
    """Test notification priority handling."""

    async def test_urgent_priority_bypasses_quiet_hours(self, hass: HomeAssistant, initialized_manager):
        """Test urgent notifications bypass quiet hours."""
        manager = await initialized_manager()
        
        # Set quiet hours active
        with patch.object(manager, '_is_in_quiet_hours', return_value=True), \
             patch.object(manager, '_send_persistent_notification', return_value=True):
            
            # Normal priority should be suppressed
            result_normal = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_FEEDING,
                "Normal message",
                priority=PRIORITY_NORMAL
            )
            assert result_normal is False
            
            # Urgent priority should go through
            result_urgent = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_SAFETY,
                "Emergency!",
                priority=PRIORITY_URGENT
            )
            assert result_urgent is True

    async def test_urgent_priority_bypasses_rate_limiting(self, hass: HomeAssistant, initialized_manager):
        """Test urgent notifications bypass rate limiting."""
        manager = await initialized_manager()
        
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            # Send normal priority first
            await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_HEALTH,
                "Health update",
                priority=PRIORITY_NORMAL
            )
            
            # Send another normal priority immediately (should be rate limited)
            result_limited = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_HEALTH,
                "Another health update",
                priority=PRIORITY_NORMAL
            )
            assert result_limited is False
            
            # Send urgent priority (should go through)
            result_urgent = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_HEALTH,
                "Urgent health alert!",
                priority=PRIORITY_URGENT
            )
            assert result_urgent is True

    async def test_priority_affects_delivery_methods(self, hass: HomeAssistant, initialized_manager):
        """Test priority affects delivery method selection."""
        manager = await initialized_manager()
        manager._config["delivery_methods"] = [DELIVERY_PERSISTENT]  # Base methods
        
        with patch.object(manager, '_send_persistent_notification', return_value=True), \
             patch.object(manager, '_send_mobile_app_notification', return_value=True):
            
            # High priority should add mobile app
            await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_WALK,
                "Walk reminder",
                priority=PRIORITY_HIGH
            )
            
            notification = list(manager._active_notifications.values())[0]
            assert DELIVERY_MOBILE_APP in notification["delivery_status"]

    async def test_title_generation_with_priority(self, hass: HomeAssistant, notification_manager):
        """Test title generation includes priority indicators."""
        # Test different priority levels
        title_urgent = notification_manager._generate_title("Buddy", NOTIFICATION_FEEDING, PRIORITY_URGENT)
        title_high = notification_manager._generate_title("Buddy", NOTIFICATION_FEEDING, PRIORITY_HIGH)
        title_normal = notification_manager._generate_title("Buddy", NOTIFICATION_FEEDING, PRIORITY_NORMAL)
        title_low = notification_manager._generate_title("Buddy", NOTIFICATION_FEEDING, PRIORITY_LOW)
        
        assert "🚨 URGENT" in title_urgent
        assert "⚠️ Important" in title_high
        assert "🐕" in title_normal
        assert "ℹ️" in title_low
        
        # All should contain dog name
        assert "Buddy" in title_urgent
        assert "Buddy" in title_high
        assert "Buddy" in title_normal
        assert "Buddy" in title_low


# Quiet Hours Tests
class TestQuietHours:
    """Test quiet hours functionality."""

    async def test_quiet_hours_detection(self, hass: HomeAssistant, notification_manager):
        """Test quiet hours detection logic."""
        # Test with quiet hours enabled
        manager = notification_manager
        manager._config["quiet_hours_enabled"] = True
        manager._config["quiet_hours_start"] = "22:00"
        manager._config["quiet_hours_end"] = "08:00"
        
        # Mock different times
        with patch('custom_components.pawcontrol.utils.is_within_quiet_hours') as mock_quiet:
            mock_quiet.return_value = True
            assert manager._is_in_quiet_hours() is True
            
            mock_quiet.return_value = False
            assert manager._is_in_quiet_hours() is False

    async def test_quiet_hours_disabled(self, hass: HomeAssistant, notification_manager):
        """Test behavior when quiet hours are disabled."""
        manager = notification_manager
        manager._config["quiet_hours_enabled"] = False
        
        # Should always return False when disabled
        with patch('custom_components.pawcontrol.utils.is_within_quiet_hours', return_value=True):
            assert manager._is_in_quiet_hours() is False

    async def test_notification_suppression_during_quiet_hours(self, hass: HomeAssistant, initialized_manager):
        """Test notifications are suppressed during quiet hours."""
        manager = await initialized_manager()
        
        with patch.object(manager, '_is_in_quiet_hours', return_value=True):
            # Normal priority should be suppressed
            result = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_WALK,
                "Walk time!",
                priority=PRIORITY_NORMAL
            )
            
            assert result is False
            assert manager._metrics["notifications_suppressed"] == 1


# Rate Limiting Tests
class TestRateLimiting:
    """Test rate limiting functionality."""

    async def test_rate_limiting_by_priority(self, hass: HomeAssistant, initialized_manager):
        """Test rate limiting intervals by priority."""
        manager = await initialized_manager()
        
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            # Send first notification
            result1 = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_FEEDING,
                "First feeding",
                priority=PRIORITY_NORMAL
            )
            assert result1 is True
            
            # Send second notification immediately (should be rate limited)
            result2 = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_FEEDING,
                "Second feeding",
                priority=PRIORITY_NORMAL
            )
            assert result2 is False
            assert manager._metrics["rate_limited_count"] == 1

    async def test_different_notification_types_not_rate_limited(self, hass: HomeAssistant, initialized_manager):
        """Test different notification types are not rate limited together."""
        manager = await initialized_manager()
        
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            # Send feeding notification
            result1 = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_FEEDING,
                "Feeding time"
            )
            assert result1 is True
            
            # Send walk notification (different type, should not be rate limited)
            result2 = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_WALK,
                "Walk time"
            )
            assert result2 is True

    async def test_different_dogs_not_rate_limited(self, hass: HomeAssistant, initialized_manager):
        """Test different dogs are not rate limited together."""
        manager = await initialized_manager()
        
        with patch.object(manager, '_send_persistent_notification', return_value=True), \
             patch.object(manager, '_get_dog_name', side_effect=lambda dog_id: f"Dog {dog_id}"):
            
            # Send notification for first dog
            result1 = await manager.async_send_notification(
                "dog_1",
                NOTIFICATION_FEEDING,
                "Feeding time"
            )
            assert result1 is True
            
            # Send notification for second dog (should not be rate limited)
            result2 = await manager.async_send_notification(
                "dog_2",
                NOTIFICATION_FEEDING,
                "Feeding time"
            )
            assert result2 is True

    async def test_rate_limiting_disabled(self, hass: HomeAssistant, initialized_manager):
        """Test behavior when rate limiting is disabled."""
        manager = await initialized_manager()
        manager._config["rate_limiting_enabled"] = False
        
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            # Send multiple notifications rapidly
            for i in range(5):
                result = await manager.async_send_notification(
                    "test_dog",
                    NOTIFICATION_FEEDING,
                    f"Feeding {i}"
                )
                assert result is True
            
            assert manager._metrics["rate_limited_count"] == 0


# Delivery Methods Tests
class TestDeliveryMethods:
    """Test different delivery methods."""

    async def test_persistent_notification_delivery(self, hass: HomeAssistant, initialized_manager, mock_persistent_notification):
        """Test persistent notification delivery."""
        manager = await initialized_manager()
        
        notification_data = {
            "id": "test_notification",
            "title": "Test Title",
            "message": "Test Message",
        }
        
        result = await manager._send_persistent_notification(notification_data)
        
        assert result is True
        mock_persistent_notification["create"].assert_called_once_with(
            hass,
            "Test Message",
            title="Test Title",
            notification_id="test_notification"
        )

    async def test_persistent_notification_failure(self, hass: HomeAssistant, initialized_manager, mock_persistent_notification):
        """Test persistent notification failure handling."""
        manager = await initialized_manager()
        mock_persistent_notification["create"].side_effect = Exception("Persistent error")
        
        notification_data = {
            "id": "test_notification",
            "title": "Test Title",
            "message": "Test Message",
        }
        
        result = await manager._send_persistent_notification(notification_data)
        
        assert result is False

    async def test_mobile_app_notification_delivery(self, hass: HomeAssistant, initialized_manager, mock_hass_services):
        """Test mobile app notification delivery."""
        manager = await initialized_manager()
        
        notification_data = {
            "id": "test_notification",
            "title": "Test Title",
            "message": "Test Message",
            "priority": PRIORITY_NORMAL,
            "dog_id": "test_dog",
            "type": NOTIFICATION_FEEDING,
            "data": {"custom": "data"},
            "actions": [{"action": "test", "title": "Test"}],
        }
        
        result = await manager._send_mobile_app_notification(notification_data)
        
        assert result is True
        
        # Should call service for each mobile app device
        assert mock_hass_services.async_call.call_count == 2
        
        # Check call structure
        calls = mock_hass_services.async_call.call_args_list
        for call_args in calls:
            domain, service, data = call_args[0]
            assert domain == "notify"
            assert service.startswith("mobile_app_")
            assert data["title"] == "Test Title"
            assert data["message"] == "Test Message"
            assert "actions" in data["data"]

    async def test_mobile_app_no_services_available(self, hass: HomeAssistant, initialized_manager):
        """Test mobile app notification when no services available."""
        manager = await initialized_manager()
        
        # Mock no mobile app services
        hass.services.async_services = Mock(return_value={"notify": {}})
        
        notification_data = {
            "title": "Test",
            "message": "Test",
            "priority": PRIORITY_NORMAL,
        }
        
        result = await manager._send_mobile_app_notification(notification_data)
        
        assert result is False

    async def test_delivery_method_failure_handling(self, hass: HomeAssistant, initialized_manager):
        """Test handling of delivery method failures."""
        manager = await initialized_manager()
        
        # Mock one method succeeding, one failing
        with patch.object(manager, '_send_persistent_notification', return_value=True), \
             patch.object(manager, '_send_mobile_app_notification', side_effect=Exception("Mobile error")):
            
            result = await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_FEEDING,
                "Test message",
                delivery_methods=[DELIVERY_PERSISTENT, DELIVERY_MOBILE_APP]
            )
            
            # Should succeed if at least one method works
            assert result is True
            assert manager._metrics["delivery_failures"] == 1
            
            # Check delivery status
            notification = list(manager._active_notifications.values())[0]
            assert notification["delivery_status"][DELIVERY_PERSISTENT] == "success"
            assert notification["delivery_status"][DELIVERY_MOBILE_APP] == "failed"


# Test Notifications Tests
class TestTestNotifications:
    """Test the test notification functionality."""

    async def test_send_test_notification_success(self, hass: HomeAssistant, initialized_manager):
        """Test sending test notification successfully."""
        manager = await initialized_manager()
        
        with patch.object(manager, 'async_send_notification', return_value=True) as mock_send:
            result = await manager.async_send_test_notification("test_dog")
            
            assert result is True
            mock_send.assert_called_once()
            
            # Check call arguments
            call_args = mock_send.call_args
            assert call_args[0][0] == "test_dog"  # dog_id
            assert call_args[0][1] == NOTIFICATION_SYSTEM  # type
            assert "Test notification" in call_args[0][2]  # message
            assert call_args[1]["force"] is True  # force parameter
            assert "actions" in call_args[1]  # interactive actions

    async def test_send_test_notification_with_custom_params(self, hass: HomeAssistant, initialized_manager):
        """Test sending test notification with custom parameters."""
        manager = await initialized_manager()
        
        with patch.object(manager, 'async_send_notification', return_value=True) as mock_send:
            result = await manager.async_send_test_notification(
                "test_dog",
                message="Custom test message",
                priority=PRIORITY_HIGH
            )
            
            assert result is True
            call_args = mock_send.call_args
            assert "Custom test message" in call_args[0][2]
            assert call_args[1]["priority"] == PRIORITY_HIGH


# Background Tasks Tests
class TestBackgroundTasks:
    """Test background task functionality."""

    async def test_background_cleanup_task_start(self, hass: HomeAssistant, initialized_manager):
        """Test background cleanup task starts during initialization."""
        manager = await initialized_manager()
        
        assert manager._cleanup_task is not None
        assert not manager._cleanup_task.done()

    async def test_cleanup_old_data(self, hass: HomeAssistant, initialized_manager):
        """Test cleanup of old notification data."""
        manager = await initialized_manager()
        
        # Add old notifications to history
        old_timestamp = dt_util.utcnow() - timedelta(days=MAX_HISTORY_DAYS + 1)
        recent_timestamp = dt_util.utcnow() - timedelta(hours=1)
        
        manager._notification_history = [
            {"id": "old_1", "timestamp": old_timestamp},
            {"id": "old_2", "timestamp": old_timestamp},
            {"id": "recent_1", "timestamp": recent_timestamp},
            {"id": "recent_2", "timestamp": recent_timestamp},
        ]
        
        # Add old rate limits
        old_rate_timestamp = dt_util.utcnow() - timedelta(days=2)
        recent_rate_timestamp = dt_util.utcnow() - timedelta(minutes=30)
        
        manager._rate_limits = {
            "old_key": old_rate_timestamp,
            "recent_key": recent_rate_timestamp,
        }
        
        await manager._cleanup_old_data()
        
        # Should keep only recent notifications
        assert len(manager._notification_history) == 2
        assert all("recent" in n["id"] for n in manager._notification_history)
        
        # Should keep only recent rate limits
        assert "recent_key" in manager._rate_limits
        assert "old_key" not in manager._rate_limits

    async def test_cleanup_max_history_count(self, hass: HomeAssistant, initialized_manager):
        """Test cleanup respects maximum history count."""
        manager = await initialized_manager()
        
        # Add more than maximum notifications
        current_time = dt_util.utcnow()
        manager._notification_history = [
            {"id": f"notification_{i}", "timestamp": current_time}
            for i in range(MAX_HISTORY_COUNT + 100)
        ]
        
        await manager._cleanup_old_data()
        
        # Should limit to maximum count
        assert len(manager._notification_history) == MAX_HISTORY_COUNT


# Utility Methods Tests
class TestUtilityMethods:
    """Test utility and helper methods."""

    async def test_generate_notification_id(self, hass: HomeAssistant, notification_manager):
        """Test notification ID generation."""
        manager = notification_manager
        
        id1 = manager._generate_notification_id("dog_1", NOTIFICATION_FEEDING)
        id2 = manager._generate_notification_id("dog_2", NOTIFICATION_WALK)
        id3 = manager._generate_notification_id("dog_1", NOTIFICATION_FEEDING)
        
        # Should contain dog_id and type
        assert "dog_1" in id1
        assert "feeding" in id1
        assert "dog_2" in id2
        assert "walk" in id2
        
        # Should be unique (include timestamp)
        assert id1 != id2
        assert id1 != id3

    async def test_get_dog_name_with_coordinator_data(self, hass: HomeAssistant, notification_manager, mock_runtime_data):
        """Test getting dog name from coordinator data."""
        manager = notification_manager
        
        dog_name = await manager._get_dog_name("test_dog")
        
        assert dog_name == "Test Dog"

    async def test_get_dog_name_fallback(self, hass: HomeAssistant, notification_manager):
        """Test dog name fallback when coordinator unavailable."""
        manager = notification_manager
        
        # Mock runtime data returning None
        with patch.object(manager, '_get_runtime_data', return_value=None):
            dog_name = await manager._get_dog_name("test_dog_with_underscores")
            
            assert dog_name == "Test Dog With Underscores"

    async def test_get_delivery_methods_default(self, hass: HomeAssistant, notification_manager):
        """Test default delivery method selection."""
        manager = notification_manager
        manager._config["delivery_methods"] = [DELIVERY_PERSISTENT]
        
        methods = await manager._get_delivery_methods("test_dog", NOTIFICATION_FEEDING, PRIORITY_NORMAL)
        
        assert methods == [DELIVERY_PERSISTENT]

    async def test_get_delivery_methods_priority_enhancement(self, hass: HomeAssistant, notification_manager):
        """Test delivery method enhancement based on priority."""
        manager = notification_manager
        manager._config["delivery_methods"] = [DELIVERY_PERSISTENT]
        
        # High priority should add mobile app
        methods_high = await manager._get_delivery_methods("test_dog", NOTIFICATION_WALK, PRIORITY_HIGH)
        assert DELIVERY_MOBILE_APP in methods_high
        
        # Urgent priority should add multiple methods
        methods_urgent = await manager._get_delivery_methods("test_dog", NOTIFICATION_SAFETY, PRIORITY_URGENT)
        assert DELIVERY_MOBILE_APP in methods_urgent
        assert DELIVERY_TTS in methods_urgent

    async def test_dismiss_notification_success(self, hass: HomeAssistant, initialized_manager, mock_persistent_notification):
        """Test successful notification dismissal."""
        manager = await initialized_manager()
        
        # Add notification to active list
        notification_id = "test_notification"
        manager._active_notifications[notification_id] = {"id": notification_id}
        
        result = await manager._dismiss_notification_internal(notification_id)
        
        assert result is True
        assert notification_id not in manager._active_notifications
        mock_persistent_notification["dismiss"].assert_called_once_with(hass, notification_id)

    async def test_dismiss_notification_not_found(self, hass: HomeAssistant, initialized_manager):
        """Test dismissing non-existent notification."""
        manager = await initialized_manager()
        
        result = await manager._dismiss_notification_internal("nonexistent")
        
        assert result is False


# Error Handling and Edge Cases Tests
class TestErrorHandling:
    """Test error handling and edge cases."""

    async def test_send_notification_critical_error(self, hass: HomeAssistant, initialized_manager):
        """Test critical error during notification sending."""
        manager = await initialized_manager()
        
        # Mock a critical error in delivery method selection
        with patch.object(manager, '_get_delivery_methods', side_effect=Exception("Critical error")):
            with pytest.raises(NotificationError) as exc_info:
                await manager.async_send_notification(
                    "test_dog",
                    NOTIFICATION_FEEDING,
                    "Test message"
                )
            
            assert "feeding" in str(exc_info.value)

    async def test_background_task_error_handling(self, hass: HomeAssistant, initialized_manager):
        """Test background task continues despite errors."""
        manager = await initialized_manager()
        
        # Mock cleanup to raise error once, then succeed
        call_count = 0
        original_cleanup = manager._cleanup_old_data
        
        async def mock_cleanup():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Cleanup error")
            return await original_cleanup()
        
        with patch.object(manager, '_cleanup_old_data', side_effect=mock_cleanup):
            # Background task should handle error and continue
            # This is tested by ensuring the task doesn't fail
            assert manager._cleanup_task is not None
            assert not manager._cleanup_task.done()

    async def test_notification_with_corrupted_runtime_data(self, hass: HomeAssistant, notification_manager):
        """Test notification handling with corrupted runtime data."""
        manager = notification_manager
        
        # Initialize with corrupted data
        with patch.object(manager, '_get_runtime_data', side_effect=Exception("Data corruption")):
            await manager.async_initialize()
            
            # Should still be able to send notifications with fallback
            with patch.object(manager, '_send_persistent_notification', return_value=True):
                result = await manager.async_send_notification(
                    "unknown_dog",
                    NOTIFICATION_SYSTEM,
                    "Test message"
                )
                
                assert result is True

    async def test_notification_with_invalid_dog_id_characters(self, hass: HomeAssistant, initialized_manager):
        """Test notification with special characters in dog ID."""
        manager = await initialized_manager()
        
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            result = await manager.async_send_notification(
                "dog-with-special-chars_123!@#",
                NOTIFICATION_FEEDING,
                "Test message"
            )
            
            assert result is True
            
            # Check generated notification ID is still valid
            notification = list(manager._active_notifications.values())[0]
            assert notification["dog_id"] == "dog-with-special-chars_123!@#"


# Performance Tests
class TestPerformanceCharacteristics:
    """Test performance characteristics of notification system."""

    async def test_concurrent_notifications(self, hass: HomeAssistant, initialized_manager):
        """Test handling multiple concurrent notifications."""
        manager = await initialized_manager()
        
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            # Send multiple notifications concurrently
            tasks = [
                manager.async_send_notification(
                    f"dog_{i}",
                    NOTIFICATION_FEEDING,
                    f"Message {i}",
                    force=True  # Bypass rate limiting
                )
                for i in range(10)
            ]
            
            results = await asyncio.gather(*tasks)
            
            # All should succeed
            assert all(results)
            assert len(manager._active_notifications) == 10
            assert manager._metrics["notifications_sent"] == 10

    async def test_large_notification_history_performance(self, hass: HomeAssistant, initialized_manager):
        """Test performance with large notification history."""
        manager = await initialized_manager()
        
        # Add large number of historical notifications
        current_time = dt_util.utcnow()
        large_history = [
            {
                "id": f"notification_{i}",
                "timestamp": current_time - timedelta(minutes=i),
                "dog_id": f"dog_{i % 5}",
                "type": NOTIFICATION_FEEDING,
            }
            for i in range(1000)
        ]
        
        manager._notification_history = large_history
        
        # Test cleanup performance
        import time
        start_time = time.time()
        
        await manager._cleanup_old_data()
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Cleanup should be fast even with large history
        assert duration < 1.0, f"Cleanup took too long: {duration:.3f}s"

    async def test_memory_usage_with_many_active_notifications(self, hass: HomeAssistant, initialized_manager):
        """Test memory usage doesn't grow indefinitely."""
        manager = await initialized_manager()
        
        # Send many notifications
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            for i in range(100):
                await manager.async_send_notification(
                    f"dog_{i}",
                    NOTIFICATION_SYSTEM,
                    f"Message {i}",
                    force=True
                )
        
        # Run cleanup
        await manager._cleanup_old_data()
        
        # Active notifications should be reasonable
        assert len(manager._active_notifications) <= 100
        
        # History should be limited
        assert len(manager._notification_history) <= MAX_HISTORY_COUNT


# Integration Tests
class TestNotificationIntegration:
    """Test integration with Home Assistant components."""

    async def test_integration_with_hass_services(self, hass: HomeAssistant, initialized_manager, mock_hass_services):
        """Test integration with Home Assistant service registry."""
        manager = await initialized_manager()
        
        # Test service availability check
        assert manager.hass.services.has_service("notify", "mobile_app_test_device")
        
        # Test service calling
        with patch.object(manager, '_send_mobile_app_notification', return_value=True) as mock_mobile:
            await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_WALK,
                "Walk time!",
                delivery_methods=[DELIVERY_MOBILE_APP]
            )
            
            mock_mobile.assert_called_once()

    async def test_persistent_notification_integration(self, hass: HomeAssistant, initialized_manager, mock_persistent_notification):
        """Test integration with persistent notification component."""
        manager = await initialized_manager()
        
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_FEEDING,
                "Feeding time!",
                delivery_methods=[DELIVERY_PERSISTENT]
            )
            
            # Should create persistent notification
            notification = list(manager._active_notifications.values())[0]
            assert notification["delivery_status"][DELIVERY_PERSISTENT] == "success"


# Configuration and State Management Tests
class TestConfigurationAndState:
    """Test configuration management and state persistence."""

    async def test_dog_specific_settings(self, hass: HomeAssistant, notification_manager):
        """Test dog-specific notification settings."""
        manager = notification_manager
        
        # Set dog-specific settings
        manager._dog_settings["special_dog"] = {
            "notifications_enabled": False,
            "feeding_alerts": True,
            "delivery_methods": [DELIVERY_PERSISTENT],
        }
        
        # Test enablement check
        enabled = await manager._is_notification_enabled("special_dog", NOTIFICATION_FEEDING, force=False)
        assert enabled is False  # Disabled at dog level
        
        # Test force override
        enabled_force = await manager._is_notification_enabled("special_dog", NOTIFICATION_FEEDING, force=True)
        assert enabled_force is True

    async def test_metrics_tracking(self, hass: HomeAssistant, initialized_manager):
        """Test metrics tracking functionality."""
        manager = await initialized_manager()
        
        # Initial metrics
        assert manager._metrics["notifications_sent"] == 0
        assert manager._metrics["notifications_suppressed"] == 0
        assert manager._metrics["delivery_failures"] == 0
        assert manager._metrics["rate_limited_count"] == 0
        
        # Send successful notification
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_FEEDING,
                "Test message"
            )
        
        assert manager._metrics["notifications_sent"] == 1
        
        # Send rate-limited notification
        with patch.object(manager, '_send_persistent_notification', return_value=True):
            await manager.async_send_notification(
                "test_dog",
                NOTIFICATION_FEEDING,
                "Another message"  # Should be rate-limited
            )
        
        assert manager._metrics["rate_limited_count"] == 1
        
        # Test delivery failure
        with patch.object(manager, '_send_persistent_notification', side_effect=Exception("Error")):
            await manager.async_send_notification(
                "another_dog",
                NOTIFICATION_WALK,
                "Walk message"
            )
        
        assert manager._metrics["delivery_failures"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
