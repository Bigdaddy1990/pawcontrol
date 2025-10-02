"""Coverage tests for coordinator observability helpers."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from datetime import datetime

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_ROOT = (REPO_ROOT / "custom_components").resolve()
PAWCONTROL_ROOT = (PACKAGE_ROOT / "pawcontrol").resolve()


def _ensure_package(name: str, path: pathlib.Path) -> None:
    """Register a namespace package without executing its __init__."""

    if name in sys.modules:
        return

    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    module.__package__ = name
    sys.modules[name] = module


def _load_module(name: str, filename: str):
    """Load a module from the pawcontrol package without side effects."""

    spec = importlib.util.spec_from_file_location(
        name,
        PAWCONTROL_ROOT / filename,
        submodule_search_locations=[str(PAWCONTROL_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_ensure_package("custom_components", PACKAGE_ROOT.resolve())
_ensure_package("custom_components.pawcontrol", PAWCONTROL_ROOT)

_observability = _load_module(
    "custom_components.pawcontrol.coordinator_observability",
    "coordinator_observability.py",
)
build_performance_snapshot = _observability.build_performance_snapshot
build_security_scorecard = _observability.build_security_scorecard
EntityBudgetTracker = _observability.EntityBudgetTracker
normalise_webhook_status = _observability.normalise_webhook_status


class DummyMetrics:
    """Minimal metrics stub mirroring the coordinator counters."""

    def __init__(
        self, *, update_count: int, failed_cycles: int, consecutive_errors: int
    ) -> None:
        self.update_count = update_count
        self.failed_cycles = failed_cycles
        self.consecutive_errors = consecutive_errors

    @property
    def successful_cycles(self) -> int:
        return max(self.update_count - self.failed_cycles, 0)

    @property
    def success_rate_percent(self) -> float:
        if self.update_count == 0:
            return 0.0
        return (self.successful_cycles / self.update_count) * 100


class DummySnapshot:
    """Lightweight stand-in for :class:`EntityBudgetSnapshot`."""

    def __init__(
        self,
        *,
        dog_id: str,
        capacity: int,
        base_allocation: int,
        dynamic_allocation: int,
        requested_entities: tuple[str, ...] = (),
        denied_requests: tuple[str, ...] = (),
    ) -> None:
        self.dog_id = dog_id
        self.capacity = capacity
        self.base_allocation = base_allocation
        self.dynamic_allocation = dynamic_allocation
        self.requested_entities = requested_entities
        self.denied_requests = denied_requests

    @property
    def total_allocated(self) -> int:
        return self.base_allocation + self.dynamic_allocation

    @property
    def remaining(self) -> int:
        return max(self.capacity - self.total_allocated, 0)

    @property
    def saturation(self) -> float:
        if self.capacity <= 0:
            return 0.0
        return self.total_allocated / self.capacity


def test_security_scorecard_passes_with_secure_configuration() -> None:
    """A healthy runtime should report a passing security scorecard."""

    adaptive = {"current_interval_ms": 150.0, "target_cycle_ms": 180.0}
    entity_summary = {"peak_utilization": 40.0, "active_dogs": 1}
    webhook_status = {
        "configured": True,
        "secure": True,
        "hmac_ready": True,
        "insecure_configs": (),
    }

    scorecard = build_security_scorecard(
        adaptive=adaptive,
        entity_summary=entity_summary,
        webhook_status=webhook_status,
    )

    assert scorecard["status"] == "pass"
    assert all(check["pass"] for check in scorecard["checks"].values())


def test_security_scorecard_gracefully_handles_missing_values() -> None:
    """Missing metrics should fall back to safe defaults without raising."""

    scorecard = build_security_scorecard(
        adaptive={"current_interval_ms": None},
        entity_summary={"peak_utilization": None},
        webhook_status={},
    )

    assert scorecard["checks"]["adaptive_polling"]["pass"] is True
    assert scorecard["checks"]["entity_budget"]["pass"] is True
    assert scorecard["checks"]["webhooks"]["pass"] is True


def test_build_performance_snapshot_includes_runtime_metadata() -> None:
    """Performance snapshots expose update counters and webhook posture."""

    metrics = DummyMetrics(update_count=5, failed_cycles=1, consecutive_errors=0)
    adaptive = {"current_interval_ms": 120.0, "target_cycle_ms": 180.0}
    entity_budget = {"active_dogs": 1, "peak_utilization": 50.0}
    webhook_status = {"configured": False, "secure": True, "hmac_ready": False}

    snapshot = build_performance_snapshot(
        metrics=metrics,
        adaptive=adaptive,
        entity_budget=entity_budget,
        update_interval=0.2,
        last_update_time=datetime(2024, 1, 1, 0, 0, 0),
        last_update_success=True,
        webhook_status=webhook_status,
    )

    assert snapshot["update_counts"]["total"] == 5
    assert snapshot["performance_metrics"]["current_cycle_ms"] == 120.0
    assert snapshot["webhook_security"]["secure"] is True


def test_entity_budget_tracker_summary_and_saturation() -> None:
    """Entity budget tracking aggregates utilisation across dogs."""

    tracker = EntityBudgetTracker()
    assert tracker.saturation() == 0.0

    tracker.record(
        DummySnapshot(
            dog_id="dog-a",
            capacity=10,
            base_allocation=4,
            dynamic_allocation=1,
            requested_entities=("sensor.a",),
        )
    )
    tracker.record(
        DummySnapshot(
            dog_id="dog-b",
            capacity=5,
            base_allocation=5,
            dynamic_allocation=0,
            denied_requests=("sensor.b",),
        )
    )

    tracker.record(
        DummySnapshot(
            dog_id="dog-c",
            capacity=0,
            base_allocation=0,
            dynamic_allocation=0,
        )
    )

    summary = tracker.summary()

    assert summary["active_dogs"] == 3
    assert summary["denied_requests"] == 1
    assert 0.0 < tracker.saturation() <= 1.0
    assert len(tracker.snapshots()) == 3


def test_security_scorecard_reports_failure_reason() -> None:
    """Failing checks should include the appropriate remediation hints."""

    scorecard = build_security_scorecard(
        adaptive={"current_interval_ms": 320.0, "target_cycle_ms": 180.0},
        entity_summary={"peak_utilization": 99.0},
        webhook_status={
            "configured": True,
            "secure": False,
            "insecure_configs": ("dog-a",),
        },
    )

    assert scorecard["status"] == "fail"
    assert scorecard["checks"]["adaptive_polling"]["pass"] is False
    assert "200ms" in scorecard["checks"]["adaptive_polling"]["reason"]
    assert scorecard["checks"]["entity_budget"]["pass"] is False
    assert scorecard["checks"]["webhooks"]["pass"] is False


def test_security_scorecard_coerces_invalid_numbers() -> None:
    """Invalid numeric inputs should be normalised before evaluation."""

    scorecard = build_security_scorecard(
        adaptive={"current_interval_ms": float("nan"), "target_cycle_ms": -50},
        entity_summary={"peak_utilization": "150"},
        webhook_status={"configured": False},
    )

    adaptive_check = scorecard["checks"]["adaptive_polling"]
    assert adaptive_check["pass"] is True
    assert adaptive_check["target_ms"] == 200.0

    entity_check = scorecard["checks"]["entity_budget"]
    assert entity_check["pass"] is False
    assert entity_check["threshold_percent"] == 95.0
    assert entity_check["summary"]["peak_utilization"] == "150"


def test_normalise_webhook_status_defaults_and_errors() -> None:
    """Webhook normalisation handles missing managers and raised exceptions."""

    class BrokenManager:
        @staticmethod
        def webhook_security_status() -> dict[str, str]:
            raise RuntimeError("boom")

    error_status = normalise_webhook_status(BrokenManager())
    assert error_status["configured"] is True
    assert error_status["secure"] is False
    assert error_status["error"] == "boom"

    class WorkingManager:
        @staticmethod
        def webhook_security_status() -> dict[str, object]:
            return {
                "configured": True,
                "secure": True,
                "hmac_ready": True,
                "insecure_configs": "dog-a",
            }

    default_status = normalise_webhook_status(None)
    assert default_status["configured"] is False
    assert default_status["secure"] is True

    working_status = normalise_webhook_status(WorkingManager())
    assert working_status["insecure_configs"] == ("dog-a",)
    assert working_status["secure"] is True
