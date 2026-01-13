"""Shared helper methods for the PawControl options flow.

This module exists to keep :mod:`custom_components.pawcontrol.options_flow_main` small.
It contains common helper methods used by multiple option-flow mixins (telemetry,
manual event helpers, system/dashboard/advanced settings builders, etc.).
"""
from __future__ import annotations

import json  # noqa: F401
import logging
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import asdict  # noqa: F401
from datetime import datetime
from datetime import UTC
from pathlib import Path  # noqa: F401
from typing import Any
from typing import cast
from typing import Final
from typing import Literal

import voluptuous as vol
from homeassistant.util import dt as dt_util  # noqa: F401

from .const import *  # noqa: F403
from .diagnostics import normalize_value
from .types import AdvancedOptions
from .types import clone_placeholders
from .types import ConfigFlowPlaceholders
from .types import DashboardOptions
from .types import ensure_advanced_options
from .types import freeze_placeholders
from .types import JSONLikeMapping
from .types import JSONMutableMapping
from .types import JSONValue
from .types import normalize_performance_mode
from .types import NotificationThreshold
from .types import OptionsAdvancedSettingsInput
from .types import OptionsDashboardSettingsInput
from .types import OptionsSystemSettingsInput
from .types import SystemOptions

_LOGGER = logging.getLogger(__name__)

ManualEventField = Literal[
    'manual_check_event',
    'manual_guard_event',
    'manual_breaker_event',
]

SYSTEM_ENABLE_ANALYTICS_FIELD: Final[Literal['enable_analytics']] = cast(
    Literal['enable_analytics'], 'enable_analytics'
)
SYSTEM_ENABLE_CLOUD_BACKUP_FIELD: Final[Literal['enable_cloud_backup']] = cast(
    Literal['enable_cloud_backup'], 'enable_cloud_backup'
)
EXTERNAL_INTEGRATIONS_FIELD: Final[Literal['external_integrations']] = cast(
    Literal['external_integrations'],
    CONF_EXTERNAL_INTEGRATIONS,  # noqa: F405
)
API_ENDPOINT_FIELD: Final[Literal['api_endpoint']] = cast(
    Literal['api_endpoint'],
    CONF_API_ENDPOINT,  # noqa: F405
)
API_TOKEN_FIELD: Final[Literal['api_token']] = cast(
    Literal['api_token'],
    CONF_API_TOKEN,  # noqa: F405
)
WEATHER_ENTITY_FIELD: Final[Literal['weather_entity']] = cast(
    Literal['weather_entity'],
    CONF_WEATHER_ENTITY,  # noqa: F405
)
DOG_OPTIONS_FIELD: Final[Literal['dog_options']] = cast(
    Literal['dog_options'],
    CONF_DOG_OPTIONS,  # noqa: F405
)
ADVANCED_SETTINGS_FIELD: Final[Literal['advanced_settings']] = cast(
    Literal['advanced_settings'],
    CONF_ADVANCED_SETTINGS,  # noqa: F405
)
LAST_RECONFIGURE_FIELD: Final[Literal['last_reconfigure']] = cast(
    Literal['last_reconfigure'],
    CONF_LAST_RECONFIGURE,  # noqa: F405
)
RECONFIGURE_TELEMETRY_FIELD: Final[Literal['reconfigure_telemetry']] = cast(
    Literal['reconfigure_telemetry'],
    CONF_RECONFIGURE_TELEMETRY,  # noqa: F405
)


