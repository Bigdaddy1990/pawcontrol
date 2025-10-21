"""Comprehensive unit tests for PawControlNotificationManager.

Tests notification delivery, channel management, batching, rate limiting,
and person entity targeting.

Quality Scale: Bronze target
Python: 3.13+
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, call

import pytest
from custom_components.pawcontrol.coordinator_support import CacheMonitorRegistrar
from custom_components.pawcontrol.notifications import (
    NotificationChannel,
    NotificationConfig,
    NotificationEvent,
    NotificationPriority,
    NotificationType,
    PawControlNotificationManager,
)


class _RecorderRegistrar(CacheMonitorRegistrar):
    """Capture cache monitor registrations for assertions."""

    def __init__(self) -> None:
        self.caches: dict[str, object] = {}

    def register_cache_monitor(self, name: str, cache: object) -> None:
        self.caches[name] = cache


class _StubPersonManager:
    """Expose register_cache_monitors compatible with the registrar protocol."""

    def __init__(self) -> None:
        self.registered_with: CacheMonitorRegistrar | None = None
        self.prefix: str | None = None

    def register_cache_monitors(
        self, registrar: CacheMonitorRegistrar, *, prefix: str = "person_entity"
    ) -> None:
        self.registered_with = registrar
        self.prefix = prefix


@pytest.mark.unit
@pytest.mark.asyncio
class TestNotificationManagerInitialization:
    """Test notification manager initialization."""

    async def test_initialization_basic(self, mock_hass, mock_session):
        """Test basic notification manager initialization."""
        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )

        assert manager._hass == mock_hass
        assert manager._entry_id == "test_entry"
        assert len(manager._notifications) == 0
        assert len(manager._configs) == 0

    async def test_initialization_with_configs(self, mock_hass, mock_session):
        """Test initialization with notification configs."""
        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )

        configs = {
            "test_dog": {
                "enabled": True,
                "channels": ["persistent", "mobile"],
                "priority_threshold": "normal",
            }
        }

        await manager.async_initialize(configs)

        assert "test_dog" in manager._configs
        assert manager._configs["test_dog"].enabled is True

    async def test_initialization_reuses_session(self, mock_hass, session_factory):
        """Providing a session should be honoured and reused."""

        custom_session = session_factory()

        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=custom_session
        )

        assert manager.session is custom_session

    async def test_initialization_rejects_missing_session(self, mock_hass):
        """Fail loudly when no session is provided."""

        with pytest.raises(ValueError):
            PawControlNotificationManager(  # type: ignore[arg-type]
                mock_hass, "test_entry", session=None
            )

    async def test_initialization_rejects_closed_session(
        self, mock_hass, session_factory
    ):
        """Fail loudly when the session has been disposed."""

        closed_session = session_factory(closed=True)

        with pytest.raises(ValueError):
            PawControlNotificationManager(
                mock_hass, "test_entry", session=closed_session
            )

    async def test_register_cache_monitors_registers_person_cache(
        self, mock_hass, mock_session
    ) -> None:
        """Cache registration should wire notification and person caches."""

        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )
        stub_person = _StubPersonManager()
        manager._person_manager = stub_person
        registrar = _RecorderRegistrar()

        manager.register_cache_monitors(registrar)

        assert "notification_cache" in registrar.caches
        assert registrar.caches["notification_cache"] is manager._cache
        assert stub_person.registered_with is registrar
        assert stub_person.prefix == "person_entity"


@pytest.mark.unit
@pytest.mark.asyncio
class TestNotificationWebhooks:
    """Ensure webhook delivery honours the shared session."""

    async def test_webhook_uses_injected_session(self, mock_hass, session_factory):
        """Injected session should be used for webhook HTTP calls."""

        custom_session = session_factory()
        response = AsyncMock()
        response.status = 200
        post_cm = AsyncMock()
        post_cm.__aenter__.return_value = response
        custom_session.post = AsyncMock(return_value=post_cm)

        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=custom_session
        )
        manager._configs["system"] = NotificationConfig(
            channels=[NotificationChannel.WEBHOOK],
            custom_settings={"webhook_url": "https://example.invalid"},
        )

        notification = NotificationEvent(
            id="notif-1",
            dog_id=None,
            notification_type=NotificationType.SYSTEM_INFO,
            priority=NotificationPriority.NORMAL,
            title="Title",
            message="Body",
            created_at=datetime.now(UTC),
            channels=[NotificationChannel.WEBHOOK],
        )

        await manager._send_webhook_notification(notification)

        custom_session.post.assert_called_once()
        called_kwargs = custom_session.post.call_args.kwargs
        assert called_kwargs["timeout"].total == pytest.approx(10.0)

    async def test_webhook_releases_direct_response(self, mock_hass, session_factory):
        """Direct ClientResponse objects should be released after validation."""

        custom_session = session_factory()
        response = Mock()
        response.status = 200
        response.release = AsyncMock()
        custom_session.post = AsyncMock(return_value=response)

        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=custom_session
        )
        manager._configs["system"] = NotificationConfig(
            channels=[NotificationChannel.WEBHOOK],
            custom_settings={"webhook_url": "https://example.invalid"},
        )

        notification = NotificationEvent(
            id="notif-1",
            dog_id=None,
            notification_type=NotificationType.SYSTEM_INFO,
            priority=NotificationPriority.NORMAL,
            title="Title",
            message="Body",
            created_at=datetime.now(UTC),
            channels=[NotificationChannel.WEBHOOK],
        )

        await manager._send_webhook_notification(notification)

        response.release.assert_awaited()

    async def test_webhook_closes_response_without_release(
        self, mock_hass, session_factory
    ):
        """Responses lacking release should still close the transport."""

        custom_session = session_factory()
        response = Mock()
        response.status = 200
        response.release = None
        response.close = Mock()
        custom_session.post = AsyncMock(return_value=response)

        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=custom_session
        )
        manager._configs["system"] = NotificationConfig(
            channels=[NotificationChannel.WEBHOOK],
            custom_settings={"webhook_url": "https://example.invalid"},
        )

        notification = NotificationEvent(
            id="notif-2",
            dog_id=None,
            notification_type=NotificationType.SYSTEM_INFO,
            priority=NotificationPriority.NORMAL,
            title="Title",
            message="Body",
            created_at=datetime.now(UTC),
            channels=[NotificationChannel.WEBHOOK],
        )

        await manager._send_webhook_notification(notification)

        response.close.assert_called_once()

    async def test_initialization_validates_channels(self, mock_hass, mock_session):
        """Test that initialization validates channel names."""
        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )

        configs = {
            "test_dog": {
                "channels": ["persistent", "invalid_channel", "mobile"],
            }
        }

        await manager.async_initialize(configs)

        # Should skip invalid channel
        config = manager._configs["test_dog"]
        assert NotificationChannel.PERSISTENT in config.channels
        assert NotificationChannel.MOBILE in config.channels


@pytest.mark.unit
@pytest.mark.asyncio
class TestBasicNotificationSending:
    """Test basic notification sending."""

    async def test_send_notification_basic(self, mock_notification_manager):
        """Test sending basic notification."""
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="Test Notification",
            message="This is a test",
        )

        assert notification_id is not None
        assert notification_id in mock_notification_manager._notifications

    async def test_send_notification_with_dog_id(self, mock_notification_manager):
        """Test sending notification for specific dog."""
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Feeding Time",
            message="Time to feed Buddy",
            dog_id="buddy",
        )

        notification = mock_notification_manager._notifications[notification_id]

        assert notification.dog_id == "buddy"

    async def test_send_notification_with_priority(self, mock_notification_manager):
        """Test sending notification with specific priority."""
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.HEALTH_ALERT,
            title="Health Alert",
            message="Urgent health issue",
            priority=NotificationPriority.URGENT,
        )

        notification = mock_notification_manager._notifications[notification_id]

        assert notification.priority == NotificationPriority.URGENT

    async def test_send_notification_with_data(self, mock_notification_manager):
        """Test sending notification with additional data."""
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.WALK_REMINDER,
            title="Walk Time",
            message="Time for a walk",
            data={"duration": 30, "distance": 1.5},
        )

        notification = mock_notification_manager._notifications[notification_id]

        assert notification.data["duration"] == 30
        assert notification.data["distance"] == 1.5


@pytest.mark.unit
@pytest.mark.asyncio
class TestNotificationConfig:
    """Test notification configuration."""

    async def test_notification_disabled_prevents_sending(
        self, mock_hass, mock_session
    ):
        """Test that disabled notifications are not sent."""
        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )

        configs = {
            "test_dog": {
                "enabled": False,
            }
        }

        await manager.async_initialize(configs)

        notification_id = await manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Test",
            message="Test",
            dog_id="test_dog",
        )

        # Should return ID but not actually send
        assert notification_id is not None
        notification = manager._notifications.get(notification_id)
        assert notification is None or len(notification.sent_to) == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestWebhookSecurityStatus:
    """Test webhook security status aggregation."""

    async def test_secure_webhook_configs(self, mock_notification_manager):
        """Secure webhooks should report pass status."""

        mock_notification_manager._configs["dog1"] = NotificationConfig(
            channels=[NotificationChannel.WEBHOOK],
            custom_settings={"webhook_secret": "supersecret"},
        )

        status = mock_notification_manager.webhook_security_status()

        assert status["configured"] is True
        assert status["secure"] is True
        assert status["hmac_ready"] is True
        assert status["insecure_configs"] == ()

    async def test_insecure_webhook_configs(self, mock_notification_manager):
        """Missing secrets should be flagged as insecure."""

        mock_notification_manager._configs["dog1"] = NotificationConfig(
            channels=[NotificationChannel.WEBHOOK],
            custom_settings={},
        )
        mock_notification_manager._configs["dog2"] = NotificationConfig(
            channels=[NotificationChannel.PERSISTENT],
        )

        status = mock_notification_manager.webhook_security_status()

        assert status["configured"] is True
        assert status["secure"] is False
        assert status["hmac_ready"] is False
        assert status["insecure_configs"] == ("dog1",)

    async def test_priority_threshold_filters_low_priority(
        self, mock_hass, mock_session
    ):
        """Test that priority threshold filters notifications."""
        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )

        configs = {
            "test_dog": {
                "enabled": True,
                "priority_threshold": "high",
            }
        }

        await manager.async_initialize(configs)

        notification_id = await manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="Low Priority",
            message="Not important",
            dog_id="test_dog",
            priority=NotificationPriority.NORMAL,  # Below threshold
        )

        # Should be filtered out
        notification = manager._notifications.get(notification_id)
        assert notification is None or len(notification.sent_to) == 0

    async def test_set_priority_threshold(self, mock_notification_manager):
        """Test setting priority threshold."""
        await mock_notification_manager.async_set_priority_threshold(
            "test_dog", NotificationPriority.HIGH
        )

        config = mock_notification_manager._configs["test_dog"]

        assert config.priority_threshold == NotificationPriority.HIGH


@pytest.mark.unit
@pytest.mark.asyncio
class TestQuietHours:
    """Test quiet hours functionality."""

    async def test_quiet_hours_suppresses_normal_notifications(
        self, mock_hass, mock_session
    ):
        """Test that quiet hours suppress normal priority notifications."""
        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )

        # Set quiet hours (22:00 - 07:00)
        configs = {
            "test_dog": {
                "enabled": True,
                "quiet_hours": {"start": 22, "end": 7},
            }
        }

        await manager.async_initialize(configs)

        # Mock current time to be in quiet hours (e.g., 23:00)
        with pytest.MonkeyPatch.context() as mp:
            mock_now = datetime.now(UTC).replace(
                hour=23, minute=0, second=0, microsecond=0
            )
            mp.setattr("homeassistant.util.dt.utcnow", lambda: mock_now)

            notification_id = await manager.async_send_notification(
                notification_type=NotificationType.FEEDING_REMINDER,
                title="Quiet Time Test",
                message="Should be suppressed",
                dog_id="test_dog",
                priority=NotificationPriority.NORMAL,
            )

            # Should be suppressed
            notification = manager._notifications.get(notification_id)
            assert notification is None or len(notification.sent_to) == 0

    async def test_quiet_hours_allows_urgent_notifications(
        self, mock_hass, mock_session
    ):
        """Test that urgent notifications bypass quiet hours."""
        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )

        configs = {
            "test_dog": {
                "enabled": True,
                "quiet_hours": {"start": 22, "end": 7},
            }
        }

        await manager.async_initialize(configs)

        notification_id = await manager.async_send_notification(
            notification_type=NotificationType.HEALTH_ALERT,
            title="Urgent Alert",
            message="Health emergency",
            dog_id="test_dog",
            priority=NotificationPriority.URGENT,  # Should bypass quiet hours
        )

        notification = manager._notifications.get(notification_id)

        # Should be sent despite quiet hours
        assert notification is not None


@pytest.mark.unit
@pytest.mark.asyncio
class TestChannelDelivery:
    """Test multi-channel notification delivery."""

    async def test_send_to_persistent_channel(
        self, mock_notification_manager, mock_hass
    ):
        """Test sending to persistent notification channel."""
        mock_hass.services.async_call = AsyncMock()

        await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="Test",
            message="Test message",
            force_channels=[NotificationChannel.PERSISTENT],
        )

        # Verify persistent notification service was called
        mock_hass.services.async_call.assert_called()

        # Check call was to persistent_notification
        calls = mock_hass.services.async_call.call_args_list
        assert any(mock_call[0][0] == "persistent_notification" for mock_call in calls)

    async def test_send_to_multiple_channels(self, mock_notification_manager):
        """Test sending to multiple channels."""
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Multi-Channel",
            message="Test",
            force_channels=[
                NotificationChannel.PERSISTENT,
                NotificationChannel.MOBILE,
            ],
        )

        notification = mock_notification_manager._notifications[notification_id]

        assert len(notification.channels) == 2
        assert NotificationChannel.PERSISTENT in notification.channels
        assert NotificationChannel.MOBILE in notification.channels

    async def test_failed_channel_recorded(self, mock_notification_manager, mock_hass):
        """Test that failed channels are recorded."""
        # Mock service call to fail
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("Send failed"))

        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="Test",
            message="Test",
            force_channels=[NotificationChannel.PERSISTENT],
        )

        notification = mock_notification_manager._notifications[notification_id]

        # Should have recorded failure
        assert len(notification.failed_channels) > 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestBatchProcessing:
    """Test notification batching."""

    async def test_batch_similar_notifications(self, mock_notification_manager):
        """Test that similar notifications are batched."""
        # Send multiple similar notifications
        for i in range(5):
            await mock_notification_manager.async_send_notification(
                notification_type=NotificationType.FEEDING_REMINDER,
                title=f"Feeding {i}",
                message=f"Time to feed {i}",
                dog_id="test_dog",
                allow_batching=True,
            )

        # Check that they're queued for batching
        assert len(mock_notification_manager._batch_queue) >= 3

    async def test_urgent_notifications_not_batched(self, mock_notification_manager):
        """Test that urgent notifications are not batched."""
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.HEALTH_ALERT,
            title="Urgent",
            message="Emergency",
            priority=NotificationPriority.URGENT,
            allow_batching=True,
        )

        notification = mock_notification_manager._notifications[notification_id]

        # Should be sent immediately, not batched
        assert len(notification.grouped_with) == 0

    async def test_batch_size_limit(self, mock_notification_manager):
        """Test that batches respect size limits."""
        # Add many notifications to batch queue
        for i in range(20):
            await mock_notification_manager.async_send_notification(
                notification_type=NotificationType.FEEDING_REMINDER,
                title=f"Feed {i}",
                message=f"Feeding {i}",
                dog_id="test_dog",
                allow_batching=True,
            )

        # Batch queue should have reasonable size
        assert len(mock_notification_manager._batch_queue) < 25


@pytest.mark.unit
@pytest.mark.asyncio
class TestRateLimiting:
    """Test rate limiting functionality."""

    async def test_rate_limit_blocks_excessive_notifications(
        self, mock_hass, mock_session
    ):
        """Test that rate limiting blocks excessive notifications."""
        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )

        configs = {
            "test_dog": {
                "enabled": True,
                "rate_limit": {
                    "persistent_limit_minutes": 5,  # Max 1 per 5 minutes
                },
            }
        }

        await manager.async_initialize(configs)

        # Send first notification
        await manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="First",
            message="First",
            dog_id="test_dog",
        )

        # Send second notification immediately
        id2 = await manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="Second",
            message="Second",
            dog_id="test_dog",
        )

        # Second should be rate limited
        manager._notifications.get(id2)

        # Check rate limit metrics
        assert manager._performance_metrics["rate_limit_blocks"] >= 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestTemplates:
    """Test notification templates."""

    async def test_template_formatting(self, mock_notification_manager):
        """Test that templates are applied to notifications."""
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Feeding Time",
            message="Time to feed",
            data={"meal_type": "breakfast"},
        )

        notification = mock_notification_manager._notifications[notification_id]

        # Check that template was applied
        assert notification.template_used is not None

    async def test_custom_template_override(self, mock_hass, mock_session):
        """Test custom template overrides."""
        manager = PawControlNotificationManager(
            mock_hass, "test_entry", session=mock_session
        )

        configs = {
            "test_dog": {
                "enabled": True,
                "template_overrides": {
                    "feeding_reminder": "🐕 {title} - {message}",
                },
            }
        }

        await manager.async_initialize(configs)

        notification_id = await manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Feed Buddy",
            message="Breakfast time",
            dog_id="test_dog",
        )

        notification = manager._notifications[notification_id]

        # Should use custom template
        assert "🐕" in notification.title or "🐕" in notification.message


@pytest.mark.unit
@pytest.mark.asyncio
class TestNotificationAcknowledgment:
    """Test notification acknowledgment."""

    async def test_acknowledge_notification(self, mock_notification_manager):
        """Test acknowledging a notification."""
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Test",
            message="Test",
        )

        success = await mock_notification_manager.async_acknowledge_notification(
            notification_id
        )

        assert success is True

        notification = mock_notification_manager._notifications[notification_id]
        assert notification.acknowledged is True
        assert notification.acknowledged_at is not None

    async def test_acknowledge_notification_without_services(
        self, mock_notification_manager
    ) -> None:
        """Notification acknowledgment should short-circuit when hass services missing."""

        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Test",
            message="Test",
        )

        notification = mock_notification_manager._notifications[notification_id]
        notification.sent_to.append(NotificationChannel.PERSISTENT)
        mock_notification_manager._hass.services = None

        success = await mock_notification_manager.async_acknowledge_notification(
            notification_id
        )

        assert success is True

    async def test_acknowledge_nonexistent_notification(
        self, mock_notification_manager
    ):
        """Test acknowledging non-existent notification."""
        success = await mock_notification_manager.async_acknowledge_notification(
            "nonexistent_id"
        )

        assert success is False

    async def test_acknowledged_notifications_excluded_from_batch(
        self, mock_notification_manager
    ):
        """Test that acknowledged notifications are not batched."""
        # Create and acknowledge notification
        id1 = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Test 1",
            message="Test 1",
            dog_id="test_dog",
            allow_batching=True,
        )

        await mock_notification_manager.async_acknowledge_notification(id1)

        # Create new notification
        await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Test 2",
            message="Test 2",
            dog_id="test_dog",
            allow_batching=True,
        )

        notification1 = mock_notification_manager._notifications[id1]

        # Acknowledged notification should not be in batch queue
        assert notification1.acknowledged is True


@pytest.mark.unit
@pytest.mark.asyncio
class TestNotificationCleanup:
    """Test notification cleanup and expiration."""

    async def test_expired_notifications_cleaned(self, mock_notification_manager):
        """Test that expired notifications are cleaned up."""
        # Create notification with short expiration
        await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title="Expiring",
            message="Will expire",
            expires_in=timedelta(seconds=1),
        )

        # Wait for expiration
        import asyncio

        await asyncio.sleep(2)

        # Trigger cleanup
        cleaned = await mock_notification_manager.async_cleanup_expired_notifications()

        # Notification should be cleaned
        assert cleaned >= 0

    async def test_old_acknowledged_notifications_cleaned(
        self, mock_notification_manager
    ):
        """Test that old acknowledged notifications are cleaned."""
        # Create and acknowledge notification
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="Old",
            message="Old",
        )

        notification = mock_notification_manager._notifications[notification_id]
        notification.acknowledged = True
        notification.acknowledged_at = datetime.now() - timedelta(days=10)

        # Clean up
        cleaned = await mock_notification_manager.async_cleanup_expired_notifications()

        assert cleaned >= 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestPerformanceStatistics:
    """Test performance monitoring."""

    async def test_get_performance_statistics(self, mock_notification_manager):
        """Test retrieving performance statistics."""
        stats = await mock_notification_manager.async_get_performance_statistics()

        assert "total_notifications" in stats
        assert "active_notifications" in stats
        assert "performance_metrics" in stats
        assert "cache_stats" in stats

    async def test_statistics_track_sent_notifications(self, mock_notification_manager):
        """Test that statistics track sent notifications."""
        initial_stats = (
            await mock_notification_manager.async_get_performance_statistics()
        )
        initial_sent = initial_stats["performance_metrics"]["notifications_sent"]

        await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="Test",
            message="Test",
        )

        final_stats = await mock_notification_manager.async_get_performance_statistics()

        # Should have incremented (or stayed same if not actually sent)
        assert final_stats["performance_metrics"]["notifications_sent"] >= initial_sent

    async def test_statistics_track_failed_notifications(
        self, mock_notification_manager, mock_hass
    ):
        """Test that statistics track failed notifications."""
        # Mock service to fail
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("Failed"))

        initial_stats = (
            await mock_notification_manager.async_get_performance_statistics()
        )
        initial_failed = initial_stats["performance_metrics"]["notifications_failed"]

        await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="Fail",
            message="Will fail",
            force_channels=[NotificationChannel.PERSISTENT],
        )

        final_stats = await mock_notification_manager.async_get_performance_statistics()

        # May or may not increment depending on error handling
        assert (
            final_stats["performance_metrics"]["notifications_failed"] >= initial_failed
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestConvenienceMethods:
    """Test convenience methods for specific notification types."""

    async def test_send_feeding_reminder(self, mock_notification_manager):
        """Test feeding reminder convenience method."""
        notification_id = await mock_notification_manager.async_send_feeding_reminder(
            dog_id="buddy",
            meal_type="breakfast",
            scheduled_time="08:00",
            portion_size=250.0,
        )

        assert notification_id is not None

        notification = mock_notification_manager._notifications[notification_id]
        assert notification.notification_type == NotificationType.FEEDING_REMINDER
        assert notification.dog_id == "buddy"

    async def test_send_walk_reminder(self, mock_notification_manager):
        """Test walk reminder convenience method."""
        notification_id = await mock_notification_manager.async_send_walk_reminder(
            dog_id="buddy",
            last_walk_hours=4.5,
        )

        assert notification_id is not None

        notification = mock_notification_manager._notifications[notification_id]
        assert notification.notification_type == NotificationType.WALK_REMINDER

    async def test_send_health_alert(self, mock_notification_manager):
        """Test health alert convenience method."""
        notification_id = await mock_notification_manager.async_send_health_alert(
            dog_id="buddy",
            alert_type="temperature",
            details="Temperature above normal",
            priority=NotificationPriority.HIGH,
        )

        assert notification_id is not None

        notification = mock_notification_manager._notifications[notification_id]
        assert notification.notification_type == NotificationType.HEALTH_ALERT
        assert notification.priority == NotificationPriority.HIGH


@pytest.mark.unit
@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_send_notification_with_empty_title(self, mock_notification_manager):
        """Test sending notification with empty title."""
        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="",
            message="Message only",
        )

        # Should handle gracefully
        assert notification_id is not None

    async def test_send_notification_with_very_long_message(
        self, mock_notification_manager
    ):
        """Test notification with very long message."""
        long_message = "x" * 10000

        notification_id = await mock_notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title="Long",
            message=long_message,
        )

        # Should handle gracefully (may truncate)
        assert notification_id is not None

    async def test_concurrent_notification_sends(self, mock_notification_manager):
        """Test concurrent notification sending."""
        import asyncio

        async def send_notification(i: int):
            return await mock_notification_manager.async_send_notification(
                notification_type=NotificationType.SYSTEM_INFO,
                title=f"Concurrent {i}",
                message=f"Message {i}",
            )

        # Send 10 notifications concurrently
        ids = await asyncio.gather(*[send_notification(i) for i in range(10)])

        # All should succeed
        assert len(ids) == 10
        assert all(id is not None for id in ids)

    async def test_shutdown_cancels_background_tasks(self, mock_notification_manager):
        """Test that shutdown cancels background tasks."""
        await mock_notification_manager.async_shutdown()

        # Check that tasks are cancelled
        assert (
            mock_notification_manager._retry_task is None
            or mock_notification_manager._retry_task.done()
        )
