"""Health helper utilities for Paw Control flows."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from ..types import (
  DOG_HEALTH_PLACEHOLDERS_TEMPLATE,
  ConfigFlowPlaceholders,
  HealthOptions,
  OptionsHealthSettingsInput,
  clone_placeholders,
  freeze_placeholders,
)


def build_dog_health_placeholders(
  *,
  dog_name: str,
  dog_age: str,
  dog_weight: str,
  suggested_ideal_weight: str,
  suggested_activity: str,
  medication_enabled: str,
  bcs_info: str,
  special_diet_count: str,
  health_diet_info: str,
) -> ConfigFlowPlaceholders:
  """Return immutable placeholders for the health configuration step."""

  placeholders = clone_placeholders(DOG_HEALTH_PLACEHOLDERS_TEMPLATE)
  placeholders["dog_name"] = dog_name
  placeholders["dog_age"] = dog_age
  placeholders["dog_weight"] = dog_weight
  placeholders["suggested_ideal_weight"] = suggested_ideal_weight
  placeholders["suggested_activity"] = suggested_activity
  placeholders["medication_enabled"] = medication_enabled
  placeholders["bcs_info"] = bcs_info
  placeholders["special_diet_count"] = special_diet_count
  placeholders["health_diet_info"] = health_diet_info
  return freeze_placeholders(placeholders)


def normalise_string_sequence(value: Any) -> list[str]:
  """Return a normalised list of strings for sequence-based metadata."""

  if isinstance(value, Sequence) and not isinstance(value, str | bytes):
    normalised: list[str] = []
    for item in value:
      if item is None:
        continue
      if isinstance(item, str):
        candidate = item.strip()
        if candidate:
          normalised.append(candidate)
        continue
      normalised.append(str(item))
    return normalised
  return []


def summarise_health_summary(summary: Any) -> str:
  """Convert a health summary mapping into a user-facing string."""

  if not isinstance(summary, Mapping):
    return "No recent health summary"

  healthy = bool(summary.get("healthy", True))
  issues = normalise_string_sequence(summary.get("issues"))
  warnings = normalise_string_sequence(summary.get("warnings"))

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


def build_health_settings_payload(
  user_input: OptionsHealthSettingsInput,
  current: HealthOptions,
  *,
  coerce_bool: Callable[[Any, bool], bool],
) -> HealthOptions:
  """Create a typed health payload from the submitted form data."""

  return cast(
    HealthOptions,
    {
      "weight_tracking": coerce_bool(
        user_input.get("weight_tracking"),
        current.get("weight_tracking", True),
      ),
      "medication_reminders": coerce_bool(
        user_input.get("medication_reminders"),
        current.get("medication_reminders", True),
      ),
      "vet_reminders": coerce_bool(
        user_input.get("vet_reminders"),
        current.get("vet_reminders", True),
      ),
      "grooming_reminders": coerce_bool(
        user_input.get("grooming_reminders"),
        current.get("grooming_reminders", True),
      ),
      "health_alerts": coerce_bool(
        user_input.get("health_alerts"),
        current.get("health_alerts", True),
      ),
    },
  )
