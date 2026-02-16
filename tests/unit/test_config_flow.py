from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.config_flow import PawControlConfigFlow
from custom_components.pawcontrol.config_flow_base import INTEGRATION_SCHEMA
from custom_components.pawcontrol.const import (
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOGS,
  CONF_NAME,
  DOMAIN,
)
from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
  flow = PawControlConfigFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  result = await flow.async_step_user()  # noqa: E111

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["step_id"] == "user"  # noqa: E111


async def test_add_dog_then_finish_creates_entry(hass: HomeAssistant) -> None:
  flow = PawControlConfigFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111

  user = await flow.async_step_user({CONF_NAME: "Paw Control"})  # noqa: E111
  assert user["type"] == FlowResultType.FORM  # noqa: E111
  assert user["step_id"] == "add_dog"  # noqa: E111
  assert flow._integration_name == "Paw Control"  # noqa: E111

  dog_step = await flow.async_step_add_dog({  # noqa: E111
    CONF_DOG_NAME: "Buddy",
    CONF_DOG_ID: "buddy_1",
  })
  assert dog_step["type"] == FlowResultType.FORM  # noqa: E111
  assert dog_step["step_id"] == "dog_modules"  # noqa: E111

  step: dict[str, object] = await flow.async_step_dog_modules({"enable_feeding": True})  # noqa: E111
  assert step["type"] == FlowResultType.FORM  # noqa: E111

  step = await flow.async_step_add_another_dog({"add_another": False})  # noqa: E111

  while step["type"] == FlowResultType.FORM:  # noqa: E111
    step_id = step["step_id"]
    if step_id == "configure_modules":
      step = await flow.async_step_configure_modules({})  # noqa: E111
    elif step_id == "configure_dashboard":
      step = await flow.async_step_configure_dashboard({})  # noqa: E111
    elif step_id == "entity_profile":
      step = await flow.async_step_entity_profile({"entity_profile": "standard"})  # noqa: E111
    elif step_id == "final_setup":
      step = await flow.async_step_final_setup({})  # noqa: E111
    else:
      raise AssertionError(f"Unexpected step: {step_id}")  # noqa: E111

  result = step  # noqa: E111
  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111
  assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "buddy_1"  # noqa: E111


async def test_duplicate_dog_id_is_rejected(hass: HomeAssistant) -> None:
  flow = PawControlConfigFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  await flow.async_step_user({CONF_NAME: "Paw Control"})  # noqa: E111
  await flow.async_step_add_dog({CONF_DOG_NAME: "Buddy", CONF_DOG_ID: "buddy"})  # noqa: E111
  await flow.async_step_dog_modules({"enable_feeding": True})  # noqa: E111

  duplicate = await flow.async_step_add_dog({  # noqa: E111
    CONF_DOG_NAME: "Buddy 2",
    CONF_DOG_ID: "buddy",
  })
  assert duplicate["type"] == FlowResultType.FORM  # noqa: E111
  assert duplicate["errors"] == {CONF_DOG_ID: "dog_id_already_exists"}  # noqa: E111


async def test_reauth_step_shows_confirmation_form(
  hass: HomeAssistant,
) -> None:
  entry = MockConfigEntry(  # noqa: E111
    domain=DOMAIN,
    data={
      CONF_DOGS: [
        {
          CONF_DOG_ID: "buddy",
          CONF_DOG_NAME: "Buddy",
        }
      ]
    },
    options={},
  )
  entry.add_to_hass(hass)  # noqa: E111

  flow = PawControlConfigFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.context = {"entry_id": entry.entry_id}  # noqa: E111

  result = await flow.async_step_reauth({})  # noqa: E111

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["step_id"] == "reauth_confirm"  # noqa: E111


async def test_reauth_rejects_invalid_dog_payload(
  hass: HomeAssistant,
) -> None:
  entry = MockConfigEntry(  # noqa: E111
    domain=DOMAIN,
    data={
      CONF_DOGS: [
        {
          CONF_DOG_ID: "",
          CONF_DOG_NAME: "",
        }
      ]
    },
    options={},
  )
  entry.add_to_hass(hass)  # noqa: E111

  flow = PawControlConfigFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.context = {"entry_id": entry.entry_id}  # noqa: E111

  with pytest.raises(ConfigEntryAuthFailed):  # noqa: E111
    await flow.async_step_reauth({})


async def test_reconfigure_step_shows_form(
  hass: HomeAssistant,
) -> None:
  entry = MockConfigEntry(  # noqa: E111
    domain=DOMAIN,
    data={
      CONF_DOGS: [
        {
          CONF_DOG_ID: "buddy",
          CONF_DOG_NAME: "Buddy",
        }
      ]
    },
    options={"entity_profile": "standard"},
  )
  entry.add_to_hass(hass)  # noqa: E111

  flow = PawControlConfigFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.context = {"entry_id": entry.entry_id}  # noqa: E111

  result = await flow.async_step_reconfigure()  # noqa: E111

  assert result["type"] == FlowResultType.FORM  # noqa: E111
  assert result["step_id"] == "reconfigure"  # noqa: E111
