"""Coverage tests for feeding options flow mixin."""

from collections.abc import Mapping
from typing import Any

from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_OPTIONS,
)
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.options_flow_feeding import FeedingOptionsMixin


class _FakeFeedingFlow(FeedingOptionsMixin):
    """Minimal host for exercising ``FeedingOptionsMixin`` branches."""

    def __init__(self) -> None:
        self._dogs: list[dict[str, Any]] = []
        self._current_dog: dict[str, Any] | None = None
        self._options: dict[str, Any] = {}
        self.raise_build_error: Exception | None = None

    def _current_options(self) -> dict[str, Any]:
        return self._options

    def _current_dog_options(self) -> dict[str, Any]:
        options = self._options.get(CONF_DOG_OPTIONS)
        if isinstance(options, Mapping):
            return dict(options)
        return {}

    def _clone_options(self) -> dict[str, Any]:
        return dict(self._options)

    def _normalise_options_snapshot(self, options: dict[str, Any]) -> dict[str, Any]:
        return options

    def _select_dog_by_id(self, dog_id: str | None) -> None:
        self._current_dog = next(
            (dog for dog in self._dogs if dog.get(CONF_DOG_ID) == dog_id),
            None,
        )

    def _require_current_dog(self) -> dict[str, Any] | None:
        return self._current_dog

    def _build_dog_selector_schema(self) -> object:
        return {"dog_id": "selector"}

    def _build_feeding_settings(
        self,
        user_input: dict[str, Any],
        current: dict[str, Any],
    ) -> dict[str, Any]:
        if self.raise_build_error is not None:
            raise self.raise_build_error
        return super()._build_feeding_settings(user_input, current)

    async def async_step_init(self) -> dict[str, Any]:
        return {"type": "menu", "step_id": "init"}

    async def async_step_select_dog_for_feeding_settings(self, user_input=None):
        return await super().async_step_select_dog_for_feeding_settings(user_input)

    async def async_step_feeding_settings(self, user_input=None):
        return await super().async_step_feeding_settings(user_input)

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: object,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
        }

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}


async def test_select_dog_step_handles_empty_unknown_and_valid_selection() -> None:
    """Selection step should route to init, itself, or feeding step as needed."""
    flow = _FakeFeedingFlow()

    assert await flow.async_step_select_dog_for_feeding_settings() == {
        "type": "menu",
        "step_id": "init",
    }

    flow._dogs = [
        {CONF_DOG_ID: "dog-1", CONF_DOG_NAME: "Milo"},
        {CONF_DOG_ID: "dog-2", CONF_DOG_NAME: "Nala"},
    ]
    form = await flow.async_step_select_dog_for_feeding_settings()
    assert form["type"] == "form"
    assert form["step_id"] == "select_dog_for_feeding_settings"

    unknown = await flow.async_step_select_dog_for_feeding_settings(
        {"dog_id": "missing"},
    )
    assert unknown == {"type": "menu", "step_id": "init"}

    selected = await flow.async_step_select_dog_for_feeding_settings(
        {"dog_id": "dog-2"},
    )
    assert selected["type"] == "form"
    assert selected["step_id"] == "feeding_settings"


async def test_feeding_settings_step_routes_to_selector_without_valid_dog() -> None:
    """Feeding step should bounce back when no valid current dog is available."""
    flow = _FakeFeedingFlow()
    flow._dogs = [{CONF_DOG_ID: "dog-1", CONF_DOG_NAME: "Milo"}]

    flow._current_dog = None
    redirected = await flow.async_step_feeding_settings()
    assert redirected["type"] == "form"
    assert redirected["step_id"] == "select_dog_for_feeding_settings"

    flow._current_dog = {CONF_DOG_NAME: "Missing id"}
    redirected_missing_id = await flow.async_step_feeding_settings()
    assert redirected_missing_id["type"] == "form"
    assert redirected_missing_id["step_id"] == "select_dog_for_feeding_settings"


async def test_feeding_settings_persists_per_dog_entry_for_new_dog_id() -> None:
    """Saving feeding settings should always write the selected dog's option entry."""
    flow = _FakeFeedingFlow()
    flow._dogs = [
        {CONF_DOG_ID: "dog-1", CONF_DOG_NAME: "Milo"},
        {CONF_DOG_ID: "dog-2", CONF_DOG_NAME: "Nala"},
    ]
    flow._current_dog = flow._dogs[1]
    flow._options = {
        CONF_DOG_OPTIONS: {
            "dog-1": {
                "dog_id": "dog-1",
                "feeding_settings": {"default_meals_per_day": 1},
            },
        },
    }

    result = await flow.async_step_feeding_settings(
        {
            "meals_per_day": 3,
            "feeding_reminders": False,
            "portion_tracking": True,
            "calorie_tracking": False,
            "auto_schedule": True,
        },
    )

    assert result["type"] == "create_entry"
    persisted = result["data"][CONF_DOG_OPTIONS]
    assert "dog-2" in persisted
    assert persisted["dog-2"]["feeding_settings"] == {
        "default_meals_per_day": 3,
        "feeding_reminders": False,
        "portion_tracking": True,
        "calorie_tracking": False,
        "auto_schedule": True,
    }


async def test_feeding_settings_step_maps_validation_and_generic_errors() -> None:
    """Validation and unexpected exceptions should return dedicated form errors."""
    flow = _FakeFeedingFlow()
    flow._dogs = [{CONF_DOG_ID: "dog-1", CONF_DOG_NAME: "Milo"}]
    flow._current_dog = flow._dogs[0]

    flow.raise_build_error = FlowValidationError(base_errors=["invalid_value"])
    validation = await flow.async_step_feeding_settings({"meals_per_day": 2})
    assert validation["type"] == "form"
    assert validation["errors"] == {"base": "invalid_value"}

    flow.raise_build_error = RuntimeError("boom")
    unknown = await flow.async_step_feeding_settings({"meals_per_day": 2})
    assert unknown["type"] == "form"
    assert unknown["errors"] == {"base": "update_failed"}


def test_feeding_value_coercion_and_legacy_resolution() -> None:
    """Helper methods should coerce values and resolve legacy payload fallbacks."""
    flow = _FakeFeedingFlow()

    assert flow._coerce_meals_per_day(None, 2) == 2
    assert flow._coerce_meals_per_day("4", 2) == 4
    assert flow._coerce_meals_per_day("0", 2) == 1
    assert flow._coerce_meals_per_day("12", 2) == 6
    assert flow._coerce_meals_per_day("bad", 2) == 2
    assert flow._coerce_meals_per_day(object(), 2) == 2

    flow._options = {
        CONF_DOG_OPTIONS: {"dog-1": {"feeding_settings": {"default_meals_per_day": 5}}},
        "feeding_settings": {"default_meals_per_day": 3},
    }
    assert flow._current_feeding_options("dog-1") == {"default_meals_per_day": 5}

    flow._options = {"feeding_settings": {"default_meals_per_day": 3}}
    assert flow._current_feeding_options("dog-2") == {"default_meals_per_day": 3}

    flow._options = {"feeding_settings": "legacy-string"}
    assert flow._current_feeding_options("dog-2") == {}

    built = flow._build_feeding_settings(
        {
            "meals_per_day": "9",
            "feeding_reminders": "no",
            "portion_tracking": 1,
            "calorie_tracking": 0,
            "auto_schedule": "yes",
        },
        {},
    )
    assert built == {
        "default_meals_per_day": 6,
        "feeding_reminders": False,
        "portion_tracking": True,
        "calorie_tracking": False,
        "auto_schedule": True,
    }
