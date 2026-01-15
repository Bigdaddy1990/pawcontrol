"""System, dashboard, advanced and weather settings steps for the PawControl options flow."""

from __future__ import annotations

import logging
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DASHBOARD_MODE,
    CONF_RESET_TIME,
    CONF_WEATHER_ENTITY,
    DASHBOARD_MODE_SELECTOR_OPTIONS,
    DEFAULT_RESET_TIME,
)
from .device_api import validate_device_endpoint
from .exceptions import FlowValidationError  # noqa: F401
from .selector_shim import selector
from .types import (
    freeze_placeholders,
)

_LOGGER = logging.getLogger(__name__)


class SystemSettingsOptionsMixin:
    async def async_step_weather_settings(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure weather-based health monitoring settings.

        NEW: Comprehensive weather configuration including entity selection,
        health monitoring toggles, and alert preferences for weather-based
        health recommendations.
        """
        if user_input is not None:
            try:
                # Validate weather entity if specified
                raw_entity = user_input.get("weather_entity")
                candidate = raw_entity.strip() if isinstance(raw_entity, str) else None
                if candidate and candidate.lower() != "none":
                    weather_state = self.hass.states.get(candidate)
                    if weather_state is None:
                        return self.async_show_form(
                            step_id="weather_settings",
                            data_schema=self._get_weather_settings_schema(
                                user_input,
                            ),
                            errors={
                                "weather_entity": "weather_entity_not_found",
                            },
                        )

                    # Check if it's a weather entity
                    if not candidate.startswith("weather."):
                        return self.async_show_form(
                            step_id="weather_settings",
                            data_schema=self._get_weather_settings_schema(
                                user_input,
                            ),
                            errors={"weather_entity": "invalid_weather_entity"},
                        )

                current_weather = self._current_weather_options()
                new_options = self._clone_options()
                weather_settings = self._build_weather_settings(
                    user_input,
                    current_weather,
                )
                mutable_options = cast(JSONMutableMapping, dict(new_options))  # noqa: F821
                mutable_options["weather_settings"] = cast(JSONValue, weather_settings)  # noqa: F821
                mutable_options[CONF_WEATHER_ENTITY] = cast(
                    JSONValue,  # noqa: F821
                    weather_settings.get(CONF_WEATHER_ENTITY),
                )
                typed_options = self._normalise_options_snapshot(
                    mutable_options,
                )
                return self.async_create_entry(title="", data=typed_options)

            except Exception as err:
                _LOGGER.error("Error updating weather settings: %s", err)
                return self.async_show_form(
                    step_id="weather_settings",
                    data_schema=self._get_weather_settings_schema(user_input),
                    errors={"base": "weather_update_failed"},
                )

        return self.async_show_form(
            step_id="weather_settings",
            data_schema=self._get_weather_settings_schema(),
            description_placeholders=dict(
                self._get_weather_description_placeholders(),
            ),
        )

    def _get_weather_settings_schema(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> vol.Schema:
        """Get weather settings schema with current values and entity selection."""
        current_weather = self._current_weather_options()
        current_values = user_input or {}

        stored_entity = current_weather.get(CONF_WEATHER_ENTITY)
        entity_default = "none"
        if isinstance(stored_entity, str) and stored_entity.strip():
            entity_default = stored_entity

        # Get available weather entities
        weather_entities: list[str | dict[str, str]] = ["none"]

        for entity_id in self.hass.states.async_entity_ids("weather"):
            entity_state = self.hass.states.get(entity_id)
            if entity_state:
                friendly_name = entity_state.attributes.get(
                    "friendly_name",
                    entity_id,
                )
                weather_entities.append(
                    {"value": entity_id, "label": str(friendly_name)},
                )

        return vol.Schema(
            {
                vol.Optional(
                    "weather_entity",
                    default=current_values.get(
                        "weather_entity",
                        entity_default,
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=weather_entities,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="weather_entity",
                    ),
                ),
                vol.Optional(
                    "weather_health_monitoring",
                    default=current_values.get(
                        "weather_health_monitoring",
                        current_weather.get(
                            "weather_health_monitoring",
                            DEFAULT_WEATHER_HEALTH_MONITORING,  # noqa: F821
                        ),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "weather_alerts",
                    default=current_values.get(
                        "weather_alerts",
                        current_weather.get("weather_alerts", DEFAULT_WEATHER_ALERTS),  # noqa: F821
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "weather_update_interval",
                    default=current_values.get(
                        "weather_update_interval",
                        current_weather.get("weather_update_interval", 60),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=15,
                        max=1440,
                        step=15,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="minutes",
                    ),
                ),
                vol.Optional(
                    "temperature_alerts",
                    default=current_values.get(
                        "temperature_alerts",
                        current_weather.get("temperature_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "uv_alerts",
                    default=current_values.get(
                        "uv_alerts",
                        current_weather.get("uv_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "humidity_alerts",
                    default=current_values.get(
                        "humidity_alerts",
                        current_weather.get("humidity_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "wind_alerts",
                    default=current_values.get(
                        "wind_alerts",
                        current_weather.get("wind_alerts", False),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "storm_alerts",
                    default=current_values.get(
                        "storm_alerts",
                        current_weather.get("storm_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "breed_specific_recommendations",
                    default=current_values.get(
                        "breed_specific_recommendations",
                        current_weather.get(
                            "breed_specific_recommendations",
                            True,
                        ),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "health_condition_adjustments",
                    default=current_values.get(
                        "health_condition_adjustments",
                        current_weather.get(
                            "health_condition_adjustments",
                            True,
                        ),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "auto_activity_adjustments",
                    default=current_values.get(
                        "auto_activity_adjustments",
                        current_weather.get(
                            "auto_activity_adjustments",
                            False,
                        ),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "notification_threshold",
                    default=current_values.get(
                        "notification_threshold",
                        current_weather.get(
                            "notification_threshold",
                            "moderate",
                        ),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["low", "moderate", "high"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="weather_notification_threshold",
                    ),
                ),
            },
        )

    def _get_weather_description_placeholders(self) -> ConfigFlowPlaceholders:  # noqa: F821
        """Get description placeholders for weather configuration."""
        current_weather = self._current_weather_options()
        current_dogs_raw = self._entry.data.get(CONF_DOGS, [])  # noqa: F821
        current_dogs: list[DogConfigData] = []  # noqa: F821
        if isinstance(current_dogs_raw, Sequence):  # noqa: F821
            for dog in current_dogs_raw:
                if isinstance(dog, Mapping):  # noqa: F821
                    normalised = ensure_dog_config_data(  # noqa: F821
                        cast(Mapping[str, JSONValue], dog),  # noqa: F821
                    )
                    if normalised is not None:
                        current_dogs.append(normalised)

        # Current weather entity status
        weather_entity = current_weather.get(CONF_WEATHER_ENTITY)
        weather_status = "Not configured"
        weather_info = "No weather entity selected"

        if weather_entity:
            weather_state = self.hass.states.get(weather_entity)
            if weather_state:
                weather_status = "Available"
                temperature = weather_state.attributes.get(
                    "temperature",
                    "Unknown",
                )
                condition = weather_state.state or "Unknown"
                weather_info = f"Current: {temperature}°C, {condition}"
            else:
                weather_status = "Entity not found"
                weather_info = f"Entity {weather_entity} is not available"

        # Count dogs with health conditions
        dogs_with_health_conditions = 0
        dogs_with_breeds = 0
        for dog_config in current_dogs:
            if dog_config.get("health_conditions"):
                dogs_with_health_conditions += 1
            dog_breed = dog_config.get(CONF_DOG_BREED)  # noqa: F821
            if dog_breed and dog_breed != "Mixed Breed":
                dogs_with_breeds += 1

        # Alert configuration summary
        enabled_alerts = []
        if current_weather.get("temperature_alerts", True):
            enabled_alerts.append("Temperature")
        if current_weather.get("uv_alerts", True):
            enabled_alerts.append("UV")
        if current_weather.get("humidity_alerts", True):
            enabled_alerts.append("Humidity")
        if current_weather.get("storm_alerts", True):
            enabled_alerts.append("Storms")
        if current_weather.get("wind_alerts", False):
            enabled_alerts.append("Wind")

        alerts_summary = (
            ", ".join(
                enabled_alerts,
            )
            if enabled_alerts
            else "None"
        )

        # Feature status
        weather_monitoring = current_weather.get(
            "weather_health_monitoring",
            DEFAULT_WEATHER_HEALTH_MONITORING,  # noqa: F821
        )
        breed_recommendations = current_weather.get(
            "breed_specific_recommendations",
            True,
        )
        health_adjustments = current_weather.get(
            "health_condition_adjustments",
            True,
        )

        return freeze_placeholders(
            {
                "weather_entity_status": weather_status,
                "current_weather_info": weather_info,
                "total_dogs": str(len(current_dogs)),
                "dogs_with_health_conditions": str(dogs_with_health_conditions),
                "dogs_with_breeds": str(dogs_with_breeds),
                "monitoring_status": "Enabled" if weather_monitoring else "Disabled",
                "alerts_enabled": alerts_summary,
                "breed_recommendations_status": "Enabled"
                if breed_recommendations
                else "Disabled",
                "health_adjustments_status": "Enabled"
                if health_adjustments
                else "Disabled",
                "update_interval": str(
                    current_weather.get("weather_update_interval", 60),
                ),
                "notification_threshold": current_weather.get(
                    "notification_threshold",
                    "moderate",
                ).title(),
                "available_weather_entities": str(
                    len([e for e in self.hass.states.async_entity_ids("weather")]),
                ),
            },
        )

    async def async_step_system_settings(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure system and performance settings."""
        placeholders = self._manual_event_description_placeholders()
        if user_input is not None:
            try:
                current_system = self._current_system_options()
                reset_default = self._coerce_time_string(
                    self._current_options().get(CONF_RESET_TIME),
                    DEFAULT_RESET_TIME,
                )
                new_options = self._clone_options()
                mutable_options = cast(JSONMutableMapping, dict(new_options))  # noqa: F821
                system_settings, reset_time = self._build_system_settings(
                    user_input,
                    current_system,
                    reset_default=reset_default,
                )
                mutable_options["system_settings"] = cast(JSONValue, system_settings)  # noqa: F821
                mutable_options[CONF_RESET_TIME] = reset_time
                mutable_options[SYSTEM_ENABLE_ANALYTICS_FIELD] = system_settings[  # noqa: F821
                    SYSTEM_ENABLE_ANALYTICS_FIELD  # noqa: F821
                ]
                mutable_options[SYSTEM_ENABLE_CLOUD_BACKUP_FIELD] = system_settings[  # noqa: F821
                    SYSTEM_ENABLE_CLOUD_BACKUP_FIELD  # noqa: F821
                ]
                guard_option = system_settings.get("manual_guard_event")
                if guard_option is None:
                    mutable_options.pop("manual_guard_event", None)
                else:
                    mutable_options["manual_guard_event"] = guard_option
                breaker_option = system_settings.get("manual_breaker_event")
                if breaker_option is None:
                    mutable_options.pop("manual_breaker_event", None)
                else:
                    mutable_options["manual_breaker_event"] = breaker_option
                runtime = get_runtime_data(self.hass, self._entry)  # noqa: F821
                script_manager = getattr(runtime, "script_manager", None)
                if script_manager is not None:
                    await script_manager.async_sync_manual_resilience_events(
                        {
                            "manual_check_event": system_settings.get(
                                "manual_check_event",
                            ),
                            "manual_guard_event": system_settings.get(
                                "manual_guard_event",
                            ),
                            "manual_breaker_event": system_settings.get(
                                "manual_breaker_event",
                            ),
                        },
                    )
                typed_options = self._normalise_options_snapshot(
                    mutable_options,
                )
                return self.async_create_entry(title="", data=typed_options)
            except Exception:
                return self.async_show_form(
                    step_id="system_settings",
                    data_schema=self._get_system_settings_schema(user_input),
                    description_placeholders=dict(placeholders),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="system_settings",
            data_schema=self._get_system_settings_schema(),
            description_placeholders=dict(placeholders),
        )

    def _get_system_settings_schema(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> vol.Schema:
        """Get system settings schema."""
        current_system = self._current_system_options()
        current_values = user_input or {}
        reset_default = self._coerce_time_string(
            self._current_options().get(CONF_RESET_TIME),
            DEFAULT_RESET_TIME,
        )
        mode_default = normalize_performance_mode(  # noqa: F821
            current_system.get("performance_mode"),
            current=self._current_options().get("performance_mode"),
        )
        analytics_default = self._coerce_bool(
            current_values.get(
                "enable_analytics",
                current_system.get(SYSTEM_ENABLE_ANALYTICS_FIELD),  # noqa: F821
            ),
            bool(self._current_options().get("enable_analytics", False)),
        )
        cloud_backup_default = self._coerce_bool(
            current_values.get(
                "enable_cloud_backup",
                current_system.get(SYSTEM_ENABLE_CLOUD_BACKUP_FIELD),  # noqa: F821
            ),
            bool(self._current_options().get("enable_cloud_backup", False)),
        )

        skip_threshold_default = self._coerce_clamped_int(
            current_values.get("resilience_skip_threshold"),
            current_system.get(
                "resilience_skip_threshold",
                DEFAULT_RESILIENCE_SKIP_THRESHOLD,  # noqa: F821
            ),
            minimum=RESILIENCE_SKIP_THRESHOLD_MIN,  # noqa: F821
            maximum=RESILIENCE_SKIP_THRESHOLD_MAX,  # noqa: F821
        )

        breaker_threshold_default = self._coerce_clamped_int(
            current_values.get("resilience_breaker_threshold"),
            current_system.get(
                "resilience_breaker_threshold",
                DEFAULT_RESILIENCE_BREAKER_THRESHOLD,  # noqa: F821
            ),
            minimum=RESILIENCE_BREAKER_THRESHOLD_MIN,  # noqa: F821
            maximum=RESILIENCE_BREAKER_THRESHOLD_MAX,  # noqa: F821
        )

        manual_defaults = self._manual_event_schema_defaults(current_system)
        manual_snapshot = self._manual_events_snapshot()
        manual_context = self._resolve_manual_event_context(
            current_system,
            manual_snapshot=manual_snapshot,
        )

        manual_choices = {
            field: self._manual_event_choices(
                field,
                current_system,
                manual_snapshot=manual_snapshot,
            )
            for field in self._MANUAL_EVENT_FIELDS
        }

        manual_context_defaults: dict[str, str] = {}
        context_mapping = (
            ("manual_check_event", "check_default"),
            ("manual_guard_event", "guard_default"),
            ("manual_breaker_event", "breaker_default"),
        )
        for field, context_key in context_mapping:
            context_value = manual_context.get(context_key)
            if isinstance(context_value, str):
                manual_context_defaults[field] = context_value

        def _manual_default(field: str) -> str:
            raw_value = current_values.get(field)
            if isinstance(raw_value, str):
                return raw_value
            override = manual_context_defaults.get(field)
            if override:
                return override
            return manual_defaults[field]

        return vol.Schema(
            {
                vol.Optional(
                    "reset_time",
                    default=current_values.get("reset_time", reset_default),
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
                    ),
                ),
                vol.Optional(
                    "auto_backup",
                    default=current_values.get(
                        "auto_backup",
                        current_system.get("auto_backup", False),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_analytics",
                    default=analytics_default,
                ): selector.BooleanSelector(),
                vol.Optional(
                    "enable_cloud_backup",
                    default=cloud_backup_default,
                ): selector.BooleanSelector(),
                vol.Optional(
                    "resilience_skip_threshold",
                    default=skip_threshold_default,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=RESILIENCE_SKIP_THRESHOLD_MIN,  # noqa: F821
                        max=RESILIENCE_SKIP_THRESHOLD_MAX,  # noqa: F821
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
                vol.Optional(
                    "resilience_breaker_threshold",
                    default=breaker_threshold_default,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=RESILIENCE_BREAKER_THRESHOLD_MIN,  # noqa: F821
                        max=RESILIENCE_BREAKER_THRESHOLD_MAX,  # noqa: F821
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
                vol.Optional(
                    "manual_check_event",
                    default=_manual_default("manual_check_event"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=manual_choices["manual_check_event"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    ),
                ),
                vol.Optional(
                    "manual_guard_event",
                    default=_manual_default("manual_guard_event"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=manual_choices["manual_guard_event"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    ),
                ),
                vol.Optional(
                    "manual_breaker_event",
                    default=_manual_default("manual_breaker_event"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=manual_choices["manual_breaker_event"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    ),
                ),
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        mode_default,
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["minimal", "balanced", "full"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="performance_mode",
                    ),
                ),
            },
        )

    async def async_step_dashboard_settings(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure dashboard and display settings."""
        if user_input is not None:
            try:
                current_dashboard = self._current_dashboard_options()
                default_mode = self._normalize_choice(
                    self._current_options().get(CONF_DASHBOARD_MODE, "full"),
                    valid={
                        option["value"] for option in DASHBOARD_MODE_SELECTOR_OPTIONS
                    },
                    default="full",
                )
                new_options = self._clone_options()
                dashboard_settings, dashboard_mode = self._build_dashboard_settings(
                    user_input,
                    current_dashboard,
                    default_mode=default_mode,
                )
                mutable_options = cast(JSONMutableMapping, dict(new_options))  # noqa: F821
                mutable_options["dashboard_settings"] = cast(
                    JSONValue,  # noqa: F821
                    dashboard_settings,
                )
                mutable_options[CONF_DASHBOARD_MODE] = dashboard_mode
                typed_options = self._normalise_options_snapshot(
                    mutable_options,
                )
                return self.async_create_entry(title="", data=typed_options)
            except Exception:
                return self.async_show_form(
                    step_id="dashboard_settings",
                    data_schema=self._get_dashboard_settings_schema(
                        user_input,
                    ),
                    errors={"base": "update_failed"},
                )

        return self.async_show_form(
            step_id="dashboard_settings",
            data_schema=self._get_dashboard_settings_schema(),
        )

    def _get_dashboard_settings_schema(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> vol.Schema:
        """Get dashboard settings schema."""
        current_dashboard = self._current_dashboard_options()
        current_values = user_input or {}
        default_mode = self._normalize_choice(
            self._current_options().get(CONF_DASHBOARD_MODE, "full"),
            valid={option["value"] for option in DASHBOARD_MODE_SELECTOR_OPTIONS},
            default="full",
        )

        return vol.Schema(
            {
                vol.Optional(
                    "dashboard_mode",
                    default=current_values.get(
                        "dashboard_mode",
                        default_mode,
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=DASHBOARD_MODE_SELECTOR_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
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
                        "show_alerts",
                        current_dashboard.get("show_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "compact_mode",
                    default=current_values.get(
                        "compact_mode",
                        current_dashboard.get("compact_mode", False),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "show_maps",
                    default=current_values.get(
                        "show_maps",
                        current_dashboard.get("show_maps", True),
                    ),
                ): selector.BooleanSelector(),
            },
        )

    async def async_step_advanced_settings(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle advanced settings configuration."""
        if user_input is not None:
            errors: dict[str, str] = {}
            raw_endpoint = user_input.get(CONF_API_ENDPOINT, "")
            endpoint_value = (
                raw_endpoint.strip() if isinstance(raw_endpoint, str) else ""
            )
            if endpoint_value:
                try:
                    validate_device_endpoint(endpoint_value)
                except ValueError:
                    errors[CONF_API_ENDPOINT] = "invalid_api_endpoint"

            if errors:
                return self.async_show_form(
                    step_id="advanced_settings",
                    errors=errors,
                    data_schema=self._get_advanced_settings_schema(user_input),
                )

            try:
                current_advanced = self._current_advanced_options()
                new_options = self._clone_options()
                advanced_settings = self._build_advanced_settings(
                    user_input,
                    current_advanced,
                )
                mutable_options = cast(JSONMutableMapping, dict(new_options))  # noqa: F821
                mutable_options[ADVANCED_SETTINGS_FIELD] = cast(  # noqa: F821
                    JSONValue,  # noqa: F821
                    advanced_settings,
                )
                for key, value in advanced_settings.items():
                    if isinstance(value, bool | int | float | str) or value is None:
                        mutable_options[str(key)] = value
                    elif isinstance(value, Mapping):  # noqa: F821
                        mutable_options[str(key)] = cast(JSONValue, dict(value))  # noqa: F821
                    else:
                        mutable_options[str(key)] = repr(value)
                return self.async_create_entry(
                    title="",
                    data=self._normalise_options_snapshot(mutable_options),
                )
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

    def _get_advanced_settings_schema(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> vol.Schema:
        """Get schema for advanced settings form."""
        current_advanced = self._current_advanced_options()
        current_values = user_input or {}
        mode_default = normalize_performance_mode(  # noqa: F821
            current_advanced.get("performance_mode"),
            current=self._current_options().get("performance_mode"),
        )
        retention_default = self._coerce_int(
            current_advanced.get("data_retention_days"),
            90,
        )
        debug_default = self._coerce_bool(
            current_advanced.get("debug_logging"),
            False,
        )
        backup_default = self._coerce_bool(
            current_advanced.get("auto_backup"),
            False,
        )
        experimental_default = self._coerce_bool(
            current_advanced.get("experimental_features"),
            False,
        )
        integrations_default = self._coerce_bool(
            current_advanced.get(CONF_EXTERNAL_INTEGRATIONS),  # noqa: F821
            False,
        )
        endpoint_default = (
            current_advanced.get(CONF_API_ENDPOINT)
            if isinstance(current_advanced.get(CONF_API_ENDPOINT), str)
            else ""
        )
        token_default = (
            current_advanced.get(CONF_API_TOKEN)
            if isinstance(current_advanced.get(CONF_API_TOKEN), str)
            else ""
        )

        return vol.Schema(
            {
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        mode_default,
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["minimal", "balanced", "full"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="performance_mode",
                    ),
                ),
                vol.Optional(
                    "debug_logging",
                    default=current_values.get("debug_logging", debug_default),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "data_retention_days",
                    default=current_values.get(
                        "data_retention_days",
                        retention_default,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    ),
                ),
                vol.Optional(
                    "auto_backup",
                    default=current_values.get("auto_backup", backup_default),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "experimental_features",
                    default=current_values.get(
                        "experimental_features",
                        experimental_default,
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_EXTERNAL_INTEGRATIONS,  # noqa: F821
                    default=current_values.get(
                        CONF_EXTERNAL_INTEGRATIONS,  # noqa: F821
                        integrations_default,
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_API_ENDPOINT,
                    default=current_values.get(
                        CONF_API_ENDPOINT,
                        endpoint_default,
                    ),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        multiline=False,
                    ),
                ),
                vol.Optional(
                    CONF_API_TOKEN,
                    default=current_values.get(CONF_API_TOKEN, token_default),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                        multiline=False,
                    ),
                ),
            },
        )
