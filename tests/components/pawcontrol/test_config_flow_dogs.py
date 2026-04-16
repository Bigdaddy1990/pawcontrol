"""Tests for dog-management flow helpers and branches."""

from collections.abc import Mapping
import importlib
from types import MappingProxyType, SimpleNamespace
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
import voluptuous as vol

import custom_components.pawcontrol.config_flow_dogs as cfd_mod
from custom_components.pawcontrol.config_flow_dogs import (
    DogManagementMixin,
    _build_add_another_summary_placeholders,
    _build_add_dog_placeholders,
    _build_dog_feeding_placeholders,
    _build_dog_modules_placeholders,
    _build_module_setup_placeholders,
    _coerce_bool,
    _HealthConditions,
)
from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_MEDICATION,
)
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.types import (
    DOG_AGE_FIELD,
    DOG_BREED_FIELD,
    DOG_FEEDING_CONFIG_FIELD,
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DOG_SIZE_FIELD,
)


class _DogManagementFlow(DogManagementMixin):
    """Concrete test double exposing the dog-management mixin directly."""

    def __init__(self) -> None:
        super().__init__()
        self._dogs: list[dict[str, object]] = []
        self._errors: dict[str, str] = {}
        self._validation_cache: dict[str, dict[str, object]] = {}
        self._current_dog_config: dict[str, object] | None = None
        self.hass = SimpleNamespace(config=SimpleNamespace(language="en"))

    def async_show_form(self, **kwargs: object) -> dict[str, object]:
        """Return form responses in Home Assistant-like structure."""
        payload: dict[str, object] = {"type": FlowResultType.FORM}
        payload.update(kwargs)
        return payload

    def _format_dogs_list(self) -> str:
        """Render configured dog names for placeholder output."""
        names: list[str] = []
        for dog in self._dogs:
            name = dog.get(DOG_NAME_FIELD)
            if isinstance(name, str) and name:
                names.append(name)
        return ", ".join(names) if names else "No dogs configured"

    async def _generate_smart_dog_id_suggestion(
        self,
        _user_input: dict[str, object] | None,
    ) -> str:
        """Return a deterministic ID suggestion for tests."""
        return "dog_1"

    async def _suggest_dog_breed(self, _user_input: dict[str, object] | None) -> str:
        """Return a deterministic breed suggestion for tests."""
        return "Mixed Breed"

    async def async_step_dog_gps(self) -> dict[str, object]:
        """Return a GPS step marker for branch assertions."""
        return {"type": FlowResultType.FORM, "step_id": "dog_gps"}

    async def async_step_dog_health(self) -> dict[str, object]:
        """Return a health step marker for branch assertions."""
        return {"type": FlowResultType.FORM, "step_id": "dog_health"}

    async def async_step_entity_profile(self) -> dict[str, object]:
        """Return an entity-profile step marker for branch assertions."""
        return {"type": FlowResultType.FORM, "step_id": "entity_profile"}


def _flow() -> _DogManagementFlow:
    """Create a fresh flow instance for unit-style helper tests."""
    return _DogManagementFlow()


def _base_dog_input(**overrides: object) -> dict[str, object]:
    """Build a canonical dog-input payload for validation tests."""
    payload: dict[str, object] = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_BREED: "Collie",
        CONF_DOG_AGE: 4,
        CONF_DOG_WEIGHT: 18.5,
        CONF_DOG_SIZE: "medium",
    }
    payload.update(overrides)
    return payload


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
            "has_digestive_issues": True,
            "other_health_conditions": "Skin Allergy, Joint Pain",
        },
    )
    assert "diabetes" in conditions
    assert "skin_allergy" in conditions

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

    assert conditions == [
        "diabetes",
        "allergies",
        "digestive_issues",
        "skin_allergy",
        "joint_pain",
        "skin_issue",
        "digestive",
    ]
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


def test_health_conditions_support_skin_issue_alias_lookup() -> None:
    """Alias lookup should resolve ``skin_issue`` via ``skin_allergy`` entries."""
    conditions = _HealthConditions(["skin_allergy"])
    assert "skin_issue" in conditions


