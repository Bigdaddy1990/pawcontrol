"""Paw Control integration entry setup."""
from __future__ import annotations

import logging
import os
import json
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.issue_registry import async_create_issue

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_DOGS,
    SERVICE_GPS_START_WALK,
    SERVICE_GPS_END_WALK,
    SERVICE_GPS_GENERATE_DIAGNOSTICS,
    SERVICE_GPS_RESET_STATS,
    SERVICE_GPS_EXPORT_LAST_ROUTE,
    SERVICE_GPS_PAUSE_TRACKING,
    SERVICE_GPS_RESUME_TRACKING,
    SERVICE_GPS_POST_LOCATION,
    SERVICE_GPS_LIST_WEBHOOKS,
    SERVICE_GPS_REGENERATE_WEBHOOKS,
    SERVICE_TOGGLE_GEOFENCE_ALERTS,
    SERVICE_EXPORT_OPTIONS,
    SERVICE_IMPORT_OPTIONS,
    SERVICE_NOTIFY_TEST,
    SERVICE_PURGE_ALL_STORAGE,
    SERVICE_ROUTE_HISTORY_LIST,
    SERVICE_ROUTE_HISTORY_PURGE,
    SERVICE_ROUTE_HISTORY_EXPORT_RANGE,
    SERVICE_SEND_MEDICATION_REMINDER,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Paw Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize data structure for this entry
    data: dict[str, Any] = {
        "entry_id": entry.entry_id,
        "options": entry.options or {},
        "gps_handler": None,
        "coordinator": None,
        "_services": [],
    }
    
    hass.data[DOMAIN][entry.entry_id] = data
    
    # Store version info
    if "version" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["version"] = "1.0.15"

    # Initialize GPS handler (best-effort)
    gps_handler = None
    try:
        from .gps_handler import PawControlGPSHandler
        gps_handler = PawControlGPSHandler(hass, entry.options or {})
        gps_handler.entry_id = entry.entry_id
        await gps_handler.async_setup()
        data["gps_handler"] = gps_handler
        _LOGGER.debug("GPS handler initialized successfully")
    except Exception as exc:
        _LOGGER.debug("GPS handler unavailable: %s", exc)

    # Initialize coordinator
    try:
        from .coordinator import PawControlCoordinator
        coordinator = PawControlCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        data["coordinator"] = coordinator
        _LOGGER.debug("Coordinator initialized successfully")
    except Exception as exc:
        _LOGGER.warning("Coordinator setup failed: %s", exc)
        # Clean up the partially created data entry and signal Home Assistant
        # that the setup should be retried. Without raising
        # ConfigEntryNotReady here, Home Assistant would mark the integration
        # as loaded even though the coordinator is unavailable.
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryNotReady from exc

    # Ensure per-dog webhooks are generated & registered
    await _ensure_webhooks(hass, entry, data)

    # Register services
    await _register_services(hass, entry, data)

    # Forward entry setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register logbook descriptions (best-effort)
    try:
        from . import logbook as logbook_support
        logbook_support.async_describe_events(hass)
    except Exception as exc:
        _LOGGER.debug("Logbook registration failed: %s", exc)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Create repair issue if no dogs configured
    await _check_dogs_configuration(hass, entry)

    return True


