"""Configuration flow for Paw Control integration.

This module provides a comprehensive configuration flow that meets Home Assistant's
Platinum quality standards. It includes full UI-based setup, extensive validation,
multi-step configuration, and a complete options flow for post-setup configuration.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import (
    ACTIVITY_LEVELS,
    CONF_DASHBOARD_MODE,
    CONF_DOGS,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_FEEDING_TIMES,
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_SOURCE,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_HEALTH_TRACKING,
    CONF_MODULES,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT_MIN,
    CONF_RESET_TIME,
    CONF_SOURCES,
    DASHBOARD_MODES,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_GPS_UPDATE_INTERVAL,
    DEFAULT_REMINDER_REPEAT_MIN,
    DEFAULT_RESET_TIME,
    DOG_SIZES,
    DOMAIN,
    FOOD_TYPES,
    GPS_SOURCES,
    HEALTH_STATUS_OPTIONS,
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
    MOOD_OPTIONS,
    PERFORMANCE_MODES,
)

_LOGGER = logging.getLogger(__name__)

# Configuration schemas for validation
INTEGRATION_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default="Paw Control"): vol.All(
        cv.string, vol.Length(min=1, max=50)
    ),
})

DOG_BASE_SCHEMA = vol.Schema({
    vol.Required(CONF_DOG_ID): vol.All(
        cv.string, 
        vol.Length(min=2, max=30),
        vol.Match(r"^[a-z0-9_]+$", msg="Only lowercase letters, numbers, and underscores allowed")
    ),
    vol.Required(CONF_DOG_NAME): vol.All(
        cv.string, 
        vol.Length(min=MIN_DOG_NAME_LENGTH, max=MAX_DOG_NAME_LENGTH)
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
})


class PawControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle configuration flow for Paw Control integration.
    
    This config flow provides a comprehensive setup experience that guides
    users through configuring their dogs and initial settings. It includes
    extensive validation, helpful error messages, and a user-friendly interface.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the configuration flow.
        
        Sets up internal state for tracking the configuration process
        across multiple steps.
        """
        self._dogs: List[Dict[str, Any]] = []
        self._current_dog_index = 0
        self._integration_name = "Paw Control"
        self._errors: Dict[str, str] = {}

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step.
        
        This is the entry point for the configuration flow. It collects
        basic integration information and validates uniqueness.
        
        Args:
            user_input: User-provided configuration data
            
        Returns:
            Configuration flow result for next step or completion
        """
        errors: Dict[str, str] = {}

        if user_input is not None:
            integration_name = user_input[CONF_NAME].strip()
            
            # Validate integration name uniqueness
            await self.async_set_unique_id(integration_name.lower().replace(" ", "_"))
            self._abort_if_unique_id_configured()
            
            self._integration_name = integration_name
            return await self.async_step_add_dog()

        return self.async_show_form(
            step_id="user",
            data_schema=INTEGRATION_SCHEMA,
            errors=errors,
            description_placeholders={
                "integration_name": "Paw Control",
                "docs_url": "https://github.com/BigDaddy1990/pawcontrol",
                "version": "1.0.0",
            },
        )

    async def async_step_add_dog(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Handle adding a dog to the configuration.
        
        This step allows users to add individual dogs with their basic
        information. It includes comprehensive validation and helpful
        suggestions for dog IDs.
        
        Args:
            user_input: User-provided dog configuration data
            
        Returns:
            Configuration flow result for next step
        """
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Validate and process dog configuration
            validation_result = await self._async_validate_dog_config(user_input)
            
            if validation_result["valid"]:
                # Create dog configuration with default modules
                dog_config = self._create_dog_config(user_input)
                self._dogs.append(dog_config)
                
                _LOGGER.debug("Added dog: %s (%s)", dog_config[CONF_DOG_NAME], dog_config[CONF_DOG_ID])
                return await self.async_step_add_another_dog()
            else:
                errors = validation_result["errors"]

        # Generate suggested dog ID from name
        suggested_id = self._generate_dog_id_suggestion(user_input)

        # Create dynamic schema with current values
        schema = self._create_dog_schema(user_input, suggested_id)

        return self.async_show_form(
            step_id="add_dog",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "dog_count": len(self._dogs),
                "current_dogs": self._format_dogs_list(),
            },
        )

    async def _async_validate_dog_config(
        self, user_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate dog configuration data.
        
        Performs comprehensive validation of dog data including uniqueness
        checks, data type validation, and business rule validation.
        
        Args:
            user_input: Dog configuration to validate
            
        Returns:
            Dictionary with validation results and any errors
        """
        errors: Dict[str, str] = {}
        
        try:
            dog_id = user_input[CONF_DOG_ID].lower().strip().replace(" ", "_")
            dog_name = user_input[CONF_DOG_NAME].strip()
            
            # Validate dog ID uniqueness
            if any(dog[CONF_DOG_ID] == dog_id for dog in self._dogs):
                errors[CONF_DOG_ID] = "dog_id_already_exists"
            
            # Validate dog ID format
            if not dog_id or not dog_id.replace("_", "").replace("-", "").isalnum():
                errors[CONF_DOG_ID] = "invalid_dog_id_format"
            
            # Validate dog name
            if not dog_name:
                errors[CONF_DOG_NAME] = "dog_name_required"
            elif len(dog_name) < MIN_DOG_NAME_LENGTH:
                errors[CONF_DOG_NAME] = "dog_name_too_short"
            elif len(dog_name) > MAX_DOG_NAME_LENGTH:
                errors[CONF_DOG_NAME] = "dog_name_too_long"
            
            # Validate weight if provided
            weight = user_input.get(CONF_DOG_WEIGHT)
            if weight is not None:
                try:
                    weight_float = float(weight)
                    if weight_float < MIN_DOG_WEIGHT or weight_float > MAX_DOG_WEIGHT:
                        errors[CONF_DOG_WEIGHT] = "weight_out_of_range"
                except (ValueError, TypeError):
                    errors[CONF_DOG_WEIGHT] = "invalid_weight_format"
            
            # Validate age if provided
            age = user_input.get(CONF_DOG_AGE)
            if age is not None:
                try:
                    age_int = int(age)
                    if age_int < MIN_DOG_AGE or age_int > MAX_DOG_AGE:
                        errors[CONF_DOG_AGE] = "age_out_of_range"
                except (ValueError, TypeError):
                    errors[CONF_DOG_AGE] = "invalid_age_format"
            
        except Exception as err:
            _LOGGER.error("Error validating dog configuration: %s", err)
            errors["base"] = "validation_error"
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def _create_dog_config(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Create a complete dog configuration from user input.
        
        Builds a comprehensive dog configuration with sensible defaults
        for modules and advanced settings.
        
        Args:
            user_input: User-provided dog data
            
        Returns:
            Complete dog configuration dictionary
        """
        dog_id = user_input[CONF_DOG_ID].lower().strip().replace(" ", "_")
        
        return {
            CONF_DOG_ID: dog_id,
            CONF_DOG_NAME: user_input[CONF_DOG_NAME].strip(),
            CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, "").strip(),
            CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 3),
            CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
            CONF_DOG_SIZE: user_input.get(CONF_DOG_SIZE, "medium"),
            CONF_MODULES: {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_GPS: False,  # Disabled by default (requires setup)
                MODULE_HEALTH: True,
                MODULE_NOTIFICATIONS: True,
                MODULE_DASHBOARD: True,
                MODULE_VISITOR: False,  # Advanced feature
            },
        }

    def _generate_dog_id_suggestion(
        self, user_input: Optional[Dict[str, Any]]
    ) -> str:
        """Generate a suggested dog ID from the dog name.
        
        Creates a URL-safe, unique identifier based on the dog's name
        while avoiding conflicts with existing dogs.
        
        Args:
            user_input: Current user input (may be None)
            
        Returns:
            Suggested dog ID string
        """
        if not user_input or not user_input.get(CONF_DOG_NAME):
            return ""
        
        # Convert name to safe ID format
        dog_name = user_input[CONF_DOG_NAME].strip()
        base_id = dog_name.lower().replace(" ", "_").replace("-", "_")
        
        # Remove special characters
        safe_id = "".join(c for c in base_id if c.isalnum() or c == "_")
        
        # Ensure uniqueness
        if not any(dog[CONF_DOG_ID] == safe_id for dog in self._dogs):
            return safe_id
        
        # Add number suffix if needed
        counter = 2
        while any(dog[CONF_DOG_ID] == f"{safe_id}_{counter}" for dog in self._dogs):
            counter += 1
        
        return f"{safe_id}_{counter}"

    def _create_dog_schema(
        self, 
        user_input: Optional[Dict[str, Any]], 
        suggested_id: str
    ) -> vol.Schema:
        """Create a dynamic schema for dog configuration.
        
        Builds a form schema with current values and helpful defaults
        for an improved user experience.
        
        Args:
            user_input: Current user input values
            suggested_id: Suggested dog ID
            
        Returns:
            Voluptuous schema for the form
        """
        current_values = user_input or {}
        
        return vol.Schema({
            vol.Required(
                CONF_DOG_ID, 
                default=current_values.get(CONF_DOG_ID, suggested_id)
            ): cv.string,
            vol.Required(
                CONF_DOG_NAME, 
                default=current_values.get(CONF_DOG_NAME, "")
            ): cv.string,
            vol.Optional(
                CONF_DOG_BREED, 
                default=current_values.get(CONF_DOG_BREED, "")
            ): cv.string,
            vol.Optional(
                CONF_DOG_AGE, 
                default=current_values.get(CONF_DOG_AGE, 3)
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
                CONF_DOG_WEIGHT, 
                default=current_values.get(CONF_DOG_WEIGHT, 20.0)
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
                CONF_DOG_SIZE, 
                default=current_values.get(CONF_DOG_SIZE, "medium")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": "toy", "label": "Toy (1-6kg)"},
                        {"value": "small", "label": "Small (6-12kg)"},
                        {"value": "medium", "label": "Medium (12-27kg)"},
                        {"value": "large", "label": "Large (27-45kg)"},
                        {"value": "giant", "label": "Giant (45-90kg)"},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })

    def _format_dogs_list(self) -> str:
        """Format the current dogs list for display.
        
        Creates a readable list of configured dogs for user feedback.
        
        Returns:
            Formatted string listing all configured dogs
        """
        if not self._dogs:
            return "No dogs configured yet"
        
        dogs_list = []
        for dog in self._dogs:
            dogs_list.append(
                f"• {dog[CONF_DOG_NAME]} ({dog[CONF_DOG_ID]}) - "
                f"{dog[CONF_DOG_SIZE]} {dog.get(CONF_DOG_BREED, 'mixed breed') or 'mixed breed'}"
            )
        
        return "\n".join(dogs_list)

    async def async_step_add_another_dog(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Ask if the user wants to add another dog.
        
        This step allows users to configure multiple dogs in a single
        setup process while providing clear feedback about already
        configured dogs.
        
        Args:
            user_input: User choice about adding another dog
            
        Returns:
            Configuration flow result for next step or dog addition
        """
        if user_input is not None:
            if user_input.get("add_another", False):
                # Clear any previous errors before adding another dog
                self._errors = {}
                return await self.async_step_add_dog()
            else:
                return await self.async_step_configure_modules()

        schema = vol.Schema({
            vol.Required("add_another", default=False): bool,
        })

        return self.async_show_form(
            step_id="add_another_dog",
            data_schema=schema,
            description_placeholders={
                "dogs_list": self._format_dogs_list(),
                "dog_count": len(self._dogs),
                "max_dogs": 10,  # Reasonable limit
            },
        )

    async def async_step_configure_modules(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Configure modules for the first dog.
        
        This step allows users to enable/disable specific modules
        for their dogs, providing customization of functionality.
        
        Args:
            user_input: Module configuration choices
            
        Returns:
            Configuration flow result for next step or completion
        """
        if user_input is not None:
            # Apply module configuration to the first dog
            if self._dogs:
                self._dogs[0][CONF_MODULES].update({
                    MODULE_GPS: user_input.get("enable_gps", False),
                    MODULE_HEALTH: user_input.get("enable_health", True),
                    MODULE_VISITOR: user_input.get("enable_visitor_mode", False),
                })
            
            return await self.async_step_final_setup()

        # Only show this step if we have dogs configured
        if not self._dogs:
            return await self.async_step_final_setup()

        first_dog = self._dogs[0]
        modules = first_dog[CONF_MODULES]

        schema = vol.Schema({
            vol.Optional(
                "enable_gps", 
                default=modules.get(MODULE_GPS, False)
            ): bool,
            vol.Optional(
                "enable_health", 
                default=modules.get(MODULE_HEALTH, True)
            ): bool,
            vol.Optional(
                "enable_visitor_mode", 
                default=modules.get(MODULE_VISITOR, False)
            ): bool,
        })

        return self.async_show_form(
            step_id="configure_modules",
            data_schema=schema,
            description_placeholders={
                "dog_name": first_dog[CONF_DOG_NAME],
                "dog_count": len(self._dogs),
            },
        )

    async def async_step_final_setup(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Complete the configuration setup.
        
        This final step creates the config entry with all collected
        data and sets up default options for the integration.
        
        Args:
            user_input: Final confirmation from user
            
        Returns:
            Configuration entry creation result
        """
        if user_input is not None or not user_input:
            # Validate that we have at least one dog
            if not self._dogs:
                _LOGGER.error("No dogs configured during setup")
                return self.async_abort(reason="no_dogs_configured")
            
            # Create the configuration data
            config_data = {
                CONF_NAME: self._integration_name,
                CONF_DOGS: self._dogs,
            }
            
            # Create default options
            options_data = {
                CONF_RESET_TIME: DEFAULT_RESET_TIME,
                CONF_NOTIFICATIONS: {
                    CONF_QUIET_HOURS: False,
                    CONF_QUIET_START: "22:00:00",
                    CONF_QUIET_END: "07:00:00",
                    CONF_REMINDER_REPEAT_MIN: DEFAULT_REMINDER_REPEAT_MIN,
                },
                CONF_DASHBOARD_MODE: "full",
                "performance_mode": "balanced",
                "data_retention_days": 90,
                "auto_backup": False,
            }

            _LOGGER.info(
                "Creating Paw Control config entry with %d dogs",
                len(self._dogs)
            )

            return self.async_create_entry(
                title=self._integration_name,
                data=config_data,
                options=options_data,
            )

        # Show setup summary
        setup_summary = []
        for dog in self._dogs:
            enabled_modules = [
                module.replace("_", " ").title()
                for module, enabled in dog[CONF_MODULES].items() 
                if enabled
            ]
            setup_summary.append(
                f"• {dog[CONF_DOG_NAME]} ({dog[CONF_DOG_SIZE]} {dog.get(CONF_DOG_BREED, 'mixed breed')})\n"
                f"  Modules: {', '.join(enabled_modules)}"
            )

        return self.async_show_form(
            step_id="final_setup",
            data_schema=vol.Schema({}),
            description_placeholders={
                "setup_summary": "\n".join(setup_summary),
                "total_dogs": len(self._dogs),
                "integration_name": self._integration_name,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow for post-setup configuration.
        
        Args:
            config_entry: The config entry to create options flow for
            
        Returns:
            Options flow instance for advanced configuration
        """
        return PawControlOptionsFlow(config_entry)


class PawControlOptionsFlow(OptionsFlow):
    """Handle options flow for Paw Control integration.
    
    This comprehensive options flow allows users to modify all aspects
    of their Paw Control configuration after initial setup. It provides
    organized menu-driven navigation and extensive customization options.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow.
        
        Args:
            config_entry: Configuration entry to modify
        """
        self.config_entry = config_entry
        self._current_dog: Optional[Dict[str, Any]] = None
        self._dogs: List[Dict[str, Any]] = config_entry.data.get(CONF_DOGS, [])

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Show the main options menu.
        
        Provides organized access to all configuration categories
        with clear descriptions and easy navigation.
        
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
            ],
        )

    async def async_step_manage_dogs(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Manage dog configurations.
        
        Provides comprehensive dog management including adding, editing,
        removing dogs, and configuring their individual modules.
        
        Args:
            user_input: User action selection
            
        Returns:
            Configuration flow result for selected action
        """
        if user_input is not None:
            action = user_input.get("action")
            
            if action == "add_dog":
                return await self.async_step_add_dog()
            elif action == "edit_dog":
                return await self.async_step_select_dog_to_edit()
            elif action == "remove_dog":
                return await self.async_step_select_dog_to_remove()
            elif action == "configure_modules":
                return await self.async_step_select_dog_for_modules()
            else:
                return await self.async_step_init()

        schema = vol.Schema({
            vol.Required("action"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": "add_dog", "label": "Add new dog"},
                        {"value": "edit_dog", "label": "Edit existing dog"},
                        {"value": "configure_modules", "label": "Configure dog modules"},
                        {"value": "remove_dog", "label": "Remove dog"},
                        {"value": "back", "label": "Back to main menu"},
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        })

        # Create detailed dogs information
        dogs_info = []
        for dog in self._dogs:
            enabled_modules = [
                module.replace("_", " ").title()
                for module, enabled in dog.get(CONF_MODULES, {}).items()
                if enabled
            ]
            
            dogs_info.append(
                f"• {dog[CONF_DOG_NAME]} ({dog[CONF_DOG_ID]})\n"
                f"  {dog.get(CONF_DOG_SIZE, 'unknown')} {dog.get(CONF_DOG_BREED, 'mixed breed')}, "
                f"{dog.get(CONF_DOG_AGE, 'unknown')} years, {dog.get(CONF_DOG_WEIGHT, 'unknown')}kg\n"
                f"  Modules: {', '.join(enabled_modules) if enabled_modules else 'None'}"
            )

        return self.async_show_form(
            step_id="manage_dogs",
            data_schema=schema,
            description_placeholders={
                "dogs_info": "\n\n".join(dogs_info) if dogs_info else "No dogs configured",
                "dog_count": len(self._dogs),
            },
        )

    async def async_step_gps_settings(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Configure GPS and location tracking settings.
        
        Provides comprehensive GPS configuration including update intervals,
        accuracy filters, geofencing, and tracking optimization.
        
        Args:
            user_input: GPS configuration data
            
        Returns:
            Configuration flow result
        """
        if user_input is not None:
            # Update GPS configuration
            new_options = self.config_entry.options.copy()
            new_options["gps"] = {
                CONF_GPS_UPDATE_INTERVAL: user_input[CONF_GPS_UPDATE_INTERVAL],
                CONF_GPS_ACCURACY_FILTER: user_input[CONF_GPS_ACCURACY_FILTER],
                CONF_GPS_DISTANCE_FILTER: user_input[CONF_GPS_DISTANCE_FILTER],
                "auto_walk_detection": user_input.get("auto_walk_detection", False),
                "geofencing_enabled": user_input.get("geofencing_enabled", False),
                "route_recording": user_input.get("route_recording", True),
                "battery_optimization": user_input.get("battery_optimization", False),
            }

            return self.async_create_entry(title="", data=new_options)

        current_gps = self.config_entry.options.get("gps", {})

        schema = vol.Schema({
            vol.Required(
                CONF_GPS_UPDATE_INTERVAL,
                default=current_gps.get(CONF_GPS_UPDATE_INTERVAL, DEFAULT_GPS_UPDATE_INTERVAL)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=30, 
                    max=600, 
                    step=30, 
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="seconds",
                )
            ),
            vol.Required(
                CONF_GPS_ACCURACY_FILTER,
                default=current_gps.get(CONF_GPS_ACCURACY_FILTER, DEFAULT_GPS_ACCURACY_FILTER)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5, 
                    max=500, 
                    step=5, 
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="meters",
                )
            ),
            vol.Required(
                CONF_GPS_DISTANCE_FILTER,
                default=current_gps.get(CONF_GPS_DISTANCE_FILTER, DEFAULT_GPS_DISTANCE_FILTER)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, 
                    max=100, 
                    step=1, 
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="meters",
                )
            ),
            vol.Optional(
                "auto_walk_detection",
                default=current_gps.get("auto_walk_detection", False)
            ): bool,
            vol.Optional(
                "geofencing_enabled",
                default=current_gps.get("geofencing_enabled", False)
            ): bool,
            vol.Optional(
                "route_recording",
                default=current_gps.get("route_recording", True)
            ): bool,
            vol.Optional(
                "battery_optimization",
                default=current_gps.get("battery_optimization", False)
            ): bool,
        })

        return self.async_show_form(
            step_id="gps_settings",
            data_schema=schema,
            description_placeholders={
                "gps_dogs": self._count_gps_enabled_dogs(),
            },
        )

    async def async_step_notifications(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Configure notification settings.
        
        Provides comprehensive notification configuration including quiet hours,
        priority levels, channels, and notification preferences.
        
        Args:
            user_input: Notification configuration data
            
        Returns:
            Configuration flow result
        """
        if user_input is not None:
            new_options = self.config_entry.options.copy()
            new_options[CONF_NOTIFICATIONS] = {
                CONF_QUIET_HOURS: user_input.get(CONF_QUIET_HOURS, False),
                CONF_QUIET_START: user_input.get(CONF_QUIET_START, "22:00:00"),
                CONF_QUIET_END: user_input.get(CONF_QUIET_END, "07:00:00"),
                CONF_REMINDER_REPEAT_MIN: user_input.get(CONF_REMINDER_REPEAT_MIN, DEFAULT_REMINDER_REPEAT_MIN),
                "priority_notifications": user_input.get("priority_notifications", True),
                "summary_notifications": user_input.get("summary_notifications", False),
                "mobile_notifications": user_input.get("mobile_notifications", True),
                "persistent_notifications": user_input.get("persistent_notifications", True),
            }

            return self.async_create_entry(title="", data=new_options)

        current_notifications = self.config_entry.options.get(CONF_NOTIFICATIONS, {})

        schema = vol.Schema({
            vol.Optional(
                CONF_QUIET_HOURS,
                default=current_notifications.get(CONF_QUIET_HOURS, False)
            ): bool,
            vol.Optional(
                CONF_QUIET_START,
                default=current_notifications.get(CONF_QUIET_START, "22:00:00")
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_QUIET_END,
                default=current_notifications.get(CONF_QUIET_END, "07:00:00")
            ): selector.TimeSelector(),
            vol.Required(
                CONF_REMINDER_REPEAT_MIN,
                default=current_notifications.get(CONF_REMINDER_REPEAT_MIN, DEFAULT_REMINDER_REPEAT_MIN)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5, 
                    max=120, 
                    step=5, 
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="minutes",
                )
            ),
            vol.Optional(
                "priority_notifications",
                default=current_notifications.get("priority_notifications", True)
            ): bool,
            vol.Optional(
                "summary_notifications",
                default=current_notifications.get("summary_notifications", False)
            ): bool,
            vol.Optional(
                "mobile_notifications",
                default=current_notifications.get("mobile_notifications", True)
            ): bool,
            vol.Optional(
                "persistent_notifications",
                default=current_notifications.get("persistent_notifications", True)
            ): bool,
        })

        return self.async_show_form(
            step_id="notifications",
            data_schema=schema,
        )

    async def async_step_system_settings(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Configure system-wide settings.
        
        Provides configuration for system-level settings including
        performance modes, data retention, backup options, and reset timing.
        
        Args:
            user_input: System configuration data
            
        Returns:
            Configuration flow result
        """
        if user_input is not None:
            new_options = self.config_entry.options.copy()
            new_options.update({
                CONF_RESET_TIME: user_input.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
                "performance_mode": user_input.get("performance_mode", "balanced"),
                "data_retention_days": user_input.get("data_retention_days", 90),
                "auto_backup": user_input.get("auto_backup", False),
                "debug_logging": user_input.get("debug_logging", False),
            })

            return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema({
            vol.Required(
                CONF_RESET_TIME,
                default=self.config_entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)
            ): selector.TimeSelector(),
            vol.Required(
                "performance_mode",
                default=self.config_entry.options.get("performance_mode", "balanced")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": "minimal", "label": "Minimal (Low CPU usage)"},
                        {"value": "balanced", "label": "Balanced (Recommended)"},
                        {"value": "performance", "label": "Performance (High responsiveness)"},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                "data_retention_days",
                default=self.config_entry.options.get("data_retention_days", 90)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=7, 
                    max=365, 
                    step=1, 
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="days",
                )
            ),
            vol.Optional(
                "auto_backup",
                default=self.config_entry.options.get("auto_backup", False)
            ): bool,
            vol.Optional(
                "debug_logging",
                default=self.config_entry.options.get("debug_logging", False)
            ): bool,
        })

        return self.async_show_form(
            step_id="system_settings",
            data_schema=schema,
            description_placeholders={
                "total_entities": self._count_total_entities(),
                "storage_usage": "Estimated based on retention period",
            },
        )

    def _count_gps_enabled_dogs(self) -> str:
        """Count dogs with GPS enabled.
        
        Returns:
            Formatted string describing GPS-enabled dogs
        """
        gps_dogs = [
            dog[CONF_DOG_NAME] 
            for dog in self._dogs 
            if dog.get(CONF_MODULES, {}).get(MODULE_GPS, False)
        ]
        
        if not gps_dogs:
            return "No dogs have GPS enabled"
        
        return f"GPS enabled for: {', '.join(gps_dogs)}"

    def _count_total_entities(self) -> str:
        """Count total entities that will be created.
        
        Returns:
            Formatted string describing entity count
        """
        entity_count = 0
        for dog in self._dogs:
            modules = dog.get(CONF_MODULES, {})
            # Base entities: 2
            entity_count += 2
            # Module-specific entities
            if modules.get(MODULE_FEEDING): entity_count += 7
            if modules.get(MODULE_WALK): entity_count += 6
            if modules.get(MODULE_GPS): entity_count += 8
            if modules.get(MODULE_HEALTH): entity_count += 6
            
        return f"Approximately {entity_count} entities for {len(self._dogs)} dogs"

    # Additional helper methods for the options flow would continue here...
    # This includes steps for adding/editing/removing dogs, configuring
    # individual modules, and other advanced settings.
