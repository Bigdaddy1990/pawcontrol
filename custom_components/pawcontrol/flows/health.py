"""Health flow mixins for Paw Control."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from ..const import MODULE_MEDICATION, SPECIAL_DIET_OPTIONS
from ..exceptions import FlowValidationError
from ..flow_helpers import (
  coerce_bool,
  coerce_optional_float,
  coerce_optional_int,
  coerce_optional_str,
  coerce_str,
)
from ..types import (
  DOG_AGE_FIELD,
  DOG_FEEDING_CONFIG_FIELD,
  DOG_HEALTH_CONFIG_FIELD,
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  DOG_OPTIONS_FIELD,
  DOG_SIZE_FIELD,
  DOG_WEIGHT_FIELD,
  DogConfigData,
  DogFeedingConfig,
  DogHealthConfig,
  DogMedicationEntry,
  DogVaccinationRecord,
  DietValidationResult,
  HealthOptions,
  JSONLikeMapping,
  JSONValue,
  OptionsHealthSettingsInput,
  ensure_dog_modules_config,
  ensure_dog_options_entry,
)
from .health_helpers import (
  build_dog_health_placeholders,
  build_health_settings_payload,
  summarise_health_summary,
)
from .health_schemas import build_dog_health_schema, build_health_settings_schema

_LOGGER = logging.getLogger(__name__)


class HealthSummaryHost(Protocol):
  """Protocol describing the config flow host requirements."""


class HealthSummaryMixin(HealthSummaryHost):
  """Provide health summary formatting for reconfigure flows."""

  def _summarise_health_summary(self, summary: Any) -> str:
    """Convert a health summary mapping into a user-facing string."""

    return summarise_health_summary(summary)


if TYPE_CHECKING:

  class DogHealthFlowHost(Protocol):
    _current_dog_config: DogConfigData | None
    _dogs: list[DogConfigData]

    def _collect_health_conditions(
      self, user_input: Mapping[str, Any]
    ) -> list[str]: ...

    def _collect_special_diet(self, user_input: Mapping[str, Any]) -> list[str]: ...

    def _build_vaccination_records(
      self,
      user_input: Mapping[str, Any],
    ) -> dict[str, DogVaccinationRecord]: ...

    def _build_medication_entries(
      self,
      user_input: Mapping[str, Any],
    ) -> list[DogMedicationEntry]: ...

    def _suggest_activity_level(self, dog_age: int, dog_size: str) -> str: ...

    def _validate_diet_combinations(
      self,
      diet_options: list[str],
    ) -> DietValidationResult: ...

    async def _async_get_translation_lookup(
      self,
    ) -> tuple[dict[str, str], dict[str, str]]: ...

    async def _get_diet_compatibility_guidance(
      self,
      dog_age: int,
      dog_size: str,
    ) -> str: ...

    async def async_step_add_dog(self) -> ConfigFlowResult: ...

    async def async_step_add_another_dog(self) -> ConfigFlowResult: ...

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: vol.Schema,
      errors: dict[str, str] | None = None,
      description_placeholders: Mapping[str, str] | None = None,
    ) -> ConfigFlowResult: ...

else:  # pragma: no cover
  DogHealthFlowHost = object


class DogHealthFlowMixin(DogHealthFlowHost):
  """Handle health configuration steps in the config flow."""

  async def async_step_dog_health(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure comprehensive health settings including health-aware feeding."""

    current_dog = self._current_dog_config
    if current_dog is None:
      _LOGGER.error(
        "Health configuration step invoked without active dog; restarting add_dog",
      )
      return await self.async_step_add_dog()

    if user_input is not None:
      modules = ensure_dog_modules_config(current_dog)
      health_config: DogHealthConfig = {
        "vet_name": coerce_str(user_input.get("vet_name")),
        "vet_phone": coerce_str(user_input.get("vet_phone")),
        "weight_tracking": coerce_bool(
          user_input.get("weight_tracking"),
          default=True,
        ),
        "ideal_weight": coerce_optional_float(user_input.get("ideal_weight"))
        or coerce_optional_float(current_dog.get(DOG_WEIGHT_FIELD)),
        "body_condition_score": (
          coerce_optional_int(user_input.get("body_condition_score")) or 5
        ),
        "activity_level": coerce_str(
          user_input.get("activity_level"),
          default="moderate",
        ),
        "weight_goal": coerce_str(
          user_input.get("weight_goal"),
          default="maintain",
        ),
        "spayed_neutered": coerce_bool(
          user_input.get("spayed_neutered"),
          default=True,
        ),
        "health_conditions": self._collect_health_conditions(user_input),
        "special_diet_requirements": self._collect_special_diet(user_input),
      }

      if last_visit := coerce_optional_str(user_input.get("last_vet_visit")):
        health_config["last_vet_visit"] = last_visit
      if next_checkup := coerce_optional_str(user_input.get("next_checkup")):
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

        dog_weight_update = coerce_optional_float(
          current_dog.get(DOG_WEIGHT_FIELD),
        )
        dog_age_update = coerce_optional_int(current_dog.get(DOG_AGE_FIELD))
        dog_size_update_raw = current_dog.get(DOG_SIZE_FIELD)
        dog_size_update = (
          dog_size_update_raw if isinstance(dog_size_update_raw, str) else "medium"
        )

        diet_validation: DietValidationResult = self._validate_diet_combinations(
          health_config["special_diet_requirements"],
        )

        feeding_config_typed.update(
          {
            "health_aware_portions": user_input.get(
              "health_aware_portions",
              True,
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
          },
        )

        if diet_validation["recommended_vet_consultation"]:
          _LOGGER.info(
            "Diet validation for %s recommends veterinary consultation: %s conflicts, %s warnings",
            current_dog[DOG_NAME_FIELD],
            len(diet_validation["conflicts"]),
            len(diet_validation["warnings"]),
          )

      self._dogs.append(current_dog)
      return await self.async_step_add_another_dog()

    dog_age_raw = current_dog.get(DOG_AGE_FIELD)
    dog_age = int(dog_age_raw) if isinstance(dog_age_raw, int | float) else 3

    dog_size_raw = current_dog.get(DOG_SIZE_FIELD)
    dog_size = dog_size_raw if isinstance(dog_size_raw, str) else "medium"

    dog_weight_raw = current_dog.get(DOG_WEIGHT_FIELD)
    dog_weight = (
      float(dog_weight_raw) if isinstance(dog_weight_raw, int | float) else 20.0
    )

    suggested_ideal_weight = round(dog_weight * 1.0, 1)
    suggested_activity = self._suggest_activity_level(dog_age, dog_size)

    modules = ensure_dog_modules_config(current_dog)
    schema = build_dog_health_schema(
      dog_age=dog_age,
      dog_size=dog_size,
      suggested_ideal_weight=suggested_ideal_weight,
      suggested_activity=suggested_activity,
      modules=modules,
    )

    translations, fallback = await self._async_get_translation_lookup()
    bcs_key = "config.step.dog_health.bcs_info"
    bcs_info = translations.get(bcs_key) or fallback.get(bcs_key) or ""

    health_diet_info = await self._get_diet_compatibility_guidance(
      dog_age,
      dog_size,
    )
    medication_enabled = "yes" if current_dog.get("medications") else "no"

    return self.async_show_form(
      step_id="dog_health",
      data_schema=schema,
      description_placeholders=dict(
        cast(
          Mapping[str, str],
          build_dog_health_placeholders(
            dog_name=current_dog[DOG_NAME_FIELD],
            dog_age=str(dog_age),
            dog_weight=str(dog_weight),
            suggested_ideal_weight=str(suggested_ideal_weight),
            suggested_activity=suggested_activity,
            medication_enabled=medication_enabled,
            bcs_info=bcs_info,
            special_diet_count=str(len(SPECIAL_DIET_OPTIONS)),
            health_diet_info=health_diet_info,
          ),
        ),
      ),
    )


if TYPE_CHECKING:
  from ..options_flow_hosts import DogOptionsHost

  class HealthOptionsHost(DogOptionsHost):
    """Type-checking host for health options mixin."""

else:  # pragma: no cover
  from ..options_flow_shared import OptionsFlowSharedMixin

  class HealthOptionsHost(OptionsFlowSharedMixin):
    """Runtime host for health options mixin."""

    pass


class HealthOptionsMixin(HealthOptionsHost):
  """Handle per-dog health options."""

  def _current_health_options(self, dog_id: str) -> HealthOptions:
    """Return the stored health configuration as a typed mapping."""

    dog_options = self._current_dog_options()
    entry = dog_options.get(dog_id, {})
    raw = entry.get("health_settings")
    if isinstance(raw, Mapping):
      return cast(HealthOptions, dict(raw))

    legacy = self._current_options().get("health_settings", {})
    if isinstance(legacy, Mapping):
      return cast(HealthOptions, dict(legacy))

    return cast(HealthOptions, {})

  async def async_step_select_dog_for_health_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to configure health settings for."""

    if not self._dogs:
      return await self.async_step_init()

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")
      self._select_dog_by_id(
        selected_dog_id if isinstance(selected_dog_id, str) else None,
      )
      if self._current_dog:
        return await self.async_step_health_settings()
      return await self.async_step_init()

    return self.async_show_form(
      step_id="select_dog_for_health_settings",
      data_schema=self._build_dog_selector_schema(),
    )

  async def async_step_health_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure health monitoring settings."""

    current_dog = self._require_current_dog()
    if current_dog is None:
      return await self.async_step_select_dog_for_health_settings()

    dog_id = current_dog.get(DOG_ID_FIELD)
    if not isinstance(dog_id, str):
      return await self.async_step_select_dog_for_health_settings()

    if user_input is not None:
      try:
        current_health = self._current_health_options(dog_id)
        new_options = self._clone_options()
        dog_options = self._current_dog_options()
        entry = ensure_dog_options_entry(
          cast(JSONLikeMapping, dict(dog_options.get(dog_id, {}))),
          dog_id=dog_id,
        )
        entry["health_settings"] = self._build_health_settings(
          cast(OptionsHealthSettingsInput, user_input),
          current_health,
        )
        if dog_id in dog_options or not dog_options:
          dog_options[dog_id] = entry
          new_options[DOG_OPTIONS_FIELD] = cast(JSONValue, dog_options)
        new_options["health_settings"] = cast(JSONValue, entry["health_settings"])

        typed_options = self._normalise_options_snapshot(new_options)
        return self.async_create_entry(title="", data=typed_options)
      except FlowValidationError as err:
        return self.async_show_form(
          step_id="health_settings",
          data_schema=self._get_health_settings_schema(
            dog_id,
            user_input,
          ),
          errors=err.as_form_errors(),
        )
      except Exception:
        return self.async_show_form(
          step_id="health_settings",
          data_schema=self._get_health_settings_schema(
            dog_id,
            user_input,
          ),
          errors={"base": "update_failed"},
        )

    return self.async_show_form(
      step_id="health_settings",
      data_schema=self._get_health_settings_schema(dog_id),
    )

  def _get_health_settings_schema(
    self,
    dog_id: str,
    user_input: dict[str, Any] | None = None,
  ) -> vol.Schema:
    """Get health settings schema."""

    current_health = self._current_health_options(dog_id)
    return build_health_settings_schema(
      current_health,
      cast(dict[str, object], user_input) if user_input is not None else None,
    )

  def _build_health_settings(
    self,
    user_input: OptionsHealthSettingsInput,
    current: HealthOptions,
  ) -> HealthOptions:
    """Create a typed health payload from the submitted form data."""

    return build_health_settings_payload(
      user_input,
      current,
      coerce_bool=self._coerce_bool,
    )
