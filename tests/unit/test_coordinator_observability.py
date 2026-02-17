"""Unit tests for coordinator observability helpers."""

from datetime import UTC, datetime, timezone
from typing import Any, cast

import pytest

from custom_components.pawcontrol.coordinator_observability import (
    EntityBudgetTracker,
    build_performance_snapshot,
    build_security_scorecard,
    normalise_webhook_status,
)
from custom_components.pawcontrol.coordinator_runtime import EntityBudgetSnapshot
from custom_components.pawcontrol.coordinator_support import CoordinatorMetrics
from custom_components.pawcontrol.telemetry import (
    record_bool_coercion_event,
    reset_bool_coercion_metrics,
)
from custom_components.pawcontrol.types import (
    AdaptivePollingDiagnostics,
    CoordinatorPerformanceSnapshot,
    CoordinatorResilienceSummary,
    CoordinatorSecurityScorecard,
    EntityBudgetSummary,
    WebhookSecurityStatus,
)


@pytest.mark.unit
def test_entity_budget_tracker_records_and_summarises() -> None:
    tracker = EntityBudgetTracker()  # noqa: E111
    now = datetime.now(UTC)  # noqa: E111
    tracker.record(  # noqa: E111
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
    tracker.record(  # noqa: E111
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

    summary = tracker.summary()  # noqa: E111

    assert summary["active_dogs"] == 2  # noqa: E111
    assert summary["denied_requests"] == 1  # noqa: E111
    assert 0.0 <= tracker.saturation() <= 1.0  # noqa: E111


@pytest.mark.unit
def test_build_performance_snapshot_includes_metrics() -> None:
    metrics = CoordinatorMetrics(update_count=3, failed_cycles=1, consecutive_errors=0)  # noqa: E111
    adaptive: AdaptivePollingDiagnostics = {  # noqa: E111
        "current_interval_ms": 120.0,
        "target_cycle_ms": 180.0,
        "average_cycle_ms": 0.0,
        "history_samples": 0,
        "error_streak": 0,
        "entity_saturation": 0.0,
        "idle_interval_ms": 0.0,
        "idle_grace_ms": 0.0,
    }
    entity_budget: EntityBudgetSummary = {  # noqa: E111
        "active_dogs": 1,
        "total_capacity": 0,
        "total_allocated": 0,
        "total_remaining": 0,
        "average_utilization": 0.0,
        "peak_utilization": 0.0,
        "denied_requests": 0,
    }
    webhook_status: WebhookSecurityStatus = {  # noqa: E111
        "configured": False,
        "secure": True,
        "hmac_ready": False,
        "insecure_configs": (),
    }

    resilience_summary: CoordinatorResilienceSummary = {  # noqa: E111
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
        "rejected_call_count": 3,
        "last_failure_time": 1700000000.0,
        "last_state_change": 1700000100.0,
        "last_success_time": 1700000200.0,
        "last_rejection_time": 1700000250.0,
        "recovery_latency": 200.0,
        "recovery_breaker_id": "api",
        "recovery_breaker_name": "api",
        "last_rejection_breaker_id": "web",
        "last_rejection_breaker_name": "web",
        "rejection_rate": 0.3,
        "open_breakers": ["api"],
        "open_breaker_count": 1,
        "open_breaker_ids": ["api"],
        "half_open_breaker_count": 0,
        "unknown_breaker_count": 0,
        "rejection_breaker_count": 1,
        "rejection_breakers": ["api"],
        "rejection_breaker_ids": ["api"],
    }

    reset_bool_coercion_metrics()  # noqa: E111
    record_bool_coercion_event(  # noqa: E111
        value="yes",
        default=False,
        result=True,
        reason="truthy_string",
    )

    try:  # noqa: E111
        snapshot: CoordinatorPerformanceSnapshot = build_performance_snapshot(
            metrics=metrics,
            adaptive=adaptive,
            entity_budget=entity_budget,
            update_interval=2.5,
            last_update_time=datetime(2024, 1, 1, 0, 0, 0),
            last_update_success=True,
            webhook_status=webhook_status,
            resilience=resilience_summary,
        )
    finally:  # noqa: E111
        reset_bool_coercion_metrics()

    assert snapshot["update_counts"]["total"] == 3  # noqa: E111
    assert snapshot["performance_metrics"]["update_interval_s"] == 2.5  # noqa: E111
    assert snapshot["adaptive_polling"]["current_interval_ms"] == 120.0  # noqa: E111
    assert snapshot["webhook_security"]["secure"] is True  # noqa: E111
    performance_metrics = snapshot["performance_metrics"]  # noqa: E111
    assert performance_metrics["rejected_call_count"] == 3  # noqa: E111
    assert performance_metrics["rejection_breaker_count"] == 1  # noqa: E111
    assert performance_metrics["rejection_rate"] == 0.3  # noqa: E111
    assert performance_metrics["last_rejection_time"] == 1700000250.0  # noqa: E111
    assert performance_metrics["last_rejection_breaker_id"] == "web"  # noqa: E111
    assert performance_metrics["last_rejection_breaker_name"] == "web"  # noqa: E111
    assert performance_metrics["open_breakers"] == ["api"]  # noqa: E111
    assert performance_metrics["open_breaker_ids"] == ["api"]  # noqa: E111
    assert performance_metrics["half_open_breakers"] == []  # noqa: E111
    assert performance_metrics["half_open_breaker_ids"] == []  # noqa: E111
    assert performance_metrics["unknown_breakers"] == []  # noqa: E111
    assert performance_metrics["unknown_breaker_ids"] == []  # noqa: E111
    assert performance_metrics["rejection_breaker_ids"] == ["api"]  # noqa: E111
    assert performance_metrics["rejection_breakers"] == ["api"]  # noqa: E111
    assert "schema_version" not in performance_metrics  # noqa: E111
    resilience = snapshot["resilience_summary"]  # noqa: E111
    assert resilience["total_breakers"] == 2  # noqa: E111
    assert resilience["open_breaker_count"] == 1  # noqa: E111
    assert resilience["last_success_time"] == 1700000200.0  # noqa: E111
    assert resilience["recovery_latency"] == 200.0  # noqa: E111
    assert resilience["recovery_breaker_id"] == "api"  # noqa: E111
    assert resilience["recovery_breaker_name"] == "api"  # noqa: E111
    assert resilience["open_breakers"] == ["api"]  # noqa: E111
    assert resilience["open_breaker_ids"] == ["api"]  # noqa: E111
    assert resilience["unknown_breaker_count"] == 0  # noqa: E111
    assert resilience["unknown_breakers"] == []  # noqa: E111
    assert resilience["unknown_breaker_ids"] == []  # noqa: E111
    assert resilience["half_open_breaker_count"] == 0  # noqa: E111
    assert resilience["half_open_breakers"] == []  # noqa: E111
    assert resilience["half_open_breaker_ids"] == []  # noqa: E111
    assert resilience["rejected_call_count"] == 3  # noqa: E111
    assert resilience["last_rejection_time"] == 1700000250.0  # noqa: E111
    assert resilience["last_rejection_breaker_id"] == "web"  # noqa: E111
    assert resilience["rejection_breaker_ids"] == ["api"]  # noqa: E111
    assert resilience["rejection_breakers"] == ["api"]  # noqa: E111
    assert resilience["rejection_breaker_count"] == 1  # noqa: E111
    assert resilience["rejection_rate"] == 0.3  # noqa: E111
    rejection_metrics = snapshot["rejection_metrics"]  # noqa: E111
    assert rejection_metrics["schema_version"] == 4  # noqa: E111
    assert rejection_metrics["rejected_call_count"] == 3  # noqa: E111
    assert rejection_metrics["rejection_breaker_count"] == 1  # noqa: E111
    assert rejection_metrics["rejection_rate"] == 0.3  # noqa: E111
    assert rejection_metrics["last_rejection_time"] == 1700000250.0  # noqa: E111
    assert rejection_metrics["last_rejection_breaker_id"] == "web"  # noqa: E111
    assert rejection_metrics["last_rejection_breaker_name"] == "web"  # noqa: E111
    assert rejection_metrics["open_breaker_count"] == 1  # noqa: E111
    assert rejection_metrics["half_open_breaker_count"] == 0  # noqa: E111
    assert rejection_metrics["unknown_breaker_count"] == 0  # noqa: E111
    assert rejection_metrics["open_breakers"] == ["api"]  # noqa: E111
    assert rejection_metrics["open_breaker_ids"] == ["api"]  # noqa: E111
    assert rejection_metrics["half_open_breakers"] == []  # noqa: E111
    assert rejection_metrics["half_open_breaker_ids"] == []  # noqa: E111
    assert rejection_metrics["unknown_breakers"] == []  # noqa: E111
    assert rejection_metrics["unknown_breaker_ids"] == []  # noqa: E111
    assert rejection_metrics["rejection_breaker_ids"] == ["api"]  # noqa: E111
    assert rejection_metrics["rejection_breakers"] == ["api"]  # noqa: E111

    bool_summary = snapshot["bool_coercion"]  # noqa: E111
    assert bool_summary["recorded"] is True  # noqa: E111
    assert bool_summary["total"] == 1  # noqa: E111
    assert bool_summary["reason_counts"]["truthy_string"] == 1  # noqa: E111
    assert bool_summary["last_reason"] == "truthy_string"  # noqa: E111
    assert bool_summary["last_result"] is True  # noqa: E111
    assert bool_summary["last_default"] is False  # noqa: E111
    assert bool_summary["samples"]  # noqa: E111
    assert bool_summary["samples"][0]["reason"] == "truthy_string"  # noqa: E111


@pytest.mark.unit
def test_build_performance_snapshot_defaults_rejection_metrics() -> None:
    metrics = CoordinatorMetrics(update_count=2, failed_cycles=0, consecutive_errors=0)  # noqa: E111
    adaptive = cast(  # noqa: E111
        AdaptivePollingDiagnostics,
        {
            "current_interval_ms": 90.0,
            "target_cycle_ms": 180.0,
            "average_cycle_ms": 0.0,
            "history_samples": 0,
            "error_streak": 0,
            "entity_saturation": 0.0,
            "idle_interval_ms": 0.0,
            "idle_grace_ms": 0.0,
        },
    )
    entity_budget = cast(  # noqa: E111
        EntityBudgetSummary,
        {
            "active_dogs": 1,
            "total_capacity": 0,
            "total_allocated": 0,
            "total_remaining": 0,
            "average_utilization": 0.0,
            "peak_utilization": 0.0,
            "denied_requests": 0,
        },
    )
    webhook_status = cast(  # noqa: E111
        WebhookSecurityStatus,
        {
            "configured": True,
            "secure": True,
            "hmac_ready": True,
            "insecure_configs": (),
        },
    )

    reset_bool_coercion_metrics()  # noqa: E111
    try:  # noqa: E111
        snapshot = build_performance_snapshot(
            metrics=metrics,
            adaptive=adaptive,
            entity_budget=entity_budget,
            update_interval=2.0,
            last_update_time=datetime(2024, 1, 2, 0, 0, tzinfo=UTC),
            last_update_success=True,
            webhook_status=webhook_status,
            resilience=None,
        )
    finally:  # noqa: E111
        reset_bool_coercion_metrics()

    rejection_metrics = snapshot["rejection_metrics"]  # noqa: E111
    assert rejection_metrics["schema_version"] == 4  # noqa: E111
    assert rejection_metrics["rejected_call_count"] == 0  # noqa: E111
    assert rejection_metrics["rejection_breaker_count"] == 0  # noqa: E111
    assert rejection_metrics["rejection_rate"] == 0.0  # noqa: E111
    assert rejection_metrics["last_rejection_time"] is None  # noqa: E111
    assert rejection_metrics["last_rejection_breaker_id"] is None  # noqa: E111
    assert rejection_metrics["last_rejection_breaker_name"] is None  # noqa: E111
    assert rejection_metrics["open_breaker_count"] == 0  # noqa: E111
    assert rejection_metrics["half_open_breaker_count"] == 0  # noqa: E111
    assert rejection_metrics["unknown_breaker_count"] == 0  # noqa: E111
    assert rejection_metrics["open_breakers"] == []  # noqa: E111
    assert rejection_metrics["open_breaker_ids"] == []  # noqa: E111
    assert rejection_metrics["half_open_breakers"] == []  # noqa: E111
    assert rejection_metrics["half_open_breaker_ids"] == []  # noqa: E111
    assert rejection_metrics["unknown_breakers"] == []  # noqa: E111
    assert rejection_metrics["unknown_breaker_ids"] == []  # noqa: E111
    assert rejection_metrics["rejection_breaker_ids"] == []  # noqa: E111
    assert rejection_metrics["rejection_breakers"] == []  # noqa: E111

    bool_summary = snapshot["bool_coercion"]  # noqa: E111
    assert bool_summary["recorded"] is True  # noqa: E111
    assert bool_summary["total"] == 0  # noqa: E111
    assert bool_summary["reason_counts"] == {}  # noqa: E111
    assert bool_summary["samples"] == []  # noqa: E111

    performance_metrics = snapshot["performance_metrics"]  # noqa: E111
    assert performance_metrics["rejected_call_count"] == 0  # noqa: E111
    assert performance_metrics["rejection_rate"] == 0.0  # noqa: E111
    assert performance_metrics["open_breakers"] == []  # noqa: E111
    assert performance_metrics["open_breaker_ids"] == []  # noqa: E111
    assert performance_metrics["half_open_breakers"] == []  # noqa: E111
    assert performance_metrics["half_open_breaker_ids"] == []  # noqa: E111
    assert performance_metrics["unknown_breakers"] == []  # noqa: E111
    assert performance_metrics["unknown_breaker_ids"] == []  # noqa: E111
    assert performance_metrics["rejection_breaker_ids"] == []  # noqa: E111
    assert performance_metrics["rejection_breakers"] == []  # noqa: E111
    assert "resilience_summary" not in snapshot  # noqa: E111


@pytest.mark.unit
def test_build_security_scorecard_handles_failures() -> None:
    adaptive = {"current_interval_ms": 500.0, "target_cycle_ms": 180.0}  # noqa: E111
    entity_summary = {"peak_utilization": 99.0}  # noqa: E111
    webhook_status = {"configured": True, "secure": False, "hmac_ready": False}  # noqa: E111

    scorecard: CoordinatorSecurityScorecard = build_security_scorecard(  # noqa: E111
        adaptive=adaptive,
        entity_summary=entity_summary,
        webhook_status=webhook_status,
    )

    assert scorecard["status"] == "fail"  # noqa: E111
    assert scorecard["checks"]["adaptive_polling"]["pass"] is False  # noqa: E111
    assert scorecard["checks"]["entity_budget"]["pass"] is False  # noqa: E111
    assert scorecard["checks"]["webhooks"]["pass"] is False  # noqa: E111


@pytest.mark.unit
def test_normalise_webhook_status_handles_exception() -> None:
    class BrokenManager:  # noqa: E111
        @staticmethod
        def webhook_security_status() -> WebhookSecurityStatus:
            raise RuntimeError("boom")  # noqa: E111

    status = normalise_webhook_status(BrokenManager())  # noqa: E111

    assert status["configured"] is True  # noqa: E111
    assert status["secure"] is False  # noqa: E111
    assert status["error"] == "boom"  # noqa: E111

    default_status = normalise_webhook_status(None)  # noqa: E111
    assert default_status["configured"] is False  # noqa: E111
    assert default_status["secure"] is True  # noqa: E111
