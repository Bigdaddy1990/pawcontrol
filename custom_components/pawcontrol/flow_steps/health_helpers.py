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
  """Return immutable placeholders for the health configuration step."""  # noqa: E111

  placeholders = clone_placeholders(DOG_HEALTH_PLACEHOLDERS_TEMPLATE)  # noqa: E111
  placeholders["dog_name"] = dog_name  # noqa: E111
  placeholders["dog_age"] = dog_age  # noqa: E111
  placeholders["dog_weight"] = dog_weight  # noqa: E111
  placeholders["suggested_ideal_weight"] = suggested_ideal_weight  # noqa: E111
  placeholders["suggested_activity"] = suggested_activity  # noqa: E111
  placeholders["medication_enabled"] = medication_enabled  # noqa: E111
  placeholders["bcs_info"] = bcs_info  # noqa: E111
  placeholders["special_diet_count"] = special_diet_count  # noqa: E111
  placeholders["health_diet_info"] = health_diet_info  # noqa: E111
  return freeze_placeholders(placeholders)  # noqa: E111


def normalise_string_sequence(value: Any) -> list[str]:
  """Return a normalised list of strings for sequence-based metadata."""  # noqa: E111

  if isinstance(value, Sequence) and not isinstance(value, str | bytes):  # noqa: E111
    normalised: list[str] = []
    for item in value:
      if item is None:  # noqa: E111
        continue
      if isinstance(item, str):  # noqa: E111
        candidate = item.strip()
        if candidate:
          normalised.append(candidate)  # noqa: E111
        continue
      normalised.append(str(item))  # noqa: E111
    return normalised
  return []  # noqa: E111


def summarise_health_summary(summary: Any) -> str:
  """Convert a health summary mapping into a user-facing string."""  # noqa: E111

  if not isinstance(summary, Mapping):  # noqa: E111
    return "No recent health summary"

  healthy = bool(summary.get("healthy", True))  # noqa: E111
  issues = normalise_string_sequence(summary.get("issues"))  # noqa: E111
  warnings = normalise_string_sequence(summary.get("warnings"))  # noqa: E111

  if healthy and not issues and not warnings:  # noqa: E111
    return "Healthy"

  segments: list[str] = []  # noqa: E111
  if not healthy:  # noqa: E111
    segments.append("Issues detected")
  if issues:  # noqa: E111
    segments.append(f"Issues: {', '.join(issues)}")
  if warnings:  # noqa: E111
    segments.append(f"Warnings: {', '.join(warnings)}")

  return " | ".join(segments)  # noqa: E111


def build_health_settings_payload(
  user_input: OptionsHealthSettingsInput,
  current: HealthOptions,
  *,
  coerce_bool: Callable[[Any, bool], bool],
) -> HealthOptions:
  """Create a typed health payload from the submitted form data."""  # noqa: E111

  return cast(  # noqa: E111
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