def test_translation_helper_import_handles_missing_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import fallback should disable translation helper when module is absent."""
    real_import_module = importlib.import_module

    def _import_module(name: str, package: str | None = None) -> object:
        if name == cfd_mod._TRANSLATIONS_IMPORT_PATH:
            raise ModuleNotFoundError("translation helper missing")
        return real_import_module(name, package)

    with monkeypatch.context() as context:
        context.setattr(cfd_mod.importlib, "import_module", _import_module)
        reloaded = importlib.reload(cfd_mod)
        assert reloaded._ASYNC_GET_TRANSLATIONS is None

    importlib.reload(cfd_mod)


def test_translation_helper_import_handles_attribute_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import fallback should also handle loader attribute errors defensively."""
    real_import_module = importlib.import_module

    def _import_module(name: str, package: str | None = None) -> object:
        if name == cfd_mod._TRANSLATIONS_IMPORT_PATH:
            raise AttributeError("broken loader")
        return real_import_module(name, package)

    with monkeypatch.context() as context:
        context.setattr(cfd_mod.importlib, "import_module", _import_module)
        reloaded = importlib.reload(cfd_mod)
        assert reloaded._ASYNC_GET_TRANSLATIONS is None

    importlib.reload(cfd_mod)


@pytest.mark.asyncio
async def test_async_get_flow_translations_handles_missing_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing translation helper should produce an empty mapping."""
    flow = _flow()
    monkeypatch.setattr(cfd_mod, "_ASYNC_GET_TRANSLATIONS", None)
    assert await flow._async_get_flow_translations("de") == {}


@pytest.mark.asyncio
async def test_async_get_flow_translations_delegates_to_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translation helper should be called with config-flow arguments."""
    flow = _flow()
    flow.hass = SimpleNamespace(config=SimpleNamespace(language="de"))
    calls: list[tuple[str, str, set[str]]] = []

    async def _fake_get_translations(
        _hass: object,
        language: str,
        category: str,
        domains: set[str],
    ) -> dict[str, str]:
        calls.append((language, category, domains))
        return {"config.error.sample": "ok"}

    monkeypatch.setattr(cfd_mod, "_ASYNC_GET_TRANSLATIONS", _fake_get_translations)
    assert await flow._async_get_flow_translations("de") == {
        "config.error.sample": "ok"
    }
    assert calls == [("de", "config", {"pawcontrol"})]


@pytest.mark.asyncio
async def test_async_get_translation_lookup_uses_single_english_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When language is English the fallback should reuse the same dictionary."""
    flow = _flow()
    flow.hass = SimpleNamespace(config=SimpleNamespace(language="en"))
    requested: list[str] = []

    async def _fake_fetch(language: str) -> dict[str, str]:
        requested.append(language)
        return {"lang": language}

    monkeypatch.setattr(flow, "_async_get_flow_translations", _fake_fetch)
    translations, fallback = await flow._async_get_translation_lookup()

    assert requested == ["en"]
    assert translations == {"lang": "en"}
    assert fallback == {"lang": "en"}


@pytest.mark.asyncio
async def test_async_get_translation_lookup_fetches_english_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-English language should load target and English fallback translations."""
    flow = _flow()
    flow.hass = SimpleNamespace(config=SimpleNamespace(language="de"))
    requested: list[str] = []

    async def _fake_fetch(language: str) -> dict[str, str]:
        requested.append(language)
        return {"lang": language}

    monkeypatch.setattr(flow, "_async_get_flow_translations", _fake_fetch)
    translations, fallback = await flow._async_get_translation_lookup()

    assert requested == ["de", "en"]
    assert translations == {"lang": "de"}
    assert fallback == {"lang": "en"}


