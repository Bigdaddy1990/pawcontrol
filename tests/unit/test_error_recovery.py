"""Tests for error recovery coordinator helpers."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest

from custom_components.pawcontrol.error_recovery import (
    ErrorPattern,
    ErrorRecoveryCoordinator,
    ErrorStats,
    get_error_recovery_coordinator,
    handle_error_with_recovery,
)
from custom_components.pawcontrol.exceptions import (
    AuthenticationError,
    ConfigurationError,
    GPSUnavailableError,
    NetworkError,
)


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


@pytest.mark.asyncio
async def test_async_setup_registers_default_patterns(hass: HomeAssistant) -> None:
    """Setup should register built-in exception patterns with expected flags."""
    coordinator = ErrorRecoveryCoordinator(hass)

    await coordinator.async_setup()

    network_pattern = coordinator._patterns[NetworkError]
    assert network_pattern.retry_strategy is True
    assert network_pattern.circuit_breaker is True
    assert network_pattern.create_repair_issue is True

    config_pattern = coordinator._patterns[ConfigurationError]
    assert config_pattern.retry_strategy is False
    assert config_pattern.severity == "critical"

    gps_pattern = coordinator._patterns[GPSUnavailableError]
    assert gps_pattern.create_repair_issue is False
    assert gps_pattern.severity == "low"


@pytest.mark.asyncio
async def test_handle_error_without_matching_pattern_tracks_unrecovered(
    hass: HomeAssistant,
) -> None:
    """Unknown errors should be recorded as unrecovered when no fallback exists."""
    coordinator = ErrorRecoveryCoordinator(hass)

    result = await coordinator.handle_error(ValueError("bad input"))

    assert result == {
        "error_type": "ValueError",
        "error_message": "bad input",
        "recovered": False,
        "recovery_method": None,
        "fallback_used": False,
        "repair_issue_created": False,
    }
    stats = coordinator.get_stats()["ValueError"]
    assert stats.total_count == 1
    assert stats.unrecovered_count == 1


@pytest.mark.asyncio
async def test_create_repair_issue_uses_fallback_severity_for_unknown_levels(
    hass: HomeAssistant,
) -> None:
    """Unexpected severity labels should default to an error-level repair issue."""
    coordinator = ErrorRecoveryCoordinator(hass)
    pattern = ErrorPattern(
        exception_type=NetworkError,
        create_repair_issue=True,
        severity="unexpected",
    )

    with patch(
        "custom_components.pawcontrol.error_recovery.ir.async_create_issue"
    ) as issue:
        await coordinator._create_repair_issue(
            NetworkError("offline"),
            pattern,
            {"host": "dog-collar"},
        )

    assert issue.call_args.kwargs["severity"] is ir.IssueSeverity.ERROR


def test_reset_stats_clears_collected_metrics(hass: HomeAssistant) -> None:
    """Reset helper should remove accumulated stats entries."""
    coordinator = ErrorRecoveryCoordinator(hass)
    coordinator._stats["NetworkError"] = ErrorStats(
        exception_type="NetworkError",
        total_count=2,
    )

    coordinator.reset_stats()

    assert coordinator.get_stats() == {}
