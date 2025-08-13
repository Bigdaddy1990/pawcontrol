"""Setup synchronization helper for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from ..const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOGS,
    CONF_EXPORT_FORMAT,
    CONF_EXPORT_PATH,
    CONF_VISITOR_MODE,
    DEFAULT_GROOMING_INTERVAL_DAYS,
    DOMAIN,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
    MODULE_WALK,
)

_LOGGER = logging.getLogger(__name__)


class SetupSync:
    """Manage idempotent setup synchronization."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize setup sync."""
        self.hass = hass
        self.entry = entry
        self._entity_registry = er.async_get(hass)

    async def sync_all(self) -> None:
        """Synchronize all helpers and entities."""
        _LOGGER.info("Starting full synchronization")

        try:
            # Sync global helpers
            await self._sync_global_helpers()

            # Sync per-dog helpers
            await self._sync_dog_helpers()

            # Clean up orphaned helpers
            await self._cleanup_orphaned_helpers()

            _LOGGER.info("Synchronization completed successfully")

        except Exception as err:
            _LOGGER.error(f"Error during synchronization: {err}")
            raise HomeAssistantError(f"Failed to sync setup: {err}")

    async def _sync_global_helpers(self) -> None:
        """Synchronize global helpers."""
        _LOGGER.debug("Syncing global helpers")

        # Visitor mode toggle
        if self.entry.options.get(CONF_VISITOR_MODE, False):
            await self._ensure_helper(
                "input_boolean",
                f"{DOMAIN}_visitor_mode",
                {
                    "name": "Paw Control - Visitor Mode",
                    "icon": "mdi:account-group",
                },
            )

        # Emergency mode toggle
        await self._ensure_helper(
            "input_boolean",
            f"{DOMAIN}_emergency_mode",
            {
                "name": "Paw Control - Emergency Mode",
                "icon": "mdi:alert-circle",
            },
        )

        # Export settings (if export is configured)
        if self.entry.options.get(CONF_EXPORT_PATH):
            await self._ensure_helper(
                "input_text",
                f"{DOMAIN}_export_path",
                {
                    "name": "Paw Control - Export Path",
                    "icon": "mdi:folder-export",
                    "initial": self.entry.options.get(CONF_EXPORT_PATH, ""),
                    "max": 255,
                },
            )

            await self._ensure_helper(
                "input_select",
                f"{DOMAIN}_export_format",
                {
                    "name": "Paw Control - Export Format",
                    "icon": "mdi:file-export",
                    "options": ["csv", "json", "pdf"],
                    "initial": self.entry.options.get(CONF_EXPORT_FORMAT, "csv"),
                },
            )

            await self._ensure_helper(
                "input_datetime",
                f"{DOMAIN}_last_report",
                {
                    "name": "Paw Control - Last Report",
                    "icon": "mdi:calendar-clock",
                    "has_date": True,
                    "has_time": True,
                },
            )

        # Weather entity storage (optional)
        weather_entity = self.entry.options.get("sources", {}).get("weather")
        if weather_entity:
            await self._ensure_helper(
                "input_text",
                f"{DOMAIN}_weather_entity",
                {
                    "name": "Paw Control - Weather Entity",
                    "icon": "mdi:weather-partly-cloudy",
                    "initial": weather_entity,
                    "max": 255,
                },
            )

    async def _sync_dog_helpers(self) -> None:
        """Synchronize per-dog helpers."""
        dogs = self.entry.options.get(CONF_DOGS, [])

        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            if not dog_id:
                continue

            modules = dog.get(CONF_DOG_MODULES, {})

            _LOGGER.debug(f"Syncing helpers for dog: {dog_id}")

            # Walk/Activity module helpers
            if modules.get(MODULE_WALK, False):
                await self._sync_walk_helpers(dog_id)

            # Training module helpers
            if modules.get(MODULE_TRAINING, False):
                await self._sync_training_helpers(dog_id)

            # Grooming module helpers
            if modules.get(MODULE_GROOMING, False) or modules.get(MODULE_HEALTH, False):
                await self._sync_grooming_helpers(dog_id)

            # Always create basic tracking helpers
            await self._sync_basic_helpers(dog_id)

    async def _sync_walk_helpers(self, dog_id: str) -> None:
        """Synchronize walk-related helpers for a dog."""
        await self._ensure_helper(
            "input_datetime",
            f"{DOMAIN}_{dog_id}_last_walk",
            {
                "name": f"Last Walk - {dog_id}",
                "icon": "mdi:dog-side",
                "has_date": True,
                "has_time": True,
            },
        )

        await self._ensure_helper(
            "input_number",
            f"{DOMAIN}_{dog_id}_last_walk_duration_min",
            {
                "name": f"Last Walk Duration - {dog_id}",
                "icon": "mdi:timer",
                "min": 0,
                "max": 600,
                "step": 1,
                "unit_of_measurement": "min",
            },
        )

        await self._ensure_helper(
            "input_number",
            f"{DOMAIN}_{dog_id}_last_walk_distance_m",
            {
                "name": f"Last Walk Distance - {dog_id}",
                "icon": "mdi:map-marker-distance",
                "min": 0,
                "max": 100000,
                "step": 1,
                "unit_of_measurement": "m",
            },
        )

    async def _sync_training_helpers(self, dog_id: str) -> None:
        """Synchronize training-related helpers for a dog."""
        await self._ensure_helper(
            "input_text",
            f"{DOMAIN}_{dog_id}_last_training_topic",
            {
                "name": f"Last Training Topic - {dog_id}",
                "icon": "mdi:school",
                "max": 255,
            },
        )

        await self._ensure_helper(
            "input_number",
            f"{DOMAIN}_{dog_id}_last_training_duration_min",
            {
                "name": f"Last Training Duration - {dog_id}",
                "icon": "mdi:timer-outline",
                "min": 0,
                "max": 240,
                "step": 1,
                "unit_of_measurement": "min",
            },
        )

    async def _sync_grooming_helpers(self, dog_id: str) -> None:
        """Synchronize grooming-related helpers for a dog."""
        await self._ensure_helper(
            "input_select",
            f"{DOMAIN}_{dog_id}_grooming_type",
            {
                "name": f"Grooming Type - {dog_id}",
                "icon": "mdi:content-cut",
                "options": ["bath", "brush", "trim", "nails", "ears", "teeth", "eyes"],
                "initial": "brush",
            },
        )

        await self._ensure_helper(
            "input_datetime",
            f"{DOMAIN}_{dog_id}_last_grooming",
            {
                "name": f"Last Grooming - {dog_id}",
                "icon": "mdi:shower",
                "has_date": True,
                "has_time": False,
            },
        )

        await self._ensure_helper(
            "input_number",
            f"{DOMAIN}_{dog_id}_grooming_interval_days",
            {
                "name": f"Grooming Interval - {dog_id}",
                "icon": "mdi:calendar-repeat",
                "min": 1,
                "max": 365,
                "step": 1,
                "initial": DEFAULT_GROOMING_INTERVAL_DAYS,
                "unit_of_measurement": "days",
            },
        )

    async def _sync_basic_helpers(self, dog_id: str) -> None:
        """Synchronize basic tracking helpers for a dog."""
        # Last action timestamp
        await self._ensure_helper(
            "input_datetime",
            f"{DOMAIN}_{dog_id}_last_action",
            {
                "name": f"Last Action - {dog_id}",
                "icon": "mdi:history",
                "has_date": True,
                "has_time": True,
            },
        )

    async def _ensure_helper(
        self, component: str, entity_id: str, config: Dict[str, Any]
    ) -> None:
        """Ensure a helper entity exists with the given configuration."""
        full_entity_id = f"{component}.{entity_id}"

        # Check if entity already exists
        if self.hass.states.get(full_entity_id) is not None:
            _LOGGER.debug(f"Helper {full_entity_id} already exists")
            return

        # Create the helper
        try:
            # Map component to service
            service_map = {
                "input_boolean": "create_boolean",
                "input_datetime": "create_datetime",
                "input_number": "create_number",
                "input_select": "create_select",
                "input_text": "create_text",
            }

            service = service_map.get(component)
            if not service:
                _LOGGER.error(f"Unknown helper component: {component}")
                return

            # Note: In a real implementation, we would use the actual helper creation services
            # For now, we'll log the intent
            _LOGGER.info(f"Would create helper: {full_entity_id} with config: {config}")

            # In production, you would call:
            # await self.hass.services.async_call(
            #     component,
            #     service,
            #     service_data,
            #     blocking=True,
            # )

        except Exception as err:
            _LOGGER.error(f"Failed to create helper {full_entity_id}: {err}")

    async def _cleanup_orphaned_helpers(self) -> None:
        """Remove helpers for dogs that no longer exist."""
        current_dog_ids = [
            dog.get(CONF_DOG_ID)
            for dog in self.entry.options.get(CONF_DOGS, [])
            if dog.get(CONF_DOG_ID)
        ]

        # Get all entities for this integration
        entities = er.async_entries_for_config_entry(
            self._entity_registry, self.entry.entry_id
        )

        for entity in entities:
            # Extract dog_id from entity_id if present
            entity_id_parts = entity.entity_id.split(".")
            if len(entity_id_parts) > 1:
                entity_name = entity_id_parts[1]

                # Check if this is a dog-specific entity
                if entity_name.startswith(f"{DOMAIN}_"):
                    # Extract potential dog_id
                    remaining = entity_name[len(f"{DOMAIN}_") :]
                    parts = remaining.split("_")

                    if parts and parts[0] not in current_dog_ids:
                        # Check if this looks like a dog_id (not a global helper)
                        if parts[0] not in [
                            "visitor",
                            "emergency",
                            "export",
                            "last",
                            "weather",
                        ]:
                            _LOGGER.info(
                                f"Would remove orphaned entity: {entity.entity_id}"
                            )
                            # In production:
                            # self._entity_registry.async_remove(entity.entity_id)

    async def cleanup_all(self) -> None:
        """Remove all helpers created by this integration."""
        _LOGGER.info("Cleaning up all Paw Control helpers")

        # Get all entities for this integration
        entities = er.async_entries_for_config_entry(
            self._entity_registry, self.entry.entry_id
        )

        for entity in entities:
            _LOGGER.info(f"Would remove entity: {entity.entity_id}")
            # In production:
            # self._entity_registry.async_remove(entity.entity_id)
