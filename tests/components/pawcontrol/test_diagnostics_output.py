"""Tests for PawControl diagnostics payload defaults."""
from __future__ import annotations


import json
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import UTC
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol import diagnostics
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.types import PawControlRuntimeData


@pytest.mark.asyncio
async def test_performance_metrics_defaults_include_rejection_metrics() -> None:
    """Ensure performance diagnostics always include rejection defaults."""

    payload = await diagnostics._get_performance_metrics(None)

    assert payload["available"] is False
    rejection_metrics = payload["rejection_metrics"]
    assert rejection_metrics["schema_version"] == 4
    assert rejection_metrics["rejected_call_count"] == 0


@pytest.mark.asyncio
async def test_notification_diagnostics_include_rejection_defaults() -> None:
    """Ensure notification diagnostics include rejection metrics defaults."""

    payload = await diagnostics._get_notification_diagnostics(None)

    assert payload["available"] is False
    rejection_metrics = payload["rejection_metrics"]
    assert rejection_metrics["schema_version"] == 1
    assert rejection_metrics["total_failures"] == 0


@pytest.mark.asyncio
async def test_service_execution_defaults_include_rejection_metrics() -> None:
    """Ensure service execution diagnostics include default metrics."""

    payload = await diagnostics._get_service_execution_diagnostics(None)

    assert payload["available"] is False
    rejection_metrics = payload["rejection_metrics"]
    assert rejection_metrics["schema_version"] == 4
    assert rejection_metrics["rejected_call_count"] == 0
    guard_metrics = payload["guard_metrics"]
    assert guard_metrics["executed"] == 0
    assert guard_metrics["skipped"] == 0


def _assert_json_safe(value: object) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_json_safe(item)
        return
    if isinstance(value, dict):
        for key, entry in value.items():
            assert isinstance(key, str)
            _assert_json_safe(entry)
        return
    raise AssertionError(f"Non-JSON value found: {type(value)!r} {value!r}")


@dataclass(frozen=True)
class _DiagnosticsDataclass:
    label: str
    recorded_at: datetime


@pytest.mark.asyncio
async def test_diagnostics_payloads_json_serialisable(
    mock_coordinator,
    mock_dog_config,
) -> None:
    """Ensure diagnostics payloads remain JSON serialisable with runtime data."""

    sample_time = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    sample_delta = timedelta(minutes=15)
    sample_payload = _DiagnosticsDataclass("sample", sample_time)

    mock_coordinator.get_update_statistics = MagicMock(
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

    notification_manager = MagicMock()
    notification_manager.async_get_performance_statistics = AsyncMock(
        return_value={
            "summary": sample_payload,
            "window": sample_delta,
            "tags": {"alpha", "beta"},
        },
    )
    notification_manager.get_delivery_status_snapshot = MagicMock(
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

    runtime_data = PawControlRuntimeData(
        coordinator=mock_coordinator,
        data_manager=MagicMock(),
        notification_manager=notification_manager,
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=EntityFactory(mock_coordinator),
        entity_profile="standard",
        dogs=[mock_dog_config],
    )
    runtime_data.performance_stats = {
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

    payloads = [
        await diagnostics._get_performance_metrics(mock_coordinator),
        await diagnostics._get_notification_diagnostics(runtime_data),
        await diagnostics._get_service_execution_diagnostics(runtime_data),
    ]

    for payload in payloads:
        json.dumps(payload)
        _assert_json_safe(payload)
