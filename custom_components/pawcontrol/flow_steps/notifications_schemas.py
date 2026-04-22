"""Notification schema builders for Paw Control flows."""

import voluptuous as vol

from ..const import DEFAULT_REMINDER_REPEAT_MIN
from ..selector_shim import selector
from ..types import (
    NOTIFICATION_MOBILE_FIELD,
    NOTIFICATION_PRIORITY_FIELD,
    NOTIFICATION_QUIET_END_FIELD,
    NOTIFICATION_QUIET_HOURS_FIELD,
    NOTIFICATION_QUIET_START_FIELD,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
    NotificationOptions,
    NotificationSettingsInput,
)


def build_notifications_schema(
    current_notifications: NotificationOptions,
    user_input: NotificationSettingsInput | None = None,
) -> vol.Schema:
    """Build notifications schema."""
    current_values = user_input or {}
    return vol.Schema(
        {
            vol.Required(
                NOTIFICATION_QUIET_HOURS_FIELD,
                default=current_values.get(
                    NOTIFICATION_QUIET_HOURS_FIELD,
                    current_notifications.get(
                        NOTIFICATION_QUIET_HOURS_FIELD,
                        True,
                    ),
                ),
            ): selector.BooleanSelector(),
            vol.Required(
                NOTIFICATION_QUIET_START_FIELD,
                default=current_values.get(
                    NOTIFICATION_QUIET_START_FIELD,
                    current_notifications.get(
                        NOTIFICATION_QUIET_START_FIELD,
                        "22:00:00",
                    ),
                ),
            ): selector.TimeSelector(),
            vol.Required(
                NOTIFICATION_QUIET_END_FIELD,
                default=current_values.get(
                    NOTIFICATION_QUIET_END_FIELD,
                    current_notifications.get(
                        NOTIFICATION_QUIET_END_FIELD,
                        "07:00:00",
                    ),
                ),
            ): selector.TimeSelector(),
            vol.Required(
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
                    max=240,
                    step=5,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="minutes",
                ),
            ),
            vol.Required(
                NOTIFICATION_PRIORITY_FIELD,
                default=current_values.get(
                    NOTIFICATION_PRIORITY_FIELD,
                    current_notifications.get(
                        NOTIFICATION_PRIORITY_FIELD,
                        True,
                    ),
                ),
            ): selector.BooleanSelector(),
            vol.Required(
                NOTIFICATION_MOBILE_FIELD,
                default=current_values.get(
                    NOTIFICATION_MOBILE_FIELD,
                    current_notifications.get(
                        NOTIFICATION_MOBILE_FIELD,
                        True,
                    ),
                ),
            ): selector.BooleanSelector(),
        },
    )
