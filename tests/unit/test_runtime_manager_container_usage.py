"""Regression tests covering runtime manager container access patterns."""

from datetime import UTC, date as date_cls, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.pawcontrol.binary_sensor import (
  PawControlGardenPoopPendingBinarySensor,
  PawControlGardenSessionActiveBinarySensor,
  PawControlInGardenBinarySensor,
)
from custom_components.pawcontrol.button import PawControlConfirmGardenPoopButton
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.date import (
  PawControlBirthdateDate,
  PawControlLastVetVisitDate,
)
from custom_components.pawcontrol.datetime import PawControlEmergencyDateTime
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.switch import PawControlVisitorModeSwitch
from custom_components.pawcontrol.text import PawControlCustomMessageText
from custom_components.pawcontrol.types import (
  CoordinatorDogData,
  CoordinatorRuntimeManagers,
  DogConfigData,
  GardenConfirmationSnapshot,
  GardenModulePayload,
  PawControlRuntimeData,
)

if TYPE_CHECKING:
  from custom_components.pawcontrol.data_manager import PawControlDataManager
  from custom_components.pawcontrol.notifications import PawControlNotificationManager
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


class _GardenManagerStub:
  """Simple stub exposing the garden manager contract used by entities."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.build_calls = 0
    self.is_in_calls = 0
    self.pending_calls = 0

  def build_garden_snapshot(self, dog_id: str) -> GardenModulePayload:  # noqa: E111
    self.build_calls += 1
    confirmation: GardenConfirmationSnapshot = {
      "session_id": "garden-session",
      "created": None,
      "expires": None,
    }
    return {
      "status": "active",
      "pending_confirmations": [confirmation],
      "sessions_today": 2,
      "active_session": {
        "start_time": datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        "duration_minutes": 12,
      },
      "last_session": {
        "start_time": datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
        "end_time": datetime(2024, 1, 1, 9, 42, tzinfo=UTC),
        "duration_minutes": 12,
      },
    }

  def is_dog_in_garden(self, dog_id: str) -> bool:  # noqa: E111
    self.is_in_calls += 1
    return True

  def has_pending_confirmation(self, dog_id: str) -> bool:  # noqa: E111
    self.pending_calls += 1
    return True


class _CoordinatorStub:
  """Coordinator stub exposing the attributes required by entity helpers."""  # noqa: E111

  __slots__ = (  # noqa: E111
    "_dog_data",
    "async_request_refresh",
    "available",
    "config_entry",
    "runtime_managers",
  )

  def __init__(  # noqa: E111
    self,
    config_entry: MockConfigEntry,
    runtime_managers: CoordinatorRuntimeManagers,
    *,
    dog_data: CoordinatorDogData | None = None,
  ) -> None:
    self.available = True
    self.config_entry = config_entry
    self.runtime_managers = runtime_managers
    self._dog_data: CoordinatorDogData = dog_data or cast(CoordinatorDogData, {})
    self.async_request_refresh = AsyncMock()

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData:  # noqa: E111
    return self._dog_data


def test_garden_binary_sensors_use_runtime_manager_container(
  hass: HomeAssistant,
) -> None:
  """Garden binary sensors should resolve helpers through the runtime container."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
  entry.add_to_hass(hass)  # noqa: E111

  garden_manager = _GardenManagerStub()  # noqa: E111
  runtime_managers = CoordinatorRuntimeManagers(garden_manager=garden_manager)  # noqa: E111
  coordinator = _CoordinatorStub(entry, runtime_managers)  # noqa: E111

  dog_config: DogConfigData = {"dog_id": "dog", "dog_name": "Garden Dog"}  # noqa: E111
  runtime_data = PawControlRuntimeData(  # noqa: E111
    coordinator=coordinator,
    data_manager=Mock(),
    notification_manager=Mock(),
    feeding_manager=Mock(),
    walk_manager=Mock(),
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[dog_config],
  )

  store_runtime_data(hass, entry, runtime_data)  # noqa: E111

  assert not hasattr(coordinator, "garden_manager")  # noqa: E111

  active_sensor = PawControlGardenSessionActiveBinarySensor(  # noqa: E111
    coordinator, "dog", "Garden Dog"
  )
  in_garden_sensor = PawControlInGardenBinarySensor(coordinator, "dog", "Garden Dog")  # noqa: E111
  pending_sensor = PawControlGardenPoopPendingBinarySensor(  # noqa: E111
    coordinator, "dog", "Garden Dog"
  )

  active_sensor.hass = hass  # noqa: E111
  in_garden_sensor.hass = hass  # noqa: E111
  pending_sensor.hass = hass  # noqa: E111

  manager = active_sensor._get_garden_manager()  # noqa: E111
  assert manager is garden_manager  # noqa: E111
  data_snapshot = active_sensor._get_garden_data()  # noqa: E111
  assert data_snapshot.get("status") == "active"  # noqa: E111
  assert active_sensor.is_on is True  # noqa: E111
  assert in_garden_sensor.is_on is True  # noqa: E111
  assert pending_sensor.is_on is True  # noqa: E111

  pending_attrs = pending_sensor.extra_state_attributes  # noqa: E111
  assert pending_attrs["garden_status"] == "active"  # noqa: E111
  assert pending_attrs["sessions_today"] == 2  # noqa: E111
  assert pending_attrs["pending_confirmation_count"] == 1  # noqa: E111
  assert pending_attrs["started_at"] == "2024-01-01T10:00:00+00:00"  # noqa: E111
  assert pending_attrs["duration_minutes"] == 12.0  # noqa: E111
  assert pending_attrs["last_seen"] == "2024-01-01T09:42:00+00:00"  # noqa: E111

  assert garden_manager.build_calls >= 1  # noqa: E111
  assert garden_manager.is_in_calls >= 1  # noqa: E111
  assert garden_manager.pending_calls >= 1  # noqa: E111


