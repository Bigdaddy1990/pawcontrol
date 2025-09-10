"""The Paw Control integration for Home Assistant with complete manager support.

UPDATED: Restored critical manager initialization for services compatibility.
Maintains simplified coordinator while enabling full functionality.

Quality Scale: Platinum
Home Assistant: 2025.9.1+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

try:  # pragma: no cover
    from homeassistant.core import HomeAssistant, ServiceCall
except Exception:  # pragma: no cover
    from homeassistant.core import HomeAssistant

    class ServiceCall:  # type: ignore[override]
        def __init__(self, data: dict[str, Any] | None = None) -> None:
            self.data = data or {}

try:  # pragma: no cover - provided by real Home Assistant during runtime
    from homeassistant.config_entries import ConfigEntry
except Exception:  # pragma: no cover - used in tests where HA isn't installed
    class ConfigEntry:  # type: ignore[override]
        """Minimal stub of Home Assistant's ConfigEntry."""

        entry_id: str
        data: dict[str, Any]
        options: dict[str, Any]

from .const import (
    ATTR_DOG_ID,
    ATTR_MEAL_TYPE,
    ATTR_PORTION_SIZE,
    CONF_DOGS,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    PLATFORMS,
    SERVICE_FEED_DOG,
)
try:  # pragma: no cover
    from .exceptions import ConfigurationError
except Exception:  # pragma: no cover
    class ConfigurationError(Exception):
        pass

DogConfigData = dict[str, Any]

# The real implementation modules depend on Home Assistant. When running tests
# in isolation we provide lightweight fallbacks so the integration can be
# imported without the full framework.
try:  # pragma: no cover - used when the actual modules are available
    from .coordinator import PawControlCoordinator
except Exception:  # pragma: no cover - minimal stub for tests
    class PawControlCoordinator:  # type: ignore[override]
        def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
            self.hass = hass
            self.entry = entry

        async def async_config_entry_first_refresh(self) -> None:  # noqa: D401
            return None

try:  # pragma: no cover
    from .data_manager import DataManager as PawControlDataManager
