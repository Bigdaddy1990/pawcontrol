"""Repairs support for Paw Control integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PawControlRepairFlow(RepairsFlow):
    """Handler for Paw Control repair flows."""

    def __init__(self, issue_id: str) -> None:
        """Initialize the repair flow."""
        self.issue_id = issue_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of a fix flow."""
        
        # Parse issue ID to determine type
        if "missing_door_sensor" in self.issue_id:
            return await self.async_step_missing_door_sensor(user_input)
        elif "invalid_export_path" in self.issue_id:
            return await self.async_step_invalid_export_path(user_input)
        elif "missing_notification_service" in self.issue_id:
            return await self.async_step_missing_notification_service(user_input)
        elif "dog_config_error" in self.issue_id:
            return await self.async_step_dog_config_error(user_input)
        else:
            return await self.async_step_generic_fix(user_input)

    async def async_step_missing_door_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle missing door sensor issue."""
        if user_input is not None:
            # User acknowledged the issue
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="missing_door_sensor",
            description_placeholders={
                "description": "The configured door sensor is not available. "
                               "Walk detection may not work correctly. "
                               "Please check your door sensor configuration."
            },
        )

    async def async_step_invalid_export_path(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle invalid export path issue."""
        if user_input is not None:
            # User acknowledged the issue
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="invalid_export_path",
            description_placeholders={
                "description": "The export path is invalid or not accessible. "
                               "Reports cannot be saved to file. "
                               "Please update the export path in the integration options."
            },
        )

    async def async_step_missing_notification_service(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle missing notification service issue."""
        if user_input is not None:
            # User acknowledged the issue
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="missing_notification_service",
            description_placeholders={
                "description": "The configured notification service is not available. "
                               "You will not receive reminders and alerts. "
                               "Please check your notification configuration."
            },
        )

    async def async_step_dog_config_error(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle dog configuration error."""
        if user_input is not None:
            # User acknowledged the issue
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="dog_config_error",
            description_placeholders={
                "description": "There is an issue with your dog configuration. "
                               "Some features may not work correctly. "
                               "Please reconfigure the integration."
            },
        )

    async def async_step_generic_fix(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle generic fix flow."""
        if user_input is not None:
            # User acknowledged the issue
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="generic_fix",
            description_placeholders={
                "description": "An issue was detected with Paw Control. "
                               "Please check your configuration and logs for more details."
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """Create a repair flow."""
    return PawControlRepairFlow(issue_id)


def create_repair_issue(
    hass: HomeAssistant,
    issue_type: str,
    entry: ConfigEntry,
    severity: ir.IssueSeverity = ir.IssueSeverity.WARNING,
    translation_key: str | None = None,
    translation_placeholders: dict[str, str] | None = None,
) -> None:
    """Create a repair issue."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{entry.entry_id}_{issue_type}",
        is_fixable=True,
        is_persistent=False,
        severity=severity,
        translation_key=translation_key or issue_type,
        translation_placeholders=translation_placeholders or {},
    )


def delete_repair_issue(
    hass: HomeAssistant,
    issue_type: str,
    entry: ConfigEntry,
) -> None:
    """Delete a repair issue."""
    ir.async_delete_issue(
        hass,
        DOMAIN,
        f"{entry.entry_id}_{issue_type}",
    )
