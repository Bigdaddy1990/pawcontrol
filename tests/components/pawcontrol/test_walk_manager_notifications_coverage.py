"""Targeted coverage for walk transitions and notification runtime guards."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.pawcontrol.notifications import (
    NotificationChannel,
    NotificationConfig,
    NotificationEvent,
    NotificationPriority,
    NotificationType,
    PawControlNotificationManager,
)
from custom_components.pawcontrol.walk_manager import WalkManager


class _ValidSession:
    """Minimal aiohttp-compatible session used by notification manager tests."""

    closed = False

    async def request(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_walk_manager_invalid_and_restarted_transition_updates_state() -> None:
    """Walk manager should reject unknown dogs and restart existing sessions cleanly."""
    manager = WalkManager()
    await manager.async_initialize(["dog-1"])

    with pytest.raises(KeyError):
        await manager.async_start_walk("missing-dog")

    first_walk_id = await manager.async_start_walk("dog-1", walk_type="manual")
    assert first_walk_id is not None
    assert manager._walk_data["dog-1"]["walk_in_progress"] is True

    second_walk_id = await manager.async_start_walk("dog-1", walk_type="auto_detected")

    assert second_walk_id is not None
    assert second_walk_id != first_walk_id
    assert manager._walk_data["dog-1"]["walk_in_progress"] is True
    assert len(manager._walk_history["dog-1"]) == 1
    assert manager._walk_history["dog-1"][0]["status"] == "completed"
    await manager.async_shutdown()


@pytest.mark.asyncio
async def test_walk_manager_detection_trigger_adds_and_throttles_points() -> None:
    """Auto detection should start a walk and avoid duplicate point writes."""
    manager = WalkManager()
    await manager.async_initialize(["dog-1"])

    fixed_now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    with patch(
        "custom_components.pawcontrol.walk_manager.dt_util.now", return_value=fixed_now
    ):
        await manager._process_walk_detection_optimized(
            "dog-1",
            (52.52, 13.40),
            (52.5203, 13.4003),
            speed=1.2,
        )
        await manager._process_walk_detection_optimized(
            "dog-1",
            (52.5203, 13.4003),
            (52.5203, 13.4003),
            speed=1.2,
        )

    current_walk = manager._current_walks["dog-1"]
    assert current_walk["walk_type"] == "auto_detected"
    assert len(current_walk["path"]) == 1
    await manager.async_shutdown()


@pytest.mark.asyncio
async def test_notification_send_applies_static_fallback_and_rate_limit(hass) -> None:
    """Static fallback targets should be used once, then rate-limit duplicates."""
    manager = PawControlNotificationManager(hass, "entry-1", session=_ValidSession())
    manager._send_to_channels = AsyncMock()  # type: ignore[method-assign]
    manager._person_manager = SimpleNamespace(
        get_notification_targets=lambda **_kwargs: []
    )
    manager._configs["dog-1"] = NotificationConfig(
        channels=[NotificationChannel.MOBILE],
        use_person_entities=True,
        fallback_to_static=True,
        custom_settings={"mobile_services": ["mobile_app_primary"]},
        rate_limit={"mobile_limit_minutes": 5},
        batch_enabled=False,
    )

    first_id = await manager.async_send_notification(
        NotificationType.WALK_REMINDER,
        "Walk now",
        "Go outside",
        dog_id="dog-1",
        allow_batching=False,
    )
    second_id = await manager.async_send_notification(
        NotificationType.WALK_REMINDER,
        "Walk now",
        "Go outside",
        dog_id="dog-1",
        allow_batching=False,
    )

    assert first_id != second_id
    manager._send_to_channels.assert_awaited_once()
    sent_notification = manager._send_to_channels.await_args.args[0]
    assert sent_notification.notification_services == ["mobile_app_primary"]
    assert manager.get_performance_metrics()["static_fallback_notifications"] == 2
    assert manager.get_performance_metrics()["rate_limit_blocks"] == 1
    assert len(manager._notifications) == 1


@pytest.mark.asyncio
async def test_notification_mobile_delivery_dedupes_failed_services(hass) -> None:
    """Failed mobile service deliveries should be deduplicated deterministically."""
    hass.services = SimpleNamespace(async_services=lambda: {"notify": {}})
    manager = PawControlNotificationManager(hass, "entry-1", session=_ValidSession())

    notification = NotificationEvent(
        id="n-1",
        dog_id="dog-1",
        notification_type=NotificationType.WALK_REMINDER,
        priority=NotificationPriority.NORMAL,
        title="Walk",
        message="Now",
        created_at=datetime(2026, 4, 7, 13, 0, tzinfo=UTC),
        channels=[NotificationChannel.MOBILE],
        notification_services=["notify_me", "notify_me"],
    )

    await manager._send_mobile_notification(notification)

    assert notification.failed_notification_services == ["notify_me"]
    status = manager.get_delivery_status_snapshot()["services"]["notify_me"]
    assert status["consecutive_failures"] == 2
    assert status["last_error_reason"] == "missing_service"


@pytest.mark.asyncio
async def test_notification_mobile_fallback_records_guard_failure_reason(hass) -> None:
    """Fallback mobile delivery should persist guard-result rejection reasons."""
    hass.services = SimpleNamespace(
        async_services=lambda: {"notify": {"mobile_app": object()}}
    )
    manager = PawControlNotificationManager(hass, "entry-1", session=_ValidSession())
    manager._configs["dog-1"] = NotificationConfig(
        channels=[NotificationChannel.MOBILE],
        custom_settings={"mobile_service": "mobile_app"},
    )

    notification = NotificationEvent(
        id="n-2",
        dog_id="dog-1",
        notification_type=NotificationType.WALK_REMINDER,
        priority=NotificationPriority.NORMAL,
        title="Walk",
        message="Now",
        created_at=datetime(2026, 4, 7, 13, 30, tzinfo=UTC),
        channels=[NotificationChannel.MOBILE],
    )

    with patch(
        "custom_components.pawcontrol.notifications.async_call_hass_service_if_available",
        return_value=SimpleNamespace(executed=False, reason="service_not_registered"),
    ):
        await manager._send_mobile_notification(notification)

    assert notification.failed_notification_services == ["mobile_app"]
    status = manager.get_delivery_status_snapshot()["services"]["mobile_app"]
    assert status["consecutive_failures"] == 1
    assert status["last_error_reason"] == "unknown"
