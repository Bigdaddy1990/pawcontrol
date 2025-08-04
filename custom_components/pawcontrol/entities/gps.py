"""Gemeinsame GPS-Basisklasse für alle Paw Control GPS-Entities."""

from .base import PawControlBaseEntity
from ..helpers.gps import is_valid_gps_coords


class PawControlGpsEntity(PawControlBaseEntity):
    """Basisklasse für GPS-Entities mit gemeinsamer Update-Logik."""

    def __init__(self, coordinator, name):
        """Initialisiere die GPS-Entity."""
        super().__init__(coordinator, name)

    @property
    def available(self):
        """Entity ist verfügbar, wenn Koordinaten gültig sind."""
        data = self.coordinator.data.get(self._attr_name, {})
        return is_valid_gps_coords(data.get("lat"), data.get("lon"))

    def _update_state(self):
        """Aktualisiere internen State mit gültigen Koordinaten."""
        data = self.coordinator.data.get(self._attr_name, {})
        if is_valid_gps_coords(data.get("lat"), data.get("lon")):
            self._state = (data["lat"], data["lon"])
        else:
            self._state = None

    @property
    def extra_state_attributes(self):
        if self._state:
            lat, lon = self._state
            return self.build_extra_attributes(lat=lat, lon=lon)
        return super().extra_state_attributes
