from __future__ import annotations

from types import SimpleNamespace

from custom_components.pawcontrol.const import CONF_DOG_ID, CONF_DOG_NAME, CONF_DOGS
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow
from homeassistant.data_entry_flow import FlowResultType


async def test_init_menu() -> None:
  entry = SimpleNamespace(data={CONF_DOGS: []}, options={})
  flow = PawControlOptionsFlow(entry)

  result = await flow.async_step_init()
  assert result["type"] == FlowResultType.MENU
  assert result["step_id"] == "init"


async def test_notifications_creates_entry() -> None:
  entry = SimpleNamespace(data={CONF_DOGS: []}, options={})
  flow = PawControlOptionsFlow(entry)

  result = await flow.async_step_notifications({"quiet_hours": True})
  assert result["type"] == FlowResultType.CREATE_ENTRY
  assert "notifications" in result["data"]


async def test_manage_dogs_form() -> None:
  entry = SimpleNamespace(
    data={CONF_DOGS: [{CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"}]},
    options={},
  )
  flow = PawControlOptionsFlow(entry)

  result = await flow.async_step_manage_dogs()
  assert result["type"] == FlowResultType.FORM
  assert result["step_id"] == "manage_dogs"
