"""Additional branch coverage for config flow profile helpers."""

import pytest

import custom_components.pawcontrol.config_flow_profile as profile_helpers


def test_validate_profile_selection_requires_entity_profile_key() -> None:
    """Missing profile input should fall back to the configured default profile."""
    assert profile_helpers.validate_profile_selection({}) == "standard"


def test_coerce_str_and_title_helpers_fall_back_for_non_strings() -> None:
    """Helper functions should safely coerce non-string metadata values."""
    assert profile_helpers._coerce_str("ok") == "ok"
    assert profile_helpers._coerce_str(5, fallback="fallback") == "fallback"

    assert profile_helpers._get_profile_title("guardian", None) == "Guardian"
    assert profile_helpers._get_profile_title("guardian", {"name": 10}) == "Guardian"


def test_get_profile_selector_options_omits_optional_label_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Options should only include max-entities and description when usable."""
    monkeypatch.setattr(
        profile_helpers,
        "ENTITY_PROFILES",
        {
            "minimal": {"name": "Minimal", "max_entities": "not-an-int"},
            "with_desc": {
                "name": "Detailed",
                "max_entities": 4,
                "description": "Great for testing",
            },
        },
    )

    options = profile_helpers.get_profile_selector_options()
    assert options == [
        {"value": "minimal", "label": "Minimal"},
        {
            "value": "with_desc",
            "label": "Detailed - 4 entities per dog - Great for testing",
        },
    ]


def test_build_profile_summary_text_handles_missing_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary lines should degrade gracefully when recommendation is absent."""
    monkeypatch.setattr(
        profile_helpers,
        "ENTITY_PROFILES",
        {
            "minimal": {"name": "Minimal", "description": "No extras"},
            "advanced": {
                "name": "Advanced",
                "description": "All controls",
                "recommended_for": "power users",
            },
        },
    )

    summary = profile_helpers.build_profile_summary_text().splitlines()
    assert summary[0] == "Minimal: No extras"
    assert summary[1] == (
        "Advanced: All controls You should pick this when you want power users."
    )
