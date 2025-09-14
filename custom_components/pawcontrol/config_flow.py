"""Simplified configuration flow for Paw Control integration.

SIMPLIFIED: Collapsed 5 mixin inheritance chain into single class.
Removed ValidationCache, complex async patterns, enterprise features.
Maintains core functionality: per-dog config, entity profiles, module selection.

Quality Scale: Platinum
Home Assistant: 2025.9.1+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_MODULES,
    DOG_SIZES,
    DOMAIN,
    MAX_DOG_AGE,
    MAX_DOG_NAME_LENGTH,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_NAME_LENGTH,
    MIN_DOG_WEIGHT,
)
from .entity_factory import ENTITY_PROFILES
from .options_flow import PawControlOptionsFlow
from .types import DogConfigData, is_dog_config_valid

_LOGGER = logging.getLogger(__name__)

MAX_CONCURRENT_VALIDATIONS = 5
VALIDATION_TIMEOUT = 1
VALIDATION_CACHE_TTL = 60


class ValidationCache:
    """Simple in-memory TTL cache for validation results."""

    def __init__(self, ttl: int = VALIDATION_CACHE_TTL) -> None:
        self._ttl = ttl
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            timestamp, value = item
            if time.time() - timestamp > self._ttl:
                del self._data[key]
                return None
            return value

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._data[key] = (time.time(), value)


# Simple schemas
INTEGRATION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Paw Control"): cv.string,
    }
)

DOG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Required(CONF_DOG_NAME): cv.string,
        vol.Optional(CONF_DOG_BREED, default=""): cv.string,
        vol.Optional(CONF_DOG_AGE, default=3): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_DOG_AGE, max=MAX_DOG_AGE)
        ),
        vol.Optional(CONF_DOG_WEIGHT, default=20.0): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_DOG_WEIGHT, max=MAX_DOG_WEIGHT)
        ),
        vol.Optional(CONF_DOG_SIZE, default="medium"): vol.In(DOG_SIZES),
    }
)

MODULES_SCHEMA = vol.Schema(
    {
        vol.Optional("feeding", default=True): cv.boolean,
        vol.Optional("walk", default=True): cv.boolean,
        vol.Optional("health", default=True): cv.boolean,
        vol.Optional("gps", default=False): cv.boolean,
        vol.Optional("notifications", default=True): cv.boolean,
    }
)

PROFILE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_profile", default="standard"): vol.In(
            list(ENTITY_PROFILES.keys())
        ),
    }
)


class PawControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Simplified configuration flow for Paw Control integration."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize configuration flow."""
        self._dogs: list[DogConfigData] = []
        self._integration_name = "Paw Control"
        self._entity_profile = "standard"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup step."""
        errors = {}

        if user_input is not None:
            integration_name = user_input[CONF_NAME].strip()

            # Simple validation
            if len(integration_name) < 1:
                errors[CONF_NAME] = "Name required"
            elif len(integration_name) > 50:
                errors[CONF_NAME] = "Name too long"
            else:
                # Set unique ID
                unique_id = integration_name.lower().replace(" ", "_")
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                self._integration_name = integration_name
                return await self.async_step_add_dog()

        return self.async_show_form(
            step_id="user",
            data_schema=INTEGRATION_SCHEMA,
            errors=errors,
            description_placeholders={"integration_name": "Paw Control"},
        )

    async def async_step_add_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a dog configuration."""
        errors = {}

        if user_input is not None:
            dog_id = user_input[CONF_DOG_ID].lower().strip()
            dog_name = user_input[CONF_DOG_NAME].strip()

            # Simple validation
            if not re.match(r"^[a-z][a-z0-9_]*$", dog_id):
                errors[CONF_DOG_ID] = "Invalid ID format"
            elif any(d[CONF_DOG_ID] == dog_id for d in self._dogs):
                errors[CONF_DOG_ID] = "ID already exists"
            elif len(dog_name) < MIN_DOG_NAME_LENGTH:
                errors[CONF_DOG_NAME] = "Name too short"
            elif len(dog_name) > MAX_DOG_NAME_LENGTH:
                errors[CONF_DOG_NAME] = "Name too long"
            else:
                # Create dog config
                dog_config: DogConfigData = {
                    CONF_DOG_ID: dog_id,
                    CONF_DOG_NAME: dog_name,
                    CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, ""),
                    CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 3),
                    CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
                    CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, "medium"),
                }

                self._dogs.append(dog_config)
                return await self.async_step_dog_modules()

        return self.async_show_form(
            step_id="add_dog",
            data_schema=DOG_SCHEMA,
            errors=errors,
            description_placeholders={
                "dogs_configured": str(len(self._dogs)),
            },
        )

    async def async_step_dog_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure optional modules for the newly added dog."""
        if not self._dogs:
            return await self.async_step_add_dog()

        current_dog = self._dogs[-1]
        if user_input is not None:
            try:
                modules = MODULES_SCHEMA(user_input or {})
            except vol.Invalid:
                return self.async_show_form(
                    step_id="dog_modules",
                    data_schema=MODULES_SCHEMA,
                    errors={"base": "invalid_selection"},
                    description_placeholders={
                        "dogs_configured": str(len(self._dogs))
                    },
                )
            current_dog[CONF_MODULES] = modules
            return await self.async_step_add_another()

        return self.async_show_form(
            step_id="dog_modules",
            data_schema=MODULES_SCHEMA,
            description_placeholders={
                "dogs_configured": str(len(self._dogs)),
            },
        )

    async def async_step_add_another(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask if user wants to add another dog."""
        if user_input is not None:
            if user_input.get("add_another", False) and len(self._dogs) < 10:
                return await self.async_step_add_dog()
            else:
                return await self.async_step_entity_profile()

        return self.async_show_form(
            step_id="add_another",
            data_schema=vol.Schema(
                {
                    vol.Optional("add_another", default=False): cv.boolean,
                }
            ),
            description_placeholders={
                "dogs_configured": str(len(self._dogs)),
                "dogs_list": self._format_dogs_list(),
            },
        )

    async def async_step_entity_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select entity profile for performance optimization."""
        if user_input is not None:
            self._entity_profile = user_input["entity_profile"]
            return await self.async_step_final_setup()

        return self.async_show_form(
            step_id="entity_profile",
            data_schema=PROFILE_SCHEMA,
            description_placeholders={
                "dogs_count": str(len(self._dogs)),
                "profiles_info": self._get_profiles_info(),
            },
        )

    async def async_step_final_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete setup and create config entry."""
        if not self._dogs:
            return self.async_abort(reason="no_dogs_configured")

        # Simple validation
        for dog in self._dogs:
            if not is_dog_config_valid(dog):
                return self.async_abort(reason="invalid_dog_config")

        # Create config entry
        config_data = {
            "name": self._integration_name,
            CONF_DOGS: self._dogs,
            "entity_profile": self._entity_profile,
        }

        options_data = {
            "entity_profile": self._entity_profile,
            "dashboard_enabled": True,
            "dashboard_auto_create": True,
        }

        return self.async_create_entry(
            title=f"{self._integration_name} ({ENTITY_PROFILES[self._entity_profile]['name']})",
            data=config_data,
            options=options_data,
        )

    def _format_dogs_list(self) -> str:
        """Format list of configured dogs."""
        if not self._dogs:
            return "No dogs configured yet."

        dogs_list = []
        for i, dog in enumerate(self._dogs, 1):
            modules = dog.get("modules", {})
            enabled_count = sum(1 for enabled in modules.values() if enabled)
            dogs_list.append(
                f"{i}. {dog[CONF_DOG_NAME]} ({dog[CONF_DOG_ID]}) - {enabled_count} modules"
            )

        return "\n".join(dogs_list)

    def _get_profiles_info(self) -> str:
        """Get entity profiles information."""
        profiles_info = []
        for name, config in ENTITY_PROFILES.items():
            profiles_info.append(f"• {name}: {config['description']}")
        return "\n".join(profiles_info)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PawControlOptionsFlow:
        """Create options flow."""
        return PawControlOptionsFlow(config_entry)