async def _ensure_webhooks(hass: HomeAssistant, entry: ConfigEntry, data: dict[str, Any]) -> None:
    """Ensure per-dog webhooks are generated & registered."""
    try:
        from homeassistant.components.webhook import (
            async_generate_id,
            async_register as webhook_register,
        )
        from .gps_settings import GPSSettingsStore

        store = GPSSettingsStore(hass, entry.entry_id, DOMAIN)
        settings = await store.async_load()
        hooks = settings.setdefault("webhooks", {})
        dogs = (entry.options or {}).get("dogs") or []
        changed = False

        for dog_config in dogs:
            dog_id = dog_config.get("dog_id") or dog_config.get("name")
            if not dog_id:
                continue

            dog_hooks = hooks.setdefault(dog_id, {})
            webhook_id = dog_hooks.get("location_update")
            
            if not webhook_id:
                webhook_id = async_generate_id()
                dog_hooks["location_update"] = webhook_id
                changed = True

            async def _webhook_handler(hass2, webhook_id, request, _dog=dog_id):
                """Handle incoming webhook for GPS location update."""
                try:
                    # Validate Content-Type
                    if request.content_type != 'application/json':
                        _LOGGER.warning("Invalid content type: %s", request.content_type)
                        from aiohttp import web
                        return web.Response(status=400, text="Content-Type must be application/json")
                    
                    # Limit request size
                    content_length = request.headers.get('Content-Length')
                    if content_length and int(content_length) > 10240:  # 10KB limit
                        _LOGGER.warning("Request too large: %s bytes", content_length)
                        from aiohttp import web
                        return web.Response(status=413, text="Request too large")
                    
                    json_data = await request.json()
                    if not isinstance(json_data, dict):
                        raise ValueError("Invalid JSON structure")
                        
                except Exception as exc:
                    _LOGGER.warning("Invalid webhook request: %s", exc)
                    from aiohttp import web
                    return web.Response(status=400, text="Invalid request")

                # Validate and sanitize input
                try:
                    lat = json_data.get("lat") or json_data.get("latitude")
                    lon = json_data.get("lon") or json_data.get("longitude")
                    acc = json_data.get("acc") or json_data.get("accuracy")
                    
                    # Strict validation
                    if lat is None or lon is None:
                        raise ValueError("Missing latitude or longitude")
                    
                    lat_val = float(lat)
                    lon_val = float(lon)
                    
                    # Validate coordinate ranges
                    if not (-90 <= lat_val <= 90):
                        raise ValueError(f"Invalid latitude: {lat_val}")
                    if not (-180 <= lon_val <= 180):
                        raise ValueError(f"Invalid longitude: {lon_val}")
                    
                    acc_val = None
                    if acc is not None:
                        acc_val = float(acc)
                        if acc_val < 0 or acc_val > 10000:  # reasonable accuracy range
                            raise ValueError(f"Invalid accuracy: {acc_val}")
                    
                    # Update location if handler available
                    if data.get("gps_handler"):
                        await data["gps_handler"].async_update_location(
                            lat_val,
                            lon_val,
                            acc_val,
                            source="webhook",
                            dog_id=_dog,
                        )
                    
                except (ValueError, TypeError) as exc:
                    _LOGGER.warning("Invalid webhook data for dog %s: %s", _dog, exc)
                    from aiohttp import web
                    return web.Response(status=400, text=f"Invalid data: {exc}")
                except Exception as exc:
                    _LOGGER.error("Webhook location update failed for dog %s: %s", _dog, exc)
                    from aiohttp import web
                    return web.Response(status=500, text="Internal error")

                from aiohttp import web
                return web.Response(text="OK")

            try:
                webhook_register(
                    hass,
                    DOMAIN,
                    f"Paw Control GPS {dog_id}",
                    webhook_id,
                    _webhook_handler,
                )
            except Exception as exc:
                _LOGGER.warning("Webhook registration failed for %s: %s", dog_id, exc)

        if changed:
            await store.async_save(settings)

    except Exception as exc:
        _LOGGER.warning("Webhook setup failed: %s", exc)


