"""Options flow for PawControl."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow

from .const import CONF_DOG_ID, CONF_DOG_NAME, CONF_DOGS


class PawControlOptionsFlow(OptionsFlow):
  """Handle options."""

  def __init__(self, config_entry: ConfigEntry) -> None:
    """Initialize options flow."""
    self.config_entry = config_entry
    self._dogs = list(config_entry.data.get(CONF_DOGS, []))

  async def async_step_init(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage the options."""
    return self.async_show_menu(
      step_id="init",
      menu_options=["manage_dogs", "global_settings"],
    )

  async def async_step_global_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage global settings."""
    if user_input is not None:
      return self.async_create_entry(title="", data=user_input)

    schema = vol.Schema({vol.Optional("enable_analytics", default=False): bool})
    return self.async_show_form(step_id="global_settings", data_schema=schema)

  async def async_step_manage_dogs(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select a dog to view."""
    if user_input is not None:
      return await self.async_step_init()

    dog_options = {dog[CONF_DOG_ID]: dog[CONF_DOG_NAME] for dog in self._dogs}
    return self.async_show_form(
      step_id="manage_dogs",
      data_schema=vol.Schema({vol.Required("dog"): vol.In(dog_options)}),
    )


__all__ = ("PawControlOptionsFlow",)
