"""GPS and location logic for Paw Control integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    STATE_HOME,
    STATE_NOT_HOME,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from ..const import (
    CONF_DEVICE_TRACKERS,
    CONF_DOGS,
    CONF_DOOR_SENSOR,
    CONF_PERSON_ENTITIES,
    CONF_SOURCES,
    DEFAULT_IDLE_TIMEOUT_MIN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class GPSLogic:
    """Handle GPS tracking and walk detection logic."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize GPS logic."""
        self.hass = hass
        self.entry = entry
        self._tracked_entities: Dict[str, Any] = {}
        self._walk_sessions: Dict[str, Dict[str, Any]] = {}
        self._door_sensor: Optional[str] = None
        self._unsubscribe_callbacks: list[CALLBACK_TYPE] = []

    async def setup(self) -> None:
        """Set up GPS tracking."""
        sources = self.entry.options.get(CONF_SOURCES, {})

        # Setup door sensor tracking
        door_sensor = sources.get(CONF_DOOR_SENSOR)
        if door_sensor:
            self._door_sensor = door_sensor
            await self._setup_door_sensor_tracking()

        # Setup device tracker entities
        device_trackers = sources.get(CONF_DEVICE_TRACKERS, [])
        for tracker in device_trackers:
            await self._setup_device_tracker(tracker)

        # Setup person entities
        person_entities = sources.get(CONF_PERSON_ENTITIES, [])
        for person in person_entities:
            await self._setup_person_tracking(person)

    async def cleanup(self) -> None:
        """Clean up GPS tracking."""
        for unsubscribe in self._unsubscribe_callbacks:
            unsubscribe()
        self._unsubscribe_callbacks.clear()
        self._tracked_entities.clear()
        self._walk_sessions.clear()

    async def _setup_door_sensor_tracking(self) -> None:
        """Set up door sensor tracking for walk detection."""
        if not self._door_sensor:
            return

        @callback
        def door_sensor_changed(entity_id: str, old_state: State, new_state: State):
            """Handle door sensor state change."""
            if not new_state or not old_state:
                return

            # Door opened
            if old_state.state == "off" and new_state.state == "on":
                self._handle_door_opened()
            # Door closed
            elif old_state.state == "on" and new_state.state == "off":
                self._handle_door_closed()

        # Track door sensor changes
        unsubscribe = async_track_state_change(
            self.hass,
            self._door_sensor,
            door_sensor_changed,
        )
        self._unsubscribe_callbacks.append(unsubscribe)

        _LOGGER.info(f"Door sensor tracking setup for {self._door_sensor}")

    async def _setup_device_tracker(self, tracker_entity: str) -> None:
        """Set up tracking for a device tracker entity."""

        @callback
        def tracker_changed(entity_id: str, old_state: State, new_state: State):
            """Handle device tracker state change."""
            if not new_state:
                return

            # Extract location data
            latitude = new_state.attributes.get(ATTR_LATITUDE)
            longitude = new_state.attributes.get(ATTR_LONGITUDE)

            if latitude is not None and longitude is not None:
                self._update_location(entity_id, latitude, longitude)

            # Check for zone changes
            if old_state and old_state.state != new_state.state:
                self._handle_zone_change(entity_id, old_state.state, new_state.state)

        # Track device tracker changes
        unsubscribe = async_track_state_change(
            self.hass,
            tracker_entity,
            tracker_changed,
        )
        self._unsubscribe_callbacks.append(unsubscribe)

        # Initialize tracking data
        self._tracked_entities[tracker_entity] = {
            "type": "device_tracker",
            "last_location": None,
            "last_update": None,
            "total_distance": 0,
        }

        _LOGGER.info(f"Device tracker setup for {tracker_entity}")

    async def _setup_person_tracking(self, person_entity: str) -> None:
        """Set up tracking for a person entity."""

        @callback
        def person_changed(entity_id: str, old_state: State, new_state: State):
            """Handle person state change."""
            if not new_state:
                return

            # Extract location data
            latitude = new_state.attributes.get(ATTR_LATITUDE)
            longitude = new_state.attributes.get(ATTR_LONGITUDE)

            if latitude is not None and longitude is not None:
                self._update_location(entity_id, latitude, longitude)

            # Check for home/away changes
            if old_state and old_state.state != new_state.state:
                if old_state.state == STATE_HOME and new_state.state == STATE_NOT_HOME:
                    self._handle_left_home(entity_id)
                elif (
                    old_state.state == STATE_NOT_HOME and new_state.state == STATE_HOME
                ):
                    self._handle_arrived_home(entity_id)

        # Track person changes
        unsubscribe = async_track_state_change(
            self.hass,
            person_entity,
            person_changed,
        )
        self._unsubscribe_callbacks.append(unsubscribe)

        # Initialize tracking data
        self._tracked_entities[person_entity] = {
            "type": "person",
            "last_location": None,
            "last_update": None,
            "total_distance": 0,
        }

        _LOGGER.info(f"Person tracking setup for {person_entity}")

    def _update_location(
        self, entity_id: str, latitude: float, longitude: float
    ) -> None:
        """Update location for tracked entity."""
        if entity_id not in self._tracked_entities:
            return

        tracking_data = self._tracked_entities[entity_id]
        new_location = (latitude, longitude)

        # Calculate distance from last location
        if tracking_data["last_location"]:
            dist = self._calculate_distance(
                tracking_data["last_location"], new_location
            )

            # Only update if movement is significant (> 5 meters)
            if dist > 5:
                tracking_data["total_distance"] += dist
                tracking_data["last_location"] = new_location
                tracking_data["last_update"] = dt_util.now()

                # Check if this could be a walk
                self._check_walk_activity(entity_id, dist)
        else:
            tracking_data["last_location"] = new_location
            tracking_data["last_update"] = dt_util.now()

    def _calculate_distance(
        self, loc1: Tuple[float, float], loc2: Tuple[float, float]
    ) -> float:
        """Calculate distance between two GPS coordinates in meters."""
        return distance(loc1[0], loc1[1], loc2[0], loc2[1]) * 1000

    def _handle_door_opened(self) -> None:
        """Handle door opened event."""
        _LOGGER.debug("Door opened - potential walk start")

        # Mark potential walk start for all dogs
        dogs = self.entry.options.get(CONF_DOGS, [])
        for dog in dogs:
            dog_id = dog.get("dog_id")
            if dog_id and dog_id not in self._walk_sessions:
                self._walk_sessions[dog_id] = {
                    "door_opened_at": dt_util.now(),
                    "potential_walk": True,
                    "confirmed": False,
                }

    def _handle_door_closed(self) -> None:
        """Handle door closed event."""
        _LOGGER.debug("Door closed")

        # Check if anyone left recently
        for dog_id, session in self._walk_sessions.items():
            if session.get("potential_walk") and not session.get("confirmed"):
                # Check if door was opened recently (within 2 minutes)
                if session.get("door_opened_at"):
                    time_diff = (
                        dt_util.now() - session["door_opened_at"]
                    ).total_seconds()
                    if time_diff < 120:  # 2 minutes
                        # Likely someone left with dog
                        self._confirm_walk_start(dog_id, "door")

    def _handle_zone_change(self, entity_id: str, old_zone: str, new_zone: str) -> None:
        """Handle zone change for tracked entity."""
        _LOGGER.debug(f"{entity_id} moved from {old_zone} to {new_zone}")

        # Check if left home
        if old_zone == STATE_HOME and new_zone != STATE_HOME:
            self._handle_left_home(entity_id)
        # Check if arrived home
        elif old_zone != STATE_HOME and new_zone == STATE_HOME:
            self._handle_arrived_home(entity_id)

    def _handle_left_home(self, entity_id: str) -> None:
        """Handle entity leaving home."""
        _LOGGER.info(f"{entity_id} left home")

        # Start walk for associated dogs
        dogs = self._get_dogs_for_entity(entity_id)
        for dog_id in dogs:
            self._confirm_walk_start(dog_id, "gps")

    def _handle_arrived_home(self, entity_id: str) -> None:
        """Handle entity arriving home."""
        _LOGGER.info(f"{entity_id} arrived home")

        # End walk for associated dogs
        dogs = self._get_dogs_for_entity(entity_id)
        for dog_id in dogs:
            self._confirm_walk_end(dog_id, "home")

    def _check_walk_activity(self, entity_id: str, distance: float) -> None:
        """Check if movement indicates walk activity."""
        dogs = self._get_dogs_for_entity(entity_id)

        for dog_id in dogs:
            if dog_id in self._walk_sessions:
                session = self._walk_sessions[dog_id]

                # Add distance to current walk
                if session.get("confirmed"):
                    session["total_distance"] = (
                        session.get("total_distance", 0) + distance
                    )
                    session["last_movement"] = dt_util.now()

                    # Update coordinator
                    self._update_walk_distance(dog_id, session["total_distance"])

    def _confirm_walk_start(self, dog_id: str, source: str) -> None:
        """Confirm walk has started."""
        _LOGGER.info(f"Walk started for {dog_id} via {source}")

        # Initialize or update walk session
        if dog_id not in self._walk_sessions:
            self._walk_sessions[dog_id] = {}

        self._walk_sessions[dog_id].update(
            {
                "confirmed": True,
                "start_time": dt_util.now(),
                "source": source,
                "total_distance": 0,
                "last_movement": dt_util.now(),
            }
        )

        # Call service to start walk
        self.hass.async_create_task(
            self.hass.services.async_call(
                DOMAIN,
                "start_walk",
                {
                    "dog_id": dog_id,
                    "source": source,
                },
                blocking=False,
            )
        )

    def _confirm_walk_end(self, dog_id: str, reason: str) -> None:
        """Confirm walk has ended."""
        if dog_id not in self._walk_sessions:
            return

        session = self._walk_sessions.get(dog_id, {})
        if not session.get("confirmed"):
            return

        _LOGGER.info(f"Walk ended for {dog_id} - reason: {reason}")

        # Calculate walk duration
        start_time = session.get("start_time")
        if start_time:
            (dt_util.now() - start_time).total_seconds() / 60
        else:
            pass

        # Call service to end walk
        self.hass.async_create_task(
            self.hass.services.async_call(
                DOMAIN,
                "end_walk",
                {
                    "dog_id": dog_id,
                    "reason": reason,
                },
                blocking=False,
            )
        )

        # Clear walk session
        del self._walk_sessions[dog_id]

    def _update_walk_distance(self, dog_id: str, distance_m: float) -> None:
        """Update walk distance in coordinator."""
        coordinator = (
            self.hass.data[DOMAIN].get(self.entry.entry_id, {}).get("coordinator")
        )

        if coordinator:
            dog_data = coordinator.get_dog_data(dog_id)
            if dog_data and "walk" in dog_data:
                dog_data["walk"]["walk_distance_m"] = round(distance_m, 1)

    def _get_dogs_for_entity(self, entity_id: str) -> list[str]:
        """Get list of dogs associated with a tracked entity."""
        # For now, return all dogs
        # In a more complex setup, this could map specific trackers to specific dogs
        dogs = self.entry.options.get(CONF_DOGS, [])
        return [dog.get("dog_id") for dog in dogs if dog.get("dog_id")]

    def check_idle_timeout(self) -> None:
        """Check for idle walk sessions and end them."""
        current_time = dt_util.now()
        idle_timeout = timedelta(minutes=DEFAULT_IDLE_TIMEOUT_MIN)

        for dog_id, session in list(self._walk_sessions.items()):
            if session.get("confirmed"):
                last_movement = session.get("last_movement")
                if last_movement and (current_time - last_movement) > idle_timeout:
                    _LOGGER.info(f"Walk idle timeout for {dog_id}")
                    self._confirm_walk_end(dog_id, "idle")

    def get_current_location(self, entity_id: str) -> Optional[Tuple[float, float]]:
        """Get current location for tracked entity."""
        if entity_id in self._tracked_entities:
            return self._tracked_entities[entity_id].get("last_location")
        return None

    def get_distance_from_home(self, entity_id: str) -> Optional[float]:
        """Get distance from home for tracked entity."""
        current_location = self.get_current_location(entity_id)
        if not current_location:
            return None

        # Get home zone
        home_zone = self.hass.states.get("zone.home")
        if not home_zone:
            return None

        home_lat = home_zone.attributes.get(ATTR_LATITUDE)
        home_lon = home_zone.attributes.get(ATTR_LONGITUDE)

        if home_lat is None or home_lon is None:
            return None

        return self._calculate_distance((home_lat, home_lon), current_location)
