"""Tests for PawControl repairs flow routing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.helpers import issue_registry as ir
import pytest

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


def test_issue_registry_supports_kwarg_handles_signature_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signature parsing failures should safely report missing keyword support."""
    monkeypatch.setattr(repairs, "signature", lambda _fn: (_ for _ in ()).throw(TypeError))
    assert repairs._issue_registry_supports_kwarg(object(), "learn_more_url") is False


@pytest.mark.asyncio
async def test_async_create_issue_handles_non_awaitable_registry_results(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repair issue creation should tolerate sync registry shims without raising."""
    entry = SimpleNamespace(entry_id="entry-1")
    recorded_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _create_issue(*args: object, **kwargs: object) -> object:
        recorded_calls.append((args, kwargs))
        return "created"

    monkeypatch.setattr(repairs.ir, "async_create_issue", _create_issue)

    await repairs.async_create_issue(
        hass,
        entry,
        issue_id="entry-1_issue",
        issue_type=repairs.ISSUE_NOTIFICATION_TIMEOUT,
        data={"errors": ["timeout", {"service": "notify.mobile"}]},
        severity="NOT_A_REAL_LEVEL",
        learn_more_url="https://example.invalid/repair",
    )

    assert recorded_calls, "Issue registry should be called even when it returns sync data"
    kwargs = recorded_calls[0][1]
    assert kwargs["severity"] == ir.IssueSeverity.WARNING
    assert kwargs["translation_key"] == repairs.ISSUE_NOTIFICATION_TIMEOUT
    assert kwargs["translation_placeholders"]["errors"] == "timeout, service=notify.mobile"
