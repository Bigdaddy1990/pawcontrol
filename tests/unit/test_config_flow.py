from __future__ import annotations

from custom_components.pawcontrol.config_flow import PawControlConfigFlow
from custom_components.pawcontrol.const import (
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOGS,
  CONF_NAME,
)
from homeassistant.data_entry_flow import FlowResultType


async def test_user_step_shows_form() -> None:
  flow = PawControlConfigFlow()
  result = await flow.async_step_user()

  assert result["type"] == FlowResultType.FORM
  assert result["step_id"] == "user"


async def test_add_dog_then_finish_creates_entry() -> None:
  flow = PawControlConfigFlow()

  user = await flow.async_step_user({CONF_NAME: "Paw Control"})
  assert user["type"] == FlowResultType.FORM
  assert user["step_id"] == "add_dog"

  dog_step = await flow.async_step_add_dog(
    {CONF_DOG_NAME: "Buddy", CONF_DOG_ID: "Buddy 1"}
  )
  assert dog_step["type"] == FlowResultType.FORM
  assert dog_step["step_id"] == "dog_modules"

  modules = await flow.async_step_dog_modules({"enable_feeding": True})
  assert modules["type"] == FlowResultType.FORM
  assert modules["step_id"] == "add_another_dog"

  profile = await flow.async_step_add_another_dog({"add_another": False})
  assert profile["type"] == FlowResultType.FORM
  assert profile["step_id"] == "entity_profile"

  finalize = await flow.async_step_entity_profile({"entity_profile": "standard"})
  assert finalize["type"] == FlowResultType.FORM
  assert finalize["step_id"] == "final_setup"

  result = await flow.async_step_final_setup({})
  assert result["type"] == FlowResultType.CREATE_ENTRY
  assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "buddy_1"


async def test_duplicate_dog_id_is_rejected() -> None:
  flow = PawControlConfigFlow()
  await flow.async_step_user({CONF_NAME: "Paw Control"})
  await flow.async_step_add_dog({CONF_DOG_NAME: "Buddy", CONF_DOG_ID: "buddy"})
  await flow.async_step_dog_modules({"enable_feeding": True})

  duplicate = await flow.async_step_add_dog(
    {CONF_DOG_NAME: "Buddy 2", CONF_DOG_ID: "buddy"}
  )
  assert duplicate["type"] == FlowResultType.FORM
  assert duplicate["errors"] == {CONF_DOG_ID: "dog_id_already_exists"}
