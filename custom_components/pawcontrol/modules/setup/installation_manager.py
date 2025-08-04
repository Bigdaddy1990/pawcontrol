"""Modular setup and teardown manager for Paw Control."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import dashboard
from .const import CONF_CREATE_DASHBOARD, CONF_DOG_NAME
from .module_registry import (
    async_ensure_helpers,
    async_setup_modules,
    async_unload_modules,
)
from .utils import merge_entry_options

_LOGGER = logging.getLogger(__name__)


class InstallationManager:
    """Handle integration installation and configuration."""

    async def setup_entry(self, hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """Set up the integration and selected modules."""
        # Merge config entry data and options, with options taking precedence
        opts = merge_entry_options(entry)

        # Some parts of the integration – especially helper creation – expect a
        # dog name to be present.  The title of the entry is the dog name in the
        # config flow, so fall back to that if the name is missing from the
        # stored data. This allows setup to proceed without crashing when the
        # data is incomplete while still making the name available to modules.
        dog_present = CONF_DOG_NAME in opts
        dog_name = opts.setdefault(CONF_DOG_NAME, entry.title)

        # Ensure helper entities for enabled modules then set them up
        await async_ensure_helpers(hass, opts)
        await async_setup_modules(hass, entry, opts)

        # Create dashboard if requested. Only honour the request when the dog
        # name was explicitly provided in the stored data/options.  This avoids
        # creating dashboards accidentally if we only inferred the name from the
        # entry title above.
        if opts.get(CONF_CREATE_DASHBOARD, False):
            if dog_present and dog_name:
                await dashboard.create_dashboard(hass, dog_name)
            else:
                _LOGGER.warning(
                    "Dashboard creation requested but no dog name provided"
                )

        return True

    async def unload_entry(self, hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """Unload the integration and clean up modules."""
        await async_unload_modules(hass, entry)
        return True
