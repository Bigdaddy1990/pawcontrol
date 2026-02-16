"""Tests for PawControl repairs flow routing."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.helpers import issue_registry as ir
import pytest

from custom_components.pawcontrol import repairs


@pytest.mark.asyncio
async def test_repairs_flow_routes_notification_auth_error(
  hass,
) -> None:
  """Ensure notification auth error routes to the correct flow step."""  # noqa: E111

  issue_id = "entry_notification_auth_error"  # noqa: E111
  issue_data = {  # noqa: E111
    "config_entry_id": "entry",
    "issue_type": repairs.ISSUE_NOTIFICATION_AUTH_ERROR,
    "services": "notify.mobile_app_phone",
    "service_count": 2,
    "total_failures": 3,
    "consecutive_failures": 2,
    "last_error_reasons": "unauthorized",
  }

  hass.data[ir.DOMAIN] = {issue_id: SimpleNamespace(data=issue_data)}  # noqa: E111

  flow = repairs.PawControlRepairsFlow()  # noqa: E111
  flow.hass = hass  # noqa: E111
  flow.issue_id = issue_id  # noqa: E111

  result = await flow.async_step_init()  # noqa: E111

  assert result["type"] == "form"  # noqa: E111
  assert result["step_id"] == "notification_auth_error"  # noqa: E111
  assert result["description_placeholders"]["service_count"] == 2  # noqa: E111