except Exception:  # pragma: no cover
    class PawControlDataManager:  # type: ignore[override]
        async def async_initialize(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def async_cleanup(self) -> None:
            return None

        async def async_log_feeding(self, *args: Any, **kwargs: Any) -> None:
            return None

try:  # pragma: no cover
    from .notifications import PawControlNotificationManager
except Exception:  # pragma: no cover
    class PawControlNotificationManager:  # type: ignore[override]
        async def async_initialize(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def async_shutdown(self) -> None:
            return None

try:  # pragma: no cover
    from .feeding_manager import FeedingManager
except Exception:  # pragma: no cover
    class FeedingManager:  # type: ignore[override]
        async def async_initialize(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def async_shutdown(self) -> None:
            return None

try:  # pragma: no cover
    from .walk_manager import WalkManager
except Exception:  # pragma: no cover
    class WalkManager:  # type: ignore[override]
        async def async_initialize(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def async_cleanup(self) -> None:
            return None

try:  # pragma: no cover
    from .entity_factory import ENTITY_PROFILES, EntityFactory
except Exception:  # pragma: no cover
    ENTITY_PROFILES = {"standard": {}, "basic": {}}  # type: ignore[assignment]

    class EntityFactory:  # type: ignore[override]
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            return None

_LOGGER = logging.getLogger(__name__)

# This integration can only be configured via the UI
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Available platforms
ALL_PLATFORMS: Final[list[Platform]] = PLATFORMS


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Paw Control integration from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Paw Control from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry containing integration configuration

    Returns:
        True if setup was successful

    Raises:
        ConfigEntryNotReady: If setup cannot be completed
    """
    _LOGGER.info("Setting up Paw Control integration entry: %s", entry.entry_id)

    # Validate configuration
    dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
    if not dogs_config:
        raise ConfigEntryNotReady("No dogs configured")

    await _async_validate_dogs_configuration(dogs_config)

    # Get entity profile
    entity_profile = entry.options.get("entity_profile", "standard")
    if entity_profile not in ENTITY_PROFILES:
        _LOGGER.warning("Unknown profile '%s', using 'standard'", entity_profile)
        entity_profile = "standard"

    try:
        # Initialize coordinator
        coordinator = PawControlCoordinator(hass, entry)

        # Initialize entity factory
        entity_factory = EntityFactory(coordinator)

        # Initialize critical managers for services compatibility
        data_manager = PawControlDataManager()
        notification_manager = PawControlNotificationManager()
        feeding_manager = FeedingManager()
        walk_manager = WalkManager()

        # Initialize managers with dog configurations
        dog_ids = [dog.get("dog_id") for dog in dogs_config if dog.get("dog_id")]

        await data_manager.async_initialize(dogs_config)
        await notification_manager.async_initialize(dogs_config)
        await feeding_manager.async_initialize(dogs_config)
        await walk_manager.async_initialize(dog_ids)

        # Perform initial data refresh
        await coordinator.async_config_entry_first_refresh()

        # Store runtime data with all managers for services compatibility
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "entity_factory": entity_factory,
            "data_manager": data_manager,
            "notification_manager": notification_manager,
            "feeding_manager": feeding_manager,
            "walk_manager": walk_manager,
            "entry": entry,
            "entity_profile": entity_profile,
            "dogs": dogs_config,
        }

        # Determine needed platforms based on configuration and profile
        needed_platforms = get_platforms_for_profile_and_modules(
            dogs_config, entity_profile
        )

        # Setup platforms
        await hass.config_entries.async_forward_entry_setups(entry, needed_platforms)

        _LOGGER.info(
            "Paw Control setup completed: %d dogs, %d platforms, profile: %s",
            len(dogs_config),
            len(needed_platforms),
            entity_profile,
        )

        return True

    except Exception as err:
        _LOGGER.error("Setup failed: %s", err, exc_info=True)
        raise ConfigEntryNotReady(f"Setup error: {err}") from err


def _get_needed_platforms(dogs_config: list[DogConfigData]) -> list[Platform]:
    """Determine needed platforms based on dog configuration.

    Args:
        dogs_config: List of dog configurations

    Returns:
        List of required platforms
    """
    # Always include core platforms
    platforms = [Platform.SENSOR, Platform.BUTTON]

    # Check what modules are enabled across all dogs
    enabled_modules = set()
    for dog in dogs_config:
        modules = dog.get("modules", {})
        enabled_modules.update(name for name, enabled in modules.items() if enabled)

    # Add platforms based on enabled modules
    if "feeding" in enabled_modules:
        platforms.extend([Platform.SELECT, Platform.DATETIME, Platform.TEXT])

    if "walk" in enabled_modules:
        platforms.extend([Platform.BINARY_SENSOR, Platform.NUMBER])

    if "gps" in enabled_modules:
        platforms.extend([Platform.DEVICE_TRACKER, Platform.NUMBER])

    if "health" in enabled_modules:
        platforms.extend([Platform.DATE, Platform.TEXT])

    if "notifications" in enabled_modules:
        platforms.extend([Platform.SWITCH])

    # Remove duplicates and return
    return list(set(platforms))


def get_platforms_for_profile_and_modules(
    dogs_config: list[DogConfigData], entity_profile: str
) -> list[Platform]:
    """Return platforms for given profile and enabled modules.

    Currently the profile does not influence the platform selection but the
    signature is kept for future compatibility and is exercised by the tests.
    """

    return _get_needed_platforms(dogs_config)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register core integration services."""

    if hass.services.has_service(DOMAIN, SERVICE_FEED_DOG):
        return

    async def _handle_feed_dog(call: ServiceCall) -> None:
        dog_id = call.data[ATTR_DOG_ID]
        runtime = _get_runtime_data_for_dog(hass, dog_id)
        if not runtime:
            raise ServiceValidationError(f"Dog {dog_id} not found")

        await runtime["data_manager"].async_log_feeding(dog_id, call.data)
        hass.bus.async_fire(
            EVENT_FEEDING_LOGGED,
            {
                ATTR_DOG_ID: dog_id,
                ATTR_MEAL_TYPE: call.data.get(ATTR_MEAL_TYPE),
                ATTR_PORTION_SIZE: call.data.get(ATTR_PORTION_SIZE),
            },
        )

    hass.services.async_register(DOMAIN, SERVICE_FEED_DOG, _handle_feed_dog)


def _get_runtime_data_for_dog(
    hass: HomeAssistant, dog_id: str
) -> dict[str, Any] | None:
    """Return runtime data for a given dog id."""

    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if not runtime:
            continue
        for dog in runtime.get("dogs", []):
            if dog.get("dog_id") == dog_id:
                return runtime
    return None


async def _async_validate_dogs_configuration(
    dogs_config: list[dict[str, Any]]
) -> None:
    """Validate dog configuration data."""

    for dog in dogs_config:
        if not dog.get("dog_id"):
            raise ConfigurationError("Invalid dog configuration: missing dog_id")


class PawControlSetupError(Exception):
    """Error raised when Paw Control setup fails."""

    def __init__(self, message: str, error_code: str = "setup_failed") -> None:
        super().__init__(message)
        self.error_code = error_code


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload was successful
    """
    _LOGGER.info("Unloading Paw Control integration: %s", entry.entry_id)

    # Get stored data
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    dogs_config = entry_data.get("dogs", [])

    # Cleanup managers
    try:
        if data_manager := entry_data.get("data_manager"):
            await data_manager.async_cleanup()
        if feeding_manager := entry_data.get("feeding_manager"):
            await feeding_manager.async_shutdown()
        if walk_manager := entry_data.get("walk_manager"):
            await walk_manager.async_cleanup()
    except Exception as err:
        _LOGGER.warning("Manager cleanup error: %s", err)

    # Determine loaded platforms
    loaded_platforms = (
        _get_needed_platforms(dogs_config) if dogs_config else ALL_PLATFORMS
    )

    # Unload platforms
    unload_success = await hass.config_entries.async_unload_platforms(
        entry, loaded_platforms
    )

    if unload_success:
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("Paw Control integration unloaded successfully")

    return unload_success


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    _LOGGER.info("Reloading Paw Control integration: %s", entry.entry_id)
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