async def _register_services(hass: HomeAssistant, entry: ConfigEntry, data: dict[str, Any]) -> None:
    """Register all services for the integration."""
    tracked_services = []

    def _register_service(domain: str, name: str, handler, schema=None):
        """Helper to register a service and track it."""
        hass.services.async_register(domain, name, handler, schema=schema)
        tracked_services.append((domain, name))

    # GPS Services
    _register_service(
        DOMAIN,
        SERVICE_GPS_START_WALK,
        lambda call: _gps_service_wrapper(call, "async_start_walk", data),
        schema=vol.Schema({
            vol.Optional("dog_id"): str,
            vol.Optional("walk_type", default="normal"): str,
        }),
    )

    _register_service(
        DOMAIN,
        SERVICE_GPS_END_WALK,
        lambda call: _gps_service_wrapper(call, "async_end_walk", data),
        schema=vol.Schema({
            vol.Optional("dog_id"): str,
            vol.Optional("rating"): int,
            vol.Optional("notes"): str,
        }),
    )

    _register_service(
        DOMAIN,
        SERVICE_GPS_GENERATE_DIAGNOSTICS,
        lambda call: _gps_service_wrapper(call, "async_generate_diagnostics", data),
        schema=vol.Schema({vol.Optional("dog_id"): str}),
    )

    _register_service(
        DOMAIN,
        SERVICE_GPS_RESET_STATS,
        lambda call: _gps_service_wrapper(call, "async_reset_gps_stats", data),
        schema=vol.Schema({vol.Optional("dog_id"): str}),
    )

    _register_service(
        DOMAIN,
        SERVICE_GPS_EXPORT_LAST_ROUTE,
        lambda call: _gps_service_wrapper(call, "async_export_last_route", data),
        schema=vol.Schema({
            vol.Optional("dog_id"): str,
            vol.Optional("format", default="geojson"): str,
            vol.Optional("to_media", default=False): bool,
        }),
    )

    _register_service(
        DOMAIN,
        SERVICE_GPS_PAUSE_TRACKING,
        lambda call: _gps_service_wrapper(call, "async_pause_tracking", data),
        schema=vol.Schema({vol.Optional("dog_id"): str}),
    )

    _register_service(
        DOMAIN,
        SERVICE_GPS_RESUME_TRACKING,
        lambda call: _gps_service_wrapper(call, "async_resume_tracking", data),
        schema=vol.Schema({vol.Optional("dog_id"): str}),
    )

    _register_service(
        DOMAIN,
        SERVICE_GPS_POST_LOCATION,
        lambda call: hass.async_create_task(_gps_post_location(call, entry, data)),
        schema=vol.Schema({
            vol.Optional("dog_id"): str,
            vol.Required("latitude"): float,
            vol.Required("longitude"): float,
            vol.Optional("accuracy"): float,
        }),
    )

    # Utility Services
    _register_service(
        DOMAIN,
        SERVICE_TOGGLE_GEOFENCE_ALERTS,
        lambda call: hass.async_create_task(_toggle_geofence(call, entry)),
        schema=vol.Schema({
            vol.Optional("dog_id"): str,
            vol.Required("enable"): bool,
        }),
    )

    _register_service(DOMAIN, SERVICE_EXPORT_OPTIONS, lambda call: hass.async_create_task(_export_options(call, entry)))
    _register_service(DOMAIN, SERVICE_IMPORT_OPTIONS, lambda call: hass.async_create_task(_import_options(call, entry)), schema=vol.Schema({vol.Optional("path"): str}))
    _register_service(DOMAIN, SERVICE_NOTIFY_TEST, lambda call: hass.async_create_task(_notify_test(call, entry)))
    _register_service(DOMAIN, SERVICE_PURGE_ALL_STORAGE, lambda call: hass.async_create_task(_purge_all_storage(call, entry)))
    _register_service(DOMAIN, SERVICE_GPS_LIST_WEBHOOKS, lambda call: hass.async_create_task(_gps_list_webhooks(call, entry)))
    _register_service(DOMAIN, SERVICE_GPS_REGENERATE_WEBHOOKS, lambda call: hass.async_create_task(_gps_regenerate_webhooks(call, entry, data)))

    # Medication services
    _register_service(
        DOMAIN,
        SERVICE_SEND_MEDICATION_REMINDER,
        lambda call: hass.async_create_task(_send_medication_reminder(call, entry)),
        schema=vol.Schema({
            vol.Required("dog_id"): str,
            vol.Optional("meal"): vol.In(["breakfast", "lunch", "dinner"]),
            vol.Optional("slot"): vol.All(int, vol.Range(min=1, max=3)),
            vol.Optional("notes"): str,
        }),
    )

    # Route history services
    _register_service(
        DOMAIN,
        SERVICE_ROUTE_HISTORY_LIST,
        lambda call: hass.async_create_task(_route_history_list(call, entry)),
        schema=vol.Schema({vol.Optional("dog_id"): str}),
    )

    _register_service(
        DOMAIN,
        SERVICE_ROUTE_HISTORY_PURGE,
        lambda call: hass.async_create_task(_route_history_purge(call, entry)),
        schema=vol.Schema({vol.Optional("older_than_days"): int}),
    )

    _register_service(
        DOMAIN,
        SERVICE_ROUTE_HISTORY_EXPORT_RANGE,
        lambda call: hass.async_create_task(_route_history_export_range(call, entry)),
    )

    data["_services"] = tracked_services


async def _gps_service_wrapper(call: ServiceCall, method_name: str, data: dict[str, Any]) -> None:
    """Wrapper for GPS handler service calls."""
    gps_handler = data.get("gps_handler")
    if not gps_handler:
        _LOGGER.warning("GPS handler not available for service %s", method_name)
        return

    try:
        method = getattr(gps_handler, method_name)
        if method_name in ["async_start_walk", "async_end_walk"]:
            await method(
                call.data.get("walk_type"),
                call.data.get("dog_id"),
            )
        elif method_name == "async_export_last_route":
            await method(
                call.data.get("dog_id"),
                call.data.get("format", "geojson"),
                bool(call.data.get("to_media", False)),
            )
        else:
            await method(call.data.get("dog_id"))
    except Exception as exc:
        _LOGGER.error("GPS service %s failed: %s", method_name, exc)


