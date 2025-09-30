"""Coordinator for the PawControl integration."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import TYPE_CHECKING, Any

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
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
    CONF_EXTERNAL_INTEGRATIONS,
)
from .coordinator_support import CoordinatorMetrics, DogConfigRegistry, UpdateResult
from .device_api import PawControlDeviceClient
from .exceptions import GPSUnavailableError, NetworkError, ValidationError
from .module_adapters import CoordinatorModuleAdapters
from .resilience import ResilienceManager, RetryConfig
from .types import PawControlConfigEntry

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

API_TIMEOUT = 30.0
CACHE_TTL_SECONDS = 300
MAINTENANCE_INTERVAL = timedelta(hours=1)


@dataclass(slots=True)
class EntityBudgetSnapshot:
    """Snapshot of entity budget utilization for a single dog."""

    dog_id: str
    profile: str
    capacity: int
    base_allocation: int
    dynamic_allocation: int
    requested_entities: tuple[str, ...]
    denied_requests: tuple[str, ...]
    recorded_at: datetime

    @property
    def total_allocated(self) -> int:
        """Return the total number of allocated entities."""

        return self.base_allocation + self.dynamic_allocation

    @property
    def remaining(self) -> int:
        """Return the remaining capacity within the budget."""

        return max(self.capacity - self.total_allocated, 0)

    @property
    def saturation(self) -> float:
        """Return the saturation ratio for the entity budget."""

        if self.capacity <= 0:
            return 0.0
        return max(0.0, min(1.0, self.total_allocated / self.capacity))


class AdaptivePollingController:
    """Manage dynamic polling intervals based on runtime performance."""

    __slots__ = (
        "_history",
        "_min_interval",
        "_max_interval",
        "_target_cycle",
        "_current_interval",
        "_error_streak",
        "_entity_saturation",
    )

    def __init__(
        self,
        *,
        initial_interval_seconds: float,
        target_cycle_ms: float = 200.0,
        min_interval_seconds: float = 0.2,
        max_interval_seconds: float = 5.0,
    ) -> None:
        """Initialize the adaptive polling controller."""

        self._history: deque[float] = deque(maxlen=32)
        self._min_interval = max(min_interval_seconds, 0.05)
        self._max_interval = max(max_interval_seconds, self._min_interval)
        self._target_cycle = max(target_cycle_ms / 1000.0, self._min_interval)
        self._current_interval = min(
            max(initial_interval_seconds, self._min_interval), self._max_interval
        )
        self._error_streak = 0
        self._entity_saturation = 0.0

    @property
    def current_interval(self) -> float:
        """Return the current polling interval in seconds."""

        return self._current_interval

    def update_entity_saturation(self, saturation: float) -> None:
        """Update entity saturation feedback for adaptive decisions."""

        self._entity_saturation = max(0.0, min(1.0, saturation))

    def record_cycle(
        self,
        *,
        duration: float,
        success: bool,
        error_ratio: float,
    ) -> float:
        """Record an update cycle and return the next interval in seconds."""

        self._history.append(max(duration, 0.0))
        if success:
            self._error_streak = 0
        else:
            self._error_streak += 1

        average_duration = self._history[-1]
        if len(self._history) > 1:
            average_duration = fmean(self._history)

        next_interval = self._current_interval

        if not success:
            # Back off quickly when consecutive errors occur
            penalty_factor = 1.0 + min(0.5, 0.15 * self._error_streak + error_ratio)
            next_interval = min(self._max_interval, next_interval * penalty_factor)
        else:
            load_factor = 1.0 + (self._entity_saturation * 0.5)
            if average_duration < self._target_cycle * 0.8:
                reduction_factor = min(2.0, (self._target_cycle / average_duration) * 0.5)
                next_interval = max(
                    self._min_interval,
                    next_interval / max(1.0, reduction_factor * load_factor),
                )
            elif average_duration > self._target_cycle * 1.1:
                increase_factor = min(2.5, average_duration / self._target_cycle)
                next_interval = min(
                    self._max_interval,
                    next_interval * (increase_factor * load_factor),
                )

        self._current_interval = max(
            self._min_interval, min(self._max_interval, next_interval)
        )
        return self._current_interval

    def as_diagnostics(self) -> dict[str, Any]:
        """Return diagnostics for adaptive polling behaviour."""

        history_count = len(self._history)
        average_duration = fmean(self._history) if history_count else 0.0
        return {
            "target_cycle_ms": round(self._target_cycle * 1000, 2),
            "current_interval_ms": round(self._current_interval * 1000, 2),
            "average_cycle_ms": round(average_duration * 1000, 2),
            "history_samples": history_count,
            "error_streak": self._error_streak,
            "entity_saturation": round(self._entity_saturation, 3),
        }

class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Central data coordinator with a compact, testable core."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PawControlConfigEntry,
        session: ClientSession | None = None,
    ) -> None:
        self.config_entry = entry
        self.session = session or async_get_clientsession(hass)
        self.registry = DogConfigRegistry.from_entry(entry)
        self._configured_dog_ids = self.registry.ids()
        self._use_external_api = bool(
            entry.options.get(CONF_EXTERNAL_INTEGRATIONS, False)
        )
        self._api_client = self._build_api_client(
            endpoint=entry.options.get(CONF_API_ENDPOINT, ""),
            token=entry.options.get(CONF_API_TOKEN, ""),
        )

        # Calculate update interval with validation
        try:
            update_interval = self._calculate_update_interval()
            if update_interval <= 0:
                raise ValueError("Update interval must be positive")
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Invalid update interval calculation: %s", err)
            update_interval = UPDATE_INTERVALS.get("balanced", 120)

        # Initialize adaptive polling controller with calculated interval
        self._adaptive_polling = AdaptivePollingController(
            initial_interval_seconds=float(update_interval)
        )

        # PLATINUM: Pass config_entry to coordinator for proper type safety
        update_interval = self.registry.calculate_update_interval(entry.options)
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

        self._data: dict[str, dict[str, Any]] = {
            dog_id: self.registry.empty_payload() for dog_id in self._configured_dog_ids
        }
        self._metrics = CoordinatorMetrics()
        self._maintenance_unsub: callback | None = None
        self._setup_complete = False
        self._entity_budget_snapshots: dict[str, EntityBudgetSnapshot] = {}

        self.data_manager: PawControlDataManager | None = None
        self.feeding_manager: FeedingManager | None = None
        self.walk_manager: WalkManager | None = None
        self.notification_manager: PawControlNotificationManager | None = None
        self.gps_geofence_manager: GPSGeofenceManager | None = None
        self.geofencing_manager: PawControlGeofencing | None = None
        self.weather_health_manager: WeatherHealthManager | None = None
        self.garden_manager: GardenManager | None = None

        self.resilience_manager = ResilienceManager(hass)
        self._retry_config = RetryConfig(
            max_attempts=2,
            initial_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=True,
        )

        _LOGGER.info(
            "Coordinator initialised: %d dogs, %ds interval, external_api=%s",
            len(self.registry),
            update_interval,
            self._use_external_api,
        )

    def _build_api_client(
        self, *, endpoint: str, token: str
    ) -> PawControlDeviceClient | None:
        if not endpoint:
            return None
        try:
            return PawControlDeviceClient(
                session=self.session,
                endpoint=endpoint.strip(),
                api_key=token.strip() or None,
            )
        except ValueError as err:
            _LOGGER.warning("Invalid Paw Control API endpoint '%s': %s", endpoint, err)
            return None

    @property
    def use_external_api(self) -> bool:
        return self._use_external_api

    @use_external_api.setter
    def use_external_api(self, value: bool) -> None:
        self._use_external_api = bool(value)

    @property
    def api_client(self) -> PawControlDeviceClient | None:
        return self._api_client

    def report_entity_budget(self, snapshot: EntityBudgetSnapshot) -> None:
        """Receive entity budget metrics from the entity factory."""

        self._entity_budget_snapshots[snapshot.dog_id] = snapshot
        self._adaptive_polling.update_entity_saturation(
            self._calculate_entity_saturation()
        )

    def _calculate_entity_saturation(self) -> float:
        """Calculate aggregate entity saturation across all dogs."""

        if not self._entity_budget_snapshots:
            return 0.0

        total_capacity = sum(
            snapshot.capacity for snapshot in self._entity_budget_snapshots.values()
        )
        if total_capacity <= 0:
            return 0.0

        total_allocated = sum(
            snapshot.total_allocated
            for snapshot in self._entity_budget_snapshots.values()
        )
        saturation = total_allocated / total_capacity
        return max(0.0, min(1.0, saturation))

    def _summarize_entity_budgets(self) -> dict[str, Any]:
        """Summarize entity budget usage for diagnostics."""

        if not self._entity_budget_snapshots:
            return {
                "active_dogs": 0,
                "total_capacity": 0,
                "total_allocated": 0,
                "total_remaining": 0,
                "average_utilization": 0.0,
                "peak_utilization": 0.0,
                "denied_requests": 0,
            }

        snapshots = list(self._entity_budget_snapshots.values())
        total_capacity = sum(snapshot.capacity for snapshot in snapshots)
        total_allocated = sum(snapshot.total_allocated for snapshot in snapshots)
        total_remaining = sum(snapshot.remaining for snapshot in snapshots)
        denied_requests = sum(len(snapshot.denied_requests) for snapshot in snapshots)
        average_utilization = (
            (total_allocated / total_capacity) if total_capacity else 0.0
        )
        peak_utilization = max((snapshot.saturation for snapshot in snapshots), default=0.0)

        return {
            "active_dogs": len(snapshots),
            "total_capacity": total_capacity,
            "total_allocated": total_allocated,
            "total_remaining": total_remaining,
            "average_utilization": round(average_utilization * 100, 1),
            "peak_utilization": round(peak_utilization * 100, 1),
            "denied_requests": denied_requests,
        }

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

    def clear_runtime_managers(self) -> None:
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
        if self._setup_complete:
            return
        self._data.update(
            {
                dog_id: self.registry.empty_payload()
                for dog_id in self._configured_dog_ids
            }
        )
        self._modules.clear_caches()
        self._setup_complete = True

    async def _async_update_data(self) -> dict[str, Any]:
        if len(self.registry) == 0:
            return {}

        self._update_count += 1
        all_data: dict[str, dict[str, Any]] = {}
        errors = 0
        cycle_start = time.perf_counter()
        update_success = False

        # PLATINUM: Enhanced dog ID validation
        dog_ids: list[str] = []
        for dog in self._dogs_config:
            dog_id = dog.get(CONF_DOG_ID)
            if isinstance(dog_id, str) and dog_id.strip():
                dog_ids.append(dog_id.strip())
            else:
                _LOGGER.warning("Skipping dog with invalid identifier: %s", dog_id)
        await self._async_setup()

        dog_ids = list(self._configured_dog_ids)
        if not dog_ids:
            raise CoordinatorUpdateFailed("No valid dogs configured")

        try:
            # RESILIENCE: Enhanced concurrent fetch with resilience patterns
            async def fetch_and_store(dog_id: str) -> None:
                nonlocal errors

                try:
                    result = await self.resilience_manager.execute_with_resilience(
                        self._fetch_dog_data_protected,
                        dog_id,
                        circuit_breaker_name=f"dog_data_{dog_id}",
                        retry_config=self._retry_config,
                    )
                    all_data[dog_id] = result
                    return

                except ConfigEntryAuthFailed:
                    errors += 1
                    raise
                except ValidationError as err:
                    errors += 1
                    _LOGGER.error("Invalid configuration for dog %s: %s", dog_id, err)
                    all_data[dog_id] = self._get_empty_dog_data()
                except Exception as err:
                    errors += 1
                    _LOGGER.error(
                        "Resilience patterns exhausted for dog %s: %s (%s)",
                        dog_id,
                        err,
                        err.__class__.__name__,
                    )
                    all_data[dog_id] = self._data.get(
                        dog_id, self._get_empty_dog_data()
                    )

            try:
                async with asyncio.TaskGroup() as task_group:
                    for dog_id in dog_ids:
                        task_group.create_task(fetch_and_store(dog_id))
            except* ConfigEntryAuthFailed as auth_error_group:
                raise auth_error_group.exceptions[0]  # noqa: B904
            except* Exception as error_group:
                for exc in error_group.exceptions:
                    _LOGGER.error("Task group error: %s", exc)

            # PLATINUM: Enhanced failure analysis
            total_dogs = len(dog_ids)
            success_rate = (
                (total_dogs - errors) / total_dogs if total_dogs > 0 else 0
            )

            if errors == total_dogs:
                self._error_count += 1
                self._consecutive_errors += 1
                raise CoordinatorUpdateFailed(
                    f"All {total_dogs} dogs failed to update"
                )

            if success_rate < 0.5:
                self._consecutive_errors += 1
                _LOGGER.warning(
                    "Low success rate: %d/%d dogs updated successfully",
                    total_dogs - errors,
                    total_dogs,
                )
            else:
                self._consecutive_errors = 0

            self._data = all_data
            update_success = True
            return self._data

        finally:
            duration = max(time.perf_counter() - cycle_start, 0.0)
            error_ratio = errors / len(dog_ids) if dog_ids else 0.0
            new_interval = self._adaptive_polling.record_cycle(
                duration=duration,
                success=update_success,
                error_ratio=error_ratio,
            )

            current_seconds = self.update_interval.total_seconds()
            if abs(current_seconds - new_interval) > 0.01:
                _LOGGER.debug(
                    "Adaptive polling adjusted interval from %.3fs to %.3fs",  # pragma: no cover - log only
                    current_seconds,
                    new_interval,
                )

            self.update_interval = timedelta(seconds=new_interval)
        self._metrics.start_cycle()
        result = await self._fetch_all_dogs(dog_ids)

        success_rate, all_failed = self._metrics.record_cycle(
            len(dog_ids), result.errors
        )
        if all_failed:
            raise CoordinatorUpdateFailed(f"All {len(dog_ids)} dogs failed to update")

        if success_rate < 0.5:
            _LOGGER.warning(
                "Low success rate: %d/%d dogs updated successfully",
                len(dog_ids) - result.errors,
                len(dog_ids),
            )

        self._data = result.payload
        return self._data

    async def _fetch_all_dogs(self, dog_ids: list[str]) -> UpdateResult:
        result = UpdateResult()

        Returns:
            Dictionary containing update statistics and performance metrics
        """
        successful_updates = max(self._update_count - self._error_count, 0)
        cache_metrics = self._modules.cache_metrics()
        cache_entries = cache_metrics.entries
        cache_hit_rate = cache_metrics.hit_rate
        entity_budget_summary = self._summarize_entity_budgets()
        adaptive_metrics = self._adaptive_polling.as_diagnostics()

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
            "entity_budget": entity_budget_summary,
            "adaptive_polling": adaptive_metrics,
        }
        tasks = [self._fetch_with_resilience(dog_id) for dog_id in dog_ids]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for dog_id, response in zip(dog_ids, responses, strict=True):
            if isinstance(response, ConfigEntryAuthFailed):
                raise response
            if isinstance(response, ValidationError):
                _LOGGER.error("Invalid configuration for dog %s: %s", dog_id, response)
                result.add_error(dog_id, self.registry.empty_payload())
            elif isinstance(response, Exception):
                _LOGGER.error(
                    "Resilience exhausted for dog %s: %s (%s)",
                    dog_id,
                    response,
                    response.__class__.__name__,
                )
                result.add_error(
                    dog_id,
                    self._data.get(dog_id, self.registry.empty_payload()),
                )
            else:
                result.add_success(dog_id, response)

        return result

    async def _fetch_with_resilience(self, dog_id: str) -> dict[str, Any]:
        return await self.resilience_manager.execute_with_resilience(
            self._fetch_dog_data_protected,
            dog_id,
            circuit_breaker_name=f"dog_data_{dog_id}",
            retry_config=self._retry_config,
        )

    async def _fetch_dog_data_protected(self, dog_id: str) -> dict[str, Any]:
        async with asyncio.timeout(API_TIMEOUT):
            return await self._fetch_dog_data(dog_id)

    async def _fetch_dog_data(self, dog_id: str) -> dict[str, Any]:
        dog_config = self.registry.get(dog_id)
        if not dog_config:
            raise ValidationError("dog_id", dog_id, "Dog configuration not found")

        payload = {
            "dog_info": dog_config,
            "status": "online",
            "last_update": dt_util.utcnow().isoformat(),
        }

        modules = dog_config.get("modules", {})
        module_tasks = self._modules.build_tasks(dog_id, modules)
        if not module_tasks:
            return payload

        results = await asyncio.gather(
            *(task for _, task in module_tasks), return_exceptions=True
        )

        for (module_name, _), result in zip(module_tasks, results, strict=True):
            if isinstance(result, GPSUnavailableError):
                _LOGGER.debug("GPS unavailable for %s: %s", dog_id, result)
                payload[module_name] = {"status": "unavailable", "reason": str(result)}
            elif isinstance(result, NetworkError):
                _LOGGER.warning(
                    "Network error fetching %s data for %s: %s",
                    module_name,
                    dog_id,
                    result,
                )
                payload[module_name] = {"status": "network_error"}
            elif isinstance(result, Exception):
                _LOGGER.warning(
                    "Failed to fetch %s data for %s: %s (%s)",
                    module_name,
                    dog_id,
                    result,
                    result.__class__.__name__,
                )
                payload[module_name] = {"status": "error"}
            else:
                payload[module_name] = result

        return payload

    def get_dog_config(self, dog_id: str) -> Any:
        return self.registry.get(dog_id)

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
        return self.registry.enabled_modules(dog_id)

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        return module in self.registry.enabled_modules(dog_id)

    def get_dog_ids(self) -> list[str]:
        return list(self._configured_dog_ids)

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        return self._data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        return self._data.get(dog_id, {}).get(module, {})

    def get_configured_dog_ids(self) -> list[str]:
        return list(self._configured_dog_ids)

    def get_configured_dog_name(self, dog_id: str) -> str | None:
        return self.registry.get_name(dog_id)

    @property
    def available(self) -> bool:
        return self.last_update_success and self._metrics.consecutive_errors < 5

    def get_update_statistics(self) -> dict[str, Any]:
        cache_metrics = self._modules.cache_metrics()
        return self._metrics.update_statistics(
            cache_entries=cache_metrics.entries,
            cache_hit_rate=cache_metrics.hit_rate,
            last_update=self.last_update_time,
            interval=self.update_interval,
        )

    def get_statistics(self) -> dict[str, Any]:
        cache_metrics = self._modules.cache_metrics()
        stats = self._metrics.runtime_statistics(
            cache_metrics=cache_metrics,
            total_dogs=len(self.registry),
            last_update=self.last_update_time,
            interval=self.update_interval,
        )
        stats["resilience"] = self.resilience_manager.get_all_circuit_breakers()
        return stats

    @callback
    def async_start_background_tasks(self) -> None:
        if self._maintenance_unsub is None:
            self._maintenance_unsub = async_track_time_interval(
                self.hass, self._async_maintenance, MAINTENANCE_INTERVAL
            )

    async def _async_maintenance(self, *_: Any) -> None:
        now = dt_util.utcnow()
        expired = self._modules.cleanup_expired(now)
        if expired:
            _LOGGER.debug("Cleaned %d expired cache entries", expired)

        if self._metrics.consecutive_errors > 0 and self.last_update_success:
            hours_since_last_update = (
                now - (self.last_update_time or now)
            ).total_seconds() / 3600
            if hours_since_last_update > 1:
                previous = self._metrics.consecutive_errors
                self._metrics.reset_consecutive()
                _LOGGER.info(
                    "Reset consecutive error count (%d) after %d hours of stability",
                    previous,
                    int(hours_since_last_update),
                )

    async def async_shutdown(self) -> None:
        if self._maintenance_unsub:
            self._maintenance_unsub()
            self._maintenance_unsub = None

        self._data.clear()
        self._modules.clear_caches()
        _LOGGER.info("Coordinator shutdown completed successfully")
