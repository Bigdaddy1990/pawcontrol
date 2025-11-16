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
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
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
    WalkEvent,
    WalkNamespaceMutableEntry,
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
    monkeypatch.setattr("custom_components.pawcontrol.helpers.MAX_HISTORY_ITEMS", 3)

    data_manager = PawControlData(hass, config_entry)
    health_namespace = data_manager._ensure_namespace("health")
    existing_health_entry = cast(
        HealthHistoryEntry,
        {"timestamp": "2024-04-30T00:00:00+00:00", "weight": 12.1},
    )
    legacy_event = HealthEvent.from_raw(
        "dog-1",
        cast(
            JSONMutableMapping,
            {"timestamp": "2024-04-25T00:00:00+00:00", "weight": 12.0},
        ),
    )
    existing_health_history: list[HealthHistoryEntry | HealthEvent] = [
        existing_health_entry,
        legacy_event,
    ]
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
    assert len(dog_history) == 3
    assert all(isinstance(entry, dict) for entry in dog_history)
    assert {entry["weight"] for entry in dog_history} == {12.0, 12.1, 12.3}
    assert all(isinstance(entry.get("timestamp"), str) for entry in dog_history)

    storage.async_save_data.assert_awaited_once()
    save_args = storage.async_save_data.await_args
    assert save_args.args[0] == "health"
    serialized = save_args.args[1]
    assert serialized["dog-1"][0]["timestamp"] == "2024-04-30T00:00:00+00:00"
    assert serialized["dog-1"][1]["timestamp"] == "2024-04-25T00:00:00+00:00"
    assert serialized["dog-1"][2]["heart_rate"] == 75

    async_fire_event.assert_awaited_once()
    event_args = async_fire_event.await_args_list[0]
    assert event_args.args[1] == EVENT_HEALTH_LOGGED
    payload = event_args.args[2]
    assert payload["dog_id"] == "dog-1"
    assert payload["heart_rate"] == 75