@pytest.mark.asyncio
async def test_async_step_add_dog_success_path_routes_to_module_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid dog setup should create config and continue to module selection."""
    flow = _flow()
    previous = {DOG_ID_FIELD: "existing", DOG_NAME_FIELD: "Existing"}
    flow._current_dog_config = previous

    async def _validate(_user_input: dict[str, object]) -> dict[str, object]:
        return {
            "valid": True,
            "errors": {},
            "validated_input": _base_dog_input(dog_id="new_dog", dog_name="New Dog"),
        }

    created_dog = {
        DOG_ID_FIELD: "new_dog",
        DOG_NAME_FIELD: "New Dog",
        DOG_MODULES_FIELD: {},
    }

    async def _create(_validated_input: dict[str, object]) -> dict[str, object]:
        return created_dog

    async def _no_sleep(_seconds: float) -> None:
        return None

    async def _next_step() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "dog_modules"}

    monkeypatch.setattr(flow, "_async_validate_dog_config", _validate)
    monkeypatch.setattr(flow, "_create_dog_config", _create)
    monkeypatch.setattr(flow, "async_step_dog_modules", _next_step)
    monkeypatch.setattr(cfd_mod.asyncio, "sleep", _no_sleep)

    result = await flow.async_step_add_dog(_base_dog_input())

    assert result["step_id"] == "dog_modules"
    assert previous in flow._dogs
    assert flow._current_dog_config == created_dog


@pytest.mark.asyncio
async def test_async_step_add_dog_shows_form_for_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed validation should return to add-dog form with field errors."""
    flow = _flow()

    async def _validate(_user_input: dict[str, object]) -> dict[str, object]:
        return {"valid": False, "errors": {CONF_DOG_ID: "duplicate"}}

    async def _suggest_id(_user_input: dict[str, object] | None) -> str:
        return "suggested_id"

    async def _suggest_breed(_user_input: dict[str, object] | None) -> str:
        return "suggested_breed"

    async def _schema(
        _user_input: dict[str, object] | None,
        _suggested_id: str,
        _suggested_breed: str,
    ) -> vol.Schema:
        return vol.Schema({})

    monkeypatch.setattr(flow, "_async_validate_dog_config", _validate)
    monkeypatch.setattr(flow, "_generate_smart_dog_id_suggestion", _suggest_id)
    monkeypatch.setattr(flow, "_suggest_dog_breed", _suggest_breed)
    monkeypatch.setattr(flow, "_create_enhanced_dog_schema", _schema)

    result = await flow.async_step_add_dog(_base_dog_input())

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"
    assert result["errors"] == {CONF_DOG_ID: "duplicate"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raised_error", "expected_error"),
    [
        (TimeoutError(), "validation_timeout"),
        (RuntimeError("boom"), "add_dog_failed"),
    ],
)
async def test_async_step_add_dog_maps_validation_exceptions_to_form_errors(
    monkeypatch: pytest.MonkeyPatch,
    raised_error: Exception,
    expected_error: str,
) -> None:
    """Timeouts and unexpected errors should map to stable base-form error keys."""
    flow = _flow()

    async def _raise(_user_input: dict[str, object]) -> dict[str, object]:
        raise raised_error

    async def _suggest_id(_user_input: dict[str, object] | None) -> str:
        return "suggested_id"

    async def _suggest_breed(_user_input: dict[str, object] | None) -> str:
        return "suggested_breed"

    async def _schema(
        _user_input: dict[str, object] | None,
        _suggested_id: str,
        _suggested_breed: str,
    ) -> vol.Schema:
        return vol.Schema({})

    monkeypatch.setattr(flow, "_async_validate_dog_config", _raise)
    monkeypatch.setattr(flow, "_generate_smart_dog_id_suggestion", _suggest_id)
    monkeypatch.setattr(flow, "_suggest_dog_breed", _suggest_breed)
    monkeypatch.setattr(flow, "_create_enhanced_dog_schema", _schema)

    result = await flow.async_step_add_dog(_base_dog_input())

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == expected_error


@pytest.mark.asyncio
async def test_async_step_add_dog_does_not_reappend_tracked_current_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing staged dog already in list should not be appended twice."""
    flow = _flow()
    existing = {DOG_ID_FIELD: "existing", DOG_NAME_FIELD: "Existing"}
    flow._dogs.append(existing)
    flow._current_dog_config = existing

    async def _validate(_user_input: dict[str, object]) -> dict[str, object]:
        return {"valid": False, "errors": {}}

    async def _schema(
        _user_input: dict[str, object] | None,
        _suggested_id: str,
        _suggested_breed: str,
    ) -> vol.Schema:
        return vol.Schema({})

    monkeypatch.setattr(flow, "_async_validate_dog_config", _validate)
    monkeypatch.setattr(flow, "_create_enhanced_dog_schema", _schema)

    await flow.async_step_add_dog(_base_dog_input())
    assert flow._dogs == [existing]


@pytest.mark.asyncio
async def test_async_step_add_dog_without_input_still_renders_form() -> None:
    """No user input should bypass validation and render the add-dog form."""
    flow = _flow()
    result = await flow.async_step_add_dog()
    assert result["step_id"] == "add_dog"


@pytest.mark.asyncio
async def test_async_step_dog_modules_without_active_dog_restarts_add_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Module input without active dog context should return to add-dog step."""
    flow = _flow()
    flow._current_dog_config = None

    async def _add_step() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "add_dog"}

    monkeypatch.setattr(flow, "async_step_add_dog", _add_step)
    result = await flow.async_step_dog_modules({"enable_feeding": True})
    assert result["step_id"] == "add_dog"


