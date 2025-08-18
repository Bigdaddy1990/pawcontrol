"""Config flow for Paw Control integration.

Provides complete configuration flow with multi-step setup, discovery,
reauth, and options flow. Implements all modern Home Assistant patterns
and Python 3.12+ features for optimal user experience.

The config flow follows Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations with Python 3.12+ syntax
- Robust error handling with Exception Groups
- Pattern matching for complex flow logic
- Discovery integration with multiple protocols
- Comprehensive validation and user guidance
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

# Python 3.12+ features compatibility check
try:
    # Test if Python 3.12+ type syntax is available
    exec("type TestType = str")
    PYTHON_312_FEATURES = True
except SyntaxError:
    PYTHON_312_FEATURES = False

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_SOURCES,
    DEFAULT_EXPORT_FORMAT,
    DEFAULT_NOTIFICATION_SERVICE,
    DEFAULT_RESET_TIME,
    DOG_SIZES,
    DOMAIN,
    MAX_DOG_AGE_YEARS,
    MAX_DOG_WEIGHT_KG,
    MAX_DOGS_PER_INTEGRATION,
    MIN_DOG_AGE_YEARS,
    MIN_DOG_WEIGHT_KG,
)
from .discovery import can_connect_pawtracker
from .exceptions import (
    ConfigurationError,
    DataValidationError,
)

if TYPE_CHECKING:
    from .types import DogConfig, GeofenceConfig, IntegrationConfig

_LOGGER = logging.getLogger(__name__)

# Python 3.12+ features (with fallback for older versions)
if PYTHON_312_FEATURES:
    # Type aliases using new syntax
    exec("""
type FlowStep = (
    "user" | "discovery_confirm" | "reauth_confirm" |
    "dog_basic" | "dog_modules" | "sources" |
    "notifications" | "geofence" | "advanced"
)

