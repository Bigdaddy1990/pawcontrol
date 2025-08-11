"""The Paw Control integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    EVENT_DAILY_RESET,
    PLATFORMS,
    SERVICE_DAILY_RESET,
    SERVICE_EMERGENCY_MODE,
    SERVICE_END_WALK,
    SERVICE_EXPORT_DATA,
    SERVICE_FEED_DOG,
    SERVICE_GENERATE_REPORT,
    SERVICE_LOG_HEALTH,
    SERVICE_LOG_MEDICATION,
    SERVICE_NOTIFY_TEST,
    SERVICE_PLAY_WITH_DOG,
    SERVICE_START_GROOMING,
    SERVICE_START_TRAINING,
    SERVICE_START_WALK,
    SERVICE_SYNC_SETUP,
    SERVICE_TOGGLE_VISITOR,
    SERVICE_WALK_DOG,
)
from .coordinator import PawControlCoordinator
from .helpers.notification_router import NotificationRouter
from .helpers.scheduler import cleanup_schedulers, setup_schedulers
from .helpers.setup_sync import SetupSync
from .report_generator import ReportGenerator
from .schemas import (
    SERVICE_EMERGENCY_MODE_SCHEMA,
    SERVICE_END_WALK_SCHEMA,
    SERVICE_EXPORT_DATA_SCHEMA,
    SERVICE_FEED_DOG_SCHEMA,
    SERVICE_GENERATE_REPORT_SCHEMA,
    SERVICE_LOG_HEALTH_SCHEMA,
    SERVICE_LOG_MEDICATION_SCHEMA,
    SERVICE_NOTIFY_TEST_SCHEMA,
    SERVICE_PLAY_SESSION_SCHEMA,
    SERVICE_START_GROOMING_SCHEMA,
    SERVICE_START_WALK_SCHEMA,
    SERVICE_TOGGLE_VISITOR_SCHEMA,
    SERVICE_TRAINING_SESSION_SCHEMA,
    SERVICE_WALK_DOG_SCHEMA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the Paw Control component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Paw Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize coordinator
    coordinator = PawControlCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady from err

    # Store coordinator and helpers
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "notification_router": NotificationRouter(hass, entry),
        "setup_sync": SetupSync(hass, entry),
    }

    # Report generator depends on the coordinator being stored above, so
    # instantiate it only after the shared data structure has been created.
    hass.data[DOMAIN][entry.entry_id]["report_generator"] = ReportGenerator(hass, entry)
    
    # Register devices for each dog
    await _register_devices(hass, entry)
    
    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await _register_services(hass, entry)
    
    # Setup schedulers (daily reset, reports, reminders)
    await setup_schedulers(hass, entry)
    
    # Initial sync of helpers and entities
    setup_sync_helper = hass.data[DOMAIN][entry.entry_id]["setup_sync"]
    await setup_sync_helper.sync_all()
    
    # Add update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Cleanup schedulers
    await cleanup_schedulers(hass, entry)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Unregister services if no more entries
        if not hass.data[DOMAIN]:
            _unregister_services(hass)
    
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    setup_sync_helper = hass.data[DOMAIN][entry.entry_id]["setup_sync"]

    # Update coordinator with new options
    coordinator.update_options(entry.options)

    # Resync helpers and entities
    await setup_sync_helper.sync_all()

    # Reschedule tasks with new times
    await cleanup_schedulers(hass, entry)
    await setup_schedulers(hass, entry)

    # Refresh data
    await coordinator.async_request_refresh()


async def _register_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register devices for each dog."""
    device_registry = dr.async_get(hass)
    
    dogs = entry.options.get(CONF_DOGS, [])
    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, dog_id)},
            name=f"🐕 {dog_name}",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )


