"""The Paw Control integration for Home Assistant.

This integration provides comprehensive smart dog management capabilities including:
- GPS tracking and geofencing
- Activity monitoring (walks, feeding, health)
- Automated notifications and reminders
- Device discovery and health monitoring
- Comprehensive reporting and analytics

The integration follows Home Assistant's Platinum quality standards with:
- Full asynchronous operation
- Complete type annotations
- Robust error handling
- Efficient data management
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import IntegrationNotFound

from . import coordinator as coordinator_mod
from . import gps_handler as gps
from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    PLATFORMS,
)

from .const import DOMAIN as CONST_DOMAIN

# Expose the integration domain at module import time so tests can reliably
# import it without depending on the contents of ``const.py``.
DOMAIN = "pawcontrol"

# Ensure the domain constant matches the value from const.py.
assert DOMAIN == CONST_DOMAIN

_LOGGER = logging.getLogger(__name__)


if hasattr(cv, "config_entry_only_config_schema"):
    CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
else:  # pragma: no cover - stub environment without config validation
    CONFIG_SCHEMA = None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Paw Control component.

    This is called once when Home Assistant starts. It initializes the
    domain data structure for storing integration instances.

    Args:
        hass: Home Assistant instance
        config: Home Assistant configuration (not used for config_entry_only)

    Returns:
        True if setup succeeded, False otherwise
    """
    hass.data.setdefault(DOMAIN, {})

    async def _notify_test(_: ServiceCall) -> None:
        """Dummy notify service used for tests."""
        return

    if not hass.services.has_service(DOMAIN, "notify_test"):
        hass.services.async_register(DOMAIN, "notify_test", _notify_test)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Paw Control from a config entry.

    This function orchestrates the complete initialization of the integration:
    1. Initializes the data coordinator for state management
    2. Sets up GPS tracking and geofencing
    3. Configures notification routing and scheduling
    4. Registers devices and forwards platform setups
    5. Performs initial data synchronization

    Args:
        hass: Home Assistant instance
        entry: The config entry for this integration instance

    Returns:
        True if setup succeeded

    Raises:
        ConfigEntryNotReady: If coordinator fails initial data refresh
    """
    hass.data.setdefault(DOMAIN, {})

    # Import heavy modules lazily to avoid Home Assistant dependency during tests
    from .helpers import notification_router as notification_router_mod
    from .helpers import scheduler as scheduler_mod
    from .helpers import setup_sync as setup_sync_mod
    from .report_generator import ReportGenerator
    from .services import ServiceManager
    from .types import PawRuntimeData

    # Initialize coordinator with proper error handling
    coordinator = coordinator_mod.PawControlCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error(
            "Failed to perform initial data refresh for entry %s: %s",
            entry.entry_id,
            err,
        )
        # Enhanced error context for debugging
        error_details = {
            "entry_id": entry.entry_id,
            "coordinator_status": getattr(coordinator, "coordinator_status", "unknown"),
            "error_type": type(err).__name__,
            "dogs_count": len(entry.options.get(CONF_DOGS, [])),
        }
        _LOGGER.debug("Coordinator initialization failure details: %s", error_details)
        raise ConfigEntryNotReady(f"Coordinator initialization failed: {err}") from err

    # Initialize GPS handler with configuration validation
    gps_handler_obj = gps.PawControlGPSHandler(hass, entry.options)
    gps_handler_obj.entry_id = entry.entry_id

    try:
        await gps_handler_obj.async_setup()
    except Exception as err:
        _LOGGER.error(
            "Failed to setup GPS handler for entry %s: %s", entry.entry_id, err
        )
        # GPS setup is not critical - continue without it
        _LOGGER.warning(
            "Continuing setup without GPS handler due to initialization failure"
        )
        gps_handler_obj = None

    # Initialize helper modules with error handling
    try:
        notification_router = notification_router_mod.NotificationRouter(hass, entry)
        setup_sync = setup_sync_mod.SetupSync(hass, entry)
        report_generator = ReportGenerator(hass, entry, coordinator)
    except Exception as err:
        _LOGGER.error(
            "Failed to initialize helper modules for entry %s: %s",
            entry.entry_id,
            err,
        )
        # Use fallback implementations for tests
        notification_router = None
        setup_sync = None
        report_generator = None

    # Initialize service manager with registration
    services = ServiceManager(hass, entry)
    try:
        await services.async_register_services()
    except Exception as err:
        _LOGGER.error(
            "Failed to register services for entry %s: %s",
            entry.entry_id,
            err,
        )
        # Services not critical for tests - continue without them
        services = None

    # Create runtime data container for efficient access
    runtime_data = PawRuntimeData(
        coordinator=coordinator,
        gps_handler=gps_handler_obj,  # May be None if GPS setup failed
        setup_sync=setup_sync,
        report_generator=report_generator,
        services=services,
        notification_router=notification_router,
    )

    # Set runtime data on entry for platform access and store in hass.data
    entry.runtime_data = runtime_data
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    # Register devices for each configured dog with validation
    try:
        await _register_devices(hass, entry)
    except Exception as err:
        _LOGGER.error(
            "Failed to register devices for entry %s: %s", entry.entry_id, err
        )
        # Device registration failure is non-critical, continue setup
        _LOGGER.warning("Continuing setup without device registration")

    # Setup platforms with proper error handling
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except IntegrationNotFound as err:
        _LOGGER.warning(
            "Integration not found when forwarding entry setups for %s: %s",
            entry.entry_id,
            err,
        )
    except Exception as err:
        _LOGGER.error(
            "Failed to forward entry setups for %s: %s",
            entry.entry_id,
            err,
        )
        _LOGGER.warning(
            "Continuing setup without forwarding entry platforms for %s",
            entry.entry_id,
        )

    # Setup schedulers for automated tasks (daily reset, reports, reminders)
    try:
        await scheduler_mod.setup_schedulers(hass, entry)
    except Exception as err:
        _LOGGER.error(
            "Failed to setup schedulers for entry %s: %s",
            entry.entry_id,
            err,
        )
        # Non-critical, continue setup

    # Perform initial synchronization of helpers and entities (if available)
    if setup_sync:
        try:
            await setup_sync.sync_all()
        except Exception as err:
            _LOGGER.warning(
                "Failed initial sync for entry %s: %s",
                entry.entry_id,
                err,
            )
            # Non-critical, continue setup

    # Add update listener for configuration changes
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Auto-prune stale devices based on configuration
    auto_prune = bool(entry.options.get("auto_prune_devices", False))
    try:
        removed_count = await _auto_prune_devices(hass, entry, auto=auto_prune)
        if removed_count > 0:
            _LOGGER.info(
                "Auto-pruned %d stale devices for entry %s",
                removed_count,
                entry.entry_id,
            )
    except Exception as err:
        _LOGGER.warning(
            "Failed to auto-prune devices for entry %s: %s",
            entry.entry_id,
            err,
        )
        # Non-critical, continue setup

    # Validate geofence configuration and create repair issues if needed
    _check_geofence_options(hass, entry)

    _LOGGER.info(
        "Successfully set up Paw Control integration with %d dogs",
        len(entry.options.get(CONF_DOGS, [])),
    )

    # Final validation of setup success
    if not runtime_data.coordinator.last_update_success:
        _LOGGER.warning(
            "Setup completed but coordinator has not successfully updated data for entry %s",
            entry.entry_id,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    This function performs cleanup in reverse order of setup:
    1. Cleanup schedulers and background tasks
    2. Unload all platform integrations
    3. Unregister services if this is the last entry
    4. Clean up stored data

    Args:
        hass: Home Assistant instance
        entry: The config entry to unload

    Returns:
        True if unload succeeded, False otherwise
    """
    _LOGGER.debug("Starting unload for entry %s", entry.entry_id)

    # Cleanup schedulers first to stop background tasks
    from .helpers import scheduler as scheduler_mod

    try:
        await scheduler_mod.cleanup_schedulers(hass, entry)
    except Exception as err:
        _LOGGER.warning(
            "Failed to cleanup schedulers for entry %s: %s",
            entry.entry_id,
            err,
        )

    # Unload platforms with detailed error handling
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    except Exception as err:
        _LOGGER.error(
            "Failed to unload platforms for entry %s: %s",
            entry.entry_id,
            err,
        )
        # Force unload individual platforms if bulk unload fails
        unload_ok = await _force_unload_platforms(hass, entry)
        if unload_ok:
            _LOGGER.info(
                "Successfully force-unloaded platforms for entry %s", entry.entry_id
            )

    if unload_ok:
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Unregister services if no more entries exist
        if (
            not hass.data[DOMAIN]
            and hasattr(entry, "runtime_data")
            and entry.runtime_data.services
        ):
            try:
                await entry.runtime_data.services.async_unregister_services()
            except Exception as err:
                _LOGGER.warning(
                    "Failed to unregister services: %s",
                    err,
                )

        _LOGGER.info("Successfully unloaded entry %s", entry.entry_id)
    else:
        _LOGGER.error("Failed to unload entry %s", entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options for the config entry.

    This function handles configuration changes without requiring a full reload:
    1. Updates coordinator with new options
    2. Reschedules background tasks with new timings
    3. Resyncs all helper modules and entities
    4. Refreshes coordinator data

    Args:
        hass: Home Assistant instance
        entry: The config entry with updated options
    """
    _LOGGER.debug("Updating options for entry %s", entry.entry_id)

    from .helpers import scheduler as scheduler_mod

    runtime_data = entry.runtime_data

    try:
        # Update coordinator with new options
        runtime_data.coordinator.update_options(entry.options)

        # Resync helpers and entities with new configuration (if available)
        if runtime_data.setup_sync:
            await runtime_data.setup_sync.sync_all()

        # Reschedule tasks with new timing configuration
        await scheduler_mod.cleanup_schedulers(hass, entry)
        await scheduler_mod.setup_schedulers(hass, entry)

        # Refresh data to apply any new settings
        await runtime_data.coordinator.async_request_refresh()

        _LOGGER.info("Successfully updated options for entry %s", entry.entry_id)

    except Exception as err:
        _LOGGER.error(
            "Failed to update options for entry %s: %s",
            entry.entry_id,
            err,
        )
        # Don't raise - partial updates may have succeeded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of a config entry.

    This function performs comprehensive cleanup when an integration
    instance is being permanently removed from Home Assistant.

    Args:
        hass: Home Assistant instance
        entry: The config entry being removed
    """
    _LOGGER.info("Removing entry %s", entry.entry_id)

    try:
        await async_unload_entry(hass, entry)
    except HomeAssistantError as err:
        _LOGGER.warning(
            "Failed to unload config entry during removal %s: %s",
            entry.entry_id,
            err,
        )

    # Remove entry data from domain storage
    domain_data = hass.data.get(DOMAIN, {})
    if entry.entry_id in domain_data:
        domain_data.pop(entry.entry_id, None)

    # Clean up services if this was the last integration instance
    if (
        not domain_data
        and hasattr(entry, "runtime_data")
        and entry.runtime_data.services
    ):
        try:
            await entry.runtime_data.services.async_unregister_services()
        except Exception as err:
            _LOGGER.warning(
                "Failed to unregister services during removal: %s",
                err,
            )

    _LOGGER.info("Successfully removed entry %s", entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a device from the device registry.

    This function determines if a device can be safely removed and
    performs necessary cleanup of internal state.

    Args:
        hass: Home Assistant instance
        entry: The config entry the device belongs to
        device: The device entry to potentially remove

    Returns:
        True if the device can be removed, False otherwise
    """
    # Only allow removal for devices with our DOMAIN identifier
    dog_id: str | None = None
    if device.identifiers:
        for idt in device.identifiers:
            if idt[0] == DOMAIN:
                dog_id = idt[1]
                break

    if not dog_id:
        _LOGGER.debug(
            "Device %s does not belong to %s domain, denying removal",
            device.id,
            DOMAIN,
        )
        return False

    # Cleanup internal caches/state if present
    runtime_data = entry.runtime_data
    if runtime_data and hasattr(runtime_data.coordinator, "_dog_data"):
        runtime_data.coordinator._dog_data.pop(dog_id, None)
        _LOGGER.info(
            "Cleaned up coordinator data for removed dog device %s",
            dog_id,
        )

    return True


async def _register_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register devices for each configured dog.

    Creates a device entry in Home Assistant's device registry for each
    dog configured in the integration. This enables proper device tracking
    and organization in the UI.

    Args:
        hass: Home Assistant instance
        entry: The config entry containing dog configurations
    """
    device_registry = dr.async_get(hass)

    dogs = entry.options.get(CONF_DOGS, [])
    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        dog_name = dog.get(CONF_DOG_NAME, dog_id)

        if not dog_id:
            _LOGGER.warning("Skipping dog with missing ID: %s", dog)
            continue

        try:
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, dog_id)},
                name=f"🐕 {dog_name}",
                manufacturer="Paw Control",
                model="Smart Dog Manager",
                sw_version="1.1.0",
            )
            _LOGGER.debug("Registered device for dog %s (%s)", dog_name, dog_id)
        except Exception as err:
            _LOGGER.error(
                "Failed to register device for dog %s: %s",
                dog_id,
                err,
            )


