"""Dog management steps for Paw Control configuration flow.

This module handles all dog-related configuration steps including adding,
validating, and configuring individual dogs with intelligent defaults
and enhanced user experience.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_MODULES,
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
from .config_flow_base import (
    DOG_ID_PATTERN,
    ENTITY_CREATION_DELAY,
    MAX_DOGS_PER_ENTRY,
    VALIDATION_SEMAPHORE,
)
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)


class DogManagementMixin:
    """Mixin for dog management functionality in configuration flow.
    
    This mixin provides all the methods needed for adding, validating,
    and configuring dogs during the initial setup process with enhanced
    validation and user experience.
    """

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
