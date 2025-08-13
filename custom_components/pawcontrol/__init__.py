from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

"""The Paw Control integration for Home Assistant."""

from __future__ import annotations  # noqa: F404

import logging
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from . import coordinator as coordinator_mod
from . import gps_handler as gps
from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
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
from .helpers import notification_router as notification_router_mod
from .helpers import scheduler as scheduler_mod
from .helpers import setup_sync as setup_sync_mod
from .report_generator import ReportGenerator
from .schemas import (
    SERVICE_EMERGENCY_MODE_SCHEMA,
    SERVICE_END_WALK_SCHEMA,
    SERVICE_EXPORT_DATA_SCHEMA,
    SERVICE_FEED_DOG_SCHEMA,
    SERVICE_GENERATE_REPORT_SCHEMA,
    SERVICE_GPS_END_WALK_SCHEMA,
    SERVICE_GPS_EXPORT_LAST_ROUTE_SCHEMA,
    SERVICE_GPS_GENERATE_DIAGNOSTICS_SCHEMA,
    SERVICE_GPS_PAUSE_TRACKING_SCHEMA,
    SERVICE_GPS_POST_LOCATION_SCHEMA,
    SERVICE_GPS_RESET_STATS_SCHEMA,
    SERVICE_GPS_RESUME_TRACKING_SCHEMA,
    SERVICE_GPS_START_WALK_SCHEMA,
    SERVICE_LOG_HEALTH_SCHEMA,
    SERVICE_LOG_MEDICATION_SCHEMA,
    SERVICE_NOTIFY_TEST_SCHEMA,
    SERVICE_PLAY_SESSION_SCHEMA,
    SERVICE_PURGE_ALL_STORAGE_SCHEMA,
    SERVICE_ROUTE_HISTORY_EXPORT_RANGE_SCHEMA,
    SERVICE_ROUTE_HISTORY_LIST_SCHEMA,
    SERVICE_ROUTE_HISTORY_PURGE_SCHEMA,
    SERVICE_START_GROOMING_SCHEMA,
    SERVICE_START_WALK_SCHEMA,
    SERVICE_TOGGLE_GEOFENCE_ALERTS_SCHEMA,
    SERVICE_TOGGLE_VISITOR_SCHEMA,
    SERVICE_TRAINING_SESSION_SCHEMA,
    SERVICE_WALK_DOG_SCHEMA,
)


def _device_id_from_dog(hass, dog_id: str | None) -> str | None:
    if not dog_id:
        return None
    dev_reg = dr.async_get(hass)
    # Search devices by identifiers (DOMAIN, dog_id)
    for dev in dev_reg.devices.values():
        if dev.identifiers and any(
            idt[0] == DOMAIN and idt[1] == dog_id for idt in dev.identifiers
        ):
            return dev.id
    return None


def _dog_id_from_device_id(hass, device_id: str | None) -> str | None:
    if not device_id:
        return None
    dev_reg = dr.async_get(hass)
    dev = dev_reg.async_get(device_id)
    if not dev or not dev.identifiers:
        return None
    for idt in dev.identifiers:
        if idt[0] == DOMAIN:
            return idt[1]
    return None


def _get_known_dog_ids(hass: "HomeAssistant", entry: "ConfigEntry") -> set[str]:
    store = (hass.data.get(DOMAIN) or {}).get(entry.entry_id, {})
    coord = store.get("coordinator")
    dog_ids: set[str] = set()
    if coord and hasattr(coord, "_dog_data"):
        try:
            dog_ids = set(coord._dog_data.keys())
        except Exception:
            dog_ids = set()
    return dog_ids


def _fire_device_event(hass, event: str, dog_id: str | None, **data):
    device_id = _device_id_from_dog(hass, dog_id)
    hass.bus.async_fire(
        f"{DOMAIN}_{event}", {"device_id": device_id, "dog_id": dog_id, **data}
    )


