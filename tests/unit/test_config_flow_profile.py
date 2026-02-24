"""Unit tests for profile selection helpers."""

import pytest
import voluptuous as vol

from custom_components.pawcontrol import config_flow_profile


def test_validate_profile_selection_accepts_known_profile() -> None:
    """Known profile keys should validate successfully."""
    known_profile = next(iter(config_flow_profile.PROFILE_TITLES))

    assert (
        config_flow_profile.validate_profile_selection(
            {"entity_profile": known_profile},
        )
        == known_profile
    )


def test_validate_profile_selection_rejects_unknown_profile() -> None:
    """Unknown profiles should raise a normalized voluptuous error."""
    with pytest.raises(vol.Invalid, match="invalid_profile"):
        config_flow_profile.validate_profile_selection({"entity_profile": "unknown"})


def test_validate_profile_selection_rejects_profile_missing_from_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard should reject a profile if runtime registry no longer contains it."""
    known_profile = next(iter(config_flow_profile.PROFILE_TITLES))
    patched_profiles = dict(config_flow_profile.ENTITY_PROFILES)
    patched_profiles.pop(known_profile)
    monkeypatch.setattr(config_flow_profile, "ENTITY_PROFILES", patched_profiles)

    with pytest.raises(vol.Invalid, match="invalid_profile"):
        config_flow_profile.validate_profile_selection({"entity_profile": known_profile})


def test_profile_selector_options_include_value_and_label() -> None:
    """Selector options should expose both value and UI label fields."""
    options = config_flow_profile.get_profile_selector_options()

    assert options
    assert all("value" in option and "label" in option for option in options)


def test_build_profile_summary_text_includes_all_profile_names() -> None:
    """Summary text should contain each configured profile title."""
    summary = config_flow_profile.build_profile_summary_text()

    for profile_name in config_flow_profile.PROFILE_TITLES.values():
        assert profile_name in summary
