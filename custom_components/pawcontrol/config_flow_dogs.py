"""Dog management steps for Paw Control configuration flow.

This module handles all dog-related configuration steps including adding,
validating, and configuring individual dogs with intelligent defaults
and enhanced user experience. Now includes per-dog GPS, feeding schedules,
health data, and individual module configuration.

Quality Scale: Platinum target
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

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
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_MEDICATION,
    SPECIAL_DIET_OPTIONS,
)
from custom_components.pawcontrol.types import (
    DOG_AGE_FIELD,
    DOG_BREED_FIELD,
    DOG_FEEDING_CONFIG_FIELD,
    DOG_GPS_CONFIG_FIELD,
    DOG_HEALTH_CONFIG_FIELD,
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DOG_SIZE_FIELD,
    DOG_WEIGHT_FIELD,
    MODULE_TOGGLE_FLAG_BY_KEY,
    MODULE_TOGGLE_KEYS,
    AddAnotherDogInput,
    AddAnotherDogSummaryPlaceholders,
    AddDogCapacityPlaceholders,
    ConfigFlowPlaceholders,
    DietCompatibilityIssue,
    DietValidationResult,
    DogConfigData,
    DogFeedingConfig,
    DogFeedingPlaceholders,
    DogFeedingStepInput,
    DogGPSConfig,
    DogGPSPlaceholders,
    DogGPSStepInput,
    DogHealthConfig,
    DogHealthPlaceholders,
    DogHealthStepInput,
    DogMedicationEntry,
    DogModulesConfig,
    DogModuleSelectionInput,
    DogModulesSuggestionPlaceholders,
    DogSetupStepInput,
    DogVaccinationRecord,
    DogValidationCacheEntry,
    DogValidationResult,
    JSONMapping,
    ModuleConfigurationSnapshot,
    ModuleConfigurationStepInput,
    ModuleSetupSummaryPlaceholders,
    ModuleToggleKey,
    dog_feeding_config_from_flow,
    dog_modules_from_flow_input,
    ensure_dog_modules_config,
    normalize_performance_mode,
)
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


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Coerce an arbitrary value into a boolean flag."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    if isinstance(value, int | float):
        return bool(value)
    return default


def _build_add_dog_placeholders(
    *,
    dog_count: int,
    max_dogs: int,
    current_dogs: str,
    remaining_spots: int,
) -> ConfigFlowPlaceholders:
    """Return immutable placeholders for the add-dog form."""

    placeholders: AddDogCapacityPlaceholders = {
        "dog_count": dog_count,
        "max_dogs": max_dogs,
        "current_dogs": current_dogs,
        "remaining_spots": remaining_spots,
    }
    return MappingProxyType(placeholders)


def _build_dog_modules_placeholders(
    *, dog_name: str, dog_size: str, dog_age: int
) -> ConfigFlowPlaceholders:
    """Return immutable placeholders for the module selection step."""

    placeholders: DogModulesSuggestionPlaceholders = {
        "dog_name": dog_name,
        "dog_size": dog_size,
        "dog_age": dog_age,
    }
    return MappingProxyType(placeholders)


def _build_dog_gps_placeholders(*, dog_name: str) -> ConfigFlowPlaceholders:
    """Return immutable placeholders for the GPS configuration step."""

    placeholders: DogGPSPlaceholders = {
        "dog_name": dog_name,
    }
    return MappingProxyType(placeholders)


def _build_dog_feeding_placeholders(
    *,
    dog_name: str,
    dog_weight: str,
    suggested_amount: str,
    portion_info: str,
) -> ConfigFlowPlaceholders:
    """Return immutable placeholders for the feeding configuration step."""

    placeholders: DogFeedingPlaceholders = {
        "dog_name": dog_name,
        "dog_weight": dog_weight,
        "suggested_amount": suggested_amount,
        "portion_info": portion_info,
    }
    return MappingProxyType(placeholders)


def _build_dog_health_placeholders(
    *,
    dog_name: str,
    dog_age: str,
    dog_weight: str,
    suggested_ideal_weight: str,
    suggested_activity: str,
    medication_enabled: str,
    bcs_info: str,
    special_diet_count: str,
    health_diet_info: str,
) -> ConfigFlowPlaceholders:
    """Return immutable placeholders for the health configuration step."""

    placeholders: DogHealthPlaceholders = {
        "dog_name": dog_name,
        "dog_age": dog_age,
        "dog_weight": dog_weight,
        "suggested_ideal_weight": suggested_ideal_weight,
        "suggested_activity": suggested_activity,
        "medication_enabled": medication_enabled,
        "bcs_info": bcs_info,
        "special_diet_count": special_diet_count,
        "health_diet_info": health_diet_info,
    }
    return MappingProxyType(placeholders)


def _build_add_another_summary_placeholders(
    *,
    dogs_list: str,
    dog_count: str,
    max_dogs: int,
    remaining_spots: int,
    at_limit: str,
) -> ConfigFlowPlaceholders:
    """Return immutable placeholders when asking to add another dog."""

    placeholders: AddAnotherDogSummaryPlaceholders = {
        "dogs_list": dogs_list,
        "dog_count": dog_count,
        "max_dogs": max_dogs,
        "remaining_spots": remaining_spots,
        "at_limit": at_limit,
    }
    return MappingProxyType(placeholders)


def _build_module_setup_placeholders(
    *,
    total_dogs: str,
    gps_dogs: str,
    health_dogs: str,
    suggested_performance: str,
    complexity_info: str,
    next_step_info: str,
) -> ConfigFlowPlaceholders:
    """Return immutable placeholders for the module configuration overview."""

    placeholders: ModuleSetupSummaryPlaceholders = {
        "total_dogs": total_dogs,
        "gps_dogs": gps_dogs,
        "health_dogs": health_dogs,
        "suggested_performance": suggested_performance,
        "complexity_info": complexity_info,
        "next_step_info": next_step_info,
    }
    return MappingProxyType(placeholders)


def _coerce_int(value: Any, *, default: int) -> int:
    """Coerce a value into an integer, tolerating numeric strings."""

    if isinstance(value, bool):
        return 1 if value else default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _coerce_float(value: Any, *, default: float) -> float:
    """Coerce a value into a floating point number."""

    if isinstance(value, bool):
        return 1.0 if value else default
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _coerce_optional_float(value: Any) -> float | None:
    """Return a float when conversion is possible, otherwise ``None``."""

    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_optional_int(value: Any) -> int | None:
    """Return an integer when conversion is possible, otherwise ``None``."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _coerce_str(value: Any, *, default: str = "") -> str:
    """Coerce arbitrary user input into a trimmed string."""

    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or default
    return default


