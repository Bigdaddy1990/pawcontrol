"""Base entity classes for PawControl integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DOG_ID, CONF_DOG_NAME, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import PawControlCoordinator


class PawControlEntity(CoordinatorEntity[PawControlCoordinator]):
    """Base entity class for PawControl integration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entry = entry
        self.dog_id = dog_id
        self.entity_key = entity_key

        # Set unique ID
        self._attr_unique_id = f"{entry.entry_id}_{dog_id}_{entity_key}"

        # Set translation key if provided
        if translation_key:
            self._attr_translation_key = translation_key
        else:
            # Use entity_key as translation_key by default
            self._attr_translation_key = entity_key

        # Get dog info
        self._dog_config = self._get_dog_config()

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=f"🐕 {self.dog_name}",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )

    @property
    def dog_name(self) -> str:
        """Return the dog's name."""
        return self._dog_config.get(CONF_DOG_NAME, self.dog_id)

    @property
    def dog_data(self) -> dict[str, Any]:
        """Return all data for this dog."""
        return self.coordinator.get_dog_data(self.dog_id)

    def _get_dog_config(self) -> dict[str, Any]:
        """Get dog configuration from entry options."""
        dogs = self.entry.options.get("dogs", [])
        for dog in dogs:
            if dog.get(CONF_DOG_ID) == self.dog_id:
                return dog
        return {}

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available
            and self.dog_id in self.coordinator._dog_data
        )


class PawControlSensorEntity(PawControlEntity):
    """Base sensor entity for PawControl."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        state_class: str | None = None,
        unit_of_measurement: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize sensor entity."""
        super().__init__(coordinator, entry, dog_id, entity_key, translation_key)

        # Set sensor-specific attributes
        if device_class:
            self._attr_device_class = device_class
        if state_class:
            self._attr_state_class = state_class
        if unit_of_measurement:
            self._attr_native_unit_of_measurement = unit_of_measurement
        if entity_category:
            self._attr_entity_category = entity_category


class PawControlBinarySensorEntity(PawControlEntity):
    """Base binary sensor entity for PawControl."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize binary sensor entity."""
        super().__init__(coordinator, entry, dog_id, entity_key, translation_key)

        # Set binary sensor-specific attributes
        if device_class:
            self._attr_device_class = device_class
        if entity_category:
            self._attr_entity_category = entity_category


class PawControlButtonEntity(PawControlEntity):
    """Base button entity for PawControl."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize button entity."""
        super().__init__(coordinator, entry, dog_id, entity_key, translation_key)

        # Set button-specific attributes
        if device_class:
            self._attr_device_class = device_class
        if entity_category:
            self._attr_entity_category = entity_category


class PawControlNumberEntity(PawControlEntity):
    """Base number entity for PawControl."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        unit_of_measurement: str | None = None,
        entity_category: EntityCategory | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
        step: float | None = None,
    ) -> None:
        """Initialize number entity."""
        super().__init__(coordinator, entry, dog_id, entity_key, translation_key)

        # Set number-specific attributes
        if device_class:
            self._attr_device_class = device_class
        if unit_of_measurement:
            self._attr_native_unit_of_measurement = unit_of_measurement
        if entity_category:
            self._attr_entity_category = entity_category
        if min_value is not None:
            self._attr_native_min_value = min_value
        if max_value is not None:
            self._attr_native_max_value = max_value
        if step is not None:
            self._attr_native_step = step


class PawControlSelectEntity(PawControlEntity):
    """Base select entity for PawControl."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        options: list[str],
        translation_key: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator, entry, dog_id, entity_key, translation_key)

        # Set select-specific attributes
        self._attr_options = options
        if entity_category:
            self._attr_entity_category = entity_category


class PawControlTextEntity(PawControlEntity):
    """Base text entity for PawControl."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        entity_category: EntityCategory | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
    ) -> None:
        """Initialize text entity."""
        super().__init__(coordinator, entry, dog_id, entity_key, translation_key)

        # Set text-specific attributes
        if entity_category:
            self._attr_entity_category = entity_category
        if min_length is not None:
            self._attr_native_min = min_length
        if max_length is not None:
            self._attr_native_max = max_length
        if pattern:
            self._attr_pattern = pattern


class PawControlSwitchEntity(PawControlEntity):
    """Base switch entity for PawControl."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        device_class: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize switch entity."""
        super().__init__(coordinator, entry, dog_id, entity_key, translation_key)

        # Set switch-specific attributes
        if device_class:
            self._attr_device_class = device_class
        if entity_category:
            self._attr_entity_category = entity_category


class PawControlDateTimeEntity(PawControlEntity):
    """Base datetime entity for PawControl."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        entry: ConfigEntry,
        dog_id: str,
        entity_key: str,
        translation_key: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize datetime entity."""
        super().__init__(coordinator, entry, dog_id, entity_key, translation_key)

        # Set datetime-specific attributes
        if entity_category:
            self._attr_entity_category = entity_category
