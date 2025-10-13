"""Options flow for Paw Control integration with profile-based entity management.

This module provides comprehensive post-setup configuration options for the
Paw Control integration. It allows users to modify all aspects of their
configuration after initial setup with organized menu-driven navigation.

UPDATED: Adds entity profile selection for performance optimization
Integrates with EntityFactory for intelligent entity management
ENHANCED: GPS and Geofencing functionality per fahrplan.txt requirements

Quality Scale: Bronze target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, ClassVar, Final, Literal, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry
from .config_flow_profile import (
    DEFAULT_PROFILE,
    get_profile_selector_options,
    validate_profile_selection,
)
from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DASHBOARD_MODE,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_EXTERNAL_INTEGRATIONS,
    CONF_GPS_ACCURACY_FILTER,
    CONF_GPS_DISTANCE_FILTER,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_MODULES,
    CONF_NOTIFICATIONS,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT_MIN,
    CONF_RESET_TIME,
    CONF_WEATHER_ENTITY,
    DASHBOARD_MODE_SELECTOR_OPTIONS,
    DEFAULT_GPS_ACCURACY_FILTER,
    DEFAULT_GPS_DISTANCE_FILTER,
    DEFAULT_GPS_UPDATE_INTERVAL,
    DEFAULT_REMINDER_REPEAT_MIN,
    DEFAULT_RESET_TIME,
    DEFAULT_WEATHER_ALERTS,
    DEFAULT_WEATHER_HEALTH_MONITORING,
    GPS_ACCURACY_FILTER_SELECTOR,
    GPS_UPDATE_INTERVAL_SELECTOR,
    MAX_GEOFENCE_RADIUS,
    MIN_GEOFENCE_RADIUS,
    MODULE_FEEDING,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .coordinator_support import DogConfigRegistry
from .device_api import validate_device_endpoint
from .entity_factory import ENTITY_PROFILES, EntityFactory
from .exceptions import ValidationError
from .selector_shim import selector
from .types import (
    DOG_AGE_FIELD,
    DOG_BREED_FIELD,
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DOG_SIZE_FIELD,
    DOG_WEIGHT_FIELD,
    AdvancedOptions,
    DashboardOptions,
    DogConfigData,
    DogModulesConfig,
    DogOptionsMap,
    FeedingOptions,
    GeofenceOptions,
    GPSOptions,
    HealthOptions,
    NotificationOptions,
    OptionsExportPayload,
    PawControlOptionsData,
    ReconfigureTelemetry,
    SystemOptions,
    WeatherOptions,
    ensure_dog_config_data,
    ensure_dog_modules_config,
    ensure_dog_modules_mapping,
    ensure_dog_options_entry,
    ensure_notification_options,
    is_dog_config_valid,
)

_LOGGER = logging.getLogger(__name__)

PerformanceMode = Literal["minimal", "balanced", "full"]

QUIET_HOURS_FIELD: Final[Literal["quiet_hours"]] = cast(
    Literal["quiet_hours"], CONF_QUIET_HOURS
)
QUIET_START_FIELD: Final[Literal["quiet_start"]] = cast(
    Literal["quiet_start"], CONF_QUIET_START
)
QUIET_END_FIELD: Final[Literal["quiet_end"]] = cast(
    Literal["quiet_end"], CONF_QUIET_END
)
REMINDER_REPEAT_MIN_FIELD: Final[Literal["reminder_repeat_min"]] = cast(
    Literal["reminder_repeat_min"], CONF_REMINDER_REPEAT_MIN
)
_NOTIFICATION_DEFAULTS: Final[Mapping[str, Any]] = MappingProxyType(
    {
        CONF_QUIET_HOURS: True,
        CONF_QUIET_START: "22:00:00",
        CONF_QUIET_END: "07:00:00",
        CONF_REMINDER_REPEAT_MIN: DEFAULT_REMINDER_REPEAT_MIN,
        "priority_notifications": True,
        "mobile_notifications": True,
    }
)
EXTERNAL_INTEGRATIONS_FIELD: Final[Literal["external_integrations"]] = cast(
    Literal["external_integrations"], CONF_EXTERNAL_INTEGRATIONS
)
API_ENDPOINT_FIELD: Final[Literal["api_endpoint"]] = cast(
    Literal["api_endpoint"], CONF_API_ENDPOINT
)
API_TOKEN_FIELD: Final[Literal["api_token"]] = cast(
    Literal["api_token"], CONF_API_TOKEN
)
WEATHER_ENTITY_FIELD: Final[Literal["weather_entity"]] = cast(
    Literal["weather_entity"], CONF_WEATHER_ENTITY
)
GPS_UPDATE_INTERVAL_FIELD: Final[Literal["gps_update_interval"]] = cast(
    Literal["gps_update_interval"], CONF_GPS_UPDATE_INTERVAL
)
GPS_ACCURACY_FILTER_FIELD: Final[Literal["gps_accuracy_filter"]] = cast(
    Literal["gps_accuracy_filter"], CONF_GPS_ACCURACY_FILTER
)
GPS_DISTANCE_FILTER_FIELD: Final[Literal["gps_distance_filter"]] = cast(
    Literal["gps_distance_filter"], CONF_GPS_DISTANCE_FILTER
)


class PawControlOptionsFlow(OptionsFlow):
    """Handle options flow for Paw Control integration with Bronze UX goals.

    This comprehensive options flow allows users to modify all aspects
    of their Paw Control configuration after initial setup. It provides
    organized menu-driven navigation and extensive customization options
    with modern UI patterns and enhanced validation.

    UPDATED: Includes entity profile management for performance optimization
    ENHANCED: GPS and Geofencing configuration per requirements
    """

    _PERFORMANCE_MODES: ClassVar[set[PerformanceMode]] = {
        "minimal",
        "balanced",
        "full",
    }
    _EXPORT_VERSION: ClassVar[int] = 1

    def __init__(self) -> None:
        """Initialize the options flow with enhanced state management."""
        super().__init__()
        self._config_entry: ConfigEntry | None = None
        self._current_dog: DogConfigData | None = None
        self._dogs: list[DogConfigData] = []
        self._navigation_stack: list[str] = []

        # Initialize entity factory and caches for profile calculations
        self._entity_factory = EntityFactory(None)
        self._profile_cache: dict[str, dict[str, Any]] = {}
        self._entity_estimates_cache: dict[str, dict[str, Any]] = {}

    @property
    def _entry(self) -> ConfigEntry:
        """Return the config entry for this options flow."""

        if self._config_entry is None:
            raise RuntimeError(
                "Options flow accessed before being initialized with a config entry"
            )
        return self._config_entry

    def initialize_from_config_entry(self, config_entry: ConfigEntry) -> None:
        """Attach the originating config entry to this options flow."""

        self._config_entry = config_entry
        dogs_data = config_entry.data.get(CONF_DOGS, [])
        self._dogs = []
        for dog in dogs_data:
            if not isinstance(dog, Mapping):
                continue
            normalised = ensure_dog_config_data(dog)
            if normalised is not None:
                self._dogs.append(normalised)

    def _invalidate_profile_caches(self) -> None:
        """Clear cached profile data when configuration changes."""

        self._profile_cache.clear()
        self._entity_estimates_cache.clear()

    def _current_options(self) -> PawControlOptionsData:
        """Return the current config entry options as a typed mapping."""

        return cast(PawControlOptionsData, self._entry.options)

    def _clone_options(self) -> PawControlOptionsData:
        """Return a shallow copy of the current options for mutation."""

        return cast(PawControlOptionsData, dict(self._entry.options))

    def _normalise_options_snapshot(
        self, options: Mapping[str, Any]
    ) -> PawControlOptionsData:
        """Return a typed options mapping with notifications and dog entries coerced."""

        snapshot = cast(PawControlOptionsData, dict(options))

        if CONF_NOTIFICATIONS in snapshot:
            raw_notifications = snapshot.get(CONF_NOTIFICATIONS)
            notifications_source = (
                cast(Mapping[str, Any], raw_notifications)
                if isinstance(raw_notifications, Mapping)
                else {}
            )
            snapshot[CONF_NOTIFICATIONS] = ensure_notification_options(
                notifications_source,
                defaults=_NOTIFICATION_DEFAULTS,
            )

        if "dog_options" in snapshot:
            raw_dog_options = snapshot.get("dog_options")
            typed_dog_options: DogOptionsMap = {}
            if isinstance(raw_dog_options, Mapping):
                for raw_id, raw_entry in raw_dog_options.items():
                    dog_id = str(raw_id)
                    entry_source = (
                        cast(Mapping[str, Any], raw_entry)
                        if isinstance(raw_entry, Mapping)
                        else {}
                    )
                    entry = ensure_dog_options_entry(entry_source, dog_id=dog_id)
                    if dog_id and entry.get(DOG_ID_FIELD) != dog_id:
                        entry[DOG_ID_FIELD] = dog_id
                    typed_dog_options[dog_id] = entry
            snapshot["dog_options"] = typed_dog_options

        return snapshot

    def _normalise_entry_dogs(
        self, dogs: Sequence[Mapping[str, Any]]
    ) -> list[DogConfigData]:
        """Return typed dog configurations for entry persistence."""

        typed_dogs: list[DogConfigData] = []
        for dog in dogs:
            normalised = ensure_dog_config_data(dog)
            if normalised is None:
                raise ValueError("invalid_dog_config")
            typed_dogs.append(normalised)
        return typed_dogs

    def _last_reconfigure_timestamp(self) -> str | None:
        """Return the ISO timestamp recorded for the last reconfigure run."""

        value = self._entry.options.get("last_reconfigure")
        return str(value) if isinstance(value, str) and value else None

    def _reconfigure_telemetry(self) -> ReconfigureTelemetry | None:
        """Return the stored reconfigure telemetry, if available."""

        telemetry = self._entry.options.get("reconfigure_telemetry")
        if isinstance(telemetry, Mapping):
            return cast(ReconfigureTelemetry, telemetry)
        return None

    def _format_local_timestamp(self, timestamp: str | None) -> str:
        """Return a human-friendly representation for an ISO timestamp."""

        if not timestamp:
            return "Never reconfigured"

        parsed = dt_util.parse_datetime(timestamp)
        if parsed is None:
            return timestamp

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        local_dt = dt_util.as_local(parsed)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    def _summarise_health_summary(self, health: Any) -> str:
        """Convert a health summary mapping into a user-facing string."""

        if not isinstance(health, Mapping):
            return "No recent health summary"

        healthy = bool(health.get("healthy", True))
        issues = self._string_sequence(health.get("issues"))
        warnings = self._string_sequence(health.get("warnings"))

        if healthy and not issues and not warnings:
            return "Healthy"

        segments: list[str] = []
        if not healthy:
            segments.append("Issues detected")
        if issues:
            segments.append(f"Issues: {', '.join(issues)}")
        if warnings:
            segments.append(f"Warnings: {', '.join(warnings)}")

        return " | ".join(segments)

    def _string_sequence(self, value: Any) -> list[str]:
        """Return a normalised list of strings for sequence-based metadata."""

        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            return [str(item) for item in value if item not in (None, "")]
        return []

    def _get_reconfigure_description_placeholders(self) -> dict[str, str]:
        """Return placeholders describing the latest reconfigure telemetry."""

        telemetry = self._reconfigure_telemetry()
        timestamp = self._format_local_timestamp(
            (telemetry or {}).get("timestamp") if telemetry else None
        )
        if not telemetry:
            return {
                "last_reconfigure": timestamp,
                "reconfigure_requested_profile": "Not recorded",
                "reconfigure_previous_profile": "Not recorded",
                "reconfigure_entities": "0",
                "reconfigure_dogs": "0",
                "reconfigure_health": "No recent health summary",
                "reconfigure_warnings": "None",
            }

        requested_profile = str(telemetry.get("requested_profile", "")) or "Unknown"
        previous_profile = str(telemetry.get("previous_profile", "")) or "Unknown"
        dogs_count = telemetry.get("dogs_count")
        estimated_entities = telemetry.get("estimated_entities")
        warnings = self._string_sequence(telemetry.get("compatibility_warnings"))
        health_summary = telemetry.get("health_summary")

        last_recorded = telemetry.get("timestamp") or self._last_reconfigure_timestamp()

        return {
            "last_reconfigure": self._format_local_timestamp(
                str(last_recorded) if last_recorded else None
            ),
            "reconfigure_requested_profile": requested_profile,
            "reconfigure_previous_profile": previous_profile,
            "reconfigure_entities": (
                str(int(estimated_entities))
                if isinstance(estimated_entities, int | float)
                else "0"
            ),
            "reconfigure_dogs": (
                str(int(dogs_count)) if isinstance(dogs_count, int | float) else "0"
            ),
            "reconfigure_health": self._summarise_health_summary(health_summary),
            "reconfigure_warnings": ", ".join(warnings) if warnings else "None",
        }

    def _normalise_export_value(self, value: Any) -> Any:
        """Convert complex values into JSON-serialisable primitives."""

        if isinstance(value, Mapping):
            return {
                str(key): self._normalise_export_value(subvalue)
                for key, subvalue in value.items()
            }
        if isinstance(value, list | tuple | set | frozenset):
            return [self._normalise_export_value(item) for item in value]
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        return str(value)

    def _sanitise_imported_dog(self, raw: Mapping[str, Any]) -> DogConfigData:
        """Normalise and validate a dog payload from an import file."""

        normalised = cast(
            DogConfigData,
            self._normalise_export_value(dict(raw)),
        )

        modules_raw = normalised.get(CONF_MODULES)
        if modules_raw is not None and not isinstance(modules_raw, Mapping):
            raise ValueError("dog_invalid_modules")

        modules = ensure_dog_modules_config(normalised)
        normalised[DOG_MODULES_FIELD] = modules

        if not is_dog_config_valid(normalised):
            raise ValueError("dog_invalid_config")

        return normalised

    def _build_export_payload(self) -> OptionsExportPayload:
        """Serialise the current configuration into an export payload."""

        typed_options = self._normalise_options_snapshot(self._clone_options())
        options = cast(
            PawControlOptionsData,
            self._normalise_export_value(typed_options),
        )

        dogs_payload: list[DogConfigData] = []
        for raw in self._entry.data.get(CONF_DOGS, []):
            if not isinstance(raw, Mapping):
                continue
            normalised = cast(
                DogConfigData,
                self._normalise_export_value(dict(raw)),
            )
            dog_id = normalised.get(CONF_DOG_ID)
            if not isinstance(dog_id, str) or not dog_id.strip():
                continue
            modules_mapping = ensure_dog_modules_mapping(normalised)
            if modules_mapping:
                normalised[DOG_MODULES_FIELD] = cast(
                    DogModulesConfig, dict(modules_mapping)
                )
            elif DOG_MODULES_FIELD in normalised:
                normalised.pop(DOG_MODULES_FIELD, None)
            dogs_payload.append(normalised)

        payload: OptionsExportPayload = {
            "version": cast(Literal[1], self._EXPORT_VERSION),
            "options": options,
            "dogs": dogs_payload,
            "created_at": datetime.now(UTC).isoformat(),
        }
        return payload

    def _validate_import_payload(self, payload: Any) -> OptionsExportPayload:
        """Validate and normalise an imported payload."""

        if not isinstance(payload, Mapping):
            raise ValueError("payload_not_mapping")

        version = payload.get("version")
        if version != self._EXPORT_VERSION:
            raise ValueError("unsupported_version")

        options_raw = payload.get("options")
        if not isinstance(options_raw, Mapping):
            raise ValueError("options_missing")

        sanitised_options = cast(
            PawControlOptionsData,
            self._normalise_export_value(dict(options_raw)),
        )

        merged_candidate: dict[str, Any] = dict(self._clone_options())
        merged_candidate.update(sanitised_options)
        merged_options = self._normalise_options_snapshot(merged_candidate)

        dogs_raw = payload.get("dogs", [])
        if not isinstance(dogs_raw, list):
            raise ValueError("dogs_invalid")

        dogs_payload: list[DogConfigData] = []
        seen_ids: set[str] = set()
        for raw in dogs_raw:
            if not isinstance(raw, Mapping):
                raise ValueError("dog_invalid")
            normalised = self._sanitise_imported_dog(raw)
            dog_id = normalised.get(CONF_DOG_ID)
            if not isinstance(dog_id, str) or not dog_id.strip():
                raise ValueError("dog_missing_id")
            if dog_id in seen_ids:
                raise ValueError("dog_duplicate")
            seen_ids.add(dog_id)
            dogs_payload.append(normalised)

        created_at = payload.get("created_at")
        if not isinstance(created_at, str) or not created_at:
            created_at = datetime.now(UTC).isoformat()

        result: OptionsExportPayload = {
            "version": cast(Literal[1], self._EXPORT_VERSION),
            "options": merged_options,
            "dogs": dogs_payload,
            "created_at": created_at,
        }
        return result

    def _current_geofence_options(self) -> GeofenceOptions:
        """Fetch the stored geofence configuration as a typed mapping."""

        raw = self._current_options().get("geofence_settings", {})
        if isinstance(raw, Mapping):
            return cast(GeofenceOptions, dict(raw))
        return cast(GeofenceOptions, {})

    def _current_notification_options(self) -> NotificationOptions:
        """Fetch the stored notification configuration as a typed mapping."""

        raw = self._current_options().get(CONF_NOTIFICATIONS, {})
        payload: Mapping[str, Any] = (
            cast(Mapping[str, Any], raw) if isinstance(raw, Mapping) else {}
        )
        return ensure_notification_options(payload, defaults=_NOTIFICATION_DEFAULTS)

    def _current_weather_options(self) -> WeatherOptions:
        """Return the stored weather configuration with root fallbacks."""

        options = self._current_options()
        raw = options.get("weather_settings", {})
        if isinstance(raw, Mapping):
            current = cast(WeatherOptions, dict(raw))
        else:
            current = cast(WeatherOptions, {})

        if (
            WEATHER_ENTITY_FIELD not in current
            and (entity := options.get(CONF_WEATHER_ENTITY))
            and isinstance(entity, str)
        ):
            candidate = entity.strip()
            if candidate:
                current[WEATHER_ENTITY_FIELD] = candidate

        return current

    def _current_feeding_options(self) -> FeedingOptions:
        """Return the stored feeding configuration as a typed mapping."""

        raw = self._current_options().get("feeding_settings", {})
        if isinstance(raw, Mapping):
            return cast(FeedingOptions, dict(raw))
        return cast(FeedingOptions, {})

    def _current_gps_options(self) -> GPSOptions:
        """Return the stored GPS configuration with legacy fallbacks."""

        options = self._current_options()
        raw = options.get("gps_settings", {})
        if isinstance(raw, Mapping):
            current = cast(GPSOptions, dict(raw))
        else:
            current = cast(GPSOptions, {})

        if (
            GPS_UPDATE_INTERVAL_FIELD not in current
            and (interval := options.get(CONF_GPS_UPDATE_INTERVAL)) is not None
        ):
            if isinstance(interval, int):
                current[GPS_UPDATE_INTERVAL_FIELD] = interval
            elif isinstance(interval, float):
                current[GPS_UPDATE_INTERVAL_FIELD] = int(interval)
            elif isinstance(interval, str):
                with suppress(ValueError):
                    current[GPS_UPDATE_INTERVAL_FIELD] = int(interval)

        if (
            GPS_ACCURACY_FILTER_FIELD not in current
            and (accuracy := options.get(CONF_GPS_ACCURACY_FILTER)) is not None
        ):
            if isinstance(accuracy, int | float):
                current[GPS_ACCURACY_FILTER_FIELD] = float(accuracy)
            elif isinstance(accuracy, str):
                with suppress(ValueError):
                    current[GPS_ACCURACY_FILTER_FIELD] = float(accuracy)

        if (
            GPS_DISTANCE_FILTER_FIELD not in current
            and (distance := options.get(CONF_GPS_DISTANCE_FILTER)) is not None
        ):
            if isinstance(distance, int | float):
                current[GPS_DISTANCE_FILTER_FIELD] = float(distance)
            elif isinstance(distance, str):
                with suppress(ValueError):
                    current[GPS_DISTANCE_FILTER_FIELD] = float(distance)

        current.setdefault("gps_enabled", True)
        current.setdefault("route_recording", True)
        current.setdefault("route_history_days", 30)
        current.setdefault("auto_track_walks", True)

        return current

    def _current_dog_options(self) -> DogOptionsMap:
        """Return the stored per-dog overrides keyed by dog ID."""

        raw = self._current_options().get("dog_options", {})
        if not isinstance(raw, Mapping):
            return {}

        dog_options: DogOptionsMap = {}
        for dog_id, value in raw.items():
            if not isinstance(value, Mapping):
                continue
            entry = ensure_dog_options_entry(value, dog_id=str(dog_id))
            if entry:
                dog_options[str(dog_id)] = entry

        return dog_options

    def _current_health_options(self) -> HealthOptions:
        """Return the stored health configuration as a typed mapping."""

        raw = self._current_options().get("health_settings", {})
        if isinstance(raw, Mapping):
            return cast(HealthOptions, dict(raw))
        return cast(HealthOptions, {})

    def _current_system_options(self) -> SystemOptions:
        """Return persisted system settings metadata."""

        raw = self._current_options().get("system_settings", {})
        if isinstance(raw, Mapping):
            return cast(SystemOptions, dict(raw))
        return cast(SystemOptions, {})

    def _current_dashboard_options(self) -> DashboardOptions:
        """Return the stored dashboard configuration."""

        raw = self._current_options().get("dashboard_settings", {})
        if isinstance(raw, Mapping):
            return cast(DashboardOptions, dict(raw))
        return cast(DashboardOptions, {})

    def _current_advanced_options(self) -> AdvancedOptions:
        """Return advanced configuration merged with root fallbacks."""

        options = self._current_options()
        raw = options.get("advanced_settings", {})
        if isinstance(raw, Mapping):
            current = cast(AdvancedOptions, dict(raw))
        else:
            current = cast(AdvancedOptions, {})

        if "performance_mode" not in current:
            current["performance_mode"] = self._normalize_performance_mode(
                options.get("performance_mode"), None
            )
        if "debug_logging" not in current:
            current["debug_logging"] = self._coerce_bool(
                options.get("debug_logging"), False
            )
        if "data_retention_days" not in current:
            current["data_retention_days"] = self._coerce_int(
                options.get("data_retention_days"), 90
            )
        if "auto_backup" not in current:
            current["auto_backup"] = self._coerce_bool(
                options.get("auto_backup"), False
            )
        if "experimental_features" not in current:
            current["experimental_features"] = self._coerce_bool(
                options.get("experimental_features"), False
            )
        if EXTERNAL_INTEGRATIONS_FIELD not in current:
            current[EXTERNAL_INTEGRATIONS_FIELD] = self._coerce_bool(
                options.get(CONF_EXTERNAL_INTEGRATIONS), False
            )
        endpoint = options.get(CONF_API_ENDPOINT, "")
        if API_ENDPOINT_FIELD not in current:
            current[API_ENDPOINT_FIELD] = endpoint if isinstance(endpoint, str) else ""
        token = options.get(CONF_API_TOKEN, "")
        if API_TOKEN_FIELD not in current:
            current[API_TOKEN_FIELD] = token if isinstance(token, str) else ""

        return current

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        """Return a boolean value using Home Assistant style truthiness rules."""

        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "on", "yes"}
        return bool(value)

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        """Return an integer, falling back to the provided default on error."""

        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    @staticmethod
    def _coerce_time_string(value: Any, default: str) -> str:
        """Normalise selector values into Home Assistant time strings."""

        if value is None:
            return default
        if isinstance(value, str):
            return value
        iso_format = getattr(value, "isoformat", None)
        if callable(iso_format):
            return str(iso_format())
        return default

    @staticmethod
    def _coerce_optional_float(value: Any, default: float | None) -> float | None:
        """Return a float or ``None`` when conversion fails."""

        if value is None:
            return default
        if isinstance(value, float | int):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return default
        return default

    def _normalize_performance_mode(
        self, value: Any, current: str | None
    ) -> PerformanceMode:
        """Ensure performance mode selections remain within supported values."""

        if isinstance(value, str):
            candidate = value.lower()
            if candidate in self._PERFORMANCE_MODES:
                return cast(PerformanceMode, candidate)

        if isinstance(current, str):
            existing = current.lower()
            if existing in self._PERFORMANCE_MODES:
                return cast(PerformanceMode, existing)

        return "balanced"

    def _coerce_clamped_int(
        self, value: Any, default: int, *, minimum: int, maximum: int
    ) -> int:
        """Normalise numeric selector input and clamp to an allowed range."""

        candidate = self._coerce_int(value, default)
        if candidate < minimum:
            return minimum
        if candidate > maximum:
            return maximum
        return candidate

    @staticmethod
    def _normalize_choice(value: Any, *, valid: set[str], default: str) -> str:
        """Return a validated selector choice, falling back to ``default``."""

        if isinstance(value, str):
            candidate = value.strip().lower()
            if candidate in valid:
                return candidate

        if isinstance(default, str):
            fallback = default.strip().lower()
            if fallback in valid:
                return fallback

        return sorted(valid)[0]

    def _build_geofence_settings(
        self,
        user_input: Mapping[str, Any],
        current: GeofenceOptions,
        *,
        radius: int,
        default_lat: float | None,
        default_lon: float | None,
    ) -> GeofenceOptions:
        """Create a typed geofence payload from the submitted form data."""

        lat_source = user_input.get("geofence_lat")
        lon_source = user_input.get("geofence_lon")
        lat = self._coerce_optional_float(
            lat_source, current.get("geofence_lat", default_lat)
        )
        lon = self._coerce_optional_float(
            lon_source, current.get("geofence_lon", default_lon)
        )

        geofence: GeofenceOptions = {
            "geofencing_enabled": self._coerce_bool(
                user_input.get("geofencing_enabled"),
                current.get("geofencing_enabled", False),
            ),
            "use_home_location": self._coerce_bool(
                user_input.get("use_home_location"),
                current.get("use_home_location", True),
            ),
            "geofence_lat": lat,
            "geofence_lon": lon,
            "geofence_radius_m": radius,
            "geofence_alerts_enabled": self._coerce_bool(
                user_input.get("geofence_alerts_enabled"),
                current.get("geofence_alerts_enabled", True),
            ),
            "safe_zone_alerts": self._coerce_bool(
                user_input.get("safe_zone_alerts"),
                current.get("safe_zone_alerts", True),
            ),
            "restricted_zone_alerts": self._coerce_bool(
                user_input.get("restricted_zone_alerts"),
                current.get("restricted_zone_alerts", True),
            ),
            "zone_entry_notifications": self._coerce_bool(
                user_input.get("zone_entry_notifications"),
                current.get("zone_entry_notifications", True),
            ),
            "zone_exit_notifications": self._coerce_bool(
                user_input.get("zone_exit_notifications"),
                current.get("zone_exit_notifications", True),
            ),
        }

        return geofence

    def _build_notification_settings(
        self,
        user_input: Mapping[str, Any],
        current: NotificationOptions,
    ) -> NotificationOptions:
        """Create a typed notification payload from submitted form data."""

        notifications: NotificationOptions = {
            QUIET_HOURS_FIELD: self._coerce_bool(
                user_input.get("quiet_hours"),
                current.get(QUIET_HOURS_FIELD, True),
            ),
            QUIET_START_FIELD: self._coerce_time_string(
                user_input.get("quiet_start"),
                current.get(QUIET_START_FIELD, "22:00:00"),
            ),
            QUIET_END_FIELD: self._coerce_time_string(
                user_input.get("quiet_end"),
                current.get(QUIET_END_FIELD, "07:00:00"),
            ),
            REMINDER_REPEAT_MIN_FIELD: self._coerce_int(
                user_input.get("reminder_repeat_min"),
                current.get(REMINDER_REPEAT_MIN_FIELD, DEFAULT_REMINDER_REPEAT_MIN),
            ),
            "priority_notifications": self._coerce_bool(
                user_input.get("priority_notifications"),
                current.get("priority_notifications", True),
            ),
            "mobile_notifications": self._coerce_bool(
                user_input.get("mobile_notifications"),
                current.get("mobile_notifications", True),
            ),
        }

        return notifications

    def _build_weather_settings(
        self,
        user_input: Mapping[str, Any],
        current: WeatherOptions,
    ) -> WeatherOptions:
        """Create a typed weather configuration payload from submitted data."""

        raw_entity = user_input.get("weather_entity")
        entity: str | None
        if isinstance(raw_entity, str):
            candidate = raw_entity.strip()
            entity = None if not candidate or candidate.lower() == "none" else candidate
        else:
            entity = current.get(CONF_WEATHER_ENTITY)

        interval_default = current.get("weather_update_interval", 60)
        interval = self._coerce_clamped_int(
            user_input.get("weather_update_interval"),
            interval_default,
            minimum=15,
            maximum=1440,
        )
        threshold = self._normalize_choice(
            user_input.get("notification_threshold"),
            valid={"low", "moderate", "high"},
            default=current.get("notification_threshold", "moderate"),
        )

        weather: WeatherOptions = {
            WEATHER_ENTITY_FIELD: entity,
            "weather_health_monitoring": self._coerce_bool(
                user_input.get("weather_health_monitoring"),
                current.get(
                    "weather_health_monitoring", DEFAULT_WEATHER_HEALTH_MONITORING
                ),
            ),
            "weather_alerts": self._coerce_bool(
                user_input.get("weather_alerts"),
                current.get("weather_alerts", DEFAULT_WEATHER_ALERTS),
            ),
            "weather_update_interval": interval,
            "temperature_alerts": self._coerce_bool(
                user_input.get("temperature_alerts"),
                current.get("temperature_alerts", True),
            ),
            "uv_alerts": self._coerce_bool(
                user_input.get("uv_alerts"),
                current.get("uv_alerts", True),
            ),
            "humidity_alerts": self._coerce_bool(
                user_input.get("humidity_alerts"),
                current.get("humidity_alerts", True),
            ),
            "wind_alerts": self._coerce_bool(
                user_input.get("wind_alerts"),
                current.get("wind_alerts", False),
            ),
            "storm_alerts": self._coerce_bool(
                user_input.get("storm_alerts"),
                current.get("storm_alerts", True),
            ),
            "breed_specific_recommendations": self._coerce_bool(
                user_input.get("breed_specific_recommendations"),
                current.get("breed_specific_recommendations", True),
            ),
            "health_condition_adjustments": self._coerce_bool(
                user_input.get("health_condition_adjustments"),
                current.get("health_condition_adjustments", True),
            ),
            "auto_activity_adjustments": self._coerce_bool(
                user_input.get("auto_activity_adjustments"),
                current.get("auto_activity_adjustments", False),
            ),
            "notification_threshold": threshold,
        }

        return weather

    def _build_feeding_settings(
        self,
        user_input: Mapping[str, Any],
        current: FeedingOptions,
    ) -> FeedingOptions:
        """Create a typed feeding configuration payload from submitted data."""

        meals = self._coerce_clamped_int(
            user_input.get("meals_per_day"),
            current.get("default_meals_per_day", 2),
            minimum=1,
            maximum=6,
        )

        feeding: FeedingOptions = {
            "default_meals_per_day": meals,
            "feeding_reminders": self._coerce_bool(
                user_input.get("feeding_reminders"),
                current.get("feeding_reminders", True),
            ),
            "portion_tracking": self._coerce_bool(
                user_input.get("portion_tracking"),
                current.get("portion_tracking", True),
            ),
            "calorie_tracking": self._coerce_bool(
                user_input.get("calorie_tracking"),
                current.get("calorie_tracking", True),
            ),
            "auto_schedule": self._coerce_bool(
                user_input.get("auto_schedule"),
                current.get("auto_schedule", False),
            ),
        }

        return feeding

    def _build_health_settings(
        self,
        user_input: Mapping[str, Any],
        current: HealthOptions,
    ) -> HealthOptions:
        """Create a typed health configuration payload from submitted data."""

        health: HealthOptions = {
            "weight_tracking": self._coerce_bool(
                user_input.get("weight_tracking"),
                current.get("weight_tracking", True),
            ),
            "medication_reminders": self._coerce_bool(
                user_input.get("medication_reminders"),
                current.get("medication_reminders", True),
            ),
            "vet_reminders": self._coerce_bool(
                user_input.get("vet_reminders"),
                current.get("vet_reminders", True),
            ),
            "grooming_reminders": self._coerce_bool(
                user_input.get("grooming_reminders"),
                current.get("grooming_reminders", True),
            ),
            "health_alerts": self._coerce_bool(
                user_input.get("health_alerts"),
                current.get("health_alerts", True),
            ),
        }

        return health

    def _build_system_settings(
        self,
        user_input: Mapping[str, Any],
        current: SystemOptions,
        *,
        reset_default: str,
    ) -> tuple[SystemOptions, str]:
        """Create typed system settings and the reset time string."""

        retention = self._coerce_clamped_int(
            user_input.get("data_retention_days"),
            current.get("data_retention_days", 90),
            minimum=30,
            maximum=365,
        )
        performance_mode = self._normalize_performance_mode(
            user_input.get("performance_mode"),
            current.get("performance_mode"),
        )

        system: SystemOptions = {
            "data_retention_days": retention,
            "auto_backup": self._coerce_bool(
                user_input.get("auto_backup"),
                current.get("auto_backup", False),
            ),
            "performance_mode": performance_mode,
        }

        reset_time = self._coerce_time_string(
            user_input.get("reset_time"), reset_default
        )
        return system, reset_time

    def _build_dashboard_settings(
        self,
        user_input: Mapping[str, Any],
        current: DashboardOptions,
        *,
        default_mode: str,
    ) -> tuple[DashboardOptions, str]:
        """Create typed dashboard configuration and selected mode."""

        valid_modes = {option["value"] for option in DASHBOARD_MODE_SELECTOR_OPTIONS}
        mode = self._normalize_choice(
            user_input.get("dashboard_mode"),
            valid=valid_modes,
            default=default_mode,
        )

        dashboard: DashboardOptions = {
            "show_statistics": self._coerce_bool(
                user_input.get("show_statistics"),
                current.get("show_statistics", True),
            ),
            "show_alerts": self._coerce_bool(
                user_input.get("show_alerts"),
                current.get("show_alerts", True),
            ),
            "compact_mode": self._coerce_bool(
                user_input.get("compact_mode"),
                current.get("compact_mode", False),
            ),
            "show_maps": self._coerce_bool(
                user_input.get("show_maps"),
                current.get("show_maps", True),
            ),
        }

        return dashboard, mode

    def _build_advanced_settings(
        self,
        user_input: Mapping[str, Any],
        current: AdvancedOptions,
    ) -> AdvancedOptions:
        """Create typed advanced configuration metadata."""

        retention = self._coerce_clamped_int(
            user_input.get("data_retention_days"),
            current.get("data_retention_days", 90),
            minimum=30,
            maximum=365,
        )

        endpoint_raw = user_input.get(
            CONF_API_ENDPOINT, current.get(CONF_API_ENDPOINT, "")
        )
        endpoint = (
            endpoint_raw.strip()
            if isinstance(endpoint_raw, str)
            else current.get(CONF_API_ENDPOINT, "")
        )
        token_raw = user_input.get(CONF_API_TOKEN, current.get(CONF_API_TOKEN, ""))
        token = (
            token_raw.strip()
            if isinstance(token_raw, str)
            else current.get(CONF_API_TOKEN, "")
        )

        advanced: AdvancedOptions = {
            "performance_mode": self._normalize_performance_mode(
                user_input.get("performance_mode"),
                current.get("performance_mode"),
            ),
            "debug_logging": self._coerce_bool(
                user_input.get("debug_logging"),
                current.get("debug_logging", False),
            ),
            "data_retention_days": retention,
            "auto_backup": self._coerce_bool(
                user_input.get("auto_backup"),
                current.get("auto_backup", False),
            ),
            "experimental_features": self._coerce_bool(
                user_input.get("experimental_features"),
                current.get("experimental_features", False),
            ),
            EXTERNAL_INTEGRATIONS_FIELD: self._coerce_bool(
                user_input.get(CONF_EXTERNAL_INTEGRATIONS),
                current.get(EXTERNAL_INTEGRATIONS_FIELD, False),
            ),
            API_ENDPOINT_FIELD: endpoint,
            API_TOKEN_FIELD: token,
        }

        return advanced

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
                "entity_profiles",  # NEW: Profile management
                "manage_dogs",
                "performance_settings",  # NEW: Performance & profiles
                "gps_settings",
                "geofence_settings",  # NEW: Geofencing configuration
                "weather_settings",  # NEW: Weather configuration
                "notifications",
                "feeding_settings",
                "health_settings",
                "system_settings",
                "dashboard_settings",
                "advanced_settings",
                "import_export",
            ],
        )

    # NEW: Geofencing configuration step per requirements
    async def async_step_geofence_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure geofencing and zone settings.

        NEW: Implements missing geofencing configuration per fahrplan.txt requirements.
        Provides geofence_lat, geofence_lon, geofence_radius, and alert configuration.
        """
        if user_input is not None:
            try:
                # Validate geofence radius
                radius = self._coerce_int(user_input.get("geofence_radius_m"), 50)
                if radius < MIN_GEOFENCE_RADIUS or radius > MAX_GEOFENCE_RADIUS:
                    return self.async_show_form(
                        step_id="geofence_settings",
                        data_schema=self._get_geofence_settings_schema(user_input),
                        errors={"geofence_radius_m": "radius_out_of_range"},
                    )

                new_options = self._clone_options()
                current_geofence = self._current_geofence_options()
                default_lat = (
                    float(self.hass.config.latitude)
                    if self.hass.config.latitude is not None
                    else None
                )
                default_lon = (
                    float(self.hass.config.longitude)
                    if self.hass.config.longitude is not None
                    else None
                )
                new_options["geofence_settings"] = self._build_geofence_settings(
                    user_input,
                    current_geofence,
                    radius=radius,
                    default_lat=default_lat,
                    default_lon=default_lon,
                )

                typed_options = self._normalise_options_snapshot(new_options)

                return self.async_create_entry(title="", data=typed_options)

            except Exception as err:
                _LOGGER.error("Error updating geofence settings: %s", err)
                return self.async_show_form(
                    step_id="geofence_settings",
                    data_schema=self._get_geofence_settings_schema(user_input),
                    errors={"base": "geofence_update_failed"},
                )

        return self.async_show_form(
            step_id="geofence_settings",
            data_schema=self._get_geofence_settings_schema(),
            description_placeholders=self._get_geofence_description_placeholders(),
        )

    def _get_geofence_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get geofencing settings schema with current values."""
        current_geofence = self._current_geofence_options()
        current_values = user_input or {}

        home_lat_raw = self.hass.config.latitude
        home_lon_raw = self.hass.config.longitude
        home_lat = float(home_lat_raw) if home_lat_raw is not None else 0.0
        home_lon = float(home_lon_raw) if home_lon_raw is not None else 0.0
        default_lat = current_geofence.get("geofence_lat")
        if default_lat is None:
            default_lat = home_lat
        default_lon = current_geofence.get("geofence_lon")
        if default_lon is None:
            default_lon = home_lon

        return vol.Schema(
            {
                vol.Optional(
                    "geofencing_enabled",
                    default=current_values.get(
                        "geofencing_enabled",
                        current_geofence.get("geofencing_enabled", False),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "use_home_location",
                    default=current_values.get(
                        "use_home_location",
                        current_geofence.get("use_home_location", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "geofence_lat",
                    default=current_values.get("geofence_lat", default_lat),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-90.0,
                        max=90.0,
                        step=0.000001,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "geofence_lon",
                    default=current_values.get("geofence_lon", default_lon),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-180.0,
                        max=180.0,
                        step=0.000001,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "geofence_radius_m",
                    default=current_values.get(
                        "geofence_radius_m",
                        current_geofence.get("geofence_radius_m", 50),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_GEOFENCE_RADIUS,
                        max=MAX_GEOFENCE_RADIUS,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="meters",
                    )
                ),
                vol.Optional(
                    "geofence_alerts_enabled",
                    default=current_values.get(
                        "geofence_alerts_enabled",
                        current_geofence.get("geofence_alerts_enabled", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "safe_zone_alerts",
                    default=current_values.get(
                        "safe_zone_alerts",
                        current_geofence.get("safe_zone_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "restricted_zone_alerts",
                    default=current_values.get(
                        "restricted_zone_alerts",
                        current_geofence.get("restricted_zone_alerts", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "zone_entry_notifications",
                    default=current_values.get(
                        "zone_entry_notifications",
                        current_geofence.get("zone_entry_notifications", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "zone_exit_notifications",
                    default=current_values.get(
                        "zone_exit_notifications",
                        current_geofence.get("zone_exit_notifications", True),
                    ),
                ): selector.BooleanSelector(),
            }
        )

    def _get_geofence_description_placeholders(self) -> dict[str, str]:
        """Get description placeholders for geofencing configuration."""
        current_geofence = self._current_geofence_options()

        home_lat_raw = self.hass.config.latitude
        home_lon_raw = self.hass.config.longitude
        home_lat = float(home_lat_raw) if home_lat_raw is not None else 0.0
        home_lon = float(home_lon_raw) if home_lon_raw is not None else 0.0

        geofencing_enabled = current_geofence.get("geofencing_enabled", False)
        current_lat = self._coerce_optional_float(
            current_geofence.get("geofence_lat"), home_lat
        )
        if current_lat is None:
            current_lat = home_lat
        current_lon = self._coerce_optional_float(
            current_geofence.get("geofence_lon"), home_lon
        )
        if current_lon is None:
            current_lon = home_lon
        current_radius = self._coerce_int(current_geofence.get("geofence_radius_m"), 50)

        status = "Enabled" if geofencing_enabled else "Disabled"
        location_desc = f"Lat: {current_lat:.6f}, Lon: {current_lon:.6f}"

        return {
            "current_status": status,
            "current_location": location_desc,
            "current_radius": str(current_radius),
            "home_location": f"Lat: {home_lat:.6f}, Lon: {home_lon:.6f}",
            "radius_range": f"{MIN_GEOFENCE_RADIUS}-{MAX_GEOFENCE_RADIUS}",
            "dogs_with_gps": str(
                sum(
                    1
                    for dog in self._dogs
                    if ensure_dog_modules_mapping(dog).get(MODULE_GPS, False)
                )
            ),
        }

    async def async_step_entity_profiles(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure entity profiles for performance optimization.

        NEW: Allows users to select entity profiles that determine
        how many entities are created per dog.
        """
        if user_input is not None:
            try:
                current_profile = validate_profile_selection(user_input)
                preview_estimate = user_input.get("preview_estimate", False)

                if preview_estimate:
                    # Show entity count preview
                    return await self.async_step_profile_preview(
                        {"profile": current_profile}
                    )

                # Save the profile selection
                merged_options = {
                    **self._entry.options,
                    "entity_profile": current_profile,
                }
                typed_options = self._normalise_options_snapshot(merged_options)
                self._invalidate_profile_caches()

                return self.async_create_entry(title="", data=typed_options)

            except vol.Invalid as err:
                _LOGGER.warning("Invalid profile selection in options flow: %s", err)
                return self.async_show_form(
                    step_id="entity_profiles",
                    data_schema=self._get_entity_profiles_schema(user_input),
                    errors={"base": "invalid_profile"},
                )
            except Exception as err:
                _LOGGER.error("Error updating entity profile: %s", err)
                return self.async_show_form(
                    step_id="entity_profiles",
                    data_schema=self._get_entity_profiles_schema(user_input),
                    errors={"base": "profile_update_failed"},
                )

        return self.async_show_form(
            step_id="entity_profiles",
            data_schema=self._get_entity_profiles_schema(),
            description_placeholders=self._get_profile_description_placeholders(),
        )

    def _get_entity_profiles_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get entity profiles schema with current values."""
        current_options = self._entry.options
        current_values = user_input or {}
        current_profile = current_values.get(
            "entity_profile",
            current_options.get("entity_profile", DEFAULT_PROFILE),
        )

        if current_profile not in ENTITY_PROFILES:
            current_profile = DEFAULT_PROFILE

        profile_options = get_profile_selector_options()

        return vol.Schema(
            {
                vol.Required(
                    "entity_profile", default=current_profile
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=profile_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "preview_estimate", default=False
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
            }
        )

    def _get_profile_description_placeholders_cached(self) -> dict[str, str]:
        """Get description placeholders with caching for better performance."""

        current_dogs = self._entry.data.get(CONF_DOGS, [])
        current_profile = self._entry.options.get("entity_profile", DEFAULT_PROFILE)
        telemetry = self._reconfigure_telemetry()
        telemetry_digest = ""
        if telemetry:
            try:
                telemetry_digest = json.dumps(
                    self._normalise_export_value(dict(telemetry)), sort_keys=True
                )
            except (TypeError, ValueError):
                telemetry_digest = repr(sorted(telemetry.items()))
        cache_key = (
            f"{current_profile}_{len(current_dogs)}_"
            f"{hash(json.dumps(current_dogs, sort_keys=True))}_"
            f"{self._last_reconfigure_timestamp() or ''}_"
            f"{hash(telemetry_digest)}"
        )

        cached = self._profile_cache.get(cache_key)
        if cached is not None:
            return cached

        total_estimate = 0
        profile_compatibility_issues: list[str] = []

        profile_info = ENTITY_PROFILES.get(
            current_profile, ENTITY_PROFILES[DEFAULT_PROFILE]
        )
        max_entities = profile_info["max_entities"]

        for dog in current_dogs:
            modules = ensure_dog_modules_mapping(dog)
            estimate = self._entity_factory.estimate_entity_count(
                current_profile, modules
            )
            total_estimate += estimate

            if not self._entity_factory.validate_profile_for_modules(
                current_profile, modules
            ):
                dog_name = dog.get(CONF_DOG_NAME, "Unknown")
                profile_compatibility_issues.append(
                    f"{dog_name} modules may not be optimal for {current_profile}"
                )

        total_capacity = max_entities * len(current_dogs)
        utilization = (
            f"{(total_estimate / total_capacity * 100):.1f}"
            if total_capacity > 0
            else "0"
        )

        placeholders = {
            "current_profile": current_profile,
            "current_description": profile_info["description"],
            "dogs_count": str(len(current_dogs)),
            "estimated_entities": str(total_estimate),
            "max_entities_per_dog": str(max_entities),
            "performance_impact": self._get_performance_impact_description(
                current_profile
            ),
            "compatibility_warnings": "; ".join(profile_compatibility_issues)
            if profile_compatibility_issues
            else "No compatibility issues",
            "utilization_percentage": utilization,
        }

        placeholders.update(self._get_reconfigure_description_placeholders())

        self._profile_cache[cache_key] = placeholders
        return placeholders

    def _get_profile_description_placeholders(self) -> dict[str, str]:
        """Get description placeholders for profile selection."""

        return self._get_profile_description_placeholders_cached()

    def _get_performance_impact_description(self, profile: str) -> str:
        """Get performance impact description for profile."""
        impact_descriptions = {
            "basic": "Minimal resource usage, fastest startup",
            "standard": "Balanced performance and features",
            "advanced": "Full features, higher resource usage",
            "gps_focus": "Optimized for GPS tracking",
            "health_focus": "Optimized for health monitoring",
        }
        return impact_descriptions.get(profile, "Balanced performance")

    async def _calculate_profile_preview_optimized(
        self, profile: str
    ) -> dict[str, Any]:
        """Calculate profile preview with optimized performance."""

        current_dogs = self._entry.data.get(CONF_DOGS, [])
        cache_key = (
            f"{profile}_{len(current_dogs)}_"
            f"{hash(json.dumps(current_dogs, sort_keys=True))}"
        )

        cached_preview = self._entity_estimates_cache.get(cache_key)
        if cached_preview is not None:
            return cached_preview

        entity_breakdown: list[dict[str, Any]] = []
        total_entities = 0
        performance_score = 100.0

        profile_info = ENTITY_PROFILES.get(profile, ENTITY_PROFILES["standard"])
        max_entities = profile_info["max_entities"]

        for dog in current_dogs:
            dog_name = dog.get(CONF_DOG_NAME, "Unknown")
            dog_id = dog.get(CONF_DOG_ID, "unknown")
            modules = ensure_dog_modules_mapping(dog)

            estimate = self._entity_factory.estimate_entity_count(profile, modules)
            total_entities += estimate

            enabled_modules = [module for module, enabled in modules.items() if enabled]
            utilization = (estimate / max_entities) * 100 if max_entities > 0 else 0

            entity_breakdown.append(
                {
                    "dog_name": dog_name,
                    "dog_id": dog_id,
                    "entities": estimate,
                    "modules": enabled_modules,
                    "utilization": utilization,
                }
            )

            if utilization > 80:
                performance_score -= 10
            elif utilization > 60:
                performance_score -= 5

        current_profile = self._entry.options.get("entity_profile", "standard")
        if profile == current_profile:
            current_total = total_entities
        else:
            current_total = 0
            for dog in current_dogs:
                modules = ensure_dog_modules_mapping(dog)
                current_total += self._entity_factory.estimate_entity_count(
                    current_profile, modules
                )

        entity_difference = total_entities - current_total

        preview = {
            "profile": profile,
            "total_entities": total_entities,
            "entity_breakdown": entity_breakdown,
            "current_total": current_total,
            "entity_difference": entity_difference,
            "performance_score": performance_score,
            "recommendation": self._get_profile_recommendation_enhanced(
                total_entities, len(current_dogs), performance_score
            ),
            "warnings": self._get_profile_warnings(profile, current_dogs),
        }

        self._entity_estimates_cache[cache_key] = preview
        return preview

    def _get_profile_recommendation_enhanced(
        self, total_entities: int, dog_count: int, performance_score: float
    ) -> str:
        """Get enhanced profile recommendation with performance considerations."""

        if performance_score < 70:
            return "⚠️ Consider 'basic' or 'standard' profile for better performance"
        if performance_score < 85:
            return "💡 'Standard' profile recommended for balanced performance"
        if dog_count == 1 and total_entities < 15:
            return "✨ 'Advanced' profile available for full features"
        return "✅ Current profile is well-suited for your configuration"

    def _get_profile_warnings(
        self, profile: str, dogs: list[dict[str, Any]]
    ) -> list[str]:
        """Get profile-specific warnings and recommendations."""

        warnings: list[str] = []

        for dog in dogs:
            modules = ensure_dog_modules_mapping(dog)
            dog_name = dog.get(CONF_DOG_NAME, "Unknown")

            if profile == "gps_focus" and not modules.get(MODULE_GPS, False):
                warnings.append(
                    f"🛰️ {dog_name}: GPS focus profile but GPS module disabled"
                )

            if profile == "health_focus" and not modules.get(MODULE_HEALTH, False):
                warnings.append(
                    f"🏥 {dog_name}: Health focus profile but health module disabled"
                )

            if profile == "basic" and sum(modules.values()) > 3:
                warnings.append(
                    f"⚡ {dog_name}: Many modules enabled for basic profile"
                )

        return warnings

    async def async_step_profile_preview(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show entity count preview for selected profile.

        NEW: Provides detailed breakdown of entity counts per dog
        """
        profile = user_input.get("profile", "standard") if user_input else "standard"

        if user_input is not None:
            if user_input.get("apply_profile"):
                new_options = self._clone_options()
                new_options["entity_profile"] = profile
                typed_options = self._normalise_options_snapshot(new_options)
                self._invalidate_profile_caches()
                return self.async_create_entry(title="", data=typed_options)

            return await self.async_step_entity_profiles()

        preview_data = await self._calculate_profile_preview_optimized(profile)
        breakdown_lines = []

        for item in preview_data["entity_breakdown"]:
            modules_display = ", ".join(item["modules"]) or "none"
            breakdown_lines.append(
                f"• {item['dog_name']}: {item['entities']} entities "
                f"(modules: {modules_display}, utilization: {item['utilization']:.1f}%)"
            )

        performance_change = (
            "same"
            if preview_data["entity_difference"] == 0
            else (
                "better"
                if preview_data["entity_difference"] < 0
                else "higher resource usage"
            )
        )

        warnings_text = (
            "\n".join(preview_data["warnings"])
            if preview_data["warnings"]
            else "No warnings"
        )

        profile_info = ENTITY_PROFILES.get(profile, ENTITY_PROFILES["standard"])

        return self.async_show_form(
            step_id="profile_preview",
            data_schema=vol.Schema(
                {
                    vol.Required("profile", default=profile): vol.In([profile]),
                    vol.Optional(
                        "apply_profile", default=False
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={
                "profile_name": preview_data["profile"],
                "total_entities": str(preview_data["total_entities"]),
                "entity_breakdown": "\n".join(breakdown_lines),
                "current_total": str(preview_data["current_total"]),
                "entity_difference": (
                    f"{preview_data['entity_difference']:+d}"
                    if preview_data["entity_difference"]
                    else "0"
                ),
                "performance_change": performance_change,
                "profile_description": profile_info["description"],
                "performance_score": f"{preview_data['performance_score']:.1f}",
                "recommendation": preview_data["recommendation"],
                "warnings": warnings_text,
            },
        )

    async def async_step_performance_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure performance and optimization settings.

        NEW: Combines entity profiles with other performance settings
        """
        if user_input is not None:
            try:
                current_options = self._current_options()
                new_options = self._clone_options()

                profile = validate_profile_selection(
                    {
                        "entity_profile": user_input.get(
                            "entity_profile",
                            current_options.get("entity_profile", DEFAULT_PROFILE),
                        )
                    }
                )

                batch_default = (
                    current_options.get("batch_size")
                    if isinstance(current_options.get("batch_size"), int)
                    else 15
                )
                cache_default = (
                    current_options.get("cache_ttl")
                    if isinstance(current_options.get("cache_ttl"), int)
                    else 300
                )
                selective_default = bool(current_options.get("selective_refresh", True))

                new_options["entity_profile"] = profile
                new_options["performance_mode"] = self._normalize_performance_mode(
                    user_input.get("performance_mode"),
                    current_options.get("performance_mode"),
                )
                new_options["batch_size"] = self._coerce_int(
                    user_input.get("batch_size"), batch_default
                )
                new_options["cache_ttl"] = self._coerce_int(
                    user_input.get("cache_ttl"), cache_default
                )
                new_options["selective_refresh"] = self._coerce_bool(
                    user_input.get("selective_refresh"), selective_default
                )

                typed_options = self._normalise_options_snapshot(new_options)

                return self.async_create_entry(title="", data=typed_options)

            except Exception as err:
                _LOGGER.error("Error updating performance settings: %s", err)
                return self.async_show_form(
                    step_id="performance_settings",
                    data_schema=self._get_performance_settings_schema(user_input),
                    errors={"base": "performance_update_failed"},
                )

        return self.async_show_form(
            step_id="performance_settings",
            data_schema=self._get_performance_settings_schema(),
        )

    def _get_performance_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get performance settings schema."""
        current_options = self._entry.options
        current_values = user_input or {}

        # Profile options
        profile_options = []
        for profile_name, profile_config in ENTITY_PROFILES.items():
            max_entities = profile_config["max_entities"]
            description = profile_config["description"]
            profile_options.append(
                {
                    "value": profile_name,
                    "label": f"{profile_name.title()} ({max_entities}/dog) - {description}",
                }
            )

        stored_mode = self._normalize_performance_mode(
            current_options.get("performance_mode"), None
        )
        stored_batch = (
            current_options.get("batch_size")
            if isinstance(current_options.get("batch_size"), int)
            else 15
        )
        stored_cache_ttl = (
            current_options.get("cache_ttl")
            if isinstance(current_options.get("cache_ttl"), int)
            else 300
        )
        stored_selective = bool(current_options.get("selective_refresh", True))

        return vol.Schema(
            {
                vol.Required(
                    "entity_profile",
                    default=current_values.get(
                        "entity_profile",
                        current_options.get("entity_profile", "standard"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=profile_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "performance_mode",
                    default=current_values.get(
                        "performance_mode",
                        stored_mode,
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
                                "label": "Balanced - Good performance",
                            },
                            {"value": "full", "label": "Full - Maximum responsiveness"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "batch_size",
                    default=current_values.get("batch_size", stored_batch),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=50,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "cache_ttl",
                    default=current_values.get("cache_ttl", stored_cache_ttl),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=60,
                        max=3600,
                        step=60,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
                vol.Optional(
                    "selective_refresh",
                    default=current_values.get(
                        "selective_refresh",
                        stored_selective,
                    ),
                ): selector.BooleanSelector(),
            }
        )

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
            elif action == "configure_modules":  # NEW: Module configuration
                return await self.async_step_select_dog_for_modules()
            else:
                return await self.async_step_init()

        # Show dog management menu
        current_dogs = self._entry.data.get(CONF_DOGS, [])

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
                            "configure_modules": "Configure dog modules"  # NEW
                            if current_dogs
                            else "No dogs to configure",
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

    async def async_step_select_dog_for_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which dog to configure modules for.

        NEW: Allows per-dog module configuration
        """
        current_dogs = list(self._dogs)

        if not current_dogs:
            return await self.async_step_manage_dogs()

        if user_input is not None:
            selected_dog_id = user_input.get("dog_id")
            self._current_dog = next(
                (
                    dog
                    for dog in current_dogs
                    if dog.get(DOG_ID_FIELD) == selected_dog_id
                ),
                None,
            )
            if self._current_dog:
                return await self.async_step_configure_dog_modules()
            else:
                return await self.async_step_manage_dogs()

        # Create selection options
        dog_options = [
            {
                "value": dog.get(DOG_ID_FIELD),
                "label": f"{dog.get(DOG_NAME_FIELD)} ({dog.get(DOG_ID_FIELD)})",
            }
            for dog in current_dogs
        ]

        return self.async_show_form(
            step_id="select_dog_for_modules",
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

    async def async_step_configure_dog_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure modules for the selected dog.

        NEW: Per-dog module configuration with entity count preview
        """
        if not self._current_dog:
            return await self.async_step_manage_dogs()

        if user_input is not None:
            dog_id = self._current_dog.get(DOG_ID_FIELD)
            if not isinstance(dog_id, str):
                return self.async_show_form(
                    step_id="configure_dog_modules",
                    data_schema=self._get_dog_modules_schema(),
                    errors={"base": "invalid_dog"},
                )

            updated_modules = {
                MODULE_FEEDING: bool(user_input.get("module_feeding", True)),
                MODULE_WALK: bool(user_input.get("module_walk", True)),
                MODULE_GPS: bool(user_input.get("module_gps", False)),
                MODULE_GARDEN: bool(user_input.get("module_garden", False)),
                MODULE_HEALTH: bool(user_input.get("module_health", True)),
                "notifications": bool(user_input.get("module_notifications", True)),
                "dashboard": bool(user_input.get("module_dashboard", True)),
                "visitor": bool(user_input.get("module_visitor", False)),
                "grooming": bool(user_input.get("module_grooming", False)),
                "medication": bool(user_input.get("module_medication", False)),
                "training": bool(user_input.get("module_training", False)),
            }

            try:
                modules_payload = ensure_dog_modules_config(updated_modules)
                dog_index = next(
                    (
                        i
                        for i, dog in enumerate(self._dogs)
                        if dog.get(DOG_ID_FIELD) == dog_id
                    ),
                    -1,
                )

                if dog_index >= 0:
                    candidate: dict[str, Any] = {
                        **self._dogs[dog_index],
                        DOG_MODULES_FIELD: modules_payload,
                    }
                    normalised = ensure_dog_config_data(candidate)
                    if normalised is None:
                        raise ValueError("invalid_dog_config")

                    self._dogs[dog_index] = normalised
                    self._current_dog = normalised

                    typed_dogs = self._normalise_entry_dogs(self._dogs)
                    new_data = {**self._entry.data, CONF_DOGS: typed_dogs}

                    self.hass.config_entries.async_update_entry(
                        self._entry, data=new_data
                    )
                    self._dogs = typed_dogs
            except Exception as err:
                _LOGGER.error("Error configuring dog modules: %s", err)
                return self.async_show_form(
                    step_id="configure_dog_modules",
                    data_schema=self._get_dog_modules_schema(),
                    errors={"base": "module_config_failed"},
                )

            dog_options = self._current_dog_options()
            existing = dog_options.get(dog_id, {})
            entry = ensure_dog_options_entry(existing, dog_id=dog_id)
            entry[DOG_ID_FIELD] = dog_id
            entry[DOG_MODULES_FIELD] = modules_payload
            dog_options[dog_id] = entry

            new_options = self._clone_options()
            new_options["dog_options"] = dog_options
            self._invalidate_profile_caches()

            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="configure_dog_modules",
            data_schema=self._get_dog_modules_schema(),
            description_placeholders=self._get_module_description_placeholders(),
        )

    def _get_dog_modules_schema(self) -> vol.Schema:
        """Get modules configuration schema for current dog."""
        if not self._current_dog:
            return vol.Schema({})

        current_modules = ensure_dog_modules_mapping(self._current_dog)

        return vol.Schema(
            {
                vol.Optional(
                    "module_feeding",
                    default=current_modules.get(MODULE_FEEDING, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_walk",
                    default=current_modules.get(MODULE_WALK, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_gps",
                    default=current_modules.get(MODULE_GPS, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_garden",
                    default=current_modules.get(MODULE_GARDEN, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_health",
                    default=current_modules.get(MODULE_HEALTH, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_notifications",
                    default=current_modules.get("notifications", True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_dashboard",
                    default=current_modules.get("dashboard", True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_visitor",
                    default=current_modules.get("visitor", False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_grooming",
                    default=current_modules.get("grooming", False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_medication",
                    default=current_modules.get("medication", False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "module_training",
                    default=current_modules.get("training", False),
                ): selector.BooleanSelector(),
            }
        )

    def _get_module_description_placeholders(self) -> dict[str, str]:
        """Get description placeholders for module configuration."""
        if not self._current_dog:
            return {}

        current_profile = self._entry.options.get("entity_profile", "standard")
        current_modules = ensure_dog_modules_mapping(self._current_dog)

        # Calculate current entity count
        current_estimate = self._entity_factory.estimate_entity_count(
            current_profile, current_modules
        )

        # Module descriptions
        module_descriptions = {
            MODULE_FEEDING: "Food tracking, scheduling, portion control",
            MODULE_WALK: "Walk tracking, duration, distance monitoring",
            MODULE_GPS: "Location tracking, geofencing, route recording",
            MODULE_HEALTH: "Weight tracking, vet reminders, medication",
            "notifications": "Alerts, reminders, status notifications",
            "dashboard": "Custom dashboard generation",
            "visitor": "Visitor mode for reduced monitoring",
            "grooming": "Grooming schedule and tracking",
            "medication": "Medication reminders and tracking",
            "training": "Training progress and notes",
        }

        enabled_modules = [
            f"• {module}: {module_descriptions.get(module, 'Module functionality')}"
            for module, enabled in current_modules.items()
            if enabled
        ]

        return {
            "dog_name": self._current_dog.get(CONF_DOG_NAME, "Unknown"),
            "current_profile": current_profile,
            "current_entities": str(current_estimate),
            "enabled_modules": "\n".join(enabled_modules)
            if enabled_modules
            else "No modules enabled",
        }

    # Rest of the existing methods (add_new_dog, edit_dog, etc.) remain the same...

    async def async_step_add_new_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new dog to the configuration."""
        if user_input is not None:
            try:
                dog_id_input = str(user_input[CONF_DOG_ID])
                dog_id = dog_id_input.strip().lower().replace(" ", "_")
                dog_name = str(user_input[CONF_DOG_NAME]).strip()

                if not dog_id or not dog_name:
                    raise ValueError("invalid_dog_identifiers")

                modules_config = ensure_dog_modules_config(
                    {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_GPS: False,
                        MODULE_GARDEN: False,
                        "notifications": True,
                        "dashboard": True,
                        "visitor": False,
                        "grooming": False,
                        "medication": False,
                        "training": False,
                    }
                )

                candidate: dict[str, Any] = {
                    DOG_ID_FIELD: dog_id,
                    DOG_NAME_FIELD: dog_name,
                    DOG_MODULES_FIELD: modules_config,
                }

                breed = str(user_input.get(CONF_DOG_BREED, "")).strip()
                candidate[DOG_BREED_FIELD] = breed or "Mixed Breed"

                age = user_input.get(CONF_DOG_AGE, 3)
                candidate[DOG_AGE_FIELD] = int(age)

                weight = user_input.get(CONF_DOG_WEIGHT, 20.0)
                candidate[DOG_WEIGHT_FIELD] = float(weight)

                size = user_input.get(CONF_DOG_SIZE, "medium")
                if isinstance(size, str) and size:
                    candidate[DOG_SIZE_FIELD] = size

                new_dogs_raw: list[Mapping[str, Any]] = [*self._dogs, candidate]
                typed_dogs = self._normalise_entry_dogs(new_dogs_raw)
                self._dogs = typed_dogs
                self._current_dog = typed_dogs[-1]

                new_data = {**self._entry.data, CONF_DOGS: typed_dogs}

                self.hass.config_entries.async_update_entry(self._entry, data=new_data)
                self._invalidate_profile_caches()

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
                            {"value": "toy", "label": "Toy (1-6kg)"},
                            {"value": "small", "label": "Small (6-12kg)"},
                            {"value": "medium", "label": "Medium (12-27kg)"},
                            {"value": "large", "label": "Large (27-45kg)"},
                            {"value": "giant", "label": "Giant (45-90kg)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    def _get_remove_dog_schema(self, dogs: Sequence[Mapping[str, Any]]) -> vol.Schema:
        """Build the removal confirmation schema for the provided dog list."""

        dog_options: list[dict[str, str]] = []
        for dog in dogs:
            dog_id = dog.get(DOG_ID_FIELD)
            dog_name = dog.get(DOG_NAME_FIELD)
            if not isinstance(dog_id, str) or not dog_id:
                continue
            label_name = dog_name if isinstance(dog_name, str) and dog_name else dog_id
            dog_options.append(
                {
                    "value": dog_id,
                    "label": f"{label_name} ({dog_id})",
                }
            )

        return vol.Schema(
            {
                vol.Required("dog_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=dog_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    "confirm_remove",
                    default=False,
                ): selector.BooleanSelector(),
            }
        )

    async def async_step_select_dog_to_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which dog to edit."""
        current_dogs = self._entry.data.get(CONF_DOGS, [])

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
                target_id = self._current_dog[DOG_ID_FIELD]
                dog_index = next(
                    (
                        i
                        for i, dog in enumerate(self._dogs)
                        if dog[DOG_ID_FIELD] == target_id
                    ),
                    -1,
                )

                if dog_index >= 0:
                    candidate: dict[str, Any] = dict(self._dogs[dog_index])

                    name = user_input.get(
                        CONF_DOG_NAME, candidate.get(DOG_NAME_FIELD, "")
                    )
                    if isinstance(name, str) and name.strip():
                        candidate[DOG_NAME_FIELD] = name.strip()

                    breed = user_input.get(
                        CONF_DOG_BREED, candidate.get(DOG_BREED_FIELD, "")
                    )
                    if isinstance(breed, str):
                        candidate[DOG_BREED_FIELD] = breed.strip()

                    age = user_input.get(CONF_DOG_AGE)
                    if age is None:
                        candidate.pop(DOG_AGE_FIELD, None)
                    else:
                        candidate[DOG_AGE_FIELD] = int(age)

                    weight = user_input.get(CONF_DOG_WEIGHT)
                    if weight is None:
                        candidate.pop(DOG_WEIGHT_FIELD, None)
                    else:
                        candidate[DOG_WEIGHT_FIELD] = float(weight)

                    size = user_input.get(CONF_DOG_SIZE, candidate.get(DOG_SIZE_FIELD))
                    if isinstance(size, str):
                        cleaned_size = size.strip()
                        if cleaned_size:
                            candidate[DOG_SIZE_FIELD] = cleaned_size
                        else:
                            candidate.pop(DOG_SIZE_FIELD, None)

                    normalised = ensure_dog_config_data(candidate)
                    if normalised is None:
                        raise ValueError("invalid_dog_config")

                    self._dogs[dog_index] = normalised
                    typed_dogs = self._normalise_entry_dogs(self._dogs)
                    self._dogs = typed_dogs
                    self._current_dog = normalised

                    new_data = {**self._entry.data, CONF_DOGS: typed_dogs}

                    self.hass.config_entries.async_update_entry(
                        self._entry, data=new_data
                    )
                    self._invalidate_profile_caches()

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
                            {"value": "toy", "label": "Toy (1-6kg)"},
                            {"value": "small", "label": "Small (6-12kg)"},
                            {"value": "medium", "label": "Medium (12-27kg)"},
                            {"value": "large", "label": "Large (27-45kg)"},
                            {"value": "giant", "label": "Giant (45-90kg)"},
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
        current_dogs = list(self._dogs)

        if not current_dogs:
            return await self.async_step_init()

        if user_input is not None:
            if user_input.get("confirm_remove"):
                selected_dog_id = user_input.get("dog_id")
                # Remove the selected dog
                updated_dogs = [
                    dog
                    for dog in current_dogs
                    if dog.get(DOG_ID_FIELD) != selected_dog_id
                ]

                try:
                    typed_dogs = self._normalise_entry_dogs(updated_dogs)
                except ValueError as err:  # pragma: no cover - defensive guard
                    _LOGGER.error("Invalid dog configuration during removal: %s", err)
                    return self.async_show_form(
                        step_id="select_dog_to_remove",
                        data_schema=self._get_remove_dog_schema(current_dogs),
                        errors={"base": "dog_remove_failed"},
                    )

                # Update config entry
                new_data = {**self._entry.data, CONF_DOGS: typed_dogs}

                self.hass.config_entries.async_update_entry(self._entry, data=new_data)
                self._dogs = typed_dogs
                if self._current_dog and (
                    self._current_dog.get(DOG_ID_FIELD) == selected_dog_id
                ):
                    self._current_dog = typed_dogs[0] if typed_dogs else None

                new_options = self._clone_options()
                dog_options = self._current_dog_options()
                if isinstance(selected_dog_id, str) and selected_dog_id in dog_options:
                    dog_options.pop(selected_dog_id, None)
                    new_options["dog_options"] = dog_options

                self._invalidate_profile_caches()

                typed_options = self._normalise_options_snapshot(new_options)

                return self.async_create_entry(title="", data=typed_options)

            return await self.async_step_init()

        # Create removal confirmation form
        return self.async_show_form(
            step_id="select_dog_to_remove",
            data_schema=self._get_remove_dog_schema(current_dogs),
            description_placeholders={
                "warning": "This will permanently remove the selected dog and all associated data!"
            },
        )

    # GPS Settings (existing method, enhanced with route recording)
    async def async_step_gps_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure GPS and location settings with enhanced route recording options."""

        current = self._current_gps_options()

        if user_input is not None:
            interval_candidate = user_input.get(
                CONF_GPS_UPDATE_INTERVAL,
                current.get(CONF_GPS_UPDATE_INTERVAL, DEFAULT_GPS_UPDATE_INTERVAL),
            )
            try:
                validated_interval = DogConfigRegistry._validate_gps_interval(
                    interval_candidate
                )
            except ValidationError:
                return self.async_show_form(
                    step_id="gps_settings",
                    data_schema=self._get_gps_settings_schema(user_input),
                    errors={CONF_GPS_UPDATE_INTERVAL: "invalid_interval"},
                )

            accuracy_candidate = user_input.get(
                CONF_GPS_ACCURACY_FILTER,
                current.get(CONF_GPS_ACCURACY_FILTER, DEFAULT_GPS_ACCURACY_FILTER),
            )
            distance_candidate = user_input.get(
                CONF_GPS_DISTANCE_FILTER,
                current.get(CONF_GPS_DISTANCE_FILTER, DEFAULT_GPS_DISTANCE_FILTER),
            )

            try:
                validated_accuracy = float(accuracy_candidate)
                if validated_accuracy <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return self.async_show_form(
                    step_id="gps_settings",
                    data_schema=self._get_gps_settings_schema(user_input),
                    errors={CONF_GPS_ACCURACY_FILTER: "invalid_accuracy"},
                )

            try:
                validated_distance = float(distance_candidate)
                if validated_distance <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return self.async_show_form(
                    step_id="gps_settings",
                    data_schema=self._get_gps_settings_schema(user_input),
                    errors={CONF_GPS_DISTANCE_FILTER: "invalid_distance"},
                )

            history_candidate = user_input.get(
                "route_history_days", current.get("route_history_days", 30)
            )
            try:
                route_history_days = int(history_candidate)
            except (TypeError, ValueError):
                route_history_days = 30
            route_history_days = max(1, min(route_history_days, 365))

            gps_settings: GPSOptions = {
                "gps_enabled": bool(
                    user_input.get("gps_enabled", current["gps_enabled"])
                ),
                CONF_GPS_UPDATE_INTERVAL: validated_interval,
                CONF_GPS_ACCURACY_FILTER: validated_accuracy,
                CONF_GPS_DISTANCE_FILTER: validated_distance,
                "route_recording": bool(
                    user_input.get("route_recording", current["route_recording"])
                ),
                "route_history_days": route_history_days,
                "auto_track_walks": bool(
                    user_input.get("auto_track_walks", current["auto_track_walks"])
                ),
            }

            new_options = self._clone_options()
            new_options["gps_settings"] = gps_settings
            new_options[CONF_GPS_UPDATE_INTERVAL] = validated_interval
            new_options[CONF_GPS_ACCURACY_FILTER] = validated_accuracy
            new_options[CONF_GPS_DISTANCE_FILTER] = validated_distance

            typed_options = self._normalise_options_snapshot(new_options)

            return self.async_create_entry(title="", data=typed_options)

        return self.async_show_form(
            step_id="gps_settings", data_schema=self._get_gps_settings_schema()
        )

    def _get_gps_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get GPS settings schema with current values and enhanced route options."""

        current = self._current_gps_options()
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    "gps_enabled",
                    default=current_values.get("gps_enabled", current["gps_enabled"]),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_GPS_UPDATE_INTERVAL,
                    default=current_values.get(
                        CONF_GPS_UPDATE_INTERVAL,
                        current.get(
                            CONF_GPS_UPDATE_INTERVAL, DEFAULT_GPS_UPDATE_INTERVAL
                        ),
                    ),
                ): GPS_UPDATE_INTERVAL_SELECTOR,
                vol.Optional(
                    CONF_GPS_ACCURACY_FILTER,
                    default=current_values.get(
                        CONF_GPS_ACCURACY_FILTER,
                        current.get(
                            CONF_GPS_ACCURACY_FILTER, DEFAULT_GPS_ACCURACY_FILTER
                        ),
                    ),
                ): GPS_ACCURACY_FILTER_SELECTOR,
                vol.Optional(
                    CONF_GPS_DISTANCE_FILTER,
                    default=current_values.get(
                        CONF_GPS_DISTANCE_FILTER,
                        current.get(
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
                vol.Optional(
                    "route_recording",
                    default=current_values.get(
                        "route_recording", current["route_recording"]
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "route_history_days",
                    default=current_values.get(
                        "route_history_days", current["route_history_days"]
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    "auto_track_walks",
                    default=current_values.get(
                        "auto_track_walks", current["auto_track_walks"]
                    ),
                ): selector.BooleanSelector(),
            }
        )

    # NEW: Weather Settings Configuration
    async def async_step_weather_settings(
        self, user_input: dict[str, Any] | None = None
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
                            data_schema=self._get_weather_settings_schema(user_input),
                            errors={"weather_entity": "weather_entity_not_found"},
                        )

                    # Check if it's a weather entity
                    if not candidate.startswith("weather."):
                        return self.async_show_form(
                            step_id="weather_settings",
                            data_schema=self._get_weather_settings_schema(user_input),
                            errors={"weather_entity": "invalid_weather_entity"},
                        )

                current_weather = self._current_weather_options()
                new_options = self._clone_options()
                weather_settings = self._build_weather_settings(
                    user_input, current_weather
                )
                new_options["weather_settings"] = weather_settings
                new_options[CONF_WEATHER_ENTITY] = weather_settings.get(
                    CONF_WEATHER_ENTITY
                )
                return self.async_create_entry(title="", data=new_options)

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
            description_placeholders=self._get_weather_description_placeholders(),
        )

    def _get_weather_settings_schema(
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get weather settings schema with current values and entity selection."""
        current_weather = self._current_weather_options()
        current_values = user_input or {}

        stored_entity = current_weather.get(CONF_WEATHER_ENTITY)
        entity_default = "none"
        if isinstance(stored_entity, str) and stored_entity.strip():
            entity_default = stored_entity

        # Get available weather entities
        weather_entities = [
            {"value": "none", "label": "No weather entity (disable weather features)"}
        ]

        for entity_id in self.hass.states.async_entity_ids("weather"):
            entity_state = self.hass.states.get(entity_id)
            if entity_state:
                friendly_name = entity_state.attributes.get("friendly_name", entity_id)
                weather_entities.append(
                    {"value": entity_id, "label": f"{friendly_name} ({entity_id})"}
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
                    )
                ),
                vol.Optional(
                    "weather_health_monitoring",
                    default=current_values.get(
                        "weather_health_monitoring",
                        current_weather.get(
                            "weather_health_monitoring",
                            DEFAULT_WEATHER_HEALTH_MONITORING,
                        ),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "weather_alerts",
                    default=current_values.get(
                        "weather_alerts",
                        current_weather.get("weather_alerts", DEFAULT_WEATHER_ALERTS),
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
                    )
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
                        current_weather.get("breed_specific_recommendations", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "health_condition_adjustments",
                    default=current_values.get(
                        "health_condition_adjustments",
                        current_weather.get("health_condition_adjustments", True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "auto_activity_adjustments",
                    default=current_values.get(
                        "auto_activity_adjustments",
                        current_weather.get("auto_activity_adjustments", False),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "notification_threshold",
                    default=current_values.get(
                        "notification_threshold",
                        current_weather.get("notification_threshold", "moderate"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "low",
                                "label": "Low - Only extreme weather warnings",
                            },
                            {
                                "value": "moderate",
                                "label": "Moderate - Important weather alerts",
                            },
                            {
                                "value": "high",
                                "label": "High - All weather recommendations",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    def _get_weather_description_placeholders(self) -> dict[str, str]:
        """Get description placeholders for weather configuration."""
        current_weather = self._current_weather_options()
        current_dogs = self._entry.data.get(CONF_DOGS, [])

        # Current weather entity status
        weather_entity = current_weather.get(CONF_WEATHER_ENTITY)
        weather_status = "Not configured"
        weather_info = "No weather entity selected"

        if weather_entity:
            weather_state = self.hass.states.get(weather_entity)
            if weather_state:
                weather_status = "Available"
                temperature = weather_state.attributes.get("temperature", "Unknown")
                condition = weather_state.state or "Unknown"
                weather_info = f"Current: {temperature}°C, {condition}"
            else:
                weather_status = "Entity not found"
                weather_info = f"Entity {weather_entity} is not available"

        # Count dogs with health conditions
        dogs_with_health_conditions = 0
        dogs_with_breeds = 0
        for dog in current_dogs:
            if dog.get("health_conditions"):
                dogs_with_health_conditions += 1
            if dog.get(CONF_DOG_BREED) and dog.get(CONF_DOG_BREED) != "Mixed Breed":
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

        alerts_summary = ", ".join(enabled_alerts) if enabled_alerts else "None"

        # Feature status
        weather_monitoring = current_weather.get(
            "weather_health_monitoring", DEFAULT_WEATHER_HEALTH_MONITORING
        )
        breed_recommendations = current_weather.get(
            "breed_specific_recommendations", True
        )
        health_adjustments = current_weather.get("health_condition_adjustments", True)

        return {
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
            "update_interval": str(current_weather.get("weather_update_interval", 60)),
            "notification_threshold": current_weather.get(
                "notification_threshold", "moderate"
            ).title(),
            "available_weather_entities": str(
                len([e for e in self.hass.states.async_entity_ids("weather")])
            ),
        }

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure notification settings."""
        if user_input is not None:
            try:
                # Update notification settings
                current_notifications = self._current_notification_options()
                new_options = self._clone_options()
                notification_settings = self._build_notification_settings(
                    user_input, current_notifications
                )
                new_options[CONF_NOTIFICATIONS] = ensure_notification_options(
                    notification_settings, defaults=_NOTIFICATION_DEFAULTS
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
        current_notifications = self._current_notification_options()
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
                current_feeding = self._current_feeding_options()
                new_options = self._clone_options()
                new_options["feeding_settings"] = self._build_feeding_settings(
                    user_input, current_feeding
                )
                typed_options = self._normalise_options_snapshot(new_options)
                return self.async_create_entry(title="", data=typed_options)
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
        current_feeding = self._current_feeding_options()
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
                current_health = self._current_health_options()
                new_options = self._clone_options()
                new_options["health_settings"] = self._build_health_settings(
                    user_input, current_health
                )
                typed_options = self._normalise_options_snapshot(new_options)
                return self.async_create_entry(title="", data=typed_options)
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
        current_health = self._current_health_options()
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
                current_system = self._current_system_options()
                reset_default = self._coerce_time_string(
                    self._current_options().get(CONF_RESET_TIME), DEFAULT_RESET_TIME
                )
                new_options = self._clone_options()
                system_settings, reset_time = self._build_system_settings(
                    user_input, current_system, reset_default=reset_default
                )
                new_options["system_settings"] = system_settings
                new_options[CONF_RESET_TIME] = reset_time
                typed_options = self._normalise_options_snapshot(new_options)
                return self.async_create_entry(title="", data=typed_options)
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
        current_system = self._current_system_options()
        current_values = user_input or {}
        reset_default = self._coerce_time_string(
            self._current_options().get(CONF_RESET_TIME), DEFAULT_RESET_TIME
        )
        mode_default = self._normalize_performance_mode(
            current_system.get("performance_mode"),
            self._current_options().get("performance_mode"),
        )

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
                        mode_default,
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
                    user_input, current_dashboard, default_mode=default_mode
                )
                new_options["dashboard_settings"] = dashboard_settings
                new_options[CONF_DASHBOARD_MODE] = dashboard_mode
                typed_options = self._normalise_options_snapshot(new_options)
                return self.async_create_entry(title="", data=typed_options)
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
            }
        )

    async def async_step_advanced_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle advanced settings configuration."""
        if user_input is not None:
            errors: dict[str, str] = {}
            endpoint_value = user_input.get(CONF_API_ENDPOINT, "").strip()
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
                    user_input, current_advanced
                )
                if CONF_API_ENDPOINT in user_input:
                    advanced_settings[CONF_API_ENDPOINT] = endpoint_value
                if CONF_API_TOKEN in user_input:
                    raw_token = user_input[CONF_API_TOKEN]
                    advanced_settings[CONF_API_TOKEN] = (
                        raw_token.strip() if isinstance(raw_token, str) else ""
                    )
                new_options["advanced_settings"] = advanced_settings
                new_options.update(advanced_settings)
                return self.async_create_entry(
                    title="",
                    data=self._normalise_options_snapshot(new_options),
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
        self, user_input: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Get schema for advanced settings form."""
        current_advanced = self._current_advanced_options()
        current_values = user_input or {}
        mode_default = self._normalize_performance_mode(
            current_advanced.get("performance_mode"),
            self._current_options().get("performance_mode"),
        )
        retention_default = self._coerce_int(
            current_advanced.get("data_retention_days"), 90
        )
        debug_default = self._coerce_bool(current_advanced.get("debug_logging"), False)
        backup_default = self._coerce_bool(current_advanced.get("auto_backup"), False)
        experimental_default = self._coerce_bool(
            current_advanced.get("experimental_features"), False
        )
        integrations_default = self._coerce_bool(
            current_advanced.get(CONF_EXTERNAL_INTEGRATIONS), False
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
                    default=current_values.get("performance_mode", mode_default),
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
                    default=current_values.get("debug_logging", debug_default),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "data_retention_days",
                    default=current_values.get(
                        "data_retention_days", retention_default
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
                    default=current_values.get("auto_backup", backup_default),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "experimental_features",
                    default=current_values.get(
                        "experimental_features", experimental_default
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_EXTERNAL_INTEGRATIONS,
                    default=current_values.get(
                        CONF_EXTERNAL_INTEGRATIONS, integrations_default
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_API_ENDPOINT,
                    default=current_values.get(CONF_API_ENDPOINT, endpoint_default),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        multiline=False,
                    )
                ),
                vol.Optional(
                    CONF_API_TOKEN,
                    default=current_values.get(CONF_API_TOKEN, token_default),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                        multiline=False,
                    )
                ),
            }
        )

    async def async_step_import_export(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle selection for the import/export utilities."""

        if user_input is None:
            return self.async_show_form(
                step_id="import_export",
                data_schema=self._get_import_export_menu_schema(),
                description_placeholders={
                    "instructions": (
                        "Create a JSON backup of the current PawControl options "
                        "or restore a backup previously exported from this menu."
                    )
                },
            )

        action = user_input.get("action")
        if action == "export":
            return await self.async_step_import_export_export()
        if action == "import":
            return await self.async_step_import_export_import()

        return self.async_show_form(
            step_id="import_export",
            data_schema=self._get_import_export_menu_schema(),
            errors={"action": "invalid_action"},
        )

    async def async_step_import_export_export(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Surface a JSON export of the current configuration."""

        if user_input is not None:
            return await self.async_step_init()

        payload = self._build_export_payload()
        export_blob = json.dumps(payload, indent=2, sort_keys=True)

        return self.async_show_form(
            step_id="import_export_export",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "export_blob",
                        default=export_blob,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                            multiline=True,
                        )
                    )
                }
            ),
            description_placeholders={
                "export_blob": export_blob,
                "generated_at": payload["created_at"],
            },
        )

    async def async_step_import_export_import(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Import configuration from a JSON payload."""

        errors: dict[str, str] = {}
        payload_text = ""

        if user_input is not None:
            payload_text = str(user_input.get("payload", "")).strip()
            if not payload_text:
                errors["payload"] = "invalid_payload"
            else:
                try:
                    parsed = json.loads(payload_text)
                except json.JSONDecodeError:
                    errors["payload"] = "invalid_json"
                else:
                    try:
                        validated = self._validate_import_payload(parsed)
                    except ValueError as err:
                        _LOGGER.debug("Import payload validation failed: %s", err)
                        error_code = str(err).strip() or "invalid_payload"
                        if " " in error_code:
                            error_code = "invalid_payload"
                        errors["payload"] = error_code
                    else:
                        new_options = self._normalise_options_snapshot(
                            validated["options"]
                        )
                        new_dogs: list[DogConfigData] = []
                        for dog in validated.get("dogs", []):
                            if not isinstance(dog, Mapping):
                                continue
                            normalised = ensure_dog_config_data(dog)
                            if normalised is not None:
                                new_dogs.append(normalised)

                        new_data = {**self._entry.data, CONF_DOGS: new_dogs}
                        self.hass.config_entries.async_update_entry(
                            self._entry, data=new_data
                        )
                        self._dogs = new_dogs
                        self._current_dog = None
                        self._invalidate_profile_caches()

                        return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="import_export_import",
            data_schema=self._get_import_export_import_schema(payload_text),
            errors=errors,
        )

    def _get_import_export_menu_schema(self) -> vol.Schema:
        """Return the schema for selecting an import/export action."""

        return vol.Schema(
            {
                vol.Required("action", default="export"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "export",
                                "label": "Export current settings",
                            },
                            {
                                "value": "import",
                                "label": "Import settings from backup",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

    def _get_import_export_import_schema(self, default_payload: str) -> vol.Schema:
        """Return the schema for the import form."""

        return vol.Schema(
            {
                vol.Required("payload", default=default_payload): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        multiline=True,
                    )
                )
            }
        )
