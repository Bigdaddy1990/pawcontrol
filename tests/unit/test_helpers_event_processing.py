import asyncio
from contextlib import suppress
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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


@pytest.mark.asyncio
async def test_process_feeding_batch_limits_history_and_emits_events(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """`_process_feeding_batch` should persist JSON payloads and emit events."""  # noqa: E111

  hass = MagicMock(spec=HomeAssistant)  # noqa: E111
  hass.async_create_task = MagicMock(side_effect=asyncio.create_task)  # noqa: E111

  config_entry = MagicMock(spec=ConfigEntry)  # noqa: E111
  config_entry.data = {CONF_DOGS: [{"dog_id": "dog-1"}]}  # noqa: E111
  config_entry.options = {}  # noqa: E111
  config_entry.entry_id = "entry-id"  # noqa: E111

  storage = MagicMock()  # noqa: E111
  storage.async_save_data = AsyncMock()  # noqa: E111
  storage.async_shutdown = AsyncMock()  # noqa: E111

  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.helpers.PawControlDataStorage",
    lambda *_: storage,
  )
  monkeypatch.setattr("custom_components.pawcontrol.helpers.MAX_HISTORY_ITEMS", 2)  # noqa: E111

  data_manager = PawControlData(hass, config_entry)  # noqa: E111
  feedings_namespace = data_manager._ensure_namespace("feedings")  # noqa: E111
  existing_feeding_entry = cast(  # noqa: E111
    JSONMutableMapping,
    {"timestamp": "2024-04-30T00:00:00+00:00", "meal": "dinner"},
  )
  feedings_namespace["dog-1"] = cast(JSONValue, [existing_feeding_entry])  # noqa: E111

  events: list[QueuedEvent] = [  # noqa: E111
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

  async_fire_event = AsyncMock()  # noqa: E111
  with patch(  # noqa: E111
    "custom_components.pawcontrol.helpers.async_fire_event",
    async_fire_event,
  ):
    await data_manager._process_feeding_batch(events)

  dog_history = cast(list[JSONMutableMapping], feedings_namespace["dog-1"])  # noqa: E111
  assert len(dog_history) == 2  # noqa: E111
  assert {entry["meal"] for entry in dog_history} == {"breakfast", "lunch"}  # noqa: E111
  assert all(isinstance(entry["timestamp"], str) for entry in dog_history)  # noqa: E111

  storage.async_save_data.assert_awaited_once()  # noqa: E111
  save_args = storage.async_save_data.await_args  # noqa: E111
  assert save_args.args[0] == "feedings"  # noqa: E111
  assert save_args.args[1] is feedings_namespace  # noqa: E111

  assert async_fire_event.await_count == 2  # noqa: E111
  for call in async_fire_event.await_args_list:  # noqa: E111
    assert call.args[1] == EVENT_FEEDING_LOGGED
    payload = call.args[2]
    assert payload["dog_id"] == "dog-1"
    assert isinstance(payload["timestamp"], str)


@pytest.mark.asyncio
async def test_process_health_batch_serializes_structured_events(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """`_process_health_batch` should normalize history and fire events."""  # noqa: E111

  hass = MagicMock(spec=HomeAssistant)  # noqa: E111
  hass.async_create_task = MagicMock(side_effect=asyncio.create_task)  # noqa: E111

  config_entry = MagicMock(spec=ConfigEntry)  # noqa: E111
  config_entry.data = {CONF_DOGS: [{"dog_id": "dog-1"}]}  # noqa: E111
  config_entry.options = {}  # noqa: E111
  config_entry.entry_id = "entry-id"  # noqa: E111

  storage = MagicMock()  # noqa: E111
  storage.async_save_data = AsyncMock()  # noqa: E111
  storage.async_shutdown = AsyncMock()  # noqa: E111

  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.helpers.PawControlDataStorage",
    lambda *_: storage,
  )
  monkeypatch.setattr("custom_components.pawcontrol.helpers.MAX_HISTORY_ITEMS", 3)  # noqa: E111

  data_manager = PawControlData(hass, config_entry)  # noqa: E111
  health_namespace = data_manager._ensure_namespace("health")  # noqa: E111
  existing_health_entry = cast(  # noqa: E111
    HealthHistoryEntry,
    {"timestamp": "2024-04-30T00:00:00+00:00", "weight": 12.1},
  )
  legacy_event = HealthEvent.from_raw(  # noqa: E111
    "dog-1",
    cast(
      JSONMutableMapping,
      {"timestamp": "2024-04-25T00:00:00+00:00", "weight": 12.0},
    ),
  )
  existing_health_history: list[HealthHistoryEntry | HealthEvent] = [  # noqa: E111
    existing_health_entry,
    legacy_event,
  ]
  health_namespace["dog-1"] = cast(JSONValue, existing_health_history)  # noqa: E111

  events: list[QueuedEvent] = [  # noqa: E111
    {
      "type": "health",
      "dog_id": "dog-1",
      "timestamp": "2024-05-01T08:00:00+00:00",
      "data": cast(JSONMutableMapping, {"weight": 12.3, "heart_rate": 75}),
    }
  ]

  async_fire_event = AsyncMock()  # noqa: E111
  with patch(  # noqa: E111
    "custom_components.pawcontrol.helpers.async_fire_event",
    async_fire_event,
  ):
    await data_manager._process_health_batch(events)

  dog_history = cast(list[HealthHistoryEntry], health_namespace["dog-1"])  # noqa: E111
  assert len(dog_history) == 3  # noqa: E111
  assert all(isinstance(entry, dict) for entry in dog_history)  # noqa: E111
  assert {entry["weight"] for entry in dog_history} == {12.0, 12.1, 12.3}  # noqa: E111
  assert all(isinstance(entry.get("timestamp"), str) for entry in dog_history)  # noqa: E111

  storage.async_save_data.assert_awaited_once()  # noqa: E111
  save_args = storage.async_save_data.await_args  # noqa: E111
  assert save_args.args[0] == "health"  # noqa: E111
  serialized = save_args.args[1]  # noqa: E111
  assert serialized["dog-1"][0]["timestamp"] == "2024-04-30T00:00:00+00:00"  # noqa: E111
  assert serialized["dog-1"][1]["timestamp"] == "2024-04-25T00:00:00+00:00"  # noqa: E111
  assert serialized["dog-1"][2]["heart_rate"] == 75  # noqa: E111

  async_fire_event.assert_awaited_once()  # noqa: E111
  event_args = async_fire_event.await_args_list[0]  # noqa: E111
  assert event_args.args[1] == EVENT_HEALTH_LOGGED  # noqa: E111
  payload = event_args.args[2]  # noqa: E111
  assert payload["dog_id"] == "dog-1"  # noqa: E111
  assert payload["heart_rate"] == 75  # noqa: E111


@pytest.mark.asyncio
async def test_process_walk_batch_normalizes_storage(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """`_process_walk_batch` should persist JSON payloads and merge sessions."""  # noqa: E111

  hass = MagicMock(spec=HomeAssistant)  # noqa: E111
  hass.async_create_task = MagicMock(side_effect=asyncio.create_task)  # noqa: E111

  config_entry = MagicMock(spec=ConfigEntry)  # noqa: E111
  config_entry.data = {CONF_DOGS: [{"dog_id": "dog-1"}]}  # noqa: E111
  config_entry.options = {}  # noqa: E111
  config_entry.entry_id = "entry-id"  # noqa: E111

  storage = MagicMock()  # noqa: E111
  storage.async_save_data = AsyncMock()  # noqa: E111
  storage.async_shutdown = AsyncMock()  # noqa: E111

  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.helpers.PawControlDataStorage",
    lambda *_: storage,
  )
  monkeypatch.setattr("custom_components.pawcontrol.helpers.MAX_HISTORY_ITEMS", 3)  # noqa: E111

  data_manager = PawControlData(hass, config_entry)  # noqa: E111
  walk_namespace = data_manager._ensure_namespace("walks")  # noqa: E111
  legacy_active = WalkEvent.from_raw(  # noqa: E111
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
  walk_namespace["dog-1"] = cast(  # noqa: E111
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

  events: list[QueuedEvent] = [  # noqa: E111
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

  async_fire_event = AsyncMock()  # noqa: E111
  with patch(  # noqa: E111
    "custom_components.pawcontrol.helpers.async_fire_event",
    async_fire_event,
  ):
    await data_manager._process_walk_batch(events)

  walk_entry = cast(WalkNamespaceMutableEntry, walk_namespace["dog-1"])  # noqa: E111
  history = cast(list[JSONMutableMapping], walk_entry["history"])  # noqa: E111
  assert len(history) == 2  # noqa: E111
  assert all(isinstance(entry, dict) for entry in history)  # noqa: E111
  final_entry = history[0]  # noqa: E111
  assert final_entry["session_id"] == "session-1"  # noqa: E111
  assert final_entry["duration"] == 40  # noqa: E111
  assert final_entry["route"] == "morning"  # noqa: E111
  assert final_entry["distance"] == 1.5  # noqa: E111
  assert walk_entry["active"] is None  # noqa: E111
  assert walk_entry["metadata"] == {"surface": "trail"}  # noqa: E111

  storage.async_save_data.assert_awaited_once()  # noqa: E111
  save_args = storage.async_save_data.await_args  # noqa: E111
  assert save_args.args[0] == "walks"  # noqa: E111
  serialized = save_args.args[1]  # noqa: E111
  serialized_entry = cast(dict[str, object], serialized["dog-1"])  # noqa: E111
  assert serialized_entry["active"] is None  # noqa: E111
  serialized_history = cast(list[object], serialized_entry["history"])  # noqa: E111
  assert all(isinstance(entry, dict) for entry in serialized_history)  # noqa: E111

  assert async_fire_event.await_count == 2  # noqa: E111
  event_types = [call.args[1] for call in async_fire_event.await_args_list]  # noqa: E111
  assert event_types == [EVENT_WALK_STARTED, EVENT_WALK_ENDED]  # noqa: E111


@pytest.mark.asyncio
async def test_process_walk_batch_sorts_history_descending(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Walk history should be sorted newest first and trimmed to the limit."""  # noqa: E111

  hass = MagicMock(spec=HomeAssistant)  # noqa: E111
  hass.async_create_task = MagicMock(side_effect=asyncio.create_task)  # noqa: E111

  config_entry = MagicMock(spec=ConfigEntry)  # noqa: E111
  config_entry.data = {CONF_DOGS: [{"dog_id": "dog-1"}]}  # noqa: E111
  config_entry.options = {}  # noqa: E111
  config_entry.entry_id = "entry-id"  # noqa: E111

  storage = MagicMock()  # noqa: E111
  storage.async_save_data = AsyncMock()  # noqa: E111
  storage.async_shutdown = AsyncMock()  # noqa: E111

  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.helpers.PawControlDataStorage",
    lambda *_: storage,
  )
  monkeypatch.setattr("custom_components.pawcontrol.helpers.MAX_HISTORY_ITEMS", 2)  # noqa: E111

  data_manager = PawControlData(hass, config_entry)  # noqa: E111
  walk_namespace = data_manager._ensure_namespace("walks")  # noqa: E111
  walk_namespace["dog-1"] = cast(  # noqa: E111
    JSONValue,
    {
      "active": None,
      "history": cast(
        JSONValue,
        [
          {
            "session_id": "legacy-old",
            "timestamp": "2024-04-01T10:00:00+00:00",
          },
          {"session_id": "legacy-missing"},
          {
            "session_id": "legacy-new",
            "timestamp": "2024-05-01T12:00:00+00:00",
          },
        ],
      ),
    },
  )

  events: list[QueuedEvent] = [  # noqa: E111
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

  async_fire_event = AsyncMock()  # noqa: E111
  with patch(  # noqa: E111
    "custom_components.pawcontrol.helpers.async_fire_event",
    async_fire_event,
  ):
    await data_manager._process_walk_batch(events)

  walk_entry = cast(WalkNamespaceMutableEntry, walk_namespace["dog-1"])  # noqa: E111
  history = cast(list[JSONMutableMapping], walk_entry["history"])  # noqa: E111
  assert len(history) == 2  # noqa: E111
  assert [entry["session_id"] for entry in history] == [  # noqa: E111
    "session-new",
    "legacy-new",
  ]
  assert history[0]["timestamp"] == "2024-05-02T07:45:00+00:00"  # noqa: E111
  assert history[1]["timestamp"] == "2024-05-01T12:00:00+00:00"  # noqa: E111

  storage.async_save_data.assert_awaited_once()  # noqa: E111
  serialized = storage.async_save_data.await_args.args[1]  # noqa: E111
  serialized_entry = cast(dict[str, object], serialized["dog-1"])  # noqa: E111
  serialized_history = cast(list[JSONMutableMapping], serialized_entry["history"])  # noqa: E111
  assert [entry["session_id"] for entry in serialized_history] == [  # noqa: E111
    "session-new",
    "legacy-new",
  ]

  assert async_fire_event.await_count == 2  # noqa: E111


@pytest.mark.asyncio
async def test_async_process_notifications_prioritizes_high_priority(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """High-priority notifications should be delivered ahead of normal ones."""  # noqa: E111

  hass = MagicMock(spec=HomeAssistant)  # noqa: E111
  hass.async_create_task = MagicMock(side_effect=asyncio.create_task)  # noqa: E111

  config_entry = MagicMock(spec=ConfigEntry)  # noqa: E111
  config_entry.options = {}  # noqa: E111
  config_entry.data = {}  # noqa: E111

  with patch(  # noqa: E111
    "custom_components.pawcontrol.helpers.PawControlNotificationManager._setup_async_processor",
    lambda self: None,
  ):
    notification_manager = PawControlNotificationManager(hass, config_entry)

  monkeypatch.setattr(  # noqa: E111
    notification_manager,
    "_should_send_notification",
    MagicMock(return_value=True),
  )

  original_sleep = asyncio.sleep  # noqa: E111
  sleep_calls: list[float] = []  # noqa: E111

  async def fast_sleep(delay: float) -> None:  # noqa: E111
    sleep_calls.append(delay)
    await original_sleep(0)

  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.helpers.asyncio.sleep",
    fast_sleep,
  )

  send_calls: list[QueuedNotificationPayload] = []  # noqa: E111

  async def capture(notification: QueuedNotificationPayload) -> None:  # noqa: E111
    send_calls.append(notification)

  monkeypatch.setattr(  # noqa: E111
    notification_manager,
    "_send_notification_now",
    AsyncMock(side_effect=capture),
  )

  await notification_manager.async_send_notification(  # noqa: E111
    dog_id="dog-1",
    title="Urgent check",
    message="Immediate attention required",
    priority=cast(NotificationPriority, "urgent"),
    data=cast(JSONMutableMapping, {"retries": 1}),
  )
  await notification_manager.async_send_notification(  # noqa: E111
    dog_id="dog-1",
    title="Daily summary",
    message="Routine update",
    priority=cast(NotificationPriority, "normal"),
    data=cast(JSONMutableMapping, {"notes": "synced"}),
  )

  task = asyncio.create_task(notification_manager._async_process_notifications())  # noqa: E111

  try:  # noqa: E111
    for _ in range(10):
      await original_sleep(0)  # noqa: E111
      if len(send_calls) == 2 and 30 in sleep_calls:  # noqa: E111
        break
  finally:  # noqa: E111
    task.cancel()
    with suppress(asyncio.CancelledError):
      await task  # noqa: E111

  assert [call["priority"] for call in send_calls] == ["urgent", "normal"]  # noqa: E111
  assert all(isinstance(call["data"], dict) for call in send_calls)  # noqa: E111
  assert 30 in sleep_calls  # noqa: E111
  assert not notification_manager._high_priority_queue  # noqa: E111
  assert not notification_manager._notification_queue  # noqa: E111