@pytest.mark.asyncio
async def test_async_step_dog_modules_routes_to_gps_for_module_toggle_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy module-key payload should be normalized and route to GPS step."""
    flow = _flow()
    flow._current_dog_config = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        DOG_MODULES_FIELD: {},
    }

    async def _gps_step() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "dog_gps"}

    monkeypatch.setattr(flow, "async_step_dog_gps", _gps_step)
    result = await flow.async_step_dog_modules({MODULE_GPS: True})

    assert result["step_id"] == "dog_gps"
    assert flow._current_dog_config is not None
    assert flow._current_dog_config[DOG_MODULES_FIELD][MODULE_GPS] is True


@pytest.mark.asyncio
async def test_async_step_dog_modules_handles_missing_toggle_mapping_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown toggle mapping entries should be ignored without raising."""
    flow = _flow()
    flow._current_dog_config = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        DOG_MODULES_FIELD: {},
    }

    async def _add_another() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "add_another_dog"}

    monkeypatch.setattr(flow, "async_step_add_another_dog", _add_another)
    monkeypatch.setattr(
        cfd_mod,
        "MODULE_TOGGLE_FLAG_BY_KEY",
        {MODULE_GPS: "enable_gps"},
    )

    result = await flow.async_step_dog_modules({MODULE_FEEDING: True})
    assert result["step_id"] == "add_another_dog"


@pytest.mark.asyncio
async def test_async_step_dog_modules_routes_to_feeding_for_flow_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flow-flag payload should route directly to feeding when enabled."""
    flow = _flow()
    flow._current_dog_config = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        DOG_MODULES_FIELD: {},
    }

    async def _feeding_step() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "dog_feeding"}

    monkeypatch.setattr(flow, "async_step_dog_feeding", _feeding_step)
    result = await flow.async_step_dog_modules({"enable_feeding": True})

    assert result["step_id"] == "dog_feeding"
    assert flow._current_dog_config is not None
    assert flow._current_dog_config[DOG_MODULES_FIELD][MODULE_FEEDING] is True


@pytest.mark.asyncio
async def test_async_step_dog_modules_routes_to_health_for_health_or_medication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health or medication module selection should branch to health step."""
    flow = _flow()
    flow._current_dog_config = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        DOG_MODULES_FIELD: {},
    }

    async def _health_step() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "dog_health"}

    monkeypatch.setattr(flow, "async_step_dog_health", _health_step)
    result = await flow.async_step_dog_modules({MODULE_MEDICATION: True})

    assert result["step_id"] == "dog_health"
    assert flow._current_dog_config is not None
    assert flow._current_dog_config[DOG_MODULES_FIELD][MODULE_MEDICATION] is True


@pytest.mark.asyncio
async def test_async_step_dog_modules_appends_dog_when_no_follow_up_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without follow-up module steps, dog config should finalize immediately."""
    flow = _flow()
    current_dog = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        DOG_MODULES_FIELD: {},
    }
    flow._current_dog_config = current_dog

    async def _add_another() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "add_another_dog"}

    monkeypatch.setattr(flow, "async_step_add_another_dog", _add_another)
    result = await flow.async_step_dog_modules({"enable_walk": False})

    assert result["step_id"] == "add_another_dog"
    assert flow._current_dog_config is None
    assert flow._dogs[-1] == current_dog


@pytest.mark.asyncio
async def test_async_step_dog_modules_form_defaults_when_values_are_invalid() -> None:
    """Form rendering should fallback to medium/age 3 for non-typed values."""
    flow = _flow()
    flow._current_dog_config = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        DOG_SIZE_FIELD: 123,  # type: ignore[typeddict-item]
        DOG_AGE_FIELD: "old",  # type: ignore[typeddict-item]
        DOG_MODULES_FIELD: {},
    }

    result = await flow.async_step_dog_modules()
    placeholders = result["description_placeholders"]
    assert result["step_id"] == "dog_modules"
    assert placeholders["dog_size"] == "medium"
    assert placeholders["dog_age"] == 3


@pytest.mark.asyncio
async def test_async_step_dog_modules_form_uses_existing_age_and_size() -> None:
    """Valid existing age/size values should be reflected in module placeholders."""
    flow = _flow()
    flow._current_dog_config = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        DOG_SIZE_FIELD: "large",
        DOG_AGE_FIELD: 8,
        DOG_MODULES_FIELD: {},
    }

    result = await flow.async_step_dog_modules()
    placeholders = result["description_placeholders"]
    assert placeholders["dog_size"] == "large"
    assert placeholders["dog_age"] == 8


@pytest.mark.asyncio
async def test_async_step_dog_modules_without_current_dog_and_no_input_returns_add_dog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No-input module step should return to add-dog when no active dog exists."""
    flow = _flow()
    flow._current_dog_config = None

    async def _add_step() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "add_dog"}

    monkeypatch.setattr(flow, "async_step_add_dog", _add_step)
    result = await flow.async_step_dog_modules()
    assert result["step_id"] == "add_dog"


