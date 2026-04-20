"""Coverage-focused tests for health flow step mixins."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

import pytest
import voluptuous as vol

from custom_components.pawcontrol.const import MODULE_MEDICATION
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.flow_steps.health import (
    DogHealthFlowMixin,
    HealthOptionsMixin,
    HealthSummaryMixin,
)
from custom_components.pawcontrol.types import (
    DOG_AGE_FIELD,
    DOG_FEEDING_CONFIG_FIELD,
    DOG_HEALTH_CONFIG_FIELD,
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DOG_OPTIONS_FIELD,
    DOG_SIZE_FIELD,
    DOG_WEIGHT_FIELD,
    HealthOptions,
    JSONValue,
)


class _HealthSummaryHost(HealthSummaryMixin):
    """Minimal host for summary delegation tests."""


class _DogHealthHost(DogHealthFlowMixin):
    """Minimal host for exercising dog health flow branches."""

    def __init__(self) -> None:
        self._dogs: list[dict[str, Any]] = []
        self._current_dog_config: dict[str, Any] | None = {
            DOG_ID_FIELD: "buddy-id",
            DOG_NAME_FIELD: "Buddy",
            DOG_AGE_FIELD: 4,
            DOG_SIZE_FIELD: "medium",
            DOG_WEIGHT_FIELD: 24.0,
            DOG_MODULES_FIELD: {MODULE_MEDICATION: True},
            DOG_FEEDING_CONFIG_FIELD: {},
        }
        self.last_form: dict[str, Any] | None = None
        self.collected_input: Mapping[str, Any] | None = None
        self.translation_lookup: tuple[dict[str, str], dict[str, str]] = (
            {"config.step.dog_health.bcs_info": "BCS primary"},
            {"config.step.dog_health.bcs_info": "BCS fallback"},
        )
        self.diet_guidance = "Diet compatibility guidance"

    def _collect_health_conditions(self, user_input: Mapping[str, Any]) -> list[str]:
        self.collected_input = user_input
        return ["arthritis"]

    def _collect_special_diet(self, user_input: Mapping[str, Any]) -> list[str]:
        if user_input.get("special") == "yes":
            return ["joint_support"]
        return []

    def _build_vaccination_records(
        self, user_input: Mapping[str, Any]
    ) -> dict[str, dict[str, str]]:
        if user_input.get("vaccinated"):
            return {"rabies": {"vaccination": "2024-01-01"}}
        return {}

    def _build_medication_entries(
        self, user_input: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        if user_input.get("medicate"):
            return [{"name": "Med A", "with_meals": True}]
        return []

    def _suggest_activity_level(self, dog_age: int, dog_size: str) -> str:
        if dog_age >= 8 or dog_size in {"large", "giant"}:
            return "low"
        return "moderate"

    def _validate_diet_combinations(
        self, diet_options: list[str]
    ) -> dict[str, JSONValue]:
        return {
            "recommended_vet_consultation": bool(diet_options),
            "conflicts": ["conflict"] if diet_options else [],
            "warnings": ["warning"] if diet_options else [],
        }

    async def _async_get_translation_lookup(
        self,
    ) -> tuple[dict[str, str], dict[str, str]]:
        return self.translation_lookup

    async def _get_diet_compatibility_guidance(
        self, dog_age: int, dog_size: str
    ) -> str:
        return f"{self.diet_guidance} ({dog_age}/{dog_size})"

    async def async_step_add_dog(self) -> dict[str, str]:
        return {"type": "menu", "step_id": "add_dog"}

    async def async_step_add_another_dog(self) -> dict[str, str]:
        return {"type": "menu", "step_id": "add_another_dog"}

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: vol.Schema,
        errors: dict[str, str] | None = None,
        description_placeholders: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        self.last_form = {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
            "description_placeholders": description_placeholders or {},
        }
        return self.last_form


class _HealthOptionsHost(HealthOptionsMixin):
    """Minimal host for exercising health options branches."""

    def __init__(self) -> None:
        self._dogs: list[dict[str, Any]] = [
            {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}
        ]
        self._current_dog: dict[str, Any] | None = self._dogs[0]
        self._options: dict[str, JSONValue] = {
            DOG_OPTIONS_FIELD: cast(JSONValue, {"buddy": {DOG_ID_FIELD: "buddy"}})
        }
        self.last_form: dict[str, Any] | None = None
        self.last_entry: dict[str, Any] | None = None

    def _current_options(self) -> Mapping[str, JSONValue]:
        return self._options

    def _clone_options(self) -> dict[str, JSONValue]:
        return deepcopy(self._options)

    def _normalise_options_snapshot(
        self, options: Mapping[str, JSONValue]
    ) -> dict[str, JSONValue]:
        return dict(options)

    def _current_dog_options(self) -> dict[str, dict[str, Any]]:
        raw = self._options.get(DOG_OPTIONS_FIELD, {})
        return cast(dict[str, dict[str, Any]], raw if isinstance(raw, dict) else {})

    def _build_dog_selector_schema(self) -> vol.Schema:
        return vol.Schema({vol.Required("dog_id"): str})

    def _require_current_dog(self) -> dict[str, Any] | None:
        return self._current_dog

    def _select_dog_by_id(self, dog_id: str | None) -> dict[str, Any] | None:
        selected = next(
            (dog for dog in self._dogs if dog.get(DOG_ID_FIELD) == dog_id), None
        )
        self._current_dog = selected
        return selected

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "on", "1"}:
                return True
            if lowered in {"false", "no", "off", "0"}:
                return False
        return default

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: vol.Schema,
        errors: dict[str, str] | None = None,
        description_placeholders: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        self.last_form = {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
            "description_placeholders": description_placeholders or {},
        }
        return self.last_form

    def async_create_entry(
        self, *, title: str, data: Mapping[str, JSONValue]
    ) -> dict[str, Any]:
        self.last_entry = {"type": "create_entry", "title": title, "data": dict(data)}
        return self.last_entry

    async def async_step_init(self) -> dict[str, str]:
        return {"type": "menu", "step_id": "init"}


def test_health_summary_mixin_delegates_to_helper() -> None:
    """Summary helper should render canonical fallback text for non-mappings."""
    host = _HealthSummaryHost()

    assert (
        host._summarise_health_summary("invalid-summary") == "No recent health summary"
    )


@pytest.mark.asyncio
async def test_dog_health_step_redirects_when_no_current_dog() -> None:
    """Missing current dog should send the flow back to the add-dog step."""
    host = _DogHealthHost()
    host._current_dog_config = None

    result = await host.async_step_dog_health()

    assert result == {"type": "menu", "step_id": "add_dog"}


@pytest.mark.asyncio
async def test_dog_health_step_updates_health_and_feeding_config_with_medication() -> (
    None
):
    """Submitting health input should enrich dog and feeding configuration."""
    host = _DogHealthHost()
    assert host._current_dog_config is not None
    host._current_dog_config["medications"] = [{"name": "existing"}]

    result = await host.async_step_dog_health({
        "vet_name": "Dr Vet",
        "vet_phone": "123456",
        "weight_tracking": True,
        "ideal_weight": 23.5,
        "body_condition_score": 6,
        "activity_level": "high",
        "weight_goal": "lose",
        "spayed_neutered": False,
        "health_aware_portions": False,
        "last_vet_visit": "2025-01-01",
        "next_checkup": "2026-01-01",
        "special": "yes",
        "vaccinated": True,
        "medicate": True,
    })

    assert result == {"type": "menu", "step_id": "add_another_dog"}
    assert host._dogs and host._dogs[0] is host._current_dog_config

    health_config = cast(
        dict[str, Any], host._current_dog_config[DOG_HEALTH_CONFIG_FIELD]
    )
    assert health_config["vet_name"] == "Dr Vet"
    assert health_config["last_vet_visit"] == "2025-01-01"
    assert health_config["next_checkup"] == "2026-01-01"
    assert "vaccinations" in health_config
    assert health_config["medications"][0]["with_meals"] is True

    feeding_config = cast(
        dict[str, Any], host._current_dog_config[DOG_FEEDING_CONFIG_FIELD]
    )
    assert feeding_config["health_aware_portions"] is False
    assert feeding_config["age_months"] == 48
    assert feeding_config["diet_validation"]["recommended_vet_consultation"] is True
    assert feeding_config["medication_with_meals"] is True


@pytest.mark.asyncio
async def test_dog_health_step_handles_missing_optional_sections() -> None:
    """Health submission should tolerate missing feeding config and medication module."""
    host = _DogHealthHost()
    assert host._current_dog_config is not None
    host._current_dog_config[DOG_MODULES_FIELD] = {MODULE_MEDICATION: False}
    host._current_dog_config[DOG_FEEDING_CONFIG_FIELD] = "invalid"

    result = await host.async_step_dog_health({
        "vet_name": "",
        "vet_phone": "",
        "weight_tracking": False,
        "spayed_neutered": True,
    })

    assert result == {"type": "menu", "step_id": "add_another_dog"}
    health_config = cast(
        dict[str, Any], host._current_dog_config[DOG_HEALTH_CONFIG_FIELD]
    )
    assert "vaccinations" not in health_config
    assert "medications" not in health_config


@pytest.mark.asyncio
async def test_dog_health_step_with_medication_module_can_skip_medications_and_diet_warning() -> (
    None
):
    """Medication module enabled should still allow empty meds and no diet warning."""
    host = _DogHealthHost()
    assert host._current_dog_config is not None
    host._current_dog_config[DOG_MODULES_FIELD] = {MODULE_MEDICATION: True}

    result = await host.async_step_dog_health({
        "vet_name": "Dr Vet",
        "vet_phone": "555",
        "weight_tracking": True,
        "spayed_neutered": True,
        # Intentionally omit "medicate" and "special" to exercise false branches.
    })

    assert result == {"type": "menu", "step_id": "add_another_dog"}
    health_config = cast(
        dict[str, Any], host._current_dog_config[DOG_HEALTH_CONFIG_FIELD]
    )
    assert "medications" not in health_config
    feeding_config = cast(
        dict[str, Any], host._current_dog_config[DOG_FEEDING_CONFIG_FIELD]
    )
    assert feeding_config["diet_validation"]["recommended_vet_consultation"] is False


@pytest.mark.asyncio
async def test_dog_health_step_shows_form_with_defaults_and_translation_fallbacks() -> (
    None
):
    """Initial dog health form should derive placeholder defaults from dog profile."""
    host = _DogHealthHost()
    assert host._current_dog_config is not None
    host._current_dog_config[DOG_AGE_FIELD] = "invalid"
    host._current_dog_config[DOG_SIZE_FIELD] = 5
    host._current_dog_config[DOG_WEIGHT_FIELD] = "invalid"
    host._current_dog_config.pop("medications", None)
    host.translation_lookup = ({}, {"config.step.dog_health.bcs_info": "Fallback BCS"})

    result = await host.async_step_dog_health()

    assert result["type"] == "form"
    assert result["step_id"] == "dog_health"
    placeholders = cast(dict[str, str], result["description_placeholders"])
    assert placeholders["dog_name"] == "Buddy"
    assert placeholders["dog_age"] == "3"
    assert placeholders["dog_weight"] == "20.0"
    assert placeholders["suggested_ideal_weight"] == "20.0"
    assert placeholders["medication_enabled"] == "no"
    assert placeholders["bcs_info"] == "Fallback BCS"
    assert "Diet compatibility guidance" in placeholders["health_diet_info"]


@pytest.mark.asyncio
async def test_dog_health_step_shows_form_with_primary_translation_and_medication_flag() -> (
    None
):
    """Primary translations and medication marker should be used when available."""
    host = _DogHealthHost()
    assert host._current_dog_config is not None
    host._current_dog_config["medications"] = [{"name": "med"}]
    host.translation_lookup = (
        {"config.step.dog_health.bcs_info": "Primary BCS"},
        {"config.step.dog_health.bcs_info": "Fallback BCS"},
    )

    result = await host.async_step_dog_health()

    placeholders = cast(dict[str, str], result["description_placeholders"])
    assert placeholders["bcs_info"] == "Primary BCS"
    assert placeholders["medication_enabled"] == "yes"


def test_current_health_options_prefers_dog_scoped_then_legacy_then_empty() -> None:
    """Health option lookup should honor dog-specific, legacy, and empty fallbacks."""
    host = _HealthOptionsHost()
    host._options[DOG_OPTIONS_FIELD] = cast(
        JSONValue,
        {
            "buddy": {
                DOG_ID_FIELD: "buddy",
                "health_settings": {"weight_tracking": False},
            }
        },
    )
    assert host._current_health_options("buddy") == {"weight_tracking": False}

    host._options[DOG_OPTIONS_FIELD] = cast(
        JSONValue,
        {"buddy": {DOG_ID_FIELD: "buddy", "health_settings": "invalid"}},
    )
    host._options["health_settings"] = cast(JSONValue, {"vet_reminders": False})
    assert host._current_health_options("buddy") == {"vet_reminders": False}

    host._options["health_settings"] = cast(JSONValue, "invalid")
    assert host._current_health_options("buddy") == {}


@pytest.mark.asyncio
async def test_select_dog_for_health_settings_handles_all_routes() -> None:
    """Dog selection should route to init, next step, or selector form as needed."""
    host = _HealthOptionsHost()
    host._dogs = []
    assert await host.async_step_select_dog_for_health_settings() == {
        "type": "menu",
        "step_id": "init",
    }

    host = _HealthOptionsHost()
    assert await host.async_step_select_dog_for_health_settings({
        "dog_id": "missing"
    }) == {
        "type": "menu",
        "step_id": "init",
    }

    host = _HealthOptionsHost()
    selected = await host.async_step_select_dog_for_health_settings({"dog_id": "buddy"})
    assert selected["type"] == "form"
    assert selected["step_id"] == "health_settings"

    host = _HealthOptionsHost()
    form = await host.async_step_select_dog_for_health_settings()
    assert form["type"] == "form"
    assert form["step_id"] == "select_dog_for_health_settings"


@pytest.mark.asyncio
async def test_health_settings_redirect_and_form_render_paths() -> None:
    """Health settings should redirect when no dog is selected and render form otherwise."""
    host = _HealthOptionsHost()
    host._current_dog = None
    redirected = await host.async_step_health_settings()
    assert redirected["step_id"] == "select_dog_for_health_settings"

    host = _HealthOptionsHost()
    host._current_dog = {DOG_NAME_FIELD: "Buddy"}
    redirected = await host.async_step_health_settings()
    assert redirected["step_id"] == "select_dog_for_health_settings"

    host = _HealthOptionsHost()
    form = await host.async_step_health_settings()
    assert form["type"] == "form"
    assert form["step_id"] == "health_settings"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dog_options", "expect_dog_entry"),
    [
        ({"buddy": {DOG_ID_FIELD: "buddy"}}, True),
        ({}, True),
        ({"other": {DOG_ID_FIELD: "other"}}, False),
    ],
)
async def test_health_settings_submission_updates_expected_option_targets(
    dog_options: dict[str, dict[str, Any]],
    expect_dog_entry: bool,
) -> None:
    """Submission should write per-dog options only for supported container states."""
    host = _HealthOptionsHost()
    host._options[DOG_OPTIONS_FIELD] = cast(JSONValue, dog_options)

    result = await host.async_step_health_settings({
        "weight_tracking": "false",
        "medication_reminders": "yes",
        "vet_reminders": True,
        "grooming_reminders": False,
        "health_alerts": "1",
    })

    assert result["type"] == "create_entry"
    data = cast(dict[str, Any], result["data"])
    assert data["health_settings"]["weight_tracking"] is False

    persisted_dog_options = cast(dict[str, Any], data.get(DOG_OPTIONS_FIELD, {}))
    assert ("buddy" in persisted_dog_options) is expect_dog_entry


@pytest.mark.asyncio
async def test_health_settings_reports_validation_and_unexpected_errors() -> None:
    """Validation and runtime failures should map to expected form errors."""

    class _ValidationHost(_HealthOptionsHost):
        def _build_health_settings(
            self,
            user_input: Mapping[str, Any],
            current: HealthOptions,
        ) -> HealthOptions:
            raise FlowValidationError(field_errors={"health_alerts": "invalid_value"})

    class _RuntimeHost(_HealthOptionsHost):
        def _build_health_settings(
            self,
            user_input: Mapping[str, Any],
            current: HealthOptions,
        ) -> HealthOptions:
            raise RuntimeError("boom")

    validation_result = await _ValidationHost().async_step_health_settings({
        "health_alerts": True
    })
    assert validation_result["errors"] == {"health_alerts": "invalid_value"}

    runtime_result = await _RuntimeHost().async_step_health_settings({
        "health_alerts": True
    })
    assert runtime_result["errors"] == {"base": "update_failed"}


def test_health_settings_schema_and_payload_builder_delegate_correctly() -> None:
    """Schema and payload builders should return typed structures."""
    host = _HealthOptionsHost()
    schema = host._get_health_settings_schema("buddy")
    assert isinstance(schema, vol.Schema)

    payload = host._build_health_settings(
        {
            "weight_tracking": "true",
            "medication_reminders": "false",
            "vet_reminders": "yes",
            "grooming_reminders": "off",
            "health_alerts": True,
        },
        cast(HealthOptions, {}),
    )
    assert payload["weight_tracking"] is True
    assert payload["medication_reminders"] is False
    assert payload["vet_reminders"] is True
    assert payload["grooming_reminders"] is False
    assert payload["health_alerts"] is True
