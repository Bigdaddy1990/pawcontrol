from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

try:
    # Falls vorhanden, Konsistenz mit deiner Domain
    from .const import DOMAIN  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    DOMAIN = "pawcontrol"


class OutdatedConfigRepairFlow(RepairsFlow):
    """Example repair flow with a simple confirm step."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Entry step."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Confirm and finish."""
        if user_input is not None:
            # Done; entry created -> issue will be removed
            return self.async_create_entry(title="", data={})

        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}))


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Return the appropriate repair flow for an issue."""
    if issue_id == "outdated_config":
        return OutdatedConfigRepairFlow()
    # Fallback: simple confirm flow for any other known/legacy issue IDs
    return OutdatedConfigRepairFlow()


def raise_outdated_config_issue(hass: HomeAssistant) -> None:
    """Create a fixable issue that offers the above repair flow."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "outdated_config",
        is_fixable=True,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="outdated_config",
    )
