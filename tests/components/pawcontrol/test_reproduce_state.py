"""Tests for PawControl reproduce state support."""

from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components import number as number_component
from homeassistant.components import select as select_component
from homeassistant.components import switch as switch_component
from homeassistant.components import text as text_component
from homeassistant.const import (
  ATTR_VALUE,
  STATE_OFF,
  STATE_ON,
  STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, ServiceCall, State

from custom_components.pawcontrol import number as pawcontrol_number
from custom_components.pawcontrol import select as pawcontrol_select
from custom_components.pawcontrol import switch as pawcontrol_switch
from custom_components.pawcontrol import text as pawcontrol_text

# Compatibility constants for different Home Assistant test harness versions.
ATTR_ENTITY_ID = "entity_id"
ATTR_OPTION = "option"
ATTR_OPTIONS = "options"


def _capture_service_calls(
  hass: HomeAssistant,
  domain: str,
  service: str,
) -> list[ServiceCall]:
  calls: list[ServiceCall] = []

  async def _handler(call: ServiceCall) -> None:
    calls.append(call)

  hass.services.async_register(domain, service, _handler)
  return calls


@pytest.mark.asyncio
async def test_switch_reproduce_state_calls_service(hass: HomeAssistant) -> None:
  """Reproduce switch state via turn_on service."""

  entity_id = "switch.pawcontrol_main_power"
  hass.states.async_set(entity_id, STATE_OFF)

  calls = _capture_service_calls(
    hass,
    switch_component.DOMAIN,
    switch_component.SERVICE_TURN_ON,
  )

  await pawcontrol_switch.async_reproduce_state(
    hass,
    [State(entity_id, STATE_ON)],
  )
  await hass.async_block_till_done()

  assert len(calls) == 1
  assert calls[0].data[ATTR_ENTITY_ID] == entity_id


@pytest.mark.asyncio
async def test_switch_reproduce_state_invalid_state(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Ignore invalid switch states."""

  entity_id = "switch.pawcontrol_main_power"
  hass.states.async_set(entity_id, STATE_OFF)

  calls = _capture_service_calls(
    hass,
    switch_component.DOMAIN,
    switch_component.SERVICE_TURN_ON,
  )

  await pawcontrol_switch.async_reproduce_state(
    hass,
    [State(entity_id, "invalid")],
  )
  await hass.async_block_till_done()

  assert len(calls) == 0
  assert "Invalid switch state" in caplog.text


@pytest.mark.asyncio
async def test_select_reproduce_state_calls_service(hass: HomeAssistant) -> None:
  """Reproduce select state via select_option service."""

  entity_id = "select.pawcontrol_notification_priority"
  hass.states.async_set(entity_id, "low", {ATTR_OPTIONS: ["low", "high"]})

  calls = _capture_service_calls(
    hass,
    select_component.DOMAIN,
    select_component.SERVICE_SELECT_OPTION,
  )

  await pawcontrol_select.async_reproduce_state(
    hass,
    [State(entity_id, "high")],
  )
  await hass.async_block_till_done()

  assert len(calls) == 1
  assert calls[0].data[ATTR_ENTITY_ID] == entity_id
  assert calls[0].data[ATTR_OPTION] == "high"


@pytest.mark.asyncio
async def test_select_reproduce_state_invalid_state(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Ignore invalid select options."""

  entity_id = "select.pawcontrol_notification_priority"
  hass.states.async_set(entity_id, "low", {ATTR_OPTIONS: ["low", "high"]})

  calls = _capture_service_calls(
    hass,
    select_component.DOMAIN,
    select_component.SERVICE_SELECT_OPTION,
  )

  await pawcontrol_select.async_reproduce_state(
    hass,
    [State(entity_id, "invalid")],
  )
  await hass.async_block_till_done()

  assert len(calls) == 0
  assert "Invalid select option" in caplog.text


@pytest.mark.asyncio
async def test_number_reproduce_state_calls_service(hass: HomeAssistant) -> None:
  """Reproduce number state via set_value service."""

  entity_id = "number.pawcontrol_daily_walk_target"
  hass.states.async_set(entity_id, "5")

  calls = _capture_service_calls(
    hass,
    number_component.DOMAIN,
    number_component.SERVICE_SET_VALUE,
  )

  await pawcontrol_number.async_reproduce_state(
    hass,
    [State(entity_id, "7.5")],
  )
  await hass.async_block_till_done()

  assert len(calls) == 1
  assert calls[0].data[ATTR_ENTITY_ID] == entity_id
  assert calls[0].data[ATTR_VALUE] == 7.5


@pytest.mark.asyncio
async def test_number_reproduce_state_invalid_state(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Ignore invalid number states."""

  entity_id = "number.pawcontrol_daily_walk_target"
  hass.states.async_set(entity_id, "5")

  calls = _capture_service_calls(
    hass,
    number_component.DOMAIN,
    number_component.SERVICE_SET_VALUE,
  )

  await pawcontrol_number.async_reproduce_state(
    hass,
    [State(entity_id, "bad")],
  )
  await hass.async_block_till_done()

  assert len(calls) == 0
  assert "Invalid number state" in caplog.text


@pytest.mark.asyncio
async def test_text_reproduce_state_calls_service(hass: HomeAssistant) -> None:
  """Reproduce text state via set_value service."""

  entity_id = "text.pawcontrol_dog_notes"
  hass.states.async_set(entity_id, "hello")

  calls = _capture_service_calls(
    hass,
    text_component.DOMAIN,
    text_component.SERVICE_SET_VALUE,
  )

  await pawcontrol_text.async_reproduce_state(
    hass,
    [State(entity_id, "world")],
  )
  await hass.async_block_till_done()

  assert len(calls) == 1
  assert calls[0].data[ATTR_ENTITY_ID] == entity_id
  assert calls[0].data[ATTR_VALUE] == "world"


@pytest.mark.asyncio
async def test_text_reproduce_state_invalid_state(
  hass: HomeAssistant,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Ignore invalid text states."""

  entity_id = "text.pawcontrol_dog_notes"
  hass.states.async_set(entity_id, "hello")

  calls = _capture_service_calls(
    hass,
    text_component.DOMAIN,
    text_component.SERVICE_SET_VALUE,
  )

  await pawcontrol_text.async_reproduce_state(
    hass,
    [State(entity_id, STATE_UNKNOWN)],
  )
  await hass.async_block_till_done()

  assert len(calls) == 0
  assert "Cannot reproduce text state" in caplog.text
