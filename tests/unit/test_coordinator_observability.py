"""Unit tests for coordinator observability helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import Any

import pytest
from custom_components.pawcontrol.coordinator_observability import (
    EntityBudgetTracker,
    build_performance_snapshot,
    build_security_scorecard,
    normalise_webhook_status,
)
from custom_components.pawcontrol.coordinator_runtime import EntityBudgetSnapshot
from custom_components.pawcontrol.coordinator_support import CoordinatorMetrics


@pytest.mark.unit
def test_entity_budget_tracker_records_and_summarises() -> None:
    tracker = EntityBudgetTracker()
    now = datetime.now(UTC)
    tracker.record(
        EntityBudgetSnapshot(
            dog_id="a",
            profile="standard",
            capacity=8,
            base_allocation=3,
            dynamic_allocation=2,
            requested_entities=("sensor.one",),
            denied_requests=(),
            recorded_at=now,
        )
    )
    tracker.record(
        EntityBudgetSnapshot(
            dog_id="b",
            profile="athlete",
            capacity=4,
            base_allocation=4,
            dynamic_allocation=0,
            requested_entities=(),
            denied_requests=("sensor.two",),
            recorded_at=now,
        )
    )

    summary = tracker.summary()

    assert summary["active_dogs"] == 2
    assert summary["denied_requests"] == 1
    assert 0.0 <= tracker.saturation() <= 1.0


@pytest.mark.unit
def test_build_performance_snapshot_includes_metrics() -> None:
    metrics = CoordinatorMetrics(update_count=3, failed_cycles=1, consecutive_errors=0)
    adaptive = {"current_interval_ms": 120.0, "target_cycle_ms": 180.0}
    entity_budget = {"active_dogs": 1}
    webhook_status = {"configured": False, "secure": True, "hmac_ready": False}

    resilience_summary = {
        "total_breakers": 2,
        "states": {
            "closed": 1,
            "open": 1,
            "half_open": 0,
            "unknown": 0,
            "other": 0,
        },
        "failure_count": 4,
        "success_count": 6,
        "total_calls": 10,
        "total_failures": 4,
        "total_successes": 6,
        "last_failure_time": 1700000000.0,
        "last_state_change": 1700000100.0,
        "last_success_time": 1700000200.0,
        "recovery_latency": 200.0,
        "recovery_breaker_id": "api",
        "recovery_breaker_name": "api",
        "open_breakers": ["api"],
        "open_breaker_count": 1,
        "open_breaker_ids": ["api"],
        "half_open_breaker_count": 0,
        "unknown_breaker_count": 0,
    }

    snapshot = build_performance_snapshot(
        metrics=metrics,
        adaptive=adaptive,
        entity_budget=entity_budget,
        update_interval=2.5,
        last_update_time=datetime(2024, 1, 1, 0, 0, 0),
        last_update_success=True,
        webhook_status=webhook_status,
        resilience=resilience_summary,
    )

    assert snapshot["update_counts"]["total"] == 3
    assert snapshot["performance_metrics"]["update_interval_s"] == 2.5
    assert snapshot["adaptive_polling"]["current_interval_ms"] == 120.0
    assert snapshot["webhook_security"]["secure"] is True
    resilience = snapshot["resilience_summary"]
    assert resilience["total_breakers"] == 2
    assert resilience["open_breaker_count"] == 1
    assert resilience["last_success_time"] == 1700000200.0
    assert resilience["recovery_latency"] == 200.0
    assert resilience["recovery_breaker_id"] == "api"
    assert resilience["recovery_breaker_name"] == "api"
    assert resilience["open_breaker_ids"] == ["api"]
    assert resilience["unknown_breaker_count"] == 0
    assert resilience["unknown_breakers"] == []
    assert resilience["unknown_breaker_ids"] == []
    assert resilience["half_open_breaker_count"] == 0
    assert resilience["half_open_breakers"] == []
    assert resilience["half_open_breaker_ids"] == []


@pytest.mark.unit
def test_build_security_scorecard_handles_failures() -> None:
    adaptive = {"current_interval_ms": 500.0, "target_cycle_ms": 180.0}
    entity_summary = {"peak_utilization": 99.0}
    webhook_status = {"configured": True, "secure": False, "hmac_ready": False}

    scorecard = build_security_scorecard(
        adaptive=adaptive,
        entity_summary=entity_summary,
        webhook_status=webhook_status,
    )

    assert scorecard["status"] == "fail"
    assert scorecard["checks"]["adaptive_polling"]["pass"] is False
    assert scorecard["checks"]["entity_budget"]["pass"] is False
    assert scorecard["checks"]["webhooks"]["pass"] is False


@pytest.mark.unit
def test_normalise_webhook_status_handles_exception() -> None:
    class BrokenManager:
        @staticmethod
        def webhook_security_status() -> dict[str, Any]:
            raise RuntimeError("boom")

    status = normalise_webhook_status(BrokenManager())

    assert status["configured"] is True
    assert status["secure"] is False
    assert status["error"] == "boom"

    default_status = normalise_webhook_status(None)
    assert default_status["configured"] is False
    assert default_status["secure"] is True
