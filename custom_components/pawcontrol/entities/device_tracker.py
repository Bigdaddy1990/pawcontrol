# entities/device_tracker.py
from homeassistant.components.device_tracker import TrackerEntity

from .base import PawControlBaseEntity
from ..helpers.gps import format_gps_coords, is_valid_gps_coords


class PawControlDeviceTrackerEntity(PawControlBaseEntity, TrackerEntity):
    """Basisklasse für Device Tracker-Entities mit Koordinatenvalidierung."""

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
        """Aktualisiere den internen GPS-Status."""
        data = self.coordinator.data.get(self._attr_name, {})
        lat = data.get("lat")
        lon = data.get("lon")
        if is_valid_gps_coords(lat, lon):
            self._state = {"lat": lat, "lon": lon}
        else:
            self._state = None

    @property
    def latitude(self):
        return self._state["lat"] if self._state else None

    @property
    def longitude(self):
        return self._state["lon"] if self._state else None

    @property
    def extra_state_attributes(self):
        if self._state:
            return self.build_extra_attributes(
                coords=format_gps_coords(self.latitude, self.longitude)
            )
        return super().extra_state_attributes

    @property
    def source_type(self):
        return "gps"