@pytest.mark.asyncio
async def test_async_step_dog_feeding_without_active_dog_restarts_add_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feeding step without active dog should restart the add-dog flow."""
    flow = _flow()
    flow._current_dog_config = None

    async def _add_step() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "add_dog"}

    monkeypatch.setattr(flow, "async_step_add_dog", _add_step)
    result = await flow.async_step_dog_feeding()
    assert result["step_id"] == "add_dog"


@pytest.mark.asyncio
async def test_async_step_dog_feeding_routes_to_health_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feeding submission should continue to health when enabled in modules."""
    flow = _flow()
    flow._current_dog_config = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        CONF_DOG_WEIGHT: 12.0,
        CONF_DOG_SIZE: "medium",
        DOG_MODULES_FIELD: {MODULE_HEALTH: True},
    }

    async def _health_step() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "dog_health"}

    monkeypatch.setattr(flow, "async_step_dog_health", _health_step)
    result = await flow.async_step_dog_feeding(
        {
            "meals_per_day": 2,
            "daily_food_amount": 300,
            "food_type": "dry_food",
        },
    )

    assert result["step_id"] == "dog_health"
    assert flow._current_dog_config is not None
    assert DOG_FEEDING_CONFIG_FIELD in flow._current_dog_config


@pytest.mark.asyncio
async def test_async_step_dog_feeding_finalizes_when_no_health_or_medication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feeding submission should finalize dog when no further modules are enabled."""
    flow = _flow()
    current_dog = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        CONF_DOG_WEIGHT: 11.0,
        CONF_DOG_SIZE: "small",
        DOG_MODULES_FIELD: {},
    }
    flow._current_dog_config = current_dog

    async def _add_another() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "add_another_dog"}

    monkeypatch.setattr(flow, "async_step_add_another_dog", _add_another)
    result = await flow.async_step_dog_feeding(
        {
            "meals_per_day": 2,
            "daily_food_amount": 220,
            "food_type": "dry_food",
        },
    )

    assert result["step_id"] == "add_another_dog"
    assert flow._current_dog_config is None
    assert flow._dogs[-1] == current_dog


@pytest.mark.asyncio
async def test_async_step_dog_feeding_form_uses_existing_weight_and_size() -> None:
    """Typed weight and size should drive feeding placeholders and defaults."""
    flow = _flow()
    flow._current_dog_config = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        CONF_DOG_WEIGHT: 16.0,
        CONF_DOG_SIZE: "large",
        DOG_MODULES_FIELD: {},
    }

    result = await flow.async_step_dog_feeding()
    placeholders = result["description_placeholders"]
    assert result["step_id"] == "dog_feeding"
    assert placeholders["dog_weight"] == "16.0"


@pytest.mark.asyncio
async def test_async_step_dog_feeding_form_falls_back_for_invalid_weight_and_size() -> (
    None
):
    """Invalid weight/size should fallback to medium defaults in feeding form."""
    flow = _flow()
    flow._current_dog_config = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        CONF_DOG_WEIGHT: "heavy",  # type: ignore[dict-item]
        CONF_DOG_SIZE: 42,  # type: ignore[dict-item]
        DOG_MODULES_FIELD: {},
    }

    result = await flow.async_step_dog_feeding()
    placeholders = result["description_placeholders"]
    assert placeholders["dog_weight"] == "20.0"


@pytest.mark.asyncio
async def test_async_validate_dog_config_rejects_non_string_identifiers() -> None:
    """Identifier and name must both be strings before deeper validation."""
    flow = _flow()
    result = await flow._async_validate_dog_config(
        {
            CONF_DOG_ID: 123,  # type: ignore[dict-item]
            CONF_DOG_NAME: "Buddy",
        },
    )
    assert result == {"valid": False, "errors": {"base": "invalid_dog_data"}}


@pytest.mark.asyncio
async def test_async_validate_dog_config_uses_cached_result_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh cache entries should short-circuit expensive validation."""
    flow = _flow()
    user_input = _base_dog_input()
    cache_key = flow._create_cache_key("buddy", "Buddy", user_input)
    cached_result = {"valid": False, "errors": {"base": "cached_failure"}}
    now = cfd_mod.asyncio.get_running_loop().time()
    flow._validation_cache[cache_key] = {
        "result": cached_result,
        "cached_at": now,
    }

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(cfd_mod.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        cfd_mod,
        "validate_dog_setup_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache miss")),
    )

    result = await flow._async_validate_dog_config(user_input)
    assert result == cached_result


