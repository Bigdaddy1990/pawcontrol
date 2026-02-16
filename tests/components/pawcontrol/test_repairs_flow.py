"""Tests for PawControl repairs flow routing."""


from types import SimpleNamespace

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.pawcontrol import repairs


@pytest.mark.asyncio
async def test_repairs_flow_routes_notification_auth_error(
    hass,
) -> None:
    """Ensure notification auth error routes to the correct flow step."""

    issue_id = "entry_notification_auth_error"
    issue_data = {
        "config_entry_id": "entry",
        "issue_type": repairs.ISSUE_NOTIFICATION_AUTH_ERROR,
        "services": "notify.mobile_app_phone",
        "service_count": 2,
        "total_failures": 3,
        "consecutive_failures": 2,
        "last_error_reasons": "unauthorized",
    }

    hass.data[ir.DOMAIN] = {issue_id: SimpleNamespace(data=issue_data)}

    flow = repairs.PawControlRepairsFlow()
    flow.hass = hass
    flow.issue_id = issue_id

    result = await flow.async_step_init()

    assert result["type"] == "form"
    assert result["step_id"] == "notification_auth_error"
    assert result["description_placeholders"]["service_count"] == 2
