"""Base configuration flow for Paw Control integration.

This module provides the base classes and common functionality shared between
different configuration flow components. It includes validation schemas,
common constants, and utility methods for enhanced user experience.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

import asyncio
import logging
import re
import time
from typing import ClassVar, Final

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_NAME
import voluptuous as vol

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
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_WEIGHT,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
)
from .selector_shim import selector
from .types import (
    DOG_AGE_FIELD,
    DOG_BREED_FIELD,
    DOG_FEEDING_CONFIG_FIELD,
    DOG_GPS_CONFIG_FIELD,
    DOG_HEALTH_CONFIG_FIELD,
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    DOG_SIZE_FIELD,
    DOG_WEIGHT_FIELD,
    ConfigFlowGlobalSettings,
    DashboardSetupConfig,
    DogConfigData,
    DogSetupStepInput,
    DogValidationCache,
    FeedingSetupConfig,
    FeedingSizeDefaults,
    FeedingSizeDefaultsMap,
    IntegrationNameValidationResult,
    ensure_dog_modules_mapping,
)

_LOGGER = logging.getLogger(__name__)

# FIX: Rate limiting for Entity Registry
VALIDATION_SEMAPHORE = asyncio.Semaphore(3)  # Max 3 concurrent validations
ENTITY_CREATION_DELAY = 0.05  # 50ms delay between operations

# Constants for improved maintainability
MIN_UPDATE_INTERVAL: Final = 30
MAX_UPDATE_INTERVAL: Final = 600
MIN_ACCURACY_FILTER: Final = 5
MAX_ACCURACY_FILTER: Final = 500
DEFAULT_GPS_UPDATE_INTERVAL: Final = 60

# Configuration schemas for validation
INTEGRATION_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Paw Control"): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT,
                autocomplete="organization",
            ),
        ),
    },
)

DOG_BASE_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT,
                autocomplete="off",
            ),
        ),
        vol.Required(CONF_DOG_NAME): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT,
                autocomplete="name",
            ),
        ),
        vol.Optional(CONF_DOG_BREED, default=""): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT,
                autocomplete="off",
            ),
        ),
        vol.Optional(CONF_DOG_AGE, default=3): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_DOG_AGE,
                max=MAX_DOG_AGE,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="years",
            ),
        ),
        vol.Optional(CONF_DOG_WEIGHT, default=20.0): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_DOG_WEIGHT,
                max=MAX_DOG_WEIGHT,
                step=0.1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="kg",
            ),
        ),
        vol.Optional(CONF_DOG_SIZE, default="medium"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(DOG_SIZES),
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key="dog_size",
            ),
        ),
    },
)


class PawControlBaseConfigFlow(ConfigFlow):  # type: ignore[misc]
    """Base configuration flow with common functionality.

    This base class provides shared validation, error handling, and utility
    methods used across all configuration flow steps. It implements proper
    rate limiting and caching for optimal performance.
    """  # noqa: E111

    domain = DOMAIN  # noqa: E111
    VERSION: ClassVar[int] = 1  # noqa: E111
    # Increased for new per-dog configuration features  # noqa: E114
    MINOR_VERSION: ClassVar[int] = 2  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        """Initialize base configuration flow."""
        super().__init__()
        self._dogs: list[DogConfigData] = []
        self._integration_name = "Paw Control"
        self._errors: dict[str, str] = {}
        self._validation_cache: DogValidationCache = {}
        # New: Current dog being configured
        self._current_dog_config: DogConfigData | None = None
        # New: Global settings
        self._global_settings: ConfigFlowGlobalSettings = {}
        # New: Dashboard configuration
        self._dashboard_config: DashboardSetupConfig = {}
        # Feeding defaults captured when configuring modules
        self._feeding_config: FeedingSetupConfig = {}

    def _generate_unique_id(self, integration_name: str) -> str:  # noqa: E111
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
            safe_id = f"paw_control_{safe_id}"  # noqa: E111

        return safe_id

    def _get_feature_summary(self) -> str:  # noqa: E111
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

    async def _async_validate_integration_name(  # noqa: E111
        self,
        name: str,
    ) -> IntegrationNameValidationResult:
        """Validate integration name with enhanced checks.

        Args:
            name: Integration name to validate

        Returns:
            Validation result with errors if any
        """
        errors: dict[str, str] = {}

        if not name or len(name.strip()) == 0:
            errors[CONF_NAME] = "integration_name_required"  # noqa: E111
        elif len(name) < 1:
            errors[CONF_NAME] = "integration_name_too_short"  # noqa: E111
        elif len(name) > 50:
            errors[CONF_NAME] = "integration_name_too_long"  # noqa: E111
        elif name.lower() in ("home assistant", "ha", "hassio"):
            errors[CONF_NAME] = "reserved_integration_name"  # noqa: E111

        result: IntegrationNameValidationResult = {
            "valid": len(errors) == 0,
            "errors": errors,
        }

        return result

    def _is_weight_size_compatible(self, weight: float, size: str) -> bool:  # noqa: E111
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

    def _get_feeding_defaults_by_size(self, size: str) -> FeedingSizeDefaults:  # noqa: E111
        """Get intelligent feeding defaults based on dog size.

        Args:
            size: Dog size category

        Returns:
            Dictionary of feeding configuration defaults
        """
        feeding_configs: FeedingSizeDefaultsMap = {
            "toy": {
                "meals_per_day": 3,
                "daily_food_amount": 150,  # grams
                "feeding_times": ["07:00:00", "12:00:00", "18:00:00"],
                "portion_size": 50,
            },
            "small": {
                "meals_per_day": 2,
                "daily_food_amount": 300,
                "feeding_times": ["07:30:00", "18:00:00"],
                "portion_size": 150,
            },
            "medium": {
                "meals_per_day": 2,
                "daily_food_amount": 500,
                "feeding_times": ["07:30:00", "18:00:00"],
                "portion_size": 250,
            },
            "large": {
                "meals_per_day": 2,
                "daily_food_amount": 800,
                "feeding_times": ["07:00:00", "18:30:00"],
                "portion_size": 400,
            },
            "giant": {
                "meals_per_day": 2,
                "daily_food_amount": 1200,
                "feeding_times": ["07:00:00", "18:30:00"],
                "portion_size": 600,
            },
        }

        default_config: FeedingSizeDefaults = feeding_configs["medium"]

        return feeding_configs.get(size, default_config)

    def _format_dogs_list(self) -> str:  # noqa: E111
        """Format the current dogs list with enhanced readability.

        Creates a comprehensive, readable list of configured dogs
        with rich information for user feedback.

        Returns:
            Formatted string listing all configured dogs
        """
        if not self._dogs:
            return "No dogs configured yet. Add your first dog to get started!"  # noqa: E111

        dogs_list = []
        for i, dog in enumerate(self._dogs, 1):
            breed_value = dog.get(DOG_BREED_FIELD)  # noqa: E111
            breed_info = (  # noqa: E111
                breed_value
                if isinstance(
                    breed_value,
                    str,
                )
                else "Mixed Breed"
            )
            if not breed_info or breed_info == "":  # noqa: E111
                breed_info = "Mixed Breed"

            # Size emoji mapping  # noqa: E114
            size_emojis = {  # noqa: E111
                "toy": "🐭",
                "small": "🐕",
                "medium": "🐶",
                "large": "🐕‍🦺",
                "giant": "🐺",
            }
            dog_size = dog.get(DOG_SIZE_FIELD)  # noqa: E111
            size_key = dog_size if isinstance(dog_size, str) else "medium"  # noqa: E111
            size_emoji = size_emojis.get(size_key, "🐶")  # noqa: E111

            # Enabled modules count  # noqa: E114
            modules_mapping = ensure_dog_modules_mapping(dog)  # noqa: E111
            enabled_count = sum(1 for enabled in modules_mapping.values() if enabled)  # noqa: E111
            total_modules = len(modules_mapping)  # noqa: E111

            # Special configurations  # noqa: E114
            special_configs = []  # noqa: E111
            if dog.get(DOG_GPS_CONFIG_FIELD):  # noqa: E111
                special_configs.append("📍 GPS")
            if dog.get(DOG_FEEDING_CONFIG_FIELD):  # noqa: E111
                special_configs.append("🍽️ Feeding")
            if dog.get(DOG_HEALTH_CONFIG_FIELD):  # noqa: E111
                special_configs.append("🏥 Health")

            special_text = (  # noqa: E111
                " | ".join(
                    special_configs,
                )
                if special_configs
                else ""
            )

            dogs_list.append(  # noqa: E111
                f"{i}. {size_emoji} **{dog[DOG_NAME_FIELD]}** ({dog[DOG_ID_FIELD]})\n"
                f"   {size_key.title()} {breed_info}, "
                f"{dog.get(DOG_AGE_FIELD, 'unknown')} years, {dog.get(DOG_WEIGHT_FIELD, 'unknown')}kg\n"  # noqa: E501
                f"   {enabled_count}/{total_modules} modules enabled"
                + (f"\n   {special_text}" if special_text else ""),
            )

        return "\n\n".join(dogs_list)

    async def _suggest_dog_breed(self, user_input: DogSetupStepInput | None) -> str:  # noqa: E111
        """Suggest dog breed based on name and characteristics.

        Args:
            user_input: Current user input

        Returns:
            Breed suggestion or empty string
        """
        if not user_input:
            return ""  # noqa: E111

        name = str(user_input.get(DOG_NAME_FIELD, "")).lower()
        size = user_input.get(DOG_SIZE_FIELD, "")
        user_input.get(DOG_WEIGHT_FIELD, 0)

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
            if hint_name in name:  # noqa: E111
                return breed

        # Use size-based suggestion if available
        if size in size_breeds:
            # Return first breed that roughly matches weight  # noqa: E114
            for breed in size_breeds[size]:  # noqa: E111
                return breed

        return ""

    async def _generate_smart_dog_id_suggestion(  # noqa: E111
        self,
        user_input: DogSetupStepInput | None,
    ) -> str:
        """Generate intelligent dog ID suggestion with ML-style optimization.

        Creates contextually aware suggestions based on name patterns
        and avoids conflicts with existing dogs.

        Args:
            user_input: Current user input (may be None)

        Returns:
            Optimized dog ID suggestion
        """
        if not user_input or not user_input.get(DOG_NAME_FIELD):
            return ""  # noqa: E111

        dog_name = user_input[DOG_NAME_FIELD].strip()

        # Smart conversion with common name patterns
        name_lower = dog_name.lower()

        # Handle common name patterns
        if " " in name_lower:
            # Multi-word names: take first word + first letter of others  # noqa: E114
            parts = name_lower.split()  # noqa: E111
            if len(parts) == 2:  # noqa: E111
                suggestion = f"{parts[0]}_{parts[1][0]}"
            else:  # noqa: E111
                suggestion = parts[0] + "".join(p[0] for p in parts[1:])
        else:
            suggestion = name_lower  # noqa: E111

        # Clean up the suggestion
        suggestion = re.sub(r"[^a-z0-9_]", "", suggestion)

        # Ensure it starts with a letter
        if not suggestion or not suggestion[0].isalpha():
            suggestion = f"dog_{suggestion}"  # noqa: E111

        # Avoid conflicts with intelligent numbering
        original_suggestion = suggestion
        counter = 1

        while any(dog[DOG_ID_FIELD] == suggestion for dog in self._dogs):
            if counter == 1:  # noqa: E111
                # Try common variations first
                variations = [
                    f"{original_suggestion}_2",
                    f"{original_suggestion}2",
                    f"{original_suggestion}_b",
                ]
                suggestion = variations[0]
                counter = 2
            else:  # noqa: E111
                suggestion = f"{original_suggestion}_{counter}"
                counter += 1

            # Prevent infinite loops  # noqa: E114
            if counter > 100:  # noqa: E111
                suggestion = f"{original_suggestion}_{time.time():.0f}"[-20:]
                break

        return suggestion

    def _get_available_device_trackers(self) -> dict[str, str]:  # noqa: E111
        """Get available device tracker entities.

        Returns:
            Dictionary of entity_id -> friendly_name
        """
        device_trackers = {}

        for entity_id in self.hass.states.async_entity_ids("device_tracker"):
            state = self.hass.states.get(entity_id)  # noqa: E111
            if state and state.state not in ["unknown", "unavailable"]:  # noqa: E111
                friendly_name = state.attributes.get(
                    "friendly_name",
                    entity_id,
                )
                # Filter out the Home Assistant companion apps to avoid confusion
                if "home_assistant" not in entity_id.lower():
                    device_trackers[entity_id] = friendly_name  # noqa: E111

        return device_trackers

    def _get_available_person_entities(self) -> dict[str, str]:  # noqa: E111
        """Get available person entities.

        Returns:
            Dictionary of entity_id -> friendly_name
        """
        person_entities = {}

        for entity_id in self.hass.states.async_entity_ids("person"):
            state = self.hass.states.get(entity_id)  # noqa: E111
            if state:  # noqa: E111
                friendly_name = state.attributes.get(
                    "friendly_name",
                    entity_id,
                )
                person_entities[entity_id] = friendly_name

        return person_entities

    def _get_available_door_sensors(self) -> dict[str, str]:  # noqa: E111
        """Get available door/window sensors.

        Returns:
            Dictionary of entity_id -> friendly_name
        """
        door_sensors = {}

        for entity_id in self.hass.states.async_entity_ids("binary_sensor"):
            state = self.hass.states.get(entity_id)  # noqa: E111
            if state:  # noqa: E111
                device_class = state.attributes.get("device_class")
                if device_class in ["door", "window", "opening", "garage_door"]:
                    friendly_name = state.attributes.get(  # noqa: E111
                        "friendly_name",
                        entity_id,
                    )
                    door_sensors[entity_id] = friendly_name  # noqa: E111

        return door_sensors

    def _get_available_notify_services(self) -> dict[str, str]:  # noqa: E111
        """Get available notification services.

        Returns:
            Dictionary of service_id -> friendly_name
        """
        notify_services = {}

        # Get all notification services
        services = self.hass.services.async_services().get("notify", {})
        for service_name in services:
            if (
                service_name != "persistent_notification"
            ):  # Exclude default  # noqa: E111
                service_id = f"notify.{service_name}"
                # Create friendly name from service name
                friendly_name = service_name.replace("_", " ").title()
                notify_services[service_id] = friendly_name

        return notify_services

    def _get_dogs_module_summary(self) -> str:  # noqa: E111
        """Get a summary of dogs and their configured modules.

        Returns:
            Formatted summary of dog module configurations
        """
        summaries = []
        for dog in self._dogs:
            modules = ensure_dog_modules_mapping(dog)  # noqa: E111
            enabled_modules = [name for name, enabled in modules.items() if enabled]  # noqa: E111

            if enabled_modules:  # noqa: E111
                modules_text = ", ".join(enabled_modules[:3])
                if len(enabled_modules) > 3:
                    modules_text += f" +{len(enabled_modules) - 3} more"  # noqa: E111
            else:  # noqa: E111
                modules_text = "Basic monitoring"

            summaries.append(f"• {dog[DOG_NAME_FIELD]}: {modules_text}")  # noqa: E111

        return "\n".join(summaries)

    def _get_dashboard_features_string(self, has_gps: bool) -> str:  # noqa: E111
        """Get dashboard feature list string.

        Args:
            has_gps: Whether GPS tracking is enabled.

        Returns:
            Comma-separated feature string for dashboard descriptions.
        """
        features = [
            "Statistics",
            "Alerts",
            "Mobile-Friendly",
            "Multiple Themes",
        ]
        if has_gps:
            features.insert(0, "GPS Maps")  # noqa: E111
        if len(self._dogs) > 1:
            features.append("Multi-Dog Overview")  # noqa: E111
        return ", ".join(features)

    def _get_dashboard_setup_info(self) -> str:  # noqa: E111
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
            ensure_dog_modules_mapping(dog).get(MODULE_GPS, False)
            or dog.get(DOG_GPS_CONFIG_FIELD)
            for dog in self._dogs
        )
        has_feeding = any(
            ensure_dog_modules_mapping(dog).get(MODULE_FEEDING, False)
            or dog.get(DOG_FEEDING_CONFIG_FIELD)
            for dog in self._dogs
        )
        has_health = any(
            ensure_dog_modules_mapping(dog).get(MODULE_HEALTH, False)
            or dog.get(DOG_HEALTH_CONFIG_FIELD)
            for dog in self._dogs
        )

        if has_gps:
            info.append("🗺️ GPS maps and location tracking")  # noqa: E111
        if has_feeding:
            info.append("🍽️ Feeding schedules and meal tracking")  # noqa: E111
        if has_health:
            info.append("📈 Health charts and medication reminders")  # noqa: E111

        if len(self._dogs) > 1:
            info.append(  # noqa: E111
                f"🐕 Individual dashboards for {len(self._dogs)} dogs available",
            )

        info.extend(
            [
                "⚡ Real-time updates and notifications",
                "🔧 Fully customizable via Options later",
            ],
        )

        return "\n".join(info)