_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: "HomeAssistant", _config: "ConfigType") -> bool:
    """Set up the Paw Control component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup(hass: "HomeAssistant", config: "ConfigType") -> bool:  # noqa: F811
    """Set up the PawControl integration domain and register services."""
    _register_services(hass)
    return True


async def async_setup_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    """Set up Paw Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize coordinator
    coordinator = coordinator_mod.PawControlCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady from err

    # Store coordinator and helpers
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "notification_router": notification_router_mod.NotificationRouter(hass, entry),
        "setup_sync": setup_sync_mod.SetupSync(hass, entry),
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
    await scheduler_mod.setup_schedulers(hass, entry)

    # Initial sync of helpers and entities
    setup_sync_helper = hass.data[DOMAIN][entry.entry_id]["setup_sync"]
    await setup_sync_helper.sync_all()

    # Add update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Auto-prune stale devices (report or remove based on option)
    auto = bool(entry.options.get("auto_prune_devices", False))
    await _auto_prune_devices(hass, entry, auto=auto)
    _check_geofence_options(hass, entry)


return True  # noqa: F706


async def async_unload_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    """Unload a config entry."""
    # Cleanup schedulers
    await scheduler_mod.cleanup_schedulers(hass, entry)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id)

        # Unregister services if no more entries
        if not hass.data[DOMAIN]:
            _unregister_services(hass)

    return unload_ok


