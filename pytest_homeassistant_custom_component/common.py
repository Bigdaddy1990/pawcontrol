"""Common utilities for pytest-homeassistant-custom-component stub."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from homeassistant.config_entries import ConfigEntryState

@dataclass
class MockConfigEntry:
    """Simplified stand-in for Home Assistant's ConfigEntry."""
    domain: str
    data: dict[str, Any] | None = None
    options: dict[str, Any] | None = None
    state: ConfigEntryState = ConfigEntryState.NOT_LOADED

    async def async_setup(self, hass: Any) -> bool:
        self.state = ConfigEntryState.LOADED
        return True

    async def async_unload(self, hass: Any) -> bool:
        self.state = ConfigEntryState.NOT_LOADED
        return True