async def _gps_post_location(call: ServiceCall, entry: ConfigEntry, data: dict[str, Any]) -> None:
    """Handle GPS location posting."""
    dog_id = call.data.get("dog_id") or _get_default_dog_id(entry)
    latitude = call.data.get("latitude")
    longitude = call.data.get("longitude")
    accuracy = call.data.get("accuracy")

    gps_handler = data.get("gps_handler")
    if gps_handler and latitude is not None and longitude is not None:
        await gps_handler.async_update_location(
            float(latitude),
            float(longitude),
            float(accuracy) if accuracy is not None else None,
            source="service",
            dog_id=dog_id,
        )


async def _toggle_geofence(call: ServiceCall, entry: ConfigEntry) -> None:
    """Toggle geofence alerts for a dog."""
    from .gps_settings import GPSSettingsStore

    dog_id = call.data.get("dog_id") or _get_default_dog_id(entry)
    enable = bool(call.data.get("enable", True))

    store = GPSSettingsStore(entry.hass, entry.entry_id, DOMAIN)
    settings = await store.async_load()
    safe_zones = settings.setdefault("safe_zones", {})
    dog_zone = safe_zones.setdefault(dog_id, {})
    dog_zone["enable_alerts"] = enable
    await store.async_save(settings)


async def _export_options(call: ServiceCall, entry: ConfigEntry) -> None:
    """Export integration options to file."""
    path = entry.hass.config.path("pawcontrol_options_export.json")
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(entry.options or {}, file_handle, indent=2, ensure_ascii=False)

    try:
        from homeassistant.components.persistent_notification import create as pn
        pn(entry.hass, f"Optionen exportiert: {path}", title="Paw Control – Export")
    except Exception:
        pass


async def _import_options(call: ServiceCall, entry: ConfigEntry) -> None:
    """Import integration options from file."""
    path = call.data.get("path") or entry.hass.config.path("pawcontrol_options_export.json")
    
    try:
        with open(path, "r", encoding="utf-8") as file_handle:
            options = json.load(file_handle)
        
        entry.hass.config_entries.async_update_entry(entry, options=options)
        
        try:
            from homeassistant.components.persistent_notification import create as pn
            pn(entry.hass, f"Optionen importiert aus: {path}", title="Paw Control – Import")
        except Exception:
            pass
    except Exception as exc:
        _LOGGER.error("Failed to import options from %s: %s", path, exc)


async def _notify_test(call: ServiceCall, entry: ConfigEntry) -> None:
    """Send test notification."""
    try:
        from .helpers.notification_router import NotificationRouter
        
        notify_target = (entry.options or {}).get("reminders", {}).get("notify_target")
        router = NotificationRouter(entry.hass, notify_target)
        await router.send_generic(
            "Paw Control – Test",
            "Benachrichtigungen funktionieren.",
            None,
            "test",
        )
    except Exception:
        try:
            from homeassistant.components.persistent_notification import create as pn
            pn(entry.hass, "Benachrichtigungen funktionieren (Fallback).", title="Paw Control – Test")
        except Exception:
            pass


async def _purge_all_storage(call: ServiceCall, entry: ConfigEntry) -> None:
    """Purge all stored data."""
    from .gps_settings import GPSSettingsStore
    from .route_store import RouteHistoryStore

    settings_store = GPSSettingsStore(entry.hass, entry.entry_id, DOMAIN)
    route_store = RouteHistoryStore(entry.hass, entry.entry_id, DOMAIN)
    
    await settings_store.async_save({})
    await route_store.async_save({"dogs": {}})
    
    try:
        from homeassistant.components.persistent_notification import create as pn
        pn(entry.hass, "Alle gespeicherten Einstellungen/Verläufe gelöscht.", title="Paw Control – Bereinigung")
    except Exception:
        pass


