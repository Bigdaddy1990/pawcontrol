"""Core setup for the Paw Control integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
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
from .types import DogConfigData
from .walk_manager import WalkManager

# Expose commonly patched classes/functions for tests


# Minimal DogDataManager stub for patching in tests
class DogDataManager:  # pragma: no cover - simple stub
    async def async_initialize(self, dogs: list[Any] | None = None) -> None:
        return None

    async def async_shutdown(self) -> None:
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Paw Control from a config entry."""
    _LOGGER.info("Setting up Paw Control integration entry: %s", entry.entry_id)

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

    coordinator = PawControlCoordinator(hass, entry)
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
    except Exception as err:
        raise ConfigEntryNotReady(f"Initialization failed: {err}") from err

    platforms = get_platforms_for_profile_and_modules(dogs_config, profile)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, platforms)
    except Exception as err:
        raise ConfigEntryNotReady(str(err)) from err

    # Optional service setup
    PawControlServiceManager(hass)
    await async_setup_daily_reset_scheduler(hass, entry)

    runtime_data = {
        "coordinator": coordinator,
        "data_manager": data_manager,
        "notification_manager": notification_manager,
        "feeding_manager": feeding_manager,
        "walk_manager": walk_manager,
        "entity_factory": entity_factory,
        "entity_profile": profile,
        "dogs": dogs_config,
    }
    entry.runtime_data = runtime_data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime_data
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    runtime_data = getattr(entry, "runtime_data", None)
    dogs = (
        runtime_data.get("dogs", []) if runtime_data else entry.data.get(CONF_DOGS, [])
    )
    profile = (
        runtime_data.get("entity_profile")
        if runtime_data
        else entry.options.get("entity_profile", "standard")
    )
    platforms = get_platforms_for_profile_and_modules(dogs, profile)

    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    except Exception:
        return False

    if unload_ok and runtime_data:
        for key in (
            "coordinator",
            "data_manager",
            "notification_manager",
            "feeding_manager",
            "walk_manager",
        ):
            manager = runtime_data.get(key)
            if manager and hasattr(manager, "async_shutdown"):
                await manager.async_shutdown()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