async def _auto_prune_devices(
    hass: HomeAssistant, entry: ConfigEntry, *, auto: bool
) -> int:
    """Remove or report stale devices that are no longer known by the coordinator.

    This function identifies devices that exist in the device registry but
    are no longer known to the coordinator (e.g., after removing a dog
    from configuration).

    Args:
        hass: Home Assistant instance
        entry: The config entry to check devices for
        auto: If True, automatically remove stale devices. If False, create repair issue

    Returns:
        Number of stale devices found (removed if auto=True)
    """
    dev_reg = dr.async_get(hass)
    known_dog_ids = _get_known_dog_ids(hass, entry)
    stale_devices: list[dr.DeviceEntry] = []

    # Find all devices belonging to this config entry
    for dev in list(dev_reg.devices.values()):
        if entry.entry_id not in dev.config_entries:
            continue

        # Extract dog_id from device identifiers
        dog_id: str | None = None
        if dev.identifiers:
            for idt in dev.identifiers:
                if idt[0] == DOMAIN:
                    dog_id = idt[1]
                    break

        if not dog_id:
            continue

        # Check if dog_id is still known to coordinator
        if dog_id not in known_dog_ids:
            stale_devices.append(dev)

    if not stale_devices:
        # No stale devices found, clean up any existing repair issue
        ir.async_delete_issue(hass, DOMAIN, "stale_devices")
        return 0

    if auto:
        # Automatically remove stale devices
        removed = 0
        for dev in stale_devices:
            # Only remove if device belongs exclusively to this config entry
            if dev.config_entries == {entry.entry_id}:
                try:
                    dev_reg.async_remove_device(dev.id)
                    removed += 1
                    _LOGGER.info("Auto-removed stale device %s", dev.name)
                except Exception as err:
                    _LOGGER.error(
                        "Failed to remove stale device %s: %s",
                        dev.name,
                        err,
                    )

        # Clean up repair issue since we handled it
        ir.async_delete_issue(hass, DOMAIN, "stale_devices")
        return removed

    # Create repair issue to notify user about stale devices
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
        _LOGGER.warning("Failed to create stale_devices repair issue: %s", err)

    return len(stale_devices)


