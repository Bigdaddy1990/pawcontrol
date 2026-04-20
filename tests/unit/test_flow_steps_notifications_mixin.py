"""Coverage-focused tests for notification flow mixins."""

from collections.abc import Mapping
from typing import Any, cast

import pytest
import voluptuous as vol

from custom_components.pawcontrol.const import CONF_NOTIFICATIONS
from custom_components.pawcontrol.flow_steps.notifications import (
    NotificationOptionsMixin,
    NotificationOptionsNormalizerMixin,
)
from custom_components.pawcontrol.types import (
    DEFAULT_NOTIFICATION_OPTIONS,
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    DOG_OPTIONS_FIELD,
    JSONValue,
    NotificationOptions,
)


class _NotificationHost(NotificationOptionsNormalizerMixin, NotificationOptionsMixin):
    """Minimal host for exercising the notification flow mixins."""

    def __init__(self) -> None:
        self._dogs = [
            {
                DOG_ID_FIELD: "buddy",
                DOG_NAME_FIELD: "Buddy",
            }
        ]
        self._current_dog = self._dogs[0]
        self._options: dict[str, JSONValue] = {
            CONF_NOTIFICATIONS: cast(
                JSONValue,
                {
                    "quiet_hours": False,
                    "quiet_start": "20:00:00",
                    "quiet_end": "06:00:00",
                    "reminder_repeat_min": 15,
                    "priority_notifications": False,
                    "mobile_notifications": True,
                },
            ),
            DOG_OPTIONS_FIELD: cast(
                JSONValue,
                {
                    "buddy": {
                        DOG_ID_FIELD: "buddy",
                    }
                },
            ),
        }
        self.last_form: dict[str, Any] | None = None
        self.last_created_entry: dict[str, Any] | None = None

    def _clone_options(self) -> dict[str, JSONValue]:
        return dict(self._options)

    def _current_dog_options(self) -> dict[str, dict[str, Any]]:
        dog_options = self._options.get(DOG_OPTIONS_FIELD, {})
        return cast(dict[str, dict[str, Any]], dog_options)

    def _current_options(self) -> Mapping[str, JSONValue]:
        return self._options

    def _normalise_options_snapshot(
        self,
        options: Mapping[str, JSONValue],
    ) -> Mapping[str, JSONValue]:
        mutable = dict(options)
        self._normalise_notification_options(cast(dict[str, JSONValue], mutable))
        return mutable

    def _build_dog_selector_schema(self) -> vol.Schema:
        return vol.Schema({vol.Required("dog_id"): str})

    def _require_current_dog(self) -> dict[str, str] | None:
        return cast(dict[str, str] | None, self._current_dog)

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "on", "yes", "1"}:
                return True
            if lowered in {"false", "off", "no", "0"}:
                return False
        return default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except TypeError:
            return default
        except ValueError:
            return default

    @staticmethod
    def _coerce_time_string(value: Any, default: str) -> str:
        if value is None:
            return default
        candidate = str(value).strip()
        return candidate or default

    def _select_dog_by_id(self, dog_id: str | None) -> dict[str, str] | None:
        selected = next(
            (
                cast(dict[str, str], dog)
                for dog in self._dogs
                if dog.get(DOG_ID_FIELD) == dog_id
            ),
            None,
        )
        self._current_dog = selected
        return selected

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: vol.Schema,
        errors: dict[str, str] | None = None,
        description_placeholders: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.last_form = {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
            "description_placeholders": description_placeholders,
        }
        return self.last_form

    def async_create_entry(
        self,
        *,
        title: str,
        data: Mapping[str, JSONValue],
    ) -> dict[str, Any]:
        self.last_created_entry = {
            "type": "create_entry",
            "title": title,
            "data": dict(data),
        }
        return self.last_created_entry

    async def async_step_init(self) -> dict[str, str]:
        return {"type": "menu", "step_id": "init"}


def test_current_notification_options_prefers_per_dog_payload() -> None:
    """Dog-specific notifications should take precedence over legacy options."""
    host = _NotificationHost()
    host._current_dog_options()["buddy"][CONF_NOTIFICATIONS] = {
        "quiet_hours": True,
        "quiet_start": "21:15:00",
        "quiet_end": "05:45:00",
        "reminder_repeat_min": 25,
        "priority_notifications": True,
        "mobile_notifications": False,
    }

    options = host._current_notification_options("buddy")

    assert options["quiet_hours"] is True
    assert options["quiet_start"] == "21:15:00"
    assert options["quiet_end"] == "05:45:00"
    assert options["reminder_repeat_min"] == 25
    assert options["priority_notifications"] is True
    assert options["mobile_notifications"] is False


def test_current_notification_options_falls_back_to_defaults_for_invalid_legacy() -> (
    None
):
    """Invalid legacy payloads should normalise back to typed defaults."""
    host = _NotificationHost()
    host._options[CONF_NOTIFICATIONS] = cast(JSONValue, "invalid")

    options = host._current_notification_options("missing")

    assert options == dict(DEFAULT_NOTIFICATION_OPTIONS)


