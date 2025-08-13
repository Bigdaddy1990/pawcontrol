"""GPS settings storage for Paw Control integration."""

from __future__ import annotations

from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store


class GPSSettingsStore:
    """Manage GPS settings storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str, domain: str):
        """Initialize the storage."""
        self.hass = hass
        self._store = Store(hass, 1, f"{domain}_{entry_id}_gps_settings")
        self._data: Dict[str, Any] = {}

    async def async_load(self) -> Dict[str, Any]:
        """Load settings from storage."""
        try:
            self._data = await self._store.async_load() or {}
        except Exception:
            self._data = {}
        return self._data

    async def async_save(self, data: Dict[str, Any]) -> None:
        """Save settings to storage."""
        self._data = data
        await self._store.async_save(data)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting value."""
        self._data[key] = value
