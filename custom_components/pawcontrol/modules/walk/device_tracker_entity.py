"""Device Tracker Entity für Paw Control."""
from homeassistant.components.device_tracker import TrackerEntity
from ...base.entity import BaseEntity
from ...helpers.gps import format_gps_coords, is_valid_gps_coords

class PawControlDeviceTrackerEntity(BaseEntity, TrackerEntity):
    def __init__(self, coordinator, name=None, dog_name=None, unique_suffix=None, *, key=None, icon=None):
        super().__init__(coordinator, name, dog_name, unique_suffix, key=key, icon=icon)

    def _update_state(self) -> None:
        # Logik zur GPS-Validierung oder -Anzeige
        pass