@pytest.mark.asyncio
async def test_async_validate_dog_config_success_caches_validated_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful validation should return normalized input and update cache."""
    flow = _flow()
    flow._dogs = [
        {DOG_ID_FIELD: "old_id", DOG_NAME_FIELD: "Old Name"},
        {DOG_ID_FIELD: 7, DOG_NAME_FIELD: "Ignored"},  # type: ignore[dict-item]
    ]
    user_input = _base_dog_input()
    validated_input = dict(user_input)

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(cfd_mod.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        cfd_mod,
        "validate_dog_setup_input",
        lambda _input, **_kwargs: validated_input,
    )

    result = await flow._async_validate_dog_config(user_input)

    assert result["valid"] is True
    assert result["errors"] == {}
    assert result["validated_input"] == validated_input
    assert flow._validation_cache


@pytest.mark.asyncio
async def test_async_validate_dog_config_maps_flow_validation_error_to_form_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured FlowValidationError values should map directly to form fields."""
    flow = _flow()
    user_input = _base_dog_input()

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(cfd_mod.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        cfd_mod,
        "validate_dog_setup_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FlowValidationError(field_errors={CONF_DOG_NAME: "duplicate_name"}),
        ),
    )

    result = await flow._async_validate_dog_config(user_input)

    assert result["valid"] is False
    assert result["errors"] == {CONF_DOG_NAME: "duplicate_name"}


