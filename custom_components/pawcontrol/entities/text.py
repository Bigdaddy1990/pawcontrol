"""Basisklasse für Text-Entities."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode

from .base import PawControlBaseEntity
from ..helpers.entity import clamp_string


class PawControlTextEntity(PawControlBaseEntity, TextEntity):
    """Gemeinsame Funktionalität für Text-Entities."""

    def __init__(
        self,
        coordinator,
        name: str | None = None,
        dog_name: str | None = None,
        unique_suffix: str | None = None,
        *,
        key: str | None = None,
        icon: str | None = None,
        max_length: int = 255,
        mode: TextMode = TextMode.TEXT,
    ) -> None:
        super().__init__(
            coordinator,
            name,
            dog_name,
            unique_suffix,
            key=key,
            icon=icon,
        )
        self._attr_native_max = max_length
        self._attr_mode = mode

    @property
    def native_value(self) -> str | None:
        return self._state

    async def async_set_value(self, value: str) -> None:
        """Setze den Textwert mit Längenbegrenzung."""
        self._state = clamp_string(value, self.native_max)
