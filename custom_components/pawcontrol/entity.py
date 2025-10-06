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

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the entity and attach device metadata."""

        super().__init__(coordinator)
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._attr_extra_state_attributes = {
            ATTR_DOG_ID: dog_id,
            ATTR_DOG_NAME: dog_name,
        }
        # The Home Assistant entity base class sets ``hass`` when entities are
        # added to the registry. The lightweight stubs used in the test suite
        # instantiate entities directly, so we provide a safe default here to
        # avoid attribute errors in helper routines that guard on ``self.hass``.
        self.hass = getattr(self, "hass", None)

    @property
    def dog_id(self) -> str:
        """Return the identifier for the dog this entity represents."""

        return self._dog_id

    @property
    def dog_name(self) -> str:
        """Return the friendly dog name."""

        return self._dog_name

    @property
    def has_entity_name(self) -> bool:
        """Expose the entity-name flag for simplified test doubles."""

        return bool(getattr(self, "_attr_has_entity_name", False))

    @property
    def name(self) -> str | None:
        """Return the entity name, defaulting to the dog name when unset."""

        name = getattr(self, "_attr_name", None)
        return name if name is not None else self._dog_name

    @property
    def unique_id(self) -> str | None:
        """Expose the generated unique ID for compatibility with stubs."""

        return getattr(self, "_attr_unique_id", None)

    @property
    def translation_key(self) -> str | None:
        """Expose the translation key assigned during entity construction."""

        return getattr(self, "_attr_translation_key", None)

    @property
    def device_class(self) -> str | None:
        """Return the configured device class if set.

        The Home Assistant test doubles only expose plain attributes rather
        than the full entity helper stack. Surfacing the device class through
        an explicit property keeps the behaviour consistent with Home
        Assistant's core entity implementation while remaining compatible with
        the lightweight stubs used in the test harness.
        """

        return getattr(self, "_attr_device_class", None)

    @property
    def icon(self) -> str | None:
        """Return the configured Material Design icon for the entity."""

        return getattr(self, "_attr_icon", None)

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