async def _register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register services for the integration."""
    
    async def handle_daily_reset(call: ServiceCall) -> None:
        """Handle daily reset service."""
        _LOGGER.info("Executing daily reset")
        hass.bus.async_fire(EVENT_DAILY_RESET)
        
        # Reset all dog counters
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.reset_daily_counters()
    
    async def handle_sync_setup(call: ServiceCall) -> None:
        """Handle setup sync service."""
        _LOGGER.info("Syncing setup")
        for entry_id in hass.data[DOMAIN]:
            setup_sync = hass.data[DOMAIN][entry_id]["setup_sync"]
            await setup_sync.sync_all()
    
    async def handle_notify_test(call: ServiceCall) -> None:
        """Handle notification test service."""
        dog_id = call.data.get("dog_id")
        message = call.data.get("message", f"Test notification for {dog_id}")
        
        for entry_id in hass.data[DOMAIN]:
            router = hass.data[DOMAIN][entry_id]["notification_router"]
            await router.send_notification(
                title="Paw Control Test",
                message=message,
                dog_id=dog_id,
            )
    
    async def handle_start_walk(call: ServiceCall) -> None:
        """Handle start walk service."""
        dog_id = call.data.get("dog_id")
        source = call.data.get("source", "manual")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.start_walk(dog_id, source)
    
    async def handle_end_walk(call: ServiceCall) -> None:
        """Handle end walk service."""
        dog_id = call.data.get("dog_id")
        reason = call.data.get("reason", "manual")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.end_walk(dog_id, reason)
    
    async def handle_walk_dog(call: ServiceCall) -> None:
        """Handle quick walk log service."""
        dog_id = call.data.get("dog_id")
        duration = call.data.get("duration_min", 30)
        distance = call.data.get("distance_m", 1000)
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_walk(dog_id, duration, distance)
    
    async def handle_feed_dog(call: ServiceCall) -> None:
        """Handle feed dog service."""
        dog_id = call.data.get("dog_id")
        meal_type = call.data.get("meal_type", "snack")
        portion_g = call.data.get("portion_g", 100)
        food_type = call.data.get("food_type", "dry")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.feed_dog(dog_id, meal_type, portion_g, food_type)
    
    async def handle_log_health(call: ServiceCall) -> None:
        """Handle health data logging service."""
        dog_id = call.data.get("dog_id")
        weight_kg = call.data.get("weight_kg")
        note = call.data.get("note", "")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_health_data(dog_id, weight_kg, note)
    
    async def handle_log_medication(call: ServiceCall) -> None:
        """Handle medication logging service."""
        dog_id = call.data.get("dog_id")
        medication_name = call.data.get("medication_name")
        dose = call.data.get("dose")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_medication(dog_id, medication_name, dose)
    
    async def handle_start_grooming(call: ServiceCall) -> None:
        """Handle grooming session service."""
        dog_id = call.data.get("dog_id")
        grooming_type = call.data.get("type", "brush")
        notes = call.data.get("notes", "")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.start_grooming(dog_id, grooming_type, notes)
    
    async def handle_play_session(call: ServiceCall) -> None:
        """Handle play session service."""
        dog_id = call.data.get("dog_id")
        duration_min = call.data.get("duration_min", 15)
        intensity = call.data.get("intensity", "medium")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_play_session(dog_id, duration_min, intensity)
    
    async def handle_training_session(call: ServiceCall) -> None:
        """Handle training session service."""
        dog_id = call.data.get("dog_id")
        topic = call.data.get("topic")
        duration_min = call.data.get("duration_min", 15)
        notes = call.data.get("notes", "")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_training(dog_id, topic, duration_min, notes)
    
    async def handle_toggle_visitor(call: ServiceCall) -> None:
        """Handle visitor mode toggle service."""
        enabled = call.data.get("enabled")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.set_visitor_mode(enabled)
    
    async def handle_emergency_mode(call: ServiceCall) -> None:
        """Handle emergency mode service."""
        level = call.data.get("level", "info")
        note = call.data.get("note", "")
        
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.activate_emergency_mode(level, note)
    
    async def handle_generate_report(call: ServiceCall) -> None:
        """Handle report generation service."""
        scope = call.data.get("scope", "daily")
        target = call.data.get("target", "notification")
        format_type = call.data.get("format", "text")
        
        for entry_id in hass.data[DOMAIN]:
            report_generator = hass.data[DOMAIN][entry_id]["report_generator"]
            await report_generator.generate_report(scope, target, format_type)
    
    async def handle_export_data(call: ServiceCall) -> None:
        """Handle data export service."""
        dog_id = call.data.get("dog_id")
        date_from = call.data.get("from")
        date_to = call.data.get("to")
        format_type = call.data.get("format", "csv")
        
        for entry_id in hass.data[DOMAIN]:
            report_generator = hass.data[DOMAIN][entry_id]["report_generator"]
            await report_generator.export_health_data(dog_id, date_from, date_to, format_type)
    
    # Register all services with schema validation
    hass.services.async_register(
        DOMAIN, SERVICE_DAILY_RESET, handle_daily_reset
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_SYNC_SETUP, handle_sync_setup
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_NOTIFY_TEST, 
        handle_notify_test,
        schema=SERVICE_NOTIFY_TEST_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_START_WALK, 
        handle_start_walk,
        schema=SERVICE_START_WALK_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_END_WALK, 
        handle_end_walk,
        schema=SERVICE_END_WALK_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_WALK_DOG, 
        handle_walk_dog,
        schema=SERVICE_WALK_DOG_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_FEED_DOG, 
        handle_feed_dog,
        schema=SERVICE_FEED_DOG_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_LOG_HEALTH, 
        handle_log_health,
        schema=SERVICE_LOG_HEALTH_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_LOG_MEDICATION, 
        handle_log_medication,
        schema=SERVICE_LOG_MEDICATION_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_START_GROOMING, 
        handle_start_grooming,
        schema=SERVICE_START_GROOMING_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_PLAY_WITH_DOG, 
        handle_play_session,
        schema=SERVICE_PLAY_SESSION_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_START_TRAINING, 
        handle_training_session,
        schema=SERVICE_TRAINING_SESSION_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_TOGGLE_VISITOR, 
        handle_toggle_visitor,
        schema=SERVICE_TOGGLE_VISITOR_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_EMERGENCY_MODE, 
        handle_emergency_mode,
        schema=SERVICE_EMERGENCY_MODE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_GENERATE_REPORT, 
        handle_generate_report,
        schema=SERVICE_GENERATE_REPORT_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, 
        SERVICE_EXPORT_DATA, 
        handle_export_data,
        schema=SERVICE_EXPORT_DATA_SCHEMA
    )


def _unregister_services(hass: HomeAssistant) -> None:
    """Unregister all services."""
    services = [
        SERVICE_DAILY_RESET,
        SERVICE_SYNC_SETUP,
        SERVICE_NOTIFY_TEST,
        SERVICE_START_WALK,
        SERVICE_END_WALK,
        SERVICE_WALK_DOG,
        SERVICE_FEED_DOG,
        SERVICE_LOG_HEALTH,
        SERVICE_LOG_MEDICATION,
        SERVICE_START_GROOMING,
        SERVICE_PLAY_WITH_DOG,
        SERVICE_START_TRAINING,
        SERVICE_TOGGLE_VISITOR,
        SERVICE_EMERGENCY_MODE,
        SERVICE_GENERATE_REPORT,
        SERVICE_EXPORT_DATA,
    ]
    
    for service in services:
        hass.services.async_remove(DOMAIN, service)
