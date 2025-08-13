from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import IssueSeverity, async_delete_issue, async_create_issue
DOMAIN = "pawcontrol"
async def ensure_repairs(hass: HomeAssistant) -> None:
    async_create_issue(
        hass, DOMAIN, "review_configuration",
        is_fixable=False, severity=IssueSeverity.warning,
        translation_key="review_configuration",
    )
async def clear_issue(hass: HomeAssistant, issue_id: str) -> None:
    async_delete_issue(hass, DOMAIN, issue_id)
