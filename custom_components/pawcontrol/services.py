"""Service handlers for PawControl integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    EVENT_DAILY_RESET,
    SERVICE_DAILY_RESET,
    SERVICE_EMERGENCY_MODE,
    SERVICE_END_WALK,
    SERVICE_EXPORT_DATA,
    SERVICE_FEED_DOG,
    SERVICE_GENERATE_REPORT,
    SERVICE_GPS_END_WALK,
    SERVICE_GPS_EXPORT_LAST_ROUTE,
    SERVICE_GPS_GENERATE_DIAGNOSTICS,
    SERVICE_GPS_PAUSE_TRACKING,
    SERVICE_GPS_POST_LOCATION,
    SERVICE_GPS_RESET_STATS,
    SERVICE_GPS_RESUME_TRACKING,
    SERVICE_GPS_START_WALK,
    SERVICE_LOG_HEALTH,
    SERVICE_LOG_MEDICATION,
    SERVICE_NOTIFY_TEST,
    SERVICE_PLAY_WITH_DOG,
    SERVICE_PRUNE_STALE_DEVICES,
    SERVICE_PURGE_ALL_STORAGE,
    SERVICE_ROUTE_HISTORY_EXPORT_RANGE,
    SERVICE_ROUTE_HISTORY_LIST,
    SERVICE_ROUTE_HISTORY_PURGE,
    SERVICE_START_GROOMING,
    SERVICE_START_TRAINING,
    SERVICE_START_WALK,
    SERVICE_SYNC_SETUP,
    SERVICE_TOGGLE_GEOFENCE_ALERTS,
    SERVICE_TOGGLE_VISITOR,
    SERVICE_WALK_DOG,
)
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
    SERVICE_PRUNE_STALE_DEVICES_SCHEMA,
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

if TYPE_CHECKING:
    from collections.abc import Callable


_LOGGER: Final = logging.getLogger(__name__)


class ServiceManager:
    """Manage services for PawControl integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize service manager."""
        self.hass = hass
        self.entry = entry
        self._unsubscribers: list[Callable[[], None]] = []

    async def async_register_services(self) -> None:
        """Register all services for this entry."""
        # Only register if this is the first loaded entry
        if not self._should_register_services():
            return

        # Register all services with schemas
        services = {
            SERVICE_DAILY_RESET: (self._handle_daily_reset, None),
            SERVICE_SYNC_SETUP: (self._handle_sync_setup, None),
            SERVICE_NOTIFY_TEST: (self._handle_notify_test, SERVICE_NOTIFY_TEST_SCHEMA),
            SERVICE_START_WALK: (self._handle_start_walk, SERVICE_START_WALK_SCHEMA),
            SERVICE_END_WALK: (self._handle_end_walk, SERVICE_END_WALK_SCHEMA),
            SERVICE_WALK_DOG: (self._handle_walk_dog, SERVICE_WALK_DOG_SCHEMA),
            SERVICE_FEED_DOG: (self._handle_feed_dog, SERVICE_FEED_DOG_SCHEMA),
            SERVICE_LOG_HEALTH: (self._handle_log_health, SERVICE_LOG_HEALTH_SCHEMA),
            SERVICE_LOG_MEDICATION: (
                self._handle_log_medication,
                SERVICE_LOG_MEDICATION_SCHEMA,
            ),
            SERVICE_START_GROOMING: (
                self._handle_start_grooming,
                SERVICE_START_GROOMING_SCHEMA,
            ),
            SERVICE_PLAY_WITH_DOG: (
                self._handle_play_session,
                SERVICE_PLAY_SESSION_SCHEMA,
            ),
            SERVICE_START_TRAINING: (
                self._handle_training_session,
                SERVICE_TRAINING_SESSION_SCHEMA,
            ),
            SERVICE_TOGGLE_VISITOR: (
                self._handle_toggle_visitor,
                SERVICE_TOGGLE_VISITOR_SCHEMA,
            ),
            SERVICE_EMERGENCY_MODE: (
                self._handle_emergency_mode,
                SERVICE_EMERGENCY_MODE_SCHEMA,
            ),
            SERVICE_GENERATE_REPORT: (
                self._handle_generate_report,
                SERVICE_GENERATE_REPORT_SCHEMA,
            ),
            SERVICE_EXPORT_DATA: (
                self._handle_export_data,
                SERVICE_EXPORT_DATA_SCHEMA,
            ),
            SERVICE_GPS_START_WALK: (
                self._handle_gps_start_walk,
                SERVICE_GPS_START_WALK_SCHEMA,
            ),
            SERVICE_GPS_END_WALK: (
                self._handle_gps_end_walk,
                SERVICE_GPS_END_WALK_SCHEMA,
            ),
            SERVICE_GPS_POST_LOCATION: (
                self._handle_gps_post_location,
                SERVICE_GPS_POST_LOCATION_SCHEMA,
            ),
            SERVICE_GPS_PAUSE_TRACKING: (
                self._handle_gps_pause_tracking,
                SERVICE_GPS_PAUSE_TRACKING_SCHEMA,
            ),
            SERVICE_GPS_RESUME_TRACKING: (
                self._handle_gps_resume_tracking,
                SERVICE_GPS_RESUME_TRACKING_SCHEMA,
            ),
            SERVICE_GPS_EXPORT_LAST_ROUTE: (
                self._handle_gps_export_last_route,
                SERVICE_GPS_EXPORT_LAST_ROUTE_SCHEMA,
            ),
            SERVICE_GPS_GENERATE_DIAGNOSTICS: (
                self._handle_gps_generate_diagnostics,
                SERVICE_GPS_GENERATE_DIAGNOSTICS_SCHEMA,
            ),
            SERVICE_GPS_RESET_STATS: (
                self._handle_gps_reset_stats,
                SERVICE_GPS_RESET_STATS_SCHEMA,
            ),
            SERVICE_ROUTE_HISTORY_LIST: (
                self._handle_route_history_list,
                SERVICE_ROUTE_HISTORY_LIST_SCHEMA,
            ),
            SERVICE_ROUTE_HISTORY_PURGE: (
                self._handle_route_history_purge,
                SERVICE_ROUTE_HISTORY_PURGE_SCHEMA,
            ),
            SERVICE_ROUTE_HISTORY_EXPORT_RANGE: (
                self._handle_route_history_export_range,
                SERVICE_ROUTE_HISTORY_EXPORT_RANGE_SCHEMA,
            ),
            SERVICE_TOGGLE_GEOFENCE_ALERTS: (
                self._handle_toggle_geofence_alerts,
                SERVICE_TOGGLE_GEOFENCE_ALERTS_SCHEMA,
            ),
            SERVICE_PRUNE_STALE_DEVICES: (
                self._handle_prune_stale_devices,
                SERVICE_PRUNE_STALE_DEVICES_SCHEMA,
            ),
            SERVICE_PURGE_ALL_STORAGE: (
                self._handle_purge_all_storage,
                SERVICE_PURGE_ALL_STORAGE_SCHEMA,
            ),
        }

        for service_name, (handler, schema) in services.items():
            if self.hass.services.has_service(DOMAIN, service_name):
                self.hass.services.async_remove(DOMAIN, service_name)
            self.hass.services.async_register(
                DOMAIN, service_name, handler, schema=schema
            )
            self._unsubscribers.append(
                lambda svc=service_name: self.hass.services.async_remove(DOMAIN, svc)
            )

    async def async_unregister_services(self) -> None:
        """Unregister all services."""
        for unsub in self._unsubscribers:
            try:
                unsub()
            except Exception:
                _LOGGER.exception("Error unregistering service")
        self._unsubscribers.clear()

    def _should_register_services(self) -> bool:
        """Check if services should be registered."""
        # Only register if this is the first loaded entry
        return not any(
            entry.entry_id != self.entry.entry_id
            and entry.state is ConfigEntryState.LOADED
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )

    def _get_entry_from_call(self, call: ServiceCall) -> ConfigEntry:
        """Get the config entry from a service call."""
        entry_id = call.data.get("config_entry_id")

        if entry_id:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if not entry:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="entry_not_found",
                )
            if entry.state != ConfigEntryState.LOADED:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="entry_not_loaded",
                )
            return entry

        return self.entry

    def _get_coordinator(self, call: ServiceCall):
        """Get coordinator from service call."""
        entry = self._get_entry_from_call(call)
        return entry.runtime_data.coordinator

    async def _handle_daily_reset(self, call: ServiceCall) -> None:
        """Handle daily reset service."""
        coordinator = self._get_coordinator(call)
        _LOGGER.info("Executing daily reset")
        self.hass.bus.async_fire(EVENT_DAILY_RESET)
        await coordinator.reset_daily_counters()

    async def _handle_sync_setup(self, call: ServiceCall) -> None:
        """Handle setup sync service."""
        entry = self._get_entry_from_call(call)
        setup_sync = entry.runtime_data.setup_sync
        _LOGGER.info("Syncing setup")
        await setup_sync.sync_all()

    async def _handle_notify_test(self, call: ServiceCall) -> None:
        """Handle notification test service."""
        entry = self._get_entry_from_call(call)
        dog_id = call.data.get("dog_id")
        message = call.data.get("message", f"Test notification for {dog_id}")

        router = entry.runtime_data.notification_router
        await router.send_notification(
            title="Paw Control Test", message=message, dog_id=dog_id
        )

    async def _handle_start_walk(self, call: ServiceCall) -> None:
        """Handle start walk service."""
        coordinator = self._get_coordinator(call)
        dog_id = call.data.get("dog_id")
        source = call.data.get("source", "manual")

        await coordinator.start_walk(dog_id, source)
        self._fire_device_event("walk_started", dog_id)

    async def _handle_end_walk(self, call: ServiceCall) -> None:
        """Handle end walk service."""
        coordinator = self._get_coordinator(call)
        dog_id = call.data.get("dog_id")
        reason = call.data.get("reason", "manual")

        await coordinator.end_walk(dog_id, reason)
        self._fire_device_event("walk_ended", dog_id)

    async def _handle_walk_dog(self, call: ServiceCall) -> None:
        """Handle quick walk log service."""
        coordinator = self._get_coordinator(call)
        dog_id = call.data.get("dog_id")
        duration = call.data.get("duration_min", 30)
        distance = call.data.get("distance_m", 1000)

        await coordinator.log_walk(dog_id, duration, distance)

    async def _handle_feed_dog(self, call: ServiceCall) -> None:
        """Handle feed dog service."""
        coordinator = self._get_coordinator(call)
        dog_id = call.data.get("dog_id")
        meal_type = call.data.get("meal_type", "snack")
        portion_g = call.data.get("portion_g", 100)
        food_type = call.data.get("food_type", "dry")

        await coordinator.feed_dog(dog_id, meal_type, portion_g, food_type)
        self._fire_device_event("dog_fed", dog_id, meal_type=meal_type)

    async def _handle_log_health(self, call: ServiceCall) -> None:
        """Handle health data logging service."""
        coordinator = self._get_coordinator(call)
        dog_id = call.data.get("dog_id")
        weight_kg = call.data.get("weight_kg")
        note = call.data.get("note", "")

        await coordinator.log_health_data(dog_id, weight_kg, note)

    async def _handle_log_medication(self, call: ServiceCall) -> None:
        """Handle medication logging service."""
        coordinator = self._get_coordinator(call)
        dog_id = call.data.get("dog_id")
        medication_name = call.data.get("medication_name")
        dose = call.data.get("dose")

        await coordinator.log_medication(dog_id, medication_name, dose)
        self._fire_device_event("medication_given", dog_id, medication=medication_name)

    async def _handle_start_grooming(self, call: ServiceCall) -> None:
        """Handle grooming session service."""
        coordinator = self._get_coordinator(call)
        dog_id = call.data.get("dog_id")
        grooming_type = call.data.get("type", "brush")
        notes = call.data.get("notes", "")

        await coordinator.start_grooming(dog_id, grooming_type, notes)
        self._fire_device_event("grooming_done", dog_id, type=grooming_type)

    async def _handle_play_session(self, call: ServiceCall) -> None:
        """Handle play session service."""
        coordinator = self._get_coordinator(call)
        dog_id = call.data.get("dog_id")
        duration_min = call.data.get("duration_min", 15)
        intensity = call.data.get("intensity", "medium")

        await coordinator.log_play_session(dog_id, duration_min, intensity)

    async def _handle_training_session(self, call: ServiceCall) -> None:
        """Handle training session service."""
        coordinator = self._get_coordinator(call)
        dog_id = call.data.get("dog_id")
        topic = call.data.get("topic")
        duration_min = call.data.get("duration_min", 15)
        notes = call.data.get("notes", "")

        await coordinator.log_training(dog_id, topic, duration_min, notes)

    async def _handle_toggle_visitor(self, call: ServiceCall) -> None:
        """Handle visitor mode toggle service."""
        coordinator = self._get_coordinator(call)
        enabled = call.data.get("enabled")

        await coordinator.set_visitor_mode(enabled)

    async def _handle_emergency_mode(self, call: ServiceCall) -> None:
        """Handle emergency mode service."""
        coordinator = self._get_coordinator(call)
        level = call.data.get("level", "info")
        note = call.data.get("note", "")

        await coordinator.activate_emergency_mode(level, note)

    async def _handle_generate_report(self, call: ServiceCall) -> None:
        """Handle report generation service."""
        entry = self._get_entry_from_call(call)
        report_generator = entry.runtime_data.report_generator
        scope = call.data.get("scope", "daily")
        target = call.data.get("target", "notification")
        format_type = call.data.get("format", "text")

        await report_generator.generate_report(scope, target, format_type)

    async def _handle_export_data(self, call: ServiceCall) -> None:
        """Handle data export service."""
        entry = self._get_entry_from_call(call)
        report_generator = entry.runtime_data.report_generator
        dog_id = call.data.get("dog_id")
        date_from = call.data.get("from")
        date_to = call.data.get("to")
        format_type = call.data.get("format", "csv")

        await report_generator.export_health_data(
            dog_id, date_from, date_to, format_type
        )

    async def _handle_gps_start_walk(self, call: ServiceCall) -> None:
        """Handle GPS start walk service."""
        entry = self._get_entry_from_call(call)
        gps_handler = entry.runtime_data.gps_handler

        dog_id = call.data.get("dog_id")
        await gps_handler.async_start_walk(self.hass, call)
        self._fire_device_event("walk_started", dog_id)

    async def _handle_gps_end_walk(self, call: ServiceCall) -> None:
        """Handle GPS end walk service."""
        entry = self._get_entry_from_call(call)
        gps_handler = entry.runtime_data.gps_handler

        dog_id = call.data.get("dog_id")
        await gps_handler.async_end_walk(self.hass, call)
        self._fire_device_event("walk_ended", dog_id)

    async def _handle_gps_post_location(self, call: ServiceCall) -> None:
        """Handle GPS post location service."""
        entry = self._get_entry_from_call(call)
        gps_handler = entry.runtime_data.gps_handler

        dog_id = call.data.get("dog_id")
        await gps_handler.async_update_location(self.hass, call)
        self._fire_device_event("gps_location_posted", dog_id)

    async def _handle_gps_pause_tracking(self, call: ServiceCall) -> None:
        """Handle GPS pause tracking service."""
        entry = self._get_entry_from_call(call)
        gps_handler = entry.runtime_data.gps_handler

        await gps_handler.async_pause_tracking(self.hass, call)

    async def _handle_gps_resume_tracking(self, call: ServiceCall) -> None:
        """Handle GPS resume tracking service."""
        entry = self._get_entry_from_call(call)
        gps_handler = entry.runtime_data.gps_handler

        await gps_handler.async_resume_tracking(self.hass, call)

    async def _handle_gps_export_last_route(self, call: ServiceCall) -> None:
        """Handle GPS export last route service."""
        from .route_store import RouteHistoryStore

        entry = self._get_entry_from_call(call)
        dog_id = call.data.get("dog_id")

        store = RouteHistoryStore(self.hass, entry.entry_id, DOMAIN)
        routes = await store.async_list(dog_id)

        if routes:
            # Get the last route
            last_route = routes[-1]

            # Fire event with route data
            self.hass.bus.async_fire(
                f"{DOMAIN}_route_exported",
                {
                    "dog_id": dog_id,
                    "route": last_route,
                    "points": last_route.get("points", 0),
                    "distance_m": last_route.get("distance_m", 0),
                    "duration_s": last_route.get("duration_s", 0),
                },
            )
            _LOGGER.info(f"Exported last route for {dog_id}")
        else:
            _LOGGER.warning(f"No routes found for {dog_id}")

    async def _handle_gps_generate_diagnostics(self, call: ServiceCall) -> None:
        """Handle GPS generate diagnostics service."""
        from .gps_settings import GPSSettingsStore
        from .route_store import RouteHistoryStore

        entry = self._get_entry_from_call(call)
        dog_id = call.data.get("dog_id")
        coordinator = self._get_coordinator(call)

        # Gather diagnostic information
        dog_data = coordinator.get_dog_data(dog_id) if dog_id else {}
        location_data = dog_data.get("location", {})

        # Load GPS settings
        settings_store = GPSSettingsStore(self.hass, entry.entry_id, DOMAIN)
        gps_settings = await settings_store.async_load()

        # Get route history stats
        route_store = RouteHistoryStore(self.hass, entry.entry_id, DOMAIN)
        routes = await route_store.async_list(dog_id) if dog_id else []

        diagnostics = {
            "dog_id": dog_id,
            "gps_enabled": bool(gps_settings.get("enabled", False)),
            "last_gps_update": location_data.get("last_gps_update"),
            "current_location": location_data.get("current_location", "unknown"),
            "is_home": location_data.get("is_home"),
            "distance_from_home": location_data.get("distance_from_home"),
            "geofence": {
                "radius_m": location_data.get("radius_m", 0),
                "enters_today": location_data.get("enters_today", 0),
                "leaves_today": location_data.get("leaves_today", 0),
                "time_inside_today_min": location_data.get("time_inside_today_min", 0),
            },
            "routes": {
                "total_count": len(routes),
                "total_distance_m": sum(r.get("distance_m", 0) for r in routes),
                "total_duration_s": sum(r.get("duration_s", 0) for r in routes),
                "total_points": sum(r.get("points", 0) for r in routes),
            },
            "settings": gps_settings,
        }

        # Fire event with diagnostics
        self.hass.bus.async_fire(
            f"{DOMAIN}_gps_diagnostics", {"diagnostics": diagnostics}
        )
        _LOGGER.info(f"Generated GPS diagnostics for {dog_id or 'all dogs'}")

    async def _handle_gps_reset_stats(self, call: ServiceCall) -> None:
        """Handle GPS reset stats service."""
        self._get_entry_from_call(call)
        dog_id = call.data.get("dog_id")
        coordinator = self._get_coordinator(call)

        if dog_id:
            # Reset stats for specific dog
            dog_data = coordinator._dog_data.get(dog_id, {})
            if "location" in dog_data:
                dog_data["location"]["enters_today"] = 0
                dog_data["location"]["leaves_today"] = 0
                dog_data["location"]["time_inside_today_min"] = 0.0
                dog_data["location"]["last_gps_update"] = None

            if "walk" in dog_data:
                dog_data["walk"]["total_distance_today"] = 0

            _LOGGER.info(f"Reset GPS stats for {dog_id}")
        else:
            # Reset stats for all dogs
            for _did, ddata in coordinator._dog_data.items():
                if "location" in ddata:
                    ddata["location"]["enters_today"] = 0
                    ddata["location"]["leaves_today"] = 0
                    ddata["location"]["time_inside_today_min"] = 0.0
                    ddata["location"]["last_gps_update"] = None

                if "walk" in ddata:
                    ddata["walk"]["total_distance_today"] = 0

            _LOGGER.info("Reset GPS stats for all dogs")

        # Refresh coordinator to update entities
        await coordinator.async_request_refresh()

        # Fire event
        self.hass.bus.async_fire(
            f"{DOMAIN}_gps_stats_reset", {"dog_id": dog_id or "all"}
        )

    async def _handle_route_history_list(self, call: ServiceCall) -> None:
        """Handle route history list service."""
        from .route_store import RouteHistoryStore

        entry = self._get_entry_from_call(call)
        dog_id = call.data.get("dog_id")
        store = RouteHistoryStore(self.hass, entry.entry_id, DOMAIN)
        data = await store.async_list(dog_id=dog_id)
        self.hass.bus.async_fire(
            f"{DOMAIN}_route_history_listed", {"dog_id": dog_id, "result": data}
        )

    async def _handle_route_history_purge(self, call: ServiceCall) -> None:
        """Handle route history purge service."""
        from .route_store import RouteHistoryStore

        entry = self._get_entry_from_call(call)
        older_than_days = call.data.get("older_than_days")
        store = RouteHistoryStore(self.hass, entry.entry_id, DOMAIN)
        await store.async_purge(older_than_days=older_than_days)

    async def _handle_route_history_export_range(self, call: ServiceCall) -> None:
        """Handle route history export range service."""
        from homeassistant.helpers.storage import Store
        from homeassistant.util import dt as dt_util

        from .route_store import RouteHistoryStore

        entry = self._get_entry_from_call(call)
        dog_id = call.data.get("dog_id")
        date_from = call.data.get("date_from")
        date_to = call.data.get("date_to")

        # Parse dates
        try:
            df = (
                dt_util.parse_date(date_from)
                if isinstance(date_from, str)
                else date_from
            )
            dt = dt_util.parse_date(date_to) if isinstance(date_to, str) else date_to
        except Exception:
            df = dt = None

        store = RouteHistoryStore(self.hass, entry.entry_id, DOMAIN)
        data = await store.async_list(dog_id=dog_id)

        def in_range(item: dict[str, Any]) -> bool:
            """Check if item is in date range."""
            ts = item.get("start_time") or item.get("timestamp")
            try:
                t = dt_util.parse_datetime(ts)
            except Exception:
                return False
            if df and t.date() < df:
                return False
            return not (dt and t.date() > dt)

        filtered = [x for x in data if in_range(x)]

        # Save to storage
        export_name = f"{DOMAIN}_{entry.entry_id}_route_export"
        store_out = Store(self.hass, 1, export_name)
        await store_out.async_save(
            {
                "dog_id": dog_id,
                "from": str(date_from),
                "to": str(date_to),
                "items": filtered,
            }
        )
        self.hass.bus.async_fire(
            f"{DOMAIN}_route_history_exported",
            {"dog_id": dog_id, "count": len(filtered)},
        )

    async def _handle_toggle_geofence_alerts(self, call: ServiceCall) -> None:
        """Handle toggle geofence alerts service."""
        from .gps_settings import GPSSettingsStore

        entry = self._get_entry_from_call(call)
        enabled = bool(call.data.get("enabled", True))
        store = GPSSettingsStore(self.hass, entry.entry_id, DOMAIN)
        data = await store.async_load()
        data.setdefault("geofence", {})["alerts_enabled"] = enabled
        await store.async_save(data)

    async def _handle_prune_stale_devices(self, call: ServiceCall) -> None:
        """Handle pruning of stale devices."""
        from . import _auto_prune_devices

        entry = self._get_entry_from_call(call)
        await _auto_prune_devices(self.hass, entry, auto=bool(call.data.get("auto")))

    async def _handle_purge_all_storage(self, call: ServiceCall) -> None:
        """Handle purge all storage service."""
        from .gps_settings import GPSSettingsStore
        from .route_store import RouteHistoryStore

        entry = self._get_entry_from_call(call)

        # Route history
        store = RouteHistoryStore(self.hass, entry.entry_id, DOMAIN)
        await store.async_purge(older_than_days=None)

        # GPS settings
        gstore = GPSSettingsStore(self.hass, entry.entry_id, DOMAIN)
        await gstore.async_save({})

    @callback
    def _fire_device_event(self, event: str, dog_id: str | None, **data: Any) -> None:
        """Fire a device event."""
        device_id = self._device_id_from_dog(dog_id)
        self.hass.bus.async_fire(
            f"{DOMAIN}_{event}",
            {"device_id": device_id, "dog_id": dog_id, **data},
        )

    def _device_id_from_dog(self, dog_id: str | None) -> str | None:
        """Get device ID from dog ID."""
        if not dog_id:
            return None

        dev_reg = dr.async_get(self.hass)
        for device in dev_reg.devices.values():
            if device.identifiers:
                for domain, identifier in device.identifiers:
                    if domain == DOMAIN and identifier == dog_id:
                        return device.id
        return None