@pytest.mark.asyncio
async def test_birthdate_date_uses_runtime_data_manager_container(
  hass: HomeAssistant,
) -> None:
  """Birthdate date entity should persist updates through the runtime container."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
  entry.add_to_hass(hass)  # noqa: E111

  data_manager = Mock()  # noqa: E111
  data_manager.async_update_dog_profile = AsyncMock()  # noqa: E111

  runtime_managers = CoordinatorRuntimeManagers(data_manager=data_manager)  # noqa: E111
  coordinator = _CoordinatorStub(entry, runtime_managers)  # noqa: E111

  dog_config: DogConfigData = {"dog_id": "dog", "dog_name": "Garden Dog"}  # noqa: E111
  runtime_data = PawControlRuntimeData(  # noqa: E111
    coordinator=coordinator,
    data_manager=data_manager,
    notification_manager=Mock(),
    feeding_manager=Mock(),
    walk_manager=Mock(),
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[dog_config],
  )

  store_runtime_data(hass, entry, runtime_data)  # noqa: E111

  entity = PawControlBirthdateDate(coordinator, "dog", "Garden Dog")  # noqa: E111
  entity.hass = hass  # noqa: E111
  entity.async_write_ha_state = Mock()  # noqa: E111

  await entity.async_set_value(date_cls(2020, 1, 1))  # noqa: E111

  data_manager.async_update_dog_profile.assert_awaited_once_with(  # noqa: E111
    "dog", {"birthdate": "2020-01-01"}
  )


@pytest.mark.asyncio
async def test_emergency_datetime_uses_runtime_notification_manager(
  hass: HomeAssistant,
) -> None:
  """Emergency datetime entity should dispatch notifications via the container."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
  entry.add_to_hass(hass)  # noqa: E111

  notification_manager_stub = SimpleNamespace(async_send_notification=AsyncMock())  # noqa: E111
  notification_manager = cast(  # noqa: E111
    "PawControlNotificationManager", notification_manager_stub
  )

  runtime_managers = CoordinatorRuntimeManagers(  # noqa: E111
    notification_manager=notification_manager
  )
  coordinator = _CoordinatorStub(entry, runtime_managers)  # noqa: E111

  dog_config: DogConfigData = {"dog_id": "dog", "dog_name": "Garden Dog"}  # noqa: E111
  data_manager_stub = SimpleNamespace(async_update_dog_data=AsyncMock())  # noqa: E111
  data_manager = cast("PawControlDataManager", data_manager_stub)  # noqa: E111
  runtime_data = PawControlRuntimeData(  # noqa: E111
    coordinator=coordinator,
    data_manager=data_manager,
    notification_manager=notification_manager,
    feeding_manager=Mock(),
    walk_manager=Mock(),
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[dog_config],
  )

  store_runtime_data(hass, entry, runtime_data)  # noqa: E111

  entity = PawControlEmergencyDateTime(coordinator, "dog", "Garden Dog")  # noqa: E111
  entity.hass = hass  # noqa: E111
  entity.async_write_ha_state = Mock()  # noqa: E111
  hass.services.async_call = AsyncMock()  # type: ignore[assignment]  # noqa: E111

  await entity.async_set_value(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))  # noqa: E111

  notification_manager.async_send_notification.assert_awaited_once()  # noqa: E111


