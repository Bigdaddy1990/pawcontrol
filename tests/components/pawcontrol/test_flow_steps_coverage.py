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
from custom_components.pawcontrol.flow_steps.notifications import (
    NotificationOptionsMixin as NotificationOptionsMixinImpl,
)
from custom_components.pawcontrol.types import DOG_OPTIONS_FIELD


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
async def test_notification_flow_notifications_step_handles_success_and_errors() -> None:
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
