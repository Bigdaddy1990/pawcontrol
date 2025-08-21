"""Data management for Paw Control integration.

This module provides comprehensive data storage, retrieval, and management
functionality for all dog monitoring data. It handles data persistence,
cleanup, export/import operations, and maintains data integrity across
all modules and components.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DATA_RETENTION_DAYS,
    DOMAIN,
    STORAGE_VERSION,
)
from .exceptions import (
    DataExportError,
    StorageError,
)
from .utils import (
    deep_merge_dicts,
    sanitize_filename,
)

_LOGGER = logging.getLogger(__name__)

# Type aliases
DataDict = Dict[str, Any]
DogDataDict = Dict[str, DataDict]


class PawControlDataManager:
    """Central data management for Paw Control integration.
    
    Handles all data storage, retrieval, and management operations
    including persistence, cleanup, backup, and export/import.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the data manager.
        
        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id
        
        # Storage instances for different data types
        self._dog_store = Store(
            hass, 
            STORAGE_VERSION, 
            f"{DOMAIN}_{entry_id}_dogs"
        )
        self._feeding_store = Store(
            hass, 
            STORAGE_VERSION, 
            f"{DOMAIN}_{entry_id}_feeding"
        )
        self._walk_store = Store(
            hass, 
            STORAGE_VERSION, 
            f"{DOMAIN}_{entry_id}_walks"
        )
        self._health_store = Store(
            hass, 
            STORAGE_VERSION, 
            f"{DOMAIN}_{entry_id}_health"
        )
        self._gps_store = Store(
            hass, 
            STORAGE_VERSION, 
            f"{DOMAIN}_{entry_id}_gps"
        )
        self._grooming_store = Store(
            hass, 
            STORAGE_VERSION, 
            f"{DOMAIN}_{entry_id}_grooming"
        )
        
        # In-memory cache for frequently accessed data
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)
        
        # Data cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Initialize the data manager and load existing data."""
        _LOGGER.debug("Initializing data manager for entry %s", self.entry_id)
        
        try:
            # Load existing data
            await self._load_initial_data()
            
            # Start periodic cleanup task
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            
            _LOGGER.info("Data manager initialized successfully")
            
        except Exception as err:
            _LOGGER.error("Failed to initialize data manager: %s", err)
            raise StorageError("initialize", str(err)) from err

    async def async_shutdown(self) -> None:
        """Shutdown the data manager and cleanup resources."""
        _LOGGER.debug("Shutting down data manager")
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Clear cache
        self._cache.clear()
        self._cache_timestamps.clear()
        
        _LOGGER.info("Data manager shutdown complete")

    async def _load_initial_data(self) -> None:
        """Load initial data from storage into cache."""
        async with self._lock:
            try:
                # Load dog data
                dog_data = await self._dog_store.async_load() or {}
                self._cache["dogs"] = dog_data
                self._cache_timestamps["dogs"] = dt_util.utcnow()
                
                _LOGGER.debug("Loaded data for %d dogs", len(dog_data))
                
            except Exception as err:
                _LOGGER.error("Failed to load initial data: %s", err)
                self._cache["dogs"] = {}

    async def async_get_dog_data(self, dog_id: str) -> Optional[DataDict]:
        """Get all data for a specific dog.
        
        Args:
            dog_id: Dog identifier
            
        Returns:
            Dog data dictionary or None if not found
        """
        await self._ensure_cache_fresh("dogs")
        
        dogs_data = self._cache.get("dogs", {})
        return dogs_data.get(dog_id)

    async def async_set_dog_data(self, dog_id: str, data: DataDict) -> None:
        """Set data for a specific dog.
        
        Args:
            dog_id: Dog identifier
            data: Dog data to store
        """
        async with self._lock:
            # Update cache
            if "dogs" not in self._cache:
                self._cache["dogs"] = {}
            
            self._cache["dogs"][dog_id] = data
            self._cache_timestamps["dogs"] = dt_util.utcnow()
            
            # Persist to storage
            await self._dog_store.async_save(self._cache["dogs"])
            
            _LOGGER.debug("Updated data for dog %s", dog_id)

    async def async_update_dog_data(self, dog_id: str, updates: DataDict) -> None:
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
            # Remove from cache
            if "dogs" in self._cache and dog_id in self._cache["dogs"]:
                del self._cache["dogs"][dog_id]
                self._cache_timestamps["dogs"] = dt_util.utcnow()
                
                # Persist to storage
                await self._dog_store.async_save(self._cache["dogs"])
            
            # Remove from all module stores
            await self._delete_dog_from_all_modules(dog_id)
            
            _LOGGER.info("Deleted all data for dog %s", dog_id)

    async def async_get_all_dogs(self) -> DogDataDict:
        """Get data for all dogs.
        
        Returns:
            Dictionary of all dog data
        """
        await self._ensure_cache_fresh("dogs")
        return self._cache.get("dogs", {}).copy()

    async def async_log_feeding(
        self, 
        dog_id: str, 
        meal_data: DataDict
    ) -> None:
        """Log a feeding event for a dog.
        
        Args:
            dog_id: Dog identifier
            meal_data: Feeding data to log
        """
        timestamp = dt_util.utcnow().isoformat()
        feeding_entry = {
            "timestamp": timestamp,
            "dog_id": dog_id,
            **meal_data,
        }
        
        await self._append_to_module_data("feeding", dog_id, feeding_entry)
        
        # Update dog's last feeding time
        await self.async_update_dog_data(dog_id, {
            "feeding": {
                "last_feeding": timestamp,
                "last_feeding_hours": 0,
            }
        })
        
        _LOGGER.debug("Logged feeding for dog %s: %s", dog_id, meal_data.get("meal_type"))

    async def async_start_walk(self, dog_id: str, walk_data: DataDict) -> str:
        """Start a walk session for a dog.
        
        Args:
            dog_id: Dog identifier
            walk_data: Walk start data
            
        Returns:
            Walk session ID
        """
        walk_id = f"walk_{dog_id}_{int(dt_util.utcnow().timestamp())}"
        timestamp = dt_util.utcnow().isoformat()
        
        walk_entry = {
            "walk_id": walk_id,
            "dog_id": dog_id,
            "start_time": timestamp,
            "status": "in_progress",
            **walk_data,
        }
        
        await self._append_to_module_data("walks", dog_id, walk_entry)
        
        # Update dog's walk status
        await self.async_update_dog_data(dog_id, {
            "walk": {
                "walk_in_progress": True,
                "current_walk_id": walk_id,
                "current_walk_start": timestamp,
            }
        })
        
        _LOGGER.debug("Started walk %s for dog %s", walk_id, dog_id)
        return walk_id

    async def async_end_walk(
        self, 
        dog_id: str, 
        walk_data: Optional[DataDict] = None
    ) -> None:
        """End the current walk session for a dog.
        
        Args:
            dog_id: Dog identifier
            walk_data: Optional walk end data
        """
        dog_data = await self.async_get_dog_data(dog_id)
        if not dog_data or not dog_data.get("walk", {}).get("walk_in_progress"):
            return
        
        walk_id = dog_data["walk"].get("current_walk_id")
        if not walk_id:
            return
        
        timestamp = dt_util.utcnow().isoformat()
        
        # Update the walk entry
        walk_updates = {
            "end_time": timestamp,
            "status": "completed",
            **(walk_data or {}),
        }
        
        await self._update_module_entry("walks", dog_id, walk_id, walk_updates)
        
        # Update dog's walk status
        await self.async_update_dog_data(dog_id, {
            "walk": {
                "walk_in_progress": False,
                "current_walk_id": None,
                "current_walk_start": None,
                "last_walk": timestamp,
                "last_walk_hours": 0,
            }
        })
        
        _LOGGER.debug("Ended walk %s for dog %s", walk_id, dog_id)

    async def async_log_health(self, dog_id: str, health_data: DataDict) -> None:
        """Log health data for a dog.
        
        Args:
            dog_id: Dog identifier
            health_data: Health data to log
        """
        timestamp = dt_util.utcnow().isoformat()
        health_entry = {
            "timestamp": timestamp,
            "dog_id": dog_id,
            **health_data,
        }
        
        await self._append_to_module_data("health", dog_id, health_entry)
        
        # Update dog's current health status
        health_updates = {"health": {"last_health_update": timestamp}}
        
        # Update specific health fields if provided
        if "weight" in health_data:
            health_updates["health"]["current_weight"] = health_data["weight"]
        if "health_status" in health_data:
            health_updates["health"]["health_status"] = health_data["health_status"]
        if "mood" in health_data:
            health_updates["health"]["mood"] = health_data["mood"]
        
        await self.async_update_dog_data(dog_id, health_updates)
        
        _LOGGER.debug("Logged health data for dog %s", dog_id)

    async def async_log_gps(self, dog_id: str, gps_data: DataDict) -> None:
        """Log GPS location data for a dog.
        
        Args:
            dog_id: Dog identifier
            gps_data: GPS data to log
        """
        timestamp = dt_util.utcnow().isoformat()
        gps_entry = {
            "timestamp": timestamp,
            "dog_id": dog_id,
            **gps_data,
        }
        
        await self._append_to_module_data("gps", dog_id, gps_entry)
        
        # Update dog's current location
        gps_updates = {
            "gps": {
                "last_seen": timestamp,
                "latitude": gps_data.get("latitude"),
                "longitude": gps_data.get("longitude"),
                "accuracy": gps_data.get("accuracy"),
                "speed": gps_data.get("speed"),
            }
        }
        
        await self.async_update_dog_data(dog_id, gps_updates)

    async def async_start_grooming(self, dog_id: str, grooming_data: DataDict) -> str:
        """Start a grooming session for a dog.
        
        Args:
            dog_id: Dog identifier
            grooming_data: Grooming start data
            
        Returns:
            Grooming session ID
        """
        grooming_id = f"grooming_{dog_id}_{int(dt_util.utcnow().timestamp())}"
        timestamp = dt_util.utcnow().isoformat()
        
        grooming_entry = {
            "grooming_id": grooming_id,
            "dog_id": dog_id,
            "start_time": timestamp,
            "status": "in_progress",
            **grooming_data,
        }
        
        await self._append_to_module_data("grooming", dog_id, grooming_entry)
        
        # Update dog's grooming status
        await self.async_update_dog_data(dog_id, {
            "grooming": {
                "grooming_in_progress": True,
                "current_grooming_id": grooming_id,
                "current_grooming_start": timestamp,
            }
        })
        
        _LOGGER.debug("Started grooming %s for dog %s", grooming_id, dog_id)
        return grooming_id

    async def async_end_grooming(
        self, 
        dog_id: str, 
        grooming_data: Optional[DataDict] = None
    ) -> None:
        """End the current grooming session for a dog.
        
        Args:
            dog_id: Dog identifier
            grooming_data: Optional grooming end data
        """
        dog_data = await self.async_get_dog_data(dog_id)
        if not dog_data or not dog_data.get("grooming", {}).get("grooming_in_progress"):
            return
        
        grooming_id = dog_data["grooming"].get("current_grooming_id")
        if not grooming_id:
            return
        
        timestamp = dt_util.utcnow().isoformat()
        
        # Update the grooming entry
        grooming_updates = {
            "end_time": timestamp,
            "status": "completed",
            **(grooming_data or {}),
        }
        
        await self._update_module_entry("grooming", dog_id, grooming_id, grooming_updates)
        
        # Update dog's grooming status
        await self.async_update_dog_data(dog_id, {
            "grooming": {
                "grooming_in_progress": False,
                "current_grooming_id": None,
                "current_grooming_start": None,
                "last_grooming": timestamp,
            }
        })
        
        _LOGGER.debug("Ended grooming %s for dog %s", grooming_id, dog_id)

    async def async_get_module_data(
        self, 
        module: str, 
        dog_id: str,
        limit: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[DataDict]:
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
        cache_key = f"{module}_{dog_id}"
        await self._ensure_cache_fresh(cache_key)
        
        # Get data from cache or load from storage
        if cache_key not in self._cache:
            store = self._get_module_store(module)
            data = await store.async_load() or {}
            self._cache[cache_key] = data.get(dog_id, [])
            self._cache_timestamps[cache_key] = dt_util.utcnow()
        
        entries = self._cache[cache_key].copy()
        
        # Apply filters
        if start_date or end_date:
            filtered_entries = []
            for entry in entries:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if start_date and entry_time < start_date:
                    continue
                if end_date and entry_time > end_date:
                    continue
                filtered_entries.append(entry)
            entries = filtered_entries
        
        # Apply limit
        if limit:
            entries = entries[-limit:]  # Get most recent entries
        
        return entries

    async def async_reset_dog_daily_stats(self, dog_id: str) -> None:
        """Reset daily statistics for a dog.
        
        Args:
            dog_id: Dog identifier
        """
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
        _LOGGER.info("Reset daily statistics for dog %s", dog_id)

    async def async_export_data(
        self,
        dog_id: str,
        data_type: str = "all",
        format_type: str = "json",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> str:
        """Export data for a dog.
        
        Args:
            dog_id: Dog identifier
            data_type: Type of data to export (all, feeding, walks, health, gps, grooming)
            format_type: Export format (json, csv)
            start_date: Start date filter
            end_date: End date filter
            
        Returns:
            Path to exported file
            
        Raises:
            DataExportError: If export fails
        """
        try:
            # Get export directory
            export_dir = Path(self.hass.config.config_dir) / "paw_control_exports"
            export_dir.mkdir(exist_ok=True)
            
            # Generate filename
            timestamp = dt_util.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{dog_id}_{data_type}_{timestamp}.{format_type}"
            filepath = export_dir / sanitize_filename(filename)
            
            # Collect data to export
            if data_type == "all":
                export_data = {
                    "dog_info": await self.async_get_dog_data(dog_id),
                    "feeding": await self.async_get_module_data("feeding", dog_id, start_date=start_date, end_date=end_date),
                    "walks": await self.async_get_module_data("walks", dog_id, start_date=start_date, end_date=end_date),
                    "health": await self.async_get_module_data("health", dog_id, start_date=start_date, end_date=end_date),
                    "gps": await self.async_get_module_data("gps", dog_id, start_date=start_date, end_date=end_date),
                    "grooming": await self.async_get_module_data("grooming", dog_id, start_date=start_date, end_date=end_date),
                }
            else:
                export_data = await self.async_get_module_data(data_type, dog_id, start_date=start_date, end_date=end_date)
            
            # Export based on format
            if format_type == "json":
                await self._export_json(filepath, export_data)
            elif format_type == "csv":
                await self._export_csv(filepath, export_data, data_type)
            else:
                raise DataExportError(data_type, f"Unsupported format: {format_type}")
            
            _LOGGER.info("Exported %s data for dog %s to %s", data_type, dog_id, filepath)
            return str(filepath)
            
        except Exception as err:
            _LOGGER.error("Failed to export %s data for dog %s: %s", data_type, dog_id, err)
            raise DataExportError(data_type, str(err)) from err

    async def async_cleanup_old_data(self, retention_days: int = DATA_RETENTION_DAYS) -> None:
        """Clean up old data based on retention policy.
        
        Args:
            retention_days: Number of days to retain data
        """
        cutoff_date = dt_util.utcnow() - timedelta(days=retention_days)
        
        _LOGGER.debug("Cleaning up data older than %s", cutoff_date)
        
        # Clean up each module's data
        modules = ["feeding", "walks", "health", "gps", "grooming"]
        total_deleted = 0
        
        for module in modules:
            deleted_count = await self._cleanup_module_data(module, cutoff_date)
            total_deleted += deleted_count
        
        _LOGGER.info("Cleaned up %d old data entries", total_deleted)

    async def _append_to_module_data(
        self, 
        module: str, 
        dog_id: str, 
        entry: DataDict
    ) -> None:
        """Append an entry to module data.
        
        Args:
            module: Module name
            dog_id: Dog identifier
            entry: Data entry to append
        """
        async with self._lock:
            store = self._get_module_store(module)
            data = await store.async_load() or {}
            
            if dog_id not in data:
                data[dog_id] = []
            
            data[dog_id].append(entry)
            
            # Update cache
            cache_key = f"{module}_{dog_id}"
            self._cache[cache_key] = data[dog_id].copy()
            self._cache_timestamps[cache_key] = dt_util.utcnow()
            
            # Save to storage
            await store.async_save(data)

    async def _update_module_entry(
        self, 
        module: str, 
        dog_id: str, 
        entry_id: str, 
        updates: DataDict
    ) -> None:
        """Update a specific entry in module data.
        
        Args:
            module: Module name
            dog_id: Dog identifier
            entry_id: Entry identifier
            updates: Updates to apply
        """
        async with self._lock:
            store = self._get_module_store(module)
            data = await store.async_load() or {}
            
            if dog_id in data:
                for entry in data[dog_id]:
                    if entry.get(f"{module[:-1]}_id") == entry_id:  # Remove 's' from module name
                        entry.update(updates)
                        break
                
                # Update cache
                cache_key = f"{module}_{dog_id}"
                self._cache[cache_key] = data[dog_id].copy()
                self._cache_timestamps[cache_key] = dt_util.utcnow()
                
                # Save to storage
                await store.async_save(data)

    async def _delete_dog_from_all_modules(self, dog_id: str) -> None:
        """Delete dog data from all module stores.
        
        Args:
            dog_id: Dog identifier
        """
        modules = ["feeding", "walks", "health", "gps", "grooming"]
        
        for module in modules:
            store = self._get_module_store(module)
            data = await store.async_load() or {}
            
            if dog_id in data:
                del data[dog_id]
                await store.async_save(data)
            
            # Clear from cache
            cache_key = f"{module}_{dog_id}"
            if cache_key in self._cache:
                del self._cache[cache_key]
                del self._cache_timestamps[cache_key]

    async def _cleanup_module_data(self, module: str, cutoff_date: datetime) -> int:
        """Clean up old data from a specific module.
        
        Args:
            module: Module name
            cutoff_date: Cutoff date for cleanup
            
        Returns:
            Number of entries deleted
        """
        store = self._get_module_store(module)
        data = await store.async_load() or {}
        
        total_deleted = 0
        
        for dog_id, entries in data.items():
            original_count = len(entries)
            
            # Filter out old entries
            filtered_entries = []
            for entry in entries:
                try:
                    entry_date = datetime.fromisoformat(entry["timestamp"])
                    if entry_date >= cutoff_date:
                        filtered_entries.append(entry)
                except (ValueError, KeyError):
                    # Keep entries with invalid timestamps
                    filtered_entries.append(entry)
            
            data[dog_id] = filtered_entries
            deleted_count = original_count - len(filtered_entries)
            total_deleted += deleted_count
            
            # Update cache if present
            cache_key = f"{module}_{dog_id}"
            if cache_key in self._cache:
                self._cache[cache_key] = filtered_entries.copy()
                self._cache_timestamps[cache_key] = dt_util.utcnow()
        
        # Save updated data
        await store.async_save(data)
        
        return total_deleted

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

    async def _ensure_cache_fresh(self, cache_key: str) -> None:
        """Ensure cache entry is fresh."""
        if cache_key not in self._cache_timestamps:
            return
        
        last_update = self._cache_timestamps[cache_key]
        if dt_util.utcnow() - last_update > self._cache_ttl:
            # Cache is stale, remove it to force reload
            if cache_key in self._cache:
                del self._cache[cache_key]
                del self._cache_timestamps[cache_key]

    def _get_module_store(self, module: str) -> Store:
        """Get the storage instance for a specific module.
        
        Args:
            module: Module name
            
        Returns:
            Store instance
        """
        store_map = {
            "feeding": self._feeding_store,
            "walks": self._walk_store,
            "health": self._health_store,
            "gps": self._gps_store,
            "grooming": self._grooming_store,
        }
        
        return store_map[module]

    async def _export_json(self, filepath: Path, data: Any) -> None:
        """Export data as JSON.
        
        Args:
            filepath: Export file path
            data: Data to export
        """
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, default=str))

    async def _export_csv(self, filepath: Path, data: Any, data_type: str) -> None:
        """Export data as CSV.
        
        Args:
            filepath: Export file path
            data: Data to export
            data_type: Type of data being exported
        """
        import csv
        
        # For now, simple CSV export - could be enhanced
        if isinstance(data, list) and data:
            fieldnames = list(data[0].keys())
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in data:
                    writer.writerow(row)
        else:
            # Fallback to JSON for complex data
            await self._export_json(filepath, data)
