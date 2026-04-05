"""Coverage-focused tests for flow_steps mixins and exports."""

from typing import Any

import pytest

from custom_components.pawcontrol.const import CONF_NOTIFICATIONS
from custom_components.pawcontrol.exceptions import FlowValidationError, ValidationError
from custom_components.pawcontrol.flow_steps import (
    DogGPSFlowMixin,
    DogHealthFlowMixin,
    GPSModuleDefaultsMixin,
    GPSOptionsMixin,
    HealthOptionsMixin,
    HealthSummaryMixin,
    NotificationOptionsMixin,
    NotificationOptionsNormalizerMixin,
    SystemSettingsOptionsMixin,
)
from custom_components.pawcontrol.flow_steps.gps import (
    _validate_gps_accuracy,
    _validate_gps_update_interval,
)
from custom_components.pawcontrol.flow_steps.health import MODULE_MEDICATION
from custom_components.pawcontrol.flow_steps.notifications import (
    NotificationOptionsMixin as NotificationOptionsMixinImpl,
)
from custom_components.pawcontrol.types import (
    DOG_AGE_FIELD,
    DOG_FEEDING_CONFIG_FIELD,
    DOG_HEALTH_CONFIG_FIELD,
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    DOG_OPTIONS_FIELD,
    DOG_SIZE_FIELD,
    DOG_WEIGHT_FIELD,
)


class _GPSDefaultsFlow(GPSModuleDefaultsMixin):
    def __init__(self, discovery: dict[str, Any] | None) -> None:
        self._discovery_info = discovery


class _HealthSummaryFlow(HealthSummaryMixin):
    pass


class _NotificationFlow(
    NotificationOptionsMixin,
    NotificationOptionsNormalizerMixin,
):
    def __init__(self, *, options: dict[str, Any], dog_options: dict[str, Any]) -> None:
        self._options = options
        self._dog_options = dog_options
        self._dogs: list[dict[str, Any]] = []
        self._current_dog = None

    def _current_options(self) -> dict[str, Any]:
        return self._options

    def _current_dog_options(self) -> dict[str, Any]:
        return self._dog_options


class _NotificationAsyncFlow(_NotificationFlow):
    def __init__(self, *, options: dict[str, Any], dog_options: dict[str, Any]) -> None:
        super().__init__(options=options, dog_options=dog_options)
        self._dogs = [{"dog_id": "dog-1", "name": "Rex"}]
        self._current_dog = self._dogs[0]
        self.init_calls = 0

    def _build_dog_selector_schema(self) -> Any:
        return object()

    def _select_dog_by_id(self, dog_id: str | None) -> dict[str, Any] | None:
        self._current_dog = next(
            (dog for dog in self._dogs if dog.get("dog_id") == dog_id),
            None,
        )
        return self._current_dog

    def _require_current_dog(self) -> dict[str, Any] | None:
        return self._current_dog

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        return bool(value) if value is not None else default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        return int(value) if value is not None else default

    @staticmethod
    def _coerce_time_string(value: Any, default: str) -> str:
        return str(value) if value is not None else default

    def _clone_options(self) -> dict[str, Any]:
        return dict(self._options)

    def _normalise_options_snapshot(self, options: dict[str, Any]) -> dict[str, Any]:
        return options

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}

    async def async_step_init(self) -> dict[str, Any]:
        self.init_calls += 1
        return {"type": "init"}


