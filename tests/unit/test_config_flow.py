from __future__ import annotations

from custom_components.pawcontrol.config_flow import PawControlConfigFlow
from custom_components.pawcontrol.const import CONF_DOG_ID, CONF_DOG_NAME, CONF_DOGS
from homeassistant.data_entry_flow import FlowResultType


async def test_user_step_shows_form() -> None:
  flow = PawControlConfigFlow()
  result = await flow.async_step_user()

  assert result["type"] == FlowResultType.FORM
  assert result["step_id"] == "user"


async def test_add_dog_then_finish_creates_entry() -> None:
  flow = PawControlConfigFlow()

  await flow.async_step_user({})
  menu = await flow.async_step_dogs({CONF_DOG_NAME: "Buddy", CONF_DOG_ID: "Buddy 1"})
  assert menu["type"] == FlowResultType.MENU

  result = await flow.async_step_dogs_menu({"next_step_id": "finish"})
  assert result["type"] == FlowResultType.CREATE_ENTRY
  assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "buddy_1"


async def test_duplicate_dog_id_is_rejected() -> None:
  flow = PawControlConfigFlow()
  await flow.async_step_dogs({CONF_DOG_NAME: "Buddy", CONF_DOG_ID: "buddy"})

  duplicate = await flow.async_step_dogs(
    {CONF_DOG_NAME: "Buddy 2", CONF_DOG_ID: "buddy"}
  )
  assert duplicate["type"] == FlowResultType.FORM
  assert duplicate["errors"] == {"base": "duplicate_dog_id"}
