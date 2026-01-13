"""Helpers for the entity profile selection step in the config flow.

The Home Assistant quality scale requires strict typing and centralized
validation. The original helper bundled a dynamic method without any type
annotations, which made reuse from both the configuration flow and the
options flow difficult.  This module now provides reusable, fully typed
utilities that standardize how entity profiles are presented and validated.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from typing import Final

import voluptuous as vol

from .entity_factory import ENTITY_PROFILES
from .types import ProfileSelectionInput
from .types import ProfileSelectorOption

#: Default profile used when the user has not made a choice yet.
DEFAULT_PROFILE: Final[str] = 'standard'


def _coerce_str(value: object, *, fallback: str = '') -> str:
    """Return the string value or a fallback when not a string."""

    return value if isinstance(value, str) else fallback


def _get_profile_title(profile: str, config: Mapping[str, object] | None) -> str:
    """Return a safe profile title string for voluptuous selectors."""

    name = config.get('name') if config else None
    return _coerce_str(name, fallback=profile.title())


# Mapping used by voluptuous to offer friendly names in the dropdown.
PROFILE_TITLES: Final[dict[str, str]] = {
    profile: _get_profile_title(profile, config)
    for profile, config in ENTITY_PROFILES.items()
}

# Schema reused by the config flow and options flow when asking for a profile.
PROFILE_SCHEMA: Final[vol.Schema] = vol.Schema(
    {vol.Required('entity_profile', default=DEFAULT_PROFILE): vol.In(PROFILE_TITLES)}
)


def validate_profile_selection(user_input: ProfileSelectionInput) -> str:
    """Validate and return the selected profile.

    Args:
        user_input: Mapping containing the submitted form values.

    Returns:
        The validated profile key.

    Raises:
        vol.Invalid: If the provided profile is not part of the supported set.
    """

    try:
        # ``PROFILE_SCHEMA`` already restricts the value to supported profiles,
        # but we still run it here to benefit from voluptuous error reporting.
        profile_data = PROFILE_SCHEMA(dict(user_input))
    except vol.Invalid as err:  # pragma: no cover - exercised by HA UI
        raise vol.Invalid('invalid_profile') from err

    profile = cast(str, profile_data['entity_profile'])

    if profile not in ENTITY_PROFILES:
        # This should never happen because of the schema, but keeping this
        # guard makes mypy and future refactors happier.
        raise vol.Invalid('invalid_profile')

    return profile


def get_profile_selector_options() -> list[ProfileSelectorOption]:
    """Return selector options with descriptive labels for each profile."""

    options: list[ProfileSelectorOption] = []
    for profile, config in ENTITY_PROFILES.items():
        name = _get_profile_title(profile, config)
        description = _coerce_str(config.get('description'))
        max_entities = config.get('max_entities')

        label_parts = [name]
        if isinstance(max_entities, int):
            label_parts.append(f"{max_entities} entities per dog")
        if description:
            # Use second-person tone to match the global writing guidance.
            label_parts.append(description)

        option: ProfileSelectorOption = {
            'value': profile,
            'label': ' - '.join(label_parts),
        }
        options.append(option)

    return options


def build_profile_summary_text() -> str:
    """Create a human readable summary of all profiles for UI hints."""

    summaries: list[str] = []
    for profile, config in ENTITY_PROFILES.items():
        name = _get_profile_title(profile, config)
        description = _coerce_str(config.get('description'))
        recommended_for = _coerce_str(config.get('recommended_for'))

        summary_parts = [f"{name}: {description}".rstrip()]
        if recommended_for:
            summary_parts.append(
                f"You should pick this when you want {recommended_for.lower()}."
            )

        summaries.append(' '.join(summary_parts).strip())

    return '\n'.join(summaries)
