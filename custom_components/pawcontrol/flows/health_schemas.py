"""Health schema builders for Paw Control flows."""

from __future__ import annotations

import voluptuous as vol

from ..const import (
  MAX_DOG_WEIGHT,
  MIN_DOG_WEIGHT,
  MODULE_MEDICATION,
  SPECIAL_DIET_OPTIONS,
)
from ..selector_shim import selector
from ..types import DogModulesConfig, HealthOptions


def build_dog_health_schema(
  *,
  dog_age: int,
  dog_size: str,
  suggested_ideal_weight: float,
  suggested_activity: str,
  modules: DogModulesConfig,
) -> vol.Schema:
  """Build schema for dog health configuration."""

  schema_dict: dict[vol.Marker, object] = {
    vol.Optional("vet_name", default=""): selector.TextSelector(),
    vol.Optional("vet_phone", default=""): selector.TextSelector(
      selector.TextSelectorConfig(
        type=selector.TextSelectorType.TEL,
      ),
    ),
    vol.Optional("last_vet_visit"): selector.DateSelector(),
    vol.Optional("next_checkup"): selector.DateSelector(),
    vol.Optional("weight_tracking", default=True): selector.BooleanSelector(),
    vol.Optional(
      "health_aware_portions",
      default=True,
    ): selector.BooleanSelector(),
    vol.Optional(
      "ideal_weight",
      default=suggested_ideal_weight,
    ): selector.NumberSelector(
      selector.NumberSelectorConfig(
        min=MIN_DOG_WEIGHT,
        max=MAX_DOG_WEIGHT,
        step=0.1,
        mode=selector.NumberSelectorMode.BOX,
        unit_of_measurement="kg",
      ),
    ),
    vol.Optional("body_condition_score", default=5): selector.NumberSelector(
      selector.NumberSelectorConfig(
        min=1,
        max=9,
        step=1,
        mode=selector.NumberSelectorMode.BOX,
      ),
    ),
    vol.Optional(
      "activity_level",
      default=suggested_activity,
    ): selector.SelectSelector(
      selector.SelectSelectorConfig(
        options=[
          "very_low",
          "low",
          "moderate",
          "high",
          "very_high",
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key="activity_level",
      ),
    ),
    vol.Optional("weight_goal", default="maintain"): selector.SelectSelector(
      selector.SelectSelectorConfig(
        options=["lose", "maintain", "gain"],
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key="weight_goal",
      ),
    ),
    vol.Optional("spayed_neutered", default=True): selector.BooleanSelector(),
    vol.Optional("has_diabetes", default=False): selector.BooleanSelector(),
    vol.Optional(
      "has_kidney_disease",
      default=False,
    ): selector.BooleanSelector(),
    vol.Optional(
      "has_heart_disease",
      default=False,
    ): selector.BooleanSelector(),
    vol.Optional("has_arthritis", default=False): selector.BooleanSelector(),
    vol.Optional("has_allergies", default=False): selector.BooleanSelector(),
    vol.Optional(
      "has_digestive_issues",
      default=False,
    ): selector.BooleanSelector(),
    vol.Optional(
      "other_health_conditions",
      default="",
    ): selector.TextSelector(),
  }

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
      schema_dict[vol.Optional(diet, default=False)] = selector.BooleanSelector()

  age_diets = ["senior_formula", "puppy_formula"]
  for diet in age_diets:
    if diet in SPECIAL_DIET_OPTIONS:
      default_value = (diet == "senior_formula" and dog_age >= 7) or (
        diet == "puppy_formula" and dog_age < 2
      )
      schema_dict[vol.Optional(diet, default=default_value)] = (
        selector.BooleanSelector()
      )

  allergy_diets = ["grain_free", "hypoallergenic"]
  for diet in allergy_diets:
    if diet in SPECIAL_DIET_OPTIONS:
      schema_dict[vol.Optional(diet, default=False)] = selector.BooleanSelector()

  lifestyle_diets = ["organic", "raw_diet", "dental_care", "joint_support"]
  for diet in lifestyle_diets:
    if diet in SPECIAL_DIET_OPTIONS:
      default_value = False
      if diet == "joint_support" and (dog_age >= 7 or dog_size in ("large", "giant")):
        default_value = True
      schema_dict[vol.Optional(diet, default=default_value)] = (
        selector.BooleanSelector()
      )

  schema_dict.update(
    {
      vol.Optional("rabies_vaccination"): selector.DateSelector(),
      vol.Optional("rabies_next"): selector.DateSelector(),
      vol.Optional("dhpp_vaccination"): selector.DateSelector(),
      vol.Optional("dhpp_next"): selector.DateSelector(),
      vol.Optional("bordetella_vaccination"): selector.DateSelector(),
      vol.Optional("bordetella_next"): selector.DateSelector(),
    },
  )

  if modules.get(MODULE_MEDICATION, False):
    schema_dict.update(
      {
        vol.Optional("medication_1_name"): selector.TextSelector(),
        vol.Optional("medication_1_dosage"): selector.TextSelector(),
        vol.Optional(
          "medication_1_frequency",
          default="daily",
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=["daily", "twice_daily", "weekly", "as_needed"],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="medication_frequency",
          ),
        ),
        vol.Optional(
          "medication_1_time",
          default="08:00:00",
        ): selector.TimeSelector(),
        vol.Optional(
          "medication_1_with_meals",
          default=False,
        ): selector.BooleanSelector(),
        vol.Optional("medication_1_notes"): selector.TextSelector(),
        vol.Optional("medication_2_name"): selector.TextSelector(),
        vol.Optional("medication_2_dosage"): selector.TextSelector(),
        vol.Optional(
          "medication_2_frequency",
          default="daily",
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=["daily", "twice_daily", "weekly", "as_needed"],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="medication_frequency",
          ),
        ),
        vol.Optional(
          "medication_2_time",
          default="20:00:00",
        ): selector.TimeSelector(),
        vol.Optional(
          "medication_2_with_meals",
          default=False,
        ): selector.BooleanSelector(),
        vol.Optional("medication_2_notes"): selector.TextSelector(),
      },
    )

  return vol.Schema(schema_dict)


def build_health_settings_schema(
  current_health: HealthOptions,
  user_input: dict[str, object] | None = None,
) -> vol.Schema:
  """Get health settings schema."""

  current_values = user_input or {}

  return vol.Schema(
    {
      vol.Optional(
        "weight_tracking",
        default=current_values.get(
          "weight_tracking",
          current_health.get("weight_tracking", True),
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
          "vet_reminders",
          current_health.get("vet_reminders", True),
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
          "health_alerts",
          current_health.get("health_alerts", True),
        ),
      ): selector.BooleanSelector(),
    },
  )
