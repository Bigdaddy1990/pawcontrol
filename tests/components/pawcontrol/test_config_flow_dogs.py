"""Unit tests for dog-specific config-flow helper logic."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.config_flow_dogs import (
    DogManagementMixin,
    _build_add_another_summary_placeholders,
    _build_add_dog_placeholders,
    _build_dog_feeding_placeholders,
    _build_dog_modules_placeholders,
    _build_module_setup_placeholders,
    _coerce_bool,
)


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        (True, False, True),
        (False, True, False),
        (" yes ", False, True),
        ("OFF", True, False),
        ("disabled", True, False),
        (1, False, True),
        (0, True, False),
        (None, True, True),
        (object(), False, False),
    ],
)
def test_coerce_bool_handles_common_input_shapes(
    value: object,
    default: bool,
    expected: bool,
) -> None:
    """Boolean coercion should normalize strings, numerics, and fallback values."""
    assert _coerce_bool(value, default=default) is expected


def test_placeholder_builders_return_expected_immutable_payloads() -> None:
    """Placeholder helper builders should include all expected values."""
    add_dog = _build_add_dog_placeholders(
        dog_count=2,
        max_dogs=5,
        current_dogs="Buddy, Luna",
        remaining_spots=3,
    )
    modules = _build_dog_modules_placeholders(
        dog_name="Buddy",
        dog_size="medium",
        dog_age=4,
    )
    feeding = _build_dog_feeding_placeholders(
        dog_name="Buddy",
        dog_weight="22.5",
        suggested_amount="430",
        portion_info="2x 215g",
    )
    add_another = _build_add_another_summary_placeholders(
        dogs_list="Buddy, Luna",
        dog_count="2",
        max_dogs=5,
        remaining_spots=3,
        at_limit="false",
    )
    module_setup = _build_module_setup_placeholders(
        total_dogs="2",
        gps_dogs="1",
        health_dogs="1",
        suggested_performance="balanced",
        complexity_info="moderate",
        next_step_info="continue",
    )

    assert dict(add_dog) == {
        "dog_count": 2,
        "max_dogs": 5,
        "current_dogs": "Buddy, Luna",
        "remaining_spots": 3,
    }
    assert dict(modules) == {"dog_name": "Buddy", "dog_size": "medium", "dog_age": 4}
    assert dict(feeding) == {
        "dog_name": "Buddy",
        "dog_weight": "22.5",
        "suggested_amount": "430",
        "portion_info": "2x 215g",
    }
    assert dict(add_another) == {
        "dogs_list": "Buddy, Luna",
        "dog_count": "2",
        "max_dogs": 5,
        "remaining_spots": 3,
        "at_limit": "false",
    }
    assert dict(module_setup) == {
        "total_dogs": "2",
        "gps_dogs": "1",
        "health_dogs": "1",
        "suggested_performance": "balanced",
        "complexity_info": "moderate",
        "next_step_info": "continue",
    }


def _mixin() -> DogManagementMixin:
    """Create a lightweight mixin instance for pure helper method tests."""
    return DogManagementMixin.__new__(DogManagementMixin)


def test_build_vaccination_records_omits_empty_values() -> None:
    """Vaccination records should include only fields with concrete values."""
    mixin = _mixin()

    records = mixin._build_vaccination_records(
        {
            "rabies_vaccination": "2025-01-01",
            "rabies_next": "",
            "dhpp_vaccination": "",
            "dhpp_next": "2026-01-01",
            "bordetella_vaccination": "",
            "bordetella_next": "",
        },
    )

    assert records == {
        "rabies": {"date": "2025-01-01"},
        "dhpp": {"next_due": "2026-01-01"},
    }


def test_build_medication_entries_applies_defaults_and_bool_coercion() -> None:
    """Medication helper should normalize optional values and time defaults."""
    mixin = _mixin()

    medications = mixin._build_medication_entries(
        {
            "medication_1_name": "Pain Relief",
            "medication_1_frequency": "",
            "medication_1_with_meals": "yes",
            "medication_2_name": "Vitamin",
            "medication_2_time": "",
            "medication_2_with_meals": 0,
            "medication_2_notes": "night",
        },
    )

    assert medications == [
        {
            "name": "Pain Relief",
            "time": "08:00:00",
            "with_meals": True,
        },
        {
            "name": "Vitamin",
            "time": "20:00:00",
            "notes": "night",
            "with_meals": False,
        },
    ]


def test_collect_condition_and_diet_helpers_cover_conflicts() -> None:
    """Health helper methods should normalize conditions and detect diet issues."""
    mixin = _mixin()

    conditions = mixin._collect_health_conditions(
        {
            "has_diabetes": "true",
            "has_digestive_issues": 1,
            "other_health_conditions": " Skin Allergy,  Joint Pain ",
        },
    )
    diets = mixin._collect_special_diet(
        {
            "puppy_formula": True,
            "senior_formula": True,
            "raw_diet": True,
            "prescription": True,
            "kidney_support": True,
            "hypoallergenic": True,
            "organic": True,
        },
    )
    diet_validation = mixin._validate_diet_combinations(diets)

    assert conditions == [
        "diabetes",
        "digestive_issues",
        "skin_allergy",
        "joint_pain",
    ]
    assert set(diets) == {
        "prescription",
        "kidney_support",
        "organic",
        "hypoallergenic",
        "raw_diet",
        "puppy_formula",
        "senior_formula",
    }
    assert diet_validation["valid"] is False
    assert diet_validation["recommended_vet_consultation"] is True
    assert any(
        issue["type"] == "age_conflict" for issue in diet_validation["conflicts"]
    )
    assert {issue["type"] for issue in diet_validation["warnings"]} >= {
        "raw_medical_warning",
        "multiple_prescription_warning",
        "hypoallergenic_warning",
    }


@pytest.mark.parametrize(
    ("age", "size", "expected"),
    [
        (0, "small", "moderate"),
        (11, "medium", "low"),
        (7, "large", "moderate"),
        (4, "medium", "high"),
        (4, "unknown", "moderate"),
    ],
)
def test_suggest_activity_level_respects_age_and_size(
    age: int,
    size: str,
    expected: str,
) -> None:
    """Activity suggestion helper should prioritize age bands before size mapping."""
    mixin = _mixin()
    assert mixin._suggest_activity_level(age, size) == expected


@pytest.mark.asyncio
async def test_get_diet_compatibility_guidance_uses_translations_and_fallback() -> None:
    """Guidance helper should include all relevant bullet lines and fallback text."""
    mixin = _mixin()

    async def _lookup() -> tuple[dict[str, str], dict[str, str]]:
        return (
            {
                "config.error.diet_guidance_puppies": "Puppy guidance",
                "config.error.diet_guidance_large_breed": "Large breed guidance",
                "config.error.diet_guidance_raw_diets": "Raw guidance",
                "config.error.diet_guidance_none": "No warnings",
            },
            {
                "config.error.diet_guidance_multiple_prescription": (
                    "Prescription fallback"
                ),
                "config.error.diet_guidance_prescription_overrides": (
                    "Override fallback"
                ),
                "config.error.diet_guidance_none": "Fallback none",
            },
        )

    mixin._async_get_translation_lookup = _lookup  # type: ignore[method-assign]

    guidance = await mixin._get_diet_compatibility_guidance(1, "large")

    assert guidance.split("\n") == [
        "Puppy guidance",
        "Large breed guidance",
        "Prescription fallback",
        "Raw guidance",
        "Override fallback",
    ]


@pytest.mark.asyncio
async def test_get_diet_compatibility_guidance_returns_none_when_empty() -> None:
    """Guidance helper should return the explicit "none" translation."""
    mixin = _mixin()

    async def _lookup() -> tuple[dict[str, str], dict[str, str]]:
        return ({}, {"config.error.diet_guidance_none": "No compatibility notes"})

    mixin._async_get_translation_lookup = _lookup  # type: ignore[method-assign]

    assert (
        await mixin._get_diet_compatibility_guidance(3, "small")
        == "No compatibility notes"
    )
