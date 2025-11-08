"""Tests for select entities with active configuration updates."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.feeding_manager import FeedingManager
from custom_components.pawcontrol.notifications import (
    NotificationPriority,
    PawControlNotificationManager,
)
from custom_components.pawcontrol.select import (
    PawControlGPSSourceSelect,
    PawControlNotificationPrioritySelect,
)
from custom_components.pawcontrol.types import (
    CoordinatorDataPayload,
    CoordinatorDogData,
    CoordinatorRuntimeManagers,
    JSONMutableMapping,
    PawControlRuntimeData,
)
from custom_components.pawcontrol.walk_manager import WalkManager
from homeassistant.core import HomeAssistant


class _DummyCoordinator:
    """Minimal coordinator implementation for select entity tests."""

    def __init__(
        self, hass: HomeAssistant, runtime_data: PawControlRuntimeData, dog_id: str
    ) -> None:
        self.hass = hass
        self.config_entry = SimpleNamespace(
            entry_id="test-entry", runtime_data=runtime_data
        )
        self.data: CoordinatorDataPayload = cast(
            CoordinatorDataPayload,
            {
                dog_id: {
                    "gps": {},
                    "notifications": {},
                }
            },
        )
        self.last_update_success = True
        self.runtime_managers = runtime_data.runtime_managers

    def async_add_listener(  # pragma: no cover - coordinator interface
        self, _update_callback: Callable[[], None]
    ) -> Callable[[], None]:
        return lambda: None

    async def async_request_refresh(
        self,
    ) -> None:  # pragma: no cover - coordinator interface
        return None

    async def async_set_updated_data(self, data: CoordinatorDataPayload) -> None:
        self.data = data

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self.data.get(dog_id)

    @property
    def available(self) -> bool:
        return True


@pytest.fixture(name="runtime_data")
def runtime_data_fixture() -> PawControlRuntimeData:
    """Return runtime data with async-capable managers."""

    data_manager = cast(
        PawControlDataManager,
        SimpleNamespace(async_update_dog_data=AsyncMock()),
    )
    notification_manager = cast(
        PawControlNotificationManager,
        SimpleNamespace(async_set_priority_threshold=AsyncMock()),
    )
    coordinator = cast(PawControlCoordinator, MagicMock())
    coordinator.runtime_managers = CoordinatorRuntimeManagers(data_manager=data_manager)

    runtime = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=data_manager,
        notification_manager=notification_manager,
        feeding_manager=cast(FeedingManager, MagicMock()),
        walk_manager=cast(WalkManager, MagicMock()),
        entity_factory=cast(EntityFactory, MagicMock()),
        entity_profile="standard",
        dogs=[],
    )

    return runtime


@pytest.mark.parametrize("option", ["device_tracker", "mqtt"])
@pytest.mark.asyncio
async def test_gps_source_select_updates_storage(
    hass: HomeAssistant, runtime_data: PawControlRuntimeData, option: str
) -> None:
    """Ensure selecting a GPS source persists the choice and updates coordinator data."""

    dog_id = "dog-1"
    coordinator = _DummyCoordinator(hass, runtime_data, dog_id)

    select = PawControlGPSSourceSelect(
        cast(PawControlCoordinator, coordinator), dog_id, "Buddy"
    )
    select.hass = hass

    await select._async_set_select_option(option)

    async_call = cast(AsyncMock, runtime_data.data_manager.async_update_dog_data)
    async_call.assert_awaited_once()
    await_args = async_call.await_args
    assert await_args is not None
    assert await_args.args[0] == dog_id
    updates = cast(JSONMutableMapping, dict(await_args.args[1]))
    gps_payload = updates.get("gps")
    assert isinstance(gps_payload, dict)
    gps_updates = cast(JSONMutableMapping, gps_payload)
    assert gps_updates["source"] == option
    assert "source_updated_at" in gps_updates

    stored_gps = coordinator.data[dog_id]["gps"]
    assert isinstance(stored_gps, dict)
    assert cast(JSONMutableMapping, stored_gps)["source"] == option


@pytest.mark.asyncio
async def test_notification_priority_select_updates_manager(
    hass: HomeAssistant, runtime_data: PawControlRuntimeData
) -> None:
    """Ensure selecting a notification priority updates manager and persistence layer."""

    dog_id = "dog-2"
    coordinator = _DummyCoordinator(hass, runtime_data, dog_id)

    select = PawControlNotificationPrioritySelect(
        cast(PawControlCoordinator, coordinator), dog_id, "Rex"
    )
    select.hass = hass

    await select._async_set_select_option("high")

    priority_mock = cast(
        AsyncMock, runtime_data.notification_manager.async_set_priority_threshold
    )
    priority_mock.assert_awaited_once_with(dog_id, NotificationPriority.HIGH)

    data_mock = cast(AsyncMock, runtime_data.data_manager.async_update_dog_data)
    data_mock.assert_awaited_once()
    data_args = data_mock.await_args
    assert data_args is not None
    assert data_args.args[0] == dog_id
    updates = cast(JSONMutableMapping, dict(data_args.args[1]))
    notifications_payload = updates.get("notifications")
    assert isinstance(notifications_payload, dict)
    notification_updates = cast(JSONMutableMapping, notifications_payload)
    assert notification_updates["default_priority"] == "high"
    assert (
        notification_updates["priority_numeric"]
        == NotificationPriority.HIGH.value_numeric
    )

    stored_notifications = coordinator.data[dog_id]["notifications"]
    assert isinstance(stored_notifications, dict)
    assert cast(JSONMutableMapping, stored_notifications)["default_priority"] == "high"


@pytest.mark.asyncio
async def test_notification_manager_priority_helper_updates_config(
    hass: HomeAssistant, session_factory: Callable[[], Any]
) -> None:
    """Ensure the notification manager helper persists priority changes."""

    session = session_factory()
    session.request = AsyncMock()
    manager = PawControlNotificationManager(hass, "entry-123", session=session)

    await manager.async_set_priority_threshold("dog-3", NotificationPriority.URGENT)

    config = manager._configs["dog-3"]
    assert config.priority_threshold == NotificationPriority.URGENT
    cached = manager._cache.get_config("dog-3")
    assert cached is config
    assert manager._performance_metrics["config_updates"] == 1
