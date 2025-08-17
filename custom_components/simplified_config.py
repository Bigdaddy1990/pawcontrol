"""Simplified configuration structure for Paw Control integration.

This module provides a cleaner, more maintainable configuration system
that focuses on essential features while keeping the door open for extensions.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

# Configuration profiles for different use cases
CONFIG_PROFILES = {
    "basic": {
        "name": "Basic Pet Tracking",
        "description": "Essential features: location, walks, feeding",
        "modules": ["location", "walks", "feeding"],
        "entities_per_dog": 8,
    },
    "advanced": {
        "name": "Advanced Pet Management",
        "description": "Full feature set including health, grooming, training",
        "modules": ["location", "walks", "feeding", "health", "grooming", "training"],
        "entities_per_dog": 15,
    },
    "gps_only": {
        "name": "GPS Tracking Only",
        "description": "Focus on location tracking and geofencing",
        "modules": ["location", "walks"],
        "entities_per_dog": 5,
    },
    "smart_home": {
        "name": "Smart Home Integration",
        "description": "Integration with existing smart home devices",
        "modules": ["location", "walks", "feeding", "automation"],
        "entities_per_dog": 10,
    },
}

# Essential vs Optional modules
ESSENTIAL_MODULES = ["location", "walks"]
OPTIONAL_MODULES = [
    "feeding",
    "health",
    "grooming",
    "training",
    "medication",
    "automation",
]


class SimplifiedConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Simplified config flow focusing on essential setup."""

    VERSION = 2  # Increment version for simplified structure

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial setup step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=self._get_profile_schema(),
                description_placeholders={
                    "profiles_info": self._get_profiles_description()
                },
            )

        # Store selected profile and proceed to dog setup
        self.context["profile"] = user_input["profile"]
        self.context["dogs_count"] = user_input["dogs_count"]
        self.context["current_dog"] = 1

        return await self.async_step_dog_setup()

    def _get_profile_schema(self) -> vol.Schema:
        """Get schema for profile selection."""
        profile_options = {key: info["name"] for key, info in CONFIG_PROFILES.items()}

        return vol.Schema(
            {
                vol.Required("profile", default="basic"): vol.In(profile_options),
                vol.Required("dogs_count", default=1): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=3),  # Limit to 3 dogs for simplicity
                ),
            }
        )

    def _get_profiles_description(self) -> str:
        """Get description of available profiles."""
        descriptions = []
        for key, info in CONFIG_PROFILES.items():
            descriptions.append(f"**{info['name']}**: {info['description']}")
        return "\n".join(descriptions)

    async def async_step_dog_setup(self, user_input: dict | None = None) -> FlowResult:
        """Handle dog setup step."""
        current_dog = self.context["current_dog"]
        total_dogs = self.context["dogs_count"]

        if user_input is None:
            return self.async_show_form(
                step_id="dog_setup",
                data_schema=self._get_dog_schema(),
                description_placeholders={
                    "dog_number": str(current_dog),
                    "total_dogs": str(total_dogs),
                },
            )

        # Store dog configuration
        if "dogs" not in self.context:
            self.context["dogs"] = []

        # Validate dog configuration
        dog_config = self._validate_dog_config(user_input)
        self.context["dogs"].append(dog_config)

        # Check if we need to configure more dogs
        if current_dog < total_dogs:
            self.context["current_dog"] = current_dog + 1
            return await self.async_step_dog_setup()

        # All dogs configured, proceed to optional settings
        return await self.async_step_optional_settings()

    def _get_dog_schema(self) -> vol.Schema:
        """Get schema for dog configuration."""
        return vol.Schema(
            {
                vol.Required("dog_id"): vol.All(str, vol.Length(min=1, max=20)),
                vol.Required("dog_name"): vol.All(str, vol.Length(min=1, max=50)),
                vol.Optional("dog_breed", default=""): str,
                vol.Optional("dog_weight", default=20.0): vol.All(
                    vol.Coerce(float), vol.Range(min=0.5, max=100.0)
                ),
                vol.Optional("dog_age", default=5): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=25)
                ),
            }
        )

    def _validate_dog_config(self, user_input: dict) -> dict:
        """Validate and normalize dog configuration."""
        # Check for duplicate dog IDs
        existing_dogs = self.context.get("dogs", [])
        for existing_dog in existing_dogs:
            if existing_dog["dog_id"] == user_input["dog_id"]:
                raise vol.Invalid("Dog ID already exists")

        # Normalize configuration
        return {
            "dog_id": user_input["dog_id"].lower().replace(" ", "_"),
            "dog_name": user_input["dog_name"].strip(),
            "dog_breed": user_input.get("dog_breed", "").strip(),
            "dog_weight": float(user_input.get("dog_weight", 20.0)),
            "dog_age": int(user_input.get("dog_age", 5)),
        }

    async def async_step_optional_settings(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle optional settings configuration."""
        if user_input is None:
            return self.async_show_form(
                step_id="optional_settings",
                data_schema=self._get_optional_settings_schema(),
            )

        # Create final configuration
        profile = CONFIG_PROFILES[self.context["profile"]]

        config_data = {
            "name": user_input.get("integration_name", "Paw Control"),
            "profile": self.context["profile"],
            "dogs": self.context["dogs"],
            "modules": profile["modules"],
            "settings": {
                "notifications_enabled": user_input.get("notifications_enabled", True),
                "geofencing_enabled": user_input.get("geofencing_enabled", True),
                "data_retention_days": user_input.get("data_retention_days", 90),
            },
        }

        # Create config entry
        return self.async_create_entry(
            title=config_data["name"],
            data=config_data,
        )

    def _get_optional_settings_schema(self) -> vol.Schema:
        """Get schema for optional settings."""
        return vol.Schema(
            {
                vol.Optional("integration_name", default="Paw Control"): str,
                vol.Optional("notifications_enabled", default=True): bool,
                vol.Optional("geofencing_enabled", default=True): bool,
                vol.Optional("data_retention_days", default=90): vol.All(
                    vol.Coerce(int), vol.Range(min=7, max=365)
                ),
            }
        )


class SimplifiedOptionsFlow(config_entries.OptionsFlow):
    """Simplified options flow for easier configuration changes."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options={
                "basic_settings": "Basic Settings",
                "modules": "Enable/Disable Modules",
                "notifications": "Notifications",
                "performance": "Performance Settings",
            },
        )

    async def async_step_basic_settings(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Configure basic settings."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_options = self.config_entry.options

        return self.async_show_form(
            step_id="basic_settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "geofencing_enabled",
                        default=current_options.get("geofencing_enabled", True),
                    ): bool,
                    vol.Optional(
                        "data_retention_days",
                        default=current_options.get("data_retention_days", 90),
                    ): vol.All(vol.Coerce(int), vol.Range(min=7, max=365)),
                    vol.Optional(
                        "update_interval_minutes",
                        default=current_options.get("update_interval_minutes", 5),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                }
            ),
        )

    async def async_step_modules(self, user_input: dict | None = None) -> FlowResult:
        """Configure enabled modules."""
        if user_input is not None:
            # Update modules in config
            new_options = dict(self.config_entry.options)
            new_options["modules"] = [
                module
                for module in ESSENTIAL_MODULES + OPTIONAL_MODULES
                if user_input.get(f"module_{module}", module in ESSENTIAL_MODULES)
            ]
            return self.async_create_entry(title="", data=new_options)

        current_modules = self.config_entry.options.get(
            "modules", ["location", "walks"]
        )

        schema_dict = {}

        # Essential modules (always enabled)
        for module in ESSENTIAL_MODULES:
            schema_dict[vol.Optional(f"module_{module}", default=True)] = bool

        # Optional modules
        for module in OPTIONAL_MODULES:
            default_enabled = module in current_modules
            schema_dict[vol.Optional(f"module_{module}", default=default_enabled)] = (
                bool
            )

        return self.async_show_form(
            step_id="modules",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "essential_modules": ", ".join(ESSENTIAL_MODULES),
                "optional_modules": ", ".join(OPTIONAL_MODULES),
            },
        )

    async def async_step_notifications(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Configure notification settings."""
        if user_input is not None:
            new_options = dict(self.config_entry.options)
            new_options["notifications"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_notifications = self.config_entry.options.get("notifications", {})

        return self.async_show_form(
            step_id="notifications",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "enabled",
                        default=current_notifications.get("enabled", True),
                    ): bool,
                    vol.Optional(
                        "walk_reminders",
                        default=current_notifications.get("walk_reminders", True),
                    ): bool,
                    vol.Optional(
                        "feeding_reminders",
                        default=current_notifications.get("feeding_reminders", True),
                    ): bool,
                    vol.Optional(
                        "quiet_hours_start",
                        default=current_notifications.get("quiet_hours_start", "22:00"),
                    ): str,
                    vol.Optional(
                        "quiet_hours_end",
                        default=current_notifications.get("quiet_hours_end", "07:00"),
                    ): str,
                }
            ),
        )

    async def async_step_performance(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Configure performance settings."""
        if user_input is not None:
            new_options = dict(self.config_entry.options)
            new_options["performance"] = user_input
            return self.async_create_entry(title="", data=new_options)

        current_performance = self.config_entry.options.get("performance", {})

        return self.async_show_form(
            step_id="performance",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "max_entities_per_dog",
                        default=current_performance.get("max_entities_per_dog", 10),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=20)),
                    vol.Optional(
                        "enable_caching",
                        default=current_performance.get("enable_caching", True),
                    ): bool,
                    vol.Optional(
                        "batch_updates",
                        default=current_performance.get("batch_updates", True),
                    ): bool,
                    vol.Optional(
                        "debug_mode",
                        default=current_performance.get("debug_mode", False),
                    ): bool,
                }
            ),
        )


