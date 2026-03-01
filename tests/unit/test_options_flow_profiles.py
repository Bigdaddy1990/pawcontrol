"""Coverage tests for profile options mixin helper logic."""

from custom_components.pawcontrol.options_flow_profiles import ProfileOptionsMixin


class _ProfileHost(ProfileOptionsMixin):
    """Minimal host exposing pure helper methods from the mixin."""


def test_get_performance_impact_description_uses_known_and_fallback_values() -> None:
    """Known profiles should return explicit text, unknown values use fallback."""
    host = _ProfileHost()

    assert host._get_performance_impact_description("basic") == (
        "Minimal resource usage, fastest startup"
    )
    assert host._get_performance_impact_description("custom") == "Balanced performance"


def test_get_profile_recommendation_enhanced_covers_all_priority_branches() -> None:
    """Recommendation helper should prioritise low score, medium score, then dog/entity fit."""
    host = _ProfileHost()

    assert (
        host._get_profile_recommendation_enhanced(
            total_entities=30,
            dog_count=2,
            performance_score=60.0,
        )
        == "⚠️ Consider 'basic' or 'standard' profile for better performance"
    )
    assert (
        host._get_profile_recommendation_enhanced(
            total_entities=30,
            dog_count=2,
            performance_score=80.0,
        )
        == "💡 'Standard' profile recommended for balanced performance"
    )
    assert (
        host._get_profile_recommendation_enhanced(
            total_entities=10,
            dog_count=1,
            performance_score=95.0,
        )
        == "✨ 'Advanced' profile available for full features"
    )
    assert (
        host._get_profile_recommendation_enhanced(
            total_entities=25,
            dog_count=2,
            performance_score=95.0,
        )
        == "✅ Current profile is well-suited for your configuration"
    )


def test_get_profile_warnings_flags_profile_module_mismatches() -> None:
    """Warnings should be emitted when profile choice conflicts with enabled modules."""
    host = _ProfileHost()
    dogs = [
        {
            "dog_name": "Nala",
            "gps": False,
            "health": False,
            "feeding": True,
            "walk": True,
            "garden": True,
            "notifications": True,
        },
    ]

    gps_warnings = host._get_profile_warnings("gps_focus", dogs)
    assert gps_warnings == ["🛰️ Nala: GPS focus profile but GPS module disabled"]

    health_warnings = host._get_profile_warnings("health_focus", dogs)
    assert health_warnings == [
        "🏥 Nala: Health focus profile but health module disabled",
    ]

    basic_warnings = host._get_profile_warnings("basic", dogs)
    assert basic_warnings == ["⚡ Nala: Many modules enabled for basic profile"]
