from __future__ import annotations

from types import SimpleNamespace

from custom_components.pawcontrol.const import CONF_DOG_ID, CONF_DOG_NAME, CONF_DOGS
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow
from homeassistant.data_entry_flow import FlowResultType


async def test_init_menu() -> None:
  entry = SimpleNamespace(data={CONF_DOGS: []})
  flow = PawControlOptionsFlow(entry)

  result = await flow.async_step_init()
  assert result["type"] == FlowResultType.MENU
  assert result["step_id"] == "init"


async def test_global_settings_creates_entry() -> None:
  entry = SimpleNamespace(data={CONF_DOGS: []})
  flow = PawControlOptionsFlow(entry)

  result = await flow.async_step_global_settings({"enable_analytics": True})
  assert result["type"] == FlowResultType.CREATE_ENTRY
  assert result["data"] == {"enable_analytics": True}


async def test_manage_dogs_form() -> None:
  entry = SimpleNamespace(
    data={CONF_DOGS: [{CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"}]},
  )
  flow = PawControlOptionsFlow(entry)

  result = await flow.async_step_manage_dogs()
  assert result["type"] == FlowResultType.FORM
  assert result["step_id"] == "manage_dogs"