async def async_update_options(hass: "HomeAssistant", entry: "ConfigEntry") -> None:
    """Update options."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    setup_sync_helper = hass.data[DOMAIN][entry.entry_id]["setup_sync"]

    # Update coordinator with new options
    coordinator.update_options(entry.options)

    # Resync helpers and entities
    await setup_sync_helper.sync_all()

    # Reschedule tasks with new times
    await scheduler_mod.cleanup_schedulers(hass, entry)
    await scheduler_mod.setup_schedulers(hass, entry)

    # Refresh data
    await coordinator.async_request_refresh()


async def _register_devices(hass: "HomeAssistant", entry: "ConfigEntry") -> None:
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


async def _register_services(
    hass: "HomeAssistant", _entry: "ConfigEntry"
) -> None:
    """Register services for the integration."""

    async def handle_daily_reset(_call: "ServiceCall") -> None:
        """Handle daily reset service."""
        _LOGGER.info("Executing daily reset")
        hass.bus.async_fire(EVENT_DAILY_RESET)

        # Reset all dog counters
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.reset_daily_counters()

    async def handle_sync_setup(_call: "ServiceCall") -> None:
        """Handle setup sync service."""
        _LOGGER.info("Syncing setup")
        for entry_id in hass.data[DOMAIN]:
            setup_sync = hass.data[DOMAIN][entry_id]["setup_sync"]
            await setup_sync.sync_all()

    async def handle_notify_test(call: "ServiceCall") -> None:
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

    async def handle_start_walk(call: "ServiceCall") -> None:
        """Handle start walk service."""
        dog_id = call.data.get("dog_id")
        source = call.data.get("source", "manual")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.start_walk(dog_id, source)

    async def handle_end_walk(call: "ServiceCall") -> None:
        """Handle end walk service."""
        dog_id = call.data.get("dog_id")
        reason = call.data.get("reason", "manual")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.end_walk(dog_id, reason)

    async def handle_walk_dog(call: "ServiceCall") -> None:
        """Handle quick walk log service."""
        dog_id = call.data.get("dog_id")
        duration = call.data.get("duration_min", 30)
        distance = call.data.get("distance_m", 1000)

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_walk(dog_id, duration, distance)

    async def handle_feed_dog(call: "ServiceCall") -> None:
        """Handle feed dog service."""
        dog_id = call.data.get("dog_id")
        meal_type = call.data.get("meal_type", "snack")
        portion_g = call.data.get("portion_g", 100)
        food_type = call.data.get("food_type", "dry")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.feed_dog(dog_id, meal_type, portion_g, food_type)

    async def handle_log_health(call: "ServiceCall") -> None:
        """Handle health data logging service."""
        dog_id = call.data.get("dog_id")
        weight_kg = call.data.get("weight_kg")
        note = call.data.get("note", "")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_health_data(dog_id, weight_kg, note)

    async def handle_log_medication(call: "ServiceCall") -> None:
        """Handle medication logging service."""
        dog_id = call.data.get("dog_id")
        medication_name = call.data.get("medication_name")
        dose = call.data.get("dose")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_medication(dog_id, medication_name, dose)

    async def handle_start_grooming(call: "ServiceCall") -> None:
        """Handle grooming session service."""
        dog_id = call.data.get("dog_id")
        grooming_type = call.data.get("type", "brush")
        notes = call.data.get("notes", "")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.start_grooming(dog_id, grooming_type, notes)

    async def handle_play_session(call: "ServiceCall") -> None:
        """Handle play session service."""
        dog_id = call.data.get("dog_id")
        duration_min = call.data.get("duration_min", 15)
        intensity = call.data.get("intensity", "medium")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_play_session(dog_id, duration_min, intensity)

    async def handle_training_session(call: "ServiceCall") -> None:
        """Handle training session service."""
        dog_id = call.data.get("dog_id")
        topic = call.data.get("topic")
        duration_min = call.data.get("duration_min", 15)
        notes = call.data.get("notes", "")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.log_training(dog_id, topic, duration_min, notes)

    async def handle_toggle_visitor(call: "ServiceCall") -> None:
        """Handle visitor mode toggle service."""
        enabled = call.data.get("enabled")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.set_visitor_mode(enabled)

    async def handle_emergency_mode(call: "ServiceCall") -> None:
        """Handle emergency mode service."""
        level = call.data.get("level", "info")
        note = call.data.get("note", "")

        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.activate_emergency_mode(level, note)

    async def handle_generate_report(call: "ServiceCall") -> None:
        """Handle report generation service."""
        scope = call.data.get("scope", "daily")
        target = call.data.get("target", "notification")
        format_type = call.data.get("format", "text")

        for entry_id in hass.data[DOMAIN]:
            report_generator = hass.data[DOMAIN][entry_id]["report_generator"]
            await report_generator.generate_report(scope, target, format_type)

    async def handle_export_data(call: "ServiceCall") -> None:
        """Handle data export service."""
        dog_id = call.data.get("dog_id")
        date_from = call.data.get("from")
        date_to = call.data.get("to")
        format_type = call.data.get("format", "csv")

        for entry_id in hass.data[DOMAIN]:
            report_generator = hass.data[DOMAIN][entry_id]["report_generator"]
            await report_generator.export_health_data(
                dog_id, date_from, date_to, format_type
            )

    # Register all services with schema validation
    hass.services.async_register(DOMAIN, SERVICE_DAILY_RESET, handle_daily_reset)

    hass.services.async_register(DOMAIN, SERVICE_SYNC_SETUP, handle_sync_setup)

    hass.services.async_register(
        DOMAIN,
        SERVICE_NOTIFY_TEST,
        handle_notify_test,
        schema=SERVICE_NOTIFY_TEST_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN, SERVICE_START_WALK, handle_start_walk, schema=SERVICE_START_WALK_SCHEMA
    )

    hass.services.async_register(
        DOMAIN, SERVICE_END_WALK, handle_end_walk, schema=SERVICE_END_WALK_SCHEMA
    )

    hass.services.async_register(
        DOMAIN, SERVICE_WALK_DOG, handle_walk_dog, schema=SERVICE_WALK_DOG_SCHEMA
    )

    hass.services.async_register(
        DOMAIN, SERVICE_FEED_DOG, handle_feed_dog, schema=SERVICE_FEED_DOG_SCHEMA
    )

    hass.services.async_register(
        DOMAIN, SERVICE_LOG_HEALTH, handle_log_health, schema=SERVICE_LOG_HEALTH_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_MEDICATION,
        handle_log_medication,
        schema=SERVICE_LOG_MEDICATION_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_GROOMING,
        handle_start_grooming,
        schema=SERVICE_START_GROOMING_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_PLAY_WITH_DOG,
        handle_play_session,
        schema=SERVICE_PLAY_SESSION_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_TRAINING,
        handle_training_session,
        schema=SERVICE_TRAINING_SESSION_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_TOGGLE_VISITOR,
        handle_toggle_visitor,
        schema=SERVICE_TOGGLE_VISITOR_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_EMERGENCY_MODE,
        handle_emergency_mode,
        schema=SERVICE_EMERGENCY_MODE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_REPORT,
        handle_generate_report,
        schema=SERVICE_GENERATE_REPORT_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT_DATA,
        handle_export_data,
        schema=SERVICE_EXPORT_DATA_SCHEMA,
    )


async def handle_gps_start_walk(call: "ServiceCall") -> None:
    dog_id = call.data.get("dog_id")
    await gps.async_start_walk(call)
    _fire_device_event(hass, "walk_started", dog_id)  # noqa: F821


async def handle_gps_end_walk(call: "ServiceCall") -> None:
    dog_id = call.data.get("dog_id")
    await gps.async_end_walk(call)
    _fire_device_event(hass, "walk_ended", dog_id)  # noqa: F821


async def handle_gps_post_location(call: "ServiceCall") -> None:
    dog_id = call.data.get("dog_id")
    await gps.async_update_location(call)
    _fire_device_event(hass, "gps_location_posted", dog_id)  # noqa: F821


async def handle_prune_stale_devices(call: "ServiceCall") -> None:
    """Prune stale devices, optionally auto=True."""
    _entry = _get_valid_entry_from_call(hass, call)  # noqa: F821
    if _entry is None:
        raise HomeAssistantError("No loaded config entry found")
    auto = bool(call.data.get("auto", True))
    await _auto_prune_devices(hass, _entry, auto=auto)  # noqa: F821
    # GPS services
    hass.services.async_register(DOMAIN, SERVICE_GPS_START_WALK, handle_gps_start_walk)  # noqa: F821
    store["unsub"].append(  # noqa: F821
        lambda: hass.services.async_remove(DOMAIN, SERVICE_GPS_START_WALK)  # noqa: F821
    )
    entry.async_on_unload(  # noqa: F821
        lambda: hass.services.async_remove(DOMAIN, SERVICE_GPS_START_WALK)  # noqa: F821
    )
    hass.services.async_register(DOMAIN, SERVICE_GPS_END_WALK, handle_gps_end_walk)  # noqa: F821
    store["unsub"].append(  # noqa: F821
        lambda: hass.services.async_remove(DOMAIN, SERVICE_GPS_END_WALK)  # noqa: F821
    )
    entry.async_on_unload(  # noqa: F821
        lambda: hass.services.async_remove(DOMAIN, SERVICE_GPS_END_WALK)  # noqa: F821
    )
    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_GPS_POST_LOCATION, handle_gps_post_location  # noqa: F821
    )
    store["unsub"].append(  # noqa: F821
        lambda: hass.services.async_remove(DOMAIN, SERVICE_GPS_POST_LOCATION)  # noqa: F821
    )
    entry.async_on_unload(  # noqa: F821
        lambda: hass.services.async_remove(DOMAIN, SERVICE_GPS_POST_LOCATION)  # noqa: F821
    )
    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_GPS_PAUSE_TRACKING, gps.async_pause_tracking  # noqa: F821
    )
    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_GPS_RESUME_TRACKING, gps.async_resume_tracking  # noqa: F821
    )
    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_GPS_EXPORT_LAST_ROUTE, gps.async_export_last_route  # noqa: F821
    )
    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_GPS_GENERATE_DIAGNOSTICS, gps.async_generate_diagnostics  # noqa: F821
    )
    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_GPS_RESET_STATS, gps.async_reset_gps_stats  # noqa: F821
    )

    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_ROUTE_HISTORY_LIST, handle_route_history_list  # noqa: F821
    )
    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_ROUTE_HISTORY_PURGE, handle_route_history_purge  # noqa: F821
    )
    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_ROUTE_HISTORY_EXPORT_RANGE, handle_route_history_export_range  # noqa: F821
    )

    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_TOGGLE_GEOFENCE_ALERTS, handle_toggle_geofence_alerts  # noqa: F821
    )
    store["unsub"].append(  # noqa: F821
        lambda: hass.services.async_remove(DOMAIN, SERVICE_TOGGLE_GEOFENCE_ALERTS)  # noqa: F821
    )
    entry.async_on_unload(  # noqa: F821
        lambda: hass.services.async_remove(DOMAIN, SERVICE_TOGGLE_GEOFENCE_ALERTS)  # noqa: F821
    )

    hass.services.async_register(  # noqa: F821
        DOMAIN, SERVICE_PURGE_ALL_STORAGE, handle_purge_all_storage  # noqa: F821
    )


def _get_valid_entry_from_call(
    hass: "HomeAssistant", call: "ServiceCall"
) -> "ConfigEntry | None":
    """Resolve and validate a config entry for a service call.
    Prefers call.data['config_entry_id'] when provided.
    Raises ServiceValidationError if specified entry is not found/loaded.
    Returns first loaded entry if nothing specified and any exist.
    """
    entry_id: str | None = call.data.get("config_entry_id")
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_found"
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_loaded"
            )
        return entry
    # Fallback: pick first LOADED entry if present
    for e in hass.config_entries.async_entries(DOMAIN):
        if e.state is ConfigEntryState.LOADED:
            return e
    # None found
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="no_entries"
    )


def _unregister_services(hass: "HomeAssistant") -> None:
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


async def async_remove_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> None:
    """Handle removal of a config entry."""
    try:
        await async_unload_entry(hass, entry)
    except Exception:  # pragma: no cover - best effort
        pass
    # Remove entry data
    domain_data = hass.data.get(DOMAIN, {})
    if entry.entry_id in domain_data:
        domain_data.pop(entry.entry_id, None)
    # If domain empty, unregister services
    if not domain_data:
        _unregister_services(hass)


async def handle_route_history_list(hass: "HomeAssistant", call: "ServiceCall") -> None:
    _get_valid_entry_from_call(hass, call)
    """List route history for a dog."""
    from .route_store import RouteHistoryStore

    entry_id = next(iter(hass.data.get(DOMAIN, {})), None)
    if entry_id is None:
        raise HomeAssistantError("No Paw Control entry found for service call")
    dog_id = call.data.get("dog_id")
    store = RouteHistoryStore(hass, entry_id, DOMAIN)
    data = await store.async_list(dog_id=dog_id)
    hass.bus.async_fire(
        f"{DOMAIN}_route_history_listed", {"dog_id": dog_id, "result": data}
    )


async def handle_route_history_purge(
    hass: "HomeAssistant", call: "ServiceCall"
) -> None:
    _get_valid_entry_from_call(hass, call)
    """Purge route history (optionally for a specific dog)."""
    from .route_store import RouteHistoryStore

    entry_id = next(iter(hass.data.get(DOMAIN, {})), None)
    if entry_id is None:
        raise HomeAssistantError("No Paw Control entry found for service call")
    dog_id = call.data.get("dog_id")
    store = RouteHistoryStore(hass, entry_id, DOMAIN)
    await store.async_purge(dog_id=dog_id)


async def handle_route_history_export_range(
    hass: "HomeAssistant", call: "ServiceCall"
) -> None:
    _get_valid_entry_from_call(hass, call)
    """Export route history within date range to .storage."""
    from homeassistant.util import dt as dt_util

    from .route_store import RouteHistoryStore

    entry_id = next(iter(hass.data.get(DOMAIN, {})), None)
    if entry_id is None:
        raise HomeAssistantError("No Paw Control entry found for service call")
    dog_id = call.data.get("dog_id")
    date_from = call.data.get("date_from")
    date_to = call.data.get("date_to")
    # Parse dates (YYYY-MM-DD)
    try:
        df = dt_util.parse_date(date_from) if isinstance(date_from, str) else date_from
        dt = dt_util.parse_date(date_to) if isinstance(date_to, str) else date_to
    except Exception:
        df = dt = None
    store = RouteHistoryStore(hass, entry_id, DOMAIN)
    data = await store.async_list(dog_id=dog_id)

    def in_range(item):
        ts = item.get("start_time") or item.get("timestamp")
        try:
            t = dt_util.parse_datetime(ts)
        except Exception:
            return False
        if df and t.date() < df:
            return False
        if dt and t.date() > dt:
            return False
        return True

    filtered = [x for x in data if in_range(x)]
    # Save to .storage export file
    from homeassistant.helpers.storage import Store

    export_name = f"{DOMAIN}_{entry_id}_route_export"
    store_out = Store(hass, 1, export_name)
    await store_out.async_save(
        {
            "dog_id": dog_id,
            "from": str(date_from),
            "to": str(date_to),
            "items": filtered,
        }
    )
    hass.bus.async_fire(
        f"{DOMAIN}_route_history_exported", {"dog_id": dog_id, "count": len(filtered)}
    )


async def handle_toggle_geofence_alerts(
    hass: "HomeAssistant", call: "ServiceCall"
) -> None:
    _get_valid_entry_from_call(hass, call)
    """Toggle geofence alerts flag in GPS settings."""
    from .gps_settings import GPSSettingsStore

    entry_id = next(iter(hass.data.get(DOMAIN, {})), None)
    if entry_id is None:
        raise HomeAssistantError("No Paw Control entry found for service call")
    enabled = bool(call.data.get("enabled", True))
    store = GPSSettingsStore(hass, entry_id, DOMAIN)
    data = await store.async_load()
    data.setdefault("geofence", {})["alerts_enabled"] = enabled
    await store.async_save(data)


async def handle_purge_all_storage(hass: "HomeAssistant", call: "ServiceCall") -> None:
    _get_valid_entry_from_call(hass, call)
    """Purge all Paw Control storage (route history, gps settings)."""
    from .gps_settings import GPSSettingsStore
    from .route_store import RouteHistoryStore

    entry_id = next(iter(hass.data.get(DOMAIN, {})), None)
    if entry_id is None:
        raise HomeAssistantError("No Paw Control entry found for service call")
    # Route history -> purge all
    store = RouteHistoryStore(hass, entry_id, DOMAIN)
    await store.async_purge(dog_id=None)
    # GPS settings -> clear
    gstore = GPSSettingsStore(hass, entry_id, DOMAIN)
    await gstore.async_save({})


async def async_remove_config_entry_device(
    hass: "HomeAssistant", entry: "ConfigEntry", device: "dr.DeviceEntry"
) -> bool:
    """Allow removing a device from the device registry.
    We allow removal if the device belongs to this config entry / domain.
    Perform any internal cleanup for the dog_id if present.
    """
    try:
        from homeassistant.helpers import device_registry as dr
    except Exception:
        return False
    # Only allow removal for devices with our DOMAIN identifier
    dog_id = None
    if device.identifiers:
        for idt in device.identifiers:
            if idt[0] == DOMAIN:
                dog_id = idt[1]
                break
    if not dog_id:
        # Not our device
        return False
    # Cleanup internal caches/state if present
    store = (hass.data.get(DOMAIN) or {}).get(entry.entry_id, {})
    coord = store.get("coordinator")
    if coord and hasattr(coord, "_dog_data"):
        coord._dog_data.pop(dog_id, None)
    # If we maintain any listeners per dog, remove them here too
    listeners = store.get("listeners") or {}
    lst = listeners.pop(dog_id, None)
    try:
        if lst:
            for unsub in lst:
                unsub()
    except Exception:
        pass
    # Allow the registry to delete the device
    return True


async def _auto_prune_devices(
    hass: "HomeAssistant", entry: "ConfigEntry", *, auto: bool
) -> int:
    """Remove or report stale devices that are no longer known by the coordinator.
    Returns number of stale devices found (and removed if auto=True).
    """
    dev_reg = dr.async_get(hass)
    known = _get_known_dog_ids(hass, entry)
    stale_devices: list[dr.DeviceEntry] = []
    for dev in list(dev_reg.devices.values()):
        if entry.entry_id not in dev.config_entries:
            continue
        dog_id = None
        if dev.identifiers:
            for idt in dev.identifiers:
                if idt[0] == DOMAIN:
                    dog_id = idt[1]
                    break
        if not dog_id:
            continue
        if dog_id not in known:
            stale_devices.append(dev)

    if not stale_devices:
        ir.async_delete_issue(hass, DOMAIN, "stale_devices")
        return 0

    if auto:
        removed = 0
        for dev in stale_devices:
            if dev.config_entries == {entry.entry_id}:
                dev_reg.async_remove_device(dev.id)
                removed += 1
        ir.async_delete_issue(hass, DOMAIN, "stale_devices")
        return removed

    try:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "stale_devices",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="stale_devices",
            translation_placeholders={"count": str(len(stale_devices))},
            learn_more_url="https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/stale-devices/",
        )
    except Exception:
        pass
    return len(stale_devices)


def _check_geofence_options(hass: "HomeAssistant", entry: "ConfigEntry") -> None:
    """Create a Repairs issue if geofence settings look invalid."""
    opts = entry.options or {}
    radius = opts.get("geofence_radius_m")
    lat = opts.get("home_lat")
    lon = opts.get("home_lon")
    invalid = False
    if radius is not None and (not isinstance(radius, (int, float)) or radius <= 0):
        invalid = True
    if (lat is None) != (lon is None):
        invalid = True
    if invalid:
        try:
            ir.async_create_issue(
                hass,
                DOMAIN,
                "invalid_geofence",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="invalid_geofence",
                translation_placeholders={},
                learn_more_url="https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/repair-issues/",
            )
        except Exception:
            pass
    else:
        ir.async_delete_issue(hass, DOMAIN, "invalid_geofence")
