"""Tests for profile helpers used in config and options flows."""

import pytest
import voluptuous as vol

from custom_components.pawcontrol.config_flow_profile import (
    DEFAULT_PROFILE,
    PROFILE_TITLES,
    build_profile_summary_text,
    get_profile_selector_options,
    validate_profile_selection,
)
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES


def test_validate_profile_selection_returns_default_when_missing() -> None:
    """The schema default should be used when no selection is provided."""
    assert validate_profile_selection({}) == DEFAULT_PROFILE


def test_validate_profile_selection_rejects_unknown_profile() -> None:
    """Unsupported profile values should return the shared invalid marker."""
    with pytest.raises(vol.Invalid, match="invalid_profile"):
        validate_profile_selection({"entity_profile": "not-a-profile"})


def test_get_profile_selector_options_mirrors_profile_metadata() -> None:
    """Options should expose title, limits, and descriptions for each profile."""
    options_by_value = {
        option["value"]: option for option in get_profile_selector_options()
    }

    assert set(options_by_value) == set(ENTITY_PROFILES)

    for profile, config in ENTITY_PROFILES.items():
        option = options_by_value[profile]
        label = option["label"]

        assert PROFILE_TITLES[profile] in label
        assert f"{config['max_entities']} entities per dog" in label
        assert str(config["description"]) in label


def test_build_profile_summary_text_contains_recommendations() -> None:
    """Summary text should include one line per profile with recommendation copy."""
    summary_text = build_profile_summary_text()
    summary_lines = [line for line in summary_text.splitlines() if line.strip()]

    assert len(summary_lines) == len(ENTITY_PROFILES)

    for profile, config in ENTITY_PROFILES.items():
        expected_name = PROFILE_TITLES[profile]
        expected_description = str(config["description"])
        expected_recommendation = (
            f"You should pick this when you want "
            f"{str(config['recommended_for']).lower()}."
        )

        matching_line = next(
            line for line in summary_lines if line.startswith(expected_name)
        )
        assert expected_description in matching_line
        assert expected_recommendation in matching_line
