"""Tests for PawControl device automations."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
  CONF_CONDITION,
  CONF_DEVICE_ID,
  CONF_DOMAIN,
  CONF_ENTITY_ID,
  CONF_FROM,
  CONF_METADATA,
  CONF_TO,
  CONF_TYPE,
  STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
import voluptuous as vol

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.device_action import (
  async_call_action,
  async_get_action_capabilities,
  async_get_actions,
)
from custom_components.pawcontrol.device_automation_helpers import build_unique_id
from custom_components.pawcontrol.device_condition import (
  async_condition_from_config,
  async_get_conditions,
)
from custom_components.pawcontrol.device_trigger import (
  async_get_trigger_capabilities,
  async_get_triggers,
)
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import PawControlRuntimeData

DOG_ID = "buddy"
ENTRY_ID = "entry-1"


def _register_device(hass: HomeAssistant) -> dr.DeviceEntry:
  device_registry = dr.async_get(hass)  # noqa: E111
  return device_registry.async_get_or_create(  # noqa: E111
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
  entity_registry = er.async_get(hass)  # noqa: E111
  entity_registry.async_get_or_create(  # noqa: E111
    entity_id,
    config_entry_id=ENTRY_ID,
    device_id=device_entry.id,
    platform=platform,
    unique_id=build_unique_id(DOG_ID, suffix),
  )


@pytest.mark.asyncio
async def test_async_get_triggers_returns_available(hass: HomeAssistant) -> None:
  """Verify triggers are generated for registered device entities."""  # noqa: E111

  device_entry = _register_device(hass)  # noqa: E111
  _register_entity(  # noqa: E111
    hass,
    device_entry,
    entity_id="binary_sensor.pawcontrol_buddy_is_hungry",
    platform="binary_sensor",
    suffix="is_hungry",
  )
  _register_entity(  # noqa: E111
    hass,
    device_entry,
    entity_id="binary_sensor.pawcontrol_buddy_walk_in_progress",
    platform="binary_sensor",
    suffix="walk_in_progress",
  )
  _register_entity(  # noqa: E111
    hass,
    device_entry,
    entity_id="sensor.pawcontrol_buddy_status",
    platform="sensor",
    suffix="status",
  )

  triggers = await async_get_triggers(hass, device_entry.id)  # noqa: E111
  trigger_types = {trigger[CONF_TYPE] for trigger in triggers}  # noqa: E111

  assert "hungry" in trigger_types  # noqa: E111
  assert "walk_started" in trigger_types  # noqa: E111
  assert "walk_ended" in trigger_types  # noqa: E111
  assert "status_changed" in trigger_types  # noqa: E111
  assert all(CONF_METADATA in trigger for trigger in triggers)  # noqa: E111


@pytest.mark.asyncio
async def test_async_get_triggers_missing_device(hass: HomeAssistant) -> None:
  """Return no triggers when device is unknown."""  # noqa: E111

  triggers = await async_get_triggers(hass, "missing-device")  # noqa: E111

  assert triggers == []  # noqa: E111


@pytest.mark.asyncio
async def test_async_get_actions_returns_metadata(
  hass: HomeAssistant,
) -> None:
  """Verify action metadata is provided for devices."""  # noqa: E111

  device_entry = _register_device(hass)  # noqa: E111

  actions = await async_get_actions(hass, device_entry.id)  # noqa: E111

  assert actions  # noqa: E111
  assert all(CONF_METADATA in action for action in actions)  # noqa: E111


@pytest.mark.asyncio
async def test_async_get_conditions_returns_metadata(
  hass: HomeAssistant,
) -> None:
  """Verify condition metadata is provided for devices."""  # noqa: E111

  device_entry = _register_device(hass)  # noqa: E111
  entity_id = "binary_sensor.pawcontrol_buddy_is_hungry"  # noqa: E111
  _register_entity(  # noqa: E111
    hass,
    device_entry,
    entity_id=entity_id,
    platform="binary_sensor",
    suffix="is_hungry",
  )

  conditions = await async_get_conditions(hass, device_entry.id)  # noqa: E111

  assert conditions  # noqa: E111
  assert all(CONF_METADATA in condition for condition in conditions)  # noqa: E111


@pytest.mark.asyncio
async def test_condition_uses_entity_state_fallback(
  hass: HomeAssistant,
) -> None:
  """Verify conditions evaluate using entity state when no runtime data exists."""  # noqa: E111

  device_entry = _register_device(hass)  # noqa: E111
  entity_id = "binary_sensor.pawcontrol_buddy_is_hungry"  # noqa: E111
  _register_entity(  # noqa: E111
    hass,
    device_entry,
    entity_id=entity_id,
    platform="binary_sensor",
    suffix="is_hungry",
  )

  hass.states.async_set(entity_id, STATE_ON)  # noqa: E111

  condition = await async_condition_from_config(  # noqa: E111
    hass,
    {
      CONF_CONDITION: "device",
      CONF_DEVICE_ID: device_entry.id,
      CONF_DOMAIN: DOMAIN,
      CONF_TYPE: "is_hungry",
      CONF_ENTITY_ID: entity_id,
    },
  )

  assert condition(hass, {})  # noqa: E111


@pytest.mark.asyncio
async def test_condition_missing_entity_returns_false(
  hass: HomeAssistant,
) -> None:
  """Ensure missing entities cause conditions to fail."""  # noqa: E111

  device_entry = _register_device(hass)  # noqa: E111

  condition = await async_condition_from_config(  # noqa: E111
    hass,
    {
      CONF_CONDITION: "device",
      CONF_DEVICE_ID: device_entry.id,
      CONF_DOMAIN: DOMAIN,
      CONF_TYPE: "needs_walk",
      CONF_ENTITY_ID: "binary_sensor.pawcontrol_buddy_needs_walk",
    },
  )

  assert not condition(hass, {})  # noqa: E111


@pytest.mark.asyncio
async def test_action_calls_feeding_manager(hass: HomeAssistant) -> None:
  """Verify device actions call managers with dog identifiers."""  # noqa: E111

  device_entry = _register_device(hass)  # noqa: E111

  feeding_manager = AsyncMock()  # noqa: E111
  walk_manager = AsyncMock()  # noqa: E111

  runtime_data = PawControlRuntimeData(  # noqa: E111
    coordinator=Mock(),
    data_manager=Mock(),
    notification_manager=Mock(),
    feeding_manager=feeding_manager,
    walk_manager=walk_manager,
    entity_factory=Mock(),
    entity_profile="standard",
    dogs=[{"dog_id": DOG_ID, "dog_name": "Buddy"}],
  )

  entry = ConfigEntry(entry_id=ENTRY_ID, domain=DOMAIN, data={"dogs": []})  # noqa: E111
  store_runtime_data(hass, entry, runtime_data)  # noqa: E111

  await async_call_action(  # noqa: E111
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

  feeding_manager.async_add_feeding.assert_awaited_once()  # noqa: E111
  call_args = feeding_manager.async_add_feeding.call_args  # noqa: E111
  assert call_args.args[0] == DOG_ID  # noqa: E111
  assert call_args.args[1] == 120.0  # noqa: E111


@pytest.mark.asyncio
async def test_action_capabilities_require_amount(
  hass: HomeAssistant,
) -> None:
  """Ensure feeding action capabilities require amount."""  # noqa: E111

  capabilities = await async_get_action_capabilities(  # noqa: E111
    hass,
    {CONF_TYPE: "log_feeding"},
  )

  fields = capabilities["fields"]  # noqa: E111
  fields({"amount": 1.0})  # noqa: E111
  with pytest.raises(vol.Invalid):  # noqa: E111
    fields({})


@pytest.mark.asyncio
async def test_trigger_capabilities_status_changed(
  hass: HomeAssistant,
) -> None:
  """Ensure status trigger capabilities expose from/to fields."""  # noqa: E111

  capabilities = await async_get_trigger_capabilities(  # noqa: E111
    hass,
    {CONF_TYPE: "status_changed"},
  )

  fields = capabilities["extra_fields"]  # noqa: E111
  fields({CONF_FROM: "sleeping", CONF_TO: "playing"})  # noqa: E111

  assert (await async_get_trigger_capabilities(hass, {CONF_TYPE: "hungry"})) == {}  # noqa: E111


@pytest.mark.asyncio
async def test_action_missing_runtime_data_raises(
  hass: HomeAssistant,
) -> None:
  """Ensure actions raise when runtime data is missing."""  # noqa: E111

  with pytest.raises(HomeAssistantError):  # noqa: E111
    await async_call_action(
      hass,
      {
        CONF_DEVICE_ID: "missing-device",
        CONF_DOMAIN: DOMAIN,
        CONF_TYPE: "start_walk",
      },
      {},
    )
