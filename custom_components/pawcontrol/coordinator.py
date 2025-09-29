"""Coordinator for PawControl integration.

Simplified coordinator with session management and intelligent caching
for Platinum quality compliance without overengineering.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError, ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import (
    CoordinatorUpdateFailed,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_EXTERNAL_INTEGRATIONS,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_MODULES,
    MODULE_GPS,
    MODULE_WEATHER,
    UPDATE_INTERVALS,
)
from .device_api import PawControlDeviceClient
from .exceptions import (
    GPSUnavailableError,
    NetworkError,
    RateLimitError,
    ValidationError,
)
from .module_adapters import CoordinatorModuleAdapters
from .types import DogConfigData, PawControlConfigEntry

if TYPE_CHECKING:
    from .data_manager import PawControlDataManager
    from .feeding_manager import FeedingManager
    from .garden_manager import GardenManager
    from .geofencing import PawControlGeofencing
    from .gps_manager import GPSGeofenceManager
    from .notifications import PawControlNotificationManager
    from .walk_manager import WalkManager
    from .weather_manager import WeatherHealthManager

_LOGGER = logging.getLogger(__name__)

# PLATINUM: Optimized constants
API_TIMEOUT = 30.0
CACHE_TTL_SECONDS = 300  # 5 minutes
MAINTENANCE_INTERVAL = timedelta(hours=1)
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 1.5
COORDINATOR_SETUP_TIMEOUT = 15


class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for PawControl integration.

    Enhanced coordinator focused on reliability, maintainability and performance
    while meeting all Platinum quality requirements with specific error handling.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PawControlConfigEntry,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize coordinator with session management and enhanced caching.

        Args:
            hass: Home Assistant instance
            entry: Config entry for this integration with typed runtime data
            session: Optional aiohttp session for external API calls

        Raises:
            ConfigEntryNotReady: If initialization prerequisites are not met
            ValidationError: If entry configuration is invalid
        """
        self.config_entry = entry
        self.session = session or async_get_clientsession(hass)

        # PLATINUM: Enhanced configuration validation
        try:
            self._dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
            if not isinstance(self._dogs_config, list):
                raise ValidationError(
                    "dogs_config",
                    type(self._dogs_config).__name__,
                    "Must be a list of dog configurations",
                )
        except (KeyError, TypeError) as err:
            raise ValidationError(
                "dogs_config", None, f"Invalid dogs configuration: {err}"
            ) from err

        self._dog_config_by_id: dict[str, DogConfigData] = {}
        self._configured_dog_ids: list[str] = []
        for config in self._dogs_config:
            dog_id = config.get(CONF_DOG_ID)
            if not isinstance(dog_id, str):
                continue
            normalized_id = dog_id.strip()
            if not normalized_id or normalized_id in self._dog_config_by_id:
                continue
            self._dog_config_by_id[normalized_id] = config
            self._configured_dog_ids.append(normalized_id)

        self._use_external_api = bool(
            entry.options.get(CONF_EXTERNAL_INTEGRATIONS, False)
        )
        api_endpoint_option = entry.options.get(CONF_API_ENDPOINT) or ""
        api_token_option = entry.options.get(CONF_API_TOKEN) or ""
        self._api_client: PawControlDeviceClient | None = None
        if api_endpoint_option:
            try:
                self._api_client = PawControlDeviceClient(
                    self.session,
                    endpoint=api_endpoint_option.strip(),
                    api_key=api_token_option.strip() or None,
                )
            except ValueError as err:
                _LOGGER.warning(
                    "Invalid Paw Control API endpoint '%s': %s",
                    api_endpoint_option,
                    err,
                )

        # Calculate update interval with validation
        try:
            update_interval = self._calculate_update_interval()
            if update_interval <= 0:
                raise ValueError("Update interval must be positive")
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Invalid update interval calculation: %s", err)
            update_interval = UPDATE_INTERVALS.get("balanced", 120)

        # PLATINUM: Pass config_entry to coordinator for proper type safety
        super().__init__(
            hass,
            _LOGGER,
            name="PawControl Data",
            update_interval=timedelta(seconds=update_interval),
            config_entry=entry,
        )

        self._modules = CoordinatorModuleAdapters(
            session=self.session,
            config_entry=entry,
            use_external_api=self._use_external_api,
            cache_ttl=timedelta(seconds=CACHE_TTL_SECONDS),
            api_client=self._api_client,
        )

        # Runtime data and performance tracking
        self._data: dict[str, dict[str, Any]] = {}
        self._update_count = 0
        self._error_count = 0
        self._consecutive_errors = 0
        self._maintenance_unsub: callback | None = None
        self._setup_complete = False

        # Runtime manager references (TYPE_CHECKING imports)
        self.data_manager: PawControlDataManager | None = None
        self.feeding_manager: FeedingManager | None = None
        self.walk_manager: WalkManager | None = None
        self.notification_manager: PawControlNotificationManager | None = None
        self.gps_geofence_manager: GPSGeofenceManager | None = None
        self.weather_health_manager: WeatherHealthManager | None = None
        self.garden_manager: GardenManager | None = None
        self.geofencing_manager: PawControlGeofencing | None = None

        _LOGGER.info(
            "Coordinator initialized: %d dogs, %ds interval, external_api=%s",
            len(self._dogs_config),
            update_interval,
            self._use_external_api,
        )

    @property
    def use_external_api(self) -> bool:
        """Return whether external integrations are enabled."""
        return self._use_external_api

    @use_external_api.setter
    def use_external_api(self, value: bool) -> None:
        """Update the external API usage flag."""
        self._use_external_api = bool(value)

    @property
    def api_client(self) -> PawControlDeviceClient | None:
        """Return the configured device API client, if any."""

        return self._api_client

    def attach_runtime_managers(
        self,
        *,
        data_manager: PawControlDataManager,
        feeding_manager: FeedingManager,
        walk_manager: WalkManager,
        notification_manager: PawControlNotificationManager,
        geofencing_manager: PawControlGeofencing | None = None,
        gps_geofence_manager: GPSGeofenceManager | None = None,
        weather_health_manager: WeatherHealthManager | None = None,
        garden_manager: GardenManager | None = None,
    ) -> None:
        """Attach runtime managers for service integration.

        Args:
            data_manager: Data management service
            feeding_manager: Feeding tracking service
            walk_manager: Walk tracking service
            notification_manager: Notification service
            gps_geofence_manager: GPS and geofencing service (optional)
            weather_health_manager: Weather health service (optional)
        """
        self.data_manager = data_manager
        self.feeding_manager = feeding_manager
        self.walk_manager = walk_manager
        self.notification_manager = notification_manager
        self.gps_geofence_manager = gps_geofence_manager
        self.geofencing_manager = geofencing_manager
        self.weather_health_manager = weather_health_manager
        self.garden_manager = garden_manager
        if gps_geofence_manager:
            gps_geofence_manager.set_notification_manager(notification_manager)
        self._modules.attach_managers(
            data_manager=data_manager,
            feeding_manager=feeding_manager,
            walk_manager=walk_manager,
            gps_geofence_manager=gps_geofence_manager,
            weather_health_manager=weather_health_manager,
            garden_manager=garden_manager,
        )
        _LOGGER.debug(
            "Runtime managers attached (gps_geofence: %s, weather: %s)",
            bool(gps_geofence_manager),
            bool(weather_health_manager),
        )

    def clear_runtime_managers(self) -> None:
        """Clear runtime manager references during unload."""
        self.data_manager = None
        self.feeding_manager = None
        self.walk_manager = None
        self.notification_manager = None
        self.gps_geofence_manager = None
        self.geofencing_manager = None
        self.weather_health_manager = None
        self.garden_manager = None
        self._modules.detach_managers()

    async def _async_setup(self) -> None:
        """Perform coordinator preparation before the first refresh."""

        if self._setup_complete:
            return

        if not self._dogs_config:
            _LOGGER.debug("Skipping coordinator setup: no dogs configured")
            self._setup_complete = True
            return

        # Normalize module mappings to avoid key errors in later refreshes.
        for dog in self._dogs_config:
            modules = dog.get(CONF_MODULES)
            if modules is None:
                dog[CONF_MODULES] = {}
            elif not isinstance(modules, dict):
                _LOGGER.warning(
                    "Normalizing invalid module configuration for dog %s",
                    dog.get(CONF_DOG_ID, "<unknown>"),
                )
                dog[CONF_MODULES] = {}

        # Ensure runtime storage contains placeholders so entities do not read
        # from an empty mapping during the first coordinator refresh.
        for dog_id in self._configured_dog_ids:
            self._data.setdefault(dog_id, {})

        # Clear adapter caches to guarantee fresh data after reloads.
        self._modules.clear_caches()

        self._setup_complete = True
        _LOGGER.debug(
            "Coordinator pre-setup completed for %d dogs", len(self._configured_dog_ids)
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data for all dogs efficiently with enhanced error handling.

        Returns:
            Dictionary mapping dog_id to dog data

        Raises:
            CoordinatorUpdateFailed: If all dogs fail or critical errors occur
            ConfigEntryAuthFailed: If authentication fails
            ConfigEntryNotReady: If coordinator is not ready
        """
        if not self._dogs_config:
            return {}

        self._update_count += 1
        all_data: dict[str, dict[str, Any]] = {}
        errors = 0

        # PLATINUM: Enhanced dog ID validation
        dog_ids: list[str] = []
        for dog in self._dogs_config:
            dog_id = dog.get(CONF_DOG_ID)
            if isinstance(dog_id, str) and dog_id.strip():
                dog_ids.append(dog_id.strip())
            else:
                _LOGGER.warning("Skipping dog with invalid identifier: %s", dog_id)

        if not dog_ids:
            self._error_count += 1
            raise CoordinatorUpdateFailed("No valid dogs configured")

        # PLATINUM: Enhanced concurrent fetch with specific error handling
        async def fetch_and_store(dog_id: str) -> None:
            nonlocal errors
            retry_count = 0
            last_error: Exception | None = None

            while retry_count < MAX_RETRY_ATTEMPTS:
                try:
                    async with asyncio.timeout(API_TIMEOUT):
                        all_data[dog_id] = await self._fetch_dog_data(dog_id)
                    return  # Success, exit retry loop

                except TimeoutError as err:
                    last_error = err
                    _LOGGER.warning(
                        "Timeout fetching data for dog %s (attempt %d/%d): %s",
                        dog_id,
                        retry_count + 1,
                        MAX_RETRY_ATTEMPTS,
                        err,
                    )
                except ConfigEntryAuthFailed:
                    # Authentication errors should not be retried
                    raise
                except (ClientError, NetworkError) as err:
                    last_error = err
                    _LOGGER.warning(
                        "Network error fetching data for dog %s (attempt %d/%d): %s",
                        dog_id,
                        retry_count + 1,
                        MAX_RETRY_ATTEMPTS,
                        err,
                    )
                except RateLimitError as err:
                    last_error = err
                    _LOGGER.warning(
                        "Rate limit hit for dog %s, waiting %s seconds",
                        dog_id,
                        err.retry_after or 60,
                    )
                    if err.retry_after:
                        await asyncio.sleep(min(err.retry_after, 300))  # Max 5 min wait
                except ValidationError as err:
                    # Data validation errors shouldn't be retried
                    errors += 1
                    _LOGGER.error("Invalid configuration for dog %s: %s", dog_id, err)
                    all_data[dog_id] = self._get_empty_dog_data()
                    return
                except HomeAssistantError as err:
                    last_error = err
                    _LOGGER.warning(
                        "HA error fetching data for dog %s (attempt %d/%d): %s",
                        dog_id,
                        retry_count + 1,
                        MAX_RETRY_ATTEMPTS,
                        err,
                    )

                retry_count += 1
                if retry_count < MAX_RETRY_ATTEMPTS:
                    # Exponential backoff
                    wait_time = min(2**retry_count * RETRY_BACKOFF_FACTOR, 30)
                    await asyncio.sleep(wait_time)

            # All retries failed
            errors += 1
            _LOGGER.error(
                "Failed to fetch data for dog %s after %d attempts, last error: %s",
                dog_id,
                MAX_RETRY_ATTEMPTS,
                last_error,
            )
            all_data[dog_id] = self._data.get(dog_id, self._get_empty_dog_data())

        # Execute with proper task group error handling
        try:
            async with asyncio.TaskGroup() as task_group:
                for dog_id in dog_ids:
                    task_group.create_task(fetch_and_store(dog_id))
        except* ConfigEntryAuthFailed as auth_error_group:
            # Re-raise authentication failures
            raise auth_error_group.exceptions[0]  # noqa: B904
        except* Exception as error_group:
            # Log other task group errors but continue
            for exc in error_group.exceptions:
                _LOGGER.error("Task group error: %s", exc)

        # PLATINUM: Enhanced failure analysis
        total_dogs = len(dog_ids)
        success_rate = ((total_dogs - errors) / total_dogs) if total_dogs > 0 else 0

        if errors == total_dogs:
            self._error_count += 1
            self._consecutive_errors += 1
            raise CoordinatorUpdateFailed(
                f"All {total_dogs} dogs failed to update"
            )

        if success_rate < 0.5:  # More than 50% failed
            self._consecutive_errors += 1
            _LOGGER.warning(
                "Low success rate: %d/%d dogs updated successfully",
                total_dogs - errors,
                total_dogs,
            )
        else:
            self._consecutive_errors = 0  # Reset on good update

        self._data = all_data
        return self._data

    def get_update_statistics(self) -> dict[str, Any]:
        """Return coordinator update metrics for diagnostics and system health.

        Returns:
            Dictionary containing update statistics and performance metrics
        """
        successful_updates = max(self._update_count - self._error_count, 0)
        cache_metrics = self._modules.cache_metrics()
        cache_entries = cache_metrics.entries
        cache_hit_rate = cache_metrics.hit_rate

        return {
            "update_counts": {
                "total": self._update_count,
                "successful": successful_updates,
                "failed": self._error_count,
                "consecutive_errors": self._consecutive_errors,
            },
            "performance_metrics": {
                "api_calls": self._update_count if self._use_external_api else 0,
                "cache_entries": cache_entries,
                "cache_hit_rate": round(cache_hit_rate, 1),
                "cache_ttl": CACHE_TTL_SECONDS,
            },
            "health_indicators": {
                "success_rate": round(
                    (successful_updates / max(self._update_count, 1)) * 100, 1
                ),
                "is_healthy": self._consecutive_errors < 3,
                "external_api_enabled": self._use_external_api,
            },
        }

    async def _fetch_dog_data(self, dog_id: str) -> dict[str, Any]:
        """Fetch data for a single dog with enhanced error handling.

        Args:
            dog_id: Dog identifier

        Returns:
            Dog data dictionary

        Raises:
            ValidationError: If dog configuration is invalid
            NetworkError: If network-related errors occur
            ConfigEntryAuthFailed: If authentication fails
        """
        dog_config = self.get_dog_config(dog_id)
        if not dog_config:
            raise ValidationError("dog_id", dog_id, "Dog configuration not found")

        data = {
            "dog_info": dog_config,
            "status": "online",
            "last_update": dt_util.utcnow().isoformat(),
        }

        modules = dog_config.get("modules", {})

        # PLATINUM: Enhanced module data fetching with dedicated adapters
        module_tasks = self._modules.build_tasks(dog_id, modules)

        # Execute module tasks concurrently with enhanced error handling
        if module_tasks:
            results = await asyncio.gather(
                *(task for _, task in module_tasks), return_exceptions=True
            )

            for (module_name, _), result in zip(module_tasks, results, strict=False):
                if isinstance(result, Exception):
                    # PLATINUM: Module-specific error handling
                    if isinstance(result, GPSUnavailableError):
                        _LOGGER.debug("GPS unavailable for %s: %s", dog_id, result)
                        data[module_name] = {
                            "status": "unavailable",
                            "reason": str(result),
                        }
                    elif isinstance(result, NetworkError):
                        _LOGGER.warning(
                            "Network error fetching %s data for %s: %s",
                            module_name,
                            dog_id,
                            result,
                        )
                        data[module_name] = {"status": "network_error"}
                    else:
                        _LOGGER.warning(
                            "Failed to fetch %s data for %s: %s (%s)",
                            module_name,
                            dog_id,
                            result,
                            result.__class__.__name__,
                        )
                        data[module_name] = {"status": "error"}
                else:
                    data[module_name] = result

        return data

    def _get_empty_dog_data(self) -> dict[str, Any]:
        """Get empty dog data structure.

        Returns:
            Empty dog data dictionary
        """
        return {
            "dog_info": {},
            "status": "unknown",
            "last_update": None,
            "feeding": {},
            "walk": {},
            "gps": {},
            "health": {},
        }

    def _calculate_update_interval(self) -> int:
        """Calculate optimized update interval with validation.

        Returns:
            Update interval in seconds

        Raises:
            ValueError: If configuration is invalid
        """
        if not self._dogs_config:
            return UPDATE_INTERVALS.get("minimal", 300)

        # Check for GPS requirements
        has_gps = any(
            dog.get("modules", {}).get(MODULE_GPS, False) for dog in self._dogs_config
        )

        if has_gps:
            gps_interval = self.config_entry.options.get(
                CONF_GPS_UPDATE_INTERVAL, UPDATE_INTERVALS.get("frequent", 60)
            )
            if not isinstance(gps_interval, int) or gps_interval <= 0:
                raise ValueError(f"Invalid GPS update interval: {gps_interval}")
            return gps_interval

        # Check for weather module - needs frequent updates for accurate health alerts
        has_weather = any(
            dog.get("modules", {}).get(MODULE_WEATHER, False)
            for dog in self._dogs_config
        )

        if has_weather:
            return UPDATE_INTERVALS.get("frequent", 60)

        # Calculate based on enabled modules
        total_modules = sum(
            sum(1 for enabled in dog.get("modules", {}).values() if enabled)
            for dog in self._dogs_config
        )

        if total_modules > 15:
            return UPDATE_INTERVALS.get("real_time", 30)
        elif total_modules > 8:
            return UPDATE_INTERVALS.get("balanced", 120)
        else:
            return UPDATE_INTERVALS.get("minimal", 300)

    # Public interface methods with enhanced documentation

    def get_dog_config(self, dog_id: str) -> DogConfigData | None:
        """Get dog configuration by ID.

        Args:
            dog_id: Dog identifier

        Returns:
            Dog configuration or None if not found
        """
        if not isinstance(dog_id, str):
            return None
        return self._dog_config_by_id.get(dog_id.strip())

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
        """Get enabled modules for dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Set of enabled module names
        """
        config = self.get_dog_config(dog_id)
        if not config:
            return frozenset()

        modules = config.get("modules", {})
        return frozenset(name for name, enabled in modules.items() if enabled)

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        """Check if module is enabled for dog.

        Args:
            dog_id: Dog identifier
            module: Module name

        Returns:
            True if module is enabled
        """
        return module in self.get_enabled_modules(dog_id)

    def get_dog_ids(self) -> list[str]:
        """Get all configured dog IDs.

        Returns:
            List of dog identifiers
        """
        return list(self._configured_dog_ids)

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        """Get data for specific dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Dog data or None if not found
        """
        return self._data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        """Get data for specific module.

        Args:
            dog_id: Dog identifier
            module: Module name

        Returns:
            Module data dictionary
        """
        return self._data.get(dog_id, {}).get(module, {})

    def get_configured_dog_ids(self) -> list[str]:
        """Return a list of configured dog identifiers."""

        return [dog_id for dog_id in self._configured_dog_ids]

    def get_configured_dog_name(self, dog_id: str) -> str | None:
        """Return the configured display name for a dog if available."""

        config = self.get_dog_config(dog_id)
        if not config:
            return None

        dog_name = config.get(CONF_DOG_NAME)
        if isinstance(dog_name, str) and dog_name.strip():
            return dog_name
        return None

    @property
    def available(self) -> bool:
        """Check if coordinator is available.

        Returns:
            True if coordinator is available and healthy
        """
        return self.last_update_success and self._consecutive_errors < 5

    def get_statistics(self) -> dict[str, Any]:
        """Get coordinator statistics.

        Returns:
            Statistics dictionary
        """
        cache_metrics = self._modules.cache_metrics()

        return {
            "total_dogs": len(self._dogs_config),
            "update_count": self._update_count,
            "error_count": self._error_count,
            "consecutive_errors": self._consecutive_errors,
            "error_rate": self._error_count / max(self._update_count, 1),
            "last_update": self.last_update_time,
            "update_interval": self.update_interval.total_seconds(),
            "cache_performance": {
                "hits": cache_metrics.hits,
                "misses": cache_metrics.misses,
                "hit_rate": cache_metrics.hit_rate / 100,
            },
        }

    @callback
    def async_start_background_tasks(self) -> None:
        """Start background maintenance tasks."""
        if self._maintenance_unsub is None:
            self._maintenance_unsub = async_track_time_interval(
                self.hass, self._async_maintenance, MAINTENANCE_INTERVAL
            )

    async def _async_maintenance(self, *_: Any) -> None:
        """Perform periodic maintenance with enhanced cache management.

        Args:
            *_: Unused arguments from time tracking
        """
        # PLATINUM: Enhanced cache cleanup
        now = dt_util.utcnow()
        expired = self._modules.cleanup_expired(now)

        if expired:
            _LOGGER.debug("Cleaned %d expired cache entries", expired)

        # Reset consecutive errors if we've been stable
        if self._consecutive_errors > 0 and self.last_update_success:
            hours_since_last_error = (
                now - (self.last_update_time or now)
            ).total_seconds() / 3600
            if hours_since_last_error > 1:  # 1 hour of stability
                old_errors = self._consecutive_errors
                self._consecutive_errors = 0
                _LOGGER.info(
                    "Reset consecutive error count (%d) after %d hours of stability",
                    old_errors,
                    int(hours_since_last_error),
                )

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and cleanup resources.

        Raises:
            Exception: If shutdown encounters critical errors
        """
        _LOGGER.debug("Shutting down coordinator")

        try:
            # Cancel maintenance task
            if self._maintenance_unsub:
                self._maintenance_unsub()
                self._maintenance_unsub = None

            # Clear data and cache
            self._data.clear()
            self._modules.clear_caches()

            _LOGGER.info("Coordinator shutdown completed successfully")

        except Exception as err:
            _LOGGER.error("Error during coordinator shutdown: %s", err)
            raise
