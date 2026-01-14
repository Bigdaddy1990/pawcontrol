"""Placeholder helpers for PawControl config flow.

These functions generate description placeholders for flow forms and are kept in a
dedicated module to keep the entry flow implementation smaller and easier to
maintain.
"""
from __future__ import annotations

from .types import ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE
from .types import ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE
from .types import clone_placeholders
from .types import ConfigFlowPlaceholders
from .types import DOG_MODULES_SMART_DEFAULTS_TEMPLATE
from .types import freeze_placeholders


def _build_add_dog_summary_placeholders(
    *,
    dogs_configured: int,
    max_dogs: int,
    discovery_hint: str,
) -> ConfigFlowPlaceholders:
    """Return placeholders for the main add-dog form."""

    placeholders = clone_placeholders(ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE)
    placeholders["dogs_configured"] = str(dogs_configured)
    placeholders["max_dogs"] = str(max_dogs)
    placeholders["discovery_hint"] = discovery_hint
    return freeze_placeholders(placeholders)


def _build_dog_modules_form_placeholders(
    *,
    dog_name: str,
    dogs_configured: int,
    smart_defaults: str,
) -> ConfigFlowPlaceholders:
    """Return placeholders for the module selection form."""

    placeholders = clone_placeholders(DOG_MODULES_SMART_DEFAULTS_TEMPLATE)
    placeholders["dog_name"] = dog_name
    placeholders["dogs_configured"] = str(dogs_configured)
    placeholders["smart_defaults"] = smart_defaults
    return freeze_placeholders(placeholders)


def _build_add_another_placeholders(
    *,
    dogs_configured: int,
    dogs_list: str,
    can_add_more: bool,
    max_dogs: int,
    performance_note: str,
) -> ConfigFlowPlaceholders:
    """Return placeholders used when prompting to add another dog."""

    placeholders = clone_placeholders(ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE)
    placeholders["dogs_configured"] = str(dogs_configured)
    placeholders["dogs_list"] = dogs_list
    placeholders["can_add_more"] = "yes" if can_add_more else "no"
    placeholders["max_dogs"] = str(max_dogs)
    placeholders["performance_note"] = performance_note
    return freeze_placeholders(placeholders)
