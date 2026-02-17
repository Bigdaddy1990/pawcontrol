"""Placeholder helpers for PawControl config flow.

These functions generate description placeholders for flow forms and are kept in a
dedicated module to keep the entry flow implementation smaller and easier to
maintain.
"""

from .types import (
    ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE,
    ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE,
    DOG_MODULES_SMART_DEFAULTS_TEMPLATE,
    ConfigFlowPlaceholders,
    clone_placeholders,
    freeze_placeholders,
)


def _build_add_dog_summary_placeholders(
    *,
    dogs_configured: int,
    max_dogs: int,
    discovery_hint: str,
) -> ConfigFlowPlaceholders:
    """Return placeholders for the main add-dog form."""  # noqa: E111

    placeholders = clone_placeholders(ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE)  # noqa: E111
    placeholders["dogs_configured"] = str(dogs_configured)  # noqa: E111
    placeholders["max_dogs"] = str(max_dogs)  # noqa: E111
    placeholders["discovery_hint"] = discovery_hint  # noqa: E111
    return freeze_placeholders(placeholders)  # noqa: E111


def _build_dog_modules_form_placeholders(
    *,
    dog_name: str,
    dogs_configured: int,
    smart_defaults: str,
) -> ConfigFlowPlaceholders:
    """Return placeholders for the module selection form."""  # noqa: E111

    placeholders = clone_placeholders(DOG_MODULES_SMART_DEFAULTS_TEMPLATE)  # noqa: E111
    placeholders["dog_name"] = dog_name  # noqa: E111
    placeholders["dogs_configured"] = str(dogs_configured)  # noqa: E111
    placeholders["smart_defaults"] = smart_defaults  # noqa: E111
    return freeze_placeholders(placeholders)  # noqa: E111


def _build_add_another_placeholders(
    *,
    dogs_configured: int,
    dogs_list: str,
    can_add_more: bool,
    max_dogs: int,
    performance_note: str,
) -> ConfigFlowPlaceholders:
    """Return placeholders used when prompting to add another dog."""  # noqa: E111

    placeholders = clone_placeholders(ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE)  # noqa: E111
    placeholders["dogs_configured"] = str(dogs_configured)  # noqa: E111
    placeholders["dogs_list"] = dogs_list  # noqa: E111
    placeholders["can_add_more"] = "yes" if can_add_more else "no"  # noqa: E111
    placeholders["max_dogs"] = str(max_dogs)  # noqa: E111
    placeholders["performance_note"] = performance_note  # noqa: E111
    return freeze_placeholders(placeholders)  # noqa: E111
