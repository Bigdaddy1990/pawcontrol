"""Specialized dog data management for PawControl integration.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

Handles core dog data structures, validation, and basic CRUD operations
separated from the main coordinator for better maintainability.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.util import dt as dt_util

from .const import CONF_DOG_ID, CONF_DOG_NAME
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)


class DogDataManager:
    """Manages core dog data structures and validation.

    Separated from coordinator to reduce complexity and improve maintainability.
    Handles dog configuration, basic data storage, and validation.
    """

    def __init__(self) -> None:
        """Initialize dog data manager."""
        self._dogs_data: Dict[str, Dict[str, Any]] = {}
        self._dogs_config: List[DogConfigData] = []
        self._data_lock = asyncio.Lock()
        self._last_updated: Dict[str, datetime] = {}

        # Data validation cache
        self._validation_cache: Dict[str, Any] = {}
        self._cache_expiry: Dict[str, datetime] = {}

        _LOGGER.debug("DogDataManager initialized")

    async def async_initialize(self, dogs_config: List[DogConfigData]) -> None:
        """Initialize with dog configurations.

        Args:
            dogs_config: List of dog configurations from config entry
        """
        async with self._data_lock:
            self._dogs_config = dogs_config.copy()

            # Initialize data structures for each dog
            for dog in self._dogs_config:
                dog_id = dog[CONF_DOG_ID]
                self._dogs_data[dog_id] = {
                    "dog_info": dog,
                    "feeding": {},
                    "walk": {},
                    "health": {},
                    "gps": {},
                    "created_at": dt_util.now().isoformat(),
                    "last_updated": dt_util.now().isoformat(),
                }
                self._last_updated[dog_id] = dt_util.now()

            _LOGGER.info("Initialized data for %d dogs", len(self._dogs_config))

    async def async_get_dog_data(self, dog_id: str) -> Optional[Dict[str, Any]]:
        """Get complete data for a specific dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Complete dog data or None if not found
        """
        async with self._data_lock:
            return (
                self._dogs_data.get(dog_id, {}).copy()
                if dog_id in self._dogs_data
                else None
            )

    async def async_update_dog_data(
        self, dog_id: str, module: str, data: Dict[str, Any]
    ) -> bool:
        """Update data for a specific dog module.

        Args:
            dog_id: Dog identifier
            module: Module name (feeding, walk, health, gps)
            data: New data for the module

        Returns:
            True if update successful
        """
        async with self._data_lock:
            if dog_id not in self._dogs_data:
                _LOGGER.warning("Dog %s not found for data update", dog_id)
                return False

            # Update module data
            self._dogs_data[dog_id][module] = data.copy()
            self._dogs_data[dog_id]["last_updated"] = dt_util.now().isoformat()
            self._last_updated[dog_id] = dt_util.now()

            _LOGGER.debug("Updated %s data for dog %s", module, dog_id)
            return True

    async def async_get_all_dogs_data(self) -> Dict[str, Dict[str, Any]]:
        """Get data for all dogs.

        Returns:
            Dictionary mapping dog_id to complete dog data
        """
        async with self._data_lock:
            return {dog_id: data.copy() for dog_id, data in self._dogs_data.items()}

    def get_dog_config(self, dog_id: str) -> Optional[DogConfigData]:
        """Get configuration for a specific dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Dog configuration or None if not found
        """
        for dog in self._dogs_config:
            if dog.get(CONF_DOG_ID) == dog_id:
                return dog
        return None

    def get_all_dog_configs(self) -> List[DogConfigData]:
        """Get all dog configurations.

        Returns:
            List of all dog configurations
        """
        return self._dogs_config.copy()

    def get_dog_ids(self) -> List[str]:
        """Get list of all dog IDs.

        Returns:
            List of dog identifiers
        """
        return [dog.get(CONF_DOG_ID) for dog in self._dogs_config]

    def get_enabled_modules(self, dog_id: str) -> set[str]:
        """Get enabled modules for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Set of enabled module names
        """
        dog_config = self.get_dog_config(dog_id)
        if not dog_config:
            return set()

        modules = dog_config.get("modules", {})
        return {name for name, enabled in modules.items() if enabled}

    def is_module_enabled(self, dog_id: str, module: str) -> bool:
        """Check if a module is enabled for a dog.

        Args:
            dog_id: Dog identifier
            module: Module name

        Returns:
            True if module is enabled
        """
        return module in self.get_enabled_modules(dog_id)

    async def async_validate_dog_data(
        self, dog_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate dog data for consistency and completeness.

        Args:
            dog_id: Dog identifier
            data: Data to validate

        Returns:
            Validation result with status and errors
        """
        # Check cache first
        cache_key = f"{dog_id}_{hash(str(data))}"
        now = dt_util.now()

        if (
            cache_key in self._validation_cache
            and cache_key in self._cache_expiry
            and now < self._cache_expiry[cache_key]
        ):
            return self._validation_cache[cache_key]

        # Perform validation
        result = await self._perform_validation(dog_id, data)

        # Cache result for 5 minutes
        self._validation_cache[cache_key] = result
        self._cache_expiry[cache_key] = now + timedelta(minutes=5)

        # Clean old cache entries
        await self._clean_validation_cache()

        return result

    async def _perform_validation(
        self, dog_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform actual data validation.

        Args:
            dog_id: Dog identifier
            data: Data to validate

        Returns:
            Validation result
        """
        errors = []
        warnings = []

        dog_config = self.get_dog_config(dog_id)
        if not dog_config:
            errors.append(f"Dog configuration not found for {dog_id}")
            return {"valid": False, "errors": errors, "warnings": warnings}

        # Validate required fields
        required_fields = ["dog_info"]
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Validate dog_info structure
        if "dog_info" in data:
            dog_info = data["dog_info"]
            if not isinstance(dog_info, dict):
                errors.append("dog_info must be a dictionary")
            else:
                # Check required dog_info fields
                required_dog_fields = [CONF_DOG_ID, CONF_DOG_NAME]
                for field in required_dog_fields:
                    if field not in dog_info:
                        errors.append(f"Missing required dog_info field: {field}")
                    elif not dog_info[field]:
                        errors.append(f"Empty required dog_info field: {field}")

        # Validate module data based on enabled modules
        enabled_modules = self.get_enabled_modules(dog_id)
        for module in enabled_modules:
            if module in data:
                module_errors = await self._validate_module_data(module, data[module])
                errors.extend(module_errors)

        # Check for unexpected modules
        valid_modules = {
            "dog_info",
            "feeding",
            "walk",
            "health",
            "gps",
            "created_at",
            "last_updated",
        }
        for key in data:
            if key not in valid_modules:
                warnings.append(f"Unexpected data field: {key}")

        # Validate timestamps
        timestamp_fields = ["created_at", "last_updated"]
        for field in timestamp_fields:
            if field in data:
                if not self._is_valid_timestamp(data[field]):
                    errors.append(f"Invalid timestamp format in {field}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "validated_at": dt_util.now().isoformat(),
        }

    async def _validate_module_data(self, module: str, data: Any) -> List[str]:
        """Validate specific module data.

        Args:
            module: Module name
            data: Module data

        Returns:
            List of validation errors
        """
        errors = []

        if not isinstance(data, dict):
            errors.append(f"{module} data must be a dictionary")
            return errors

        # Module-specific validation
        if module == "feeding":
            if "last_feeding" in data and data["last_feeding"]:
                if not self._is_valid_timestamp(data["last_feeding"]):
                    errors.append("Invalid last_feeding timestamp")

            if "meals_today" in data:
                try:
                    meals = int(data["meals_today"])
                    if meals < 0 or meals > 10:
                        errors.append("meals_today must be between 0 and 10")
                except (ValueError, TypeError):
                    errors.append("meals_today must be a valid integer")

        elif module == "walk":
            if "walk_in_progress" in data:
                if not isinstance(data["walk_in_progress"], bool):
                    errors.append("walk_in_progress must be boolean")

            if "walks_today" in data:
                try:
                    walks = int(data["walks_today"])
                    if walks < 0 or walks > 20:
                        errors.append("walks_today must be between 0 and 20")
                except (ValueError, TypeError):
                    errors.append("walks_today must be a valid integer")

        elif module == "health":
            if "current_weight" in data and data["current_weight"] is not None:
                try:
                    weight = float(data["current_weight"])
                    if weight <= 0 or weight > 150:
                        errors.append("current_weight must be between 0 and 150 kg")
                except (ValueError, TypeError):
                    errors.append("current_weight must be a valid number")

        elif module == "gps":
            if "latitude" in data and data["latitude"] is not None:
                try:
                    lat = float(data["latitude"])
                    if lat < -90 or lat > 90:
                        errors.append("latitude must be between -90 and 90")
                except (ValueError, TypeError):
                    errors.append("latitude must be a valid number")

            if "longitude" in data and data["longitude"] is not None:
                try:
                    lon = float(data["longitude"])
                    if lon < -180 or lon > 180:
                        errors.append("longitude must be between -180 and 180")
                except (ValueError, TypeError):
                    errors.append("longitude must be a valid number")

        return errors

    def _is_valid_timestamp(self, timestamp: Any) -> bool:
        """Check if timestamp is valid.

        Args:
            timestamp: Timestamp to validate

        Returns:
            True if valid timestamp
        """
        if isinstance(timestamp, datetime):
            return True

        if isinstance(timestamp, str):
            try:
                dt_util.parse_datetime(timestamp)
                return True
            except (ValueError, TypeError):
                return False

        return False

    async def _clean_validation_cache(self) -> None:
        """Clean expired validation cache entries."""
        now = dt_util.now()
        expired_keys = [
            key for key, expiry in self._cache_expiry.items() if now > expiry
        ]

        for key in expired_keys:
            self._validation_cache.pop(key, None)
            self._cache_expiry.pop(key, None)

    async def async_get_data_statistics(self) -> Dict[str, Any]:
        """Get data management statistics.

        Returns:
            Statistics about managed data
        """
        async with self._data_lock:
            total_dogs = len(self._dogs_data)

            # Calculate data sizes
            total_data_points = 0
            module_counts = {"feeding": 0, "walk": 0, "health": 0, "gps": 0}

            for dog_data in self._dogs_data.values():
                for module, data in dog_data.items():
                    if module in module_counts and isinstance(data, dict):
                        module_counts[module] += len(data)
                        total_data_points += len(data)

            # Get update statistics
            recent_updates = sum(
                1
                for update_time in self._last_updated.values()
                if (dt_util.now() - update_time).total_seconds() < 300  # Last 5 minutes
            )

            return {
                "total_dogs": total_dogs,
                "total_data_points": total_data_points,
                "module_data_counts": module_counts,
                "recent_updates": recent_updates,
                "validation_cache_size": len(self._validation_cache),
                "last_updated_times": {
                    dog_id: update_time.isoformat()
                    for dog_id, update_time in list(self._last_updated.items())[:5]
                },
            }

    async def async_cleanup(self) -> None:
        """Clean up resources."""
        async with self._data_lock:
            self._dogs_data.clear()
            self._dogs_config.clear()
            self._last_updated.clear()
            self._validation_cache.clear()
            self._cache_expiry.clear()

        _LOGGER.debug("DogDataManager cleanup completed")
