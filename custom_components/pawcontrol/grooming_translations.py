"""Translation helpers for grooming workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from homeassistant.core import HomeAssistant

from .translation_helpers import (
  get_cached_component_translation_lookup,
  resolve_component_translation,
)

GROOMING_LABEL_TRANSLATION_KEYS: Final[Mapping[str, str]] = {
  "button_action": "grooming_label_button_action",
  "button_notes": "grooming_label_button_notes",
  "button_error": "grooming_label_button_error",
  "module_switch": "grooming_label_module_switch",
  "module_summary_label": "grooming_label_module_summary_label",
  "module_summary_description": "grooming_label_module_summary_description",
  "feature_grooming_reminders": "grooming_label_feature_grooming_reminders",
  "feature_grooming_schedule": "grooming_label_feature_grooming_schedule",
  "feature_grooming_tracking": "grooming_label_feature_grooming_tracking",
}

GROOMING_TEMPLATE_TRANSLATION_KEYS: Final[Mapping[str, str]] = {
  "helper_due": "grooming_template_helper_due",
  "notification_title": "grooming_template_notification_title",
  "notification_message": "grooming_template_notification_message",
  "notification_with_groomer": "grooming_template_notification_with_groomer",
  "notification_estimated_duration": "grooming_template_notification_estimated_duration",
  "start_failure": "grooming_template_start_failure",
  "manual_session_notes": "grooming_template_manual_session_notes",
}


def translated_grooming_label(
  hass: HomeAssistant | None,
  language: str | None,
  key: str,
  **values: object,
) -> str:
  """Return a localized grooming label."""

  translation_key = GROOMING_LABEL_TRANSLATION_KEYS.get(key)
  if translation_key is None:
    return key.format(**values) if values else key

  if hass is None:
    template = translation_key
  else:
    translations, fallback = get_cached_component_translation_lookup(
      hass,
      language,
    )
    template = resolve_component_translation(
      translations,
      fallback,
      translation_key,
      default=key,
    )

  if values:
    return template.format(**values)
  return template


def translated_grooming_template(
  hass: HomeAssistant | None,
  language: str | None,
  key: str,
  **values: object,
) -> str:
  """Return a localized grooming template string."""

  translation_key = GROOMING_TEMPLATE_TRANSLATION_KEYS.get(key)
  if translation_key is None:
    return key.format(**values)

  if hass is None:
    template = translation_key
  else:
    translations, fallback = get_cached_component_translation_lookup(
      hass,
      language,
    )
    template = resolve_component_translation(
      translations,
      fallback,
      translation_key,
      default=key,
    )
  return template.format(**values)


__all__ = [
  "translated_grooming_label",
  "translated_grooming_template",
]