def get_module_entities(module: str, dog_id: str) -> list[str]:
    """Get list of entities for a specific module."""
    entity_map = {
        "location": [
            f"device_tracker.{dog_id}_gps",
            f"binary_sensor.{dog_id}_is_home",
            f"sensor.{dog_id}_distance_from_home",
        ],
        "walks": [
            f"binary_sensor.{dog_id}_walk_in_progress",
            f"binary_sensor.{dog_id}_needs_walk",
            f"sensor.{dog_id}_walk_distance_today",
            f"sensor.{dog_id}_last_walk_hours",
            f"button.{dog_id}_start_walk",
            f"button.{dog_id}_end_walk",
        ],
        "feeding": [
            f"binary_sensor.{dog_id}_is_hungry",
            f"sensor.{dog_id}_last_feeding_hours",
            f"sensor.{dog_id}_feedings_today",
            f"button.{dog_id}_mark_fed",
        ],
        "health": [
            f"sensor.{dog_id}_weight",
            f"sensor.{dog_id}_medications_today",
            f"binary_sensor.{dog_id}_medication_due",
            f"button.{dog_id}_log_medication",
        ],
        "grooming": [
            f"binary_sensor.{dog_id}_needs_grooming",
            f"sensor.{dog_id}_days_since_grooming",
            f"button.{dog_id}_start_grooming",
        ],
        "training": [
            f"sensor.{dog_id}_training_sessions_today",
            f"button.{dog_id}_start_training",
        ],
    }

    return entity_map.get(module, [])


def calculate_total_entities(dogs: list[dict], modules: list[str]) -> int:
    """Calculate total number of entities that will be created."""
    total = 0
    for dog in dogs:
        for module in modules:
            total += len(get_module_entities(module, dog["dog_id"]))
    return total


def validate_configuration(config: dict) -> tuple[bool, list[str]]:
    """Validate the complete configuration and return any warnings."""
    warnings = []

    # Check entity count
    total_entities = calculate_total_entities(config["dogs"], config["modules"])
    if total_entities > 50:
        warnings.append(
            f"High entity count ({total_entities}). Consider reducing modules or dogs."
        )

    # Check dog names for conflicts
    dog_names = [dog["dog_name"] for dog in config["dogs"]]
    if len(dog_names) != len(set(dog_names)):
        warnings.append("Duplicate dog names detected. This may cause confusion.")

    # Check module combinations
    if "health" in config["modules"] and len(config["dogs"]) > 2:
        warnings.append("Health module with multiple dogs may create many entities.")

    return len(warnings) == 0, warnings


async def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> SimplifiedOptionsFlow:
    """Return the options flow handler."""
    return SimplifiedOptionsFlow(config_entry)