@pytest.mark.asyncio
async def test_process_walk_batch_normalizes_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_process_walk_batch` should persist JSON payloads and merge sessions."""

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
    monkeypatch.setattr("custom_components.pawcontrol.helpers.MAX_HISTORY_ITEMS", 3)

    data_manager = PawControlData(hass, config_entry)
    walk_namespace = data_manager._ensure_namespace("walks")
    legacy_active = WalkEvent.from_raw(
        "dog-1",
        cast(
            JSONMutableMapping,
            {
                "timestamp": "2024-04-30T09:00:00+00:00",
                "action": "start",
                "session_id": "session-0",
                "route": "evening",
            },
        ),
    )
    walk_namespace["dog-1"] = cast(
        JSONValue,
        {
            "active": cast(JSONValue, legacy_active),
            "history": cast(
                JSONValue,
                [
                    legacy_active.as_dict(),
                    None,
                ],
            ),
            "metadata": cast(JSONValue, {"surface": "trail"}),
        },
    )

    events: list[QueuedEvent] = [
        {
            "type": "walk",
            "dog_id": "dog-1",
            "timestamp": "2024-05-01T08:00:00+00:00",
            "data": cast(
                JSONMutableMapping,
                {"action": "start", "session_id": "session-1", "route": "morning"},
            ),
        },
        {
            "type": "walk",
            "dog_id": "dog-1",
            "timestamp": "2024-05-01T08:20:00+00:00",
            "data": cast(
                JSONMutableMapping,
                {"session_id": "session-1", "distance": 1.5},
            ),
        },
        {
            "type": "walk",
            "dog_id": "dog-1",
            "timestamp": "2024-05-01T08:40:00+00:00",
            "data": cast(
                JSONMutableMapping,
                {"action": "end", "session_id": "session-1", "duration": 40},
            ),
        },
    ]

    async_fire_event = AsyncMock()
    with patch(
        "custom_components.pawcontrol.helpers.async_fire_event",
        async_fire_event,
    ):
        await data_manager._process_walk_batch(events)

    walk_entry = cast(WalkNamespaceMutableEntry, walk_namespace["dog-1"])
    history = cast(list[JSONMutableMapping], walk_entry["history"])
    assert len(history) == 2
    assert all(isinstance(entry, dict) for entry in history)
    final_entry = history[0]
    assert final_entry["session_id"] == "session-1"
    assert final_entry["duration"] == 40
    assert final_entry["route"] == "morning"
    assert final_entry["distance"] == 1.5
    assert walk_entry["active"] is None
    assert walk_entry["metadata"] == {"surface": "trail"}

    storage.async_save_data.assert_awaited_once()
    save_args = storage.async_save_data.await_args
    assert save_args.args[0] == "walks"
    serialized = save_args.args[1]
    serialized_entry = cast(dict[str, object], serialized["dog-1"])
    assert serialized_entry["active"] is None
    serialized_history = cast(list[object], serialized_entry["history"])
    assert all(isinstance(entry, dict) for entry in serialized_history)

    assert async_fire_event.await_count == 2
    event_types = [call.args[1] for call in async_fire_event.await_args_list]
    assert event_types == [EVENT_WALK_STARTED, EVENT_WALK_ENDED]


@pytest.mark.asyncio
async def test_process_walk_batch_sorts_history_descending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walk history should be sorted newest first and trimmed to the limit."""

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
    walk_namespace = data_manager._ensure_namespace("walks")
    walk_namespace["dog-1"] = cast(
        JSONValue,
        {
            "active": None,
            "history": cast(
                JSONValue,
                [
                    {"session_id": "legacy-old", "timestamp": "2024-04-01T10:00:00+00:00"},
                    {"session_id": "legacy-missing"},
                    {"session_id": "legacy-new", "timestamp": "2024-05-01T12:00:00+00:00"},
                ],
            ),
        },
    )

    events: list[QueuedEvent] = [
        {
            "type": "walk",
            "dog_id": "dog-1",
            "timestamp": "2024-05-02T07:00:00+00:00",
            "data": cast(
                JSONMutableMapping,
                {
                    "action": "start",
                    "session_id": "session-new",
                    "route": "sunrise",
                },
            ),
        },
        {
            "type": "walk",
            "dog_id": "dog-1",
            "timestamp": "2024-05-02T07:25:00+00:00",
            "data": cast(
                JSONMutableMapping,
                {
                    "session_id": "session-new",
                    "distance": 2.4,
                },
            ),
        },
        {
            "type": "walk",
            "dog_id": "dog-1",
            "timestamp": "2024-05-02T07:45:00+00:00",
            "data": cast(
                JSONMutableMapping,
                {
                    "action": "end",
                    "session_id": "session-new",
                    "duration": 45,
                },
            ),
        },
    ]

    async_fire_event = AsyncMock()
    with patch(
        "custom_components.pawcontrol.helpers.async_fire_event",
        async_fire_event,
    ):
        await data_manager._process_walk_batch(events)

    walk_entry = cast(WalkNamespaceMutableEntry, walk_namespace["dog-1"])
    history = cast(list[JSONMutableMapping], walk_entry["history"])
    assert len(history) == 2
    assert [entry["session_id"] for entry in history] == [
        "session-new",
        "legacy-new",
    ]
    assert history[0]["timestamp"] == "2024-05-02T07:45:00+00:00"
    assert history[1]["timestamp"] == "2024-05-01T12:00:00+00:00"

    storage.async_save_data.assert_awaited_once()
    serialized = storage.async_save_data.await_args.args[1]
    serialized_entry = cast(dict[str, object], serialized["dog-1"])
    serialized_history = cast(list[JSONMutableMapping], serialized_entry["history"])
    assert [entry["session_id"] for entry in serialized_history] == [
        "session-new",
        "legacy-new",
    ]

    assert async_fire_event.await_count == 2


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