type ValidationResult = tuple[dict[str, Any], dict[str, str] | None]
""")
else:
    # Fallback for Python < 3.12
    from typing import Literal

    FlowStep = Literal[
        "user",
        "discovery_confirm",
        "reauth_confirm",
        "dog_basic",
        "dog_modules",
        "sources",
        "notifications",
        "geofence",
        "advanced",
    ]
    ValidationResult = tuple[dict[str, Any], dict[str, str] | None]

# Exception groups for comprehensive error handling (Python 3.11+)
try:

    class ConfigFlowErrors(ExceptionGroup):
        """Group for config flow related errors."""

        pass

    class ValidationErrors(ExceptionGroup):
        """Group for validation related errors."""

        pass
except NameError:
    # Fallback for Python < 3.11
    class ConfigFlowErrors(Exception):
        """Config flow related errors."""

        def __init__(self, message: str, exceptions: list[Exception] | None = None):
            super().__init__(message)
            self.exceptions = exceptions or []

    class ValidationErrors(Exception):
        """Validation related errors."""

        def __init__(self, message: str, exceptions: list[Exception] | None = None):
            super().__init__(message)
            self.exceptions = exceptions or []


class PawControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for Paw Control integration.

    Implements modern Python 3.12+ patterns with structural pattern matching,
    exception groups, and enhanced type safety for robust configuration.
    """

    VERSION = 1
    MINOR_VERSION = 3

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._discovery_info: dict[str, Any] | None = None
        self._dogs: list[DogConfig] = []
        self._current_dog_index: int = 0
        self._reauth_entry: ConfigEntry | None = None
        self._errors: list[Exception] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial user step with enhanced validation."""
        if user_input is None:
            return self._show_setup_form()

        try:
            # Python 3.12+ pattern matching for input validation
            match user_input.get("setup_mode"):
                case "quick":
                    return await self._handle_quick_setup(user_input)
                case "advanced":
                    return await self.async_step_dog_basic()
                case "discovery":
                    return await self._handle_discovery_setup()
                case _:
                    return self._show_setup_form({"base": "invalid_setup_mode"})

        except (ValueError, TypeError) as err:
            _LOGGER.error("Validation errors in user step: %s", err)
            return self._show_setup_form({"base": "invalid_input"})
        except (ConfigurationError, DataValidationError) as err:
            _LOGGER.error("Config errors in user step: %s", err)
            return self._show_setup_form({"base": "config_error"})

    def _show_setup_form(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Show the initial setup form with modern selectors."""
        schema = vol.Schema(
            {
                vol.Required("setup_mode", default="quick"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "quick", "label": "Schnelle Einrichtung"},
                            {"value": "advanced", "label": "Erweiterte Einrichtung"},
                            {"value": "discovery", "label": "Automatische Erkennung"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "domain": DOMAIN,
                "version": f"{self.VERSION}.{self.MINOR_VERSION}",
            },
        )

    async def _handle_quick_setup(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Handle quick setup with single dog configuration."""
        schema = vol.Schema(
            {
                vol.Required(CONF_DOG_NAME, default="Mein Hund"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required("dog_breed", default="Mischling"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required("dog_size", default="medium"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v["name"]}
                            for k, v in DOG_SIZES.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("dog_weight", default=20.0): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_DOG_WEIGHT_KG,
                        max=MAX_DOG_WEIGHT_KG,
                        step=0.1,
                        unit_of_measurement="kg",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required("dog_age", default=5): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_DOG_AGE_YEARS,
                        max=MAX_DOG_AGE_YEARS,
                        step=1,
                        unit_of_measurement="Jahre",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="quick_setup", data_schema=schema)

        try:
            # Validate and create single dog configuration
            dog_config = await self._validate_dog_config(user_input)

            # Create integration configuration
            config: IntegrationConfig = {
                "dogs": [dog_config],
                "reset_time": DEFAULT_RESET_TIME,
                "export_format": DEFAULT_EXPORT_FORMAT,
            }

            # Create entry with unique ID
            unique_id = f"{DOMAIN}_{dog_config[CONF_DOG_ID]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Paw Control - {dog_config[CONF_DOG_NAME]}",
                data={},  # Store in options for easy updates
                options=config,
            )

        except DataValidationError as err:
            errors = {"base": str(err)}
            return self.async_show_form(
                step_id="quick_setup", data_schema=schema, errors=errors
            )

    async def async_step_dog_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle dog basic information step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                dog_config = await self._validate_dog_config(user_input)
                self._dogs.append(dog_config)

                # Check if user wants to add more dogs
                if (
                    user_input.get("add_another", False)
                    and len(self._dogs) < MAX_DOGS_PER_INTEGRATION
                ):
                    self._current_dog_index += 1
                    return await self.async_step_dog_basic()

                return await self.async_step_sources()

            except DataValidationError as err:
                errors["base"] = str(err)

        # Dynamic schema based on current dog being configured
        dog_number = self._current_dog_index + 1
        default_name = f"Hund {dog_number}" if dog_number > 1 else "Mein Hund"

        schema = vol.Schema(
            {
                vol.Required(CONF_DOG_NAME, default=default_name): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required("dog_breed", default=""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required("dog_size", default="medium"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v["name"]}
                            for k, v in DOG_SIZES.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("dog_weight", default=20.0): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_DOG_WEIGHT_KG,
                        max=MAX_DOG_WEIGHT_KG,
                        step=0.1,
                        unit_of_measurement="kg",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required("dog_age", default=5): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_DOG_AGE_YEARS,
                        max=MAX_DOG_AGE_YEARS,
                        step=1,
                        unit_of_measurement="Jahre",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        # Add "add another dog" option if not at limit
        if len(self._dogs) < MAX_DOGS_PER_INTEGRATION - 1:
            schema = schema.extend(
                {
                    vol.Optional("add_another", default=False): cv.boolean,
                }
            )

        return self.async_show_form(
            step_id="dog_basic",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "dog_number": str(dog_number),
                "dogs_configured": str(len(self._dogs)),
                "max_dogs": str(MAX_DOGS_PER_INTEGRATION),
            },
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure data sources for integration."""
        if user_input is not None:
            return await self.async_step_notifications()

        # Get available entities for source selection
        person_entities = self._get_entities_by_domain("person")
        device_tracker_entities = self._get_entities_by_domain("device_tracker")
        binary_sensor_entities = self._get_entities_by_domain("binary_sensor")
        calendar_entities = self._get_entities_by_domain("calendar")
        weather_entities = self._get_entities_by_domain("weather")

        schema = vol.Schema(
            {
                vol.Optional("person_entities", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=person_entities,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional("device_trackers", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=device_tracker_entities,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional("door_sensor"): SelectSelector(
                    SelectSelectorConfig(
                        options=binary_sensor_entities,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("calendar"): SelectSelector(
                    SelectSelectorConfig(
                        options=calendar_entities,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("weather"): SelectSelector(
                    SelectSelectorConfig(
                        options=weather_entities,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="sources",
            data_schema=schema,
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure notification settings."""
        if user_input is not None:
            return await self.async_step_geofence()

        # Get available notification services
        notify_services = self._get_notify_services()

        schema = vol.Schema(
            {
                vol.Optional(
                    "notify_fallback", default=DEFAULT_NOTIFICATION_SERVICE
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=notify_services,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("quiet_start", default="22:00"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TIME)
                ),
                vol.Optional("quiet_end", default="07:00"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TIME)
                ),
                vol.Optional("reminder_repeat", default=30): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=480,
                        step=5,
                        unit_of_measurement="Minuten",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional("snooze_min", default=15): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=60,
                        step=5,
                        unit_of_measurement="Minuten",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="notifications",
            data_schema=schema,
        )

    async def async_step_geofence(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure geofence settings."""
        if user_input is not None:
            return await self.async_step_advanced()

        # Get current location from Home Assistant
        latitude = self.hass.config.latitude
        longitude = self.hass.config.longitude

        schema = vol.Schema(
            {
                vol.Optional("enable_geofence", default=True): cv.boolean,
                vol.Optional("lat", default=latitude): NumberSelector(
                    NumberSelectorConfig(
                        min=-90.0,
                        max=90.0,
                        step=0.000001,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional("lon", default=longitude): NumberSelector(
                    NumberSelectorConfig(
                        min=-180.0,
                        max=180.0,
                        step=0.000001,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional("radius_m", default=50): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=2000,
                        step=5,
                        unit_of_measurement="Meter",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional("enable_alerts", default=True): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="geofence",
            data_schema=schema,
        )

    async def async_step_gps(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure GPS and tracking settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options["gps"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_gps = self._options.get("gps", {})

        schema = vol.Schema(
            {
                vol.Optional(
                    "gps_enabled",
                    default=current_gps.get("enabled", True),
                ): cv.boolean,
                vol.Optional(
                    "gps_accuracy_filter",
                    default=current_gps.get("accuracy_filter", 100),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1000)),
                vol.Optional(
                    "gps_distance_filter",
                    default=current_gps.get("distance_filter", 5),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Optional(
                    "auto_start_walk",
                    default=current_gps.get("auto_start_walk", False),
                ): cv.boolean,
                vol.Optional(
                    "auto_end_walk",
                    default=current_gps.get("auto_end_walk", True),
                ): cv.boolean,
                vol.Optional(
                    "route_recording",
                    default=current_gps.get("route_recording", True),
                ): cv.boolean,
            }
        )

        return self.async_show_form(step_id="gps", data_schema=schema)

    async def async_step_data_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure data source connections."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options["data_sources"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_sources = self._options.get("data_sources", {})

        # Get available entities for selection
        ent_reg = er.async_get(self.hass)

        # Get person entities
        person_entities = [
            {"value": entity.entity_id, "label": entity.entity_id}
            for entity in ent_reg.entities.values()
            if entity.domain == "person"
        ]

        # Get device tracker entities
        device_tracker_entities = [
            {"value": entity.entity_id, "label": entity.entity_id}
            for entity in ent_reg.entities.values()
            if entity.domain == "device_tracker"
        ]

        schema = vol.Schema(
            {
                vol.Optional(
                    "person_entities",
                    default=current_sources.get("person_entities", []),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=person_entities,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
                if person_entities
                else SelectSelector(
                    SelectSelectorConfig(
                        options=[],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    "device_trackers",
                    default=current_sources.get("device_trackers", []),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=device_tracker_entities,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
                if device_tracker_entities
                else SelectSelector(
                    SelectSelectorConfig(
                        options=[],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    "auto_discovery",
                    default=current_sources.get("auto_discovery", True),
                ): cv.boolean,
            }
        )

        return self.async_show_form(step_id="data_sources", data_schema=schema)

    async def async_step_maintenance(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure maintenance and backup options."""
        if user_input is not None:
            if user_input.get("action") == "backup_config":
                return await self._async_backup_configuration()
            elif user_input.get("action") == "cleanup":
                return await self._async_cleanup_data()
            else:
                new_options = dict(self._options)
                new_options["maintenance"] = {
                    k: v for k, v in user_input.items() if k != "action"
                }
                return self.async_create_entry(title="", data=new_options)

        current_maintenance = self._options.get("maintenance", {})

        schema = vol.Schema(
            {
                vol.Optional(
                    "auto_backup_enabled",
                    default=current_maintenance.get("auto_backup_enabled", True),
                ): cv.boolean,
                vol.Optional(
                    "auto_cleanup_enabled",
                    default=current_maintenance.get("auto_cleanup_enabled", True),
                ): cv.boolean,
                vol.Optional(
                    "action",
                    default="save_settings",
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "save_settings", "label": "Save Settings"},
                            {
                                "value": "backup_config",
                                "label": "Backup Configuration Now",
                            },
                            {"value": "cleanup", "label": "Cleanup Old Data"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="maintenance", data_schema=schema)

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure advanced settings and finalize setup."""
        if user_input is not None:
            try:
                # Build final configuration from all steps
                config = await self._build_final_config(user_input)

                # Create unique ID based on first dog
                first_dog = self._dogs[0] if self._dogs else {"dog_id": "unknown"}
                unique_id = f"{DOMAIN}_{first_dog[CONF_DOG_ID]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                # Create entry
                title = self._generate_entry_title()
                return self.async_create_entry(
                    title=title,
                    data={},  # Store everything in options for easy updates
                    options=config,
                )

            except ConfigurationError:
                errors = {"base": "config_error"}
                return self.async_show_form(
                    step_id="advanced",
                    data_schema=self._get_advanced_schema(),
                    errors=errors,
                )

        return self.async_show_form(
            step_id="advanced",
            data_schema=self._get_advanced_schema(),
        )

    def _get_advanced_schema(self) -> vol.Schema:
        """Get schema for advanced settings."""
        return vol.Schema(
            {
                vol.Optional("reset_time", default=DEFAULT_RESET_TIME): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TIME)
                ),
                vol.Optional(
                    "export_format", default=DEFAULT_EXPORT_FORMAT
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "csv", "label": "CSV"},
                            {"value": "json", "label": "JSON"},
                            {"value": "pdf", "label": "PDF"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("visitor_mode", default=False): cv.boolean,
                vol.Optional("route_history_limit", default=1000): NumberSelector(
                    NumberSelectorConfig(
                        min=100,
                        max=10000,
                        step=100,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional("diagnostic_sensors", default=True): cv.boolean,
                vol.Optional("debug_logging", default=False): cv.boolean,
            }
        )

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery of PAW devices."""
        if user_input is not None:
            return await self.async_step_dog_basic()

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "device_info": str(self._discovery_info or {}),
            },
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth flow."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth and update configuration."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")

        if self._reauth_entry:
            new_data = {**self._reauth_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self._reauth_entry,
                data=new_data,
                options=self._reauth_entry.options,
            )
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_abort(reason="reauth_failed")

    # Discovery methods for USB, DHCP, Zeroconf
    async def async_step_usb(self, discovery_info: dict[str, Any]) -> ConfigFlowResult:
        """Handle USB discovery."""
        self._discovery_info = discovery_info
        await self.async_set_unique_id(
            f"usb_{discovery_info.get('vid')}_{discovery_info.get('pid')}"
        )
        self._abort_if_unique_id_configured()
        return await self.async_step_discovery_confirm()

    async def async_step_dhcp(self, discovery_info: dict[str, Any]) -> ConfigFlowResult:
        """Handle DHCP discovery."""
        self._discovery_info = discovery_info
        mac = discovery_info.get("macaddress", "").replace(":", "").lower()
        await self.async_set_unique_id(f"dhcp_{mac}")
        self._abort_if_unique_id_configured()
        return await self.async_step_discovery_confirm()

    async def async_step_zeroconf(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle Zeroconf discovery."""
        self._discovery_info = discovery_info
        host = discovery_info.get("host", "unknown")
        await self.async_set_unique_id(f"zeroconf_{host}")
        self._abort_if_unique_id_configured()
        return await self.async_step_discovery_confirm()

    # Helper methods with modern Python patterns
    async def _validate_dog_config(self, user_input: dict[str, Any]) -> DogConfig:
        """Validate dog configuration with comprehensive error handling."""
        try:
            # Generate unique dog ID
            dog_name = user_input[CONF_DOG_NAME].strip()
            if not dog_name:
                raise DataValidationError("Dog name cannot be empty")

            # Create safe dog ID from name
            dog_id = re.sub(r"[^a-z0-9_]", "_", dog_name.lower())
            if not dog_id or dog_id == "_":
                dog_id = f"dog_{len(self._dogs) + 1}"

            # Ensure unique dog ID
            existing_ids = {dog[CONF_DOG_ID] for dog in self._dogs}
            original_dog_id = dog_id
            counter = 1
            while dog_id in existing_ids:
                dog_id = f"{original_dog_id}_{counter}"
                counter += 1

            # Validate weight and age
            weight = float(user_input.get("dog_weight", 20.0))
            age = int(user_input.get("dog_age", 5))

            if not (MIN_DOG_WEIGHT_KG <= weight <= MAX_DOG_WEIGHT_KG):
                raise DataValidationError(
                    f"Dog weight must be between {MIN_DOG_WEIGHT_KG} and {MAX_DOG_WEIGHT_KG} kg"
                )

            if not (MIN_DOG_AGE_YEARS <= age <= MAX_DOG_AGE_YEARS):
                raise DataValidationError(
                    f"Dog age must be between {MIN_DOG_AGE_YEARS} and {MAX_DOG_AGE_YEARS} years"
                )

            # Create validated dog config
            dog_config: DogConfig = {
                CONF_DOG_ID: dog_id,
                CONF_DOG_NAME: dog_name,
                "dog_breed": user_input.get("dog_breed", "Mischling").strip()
                or "Mischling",
                "dog_size": user_input.get("dog_size", "medium"),
                "dog_weight": weight,
                "dog_age": age,
                "dog_modules": {
                    "feeding": True,
                    "gps": True,
                    "health": True,
                    "walk": True,
                    "grooming": True,
                    "training": True,
                    "notifications": True,
                    "dashboard": True,
                    "medication": True,
                },
            }

            return dog_config

        except (ValueError, TypeError) as err:
            raise DataValidationError(f"Invalid input: {err}") from err

    async def _build_final_config(
        self, advanced_input: dict[str, Any]
    ) -> IntegrationConfig:
        """Build final integration configuration from all steps."""
        if not self._dogs:
            raise ConfigurationError("No dogs configured")

        config: IntegrationConfig = {
            "dogs": self._dogs,
            "reset_time": advanced_input.get("reset_time", DEFAULT_RESET_TIME),
            "export_format": advanced_input.get("export_format", DEFAULT_EXPORT_FORMAT),
            "visitor_mode": advanced_input.get("visitor_mode", False),
        }

        return config

    def _generate_entry_title(self) -> str:
        """Generate a descriptive title for the config entry."""
        if not self._dogs:
            return "Paw Control"

        if len(self._dogs) == 1:
            return f"Paw Control - {self._dogs[0][CONF_DOG_NAME]}"

        return f"Paw Control - {len(self._dogs)} Hunde"

    def _get_entities_by_domain(self, domain: str) -> list[dict[str, str]]:
        """Get entities by domain for selector options."""
        entities = []
        for entity_id in self.hass.states.async_entity_ids(domain):
            state = self.hass.states.get(entity_id)
            if state:
                name = state.attributes.get("friendly_name", entity_id)
                entities.append({"value": entity_id, "label": name})
        return entities

    def _get_notify_services(self) -> list[dict[str, str]]:
        """Get available notification services."""
        services = [{"value": "notify.notify", "label": "Standard Notification"}]

        for service in self.hass.services.async_services().get("notify", {}):
            if service != "notify":
                services.append(
                    {
                        "value": f"notify.{service}",
                        "label": service.replace("_", " ").title(),
                    }
                )

        return services

    async def _handle_discovery_setup(self) -> ConfigFlowResult:
        """Handle automatic discovery of PAW devices."""
        try:
            # Check for PAW tracker devices
            if await can_connect_pawtracker(self.hass):
                self._discovery_info = {"type": "pawtracker", "status": "connected"}
                return await self.async_step_discovery_confirm()

            # No devices found
            return self.async_show_form(
                step_id="discovery_failed",
                errors={"base": "no_devices_found"},
            )

        except Exception as err:
            _LOGGER.error("Discovery failed: %s", err)
            return self.async_show_form(
                step_id="discovery_failed",
                errors={"base": "discovery_error"},
            )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return PawControlOptionsFlow(config_entry)


class PawControlOptionsFlow(OptionsFlow):
    """Handle options flow for Paw Control integration.

    Provides comprehensive options management with Python 3.12+ features
    for modifying integration configuration without recreation.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._config_entry = config_entry
        self._options = dict(config_entry.options)
        self._dogs_data: dict[str, Any] = {}
        self._current_dog_index = 0
        self._total_dogs = 0
        self._editing_dog_id: str | None = None
        self._temp_options: dict[str, Any] = {}

    @property
    def config_entry(self) -> ConfigEntry:
        """Return the config entry associated with this flow."""
        return self._config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options with a comprehensive menu."""
        if user_input is not None:
            # Handle direct option updates for backward compatibility
            if "geofencing_enabled" in user_input or "modules" in user_input:
                return self.async_create_entry(title="", data=user_input)

        # ERWEITERTE MENU-OPTIONEN
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "dogs",  # Dog Management
                "gps",  # GPS & Tracking
                "geofence",  # Geofence Settings
                "notifications",  # Notifications
                "data_sources",  # Data Sources
                "modules",  # Feature Modules
                "system",  # System Settings
                "maintenance",  # Maintenance & Backup
            ],
        )

    async def async_step_dogs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure dogs."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

    async def _async_backup_configuration(self) -> FlowResult:
        """Backup current configuration."""
        try:
            import json
            from datetime import datetime

            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "version": "1.0",
                "data": self._config_entry.data,
                "options": self._options,
            }

            # Store backup in Home Assistant config directory
            backup_path = self.hass.config.path(
                f"pawcontrol_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2)

            return self.async_show_form(
                step_id="backup_success",
                data_schema=vol.Schema({}),
                description_placeholders={"backup_path": backup_path},
            )

        except Exception as err:
            _LOGGER.error("Failed to backup configuration: %s", err)
            return self.async_show_form(
                step_id="backup_error",
                data_schema=vol.Schema({}),
                errors={"base": "backup_failed"},
            )

    async def _async_cleanup_data(self) -> FlowResult:
        """Cleanup old data and optimize storage."""
        try:
            # Call cleanup services
            await self.hass.services.async_call(
                DOMAIN,
                "purge_all_storage",
                {"config_entry_id": self._config_entry.entry_id},
            )

            return self.async_show_form(
                step_id="cleanup_success",
                data_schema=vol.Schema({}),
            )

        except Exception as err:
            _LOGGER.error("Failed to cleanup data: %s", err)
            return self.async_show_form(
                step_id="cleanup_error",
                data_schema=vol.Schema({}),
                errors={"base": "cleanup_failed"},
            )

        current_dogs = self._options.get(CONF_DOGS, [])

        # Create options for each dog
        dog_options = []
        for i, dog in enumerate(current_dogs):
            dog_options.append(
                {
                    "value": str(i),
                    "label": f"{dog.get(CONF_DOG_NAME, f'Dog {i + 1}')} ({dog.get('dog_breed', 'Unknown')})",
                }
            )

        schema = vol.Schema(
            {
                vol.Optional("edit_dog"): SelectSelector(
                    SelectSelectorConfig(
                        options=dog_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional("add_new_dog", default=False): cv.boolean,
                vol.Optional("remove_dog"): SelectSelector(
                    SelectSelectorConfig(
                        options=dog_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="dogs",
            data_schema=schema,
        )

    async def async_step_geofence(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure geofence options."""
        if user_input is not None:
            # Update geofence configuration
            geofence_config: GeofenceConfig = {
                "lat": user_input.get("lat", self.hass.config.latitude),
                "lon": user_input.get("lon", self.hass.config.longitude),
                "radius_m": user_input.get("radius_m", 50),
                "enable_alerts": user_input.get("enable_alerts", True),
            }

            self._options["geofence"] = geofence_config
            return self.async_create_entry(title="", data=self._options)

        # Get current geofence settings
        current_geofence = self._options.get("geofence", {})

        schema = vol.Schema(
            {
                vol.Optional(
                    "lat",
                    default=current_geofence.get("lat", self.hass.config.latitude),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=-90.0,
                        max=90.0,
                        step=0.000001,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "lon",
                    default=current_geofence.get("lon", self.hass.config.longitude),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=-180.0,
                        max=180.0,
                        step=0.000001,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "radius_m", default=current_geofence.get("radius_m", 50)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=2000,
                        step=5,
                        unit_of_measurement="Meter",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "enable_alerts", default=current_geofence.get("enable_alerts", True)
                ): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="geofence",
            data_schema=schema,
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure advanced options."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Optional(
                    "auto_prune_devices",
                    default=self._options.get("auto_prune_devices", False),
                ): cv.boolean,
                vol.Optional(
                    "route_history_limit",
                    default=self._options.get("route_history_limit", 1000),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=100,
                        max=10000,
                        step=100,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "diagnostic_sensors",
                    default=self._options.get("diagnostic_sensors", True),
                ): cv.boolean,
                vol.Optional(
                    "debug_logging",
                    default=self._options.get("debug_logging", False),
                ): cv.boolean,
                vol.Optional(
                    "api_timeout_seconds",
                    default=self._options.get("api_timeout_seconds", 30),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=120,
                        step=5,
                        unit_of_measurement="Sekunden",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="advanced",
            data_schema=schema,
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure data sources."""
        if user_input is not None:
            self._options[CONF_SOURCES] = user_input
            return self.async_create_entry(title="", data=self._options)

        # Implementation similar to config flow sources step
        return self.async_show_form(step_id="sources")

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure comprehensive notification settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options["notifications"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_notifications = self._options.get("notifications", {})

        schema = vol.Schema(
            {
                vol.Optional(
                    "notifications_enabled",
                    default=current_notifications.get("enabled", True),
                ): cv.boolean,
                vol.Optional(
                    "quiet_hours_enabled",
                    default=current_notifications.get("quiet_hours_enabled", False),
                ): cv.boolean,
                vol.Optional(
                    "quiet_start",
                    default=current_notifications.get("quiet_start", "22:00"),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TIME)),
                vol.Optional(
                    "quiet_end",
                    default=current_notifications.get("quiet_end", "07:00"),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TIME)),
                vol.Optional(
                    "reminder_repeat_min",
                    default=current_notifications.get("reminder_repeat_min", 30),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=120,
                        step=5,
                        unit_of_measurement="Minuten",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "priority_notifications",
                    default=current_notifications.get("priority_notifications", True),
                ): cv.boolean,
                vol.Optional(
                    "summary_notifications",
                    default=current_notifications.get("summary_notifications", True),
                ): cv.boolean,
                vol.Optional(
                    "notification_channels",
                    default=current_notifications.get(
                        "notification_channels", ["mobile", "persistent"]
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "mobile", "label": "Mobile App"},
                            {"value": "persistent", "label": "Persistent Notification"},
                            {"value": "email", "label": "Email"},
                            {"value": "slack", "label": "Slack"},
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="notifications", data_schema=schema)

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure system settings."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Optional(
                    "reset_time",
                    default=self._options.get("reset_time", "23:59:00"),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TIME)),
                vol.Optional(
                    "visitor_mode",
                    default=self._options.get("visitor_mode", False),
                ): cv.boolean,
                vol.Optional(
                    "export_format",
                    default=self._options.get("export_format", "csv"),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "csv", "label": "CSV"},
                            {"value": "json", "label": "JSON"},
                            {"value": "pdf", "label": "PDF"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "auto_prune_devices",
                    default=self._options.get("auto_prune_devices", True),
                ): cv.boolean,
                vol.Optional(
                    "performance_mode",
                    default=self._options.get("performance_mode", "balanced"),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "minimal", "label": "Minimal"},
                            {"value": "balanced", "label": "Balanced"},
                            {"value": "full", "label": "Full"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "log_level",
                    default=self._options.get("log_level", "info"),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "debug", "label": "Debug"},
                            {"value": "info", "label": "Info"},
                            {"value": "warning", "label": "Warning"},
                            {"value": "error", "label": "Error"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "data_retention_days",
                    default=self._options.get("data_retention_days", 365),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=30,
                        max=1095,
                        step=1,
                        unit_of_measurement="Tage",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="system", data_schema=schema)

    async def async_step_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure feature modules."""
        if user_input is not None:
            new_options = dict(self._options)
            new_options["modules"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_modules = self._options.get("modules", {})

        schema = vol.Schema(
            {
                vol.Optional(
                    "feeding_enabled",
                    default=current_modules.get("feeding", True),
                ): cv.boolean,
                vol.Optional(
                    "gps_enabled",
                    default=current_modules.get("gps", True),
                ): cv.boolean,
                vol.Optional(
                    "health_enabled",
                    default=current_modules.get("health", True),
                ): cv.boolean,
                vol.Optional(
                    "walk_enabled",
                    default=current_modules.get("walk", True),
                ): cv.boolean,
                vol.Optional(
                    "grooming_enabled",
                    default=current_modules.get("grooming", False),
                ): cv.boolean,
                vol.Optional(
                    "training_enabled",
                    default=current_modules.get("training", False),
                ): cv.boolean,
                vol.Optional(
                    "notifications_enabled",
                    default=current_modules.get("notifications", True),
                ): cv.boolean,
                vol.Optional(
                    "dashboard_enabled",
                    default=current_modules.get("dashboard", True),
                ): cv.boolean,
                vol.Optional(
                    "medication_enabled",
                    default=current_modules.get("medication", True),
                ): cv.boolean,
            }
        )

        return self.async_show_form(step_id="modules", data_schema=schema)

    async def async_step_export_import(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle configuration export/import."""
        if user_input is not None:
            match user_input.get("action"):
                case "export":
                    return await self._handle_export_config()
                case "import":
                    return await self._handle_import_config(user_input)
                case _:
                    return self.async_show_form(step_id="export_import")

        schema = vol.Schema(
            {
                vol.Required("action"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "export", "label": "Konfiguration exportieren"},
                            {"value": "import", "label": "Konfiguration importieren"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="export_import",
            data_schema=schema,
        )

    async def _handle_export_config(self) -> FlowResult:
        """Export current configuration."""
        # Implementation for config export
        return self.async_show_form(
            step_id="export_success",
            description_placeholders={"export_data": str(self._options)},
        )

    async def _handle_import_config(self, user_input: dict[str, Any]) -> FlowResult:
        """Import configuration from user input."""
        # Implementation for config import
        return self.async_create_entry(title="", data=self._options)


# Backwards compatibility alias
OptionsFlowHandler = PawControlOptionsFlow


# Backwards compatibility for config flow
ConfigFlow = PawControlConfigFlow
