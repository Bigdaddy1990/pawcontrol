"""Utility functions for Paw Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .helpers.utils import UtilsHelper
from .helpers.entity import EntityHelper

_LOGGER = logging.getLogger(__name__)

async def safe_service_call(
    hass: HomeAssistant, 
    domain: str, 
    service: str, 
    service_data: dict[str, Any]
) -> None:
    """Make a safe service call with error handling."""
    utils_helper = UtilsHelper(hass)
    await utils_helper.safe_service_call(domain, service, service_data)

def merge_entry_options(entry: ConfigEntry) -> dict[str, Any]:
    """Merge config entry data with options."""
    merged = dict(entry.data)
    merged.update(entry.options)
    return merged

def get_entity_id(domain: str, dog_name: str, entity_type: str) -> str:
    """Generate entity ID for dog entities."""
    entity_helper = EntityHelper(None, dog_name)  # hass wird später gesetzt
    return entity_helper.get_entity_id(domain, entity_type)

def validate_dog_name(name: str) -> bool:
    """Validate dog name format."""
    if not name or len(name) < 2:
        return False
    return name.replace(" ", "_").replace("-", "_").isalnum()
