"""Tests for error recovery coordinator helpers."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol.error_recovery import (
    ErrorPattern,
    ErrorRecoveryCoordinator,
    ErrorStats,
    get_error_recovery_coordinator,
    handle_error_with_recovery,
)
from custom_components.pawcontrol.exceptions import AuthenticationError, NetworkError


@pytest.mark.asyncio
async def test_handle_error_recovers_with_action_and_creates_issue(
    hass: HomeAssistant,
) -> None:
    """Coordinator should run recovery action and create repair issue."""
    coordinator = ErrorRecoveryCoordinator(hass)
    await coordinator.async_setup()

    recovery_action = AsyncMock(return_value={"ok": True})
    coordinator.register_pattern(
        ErrorPattern(
            exception_type=AuthenticationError,
            create_repair_issue=True,
            recovery_action=recovery_action,
        )
    )

    with patch(
        "custom_components.pawcontrol.error_recovery.ir.async_create_issue"
    ) as issue:
        result = await coordinator.handle_error(
            AuthenticationError("invalid token"),
            context={"step": "auth"},
        )

    assert result["recovered"] is True
    assert result["recovery_method"] == "recovery_action"
    assert result["repair_issue_created"] is True
    assert result["fallback_used"] is False
    issue.assert_called_once()

    stats = coordinator.get_stats()["AuthenticationError"]
    assert stats.total_count == 1
    assert stats.recovery_count == 1
    assert stats.unrecovered_count == 0
    assert stats.repair_issues_created == 1


@pytest.mark.asyncio
async def test_handle_error_recovery_action_failure_uses_fallback(
    hass: HomeAssistant,
) -> None:
    """Coordinator should report fallback when recovery action fails."""
    coordinator = ErrorRecoveryCoordinator(hass)
    coordinator.register_pattern(
        ErrorPattern(
            exception_type=NetworkError,
            recovery_action=AsyncMock(side_effect=RuntimeError("boom")),
        )
    )

    result = await coordinator.handle_error(
        NetworkError("down"),
        fallback_value={"cached": True},
    )

    assert result["recovered"] is False
    assert result["fallback_used"] is True
    assert result["fallback_value"] == {"cached": True}

    stats = coordinator.get_stats()["NetworkError"]
    assert stats.total_count == 1
    # One count when action fails + one in final unrecovered branch.
    assert stats.unrecovered_count == 2


@pytest.mark.asyncio
async def test_create_repair_issue_failure_is_handled(hass: HomeAssistant) -> None:
    """Issue registry failures must not propagate."""
    coordinator = ErrorRecoveryCoordinator(hass)

    pattern = ErrorPattern(exception_type=NetworkError, create_repair_issue=True)
    with patch(
        "custom_components.pawcontrol.error_recovery.ir.async_create_issue",
        side_effect=RuntimeError("registry unavailable"),
    ):
        await coordinator._create_repair_issue(NetworkError("down"), pattern, None)


def test_error_stats_to_dict_and_rate() -> None:
    """ErrorStats should serialize and compute rates."""
    empty = ErrorStats(exception_type="NetworkError")
    assert empty.recovery_rate == 0.0
    assert empty.to_dict()["last_occurrence"] is None

    now = datetime.now()
    populated = ErrorStats(
        exception_type="NetworkError",
        recovery_count=3,
        unrecovered_count=1,
        last_occurrence=now,
    )
    as_dict = populated.to_dict()
    assert populated.recovery_rate == 0.75
    assert as_dict["recovery_rate"] == 0.75
    assert as_dict["last_occurrence"] == now.isoformat()


@pytest.mark.asyncio
async def test_recovery_summary_and_singleton_helper(hass: HomeAssistant) -> None:
    """Summary values and module singleton should be stable."""
    with patch(
        "custom_components.pawcontrol.error_recovery._error_recovery_coordinator", None
    ):
        first = get_error_recovery_coordinator(hass)
        second = get_error_recovery_coordinator(hass)
        assert first is second

    coordinator = ErrorRecoveryCoordinator(hass)
    await coordinator.handle_error(NetworkError("down"))
    summary = coordinator.get_recovery_summary()

    assert summary["total_errors"] == 1
    assert summary["total_unrecovered"] == 1
    assert summary["recovery_rate"] == 0.0
    assert summary["error_types"] == 1
    assert len(summary["most_common"]) == 1

    helper_result = await handle_error_with_recovery(
        hass,
        NetworkError("still down"),
        fallback_value=42,
    )
    assert helper_result["fallback_used"] is True
