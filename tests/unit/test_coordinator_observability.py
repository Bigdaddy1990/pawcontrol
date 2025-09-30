"""Unit tests for coordinator observability helpers."""

from __future__ import annotations

from datetime import datetime
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
    now = datetime.utcnow()
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

    snapshot = build_performance_snapshot(
        metrics=metrics,
        adaptive=adaptive,
        entity_budget=entity_budget,
        update_interval=2.5,
        last_update_time=datetime(2024, 1, 1, 0, 0, 0),
        last_update_success=True,
        webhook_status=webhook_status,
    )

    assert snapshot["update_counts"]["total"] == 3
    assert snapshot["performance_metrics"]["update_interval_s"] == 2.5
    assert snapshot["adaptive_polling"]["current_interval_ms"] == 120.0
    assert snapshot["webhook_security"]["secure"] is True


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
