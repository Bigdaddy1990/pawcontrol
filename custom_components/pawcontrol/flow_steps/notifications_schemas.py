"""Notification schema builders for Paw Control flows."""

import voluptuous as vol

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
    del current_notifications, user_input
    return vol.Schema(
        {
            vol.Optional(NOTIFICATION_QUIET_HOURS_FIELD): selector.BooleanSelector(),
            vol.Optional(NOTIFICATION_QUIET_START_FIELD): selector.TimeSelector(),
            vol.Optional(NOTIFICATION_QUIET_END_FIELD): selector.TimeSelector(),
            vol.Optional(NOTIFICATION_REMINDER_REPEAT_FIELD): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5,
                    max=240,
                    step=5,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="minutes",
                ),
            ),
            vol.Optional(NOTIFICATION_PRIORITY_FIELD): selector.BooleanSelector(),
            vol.Optional(NOTIFICATION_MOBILE_FIELD): selector.BooleanSelector(),
        },
    )