async def _gps_list_webhooks(call: ServiceCall, entry: ConfigEntry) -> None:
    """List all configured webhooks."""
    try:
        from homeassistant.components.webhook import async_generate_url
        from .gps_settings import GPSSettingsStore

        store = GPSSettingsStore(entry.hass, entry.entry_id, DOMAIN)
        settings = await store.async_load()
        hooks = settings.get("webhooks") or {}
        
        webhook_urls = {}
        for dog_id, dog_hooks in hooks.items():
            webhook_id = dog_hooks.get("location_update")
            if webhook_id:
                webhook_urls[dog_id] = {
                    "location_update": async_generate_url(entry.hass, webhook_id)
                }

        base_path = entry.hass.config.path("pawcontrol_diagnostics")
        os.makedirs(base_path, exist_ok=True)
        
        file_path = os.path.join(base_path, "webhooks.json")
        with open(file_path, "w", encoding="utf-8") as file_handle:
            json.dump(webhook_urls, file_handle, ensure_ascii=False, indent=2)

        try:
            from homeassistant.components.persistent_notification import create as pn
            pn(entry.hass, f"Webhook-Übersicht geschrieben: {file_path}", title="Paw Control – Webhooks")
        except Exception:
            pass
    except Exception as exc:
        _LOGGER.error("Failed to list webhooks: %s", exc)


async def _gps_regenerate_webhooks(call: ServiceCall, entry: ConfigEntry, data: dict[str, Any]) -> None:
    """Regenerate all webhooks."""
    try:
        await _ensure_webhooks(entry.hass, entry, data)
        
        try:
            from homeassistant.components.persistent_notification import create as pn
            pn(entry.hass, "Webhooks regeneriert.", title="Paw Control – Webhooks")
        except Exception:
            pass
    except Exception as exc:
        _LOGGER.error("Failed to regenerate webhooks: %s", exc)


async def _send_medication_reminder(call: ServiceCall, entry: ConfigEntry) -> None:
    """Send per-dog medication reminder with optional meal/slot filtering."""
    try:
        dog_id = call.data.get("dog_id")
        meal = call.data.get("meal")
        slot = call.data.get("slot")
        notes = call.data.get("notes")

        if not dog_id:
            _LOGGER.error("No dog_id provided for medication reminder")
            return

        medication_mapping = (entry.options or {}).get("medication_mapping", {})
        dog_mapping = medication_mapping.get(dog_id, {})
        
        valid_meals = {"breakfast", "lunch", "dinner"}
        slots = []
        
        if isinstance(slot, int) and 1 <= slot <= 3:
            slots = [slot]
        elif meal in valid_meals:
            for i in (1, 2, 3):
                if meal in (dog_mapping.get(f"slot{i}") or []):
                    slots.append(i)
        else:
            # No filter -> all slots
            slots = [1, 2, 3]

        try:
            from .helpers.notification_router import NotificationRouter
            notify_target = (entry.options or {}).get("reminders", {}).get("notify_target")
            router = NotificationRouter(entry.hass, notify_target)
        except Exception:
            router = None

        for slot_num in slots:
            title = f"Medikation – {dog_id} (Slot {slot_num})"
            message = f"{dog_id}: jetzt Medikament (Slot {slot_num}) einnehmen."
            
            if meal in valid_meals:
                message += f" (zu: {meal})"
            if notes:
                message += f" – {notes}"

            if router:
                await router.send_generic(title, message, dog_id=dog_id, kind="medication")
            else:
                try:
                    from homeassistant.components.persistent_notification import create as pn
                    pn(entry.hass, message, title=f"Paw Control – {title}")
                except Exception:
                    pass
    except Exception as exc:
        _LOGGER.error("Failed to send medication reminder: %s", exc)


async def _route_history_list(call: ServiceCall, entry: ConfigEntry) -> None:
    """List route history for a dog."""
    try:
        from .route_store import RouteHistoryStore

        dog_id = call.data.get("dog_id") or _get_default_dog_id(entry)
        store = RouteHistoryStore(entry.hass, entry.entry_id, DOMAIN)
        items = await store.async_list(dog_id)

        base_path = entry.hass.config.path("pawcontrol_diagnostics")
        os.makedirs(base_path, exist_ok=True)
        
        file_path = os.path.join(base_path, f"{dog_id}_route_index.json")
        with open(file_path, "w", encoding="utf-8") as file_handle:
            json.dump(items[-200:], file_handle, indent=2, ensure_ascii=False)
            
    except Exception as exc:
        _LOGGER.error("Failed to list route history: %s", exc)


async def _route_history_purge(call: ServiceCall, entry: ConfigEntry) -> None:
    """Purge old route history."""
    try:
        from .route_store import RouteHistoryStore

        store = RouteHistoryStore(entry.hass, entry.entry_id, DOMAIN)
        days = call.data.get("older_than_days")
        await store.async_purge(days)
    except Exception as exc:
        _LOGGER.error("Failed to purge route history: %s", exc)


