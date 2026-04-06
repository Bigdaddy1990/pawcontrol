"""Additional coverage tests for ``error_recovery`` runtime paths."""

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
from custom_components.pawcontrol.exceptions import AuthenticationError, NetworkError


@pytest.mark.asyncio
async def test_handle_error_with_recovery_action_marks_recovered(
    hass: HomeAssistant,
) -> None:
    """Recovery actions should mark the error as recovered."""
    coordinator = ErrorRecoveryCoordinator(hass)
    recovery_action = AsyncMock(return_value={"cache": "ok"})
    coordinator.register_pattern(
        ErrorPattern(
            exception_type=AuthenticationError,
            recovery_action=recovery_action,
            create_repair_issue=True,
            severity="critical",
        )
    )

    with patch(
        "custom_components.pawcontrol.error_recovery.ir.async_create_issue"
    ) as create_issue:
        result = await coordinator.handle_error(
            AuthenticationError("token expired"),
            context={"stage": "login"},
        )

    assert result["recovered"] is True
    assert result["recovery_method"] == "recovery_action"
    assert result["repair_issue_created"] is True
    create_issue.assert_called_once()

    stats = coordinator.get_stats()["AuthenticationError"]
    assert stats.total_count == 1
    assert stats.recovery_count == 1
    assert stats.unrecovered_count == 0


@pytest.mark.asyncio
async def test_handle_error_with_failed_recovery_uses_fallback(
    hass: HomeAssistant,
) -> None:
    """Failing recovery action should keep unrecovered and use fallback value."""
    coordinator = ErrorRecoveryCoordinator(hass)
    coordinator.register_pattern(
        ErrorPattern(
            exception_type=NetworkError,
            recovery_action=AsyncMock(side_effect=RuntimeError("boom")),
        )
    )

    result = await coordinator.handle_error(
        NetworkError("offline"),
        fallback_value={"from": "cache"},
    )

    assert result["recovered"] is False
    assert result["fallback_used"] is True
    assert result["fallback_value"] == {"from": "cache"}

    stats = coordinator.get_stats()["NetworkError"]
    assert stats.total_count == 1
    assert stats.unrecovered_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("low", ir.IssueSeverity.WARNING),
        ("medium", ir.IssueSeverity.WARNING),
        ("high", ir.IssueSeverity.ERROR),
        ("critical", ir.IssueSeverity.CRITICAL),
        ("unknown", ir.IssueSeverity.ERROR),
    ],
)
async def test_create_repair_issue_severity_mapping(
    hass: HomeAssistant,
    severity: str,
    expected: ir.IssueSeverity,
) -> None:
    """Issue creation should map known severities and fallback for unknown values."""
    coordinator = ErrorRecoveryCoordinator(hass)
    pattern = ErrorPattern(
        exception_type=NetworkError,
        create_repair_issue=True,
        severity=severity,
    )

    with patch(
        "custom_components.pawcontrol.error_recovery.ir.async_create_issue"
    ) as create_issue:
        await coordinator._create_repair_issue(
            NetworkError("down"), pattern, {"dog": "rex"}
        )

    kwargs = create_issue.call_args.kwargs
    assert kwargs["severity"] is expected
    assert kwargs["translation_key"] == "networkerror"


@pytest.mark.asyncio
async def test_handle_error_with_recovery_helper_and_summary(
    hass: HomeAssistant,
) -> None:
    """Global helper should route through singleton and update summary values."""
    with patch(
        "custom_components.pawcontrol.error_recovery._error_recovery_coordinator",
        None,
    ):
        coordinator = get_error_recovery_coordinator(hass)
        assert coordinator is get_error_recovery_coordinator(hass)

        result = await handle_error_with_recovery(
            hass,
            RuntimeError("boom"),
            fallback_value=123,
        )

    assert result["fallback_used"] is True
    summary = coordinator.get_recovery_summary()
    assert summary["total_errors"] == 1
    assert summary["total_recovered"] == 0
    assert summary["total_unrecovered"] == 1
    assert summary["error_types"] == 1


@pytest.mark.asyncio
async def test_async_setup_registers_defaults_and_reset_stats(
    hass: HomeAssistant,
) -> None:
    """Setup should register defaults and reset should clear collected stats."""
    coordinator = ErrorRecoveryCoordinator(hass)
    await coordinator.async_setup()

    assert AuthenticationError in coordinator._patterns
    assert NetworkError in coordinator._patterns

    coordinator._stats["NetworkError"] = ErrorStats(
        exception_type="NetworkError",
        total_count=3,
        unrecovered_count=2,
    )

    coordinator.reset_stats()
    assert coordinator.get_stats() == {}
