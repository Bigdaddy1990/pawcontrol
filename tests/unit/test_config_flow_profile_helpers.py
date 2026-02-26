"""Tests for config flow profile helper utilities."""

from types import MappingProxyType

import pytest
import voluptuous as vol

from custom_components.pawcontrol import config_flow_profile as profile_helpers


def test_coerce_and_title_helpers_handle_non_string_values() -> None:
    """Private coercion helpers should return safe fallback strings."""
    assert profile_helpers._coerce_str("alpha") == "alpha"
    assert profile_helpers._coerce_str(42, fallback="fallback") == "fallback"

    assert (
        profile_helpers._get_profile_title("standard", {"name": "Custom"}) == "Custom"
    )
    assert profile_helpers._get_profile_title("standard", {"name": 7}) == "Standard"
    assert profile_helpers._get_profile_title("standard", None) == "Standard"


def test_validate_profile_selection_returns_submitted_profile() -> None:
    """Valid profile selections should pass schema validation."""
    first_profile = next(iter(profile_helpers.ENTITY_PROFILES))
    assert (
        profile_helpers.validate_profile_selection({"entity_profile": first_profile})
        == first_profile
    )


def test_validate_profile_selection_rejects_unknown_profile() -> None:
    """Unknown profiles should be normalized to Home Assistant style errors."""
    with pytest.raises(vol.Invalid, match="invalid_profile"):
        profile_helpers.validate_profile_selection({
            "entity_profile": "definitely_unknown"
        })


def test_validate_profile_selection_uses_runtime_membership_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defensive membership check should protect against stale schemas."""
    profile = next(iter(profile_helpers.PROFILE_TITLES))
    monkeypatch.setattr(profile_helpers, "ENTITY_PROFILES", MappingProxyType({}))

    with pytest.raises(vol.Invalid, match="invalid_profile"):
        profile_helpers.validate_profile_selection({"entity_profile": profile})


def test_get_profile_selector_options_includes_capacity_and_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selector labels should include max entity count and description text."""
    monkeypatch.setattr(
        profile_helpers,
        "ENTITY_PROFILES",
        {
            "compact": {
                "name": "Compact",
                "description": "Small footprint",
                "max_entities": 12,
            },
            "fallback": {},
        },
    )

    options = profile_helpers.get_profile_selector_options()

    assert options == [
        {
            "value": "compact",
            "label": "Compact - 12 entities per dog - Small footprint",
        },
        {"value": "fallback", "label": "Fallback"},
    ]


def test_build_profile_summary_text_adds_recommendation_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary output should include recommendation guidance when present."""
    monkeypatch.setattr(
        profile_helpers,
        "ENTITY_PROFILES",
        {
            "active": {
                "name": "Active",
                "description": "Detailed monitoring",
                "recommended_for": "Power users",
            },
            "plain": {
                "name": "Plain",
                "description": "",
            },
        },
    )

    summary = profile_helpers.build_profile_summary_text()

    assert (
        "Active: Detailed monitoring You should pick this when you want power users."
        in summary
    )
    assert "Plain:" in summary