class OptionsFlowSharedMixin:
    def _manual_event_description_placeholders(self) -> ConfigFlowPlaceholders:
        """Return description placeholders enumerating known manual events."""

        choices = self._resolve_manual_event_choices()
        placeholders: dict[str, str] = {}
        for field, values in choices.items():
            placeholder_key = f"{field}_options"
            placeholders[placeholder_key] = ', '.join(values) if values else '—'
        return freeze_placeholders(placeholders)

    @staticmethod
    def _coerce_manual_event_with_default(
        value: Any, default: str | None
    ) -> str | None:
        """Return a normalised manual event or fallback to the provided default."""

        if isinstance(value, str):
            candidate = value.strip()
            return candidate or None
        return default

    def _get_reconfigure_description_placeholders(self) -> ConfigFlowPlaceholders:
        """Return placeholders describing the latest reconfigure telemetry."""

        telemetry = self._reconfigure_telemetry()
        timestamp = self._format_local_timestamp(
            (telemetry or {}).get('timestamp') if telemetry else None
        )
        placeholders = clone_placeholders(RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE)  # noqa: F405
        placeholders['last_reconfigure'] = timestamp
        if not telemetry:
            placeholders['reconfigure_requested_profile'] = 'Not recorded'
            placeholders['reconfigure_previous_profile'] = 'Not recorded'
            placeholders['reconfigure_entities'] = '0'
            placeholders['reconfigure_dogs'] = '0'
            placeholders['reconfigure_health'] = 'No recent health summary'
            placeholders['reconfigure_warnings'] = 'None'
            placeholders['reconfigure_merge_notes'] = 'No merge adjustments recorded'
            return freeze_placeholders(placeholders)

        requested_profile = str(telemetry.get('requested_profile', '')) or 'Unknown'
        previous_profile = str(telemetry.get('previous_profile', '')) or 'Unknown'
        dogs_count = telemetry.get('dogs_count')
        estimated_entities = telemetry.get('estimated_entities')
        warnings = self._string_sequence(telemetry.get('compatibility_warnings'))
        merge_notes = self._string_sequence(telemetry.get('merge_notes'))
        health_summary = telemetry.get('health_summary')

        last_recorded = telemetry.get('timestamp') or self._last_reconfigure_timestamp()

        placeholders['last_reconfigure'] = self._format_local_timestamp(
            str(last_recorded) if last_recorded else None
        )
        placeholders['reconfigure_requested_profile'] = requested_profile
        placeholders['reconfigure_previous_profile'] = previous_profile
        placeholders['reconfigure_entities'] = (
            str(int(estimated_entities))
            if isinstance(estimated_entities, int | float)
            else '0'
        )
        placeholders['reconfigure_dogs'] = (
            str(int(dogs_count)) if isinstance(dogs_count, int | float) else '0'
        )
        placeholders['reconfigure_health'] = self._summarise_health_summary(
            health_summary
        )
        placeholders['reconfigure_warnings'] = (
            ', '.join(warnings) if warnings else 'None'
        )
        placeholders['reconfigure_merge_notes'] = (
            '\n'.join(merge_notes) if merge_notes else 'No merge adjustments recorded'
        )
        return freeze_placeholders(placeholders)

    def _normalise_export_value(self, value: Any) -> JSONValue:
        """Convert complex values into JSON-serialisable primitives."""

        return cast(JSONValue, normalize_value(value))

    def _sanitise_imported_dog(self, raw: Mapping[str, JSONValue]) -> DogConfigData:  # noqa: F405
        """Normalise and validate a dog payload from an import file."""

        normalised = cast(
            DogConfigData,  # noqa: F405
            self._normalise_export_value(dict(raw)),
        )

        modules_raw = normalised.get(CONF_MODULES)  # noqa: F405
        if modules_raw is not None and not isinstance(modules_raw, Mapping):
            raise FlowValidationError(field_errors={'payload': 'dog_invalid_modules'})  # noqa: F405

        modules = ensure_dog_modules_config(normalised)  # noqa: F405
        normalised[DOG_MODULES_FIELD] = modules  # noqa: F405

        if not is_dog_config_valid(normalised):  # noqa: F405
            raise FlowValidationError(field_errors={'payload': 'dog_invalid_config'})  # noqa: F405

        return normalised

    def _build_export_payload(self) -> OptionsExportPayload:  # noqa: F405
        """Serialise the current configuration into an export payload."""

        typed_options = self._normalise_options_snapshot(self._clone_options())
        options = cast(
            PawControlOptionsData,  # noqa: F405
            self._normalise_export_value(typed_options),
        )

        dogs_payload: list[DogConfigData] = []  # noqa: F405
        dogs_raw = self._entry.data.get(CONF_DOGS, [])  # noqa: F405
        dogs_iterable: Sequence[JSONLikeMapping] = (
            cast(Sequence[JSONLikeMapping], dogs_raw)
            if isinstance(dogs_raw, Sequence) and not isinstance(dogs_raw, (bytes, str))
            else ()
        )
        for raw in dogs_iterable:
            if not isinstance(raw, Mapping):
                continue
            normalised = cast(
                DogConfigData,  # noqa: F405
                self._normalise_export_value(dict(raw)),
            )
            dog_id = normalised.get(CONF_DOG_ID)  # noqa: F405
            if not isinstance(dog_id, str) or not dog_id.strip():
                continue
            modules_mapping = ensure_dog_modules_mapping(normalised)  # noqa: F405
            if modules_mapping:
                normalised[DOG_MODULES_FIELD] = cast(  # noqa: F405
                    DogModulesConfig,  # noqa: F405
                    dict(modules_mapping),
                )
            elif DOG_MODULES_FIELD in normalised:  # noqa: F405
                normalised.pop(DOG_MODULES_FIELD, None)  # noqa: F405
            dogs_payload.append(normalised)

        payload: OptionsExportPayload = {  # noqa: F405
            'version': cast(Literal[1], self._EXPORT_VERSION),
            'options': options,
            'dogs': dogs_payload,
            'created_at': datetime.now(UTC).isoformat(),
        }
        return payload

    def _validate_import_payload(self, payload: Any) -> OptionsExportPayload:  # noqa: F405
        """Validate and normalise an imported payload."""

        if not isinstance(payload, Mapping):
            raise FlowValidationError(field_errors={'payload': 'payload_not_mapping'})  # noqa: F405

        version = payload.get('version')
        if version != self._EXPORT_VERSION:
            raise FlowValidationError(field_errors={'payload': 'unsupported_version'})  # noqa: F405

        options_raw = payload.get('options')
        if not isinstance(options_raw, Mapping):
            raise FlowValidationError(field_errors={'payload': 'options_missing'})  # noqa: F405

        sanitised_options = cast(
            PawControlOptionsData,  # noqa: F405
            self._normalise_export_value(dict(options_raw)),
        )

        merged_candidate = cast(ConfigEntryOptionsPayload, dict(self._clone_options()))  # noqa: F405
        merged_candidate.update(sanitised_options)
        merged_options = self._normalise_options_snapshot(merged_candidate)

        dogs_raw = payload.get('dogs', [])
        if not isinstance(dogs_raw, list):
            raise FlowValidationError(field_errors={'payload': 'dogs_invalid'})  # noqa: F405

        dogs_payload: list[DogConfigData] = []  # noqa: F405
        seen_ids: set[str] = set()
        for raw in dogs_raw:
            if not isinstance(raw, Mapping):
                raise FlowValidationError(field_errors={'payload': 'dog_invalid'})  # noqa: F405
            normalised = self._sanitise_imported_dog(raw)
            dog_id = normalised.get(CONF_DOG_ID)  # noqa: F405
            if not isinstance(dog_id, str) or not dog_id.strip():
                raise FlowValidationError(field_errors={'payload': 'dog_missing_id'})  # noqa: F405
            if dog_id in seen_ids:
                raise FlowValidationError(field_errors={'payload': 'dog_duplicate'})  # noqa: F405
            seen_ids.add(dog_id)
            dogs_payload.append(normalised)

        created_at = payload.get('created_at')
        if not isinstance(created_at, str) or not created_at:
            created_at = datetime.now(UTC).isoformat()

        result: OptionsExportPayload = {  # noqa: F405
            'version': cast(Literal[1], self._EXPORT_VERSION),
            'options': merged_options,
            'dogs': dogs_payload,
            'created_at': created_at,
        }
        return result

    def _current_weather_options(self) -> WeatherOptions:  # noqa: F405
        """Return the stored weather configuration with root fallbacks."""

        options = self._current_options()
        raw = options.get('weather_settings', {})
        if isinstance(raw, Mapping):
            current = cast(WeatherOptions, dict(raw))  # noqa: F405
        else:
            current = cast(WeatherOptions, {})  # noqa: F405

        if (
            WEATHER_ENTITY_FIELD not in current
            and (entity := options.get(CONF_WEATHER_ENTITY))  # noqa: F405
            and isinstance(entity, str)
        ):
            candidate = entity.strip()
            if candidate:
                current[WEATHER_ENTITY_FIELD] = candidate

        return current

    def _current_dog_options(self) -> DogOptionsMap:  # noqa: F405
        """Return the stored per-dog overrides keyed by dog ID."""

        raw = self._current_options().get(DOG_OPTIONS_FIELD, {})
        if not isinstance(raw, Mapping):
            return {}

        dog_options: DogOptionsMap = {}  # noqa: F405
        for dog_id, value in raw.items():
            if not isinstance(value, Mapping):
                continue
            entry = ensure_dog_options_entry(  # noqa: F405
                cast(JSONLikeMapping, dict(value)), dog_id=str(dog_id)
            )
            if entry:
                dog_options[str(dog_id)] = entry

        return dog_options

    def _require_current_dog(self) -> DogConfigData | None:  # noqa: F405
        """Return the current dog, defaulting when only one is configured."""

        if self._current_dog is not None:
            return self._current_dog

        if len(self._dogs) == 1:
            self._current_dog = self._dogs[0]
            return self._current_dog

        return None

    def _select_dog_by_id(self, dog_id: str | None) -> DogConfigData | None:  # noqa: F405
        """Select and store the current dog based on the provided identifier."""

        if not isinstance(dog_id, str):
            self._current_dog = None
            return None

        self._current_dog = next(
            (dog for dog in self._dogs if dog.get(DOG_ID_FIELD) == dog_id),  # noqa: F405
            None,
        )
        return self._current_dog

    def _build_dog_selector_schema(self) -> vol.Schema:
        """Return a schema for selecting a dog from the current list."""
        dog_options = [
            {
                'value': dog.get(DOG_ID_FIELD),  # noqa: F405
                'label': f"{dog.get(DOG_NAME_FIELD)} ({dog.get(DOG_ID_FIELD)})",  # noqa: F405
            }
            for dog in self._dogs
        ]

        return vol.Schema(
            {
                vol.Required('dog_id'): selector.SelectSelector(  # noqa: F405
                    selector.SelectSelectorConfig(  # noqa: F405
                        options=dog_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,  # noqa: F405
                    )
                )
            }
        )

    def _current_system_options(self) -> SystemOptions:
        """Return persisted system settings metadata."""

        options = self._current_options()
        raw = options.get('system_settings', {})
        if isinstance(raw, Mapping):
            system = cast(SystemOptions, dict(raw))
        else:
            system = cast(SystemOptions, {})

        enable_analytics = options.get('enable_analytics')
        enable_cloud_backup = options.get('enable_cloud_backup')

        if SYSTEM_ENABLE_ANALYTICS_FIELD not in system:
            system[SYSTEM_ENABLE_ANALYTICS_FIELD] = bool(enable_analytics)
        if SYSTEM_ENABLE_CLOUD_BACKUP_FIELD not in system:
            system[SYSTEM_ENABLE_CLOUD_BACKUP_FIELD] = bool(enable_cloud_backup)

        has_skip = 'resilience_skip_threshold' in system
        has_breaker = 'resilience_breaker_threshold' in system

        skip_default = self._resolve_resilience_threshold_default(
            system,
            options,
            field='resilience_skip_threshold',
            fallback=DEFAULT_RESILIENCE_SKIP_THRESHOLD,  # noqa: F405
        )
        breaker_default = self._resolve_resilience_threshold_default(
            system,
            options,
            field='resilience_breaker_threshold',
            fallback=DEFAULT_RESILIENCE_BREAKER_THRESHOLD,  # noqa: F405
        )

        script_skip, script_breaker = self._resolve_script_threshold_fallbacks(
            has_skip=has_skip,
            has_breaker=has_breaker,
        )

        skip_candidate = system.get('resilience_skip_threshold')
        breaker_candidate = system.get('resilience_breaker_threshold')

        system['resilience_skip_threshold'] = self._finalise_resilience_threshold(
            candidate=skip_candidate,
            default=skip_default,
            script_value=script_skip,
            include_script=not has_skip,
            minimum=RESILIENCE_SKIP_THRESHOLD_MIN,  # noqa: F405
            maximum=RESILIENCE_SKIP_THRESHOLD_MAX,  # noqa: F405
            fallback=DEFAULT_RESILIENCE_SKIP_THRESHOLD,  # noqa: F405
        )
        system['resilience_breaker_threshold'] = self._finalise_resilience_threshold(
            candidate=breaker_candidate,
            default=breaker_default,
            script_value=script_breaker,
            include_script=not has_breaker,
            minimum=RESILIENCE_BREAKER_THRESHOLD_MIN,  # noqa: F405
            maximum=RESILIENCE_BREAKER_THRESHOLD_MAX,  # noqa: F405
            fallback=DEFAULT_RESILIENCE_BREAKER_THRESHOLD,  # noqa: F405
        )

        return system

    def _resolve_manual_event_context(
        self,
        current_system: SystemOptions,
        *,
        manual_snapshot: Mapping[str, JSONValue] | None = None,
    ) -> JSONMutableMapping:
        """Return manual event suggestions sourced from runtime and defaults."""

        check_suggestions: set[str] = {
            DEFAULT_MANUAL_CHECK_EVENT,  # noqa: F405
        }
        guard_suggestions: set[str] = {
            'pawcontrol_manual_guard',
        }
        breaker_suggestions: set[str] = {
            'pawcontrol_manual_breaker',
        }

        check_default: str | None = self._coerce_manual_event(
            current_system.get('manual_check_event')
        )
        guard_default: str | None = self._coerce_manual_event(
            current_system.get('manual_guard_event')
        )
        breaker_default: str | None = self._coerce_manual_event(
            current_system.get('manual_breaker_event')
        )

        if manual_snapshot is None:
            manual_snapshot = self._manual_events_snapshot()

        if manual_snapshot is not None:
            system_guard = self._coerce_manual_event(
                manual_snapshot.get('system_guard_event')
            )
            system_breaker = self._coerce_manual_event(
                manual_snapshot.get('system_breaker_event')
            )

            if guard_default is None:
                guard_default = system_guard
            if breaker_default is None:
                breaker_default = system_breaker

            for event in self._string_sequence(
                manual_snapshot.get('configured_check_events')
            ):
                normalised = self._coerce_manual_event(event)
                if normalised is not None:
                    check_suggestions.add(normalised)
                    if check_default is None:
                        check_default = normalised

            for event in self._string_sequence(
                manual_snapshot.get('configured_guard_events')
            ):
                normalised = self._coerce_manual_event(event)
                if normalised is not None:
                    guard_suggestions.add(normalised)
            for event in self._string_sequence(
                manual_snapshot.get('configured_breaker_events')
            ):
                normalised = self._coerce_manual_event(event)
                if normalised is not None:
                    breaker_suggestions.add(normalised)

            if check_default is None:
                preferred = manual_snapshot.get('preferred_events')
                if isinstance(preferred, Mapping):
                    check_default = self._coerce_manual_event(
                        preferred.get('manual_check_event')
                    )
            if check_default is None:
                check_default = self._coerce_manual_event(
                    manual_snapshot.get('preferred_check_event')
                )

        if guard_default is not None:
            guard_suggestions.add(guard_default)
        if breaker_default is not None:
            breaker_suggestions.add(breaker_default)
        if check_default is not None:
            check_suggestions.add(check_default)

        result: JSONMutableMapping = {
            'check_suggestions': sorted(check_suggestions),
            'guard_suggestions': sorted(guard_suggestions),
            'breaker_suggestions': sorted(breaker_suggestions),
            'check_default': check_default,
            'guard_default': guard_default,
            'breaker_default': breaker_default,
        }
        return result

    @staticmethod
    def _resolve_resilience_threshold_default(
        system: SystemOptions,
        options: Mapping[str, JSONValue],
        *,
        field: str,
        fallback: int,
    ) -> int:
        """Return the default threshold from system options or legacy storage."""

        candidate = system.get(field)
        if isinstance(candidate, int):
            return candidate

        legacy_value = options.get(field)
        if isinstance(legacy_value, int):
            return legacy_value

        return fallback

    def _resolve_script_threshold_fallbacks(
        self, *, has_skip: bool, has_breaker: bool
    ) -> tuple[int | None, int | None]:
        """Return script thresholds when options are missing values."""

        if has_skip and has_breaker:
            return None, None

        hass = getattr(self, 'hass', None)
        if hass is None:
            return None, None

        return resolve_resilience_script_thresholds(hass, self._entry)  # noqa: F405

    def _finalise_resilience_threshold(
        self,
        *,
        candidate: Any,
        default: int,
        script_value: int | None,
        include_script: bool,
        minimum: int,
        maximum: int,
        fallback: int,
    ) -> int:
        """Return the stored threshold, falling back to script defaults when needed."""

        if include_script and script_value is not None:
            return self._coerce_clamped_int(
                script_value,
                fallback,
                minimum=minimum,
                maximum=maximum,
            )

        return self._coerce_clamped_int(
            candidate,
            default,
            minimum=minimum,
            maximum=maximum,
        )

    def _current_dashboard_options(self) -> DashboardOptions:
        """Return the stored dashboard configuration."""

        raw = self._current_options().get('dashboard_settings', {})
        if isinstance(raw, Mapping):
            return cast(DashboardOptions, dict(raw))
        return cast(DashboardOptions, {})

    def _current_advanced_options(self) -> AdvancedOptions:
        """Return advanced configuration merged with root fallbacks."""

        options = self._current_options()
        raw = options.get(ADVANCED_SETTINGS_FIELD)
        source = cast(JSONLikeMapping, dict(raw)) if isinstance(raw, Mapping) else {}
        defaults = cast(JSONMutableMapping, dict(options))
        return ensure_advanced_options(source, defaults=defaults)

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        """Return a boolean value using Home Assistant style truthiness rules."""

        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {'1', 'true', 'on', 'yes'}
        return bool(value)

    @staticmethod
    def _coerce_manual_event(value: Any) -> str | None:
        """Normalise manual event identifiers, returning ``None`` when disabled."""

        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate
        return None

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
        iso_format = getattr(value, 'isoformat', None)
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

    def _build_weather_settings(
        self,
        user_input: OptionsWeatherSettingsInput,  # noqa: F405
        current: WeatherOptions,  # noqa: F405
    ) -> WeatherOptions:  # noqa: F405
        """Create a typed weather configuration payload from submitted data."""

        raw_entity = user_input.get('weather_entity')
        entity: str | None
        if isinstance(raw_entity, str):
            candidate = raw_entity.strip()
            entity = None if not candidate or candidate.lower() == 'none' else candidate
        else:
            entity = cast(str | None, current.get(CONF_WEATHER_ENTITY))  # noqa: F405

        raw_interval_default = current.get('weather_update_interval')
        interval_default = (
            raw_interval_default if isinstance(raw_interval_default, int) else 60
        )
        interval = self._coerce_clamped_int(
            user_input.get('weather_update_interval'),
            interval_default,
            minimum=15,
            maximum=1440,
        )
        threshold_value = self._normalize_choice(
            user_input.get('notification_threshold'),
            valid={'low', 'moderate', 'high'},
            default=current.get('notification_threshold', 'moderate'),
        )
        notification_threshold = cast(NotificationThreshold, threshold_value)

        weather: WeatherOptions = {  # noqa: F405
            WEATHER_ENTITY_FIELD: entity,
            'weather_health_monitoring': self._coerce_bool(
                user_input.get('weather_health_monitoring'),
                current.get(
                    'weather_health_monitoring',
                    DEFAULT_WEATHER_HEALTH_MONITORING,  # noqa: F405
                ),
            ),
            'weather_alerts': self._coerce_bool(
                user_input.get('weather_alerts'),
                current.get('weather_alerts', DEFAULT_WEATHER_ALERTS),  # noqa: F405
            ),
            'weather_update_interval': interval,
            'temperature_alerts': self._coerce_bool(
                user_input.get('temperature_alerts'),
                current.get('temperature_alerts', True),
            ),
            'uv_alerts': self._coerce_bool(
                user_input.get('uv_alerts'),
                current.get('uv_alerts', True),
            ),
            'humidity_alerts': self._coerce_bool(
                user_input.get('humidity_alerts'),
                current.get('humidity_alerts', True),
            ),
            'wind_alerts': self._coerce_bool(
                user_input.get('wind_alerts'),
                current.get('wind_alerts', False),
            ),
            'storm_alerts': self._coerce_bool(
                user_input.get('storm_alerts'),
                current.get('storm_alerts', True),
            ),
            'breed_specific_recommendations': self._coerce_bool(
                user_input.get('breed_specific_recommendations'),
                current.get('breed_specific_recommendations', True),
            ),
            'health_condition_adjustments': self._coerce_bool(
                user_input.get('health_condition_adjustments'),
                current.get('health_condition_adjustments', True),
            ),
            'auto_activity_adjustments': self._coerce_bool(
                user_input.get('auto_activity_adjustments'),
                current.get('auto_activity_adjustments', False),
            ),
            'notification_threshold': notification_threshold,
        }

        return weather

    def _build_system_settings(
        self,
        user_input: OptionsSystemSettingsInput,
        current: SystemOptions,
        *,
        reset_default: str,
    ) -> tuple[SystemOptions, str]:
        """Create typed system settings and the reset time string."""

        retention = self._coerce_clamped_int(
            user_input.get('data_retention_days'),
            current.get('data_retention_days', 90),
            minimum=30,
            maximum=365,
        )
        performance_mode = normalize_performance_mode(
            user_input.get('performance_mode'),
            current=current.get('performance_mode'),
        )

        manual_defaults = self._manual_event_defaults(current)

        analytics_enabled = self._coerce_bool(
            user_input.get('enable_analytics'),
            current.get(SYSTEM_ENABLE_ANALYTICS_FIELD, False),
        )
        cloud_backup_enabled = self._coerce_bool(
            user_input.get('enable_cloud_backup'),
            current.get(SYSTEM_ENABLE_CLOUD_BACKUP_FIELD, False),
        )

        current_skip_threshold = current.get('resilience_skip_threshold')
        skip_default = (
            current_skip_threshold
            if isinstance(current_skip_threshold, int)
            else DEFAULT_RESILIENCE_SKIP_THRESHOLD  # noqa: F405
        )
        skip_threshold = self._coerce_clamped_int(
            user_input.get('resilience_skip_threshold'),
            skip_default,
            minimum=RESILIENCE_SKIP_THRESHOLD_MIN,  # noqa: F405
            maximum=RESILIENCE_SKIP_THRESHOLD_MAX,  # noqa: F405
        )

        current_breaker_threshold = current.get('resilience_breaker_threshold')
        breaker_default = (
            current_breaker_threshold
            if isinstance(current_breaker_threshold, int)
            else DEFAULT_RESILIENCE_BREAKER_THRESHOLD  # noqa: F405
        )
        breaker_threshold = self._coerce_clamped_int(
            user_input.get('resilience_breaker_threshold'),
            breaker_default,
            minimum=RESILIENCE_BREAKER_THRESHOLD_MIN,  # noqa: F405
            maximum=RESILIENCE_BREAKER_THRESHOLD_MAX,  # noqa: F405
        )

        system: SystemOptions = {
            'data_retention_days': retention,
            'auto_backup': self._coerce_bool(
                user_input.get('auto_backup'),
                current.get('auto_backup', False),
            ),
            'performance_mode': performance_mode,
            SYSTEM_ENABLE_ANALYTICS_FIELD: analytics_enabled,
            SYSTEM_ENABLE_CLOUD_BACKUP_FIELD: cloud_backup_enabled,
            'resilience_skip_threshold': skip_threshold,
            'resilience_breaker_threshold': breaker_threshold,
            'manual_check_event': self._coerce_manual_event_with_default(
                user_input.get('manual_check_event'),
                manual_defaults.get('manual_check_event'),
            ),
            'manual_guard_event': self._coerce_manual_event_with_default(
                user_input.get('manual_guard_event'),
                manual_defaults.get('manual_guard_event'),
            ),
            'manual_breaker_event': self._coerce_manual_event_with_default(
                user_input.get('manual_breaker_event'),
                manual_defaults.get('manual_breaker_event'),
            ),
        }

        if 'manual_guard_event' in user_input:
            guard_event = self._coerce_manual_event(
                user_input.get('manual_guard_event')
            )
            if guard_event is None:
                system['manual_guard_event'] = None
            else:
                system['manual_guard_event'] = guard_event
        elif 'manual_guard_event' in current:
            guard_event = self._coerce_manual_event(current.get('manual_guard_event'))
            if guard_event is not None:
                system['manual_guard_event'] = guard_event

        if 'manual_breaker_event' in user_input:
            breaker_event = self._coerce_manual_event(
                user_input.get('manual_breaker_event')
            )
            if breaker_event is None:
                system['manual_breaker_event'] = None
            else:
                system['manual_breaker_event'] = breaker_event
        elif 'manual_breaker_event' in current:
            breaker_event = self._coerce_manual_event(
                current.get('manual_breaker_event')
            )
            if breaker_event is not None:
                system['manual_breaker_event'] = breaker_event

        reset_time = self._coerce_time_string(
            user_input.get('reset_time'), reset_default
        )
        return system, reset_time

    def _build_dashboard_settings(
        self,
        user_input: OptionsDashboardSettingsInput,
        current: DashboardOptions,
        *,
        default_mode: str,
    ) -> tuple[DashboardOptions, str]:
        """Create typed dashboard configuration and selected mode."""

        valid_modes = {option['value'] for option in DASHBOARD_MODE_SELECTOR_OPTIONS}  # noqa: F405
        mode = self._normalize_choice(
            user_input.get('dashboard_mode'),
            valid=valid_modes,
            default=default_mode,
        )

        dashboard: DashboardOptions = {
            'show_statistics': self._coerce_bool(
                user_input.get('show_statistics'),
                current.get('show_statistics', True),
            ),
            'show_alerts': self._coerce_bool(
                user_input.get('show_alerts'),
                current.get('show_alerts', True),
            ),
            'compact_mode': self._coerce_bool(
                user_input.get('compact_mode'),
                current.get('compact_mode', False),
            ),
            'show_maps': self._coerce_bool(
                user_input.get('show_maps'),
                current.get('show_maps', True),
            ),
        }

        return dashboard, mode

    def _build_advanced_settings(
        self,
        user_input: OptionsAdvancedSettingsInput,
        current: AdvancedOptions,
    ) -> AdvancedOptions:
        """Create typed advanced configuration metadata."""

        endpoint_raw = user_input.get(
            CONF_API_ENDPOINT,  # noqa: F405
            current.get(CONF_API_ENDPOINT, ''),  # noqa: F405
        )
        endpoint = (
            endpoint_raw.strip()
            if isinstance(endpoint_raw, str)
            else str(current.get(CONF_API_ENDPOINT, ''))  # noqa: F405
        )
        token_raw = user_input.get(CONF_API_TOKEN, current.get(CONF_API_TOKEN, ''))  # noqa: F405
        token = (
            token_raw.strip()
            if isinstance(token_raw, str)
            else str(current.get(CONF_API_TOKEN, ''))  # noqa: F405
        )
        sanitized_input: JSONMutableMapping = {}
        for key, value in user_input.items():
            if isinstance(value, (bool, int, float, str)) or value is None:
                sanitized_input[str(key)] = value
            elif isinstance(value, Mapping):
                sanitized_input[str(key)] = cast(JSONValue, dict(value))
            elif isinstance(value, Sequence) and not isinstance(
                value, (str, bytes, bytearray)
            ):
                sanitized_input[str(key)] = cast(
                    JSONValue, [cast(JSONValue, item) for item in value]
                )
            else:
                _LOGGER.warning(
                    'Advanced options received non-JSON-serializable value for %s; '
                    'storing repr (%s)',
                    key,
                    type(value).__name__,
                )
                sanitized_input[str(key)] = repr(value)
        if CONF_API_ENDPOINT in user_input:  # noqa: F405
            sanitized_input[CONF_API_ENDPOINT] = endpoint  # noqa: F405
        if CONF_API_TOKEN in user_input:  # noqa: F405
            sanitized_input[CONF_API_TOKEN] = token  # noqa: F405

        current_advanced = self._current_options().get(ADVANCED_SETTINGS_FIELD, {})
        advanced_defaults = cast(
            JSONMutableMapping,
            dict(current_advanced) if isinstance(current_advanced, Mapping) else {},
        )
        return ensure_advanced_options(sanitized_input, defaults=advanced_defaults)