@pytest.mark.asyncio
async def test_async_validate_dog_config_maps_unknown_exception_to_base_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected exceptions should become a stable generic validation error."""
    flow = _flow()
    user_input = _base_dog_input()

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(cfd_mod.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        cfd_mod,
        "validate_dog_setup_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = await flow._async_validate_dog_config(user_input)
    assert result == {"valid": False, "errors": {"base": "validation_error"}}


def test_create_cache_key_serializes_missing_fields_as_none() -> None:
    """Cache keys should include explicit ``none`` tokens for missing values."""
    flow = _flow()
    cache_key = flow._create_cache_key(
        "buddy",
        "Buddy",
        {
            CONF_DOG_ID: "buddy",
            CONF_DOG_NAME: "Buddy",
        },
    )
    assert cache_key == "buddy_Buddy_none_none_none_none"


@pytest.mark.asyncio
async def test_validation_cache_helpers_cover_miss_stale_valid_and_invalid_cases() -> (
    None
):
    """Cache helper should reject stale/invalid entries and accept fresh valid ones."""
    flow = _flow()
    now = cfd_mod.asyncio.get_running_loop().time()

    assert flow._get_cached_validation("missing") is None

    flow._validation_cache["stale"] = {
        "result": {"valid": True, "errors": {}},
        "cached_at": now - 6,
    }
    assert flow._get_cached_validation("stale") is None

    valid_result = {"valid": False, "errors": {"base": "field_error"}}
    flow._validation_cache["valid"] = {
        "result": valid_result,
        "cached_at": now,
    }
    assert flow._get_cached_validation("valid") == valid_result

    flow._validation_cache["invalid"] = {
        "result": {"valid": "yes", "errors": []},  # type: ignore[dict-item]
        "cached_at": now,
    }
    assert flow._get_cached_validation("invalid") is None

    flow._validation_cache["non_mapping"] = {
        "result": ["not", "a", "mapping"],  # type: ignore[dict-item]
        "cached_at": now,
    }
    assert flow._get_cached_validation("non_mapping") is None


@pytest.mark.asyncio
async def test_update_validation_cache_stores_result_and_timestamp() -> None:
    """Updating cache should persist the result alongside loop timestamp."""
    flow = _flow()
    result = {"valid": True, "errors": {}}
    flow._update_validation_cache("cache_key", result)
    entry = flow._validation_cache["cache_key"]
    assert entry["result"] == result
    assert isinstance(entry["cached_at"], float)


@pytest.mark.asyncio
async def test_create_dog_config_defaults_optional_fields_when_types_do_not_match() -> (
    None
):
    """Non-numeric age/weight and non-string size should be omitted from config."""
    flow = _flow()
    config = await flow._create_dog_config(
        {
            CONF_DOG_ID: "  buddy_id ",
            CONF_DOG_NAME: " Buddy ",
            CONF_DOG_BREED: "   ",
            CONF_DOG_AGE: "young",  # type: ignore[dict-item]
            CONF_DOG_WEIGHT: "heavy",  # type: ignore[dict-item]
            CONF_DOG_SIZE: 12,  # type: ignore[dict-item]
        },
    )

    assert config[DOG_ID_FIELD] == "buddy_id"
    assert config[DOG_NAME_FIELD] == "Buddy"
    assert config[DOG_BREED_FIELD] == "Mixed Breed"
    assert DOG_AGE_FIELD not in config


@pytest.mark.asyncio
async def test_create_enhanced_dog_schema_supports_mapping_and_none_inputs() -> None:
    """Enhanced schema should handle explicit mapping values and empty defaults."""
    flow = _flow()

    schema_from_mapping = await flow._create_enhanced_dog_schema(
        {CONF_DOG_ID: "custom_id", CONF_DOG_NAME: "Custom"},
        suggested_id="suggested",
        suggested_breed="Breed",
    )
    assert isinstance(schema_from_mapping, vol.Schema)

    schema_from_none = await flow._create_enhanced_dog_schema(
        None,
        suggested_id="suggested",
        suggested_breed="Breed",
    )
    assert isinstance(schema_from_none, vol.Schema)


def test_build_vaccination_records_supports_next_due_only_and_bordetella_slot() -> None:
    """Vaccination builder should include records when only next_due is provided."""
    flow = _flow()
    records = flow._build_vaccination_records(
        {
            "bordetella_next": "2026-07-01",
        },
    )

    assert "rabies" not in records
    assert "dhpp" not in records
    assert records["bordetella"] == {"next_due": "2026-07-01"}


def test_build_medication_entries_handles_missing_slot_and_optional_fields() -> None:
    """Medication builder should skip empty slots and capture optional metadata."""
    flow = _flow()
    records = flow._build_medication_entries(
        {
            "medication_1_name": "Omega",
            "medication_1_dosage": "10mg",
            "medication_1_frequency": "twice_daily",
            "medication_1_notes": "with food",
            "medication_1_with_meals": False,
            "medication_2_name": "",
        },
    )

    assert len(records) == 1
    entry = records[0]
    assert entry["dosage"] == "10mg"
    assert entry["frequency"] == "twice_daily"
    assert entry["notes"] == "with food"
    assert entry["with_meals"] is False


def test_collect_health_conditions_handles_empty_tokens_and_skin_alias_defaults() -> (
    None
):
    """Empty tokens should be ignored and skin issues should inject helper aliases."""
    flow = _flow()
    conditions = flow._collect_health_conditions(
        {
            "other_health_conditions": "skin issue, digestive, , ",
        },
    )

    assert "skin_issue" in conditions
    assert "digestive" in conditions
    assert "joint_pain" in conditions


def test_collect_health_conditions_without_other_conditions_skips_alias_processing(
) -> (
    None
):
    """No free-text conditions should keep only mapped checkbox flags."""
    flow = _flow()
    conditions = flow._collect_health_conditions({"has_diabetes": True})
    assert conditions == ["diabetes"]


def test_collect_special_diet_without_conflicts_skips_conflict_warning_log() -> None:
    """No conflicts should keep the selected diets without warning side effects."""
    flow = _flow()
    diets = flow._collect_special_diet({"organic": True})
    assert diets == ["organic"]


@pytest.mark.parametrize(
    ("diets", "expected_warning_types"),
    [
        (["weight_control", "puppy_formula"], {"weight_puppy_warning"}),
        (["raw_diet"], set()),
        (["raw_diet", "prescription"], {"raw_medical_warning"}),
        (["hypoallergenic"], set()),
    ],
)
def test_validate_diet_combinations_covers_warning_and_non_warning_branches(
    diets: list[str],
    expected_warning_types: set[str],
) -> None:
    """Diet validation should emit warning types only for matching combinations."""
    flow = _flow()
    result = flow._validate_diet_combinations(diets)
    warning_types = {warning["type"] for warning in result["warnings"]}
    assert warning_types == expected_warning_types


@pytest.mark.asyncio
async def test_get_diet_compatibility_guidance_covers_senior_branch() -> None:
    """Guidance helper should include senior translation lines for older dogs."""
    flow = _flow()

    async def _lookup() -> tuple[dict[str, str], dict[str, str]]:
        return (
            {
                "config.error.diet_guidance_seniors": "Senior guidance",
                "config.error.diet_guidance_large_breed": "Large breed guidance",
            },
            {
                "config.error.diet_guidance_multiple_prescription": "Rx guidance",
                "config.error.diet_guidance_raw_diets": "Raw guidance",
                "config.error.diet_guidance_prescription_overrides": (
                    "Override guidance"
                ),
                "config.error.diet_guidance_none": "None",
            },
        )

    flow._async_get_translation_lookup = _lookup  # type: ignore[method-assign]
    guidance = await flow._get_diet_compatibility_guidance(10, "large")
    assert guidance.split("\n")[0] == "Senior guidance"


@pytest.mark.asyncio
async def test_async_step_configure_modules_persists_input_and_routes_forward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submitting global module settings should store snapshot and continue flow."""
    flow = _flow()

    async def _entity_profile() -> dict[str, object]:
        return {"type": FlowResultType.FORM, "step_id": "entity_profile"}

    monkeypatch.setattr(flow, "async_step_entity_profile", _entity_profile)
    result = await flow.async_step_configure_modules(
        {
            "enable_notifications": False,
            "enable_dashboard": True,
            "performance_mode": "invalid_mode",
            "data_retention_days": "120",
            "auto_backup": True,
            "debug_logging": True,
        },
    )

    assert result["step_id"] == "entity_profile"
    assert flow._global_modules["enable_notifications"] is False
    assert flow._global_modules["performance_mode"] == "balanced"
    assert flow._global_modules["data_retention_days"] == 120
    assert flow._global_modules["auto_backup"] is True
    assert flow._global_modules["debug_logging"] is True


