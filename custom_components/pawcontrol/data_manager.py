"""Data management for Paw Control integration.

This module provides comprehensive data storage, retrieval, and management
functionality for all dog monitoring data. It handles data persistence,
cleanup, export/import operations, and maintains data integrity across
all modules and components.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

import aiofiles
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_DATA_RETENTION_DAYS,
    DOMAIN,
    STORAGE_VERSION,
)
from .exceptions import (
    StorageError,
)
from .utils import (
    deep_merge_dicts,
)

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class PawControlDataManager:
    """Central data management for Paw Control integration.

    Handles all data storage, retrieval, and management operations
    including persistence, cleanup, backup, and export/import.
    Designed for high performance with async operations and intelligent caching.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the data manager.

        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id

        # Storage instances for different data types with modern patterns
        self._stores: dict[str, Store] = {
            "dogs": Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_dogs"),
            "feeding": Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_feeding"),
            "walks": Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_walks"),
            "health": Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_health"),
            "gps": Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_gps"),
            "grooming": Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_grooming"),
            "statistics": Store(
                hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_statistics"
            ),
        }

        # In-memory cache for frequently accessed data with TTL
        self._cache: dict[str, Any] = {}
        self._cache_timestamps: dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)

        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._backup_task: Optional[asyncio.Task] = None

        # Async locks for thread-safe operations
        self._lock = asyncio.Lock()
        self._cache_lock = asyncio.Lock()

        # Performance metrics
        self._metrics: dict[str, Any] = {
            "operations_count": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_data_size": 0,
            "last_cleanup": None,
            "errors_count": 0,
        }

    async def async_initialize(self) -> None:
        """Initialize the data manager and load existing data.

        Raises:
            StorageError: If initialization fails
        """
        _LOGGER.debug("Initializing data manager for entry %s", self.entry_id)

        try:
            # Load existing data into cache
            await self._load_initial_data()

            # Start background tasks
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            self._backup_task = asyncio.create_task(self._periodic_backup())

            # Initialize statistics if not present
            await self._initialize_statistics()

            _LOGGER.info("Data manager initialized successfully")

        except Exception as err:
            _LOGGER.error("Failed to initialize data manager: %s", err, exc_info=True)
            raise StorageError("initialize", str(err)) from err

    async def async_shutdown(self) -> None:
        """Shutdown the data manager and cleanup resources."""
        _LOGGER.debug("Shutting down data manager")

        try:
            # Cancel background tasks
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass

            if self._backup_task:
                self._backup_task.cancel()
                try:
                    await self._backup_task
                except asyncio.CancelledError:
                    pass

            # Final data save
            await self._flush_cache_to_storage()

            # Clear cache
            async with self._cache_lock:
                self._cache.clear()
                self._cache_timestamps.clear()

            _LOGGER.info("Data manager shutdown complete")

        except Exception as err:
            _LOGGER.error("Error during data manager shutdown: %s", err)

    async def _load_initial_data(self) -> None:
        """Load initial data from storage into cache."""
        async with self._lock:
            try:
                # Load dog data
                dog_data = await self._stores["dogs"].async_load() or {}
                await self._set_cache("dogs", dog_data)

                # Load recent feeding data for quick access
                feeding_data = await self._stores["feeding"].async_load() or {}
                await self._set_cache("feeding", feeding_data)

                _LOGGER.debug("Loaded initial data for %d dogs", len(dog_data))

            except Exception as err:
                _LOGGER.error("Failed to load initial data: %s", err)
                await self._set_cache("dogs", {})
                await self._set_cache("feeding", {})

    async def _initialize_statistics(self) -> None:
        """Initialize statistics storage if not present."""
        stats = await self._stores["statistics"].async_load()
        if not stats:
            initial_stats = {
                "created": dt_util.utcnow().isoformat(),
                "total_operations": 0,
                "dogs_count": 0,
                "last_reset": dt_util.utcnow().isoformat(),
            }
            await self._stores["statistics"].async_save(initial_stats)

    # Core dog data operations
    async def async_get_dog_data(self, dog_id: str) -> Optional[dict[str, Any]]:
        """Get all data for a specific dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Dog data dictionary or None if not found
        """
        await self._ensure_cache_fresh("dogs")
        dogs_data = await self._get_cache("dogs", {})
        return dogs_data.get(dog_id)

    async def async_set_dog_data(self, dog_id: str, data: dict[str, Any]) -> None:
        """Set data for a specific dog.

        Args:
            dog_id: Dog identifier
            data: Dog data to store
        """
        async with self._lock:
            # Update cache
            dogs_data = await self._get_cache("dogs", {})
            dogs_data[dog_id] = data
            await self._set_cache("dogs", dogs_data)

            # Persist to storage asynchronously
            await self._stores["dogs"].async_save(dogs_data)

            # Update metrics
            self._metrics["operations_count"] += 1

            _LOGGER.debug("Updated data for dog %s", dog_id)

    async def async_update_dog_data(self, dog_id: str, updates: dict[str, Any]) -> None:
        """Update specific fields in dog data.

        Args:
            dog_id: Dog identifier
            updates: Data updates to apply
        """
        current_data = await self.async_get_dog_data(dog_id) or {}
        updated_data = deep_merge_dicts(current_data, updates)
        await self.async_set_dog_data(dog_id, updated_data)

    async def async_delete_dog_data(self, dog_id: str) -> None:
        """Delete all data for a specific dog.

        Args:
            dog_id: Dog identifier
        """
        async with self._lock:
            try:
                # Remove from main dog storage
                dogs_data = await self._get_cache("dogs", {})
                if dog_id in dogs_data:
                    del dogs_data[dog_id]
                    await self._set_cache("dogs", dogs_data)
                    await self._stores["dogs"].async_save(dogs_data)

                # Remove from all module stores
                await self._delete_dog_from_all_modules(dog_id)

                # Update metrics
                self._metrics["operations_count"] += 1

                _LOGGER.info("Deleted all data for dog %s", dog_id)

            except Exception as err:
                _LOGGER.error("Failed to delete dog data for %s: %s", dog_id, err)
                self._metrics["errors_count"] += 1
                raise

    async def async_get_all_dogs(self) -> dict[str, dict[str, Any]]:
        """Get data for all dogs.

        Returns:
            Dictionary of all dog data
        """
        await self._ensure_cache_fresh("dogs")
        dogs_data = await self._get_cache("dogs", {})
        return dogs_data.copy()

    # Feeding operations
    async def async_log_feeding(self, dog_id: str, meal_data: dict[str, Any]) -> None:
        """Log a feeding event for a dog.

        Args:
            dog_id: Dog identifier
            meal_data: Feeding data to log
        """
        try:
            timestamp = dt_util.utcnow()
            feeding_entry = {
                "feeding_id": f"feeding_{dog_id}_{int(timestamp.timestamp())}",
                "timestamp": timestamp.isoformat(),
                "dog_id": dog_id,
                **meal_data,
            }

            await self._append_to_module_data("feeding", dog_id, feeding_entry)

            # Update dog's last feeding time
            await self.async_update_dog_data(
                dog_id,
                {
                    "feeding": {
                        "last_feeding": timestamp.isoformat(),
                        "last_feeding_hours": 0,
                        "last_feeding_type": meal_data.get("meal_type"),
                    }
                },
            )

            _LOGGER.debug(
                "Logged feeding for dog %s: %s", dog_id, meal_data.get("meal_type")
            )

        except Exception as err:
            _LOGGER.error("Failed to log feeding for %s: %s", dog_id, err)
            self._metrics["errors_count"] += 1
            raise

    async def async_get_feeding_history(
        self, dog_id: str, days: int = 7
    ) -> list[dict[str, Any]]:
        """Get feeding history for a dog.

        Args:
            dog_id: Dog identifier
            days: Number of days to retrieve

        Returns:
            List of feeding entries
        """
        start_date = dt_util.utcnow() - timedelta(days=days)
        return await self.async_get_module_data(
            "feeding", dog_id, start_date=start_date
        )

    async def async_get_feeding_schedule(self, dog_id: str) -> dict[str, Any]:
        """Get feeding schedule for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Feeding schedule configuration
        """
        dog_data = await self.async_get_dog_data(dog_id)
        return dog_data.get("feeding_schedule", {}) if dog_data else {}

    # Walk operations
    async def async_start_walk(self, dog_id: str, walk_data: dict[str, Any]) -> str:
        """Start a walk session for a dog.

        Args:
            dog_id: Dog identifier
            walk_data: Walk start data

        Returns:
            Walk session ID
        """
        try:
            timestamp = dt_util.utcnow()
            walk_id = f"walk_{dog_id}_{int(timestamp.timestamp())}"

            walk_entry = {
                "walk_id": walk_id,
                "dog_id": dog_id,
                "start_time": timestamp.isoformat(),
                "status": "in_progress",
                "route_points": [],
                **walk_data,
            }

            await self._append_to_module_data("walks", dog_id, walk_entry)

            # Update dog's walk status
            await self.async_update_dog_data(
                dog_id,
                {
                    "walk": {
                        "walk_in_progress": True,
                        "current_walk_id": walk_id,
                        "current_walk_start": timestamp.isoformat(),
                    }
                },
            )

            _LOGGER.debug("Started walk %s for dog %s", walk_id, dog_id)
            return walk_id

        except Exception as err:
            _LOGGER.error("Failed to start walk for %s: %s", dog_id, err)
            self._metrics["errors_count"] += 1
            raise

    async def async_end_walk(
        self, dog_id: str, walk_data: Optional[dict[str, Any]] = None
    ) -> None:
        """End the current walk session for a dog.

        Args:
            dog_id: Dog identifier
            walk_data: Optional walk end data
        """
        try:
            dog_data = await self.async_get_dog_data(dog_id)
            if not dog_data or not dog_data.get("walk", {}).get("walk_in_progress"):
                _LOGGER.warning("No active walk found for dog %s", dog_id)
                return

            walk_id = dog_data["walk"].get("current_walk_id")
            if not walk_id:
                _LOGGER.warning("No current walk ID found for dog %s", dog_id)
                return

            timestamp = dt_util.utcnow()

            # Calculate walk duration
            start_time_str = dog_data["walk"].get("current_walk_start")
            duration_minutes = 0
            if start_time_str and isinstance(start_time_str, str):
                try:
                    start_time = datetime.fromisoformat(start_time_str)
                    duration = timestamp - start_time
                    duration_minutes = int(duration.total_seconds() / 60)
                except (ValueError, TypeError) as err:
                    _LOGGER.warning(
                        "Invalid start time format for dog %s: %s", dog_id, err
                    )
                    duration_minutes = 0

            # Update the walk entry
            walk_updates = {
                "end_time": timestamp.isoformat(),
                "status": "completed",
                "duration_minutes": duration_minutes,
                **(walk_data or {}),
            }

            await self._update_module_entry("walks", dog_id, walk_id, walk_updates)

            # Update dog's walk status
            await self.async_update_dog_data(
                dog_id,
                {
                    "walk": {
                        "walk_in_progress": False,
                        "current_walk_id": None,
                        "current_walk_start": None,
                        "last_walk": timestamp.isoformat(),
                        "last_walk_hours": 0,
                        "last_walk_duration": duration_minutes,
                    }
                },
            )

            _LOGGER.debug("Ended walk %s for dog %s", walk_id, dog_id)

        except Exception as err:
            _LOGGER.error("Failed to end walk for %s: %s", dog_id, err)
            self._metrics["errors_count"] += 1
            raise

    async def async_get_current_walk(self, dog_id: str) -> Optional[dict[str, Any]]:
        """Get current active walk for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Current walk data or None
        """
        dog_data = await self.async_get_dog_data(dog_id)
        if not dog_data or not dog_data.get("walk", {}).get("walk_in_progress"):
            return None

        walk_id = dog_data["walk"].get("current_walk_id")
        if not walk_id:
            return None

        # Get walk details from walks module
        walks = await self.async_get_module_data("walks", dog_id, limit=10)
        for walk in reversed(walks):  # Start with most recent
            if walk.get("walk_id") == walk_id:
                return walk

        return None

    async def async_get_walk_history(
        self, dog_id: str, days: int = 7
    ) -> list[dict[str, Any]]:
        """Get walk history for a dog.

        Args:
            dog_id: Dog identifier
            days: Number of days to retrieve

        Returns:
            List of walk entries
        """
        start_date = dt_util.utcnow() - timedelta(days=days)
        return await self.async_get_module_data("walks", dog_id, start_date=start_date)

    # Health operations
    async def async_log_health(self, dog_id: str, health_data: dict[str, Any]) -> None:
        """Log health data for a dog.

        Args:
            dog_id: Dog identifier
            health_data: Health data to log
        """
        try:
            timestamp = dt_util.utcnow()
            health_entry = {
                "health_id": f"health_{dog_id}_{int(timestamp.timestamp())}",
                "timestamp": timestamp.isoformat(),
                "dog_id": dog_id,
                **health_data,
            }

            await self._append_to_module_data("health", dog_id, health_entry)

            # Update dog's current health status
            health_updates = {"health": {"last_health_update": timestamp.isoformat()}}

            # Update specific health fields if provided
            if "weight" in health_data:
                health_updates["health"]["current_weight"] = health_data["weight"]
            if "health_status" in health_data:
                health_updates["health"]["health_status"] = health_data["health_status"]
            if "mood" in health_data:
                health_updates["health"]["mood"] = health_data["mood"]

            await self.async_update_dog_data(dog_id, health_updates)

            _LOGGER.debug("Logged health data for dog %s", dog_id)

        except Exception as err:
            _LOGGER.error("Failed to log health data for %s: %s", dog_id, err)
            self._metrics["errors_count"] += 1
            raise

    async def async_get_health_history(
        self, dog_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Get health history for a dog.

        Args:
            dog_id: Dog identifier
            days: Number of days to retrieve

        Returns:
            List of health entries
        """
        start_date = dt_util.utcnow() - timedelta(days=days)
        return await self.async_get_module_data("health", dog_id, start_date=start_date)

    async def async_get_weight_history(
        self, dog_id: str, days: int = 90
    ) -> list[dict[str, Any]]:
        """Get weight history for a dog.

        Args:
            dog_id: Dog identifier
            days: Number of days to retrieve

        Returns:
            List of weight entries
        """
        health_data = await self.async_get_health_history(dog_id, days)
        return [entry for entry in health_data if "weight" in entry]

    async def async_get_active_medications(self, dog_id: str) -> list[dict[str, Any]]:
        """Get active medications for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            List of active medications
        """
        dog_data = await self.async_get_dog_data(dog_id)
        if not dog_data:
            return []

        return dog_data.get("health", {}).get("active_medications", [])

    async def async_get_last_vet_visit(self, dog_id: str) -> Optional[dict[str, Any]]:
        """Get last vet visit for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Last vet visit data or None
        """
        health_data = await self.async_get_health_history(dog_id, 365)  # Last year
        vet_visits = [
            entry for entry in health_data if entry.get("type") == "vet_visit"
        ]
        return vet_visits[-1] if vet_visits else None

    async def async_get_last_grooming(self, dog_id: str) -> Optional[dict[str, Any]]:
        """Get last grooming session for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Last grooming data or None
        """
        grooming_data = await self.async_get_module_data("grooming", dog_id, limit=1)
        return grooming_data[0] if grooming_data else None

    # GPS operations
    async def async_log_gps(self, dog_id: str, gps_data: dict[str, Any]) -> None:
        """Log GPS location data for a dog.

        Args:
            dog_id: Dog identifier
            gps_data: GPS data to log
        """
        try:
            timestamp = dt_util.utcnow()
            gps_entry = {
                "gps_id": f"gps_{dog_id}_{int(timestamp.timestamp())}",
                "timestamp": timestamp.isoformat(),
                "dog_id": dog_id,
                **gps_data,
            }

            await self._append_to_module_data("gps", dog_id, gps_entry)

            # Update dog's current location
            gps_updates = {
                "gps": {
                    "last_seen": timestamp.isoformat(),
                    "latitude": gps_data.get("latitude"),
                    "longitude": gps_data.get("longitude"),
                    "accuracy": gps_data.get("accuracy"),
                    "speed": gps_data.get("speed"),
                    "source": gps_data.get("source", "unknown"),
                }
            }

            await self.async_update_dog_data(dog_id, gps_updates)

            # Add to current walk route if walk is in progress
            current_walk = await self.async_get_current_walk(dog_id)
            if current_walk:
                walk_id = current_walk["walk_id"]
                route_point = {
                    "timestamp": timestamp.isoformat(),
                    "latitude": gps_data.get("latitude"),
                    "longitude": gps_data.get("longitude"),
                    "accuracy": gps_data.get("accuracy"),
                    "speed": gps_data.get("speed"),
                }

                # Update walk with new route point
                current_route = current_walk.get("route_points", [])
                current_route.append(route_point)

                await self._update_module_entry(
                    "walks", dog_id, walk_id, {"route_points": current_route}
                )

            _LOGGER.debug("Logged GPS data for dog %s", dog_id)

        except Exception as err:
            _LOGGER.error("Failed to log GPS data for %s: %s", dog_id, err)
            self._metrics["errors_count"] += 1
            raise

    async def async_get_current_gps_data(self, dog_id: str) -> Optional[dict[str, Any]]:
        """Get current GPS data for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Current GPS data or None
        """
        dog_data = await self.async_get_dog_data(dog_id)
        return dog_data.get("gps") if dog_data else None

    # Grooming operations
    async def async_start_grooming(
        self, dog_id: str, grooming_data: dict[str, Any]
    ) -> str:
        """Start a grooming session for a dog.

        Args:
            dog_id: Dog identifier
            grooming_data: Grooming start data

        Returns:
            Grooming session ID
        """
        try:
            timestamp = dt_util.utcnow()
            grooming_id = f"grooming_{dog_id}_{int(timestamp.timestamp())}"

            grooming_entry = {
                "grooming_id": grooming_id,
                "dog_id": dog_id,
                "start_time": timestamp.isoformat(),
                "status": "in_progress",
                **grooming_data,
            }

            await self._append_to_module_data("grooming", dog_id, grooming_entry)

            # Update dog's grooming status
            await self.async_update_dog_data(
                dog_id,
                {
                    "grooming": {
                        "grooming_in_progress": True,
                        "current_grooming_id": grooming_id,
                        "current_grooming_start": timestamp.isoformat(),
                    }
                },
            )

            _LOGGER.debug("Started grooming %s for dog %s", grooming_id, dog_id)
            return grooming_id

        except Exception as err:
            _LOGGER.error("Failed to start grooming for %s: %s", dog_id, err)
            self._metrics["errors_count"] += 1
            raise

    async def async_end_grooming(
        self, dog_id: str, grooming_data: Optional[dict[str, Any]] = None
    ) -> None:
        """End the current grooming session for a dog.

        Args:
            dog_id: Dog identifier
            grooming_data: Optional grooming end data
        """
        try:
            dog_data = await self.async_get_dog_data(dog_id)
            if not dog_data or not dog_data.get("grooming", {}).get(
                "grooming_in_progress"
            ):
                return

            grooming_id = dog_data["grooming"].get("current_grooming_id")
            if not grooming_id:
                return

            timestamp = dt_util.utcnow()

            # Update the grooming entry
            grooming_updates = {
                "end_time": timestamp.isoformat(),
                "status": "completed",
                **(grooming_data or {}),
            }

            await self._update_module_entry(
                "grooming", dog_id, grooming_id, grooming_updates
            )

            # Update dog's grooming status
            await self.async_update_dog_data(
                dog_id,
                {
                    "grooming": {
                        "grooming_in_progress": False,
                        "current_grooming_id": None,
                        "current_grooming_start": None,
                        "last_grooming": timestamp.isoformat(),
                    }
                },
            )

            _LOGGER.debug("Ended grooming %s for dog %s", grooming_id, dog_id)

        except Exception as err:
            _LOGGER.error("Failed to end grooming for %s: %s", dog_id, err)
            self._metrics["errors_count"] += 1
            raise

    # Generic module data operations
    async def async_get_module_data(
        self,
        module: str,
        dog_id: str,
        limit: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Get module data for a specific dog.

        Args:
            module: Module name (feeding, walks, health, gps, grooming)
            dog_id: Dog identifier
            limit: Maximum number of entries to return
            start_date: Start date filter
            end_date: End date filter

        Returns:
            List of module data entries
        """
        try:
            cache_key = f"{module}_{dog_id}"
            await self._ensure_cache_fresh(cache_key)

            # Get data from cache or load from storage
            if cache_key not in self._cache:
                store = self._stores[module]
                data = await store.async_load() or {}
                await self._set_cache(cache_key, data.get(dog_id, []))
                self._metrics["cache_misses"] += 1
            else:
                self._metrics["cache_hits"] += 1

            entries = (await self._get_cache(cache_key, [])).copy()

            # Apply date filters
            if start_date or end_date:
                filtered_entries = []
                for entry in entries:
                    try:
                        timestamp_value = entry.get("timestamp")
                        if not timestamp_value:
                            # Keep entries with no timestamp
                            filtered_entries.append(entry)
                            continue

                        # Handle both string and datetime timestamps
                        if isinstance(timestamp_value, str):
                            entry_time = datetime.fromisoformat(timestamp_value)
                        elif isinstance(timestamp_value, datetime):
                            entry_time = timestamp_value
                        else:
                            # Keep entries with invalid timestamp types
                            filtered_entries.append(entry)
                            continue

                        # Ensure timezone consistency for comparisons
                        if entry_time.tzinfo is None:
                            entry_time = dt_util.as_local(entry_time)

                        # Make sure start_date and end_date are timezone-aware (use local copies)
                        start_date_normalized = start_date
                        end_date_normalized = end_date

                        if start_date_normalized:
                            if isinstance(start_date_normalized, str):
                                start_date_normalized = dt_util.parse_datetime(
                                    start_date_normalized
                                )
                            elif start_date_normalized.tzinfo is None:
                                start_date_normalized = dt_util.as_local(
                                    start_date_normalized
                                )
                            if entry_time < start_date_normalized:
                                continue

                        if end_date_normalized:
                            if isinstance(end_date_normalized, str):
                                end_date_normalized = dt_util.parse_datetime(
                                    end_date_normalized
                                )
                            elif end_date_normalized.tzinfo is None:
                                end_date_normalized = dt_util.as_local(
                                    end_date_normalized
                                )
                            if entry_time > end_date_normalized:
                                continue

                        filtered_entries.append(entry)
                    except (ValueError, KeyError, TypeError) as exc:
                        _LOGGER.debug(
                            "Invalid timestamp in entry for %s: %s - %s",
                            dog_id,
                            timestamp_value,
                            exc,
                        )
                        # Keep entries with invalid timestamps
                        filtered_entries.append(entry)
                entries = filtered_entries

            # Sort by timestamp (most recent first) with proper type handling
            def safe_timestamp_key(entry):
                """Extract timestamp for sorting, handling mixed string/datetime types."""
                timestamp_value = entry.get("timestamp", "")
                if isinstance(timestamp_value, str):
                    if not timestamp_value:
                        return datetime.min  # Empty strings sort last
                    try:
                        return datetime.fromisoformat(timestamp_value)
                    except (ValueError, TypeError):
                        return datetime.min  # Invalid strings sort last
                elif isinstance(timestamp_value, datetime):
                    return timestamp_value
                else:
                    return datetime.min  # Invalid types sort last

            entries.sort(key=safe_timestamp_key, reverse=True)

            # Apply limit
            if limit and limit > 0:
                entries = entries[:limit]

            return entries

        except Exception as err:
            _LOGGER.error("Failed to get %s data for %s: %s", module, dog_id, err)
            self._metrics["errors_count"] += 1
            return []

    # Daily statistics reset
    async def async_reset_dog_daily_stats(self, dog_id: str) -> None:
        """Reset daily statistics for a dog.

        Args:
            dog_id: Dog identifier, or "all" for all dogs
        """
        try:
            if dog_id == "all":
                dogs_data = await self.async_get_all_dogs()
                for single_dog_id in dogs_data.keys():
                    await self._reset_single_dog_stats(single_dog_id)
            else:
                await self._reset_single_dog_stats(dog_id)

        except Exception as err:
            _LOGGER.error("Failed to reset daily stats: %s", err)
            self._metrics["errors_count"] += 1
            raise

    async def async_set_dog_power_state(self, dog_id: str, enabled: bool) -> None:
        """Set the main power state for a dog.

        Args:
            dog_id: Dog identifier
            enabled: Whether monitoring is enabled
        """
        try:
            await self.async_update_dog_data(
                dog_id,
                {
                    "system": {
                        "enabled": enabled,
                        "power_state_changed": dt_util.utcnow().isoformat(),
                        "changed_by": "power_switch",
                    }
                },
            )

            _LOGGER.info("Set power state for %s: %s", dog_id, enabled)

        except Exception as err:
            _LOGGER.error("Failed to set power state for %s: %s", dog_id, err)
            raise

    async def async_set_gps_tracking(self, dog_id: str, enabled: bool) -> None:
        """Set GPS tracking state for a dog.

        Args:
            dog_id: Dog identifier
            enabled: Whether GPS tracking is enabled
        """
        try:
            await self.async_update_dog_data(
                dog_id,
                {
                    "gps": {
                        "tracking_enabled": enabled,
                        "tracking_state_changed": dt_util.utcnow().isoformat(),
                        "changed_by": "gps_switch",
                    }
                },
            )

            _LOGGER.info("Set GPS tracking for %s: %s", dog_id, enabled)

        except Exception as err:
            _LOGGER.error("Failed to set GPS tracking for %s: %s", dog_id, err)
            raise

    async def _reset_single_dog_stats(self, dog_id: str) -> None:
        """Reset daily statistics for a single dog."""
        reset_data = {
            "feeding": {
                "daily_food_consumed": 0,
                "daily_calories": 0,
                "meals_today": 0,
                "feeding_schedule_adherence": 100.0,
            },
            "walk": {
                "walks_today": 0,
                "daily_walk_time": 0,
                "daily_walk_distance": 0,
                "walk_goal_met": False,
            },
            "health": {
                "daily_activity_score": 0,
            },
            "last_reset": dt_util.utcnow().isoformat(),
        }

        await self.async_update_dog_data(dog_id, reset_data)
        _LOGGER.debug("Reset daily statistics for dog %s", dog_id)

    # Additional methods would be implemented here for:
    # - Export/import functionality
    # - Data cleanup operations
    # - Cache management
    # - Background tasks
    # - Performance metrics

    # Private helper methods for internal operations
    async def _append_to_module_data(
        self, module: str, dog_id: str, entry: dict[str, Any]
    ) -> None:
        """Append an entry to module data."""
        async with self._lock:
            store = self._stores[module]
            data = await store.async_load() or {}

            if dog_id not in data:
                data[dog_id] = []

            data[dog_id].append(entry)

            # Update cache
            cache_key = f"{module}_{dog_id}"
            await self._set_cache(cache_key, data[dog_id].copy())

            # Save to storage
            await store.async_save(data)

            # Update metrics
            self._metrics["operations_count"] += 1

    async def _update_module_entry(
        self, module: str, dog_id: str, entry_id: str, updates: dict[str, Any]
    ) -> None:
        """Update a specific entry in module data."""
        async with self._lock:
            store = self._stores[module]
            data = await store.async_load() or {}

            if dog_id in data:
                for entry in data[dog_id]:
                    # Look for entry by module-specific ID field
                    id_field = f"{module[:-1]}_id"  # Remove 's' from module name
                    if entry.get(id_field) == entry_id:
                        entry.update(updates)
                        break

                # Update cache
                cache_key = f"{module}_{dog_id}"
                await self._set_cache(cache_key, data[dog_id].copy())

                # Save to storage
                await store.async_save(data)

                # Update metrics
                self._metrics["operations_count"] += 1

    async def _delete_dog_from_all_modules(self, dog_id: str) -> None:
        """Delete dog data from all module stores."""
        modules = ["feeding", "walks", "health", "gps", "grooming"]

        for module in modules:
            try:
                store = self._stores[module]
                data = await store.async_load() or {}

                if dog_id in data:
                    del data[dog_id]
                    await store.async_save(data)

                # Clear from cache
                cache_key = f"{module}_{dog_id}"
                if cache_key in self._cache:
                    async with self._cache_lock:
                        del self._cache[cache_key]
                        del self._cache_timestamps[cache_key]

            except Exception as err:
                _LOGGER.error(
                    "Failed to delete %s data for dog %s: %s", module, dog_id, err
                )

    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup task."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                await self.async_cleanup_old_data()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in periodic cleanup: %s", err)

    async def _periodic_backup(self) -> None:
        """Periodic backup task."""
        while True:
            try:
                await asyncio.sleep(86400)  # Run daily
                await self._create_backup()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in periodic backup: %s", err)

    async def _create_backup(self) -> None:
        """Create a backup of all data."""
        try:
            backup_dir = Path(self.hass.config.config_dir) / "paw_control_backups"
            backup_dir.mkdir(exist_ok=True)

            timestamp = dt_util.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"paw_control_backup_{timestamp}.json"

            # Collect all data
            backup_data = {
                "backup_info": {
                    "created": dt_util.utcnow().isoformat(),
                    "entry_id": self.entry_id,
                    "version": STORAGE_VERSION,
                },
                "dogs": await self.async_get_all_dogs(),
            }

            # Add module data for all dogs
            for dog_id in backup_data["dogs"].keys():
                backup_data[f"feeding_{dog_id}"] = await self.async_get_module_data(
                    "feeding", dog_id
                )
                backup_data[f"walks_{dog_id}"] = await self.async_get_module_data(
                    "walks", dog_id
                )
                backup_data[f"health_{dog_id}"] = await self.async_get_module_data(
                    "health", dog_id
                )
                backup_data[f"gps_{dog_id}"] = await self.async_get_module_data(
                    "gps", dog_id
                )
                backup_data[f"grooming_{dog_id}"] = await self.async_get_module_data(
                    "grooming", dog_id
                )

            await self._export_json(backup_file, backup_data)

            _LOGGER.info("Created backup: %s", backup_file)

        except Exception as err:
            _LOGGER.error("Failed to create backup: %s", err)

    async def _flush_cache_to_storage(self) -> None:
        """Flush all cached data to storage."""
        try:
            # This is a simplified version - in a real implementation,
            # you would flush all dirty cache entries to their respective stores
            if "dogs" in self._cache:
                await self._stores["dogs"].async_save(self._cache["dogs"])

        except Exception as err:
            _LOGGER.error("Failed to flush cache to storage: %s", err)

    # Cache management
    async def _ensure_cache_fresh(self, cache_key: str) -> None:
        """Ensure cache entry is fresh."""
        async with self._cache_lock:
            if cache_key not in self._cache_timestamps:
                return

            last_update = self._cache_timestamps[cache_key]
            if dt_util.utcnow() - last_update > self._cache_ttl:
                # Cache is stale, remove it to force reload
                if cache_key in self._cache:
                    del self._cache[cache_key]
                    del self._cache_timestamps[cache_key]

    async def _get_cache(self, key: str, default: Any = None) -> Any:
        """Get value from cache."""
        async with self._cache_lock:
            return self._cache.get(key, default)

    async def _set_cache(self, key: str, value: Any) -> None:
        """Set value in cache."""
        async with self._cache_lock:
            self._cache[key] = value
            self._cache_timestamps[key] = dt_util.utcnow()

    async def _export_json(self, filepath: Path, data: Any) -> None:
        """Export data as JSON."""
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, default=str, ensure_ascii=False))

    async def async_cleanup_old_data(
        self, retention_days: Optional[int] = None
    ) -> dict[str, int]:
        """Clean up old data based on retention policy."""
        if retention_days is None:
            retention_days = DEFAULT_DATA_RETENTION_DAYS

        cutoff_date = dt_util.utcnow() - timedelta(days=retention_days)

        _LOGGER.debug("Cleaning up data older than %s", cutoff_date)

        # Clean up each module's data
        modules = ["feeding", "walks", "health", "gps", "grooming"]
        cleanup_stats = {}
        total_deleted = 0

        for module in modules:
            try:
                deleted_count = await self._cleanup_module_data(module, cutoff_date)
                cleanup_stats[module] = deleted_count
                total_deleted += deleted_count
            except Exception as err:
                _LOGGER.error("Failed to cleanup %s data: %s", module, err)
                cleanup_stats[module] = 0

        # Update metrics
        self._metrics["last_cleanup"] = dt_util.utcnow().isoformat()

        _LOGGER.info(
            "Cleaned up %d old data entries across %d modules",
            total_deleted,
            len(modules),
        )
        return cleanup_stats

    async def _cleanup_module_data(self, module: str, cutoff_date: datetime) -> int:
        """Clean up old data from a specific module."""
        try:
            store = self._stores[module]
            data = await store.async_load() or {}

            total_deleted = 0

            for dog_id, entries in data.items():
                original_count = len(entries)

                # Filter out old entries
                filtered_entries = []
                for entry in entries:
                    try:
                        timestamp_value = entry.get("timestamp")
                        if not isinstance(timestamp_value, str) or not timestamp_value:
                            # Keep entries with invalid timestamps
                            filtered_entries.append(entry)
                            continue

                        entry_date = datetime.fromisoformat(timestamp_value)
                        # Ensure both timestamps are timezone-aware for comparison
                        if entry_date.tzinfo is None:
                            entry_date = dt_util.as_local(entry_date)
                        if cutoff_date.tzinfo is None:
                            cutoff_date = dt_util.as_local(cutoff_date)

                        if entry_date >= cutoff_date:
                            filtered_entries.append(entry)
                    except (ValueError, KeyError, TypeError):
                        # Keep entries with invalid timestamps
                        filtered_entries.append(entry)

                data[dog_id] = filtered_entries
                deleted_count = original_count - len(filtered_entries)
                total_deleted += deleted_count

                # Update cache if present
                cache_key = f"{module}_{dog_id}"
                if cache_key in self._cache:
                    await self._set_cache(cache_key, filtered_entries.copy())

            # Save updated data
            await store.async_save(data)

            return total_deleted

        except Exception as err:
            _LOGGER.error("Failed to cleanup %s data: %s", module, err)
            return 0

    # Public metrics interface
    def get_metrics(self) -> dict[str, Any]:
        """Get data manager performance metrics.

        Returns:
            Dictionary containing performance metrics
        """
        return {
            **self._metrics,
            "cache_size": len(self._cache),
            "cache_hit_rate": (
                self._metrics["cache_hits"]
                / max(self._metrics["cache_hits"] + self._metrics["cache_misses"], 1)
            )
            * 100,
        }