def test_current_notification_options_with_none_dog_id_uses_legacy_payload() -> None:
    """A missing dog identifier should use legacy/root notifications directly."""
    host = _NotificationHost()
    host._options[CONF_NOTIFICATIONS] = cast(
        JSONValue,
        {
            "quiet_hours": True,
            "quiet_start": "23:00:00",
            "quiet_end": "07:00:00",
            "reminder_repeat_min": 10,
            "priority_notifications": True,
            "mobile_notifications": False,
        },
    )

    options = host._current_notification_options(None)

    assert options["quiet_hours"] is True
    assert options["quiet_start"] == "23:00:00"
    assert options["mobile_notifications"] is False


def test_normalise_notification_options_populates_root_and_per_dog_payloads() -> None:
    """Normalisation should type root notifications and fill missing dog entries."""
    host = _NotificationHost()
    mutable: dict[str, JSONValue] = {
        CONF_NOTIFICATIONS: cast(
            JSONValue,
            {
                "quiet_hours": "off",
                "quiet_start": " 19:30:00 ",
                "quiet_end": None,
                "reminder_repeat_min": "20",
                "priority_notifications": "yes",
                "mobile_notifications": 0,
            },
        ),
        DOG_OPTIONS_FIELD: cast(
            JSONValue,
            {
                "buddy": {DOG_ID_FIELD: "buddy"},
                "milo": {
                    DOG_ID_FIELD: "milo",
                    CONF_NOTIFICATIONS: {
                        "quiet_hours": True,
                        "quiet_start": "18:00:00",
                        "quiet_end": "06:15:00",
                        "reminder_repeat_min": 40,
                        "priority_notifications": False,
                        "mobile_notifications": True,
                    },
                },
            },
        ),
    }

    normalised = host._normalise_notification_options(mutable)

    assert normalised is not None
    assert mutable[CONF_NOTIFICATIONS] == normalised
    buddy_entry = cast(
        dict[str, Any], cast(dict[str, Any], mutable[DOG_OPTIONS_FIELD])["buddy"]
    )
    assert buddy_entry[CONF_NOTIFICATIONS] == normalised
    milo_entry = cast(
        dict[str, Any], cast(dict[str, Any], mutable[DOG_OPTIONS_FIELD])["milo"]
    )
    assert milo_entry[CONF_NOTIFICATIONS]["quiet_start"] == "18:00:00"


def test_normalise_notification_options_returns_none_when_key_missing() -> None:
    """Normalisation should no-op when notifications are absent."""
    host = _NotificationHost()
    mutable: dict[str, JSONValue] = {
        DOG_OPTIONS_FIELD: cast(JSONValue, {"buddy": {DOG_ID_FIELD: "buddy"}})
    }

    normalised = host._normalise_notification_options(mutable)

    assert normalised is None
    assert CONF_NOTIFICATIONS not in mutable


def test_normalise_notification_options_handles_non_mapping_dog_options() -> None:
    """Non-mapping dog options should still normalise root notifications safely."""
    host = _NotificationHost()
    mutable: dict[str, JSONValue] = {
        CONF_NOTIFICATIONS: cast(
            JSONValue,
            {
                "quiet_hours": False,
                "quiet_start": "20:00:00",
                "quiet_end": "06:00:00",
                "reminder_repeat_min": 15,
                "priority_notifications": True,
                "mobile_notifications": True,
            },
        ),
        DOG_OPTIONS_FIELD: cast(JSONValue, "invalid"),
    }

    normalised = host._normalise_notification_options(mutable)

    assert normalised is not None
    assert mutable[CONF_NOTIFICATIONS] == normalised
    # The non-mapping dog options payload should be left untouched.
    assert mutable[DOG_OPTIONS_FIELD] == "invalid"


def test_build_notification_settings_wrapper_uses_class_payload_builder() -> None:
    """The instance wrapper should delegate to the class-level payload helper."""
    host = _NotificationHost()
    current = host._current_notification_options("buddy")

    updated = host._build_notification_settings(
        {
            "quiet_hours": "true",
            "quiet_start": "22:10:00",
            "quiet_end": "06:20:00",
            "reminder_repeat_min": "50",
            "priority_notifications": "1",
            "mobile_notifications": "0",
        },
        current,
    )

    assert updated["quiet_hours"] is True
    assert updated["reminder_repeat_min"] == 50
    assert updated["priority_notifications"] is True
    assert updated["mobile_notifications"] is False


@pytest.mark.asyncio
async def test_select_dog_for_notifications_handles_empty_and_invalid_selection() -> (
    None
):
    """Dog selection should return to init when no selectable dog is available."""
    host = _NotificationHost()
    host._dogs = []

    assert await host.async_step_select_dog_for_notifications() == {
        "type": "menu",
        "step_id": "init",
    }

    host = _NotificationHost()
    result = await host.async_step_select_dog_for_notifications({"dog_id": "unknown"})

    assert result == {"type": "menu", "step_id": "init"}


