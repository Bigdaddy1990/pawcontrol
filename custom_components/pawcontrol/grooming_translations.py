"""Translation helpers for grooming workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from .language import normalize_language

DEFAULT_LANGUAGE: Final[str] = 'en'
SUPPORTED_LANGUAGES: Final[frozenset[str]] = frozenset({'en', 'de'})

_GROOMING_LABEL_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    'button_action': {
        'en': 'Start grooming session',
        'de': 'Pflegesitzung starten',
    },
    'button_notes': {
        'en': 'Started via button',
        'de': 'Über Schaltfläche gestartet',
    },
    'button_error': {
        'en': 'Failed to start grooming: {error}',
        'de': 'Pflege konnte nicht gestartet werden: {error}',
    },
    'module_switch': {
        'en': 'Grooming Tracking',
        'de': 'Pflege-Tracking',
    },
    'module_summary_label': {
        'en': 'Grooming',
        'de': 'Pflege',
    },
    'module_summary_description': {
        'en': 'Grooming schedule and tracking',
        'de': 'Pflegeplan und Tracking',
    },
    'feature_grooming_reminders': {
        'en': 'Grooming Reminders',
        'de': 'Pflege-Erinnerungen',
    },
    'feature_grooming_schedule': {
        'en': 'Grooming Schedule',
        'de': 'Pflegeplan',
    },
    'feature_grooming_tracking': {
        'en': 'Grooming Tracking',
        'de': 'Pflege-Tracking',
    },
}

_GROOMING_TEMPLATE_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    'helper_due': {
        'en': '{dog_name} Grooming Due',
        'de': '{dog_name} Pflege fällig',
    },
    'notification_title': {
        'en': '🛁 Grooming started: {dog_label}',
        'de': '🛁 Pflege gestartet: {dog_label}',
    },
    'notification_message': {
        'en': 'Started {grooming_type} for {dog_label}',
        'de': 'Gestartet {grooming_type} für {dog_label}',
    },
    'notification_with_groomer': {
        'en': 'with {groomer}',
        'de': 'mit {groomer}',
    },
    'notification_estimated_duration': {
        'en': '(est. {minutes} min)',
        'de': '(ca. {minutes} Min.)',
    },
    'start_failure': {
        'en': 'Failed to start grooming for {dog_label}. Check the logs for details.',
        'de': 'Pflege für {dog_label} konnte nicht gestartet werden. Details im Log prüfen.',
    },
    'manual_session_notes': {
        'en': 'Grooming session on {date}',
        'de': 'Pflegesitzung am {date}',
    },
}


def translated_grooming_label(language: str | None, key: str, **values: object) -> str:
    """Return a localized grooming label."""

    translations = _GROOMING_LABEL_TRANSLATIONS.get(key)
    if translations is None:
        return key.format(**values) if values else key

    normalized = normalize_language(
        language,
        supported=SUPPORTED_LANGUAGES,
        default=DEFAULT_LANGUAGE,
    )
    template = translations.get(normalized, translations.get(DEFAULT_LANGUAGE, key))
    if values:
        return template.format(**values)
    return template


def translated_grooming_template(
    language: str | None, key: str, **values: object
) -> str:
    """Return a localized grooming template string."""

    translations = _GROOMING_TEMPLATE_TRANSLATIONS.get(key)
    if translations is None:
        return key.format(**values)

    normalized = normalize_language(
        language,
        supported=SUPPORTED_LANGUAGES,
        default=DEFAULT_LANGUAGE,
    )
    template = translations.get(normalized, translations.get(DEFAULT_LANGUAGE, key))
    return template.format(**values)


__all__ = [
    'translated_grooming_label',
    'translated_grooming_template',
]
