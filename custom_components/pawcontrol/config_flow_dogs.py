"""Dog management steps for Paw Control configuration flow.

This module handles all dog-related configuration steps including adding,
validating, and configuring individual dogs with intelligent defaults
and enhanced user experience. Now includes per-dog GPS, feeding schedules,
health data, and individual module configuration.

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

from .config_flow_base import (
    DOG_ID_PATTERN,
    ENTITY_CREATION_DELAY,
    MAX_DOGS_PER_ENTRY,
    VALIDATION_SEMAPHORE,
)
from .const import (
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
    MAX_DOG_AGE,
    MAX_DOG_NAME_LENGTH,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_NAME_LENGTH,
    MIN_DOG_WEIGHT,
    MODULE_DASHBOARD,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_MEDICATION,
    MODULE_NOTIFICATIONS,
    MODULE_TRAINING,
    MODULE_VISITOR,
    MODULE_WALK,
)
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)


class DogManagementMixin:
    """Mixin for dog management functionality in configuration flow.

    This mixin provides all the methods needed for adding, validating,
    and configuring dogs during the initial setup process with enhanced
    validation, per-dog module configuration, and comprehensive health data.
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
                MODULE_FEEDING: user_input.get("enable_feeding", True),
                MODULE_WALK: user_input.get("enable_walk", True),
                MODULE_HEALTH: user_input.get("enable_health", True),
                MODULE_GPS: user_input.get("enable_gps", False),
                MODULE_NOTIFICATIONS: user_input.get("enable_notifications", True),
                MODULE_DASHBOARD: user_input.get("enable_dashboard", True),
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
                    "enable_feeding", default=True
                ): selector.BooleanSelector(),
                vol.Optional("enable_walk", default=True): selector.BooleanSelector(),
                vol.Optional("enable_health", default=True): selector.BooleanSelector(),
                vol.Optional(
                    "enable_gps", default=suggested_gps
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_notifications", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_dashboard", default=True
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_visitor", default=suggested_visitor
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_grooming", default=True
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
                    "gps_update_interval", default=60
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
                    "gps_accuracy_filter", default=100
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
        """Configure health settings including vaccinations and medications.

        This step allows comprehensive health data configuration including
        vaccination dates, medication schedules, and vet information.

        Args:
            user_input: Health configuration for the dog

        Returns:
            Configuration flow result for next step
        """
        if user_input is not None:
            # Store health configuration for this dog
            health_config = {
                "vet_name": user_input.get("vet_name", ""),
                "vet_phone": user_input.get("vet_phone", ""),
                "last_vet_visit": user_input.get("last_vet_visit"),
                "next_checkup": user_input.get("next_checkup"),
                "weight_tracking": user_input.get("weight_tracking", True),
                "target_weight": user_input.get(
                    "target_weight", self._current_dog_config.get(CONF_DOG_WEIGHT)
                ),
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
                        }
                    )

                if medications:
                    health_config["medications"] = medications

            self._current_dog_config["health_config"] = health_config

            # Finalize dog configuration
            self._dogs.append(self._current_dog_config)
            return await self.async_step_add_another_dog()

        # Build schema based on enabled modules
        schema_dict = {
            vol.Optional("vet_name", default=""): selector.TextSelector(),
            vol.Optional("vet_phone", default=""): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEL,
                )
            ),
            vol.Optional("last_vet_visit"): selector.DateSelector(),
            vol.Optional("next_checkup"): selector.DateSelector(),
            vol.Optional("weight_tracking", default=True): selector.BooleanSelector(),
            vol.Optional(
                "target_weight",
                default=self._current_dog_config.get(CONF_DOG_WEIGHT, 20),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_DOG_WEIGHT,
                    max=MAX_DOG_WEIGHT,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="kg",
                )
            ),
        }

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
                    vol.Optional("medication_2_notes"): selector.TextSelector(),
                }
            )

        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="dog_health",
            data_schema=schema,
            description_placeholders={
                "dog_name": self._current_dog_config[CONF_DOG_NAME],
                "dog_age": str(self._current_dog_config.get(CONF_DOG_AGE, 3)),
                "medication_enabled": "yes"
                if self._current_dog_config[CONF_MODULES].get(MODULE_MEDICATION)
                else "no",
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
        dog_weight = user_input.get(CONF_DOG_WEIGHT, 20.0)

        return {
            CONF_DOG_ID: dog_id,
            CONF_DOG_NAME: user_input[CONF_DOG_NAME].strip(),
            CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, "").strip() or "Mixed Breed",
            CONF_DOG_AGE: dog_age,
            CONF_DOG_WEIGHT: dog_weight,
            CONF_DOG_SIZE: dog_size,
            "created_at": asyncio.get_event_loop().time(),
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