class _DogHealthFlow(DogHealthFlowMixin):
    def __init__(self, current_dog: dict[str, Any] | None) -> None:
        self._current_dog_config = current_dog
        self._dogs: list[dict[str, Any]] = []
        self.add_calls = 0
        self.add_another_calls = 0

    def _collect_health_conditions(self, user_input: dict[str, Any]) -> list[str]:
        return list(user_input.get("health_conditions", []))

    def _collect_special_diet(self, user_input: dict[str, Any]) -> list[str]:
        return list(user_input.get("special_diet_requirements", []))

    def _build_vaccination_records(self, _user_input: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _build_medication_entries(
        self, user_input: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if user_input.get("with_meals"):
            return [{"name": "supplement", "with_meals": True}]
        return []

    def _suggest_activity_level(self, _dog_age: int, _dog_size: str) -> str:
        return "moderate"

    def _validate_diet_combinations(self, _diet_options: list[str]) -> dict[str, Any]:
        return {
            "conflicts": [],
            "warnings": [],
            "recommended_vet_consultation": False,
        }

    async def _async_get_translation_lookup(
        self,
    ) -> tuple[dict[str, str], dict[str, str]]:
        return ({}, {})

    async def _get_diet_compatibility_guidance(
        self,
        _dog_age: int,
        _dog_size: str,
    ) -> str:
        return "guidance"

    async def async_step_add_dog(self) -> dict[str, Any]:
        self.add_calls += 1
        return {"type": "add_dog"}

    async def async_step_add_another_dog(self) -> dict[str, Any]:
        self.add_another_calls += 1
        return {"type": "add_another"}

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}


def test_flow_steps_exports_are_available() -> None:
    """Package exports should expose flow mixins for import convenience."""
    assert DogGPSFlowMixin is not None
    assert GPSModuleDefaultsMixin is not None
    assert GPSOptionsMixin is not None
    assert DogHealthFlowMixin is not None
    assert HealthSummaryMixin is not None
    assert HealthOptionsMixin is not None
    assert NotificationOptionsMixin is not None
    assert NotificationOptionsNormalizerMixin is not None
    assert SystemSettingsOptionsMixin is not None


def test_gps_required_validators_cover_success_and_error_paths() -> None:
    """Required GPS validators should return values or raise typed errors."""
    assert _validate_gps_update_interval("45", field="gps", minimum=5, maximum=60) == 45
    assert (
        _validate_gps_accuracy("22.4", field="accuracy", minimum=1.0, maximum=50.0)
        == 22.4
    )

    with pytest.raises(ValidationError):
        _validate_gps_update_interval("oops", field="gps", minimum=5, maximum=60)

    with pytest.raises(ValidationError):
        _validate_gps_accuracy(
            "not-a-float", field="accuracy", minimum=1.0, maximum=50.0
        )


def test_gps_module_defaults_use_discovery_or_dog_size() -> None:
    """GPS defaults should react to discovery context and dog size hints."""
    discovered = _GPSDefaultsFlow(discovery={"source": "zeroconf"})
    assert discovered._should_enable_gps({"dog_size": "small"}) is True
    assert "discovered tracking device" in discovered._get_smart_module_defaults({
        "dog_size": "small"
    })

    large_dog = _GPSDefaultsFlow(discovery=None)
    assert large_dog._should_enable_gps({"dog_size": "giant"}) is True
    assert "larger dogs" in large_dog._get_smart_module_defaults({"dog_size": "large"})

    default_dog = _GPSDefaultsFlow(discovery=None)
    assert default_dog._should_enable_gps({"dog_size": "small"}) is False
    assert default_dog._get_smart_module_defaults({"dog_size": "small"}) == (
        "Standard defaults applied"
    )


def test_health_summary_mixin_formats_fallback_and_issue_strings() -> None:
    """Health summary mixin should format both healthy and unhealthy summaries."""
    flow = _HealthSummaryFlow()

    assert flow._summarise_health_summary(None) == "No recent health summary"
    assert flow._summarise_health_summary({"healthy": True}) == "Healthy"

    issue_summary = flow._summarise_health_summary({
        "healthy": False,
        "issues": ["arthritis"],
        "warnings": ["weight"],
    })
    assert "Issues detected" in issue_summary
    assert "Issues: arthritis" in issue_summary
    assert "Warnings: weight" in issue_summary


def test_notification_mixins_normalise_legacy_and_per_dog_payloads() -> None:
    """Notification mixins should pull legacy defaults and backfill dog options."""
    flow = _NotificationFlow(
        options={
            CONF_NOTIFICATIONS: {
                "priority_notifications": True,
                "quiet_hours": False,
            }
        },
        dog_options={},
    )

    current = flow._current_notification_options("dog-1")
    assert current["quiet_hours"] is False
    assert current["priority_notifications"] is True

    mutable: dict[str, Any] = {
        CONF_NOTIFICATIONS: {"quiet_hours": True},
        DOG_OPTIONS_FIELD: {"dog-1": {}},
    }
    normalised = flow._normalise_notification_options(mutable)
    assert normalised is not None
    assert mutable[DOG_OPTIONS_FIELD]["dog-1"]["notifications"]["quiet_hours"] is True


def test_notification_normaliser_returns_none_when_notifications_missing() -> None:
    """Notification normaliser should no-op if notifications key is absent."""
    flow = _NotificationFlow(options={}, dog_options={})
    mutable: dict[str, Any] = {DOG_OPTIONS_FIELD: {"dog-1": {"dog_id": "dog-1"}}}

    normalised = flow._normalise_notification_options(mutable)

    assert normalised is None


def test_notification_options_mixin_prefers_per_dog_notification_entry() -> None:
    """Per-dog notification payload should override legacy global options."""
    flow = _NotificationFlow(
        options={CONF_NOTIFICATIONS: {"quiet_hours": False}},
        dog_options={
            "dog-1": {
                "dog_id": "dog-1",
                "notifications": {
                    "quiet_hours": True,
                    "priority_notifications": True,
                },
            }
        },
    )

    current = NotificationOptionsMixinImpl._current_notification_options(flow, "dog-1")
    assert current["quiet_hours"] is True
    assert current["priority_notifications"] is True


@pytest.mark.asyncio
async def test_notification_flow_select_dog_redirects_when_missing_dogs() -> None:
    flow = _NotificationAsyncFlow(options={}, dog_options={})
    flow._dogs = []

    result = await flow.async_step_select_dog_for_notifications()

    assert result == {"type": "init"}
    assert flow.init_calls == 1


@pytest.mark.asyncio
async def test_notification_flow_select_dog_with_user_input_routes_to_form() -> None:
    flow = _NotificationAsyncFlow(options={}, dog_options={})

    result = await flow.async_step_select_dog_for_notifications({"dog_id": "missing"})

    assert result == {"type": "init"}


@pytest.mark.asyncio
async def test_notification_flow_select_dog_with_user_input_routes_to_step() -> None:
    """Selecting a known dog should route into the notifications step."""
    flow = _NotificationAsyncFlow(options={}, dog_options={})

    result = await flow.async_step_select_dog_for_notifications({"dog_id": "dog-1"})

    assert result["type"] == "form"
    assert result["step_id"] == "notifications"


@pytest.mark.asyncio
async def test_notification_flow_select_dog_without_input_shows_selector() -> None:
    """Selector step should show the selector form when no input is given."""
    flow = _NotificationAsyncFlow(options={}, dog_options={})

    result = await flow.async_step_select_dog_for_notifications()

    assert result["type"] == "form"
    assert result["step_id"] == "select_dog_for_notifications"


@pytest.mark.asyncio
async def test_notification_flow_notifications_step_redirects_without_valid_dog() -> (
    None
):
    """Notifications step should redirect if no valid current dog id exists."""
    flow = _NotificationAsyncFlow(options={}, dog_options={})
    flow._current_dog = None

    no_dog = await flow.async_step_notifications()
    assert no_dog["type"] == "form"
    assert no_dog["step_id"] == "select_dog_for_notifications"

    flow._current_dog = {"dog_id": 123}
    invalid_id = await flow.async_step_notifications()
    assert invalid_id["type"] == "form"
    assert invalid_id["step_id"] == "select_dog_for_notifications"


@pytest.mark.asyncio
async def test_notification_flow_notifications_step_without_input_shows_form() -> None:
    """Notifications step should render schema when user input is missing."""
    flow = _NotificationAsyncFlow(options={}, dog_options={})

    result = await flow.async_step_notifications()

    assert result["type"] == "form"
    assert result["step_id"] == "notifications"


@pytest.mark.asyncio
async def test_notification_flow_notifications_step_handles_success_and_errors() -> (
    None
):
    flow = _NotificationAsyncFlow(
        options={CONF_NOTIFICATIONS: {"quiet_hours": False}},
        dog_options={},
    )

    valid_input = {
        "quiet_hours": True,
        "quiet_start": "22:00",
        "quiet_end": "07:00",
        "reminder_repeat": 30,
        "priority_notifications": True,
        "mobile_notifications": True,
    }

    flow._build_notification_settings = lambda *_: {
        "quiet_hours": True,
        "quiet_start": "22:00:00",
        "quiet_end": "07:00:00",
        "reminder_repeat": 30,
        "priority_notifications": True,
        "mobile_notifications": True,
    }

    success = await flow.async_step_notifications(valid_input)
    assert success["type"] == "create_entry"

    flow._build_notification_settings = lambda *_: (_ for _ in ()).throw(
        FlowValidationError(base_errors=["invalid_notifications"])
    )
    validation = await flow.async_step_notifications(valid_input)
    assert validation["type"] == "form"
    assert validation["errors"] == {"base": "invalid_notifications"}

    flow._build_notification_settings = lambda *_: (_ for _ in ()).throw(
        RuntimeError("boom")
    )
    failed = await flow.async_step_notifications(valid_input)
    assert failed["type"] == "form"
    assert failed["errors"] == {"base": "update_failed"}


def test_notification_flow_build_notification_settings_wrapper() -> None:
    """Wrapper should delegate to the class-level payload builder."""
    flow = _NotificationAsyncFlow(options={}, dog_options={})
    user_input = {
        "quiet_hours": True,
        "quiet_start": "21:00",
        "quiet_end": "07:00",
        "reminder_repeat_min": 30,
    }
    current = flow._current_notification_options("dog-1")

    payload = flow._build_notification_settings(user_input, current)

    assert payload["quiet_hours"] is True
    assert payload["quiet_start"] == "21:00"
    assert payload["reminder_repeat_min"] == 30


@pytest.mark.asyncio
async def test_dog_health_step_redirects_when_no_current_dog() -> None:
    """Health step should restart dog flow if no active dog context is set."""
    flow = _DogHealthFlow(current_dog=None)

    result = await flow.async_step_dog_health()

    assert result == {"type": "add_dog"}
    assert flow.add_calls == 1


@pytest.mark.asyncio
async def test_dog_health_step_without_input_renders_form() -> None:
    """Health step should render the form with placeholders when input is absent."""
    flow = _DogHealthFlow(
        current_dog={
            DOG_NAME_FIELD: "Rex",
            DOG_AGE_FIELD: 4,
            DOG_SIZE_FIELD: "large",
            DOG_WEIGHT_FIELD: 28.5,
            "modules": {MODULE_MEDICATION: True},
            "medications": [{"name": "joint support"}],
        }
    )

    result = await flow.async_step_dog_health()

    assert result["type"] == "form"
    assert result["step_id"] == "dog_health"
    placeholders = result["description_placeholders"]
    assert placeholders["dog_name"] == "Rex"
    assert placeholders["medication_enabled"] == "yes"


@pytest.mark.asyncio
async def test_dog_health_step_with_input_updates_health_and_feeding() -> None:
    """Health input should persist health payload and enrich feeding settings."""
    current_dog = {
        DOG_NAME_FIELD: "Milo",
        DOG_ID_FIELD: "dog-1",
        DOG_AGE_FIELD: 2,
        DOG_SIZE_FIELD: "medium",
        DOG_WEIGHT_FIELD: 20.0,
        "modules": {MODULE_MEDICATION: True},
        DOG_FEEDING_CONFIG_FIELD: {"existing": True},
    }
    flow = _DogHealthFlow(current_dog=current_dog)

    result = await flow.async_step_dog_health({
        "vet_name": "Dr. Vet",
        "vet_phone": "555-0100",
        "weight_tracking": True,
        "ideal_weight": 19.5,
        "body_condition_score": 4,
        "activity_level": "high",
        "weight_goal": "lose",
        "spayed_neutered": True,
        "health_conditions": ["arthritis"],
        "special_diet_requirements": ["low_fat"],
        "with_meals": True,
        "health_aware_portions": True,
    })

    assert result == {"type": "add_another"}
    assert flow.add_another_calls == 1
    assert len(flow._dogs) == 1

    stored_dog = flow._dogs[0]
    assert DOG_HEALTH_CONFIG_FIELD in stored_dog
    health_config = stored_dog[DOG_HEALTH_CONFIG_FIELD]
    assert health_config["vet_name"] == "Dr. Vet"
    assert health_config["medications"][0]["with_meals"] is True

    feeding_config = stored_dog[DOG_FEEDING_CONFIG_FIELD]
    assert feeding_config["health_aware_portions"] is True
    assert feeding_config["age_months"] == 24
    assert feeding_config["medication_with_meals"] is True
