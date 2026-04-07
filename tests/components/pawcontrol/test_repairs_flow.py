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
    monkeypatch.setattr(
        repairs,
        "signature",
        lambda _fn: (_ for _ in ()).throw(TypeError),
    )
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

    assert recorded_calls, (
        "Issue registry should be called even when it returns sync data"
    )
    kwargs = recorded_calls[0][1]
    assert kwargs["severity"] == ir.IssueSeverity.WARNING
    assert kwargs["translation_key"] == repairs.ISSUE_NOTIFICATION_TIMEOUT
    assert (
        kwargs["translation_placeholders"]["errors"] == "timeout, service=notify.mobile"
    )


@pytest.mark.asyncio
async def test_notification_delivery_errors_aggregate_and_cleanup(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recurring delivery errors should aggregate by class and clear old issues."""
    entry = SimpleNamespace(entry_id="entry-1")
    services = {
        "notify.mobile_a": {
            "total_failures": "4",
            "consecutive_failures": 3,
            "last_error_reason": "unauthorized",
        },
        "notify.mobile_b": {
            "total_failures": 8,
            "consecutive_failures": 5,
            "last_error": "Connection timed out",
        },
        "notify.mobile_ignored": {
            "total_failures": 10,
            "consecutive_failures": 2,
            "last_error_reason": "unauthorized",
        },
    }
    runtime_data = SimpleNamespace(
        notification_manager=SimpleNamespace(
            get_delivery_status_snapshot=lambda: {"services": services},
        )
    )
    monkeypatch.setattr(
        repairs, "require_runtime_data", lambda _hass, _entry: runtime_data
    )

    created: list[tuple[str, str, dict[str, object], ir.IssueSeverity]] = []

    async def _fake_create_issue(
        _hass,
        _entry,
        issue_id: str,
        issue_type: str,
        data: dict[str, object] | None = None,
        severity: ir.IssueSeverity = ir.IssueSeverity.WARNING,
        *,
        learn_more_url: str | None = None,
    ) -> None:
        del learn_more_url
        created.append((issue_id, issue_type, data or {}, severity))

    deleted = AsyncMock()
    monkeypatch.setattr(repairs, "async_create_issue", _fake_create_issue)
    monkeypatch.setattr(repairs.ir, "async_delete_issue", deleted)

    await repairs._check_notification_delivery_errors(hass, entry)

    created_by_id = {
        issue_id: (issue_type, data, severity)
        for issue_id, issue_type, data, severity in created
    }
    summary = created_by_id[f"{entry.entry_id}_notification_delivery_repeated"][1]
    assert summary["service_count"] == 2
    assert summary["services"] == "notify.mobile_a, notify.mobile_b"

    auth_issue = created_by_id[f"{entry.entry_id}_notification_auth_error"][1]
    assert auth_issue["service_count"] == 1
    assert auth_issue["last_error_reasons"] == "unauthorized"

    timeout_issue = created_by_id[f"{entry.entry_id}_notification_timeout"][1]
    assert timeout_issue["total_failures"] == 8

    deleted_issue_ids = {call.args[2] for call in deleted.await_args_list}
    assert f"{entry.entry_id}_notification_missing_service" in deleted_issue_ids


@pytest.mark.asyncio
async def test_notification_delivery_errors_with_broken_inputs_produce_only_cleanup(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed snapshots should not create issues and should request cleanup."""
    entry = SimpleNamespace(entry_id="entry-2")
    runtime_data = SimpleNamespace(
        notification_manager=SimpleNamespace(
            get_delivery_status_snapshot=lambda: {"services": "bad"},
        )
    )
    monkeypatch.setattr(
        repairs, "require_runtime_data", lambda _hass, _entry: runtime_data
    )

    created = AsyncMock()
    deleted = AsyncMock()
    monkeypatch.setattr(repairs, "async_create_issue", created)
    monkeypatch.setattr(repairs.ir, "async_delete_issue", deleted)

    await repairs._check_notification_delivery_errors(hass, entry)

    created.assert_not_called()
    assert deleted.await_count >= 1
