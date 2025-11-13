from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOGS,
    EVENT_FEEDING_LOGGED,
    EVENT_HEALTH_LOGGED,
)
from custom_components.pawcontrol.helpers import (
    PawControlData,
    PawControlNotificationManager,
    QueuedEvent,
)
from custom_components.pawcontrol.types import (
    HealthEvent,
    HealthHistoryEntry,
    JSONMutableMapping,
    JSONValue,
    NotificationPriority,
    QueuedNotificationPayload,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_process_feeding_batch_limits_history_and_emits_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_process_feeding_batch` should persist JSON payloads and emit events."""

    hass = MagicMock(spec=HomeAssistant)
    hass.async_create_task = MagicMock(side_effect=asyncio.create_task)

    config_entry = MagicMock(spec=ConfigEntry)
    config_entry.data = {CONF_DOGS: [{"dog_id": "dog-1"}]}
    config_entry.options = {}
    config_entry.entry_id = "entry-id"

    storage = MagicMock()
    storage.async_save_data = AsyncMock()
    storage.async_shutdown = AsyncMock()

    monkeypatch.setattr(
        "custom_components.pawcontrol.helpers.PawControlDataStorage",
        lambda *_: storage,
    )
    monkeypatch.setattr("custom_components.pawcontrol.helpers.MAX_HISTORY_ITEMS", 2)

    data_manager = PawControlData(hass, config_entry)
    feedings_namespace = data_manager._ensure_namespace("feedings")
    existing_feeding_entry = cast(
        JSONMutableMapping,
        {"timestamp": "2024-04-30T00:00:00+00:00", "meal": "dinner"},
    )
    feedings_namespace["dog-1"] = cast(JSONValue, [existing_feeding_entry])

    events: list[QueuedEvent] = [
        {
            "type": "feeding",
            "dog_id": "dog-1",
            "timestamp": "2024-05-01T08:00:00+00:00",
            "data": cast(JSONMutableMapping, {"meal": "breakfast", "calories": 320}),
        },
        {
            "type": "feeding",
            "dog_id": "dog-1",
            "timestamp": "2024-05-01T12:00:00+00:00",
            "data": cast(JSONMutableMapping, {"meal": "lunch"}),
        },
    ]

    async_fire_event = AsyncMock()
    with patch(
        "custom_components.pawcontrol.helpers.async_fire_event",
        async_fire_event,
    ):
        await data_manager._process_feeding_batch(events)

    dog_history = cast(list[JSONMutableMapping], feedings_namespace["dog-1"])
    assert len(dog_history) == 2
    assert {entry["meal"] for entry in dog_history} == {"breakfast", "lunch"}
    assert all(isinstance(entry["timestamp"], str) for entry in dog_history)

    storage.async_save_data.assert_awaited_once()
    save_args = storage.async_save_data.await_args
    assert save_args.args[0] == "feedings"
    assert save_args.args[1] is feedings_namespace

    assert async_fire_event.await_count == 2
    for call in async_fire_event.await_args_list:
        assert call.args[1] == EVENT_FEEDING_LOGGED
        payload = call.args[2]
        assert payload["dog_id"] == "dog-1"
        assert isinstance(payload["timestamp"], str)


@pytest.mark.asyncio
async def test_process_health_batch_serializes_structured_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_process_health_batch` should normalize history and fire events."""

    hass = MagicMock(spec=HomeAssistant)
    hass.async_create_task = MagicMock(side_effect=asyncio.create_task)

    config_entry = MagicMock(spec=ConfigEntry)
    config_entry.data = {CONF_DOGS: [{"dog_id": "dog-1"}]}
    config_entry.options = {}
    config_entry.entry_id = "entry-id"

    storage = MagicMock()
    storage.async_save_data = AsyncMock()
    storage.async_shutdown = AsyncMock()

    monkeypatch.setattr(
        "custom_components.pawcontrol.helpers.PawControlDataStorage",
        lambda *_: storage,
    )
    monkeypatch.setattr("custom_components.pawcontrol.helpers.MAX_HISTORY_ITEMS", 2)

    data_manager = PawControlData(hass, config_entry)
    health_namespace = data_manager._ensure_namespace("health")
    existing_health_entry = cast(
        HealthHistoryEntry,
        {"timestamp": "2024-04-30T00:00:00+00:00", "weight": 12.1},
    )
    existing_health_history: list[HealthHistoryEntry] = [existing_health_entry]
    health_namespace["dog-1"] = cast(JSONValue, existing_health_history)

    events: list[QueuedEvent] = [
        {
            "type": "health",
            "dog_id": "dog-1",
            "timestamp": "2024-05-01T08:00:00+00:00",
            "data": cast(JSONMutableMapping, {"weight": 12.3, "heart_rate": 75}),
        }
    ]

    async_fire_event = AsyncMock()
    with patch(
        "custom_components.pawcontrol.helpers.async_fire_event",
        async_fire_event,
    ):
        await data_manager._process_health_batch(events)

    dog_history = cast(list[HealthHistoryEntry], health_namespace["dog-1"])
    assert len(dog_history) == 2
    assert all(isinstance(entry, HealthEvent) for entry in dog_history)

    storage.async_save_data.assert_awaited_once()
    save_args = storage.async_save_data.await_args
    assert save_args.args[0] == "health"
    serialized = save_args.args[1]
    assert serialized["dog-1"][0]["timestamp"] == "2024-04-30T00:00:00+00:00"
    assert serialized["dog-1"][1]["heart_rate"] == 75

    async_fire_event.assert_awaited_once()
    event_args = async_fire_event.await_args_list[0]
    assert event_args.args[1] == EVENT_HEALTH_LOGGED
    payload = event_args.args[2]
    assert payload["dog_id"] == "dog-1"
    assert payload["heart_rate"] == 75


@pytest.mark.asyncio
async def test_async_process_notifications_prioritizes_high_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High-priority notifications should be delivered ahead of normal ones."""

    hass = MagicMock(spec=HomeAssistant)
    hass.async_create_task = MagicMock(side_effect=asyncio.create_task)

    config_entry = MagicMock(spec=ConfigEntry)
    config_entry.options = {}
    config_entry.data = {}

    with patch(
        "custom_components.pawcontrol.helpers.PawControlNotificationManager._setup_async_processor",
        lambda self: None,
    ):
        notification_manager = PawControlNotificationManager(hass, config_entry)

    monkeypatch.setattr(
        notification_manager,
        "_should_send_notification",
        MagicMock(return_value=True),
    )

    original_sleep = asyncio.sleep
    sleep_calls: list[float] = []

    async def fast_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        await original_sleep(0)

    monkeypatch.setattr(
        "custom_components.pawcontrol.helpers.asyncio.sleep",
        fast_sleep,
    )

    send_calls: list[QueuedNotificationPayload] = []

    async def capture(notification: QueuedNotificationPayload) -> None:
        send_calls.append(notification)

    monkeypatch.setattr(
        notification_manager,
        "_send_notification_now",
        AsyncMock(side_effect=capture),
    )

    await notification_manager.async_send_notification(
        dog_id="dog-1",
        title="Urgent check",
        message="Immediate attention required",
        priority=cast(NotificationPriority, "urgent"),
        data=cast(JSONMutableMapping, {"retries": 1}),
    )
    await notification_manager.async_send_notification(
        dog_id="dog-1",
        title="Daily summary",
        message="Routine update",
        priority=cast(NotificationPriority, "normal"),
        data=cast(JSONMutableMapping, {"notes": "synced"}),
    )

    task = asyncio.create_task(notification_manager._async_process_notifications())

    try:
        for _ in range(10):
            await original_sleep(0)
            if len(send_calls) == 2 and 30 in sleep_calls:
                break
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert [call["priority"] for call in send_calls] == ["urgent", "normal"]
    assert all(isinstance(call["data"], dict) for call in send_calls)
    assert 30 in sleep_calls
    assert not notification_manager._high_priority_queue
    assert not notification_manager._notification_queue
