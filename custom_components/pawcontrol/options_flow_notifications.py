"""Notification configuration steps for Paw Control options flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .const import CONF_NOTIFICATIONS, DEFAULT_REMINDER_REPEAT_MIN
from .exceptions import FlowValidationError
from .selector_shim import selector
from .types import (
    DEFAULT_NOTIFICATION_OPTIONS,
    DOG_ID_FIELD,
    DOG_OPTIONS_FIELD,
    NOTIFICATION_MOBILE_FIELD,
    NOTIFICATION_PRIORITY_FIELD,
    NOTIFICATION_QUIET_END_FIELD,
    NOTIFICATION_QUIET_HOURS_FIELD,
    NOTIFICATION_QUIET_START_FIELD,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
    DogConfigData,
    DogOptionsMap,
    JSONLikeMapping,
    JSONValue,
    NotificationOptions,
    NotificationOptionsInput,
    NotificationSettingsInput,
    OptionsDogSelectionInput,
    ensure_dog_options_entry,
    ensure_notification_options,
)

if TYPE_CHECKING:

    class NotificationOptionsHost:
        _current_dog: DogConfigData | None
        _dogs: list[DogConfigData]

        def _clone_options(self) -> dict[str, JSONValue]: ...

        def _current_dog_options(self) -> DogOptionsMap: ...

        def _current_options(self) -> Mapping[str, JSONValue]: ...

        def _normalise_options_snapshot(
            self, options: Mapping[str, JSONValue]
        ) -> Mapping[str, JSONValue]: ...

        def _build_dog_selector_schema(self) -> vol.Schema: ...

        def _require_current_dog(self) -> DogConfigData | None: ...

        def _select_dog_by_id(self, dog_id: str | None) -> DogConfigData | None: ...

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: vol.Schema,
            errors: dict[str, str] | None = None,
            description_placeholders: Mapping[str, str] | None = None,
        ) -> ConfigFlowResult: ...

        def async_create_entry(
            self, *, title: str, data: Mapping[str, JSONValue]
        ) -> ConfigFlowResult: ...

        async def async_step_init(self) -> ConfigFlowResult: ...

else:  # pragma: no cover
    NotificationOptionsHost = object


class NotificationOptionsMixin(NotificationOptionsHost):
    """Handle per-dog notification options."""

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        """Return a boolean value using Home Assistant style truthiness rules."""

        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {'1', 'true', 'on', 'yes'}
        return bool(value)

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        """Return an integer, falling back to the provided default on error."""

        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    @staticmethod
    def _coerce_time_string(value: Any, default: str) -> str:
        """Normalise selector values into Home Assistant time strings."""

        if value is None:
            return default
        if isinstance(value, str):
            return value
        iso_format = getattr(value, 'isoformat', None)
        if callable(iso_format):
            return str(iso_format())
        return default

    def _current_notification_options(self, dog_id: str) -> NotificationOptions:
        """Fetch per-dog notification configuration with legacy fallbacks."""

        dog_options = self._current_dog_options()
        entry = dog_options.get(dog_id, {})
        raw = entry.get(CONF_NOTIFICATIONS)
        payload: Mapping[str, JSONValue]
        if isinstance(raw, Mapping):
            payload = raw
        else:
            legacy = self._current_options().get(CONF_NOTIFICATIONS, {})
            payload = legacy if isinstance(legacy, Mapping) else {}

        return ensure_notification_options(
            cast(JSONLikeMapping, dict(payload)),
            defaults=cast(NotificationOptionsInput, dict(DEFAULT_NOTIFICATION_OPTIONS)),
        )

    @classmethod
    def _build_notification_settings_payload(
        cls, user_input: NotificationSettingsInput, current: NotificationOptions
    ) -> NotificationOptions:
        """Create a typed notification payload from submitted form data."""

        notifications: NotificationOptions = {
            NOTIFICATION_QUIET_HOURS_FIELD: cls._coerce_bool(
                user_input.get(NOTIFICATION_QUIET_HOURS_FIELD),
                current.get(NOTIFICATION_QUIET_HOURS_FIELD, True),
            ),
            NOTIFICATION_QUIET_START_FIELD: cls._coerce_time_string(
                user_input.get(NOTIFICATION_QUIET_START_FIELD),
                current.get(NOTIFICATION_QUIET_START_FIELD, '22:00:00'),
            ),
            NOTIFICATION_QUIET_END_FIELD: cls._coerce_time_string(
                user_input.get(NOTIFICATION_QUIET_END_FIELD),
                current.get(NOTIFICATION_QUIET_END_FIELD, '07:00:00'),
            ),
            NOTIFICATION_REMINDER_REPEAT_FIELD: cls._coerce_int(
                user_input.get(NOTIFICATION_REMINDER_REPEAT_FIELD),
                current.get(
                    NOTIFICATION_REMINDER_REPEAT_FIELD, DEFAULT_REMINDER_REPEAT_MIN
                ),
            ),
            NOTIFICATION_PRIORITY_FIELD: cls._coerce_bool(
                user_input.get(NOTIFICATION_PRIORITY_FIELD),
                current.get(NOTIFICATION_PRIORITY_FIELD, True),
            ),
            NOTIFICATION_MOBILE_FIELD: cls._coerce_bool(
                user_input.get(NOTIFICATION_MOBILE_FIELD),
                current.get(NOTIFICATION_MOBILE_FIELD, True),
            ),
        }

        return notifications

    def _build_notification_settings(
        self,
        user_input: NotificationSettingsInput,
        current: NotificationOptions,
    ) -> NotificationOptions:
        """Create a typed notification payload from submitted form data."""

        return self._build_notification_settings_payload(user_input, current)

    async def async_step_select_dog_for_notifications(
        self, user_input: OptionsDogSelectionInput | None = None
    ) -> ConfigFlowResult:
        """Select which dog to configure notifications for."""

        if not self._dogs:
            return await self.async_step_init()

        if user_input is not None:
            selected_dog_id = user_input.get('dog_id')
            self._select_dog_by_id(
                selected_dog_id if isinstance(selected_dog_id, str) else None
            )
            if self._current_dog:
                return await self.async_step_notifications()
            return await self.async_step_init()

        return self.async_show_form(
            step_id='select_dog_for_notifications',
            data_schema=self._build_dog_selector_schema(),
        )

    async def async_step_notifications(
        self, user_input: NotificationSettingsInput | None = None
    ) -> ConfigFlowResult:
        """Configure notification settings."""

        current_dog = self._require_current_dog()
        if current_dog is None:
            return await self.async_step_select_dog_for_notifications()

        dog_id = current_dog.get(DOG_ID_FIELD)
        if not isinstance(dog_id, str):
            return await self.async_step_select_dog_for_notifications()

        if user_input is not None:
            try:
                current_notifications = self._current_notification_options(dog_id)
                notification_settings = self._build_notification_settings(
                    user_input,
                    current_notifications,
                )

                new_options = self._clone_options()
                dog_options = self._current_dog_options()
                entry = ensure_dog_options_entry(
                    cast(JSONLikeMapping, dict(dog_options.get(dog_id, {}))),
                    dog_id=dog_id,
                )
                entry[CONF_NOTIFICATIONS] = notification_settings
                dog_options[dog_id] = entry
                new_options[DOG_OPTIONS_FIELD] = dog_options

                typed_options = self._normalise_options_snapshot(new_options)
                return self.async_create_entry(title='', data=typed_options)

            except FlowValidationError as err:
                return self.async_show_form(
                    step_id='notifications',
                    data_schema=self._get_notifications_schema(dog_id, user_input),
                    errors=err.as_form_errors(),
                )
            except Exception:
                return self.async_show_form(
                    step_id='notifications',
                    data_schema=self._get_notifications_schema(dog_id, user_input),
                    errors={'base': 'update_failed'},
                )

        return self.async_show_form(
            step_id='notifications',
            data_schema=self._get_notifications_schema(dog_id),
        )

    def _get_notifications_schema(
        self,
        dog_id: str,
        user_input: NotificationSettingsInput | None = None,
    ) -> vol.Schema:
        """Get notifications settings schema."""

        current_notifications = self._current_notification_options(dog_id)
        current_values = user_input or {}

        return vol.Schema(
            {
                vol.Optional(
                    NOTIFICATION_QUIET_HOURS_FIELD,
                    default=current_values.get(
                        NOTIFICATION_QUIET_HOURS_FIELD,
                        current_notifications.get(NOTIFICATION_QUIET_HOURS_FIELD, True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    NOTIFICATION_QUIET_START_FIELD,
                    default=current_values.get(
                        NOTIFICATION_QUIET_START_FIELD,
                        current_notifications.get(
                            NOTIFICATION_QUIET_START_FIELD, '22:00:00'
                        ),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    NOTIFICATION_QUIET_END_FIELD,
                    default=current_values.get(
                        NOTIFICATION_QUIET_END_FIELD,
                        current_notifications.get(
                            NOTIFICATION_QUIET_END_FIELD, '07:00:00'
                        ),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    NOTIFICATION_REMINDER_REPEAT_FIELD,
                    default=current_values.get(
                        NOTIFICATION_REMINDER_REPEAT_FIELD,
                        current_notifications.get(
                            NOTIFICATION_REMINDER_REPEAT_FIELD,
                            DEFAULT_REMINDER_REPEAT_MIN,
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=180,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement='minutes',
                    )
                ),
                vol.Optional(
                    NOTIFICATION_PRIORITY_FIELD,
                    default=current_values.get(
                        NOTIFICATION_PRIORITY_FIELD,
                        current_notifications.get(NOTIFICATION_PRIORITY_FIELD, True),
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    NOTIFICATION_MOBILE_FIELD,
                    default=current_values.get(
                        NOTIFICATION_MOBILE_FIELD,
                        current_notifications.get(NOTIFICATION_MOBILE_FIELD, True),
                    ),
                ): selector.BooleanSelector(),
            }
        )
