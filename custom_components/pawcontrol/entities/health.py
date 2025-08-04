"""Gemeinsame Basisklasse für Health-bezogene Entities."""

from __future__ import annotations

from homeassistant.helpers.entity import Entity

from ..const import DOMAIN
from ..helpers.entity import build_attributes


class PawControlHealthEntity(Entity):
    """Basisklasse für Health-Überwachungs-Entities."""

    def __init__(
        self,
        activity_logger,
        entry_id: str,
        name: str,
        suffix: str,
        dog_name: str | None = None,
    ) -> None:
        """Initialisiere die Health-Entity.

        Der optionale Parameter ``dog_name`` kann ``None`` sein, wenn die
        Entity keinem spezifischen Hund zugeordnet ist.
        """
        self._activity_logger = activity_logger
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{suffix}_{entry_id}"
        self._dog_name = dog_name

    @property
    def _latest_health(self):
        """Gibt den letzten Health-Eintrag zurück."""
        return self._activity_logger.get_latest("health")

    @property
    def extra_state_attributes(self):
        """Standard-Attribute enthalten den letzten Health-Eintrag."""
        latest = self._latest_health or {}
        return build_attributes(self._dog_name, **latest)
