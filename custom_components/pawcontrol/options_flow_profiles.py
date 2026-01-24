"""Entity profile and performance related steps for the PawControl options flow."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .config_flow_profile import (
  DEFAULT_PROFILE,
  get_profile_selector_options,
  validate_profile_selection,
)
from .const import (
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOGS,
  MODULE_GPS,
  MODULE_HEALTH,
)
from .entity_factory import ENTITY_PROFILES
from .selector_shim import selector
from .types import (
  RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE,
  ConfigFlowPlaceholders,
  DogConfigData,
  JSONMutableMapping,
  JSONValue,
  MutableConfigFlowPlaceholders,
  ProfileSelectionInput,
  clone_placeholders,
  ensure_dog_config_data,
  ensure_dog_modules_config,
  ensure_dog_modules_mapping,
  freeze_placeholders,
  normalize_performance_mode,
)

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
  from .compat import ConfigEntry
  from .entity_factory import EntityFactory

  class ProfileOptionsHost(Protocol):
    @property
    def _entry(self) -> ConfigEntry: ...
    _profile_cache: dict[str, ConfigFlowPlaceholders]
    _entity_estimates_cache: dict[str, JSONMutableMapping]
    _entity_factory: EntityFactory

    def __getattr__(self, name: str) -> Any: ...

else:  # pragma: no cover
  ProfileOptionsHost = object


class ProfileOptionsMixin(ProfileOptionsHost):
  _entry: ConfigEntry
  _profile_cache: dict[str, ConfigFlowPlaceholders]
  _entity_estimates_cache: dict[str, JSONMutableMapping]

  async def async_step_entity_profiles(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure entity profiles for performance optimization.

    NEW: Allows users to select entity profiles that determine
    how many entities are created per dog.
    """
    if user_input is not None:
      try:
        current_profile = validate_profile_selection(
          cast(ProfileSelectionInput, user_input),
        )
        preview_estimate = user_input.get("preview_estimate", False)

        if preview_estimate:
          # Show entity count preview
          return await self.async_step_profile_preview(
            {"profile": current_profile},
          )

        # Save the profile selection
        merged_options = {
          **self._entry.options,
          "entity_profile": current_profile,
        }
        typed_options = self._normalise_options_snapshot(
          merged_options,
        )
        self._invalidate_profile_caches()

        return self.async_create_entry(title="", data=typed_options)

      except vol.Invalid as err:
        _LOGGER.warning(
          "Invalid profile selection in options flow: %s",
          err,
        )
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
      description_placeholders=dict(
        self._get_profile_description_placeholders(),
      ),
    )

  def _get_entity_profiles_schema(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> vol.Schema:
    """Get entity profiles schema with current values."""
    current_options = self._entry.options
    current_values: JSONMutableMapping = cast(
      JSONMutableMapping,
      dict(user_input or {}),
    )
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
          "entity_profile",
          default=current_profile,
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=profile_options,
            mode=selector.SelectSelectorMode.DROPDOWN,
          ),
        ),
        vol.Optional(
          "preview_estimate",
          default=False,
        ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
      },
    )

  def _get_profile_description_placeholders_cached(self) -> ConfigFlowPlaceholders:
    """Get description placeholders with caching for better performance."""

    dogs_raw = self._entry.data.get(CONF_DOGS, [])
    current_dogs: list[DogConfigData] = []
    if isinstance(dogs_raw, Sequence):
      for dog in dogs_raw:
        if not isinstance(dog, Mapping):
          continue
        normalised = ensure_dog_config_data(
          cast(Mapping[str, JSONValue], dog),
        )
        if normalised is not None:
          current_dogs.append(normalised)
    current_dogs = cast(list[DogConfigData], current_dogs)
    current_dogs = cast(list[DogConfigData], current_dogs)
    dog_entries: list[Mapping[str, JSONValue]] = cast(
      list[Mapping[str, JSONValue]],
      current_dogs,
    )

    current_profile_raw = self._entry.options.get(
      "entity_profile",
      DEFAULT_PROFILE,
    )
    current_profile = (
      current_profile_raw
      if isinstance(current_profile_raw, str)
      else str(current_profile_raw)
    )
    telemetry = self._reconfigure_telemetry()
    telemetry_digest = ""
    if telemetry:
      try:
        telemetry_digest = json.dumps(
          self._normalise_export_value(dict(telemetry)),
          sort_keys=True,
        )
      except (TypeError, ValueError):
        telemetry_digest = repr(sorted(telemetry.items()))
    serializable_dogs = [cast(JSONMutableMapping, dict(dog)) for dog in current_dogs]
    cache_key = (
      f"{current_profile}_{len(current_dogs)}_"
      f"{hash(json.dumps(serializable_dogs, sort_keys=True))}_"
      f"{self._last_reconfigure_timestamp() or ''}_"
      f"{hash(telemetry_digest)}"
    )

    cached = self._profile_cache.get(cache_key)
    if cached is not None:
      return cached

    total_estimate = 0
    profile_compatibility_issues: list[str] = []

    profile_info = ENTITY_PROFILES.get(
      current_profile,
      ENTITY_PROFILES[DEFAULT_PROFILE],
    )
    max_entities_value = profile_info.get("max_entities", 0)
    max_entities = (
      int(max_entities_value)
      if isinstance(max_entities_value, int | float | str)
      else 0
    )
    profile_description = str(profile_info.get("description", ""))
    str(profile_info.get("performance_impact", ""))

    dog_entries_local = dog_entries

    for dog_config in dog_entries_local:
      modules_config = ensure_dog_modules_mapping(dog_config)
      estimate = self._entity_factory.estimate_entity_count(
        current_profile,
        modules_config,
      )
      total_estimate += estimate

      if not self._entity_factory.validate_profile_for_modules(
        current_profile,
        modules_config,
      ):
        dog_name = dog_config.get(CONF_DOG_NAME, "Unknown")
        profile_compatibility_issues.append(
          f"{dog_name} modules may not be optimal for {current_profile}",
        )

    total_capacity = max_entities * len(dog_entries_local)
    utilization = (
      f"{(total_estimate / total_capacity * 100):.1f}" if total_capacity > 0 else "0"
    )

    placeholders: MutableConfigFlowPlaceholders = clone_placeholders(
      RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE,
    )
    placeholders.update(
      {
        "current_profile": current_profile,
        "current_description": profile_description,
        "dogs_count": str(len(dog_entries_local)),
        "estimated_entities": str(total_estimate),
        "max_entities_per_dog": str(max_entities),
        "performance_impact": self._get_performance_impact_description(
          current_profile or DEFAULT_PROFILE,
        ),
        "compatibility_warnings": "; ".join(profile_compatibility_issues)
        if profile_compatibility_issues
        else "No compatibility issues",
        "utilization_percentage": utilization,
      },
    )

    placeholders.update(
      clone_placeholders(
        self._get_reconfigure_description_placeholders(),
      ),
    )

    frozen_placeholders = freeze_placeholders(placeholders)
    self._profile_cache[cache_key] = frozen_placeholders
    return frozen_placeholders

  def _get_profile_description_placeholders(self) -> ConfigFlowPlaceholders:
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
    self,
    profile: str,
  ) -> JSONMutableMapping:
    """Calculate profile preview with optimized performance."""

    dogs_raw = self._entry.data.get(CONF_DOGS, [])
    current_dogs: list[DogConfigData] = []
    if isinstance(dogs_raw, Sequence):
      for dog in dogs_raw:
        if not isinstance(dog, Mapping):
          continue
        normalised = ensure_dog_config_data(
          cast(Mapping[str, JSONValue], dog),
        )
        if normalised is not None:
          current_dogs.append(normalised)
    dog_entries = cast(list[Mapping[str, JSONValue]], current_dogs)

    cache_key = (
      f"{profile}_{len(current_dogs)}_{hash(json.dumps(current_dogs, sort_keys=True))}"
    )

    cached_preview = self._entity_estimates_cache.get(cache_key)
    if cached_preview is not None:
      return cached_preview

    entity_breakdown: list[JSONMutableMapping] = []
    total_entities = 0
    performance_score = 100.0

    profile_info = ENTITY_PROFILES.get(
      profile,
      ENTITY_PROFILES["standard"],
    )
    max_entities_value = profile_info.get("max_entities", 0)
    max_entities = (
      int(max_entities_value)
      if isinstance(max_entities_value, int | float | str)
      else 0
    )

    for dog_config in dog_entries:
      dog_name = dog_config.get(CONF_DOG_NAME, "Unknown")
      dog_id = dog_config.get(CONF_DOG_ID, "unknown")
      modules_config = ensure_dog_modules_mapping(dog_config)

      estimate = self._entity_factory.estimate_entity_count(
        profile,
        modules_config,
      )
      total_entities += estimate

      enabled_modules = [
        module for module, enabled in modules_config.items() if enabled
      ]
      utilization = (estimate / max_entities) * 100 if max_entities > 0 else 0

      entity_breakdown.append(
        cast(
          JSONMutableMapping,
          {
            "dog_name": dog_name,
            "dog_id": dog_id,
            "entities": estimate,
            "modules": enabled_modules,
            "utilization": utilization,
          },
        ),
      )

      if utilization > 80:
        performance_score -= 10
      elif utilization > 60:
        performance_score -= 5

    raw_profile = self._entry.options.get("entity_profile")
    current_profile = (
      raw_profile
      if isinstance(
        raw_profile,
        str,
      )
      else "standard"
    )
    if profile == current_profile:
      current_total = total_entities
    else:
      current_total = 0
      for dog_config in dog_entries:
        modules = ensure_dog_modules_mapping(dog_config)
        current_total += self._entity_factory.estimate_entity_count(
          current_profile,
          modules,
        )

    entity_difference = total_entities - current_total

    preview: JSONMutableMapping = {
      "profile": profile,
      "total_entities": total_entities,
      "entity_breakdown": entity_breakdown,
      "current_total": current_total,
      "entity_difference": entity_difference,
      "performance_score": performance_score,
      "recommendation": self._get_profile_recommendation_enhanced(
        total_entities,
        len(current_dogs),
        performance_score,
      ),
      "warnings": self._get_profile_warnings(profile, current_dogs),
    }

    self._entity_estimates_cache[cache_key] = preview
    return preview

  def _get_profile_recommendation_enhanced(
    self,
    total_entities: int,
    dog_count: int,
    performance_score: float,
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
    self,
    profile: str,
    dogs: list[DogConfigData],
  ) -> list[str]:
    """Get profile-specific warnings and recommendations."""

    warnings: list[str] = []

    for dog in dogs:
      dog_config = cast(DogConfigData, dog)
      module_flags = ensure_dog_modules_mapping(
        cast(Mapping[str, JSONValue], dog_config),
      )
      dog_name = dog_config.get(CONF_DOG_NAME, "Unknown")

      if profile == "gps_focus" and not module_flags.get(MODULE_GPS, False):  # noqa: F821
        warnings.append(
          f"🛰️ {dog_name}: GPS focus profile but GPS module disabled",
        )

      if profile == "health_focus" and not module_flags.get(MODULE_HEALTH, False):  # noqa: F821
        warnings.append(
          f"🏥 {dog_name}: Health focus profile but health module disabled",
        )

      if profile == "basic" and sum(module_flags.values()) > 3:
        warnings.append(
          f"⚡ {dog_name}: Many modules enabled for basic profile",
        )

    return warnings

  async def async_step_profile_preview(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Show entity count preview for selected profile.

    NEW: Provides detailed breakdown of entity counts per dog
    """
    raw_profile = user_input.get("profile") if user_input else None
    profile = raw_profile if isinstance(raw_profile, str) else "standard"

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

    def as_float(value):
      return float(value) if isinstance(value, int | float) else 0.0

    def as_int(value):
      return int(value) if isinstance(value, int | float) else 0

    entity_breakdown = cast(
      list[JSONMutableMapping],
      preview_data.get("entity_breakdown", []),
    )
    for item in entity_breakdown:
      modules_raw = item.get("modules", ())
      modules_sequence = (
        modules_raw
        if isinstance(modules_raw, Sequence) and not isinstance(modules_raw, str)
        else ()
      )
      modules_display = (
        ", ".join(
          cast(Sequence[str], modules_sequence),
        )
        or "none"
      )
      breakdown_lines.append(
        f"• {item.get('dog_name', 'Unknown')}: {item.get('entities', 0)} "
        f"entities (modules: {modules_display}, "
        f"utilization: {as_float(item.get('utilization', 0.0)):.1f}%)",
      )

    performance_change = (
      "same"
      if as_int(preview_data.get("entity_difference", 0)) == 0
      else (
        "better"
        if as_int(preview_data.get("entity_difference", 0)) < 0
        else "higher resource usage"
      )
    )

    warnings_raw = preview_data.get("warnings", [])
    warnings_sequence = (
      warnings_raw
      if isinstance(warnings_raw, Sequence) and not isinstance(warnings_raw, str)
      else ()
    )
    warnings_text = (
      "\n".join(cast(Sequence[str], warnings_sequence))
      if warnings_sequence
      else "No warnings"
    )

    profile_info = ENTITY_PROFILES.get(
      profile,
      ENTITY_PROFILES["standard"],
    )

    return self.async_show_form(
      step_id="profile_preview",
      data_schema=vol.Schema(
        {
          vol.Required("profile", default=profile): vol.In([profile]),
          vol.Optional(
            "apply_profile",
            default=False,
          ): selector.BooleanSelector(),
        },
      ),
      description_placeholders=dict(
        freeze_placeholders(
          {
            "profile_name": str(preview_data["profile"]),
            "total_entities": str(preview_data["total_entities"]),
            "entity_breakdown": "\n".join(breakdown_lines),
            "current_total": str(preview_data["current_total"]),
            "entity_difference": (
              f"{preview_data['entity_difference']:+d}"
              if preview_data["entity_difference"]
              else "0"
            ),
            "performance_change": str(performance_change),
            "profile_description": str(profile_info.get("description", "")),
            "performance_score": f"{preview_data['performance_score']:.1f}",
            "recommendation": str(preview_data["recommendation"]),
            "warnings": warnings_text,
          },
        ),
      ),
    )

  async def async_step_performance_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure performance and optimization settings.

    NEW: Combines entity profiles with other performance settings
    """
    if user_input is not None:
      try:
        current_options = self._current_options()
        new_options = self._clone_options()

        profile_candidate = user_input.get(
          "entity_profile",
          current_options.get("entity_profile", DEFAULT_PROFILE),
        )
        profile_input = (
          profile_candidate
          if isinstance(profile_candidate, str)
          else str(profile_candidate)
        )
        profile = validate_profile_selection(
          {"entity_profile": profile_input},
        )

        raw_batch = current_options.get("batch_size")
        if isinstance(raw_batch, int):
          batch_default: int = raw_batch
        else:
          batch_default = 15

        raw_cache = current_options.get("cache_ttl")
        if isinstance(raw_cache, int):
          cache_default: int = raw_cache
        else:
          cache_default = 300
        selective_default = bool(
          current_options.get("selective_refresh", True),
        )

        new_options["entity_profile"] = profile
        new_options["performance_mode"] = normalize_performance_mode(  # noqa: F821
          user_input.get("performance_mode")
          if isinstance(user_input.get("performance_mode"), str)
          else None,
          current=(
            current_options.get("performance_mode")
            if isinstance(current_options.get("performance_mode"), str)
            else None
          ),
        )
        new_options["batch_size"] = self._coerce_int(
          user_input.get("batch_size"),
          batch_default,
        )
        new_options["cache_ttl"] = self._coerce_int(
          user_input.get("cache_ttl"),
          cache_default,
        )
        new_options["selective_refresh"] = self._coerce_bool(
          user_input.get("selective_refresh"),
          selective_default,
        )

        typed_options = self._normalise_options_snapshot(new_options)

        return self.async_create_entry(title="", data=typed_options)

      except Exception as err:
        _LOGGER.error("Error updating performance settings: %s", err)
        return self.async_show_form(
          step_id="performance_settings",
          data_schema=self._get_performance_settings_schema(
            user_input,
          ),
          errors={"base": "performance_update_failed"},
        )

    return self.async_show_form(
      step_id="performance_settings",
      data_schema=self._get_performance_settings_schema(),
    )

  def _get_performance_settings_schema(
    self,
    user_input: dict[str, Any] | None = None,
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
        },
      )

    stored_mode_value = current_options.get("performance_mode")
    stored_mode_current = self._entry.options.get("performance_mode")
    stored_mode = normalize_performance_mode(  # noqa: F821
      stored_mode_value if isinstance(stored_mode_value, str) else None,
      current=(
        stored_mode_current
        if isinstance(
          stored_mode_current,
          str,
        )
        else None
      ),
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
          ),
        ),
        vol.Optional(
          "performance_mode",
          default=current_values.get(
            "performance_mode",
            stored_mode,
          ),
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=["minimal", "balanced", "full"],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="performance_mode",
          ),
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
          ),
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
          ),
        ),
        vol.Optional(
          "selective_refresh",
          default=current_values.get(
            "selective_refresh",
            stored_selective,
          ),
        ): selector.BooleanSelector(),
      },
    )