@pytest.mark.asyncio
async def test_custom_message_text_prefers_notification_manager(
  hass: HomeAssistant,
) -> None:
  """Custom message text should route notifications through the runtime container."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
  entry.add_to_hass(hass)  # noqa: E111

  notification_manager_stub = SimpleNamespace(async_send_notification=AsyncMock())  # noqa: E111
  notification_manager = cast(  # noqa: E111
    "PawControlNotificationManager", notification_manager_stub
  )
  data_manager_stub = SimpleNamespace(async_update_dog_data=AsyncMock())  # noqa: E111
  data_manager = cast("PawControlDataManager", data_manager_stub)  # noqa: E111

  runtime_managers = CoordinatorRuntimeManagers(  # noqa: E111
    data_manager=data_manager,
    notification_manager=notification_manager,
  )
  coordinator = _CoordinatorStub(entry, runtime_managers)  # noqa: E111

  dog_config: DogConfigData = {"dog_id": "dog", "dog_name": "Garden Dog"}  # noqa: E111
  runtime_data = PawControlRuntimeData(  # noqa: E111
    coordinator=coordinator,
    data_manager=data_manager,
    notification_manager=notification_manager,
    feeding_manager=Mock(),
    walk_manager=Mock(),
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[dog_config],
  )

  store_runtime_data(hass, entry, runtime_data)  # noqa: E111

  entity = PawControlCustomMessageText(coordinator, "dog", "Garden Dog")  # noqa: E111
  entity.hass = hass  # noqa: E111
  entity.async_write_ha_state = Mock()  # noqa: E111
  entity.native_max = entity._attr_native_max  # noqa: E111
  hass.services.async_call = AsyncMock()  # type: ignore[assignment]  # noqa: E111

  await entity.async_set_value("   Hello runtime managers!   ")  # noqa: E111

  notification_manager.async_send_notification.assert_awaited_once()  # noqa: E111
  _args, kwargs = notification_manager.async_send_notification.await_args  # noqa: E111
  assert kwargs["message"] == "Hello runtime managers!"  # noqa: E111
  hass.services.async_call.assert_not_awaited()  # noqa: E111


@pytest.mark.asyncio
async def test_date_entity_skips_service_call_when_hass_missing(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Date entities should skip service calls when Home Assistant is unavailable."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
  runtime_managers = CoordinatorRuntimeManagers()  # noqa: E111
  coordinator = _CoordinatorStub(entry, runtime_managers)  # noqa: E111

  entity = PawControlLastVetVisitDate(coordinator, "dog", "Garden Dog")  # noqa: E111
  entity.async_write_ha_state = Mock()  # noqa: E111

  caplog.clear()  # noqa: E111
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):  # noqa: E111
    await entity.async_set_value(date_cls(2024, 4, 1))

  assert "Skipping pawcontrol.log_health_data service call" in caplog.text  # noqa: E111


@pytest.mark.asyncio
async def test_emergency_datetime_skips_services_without_hass(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Emergency datetime should guard hass-dependent service calls."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
  runtime_managers = CoordinatorRuntimeManagers()  # noqa: E111
  coordinator = _CoordinatorStub(entry, runtime_managers)  # noqa: E111

  entity = PawControlEmergencyDateTime(coordinator, "dog", "Garden Dog")  # noqa: E111
  entity.async_write_ha_state = Mock()  # noqa: E111

  caplog.clear()  # noqa: E111
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):  # noqa: E111
    await entity.async_set_value(datetime(2024, 4, 1, 12, 30, tzinfo=UTC))

  assert "Skipping pawcontrol.log_health_data service call" in caplog.text  # noqa: E111


@pytest.mark.asyncio
async def test_custom_message_text_skips_notify_when_hass_missing(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Custom message text should guard hass-based notifications."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
  runtime_managers = CoordinatorRuntimeManagers()  # noqa: E111
  coordinator = _CoordinatorStub(entry, runtime_managers)  # noqa: E111

  entity = PawControlCustomMessageText(coordinator, "dog", "Garden Dog")  # noqa: E111
  entity.async_write_ha_state = Mock()  # noqa: E111
  entity.native_max = entity._attr_native_max  # noqa: E111

  caplog.clear()  # noqa: E111
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):  # noqa: E111
    await entity.async_set_value("  Hello  ")

  assert "Skipping pawcontrol.notify_test service call" in caplog.text  # noqa: E111


@pytest.mark.asyncio
async def test_visitor_mode_switch_skips_service_without_hass(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Visitor mode switch should guard Home Assistant service usage."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
  runtime_managers = CoordinatorRuntimeManagers()  # noqa: E111
  coordinator = _CoordinatorStub(entry, runtime_managers)  # noqa: E111

  entity = PawControlVisitorModeSwitch(coordinator, "dog", "Garden Dog")  # noqa: E111
  entity.async_write_ha_state = Mock()  # noqa: E111

  caplog.clear()  # noqa: E111
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):  # noqa: E111
    await entity.async_turn_on()

  assert "Skipping pawcontrol.set_visitor_mode service call" in caplog.text  # noqa: E111


@pytest.mark.asyncio
async def test_confirm_poop_button_skips_service_without_hass(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Garden confirmation button should guard Home Assistant service usage."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})  # noqa: E111
  runtime_managers = CoordinatorRuntimeManagers()  # noqa: E111
  coordinator = _CoordinatorStub(entry, runtime_managers)  # noqa: E111

  entity = PawControlConfirmGardenPoopButton(coordinator, "dog", "Garden Dog")  # noqa: E111

  caplog.clear()  # noqa: E111
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):  # noqa: E111
    await entity.async_press()

  assert "Skipping pawcontrol.confirm_garden_poop service call" in caplog.text  # noqa: E111
