"""Shared base entity classes for the PawControl integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_DOG_ID, ATTR_DOG_NAME
from .coordinator import PawControlCoordinator
from .utils import PawControlDeviceLinkMixin

__all__ = ["PawControlEntity"]


class PawControlEntity(
    PawControlDeviceLinkMixin, CoordinatorEntity[PawControlCoordinator]
):
    """Common base class shared across all PawControl entities."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str) -> None:
        """Initialise the entity and attach device metadata."""

        super().__init__(coordinator)
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._attr_extra_state_attributes = {
            ATTR_DOG_ID: dog_id,
            ATTR_DOG_NAME: dog_name,
        }

    @property
    def dog_id(self) -> str:
        """Return the identifier for the dog this entity represents."""

        return self._dog_id

    @property
    def dog_name(self) -> str:
        """Return the friendly dog name."""

        return self._dog_name

    @callback
    def update_device_metadata(self, **details: Any) -> None:
        """Update device metadata shared with the device registry."""

        self._set_device_link_info(**details)

    def _apply_name_suffix(self, suffix: str | None) -> None:
        """Helper to update the entity name with a consistent suffix."""

        if not suffix:
            self._attr_name = self._dog_name
            return
        self._attr_name = f"{self._dog_name} {suffix}".strip()