@pytest.mark.asyncio
async def test_async_step_configure_modules_form_suggests_minimal_for_simple_setup(
) -> (
    None
):
    """Single-dog setup should suggest minimal performance profile."""
    flow = _flow()
    flow._dogs = [
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            DOG_MODULES_FIELD: {},
        },
    ]

    result = await flow.async_step_configure_modules()
    placeholders = result["description_placeholders"]
    assert result["step_id"] == "configure_modules"
    assert placeholders["suggested_performance"] == "minimal"


@pytest.mark.asyncio
async def test_async_step_configure_modules_form_suggests_balanced_for_mid_complexity(
) -> (
    None
):
    """Three-dog setup should suggest balanced performance and auto-backup."""
    flow = _flow()
    flow._dogs = [
        {DOG_ID_FIELD: "dog_1", DOG_NAME_FIELD: "A", DOG_MODULES_FIELD: {}},
        {DOG_ID_FIELD: "dog_2", DOG_NAME_FIELD: "B", DOG_MODULES_FIELD: {}},
        {DOG_ID_FIELD: "dog_3", DOG_NAME_FIELD: "C", DOG_MODULES_FIELD: {}},
    ]

    result = await flow.async_step_configure_modules()
    placeholders = result["description_placeholders"]
    assert placeholders["suggested_performance"] == "balanced"


@pytest.mark.asyncio
async def test_async_step_configure_modules_form_suggests_full_for_high_complexity(
) -> (
    None
):
    """Very large setups should now elevate recommendation to full performance."""
    flow = _flow()
    flow._dogs = [
        {
            DOG_ID_FIELD: f"dog_{idx}",
            DOG_NAME_FIELD: f"Dog {idx}",
            DOG_MODULES_FIELD: {},
        }
        for idx in range(6)
    ]

    result = await flow.async_step_configure_modules()
    placeholders = result["description_placeholders"]
    assert placeholders["suggested_performance"] == "full"
