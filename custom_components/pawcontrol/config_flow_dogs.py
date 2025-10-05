"""Dog management steps for Paw Control configuration flow.

This module handles all dog-related configuration steps including adding,
validating, and configuring individual dogs with intelligent defaults
and enhanced user experience. Now includes per-dog GPS, feeding schedules,
health data, and individual module configuration.

Quality Scale: Bronze target
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import voluptuous as vol
from custom_components.pawcontrol.config_flow_base import (
    DOG_ID_PATTERN,
    ENTITY_CREATION_DELAY,
    MAX_DOGS_PER_ENTRY,
    VALIDATION_SEMAPHORE,
)
from custom_components.pawcontrol.const import (
    CONF_BREAKFAST_TIME,
    CONF_DAILY_FOOD_AMOUNT,
    CONF_DINNER_TIME,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_FOOD_TYPE,
    CONF_GPS_SOURCE,
    CONF_LUNCH_TIME,
    CONF_MEALS_PER_DAY,
    CONF_MODULES,
    CONF_SNACK_TIMES,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_UPDATE_INTERVAL,
    GPS_ACCURACY_FILTER_SELECTOR,
    GPS_UPDATE_INTERVAL_SELECTOR,
    MAX_DOG_AGE,
    MAX_DOG_NAME_LENGTH,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_NAME_LENGTH,
    MIN_DOG_WEIGHT,
    MODULE_DASHBOARD,
    MODULE_FEEDING,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_MEDICATION,
    MODULE_NOTIFICATIONS,
    MODULE_TRAINING,
    MODULE_VISITOR,
    MODULE_WALK,
    SPECIAL_DIET_OPTIONS,
)
from custom_components.pawcontrol.types import DogConfigData
from homeassistant.config_entries import ConfigFlowResult
from .selector_shim import selector

_LOGGER = logging.getLogger(__name__)

# Diet compatibility matrix for validation
DIET_COMPATIBILITY_RULES = {
    "age_exclusive": {
        "groups": [["puppy_formula", "senior_formula"]],
        "type": "conflict",
        "message": "Age-specific formulas are mutually exclusive",
    },
    "prescription_warnings": {
        "groups": [["prescription", "diabetic", "kidney_support"]],
        "type": "warning",
        "max_concurrent": 1,
        "message": "Multiple prescription diets require veterinary coordination",
    },
    "raw_medical_caution": {
        "incompatible_with_raw": [
            "prescription",
            "kidney_support",
            "diabetic",
            "sensitive_stomach",
        ],
        "type": "warning",
        "message": "Raw diets may require veterinary supervision with medical conditions",
    },
}


class DogManagementMixin:
    """Mixin for dog management functionality in configuration flow.

    This mixin provides all the methods needed for adding, validating,
    and configuring dogs during the initial setup process with enhanced
    validation, per-dog module configuration, and comprehensive health data.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize dog management mixin."""
        super().__init__(*args, **kwargs)
        self._validation_cache: dict[str, Any] = {}
        self._lower_dog_names: set[str] = set()

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

        if user_input is not None and self._current_dog_config:
            # Finalize any previous dog configuration that wasn't completed
            if self._current_dog_config not in self._dogs:
                self._dogs.append(self._current_dog_config)
            self._current_dog_config = None

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

                    # Store temporarily for module configuration
                    self._current_dog_config = dog_config

                    # Small delay after adding dog to prevent registry flooding
                    await asyncio.sleep(ENTITY_CREATION_DELAY)

                    _LOGGER.debug(
                        "Added dog base config: %s (%s)",
                        dog_config[CONF_DOG_NAME],
                        dog_config[CONF_DOG_ID],
                    )

                    # Continue to module selection for this specific dog
                    return await self.async_step_dog_modules()
                else:
                    errors = validation_result["errors"]

            except TimeoutError:
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

    async def async_step_dog_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure modules for the specific dog being added.

        This step allows individual module configuration per dog,
        ensuring only needed entities are created.

        Args:
            user_input: Module selection for the dog

        Returns:
            Configuration flow result for next step
        """
        if user_input is not None:
            # Apply module selection to current dog
            modules = {
                MODULE_FEEDING: user_input.get("enable_feeding", False),
                MODULE_WALK: user_input.get("enable_walk", False),
                MODULE_HEALTH: user_input.get("enable_health", False),
                MODULE_GPS: user_input.get("enable_gps", False),
                MODULE_GARDEN: user_input.get("enable_garden", False),
                MODULE_NOTIFICATIONS: user_input.get("enable_notifications", False),
                MODULE_DASHBOARD: user_input.get("enable_dashboard", False),
                MODULE_VISITOR: user_input.get("enable_visitor", False),
                MODULE_GROOMING: user_input.get("enable_grooming", False),
                MODULE_MEDICATION: user_input.get("enable_medication", False),
                MODULE_TRAINING: user_input.get("enable_training", False),
            }

            self._current_dog_config[CONF_MODULES] = modules

            # Continue to GPS configuration if enabled
            if modules[MODULE_GPS]:
                return await self.async_step_dog_gps()
            # Continue to feeding configuration if enabled
            elif modules[MODULE_FEEDING]:
                return await self.async_step_dog_feeding()
            # Continue to health configuration if enabled
            elif modules[MODULE_HEALTH] or modules[MODULE_MEDICATION]:
                return await self.async_step_dog_health()
            else:
                # No additional configuration needed, finalize dog
                self._dogs.append(self._current_dog_config)
                return await self.async_step_add_another_dog()

        # Suggest modules based on dog characteristics
        dog_size = self._current_dog_config.get(CONF_DOG_SIZE, "medium")
        dog_age = self._current_dog_config.get(CONF_DOG_AGE, 3)

        suggested_gps = dog_size in ("large", "giant")
        suggested_visitor = dog_age >= 2
        suggested_medication = dog_age >= 7  # Older dogs more likely to need medication

        schema = vol.Schema(
            {
                vol.Optional(
                    "enable_feeding", default=False
                ): selector.BooleanSelector(),
                vol.Optional("enable_walk", default=False): selector.BooleanSelector(),
                vol.Optional(
                    "enable_health", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_gps", default=suggested_gps
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_garden", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_garden", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_notifications", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_dashboard", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_visitor", default=suggested_visitor
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_grooming", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_medication", default=suggested_medication
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_training", default=False
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="dog_modules",
            data_schema=schema,
            description_placeholders={
                "dog_name": self._current_dog_config[CONF_DOG_NAME],
                "dog_size": dog_size,
                "dog_age": dog_age,
            },
        )

    async def async_step_dog_gps(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure GPS settings for the specific dog.

        This step allows individual GPS device configuration per dog.

        Args:
            user_input: GPS configuration for the dog

        Returns:
            Configuration flow result for next step
        """
        if self._current_dog_config is None:
            return self.async_show_form(
                step_id="dog_gps", data_schema=vol.Schema({}), errors={}
            )

        if user_input is not None:
            # Store GPS configuration for this dog
            self._current_dog_config["gps_config"] = {
                CONF_GPS_SOURCE: user_input.get(CONF_GPS_SOURCE, "manual"),
                "gps_update_interval": user_input.get("gps_update_interval", 60),
                "gps_accuracy_filter": user_input.get("gps_accuracy_filter", 100),
                "enable_geofencing": user_input.get("enable_geofencing", True),
                "home_zone_radius": user_input.get("home_zone_radius", 50),
            }

            # Continue to feeding configuration if enabled
            if self._current_dog_config[CONF_MODULES].get(MODULE_FEEDING):
                return await self.async_step_dog_feeding()
            # Continue to health configuration if enabled
            elif self._current_dog_config[CONF_MODULES].get(MODULE_HEALTH):
                return await self.async_step_dog_health()
            else:
                # Finalize dog configuration
                self._dogs.append(self._current_dog_config)
                return await self.async_step_add_another_dog()

        # Get available GPS sources
        device_trackers = self._get_available_device_trackers()
        person_entities = self._get_available_person_entities()

        gps_options = [{"value": "manual", "label": "📝 Manual GPS (configure later)"}]

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

        # Add per-dog GPS device options
        gps_options.extend(
            [
                {"value": "webhook", "label": "🌐 Webhook (REST API)"},
                {"value": "mqtt", "label": "📡 MQTT Topic"},
                {"value": "tractive", "label": "🐕 Tractive GPS Collar"},
            ]
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_GPS_SOURCE, default="manual"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=gps_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "gps_update_interval",
                    default=DEFAULT_GPS_UPDATE_INTERVAL,
                ): GPS_UPDATE_INTERVAL_SELECTOR,
                vol.Optional(
                    "gps_accuracy_filter",
                    default=DEFAULT_GPS_ACCURACY_FILTER,
                ): GPS_ACCURACY_FILTER_SELECTOR,
                vol.Optional(
                    "enable_geofencing", default=True
                ): selector.BooleanSelector(),
                vol.Optional("home_zone_radius", default=50): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=500,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="meters",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="dog_gps",
            data_schema=schema,
            description_placeholders={
                "dog_name": self._current_dog_config[CONF_DOG_NAME],
            },
        )

    async def async_step_dog_feeding(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure feeding settings for the specific dog.

        This step allows detailed feeding configuration including
        meal times, portions, and automatic calculations.

        Args:
            user_input: Feeding configuration for the dog

        Returns:
            Configuration flow result for next step
        """
        if user_input is not None:
            # Calculate portions based on meals per day
            meals_per_day = user_input.get(CONF_MEALS_PER_DAY, 2)
            daily_amount = user_input.get(CONF_DAILY_FOOD_AMOUNT, 500)
            portion_size = daily_amount / meals_per_day

            # Store feeding configuration for this dog
            feeding_config = {
                CONF_MEALS_PER_DAY: meals_per_day,
                CONF_DAILY_FOOD_AMOUNT: daily_amount,
                "portion_size": portion_size,
                CONF_FOOD_TYPE: user_input.get(CONF_FOOD_TYPE, "dry_food"),
                "feeding_schedule": user_input.get("feeding_schedule", "flexible"),
                "enable_reminders": user_input.get("enable_reminders", True),
                "reminder_minutes_before": user_input.get(
                    "reminder_minutes_before", 15
                ),
            }

            # Add meal times based on selection
            if user_input.get("breakfast_enabled", meals_per_day >= 1):
                feeding_config[CONF_BREAKFAST_TIME] = user_input.get(
                    CONF_BREAKFAST_TIME, "07:00:00"
                )

            if user_input.get("lunch_enabled", meals_per_day >= 3):
                feeding_config[CONF_LUNCH_TIME] = user_input.get(
                    CONF_LUNCH_TIME, "12:00:00"
                )

            if user_input.get("dinner_enabled", meals_per_day >= 2):
                feeding_config[CONF_DINNER_TIME] = user_input.get(
                    CONF_DINNER_TIME, "18:00:00"
                )

            if user_input.get("snacks_enabled", False):
                feeding_config[CONF_SNACK_TIMES] = ["10:00:00", "15:00:00", "20:00:00"]

            self._current_dog_config["feeding_config"] = feeding_config

            # Continue to health configuration if enabled
            if self._current_dog_config[CONF_MODULES].get(
                MODULE_HEALTH
            ) or self._current_dog_config[CONF_MODULES].get(MODULE_MEDICATION):
                return await self.async_step_dog_health()
            else:
                # Finalize dog configuration
                self._dogs.append(self._current_dog_config)
                self._current_dog_config = None
                return await self.async_step_add_another_dog()

        # Calculate suggested daily food amount based on weight and size
        dog_weight = self._current_dog_config.get(CONF_DOG_WEIGHT, 20)
        dog_size = self._current_dog_config.get(CONF_DOG_SIZE, "medium")
        suggested_amount = self._calculate_suggested_food_amount(dog_weight, dog_size)

        schema = vol.Schema(
            {
                vol.Required(CONF_MEALS_PER_DAY, default=2): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=6,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_DAILY_FOOD_AMOUNT, default=suggested_amount
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=50,
                        max=2000,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="g",
                    )
                ),
                vol.Optional(
                    CONF_FOOD_TYPE, default="dry_food"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "dry_food", "label": "🥜 Dry Food"},
                            {"value": "wet_food", "label": "🥫 Wet Food"},
                            {"value": "barf", "label": "🥩 BARF"},
                            {"value": "home_cooked", "label": "🍲 Home Cooked"},
                            {"value": "mixed", "label": "🔄 Mixed"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "feeding_schedule", default="flexible"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "flexible", "label": "⏰ Flexible Times"},
                            {"value": "strict", "label": "🎯 Strict Schedule"},
                            {"value": "custom", "label": "⚙️ Custom Schedule"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "breakfast_enabled", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_BREAKFAST_TIME, default="07:00:00"
                ): selector.TimeSelector(),
                vol.Optional(
                    "lunch_enabled", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_LUNCH_TIME, default="12:00:00"
                ): selector.TimeSelector(),
                vol.Optional(
                    "dinner_enabled", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_DINNER_TIME, default="18:00:00"
                ): selector.TimeSelector(),
                vol.Optional(
                    "snacks_enabled", default=False
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_reminders", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "reminder_minutes_before", default=15
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=60,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="minutes",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="dog_feeding",
            data_schema=schema,
            description_placeholders={
                "dog_name": self._current_dog_config[CONF_DOG_NAME],
                "dog_weight": str(dog_weight),
                "suggested_amount": str(suggested_amount),
                "portion_info": f"Automatic portion calculation: {suggested_amount}g per day",
            },
        )

    async def async_step_dog_health(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure comprehensive health settings including health-aware feeding.

        This step collects detailed health data for advanced portion calculation,
        body condition scoring, activity levels, and medical conditions.

        Args:
            user_input: Health configuration for the dog

        Returns:
            Configuration flow result for next step
        """
        if user_input is not None:
            # Store comprehensive health configuration for this dog
            health_config = {
                # Basic vet information
                "vet_name": user_input.get("vet_name", ""),
                "vet_phone": user_input.get("vet_phone", ""),
                "last_vet_visit": user_input.get("last_vet_visit"),
                "next_checkup": user_input.get("next_checkup"),
                "weight_tracking": user_input.get("weight_tracking", True),
                # Health-aware feeding integration
                "ideal_weight": user_input.get(
                    "ideal_weight", self._current_dog_config.get(CONF_DOG_WEIGHT)
                ),
                "body_condition_score": user_input.get("body_condition_score", 5),
                "activity_level": user_input.get("activity_level", "moderate"),
                "weight_goal": user_input.get("weight_goal", "maintain"),
                "spayed_neutered": user_input.get("spayed_neutered", True),
                # Health conditions that affect feeding
                "health_conditions": self._collect_health_conditions(user_input),
                "special_diet_requirements": self._collect_special_diet(user_input),
            }

            # Vaccination data
            vaccinations = {}
            if user_input.get("rabies_vaccination"):
                vaccinations["rabies"] = {
                    "date": user_input.get("rabies_vaccination"),
                    "next_due": user_input.get("rabies_next"),
                }

            if user_input.get("dhpp_vaccination"):
                vaccinations["dhpp"] = {
                    "date": user_input.get("dhpp_vaccination"),
                    "next_due": user_input.get("dhpp_next"),
                }

            if user_input.get("bordetella_vaccination"):
                vaccinations["bordetella"] = {
                    "date": user_input.get("bordetella_vaccination"),
                    "next_due": user_input.get("bordetella_next"),
                }

            if vaccinations:
                health_config["vaccinations"] = vaccinations

            # Medication data
            if self._current_dog_config[CONF_MODULES].get(MODULE_MEDICATION):
                medications = []

                if user_input.get("medication_1_name"):
                    medications.append(
                        {
                            "name": user_input.get("medication_1_name"),
                            "dosage": user_input.get("medication_1_dosage", ""),
                            "frequency": user_input.get(
                                "medication_1_frequency", "daily"
                            ),
                            "time": user_input.get("medication_1_time", "08:00:00"),
                            "notes": user_input.get("medication_1_notes", ""),
                            "with_meals": user_input.get(
                                "medication_1_with_meals", False
                            ),
                        }
                    )

                if user_input.get("medication_2_name"):
                    medications.append(
                        {
                            "name": user_input.get("medication_2_name"),
                            "dosage": user_input.get("medication_2_dosage", ""),
                            "frequency": user_input.get(
                                "medication_2_frequency", "daily"
                            ),
                            "time": user_input.get("medication_2_time", "20:00:00"),
                            "notes": user_input.get("medication_2_notes", ""),
                            "with_meals": user_input.get(
                                "medication_2_with_meals", False
                            ),
                        }
                    )

                if medications:
                    health_config["medications"] = medications

            self._current_dog_config["health_config"] = health_config

            # Update feeding config with health data for portion calculation
            if "feeding_config" in self._current_dog_config:
                feeding_config = self._current_dog_config["feeding_config"]

                # Validate diet combinations and log results
                diet_validation = self._validate_diet_combinations(
                    health_config["special_diet_requirements"]
                )

                # Add health integration to feeding config
                feeding_config.update(
                    {
                        "health_aware_portions": user_input.get(
                            "health_aware_portions", True
                        ),
                        "dog_weight": self._current_dog_config.get(CONF_DOG_WEIGHT),
                        "ideal_weight": health_config["ideal_weight"],
                        "age_months": self._current_dog_config.get(CONF_DOG_AGE, 3)
                        * 12,
                        "breed_size": self._current_dog_config.get(
                            CONF_DOG_SIZE, "medium"
                        ),
                        "activity_level": health_config["activity_level"],
                        "body_condition_score": health_config["body_condition_score"],
                        "health_conditions": health_config["health_conditions"],
                        "weight_goal": health_config["weight_goal"],
                        "spayed_neutered": health_config["spayed_neutered"],
                        "special_diet": health_config["special_diet_requirements"],
                        "diet_validation": diet_validation,
                        "medication_with_meals": any(
                            med.get("with_meals", False)
                            for med in health_config.get("medications", [])
                        ),
                    }
                )

                # Log diet validation results for portion calculation optimization
                if diet_validation["recommended_vet_consultation"]:
                    _LOGGER.info(
                        "Diet validation for %s recommends veterinary consultation: %s conflicts, %s warnings",
                        self._current_dog_config[CONF_DOG_NAME],
                        len(diet_validation["conflicts"]),
                        len(diet_validation["warnings"]),
                    )

            # Finalize dog configuration
            self._dogs.append(self._current_dog_config)
            return await self.async_step_add_another_dog()

        # Calculate suggestions based on dog characteristics
        dog_age = self._current_dog_config.get(CONF_DOG_AGE, 3)
        dog_size = self._current_dog_config.get(CONF_DOG_SIZE, "medium")
        dog_weight = self._current_dog_config.get(CONF_DOG_WEIGHT, 20.0)

        # Suggest ideal weight (typically 95-105% of current weight for healthy dogs)
        suggested_ideal_weight = round(dog_weight * 1.0, 1)

        # Suggest activity level based on age and size
        suggested_activity = self._suggest_activity_level(dog_age, dog_size)

        # Build comprehensive schema with ALL special diet options from const.py
        schema_dict = {
            # Basic vet information
            vol.Optional("vet_name", default=""): selector.TextSelector(),
            vol.Optional("vet_phone", default=""): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEL,
                )
            ),
            vol.Optional("last_vet_visit"): selector.DateSelector(),
            vol.Optional("next_checkup"): selector.DateSelector(),
            vol.Optional("weight_tracking", default=True): selector.BooleanSelector(),
            # Health-aware feeding configuration
            vol.Optional(
                "health_aware_portions", default=True
            ): selector.BooleanSelector(),
            vol.Optional(
                "ideal_weight", default=suggested_ideal_weight
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_DOG_WEIGHT,
                    max=MAX_DOG_WEIGHT,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="kg",
                )
            ),
            vol.Optional("body_condition_score", default=5): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=9,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                "activity_level", default=suggested_activity
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {
                            "value": "very_low",
                            "label": "🛌 Very Low - Inactive, elderly, or sick",
                        },
                        {
                            "value": "low",
                            "label": "🚶 Low - Light exercise, mostly indoor",
                        },
                        {
                            "value": "moderate",
                            "label": "🏃 Moderate - Regular walks and play",
                        },
                        {
                            "value": "high",
                            "label": "🏋️ High - Very active, long walks/runs",
                        },
                        {
                            "value": "very_high",
                            "label": "🏆 Very High - Working or athletic dogs",
                        },
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("weight_goal", default="maintain"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": "lose", "label": "📉 Weight Loss"},
                        {"value": "maintain", "label": "⚖️ Maintain Current Weight"},
                        {"value": "gain", "label": "📈 Weight Gain"},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("spayed_neutered", default=True): selector.BooleanSelector(),
            # Health conditions affecting feeding
            vol.Optional("has_diabetes", default=False): selector.BooleanSelector(),
            vol.Optional(
                "has_kidney_disease", default=False
            ): selector.BooleanSelector(),
            vol.Optional(
                "has_heart_disease", default=False
            ): selector.BooleanSelector(),
            vol.Optional("has_arthritis", default=False): selector.BooleanSelector(),
            vol.Optional("has_allergies", default=False): selector.BooleanSelector(),
            vol.Optional(
                "has_digestive_issues", default=False
            ): selector.BooleanSelector(),
            vol.Optional(
                "other_health_conditions", default=""
            ): selector.TextSelector(),
        }

        # Add ALL special diet options from const.SPECIAL_DIET_OPTIONS
        # Organized by category for better UX

        # Health/Medical diet requirements
        medical_diets = [
            "prescription",
            "diabetic",
            "kidney_support",
            "low_fat",
            "weight_control",
            "sensitive_stomach",
        ]
        for diet in medical_diets:
            if diet in SPECIAL_DIET_OPTIONS:
                schema_dict[vol.Optional(diet, default=False)] = (
                    selector.BooleanSelector()
                )

        # Age-based diet requirements
        age_diets = ["senior_formula", "puppy_formula"]
        for diet in age_diets:
            if diet in SPECIAL_DIET_OPTIONS:
                default_value = (diet == "senior_formula" and dog_age >= 7) or (
                    diet == "puppy_formula" and dog_age < 2
                )
                schema_dict[vol.Optional(diet, default=default_value)] = (
                    selector.BooleanSelector()
                )

        # Allergy/Sensitivity diet requirements
        allergy_diets = ["grain_free", "hypoallergenic"]
        for diet in allergy_diets:
            if diet in SPECIAL_DIET_OPTIONS:
                schema_dict[vol.Optional(diet, default=False)] = (
                    selector.BooleanSelector()
                )

        # Lifestyle/Care diet requirements
        lifestyle_diets = ["organic", "raw_diet", "dental_care", "joint_support"]
        for diet in lifestyle_diets:
            if diet in SPECIAL_DIET_OPTIONS:
                # Smart defaults based on dog characteristics
                default_value = False
                if diet == "joint_support" and (
                    dog_age >= 7 or dog_size in ("large", "giant")
                ):
                    default_value = True
                schema_dict[vol.Optional(diet, default=default_value)] = (
                    selector.BooleanSelector()
                )

        # Add vaccination fields
        schema_dict.update(
            {
                vol.Optional("rabies_vaccination"): selector.DateSelector(),
                vol.Optional("rabies_next"): selector.DateSelector(),
                vol.Optional("dhpp_vaccination"): selector.DateSelector(),
                vol.Optional("dhpp_next"): selector.DateSelector(),
                vol.Optional("bordetella_vaccination"): selector.DateSelector(),
                vol.Optional("bordetella_next"): selector.DateSelector(),
            }
        )

        # Add medication fields if module is enabled
        if self._current_dog_config[CONF_MODULES].get(MODULE_MEDICATION):
            schema_dict.update(
                {
                    vol.Optional("medication_1_name"): selector.TextSelector(),
                    vol.Optional("medication_1_dosage"): selector.TextSelector(),
                    vol.Optional(
                        "medication_1_frequency", default="daily"
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "daily", "label": "Daily"},
                                {"value": "twice_daily", "label": "Twice Daily"},
                                {"value": "weekly", "label": "Weekly"},
                                {"value": "as_needed", "label": "As Needed"},
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        "medication_1_time", default="08:00:00"
                    ): selector.TimeSelector(),
                    vol.Optional(
                        "medication_1_with_meals", default=False
                    ): selector.BooleanSelector(),
                    vol.Optional("medication_1_notes"): selector.TextSelector(),
                    vol.Optional("medication_2_name"): selector.TextSelector(),
                    vol.Optional("medication_2_dosage"): selector.TextSelector(),
                    vol.Optional(
                        "medication_2_frequency", default="daily"
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "daily", "label": "Daily"},
                                {"value": "twice_daily", "label": "Twice Daily"},
                                {"value": "weekly", "label": "Weekly"},
                                {"value": "as_needed", "label": "As Needed"},
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        "medication_2_time", default="20:00:00"
                    ): selector.TimeSelector(),
                    vol.Optional(
                        "medication_2_with_meals", default=False
                    ): selector.BooleanSelector(),
                    vol.Optional("medication_2_notes"): selector.TextSelector(),
                }
            )

        schema = vol.Schema(schema_dict)

        # Generate diet compatibility info
        diet_compatibility_info = self._get_diet_compatibility_guidance(
            dog_age, dog_size
        )

        return self.async_show_form(
            step_id="dog_health",
            data_schema=schema,
            description_placeholders={
                "dog_name": self._current_dog_config[CONF_DOG_NAME],
                "dog_age": str(dog_age),
                "dog_weight": str(dog_weight),
                "suggested_ideal_weight": str(suggested_ideal_weight),
                "suggested_activity": suggested_activity,
                "medication_enabled": "yes"
                if self._current_dog_config[CONF_MODULES].get(MODULE_MEDICATION)
                else "no",
                "bcs_info": "Body Condition Score: 1=Emaciated, 5=Ideal, 9=Obese",
                "special_diet_count": str(len(SPECIAL_DIET_OPTIONS)),
                "health_diet_info": f"Select all special diet requirements that apply to optimize feeding calculations\n\n⚠️ Compatibility Info:\n{diet_compatibility_info}",
            },
        )

    async def _async_validate_dog_config(
        self, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate dog configuration with rate limiting.

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
            # Increased micro-delay for rate limiting
            await asyncio.sleep(0.05)

            # Check cache first for performance
            cache_key = self._create_cache_key(dog_id, dog_name, user_input)
            if (cached := self._get_cached_validation(cache_key)) is not None:
                return cached

            # Enhanced dog ID validation
            if error := self._validate_dog_id(dog_id):
                errors[CONF_DOG_ID] = error

            # Enhanced dog name validation
            if error := self._validate_dog_name(dog_name):
                errors[CONF_DOG_NAME] = error

            # Enhanced weight validation with size correlation
            if error := self._validate_weight(user_input):
                errors[CONF_DOG_WEIGHT] = error

            # Enhanced age validation
            if error := self._validate_age(user_input):
                errors[CONF_DOG_AGE] = error

            # Breed validation (optional but helpful)
            if error := self._validate_breed(user_input):
                errors[CONF_DOG_BREED] = error

            # Cache the result for performance
            result = {
                "valid": len(errors) == 0,
                "errors": errors,
            }

            self._update_validation_cache(cache_key, result)

            return result

        except Exception as err:
            _LOGGER.error("Error validating dog configuration: %s", err)
            return {
                "valid": False,
                "errors": {"base": "validation_error"},
            }

    def _create_cache_key(
        self, dog_id: str, dog_name: str, user_input: dict[str, Any]
    ) -> str:
        weight = user_input.get(CONF_DOG_WEIGHT, "none")
        age_val = user_input.get(CONF_DOG_AGE, "none")
        size = user_input.get(CONF_DOG_SIZE, "none")
        breed = user_input.get(CONF_DOG_BREED, "none")
        return f"{dog_id}_{dog_name}_{weight}_{age_val}_{size}_{breed}"

    def _get_cached_validation(self, cache_key: str) -> dict[str, Any] | None:
        cached = self._validation_cache.get(cache_key)
        if cached is not None and (
            cached.get("timestamp", 0) > asyncio.get_running_loop().time() - 5
        ):
            return cached["result"]
        return None

    def _update_validation_cache(self, cache_key: str, result: dict[str, Any]) -> None:
        self._validation_cache[cache_key] = {
            "result": result,
            "timestamp": asyncio.get_running_loop().time(),
        }

    def _validate_dog_id(self, dog_id: str) -> str | None:
        if not DOG_ID_PATTERN.match(dog_id):
            return "invalid_dog_id_format"
        if any(dog[CONF_DOG_ID] == dog_id for dog in self._dogs):
            return "dog_id_already_exists"
        if len(dog_id) < 2:
            return "dog_id_too_short"
        if len(dog_id) > 30:
            return "dog_id_too_long"
        return None

    def _validate_dog_name(self, dog_name: str) -> str | None:
        if not dog_name:
            return "dog_name_required"
        if len(dog_name) < MIN_DOG_NAME_LENGTH:
            return "dog_name_too_short"
        if len(dog_name) > MAX_DOG_NAME_LENGTH:
            return "dog_name_too_long"
        if len(self._lower_dog_names) != len(self._dogs):
            self._lower_dog_names = {dog[CONF_DOG_NAME].lower() for dog in self._dogs}
        if dog_name.lower() in self._lower_dog_names:
            return "dog_name_already_exists"
        return None

    def _validate_weight(self, user_input: dict[str, Any]) -> str | None:
        weight = user_input.get(CONF_DOG_WEIGHT)
        size = user_input.get(CONF_DOG_SIZE, "medium")
        if weight is not None:
            try:
                weight_float = float(weight)
                if weight_float < MIN_DOG_WEIGHT or weight_float > MAX_DOG_WEIGHT:
                    return "weight_out_of_range"
                if not self._is_weight_size_compatible(weight_float, size):
                    return "weight_size_mismatch"
            except (ValueError, TypeError):
                return "invalid_weight_format"
        return None

    def _validate_age(self, user_input: dict[str, Any]) -> str | None:
        age = user_input.get(CONF_DOG_AGE)
        if age is not None:
            try:
                age_int = int(age)
                if age_int < MIN_DOG_AGE or age_int > MAX_DOG_AGE:
                    return "age_out_of_range"
            except (ValueError, TypeError):
                return "invalid_age_format"
        return None

    def _validate_breed(self, user_input: dict[str, Any]) -> str | None:
        breed = user_input.get(CONF_DOG_BREED, "").strip()
        if breed and len(breed) > 100:
            return "breed_name_too_long"
        return None

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
        dog_weight = user_input.get(CONF_DOG_WEIGHT, 20.0)

        return {
            CONF_DOG_ID: dog_id,
            CONF_DOG_NAME: user_input[CONF_DOG_NAME].strip(),
            CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, "").strip() or "Mixed Breed",
            CONF_DOG_AGE: dog_age,
            CONF_DOG_WEIGHT: dog_weight,
            CONF_DOG_SIZE: dog_size,
            "created_at": time.time(),
        }

    def _calculate_suggested_food_amount(self, weight: float, size: str) -> int:
        """Calculate suggested daily food amount based on dog characteristics.

        Args:
            weight: Dog weight in kg
            size: Dog size category

        Returns:
            Suggested daily food amount in grams
        """
        # Basic calculation: 2-3% of body weight for adult dogs
        base_amount = weight * 25  # 2.5% of body weight in grams

        # Adjust for size (smaller dogs have higher metabolism)
        size_multipliers = {
            "toy": 1.3,
            "small": 1.2,
            "medium": 1.0,
            "large": 0.9,
            "giant": 0.85,
        }

        multiplier = size_multipliers.get(size, 1.0)
        suggested = int(base_amount * multiplier)

        # Round to nearest 10g
        return round(suggested / 10) * 10

    def _get_feeding_defaults_by_size(self, dog_size: str) -> dict[str, Any]:
        """Get feeding defaults based on dog size.

        Args:
            dog_size: Size category of the dog

        Returns:
            Dictionary with feeding defaults
        """
        feeding_defaults = {
            "toy": {
                CONF_MEALS_PER_DAY: 3,
                CONF_DAILY_FOOD_AMOUNT: 150,
                "portion_size": 50,
            },
            "small": {
                CONF_MEALS_PER_DAY: 2,
                CONF_DAILY_FOOD_AMOUNT: 300,
                "portion_size": 150,
            },
            "medium": {
                CONF_MEALS_PER_DAY: 2,
                CONF_DAILY_FOOD_AMOUNT: 500,
                "portion_size": 250,
            },
            "large": {
                CONF_MEALS_PER_DAY: 2,
                CONF_DAILY_FOOD_AMOUNT: 800,
                "portion_size": 400,
            },
            "giant": {
                CONF_MEALS_PER_DAY: 2,
                CONF_DAILY_FOOD_AMOUNT: 1200,
                "portion_size": 600,
            },
        }

        return feeding_defaults.get(dog_size, feeding_defaults["medium"])

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
                self._current_dog_config = None
                return await self.async_step_add_dog()
            else:
                # All dogs configured, continue to global settings if needed
                return await self.async_step_configure_modules()

        # Check if we've reached the limit
        at_limit = len(self._dogs) >= MAX_DOGS_PER_ENTRY

        schema = vol.Schema(
            {
                vol.Required("add_another", default=False): selector.BooleanSelector(),
            }
        )

        description_placeholders = {
            "dogs_list": self._format_dogs_list(),
            "dog_count": str(len(self._dogs)),
            "max_dogs": MAX_DOGS_PER_ENTRY,
            "remaining_spots": MAX_DOGS_PER_ENTRY - len(self._dogs),
            "at_limit": "true" if at_limit else "false",
        }

        return self.async_show_form(
            step_id="add_another_dog",
            data_schema=schema,
            description_placeholders=description_placeholders,
        )

    def _collect_health_conditions(self, user_input: dict[str, Any]) -> list[str]:
        """Collect health conditions from user input for feeding calculations.

        Args:
            user_input: User form input data

        Returns:
            List of health conditions affecting feeding
        """
        conditions = []

        # Map form fields to health condition names
        condition_mapping = {
            "has_diabetes": "diabetes",
            "has_kidney_disease": "kidney_disease",
            "has_heart_disease": "heart_disease",
            "has_arthritis": "arthritis",
            "has_allergies": "allergies",
            "has_digestive_issues": "digestive_issues",
        }

        # Add selected conditions
        for field, condition in condition_mapping.items():
            if user_input.get(field, False):
                conditions.append(condition)

        # Add other conditions from text field
        other_conditions = user_input.get("other_health_conditions", "").strip()
        if other_conditions:
            # Split by comma and clean up
            additional = [
                cond.strip().lower().replace(" ", "_")
                for cond in other_conditions.split(",")
                if cond.strip()
            ]
            conditions.extend(additional)

        return conditions

    def _collect_special_diet(self, user_input: dict[str, Any]) -> list[str]:
        """Collect special diet requirements from user input.

        Uses SPECIAL_DIET_OPTIONS from const.py to ensure consistency
        across the integration and capture all 14 diet options.

        Args:
            user_input: User form input data

        Returns:
            List of special diet requirements matching const.SPECIAL_DIET_OPTIONS
        """
        diet_requirements = []

        # Use SPECIAL_DIET_OPTIONS as authoritative source
        # Direct 1:1 mapping from form fields to diet requirement names
        for diet_option in SPECIAL_DIET_OPTIONS:
            if user_input.get(diet_option, False):
                diet_requirements.append(diet_option)  # noqa: PERF401

        # Validate diet combinations for conflicts
        validation_result = self._validate_diet_combinations(diet_requirements)
        if validation_result["conflicts"]:
            _LOGGER.warning(
                "Conflicting diet combinations detected: %s",
                validation_result["conflicts"],
            )
            # Log conflicts but don't prevent configuration - user might have vet guidance

        _LOGGER.debug(
            "Collected special diet requirements: %s from input: %s",
            diet_requirements,
            {k: v for k, v in user_input.items() if k in SPECIAL_DIET_OPTIONS and v},
        )

        return diet_requirements

    def _validate_diet_combinations(
        self, diet_requirements: list[str]
    ) -> dict[str, Any]:
        """Validate special diet combinations for conflicts and incompatibilities.

        Args:
            diet_requirements: List of selected diet requirements

        Returns:
            Dictionary with validation results and conflict information
        """
        conflicts = []
        warnings = []

        # Age-based diet conflicts
        if (
            "puppy_formula" in diet_requirements
            and "senior_formula" in diet_requirements
        ):
            conflicts.append(
                {
                    "type": "age_conflict",
                    "diets": ["puppy_formula", "senior_formula"],
                    "message": "Puppy and senior formulas are mutually exclusive",
                }
            )

        # Weight management conflicts
        if (
            "weight_control" in diet_requirements
            and "puppy_formula" in diet_requirements
        ):
            warnings.append(
                {
                    "type": "weight_puppy_warning",
                    "diets": ["weight_control", "puppy_formula"],
                    "message": "Weight control diets are typically not recommended for growing puppies",
                }
            )

        # Raw diet with certain medical conditions
        if "raw_diet" in diet_requirements:
            medical_conflicts = [
                "prescription",
                "kidney_support",
                "diabetic",
                "sensitive_stomach",
                "organic",
            ]
            conflicting_medical = [
                diet for diet in medical_conflicts if diet in diet_requirements
            ]
            if conflicting_medical:
                warnings.append(
                    {
                        "type": "raw_medical_warning",
                        "diets": ["raw_diet", *conflicting_medical],
                        "message": "Raw diets may require veterinary supervision with medical conditions",
                    }
                )

        # Multiple prescription-level diets
        prescription_diets = [
            "prescription",
            "diabetic",
            "kidney_support",
            "sensitive_stomach",
        ]
        selected_prescriptions = [
            diet for diet in prescription_diets if diet in diet_requirements
        ]
        if len(selected_prescriptions) > 1:
            warnings.append(
                {
                    "type": "multiple_prescription_warning",
                    "diets": selected_prescriptions,
                    "message": "Multiple prescription diets should be coordinated with veterinarian",
                }
            )

        # Hypoallergenic conflicts
        if "hypoallergenic" in diet_requirements:
            potential_allergen_diets = ["organic", "raw_diet"]
            conflicting_allergens = [
                diet for diet in potential_allergen_diets if diet in diet_requirements
            ]
            if conflicting_allergens:
                warnings.append(
                    {
                        "type": "hypoallergenic_warning",
                        "diets": ["hypoallergenic", *conflicting_allergens],
                        "message": "Hypoallergenic diets should be carefully managed with other diet types",
                    }
                )

        # Low fat with high-activity requirements
        if False:
            warnings.append({})

        return {
            "valid": len(conflicts) == 0,
            "conflicts": conflicts,
            "warnings": warnings,
            "total_diets": len(diet_requirements),
            "recommended_vet_consultation": len(warnings) > 0 or len(conflicts) > 0,
        }

    def _suggest_activity_level(self, dog_age: int, dog_size: str) -> str:
        """Suggest activity level based on dog characteristics.

        Args:
            dog_age: Dog age in years
            dog_size: Dog size category

        Returns:
            Suggested activity level
        """
        # Age-based activity suggestions
        if dog_age < 1:
            return "moderate"  # Puppies have bursts of energy but need rest
        elif dog_age >= 10:
            return "low"  # Senior dogs generally less active
        elif dog_age >= 7:
            return "moderate"  # Older adults

        # Size-based activity suggestions for adult dogs
        size_activity_map = {
            "toy": "moderate",  # Small dogs, moderate exercise needs
            "small": "moderate",  # Good for apartments, regular walks
            "medium": "high",  # Active breeds, need regular exercise
            "large": "high",  # Working breeds, high energy
            "giant": "moderate",  # Large but often calmer temperament
        }

        return size_activity_map.get(dog_size, "moderate")

    def _get_diet_compatibility_guidance(self, dog_age: int, dog_size: str) -> str:
        """Get guidance text about diet compatibility based on dog characteristics.

        Args:
            dog_age: Dog age in years
            dog_size: Dog size category

        Returns:
            Formatted guidance text for diet selection
        """
        guidance_points = []

        # Age-specific guidance
        if dog_age < 2:
            guidance_points.append(
                "🐶 Puppies: Consider puppy_formula, avoid weight_control"
            )
        elif dog_age >= 7:
            guidance_points.append(
                "👴 Seniors: Consider senior_formula, joint_support may be beneficial"
            )

        # Size-specific guidance
        if dog_size in ("large", "giant"):
            guidance_points.append(
                "🦴 Large breeds: Joint_support recommended, watch for food allergies"
            )
        elif dog_size == "toy":
            guidance_points.append(
                "🐭 Toy breeds: Often benefit from sensitive_stomach, small kibble size"
            )

        # General compatibility warnings
        guidance_points.extend(
            [
                "⚠️ Multiple prescription diets need vet coordination",
                "🥩 Raw diets require careful handling with medical conditions",
                "🏥 Prescription diets override lifestyle preferences",
            ]
        )

        return (
            "\n".join(guidance_points)
            if guidance_points
            else "No specific compatibility concerns detected"
        )

    async def async_step_configure_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure global module settings after all dogs are added.

        UPDATED: Now redirects to entity profile selection for performance optimization.

        This step allows configuration of integration-wide settings
        that affect all dogs, such as notification preferences and
        performance optimization.

        Args:
            user_input: Global module configuration

        Returns:
            Configuration flow result for entity profile selection
        """
        if user_input is not None:
            # Store global module settings
            self._global_modules = {
                "notifications": user_input.get("enable_notifications", True),
                "dashboard": user_input.get("enable_dashboard", True),
                "performance_mode": user_input.get("performance_mode", "balanced"),
                "data_retention_days": user_input.get("data_retention_days", 90),
                "auto_backup": user_input.get("auto_backup", False),
                "debug_logging": user_input.get("debug_logging", False),
            }

            # UPDATED: Redirect to entity profile selection for performance optimization
            _LOGGER.info(
                "Global modules configured for %d dogs, proceeding to entity profile selection",
                len(self._dogs),
            )
            return await self.async_step_entity_profile()

        # Analyze configured dogs to suggest global settings
        total_dogs = len(self._dogs)
        has_gps_dogs = sum(
            1 for dog in self._dogs if dog.get("modules", {}).get(MODULE_GPS, False)
        )
        has_health_tracking = sum(
            1 for dog in self._dogs if dog.get("modules", {}).get(MODULE_HEALTH, False)
        )

        # Suggest performance mode based on complexity
        suggested_performance = "minimal"
        if total_dogs >= 3 or has_gps_dogs >= 2:
            suggested_performance = "balanced"
        elif total_dogs >= 5 or has_gps_dogs >= 3:
            suggested_performance = "full"

        # Suggest auto-backup for complex setups
        suggested_backup = total_dogs >= 2 or has_health_tracking >= 1

        schema = vol.Schema(
            {
                vol.Optional(
                    "enable_notifications", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_dashboard", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "performance_mode", default=suggested_performance
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "minimal",
                                "label": "⚡ Minimal - Low resource usage",
                            },
                            {
                                "value": "balanced",
                                "label": "⚖️ Balanced - Good performance and features",
                            },
                            {
                                "value": "full",
                                "label": "🚀 Full - Maximum features and responsiveness",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "data_retention_days", default=90
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=365,
                        step=30,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "auto_backup", default=suggested_backup
                ): selector.BooleanSelector(),
                vol.Optional(
                    "debug_logging", default=False
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="configure_modules",
            data_schema=schema,
            description_placeholders={
                "total_dogs": str(total_dogs),
                "gps_dogs": str(has_gps_dogs),
                "health_dogs": str(has_health_tracking),
                "suggested_performance": suggested_performance,
                "complexity_info": self._get_setup_complexity_info(),
                "next_step_info": "Next: Entity profile selection for performance optimization",
            },
        )

    def _get_setup_complexity_info(self) -> str:
        """Get information about setup complexity for user guidance.

        Returns:
            Formatted complexity information string
        """
        total_dogs = len(self._dogs)
        total_modules = sum(
            len([m for m in dog.get("modules", {}).values() if m]) for dog in self._dogs
        )

        if total_dogs == 1 and total_modules <= 5:
            return "Simple setup - minimal resources needed"
        elif total_dogs <= 2 and total_modules <= 10:
            return "Standard setup - balanced performance recommended"
        else:
            return "Complex setup - full performance mode recommended"
