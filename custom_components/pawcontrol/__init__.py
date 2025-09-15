"""Core setup and platform initialization for the PawControl integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_DOG_ID,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
    PLATFORMS,
)
from .coordinator import PawControlCoordinator
from .data_manager import PawControlDataManager
from .exceptions import PawControlSetupError
from .feeding_manager import FeedingManager
from .health_calculator import HealthCalculator
from .notifications import PawControlNotificationManager
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .types import DogConfigData, PawControlConfigEntry, PawControlRuntimeData
from .walk_manager import WalkManager

# Expose commonly patched classes/functions for tests


# Minimal DogDataManager stub for patching in tests
class DogDataManager:  # pragma: no cover - simple stub
    """Trivial dog data manager used for test patching."""

    async def async_initialize(self, dogs: list[Any] | None = None) -> None:
        """Initialize the stub manager."""
        return None

    async def async_shutdown(self) -> None:
        """Shut down the stub manager."""
        return None


_LOGGER = logging.getLogger(__name__)

# This integration can only be configured via the UI
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Available platforms
ALL_PLATFORMS: Final[list[Platform]] = PLATFORMS


def get_platforms_for_profile_and_modules(
    dogs_config: list[dict[str, Any]], profile: str
) -> list[Platform]:
    """Determine required platforms based on dogs, modules and profile."""
    enabled_modules: set[str] = set()
    for dog in dogs_config:
        modules = dog.get("modules", {})
        enabled_modules.update(m for m, enabled in modules.items() if enabled)

    platforms: set[Platform] = {Platform.SENSOR, Platform.BUTTON}

    if profile == "basic":
        if MODULE_WALK in enabled_modules or MODULE_GPS in enabled_modules:
            platforms.add(Platform.BINARY_SENSOR)
        if MODULE_NOTIFICATIONS in enabled_modules:
            platforms.add(Platform.SWITCH)
        return list(platforms)

    # Profiles other than basic include switches for notifications or any module
    if MODULE_NOTIFICATIONS in enabled_modules or enabled_modules:
        platforms.add(Platform.SWITCH)

    if MODULE_WALK in enabled_modules or MODULE_GPS in enabled_modules:
        platforms.add(Platform.BINARY_SENSOR)

    if MODULE_FEEDING in enabled_modules:
        platforms.add(Platform.SELECT)

    if MODULE_GPS in enabled_modules:
        platforms.update({Platform.DEVICE_TRACKER, Platform.NUMBER})

    if MODULE_HEALTH in enabled_modules:
        platforms.update({Platform.DATE, Platform.NUMBER, Platform.TEXT})

    if profile == "advanced":
        platforms.add(Platform.DATETIME)
    elif profile == "gps_focus":
        platforms.add(Platform.NUMBER)
    elif profile == "health_focus":
        platforms.update({Platform.DATE, Platform.NUMBER, Platform.TEXT})

    return list(platforms)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Paw Control integration from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Set up Paw Control from a config entry.

    Args:
        hass: Home Assistant instance
        entry: PawControl config entry with typed runtime data

    Returns:
        True if setup successful

    Raises:
        ConfigEntryNotReady: If setup prerequisites not met
    """
    _LOGGER.debug("Setting up Paw Control integration entry: %s", entry.entry_id)

    dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
    if not dogs_config:
        raise ConfigEntryNotReady("No dogs configured")
    if any(not dog.get(CONF_DOG_ID) for dog in dogs_config):
        raise ConfigEntryNotReady("Invalid dog configuration")

    # Determine profile
    profile = entry.options.get("entity_profile", "standard")
    from .entity_factory import ENTITY_PROFILES, EntityFactory

    if profile not in ENTITY_PROFILES:
        _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
        profile = "standard"

    # WebSession injection for Platinum compliance
    session = async_get_clientsession(hass)
    coordinator = PawControlCoordinator(hass, entry, session)
    data_manager = PawControlDataManager(hass, entry.entry_id)
    notification_manager = PawControlNotificationManager(hass, entry.entry_id)
    feeding_manager = FeedingManager()
    walk_manager = WalkManager()
    entity_factory = EntityFactory(coordinator)

    # Estimate entity count (used in performance tests)
    for dog in dogs_config:
        entity_factory.estimate_entity_count(profile, dog.get("modules", {}))

    try:
        await asyncio.gather(
            coordinator.async_config_entry_first_refresh(),
            data_manager.async_initialize(),
            notification_manager.async_initialize(),
            feeding_manager.async_initialize(dogs_config),
            walk_manager.async_initialize([dog[CONF_DOG_ID] for dog in dogs_config]),
        )
    except TimeoutError as err:
        raise ConfigEntryNotReady(f"Timeout during initialization: {err}") from err
    except (ValueError, KeyError) as err:
        raise ConfigEntryNotReady(f"Invalid configuration: {err}") from err
    except PawControlSetupError as err:
        raise ConfigEntryNotReady(f"Setup error: {err}") from err

    platforms = get_platforms_for_profile_and_modules(dogs_config, profile)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, platforms)
    except ImportError as err:
        raise ConfigEntryNotReady(f"Platform import failed: {err}") from err
    except (ValueError, TypeError) as err:
        raise ConfigEntryNotReady(f"Platform setup failed: {err}") from err

    # Optional service setup
    PawControlServiceManager(hass)
    await async_setup_daily_reset_scheduler(hass, entry)

    # Store runtime data in typed ConfigEntry - Platinum compliance
    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=data_manager,
        notification_manager=notification_manager,
        feeding_manager=feeding_manager,
        walk_manager=walk_manager,
        entity_factory=entity_factory,
        entity_profile=profile,
        dogs=dogs_config,
    )
    entry.runtime_data = runtime_data
    # NO hass.data storage - only use entry.runtime_data for Platinum
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload successful
    """
    runtime_data = entry.runtime_data
    dogs = runtime_data.dogs if runtime_data else entry.data.get(CONF_DOGS, [])
    profile = (
        runtime_data.entity_profile
        if runtime_data
        else entry.options.get("entity_profile", "standard")
    )
    platforms = get_platforms_for_profile_and_modules(dogs, profile)

    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    except (ImportError, ValueError, TypeError) as err:
        _LOGGER.error("Failed to unload platforms: %s", err)
        return False

    if unload_ok and runtime_data:
        # Clean shutdown of all managers
        managers = [
            runtime_data.coordinator,
            runtime_data.data_manager,
            runtime_data.notification_manager,
            runtime_data.feeding_manager,
            runtime_data.walk_manager,
        ]
        shutdown_managers = [mgr for mgr in managers if hasattr(mgr, "async_shutdown")]
        results = await asyncio.gather(
            *(manager.async_shutdown() for manager in shutdown_managers),
            return_exceptions=True,
        )
        for manager, result in zip(shutdown_managers, results, strict=True):
            if isinstance(result, Exception):
                _LOGGER.error(
                    "Error shutting down %s: %s",
                    manager.__class__.__name__,
                    result,
                )
        # No hass.data cleanup needed - only using entry.runtime_data

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> None:
    """Reload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
