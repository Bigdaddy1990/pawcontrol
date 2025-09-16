"""Helpers for the entity profile selection step in the config flow.

The Home Assistant quality scale requires strict typing and centralized
validation. The original helper bundled a dynamic method without any type
annotations, which made reuse from both the configuration flow and the
options flow difficult.  This module now provides reusable, fully typed
utilities that standardize how entity profiles are presented and validated.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import voluptuous as vol

from .entity_factory import ENTITY_PROFILES

#: Default profile used when the user has not made a choice yet.
DEFAULT_PROFILE: Final[str] = "standard"

# Mapping used by voluptuous to offer friendly names in the dropdown.
PROFILE_TITLES: Final[dict[str, str]] = {
    profile: config.get("name", profile.title())
    for profile, config in ENTITY_PROFILES.items()
}

# Schema reused by the config flow and options flow when asking for a profile.
PROFILE_SCHEMA: Final[vol.Schema] = vol.Schema(
    {vol.Required("entity_profile", default=DEFAULT_PROFILE): vol.In(PROFILE_TITLES)}
)


def validate_profile_selection(user_input: Mapping[str, Any]) -> str:
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
        raise vol.Invalid("invalid_profile") from err

    profile = profile_data["entity_profile"]

    if profile not in ENTITY_PROFILES:
        # This should never happen because of the schema, but keeping this
        # guard makes mypy and future refactors happier.
        raise vol.Invalid("invalid_profile")

    return profile


def get_profile_selector_options() -> list[dict[str, str]]:
    """Return selector options with descriptive labels for each profile."""

    options: list[dict[str, str]] = []
    for profile, config in ENTITY_PROFILES.items():
        name = config.get("name", profile.title())
        description = config.get("description", "")
        max_entities = config.get("max_entities")

        label_parts = [name]
        if isinstance(max_entities, int):
            label_parts.append(f"{max_entities} entities per dog")
        if description:
            # Use second-person tone to match the global writing guidance.
            label_parts.append(description)

        options.append({"value": profile, "label": " – ".join(label_parts)})

    return options


def build_profile_summary_text() -> str:
    """Create a human readable summary of all profiles for UI hints."""

    summaries: list[str] = []
    for profile, config in ENTITY_PROFILES.items():
        name = config.get("name", profile.title())
        description = config.get("description", "")
        recommended_for = config.get("recommended_for")

        summary_parts = [f"{name}: {description}".rstrip()]
        if isinstance(recommended_for, str) and recommended_for:
            summary_parts.append(
                f"You should pick this when you want {recommended_for.lower()}."
            )

        summaries.append(" ".join(summary_parts).strip())

    return "\n".join(summaries)
