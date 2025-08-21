"""The Paw Control integration for Home Assistant.

This integration provides comprehensive smart dog management functionality
including GPS tracking, feeding management, health monitoring, and walk tracking.
Designed to meet Home Assistant's Platinum quality standards with full async
operation, complete type annotations, and robust error handling.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    ATTR_MEAL_TYPE,
    ATTR_PORTION_SIZE,
    ATTR_TIMESTAMP,
    ATTR_WALK_DISTANCE,
    ATTR_WALK_DURATION,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_RESET_TIME,
    DEFAULT_RESET_TIME,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
    SERVICE_DAILY_RESET,
    SERVICE_FEED_DOG,
    SERVICE_GPS_END_WALK,
    SERVICE_GPS_START_WALK,
    SERVICE_LOG_HEALTH,
    SERVICE_LOG_MEDICATION,
    SERVICE_LOG_POOP,
    SERVICE_NOTIFY_TEST,
    SERVICE_START_GROOMING,
    SERVICE_START_WALK,
    SERVICE_END_WALK,
    SERVICE_TOGGLE_VISITOR_MODE,
)
from .coordinator import PawControlCoordinator
from .helpers import PawControlData, PawControlNotificationManager

_LOGGER = logging.getLogger(__name__)

# All platforms this integration provides
PLATFORMS: List[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
    Platform.DATETIME,
    Platform.DEVICE_TRACKER,
]

# Service validation schemas with comprehensive validation
SERVICE_FEED_DOG_SCHEMA = vol.Schema({
    vol.Required(ATTR_DOG_ID): cv.string,
    vol.Required(ATTR_MEAL_TYPE): vol.In(["breakfast", "lunch", "dinner", "snack"]),
    vol.Optional(ATTR_PORTION_SIZE, default=0): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=10000)
    ),
})

SERVICE_WALK_SCHEMA = vol.Schema({
    vol.Required(ATTR_DOG_ID): cv.string,
    vol.Optional("label", default=""): vol.All(cv.string, vol.Length(max=100)),
})

SERVICE_GPS_WALK_SCHEMA = vol.Schema({
    vol.Required(ATTR_DOG_ID): cv.string,
    vol.Optional("label", default=""): vol.All(cv.string, vol.Length(max=100)),
    vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
})

SERVICE_HEALTH_SCHEMA = vol.Schema({
    vol.Required(ATTR_DOG_ID): cv.string,
    vol.Optional("weight_kg"): vol.All(
        vol.Coerce(float), vol.Range(min=0.1, max=200.0)
    ),
    vol.Optional("note", default=""): vol.All(cv.string, vol.Length(max=500)),
})

SERVICE_MEDICATION_SCHEMA = vol.Schema({
    vol.Required(ATTR_DOG_ID): cv.string,
    vol.Required("medication_name"): vol.All(cv.string, vol.Length(max=100)),
    vol.Optional("dose", default=""): vol.All(cv.string, vol.Length(max=100)),
})

SERVICE_GROOMING_SCHEMA = vol.Schema({
    vol.Required(ATTR_DOG_ID): cv.string,
    vol.Required("type"): vol.In(["bath", "brush", "nails", "teeth", "trim"]),
    vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
})

SERVICE_NOTIFY_TEST_SCHEMA = vol.Schema({
    vol.Required(ATTR_DOG_ID): cv.string,
    vol.Optional("message", default="Test notification"): vol.All(
        cv.string, vol.Length(max=200)
    ),
})

SERVICE_VISITOR_MODE_SCHEMA = vol.Schema({
    vol.Required(ATTR_DOG_ID): cv.string,
    vol.Optional("enabled"): cv.boolean,
})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Paw Control integration from configuration.yaml.
    
    This function handles legacy configuration setup. New installations
    should use the config flow for UI-based setup.
    
    Args:
        hass: Home Assistant instance
        config: Configuration dictionary from configuration.yaml
        
    Returns:
        True if setup was successful
    """
    # Initialize domain data storage
    hass.data.setdefault(DOMAIN, {})
    
    _LOGGER.debug("Paw Control integration legacy setup completed")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Paw Control from a config entry.
    
    This is the main setup function for the integration. It initializes
    all components including the coordinator, data manager, and notification
    system. All operations are performed asynchronously for optimal performance.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry containing integration configuration
        
    Returns:
        True if setup was successful
        
    Raises:
        ConfigEntryNotReady: If setup cannot be completed
    """
    _LOGGER.debug("Setting up Paw Control integration entry: %s", entry.entry_id)
    
    try:
        # Validate that dogs are configured
        dogs_config = entry.data.get(CONF_DOGS, [])
        if not dogs_config:
            _LOGGER.error("No dogs configured in entry")
            raise ConfigEntryNotReady("No dogs configured")
        
        # Validate dog configuration structure
        for dog in dogs_config:
            if not dog.get(CONF_DOG_ID) or not dog.get(CONF_DOG_NAME):
                _LOGGER.error("Invalid dog configuration: %s", dog)
                raise ConfigEntryNotReady("Invalid dog configuration")
        
        # Initialize core components concurrently for better performance
        coordinator_task = asyncio.create_task(
            _async_setup_coordinator(hass, entry)
        )
        data_manager_task = asyncio.create_task(
            _async_setup_data_manager(hass, entry)
        )
        notification_manager_task = asyncio.create_task(
            _async_setup_notification_manager(hass, entry)
        )
        
        # Wait for all core components to initialize
        coordinator, data_manager, notification_manager = await asyncio.gather(
            coordinator_task,
            data_manager_task,
            notification_manager_task,
        )
        
        # Store all components in hass.data
        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "data": data_manager,
            "notifications": notification_manager,
            "entry": entry,
        }
        
        # Setup platforms - this creates all entities
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        # Register integration services
        await _async_register_services(hass)
        
        # Setup daily reset scheduler
        await _async_setup_daily_reset_scheduler(hass, entry)
        
        # Perform initial data refresh
        await coordinator.async_config_entry_first_refresh()
        
        _LOGGER.info(
            "Paw Control integration setup completed successfully for %d dogs",
            len(dogs_config)
        )
        return True
        
    except ConfigEntryNotReady:
        # Re-raise ConfigEntryNotReady exceptions
        raise
    except Exception as err:
        _LOGGER.error("Failed to setup Paw Control integration: %s", err, exc_info=True)
        raise ConfigEntryNotReady(f"Setup failed: {err}") from err


async def _async_setup_coordinator(
    hass: HomeAssistant, 
    entry: ConfigEntry
) -> PawControlCoordinator:
    """Initialize and setup the data coordinator.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry
        
    Returns:
        Initialized coordinator instance
    """
    coordinator = PawControlCoordinator(hass, entry)
    _LOGGER.debug("Data coordinator initialized")
    return coordinator


async def _async_setup_data_manager(
    hass: HomeAssistant, 
    entry: ConfigEntry
) -> PawControlData:
    """Initialize and setup the data manager.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry
        
    Returns:
        Initialized data manager instance
    """
    data_manager = PawControlData(hass, entry)
    await data_manager.async_load_data()
    _LOGGER.debug("Data manager initialized and data loaded")
    return data_manager


async def _async_setup_notification_manager(
    hass: HomeAssistant, 
    entry: ConfigEntry
) -> PawControlNotificationManager:
    """Initialize and setup the notification manager.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry
        
    Returns:
        Initialized notification manager instance
    """
    notification_manager = PawControlNotificationManager(hass, entry)
    _LOGGER.debug("Notification manager initialized")
    return notification_manager


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Paw Control config entry.
    
    This function cleanly shuts down all integration components and
    releases resources. All cleanup operations are performed asynchronously.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry to unload
        
    Returns:
        True if unload was successful
    """
    _LOGGER.debug("Unloading Paw Control integration entry: %s", entry.entry_id)
    
    # Unload all platforms
    unload_success = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    
    if unload_success:
        # Clean up integration data and stop coordinator
        entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
        
        # Shutdown coordinator if it exists
        coordinator = entry_data.get("coordinator")
        if coordinator:
            await coordinator.async_shutdown()
        
        # Remove entry data
        if entry.entry_id in hass.data[DOMAIN]:
            del hass.data[DOMAIN][entry.entry_id]
        
        _LOGGER.debug("Paw Control integration unloaded successfully")
    else:
        _LOGGER.error("Failed to unload Paw Control platforms")
    
    return unload_success


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a Paw Control config entry.
    
    This performs a complete reload of the integration by unloading
    and then setting up the entry again.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    _LOGGER.debug("Reloading Paw Control integration entry: %s", entry.entry_id)
    
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
    
    _LOGGER.info("Paw Control integration reloaded successfully")


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register all Paw Control services.
    
    This function registers all integration services with proper validation
    schemas. Services are only registered once globally, not per config entry.
    
    Args:
        hass: Home Assistant instance
    """
    # Check if services are already registered to avoid duplicates
    if hass.services.has_service(DOMAIN, SERVICE_FEED_DOG):
        _LOGGER.debug("Services already registered, skipping")
        return
    
    async def _handle_feed_dog_service(call: ServiceCall) -> None:
        """Handle the feed_dog service call.
        
        Args:
            call: Service call data
            
        Raises:
            ServiceValidationError: If dog is not found or other validation fails
        """
        dog_id = call.data[ATTR_DOG_ID]
        meal_type = call.data[ATTR_MEAL_TYPE]
        portion_size = call.data.get(ATTR_PORTION_SIZE, 0)
        
        _LOGGER.debug("Processing feed_dog service for %s: %s", dog_id, meal_type)
        
        # Find the entry data for this dog
        entry_data = _get_entry_data_for_dog(hass, dog_id)
        if not entry_data:
            raise ServiceValidationError(f"Dog '{dog_id}' not found in any configuration")
        
        data_manager = entry_data["data"]
        
        # Prepare feeding data with validation
        feeding_data = {
            "timestamp": datetime.now().isoformat(),
            "meal_type": meal_type,
            "portion_size": portion_size,
            "logged_by": "service_call",
        }
        
        try:
            await data_manager.async_log_feeding(dog_id, feeding_data)
            
            # Fire Home Assistant event for automations
            hass.bus.async_fire(EVENT_FEEDING_LOGGED, {
                ATTR_DOG_ID: dog_id,
                ATTR_MEAL_TYPE: meal_type,
                ATTR_PORTION_SIZE: portion_size,
                ATTR_TIMESTAMP: feeding_data["timestamp"],
            })
            
            _LOGGER.info("Logged feeding for %s: %s (%.1fg)", dog_id, meal_type, portion_size)
            
        except Exception as err:
            _LOGGER.error("Failed to log feeding for %s: %s", dog_id, err)
            raise ServiceValidationError(f"Failed to log feeding: {err}") from err
    
    async def _handle_start_walk_service(call: ServiceCall) -> None:
        """Handle the start_walk service call.
        
        Args:
            call: Service call data
            
        Raises:
            ServiceValidationError: If dog is not found or walk cannot be started
        """
        dog_id = call.data[ATTR_DOG_ID]
        label = call.data.get("label", "")
        
        _LOGGER.debug("Processing start_walk service for %s", dog_id)
        
        entry_data = _get_entry_data_for_dog(hass, dog_id)
        if not entry_data:
            raise ServiceValidationError(f"Dog '{dog_id}' not found in any configuration")
        
        data_manager = entry_data["data"]
        
        # Prepare walk data
        walk_data = {
            "start_time": datetime.now().isoformat(),
            "label": label.strip() if label else "",
            "status": "active",
            "started_by": "service_call",
        }
        
        try:
            await data_manager.async_start_walk(dog_id, walk_data)
            
            # Fire event for automations
            hass.bus.async_fire(EVENT_WALK_STARTED, {
                ATTR_DOG_ID: dog_id,
                ATTR_TIMESTAMP: walk_data["start_time"],
                "label": walk_data["label"],
            })
            
            _LOGGER.info("Started walk for %s%s", dog_id, f" ({label})" if label else "")
            
        except Exception as err:
            _LOGGER.error("Failed to start walk for %s: %s", dog_id, err)
            raise ServiceValidationError(f"Failed to start walk: {err}") from err
    
    async def _handle_end_walk_service(call: ServiceCall) -> None:
        """Handle the end_walk service call.
        
        Args:
            call: Service call data
            
        Raises:
            ServiceValidationError: If dog is not found or no active walk
        """
        dog_id = call.data[ATTR_DOG_ID]
        
        _LOGGER.debug("Processing end_walk service for %s", dog_id)
        
        entry_data = _get_entry_data_for_dog(hass, dog_id)
        if not entry_data:
            raise ServiceValidationError(f"Dog '{dog_id}' not found in any configuration")
        
        data_manager = entry_data["data"]
        
        try:
            walk_data = await data_manager.async_end_walk(dog_id)
            
            if walk_data:
                # Fire event with walk statistics
                hass.bus.async_fire(EVENT_WALK_ENDED, {
                    ATTR_DOG_ID: dog_id,
                    ATTR_WALK_DURATION: walk_data.get("duration", 0),
                    ATTR_WALK_DISTANCE: walk_data.get("distance", 0),
                    ATTR_TIMESTAMP: walk_data.get("end_time", ""),
                })
                
                _LOGGER.info(
                    "Ended walk for %s: %.1f minutes, %.0f meters",
                    dog_id,
                    walk_data.get("duration", 0),
                    walk_data.get("distance", 0)
                )
            else:
                _LOGGER.warning("No active walk found for %s", dog_id)
                
        except Exception as err:
            _LOGGER.error("Failed to end walk for %s: %s", dog_id, err)
            raise ServiceValidationError(f"Failed to end walk: {err}") from err
    
    async def _handle_log_health_data_service(call: ServiceCall) -> None:
        """Handle the log_health_data service call.
        
        Args:
            call: Service call data
            
        Raises:
            ServiceValidationError: If dog is not found or data is invalid
        """
        dog_id = call.data[ATTR_DOG_ID]
        weight_kg = call.data.get("weight_kg")
        note = call.data.get("note", "")
        
        _LOGGER.debug("Processing log_health_data service for %s", dog_id)
        
        entry_data = _get_entry_data_for_dog(hass, dog_id)
        if not entry_data:
            raise ServiceValidationError(f"Dog '{dog_id}' not found in any configuration")
        
        data_manager = entry_data["data"]
        
        # Prepare health data
        health_data = {
            "timestamp": datetime.now().isoformat(),
            "weight_kg": weight_kg,
            "note": note.strip() if note else "",
            "logged_by": "service_call",
        }
        
        try:
            await data_manager.async_log_health(dog_id, health_data)
            _LOGGER.info("Logged health data for %s", dog_id)
            
        except Exception as err:
            _LOGGER.error("Failed to log health data for %s: %s", dog_id, err)
            raise ServiceValidationError(f"Failed to log health data: {err}") from err
    
    async def _handle_notify_test_service(call: ServiceCall) -> None:
        """Handle the notify_test service call.
        
        Args:
            call: Service call data
            
        Raises:
            ServiceValidationError: If dog is not found
        """
        dog_id = call.data[ATTR_DOG_ID]
        message = call.data.get("message", "Test notification")
        
        _LOGGER.debug("Processing notify_test service for %s", dog_id)
        
        entry_data = _get_entry_data_for_dog(hass, dog_id)
        if not entry_data:
            raise ServiceValidationError(f"Dog '{dog_id}' not found in any configuration")
        
        notification_manager = entry_data["notifications"]
        
        try:
            await notification_manager.async_send_notification(
                dog_id,
                "🐕 Paw Control Test",
                message,
                priority="normal"
            )
            
            _LOGGER.info("Sent test notification for %s", dog_id)
            
        except Exception as err:
            _LOGGER.error("Failed to send test notification for %s: %s", dog_id, err)
            raise ServiceValidationError(f"Failed to send notification: {err}") from err
    
    async def _handle_daily_reset_service(call: ServiceCall) -> None:
        """Handle the daily_reset service call.
        
        This resets daily statistics for all dogs across all config entries.
        
        Args:
            call: Service call data
        """
        _LOGGER.debug("Processing daily_reset service")
        
        reset_count = 0
        error_count = 0
        
        # Reset daily data for all config entries
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if not isinstance(entry_data, dict) or "data" not in entry_data:
                continue
            
            try:
                data_manager = entry_data["data"]
                await data_manager.async_daily_reset()
                reset_count += 1
                
            except Exception as err:
                _LOGGER.error("Failed to reset daily data for entry %s: %s", entry_id, err)
                error_count += 1
        
        if error_count == 0:
            _LOGGER.info("Daily reset completed successfully for %d entries", reset_count)
        else:
            _LOGGER.warning(
                "Daily reset completed with %d errors out of %d entries",
                error_count,
                reset_count + error_count
            )
    
    # Register all services with their respective schemas
    service_configs = [
        (SERVICE_FEED_DOG, _handle_feed_dog_service, SERVICE_FEED_DOG_SCHEMA),
        (SERVICE_START_WALK, _handle_start_walk_service, SERVICE_WALK_SCHEMA),
        (SERVICE_END_WALK, _handle_end_walk_service, SERVICE_WALK_SCHEMA),
        (SERVICE_LOG_HEALTH, _handle_log_health_data_service, SERVICE_HEALTH_SCHEMA),
        (SERVICE_NOTIFY_TEST, _handle_notify_test_service, SERVICE_NOTIFY_TEST_SCHEMA),
        (SERVICE_DAILY_RESET, _handle_daily_reset_service, None),
    ]
    
    for service_name, handler, schema in service_configs:
        hass.services.async_register(
            DOMAIN,
            service_name,
            handler,
            schema=schema,
        )
    
    _LOGGER.debug("Registered %d Paw Control services", len(service_configs))


async def _async_setup_daily_reset_scheduler(
    hass: HomeAssistant, 
    entry: ConfigEntry
) -> None:
    """Set up the daily reset scheduler.
    
    This scheduler automatically resets daily statistics at the configured
    time each day. Only one scheduler is needed per Home Assistant instance.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry containing reset time configuration
    """
    # Check if scheduler is already set up (avoid multiple schedulers)
    if hasattr(hass.data[DOMAIN], "_daily_reset_scheduled"):
        _LOGGER.debug("Daily reset scheduler already configured")
        return
    
    reset_time_str = entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)
    
    try:
        reset_time_obj = time.fromisoformat(reset_time_str)
    except ValueError:
        _LOGGER.warning(
            "Invalid reset time format '%s', using default %s",
            reset_time_str,
            DEFAULT_RESET_TIME
        )
        reset_time_obj = time.fromisoformat(DEFAULT_RESET_TIME)
    
    @callback
    def _daily_reset_callback(now: datetime) -> None:
        """Callback function for daily reset.
        
        This function is called by Home Assistant's time tracking system
        at the configured reset time each day.
        
        Args:
            now: Current datetime when callback is triggered
        """
        _LOGGER.debug("Triggering daily reset at %s", now)
        
        # Create task to run the daily reset service
        hass.async_create_task(
            hass.services.async_call(DOMAIN, SERVICE_DAILY_RESET, {})
        )
    
    # Schedule the daily reset using Home Assistant's time tracking
    async_track_time_change(
        hass,
        _daily_reset_callback,
        hour=reset_time_obj.hour,
        minute=reset_time_obj.minute,
        second=reset_time_obj.second,
    )
    
    # Mark scheduler as configured
    hass.data[DOMAIN]["_daily_reset_scheduled"] = True
    
    _LOGGER.debug(
        "Daily reset scheduled for %02d:%02d:%02d",
        reset_time_obj.hour,
        reset_time_obj.minute,
        reset_time_obj.second,
    )


def _get_entry_data_for_dog(
    hass: HomeAssistant, 
    dog_id: str
) -> Optional[Dict[str, Any]]:
    """Find the config entry data that contains a specific dog.
    
    This function searches through all Paw Control config entries to find
    which one contains the specified dog ID.
    
    Args:
        hass: Home Assistant instance
        dog_id: Unique identifier of the dog to find
        
    Returns:
        Entry data dictionary containing the dog, or None if not found
    """
    for entry_id, entry_data in hass.data[DOMAIN].items():
        # Skip non-dict entries (like the scheduler flag)
        if not isinstance(entry_data, dict) or "coordinator" not in entry_data:
            continue
        
        coordinator = entry_data["coordinator"]
        if not coordinator:
            continue
        
        # Check if this coordinator's entry contains the dog
        dogs = coordinator.config_entry.data.get(CONF_DOGS, [])
        for dog in dogs:
            if dog.get(CONF_DOG_ID) == dog_id:
                return entry_data
    
    return None
