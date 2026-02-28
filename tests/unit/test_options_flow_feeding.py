"""Tests for feeding options flow mixin helpers."""

from copy import deepcopy

from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.options_flow_feeding import FeedingOptionsMixin
from custom_components.pawcontrol.types import DOG_OPTIONS_FIELD


class _FeedingFlow(FeedingOptionsMixin):
    """Minimal host implementation for feeding options mixin tests."""

    def __init__(
        self,
        *,
        dogs: list[dict[str, object]] | None = None,
        current_dog: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
    ) -> None:
        self._dogs = dogs or []
        self._current_dog = current_dog
        self._options = options or {}

    def _current_options(self) -> dict[str, object]:
        return self._options

    def _current_dog_options(self) -> dict[str, dict[str, object]]:
        raw = self._options.get(DOG_OPTIONS_FIELD)
        if isinstance(raw, dict):
            return raw  # type: ignore[return-value]
        return {}

    def _clone_options(self) -> dict[str, object]:
        return deepcopy(self._options)

    def _normalise_options_snapshot(
        self, options: dict[str, object]
    ) -> dict[str, object]:
        return options

    def _select_dog_by_id(self, dog_id: str | None) -> None:
        self._current_dog = next(
            (
                dog
                for dog in self._dogs
                if dog_id is not None and dog.get("dog_id") == dog_id
            ),
            None,
        )

    def _require_current_dog(self) -> dict[str, object] | None:
        return self._current_dog

    def _build_dog_selector_schema(self):
        return {}

    async def async_step_init(self):
        return {"type": FlowResultType.MENU, "step_id": "init"}

    def async_show_form(self, *, step_id: str, data_schema, errors=None):
        return {
            "type": FlowResultType.FORM,
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
        }

    def async_create_entry(self, *, title: str, data: dict[str, object]):
        return {
            "type": FlowResultType.CREATE_ENTRY,
            "title": title,
            "data": data,
        }


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        (None, 2, 2),
        ("bad", 2, 2),
        (object(), 2, 2),
        ("0", 2, 1),
        (9, 2, 6),
    ],
)
def test_coerce_meals_per_day_handles_invalid_and_clamps(
    value: object,
    default: int,
    expected: int,
) -> None:
    """Meal coercion should apply defaults and clamp to the supported range."""
    assert _FeedingFlow._coerce_meals_per_day(value, default) == expected


def test_current_feeding_options_prefers_dog_specific_and_falls_back() -> None:
    """Feeding options should prefer per-dog config with legacy fallback support."""
    flow = _FeedingFlow(
        options={
            DOG_OPTIONS_FIELD: {
                "dog-1": {
                    "feeding_settings": {
                        "default_meals_per_day": 3,
                        "portion_tracking": False,
                    }
                },
                "dog-2": {"feeding_settings": "invalid"},
            },
            "feeding_settings": {
                "default_meals_per_day": 4,
                "feeding_reminders": False,
            },
        }
    )

    assert flow._current_feeding_options("dog-1") == {
        "default_meals_per_day": 3,
        "portion_tracking": False,
    }
    assert flow._current_feeding_options("dog-2") == {
        "default_meals_per_day": 4,
        "feeding_reminders": False,
    }
    assert flow._current_feeding_options("missing") == {
        "default_meals_per_day": 4,
        "feeding_reminders": False,
    }


async def test_select_dog_for_feeding_settings_handles_navigation() -> None:
    """Dog selection should route to init for unknown dogs and to settings otherwise."""
    flow = _FeedingFlow(dogs=[])
    empty_result = await flow.async_step_select_dog_for_feeding_settings()
    assert empty_result["step_id"] == "init"

    flow = _FeedingFlow(dogs=[{"dog_id": "dog-1"}, {"dog_id": "dog-2"}])
    form_result = await flow.async_step_select_dog_for_feeding_settings()
    assert form_result["type"] == FlowResultType.FORM
    assert form_result["step_id"] == "select_dog_for_feeding_settings"

    missing_result = await flow.async_step_select_dog_for_feeding_settings({
        "dog_id": "unknown"
    })
    assert missing_result["step_id"] == "init"

    selected_result = await flow.async_step_select_dog_for_feeding_settings({
        "dog_id": "dog-2"
    })
    assert selected_result["type"] == FlowResultType.FORM
    assert selected_result["step_id"] == "feeding_settings"


async def test_async_step_feeding_settings_persists_updates() -> None:
    """Submitting feeding settings should write per-dog and legacy keys."""
    flow = _FeedingFlow(
        dogs=[{"dog_id": "dog-1"}],
        current_dog={"dog_id": "dog-1"},
        options={
            DOG_OPTIONS_FIELD: {
                "dog-1": {"feeding_settings": {"default_meals_per_day": 2}},
            }
        },
    )

    result = await flow.async_step_feeding_settings({
        "meals_per_day": "5",
        "feeding_reminders": False,
        "portion_tracking": "yes",
        "calorie_tracking": 0,
        "auto_schedule": "on",
    })

    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[DOG_OPTIONS_FIELD]["dog-1"]["feeding_settings"] == {
        "default_meals_per_day": 5,
        "feeding_reminders": False,
        "portion_tracking": True,
        "calorie_tracking": False,
        "auto_schedule": True,
    }
    assert (
        data["feeding_settings"] == data[DOG_OPTIONS_FIELD]["dog-1"]["feeding_settings"]
    )


async def test_async_step_feeding_settings_reports_validation_and_generic_errors() -> (
    None
):
    """Validation and unexpected exceptions should map to expected form errors."""
    flow = _FeedingFlow(dogs=[{"dog_id": "dog-1"}], current_dog={"dog_id": "dog-1"})

    def _raise_validation(*_args, **_kwargs):
        raise FlowValidationError(field_errors={"meals_per_day": "invalid"})

    flow._build_feeding_settings = _raise_validation  # type: ignore[assignment]
    validation = await flow.async_step_feeding_settings({"meals_per_day": 0})
    assert validation["type"] == FlowResultType.FORM
    assert validation["errors"] == {"meals_per_day": "invalid"}

    def _raise_generic(*_args, **_kwargs):
        raise RuntimeError("boom")

    flow._build_feeding_settings = _raise_generic  # type: ignore[assignment]
    generic = await flow.async_step_feeding_settings({"meals_per_day": 2})
    assert generic["type"] == FlowResultType.FORM
    assert generic["errors"] == {"base": "update_failed"}
