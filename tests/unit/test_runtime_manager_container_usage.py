"""Regression tests covering runtime manager container access patterns."""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_cls
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
  """Simple stub exposing the garden manager contract used by entities."""

  def __init__(self) -> None:
    self.build_calls = 0
    self.is_in_calls = 0
    self.pending_calls = 0

  def build_garden_snapshot(self, dog_id: str) -> GardenModulePayload:
    self.build_calls += 1
    confirmation: GardenConfirmationSnapshot = {
      "session_id": "garden-session",
      "created": None,
      "expires": None,
    }
    return {
      "status": "active",
      "pending_confirmations": [confirmation],
    }

  def is_dog_in_garden(self, dog_id: str) -> bool:
    self.is_in_calls += 1
    return True

  def has_pending_confirmation(self, dog_id: str) -> bool:
    self.pending_calls += 1
    return True


class _CoordinatorStub:
  """Coordinator stub exposing the attributes required by entity helpers."""

  __slots__ = (
    "_dog_data",
    "async_request_refresh",
    "available",
    "config_entry",
    "runtime_managers",
  )

  def __init__(
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

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData:
    return self._dog_data


def test_garden_binary_sensors_use_runtime_manager_container(
  hass: HomeAssistant,
) -> None:
  """Garden binary sensors should resolve helpers through the runtime container."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
  entry.add_to_hass(hass)

  garden_manager = _GardenManagerStub()
  runtime_managers = CoordinatorRuntimeManagers(garden_manager=garden_manager)
  coordinator = _CoordinatorStub(entry, runtime_managers)

  dog_config: DogConfigData = {"dog_id": "dog", "dog_name": "Garden Dog"}
  runtime_data = PawControlRuntimeData(
    coordinator=coordinator,
    data_manager=Mock(),
    notification_manager=Mock(),
    feeding_manager=Mock(),
    walk_manager=Mock(),
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[dog_config],
  )

  store_runtime_data(hass, entry, runtime_data)

  assert not hasattr(coordinator, "garden_manager")

  active_sensor = PawControlGardenSessionActiveBinarySensor(
    coordinator, "dog", "Garden Dog"
  )
  in_garden_sensor = PawControlInGardenBinarySensor(coordinator, "dog", "Garden Dog")
  pending_sensor = PawControlGardenPoopPendingBinarySensor(
    coordinator, "dog", "Garden Dog"
  )

  active_sensor.hass = hass
  in_garden_sensor.hass = hass
  pending_sensor.hass = hass

  manager = active_sensor._get_garden_manager()
  assert manager is garden_manager
  data_snapshot = active_sensor._get_garden_data()
  assert data_snapshot.get("status") == "active"
  assert active_sensor.is_on is True
  assert in_garden_sensor.is_on is True
  assert pending_sensor.is_on is True

  assert garden_manager.build_calls >= 1
  assert garden_manager.is_in_calls >= 1
  assert garden_manager.pending_calls >= 1


@pytest.mark.asyncio
async def test_birthdate_date_uses_runtime_data_manager_container(
  hass: HomeAssistant,
) -> None:
  """Birthdate date entity should persist updates through the runtime container."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
  entry.add_to_hass(hass)

  data_manager = Mock()
  data_manager.async_update_dog_profile = AsyncMock()

  runtime_managers = CoordinatorRuntimeManagers(data_manager=data_manager)
  coordinator = _CoordinatorStub(entry, runtime_managers)

  dog_config: DogConfigData = {"dog_id": "dog", "dog_name": "Garden Dog"}
  runtime_data = PawControlRuntimeData(
    coordinator=coordinator,
    data_manager=data_manager,
    notification_manager=Mock(),
    feeding_manager=Mock(),
    walk_manager=Mock(),
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[dog_config],
  )

  store_runtime_data(hass, entry, runtime_data)

  entity = PawControlBirthdateDate(coordinator, "dog", "Garden Dog")
  entity.hass = hass
  entity.async_write_ha_state = Mock()

  await entity.async_set_value(date_cls(2020, 1, 1))

  data_manager.async_update_dog_profile.assert_awaited_once_with(
    "dog", {"birthdate": "2020-01-01"}
  )


@pytest.mark.asyncio
async def test_emergency_datetime_uses_runtime_notification_manager(
  hass: HomeAssistant,
) -> None:
  """Emergency datetime entity should dispatch notifications via the container."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
  entry.add_to_hass(hass)

  notification_manager_stub = SimpleNamespace(async_send_notification=AsyncMock())
  notification_manager = cast(
    "PawControlNotificationManager", notification_manager_stub
  )

  runtime_managers = CoordinatorRuntimeManagers(
    notification_manager=notification_manager
  )
  coordinator = _CoordinatorStub(entry, runtime_managers)

  dog_config: DogConfigData = {"dog_id": "dog", "dog_name": "Garden Dog"}
  data_manager_stub = SimpleNamespace(async_update_dog_data=AsyncMock())
  data_manager = cast("PawControlDataManager", data_manager_stub)
  runtime_data = PawControlRuntimeData(
    coordinator=coordinator,
    data_manager=data_manager,
    notification_manager=notification_manager,
    feeding_manager=Mock(),
    walk_manager=Mock(),
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[dog_config],
  )

  store_runtime_data(hass, entry, runtime_data)

  entity = PawControlEmergencyDateTime(coordinator, "dog", "Garden Dog")
  entity.hass = hass
  entity.async_write_ha_state = Mock()
  hass.services.async_call = AsyncMock()  # type: ignore[assignment]

  await entity.async_set_value(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))

  notification_manager.async_send_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_custom_message_text_prefers_notification_manager(
  hass: HomeAssistant,
) -> None:
  """Custom message text should route notifications through the runtime container."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
  entry.add_to_hass(hass)

  notification_manager_stub = SimpleNamespace(async_send_notification=AsyncMock())
  notification_manager = cast(
    "PawControlNotificationManager", notification_manager_stub
  )
  data_manager_stub = SimpleNamespace(async_update_dog_data=AsyncMock())
  data_manager = cast("PawControlDataManager", data_manager_stub)

  runtime_managers = CoordinatorRuntimeManagers(
    data_manager=data_manager,
    notification_manager=notification_manager,
  )
  coordinator = _CoordinatorStub(entry, runtime_managers)

  dog_config: DogConfigData = {"dog_id": "dog", "dog_name": "Garden Dog"}
  runtime_data = PawControlRuntimeData(
    coordinator=coordinator,
    data_manager=data_manager,
    notification_manager=notification_manager,
    feeding_manager=Mock(),
    walk_manager=Mock(),
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[dog_config],
  )

  store_runtime_data(hass, entry, runtime_data)

  entity = PawControlCustomMessageText(coordinator, "dog", "Garden Dog")
  entity.hass = hass
  entity.async_write_ha_state = Mock()
  entity.native_max = entity._attr_native_max
  hass.services.async_call = AsyncMock()  # type: ignore[assignment]

  await entity.async_set_value("   Hello runtime managers!   ")

  notification_manager.async_send_notification.assert_awaited_once()
  _args, kwargs = notification_manager.async_send_notification.await_args
  assert kwargs["message"] == "Hello runtime managers!"
  hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_date_entity_skips_service_call_when_hass_missing(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Date entities should skip service calls when Home Assistant is unavailable."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
  runtime_managers = CoordinatorRuntimeManagers()
  coordinator = _CoordinatorStub(entry, runtime_managers)

  entity = PawControlLastVetVisitDate(coordinator, "dog", "Garden Dog")
  entity.async_write_ha_state = Mock()

  caplog.clear()
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):
    await entity.async_set_value(date_cls(2024, 4, 1))

  assert "Skipping pawcontrol.log_health_data service call" in caplog.text


@pytest.mark.asyncio
async def test_emergency_datetime_skips_services_without_hass(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Emergency datetime should guard hass-dependent service calls."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
  runtime_managers = CoordinatorRuntimeManagers()
  coordinator = _CoordinatorStub(entry, runtime_managers)

  entity = PawControlEmergencyDateTime(coordinator, "dog", "Garden Dog")
  entity.async_write_ha_state = Mock()

  caplog.clear()
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):
    await entity.async_set_value(datetime(2024, 4, 1, 12, 30, tzinfo=UTC))

  assert "Skipping pawcontrol.log_health_data service call" in caplog.text


@pytest.mark.asyncio
async def test_custom_message_text_skips_notify_when_hass_missing(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Custom message text should guard hass-based notifications."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
  runtime_managers = CoordinatorRuntimeManagers()
  coordinator = _CoordinatorStub(entry, runtime_managers)

  entity = PawControlCustomMessageText(coordinator, "dog", "Garden Dog")
  entity.async_write_ha_state = Mock()
  entity.native_max = entity._attr_native_max

  caplog.clear()
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):
    await entity.async_set_value("  Hello  ")

  assert "Skipping pawcontrol.notify_test service call" in caplog.text


@pytest.mark.asyncio
async def test_visitor_mode_switch_skips_service_without_hass(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Visitor mode switch should guard Home Assistant service usage."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
  runtime_managers = CoordinatorRuntimeManagers()
  coordinator = _CoordinatorStub(entry, runtime_managers)

  entity = PawControlVisitorModeSwitch(coordinator, "dog", "Garden Dog")
  entity.async_write_ha_state = Mock()

  caplog.clear()
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):
    await entity.async_turn_on()

  assert "Skipping pawcontrol.set_visitor_mode service call" in caplog.text


@pytest.mark.asyncio
async def test_confirm_poop_button_skips_service_without_hass(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Garden confirmation button should guard Home Assistant service usage."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
  runtime_managers = CoordinatorRuntimeManagers()
  coordinator = _CoordinatorStub(entry, runtime_managers)

  entity = PawControlConfirmGardenPoopButton(coordinator, "dog", "Garden Dog")

  caplog.clear()
  with caplog.at_level("DEBUG", logger="custom_components.pawcontrol.entity"):
    await entity.async_press()

  assert "Skipping pawcontrol.confirm_garden_poop service call" in caplog.text
