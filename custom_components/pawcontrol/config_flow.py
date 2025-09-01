"""Configuration flow for Paw Control integration.

This module provides a comprehensive configuration flow that meets Home Assistant's
Platinum quality standards. It includes full UI-based setup, extensive validation,
multi-step configuration, and a complete options flow for post-setup configuration.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Final

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .const import (
    CONF_DASHBOARD_MODE,
    CONF_DOGS,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOOR_SENSOR,
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_SOURCE,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_MODULES,
    CONF_NOTIFICATIONS,
    CONF_NOTIFY_FALLBACK,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT_MIN,
    CONF_RESET_TIME,
    CONF_SOURCES,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_REMINDER_REPEAT_MIN,
    DEFAULT_RESET_TIME,
    DEFAULT_DASHBOARD_ENABLED,
    DEFAULT_DASHBOARD_MODE,
    DOG_SIZES,
    DOMAIN,
    MAX_DOG_AGE,
    MAX_DOG_NAME_LENGTH,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_NAME_LENGTH,
    MIN_DOG_WEIGHT,
    MODULE_DASHBOARD,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
)
from .config_flow_dashboard_extension import DashboardFlowMixin
from .types import DogConfigData, is_dog_config_valid

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
            cv.string, vol.Length(min=MIN_DOG_NAME_LENGTH, max=MAX_DOG_NAME_LENGTH)
        ),
        vol.Optional(CONF_DOG_BREED, default=""): vol.All(
            cv.string, vol.Length(max=50)
        ),
        vol.Optional(CONF_DOG_AGE, default=3): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_DOG_AGE, max=MAX_DOG_AGE)
        ),
        vol.Optional(CONF_DOG_WEIGHT, default=20.0): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_DOG_WEIGHT, max=MAX_DOG_WEIGHT)
        ),
        vol.Optional(CONF_DOG_SIZE, default="medium"): vol.In(DOG_SIZES),
    }
)


class PawControlConfigFlow(DashboardFlowMixin, ConfigFlow, domain=DOMAIN):
    """Handle configuration flow for Paw Control integration.

    This config flow provides a comprehensive setup experience that guides
    users through configuring their dogs and initial settings. It includes
    extensive validation, helpful error messages, and a user-friendly interface.
    Designed for Home Assistant 2025.8.2+ with Platinum quality standards.
    """

    VERSION: Final = 1
    MINOR_VERSION: Final = 1

    def __init__(self) -> None:
        """Initialize the configuration flow with enhanced state management."""
        self._dogs: list[DogConfigData] = []
        self._current_dog_index = 0
        self._integration_name = "Paw Control"
        self._errors: dict[str, str] = {}
        self._step_stack: list[str] = []
        self._enabled_modules: dict[str, bool] = {}
        self._external_entities: dict[str, str] = {}

        # Performance tracking for better UX
        self._validation_cache: dict[str, dict[str, Any]] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step with enhanced validation.

        This is the entry point for the configuration flow. It collects
        basic integration information and validates uniqueness.

        Args:
            user_input: User-provided configuration data

        Returns:
            Configuration flow result for next step or completion
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                integration_name = user_input[CONF_NAME].strip()

                # Enhanced validation with async checking
                validation_result = await self._async_validate_integration_name(
                    integration_name
                )

                if validation_result["valid"]:
                    # Set unique ID with enhanced collision detection
                    unique_id = self._generate_unique_id(integration_name)
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    self._integration_name = integration_name
                    return await self.async_step_add_dog()
                else:
                    errors = validation_result["errors"]

            except Exception as err:
                _LOGGER.error("Error processing user input: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=INTEGRATION_SCHEMA,
            errors=errors,
            description_placeholders={
                "integration_name": "Paw Control",
                "docs_url": "https://github.com/BigDaddy1990/pawcontrol",
                "version": "1.0.0",
                "ha_version": "2025.8.2+",
                "features": self._get_feature_summary(),
            },
        )

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
            "🐕 Multi-dog management",
            "📍 GPS tracking & geofencing",
            "🍽️ Feeding schedules & logging",
            "🏥 Health monitoring & vet reminders",
            "🚶 Walk tracking with routes",
            "🔔 Smart notifications",
            "📊 Dashboard & analytics",
            "🏠 Visitor mode",
            "📱 Mobile app integration",
        ]
        return "\n".join(features)

    async def async_step_add_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a dog with rate-limited validation.

        FIXED: Prevents Entity Registry flooding through controlled validation.

        Args:
            user_input: User-provided dog configuration data

        Returns:
            Configuration flow result for next step
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # FIXED: Rate-limited validation to prevent flooding
                async with VALIDATION_SEMAPHORE:
                    # Add timeout for validation
                    async with asyncio.timeout(5):
                        validation_result = await self._async_validate_dog_config(
                            user_input
                        )

                if validation_result["valid"]:
                    # Create dog configuration with enhanced defaults
                    dog_config = await self._create_dog_config(user_input)
                    self._dogs.append(dog_config)

                    # Small delay after adding dog to prevent registry flooding
                    await asyncio.sleep(ENTITY_CREATION_DELAY)

                    _LOGGER.debug(
                        "Added dog: %s (%s)",
                        dog_config[CONF_DOG_NAME],
                        dog_config[CONF_DOG_ID],
                    )
                    return await self.async_step_add_another_dog()
                else:
                    errors = validation_result["errors"]

            except asyncio.TimeoutError:
                _LOGGER.error("Dog validation timed out")
                errors["base"] = "validation_timeout"
            except Exception as err:
                _LOGGER.error("Error adding dog: %s", err)
                errors["base"] = "add_dog_failed"

        # Generate intelligent suggestions
        suggested_id = await self._generate_smart_dog_id_suggestion(user_input)
        suggested_breed = await self._suggest_dog_breed(user_input)

        # Create dynamic schema with enhanced UX
        schema = await self._create_enhanced_dog_schema(
            user_input, suggested_id, suggested_breed
        )

        return self.async_show_form(
            step_id="add_dog",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "dog_count": len(self._dogs),
                "max_dogs": MAX_DOGS_PER_ENTRY,
                "current_dogs": self._format_dogs_list(),
                "remaining_spots": MAX_DOGS_PER_ENTRY - len(self._dogs),
            },
        )

    async def _async_validate_dog_config(
        self, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate dog configuration with rate-limiting.

        FIXED: Controlled validation to prevent Entity Registry flooding.

        Args:
            user_input: Dog configuration to validate

        Returns:
            Dictionary with validation results and any errors
        """
        errors: dict[str, str] = {}

        try:
            dog_id = user_input[CONF_DOG_ID].lower().strip().replace(" ", "_")
            dog_name = user_input[CONF_DOG_NAME].strip()

            # Add small delay between validations to prevent flooding
            await asyncio.sleep(0.01)  # 10ms micro-delay

            # Check cache first for performance
            cache_key = f"{dog_id}_{dog_name}"
            if cache_key in self._validation_cache:
                cached = self._validation_cache[cache_key]
                if (
                    cached.get("timestamp", 0) > asyncio.get_event_loop().time() - 5
                ):  # 5 second cache
                    return cached["result"]

            # Enhanced dog ID validation
            if not DOG_ID_PATTERN.match(dog_id):
                errors[CONF_DOG_ID] = "invalid_dog_id_format"
            elif any(dog[CONF_DOG_ID] == dog_id for dog in self._dogs):
                errors[CONF_DOG_ID] = "dog_id_already_exists"
            elif len(dog_id) < 2:
                errors[CONF_DOG_ID] = "dog_id_too_short"
            elif len(dog_id) > 30:
                errors[CONF_DOG_ID] = "dog_id_too_long"

            # Enhanced dog name validation
            if not dog_name:
                errors[CONF_DOG_NAME] = "dog_name_required"
            elif len(dog_name) < MIN_DOG_NAME_LENGTH:
                errors[CONF_DOG_NAME] = "dog_name_too_short"
            elif len(dog_name) > MAX_DOG_NAME_LENGTH:
                errors[CONF_DOG_NAME] = "dog_name_too_long"
            elif any(
                dog[CONF_DOG_NAME].lower() == dog_name.lower() for dog in self._dogs
            ):
                errors[CONF_DOG_NAME] = "dog_name_already_exists"

            # Enhanced weight validation with size correlation
            weight = user_input.get(CONF_DOG_WEIGHT)
            size = user_input.get(CONF_DOG_SIZE, "medium")
            if weight is not None:
                try:
                    weight_float = float(weight)
                    if weight_float < MIN_DOG_WEIGHT or weight_float > MAX_DOG_WEIGHT:
                        errors[CONF_DOG_WEIGHT] = "weight_out_of_range"
                    elif not self._is_weight_size_compatible(weight_float, size):
                        errors[CONF_DOG_WEIGHT] = "weight_size_mismatch"
                except (ValueError, TypeError):
                    errors[CONF_DOG_WEIGHT] = "invalid_weight_format"

            # Enhanced age validation
            age = user_input.get(CONF_DOG_AGE)
            if age is not None:
                try:
                    age_int = int(age)
                    if age_int < MIN_DOG_AGE or age_int > MAX_DOG_AGE:
                        errors[CONF_DOG_AGE] = "age_out_of_range"
                except (ValueError, TypeError):
                    errors[CONF_DOG_AGE] = "invalid_age_format"

            # Breed validation (optional but helpful)
            breed = user_input.get(CONF_DOG_BREED, "").strip()
            if breed and len(breed) > 50:
                errors[CONF_DOG_BREED] = "breed_name_too_long"

            # Cache the result for performance
            result = {
                "valid": len(errors) == 0,
                "errors": errors,
            }

            self._validation_cache[cache_key] = {
                "result": result,
                "timestamp": asyncio.get_event_loop().time(),
            }

            return result

        except Exception as err:
            _LOGGER.error("Error validating dog configuration: %s", err)
            return {
                "valid": False,
                "errors": {"base": "validation_error"},
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
            "toy": (1.0, 6.0),  # Chihuahua, Yorkshire Terrier
            "small": (4.0, 15.0),  # Beagle, Cocker Spaniel (overlap with toy/medium)
            "medium": (8.0, 30.0),  # Border Collie, Labrador (overlap with small/large)
            "large": (
                22.0,
                50.0,
            ),  # German Shepherd, Golden Retriever (overlap with medium/giant)
            "giant": (35.0, 90.0),  # Great Dane, Saint Bernard (overlap with large)
        }

        range_min, range_max = size_ranges.get(size, (1.0, 90.0))

        # Allow some flexibility with overlapping ranges for realistic breed variations
        return range_min <= weight <= range_max

    async def _create_dog_config(self, user_input: dict[str, Any]) -> DogConfigData:
        """Create a complete dog configuration with intelligent defaults.

        Builds a comprehensive dog configuration with sensible defaults
        based on dog characteristics and best practices.

        Args:
            user_input: User-provided dog data

        Returns:
            Complete dog configuration dictionary
        """
        dog_id = user_input[CONF_DOG_ID].lower().strip().replace(" ", "_")
        dog_size = user_input.get(CONF_DOG_SIZE, "medium")
        dog_age = user_input.get(CONF_DOG_AGE, 3)

        # Intelligent module defaults based on dog characteristics
        default_modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_HEALTH: True,
            MODULE_NOTIFICATIONS: True,
            MODULE_DASHBOARD: True,
            MODULE_GPS: dog_size
            in ("medium", "large", "giant"),  # Larger dogs more likely to roam
            MODULE_VISITOR: dog_age >= 2,  # Mature dogs better for visitor mode
        }

        # Size-based feeding defaults
        feeding_defaults = self._get_feeding_defaults_by_size(dog_size)

        return {
            CONF_DOG_ID: dog_id,
            CONF_DOG_NAME: user_input[CONF_DOG_NAME].strip(),
            CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, "").strip() or "Mixed Breed",
            CONF_DOG_AGE: dog_age,
            CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
            CONF_DOG_SIZE: dog_size,
            CONF_MODULES: default_modules,
            "feeding_defaults": feeding_defaults,
            "created_at": asyncio.get_event_loop().time(),
        }

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
                "daily_amount": 0.5,
                "feeding_times": ["07:00", "12:00", "18:00"],
            },
            "small": {
                "meals_per_day": 2,
                "daily_amount": 1.0,
                "feeding_times": ["07:30", "18:00"],
            },
            "medium": {
                "meals_per_day": 2,
                "daily_amount": 2.0,
                "feeding_times": ["07:30", "18:00"],
            },
            "large": {
                "meals_per_day": 2,
                "daily_amount": 3.0,
                "feeding_times": ["07:00", "18:30"],
            },
            "giant": {
                "meals_per_day": 2,
                "daily_amount": 4.5,
                "feeding_times": ["07:00", "18:30"],
            },
        }

        return feeding_configs.get(size, feeding_configs["medium"])

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
                suggestion = (
                    f"{original_suggestion}_{asyncio.get_event_loop().time():.0f}"[-20:]
                )
                break

        return suggestion

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
        user_input.get(CONF_DOG_SIZE, "")
        user_input.get(CONF_DOG_WEIGHT, 0)

        # Simple breed suggestions based on common patterns
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

        # Check name patterns
        for hint_name, breed in breed_hints.items():
            if hint_name in name:
                return breed

        return ""

    async def _create_enhanced_dog_schema(
        self, user_input: dict[str, Any] | None, suggested_id: str, suggested_breed: str
    ) -> vol.Schema:
        """Create an enhanced dynamic schema with modern selectors.

        Builds a form schema with intelligent defaults, better UX,
        and accessibility improvements.

        Args:
            user_input: Current user input values
            suggested_id: Suggested dog ID
            suggested_breed: Suggested breed

        Returns:
            Enhanced Voluptuous schema for the form
        """
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Required(
                    CONF_DOG_ID, default=current_values.get(CONF_DOG_ID, suggested_id)
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="off",
                    )
                ),
                vol.Required(
                    CONF_DOG_NAME, default=current_values.get(CONF_DOG_NAME, "")
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="name",
                    )
                ),
                vol.Optional(
                    CONF_DOG_BREED,
                    default=current_values.get(CONF_DOG_BREED, suggested_breed),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="off",
                    )
                ),
                vol.Optional(
                    CONF_DOG_AGE, default=current_values.get(CONF_DOG_AGE, 3)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_DOG_AGE,
                        max=MAX_DOG_AGE,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="years",
                    )
                ),
                vol.Optional(
                    CONF_DOG_WEIGHT, default=current_values.get(CONF_DOG_WEIGHT, 20.0)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_DOG_WEIGHT,
                        max=MAX_DOG_WEIGHT,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kg",
                    )
                ),
                vol.Optional(
                    CONF_DOG_SIZE, default=current_values.get(CONF_DOG_SIZE, "medium")
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "toy",
                                "label": "🐭 Toy (1-6kg) - Chihuahua, Yorkshire Terrier",
                            },
                            {
                                "value": "small",
                                "label": "🐕 Small (6-12kg) - Beagle, Cocker Spaniel",
                            },
                            {
                                "value": "medium",
                                "label": "🐶 Medium (12-27kg) - Border Collie, Labrador",
                            },
                            {
                                "value": "large",
                                "label": "🐕‍🦺 Large (27-45kg) - German Shepherd, Golden Retriever",
                            },
                            {
                                "value": "giant",
                                "label": "🐺 Giant (45-90kg) - Great Dane, Saint Bernard",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

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
            modules = dog.get(CONF_MODULES, {})
            enabled_count = sum(1 for enabled in modules.values() if enabled)

            dogs_list.append(
                f"{i}. {size_emoji} **{dog[CONF_DOG_NAME]}** ({dog[CONF_DOG_ID]})\n"
                f"   {dog.get(CONF_DOG_SIZE, 'medium').title()} {breed_info}, "
                f"{dog.get(CONF_DOG_AGE, 'unknown')} years, {dog.get(CONF_DOG_WEIGHT, 'unknown')}kg\n"
                f"   {enabled_count}/{len(modules)} modules enabled"
            )

        return "\n\n".join(dogs_list)

    async def async_step_add_another_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask if the user wants to add another dog with enhanced UX.

        This step allows users to configure multiple dogs in a single
        setup process while providing clear feedback and guidance.

        Args:
            user_input: User choice about adding another dog

        Returns:
            Configuration flow result for next step or dog addition
        """
        if user_input is not None:
            if user_input.get("add_another", False):
                # Clear cache and errors for fresh start
                self._validation_cache.clear()
                self._errors.clear()
                return await self.async_step_add_dog()
            else:
                return await self.async_step_configure_modules()

        # Check if we've reached the limit
        at_limit = len(self._dogs) >= MAX_DOGS_PER_ENTRY

        schema = vol.Schema(
            {
                vol.Required(
                    "add_another", default=False and not at_limit
                ): selector.BooleanSelector(),
            }
        )

        description_placeholders = {
            "dogs_list": self._format_dogs_list(),
            "dog_count": len(self._dogs),
            "max_dogs": MAX_DOGS_PER_ENTRY,
            "remaining_spots": MAX_DOGS_PER_ENTRY - len(self._dogs),
            "at_limit": "true" if at_limit else "false",
        }

        return self.async_show_form(
            step_id="add_another_dog",
            data_schema=schema,
            description_placeholders=description_placeholders,
        )

    async def async_step_configure_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure modules with enhanced guidance and validation.

        This step allows users to customize functionality for their dogs
        with intelligent suggestions and clear explanations.

        Args:
            user_input: Module configuration choices

        Returns:
            Configuration flow result for next step or completion
        """
        if user_input is not None:
            # Apply module configuration to all dogs with smart defaults
            gps_enabled = user_input.get("enable_gps", False)
            health_enabled = user_input.get("enable_health", True)
            visitor_enabled = user_input.get("enable_visitor_mode", False)
            dashboard_enabled = user_input.get(
                "enable_dashboard", DEFAULT_DASHBOARD_ENABLED
            )
            advanced_features = user_input.get("enable_advanced_features", False)

            for dog in self._dogs:
                dog[CONF_MODULES].update(
                    {
                        MODULE_GPS: gps_enabled,
                        MODULE_HEALTH: health_enabled,
                        MODULE_VISITOR: visitor_enabled,
                        MODULE_DASHBOARD: dashboard_enabled,
                    }
                )

                # Advanced features include additional modules
                if advanced_features:
                    dog[CONF_MODULES][MODULE_NOTIFICATIONS] = True

            # Store enabled modules for next step
            self._enabled_modules = {
                "gps": gps_enabled,
                "health": health_enabled,
                "visitor": visitor_enabled,
                "dashboard": dashboard_enabled,
                "advanced": advanced_features,
            }

            if dashboard_enabled:
                return await self.async_step_configure_dashboard()
            if gps_enabled:
                return await self.async_step_configure_external_entities()
            return await self.async_step_final_setup()

        # Only show this step if we have dogs configured
        if not self._dogs:
            return await self.async_step_final_setup()

        # Analyze dogs for intelligent suggestions
        large_dogs = [
            d for d in self._dogs if d.get(CONF_DOG_SIZE) in ("large", "giant")
        ]
        mature_dogs = [d for d in self._dogs if d.get(CONF_DOG_AGE, 0) >= 2]

        # Default suggestions based on dog characteristics
        default_gps = len(large_dogs) > 0
        default_visitor = len(mature_dogs) > 0

        schema = vol.Schema(
            {
                vol.Optional(
                    "enable_gps", default=default_gps
                ): selector.BooleanSelector(),
                vol.Optional("enable_health", default=True): selector.BooleanSelector(),
                vol.Optional(
                    "enable_visitor_mode", default=default_visitor
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_dashboard", default=DEFAULT_DASHBOARD_ENABLED
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_advanced_features", default=len(self._dogs) > 1
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="configure_modules",
            data_schema=schema,
            description_placeholders={
                "dog_count": len(self._dogs),
                "large_dog_count": len(large_dogs),
                "mature_dog_count": len(mature_dogs),
                "gps_suggestion": "recommended" if default_gps else "optional",
                "visitor_suggestion": "recommended" if default_visitor else "optional",
                "dogs_summary": self._get_dogs_module_summary(),
            },
        )

    def _get_dogs_module_summary(self) -> str:
        """Get a summary of dogs and their suggested modules.

        Returns:
            Formatted summary of dog module recommendations
        """
        summaries = []
        for dog in self._dogs:
            size = dog.get(CONF_DOG_SIZE, "medium")
            age = dog.get(CONF_DOG_AGE, 0)

            suggestions = []
            if size in ("large", "giant"):
                suggestions.append("GPS tracking")
            if age >= 2:
                suggestions.append("Visitor mode")
            if not suggestions:
                suggestions = ["Standard modules"]

            summaries.append(f"• {dog[CONF_DOG_NAME]}: {', '.join(suggestions)}")

        return "\n".join(summaries)

    async def async_step_configure_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure dashboard settings during setup.

        This step allows users to configure how the dashboard should be created
        and displayed, including per-dog dashboards and theme selection.

        Args:
            user_input: Dashboard configuration choices

        Returns:
            Configuration flow result for next step
        """
        if user_input is not None:
            # Store dashboard configuration
            has_multiple_dogs = len(self._dogs) > 1
            self._dashboard_config = {
                "dashboard_enabled": True,
                "dashboard_auto_create": user_input.get("auto_create_dashboard", True),
                "dashboard_per_dog": user_input.get("create_per_dog_dashboards", has_multiple_dogs),
                "dashboard_theme": user_input.get("dashboard_theme", "default"),
                "dashboard_mode": user_input.get("dashboard_mode", "full" if has_multiple_dogs else "cards"),
                "show_statistics": user_input.get("show_statistics", True),
                "show_maps": user_input.get("show_maps", self._enabled_modules.get("gps", False)),
                "show_alerts": user_input.get("show_alerts", True),
                "compact_mode": user_input.get("compact_mode", False),
            }

            # Continue to next step based on enabled modules
            if self._enabled_modules.get("gps", False):
                return await self.async_step_configure_external_entities()
            return await self.async_step_final_setup()

        # Build dashboard configuration form
        has_multiple_dogs = len(self._dogs) > 1
        has_gps = self._enabled_modules.get("gps", False)

        schema = vol.Schema(
            {
                vol.Optional(
                    "auto_create_dashboard", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "create_per_dog_dashboards", default=has_multiple_dogs
                ): selector.BooleanSelector(),
                vol.Optional(
                    "dashboard_theme", default="default"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "default", "label": "🎨 Default - Clean and modern"},
                            {"value": "dark", "label": "🌙 Dark - Night-friendly theme"},
                            {"value": "playful", "label": "🎉 Playful - Colorful and fun"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "dashboard_mode", default="full" if has_multiple_dogs else "cards"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "full", "label": "📊 Full - Complete dashboard with all features"},
                            {"value": "cards", "label": "🃏 Cards - Organized card-based layout"},
                            {"value": "minimal", "label": "⚡ Minimal - Essential information only"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("show_statistics", default=True): selector.BooleanSelector(),
                vol.Optional("show_maps", default=has_gps): selector.BooleanSelector(),
                vol.Optional("show_alerts", default=True): selector.BooleanSelector(),
                vol.Optional("compact_mode", default=False): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="configure_dashboard",
            data_schema=schema,
            description_placeholders={
                "dog_count": len(self._dogs),
                "dashboard_info": self._get_dashboard_setup_info(),
                "features": "GPS Maps, Statistics, Alerts, Mobile-Friendly" if has_gps else "Statistics, Alerts, Mobile-Friendly",
            },
        )

    def _get_dashboard_setup_info(self) -> str:
        """Get dashboard setup information for display.

        Returns:
            Formatted dashboard information string
        """
        info = [
            "🎨 Dashboard will be automatically created after setup",
            "📊 Includes cards for each dog and their activities",
            "📱 Mobile-friendly and responsive design",
        ]

        if self._enabled_modules.get("gps", False):
            info.append("🗺️ GPS maps and location tracking")

        if len(self._dogs) > 1:
            info.append(f"🐕 Individual dashboards for {len(self._dogs)} dogs available")

        info.extend([
            "⚡ Real-time updates and notifications",
            "🔧 Fully customizable via Options later"
        ])

        return "\n".join(info)

    async def async_step_configure_external_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure external entities required for enabled modules.

        This critical step configures external Home Assistant entities that
        the integration depends on. Required for Platinum quality scale compliance.

        Args:
            user_input: External entity configuration

        Returns:
            Configuration flow result for final setup
        """
        if user_input is not None:
            # Validate and store external entity selections
            try:
                validated_entities = await self._async_validate_external_entities(
                    user_input
                )
                self._external_entities.update(validated_entities)
                return await self.async_step_final_setup()
            except ValueError as err:
                return self.async_show_form(
                    step_id="configure_external_entities",
                    data_schema=self._get_external_entities_schema(),
                    errors={"base": str(err)},
                )

        return self.async_show_form(
            step_id="configure_external_entities",
            data_schema=self._get_external_entities_schema(),
            description_placeholders={
                "gps_enabled": self._enabled_modules.get("gps", False),
                "visitor_enabled": self._enabled_modules.get("visitor", False),
                "dog_count": len(self._dogs),
            },
        )

    def _get_external_entities_schema(self) -> vol.Schema:
        """Get schema for external entities configuration.

        Returns:
            Schema based on enabled modules
        """
        schema_dict = {}

        # GPS source selection - REQUIRED if GPS enabled
        if self._enabled_modules.get("gps", False):
            # Get available device trackers and person entities
            device_trackers = self._get_available_device_trackers()
            person_entities = self._get_available_person_entities()

            gps_options = []
            if device_trackers:
                gps_options.extend(
                    [
                        {"value": entity_id, "label": f"📍 {name} (Device Tracker)"}
                        for entity_id, name in device_trackers.items()
                    ]
                )
            if person_entities:
                gps_options.extend(
                    [
                        {"value": entity_id, "label": f"👤 {name} (Person)"}
                        for entity_id, name in person_entities.items()
                    ]
                )

            if gps_options:
                schema_dict[vol.Required(CONF_GPS_SOURCE)] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=gps_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            else:
                # No GPS entities available - offer manual setup
                schema_dict[vol.Required(CONF_GPS_SOURCE, default="manual")] = (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": "manual",
                                    "label": "📝 Manual GPS (configure later)",
                                }
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                )

        # Door sensor for visitor mode (optional)
        if self._enabled_modules.get("visitor", False):
            door_sensors = self._get_available_door_sensors()
            if door_sensors:
                door_options = [{"value": "", "label": "None (optional)"}]
                door_options.extend(
                    [
                        {"value": entity_id, "label": f"🚪 {name}"}
                        for entity_id, name in door_sensors.items()
                    ]
                )

                schema_dict[vol.Optional(CONF_DOOR_SENSOR, default="")] = (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=door_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                )

        # Notification services (always show if advanced features enabled)
        if self._enabled_modules.get("advanced", False):
            notify_services = self._get_available_notify_services()
            if notify_services:
                notify_options = [
                    {"value": "", "label": "Default (persistent_notification)"}
                ]
                notify_options.extend(
                    [
                        {"value": service_id, "label": f"🔔 {name}"}
                        for service_id, name in notify_services.items()
                    ]
                )

                schema_dict[vol.Optional(CONF_NOTIFY_FALLBACK, default="")] = (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=notify_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                )

        return vol.Schema(schema_dict)

    def _get_available_device_trackers(self) -> dict[str, str]:
        """Get available device tracker entities.

        Returns:
            Dictionary of entity_id -> friendly_name
        """
        device_trackers = {}

        for entity_id in self.hass.states.async_entity_ids("device_tracker"):
            state = self.hass.states.get(entity_id)
            if state and state.state not in ["unknown", "unavailable"]:
                friendly_name = state.attributes.get("friendly_name", entity_id)
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
                friendly_name = state.attributes.get("friendly_name", entity_id)
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
                    friendly_name = state.attributes.get("friendly_name", entity_id)
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

    async def _async_validate_external_entities(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Validate external entity selections.

        Args:
            user_input: User selections to validate

        Returns:
            Validated entity configuration

        Raises:
            ValueError: If validation fails
        """
        validated = {}

        # Validate GPS source if provided
        gps_source = user_input.get(CONF_GPS_SOURCE)
        if gps_source and gps_source != "manual":
            state = self.hass.states.get(gps_source)
            if not state:
                raise ValueError(f"GPS source entity {gps_source} not found")
            if state.state in ["unknown", "unavailable"]:
                raise ValueError(f"GPS source entity {gps_source} is unavailable")
            validated[CONF_GPS_SOURCE] = gps_source
        elif gps_source == "manual":
            validated[CONF_GPS_SOURCE] = "manual"

        # Validate door sensor if provided
        door_sensor = user_input.get(CONF_DOOR_SENSOR)
        if door_sensor:
            state = self.hass.states.get(door_sensor)
            if not state:
                raise ValueError(f"Door sensor entity {door_sensor} not found")
            validated[CONF_DOOR_SENSOR] = door_sensor

        # Validate notification service if provided
        notify_service = user_input.get(CONF_NOTIFY_FALLBACK)
        if notify_service:
            # Check if service exists
            service_parts = notify_service.split(".", 1)
            if len(service_parts) != 2 or service_parts[0] != "notify":
                raise ValueError(f"Invalid notification service: {notify_service}")

            services = self.hass.services.async_services().get("notify", {})
            if service_parts[1] not in services:
                raise ValueError(f"Notification service {service_parts[1]} not found")

            validated[CONF_NOTIFY_FALLBACK] = notify_service

        return validated

    async def async_step_final_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete the configuration setup with comprehensive validation.

        This final step creates the config entry with all collected
        data and sets up intelligent default options.

        Args:
            user_input: Final confirmation from user

        Returns:
            Configuration entry creation result
        """
        # Validate that we have at least one dog
        if not self._dogs:
            _LOGGER.error("No dogs configured during setup")
            return self.async_abort(reason="no_dogs_configured")

        try:
            # Create comprehensive configuration data
            config_data = {
                CONF_NAME: self._integration_name,
                CONF_DOGS: self._dogs,
                "setup_version": self.VERSION,
                "setup_timestamp": asyncio.get_event_loop().time(),
            }

            # Add external entities configuration if configured
            if self._external_entities:
                config_data[CONF_SOURCES] = self._external_entities

            # Create intelligent default options based on configuration
            options_data = await self._create_intelligent_options(config_data)
            if hasattr(self, "_dashboard_config"):
                options_data.update(self._dashboard_config)

            # Validate configuration integrity
            if not is_dog_config_valid(self._dogs[0]) if self._dogs else False:
                raise ValueError("Invalid dog configuration detected")

            _LOGGER.info(
                "Creating Paw Control config entry '%s' with %d dogs",
                self._integration_name,
                len(self._dogs),
            )

            return self.async_create_entry(
                title=self._integration_name,
                data=config_data,
                options=options_data,
            )

        except Exception as err:
            _LOGGER.error("Failed to create config entry: %s", err)
            return self.async_abort(reason="setup_failed")

    async def _create_intelligent_options(
        self, config_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create intelligent default options based on configuration.

        Args:
            config_data: Complete configuration data

        Returns:
            Optimized options dictionary
        """
        dogs = config_data[CONF_DOGS]

        # Analyze configuration for intelligent defaults
        has_gps = any(dog.get(CONF_MODULES, {}).get(MODULE_GPS, False) for dog in dogs)
        has_multiple_dogs = len(dogs) > 1
        has_large_dogs = any(
            dog.get(CONF_DOG_SIZE) in ("large", "giant") for dog in dogs
        )

        # Performance mode based on complexity
        if has_multiple_dogs and has_gps:
            performance_mode = "balanced"
        elif has_gps or has_multiple_dogs:
            performance_mode = "balanced"
        else:
            performance_mode = "minimal"

        # Update interval based on features
        if has_gps:
            update_interval = 60 if has_multiple_dogs else 45
        else:
            update_interval = 120

        return {
            CONF_RESET_TIME: DEFAULT_RESET_TIME,
            CONF_NOTIFICATIONS: {
                CONF_QUIET_HOURS: True,
                CONF_QUIET_START: "22:00:00",
                CONF_QUIET_END: "07:00:00",
                CONF_REMINDER_REPEAT_MIN: DEFAULT_REMINDER_REPEAT_MIN,
                "priority_notifications": has_large_dogs,
                "summary_notifications": has_multiple_dogs,
            },
            CONF_GPS_UPDATE_INTERVAL: update_interval,
            CONF_GPS_ACCURACY_FILTER: DEFAULT_GPS_ACCURACY_FILTER,
            CONF_GPS_DISTANCE_FILTER: DEFAULT_GPS_DISTANCE_FILTER,
            CONF_DASHBOARD_MODE: DEFAULT_DASHBOARD_MODE
            if has_multiple_dogs
            else "cards",
            "performance_mode": performance_mode,
            "data_retention_days": 90,
            "auto_backup": has_multiple_dogs,
            "debug_logging": False,
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow for post-setup configuration.

        Args:
            config_entry: The config entry to create options flow for

        Returns:
            Enhanced options flow instance for advanced configuration
        """
        return PawControlOptionsFlow(config_entry)


class PawControlOptionsFlow(OptionsFlow):
    """Handle options flow for Paw Control integration with Platinum UX.

    This comprehensive options flow allows users to modify all aspects
    of their Paw Control configuration after initial setup. It provides
    organized menu-driven navigation and extensive customization options
    with modern UI patterns and enhanced validation.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow with enhanced state management.

        Args:
            config_entry: Configuration entry to modify
        """
        self._config_entry = config_entry
        self._current_dog: DogConfigData | None = None
        self._dogs: list[DogConfigData] = [
            d.copy() for d in self._config_entry.data.get(CONF_DOGS, [])
        ]
        self._navigation_stack: list[str] = []
        self._unsaved_changes: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the main options menu with enhanced navigation.

        Provides organized access to all configuration categories
        with clear descriptions and intelligent suggestions.

        Args:
            user_input: User menu selection

        Returns:
            Configuration flow result for selected option
        """
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "manage_dogs",
                "gps_settings",
                "notifications",
                "feeding_settings",
                "health_settings",
                "system_settings",
                "dashboard_settings",
                "advanced_settings",
                "import_export",
            ],
        )

    async def async_step_advanced_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle advanced settings configuration.

        This step provides access to advanced system configuration options
        including performance settings, debugging, and experimental features.

        Args:
            user_input: User-provided configuration data

        Returns:
            Configuration flow result
        """
        if user_input is not None:
            try:
                # Update options with advanced settings
                self._unsaved_changes.update(
                    {
                        "performance_mode": user_input.get(
                            "performance_mode", "balanced"
                        ),
                        "debug_logging": user_input.get("debug_logging", False),
                        "data_retention_days": user_input.get(
                            "data_retention_days", 90
                        ),
                        "auto_backup": user_input.get("auto_backup", False),
                        "experimental_features": user_input.get(
                            "experimental_features", False
                        ),
                    }
                )
                # Save changes and return to main menu
                return await self._async_save_options()
            except Exception as err:
                _LOGGER.error("Error saving advanced settings: %s", err)
                return self.async_show_form(
                    step_id="advanced_settings",
                    errors={"base": "save_failed"},
                    data_schema=self._get_advanced_settings_schema(user_input),
                )

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=self._get_advanced_settings_schema(),
        )

    async def async_step_add_new_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new dog to the configuration."""
        if user_input is not None:
            try:
                # Create the new dog config
                new_dog = {
                    CONF_DOG_ID: user_input[CONF_DOG_ID]
                    .lower()
                    .strip()
                    .replace(" ", "_"),
                    CONF_DOG_NAME: user_input[CONF_DOG_NAME].strip(),
                    CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, "").strip()
                    or "Mixed Breed",
                    CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 3),
                    CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
                    CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, "medium"),
                    "modules": {
                        "feeding": True,
                        "walk": True,
                        "health": True,
                        "notifications": True,
                        "dashboard": True,
                        "gps": False,
                        "visitor": False,
                    },
                    "created_at": asyncio.get_event_loop().time(),
                }

                # Add to existing dogs
                current_dogs = list(self._config_entry.data.get(CONF_DOGS, []))
                current_dogs.append(new_dog)

                # Update the config entry data
                new_data = {**self._config_entry.data}
                new_data[CONF_DOGS] = current_dogs

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )

                return await self.async_step_init()
            except Exception as err:
                _LOGGER.error("Error adding new dog: %s", err)
                return self.async_show_form(
                    step_id="add_new_dog",
                    data_schema=self._get_add_dog_schema(),
                    errors={"base": "add_dog_failed"},
                )

        return self.async_show_form(
            step_id="add_new_dog", data_schema=self._get_add_dog_schema()
        )

    def _get_add_dog_schema(self) -> vol.Schema:
        """Get schema for adding a new dog."""
        return vol.Schema(
            {
                vol.Required(CONF_DOG_ID): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="off",
                    )
                ),
                vol.Required(CONF_DOG_NAME): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="name",
                    )
                ),
                vol.Optional(CONF_DOG_BREED, default=""): selector.TextSelector(),
                vol.Optional(CONF_DOG_AGE, default=3): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=30, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(CONF_DOG_WEIGHT, default=20.0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=200.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kg",
                    )
                ),
                vol.Optional(CONF_DOG_SIZE, default="medium"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "toy", "label": "🐭 Toy (1-6kg)"},
                            {"value": "small", "label": "🐕 Small (6-12kg)"},
                            {"value": "medium", "label": "🐶 Medium (12-27kg)"},
                            {"value": "large", "label": "🐕‍🦺 Large (27-45kg)"},
                            {"value": "giant", "label": "🐺 Giant (45-90kg)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_select_dog_to_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which dog to edit."""
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        if not current_dogs:
            return await self.async_step_init()

        if user_input is not None:
            selected_dog_id = user_input.get("dog_id")
            self._current_dog = next(
                (
                    dog
                    for dog in current_dogs
                    if dog.get(CONF_DOG_ID) == selected_dog_id
                ),
                None,
            )
            if self._current_dog:
                return await self.async_step_edit_dog()
            else:
                return await self.async_step_init()

        # Create selection options
        dog_options = [
            {
                "value": dog.get(CONF_DOG_ID),
                "label": f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})",
            }
            for dog in current_dogs
        ]

        return self.async_show_form(
            step_id="select_dog_to_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=dog_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected dog."""
        if not self._current_dog:
            return await self.async_step_init()

        if user_input is not None:
            try:
                # Update the dog in the config entry
                current_dogs = list(self._config_entry.data.get(CONF_DOGS, []))
                dog_index = next(
                    (
                        i
                        for i, dog in enumerate(current_dogs)
                        if dog.get(CONF_DOG_ID) == self._current_dog.get(CONF_DOG_ID)
                    ),
                    -1,
                )

                if dog_index >= 0:
                    # Update the dog with new values
                    updated_dog = {**current_dogs[dog_index]}
                    updated_dog.update(user_input)
                    current_dogs[dog_index] = updated_dog

                    # Update config entry
                    new_data = {**self._config_entry.data}
                    new_data[CONF_DOGS] = current_dogs

                    self.hass.config_entries.async_update_entry(
                        self._config_entry, data=new_data
                    )

                return await self.async_step_init()
            except Exception as err:
                _LOGGER.error("Error editing dog: %s", err)
                return self.async_show_form(
                    step_id="edit_dog",
                    data_schema=self._get_edit_dog_schema(),
                    errors={"base": "edit_dog_failed"},
                )

        return self.async_show_form(
            step_id="edit_dog", data_schema=self._get_edit_dog_schema()
        )

    def _get_edit_dog_schema(self) -> vol.Schema:
        """Get schema for editing a dog with current values pre-filled."""
        if not self._current_dog:
            return vol.Schema({})

        return vol.Schema(
            {
                vol.Optional(
                    CONF_DOG_NAME, default=self._current_dog.get(CONF_DOG_NAME, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DOG_BREED, default=self._current_dog.get(CONF_DOG_BREED, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DOG_AGE, default=self._current_dog.get(CONF_DOG_AGE, 3)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=30, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_DOG_WEIGHT,
                    default=self._current_dog.get(CONF_DOG_WEIGHT, 20.0),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=200.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kg",
                    )
                ),
                vol.Optional(
                    CONF_DOG_SIZE,
                    default=self._current_dog.get(CONF_DOG_SIZE, "medium"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "toy", "label": "🐭 Toy (1-6kg)"},
                            {"value": "small", "label": "🐕 Small (6-12kg)"},
                            {"value": "medium", "label": "🐶 Medium (12-27kg)"},
                            {"value": "large", "label": "🐕‍🦺 Large (27-45kg)"},
                            {"value": "giant", "label": "🐺 Giant (45-90kg)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_select_dog_to_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which dog to remove."""
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        if not current_dogs:
            return await self.async_step_init()

        if user_input is not None:
            if user_input.get("confirm_remove"):
                selected_dog_id = user_input.get("dog_id")
                # Remove the selected dog
                updated_dogs = [
                    dog
                    for dog in current_dogs
                    if dog.get(CONF_DOG_ID) != selected_dog_id
                ]

                # Update config entry
                new_data = {**self._config_entry.data}
                new_data[CONF_DOGS] = updated_dogs

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )

            return await self.async_step_init()

        # Create removal confirmation form
        dog_options = [
            {
                "value": dog.get(CONF_DOG_ID),
                "label": f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})",
            }
            for dog in current_dogs
        ]

        return self.async_show_form(
            step_id="select_dog_to_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=dog_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        "confirm_remove", default=False
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={
                "warning": "⚠️ This will permanently remove the selected dog and all associated data!"
            },
        )

    def _get_advanced_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get schema for advanced settings form.

        Args:
            user_input: Current user input values

        Returns:
            Voluptuous schema for advanced settings
        """
        current_options = self._config_entry.options
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        current_options.get("performance_mode", "balanced"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "minimal",
                                "label": "Minimal - Lowest resource usage",
                            },
                            {
                                "value": "balanced",
                                "label": "Balanced - Good performance and efficiency",
                            },
                            {
                                "value": "full",
                                "label": "Full - Maximum features and responsiveness",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "debug_logging",
                    default=current_values.get(
                        "debug_logging", current_options.get("debug_logging", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "data_retention_days",
                    default=current_values.get(
                        "data_retention_days",
                        current_options.get("data_retention_days", 90),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "auto_backup",
                    default=current_values.get(
                        "auto_backup", current_options.get("auto_backup", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "experimental_features",
                    default=current_values.get(
                        "experimental_features",
                        current_options.get("experimental_features", False),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_import_export(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Placeholder handler for import/export settings.

        The import/export feature has not yet been implemented. Instead of
        raising an ``UnknownStep`` error when users navigate to this menu
        entry, we immediately redirect them back to the main options menu.

        Args:
            user_input: Not used.

        Returns:
            Flow result for the initial options step.
        """
        return await self.async_step_init()

    async def _async_save_options(self) -> ConfigFlowResult:
        """Save the current options changes.

        Returns:
            Configuration flow result indicating successful save
        """
        try:
            # Merge unsaved changes with existing options
            new_options = {**self._config_entry.options, **self._unsaved_changes}

            # Clear unsaved changes
            self._unsaved_changes.clear()

            # Update the config entry
            return self.async_create_entry(
                title="",  # Title is not used for options flow
                data=new_options,
            )
        except Exception as err:
            _LOGGER.error("Failed to save options: %s", err)
            return await self.async_step_init()

    async def async_step_manage_dogs(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage dogs - add, edit, or remove dogs."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_dog":
                return await self.async_step_add_new_dog()
            elif action == "edit_dog":
                return await self.async_step_select_dog_to_edit()
            elif action == "remove_dog":
                return await self.async_step_select_dog_to_remove()
            else:
                return await self.async_step_init()

        # Show dog management menu
        current_dogs = self._config_entry.data.get(CONF_DOGS, [])

        return self.async_show_form(
            step_id="manage_dogs",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="add_dog"): vol.In(
                        {
                            "add_dog": "Add new dog",
                            "edit_dog": "Edit existing dog"
                            if current_dogs
                            else "No dogs to edit",
                            "remove_dog": "Remove dog"
                            if current_dogs
                            else "No dogs to remove",
                            "back": "Back to main menu",
                        }
                    )
                }
            ),
            description_placeholders={
                "current_dogs_count": str(len(current_dogs)),
                "dogs_list": "\n".join(
                    [
                        f"• {dog.get(CONF_DOG_NAME, 'Unknown')} ({dog.get(CONF_DOG_ID, 'unknown')})"
                        for dog in current_dogs
                    ]
                )
                if current_dogs
                else "No dogs configured",
            },
        )

    async def async_step_gps_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure GPS and location settings."""
        if user_input is not None:
            try:
                # Update GPS settings in options
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_GPS_UPDATE_INTERVAL: user_input.get(
                            "gps_update_interval", DEFAULT_GPS_UPDATE_INTERVAL
                        ),
                        CONF_GPS_ACCURACY_FILTER: user_input.get(
                            "gps_accuracy_filter", DEFAULT_GPS_ACCURACY_FILTER
                        ),
                        CONF_GPS_DISTANCE_FILTER: user_input.get(
                            "gps_distance_filter", DEFAULT_GPS_DISTANCE_FILTER
                        ),
                        "gps_enabled": user_input.get("gps_enabled", True),
                    }
                )

                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="gps_settings",
                    data_schema=self._get_gps_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="gps_settings", data_schema=self._get_gps_settings_schema()
        )

    def _get_gps_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get GPS settings schema with current values."""
        current_options = self._config_entry.options
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "gps_enabled",
                    default=current_values.get(
                        "gps_enabled", current_options.get("gps_enabled", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "gps_update_interval",
                    default=current_values.get(
                        "gps_update_interval",
                        current_options.get(
                            CONF_GPS_UPDATE_INTERVAL, DEFAULT_GPS_UPDATE_INTERVAL
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=600,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
                vol.Optional(
                    "gps_accuracy_filter",
                    default=current_values.get(
                        "gps_accuracy_filter",
                        current_options.get(
                            CONF_GPS_ACCURACY_FILTER, DEFAULT_GPS_ACCURACY_FILTER
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=500,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="meters",
                    )
                ),
                vol.Optional(
                    "gps_distance_filter",
                    default=current_values.get(
                        "gps_distance_filter",
                        current_options.get(
                            CONF_GPS_DISTANCE_FILTER, DEFAULT_GPS_DISTANCE_FILTER
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=100,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="meters",
                    )
                ),
            }
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure notification settings."""
        if user_input is not None:
            try:
                # Update notification settings
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_NOTIFICATIONS: {
                            CONF_QUIET_HOURS: user_input.get("quiet_hours", True),
                            CONF_QUIET_START: user_input.get("quiet_start", "22:00:00"),
                            CONF_QUIET_END: user_input.get("quiet_end", "07:00:00"),
                            CONF_REMINDER_REPEAT_MIN: user_input.get(
                                "reminder_repeat_min", DEFAULT_REMINDER_REPEAT_MIN
                            ),
                            "priority_notifications": user_input.get(
                                "priority_notifications", True
                            ),
                            "mobile_notifications": user_input.get(
                                "mobile_notifications", True
                            ),
                        }
                    }
                )

                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="notifications",
                    data_schema=self._get_notifications_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="notifications", data_schema=self._get_notifications_schema()
        )

    def _get_notifications_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get notifications settings schema."""
        current_options = self._config_entry.options
        current_notifications = current_options.get(CONF_NOTIFICATIONS, {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "quiet_hours",
                    default=current_values.get(
                        "quiet_hours", current_notifications.get(CONF_QUIET_HOURS, True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "quiet_start",
                    default=current_values.get(
                        "quiet_start",
                        current_notifications.get(CONF_QUIET_START, "22:00:00"),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "quiet_end",
                    default=current_values.get(
                        "quiet_end",
                        current_notifications.get(CONF_QUIET_END, "07:00:00"),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "reminder_repeat_min",
                    default=current_values.get(
                        "reminder_repeat_min",
                        current_notifications.get(
                            CONF_REMINDER_REPEAT_MIN, DEFAULT_REMINDER_REPEAT_MIN
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=180,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="minutes",
                    )
                ),
                vol.Optional(
                    "priority_notifications",
                    default=current_values.get(
                        "priority_notifications",
                        current_notifications.get("priority_notifications", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "mobile_notifications",
                    default=current_values.get(
                        "mobile_notifications",
                        current_notifications.get("mobile_notifications", True),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_feeding_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure feeding and nutrition settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        "feeding_settings": {
                            "default_meals_per_day": user_input.get("meals_per_day", 2),
                            "feeding_reminders": user_input.get(
                                "feeding_reminders", True
                            ),
                            "portion_tracking": user_input.get(
                                "portion_tracking", True
                            ),
                            "calorie_tracking": user_input.get(
                                "calorie_tracking", True
                            ),
                            "auto_schedule": user_input.get("auto_schedule", False),
                        }
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="feeding_settings",
                    data_schema=self._get_feeding_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="feeding_settings", data_schema=self._get_feeding_settings_schema()
        )

    def _get_feeding_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get feeding settings schema."""
        current_options = self._config_entry.options
        current_feeding = current_options.get("feeding_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "meals_per_day",
                    default=current_values.get(
                        "meals_per_day", current_feeding.get("default_meals_per_day", 2)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=6, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    "feeding_reminders",
                    default=current_values.get(
                        "feeding_reminders",
                        current_feeding.get("feeding_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "portion_tracking",
                    default=current_values.get(
                        "portion_tracking",
                        current_feeding.get("portion_tracking", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "calorie_tracking",
                    default=current_values.get(
                        "calorie_tracking",
                        current_feeding.get("calorie_tracking", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "auto_schedule",
                    default=current_values.get(
                        "auto_schedule", current_feeding.get("auto_schedule", False)
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_health_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure health monitoring settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        "health_settings": {
                            "weight_tracking": user_input.get("weight_tracking", True),
                            "medication_reminders": user_input.get(
                                "medication_reminders", True
                            ),
                            "vet_reminders": user_input.get("vet_reminders", True),
                            "grooming_reminders": user_input.get(
                                "grooming_reminders", True
                            ),
                            "health_alerts": user_input.get("health_alerts", True),
                        }
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="health_settings",
                    data_schema=self._get_health_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="health_settings", data_schema=self._get_health_settings_schema()
        )

    def _get_health_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get health settings schema."""
        current_options = self._config_entry.options
        current_health = current_options.get("health_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "weight_tracking",
                    default=current_values.get(
                        "weight_tracking", current_health.get("weight_tracking", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "medication_reminders",
                    default=current_values.get(
                        "medication_reminders",
                        current_health.get("medication_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "vet_reminders",
                    default=current_values.get(
                        "vet_reminders", current_health.get("vet_reminders", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "grooming_reminders",
                    default=current_values.get(
                        "grooming_reminders",
                        current_health.get("grooming_reminders", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "health_alerts",
                    default=current_values.get(
                        "health_alerts", current_health.get("health_alerts", True)
                    ),
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_system_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure system and performance settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_RESET_TIME: user_input.get(
                            "reset_time", DEFAULT_RESET_TIME
                        ),
                        "system_settings": {
                            "data_retention_days": user_input.get(
                                "data_retention_days", 90
                            ),
                            "auto_backup": user_input.get("auto_backup", False),
                            "performance_mode": user_input.get(
                                "performance_mode", "balanced"
                            ),
                        },
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="system_settings",
                    data_schema=self._get_system_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="system_settings", data_schema=self._get_system_settings_schema()
        )

    def _get_system_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get system settings schema."""
        current_options = self._config_entry.options
        current_system = current_options.get("system_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "reset_time",
                    default=current_values.get(
                        "reset_time",
                        current_options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "data_retention_days",
                    default=current_values.get(
                        "data_retention_days",
                        current_system.get("data_retention_days", 90),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "auto_backup",
                    default=current_values.get(
                        "auto_backup", current_system.get("auto_backup", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        current_system.get("performance_mode", "balanced"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "minimal",
                                "label": "Minimal - Lowest resource usage",
                            },
                            {
                                "value": "balanced",
                                "label": "Balanced - Good performance and efficiency",
                            },
                            {
                                "value": "full",
                                "label": "Full - Maximum features and responsiveness",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_dashboard_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure dashboard and display settings."""
        if user_input is not None:
            try:
                new_options = {**self._config_entry.options}
                new_options.update(
                    {
                        CONF_DASHBOARD_MODE: user_input.get("dashboard_mode", "full"),
                        "dashboard_settings": {
                            "show_statistics": user_input.get("show_statistics", True),
                            "show_alerts": user_input.get("show_alerts", True),
                            "compact_mode": user_input.get("compact_mode", False),
                            "show_maps": user_input.get("show_maps", True),
                        },
                    }
                )
                return self.async_create_entry(title="", data=new_options)
            except Exception:
                return self.async_show_form(
                    step_id="dashboard_settings",
                    data_schema=self._get_dashboard_settings_schema(user_input),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="dashboard_settings",
            data_schema=self._get_dashboard_settings_schema(),
        )

    def _get_dashboard_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get dashboard settings schema."""
        current_options = self._config_entry.options
        current_dashboard = current_options.get("dashboard_settings", {})
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "dashboard_mode",
                    default=current_values.get(
                        "dashboard_mode",
                        current_options.get(CONF_DASHBOARD_MODE, "full"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "full",
                                "label": "Full - All information displayed",
                            },
                            {
                                "value": "cards",
                                "label": "Cards - Organized card layout",
                            },
                            {
                                "value": "minimal",
                                "label": "Minimal - Essential information only",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "show_statistics",
                    default=current_values.get(
                        "show_statistics",
                        current_dashboard.get("show_statistics", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_alerts",
                    default=current_values.get(
                        "show_alerts", current_dashboard.get("show_alerts", True)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "compact_mode",
                    default=current_values.get(
                        "compact_mode", current_dashboard.get("compact_mode", False)
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_maps",
                    default=current_values.get(
                        "show_maps", current_dashboard.get("show_maps", True)
                    ),
                ): selector.BooleanSelector(),
            }
        )
