# entities/switch.py
from homeassistant.components.switch import SwitchEntity

from .base import PawControlBaseEntity
from ..helpers.entity import as_bool


class PawControlSwitchEntity(PawControlBaseEntity, SwitchEntity):
    """Basisklasse für Switch-Entities mit boolescher Konvertierung."""

    def __init__(
        self,
        coordinator,
        name: str | None = None,
        dog_name: str | None = None,
        unique_suffix: str | None = None,
        *,
        key: str | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            name,
            dog_name,
            unique_suffix,
            key=key,
            icon=icon,
        )

    def _update_state(self) -> None:
        """Hole und konvertiere den Status aus den Koordinatordaten."""
        self._state = as_bool(self.coordinator.data.get(self._attr_name))

    @property
    def is_on(self) -> bool:
        return self._state

    async def async_turn_on(self, **kwargs):
        # Geräte einschalten
        pass

    async def async_turn_off(self, **kwargs):
        # Geräte ausschalten
        pass