def _coerce_optional_str(value: Any) -> str | None:
    """Return a trimmed string when available, otherwise ``None``."""

    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


if TYPE_CHECKING:
    from .config_flow_base import PawControlBaseConfigFlow as DogManagementMixinBase
else:

    class DogManagementMixinBase:  # pragma: no cover - runtime shim
        """Runtime stand-in for the config flow base during type checking."""

        pass


class DogManagementMixin(DogManagementMixinBase):
    """Mixin for dog management functionality in configuration flow.

    This mixin provides all the methods needed for adding, validating,
    and configuring dogs during the initial setup process with enhanced
    validation, per-dog module configuration, and comprehensive health data.
    """

    if TYPE_CHECKING:
        _current_dog_config: DogConfigData | None
        _dogs: list[DogConfigData]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize dog management mixin."""
        super().__init__(*args, **kwargs)
        self._lower_dog_names: set[str] = set()
        self._global_modules: ModuleConfigurationSnapshot = {
            "enable_notifications": True,
            "enable_dashboard": True,
            "performance_mode": "balanced",
            "data_retention_days": 90,
            "auto_backup": False,
            "debug_logging": False,
        }

    async def async_step_add_dog(
        self, user_input: DogSetupStepInput | None = None
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
                        dog_config[DOG_NAME_FIELD],
                        dog_config[DOG_ID_FIELD],
                    )

                    # Continue to module selection for this specific dog
                    return await self.async_step_dog_modules()
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
            description_placeholders=_build_add_dog_placeholders(
                dog_count=len(self._dogs),
                max_dogs=MAX_DOGS_PER_ENTRY,
                current_dogs=self._format_dogs_list(),
                remaining_spots=MAX_DOGS_PER_ENTRY - len(self._dogs),
            ),
        )

    async def async_step_dog_modules(
        self,
        user_input: DogModuleSelectionInput | DogModulesConfig | None = None,
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
            current_dog = self._current_dog_config
            if current_dog is None:
                _LOGGER.error(
                    "Dog modules step received input without active dog context"
                )
                return await self.async_step_add_dog()

            existing_modules = ensure_dog_modules_config(current_dog)
            if all(key in MODULE_TOGGLE_KEYS for key in user_input):
                modules_input = cast(DogModulesConfig, user_input)
                selection: DogModuleSelectionInput = {}
                for module_key, enabled in modules_input.items():
                    module_literal = cast(ModuleToggleKey, module_key)
                    flag = MODULE_TOGGLE_FLAG_BY_KEY.get(module_literal)
                    if flag is not None:
                        selection[flag] = bool(enabled)
                input_payload: DogModuleSelectionInput = selection
            else:
                input_payload = cast(DogModuleSelectionInput, user_input)

            modules: DogModulesConfig = dog_modules_from_flow_input(
                input_payload, existing=existing_modules
            )

            current_dog[DOG_MODULES_FIELD] = modules

            if modules.get(MODULE_GPS, False):
                return await self.async_step_dog_gps()
            if modules.get(MODULE_FEEDING, False):
                return await self.async_step_dog_feeding()
            if modules.get(MODULE_HEALTH, False) or modules.get(
                MODULE_MEDICATION, False
            ):
                return await self.async_step_dog_health()

            self._dogs.append(current_dog)
            self._current_dog_config = None
            return await self.async_step_add_another_dog()

        # Suggest modules based on dog characteristics
        current_dog = self._current_dog_config
        if current_dog is None:
            _LOGGER.error(
                "Dog modules step invoked without an active dog; returning to add_dog"
            )
            return await self.async_step_add_dog()

        dog_size_raw = current_dog.get(DOG_SIZE_FIELD)
        dog_size = dog_size_raw if isinstance(dog_size_raw, str) else "medium"

        dog_age_raw = current_dog.get(DOG_AGE_FIELD)
        dog_age = int(dog_age_raw) if isinstance(dog_age_raw, int | float) else 3

        suggested_gps = dog_size in ("large", "giant")
        suggested_visitor = dog_age >= 2
        suggested_medication = dog_age >= 7

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
            description_placeholders=_build_dog_modules_placeholders(
                dog_name=current_dog[DOG_NAME_FIELD],
                dog_size=dog_size,
                dog_age=dog_age,
            ),
        )

    async def async_step_dog_gps(
        self, user_input: DogGPSStepInput | None = None
    ) -> ConfigFlowResult:
        """Configure GPS settings for the specific dog.

        This step allows individual GPS device configuration per dog.

        Args:
            user_input: GPS configuration for the dog

        Returns:
            Configuration flow result for next step
        """
        current_dog = self._current_dog_config
        if current_dog is None:
            _LOGGER.error(
                "GPS configuration step invoked without active dog; restarting add_dog"
            )
            return await self.async_step_add_dog()

        if user_input is not None:
            # Store GPS configuration for this dog with strict typing
            gps_source = _coerce_str(user_input.get(CONF_GPS_SOURCE), default="manual")
            gps_update_interval = max(
                5, _coerce_int(user_input.get("gps_update_interval"), default=60)
            )
            gps_accuracy = _coerce_float(
                user_input.get("gps_accuracy_filter"), default=100.0
            )
            home_zone_radius = max(
                1.0, _coerce_float(user_input.get("home_zone_radius"), default=50.0)
            )

            gps_config: DogGPSConfig = {
                "gps_source": gps_source,
                "gps_update_interval": gps_update_interval,
                "gps_accuracy_filter": gps_accuracy,
                "enable_geofencing": _coerce_bool(
                    user_input.get("enable_geofencing"), default=True
                ),
                "home_zone_radius": home_zone_radius,
            }

            current_dog[DOG_GPS_CONFIG_FIELD] = gps_config

            modules = ensure_dog_modules_config(current_dog)
            if modules.get(MODULE_FEEDING, False):
                return await self.async_step_dog_feeding()
            if modules.get(MODULE_HEALTH, False):
                return await self.async_step_dog_health()

            self._dogs.append(current_dog)
            self._current_dog_config = None
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
            description_placeholders=_build_dog_gps_placeholders(
                dog_name=current_dog[DOG_NAME_FIELD]
            ),
        )

    async def async_step_dog_feeding(
        self, user_input: DogFeedingStepInput | None = None
    ) -> ConfigFlowResult:
        """Configure feeding settings for the specific dog.

        This step allows detailed feeding configuration including
        meal times, portions, and automatic calculations.

        Args:
            user_input: Feeding configuration for the dog

        Returns:
            Configuration flow result for next step
        """
        current_dog = self._current_dog_config
        if current_dog is None:
            _LOGGER.error(
                "Feeding configuration step invoked without active dog; restarting add_dog"
            )
            return await self.async_step_add_dog()

        if user_input is not None:
            feeding_config: DogFeedingConfig = dog_feeding_config_from_flow(user_input)

            current_dog[DOG_FEEDING_CONFIG_FIELD] = feeding_config

            modules = ensure_dog_modules_config(current_dog)
            if modules.get(MODULE_HEALTH, False) or modules.get(
                MODULE_MEDICATION, False
            ):
                return await self.async_step_dog_health()

            self._dogs.append(current_dog)
            self._current_dog_config = None
            return await self.async_step_add_another_dog()

        dog_weight_raw = current_dog.get(DOG_WEIGHT_FIELD)
        if isinstance(dog_weight_raw, int | float):
            dog_weight_value = float(dog_weight_raw)
        else:
            dog_weight_value = 20.0

        dog_size_raw = current_dog.get(DOG_SIZE_FIELD)
        dog_size = dog_size_raw if isinstance(dog_size_raw, str) else "medium"

        suggested_amount = self._calculate_suggested_food_amount(
            dog_weight_value, dog_size
        )

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
                    CONF_DAILY_FOOD_AMOUNT, default=int(suggested_amount)
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

        portion_info = f"Automatic portion calculation: {suggested_amount}g per day"

        return self.async_show_form(
            step_id="dog_feeding",
            data_schema=schema,
            description_placeholders=_build_dog_feeding_placeholders(
                dog_name=current_dog[DOG_NAME_FIELD],
                dog_weight=str(dog_weight_value),
                suggested_amount=str(suggested_amount),
                portion_info=portion_info,
            ),
        )

    async def async_step_dog_health(
        self, user_input: DogHealthStepInput | None = None
    ) -> ConfigFlowResult:
        """Configure comprehensive health settings including health-aware feeding.

        This step collects detailed health data for advanced portion calculation,
        body condition scoring, activity levels, and medical conditions.

        Args:
            user_input: Health configuration for the dog

        Returns:
            Configuration flow result for next step
        """
        current_dog = self._current_dog_config
        if current_dog is None:
            _LOGGER.error(
                "Health configuration step invoked without active dog; restarting add_dog"
            )
            return await self.async_step_add_dog()

        if user_input is not None:
            modules = ensure_dog_modules_config(current_dog)
            # Store comprehensive health configuration for this dog
            health_config: DogHealthConfig = {
                "vet_name": _coerce_str(user_input.get("vet_name")),
                "vet_phone": _coerce_str(user_input.get("vet_phone")),
                "weight_tracking": _coerce_bool(
                    user_input.get("weight_tracking"), default=True
                ),
                "ideal_weight": _coerce_optional_float(user_input.get("ideal_weight"))
                or _coerce_optional_float(current_dog.get(CONF_DOG_WEIGHT)),
                "body_condition_score": _coerce_int(
                    user_input.get("body_condition_score"), default=5
                ),
                "activity_level": _coerce_str(
                    user_input.get("activity_level"), default="moderate"
                ),
                "weight_goal": _coerce_str(
                    user_input.get("weight_goal"), default="maintain"
                ),
                "spayed_neutered": _coerce_bool(
                    user_input.get("spayed_neutered"), default=True
                ),
                "health_conditions": self._collect_health_conditions(user_input),
                "special_diet_requirements": self._collect_special_diet(user_input),
            }

            if last_visit := _coerce_optional_str(user_input.get("last_vet_visit")):
                health_config["last_vet_visit"] = last_visit
            if next_checkup := _coerce_optional_str(user_input.get("next_checkup")):
                health_config["next_checkup"] = next_checkup

            vaccinations = self._build_vaccination_records(user_input)
            if vaccinations:
                health_config["vaccinations"] = vaccinations

            if modules.get(MODULE_MEDICATION, False):
                medications = self._build_medication_entries(user_input)
                if medications:
                    health_config["medications"] = medications

            current_dog[DOG_HEALTH_CONFIG_FIELD] = health_config

            feeding_config = current_dog.get(DOG_FEEDING_CONFIG_FIELD)
            if isinstance(feeding_config, dict):
                feeding_config_typed = cast(DogFeedingConfig, feeding_config)

                dog_weight_update = _coerce_optional_float(
                    current_dog.get(DOG_WEIGHT_FIELD)
                )
                dog_age_update = _coerce_optional_int(current_dog.get(DOG_AGE_FIELD))
                dog_size_update_raw = current_dog.get(DOG_SIZE_FIELD)
                dog_size_update = (
                    dog_size_update_raw
                    if isinstance(dog_size_update_raw, str)
                    else "medium"
                )

                # Validate diet combinations and log results
                diet_validation: DietValidationResult = (
                    self._validate_diet_combinations(
                        health_config["special_diet_requirements"]
                    )
                )

                # Add health integration to feeding config
                feeding_config_typed.update(
                    {
                        "health_aware_portions": user_input.get(
                            "health_aware_portions", True
                        ),
                        "dog_weight": dog_weight_update,
                        "ideal_weight": health_config["ideal_weight"],
                        "age_months": (dog_age_update or 3) * 12,
                        "breed_size": dog_size_update,
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
                        current_dog[DOG_NAME_FIELD],
                        len(diet_validation["conflicts"]),
                        len(diet_validation["warnings"]),
                    )

            # Finalize dog configuration
            self._dogs.append(current_dog)
            return await self.async_step_add_another_dog()

        # Calculate suggestions based on dog characteristics
        dog_age_raw = current_dog.get(DOG_AGE_FIELD)
        dog_age = int(dog_age_raw) if isinstance(dog_age_raw, int | float) else 3

        dog_size_raw = current_dog.get(DOG_SIZE_FIELD)
        dog_size = dog_size_raw if isinstance(dog_size_raw, str) else "medium"

        dog_weight_raw = current_dog.get(DOG_WEIGHT_FIELD)
        dog_weight = (
            float(dog_weight_raw) if isinstance(dog_weight_raw, int | float) else 20.0
        )

        # Suggest ideal weight (typically 95-105% of current weight for healthy dogs)
        suggested_ideal_weight = round(dog_weight * 1.0, 1)

        # Suggest activity level based on age and size
        suggested_activity = self._suggest_activity_level(dog_age, dog_size)

        modules = ensure_dog_modules_config(current_dog)

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
        if modules.get(MODULE_MEDICATION, False):
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

        medication_enabled = "yes" if modules.get(MODULE_MEDICATION, False) else "no"
        health_diet_info = (
            "Select all special diet requirements that apply to optimize "
            "feeding calculations\n\n⚠️ Compatibility Info:\n"
            f"{diet_compatibility_info}"
        )

        return self.async_show_form(
            step_id="dog_health",
            data_schema=schema,
            description_placeholders=_build_dog_health_placeholders(
                dog_name=current_dog[DOG_NAME_FIELD],
                dog_age=str(dog_age),
                dog_weight=str(dog_weight),
                suggested_ideal_weight=str(suggested_ideal_weight),
                suggested_activity=suggested_activity,
                medication_enabled=medication_enabled,
                bcs_info="Body Condition Score: 1=Emaciated, 5=Ideal, 9=Obese",
                special_diet_count=str(len(SPECIAL_DIET_OPTIONS)),
                health_diet_info=health_diet_info,
            ),
        )

    async def _async_validate_dog_config(
        self, user_input: DogSetupStepInput
    ) -> DogValidationResult:
        """Validate dog configuration with rate limiting.

        Args:
            user_input: Dog configuration to validate

        Returns:
            Dictionary with validation results and any errors
        """
        errors: dict[str, str] = {}

        try:
            dog_id_raw = user_input.get(CONF_DOG_ID)
            dog_name_raw = user_input.get(CONF_DOG_NAME)

            if not isinstance(dog_id_raw, str) or not isinstance(dog_name_raw, str):
                return {"valid": False, "errors": {"base": "invalid_dog_data"}}

            dog_id = dog_id_raw.lower().strip().replace(" ", "_")
            dog_name = dog_name_raw.strip()

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
            result: DogValidationResult = {
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
        self, dog_id: str, dog_name: str, user_input: DogSetupStepInput
    ) -> str:
        weight = user_input.get(CONF_DOG_WEIGHT)
        age_val = user_input.get(CONF_DOG_AGE)
        size = user_input.get(CONF_DOG_SIZE) or "none"
        breed = user_input.get(CONF_DOG_BREED) or "none"
        weight_token = str(weight) if weight is not None else "none"
        age_token = str(age_val) if age_val is not None else "none"
        return f"{dog_id}_{dog_name}_{weight_token}_{age_token}_{size}_{breed}"

    def _get_cached_validation(self, cache_key: str) -> DogValidationResult | None:
        cached: DogValidationCacheEntry | None = self._validation_cache.get(cache_key)
        if cached is None:
            return None

        if cached["cached_at"] <= asyncio.get_running_loop().time() - 5:
            return None

        cached_result = cached["result"]
        if isinstance(cached_result, Mapping):
            valid = cached_result.get("valid")
            errors = cached_result.get("errors")
            if isinstance(valid, bool) and isinstance(errors, dict):
                return cast(DogValidationResult, cached_result)
        return None

    def _update_validation_cache(
        self, cache_key: str, result: DogValidationResult
    ) -> None:
        cache_entry: DogValidationCacheEntry = {
            "result": cast(DogSetupStepInput | DogValidationResult | None, result),
            "cached_at": asyncio.get_running_loop().time(),
        }
        self._validation_cache[cache_key] = cache_entry

    def _validate_dog_id(self, dog_id: str) -> str | None:
        if not DOG_ID_PATTERN.match(dog_id):
            return "invalid_dog_id_format"
        if any(dog[DOG_ID_FIELD] == dog_id for dog in self._dogs):
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
            self._lower_dog_names = {dog[DOG_NAME_FIELD].lower() for dog in self._dogs}
        if dog_name.lower() in self._lower_dog_names:
            return "dog_name_already_exists"
        return None

    def _validate_weight(self, user_input: DogSetupStepInput) -> str | None:
        weight_value = _coerce_optional_float(user_input.get(CONF_DOG_WEIGHT))
        size_raw = user_input.get(CONF_DOG_SIZE)
        size = size_raw if isinstance(size_raw, str) and size_raw else "medium"

        if weight_value is None:
            return None

        if weight_value < MIN_DOG_WEIGHT or weight_value > MAX_DOG_WEIGHT:
            return "weight_out_of_range"
        if not self._is_weight_size_compatible(weight_value, size):
            return "weight_size_mismatch"
        return None

    def _validate_age(self, user_input: DogSetupStepInput) -> str | None:
        age_value = _coerce_optional_int(user_input.get(CONF_DOG_AGE))
        if age_value is None:
            return None

        if age_value < MIN_DOG_AGE or age_value > MAX_DOG_AGE:
            return "age_out_of_range"
        return None

    def _validate_breed(self, user_input: DogSetupStepInput) -> str | None:
        breed_raw = user_input.get(CONF_DOG_BREED)
        breed = breed_raw.strip() if isinstance(breed_raw, str) else ""
        if breed and len(breed) > 100:
            return "breed_name_too_long"
        return None

    async def _create_dog_config(self, user_input: DogSetupStepInput) -> DogConfigData:
        """Create a complete dog configuration with intelligent defaults.

        Builds a comprehensive dog configuration with sensible defaults
        based on dog characteristics and best practices.

        Args:
            user_input: User-provided dog data

        Returns:
            Complete dog configuration dictionary
        """
        dog_id_raw = user_input[DOG_ID_FIELD]
        dog_id = dog_id_raw.lower().strip().replace(" ", "_")

        dog_name_raw = user_input[DOG_NAME_FIELD]
        dog_name = dog_name_raw.strip()

        config: DogConfigData = {
            DOG_ID_FIELD: dog_id,
            DOG_NAME_FIELD: dog_name,
            DOG_MODULES_FIELD: cast(DogModulesConfig, {}),
        }

        breed_value_raw = user_input.get(CONF_DOG_BREED)
        if isinstance(breed_value_raw, str) and breed_value_raw.strip():
            config[DOG_BREED_FIELD] = breed_value_raw.strip()
        else:
            config[DOG_BREED_FIELD] = "Mixed Breed"

        dog_age_value = user_input.get(CONF_DOG_AGE)
        if isinstance(dog_age_value, int | float):
            config[DOG_AGE_FIELD] = int(dog_age_value)

        dog_weight_value = user_input.get(CONF_DOG_WEIGHT)
        if isinstance(dog_weight_value, int | float):
            config[DOG_WEIGHT_FIELD] = float(dog_weight_value)

        dog_size_value = user_input.get(CONF_DOG_SIZE)
        if isinstance(dog_size_value, str):
            config[DOG_SIZE_FIELD] = dog_size_value

        return config

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

    async def _create_enhanced_dog_schema(
        self,
        user_input: DogSetupStepInput | JSONMapping | None,
        suggested_id: str,
        suggested_breed: str,
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
        current_values: JSONMapping
        if isinstance(user_input, Mapping):
            current_values = cast(JSONMapping, user_input)
        else:
            current_values = cast(JSONMapping, MappingProxyType({}))

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
        self, user_input: AddAnotherDogInput | None = None
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
            if bool(user_input.get("add_another", False)):
                # Clear cache and errors for fresh start
                self._validation_cache.clear()
                self._errors.clear()
                self._current_dog_config = None
                return await self.async_step_add_dog()
            # All dogs configured, continue to global settings if needed
            return await self.async_step_configure_modules()

        # Check if we've reached the limit
        at_limit = len(self._dogs) >= MAX_DOGS_PER_ENTRY

        schema = vol.Schema(
            {
                vol.Required("add_another", default=False): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="add_another_dog",
            data_schema=schema,
            description_placeholders=_build_add_another_summary_placeholders(
                dogs_list=self._format_dogs_list(),
                dog_count=str(len(self._dogs)),
                max_dogs=MAX_DOGS_PER_ENTRY,
                remaining_spots=MAX_DOGS_PER_ENTRY - len(self._dogs),
                at_limit="true" if at_limit else "false",
            ),
        )

    def _build_vaccination_records(
        self, user_input: DogHealthStepInput
    ) -> dict[str, DogVaccinationRecord]:
        """Build vaccination records from user form input."""

        def _build_record(date_key: str, next_key: str) -> DogVaccinationRecord | None:
            date_value = _coerce_optional_str(user_input.get(date_key))
            next_value = _coerce_optional_str(user_input.get(next_key))
            if date_value is None and next_value is None:
                return None

            record: DogVaccinationRecord = {}
            if date_value is not None:
                record["date"] = date_value
            if next_value is not None:
                record["next_due"] = next_value
            return record

        vaccinations: dict[str, DogVaccinationRecord] = {}

        if record := _build_record("rabies_vaccination", "rabies_next"):
            vaccinations["rabies"] = record
        if record := _build_record("dhpp_vaccination", "dhpp_next"):
            vaccinations["dhpp"] = record
        if record := _build_record("bordetella_vaccination", "bordetella_next"):
            vaccinations["bordetella"] = record

        return vaccinations

    def _build_medication_entries(
        self, user_input: DogHealthStepInput
    ) -> list[DogMedicationEntry]:
        """Construct typed medication entries from the configuration form."""

        medications: list[DogMedicationEntry] = []
        for slot in ("1", "2"):
            name = _coerce_optional_str(user_input.get(f"medication_{slot}_name"))
            if name is None:
                continue

            entry: DogMedicationEntry = {"name": name}

            if dosage := _coerce_optional_str(
                user_input.get(f"medication_{slot}_dosage")
            ):
                entry["dosage"] = dosage

            frequency = _coerce_optional_str(
                user_input.get(f"medication_{slot}_frequency")
            )
            if frequency is not None:
                entry["frequency"] = frequency or "daily"

            time_value = _coerce_optional_str(user_input.get(f"medication_{slot}_time"))
            entry["time"] = time_value or ("08:00:00" if slot == "1" else "20:00:00")

            if notes := _coerce_optional_str(
                user_input.get(f"medication_{slot}_notes")
            ):
                entry["notes"] = notes

            entry["with_meals"] = _coerce_bool(
                user_input.get(f"medication_{slot}_with_meals"), default=False
            )

            medications.append(entry)

        return medications

    def _collect_health_conditions(self, user_input: DogHealthStepInput) -> list[str]:
        """Collect health conditions from user input for feeding calculations."""

        conditions: list[str] = []

        condition_mapping = {
            "has_diabetes": "diabetes",
            "has_kidney_disease": "kidney_disease",
            "has_heart_disease": "heart_disease",
            "has_arthritis": "arthritis",
            "has_allergies": "allergies",
            "has_digestive_issues": "digestive_issues",
        }

        for field, condition in condition_mapping.items():
            if _coerce_bool(user_input.get(field), default=False):
                conditions.append(condition)

        other_conditions_raw = _coerce_optional_str(
            user_input.get("other_health_conditions")
        )
        if other_conditions_raw:
            additional = [
                cond.strip().lower().replace(" ", "_")
                for cond in other_conditions_raw.split(",")
                if cond.strip()
            ]
            conditions.extend(additional)

        return conditions

    def _collect_special_diet(self, user_input: DogHealthStepInput) -> list[str]:
        """Collect special diet requirements from user input.

        Uses SPECIAL_DIET_OPTIONS from const.py to ensure consistency
        across the integration and capture all 14 diet options.

        Returns a list of special diet requirements matching
        ``const.SPECIAL_DIET_OPTIONS``.
        """
        diet_requirements: list[str] = [
            diet_option
            for diet_option in SPECIAL_DIET_OPTIONS
            if _coerce_bool(user_input.get(diet_option), default=False)
        ]

        # Validate diet combinations for conflicts
        validation_result: DietValidationResult = self._validate_diet_combinations(
            diet_requirements
        )
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
    ) -> DietValidationResult:
        """Validate special diet combinations for conflicts and incompatibilities.

        Args:
            diet_requirements: List of selected diet requirements

        Returns:
            Dictionary with validation results and conflict information
        """
        conflicts: list[DietCompatibilityIssue] = []
        warnings: list[DietCompatibilityIssue] = []

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
            warnings.append(
                {
                    "type": "low_fat_activity_warning",
                    "diets": ["low_fat", "high_activity"],
                    "message": "Low fat diets may need veterinary review for highly active dogs",
                }
            )

        return {
            "valid": len(conflicts) == 0,
            "conflicts": conflicts,
            "warnings": warnings,
            "total_diets": len(diet_requirements),
            "recommended_vet_consultation": bool(warnings or conflicts),
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
        if dog_age >= 10:
            return "low"  # Senior dogs generally less active
        if dog_age >= 7:
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
        self, user_input: ModuleConfigurationStepInput | None = None
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
            self._global_modules = ModuleConfigurationSnapshot(
                enable_notifications=bool(user_input.get("enable_notifications", True)),
                enable_dashboard=bool(user_input.get("enable_dashboard", True)),
                performance_mode=normalize_performance_mode(
                    user_input.get("performance_mode"), fallback="balanced"
                ),
                data_retention_days=int(user_input.get("data_retention_days", 90)),
                auto_backup=bool(user_input.get("auto_backup", False)),
                debug_logging=bool(user_input.get("debug_logging", False)),
            )

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
            description_placeholders=_build_module_setup_placeholders(
                total_dogs=str(total_dogs),
                gps_dogs=str(has_gps_dogs),
                health_dogs=str(has_health_tracking),
                suggested_performance=suggested_performance,
                complexity_info=self._get_setup_complexity_info(),
                next_step_info=(
                    "Next: Entity profile selection for performance optimization"
                ),
            ),
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
        if total_dogs <= 2 and total_modules <= 10:
            return "Standard setup - balanced performance recommended"
        return "Complex setup - full performance mode recommended"
