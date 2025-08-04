"""Configuration flow for Paw Control - angepasst."""
from __future__ import annotations

from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_NAME,
    CONF_DOG_WEIGHT,
    CONF_FEEDING_TIMES,
    CONF_VET_CONTACT,
    CONF_WALK_DURATION,
    DEFAULT_FEEDING_TIMES,
    DEFAULT_WALK_DURATION,
    DOMAIN,
)
from .config_helpers import build_module_schema
from .utils import merge_entry_options
from .helpers.config import ConfigHelper

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration for Paw Control."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the first step of the configuration flow."""

        errors: dict[str, str] = {}

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_DOG_NAME): str,
            vol.Optional(CONF_DOG_BREED, default=""): str,
            vol.Optional(CONF_DOG_AGE, default=0): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=25)
            ),
            vol.Optional(CONF_DOG_WEIGHT, default=0.0): vol.All(
                vol.Coerce(float), vol.Range(min=0.5, max=100.0)
            ),
            vol.Optional(
                CONF_FEEDING_TIMES, default=list(DEFAULT_FEEDING_TIMES)
            ): list,
            vol.Optional(CONF_WALK_DURATION, default=DEFAULT_WALK_DURATION): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=300)
            ),
            vol.Optional(CONF_VET_CONTACT, default=""): str,
        }
        
        # Add toggles for modules using helper
        schema_dict.update(build_module_schema())
        schema = vol.Schema(schema_dict, extra=vol.PREVENT_EXTRA)

        if user_input is not None:
            try:
                user_input = schema(user_input)
                
                # Validate dog name using helper
                from .helpers.utils import UtilsHelper
                utils_helper = UtilsHelper(self.hass)
                if not utils_helper.validate_dog_name(user_input[CONF_DOG_NAME]):
                    errors[CONF_DOG_NAME] = "invalid_dog_name"
                else:
                    return self.async_create_entry(
                        title=user_input[CONF_DOG_NAME], data=user_input
                    )
                    
            except vol.MultipleInvalid as err:
                for error in err.errors:
                    if error.path:
                        errors[str(error.path[0])] = "invalid_input"
                    else:
                        errors["base"] = "invalid_input"

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the options flow for Paw Control."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self.config_helper = ConfigHelper(None, config_entry)  # hass wird später gesetzt

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show and persist module options during configuration."""

        data = merge_entry_options(self.config_entry)
        schema = vol.Schema(build_module_schema(data), extra=vol.PREVENT_EXTRA)

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user_input = schema(user_input)
            except vol.MultipleInvalid:
                errors["base"] = "invalid_input"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