@pytest.mark.asyncio
async def test_select_dog_for_notifications_routes_to_notifications_when_selected() -> (
    None
):
    """Selecting a valid dog should continue to notifications step."""
    host = _NotificationHost()

    result = await host.async_step_select_dog_for_notifications({"dog_id": "buddy"})

    assert result["type"] == "form"
    assert result["step_id"] == "notifications"


@pytest.mark.asyncio
async def test_select_dog_for_notifications_shows_selector_form_without_input() -> None:
    """Without user input, the step should render the dog selector form."""
    host = _NotificationHost()

    result = await host.async_step_select_dog_for_notifications()

    assert result["type"] == "form"
    assert result["step_id"] == "select_dog_for_notifications"


@pytest.mark.asyncio
async def test_async_step_notifications_creates_typed_entry() -> None:
    """Submitting valid notification settings should create an updated entry."""
    host = _NotificationHost()

    result = await host.async_step_notifications({
        "quiet_hours": True,
        "quiet_start": "21:00:00",
        "quiet_end": "06:30:00",
        "reminder_repeat_min": "45",
        "priority_notifications": False,
        "mobile_notifications": True,
    })

    assert result["type"] == "create_entry"
    created_data = cast(dict[str, Any], result["data"])
    assert created_data[CONF_NOTIFICATIONS]["reminder_repeat_min"] == 45
    assert created_data[DOG_OPTIONS_FIELD]["buddy"][CONF_NOTIFICATIONS][
        "quiet_end"
    ] == ("06:30:00")


@pytest.mark.asyncio
async def test_async_step_notifications_skips_per_dog_write_when_other_dogs_exist() -> (
    None
):
    """Per-dog options should remain unchanged when current dog is absent from map."""
    host = _NotificationHost()
    host._options[DOG_OPTIONS_FIELD] = cast(
        JSONValue,
        {"other": {DOG_ID_FIELD: "other", CONF_NOTIFICATIONS: {"quiet_hours": False}}},
    )

    result = await host.async_step_notifications({
        "quiet_hours": True,
        "quiet_start": "21:00:00",
        "quiet_end": "06:30:00",
        "reminder_repeat_min": "45",
        "priority_notifications": False,
        "mobile_notifications": True,
    })

    assert result["type"] == "create_entry"
    created_data = cast(dict[str, Any], result["data"])
    assert "buddy" not in cast(dict[str, Any], created_data[DOG_OPTIONS_FIELD])
    assert created_data[CONF_NOTIFICATIONS]["quiet_hours"] is True


@pytest.mark.asyncio
async def test_async_step_notifications_reports_validation_and_runtime_errors() -> None:
    """Validation and unexpected failures should map to Home Assistant form errors."""
    host = _NotificationHost()
    invalid_result = await host.async_step_notifications({
        "quiet_hours": True,
        "quiet_start": "21:00:00",
        "quiet_end": "06:30:00",
        "reminder_repeat_min": "1",
        "priority_notifications": True,
        "mobile_notifications": True,
    })
    assert invalid_result["errors"] == {"reminder_repeat_min": "invalid_configuration"}

    class _RuntimeFailureHost(_NotificationHost):
        def _build_notification_settings(
            self,
            user_input: dict[str, Any],
            current: NotificationOptions,
        ) -> NotificationOptions:
            raise RuntimeError("boom")

    runtime_result = await _RuntimeFailureHost().async_step_notifications({
        "quiet_hours": True,
        "quiet_start": "21:00:00",
        "quiet_end": "06:30:00",
        "reminder_repeat_min": "30",
        "priority_notifications": True,
        "mobile_notifications": True,
    })
    assert runtime_result["errors"] == {"base": "update_failed"}


@pytest.mark.asyncio
async def test_notifications_redirects_when_current_dog_missing() -> None:
    """Hosts without a current dog should return to dog selection."""
    host = _NotificationHost()
    host._current_dog = None

    result = await host.async_step_notifications()

    assert result["type"] == "form"
    assert result["step_id"] == "select_dog_for_notifications"


@pytest.mark.asyncio
async def test_notifications_redirects_when_current_dog_missing_identifier() -> None:
    """Hosts without a current dog identifier should return to dog selection."""
    host = _NotificationHost()
    host._current_dog = {DOG_NAME_FIELD: "Buddy"}

    result = await host.async_step_notifications()

    assert result["type"] == "form"
    assert result["step_id"] == "select_dog_for_notifications"


@pytest.mark.asyncio
async def test_notifications_without_user_input_shows_notifications_form() -> None:
    """When a dog is selected, the notifications step should render its form."""
    host = _NotificationHost()

    result = await host.async_step_notifications()

    assert result["type"] == "form"
    assert result["step_id"] == "notifications"
