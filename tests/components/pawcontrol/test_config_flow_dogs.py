"""Tests for dog-management flow helpers and branches."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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
from custom_components.pawcontrol.config_flow_main import PawControlConfigFlow
from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
)
from custom_components.pawcontrol.types import (
    DOG_AGE_FIELD,
    DOG_BREED_FIELD,
    DOG_ID_FIELD,
)


def _flow() -> PawControlConfigFlow:
    """Create a fresh flow instance for unit-style helper tests."""
    flow = PawControlConfigFlow()
    flow._dogs = []
    return flow


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        (True, False, True),
        ("YES", False, True),
        ("off", True, False),
        (1, False, True),
        (0, True, False),
        (object(), True, True),
    ],
)
def test_coerce_bool(value: Any, default: bool, expected: bool) -> None:
    """Boolean coercion should normalize common truthy/falsy values."""
    assert _coerce_bool(value, default=default) is expected


@pytest.mark.parametrize(
    "builder_kwargs",
    [
        (
            _build_add_dog_placeholders,
            {
                "dog_count": 1,
                "max_dogs": 3,
                "current_dogs": "Buddy",
                "remaining_spots": 2,
            },
        ),
        (
            _build_dog_modules_placeholders,
            {"dog_name": "Buddy", "dog_size": "medium", "dog_age": 3},
        ),
        (
            _build_dog_feeding_placeholders,
            {
                "dog_name": "Buddy",
                "dog_weight": "20.0",
                "suggested_amount": "500",
                "portion_info": "2 meals",
            },
        ),
        (
            _build_add_another_summary_placeholders,
            {
                "dogs_list": "Buddy",
                "dog_count": "1",
                "max_dogs": 10,
                "remaining_spots": 9,
                "at_limit": "false",
            },
        ),
        (
            _build_module_setup_placeholders,
            {
                "total_dogs": "2",
                "gps_dogs": "1",
                "health_dogs": "1",
                "suggested_performance": "balanced",
                "complexity_info": "Standard",
                "next_step_info": "Next",
            },
        ),
    ],
)
def test_placeholder_builders_return_immutable_mappings(
    builder_kwargs: tuple[Any, dict[str, Any]],
) -> None:
    """Placeholder builders should return frozen mappings with expected keys."""
    builder, kwargs = builder_kwargs

    placeholders = builder(**kwargs)

    assert isinstance(placeholders, MappingProxyType)
    assert isinstance(placeholders, Mapping)
    assert all(key in placeholders for key in kwargs)

    with pytest.raises(TypeError):
        placeholders["new"] = "value"  # type: ignore[index]


@pytest.mark.parametrize(
    ("weight", "size", "expected"),
    [
        (20.0, "medium", 500),
        (2.0, "toy", 60),
        (30.0, "giant", 640),
        (7.0, "unknown", 180),
    ],
)
def test_calculate_suggested_food_amount(
    weight: float, size: str, expected: int
) -> None:
    """Suggested feeding amount should apply size multiplier and rounding."""
    assert _flow()._calculate_suggested_food_amount(weight, size) == expected


@pytest.mark.asyncio
async def test_create_dog_config_sets_defaults_and_optional_fields() -> None:
    """Dog config creation should normalize identifiers and defaults."""
    flow = _flow()

    created = await flow._create_dog_config(
        {
            CONF_DOG_ID: "Buddy One",
            CONF_DOG_NAME: "Buddy",
            CONF_DOG_BREED: "  Collie ",
            CONF_DOG_AGE: 4,
            CONF_DOG_WEIGHT: 18.5,
            CONF_DOG_SIZE: "medium",
        },
    )

    assert created[DOG_ID_FIELD] == "Buddy One"
    assert created[DOG_BREED_FIELD] == "Collie"
    assert created[DOG_AGE_FIELD] == 4


@pytest.mark.asyncio
async def test_get_diet_compatibility_guidance_uses_translations() -> None:
    """Guidance helper should combine translated snippets by dog profile."""
    flow = _flow()

    async def _lookup() -> tuple[dict[str, str], dict[str, str]]:
        keys = {
            "config.error.diet_guidance_puppies": "Puppy",
            "config.error.diet_guidance_toy_breed": "Toy",
            "config.error.diet_guidance_multiple_prescription": "Multi",
            "config.error.diet_guidance_raw_diets": "Raw",
            "config.error.diet_guidance_prescription_overrides": "Rx",
            "config.error.diet_guidance_none": "None",
        }
        return keys, keys

    flow._async_get_translation_lookup = _lookup  # type: ignore[method-assign]

    result = await flow._get_diet_compatibility_guidance(1, "toy")

    assert result == "Puppy\nToy\nMulti\nRaw\nRx"


@pytest.mark.asyncio
async def test_get_diet_compatibility_guidance_falls_back_to_none() -> None:
    """When no snippets are available, the generic guidance should be returned."""
    flow = _flow()

    async def _lookup() -> tuple[dict[str, str], dict[str, str]]:
        return {}, {"config.error.diet_guidance_none": "Fallback"}

    flow._async_get_translation_lookup = _lookup  # type: ignore[method-assign]

    assert await flow._get_diet_compatibility_guidance(4, "small") == "Fallback"


def test_health_input_helpers_cover_vaccines_medications_and_diets() -> None:
    """Health helper methods should extract structured records from flow input."""
    flow = _flow()

    vaccinations = flow._build_vaccination_records(
        {
            "rabies_vaccination": "2024-01-01",
            "rabies_next": "2025-01-01",
            "dhpp_vaccination": "2024-02-02",
        },
    )
    assert vaccinations["rabies"]["date"] == "2024-01-01"
    assert vaccinations["dhpp"]["date"] == "2024-02-02"

    medications = flow._build_medication_entries(
        {
            "medication_1_name": "Omega",
            "medication_1_with_meals": "yes",
            "medication_2_name": "Joint",
            "medication_2_time": "",
        },
    )
    assert medications[0]["with_meals"] is True
    assert medications[1]["time"] == "20:00:00"

    conditions = flow._collect_health_conditions(
        {
            "has_diabetes": True,
            "has_allergies": "true",
            "other_health_conditions": "Skin Issue, Digestive",
        },
    )
    assert "diabetes" in conditions
    assert "skin_issue" in conditions

    diets = flow._collect_special_diet(
        {
            "puppy_formula": True,
            "senior_formula": True,
            "raw_diet": True,
            "prescription": True,
            "kidney_support": True,
            "diabetic": True,
            "hypoallergenic": True,
            "organic": True,
        },
    )
    diet_validation = flow._validate_diet_combinations(diets)

    assert conditions == ["diabetes", "allergies", "skin_issue", "digestive"]
    assert set(diets) == {
        "prescription",
        "kidney_support",
        "organic",
        "hypoallergenic",
        "raw_diet",
        "diabetic",
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
    assert "puppy_formula" in diets

    validation = flow._validate_diet_combinations(diets)
    assert validation["valid"] is False
    assert validation["recommended_vet_consultation"] is True
    assert validation["conflicts"]
    assert validation["warnings"]


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
    mixin = _flow()
    assert mixin._suggest_activity_level(age, size) == expected


@pytest.mark.asyncio
async def test_get_diet_compatibility_guidance_uses_translations_and_fallback() -> None:
    """Guidance helper should include all relevant bullet lines and fallback text."""
    mixin = _flow()

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
    mixin = _flow()

    async def _lookup() -> tuple[dict[str, str], dict[str, str]]:
        return ({}, {"config.error.diet_guidance_none": "No compatibility notes"})

    mixin._async_get_translation_lookup = _lookup  # type: ignore[method-assign]

    assert (
        await mixin._get_diet_compatibility_guidance(3, "small")
        == "No compatibility notes"
    )


def test_setup_complexity_info_branches() -> None:
    """Complexity helper should classify simple, standard, and complex setups."""
    flow = _flow()
    flow._dogs = [{"modules": {"a": True}}]
    assert flow._get_setup_complexity_info().startswith("Simple")

    flow._dogs = [
        {"modules": {"a": True, "b": True}},
        {"modules": {"c": True}},
    ]
    assert flow._get_setup_complexity_info().startswith("Standard")

    flow._dogs = [{"modules": {f"m{i}": True for i in range(11)}}]
    assert flow._get_setup_complexity_info().startswith("Complex")


@pytest.mark.asyncio
async def test_add_another_dog_step_handles_yes_no_and_form(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Add-another step should branch to add-dog, configure-modules, or form."""
    flow = _flow()
    flow.hass = hass

    async def _return_add() -> dict[str, Any]:
        return {"type": FlowResultType.FORM, "step_id": "add_dog"}

    async def _return_modules() -> dict[str, Any]:
        return {"type": FlowResultType.FORM, "step_id": "configure_modules"}

    monkeypatch.setattr(flow, "async_step_add_dog", _return_add)
    monkeypatch.setattr(flow, "async_step_configure_modules", _return_modules)

    flow._validation_cache["key"] = {"valid": True}
    flow._errors["field"] = "invalid"
    flow._current_dog_config = {"dog_id": "temp", "dog_name": "Temp"}

    yes_result = await flow.async_step_add_another_dog({"add_another": True})
    assert yes_result["step_id"] == "add_dog"
    assert flow._validation_cache == {}
    assert flow._errors == {}
    assert flow._current_dog_config is None

    no_result = await flow.async_step_add_another_dog({"add_another": False})
    assert no_result["step_id"] == "configure_modules"

    flow._dogs = [{DOG_ID_FIELD: "buddy", "dog_name": "Buddy"}]
    form_result = await flow.async_step_add_another_dog()
    assert form_result["type"] == FlowResultType.FORM
    assert form_result["step_id"] == "add_another_dog"


def test_dog_management_runtime_shim_initializes_via_super() -> None:
    """Runtime shim should preserve cooperative initialisation semantics."""

    class Probe(DogManagementMixin):
        def __init__(self) -> None:
            super().__init__()

    probe = Probe()
    assert isinstance(probe._global_modules, dict)
