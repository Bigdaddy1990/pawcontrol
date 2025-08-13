"""The Paw Control integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
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
)
from .helpers import notification_router as notification_router_mod
from .helpers import scheduler as scheduler_mod
from .helpers import setup_sync as setup_sync_mod
from .report_generator import ReportGenerator
from .services import ServiceManager
from .types import PawRuntimeData

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Paw Control component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Paw Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize coordinator
    coordinator = coordinator_mod.PawControlCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady from err

    # Initialize GPS handler
    gps_handler_obj = gps.PawControlGPSHandler(hass, entry.options)
    gps_handler_obj.entry_id = entry.entry_id
    await gps_handler_obj.async_setup()

    # Initialize helpers
    notification_router = notification_router_mod.NotificationRouter(hass, entry)
    setup_sync = setup_sync_mod.SetupSync(hass, entry)
    report_generator = ReportGenerator(hass, entry)

    # Initialize service manager
    services = ServiceManager(hass, entry)
    await services.async_register_services()

    # Create runtime data
    runtime_data = PawRuntimeData(
        coordinator=coordinator,
        gps_handler=gps_handler_obj,
        setup_sync=setup_sync,
        report_generator=report_generator,
        services=services,
        notification_router=notification_router,
    )

    # Set runtime data on entry
    entry.runtime_data = runtime_data

    # Store in hass.data for backward compatibility (will be removed later)
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "notification_router": notification_router,
        "setup_sync": setup_sync,
        "gps_handler": gps_handler_obj,
        "report_generator": report_generator,
        "services": services,
    }

    # Register devices for each dog
    await _register_devices(hass, entry)

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup schedulers (daily reset, reports, reminders)
    await scheduler_mod.setup_schedulers(hass, entry)

    # Initial sync of helpers and entities
    await setup_sync.sync_all()

    # Add update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Auto-prune stale devices (report or remove based on option)
    auto = bool(entry.options.get("auto_prune_devices", False))
    await _auto_prune_devices(hass, entry, auto=auto)

    # Check geofence options
    _check_geofence_options(hass, entry)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Cleanup schedulers
    await scheduler_mod.cleanup_schedulers(hass, entry)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Unregister services if no more entries
        if not hass.data[DOMAIN]:
            await entry.runtime_data.services.async_unregister_services()

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    runtime_data = entry.runtime_data

    # Update coordinator with new options
    runtime_data.coordinator.update_options(entry.options)

    # Resync helpers and entities
    await runtime_data.setup_sync.sync_all()

    # Reschedule tasks with new times
    await scheduler_mod.cleanup_schedulers(hass, entry)
    await scheduler_mod.setup_schedulers(hass, entry)

    # Refresh data
    await runtime_data.coordinator.async_request_refresh()


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of a config entry."""
    try:
        await async_unload_entry(hass, entry)
    except HomeAssistantError as err:
        _LOGGER.warning("Failed to unload config entry %s: %s", entry.entry_id, err)

    # Remove entry data
    domain_data = hass.data.get(DOMAIN, {})
    if entry.entry_id in domain_data:
        domain_data.pop(entry.entry_id, None)

    # If domain empty, unregister services
    if not domain_data and hasattr(entry, "runtime_data"):
        await entry.runtime_data.services.async_unregister_services()


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a device from the device registry."""
    # Only allow removal for devices with our DOMAIN identifier
    dog_id = None
    if device.identifiers:
        for idt in device.identifiers:
            if idt[0] == DOMAIN:
                dog_id = idt[1]
                break

    if not dog_id:
        return False

    # Cleanup internal caches/state if present
    runtime_data = entry.runtime_data
    if runtime_data and hasattr(runtime_data.coordinator, "_dog_data"):
        runtime_data.coordinator._dog_data.pop(dog_id, None)

    return True


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


async def _auto_prune_devices(
    hass: HomeAssistant, entry: ConfigEntry, *, auto: bool
) -> int:
    """Remove or report stale devices that are no longer known by the coordinator."""
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
    except HomeAssistantError as err:
        _LOGGER.warning("Failed to create stale_devices issue: %s", err)

    return len(stale_devices)


def _get_known_dog_ids(hass: HomeAssistant, entry: ConfigEntry) -> set[str]:
    """Get known dog IDs from coordinator."""
    runtime_data = entry.runtime_data
    dog_data = getattr(getattr(runtime_data, "coordinator", None), "_dog_data", {})
    if isinstance(dog_data, dict):
        return set(dog_data)
    return set()


def _check_geofence_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create a Repairs issue if geofence settings look invalid."""
    opts = entry.options or {}
    geo = opts.get("geofence", {})

    radius = geo.get("radius_m")
    lat = geo.get("lat")
    lon = geo.get("lon")

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
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="invalid_geofence",
                learn_more_url="https://developers.home-assistant.io/docs/core/integration-quality-scale/",
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Failed to create invalid_geofence issue: %s", err)
    else:
        ir.async_delete_issue(hass, DOMAIN, "invalid_geofence")