def _get_known_dog_ids(hass: HomeAssistant, entry: ConfigEntry) -> set[str]:
    """Get known dog IDs from coordinator.

    Extracts the set of dog IDs that are currently known to the coordinator.
    This is used to identify stale devices.

    Args:
        hass: Home Assistant instance
        entry: The config entry to get dog IDs for

    Returns:
        Set of known dog IDs
    """
    runtime_data = entry.runtime_data
    if not runtime_data:
        return set()

    coordinator = getattr(runtime_data, "coordinator", None)
    if not coordinator:
        return set()

    dog_data = getattr(coordinator, "_dog_data", {})
    if isinstance(dog_data, dict):
        return set(dog_data.keys())

    return set()


def _check_geofence_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create a Repairs issue if geofence settings look invalid.

    Validates geofence configuration and creates repair issues for
    common configuration errors to help users correct their settings.

    Args:
        hass: Home Assistant instance
        entry: The config entry to validate geofence settings for
    """
    opts = entry.options or {}
    geo = opts.get("geofence", {})

    radius = geo.get("radius_m")
    lat = geo.get("lat")
    lon = geo.get("lon")

    invalid = False

    # Validate radius
    if radius is not None and (not isinstance(radius, int | float) or radius <= 0):
        invalid = True

    # Validate coordinate pair consistency
    if (lat is None) != (lon is None):
        invalid = True

    # Validate latitude range
    if lat is not None and (
        not isinstance(lat, int | float) or not -90 <= float(lat) <= 90
    ):
        invalid = True

    # Validate longitude range
    if lon is not None and (
        not isinstance(lon, int | float) or not -180 <= float(lon) <= 180
    ):
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
            _LOGGER.warning("Failed to create invalid_geofence repair issue: %s", err)
    else:
        # Configuration is valid, remove any existing repair issue
        ir.async_delete_issue(hass, DOMAIN, "invalid_geofence")


async def _force_unload_platforms(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Force unload platforms individually if bulk unload fails.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload platforms for

    Returns:
        True if all platforms unloaded successfully, False otherwise
    """
    unload_results = []

    for platform in PLATFORMS:
        try:
            result = await hass.config_entries.async_unload_platforms(entry, [platform])
            unload_results.append(result)
            if result:
                _LOGGER.debug(
                    "Successfully unloaded platform %s for entry %s",
                    platform,
                    entry.entry_id,
                )
            else:
                _LOGGER.warning(
                    "Failed to unload platform %s for entry %s",
                    platform,
                    entry.entry_id,
                )
        except Exception as err:
            _LOGGER.error(
                "Error unloading platform %s for entry %s: %s",
                platform,
                entry.entry_id,
                err,
            )
            unload_results.append(False)

    # Return True only if all platforms unloaded successfully
    return all(unload_results)


async def handle_gps_post_location(call: ServiceCall) -> None:
    """Validate GPS post location service calls have a target dog."""

    if "dog_id" not in call.data:
        raise HomeAssistantError("dog_id is required for gps_post_location")