async def _route_history_export_range(call: ServiceCall, entry: ConfigEntry) -> None:
    """Export route history for a date range."""
    try:
        from .route_store import RouteHistoryStore
        from homeassistant.util import dt as dt_util
        import zipfile

        dog_id = call.data.get("dog_id") or _get_default_dog_id(entry)
        export_format = call.data.get("format", "geojson")
        start_date = dt_util.parse_datetime(call.data.get("start")) if call.data.get("start") else None
        end_date = dt_util.parse_datetime(call.data.get("end")) if call.data.get("end") else None
        
        store = RouteHistoryStore(entry.hass, entry.entry_id, DOMAIN)
        items = await store.async_list(dog_id)

        base_dir = entry.hass.config.path("media/pawcontrol_routes")
        os.makedirs(base_dir, exist_ok=True)
        
        zip_path = os.path.join(base_dir, f"{dog_id}_routes_export.zip")
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for i, item in enumerate(items):
                if export_format == "geojson":
                    feature = {
                        "type": "Feature",
                        "properties": {
                            "dog_id": dog_id,
                            "distance_m": item.get("distance_m"),
                            "duration_s": item.get("duration_s"),
                            "end": item.get("end"),
                        },
                        "geometry": {"type": "LineString", "coordinates": []},
                    }
                    data = {"type": "FeatureCollection", "features": [feature]}
                    zip_file.writestr(f"{dog_id}_summary_{i}.geojson", json.dumps(data))
                elif export_format == "gpx":
                    zip_file.writestr(
                        f"{dog_id}_summary_{i}.gpx",
                        "<?xml version='1.0'?><gpx version='1.1'></gpx>",
                    )
    except Exception as exc:
        _LOGGER.error("Failed to export route history: %s", exc)


def _get_default_dog_id(entry: ConfigEntry) -> str:
    """Get the default dog ID from the first configured dog."""
    dogs = (entry.options or {}).get("dogs", [])
    if dogs:
        return dogs[0].get("dog_id") or dogs[0].get("name") or "dog"
    return "dog"


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates by reloading the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _check_dogs_configuration(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Check if dogs are configured and create repair issue if not."""
    try:
        dogs = (entry.options or {}).get("dogs", [])
        if not dogs:
            async_create_issue(
                hass,
                DOMAIN,
                "no_dogs_configured",
                is_fixable=False,
                is_persistent=True,
                severity="warning",
                translation_key="no_dogs_configured",
            )
    except Exception as exc:
        _LOGGER.debug("Failed to check dogs configuration: %s", exc)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from homeassistant.components.webhook import async_unregister as webhook_unregister

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Unregister webhooks
    try:
        from .gps_settings import GPSSettingsStore

        store = GPSSettingsStore(hass, entry.entry_id, DOMAIN)
        settings = await store.async_load()
        
        for dog_id, hooks in (settings.get("webhooks") or {}).items():
            for hook_name, webhook_id in (hooks or {}).items():
                try:
                    webhook_unregister(hass, webhook_id)
                except Exception as exc:
                    _LOGGER.debug("Failed to unregister webhook %s: %s", webhook_id, exc)
    except Exception as exc:
        _LOGGER.debug("Failed to unregister webhooks: %s", exc)

    # Remove registered services
    try:
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        for domain, service_name in entry_data.get("_services", []):
            try:
                hass.services.async_remove(domain, service_name)
            except Exception as exc:
                _LOGGER.debug("Failed to remove service %s.%s: %s", domain, service_name, exc)
    except Exception as exc:
        _LOGGER.debug("Failed to remove services: %s", exc)

    # Remove entry data
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry data/options."""
    options = dict(entry.options or {})
    changed = False

    # Migrate dogs configuration
    dogs = options.get("dogs")
    if isinstance(dogs, dict):
        options["dogs"] = [
            {"dog_id": k, "name": v.get("name", k)} for k, v in dogs.items()
        ]
        changed = True
    elif not isinstance(dogs, list):
        options["dogs"] = []
        changed = True

    # Ensure modules configuration
    if "modules" not in options or not isinstance(options.get("modules"), dict):
        options["modules"] = {
            "gps": True,
            "feeding": True,
            "health": True,
            "walk": True,
            "notifications": True,
        }
        changed = True

    # Ensure reset time
    if "reset_time" not in options:
        options["reset_time"] = "23:59:00"
        changed = True

    if changed:
        hass.config_entries.async_update_entry(entry, options=options)

    return True
