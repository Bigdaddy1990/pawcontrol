"""Tests for PawControl device automations."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
  CONF_CONDITION,
  CONF_DEVICE_ID,
  CONF_DOMAIN,
  CONF_ENTITY_ID,
  CONF_TYPE,
  STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.device_action import async_call_action
from custom_components.pawcontrol.device_automation_helpers import build_unique_id
from custom_components.pawcontrol.device_condition import async_condition_from_config
from custom_components.pawcontrol.device_trigger import async_get_triggers
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import PawControlRuntimeData

DOG_ID = "buddy"
ENTRY_ID = "entry-1"


def _register_device(hass: HomeAssistant) -> dr.DeviceEntry:
  device_registry = dr.async_get(hass)
  return device_registry.async_get_or_create(
    config_entry_id=ENTRY_ID,
    identifiers={(DOMAIN, DOG_ID)},
  )


def _register_entity(
  hass: HomeAssistant,
  device_entry: dr.DeviceEntry,
  *,
  entity_id: str,
  platform: str,
  suffix: str,
) -> None:
  entity_registry = er.async_get(hass)
  entity_registry.async_get_or_create(
    entity_id,
    config_entry_id=ENTRY_ID,
    device_id=device_entry.id,
    platform=platform,
    unique_id=build_unique_id(DOG_ID, suffix),
  )


@pytest.mark.asyncio
async def test_async_get_triggers_returns_available(hass: HomeAssistant) -> None:
  """Verify triggers are generated for registered device entities."""

  device_entry = _register_device(hass)
  _register_entity(
    hass,
    device_entry,
    entity_id="binary_sensor.pawcontrol_buddy_is_hungry",
    platform="binary_sensor",
    suffix="is_hungry",
  )
  _register_entity(
    hass,
    device_entry,
    entity_id="binary_sensor.pawcontrol_buddy_walk_in_progress",
    platform="binary_sensor",
    suffix="walk_in_progress",
  )
  _register_entity(
    hass,
    device_entry,
    entity_id="sensor.pawcontrol_buddy_status",
    platform="sensor",
    suffix="status",
  )

  triggers = await async_get_triggers(hass, device_entry.id)
  trigger_types = {trigger[CONF_TYPE] for trigger in triggers}

  assert "hungry" in trigger_types
  assert "walk_started" in trigger_types
  assert "walk_ended" in trigger_types
  assert "status_changed" in trigger_types


@pytest.mark.asyncio
async def test_async_get_triggers_missing_device(hass: HomeAssistant) -> None:
  """Return no triggers when device is unknown."""

  triggers = await async_get_triggers(hass, "missing-device")

  assert triggers == []


@pytest.mark.asyncio
async def test_condition_uses_entity_state_fallback(
  hass: HomeAssistant,
) -> None:
  """Verify conditions evaluate using entity state when no runtime data exists."""

  device_entry = _register_device(hass)
  entity_id = "binary_sensor.pawcontrol_buddy_is_hungry"
  _register_entity(
    hass,
    device_entry,
    entity_id=entity_id,
    platform="binary_sensor",
    suffix="is_hungry",
  )

  hass.states.async_set(entity_id, STATE_ON)

  condition = await async_condition_from_config(
    hass,
    {
      CONF_CONDITION: "device",
      CONF_DEVICE_ID: device_entry.id,
      CONF_DOMAIN: DOMAIN,
      CONF_TYPE: "is_hungry",
      CONF_ENTITY_ID: entity_id,
    },
  )

  assert condition(hass, {})


@pytest.mark.asyncio
async def test_condition_missing_entity_returns_false(
  hass: HomeAssistant,
) -> None:
  """Ensure missing entities cause conditions to fail."""

  device_entry = _register_device(hass)

  condition = await async_condition_from_config(
    hass,
    {
      CONF_CONDITION: "device",
      CONF_DEVICE_ID: device_entry.id,
      CONF_DOMAIN: DOMAIN,
      CONF_TYPE: "needs_walk",
      CONF_ENTITY_ID: "binary_sensor.pawcontrol_buddy_needs_walk",
    },
  )

  assert not condition(hass, {})


@pytest.mark.asyncio
async def test_action_calls_feeding_manager(hass: HomeAssistant) -> None:
  """Verify device actions call managers with dog identifiers."""

  device_entry = _register_device(hass)

  feeding_manager = AsyncMock()
  walk_manager = AsyncMock()

  runtime_data = PawControlRuntimeData(
    coordinator=Mock(),
    data_manager=Mock(),
    notification_manager=Mock(),
    feeding_manager=feeding_manager,
    walk_manager=walk_manager,
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[{"dog_id": DOG_ID, "dog_name": "Buddy"}],
  )

  entry = ConfigEntry(entry_id=ENTRY_ID, domain=DOMAIN, data={"dogs": []})
  store_runtime_data(hass, entry, runtime_data)

  await async_call_action(
    hass,
    {
      CONF_DEVICE_ID: device_entry.id,
      CONF_DOMAIN: DOMAIN,
      CONF_TYPE: "log_feeding",
      "amount": 120.0,
      "meal_type": "breakfast",
    },
    {},
  )

  feeding_manager.async_add_feeding.assert_awaited_once()
  call_args = feeding_manager.async_add_feeding.call_args
  assert call_args.args[0] == DOG_ID
  assert call_args.args[1] == 120.0


@pytest.mark.asyncio
async def test_action_missing_runtime_data_raises(
  hass: HomeAssistant,
) -> None:
  """Ensure actions raise when runtime data is missing."""

  with pytest.raises(HomeAssistantError):
    await async_call_action(
      hass,
      {
        CONF_DEVICE_ID: "missing-device",
        CONF_DOMAIN: DOMAIN,
        CONF_TYPE: "start_walk",
      },
      {},
    )
