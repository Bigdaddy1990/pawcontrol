"""Options flow for Paw Control integration with profile-based entity management.

This module provides comprehensive post-setup configuration options for the
Paw Control integration. It allows users to modify all aspects of their
configuration after initial setup with organized menu-driven navigation.

UPDATED: Adds entity profile selection for performance optimization
Integrates with EntityFactory for intelligent entity management
ENHANCED: GPS and Geofencing functionality per fahrplan.txt requirements

Quality Scale: Platinum target
P26.1.1++
Python: 3.13+
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from datetime import UTC
from importlib import import_module
from pathlib import Path
from typing import Any, ClassVar, Final, Literal, cast

from homeassistant.config_entries import OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry
from .const import (
  CONF_DOGS,
  CONF_LAST_RECONFIGURE,
  CONF_RECONFIGURE_TELEMETRY,
  DEFAULT_MANUAL_BREAKER_EVENT,
  DEFAULT_MANUAL_CHECK_EVENT,
  DEFAULT_MANUAL_GUARD_EVENT,
  MANUAL_EVENT_SOURCE_CANONICAL,
)
from .entity_factory import EntityFactory
from .exceptions import FlowValidationError
from .language import normalize_language
from .options_flow_dogs_management import DogManagementOptionsMixin
from .options_flow_door_sensor import DoorSensorOptionsMixin
from .options_flow_feeding import FeedingOptionsMixin
from .flows.gps import GPSOptionsMixin, GPSOptionsNormalizerMixin
from .flows.health import HealthOptionsMixin
from .flows.notifications import (
  NotificationOptionsMixin,
  NotificationOptionsNormalizerMixin,
)
from .options_flow_import_export import ImportExportOptionsMixin
from .options_flow_menu import MenuOptionsMixin
from .options_flow_profiles import ProfileOptionsMixin
from .options_flow_shared import ADVANCED_SETTINGS_FIELD
from .options_flow_system_settings import SystemSettingsOptionsMixin
from .runtime_data import get_runtime_data as _get_runtime_data
from .types import (
  ConfigFlowPlaceholders,
  DogConfigData,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  ManualEventField,
  ManualEventOption,
  ManualEventSource,
  ReconfigureTelemetry,
  SystemOptions,
  ensure_advanced_options,
  ensure_dog_config_data,
  ensure_json_mapping,
  PawControlRuntimeData,
)

_LOGGER = logging.getLogger(__name__)

RuntimeDataGetter = Callable[[HomeAssistant, ConfigEntry], PawControlRuntimeData | None]


def _resolve_setup_flag_supported_languages(
  translations_dir: Path,
  strings_path: Path,
) -> frozenset[str]:
  """Return the supported translation languages for setup flag localization."""

  languages = {path.stem for path in translations_dir.glob("*.json")}
  if strings_path.exists():
    languages.add("en")
  if not languages:
    languages.add("en")
  return frozenset(languages)


def _resolve_get_runtime_data() -> RuntimeDataGetter:
  """Return the patched runtime data helper when available."""

  try:
    support_module = import_module(
      "custom_components.pawcontrol.options_flow_support",
    )
    patched = getattr(support_module, "get_runtime_data", None)
    if callable(patched):
      return patched
  except Exception:
    pass
  return _get_runtime_data


LAST_RECONFIGURE_FIELD: Final[Literal["last_reconfigure"]] = cast(
  Literal["last_reconfigure"],
  CONF_LAST_RECONFIGURE,
)
RECONFIGURE_TELEMETRY_FIELD: Final[Literal["reconfigure_telemetry"]] = cast(
  Literal["reconfigure_telemetry"],
  CONF_RECONFIGURE_TELEMETRY,
)


class PawControlOptionsFlow(
  MenuOptionsMixin,
  ProfileOptionsMixin,
  DogManagementOptionsMixin,
  DoorSensorOptionsMixin,
  SystemSettingsOptionsMixin,
  ImportExportOptionsMixin,
  NotificationOptionsNormalizerMixin,
  GPSOptionsNormalizerMixin,
  NotificationOptionsMixin,
  GPSOptionsMixin,
  FeedingOptionsMixin,
  HealthOptionsMixin,
  OptionsFlow,
):
  """Handle options flow for Paw Control integration with Platinum UX goals.

  This comprehensive options flow allows users to modify all aspects
  of their Paw Control configuration after initial setup. It provides
  organized menu-driven navigation and extensive customization options
  with modern UI patterns and enhanced validation.

  UPDATED: Includes entity profile management for performance optimization
  ENHANCED: GPS and Geofencing configuration per requirements
  """

  _EXPORT_VERSION: ClassVar[int] = 1
  _MANUAL_EVENT_FIELDS: ClassVar[tuple[ManualEventField, ...]] = (
    "manual_check_event",
    "manual_guard_event",
    "manual_breaker_event",
  )
  _SETUP_FLAG_TRANSLATION_CACHE: ClassVar[dict[str, dict[str, str]]] = {}
  _SETUP_FLAG_EN_TRANSLATIONS: ClassVar[dict[str, str] | None] = None
  _SETUP_FLAG_PREFIXES: ClassVar[tuple[str, ...]] = (
    "setup_flags_panel_flag_",
    "setup_flags_panel_source_",
    "manual_event_source_badge_",
    "manual_event_source_help_",
  )
  _SETUP_FLAG_SOURCE_LABEL_KEYS: ClassVar[dict[ManualEventSource, str]] = {
    "default": "setup_flags_panel_source_default",
    "system_settings": "setup_flags_panel_source_system_settings",
    "options": "setup_flags_panel_source_options",
    "config_entry": "setup_flags_panel_source_config_entry",
    "blueprint": "setup_flags_panel_source_blueprint",
    "disabled": "setup_flags_panel_source_disabled",
  }
  _MANUAL_SOURCE_BADGE_KEYS: ClassVar[dict[ManualEventSource, str]] = {
    "default": "manual_event_source_badge_default",
    "system_settings": "manual_event_source_badge_system_settings",
    "options": "manual_event_source_badge_options",
    "config_entry": "manual_event_source_badge_config_entry",
    "blueprint": "manual_event_source_badge_blueprint",
    "disabled": "manual_event_source_badge_disabled",
  }
  _MANUAL_SOURCE_HELP_KEYS: ClassVar[dict[ManualEventSource, str]] = {
    "default": "manual_event_source_help_default",
    "system_settings": "manual_event_source_help_system_settings",
    "options": "manual_event_source_help_options",
    "config_entry": "manual_event_source_help_config_entry",
    "blueprint": "manual_event_source_help_blueprint",
    "disabled": "manual_event_source_help_disabled",
  }
  _MANUAL_SOURCE_PRIORITY: ClassVar[tuple[ManualEventSource, ...]] = (
    "system_settings",
    "options",
    "config_entry",
    "blueprint",
    "default",
  )
  _STRINGS_PATH: ClassVar[Path] = Path(__file__).with_name("strings.json")
  _TRANSLATIONS_DIR: ClassVar[Path] = Path(
    __file__,
  ).with_name("translations")
  _SETUP_FLAG_SUPPORTED_LANGUAGES: ClassVar[frozenset[str]] = (
    _resolve_setup_flag_supported_languages(_TRANSLATIONS_DIR, _STRINGS_PATH)
  )

  def __init__(self) -> None:
    """Initialize the options flow with enhanced state management."""
    super().__init__()
    self._entry = cast(ConfigEntry, None)
    self._current_dog: DogConfigData | None = None
    self._dogs: list[DogConfigData] = []
    self._navigation_stack: list[str] = []

    # Initialize entity factory and caches for profile calculations
    self._entity_factory = EntityFactory(None)
    self._profile_cache: dict[str, ConfigFlowPlaceholders] = {}
    self._entity_estimates_cache: dict[str, JSONMutableMapping] = {}

  def initialize_from_config_entry(self, config_entry: ConfigEntry) -> None:
    """Attach the originating config entry to this options flow."""

    self._entry = config_entry
    dogs_data_raw = config_entry.data.get(CONF_DOGS, [])
    dogs_iterable: Sequence[JSONLikeMapping] = (
      cast(Sequence[JSONLikeMapping], dogs_data_raw)
      if isinstance(dogs_data_raw, Sequence)
      and not isinstance(dogs_data_raw, bytes | str)
      else ()
    )
    self._dogs = []
    for dog in dogs_iterable:
      if not isinstance(dog, Mapping):
        continue
      normalised = ensure_dog_config_data(
        cast(Mapping[str, JSONValue], dog),
      )
      if normalised is not None:
        self._dogs.append(normalised)

  def _invalidate_profile_caches(self) -> None:
    """Clear cached profile data when configuration changes."""

    self._profile_cache.clear()
    self._entity_estimates_cache.clear()

  def _current_options(self) -> Mapping[str, JSONValue]:
    """Return the current config entry options as a typed mapping."""

    return cast(Mapping[str, JSONValue], self._entry.options)

  def _clone_options(self) -> dict[str, JSONValue]:
    """Return a shallow copy of the current options for mutation."""

    return cast(
      dict[str, JSONValue],
      dict(cast(Mapping[str, JSONValue], self._entry.options)),
    )

  def _normalise_options_snapshot(
    self,
    options: Mapping[str, JSONValue] | JSONMutableMapping,
  ) -> Mapping[str, JSONValue]:
    """Return a typed options mapping with notifications and dog entries coerced."""

    mutable = ensure_json_mapping(options)
    self._normalise_notification_options(mutable)
    self._normalise_gps_options_snapshot(mutable)

    if ADVANCED_SETTINGS_FIELD in mutable:
      raw_advanced = mutable.get(ADVANCED_SETTINGS_FIELD)
      advanced_source = (
        cast(Mapping[str, JSONValue], raw_advanced)
        if isinstance(raw_advanced, Mapping)
        else {}
      )
      mutable[ADVANCED_SETTINGS_FIELD] = cast(
        JSONValue,
        ensure_advanced_options(
          cast(JSONLikeMapping, dict(advanced_source)),
          defaults=cast(JSONLikeMapping, dict(mutable)),
        ),
      )

    return cast(Mapping[str, JSONValue], mutable)

  def _normalise_entry_dogs(
    self,
    dogs: Sequence[Mapping[str, JSONValue]],
  ) -> list[DogConfigData]:
    """Return typed dog configurations for entry persistence."""

    typed_dogs: list[DogConfigData] = []
    for dog in dogs:
      normalised = ensure_dog_config_data(
        cast(Mapping[str, JSONValue], dog),
      )
      if normalised is None:
        raise FlowValidationError(base_errors=["invalid_dog_config"])
      typed_dogs.append(normalised)
    return typed_dogs

  def _last_reconfigure_timestamp(self) -> str | None:
    """Return the ISO timestamp recorded for the last reconfigure run."""

    value = self._entry.options.get(LAST_RECONFIGURE_FIELD)
    return str(value) if isinstance(value, str) and value else None

  def _reconfigure_telemetry(self) -> ReconfigureTelemetry | None:
    """Return the stored reconfigure telemetry, if available."""

    telemetry = self._entry.options.get(RECONFIGURE_TELEMETRY_FIELD)
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

  @classmethod
  def _load_setup_flag_translations_from_mapping(
    cls,
    mapping: Mapping[str, JSONValue],
  ) -> dict[str, str]:
    """Extract setup flag translations from a loaded JSON mapping."""

    common = (
      mapping.get("common")
      if isinstance(
        mapping,
        Mapping,
      )
      else None
    )
    if not isinstance(common, Mapping):
      return {}

    translations: dict[str, str] = {}
    for key, value in common.items():
      if not isinstance(key, str) or not isinstance(value, str):
        continue
      if any(key.startswith(prefix) for prefix in cls._SETUP_FLAG_PREFIXES):
        translations[key] = value
    return translations

  @classmethod
  async def _load_setup_flag_translations_from_path(
    cls,
    path: Path,
    hass: HomeAssistant,
  ) -> dict[str, str]:
    """Load setup flag translations from a JSON file if it exists."""

    try:
      raw = await hass.async_add_executor_job(path.read_text, "utf-8")
      content = json.loads(raw)
    except FileNotFoundError:
      return {}
    except ValueError:  # pragma: no cover - defensive against malformed JSON
      _LOGGER.warning(
        "Failed to parse setup flag translations from %s",
        path,
      )
      return {}

    if not isinstance(content, Mapping):
      return {}

    return cls._load_setup_flag_translations_from_mapping(content)

  @classmethod
  def _load_setup_flag_translations_from_path_sync(
    cls,
    path: Path,
  ) -> dict[str, str]:
    """Synchronously load setup flag translations from a JSON file."""

    try:
      content = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
      return {}
    except ValueError:  # pragma: no cover - defensive against malformed JSON
      _LOGGER.warning(
        "Failed to parse setup flag translations from %s",
        path,
      )
      return {}

    if not isinstance(content, Mapping):
      return {}

    return cls._load_setup_flag_translations_from_mapping(content)

  @classmethod
  async def _async_setup_flag_translations_for_language(
    cls,
    language: str,
    hass: HomeAssistant,
  ) -> dict[str, str]:
    """Return setup flag translations for the provided language."""

    if cls._SETUP_FLAG_EN_TRANSLATIONS is None:
      cls._SETUP_FLAG_EN_TRANSLATIONS = (
        await cls._load_setup_flag_translations_from_path(
          cls._STRINGS_PATH,
          hass=hass,
        )
      )

    base = cls._SETUP_FLAG_EN_TRANSLATIONS or {}
    if language == "en":
      return base

    cached = cls._SETUP_FLAG_TRANSLATION_CACHE.get(language)
    if cached is not None:
      return cached

    translation_path = cls._TRANSLATIONS_DIR / f"{language}.json"
    overlay = await cls._load_setup_flag_translations_from_path(
      translation_path,
      hass=hass,
    )
    merged = dict(base)
    merged.update(overlay)
    cls._SETUP_FLAG_TRANSLATION_CACHE[language] = merged
    return merged

  @classmethod
  def _setup_flag_translations_for_language(cls, language: str) -> dict[str, str]:
    """Return setup flag translations for the provided language."""

    if cls._SETUP_FLAG_EN_TRANSLATIONS is None:
      cls._SETUP_FLAG_EN_TRANSLATIONS = (
        cls._load_setup_flag_translations_from_path_sync(cls._STRINGS_PATH)
      )

    base = cls._SETUP_FLAG_EN_TRANSLATIONS or {}
    if language == "en":
      return base

    cached = cls._SETUP_FLAG_TRANSLATION_CACHE.get(language)
    if cached is not None:
      return cached

    overlay = cls._load_setup_flag_translations_from_path_sync(
      cls._TRANSLATIONS_DIR / f"{language}.json",
    )
    merged = dict(base)
    merged.update(overlay)
    cls._SETUP_FLAG_TRANSLATION_CACHE[language] = merged
    return merged

  def _determine_language(self) -> str:
    """Return the preferred language for localized labels."""

    hass = getattr(self, "hass", None)
    hass_language: str | None = None
    if hass is not None:
      config = getattr(hass, "config", None)
      if config is not None:
        hass_language = getattr(config, "language", None)

    return normalize_language(
      hass_language,
      supported=self._SETUP_FLAG_SUPPORTED_LANGUAGES,
      default="en",
    )

  def _setup_flag_translation(self, key: str, *, language: str) -> str:
    """Return the localized string for the provided setup flag key."""

    translations = self._setup_flag_translations_for_language(language)
    return translations.get(key, key)

  async def _async_prepare_setup_flag_translations(self) -> None:
    """Preload setup flag translations without blocking the event loop."""

    language = self._determine_language()
    hass = getattr(self, "hass", None)
    if not isinstance(hass, HomeAssistant):
      return
    await self._async_setup_flag_translations_for_language(language, hass)

  @staticmethod
  def _normalise_manual_event_value(value: Any) -> str | None:
    """Return a normalised manual event string."""

    if isinstance(value, str):
      candidate = value.strip()
      return candidate or None
    return None

  def _manual_event_defaults(
    self,
    current: SystemOptions,
  ) -> dict[ManualEventField, str | None]:
    """Return preferred manual event defaults for the system settings form."""

    defaults: dict[ManualEventField, str | None] = {
      "manual_check_event": DEFAULT_MANUAL_CHECK_EVENT,
      "manual_guard_event": DEFAULT_MANUAL_GUARD_EVENT,
      "manual_breaker_event": DEFAULT_MANUAL_BREAKER_EVENT,
    }

    for field in self._MANUAL_EVENT_FIELDS:
      if field not in current:
        continue
      defaults[field] = self._normalise_manual_event_value(
        current.get(field),
      )

    return defaults

  def _manual_event_schema_defaults(
    self,
    current: SystemOptions,
  ) -> dict[ManualEventField, str]:
    """Return schema defaults for manual event inputs as strings."""

    defaults = self._manual_event_defaults(current)
    return {key: value or "" for key, value in defaults.items()}

  def _manual_events_snapshot(self) -> Mapping[str, JSONValue] | None:
    """Return the current manual events snapshot from the script manager."""

    hass = getattr(self, "hass", None)
    if hass is None:
      return None

    runtime: Any | None = None
    with suppress(Exception):
      runtime = _resolve_get_runtime_data()(hass, self._entry)
    if runtime is None:
      return None

    script_manager = getattr(runtime, "script_manager", None)
    if script_manager is None:
      return None

    snapshot = script_manager.get_resilience_escalation_snapshot()
    if not isinstance(snapshot, Mapping):
      return None

    manual_section = snapshot.get("manual_events")
    if isinstance(manual_section, Mapping):
      return cast(Mapping[str, JSONValue], manual_section)
    return None

  def _collect_manual_event_sources(
    self,
    field: ManualEventField,
    current: SystemOptions,
    *,
    manual_snapshot: Mapping[str, JSONValue] | None = None,
  ) -> dict[str, set[ManualEventSource]]:
    """Return known manual events mapped to their source categories."""

    sources: dict[str, set[ManualEventSource]] = {}

    def _register(value: Any, source: ManualEventSource) -> None:
      normalised = self._normalise_manual_event_value(value)
      if not normalised:
        return
      sources.setdefault(normalised, set()).add(source)

    def _as_manual_event_source(source: object) -> ManualEventSource | None:
      if isinstance(source, str) and source in self._MANUAL_SOURCE_BADGE_KEYS:
        return cast(ManualEventSource, source)
      return None

    default_map = {
      "manual_check_event": DEFAULT_MANUAL_CHECK_EVENT,
      "manual_guard_event": DEFAULT_MANUAL_GUARD_EVENT,
      "manual_breaker_event": DEFAULT_MANUAL_BREAKER_EVENT,
    }
    default_value = self._normalise_manual_event_value(default_map[field])

    current_options = self._current_options()
    _register(current_options.get(field), "options")

    options_settings = current_options.get("system_settings")
    if isinstance(options_settings, Mapping):
      _register(options_settings.get(field), "system_settings")

    _register(current.get(field), "system_settings")

    if manual_snapshot is None:
      manual_snapshot = self._manual_events_snapshot()

    if isinstance(manual_snapshot, Mapping):
      configured_key_map = {
        "manual_check_event": "configured_check_events",
        "manual_guard_event": "configured_guard_events",
        "manual_breaker_event": "configured_breaker_events",
      }
      configured_values = manual_snapshot.get(configured_key_map[field])
      for candidate in self._string_sequence(configured_values):
        _register(candidate, "blueprint")

      if field != "manual_check_event":
        system_key_map = {
          "manual_guard_event": "system_guard_event",
          "manual_breaker_event": "system_breaker_event",
        }
        system_value = manual_snapshot.get(
          system_key_map.get(field, ""),
        )
        _register(system_value, "system_settings")

      preferred = manual_snapshot.get("preferred_events")
      if isinstance(preferred, Mapping):
        preferred_value = self._normalise_manual_event_value(
          preferred.get(field),
        )
        if preferred_value and preferred_value != default_map[field]:
          _register(preferred_value, "system_settings")

      specific_preference = manual_snapshot.get(f"preferred_{field}")
      specific_normalised = self._normalise_manual_event_value(
        specific_preference,
      )
      if specific_normalised and specific_normalised != default_map[field]:
        _register(specific_normalised, "system_settings")

      listener_sources = manual_snapshot.get("listener_sources")
      if isinstance(listener_sources, Mapping):
        for event, raw_sources in listener_sources.items():
          if not isinstance(event, str):
            continue
          for raw_source in self._string_sequence(raw_sources):
            mapped = MANUAL_EVENT_SOURCE_CANONICAL.get(
              raw_source,
              raw_source,
            )
            source = _as_manual_event_source(mapped)
            if source:
              _register(event, source)

      metadata = manual_snapshot.get("listener_metadata")
      if isinstance(metadata, Mapping):
        for event, info in metadata.items():
          if not isinstance(event, str) or not isinstance(info, Mapping):
            continue
          canonical_sources = info.get("sources")
          for canonical in self._string_sequence(canonical_sources):
            source = _as_manual_event_source(canonical)
            if source:
              _register(event, source)
          primary_source = info.get("primary_source")
          source = _as_manual_event_source(primary_source)
          if source:
            _register(event, source)

    if default_value:
      existing_sources = sources.get(default_value)
      if existing_sources is None:
        sources[default_value] = {"default"}
      elif (
        field == "manual_guard_event"
        and "blueprint" in existing_sources
        and not (existing_sources - {"blueprint"})
      ):
        # Blueprint-only defaults should not inherit the integration default tag.
        pass
      else:
        existing_sources.add("default")

    return sources

  def _manual_event_choices(
    self,
    field: ManualEventField,
    current: SystemOptions,
    *,
    manual_snapshot: Mapping[str, JSONValue] | None = None,
  ) -> list[ManualEventOption]:
    """Return select options for manual event configuration."""

    language = self._determine_language()

    disabled_label = self._setup_flag_translation(
      self._SETUP_FLAG_SOURCE_LABEL_KEYS["disabled"],
      language=language,
    )
    disabled_description = self._setup_flag_translation(
      self._SETUP_FLAG_SOURCE_LABEL_KEYS["default"],
      language=language,
    )

    def _primary_source(source_set: set[ManualEventSource]) -> ManualEventSource | None:
      for candidate in self._MANUAL_SOURCE_PRIORITY:
        if candidate in source_set:
          return candidate
      if "disabled" in source_set:
        return "disabled"
      if source_set:
        return sorted(source_set)[0]
      return None

    def _source_badge(source: ManualEventSource | None) -> str | None:
      if not source:
        return None
      translation_key = self._MANUAL_SOURCE_BADGE_KEYS.get(source)
      if not translation_key:
        return None
      return self._setup_flag_translation(translation_key, language=language)

    def _help_text(source_list: Sequence[ManualEventSource]) -> str | None:
      help_segments: list[str] = []
      for source_name in source_list:
        key = self._MANUAL_SOURCE_HELP_KEYS.get(source_name)
        if key:
          help_segments.append(
            self._setup_flag_translation(key, language=language),
          )
      if help_segments:
        return " ".join(help_segments)
      return None

    disabled_sources: list[ManualEventSource] = ["disabled"]
    disabled_badge = _source_badge("disabled")
    disabled_help = _help_text(disabled_sources)
    disabled_option: ManualEventOption = {
      "value": "",
      "label": disabled_label,
      "description": disabled_description,
      "metadata_sources": disabled_sources,
      "metadata_primary_source": "disabled",
    }
    if disabled_badge:
      disabled_option["badge"] = disabled_badge
    if disabled_help:
      disabled_option["help_text"] = disabled_help

    options: list[ManualEventOption] = [disabled_option]

    event_sources = self._collect_manual_event_sources(
      field,
      current,
      manual_snapshot=manual_snapshot,
    )

    current_value = self._normalise_manual_event_value(current.get(field))

    def _priority(item: tuple[str, set[str]]) -> tuple[int, str]:
      value, sources = item
      if current_value and value == current_value:
        return (0, value)
      if "system_settings" in sources:
        return (1, value)
      if "options" in sources:
        return (2, value)
      if "blueprint" in sources:
        return (3, value)
      if "default" in sources:
        return (4, value)
      return (5, value)

    for value, source_tags in sorted(event_sources.items(), key=_priority):
      description_parts: list[str] = []
      sorted_sources = sorted(source_tags)
      for source in sorted_sources:
        if source == "default" and "blueprint" in source_tags:
          # Blueprint suggestions inherit the integration default but should not
          # surface that tag in the description list.
          continue
        key = self._SETUP_FLAG_SOURCE_LABEL_KEYS.get(source)
        if key:
          description_parts.append(
            self._setup_flag_translation(key, language=language),
          )

      option: ManualEventOption = {"value": value, "label": value}
      if description_parts:
        option["description"] = ", ".join(description_parts)
      primary_source = _primary_source(source_tags)
      badge = _source_badge(primary_source)
      if badge:
        option["badge"] = badge
      help_text = _help_text(sorted_sources)
      if help_text:
        option["help_text"] = help_text
      option["metadata_sources"] = sorted_sources
      if primary_source:
        option["metadata_primary_source"] = primary_source
      options.append(option)

    return options

  def _resolve_manual_event_choices(self) -> dict[ManualEventField, list[str]]:
    """Return configured manual event identifiers for blueprint helpers."""

    current_system = self._current_system_options()
    manual_snapshot = self._manual_events_snapshot()

    choices: dict[str, list[str]] = {}
    for field in self._MANUAL_EVENT_FIELDS:
      options = self._manual_event_choices(
        field,
        current_system,
        manual_snapshot=manual_snapshot,
      )
      values: list[str] = []
      for option in options:
        if not isinstance(option, Mapping):
          continue
        value = option.get("value")
        if isinstance(value, str) and value:
          values.append(value)
      choices[field] = values

    return choices
