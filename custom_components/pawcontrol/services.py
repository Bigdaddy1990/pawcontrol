"""Services for Paw Control integration."""
from __future__ import annotations

import logging
import voluptuous as vol
from datetime import datetime

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_FEED_DOG,
    SERVICE_START_WALK,
    SERVICE_LOG_HEALTH,
    SERVICE_FOOD_TYPE,
    SERVICE_FOOD_AMOUNT,
    SERVICE_DURATION,
    SERVICE_WEIGHT,
    SERVICE_NOTES,
)
from .service_handlers import (
    update_feeding_entities,
    update_walk_start_entities,
    update_walk_end_entities,
    update_health_entities,
    reset_all_entities,
    update_gps_entities,
)
from .helpers.push import PushHelper
from .helpers.gps import GPSHelper

_LOGGER = logging.getLogger(__name__)

FEED_DOG_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Optional(SERVICE_FOOD_TYPE, default="morning"): vol.In(["morning", "lunch", "evening", "snack"]),
    vol.Optional(SERVICE_FOOD_AMOUNT, default=100): vol.All(vol.Coerce(int), vol.Range(min=10, max=1000)),
})

START_WALK_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Optional("walk_type", default="normal"): vol.In(["short", "normal", "long"]),
})

END_WALK_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Optional(SERVICE_DURATION, default=30): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
})

HEALTH_CHECK_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Optional(SERVICE_WEIGHT): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=100.0)),
    vol.Optional("temperature"): vol.All(vol.Coerce(float), vol.Range(min=35.0, max=42.0)),
    vol.Optional(SERVICE_NOTES): cv.string,
})

UPDATE_GPS_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
    vol.Required("latitude"): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
    vol.Required("longitude"): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
    vol.Optional("accuracy", default=10): vol.All(vol.Coerce(int), vol.Range(min=1, max=1000)),
})

DAILY_RESET_SCHEMA = vol.Schema({
    vol.Required("dog_name"): cv.string,
})

async def async_setup_services(hass: HomeAssistant, dog_name: str) -> None:
    """Setup services for Paw Control."""
    
    # Initialize helpers
    push_helper = PushHelper(hass)
    gps_helper = GPSHelper(hass)
    
    async def handle_feed_dog(call: ServiceCall) -> None:
        """Handle feed dog service."""
        dog_name = call.data["dog_name"].lower().replace(" ", "_")
        data = dict(call.data)
        await update_feeding_entities(hass, dog_name, data)
        
        # Send push notification if enabled
        await push_helper.send_feeding_notification(dog_name, data.get(SERVICE_FOOD_TYPE, "food"))
        _LOGGER.info("Fed %s with %s", dog_name, data.get(SERVICE_FOOD_TYPE, "food"))

    async def handle_start_walk(call: ServiceCall) -> None:
        """Handle start walk service."""
        dog_name = call.data["dog_name"].lower().replace(" ", "_")
        data = dict(call.data)
        await update_walk_start_entities(hass, dog_name, data)
        
        # Send push notification
        await push_helper.send_walk_notification(dog_name, "started")
        _LOGGER.info("Started walk for %s", dog_name)

    async def handle_end_walk(call: ServiceCall) -> None:
        """Handle end walk service."""
        dog_name = call.data["dog_name"].lower().replace(" ", "_")
        data = dict(call.data)
        await update_walk_end_entities(hass, dog_name, data)
        
        # Send push notification
        duration = data.get(SERVICE_DURATION, 30)
        await push_helper.send_walk_notification(dog_name, "ended", duration)
        _LOGGER.info("Ended walk for %s", dog_name)

    async def handle_health_check(call: ServiceCall) -> None:
        """Handle health check service."""
        dog_name = call.data["dog_name"].lower().replace(" ", "_")
        data = dict(call.data)
        await update_health_entities(hass, dog_name, data)
        
        # Send health notification if weight changed significantly
        if SERVICE_WEIGHT in data:
            await push_helper.send_health_notification(dog_name, "weight_update", data[SERVICE_WEIGHT])
        
        _LOGGER.info("Updated health data for %s", dog_name)

    async def handle_update_gps(call: ServiceCall) -> None:
        """Handle GPS update service."""
        dog_name = call.data["dog_name"].lower().replace(" ", "_")
        data = dict(call.data)
        
        # Validate and process GPS coordinates
        latitude = data["latitude"]
        longitude = data["longitude"]
        accuracy = data.get("accuracy", 10)
        
        if await gps_helper.validate_coordinates(latitude, longitude):
            await update_gps_entities(hass, dog_name, data)
            
            # Check for geofence alerts
            await gps_helper.check_geofence(dog_name, latitude, longitude)
            
            _LOGGER.info("Updated GPS for %s: %f, %f", dog_name, latitude, longitude)
        else:
            _LOGGER.error("Invalid GPS coordinates for %s: %f, %f", dog_name, latitude, longitude)

    async def handle_daily_reset(call: ServiceCall) -> None:
        """Handle daily reset service."""
        dog_name = call.data["dog_name"].lower().replace(" ", "_")
        data = dict(call.data)
        await reset_all_entities(hass, dog_name, data)
        
        # Send reset notification
        await push_helper.send_system_notification(dog_name, "daily_reset")
        _LOGGER.info("Reset daily data for %s", dog_name)

    # Register services
    hass.services.async_register(DOMAIN, SERVICE_FEED_DOG, handle_feed_dog, schema=FEED_DOG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_START_WALK, handle_start_walk, schema=START_WALK_SCHEMA)
    hass.services.async_register(DOMAIN, "end_walk", handle_end_walk, schema=END_WALK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_LOG_HEALTH, handle_health_check, schema=HEALTH_CHECK_SCHEMA)
    hass.services.async_register(DOMAIN, "update_gps", handle_update_gps, schema=UPDATE_GPS_SCHEMA)
    hass.services.async_register(DOMAIN, "daily_reset", handle_daily_reset, schema=DAILY_RESET_SCHEMA)
    
    _LOGGER.info("Paw Control services registered successfully")
```,
    _LOGGER.info("Paw Control services registered successfully")
