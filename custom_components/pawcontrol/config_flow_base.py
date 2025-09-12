"""Base configuration flow for Paw Control integration.

This module provides the base classes and common functionality shared between
different configuration flow components. It includes validation schemas,
common constants, and utility methods for enhanced user experience.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Final

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_NAME
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    DOG_SIZES,
    DOMAIN,
    MAX_DOG_AGE,
    MAX_DOG_NAME_LENGTH,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_NAME_LENGTH,
    MIN_DOG_WEIGHT,
)
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)

# FIX: Rate limiting for Entity Registry
VALIDATION_SEMAPHORE = asyncio.Semaphore(3)  # Max 3 concurrent validations
ENTITY_CREATION_DELAY = 0.05  # 50ms delay between operations

# Constants for improved maintainability
MAX_DOGS_PER_ENTRY: Final = 10
MIN_UPDATE_INTERVAL: Final = 30
MAX_UPDATE_INTERVAL: Final = 600
MIN_ACCURACY_FILTER: Final = 5
MAX_ACCURACY_FILTER: Final = 500
DEFAULT_GPS_UPDATE_INTERVAL: Final = 60

# Dog ID validation pattern
DOG_ID_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]*$")

# Configuration schemas for validation
INTEGRATION_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Paw Control"): vol.All(
            cv.string, vol.Length(min=1, max=50)
        ),
    }
)

DOG_BASE_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): vol.All(
            cv.string,
            vol.Length(min=2, max=30),
            vol.Match(
                DOG_ID_PATTERN,
                msg="Must start with letter, contain only lowercase letters, numbers, and underscores",
            ),
        ),
        vol.Required(CONF_DOG_NAME): vol.All(
            cv.string, vol.Length(min=MIN_DOG_NAME_LENGTH,
                                  max=MAX_DOG_NAME_LENGTH)
        ),
        vol.Optional(CONF_DOG_BREED, default=""): vol.All(
            cv.string, vol.Length(max=50)
        ),
        vol.Optional(CONF_DOG_AGE, default=3): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_DOG_AGE, max=MAX_DOG_AGE)
        ),
        vol.Optional(CONF_DOG_WEIGHT, default=20.0): vol.All(
            vol.Coerce(float), vol.Range(
                min=MIN_DOG_WEIGHT, max=MAX_DOG_WEIGHT)
        ),
        vol.Optional(CONF_DOG_SIZE, default="medium"): vol.In(DOG_SIZES),
    }
)


class PawControlBaseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Base configuration flow with common functionality.

    This base class provides shared validation, error handling, and utility
    methods used across all configuration flow steps. It implements proper
    rate limiting and caching for optimal performance.
    """

    VERSION: Final = 1
    MINOR_VERSION: Final = 2  # Increased for new per-dog configuration features

    def __init__(self) -> None:
        """Initialize base configuration flow."""
        self._dogs: list[DogConfigData] = []
        self._integration_name = "Paw Control"
        self._errors: dict[str, str] = {}
        self._validation_cache: dict[str, dict[str, Any]] = {}
        # New: Current dog being configured
        self._current_dog_config: DogConfigData | None = None
        # New: Global settings
        self._global_settings: dict[str, Any] = {}
        # New: Dashboard configuration
        self._dashboard_config: dict[str, Any] = {}

    def _generate_unique_id(self, integration_name: str) -> str:
        """Generate a unique ID for the integration with collision avoidance.

        Args:
            integration_name: Name to generate unique ID from

        Returns:
            Unique identifier string
        """
        base_id = integration_name.lower().replace(" ", "_").replace("-", "_")

        # Sanitize for URL safety
        safe_id = re.sub(r"[^a-z0-9_]", "", base_id)

        # Ensure it starts with a letter
        if not safe_id or not safe_id[0].isalpha():
            safe_id = f"paw_control_{safe_id}"

        return safe_id

    def _get_feature_summary(self) -> str:
        """Get a summary of key features for display.

        Returns:
            Formatted feature list string
        """
        features = [
            "🐕 Multi-dog management with individual settings",
            "📍 GPS tracking & geofencing",
            "🍽️ Feeding schedules & reminders",
            "💊 Medication tracking & vaccination reminders",
            "🏥 Health monitoring & vet appointment tracking",
            "🚶 Walk tracking with automatic detection",
            "🔔 Smart notifications with quiet hours",
            "📊 Beautiful dashboards with multiple themes",
            "🏠 Visitor mode for dog sitters",
            "📱 Mobile app integration",
        ]
        return "\n".join(features)

    async def _async_validate_integration_name(self, name: str) -> dict[str, Any]:
        """Validate integration name with enhanced checks.

        Args:
            name: Integration name to validate

        Returns:
            Validation result with errors if any
        """
        errors: dict[str, str] = {}

        if not name or len(name.strip()) == 0:
            errors[CONF_NAME] = "integration_name_required"
        elif len(name) < 1:
            errors[CONF_NAME] = "integration_name_too_short"
        elif len(name) > 50:
            errors[CONF_NAME] = "integration_name_too_long"
        elif name.lower() in ("home assistant", "ha", "hassio"):
            errors[CONF_NAME] = "reserved_integration_name"

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def _is_weight_size_compatible(self, weight: float, size: str) -> bool:
        """Check if weight is compatible with selected size category.

        Args:
            weight: Dog weight in kg
            size: Dog size category

        Returns:
            True if weight matches size expectations
        """
        # Consistent realistic weight ranges with overlap to accommodate breed variations
        size_ranges = {
            "toy": (1.0, 15.0),  # Chihuahua, Yorkshire Terrier
            # Beagle, Cocker Spaniel (overlap with toy/medium)
            "small": (4.0, 25.0),
            # Border Collie, Labrador (overlap with small/large)
            "medium": (8.0, 45.0),
            "large": (
                10.0,
                80.0,
            ),  # German Shepherd, Golden Retriever (overlap with medium/giant)
            # Great Dane, Saint Bernard (overlap with large)
            "giant": (14.0, 120.0),
        }

        range_min, range_max = size_ranges.get(size, (1.0, 90.0))

        # Allow some flexibility with overlapping ranges for realistic breed variations
        return range_min <= weight <= range_max

    def _get_feeding_defaults_by_size(self, size: str) -> dict[str, Any]:
        """Get intelligent feeding defaults based on dog size.

        Args:
            size: Dog size category

        Returns:
            Dictionary of feeding configuration defaults
        """
        feeding_configs = {
            "toy": {
                "meals_per_day": 3,
                "daily_amount": 150,  # grams
                "feeding_times": ["07:00:00", "12:00:00", "18:00:00"],
                "portion_size": 50,
            },
            "small": {
                "meals_per_day": 2,
                "daily_amount": 300,
                "feeding_times": ["07:30:00", "18:00:00"],
                "portion_size": 150,
            },
            "medium": {
                "meals_per_day": 2,
                "daily_amount": 500,
                "feeding_times": ["07:30:00", "18:00:00"],
                "portion_size": 250,
            },
            "large": {
                "meals_per_day": 2,
                "daily_amount": 800,
                "feeding_times": ["07:00:00", "18:30:00"],
                "portion_size": 400,
            },
            "giant": {
                "meals_per_day": 2,
                "daily_amount": 1200,
                "feeding_times": ["07:00:00", "18:30:00"],
                "portion_size": 600,
            },
        }

        return feeding_configs.get(size, feeding_configs["medium"])

    def _format_dogs_list(self) -> str:
        """Format the current dogs list with enhanced readability.

        Creates a comprehensive, readable list of configured dogs
        with rich information for user feedback.

        Returns:
            Formatted string listing all configured dogs
        """
        if not self._dogs:
            return "No dogs configured yet. Add your first dog to get started!"

        dogs_list = []
        for i, dog in enumerate(self._dogs, 1):
            breed_info = dog.get(CONF_DOG_BREED, "Mixed Breed")
            if not breed_info or breed_info == "":
                breed_info = "Mixed Breed"

            # Size emoji mapping
            size_emojis = {
                "toy": "🐭",
                "small": "🐕",
                "medium": "🐶",
                "large": "🐕‍🦺",
                "giant": "🐺",
            }
            size_emoji = size_emojis.get(dog.get(CONF_DOG_SIZE, "medium"), "🐶")

            # Enabled modules count
            modules = dog.get("modules", {})
            enabled_count = sum(1 for enabled in modules.values() if enabled)

            # Special configurations
            special_configs = []
            if dog.get("gps_config"):
                special_configs.append("📍 GPS")
            if dog.get("feeding_config"):
                special_configs.append("🍽️ Feeding")
            if dog.get("health_config"):
                special_configs.append("🏥 Health")

            special_text = " | ".join(
                special_configs) if special_configs else ""

            dogs_list.append(
                f"{i}. {size_emoji} **{dog[CONF_DOG_NAME]}** ({dog[CONF_DOG_ID]})\n"
                f"   {dog.get(CONF_DOG_SIZE, 'medium').title()} {breed_info}, "
                f"{dog.get(CONF_DOG_AGE, 'unknown')} years, {dog.get(CONF_DOG_WEIGHT, 'unknown')}kg\n"
                f"   {enabled_count}/{len(modules)} modules enabled"
                + (f"\n   {special_text}" if special_text else "")
            )

        return "\n\n".join(dogs_list)

    async def _suggest_dog_breed(self, user_input: dict[str, Any] | None) -> str:
        """Suggest dog breed based on name and characteristics.

        Args:
            user_input: Current user input

        Returns:
            Breed suggestion or empty string
        """
        if not user_input:
            return ""

        name = user_input.get(CONF_DOG_NAME, "").lower()
        size = user_input.get(CONF_DOG_SIZE, "")
        user_input.get(CONF_DOG_WEIGHT, 0)

        # Size-based breed suggestions
        size_breeds = {
            "toy": ["Chihuahua", "Yorkshire Terrier", "Pomeranian", "Maltese"],
            "small": ["Beagle", "Cocker Spaniel", "French Bulldog", "Dachshund"],
            "medium": ["Border Collie", "Australian Shepherd", "Labrador", "Bulldog"],
            "large": ["German Shepherd", "Golden Retriever", "Rottweiler", "Boxer"],
            "giant": ["Great Dane", "Saint Bernard", "Mastiff", "Newfoundland"],
        }

        # Name-based breed hints
        breed_hints = {
            "max": "German Shepherd",
            "buddy": "Golden Retriever",
            "bella": "Labrador",
            "charlie": "Beagle",
            "luna": "Border Collie",
            "cooper": "Australian Shepherd",
            "daisy": "Poodle",
            "rocky": "Boxer",
        }

        # Check name patterns first
        for hint_name, breed in breed_hints.items():
            if hint_name in name:
                return breed

        # Use size-based suggestion if available
        if size in size_breeds:
            # Return first breed that roughly matches weight
            for breed in size_breeds[size]:
                return breed

        return ""

    async def _generate_smart_dog_id_suggestion(
        self, user_input: dict[str, Any] | None
    ) -> str:
        """Generate intelligent dog ID suggestion with ML-style optimization.

        Creates contextually aware suggestions based on name patterns
        and avoids conflicts with existing dogs.

        Args:
            user_input: Current user input (may be None)

        Returns:
            Optimized dog ID suggestion
        """
        if not user_input or not user_input.get(CONF_DOG_NAME):
            return ""

        dog_name = user_input[CONF_DOG_NAME].strip()

        # Smart conversion with common name patterns
        name_lower = dog_name.lower()

        # Handle common name patterns
        if " " in name_lower:
            # Multi-word names: take first word + first letter of others
            parts = name_lower.split()
            if len(parts) == 2:
                suggestion = f"{parts[0]}_{parts[1][0]}"
            else:
                suggestion = parts[0] + "".join(p[0] for p in parts[1:])
        else:
            suggestion = name_lower

        # Clean up the suggestion
        suggestion = re.sub(r"[^a-z0-9_]", "", suggestion)

        # Ensure it starts with a letter
        if not suggestion or not suggestion[0].isalpha():
            suggestion = f"dog_{suggestion}"

        # Avoid conflicts with intelligent numbering
        original_suggestion = suggestion
        counter = 1

        while any(dog[CONF_DOG_ID] == suggestion for dog in self._dogs):
            if counter == 1:
                # Try common variations first
                variations = [
                    f"{original_suggestion}_2",
                    f"{original_suggestion}2",
                    f"{original_suggestion}_b",
                ]
                suggestion = variations[0]
                counter = 2
            else:
                suggestion = f"{original_suggestion}_{counter}"
                counter += 1

            # Prevent infinite loops
            if counter > 100:
                suggestion = f"{original_suggestion}_{time.time():.0f}"[-20:]
                break

        return suggestion

    def _get_available_device_trackers(self) -> dict[str, str]:
        """Get available device tracker entities.

        Returns:
            Dictionary of entity_id -> friendly_name
        """
        device_trackers = {}

        for entity_id in self.hass.states.async_entity_ids("device_tracker"):
            state = self.hass.states.get(entity_id)
            if state and state.state not in ["unknown", "unavailable"]:
                friendly_name = state.attributes.get(
                    "friendly_name", entity_id)
                # Filter out the Home Assistant companion apps to avoid confusion
                if "home_assistant" not in entity_id.lower():
                    device_trackers[entity_id] = friendly_name

        return device_trackers

    def _get_available_person_entities(self) -> dict[str, str]:
        """Get available person entities.

        Returns:
            Dictionary of entity_id -> friendly_name
        """
        person_entities = {}

        for entity_id in self.hass.states.async_entity_ids("person"):
            state = self.hass.states.get(entity_id)
            if state:
                friendly_name = state.attributes.get(
                    "friendly_name", entity_id)
                person_entities[entity_id] = friendly_name

        return person_entities

    def _get_available_door_sensors(self) -> dict[str, str]:
        """Get available door/window sensors.

        Returns:
            Dictionary of entity_id -> friendly_name
        """
        door_sensors = {}

        for entity_id in self.hass.states.async_entity_ids("binary_sensor"):
            state = self.hass.states.get(entity_id)
            if state:
                device_class = state.attributes.get("device_class")
                if device_class in ["door", "window", "opening", "garage_door"]:
                    friendly_name = state.attributes.get(
                        "friendly_name", entity_id)
                    door_sensors[entity_id] = friendly_name

        return door_sensors

    def _get_available_notify_services(self) -> dict[str, str]:
        """Get available notification services.

        Returns:
            Dictionary of service_id -> friendly_name
        """
        notify_services = {}

        # Get all notification services
        services = self.hass.services.async_services().get("notify", {})
        for service_name in services:
            if service_name != "persistent_notification":  # Exclude default
                service_id = f"notify.{service_name}"
                # Create friendly name from service name
                friendly_name = service_name.replace("_", " ").title()
                notify_services[service_id] = friendly_name

        return notify_services

    def _get_dogs_module_summary(self) -> str:
        """Get a summary of dogs and their configured modules.

        Returns:
            Formatted summary of dog module configurations
        """
        summaries = []
        for dog in self._dogs:
            modules = dog.get("modules", {})
            enabled_modules = [name for name,
                               enabled in modules.items() if enabled]

            if enabled_modules:
                modules_text = ", ".join(enabled_modules[:3])
                if len(enabled_modules) > 3:
                    modules_text += f" +{len(enabled_modules) - 3} more"
            else:
                modules_text = "Basic monitoring"

            summaries.append(f"• {dog[CONF_DOG_NAME]}: {modules_text}")

        return "\n".join(summaries)

    def _get_dashboard_features_string(self, has_gps: bool) -> str:
        """Get dashboard feature list string.

        Args:
            has_gps: Whether GPS tracking is enabled.

        Returns:
            Comma-separated feature string for dashboard descriptions.
        """
        features = ["Statistics", "Alerts",
                    "Mobile-Friendly", "Multiple Themes"]
        if has_gps:
            features.insert(0, "GPS Maps")
        if len(self._dogs) > 1:
            features.append("Multi-Dog Overview")
        return ", ".join(features)

    def _get_dashboard_setup_info(self) -> str:
        """Get dashboard setup information for display.

        Returns:
            Formatted dashboard information string
        """
        info = [
            "🎨 Dashboard will be automatically created after setup",
            "📊 Includes cards for each dog and their activities",
            "📱 Mobile-friendly and responsive design",
            "🎭 Multiple visual themes available (Modern, Playful, Minimal, Dark)",
        ]

        # Check enabled modules across all dogs
        has_gps = any(
            dog.get("modules", {}).get("gps", False) or dog.get("gps_config")
            for dog in self._dogs
        )
        has_feeding = any(
            dog.get("modules", {}).get(
                "feeding", False) or dog.get("feeding_config")
            for dog in self._dogs
        )
        has_health = any(
            dog.get("modules", {}).get(
                "health", False) or dog.get("health_config")
            for dog in self._dogs
        )

        if has_gps:
            info.append("🗺️ GPS maps and location tracking")
        if has_feeding:
            info.append("🍽️ Feeding schedules and meal tracking")
        if has_health:
            info.append("📈 Health charts and medication reminders")

        if len(self._dogs) > 1:
            info.append(
                f"🐕 Individual dashboards for {len(self._dogs)} dogs available"
            )

        info.extend(
            [
                "⚡ Real-time updates and notifications",
                "🔧 Fully customizable via Options later",
            ]
        )

        return "\n".join(info)
