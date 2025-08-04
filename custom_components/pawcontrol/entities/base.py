"""Gemeinsame Basisklasse für Paw Control-Entities."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..helpers.entity import build_attributes, format_name, get_icon
from ..utils import safe_service_call


class PawControlBaseEntity(CoordinatorEntity):
    """Gemeinsame Funktionalität für alle Entities der Integration."""

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
        """Initialisiere die Basis-Entity."""
        if dog_name and key and not name:
            name = format_name(dog_name, key)
        if key and not unique_suffix:
            unique_suffix = key

        super().__init__(coordinator)
        self._attr_name = name
        self._dog_name = dog_name
        self._state = None

        if dog_name and unique_suffix:
            self._attr_unique_id = f"{DOMAIN}_{dog_name.lower()}_{unique_suffix}"
        if icon or key:
            self._attr_icon = icon or get_icon(key)

    @property
    def available(self) -> bool:
        """Verfügbarkeit, standardmäßig via Coordinator."""
        return getattr(self.coordinator, "last_update_success", True)

    async def async_update(self) -> None:
        """Standard-Update via Coordinator."""
        await self.coordinator.async_request_refresh()
        self._update_state()

    def _update_state(self) -> None:
        """Setzt ``self._state``. Kann in Unterklassen überschrieben werden."""
        self._state = self.coordinator.data.get(self._attr_name)

    @property
    def device_info(self) -> dict | None:
        """Gebe Geräteinformationen zurück, falls ein Hund gesetzt wurde."""
        if not self._dog_name:
            return None
        return {
            "identifiers": {(DOMAIN, self._dog_name.lower())},
            "name": f"Paw Control - {self._dog_name}",
            "manufacturer": "Paw Control",
            "model": "Dog Management System",
            "sw_version": "1.0.0",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Zusätzliche Attribute für den Entity-State."""
        if not self._dog_name:
            return {}
        return self.build_extra_attributes()

    def build_extra_attributes(self, **extra: Any) -> dict[str, Any]:
        """Hilfsfunktion für Unterklassen zur Attribut-Erstellung."""
        return build_attributes(self._dog_name, **extra)

    async def _safe_service_call(self, domain: str, service: str, data: dict) -> bool:
        """Hilfsfunktion für sichere Serviceaufrufe."""
        return await safe_service_call(self.hass, domain, service, data)
