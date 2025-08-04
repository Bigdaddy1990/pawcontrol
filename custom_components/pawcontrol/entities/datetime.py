"""Basisklasse für DateTime-Entities."""

from __future__ import annotations

from homeassistant.components.datetime import DateTimeEntity

from .base import PawControlBaseEntity
from ..helpers.entity import parse_datetime


class PawControlDateTimeEntity(PawControlBaseEntity, DateTimeEntity):
    """Gemeinsame Funktionalität für DateTime-Entities."""

    def __init__(
        self,
        coordinator,
        name: str | None = None,
        dog_name: str | None = None,
        unique_suffix: str | None = None,
        *,
        key: str | None = None,
        icon: str | None = None,
        has_date: bool = True,
        has_time: bool = True,
    ) -> None:
        super().__init__(
            coordinator,
            name,
            dog_name,
            unique_suffix,
            key=key,
            icon=icon,
        )
        self._attr_has_date = has_date
        self._attr_has_time = has_time

    @property
    def native_value(self):
        return parse_datetime(self._state)
