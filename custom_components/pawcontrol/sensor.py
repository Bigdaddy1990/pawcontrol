
"""Sensors for Paw Control."""
from __future__ import annotations
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from .const import DOMAIN, MODULE_GPS
PARALLEL_UPDATES = 0

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    dogs = (entry.options or {}).get("dogs", [])
    modules = (entry.options or {}).get("modules", {})
    entities: list[BaseDogSensor] = []
    for d in dogs:
        dog_id = d.get("dog_id") or d.get("name")
        title = d.get("name") or dog_id or "Dog"
        if not dog_id:
            continue
        entities.extend([
            WalkDistanceCurrentSensor(hass, dog_id, title),
            WalkDistanceLastSensor(hass, dog_id, title),
            WalkDurationLastSensor(hass, dog_id, title),
            WalkAvgSpeedLastSensor(hass, dog_id, title),
            WalkDistanceTodaySensor(hass, dog_id, title),
            WalkTimeTodaySensor(hass, dog_id, title),
        ])
        # Diagnostics
        entities.extend([
            GPSPointsTotalSensor(hass, dog_id, title),
            GPSPointsDroppedSensor(hass, dog_id, title),
            GPSAccuracyAvgSensor(hass, dog_id, title),
            TimeInSafeZoneTodaySensor(hass, dog_id, title),
            SafeZoneEntersTodaySensor(hass, dog_id, title),
            SafeZoneLeavesTodaySensor(hass, dog_id, title),
        ])
    if entities:
        async_add_entities(entities)


class BaseDogSensor(SensorEntity):
    @property
    def available(self) -> bool:
        try:
            data = self.hass.data.get(DOMAIN) or {}
            for entry_id, st in data.items():
                coord = st.get('coordinator')
                if coord and getattr(coord, '_dog_data', {}).get(self._dog) is not None:
                    return bool(getattr(coord, 'last_update_success', True))
        except Exception:
            pass
        return True
    try:
        data = self.hass.data.get(DOMAIN) or {}
        for entry_id, st in data.items():
            coord = st.get('coordinator')
            if coord and getattr(coord, '_dog_data', {}).get(self._dog) is not None:
                return bool(getattr(coord, 'last_update_success', True))
    except Exception:
        pass
    return True

    _attr_has_entity_name = True
    def __init__(self, hass: HomeAssistant, dog_id: str, title: str, key: str):
        self.hass = hass
        self._dog = dog_id
        self._name = title
        self._key = key
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.sensor.{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, dog_id)}, name=f"Hund {title}", manufacturer="Paw Control", model="PawControl Sensors" )

class WalkDistanceCurrentSensor(BaseDogSensor):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "walk_distance_current")
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_unit_of_measurement(self): return "m"
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_walk_distance_current")
        try: return round(float(st.state), 1) if st and st.state not in ("unknown","unavailable") else None
        except Exception: return None

class WalkDistanceLastSensor(BaseDogSensor):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "walk_distance_last")
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_unit_of_measurement(self): return "m"
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_walk_distance_last")
        try: return round(float(st.state), 1) if st and st.state not in ("unknown","unavailable") else None
        except Exception: return None

class WalkDurationLastSensor(BaseDogSensor):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "walk_duration_last")
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_unit_of_measurement(self): return "s"
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_walk_duration_last")
        try: return int(float(st.state)) if st and st.state not in ("unknown","unavailable") else None
        except Exception: return None

class WalkAvgSpeedLastSensor(BaseDogSensor):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "walk_avg_speed_last")
    _attr_device_class = SensorDeviceClass.SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_unit_of_measurement(self): return "km/h"
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_walk_avg_speed_last")
        try: return round(float(st.state), 2) if st and st.state not in ("unknown","unavailable") else None
        except Exception: return None

class WalkDistanceTodaySensor(BaseDogSensor):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "walk_distance_today")
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_unit_of_measurement(self): return "m"
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_walk_distance_today")
        try: return round(float(st.state), 1) if st and st.state not in ("unknown","unavailable") else 0.0
        except Exception: return 0.0

class WalkTimeTodaySensor(BaseDogSensor):
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "walk_time_today")
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_unit_of_measurement(self): return "s"
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_walk_time_today")
        try: return int(float(st.state)) if st and st.state not in ("unknown","unavailable") else 0
        except Exception: return 0

class GPSPointsTotalSensor(BaseDogSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "gps_points_total")
    _attr_entity_category = "diagnostic"
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_gps_points_total")
        try: return int(float(st.state)) if st and st.state not in ("unknown","unavailable") else 0
        except Exception: return 0

class GPSPointsDroppedSensor(BaseDogSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "gps_points_dropped")
    _attr_entity_category = "diagnostic"
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_gps_points_dropped")
        try: return int(float(st.state)) if st and st.state not in ("unknown","unavailable") else 0
        except Exception: return 0

class GPSAccuracyAvgSensor(BaseDogSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "gps_accuracy_avg")
    _attr_entity_category = "diagnostic"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_unit_of_measurement(self): return "m"
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_gps_accuracy_avg")
        try: return round(float(st.state), 1) if st and st.state not in ("unknown","unavailable") else None
        except Exception: return None


class TimeInSafeZoneTodaySensor(BaseDogSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "time_in_safe_zone_today")
    _attr_entity_category = "diagnostic"
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_unit_of_measurement(self): return "s"
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_time_in_safe_zone_today")
        try: return int(float(st.state)) if st and st.state not in ("unknown","unavailable") else 0
        except Exception: return 0

class SafeZoneEntersTodaySensor(BaseDogSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "safe_zone_enters_today")
    _attr_entity_category = "diagnostic"
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_safe_zone_enters_today")
        try: return int(float(st.state)) if st and st.state not in ("unknown","unavailable") else 0
        except Exception: return 0

class SafeZoneLeavesTodaySensor(BaseDogSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, hass, dog_id, title): super().__init__(hass, dog_id, title, "safe_zone_leaves_today")
    _attr_entity_category = "diagnostic"
    _attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_safe_zone_leaves_today")
        try: return int(float(st.state)) if st and st.state not in ("unknown","unavailable") else 0
        except Exception: return 0