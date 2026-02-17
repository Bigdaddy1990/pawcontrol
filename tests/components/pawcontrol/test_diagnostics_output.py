"""Tests for PawControl diagnostics payload defaults."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol import diagnostics
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.types import PawControlRuntimeData


@pytest.mark.asyncio
async def test_performance_metrics_defaults_include_rejection_metrics() -> None:
    """Ensure performance diagnostics always include rejection defaults."""  # noqa: E111

    payload = await diagnostics._get_performance_metrics(None)  # noqa: E111

    assert payload["available"] is False  # noqa: E111
    rejection_metrics = payload["rejection_metrics"]  # noqa: E111
    assert rejection_metrics["schema_version"] == 4  # noqa: E111
    assert rejection_metrics["rejected_call_count"] == 0  # noqa: E111


@pytest.mark.asyncio
async def test_notification_diagnostics_include_rejection_defaults() -> None:
    """Ensure notification diagnostics include rejection metrics defaults."""  # noqa: E111

    payload = await diagnostics._get_notification_diagnostics(None)  # noqa: E111

    assert payload["available"] is False  # noqa: E111
    rejection_metrics = payload["rejection_metrics"]  # noqa: E111
    assert rejection_metrics["schema_version"] == 1  # noqa: E111
    assert rejection_metrics["total_failures"] == 0  # noqa: E111


@pytest.mark.asyncio
async def test_service_execution_defaults_include_rejection_metrics() -> None:
    """Ensure service execution diagnostics include default metrics."""  # noqa: E111

    payload = await diagnostics._get_service_execution_diagnostics(None)  # noqa: E111

    assert payload["available"] is False  # noqa: E111
    rejection_metrics = payload["rejection_metrics"]  # noqa: E111
    assert rejection_metrics["schema_version"] == 4  # noqa: E111
    assert rejection_metrics["rejected_call_count"] == 0  # noqa: E111
    guard_metrics = payload["guard_metrics"]  # noqa: E111
    assert guard_metrics["executed"] == 0  # noqa: E111
    assert guard_metrics["skipped"] == 0  # noqa: E111


def _assert_json_safe(value: object) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):  # noqa: E111
        return
    if isinstance(value, (list, tuple)):  # noqa: E111
        for item in value:
            _assert_json_safe(item)  # noqa: E111
        return
    if isinstance(value, dict):  # noqa: E111
        for key, entry in value.items():
            assert isinstance(key, str)  # noqa: E111
            _assert_json_safe(entry)  # noqa: E111
        return
    raise AssertionError(f"Non-JSON value found: {type(value)!r} {value!r}")  # noqa: E111


@dataclass(frozen=True)
class _DiagnosticsDataclass:
    label: str  # noqa: E111
    recorded_at: datetime  # noqa: E111


@pytest.mark.asyncio
async def test_diagnostics_payloads_json_serialisable(
    mock_coordinator,
    mock_dog_config,
) -> None:
    """Ensure diagnostics payloads remain JSON serialisable with runtime data."""  # noqa: E111

    sample_time = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)  # noqa: E111
    sample_delta = timedelta(minutes=15)  # noqa: E111
    sample_payload = _DiagnosticsDataclass("sample", sample_time)  # noqa: E111

    mock_coordinator.get_update_statistics = MagicMock(  # noqa: E111
        return_value={
            "update_counts": {"total": 4, "failed": 1, "successful": 3},
            "performance_metrics": {
                "update_interval": 30,
                "last_update": sample_time,
            },
            "rejection_metrics": {
                "rejected_call_count": 1,
                "last_rejection_time": sample_time,
            },
            "repairs": {"last_run": sample_time},
            "adaptive_polling": {"cooldown": sample_delta},
            "resilience": {"recent_events": {sample_payload}},
        },
    )

    notification_manager = MagicMock()  # noqa: E111
    notification_manager.async_get_performance_statistics = AsyncMock(  # noqa: E111
        return_value={
            "summary": sample_payload,
            "window": sample_delta,
            "tags": {"alpha", "beta"},
        },
    )
    notification_manager.get_delivery_status_snapshot = MagicMock(  # noqa: E111
        return_value={
            "last_delivery": sample_time,
            "recent_failures": {sample_time, sample_delta},
            "services": {
                "email": {
                    "total_failures": 1,
                    "consecutive_failures": 1,
                    "last_error": sample_payload,
                },
            },
        },
    )

    runtime_data = PawControlRuntimeData(  # noqa: E111
        coordinator=mock_coordinator,
        data_manager=MagicMock(),
        notification_manager=notification_manager,
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=EntityFactory(mock_coordinator),
        entity_profile="standard",
        dogs=[mock_dog_config],
    )
    runtime_data.performance_stats = {  # noqa: E111
        "service_guard_metrics": {
            "executed": 3,
            "skipped": 1,
            "reasons": {"blocked": 1},
            "last_results": [
                {
                    "executed": True,
                    "timestamp": sample_time,
                },
            ],
        },
        "service_results": [
            {"service": "test", "executed_at": sample_time},
        ],
        "last_service_result": {
            "service": "test",
            "finished_at": sample_time,
        },
        "service_call_telemetry": {
            "last_success": sample_time,
            "recent_durations": [sample_delta],
        },
    }

    payloads = [  # noqa: E111
        await diagnostics._get_performance_metrics(mock_coordinator),
        await diagnostics._get_notification_diagnostics(runtime_data),
        await diagnostics._get_service_execution_diagnostics(runtime_data),
    ]

    for payload in payloads:  # noqa: E111
        json.dumps(payload)
        _assert_json_safe(payload)
