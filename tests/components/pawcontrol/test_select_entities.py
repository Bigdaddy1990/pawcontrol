"""Tests for select entities with active configuration updates."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.notifications import (
    NotificationPriority,
    PawControlNotificationManager,
)
from custom_components.pawcontrol.select import (
    PawControlGPSSourceSelect,
    PawControlNotificationPrioritySelect,
)
from custom_components.pawcontrol.types import PawControlRuntimeData


class _DummyCoordinator:
    """Minimal coordinator implementation for select entity tests."""

    def __init__(self, hass, runtime_data: PawControlRuntimeData, dog_id: str) -> None:
        self.hass = hass
        self.config_entry = SimpleNamespace(entry_id="test-entry", runtime_data=runtime_data)
        self.data: dict[str, dict[str, object]] = {dog_id: {"gps": {}, "notifications": {}}}
        self.last_update_success = True

    def async_add_listener(self, _update_callback):  # pragma: no cover - coordinator interface
        return lambda: None

    async def async_request_refresh(self) -> None:  # pragma: no cover - coordinator interface
        return None

    async def async_set_updated_data(self, data: dict[str, dict[str, object]]) -> None:
        self.data = data

    def get_dog_data(self, dog_id: str) -> dict[str, object] | None:
        return self.data.get(dog_id)

    @property
    def available(self) -> bool:
        return True


@pytest.fixture(name="runtime_data")
def runtime_data_fixture() -> PawControlRuntimeData:
    """Return runtime data with async-capable managers."""

    data_manager = SimpleNamespace(async_update_dog_data=AsyncMock())
    notification_manager = SimpleNamespace(async_set_priority_threshold=AsyncMock())

    runtime = PawControlRuntimeData(
        coordinator=MagicMock(),
        data_manager=data_manager,
        notification_manager=notification_manager,
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
    )

    return runtime


@pytest.mark.parametrize("option", ["device_tracker", "mqtt"])
@pytest.mark.asyncio
async def test_gps_source_select_updates_storage(
    hass, runtime_data: PawControlRuntimeData, option: str
) -> None:
    """Ensure selecting a GPS source persists the choice and updates coordinator data."""

    dog_id = "dog-1"
    coordinator = _DummyCoordinator(hass, runtime_data, dog_id)
    hass.data.setdefault(DOMAIN, {})[coordinator.config_entry.entry_id] = {
        "runtime_data": runtime_data,
        "data_manager": runtime_data.data_manager,
        "notifications": runtime_data.notification_manager,
        "coordinator": coordinator,
    }

    select = PawControlGPSSourceSelect(coordinator, dog_id, "Buddy")
    select.hass = hass

    await select._async_set_select_option(option)

    runtime_data.data_manager.async_update_dog_data.assert_awaited_once()
    update_call = runtime_data.data_manager.async_update_dog_data.await_args
    assert update_call.args[0] == dog_id
    gps_updates = update_call.args[1]["gps"]
    assert gps_updates["source"] == option
    assert "source_updated_at" in gps_updates

    assert coordinator.data[dog_id]["gps"]["source"] == option


@pytest.mark.asyncio
async def test_notification_priority_select_updates_manager(
    hass, runtime_data: PawControlRuntimeData
) -> None:
    """Ensure selecting a notification priority updates manager and persistence layer."""

    dog_id = "dog-2"
    coordinator = _DummyCoordinator(hass, runtime_data, dog_id)
    hass.data.setdefault(DOMAIN, {})[coordinator.config_entry.entry_id] = {
        "runtime_data": runtime_data,
        "data_manager": runtime_data.data_manager,
        "notification_manager": runtime_data.notification_manager,
        "notifications": runtime_data.notification_manager,
        "coordinator": coordinator,
    }

    select = PawControlNotificationPrioritySelect(coordinator, dog_id, "Rex")
    select.hass = hass

    await select._async_set_select_option("high")

    runtime_data.notification_manager.async_set_priority_threshold.assert_awaited_once_with(
        dog_id, NotificationPriority.HIGH
    )

    runtime_data.data_manager.async_update_dog_data.assert_awaited_once()
    update_call = runtime_data.data_manager.async_update_dog_data.await_args
    assert update_call.args[0] == dog_id
    notification_updates = update_call.args[1]["notifications"]
    assert notification_updates["default_priority"] == "high"
    assert notification_updates["priority_numeric"] == NotificationPriority.HIGH.value_numeric

    assert (
        coordinator.data[dog_id]["notifications"]["default_priority"]
        == "high"
    )


@pytest.mark.asyncio
async def test_notification_manager_priority_helper_updates_config(hass) -> None:
    """Ensure the notification manager helper persists priority changes."""

    manager = PawControlNotificationManager(hass, "entry-123")

    await manager.async_set_priority_threshold("dog-3", NotificationPriority.URGENT)

    config = manager._configs["dog-3"]
    assert config.priority_threshold == NotificationPriority.URGENT
    cached = manager._cache.get_config("dog-3")
    assert cached is config
    assert manager._performance_metrics["config_updates"] == 1
