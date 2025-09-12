"""Helper classes and functions for Paw Control integration.

This module provides core data management and notification functionality
required for the Paw Control integration to achieve Platinum quality standards.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import storage
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    DATA_FILE_FEEDINGS,
    DATA_FILE_HEALTH,
    DATA_FILE_ROUTES,
    DATA_FILE_STATS,
    DATA_FILE_WALKS,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    EVENT_HEALTH_LOGGED,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
)

_LOGGER = logging.getLogger(__name__)

# Storage version for data persistence
STORAGE_VERSION = 1


class PawControlDataStorage:
    """Manages persistent data storage for Paw Control integration.

    This class handles all data persistence operations including walks,
    feedings, health records, and statistics. It provides async methods
    for efficient I/O operations and maintains data integrity.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the data storage manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry for the integration
        """
        self.hass = hass
        self.config_entry = config_entry
        self._stores: dict[str, storage.Store] = {}

        # Initialize storage for each data type
        self._initialize_stores()

    def _initialize_stores(self) -> None:
        """Initialize storage stores for different data types.

        Creates separate storage instances for walks, feedings, health data,
        routes, and statistics to maintain data separation and integrity.
        """
        store_configs = [
            (DATA_FILE_WALKS, "walks"),
            (DATA_FILE_FEEDINGS, "feedings"),
            (DATA_FILE_HEALTH, "health"),
            (DATA_FILE_ROUTES, "routes"),
            (DATA_FILE_STATS, "statistics"),
        ]

        for filename, store_key in store_configs:
            self._stores[store_key] = storage.Store(
                self.hass,
                STORAGE_VERSION,
                f"{DOMAIN}_{self.config_entry.entry_id}_{filename}",
                encoder=_data_encoder,
                atomic_writes=True,
            )

    async def async_load_all_data(self) -> dict[str, Any]:
        """Load all stored data for the integration.

        Returns:
            Dictionary containing all stored data organized by type

        Raises:
            HomeAssistantError: If data loading fails
        """
        try:
            # Load all data stores concurrently for better performance
            load_tasks = [
                self._load_store_data(store_key) for store_key in self._stores
            ]

            results = await asyncio.gather(*load_tasks, return_exceptions=True)

            data = {}
            for store_key, result in zip(self._stores.keys(), results, strict=False):
                if isinstance(result, Exception):
                    _LOGGER.error("Failed to load %s data: %s", store_key, result)
                    data[store_key] = {}
                else:
                    data[store_key] = result or {}

            _LOGGER.debug("Loaded data for %d stores", len(data))
            return data

        except Exception as err:
            _LOGGER.error("Failed to load integration data: %s", err)
            raise HomeAssistantError(f"Data loading failed: {err}") from err

    async def _load_store_data(self, store_key: str) -> dict[str, Any]:
        """Load data from a specific store.

        Args:
            store_key: Key identifying the data store

        Returns:
            Loaded data or empty dict if no data exists
        """
        store = self._stores.get(store_key)
        if not store:
            return {}

        try:
            data = await store.async_load()
            return data or {}
        except Exception as err:
            _LOGGER.error("Failed to load %s store: %s", store_key, err)
            return {}

    async def async_save_data(self, store_key: str, data: dict[str, Any]) -> None:
        """Save data to a specific store.

        Args:
            store_key: Key identifying the data store
            data: Data to save

        Raises:
            HomeAssistantError: If saving fails
        """
        store = self._stores.get(store_key)
        if not store:
            raise HomeAssistantError(f"Store {store_key} not found")

        try:
            await store.async_save(data)
            _LOGGER.debug("Saved data to %s store", store_key)
        except Exception as err:
            _LOGGER.error("Failed to save %s data: %s", store_key, err)
            raise HomeAssistantError(f"Failed to save {store_key} data") from err

    async def async_cleanup_old_data(self, retention_days: int = 90) -> None:
        """Clean up old data based on retention policy.

        Args:
            retention_days: Number of days to retain data
        """
        cutoff_date = dt_util.utcnow() - timedelta(days=retention_days)

        # Clean up each data store
        for store_key in self._stores:
            try:
                data = await self._load_store_data(store_key)
                cleaned_data = self._cleanup_store_data(data, cutoff_date)

                if data != cleaned_data:
                    await self.async_save_data(store_key, cleaned_data)
                    _LOGGER.debug("Cleaned up old data from %s store", store_key)

            except Exception as err:
                _LOGGER.error("Failed to cleanup %s data: %s", store_key, err)

    def _cleanup_store_data(
        self, data: dict[str, Any], cutoff_date: datetime
    ) -> dict[str, Any]:
        """Remove entries older than cutoff date from store data.

        Args:
            data: Data to clean
            cutoff_date: Cutoff date for data retention

        Returns:
            Cleaned data with old entries removed
        """
        if not isinstance(data, dict):
            return data

        cleaned = {}
        for key, value in data.items():
            if isinstance(value, dict) and "timestamp" in value:
                try:
                    entry_date = datetime.fromisoformat(value["timestamp"])
                    if entry_date >= cutoff_date:
                        cleaned[key] = value
                except (ValueError, TypeError):
                    # Keep entries with invalid timestamps
                    cleaned[key] = value
            else:
                # Keep non-timestamped entries
                cleaned[key] = value

        return cleaned


class PawControlData:
    """Main data management class for Paw Control integration.

    Provides high-level data operations for walks, feedings, health records,
    and other pet-related data. Handles business logic and data validation.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the data manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry for the integration
        """
        self.hass = hass
        self.config_entry = config_entry
        self.storage = PawControlDataStorage(hass, config_entry)
        self._data: dict[str, Any] = {}
        self._dogs: list[dict[str, Any]] = config_entry.data.get(CONF_DOGS, [])

    async def async_load_data(self) -> None:
        """Load all data from storage.

        Initializes the data manager with persisted data from storage.
        """
        try:
            self._data = await self.storage.async_load_all_data()
            _LOGGER.debug(
                "Data manager initialized with %d data types", len(self._data)
            )
        except Exception as err:
            _LOGGER.error("Failed to initialize data manager: %s", err)
            # Initialize with empty data if loading fails
            self._data = {
                "walks": {},
                "feedings": {},
                "health": {},
                "routes": {},
                "statistics": {},
            }

    async def async_log_feeding(
        self, dog_id: str, feeding_data: dict[str, Any]
    ) -> None:
        """Log a feeding event for a dog.

        Args:
            dog_id: Unique identifier for the dog
            feeding_data: Feeding information including timestamp, meal type, etc.

        Raises:
            HomeAssistantError: If logging fails
        """
        if not self._is_valid_dog_id(dog_id):
            raise HomeAssistantError(f"Invalid dog ID: {dog_id}")

        try:
            # Ensure feedings data structure exists
            if "feedings" not in self._data:
                self._data["feedings"] = {}
            if dog_id not in self._data["feedings"]:
                self._data["feedings"][dog_id] = []

            # Add timestamp if not provided
            if "timestamp" not in feeding_data:
                feeding_data["timestamp"] = dt_util.utcnow().isoformat()

            # Add feeding entry
            self._data["feedings"][dog_id].append(feeding_data)

            # Save to storage
            await self.storage.async_save_data("feedings", self._data["feedings"])

            # Fire event
            self.hass.bus.async_fire(
                EVENT_FEEDING_LOGGED,
                {
                    "dog_id": dog_id,
                    **feeding_data,
                },
            )

            _LOGGER.debug("Logged feeding for %s: %s", dog_id, feeding_data)

        except Exception as err:
            _LOGGER.error("Failed to log feeding for %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to log feeding: {err}") from err

    async def async_start_walk(self, dog_id: str, walk_data: dict[str, Any]) -> None:
        """Start a walk for a dog.

        Args:
            dog_id: Unique identifier for the dog
            walk_data: Walk information including start time, label, etc.

        Raises:
            HomeAssistantError: If starting walk fails
        """
        if not self._is_valid_dog_id(dog_id):
            raise HomeAssistantError(f"Invalid dog ID: {dog_id}")

        try:
            # Ensure walks data structure exists
            if "walks" not in self._data:
                self._data["walks"] = {}
            if dog_id not in self._data["walks"]:
                self._data["walks"][dog_id] = {"active": None, "history": []}

            # Check if a walk is already active
            if self._data["walks"][dog_id]["active"]:
                raise HomeAssistantError(f"Walk already active for {dog_id}")

            # Set active walk
            self._data["walks"][dog_id]["active"] = walk_data

            # Save to storage
            await self.storage.async_save_data("walks", self._data["walks"])

            # Fire event
            self.hass.bus.async_fire(
                EVENT_WALK_STARTED,
                {
                    "dog_id": dog_id,
                    **walk_data,
                },
            )

            _LOGGER.debug("Started walk for %s", dog_id)

        except Exception as err:
            _LOGGER.error("Failed to start walk for %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to start walk: {err}") from err

    async def async_end_walk(self, dog_id: str) -> dict[str, Any] | None:
        """End an active walk for a dog.

        Args:
            dog_id: Unique identifier for the dog

        Returns:
            Walk data with calculated statistics, or None if no active walk

        Raises:
            HomeAssistantError: If ending walk fails
        """
        if not self._is_valid_dog_id(dog_id):
            raise HomeAssistantError(f"Invalid dog ID: {dog_id}")

        try:
            walks_data = self._data.get("walks", {}).get(dog_id, {})
            active_walk = walks_data.get("active")

            if not active_walk:
                _LOGGER.warning("No active walk found for %s", dog_id)
                return None

            # Calculate walk statistics
            end_time = dt_util.utcnow().isoformat()
            start_time = active_walk["start_time"]

            try:
                start_dt = datetime.fromisoformat(start_time)
                end_dt = datetime.fromisoformat(end_time)
                duration_minutes = (end_dt - start_dt).total_seconds() / 60
            except ValueError:
                duration_minutes = 0

            # Create completed walk data
            completed_walk = {
                **active_walk,
                "end_time": end_time,
                "duration": duration_minutes,
                "distance": 0,  # Would be calculated from GPS data
            }

            # Move to history and clear active
            if "history" not in walks_data:
                walks_data["history"] = []
            walks_data["history"].append(completed_walk)
            walks_data["active"] = None

            # Update data structure
            if "walks" not in self._data:
                self._data["walks"] = {}
            self._data["walks"][dog_id] = walks_data

            # Save to storage
            await self.storage.async_save_data("walks", self._data["walks"])

            # Fire event
            self.hass.bus.async_fire(
                EVENT_WALK_ENDED,
                {
                    "dog_id": dog_id,
                    **completed_walk,
                },
            )

            _LOGGER.debug("Ended walk for %s: %d minutes", dog_id, duration_minutes)
            return completed_walk

        except Exception as err:
            _LOGGER.error("Failed to end walk for %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to end walk: {err}") from err

    async def async_log_health(self, dog_id: str, health_data: dict[str, Any]) -> None:
        """Log health data for a dog.

        Args:
            dog_id: Unique identifier for the dog
            health_data: Health information including weight, notes, etc.

        Raises:
            HomeAssistantError: If logging fails
        """
        if not self._is_valid_dog_id(dog_id):
            raise HomeAssistantError(f"Invalid dog ID: {dog_id}")

        try:
            # Ensure health data structure exists
            if "health" not in self._data:
                self._data["health"] = {}
            if dog_id not in self._data["health"]:
                self._data["health"][dog_id] = []

            # Add timestamp if not provided
            if "timestamp" not in health_data:
                health_data["timestamp"] = dt_util.utcnow().isoformat()

            # Add health entry
            self._data["health"][dog_id].append(health_data)

            # Save to storage
            await self.storage.async_save_data("health", self._data["health"])

            # Fire event
            self.hass.bus.async_fire(
                EVENT_HEALTH_LOGGED,
                {
                    "dog_id": dog_id,
                    **health_data,
                },
            )

            _LOGGER.debug("Logged health data for %s", dog_id)

        except Exception as err:
            _LOGGER.error("Failed to log health data for %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to log health data: {err}") from err

    async def async_daily_reset(self) -> None:
        """Reset daily statistics for all dogs.

        This method is called daily to reset counters and prepare
        for the next day's tracking.
        """
        try:
            # Reset daily statistics in the statistics store
            stats_data = self._data.get("statistics", {})

            for dog_id in [dog[CONF_DOG_ID] for dog in self._dogs]:
                if dog_id not in stats_data:
                    stats_data[dog_id] = {}

                # Archive yesterday's stats and reset daily counters
                yesterday = (dt_util.utcnow() - timedelta(days=1)).date().isoformat()

                if "daily" in stats_data[dog_id]:
                    if "history" not in stats_data[dog_id]:
                        stats_data[dog_id]["history"] = {}
                    stats_data[dog_id]["history"][yesterday] = stats_data[dog_id][
                        "daily"
                    ]

                # Reset daily counters
                stats_data[dog_id]["daily"] = {
                    "feedings": 0,
                    "walks": 0,
                    "distance": 0,
                    "duration": 0,
                    "reset_time": dt_util.utcnow().isoformat(),
                }

            self._data["statistics"] = stats_data
            await self.storage.async_save_data("statistics", stats_data)

            _LOGGER.debug("Completed daily reset for %d dogs", len(self._dogs))

        except Exception as err:
            _LOGGER.error("Failed to perform daily reset: %s", err)

    def _is_valid_dog_id(self, dog_id: str) -> bool:
        """Validate that a dog ID exists in the configuration.

        Args:
            dog_id: Dog ID to validate

        Returns:
            True if the dog ID is valid, False otherwise
        """
        return any(dog[CONF_DOG_ID] == dog_id for dog in self._dogs)


class PawControlNotificationManager:
    """Manages notifications for the Paw Control integration.

    Handles all notification logic including quiet hours, priority levels,
    and different notification channels (mobile, persistent, etc.).
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the notification manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry for the integration
        """
        self.hass = hass
        self.config_entry = config_entry
        self._notification_queue: list[dict[str, Any]] = []
        self._setup_notification_processor()

    def _setup_notification_processor(self) -> None:
        """Set up the notification processing task.

        Creates a background task to process queued notifications
        at regular intervals to avoid overwhelming the user.
        """

        async def _process_notifications() -> None:
            """Process queued notifications."""
            if not self._notification_queue:
                return

            # Process up to 3 notifications at once
            notifications_to_send = self._notification_queue[:3]
            self._notification_queue = self._notification_queue[3:]

            for notification in notifications_to_send:
                try:
                    await self._send_notification_now(notification)
                except Exception as err:
                    _LOGGER.error("Failed to send notification: %s", err)

        # Schedule notification processing every 30 seconds
        async_track_time_interval(
            self.hass,
            lambda _: self.hass.async_create_task(_process_notifications()),
            timedelta(seconds=30),
        )

    async def async_send_notification(
        self,
        dog_id: str,
        title: str,
        message: str,
        priority: str = "normal",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Send a notification for a specific dog.

        Args:
            dog_id: Unique identifier for the dog
            title: Notification title
            message: Notification message
            priority: Priority level ("low", "normal", "high", "urgent")
            data: Optional additional data for the notification
        """
        if not self._should_send_notification(priority):
            _LOGGER.debug("Notification suppressed due to quiet hours")
            return

        notification = {
            "dog_id": dog_id,
            "title": title,
            "message": message,
            "priority": priority,
            "data": data or {},
            "timestamp": dt_util.utcnow().isoformat(),
        }

        # High and urgent priority notifications are sent immediately
        if priority in ["high", "urgent"]:
            await self._send_notification_now(notification)
        else:
            # Queue normal and low priority notifications
            self._notification_queue.append(notification)

    async def _send_notification_now(self, notification: dict[str, Any]) -> None:
        """Send a notification immediately.

        Args:
            notification: Notification data to send
        """
        try:
            # Get notification configuration
            self.config_entry.options.get(CONF_NOTIFICATIONS, {})

            # Determine notification service
            service_data = {
                "title": notification["title"],
                "message": notification["message"],
                "notification_id": f"pawcontrol_{notification['dog_id']}_{notification['timestamp']}",
            }

            # Add priority-specific styling
            if notification["priority"] == "urgent":
                service_data["message"] = f"🚨 {service_data['message']}"
            elif notification["priority"] == "high":
                service_data["message"] = f"⚠️ {service_data['message']}"

            # Send the notification
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                service_data,
            )

            _LOGGER.debug(
                "Sent %s priority notification for %s",
                notification["priority"],
                notification["dog_id"],
            )

        except Exception as err:
            _LOGGER.error("Failed to send notification: %s", err)

    def _should_send_notification(self, priority: str) -> bool:
        """Check if a notification should be sent based on quiet hours.

        Args:
            priority: Priority level of the notification

        Returns:
            True if notification should be sent, False otherwise
        """
        notification_config = self.config_entry.options.get(CONF_NOTIFICATIONS, {})

        # Always send urgent notifications
        if priority == "urgent":
            return True

        # Check quiet hours
        if not notification_config.get(CONF_QUIET_HOURS, False):
            return True

        now = dt_util.now().time()
        quiet_start = notification_config.get(CONF_QUIET_START, "22:00:00")
        quiet_end = notification_config.get(CONF_QUIET_END, "07:00:00")

        try:
            quiet_start_time = datetime.strptime(quiet_start, "%H:%M:%S").time()
            quiet_end_time = datetime.strptime(quiet_end, "%H:%M:%S").time()
        except ValueError:
            # Invalid time format, allow notification
            return True

        # Handle quiet hours that span midnight
        if quiet_start_time > quiet_end_time:
            # Quiet hours span midnight (e.g., 22:00 to 07:00)
            return not (now >= quiet_start_time or now <= quiet_end_time)
        else:
            # Quiet hours within same day
            return not (quiet_start_time <= now <= quiet_end_time)


def _data_encoder(obj: Any) -> Any:
    """Custom JSON encoder for data serialization.

    Args:
        obj: Object to encode

    Returns:
        JSON-serializable representation of the object
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, "__dict__"):
        return obj.__dict__
    else:
        return str(obj)
