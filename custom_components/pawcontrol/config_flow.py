"""Config flow for PawControl integration.

Consolidated flow handling setup and initial dog configuration.
"""

from __future__ import annotations

from typing import Any, Final, Literal

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.util import slugify

from .const import CONF_DOG_ID, CONF_DOG_NAME, CONF_DOGS, DOMAIN
from .options_flow import PawControlOptionsFlow

DOG_SCHEMA = vol.Schema(
  {
    vol.Required(CONF_DOG_NAME): cv.string,
    vol.Required(CONF_DOG_ID): cv.string,
  },
)


class PawControlConfigFlow(ConfigFlow, domain=DOMAIN):
  """Handle a config flow for PawControl."""

  VERSION = 1

  def __init__(self) -> None:
    """Initialize the config flow."""
    self._data: dict[str, Any] = {CONF_DOGS: []}

  @staticmethod
  @callback
  def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
    """Get the options flow for this handler."""
    return PawControlOptionsFlow(config_entry)

  async def async_step_user(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle the initial step."""
    if user_input is not None:
      if self._async_current_entries():
        return self.async_abort(reason="single_instance_allowed")
      return await self.async_step_dogs()

    return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

  async def async_step_dogs(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle dog configuration."""
    errors: dict[str, str] = {}

    if user_input is not None:
      dog_id = slugify(user_input[CONF_DOG_ID])
      if any(d[CONF_DOG_ID] == dog_id for d in self._data[CONF_DOGS]):
        errors["base"] = "duplicate_dog_id"
      else:
        self._data[CONF_DOGS].append(
          {
            CONF_DOG_ID: dog_id,
            CONF_DOG_NAME: user_input[CONF_DOG_NAME],
            "modules": {},
          },
        )
        return self.async_show_menu(
          step_id="dogs_menu",
          menu_options=["dogs", "finish"],
        )

    return self.async_show_form(
      step_id="dogs",
      data_schema=DOG_SCHEMA,
      errors=errors,
      description_placeholders={"count": str(len(self._data[CONF_DOGS]))},
    )

  async def async_step_dogs_menu(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Menu to add more dogs or finish."""
    if user_input and user_input.get("next_step_id") == "dogs":
      return await self.async_step_dogs()
    return await self.async_step_finish()

  async def async_step_finish(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Finish configuration."""
    return self.async_create_entry(title="PawControl", data=self._data)


ConfigFlowAlias: Final[Literal["ConfigFlow"]] = "ConfigFlow"
ConfigFlow = PawControlConfigFlow

__all__: Final[tuple[Literal["ConfigFlow"], Literal["PawControlConfigFlow"]]] = (
  ConfigFlowAlias,
  "PawControlConfigFlow",
)
