from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol import coordinator_tasks as tasks
from custom_components.pawcontrol.coordinator_support import CoordinatorMetrics
from custom_components.pawcontrol.telemetry import (
  record_bool_coercion_event,
  reset_bool_coercion_metrics,
)
from custom_components.pawcontrol.types import (
  AdaptivePollingDiagnostics,
  CacheRepairAggregate,
  EntityBudgetSummary,
)


def _patch_runtime_store(
  monkeypatch: pytest.MonkeyPatch, status: str = "current"
) -> dict[str, object]:
  """Patch runtime store snapshot helpers to return a deterministic snapshot."""  # noqa: E111

  snapshot = {  # noqa: E111
    "entry_id": "entry",
    "status": status,
    "current_version": 2,
    "minimum_compatible_version": 1,
    "entry": {
      "available": True,
      "status": status,
      "version": 2,
      "created_version": 2,
    },
    "store": {
      "available": True,
      "status": status,
      "version": 2,
      "created_version": 2,
    },
    "divergence_detected": False,
  }

  def _mock_snapshot(*_args: object, **_kwargs: object) -> dict[str, object]:  # noqa: E111
    return snapshot.copy()

  monkeypatch.setattr(tasks, "describe_runtime_store_status", _mock_snapshot)  # noqa: E111
  return snapshot  # noqa: E111


class _DummyLogger:
  def debug(self, *args, **kwargs) -> None:  # pragma: no cover - helpers  # noqa: E111
    return None

  def info(self, *args, **kwargs) -> None:  # pragma: no cover - helpers  # noqa: E111
    return None


class _DummyModules:
  def __init__(self, metrics: SimpleNamespace) -> None:  # noqa: E111
    self._metrics = metrics

  def cache_metrics(self) -> SimpleNamespace:  # noqa: E111
    return self._metrics


class _DummyBudget:
  def summary(self) -> EntityBudgetSummary:  # noqa: E111
    return {
      "active_dogs": 1,
      "total_capacity": 10,
      "total_allocated": 4,
      "total_remaining": 6,
      "average_utilization": 40.0,
      "peak_utilization": 60.0,
      "denied_requests": 0,
    }


class _DummyAdaptivePolling:
  def as_diagnostics(self) -> AdaptivePollingDiagnostics:  # noqa: E111
    return {
      "target_cycle_ms": 200.0,
      "current_interval_ms": 150.0,
      "average_cycle_ms": 175.0,
      "history_samples": 5,
      "error_streak": 0,
      "entity_saturation": 0.25,
      "idle_interval_ms": 300.0,
      "idle_grace_ms": 45.0,
    }


class _DummyResilience:
  def __init__(self, payload: object | None = None) -> None:  # noqa: E111
    self._payload = payload if payload is not None else ["analytics"]

  def get_all_circuit_breakers(self) -> object:  # noqa: E111
    return self._payload


class _MissingResilience:
  """Simulate a coordinator without a resilience manager interface."""  # noqa: E111


class _BrokenResilience:
  """Resilience manager stub that raises when queried."""  # noqa: E111

  def get_all_circuit_breakers(self) -> object:  # noqa: E111
    raise RuntimeError("boom")


class _MaintenanceModules:
  def __init__(self, expired: int = 3) -> None:  # noqa: E111
    self.expired = expired
    self.calls = 0

  def cleanup_expired(self, now: object) -> int:  # noqa: E111
    self.calls += 1
    return self.expired


class _FailingModules:
  def cleanup_expired(self, now: object) -> int:  # noqa: E111
    raise RuntimeError("cleanup failed")


class _MaintenanceMetrics:
  def __init__(self, consecutive_errors: int) -> None:  # noqa: E111
    self.consecutive_errors = consecutive_errors
    self.reset_calls = 0

  def reset_consecutive(self) -> None:  # noqa: E111
    self.reset_calls += 1
    self.consecutive_errors = 0


def _build_coordinator(
  options: Mapping[str, object] | None = None,
  resilience_manager: object | None = None,
) -> SimpleNamespace:
  cache_metrics = SimpleNamespace(entries=5, hit_rate=80.0, hits=8, misses=2)  # noqa: E111
  modules = _DummyModules(cache_metrics)  # noqa: E111
  metrics = CoordinatorMetrics()  # noqa: E111
  metrics.update_count = 4  # noqa: E111
  metrics.failed_cycles = 1  # noqa: E111

  coordinator = SimpleNamespace(  # noqa: E111
    _modules=modules,
    _metrics=metrics,
    _entity_budget=_DummyBudget(),
    _adaptive_polling=_DummyAdaptivePolling(),
    resilience_manager=resilience_manager or _DummyResilience(),
    registry=["dog_a"],
    last_update_time="2024-01-02T00:00:00+00:00",
    update_interval=timedelta(minutes=30),
    hass=object(),
    config_entry=SimpleNamespace(entry_id="entry", options=options or {}),
    logger=_DummyLogger(),
  )

  return coordinator  # noqa: E111


def test_build_update_statistics_includes_repair_summary(monkeypatch) -> None:
  """Coordinator update statistics should surface repair telemetry."""  # noqa: E111

  summary = CacheRepairAggregate(  # noqa: E111
    total_caches=3,
    anomaly_count=2,
    severity="warning",
    generated_at="2024-01-02T00:00:00+00:00",
    issues=[{"cache": "adaptive_cache"}],
    caches_with_errors=["adaptive_cache"],
    caches_with_override_flags=["optimized_cache"],
  )

  _patch_runtime_store(monkeypatch)  # noqa: E111
  coordinator = _build_coordinator()  # noqa: E111
  reconfigure_summary = {  # noqa: E111
    "timestamp": "2024-01-02T00:00:00+00:00",
    "requested_profile": "advanced",
    "previous_profile": "standard",
    "dogs_count": 2,
    "estimated_entities": 24,
    "version": 1,
    "warnings": ["gps_disabled"],
    "warning_count": 1,
    "healthy": True,
    "health_issues": [],
    "health_issue_count": 0,
    "health_warnings": [],
    "health_warning_count": 0,
    "merge_notes": [],
    "merge_note_count": 0,
  }

  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: summary),
    performance_stats={"reconfigure_summary": reconfigure_summary},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  stats = tasks.build_update_statistics(coordinator)  # noqa: E111

  assert "repairs" in stats  # noqa: E111
  repairs = stats["repairs"]  # noqa: E111
  assert repairs["severity"] == "warning"  # noqa: E111
  assert repairs["anomaly_count"] == 2  # noqa: E111
  assert repairs["issues"] == 1  # noqa: E111
  assert repairs["caches_with_errors"] == 1  # noqa: E111
  assert repairs["caches_with_override_flags"] == 1  # noqa: E111
  assert "reconfigure" in stats  # noqa: E111
  assert stats["reconfigure"]["requested_profile"] == "advanced"  # noqa: E111
  assert stats["reconfigure"]["warning_count"] == 1  # noqa: E111
  assert stats["reconfigure"]["merge_note_count"] == 0  # noqa: E111
  runtime_store = stats["runtime_store"]  # noqa: E111
  assert runtime_store["snapshot"]["status"] == "current"  # noqa: E111
  assert runtime_store["history"]["checks"] == 1  # noqa: E111
  assert runtime_store["assessment"]["level"] in {  # noqa: E111
    "ok",
    "watch",
    "action_required",
  }


def test_build_update_statistics_serialises_resilience_payload(monkeypatch) -> None:
  """Coordinator update statistics should expose resilience telemetry when present."""  # noqa: E111

  breaker = SimpleNamespace(  # noqa: E111
    state=SimpleNamespace(value="closed"),
    failure_count=2,
    success_count=8,
    last_failure_time=1700000000.0,
    last_state_change=1700000100.0,
    total_calls=10,
    total_failures=2,
    total_successes=8,
    rejected_calls=0,
    last_rejection_time=None,
  )
  resilience_manager = _DummyResilience({"api": breaker})  # noqa: E111
  coordinator = _build_coordinator(resilience_manager=resilience_manager)  # noqa: E111

  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_update_statistics(coordinator)  # noqa: E111

  assert "resilience" in stats  # noqa: E111
  resilience = stats["resilience"]  # noqa: E111
  assert resilience["breakers"]["api"]["breaker_id"] == "api"  # noqa: E111
  assert resilience["breakers"]["api"]["state"] == "closed"  # noqa: E111
  assert resilience["breakers"]["api"]["failure_count"] == 2  # noqa: E111
  assert resilience["breakers"]["api"]["rejected_calls"] == 0  # noqa: E111
  assert resilience["summary"]["total_breakers"] == 1  # noqa: E111
  assert resilience["summary"]["states"]["closed"] == 1  # noqa: E111
  assert resilience["summary"]["open_breaker_count"] == 0  # noqa: E111
  assert resilience["summary"]["half_open_breaker_count"] == 0  # noqa: E111
  assert resilience["summary"]["rejected_call_count"] == 0  # noqa: E111
  assert resilience["summary"]["rejection_breaker_count"] == 0  # noqa: E111
  assert resilience["summary"]["rejection_breakers"] == []  # noqa: E111
  assert resilience["summary"]["rejection_breaker_ids"] == []  # noqa: E111
  assert resilience["summary"]["rejection_rate"] == 0.0  # noqa: E111
  assert resilience["summary"]["last_rejection_time"] is None  # noqa: E111
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111
  assert "last_rejection_breaker_id" not in resilience["summary"]  # noqa: E111
  performance_metrics = stats["performance_metrics"]  # noqa: E111
  assert performance_metrics["rejected_call_count"] == 0  # noqa: E111
  assert performance_metrics["rejection_breaker_count"] == 0  # noqa: E111
  assert performance_metrics["rejection_rate"] == 0.0  # noqa: E111
  assert performance_metrics["last_rejection_time"] is None  # noqa: E111
  assert performance_metrics.get("last_rejection_breaker_id") is None  # noqa: E111
  assert "schema_version" not in performance_metrics  # noqa: E111
  assert performance_metrics["open_breakers"] == []  # noqa: E111
  assert performance_metrics["open_breaker_ids"] == []  # noqa: E111
  assert performance_metrics["half_open_breakers"] == []  # noqa: E111
  assert performance_metrics["half_open_breaker_ids"] == []  # noqa: E111
  assert performance_metrics["unknown_breakers"] == []  # noqa: E111
  assert performance_metrics["unknown_breaker_ids"] == []  # noqa: E111
  assert performance_metrics["rejection_breaker_ids"] == []  # noqa: E111
  assert performance_metrics["rejection_breakers"] == []  # noqa: E111
  assert "rejection_metrics" in stats  # noqa: E111
  assert stats["rejection_metrics"]["schema_version"] == 4  # noqa: E111
  assert stats["rejection_metrics"]["rejected_call_count"] == 0  # noqa: E111
  assert stats["rejection_metrics"]["rejection_rate"] == 0.0  # noqa: E111
  assert stats["rejection_metrics"]["unknown_breaker_count"] == 0  # noqa: E111
  assert stats["rejection_metrics"]["open_breakers"] == []  # noqa: E111
  assert stats["rejection_metrics"]["unknown_breaker_ids"] == []  # noqa: E111


def test_build_update_statistics_defaults_rejection_metrics(monkeypatch) -> None:
  """Update statistics should provide default rejection metrics without resilience data."""  # noqa: E111, E501

  coordinator = _build_coordinator(resilience_manager=None)  # noqa: E111

  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  monkeypatch.setattr(tasks, "collect_resilience_diagnostics", lambda *_: None)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_update_statistics(coordinator)  # noqa: E111

  assert "rejection_metrics" in stats  # noqa: E111
  metrics = stats["rejection_metrics"]  # noqa: E111
  assert metrics["schema_version"] == 4  # noqa: E111
  assert metrics["rejected_call_count"] == 0  # noqa: E111
  assert metrics["rejection_breaker_count"] == 0  # noqa: E111
  assert metrics["rejection_rate"] == 0.0  # noqa: E111
  assert metrics["last_rejection_time"] is None  # noqa: E111
  assert metrics["last_rejection_breaker_id"] is None  # noqa: E111
  assert metrics["last_rejection_breaker_name"] is None  # noqa: E111
  assert metrics["open_breaker_count"] == 0  # noqa: E111
  assert metrics["half_open_breaker_count"] == 0  # noqa: E111
  assert metrics["unknown_breaker_count"] == 0  # noqa: E111
  assert metrics["open_breakers"] == []  # noqa: E111
  assert metrics["open_breaker_ids"] == []  # noqa: E111
  assert metrics["half_open_breakers"] == []  # noqa: E111
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111
  assert metrics["half_open_breaker_ids"] == []  # noqa: E111
  assert metrics["unknown_breakers"] == []  # noqa: E111
  assert metrics["unknown_breaker_ids"] == []  # noqa: E111
  assert metrics["rejection_breaker_ids"] == []  # noqa: E111
  assert metrics["rejection_breakers"] == []  # noqa: E111

  performance_metrics = stats.get("performance_metrics")  # noqa: E111
  if isinstance(performance_metrics, dict):  # noqa: E111
    assert performance_metrics["rejected_call_count"] == 0
    assert performance_metrics["rejection_rate"] == 0.0
    assert "schema_version" not in performance_metrics
    assert performance_metrics["open_breaker_ids"] == []
    assert performance_metrics["half_open_breaker_ids"] == []
    assert performance_metrics["unknown_breaker_ids"] == []
    assert performance_metrics["rejection_breaker_ids"] == []
    assert performance_metrics["rejection_breakers"] == []


def test_derive_rejection_metrics_preserves_defaults() -> None:
  """Derived metrics should keep seeded defaults when resilience payload omits values."""  # noqa: E111, E501

  metrics = tasks.derive_rejection_metrics({  # noqa: E111
    "rejected_call_count": None,
    "rejection_breaker_count": None,
    "rejection_rate": None,
    "last_rejection_time": None,
    "last_rejection_breaker_id": None,
    "last_rejection_breaker_name": None,
  })

  assert metrics["schema_version"] == 4  # noqa: E111
  assert metrics["rejected_call_count"] == 0  # noqa: E111
  assert metrics["rejection_breaker_count"] == 0  # noqa: E111
  assert metrics["rejection_rate"] == 0.0  # noqa: E111
  assert metrics["last_rejection_time"] is None  # noqa: E111
  assert metrics["last_rejection_breaker_id"] is None  # noqa: E111
  assert metrics["last_rejection_breaker_name"] is None  # noqa: E111
  assert metrics["open_breaker_count"] == 0  # noqa: E111
  assert metrics["half_open_breaker_count"] == 0  # noqa: E111
  assert metrics["unknown_breaker_count"] == 0  # noqa: E111
  assert metrics["open_breakers"] == []  # noqa: E111
  assert metrics["open_breaker_ids"] == []  # noqa: E111
  assert metrics["half_open_breakers"] == []  # noqa: E111
  assert metrics["half_open_breaker_ids"] == []  # noqa: E111
  assert metrics["unknown_breakers"] == []  # noqa: E111
  assert metrics["unknown_breaker_ids"] == []  # noqa: E111
  assert metrics["rejection_breaker_ids"] == []  # noqa: E111
  assert metrics["rejection_breakers"] == []  # noqa: E111


def test_derive_rejection_metrics_handles_missing_summary() -> None:
  """Passing ``None`` or an empty summary returns seeded defaults."""  # noqa: E111

  assert tasks.derive_rejection_metrics(None) == tasks.default_rejection_metrics()  # noqa: E111
  assert tasks.derive_rejection_metrics({}) == tasks.default_rejection_metrics()  # noqa: E111


def test_collect_resilience_diagnostics_persists_summary(monkeypatch) -> None:
  """Collected resilience summaries should persist into runtime performance stats."""  # noqa: E111

  breaker = SimpleNamespace(  # noqa: E111
    state=SimpleNamespace(value="open"),
    failure_count=5,
    success_count=1,
    last_failure_time=1700000200.0,
    last_state_change=1700000300.0,
    total_calls=6,
    total_failures=5,
    total_successes=1,
    rejected_calls=2,
    last_rejection_time=1700000350.0,
  )
  resilience_manager = _DummyResilience({"automation": breaker})  # noqa: E111
  coordinator = _build_coordinator(resilience_manager=resilience_manager)  # noqa: E111

  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  stored = runtime_data.performance_stats["resilience_summary"]  # noqa: E111
  assert stored["total_breakers"] == 1  # noqa: E111
  assert stored["open_breaker_count"] == 1  # noqa: E111
  assert stored["half_open_breaker_count"] == 0  # noqa: E111
  assert stored["rejected_call_count"] == 2  # noqa: E111
  assert stored["last_rejection_time"] == 1700000350.0  # noqa: E111
  assert stored["rejection_breaker_ids"] == ["automation"]  # noqa: E111
  assert stored["rejection_rate"] == pytest.approx(0.25)  # noqa: E111
  diagnostics_payload = runtime_data.performance_stats["resilience_diagnostics"]  # noqa: E111
  assert diagnostics_payload["summary"]["rejection_rate"] == pytest.approx(0.25)  # noqa: E111
  assert diagnostics_payload["summary"]["rejection_breakers"] == ["automation"]  # noqa: E111
  breaker_snapshot = diagnostics_payload["breakers"]["automation"]  # noqa: E111
  assert breaker_snapshot["breaker_id"] == "automation"  # noqa: E111
  assert payload["breakers"]["automation"]["breaker_id"] == "automation"  # noqa: E111
  assert payload["summary"]["open_breakers"] == ["automation"]  # noqa: E111
  assert payload["summary"]["rejection_breakers"] == ["automation"]  # noqa: E111
  assert payload["summary"]["rejection_rate"] == pytest.approx(0.25)  # noqa: E111


def test_collect_resilience_diagnostics_clears_summary_when_no_breakers(
  monkeypatch,
) -> None:
  """Persisted resilience summaries should be cleared when no breakers exist."""  # noqa: E111

  summary = {  # noqa: E111
    "total_breakers": 1,
    "states": {
      "closed": 1,
      "open": 0,
      "half_open": 0,
      "unknown": 0,
      "other": 0,
    },
    "failure_count": 0,
    "success_count": 0,
    "total_calls": 0,
    "total_failures": 0,
    "total_successes": 0,
    "rejected_call_count": 0,
    "last_failure_time": None,
    "last_state_change": None,
    "open_breaker_count": 0,
    "half_open_breaker_count": 0,
    "last_rejection_time": None,
    "rejection_breaker_count": 0,
    "rejection_breakers": [],
    "rejection_breaker_ids": [],
    "rejection_rate": None,
  }

  runtime_data = SimpleNamespace(  # noqa: E111
    performance_stats={
      "resilience_summary": dict(summary),
      "resilience_diagnostics": {"summary": dict(summary)},
    }
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=_DummyResilience({}))  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  assert payload == {}  # noqa: E111
  assert "resilience_summary" not in runtime_data.performance_stats  # noqa: E111
  assert "resilience_diagnostics" not in runtime_data.performance_stats  # noqa: E111


def test_collect_resilience_diagnostics_clears_summary_without_manager(
  monkeypatch,
) -> None:
  """Persisted resilience summaries should be cleared when manager is unavailable."""  # noqa: E111

  summary = {  # noqa: E111
    "total_breakers": 2,
    "states": {
      "closed": 1,
      "open": 1,
      "half_open": 0,
      "unknown": 0,
      "other": 0,
    },
    "failure_count": 3,
    "success_count": 1,
    "total_calls": 4,
    "total_failures": 3,
    "total_successes": 1,
    "last_failure_time": None,
    "last_state_change": None,
    "last_success_time": None,
    "open_breakers": ["api"],
    "open_breaker_ids": ["api"],
    "open_breaker_count": 1,
    "half_open_breaker_count": 0,
    "rejected_call_count": 0,
    "last_rejection_time": None,
    "rejection_breaker_count": 0,
    "rejection_breakers": [],
    "rejection_breaker_ids": [],
    "rejection_rate": None,
  }

  runtime_data = SimpleNamespace(  # noqa: E111
    performance_stats={
      "resilience_summary": dict(summary),
      "resilience_diagnostics": {"summary": dict(summary)},
    }
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=_MissingResilience())  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  assert payload == {}  # noqa: E111
  assert "resilience_summary" not in runtime_data.performance_stats  # noqa: E111
  assert "resilience_diagnostics" not in runtime_data.performance_stats  # noqa: E111


def test_collect_resilience_diagnostics_clears_summary_on_error(monkeypatch) -> None:
  """Resilience summaries should be cleared when collection raises an exception."""  # noqa: E111

  summary = {  # noqa: E111
    "total_breakers": 1,
    "states": {
      "closed": 0,
      "open": 1,
      "half_open": 0,
      "unknown": 0,
      "other": 0,
    },
    "failure_count": 4,
    "success_count": 0,
    "total_calls": 4,
    "total_failures": 4,
    "total_successes": 0,
    "last_failure_time": None,
    "last_state_change": None,
    "last_success_time": None,
    "open_breakers": ["api"],
    "open_breaker_ids": ["api"],
    "open_breaker_count": 1,
    "half_open_breaker_count": 0,
    "rejected_call_count": 0,
    "last_rejection_time": None,
    "rejection_breaker_count": 0,
    "rejection_breakers": [],
    "rejection_breaker_ids": [],
    "rejection_rate": None,
  }

  runtime_data = SimpleNamespace(  # noqa: E111
    performance_stats={
      "resilience_summary": dict(summary),
      "resilience_diagnostics": {"summary": dict(summary)},
    }
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=_BrokenResilience())  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  assert payload == {}  # noqa: E111
  assert "resilience_summary" not in runtime_data.performance_stats  # noqa: E111
  assert "resilience_diagnostics" not in runtime_data.performance_stats  # noqa: E111


def test_collect_resilience_diagnostics_clears_summary_on_invalid_payload(
  monkeypatch,
) -> None:
  """Resilience summaries should be cleared when payload is not iterable."""  # noqa: E111

  summary = {  # noqa: E111
    "total_breakers": 1,
    "states": {
      "closed": 0,
      "open": 1,
      "half_open": 0,
      "unknown": 0,
      "other": 0,
    },
    "failure_count": 2,
    "success_count": 0,
    "total_calls": 2,
    "total_failures": 2,
    "total_successes": 0,
    "last_failure_time": None,
    "last_state_change": None,
    "last_success_time": None,
    "open_breakers": ["api"],
    "open_breaker_count": 1,
    "half_open_breakers": [],
    "half_open_breaker_count": 0,
    "rejected_call_count": 0,
    "last_rejection_time": None,
    "rejection_breaker_count": 0,
    "rejection_breakers": [],
    "rejection_breaker_ids": [],
    "rejection_rate": None,
  }

  runtime_data = SimpleNamespace(  # noqa: E111
    performance_stats={
      "resilience_summary": dict(summary),
      "resilience_diagnostics": {"summary": dict(summary)},
    }
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  class _InvalidResilience:  # noqa: E111
    def get_all_circuit_breakers(self) -> object:
      return object()  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=_InvalidResilience())  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  assert payload == {}  # noqa: E111
  assert "resilience_summary" not in runtime_data.performance_stats  # noqa: E111
  assert "resilience_diagnostics" not in runtime_data.performance_stats  # noqa: E111


def test_collect_resilience_diagnostics_coerces_stats_values(monkeypatch) -> None:
  """Circuit breaker stats should coerce mixed-value payloads safely."""  # noqa: E111

  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  class _MixedStats(dict):  # noqa: E111
    def __init__(self) -> None:
      super().__init__(  # noqa: E111
        state="HALF_OPEN",
        failure_count="3",
        success_count=None,
        last_failure_time="1700000000.5",
        last_state_change="not-a-number",
        total_calls="12",
        total_failures="4",
        total_successes=None,
        last_success_time=datetime(2024, 1, 2, tzinfo=UTC),
        rejected_calls="2",
        last_rejection_time="2024-01-02T11:00:00+00:00",
      )

  resilience_manager = _DummyResilience({"mixed": _MixedStats()})  # noqa: E111
  coordinator = _build_coordinator(resilience_manager=resilience_manager)  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  entry = payload["breakers"]["mixed"]  # noqa: E111
  assert entry["breaker_id"] == "mixed"  # noqa: E111
  assert entry["state"] == "HALF_OPEN"  # noqa: E111
  assert entry["failure_count"] == 3  # noqa: E111
  assert entry["success_count"] == 0  # noqa: E111
  assert entry["total_calls"] == 12  # noqa: E111
  assert entry["total_failures"] == 4  # noqa: E111
  assert entry["total_successes"] == 0  # noqa: E111
  assert entry["last_failure_time"] == pytest.approx(1700000000.5)  # noqa: E111
  assert entry["last_state_change"] is None  # noqa: E111
  assert entry["last_success_time"] is not None  # noqa: E111
  assert entry["rejected_calls"] == 2  # noqa: E111
  assert entry["last_rejection_time"] is not None  # noqa: E111

  summary = payload["summary"]  # noqa: E111
  assert summary["total_calls"] == 12  # noqa: E111
  assert summary["total_failures"] == 4  # noqa: E111
  assert summary["total_successes"] == 0  # noqa: E111
  assert summary["rejected_call_count"] == 2  # noqa: E111
  assert summary["rejection_breaker_count"] == 1  # noqa: E111
  assert summary["rejection_breakers"] == ["mixed"]  # noqa: E111
  assert summary["rejection_rate"] == pytest.approx(2 / (12 + 2))  # noqa: E111


def test_collect_resilience_diagnostics_defaults_unknown_state(monkeypatch) -> None:
  """Collector should normalise missing or blank states to "unknown"."""  # noqa: E111

  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  class _MissingState(dict):  # noqa: E111
    def __init__(self) -> None:
      super().__init__(  # noqa: E111
        failure_count=1,
        success_count=0,
        total_calls=1,
        total_failures=1,
        total_successes=0,
      )

  class _BlankState(dict):  # noqa: E111
    def __init__(self) -> None:
      super().__init__(  # noqa: E111
        state="   ",
        failure_count=0,
        success_count=2,
        total_calls=2,
        total_failures=0,
        total_successes=2,
      )

  resilience_manager = _DummyResilience({  # noqa: E111
    "legacy": _MissingState(),
    "blank": _BlankState(),
  })
  coordinator = _build_coordinator(resilience_manager=resilience_manager)  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  breakers = payload["breakers"]  # noqa: E111
  assert breakers["legacy"]["state"] == "unknown"  # noqa: E111
  assert breakers["blank"]["state"] == "unknown"  # noqa: E111

  summary = payload["summary"]  # noqa: E111
  assert summary["states"]["unknown"] == 2  # noqa: E111
  assert summary["states"]["other"] == 0  # noqa: E111
  assert summary["unknown_breakers"] == ["legacy", "blank"]  # noqa: E111
  assert summary["unknown_breaker_ids"] == ["legacy", "blank"]  # noqa: E111
  assert summary["unknown_breaker_count"] == 2  # noqa: E111


def test_summarise_resilience_normalises_state_metadata() -> None:
  """State aggregation should coerce whitespace, enums, and hyphenated values."""  # noqa: E111

  @dataclass(slots=True)  # noqa: E111
  class _EnumState:  # noqa: E111
    value: str

  summary = tasks._summarise_resilience({  # noqa: E111
    "legacy": {"state": None, "breaker_id": "legacy"},
    "spaced": {"state": "  Open  ", "breaker_id": "api"},
    "hyphen": {"state": "half-open", "breaker_id": "fallback"},
    "enum": {"state": _EnumState("CLOSED"), "breaker_id": "enum"},
  })

  assert summary["states"]["closed"] == 1  # noqa: E111
  assert summary["states"]["open"] == 1  # noqa: E111
  assert summary["states"]["half_open"] == 1  # noqa: E111
  assert summary["states"]["unknown"] == 1  # noqa: E111
  assert summary["open_breakers"] == ["spaced"]  # noqa: E111
  assert summary["open_breaker_ids"] == ["api"]  # noqa: E111
  assert summary["half_open_breakers"] == ["hyphen"]  # noqa: E111
  assert summary["half_open_breaker_ids"] == ["fallback"]  # noqa: E111
  assert summary["unknown_breakers"] == ["legacy"]  # noqa: E111
  assert summary["unknown_breaker_ids"] == ["legacy"]  # noqa: E111
  assert summary["unknown_breaker_count"] == 1  # noqa: E111


def test_summarise_resilience_uses_extended_breaker_identifiers() -> None:
  """Aggregation should honour identifier metadata when breaker IDs are missing."""  # noqa: E111

  summary = tasks._summarise_resilience({  # noqa: E111
    "api": {"state": "OPEN", "identifier": "api-primary"},
    "fallback": {"state": "half_open", "name": "fallback-service"},
  })

  assert summary["open_breaker_ids"] == ["api-primary"]  # noqa: E111
  assert summary["half_open_breaker_ids"] == ["fallback-service"]  # noqa: E111


def test_collect_resilience_diagnostics_prefers_breaker_metadata(monkeypatch) -> None:
  """Collector should use embedded breaker identifiers when provided."""  # noqa: E111

  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  class _MetadataStats(dict):  # noqa: E111
    def __init__(self) -> None:
      super().__init__(  # noqa: E111
        breaker_id="api-primary",
        state="OPEN",
        failure_count=2,
        success_count=0,
        total_calls=2,
        total_failures=2,
        total_successes=0,
        last_failure_time=100.0,
        rejected_calls=1,
        last_rejection_time=150.0,
      )

  resilience_manager = _DummyResilience({"api": _MetadataStats()})  # noqa: E111
  coordinator = _build_coordinator(resilience_manager=resilience_manager)  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  breakers = payload["breakers"]  # noqa: E111
  assert set(breakers) == {"api"}  # noqa: E111
  entry = breakers["api"]  # noqa: E111
  assert entry["breaker_id"] == "api-primary"  # noqa: E111

  summary = payload["summary"]  # noqa: E111
  assert summary["open_breakers"] == ["api"]  # noqa: E111
  assert summary["open_breaker_count"] == 1  # noqa: E111
  assert summary["open_breaker_ids"] == ["api-primary"]  # noqa: E111
  assert summary["unknown_breaker_count"] == 0  # noqa: E111
  assert summary["unknown_breakers"] == []  # noqa: E111
  assert summary["unknown_breaker_ids"] == []  # noqa: E111
  assert "recovery_breaker_name" not in summary  # noqa: E111
  assert summary["rejected_call_count"] == 1  # noqa: E111
  assert summary["rejection_breakers"] == ["api"]  # noqa: E111
  assert summary["rejection_breaker_ids"] == ["api-primary"]  # noqa: E111
  assert summary["rejection_rate"] == pytest.approx(1 / (2 + 1))  # noqa: E111

  stored = runtime_data.performance_stats["resilience_summary"]  # noqa: E111
  assert stored["open_breakers"] == ["api"]  # noqa: E111
  assert stored["open_breaker_count"] == 1  # noqa: E111
  assert stored["open_breaker_ids"] == ["api-primary"]  # noqa: E111
  assert stored["unknown_breaker_count"] == 0  # noqa: E111
  assert stored["unknown_breakers"] == []  # noqa: E111
  assert stored["unknown_breaker_ids"] == []  # noqa: E111
  assert "recovery_breaker_name" not in stored  # noqa: E111
  assert stored["rejected_call_count"] == 1  # noqa: E111
  assert stored["rejection_breakers"] == ["api"]  # noqa: E111
  assert stored["rejection_breaker_ids"] == ["api-primary"]  # noqa: E111
  assert stored["rejection_rate"] == pytest.approx(1 / (2 + 1))  # noqa: E111
  diagnostics_payload = runtime_data.performance_stats["resilience_diagnostics"]  # noqa: E111
  assert diagnostics_payload["summary"]["rejection_breaker_ids"] == ["api-primary"]  # noqa: E111
  assert diagnostics_payload["summary"]["rejection_rate"] == pytest.approx(1 / (2 + 1))  # noqa: E111
  assert diagnostics_payload["breakers"]["api"]["breaker_id"] == "api-primary"  # noqa: E111


def test_collect_resilience_diagnostics_converts_temporal_values(monkeypatch) -> None:
  """Resilience telemetry should normalise datetime, date, and ISO timestamps."""  # noqa: E111

  failure_time = datetime(2024, 1, 2, 12, 30, tzinfo=UTC)  # noqa: E111
  state_change_iso = "2024-03-01T08:15:00+00:00"  # noqa: E111
  fallback_date = date(2024, 4, 5)  # noqa: E111

  class _TemporalStats(dict):  # noqa: E111
    def __init__(self) -> None:
      super().__init__(  # noqa: E111
        state="OPEN",
        failure_count=5,
        success_count=7,
        last_failure_time=failure_time,
        last_state_change=state_change_iso,
        total_calls=12,
        total_failures=5,
        total_successes=7,
        last_success_time=fallback_date,
      )

  resilience_manager = _DummyResilience({"temporal": _TemporalStats()})  # noqa: E111
  coordinator = _build_coordinator(resilience_manager=resilience_manager)  # noqa: E111

  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  entry = payload["breakers"]["temporal"]  # noqa: E111
  assert entry["breaker_id"] == "temporal"  # noqa: E111
  expected_failure = tasks._timestamp_from_datetime(failure_time)  # noqa: E111
  assert expected_failure is not None  # noqa: E111
  parsed_state_change = dt_util.parse_datetime(state_change_iso)  # noqa: E111
  assert parsed_state_change is not None  # noqa: E111
  expected_state_change = tasks._timestamp_from_datetime(parsed_state_change)  # noqa: E111
  assert expected_state_change is not None  # noqa: E111

  assert entry["last_failure_time"] == pytest.approx(expected_failure)  # noqa: E111
  assert entry["last_state_change"] == pytest.approx(expected_state_change)  # noqa: E111

  fallback = entry.get("last_success_time")  # noqa: E111
  assert fallback is not None  # noqa: E111
  try:  # noqa: E111
    start_of_day = dt_util.start_of_local_day(fallback_date)
  except AttributeError:  # noqa: E111
    start_of_day = datetime.combine(fallback_date, datetime.min.time(), tzinfo=UTC)
  expected_success = tasks._timestamp_from_datetime(start_of_day)  # noqa: E111
  assert expected_success is not None  # noqa: E111
  assert fallback == pytest.approx(expected_success)  # noqa: E111

  summary = payload["summary"]  # noqa: E111
  assert summary["last_success_time"] == pytest.approx(expected_success)  # noqa: E111
  assert summary["recovery_latency"] == pytest.approx(  # noqa: E111
    expected_success - expected_failure
  )
  assert summary["recovery_breaker_id"] == "temporal"  # noqa: E111
  assert summary["recovery_breaker_name"] == "temporal"  # noqa: E111
  assert summary["open_breaker_ids"] == ["temporal"]  # noqa: E111
  assert summary["rejected_call_count"] == 0  # noqa: E111
  assert summary["rejection_breaker_count"] == 0  # noqa: E111
  assert summary["last_rejection_time"] is None  # noqa: E111

  stored = runtime_data.performance_stats["resilience_summary"]  # noqa: E111
  assert stored["last_failure_time"] == pytest.approx(expected_failure)  # noqa: E111
  assert stored["last_state_change"] == pytest.approx(expected_state_change)  # noqa: E111
  assert stored["last_success_time"] == pytest.approx(expected_success)  # noqa: E111
  assert stored["recovery_latency"] == pytest.approx(  # noqa: E111
    expected_success - expected_failure
  )
  assert stored["recovery_breaker_id"] == "temporal"  # noqa: E111
  assert stored["recovery_breaker_name"] == "temporal"  # noqa: E111
  assert stored["open_breaker_ids"] == ["temporal"]  # noqa: E111
  assert stored["rejected_call_count"] == 0  # noqa: E111
  assert stored["rejection_breaker_count"] == 0  # noqa: E111
  assert stored["last_rejection_time"] is None  # noqa: E111
  diagnostics_payload = runtime_data.performance_stats["resilience_diagnostics"]  # noqa: E111
  assert diagnostics_payload["summary"]["recovery_breaker_id"] == "temporal"  # noqa: E111
  assert diagnostics_payload["summary"]["recovery_latency"] == pytest.approx(  # noqa: E111
    expected_success - expected_failure
  )
  assert diagnostics_payload["breakers"]["temporal"]["breaker_id"] == "temporal"  # noqa: E111


def test_collect_resilience_diagnostics_handles_unrecovered_breaker(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Recovery latency should be omitted when success precedes the latest failure."""  # noqa: E111

  class _Unrecovered(dict):  # noqa: E111
    def __init__(self) -> None:
      super().__init__(  # noqa: E111
        state="OPEN",
        failure_count=1,
        success_count=0,
        total_calls=5,
        total_failures=1,
        total_successes=4,
        last_failure_time=200.0,
        last_success_time=150.0,
      )

  resilience_manager = _DummyResilience({"api": _Unrecovered()})  # noqa: E111
  coordinator = _build_coordinator(resilience_manager=resilience_manager)  # noqa: E111

  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  summary = payload["summary"]  # noqa: E111
  assert summary["recovery_latency"] is None  # noqa: E111
  assert summary["recovery_breaker_id"] is None  # noqa: E111
  assert "recovery_breaker_name" not in summary  # noqa: E111
  assert summary["open_breaker_ids"] == ["api"]  # noqa: E111
  assert summary["rejected_call_count"] == 0  # noqa: E111
  assert summary["rejection_breaker_count"] == 0  # noqa: E111
  assert summary["last_rejection_time"] is None  # noqa: E111

  stored = runtime_data.performance_stats["resilience_summary"]  # noqa: E111
  assert stored["recovery_latency"] is None  # noqa: E111
  assert stored["recovery_breaker_id"] is None  # noqa: E111
  assert "recovery_breaker_name" not in stored  # noqa: E111
  assert stored["open_breaker_ids"] == ["api"]  # noqa: E111
  assert stored["rejected_call_count"] == 0  # noqa: E111
  assert stored["rejection_breaker_count"] == 0  # noqa: E111
  assert stored["last_rejection_time"] is None  # noqa: E111
  diagnostics_payload = runtime_data.performance_stats["resilience_diagnostics"]  # noqa: E111
  assert diagnostics_payload["summary"]["recovery_breaker_id"] is None  # noqa: E111
  assert diagnostics_payload["summary"]["open_breaker_ids"] == ["api"]  # noqa: E111


def test_collect_resilience_diagnostics_pairs_latest_recovery(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Latest recovery latency should pair success with its originating breaker."""  # noqa: E111

  stale_breaker = {  # noqa: E111
    "state": "OPEN",
    "failure_count": 4,
    "success_count": 1,
    "total_calls": 6,
    "total_failures": 4,
    "total_successes": 2,
    "last_failure_time": 200.0,
    "last_success_time": 100.0,
    "rejected_calls": 1,
    "last_rejection_time": 50.0,
  }
  recovered_breaker = {  # noqa: E111
    "state": "CLOSED",
    "failure_count": 3,
    "success_count": 6,
    "total_calls": 12,
    "total_failures": 3,
    "total_successes": 9,
    "last_failure_time": 150.0,
    "last_success_time": 300.0,
    "rejected_calls": 4,
    "last_rejection_time": 275.0,
  }

  resilience_manager = _DummyResilience({  # noqa: E111
    "stale": stale_breaker,
    "recovered": recovered_breaker,
  })
  coordinator = _build_coordinator(resilience_manager=resilience_manager)  # noqa: E111

  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111

  payload = tasks.collect_resilience_diagnostics(coordinator)  # noqa: E111

  summary = payload["summary"]  # noqa: E111
  assert summary["last_failure_time"] == 200.0  # noqa: E111
  assert summary["last_success_time"] == 300.0  # noqa: E111
  assert summary["recovery_latency"] == pytest.approx(150.0)  # noqa: E111
  assert summary["recovery_breaker_id"] == "recovered"  # noqa: E111
  assert summary["recovery_breaker_name"] == "recovered"  # noqa: E111
  assert summary["open_breaker_ids"] == ["stale"]  # noqa: E111
  assert summary["rejected_call_count"] == 5  # noqa: E111
  assert summary["last_rejection_time"] == 275.0  # noqa: E111
  assert summary["last_rejection_breaker_id"] == "recovered"  # noqa: E111
  assert summary["rejection_breaker_count"] == 2  # noqa: E111
  assert sorted(summary["rejection_breakers"]) == ["recovered", "stale"]  # noqa: E111
  assert summary["rejection_rate"] == pytest.approx(5 / (18 + 5))  # noqa: E111

  stored = runtime_data.performance_stats["resilience_summary"]  # noqa: E111
  assert stored["recovery_latency"] == pytest.approx(150.0)  # noqa: E111
  assert stored["recovery_breaker_id"] == "recovered"  # noqa: E111
  assert stored["recovery_breaker_name"] == "recovered"  # noqa: E111
  assert stored["open_breaker_ids"] == ["stale"]  # noqa: E111
  assert stored["rejected_call_count"] == 5  # noqa: E111
  assert stored["last_rejection_time"] == 275.0  # noqa: E111
  assert stored["last_rejection_breaker_id"] == "recovered"  # noqa: E111
  assert stored["rejection_breaker_count"] == 2  # noqa: E111
  assert stored["rejection_rate"] == pytest.approx(5 / (18 + 5))  # noqa: E111
  diagnostics_payload = runtime_data.performance_stats["resilience_diagnostics"]  # noqa: E111
  assert diagnostics_payload["summary"]["rejection_breaker_count"] == 2  # noqa: E111
  assert diagnostics_payload["summary"]["recovery_breaker_id"] == "recovered"  # noqa: E111
  assert diagnostics_payload["breakers"]["recovered"]["last_success_time"] == 300.0  # noqa: E111


def test_build_runtime_statistics_omits_empty_repair_summary(monkeypatch) -> None:
  """Runtime statistics should omit repairs telemetry when unavailable."""  # noqa: E111

  coordinator = _build_coordinator()  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None)
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_runtime_statistics(coordinator)  # noqa: E111

  assert "repairs" not in stats  # noqa: E111
  assert "reconfigure" not in stats  # noqa: E111
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111


def test_build_runtime_statistics_omits_empty_resilience(monkeypatch) -> None:
  """Runtime statistics should skip resilience telemetry when no payload is available."""  # noqa: E111, E501

  coordinator = _build_coordinator(resilience_manager=_DummyResilience({}))  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None)
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_runtime_statistics(coordinator)  # noqa: E111

  assert "resilience" not in stats  # noqa: E111
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111


def test_build_runtime_statistics_defaults_rejection_metrics(monkeypatch) -> None:
  """Runtime statistics should include default rejection metrics when none recorded."""  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=None)  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  monkeypatch.setattr(tasks, "collect_resilience_diagnostics", lambda *_: None)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_runtime_statistics(coordinator)  # noqa: E111

  metrics = stats["rejection_metrics"]  # noqa: E111
  assert metrics["schema_version"] == 4  # noqa: E111
  assert metrics["rejected_call_count"] == 0  # noqa: E111
  assert metrics["rejection_breaker_count"] == 0  # noqa: E111
  assert metrics["rejection_rate"] == 0.0  # noqa: E111
  assert metrics["last_rejection_time"] is None  # noqa: E111
  assert metrics["last_rejection_breaker_id"] is None  # noqa: E111
  assert metrics["last_rejection_breaker_name"] is None  # noqa: E111
  assert metrics["open_breaker_count"] == 0  # noqa: E111
  assert metrics["half_open_breaker_count"] == 0  # noqa: E111
  assert metrics["unknown_breaker_count"] == 0  # noqa: E111
  assert metrics["open_breaker_ids"] == []  # noqa: E111
  assert metrics["half_open_breaker_ids"] == []  # noqa: E111
  assert metrics["unknown_breaker_ids"] == []  # noqa: E111
  assert metrics["rejection_breaker_ids"] == []  # noqa: E111
  assert metrics["rejection_breakers"] == []  # noqa: E111

  error_summary = stats["error_summary"]  # noqa: E111
  assert error_summary["rejection_rate"] == 0.0  # noqa: E111
  assert error_summary["rejected_call_count"] == 0  # noqa: E111
  assert error_summary["rejection_breaker_count"] == 0  # noqa: E111
  assert error_summary["open_breaker_count"] == 0  # noqa: E111
  assert error_summary["half_open_breaker_count"] == 0  # noqa: E111
  assert error_summary["unknown_breaker_count"] == 0  # noqa: E111
  assert error_summary["open_breakers"] == []  # noqa: E111
  assert error_summary["open_breaker_ids"] == []  # noqa: E111
  runtime_store = stats["runtime_store"]  # noqa: E111
  assert runtime_store["snapshot"]["status"] == "current"  # noqa: E111
  assert runtime_store["history"]["checks"] == 1  # noqa: E111
  assert error_summary["half_open_breakers"] == []  # noqa: E111
  assert error_summary["half_open_breaker_ids"] == []  # noqa: E111
  assert error_summary["unknown_breakers"] == []  # noqa: E111
  assert error_summary["unknown_breaker_ids"] == []  # noqa: E111
  assert error_summary["rejection_breaker_ids"] == []  # noqa: E111
  assert error_summary["rejection_breakers"] == []  # noqa: E111

  performance_metrics = stats.get("performance_metrics")  # noqa: E111
  if isinstance(performance_metrics, dict):  # noqa: E111
    assert "schema_version" not in performance_metrics
    assert performance_metrics["open_breakers"] == []
    assert performance_metrics["open_breaker_ids"] == []
    assert performance_metrics["half_open_breakers"] == []
    assert performance_metrics["half_open_breaker_ids"] == []
    assert performance_metrics["unknown_breakers"] == []
    assert performance_metrics["unknown_breaker_ids"] == []
    assert performance_metrics["rejection_breaker_ids"] == []
    assert performance_metrics["rejection_breakers"] == []


def test_build_runtime_statistics_includes_guard_metrics(monkeypatch) -> None:
  """Runtime statistics should export guard counters alongside rejection metrics."""  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=None)  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={
      "service_guard_metrics": {
        "executed": 3,
        "skipped": 1,
        "reasons": {"missing_instance": 1, "": 5, "negative": -2},
        "last_results": [
          {
            "domain": "notify",
            "service": "send",
            "executed": False,
            "reason": "missing_instance",
          },
          "invalid",
        ],
      }
    },
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  monkeypatch.setattr(tasks, "collect_resilience_diagnostics", lambda *_: None)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_runtime_statistics(coordinator)  # noqa: E111

  service_execution = stats["service_execution"]  # noqa: E111
  guard_metrics = service_execution["guard_metrics"]  # noqa: E111
  assert guard_metrics["executed"] == 3  # noqa: E111
  assert guard_metrics["skipped"] == 1  # noqa: E111
  assert guard_metrics["reasons"] == {"missing_instance": 1}  # noqa: E111
  assert guard_metrics["last_results"] == [  # noqa: E111
    {
      "domain": "notify",
      "executed": False,
      "reason": "missing_instance",
      "service": "send",
    }
  ]
  assert service_execution["rejection_metrics"] is stats["rejection_metrics"]  # noqa: E111
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111

  stored_guard_metrics = runtime_data.performance_stats["service_guard_metrics"]  # noqa: E111
  assert stored_guard_metrics["executed"] == 3  # noqa: E111
  assert stored_guard_metrics["skipped"] == 1  # noqa: E111
  assert stored_guard_metrics["reasons"] == {"missing_instance": 1}  # noqa: E111
  assert stored_guard_metrics["last_results"] == [  # noqa: E111
    {
      "domain": "notify",
      "executed": False,
      "reason": "missing_instance",
      "service": "send",
    }
  ]


def test_build_runtime_statistics_defaults_guard_metrics(monkeypatch) -> None:
  """Guard metrics should fall back to zeroed counters when none recorded."""  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=None)  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  monkeypatch.setattr(tasks, "collect_resilience_diagnostics", lambda *_: None)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_runtime_statistics(coordinator)  # noqa: E111

  guard_metrics = stats["service_execution"]["guard_metrics"]  # noqa: E111
  assert guard_metrics == {  # noqa: E111
    "executed": 0,
    "skipped": 0,
    "reasons": {},
    "last_results": [],
  }
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111


def test_build_runtime_statistics_captures_bool_coercion_summary(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Runtime statistics should include and persist bool coercion telemetry."""  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=None)  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  monkeypatch.setattr(tasks, "collect_resilience_diagnostics", lambda *_: None)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111
  try:  # noqa: E111
    record_bool_coercion_event(
      value="yes", default=False, result=True, reason="truthy_string"
    )

    stats = tasks.build_runtime_statistics(coordinator)
  finally:  # noqa: E111
    reset_bool_coercion_metrics()

  assert "bool_coercion" in stats  # noqa: E111
  summary = stats["bool_coercion"]  # noqa: E111
  assert summary["recorded"] is True  # noqa: E111
  assert summary["total"] == 1  # noqa: E111
  assert summary["reason_counts"]["truthy_string"] == 1  # noqa: E111
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111

  stored = runtime_data.performance_stats.get("bool_coercion_summary")  # noqa: E111
  assert stored is not None  # noqa: E111
  assert stored["total"] == 1  # noqa: E111
  assert stored["reason_counts"]["truthy_string"] == 1  # noqa: E111


def test_build_runtime_statistics_threads_rejection_metrics(monkeypatch) -> None:
  """Runtime statistics should expose rejection metrics within error summaries."""  # noqa: E111

  breaker = SimpleNamespace(  # noqa: E111
    state=SimpleNamespace(value="open"),
    failure_count=3,
    success_count=5,
    last_failure_time=1700000000.0,
    last_state_change=1700000100.0,
    total_calls=10,
    total_failures=3,
    total_successes=7,
    rejected_calls=2,
    last_rejection_time=1700000150.0,
  )
  resilience_manager = _DummyResilience({"api": breaker})  # noqa: E111
  coordinator = _build_coordinator(resilience_manager=resilience_manager)  # noqa: E111

  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_runtime_statistics(coordinator)  # noqa: E111

  rejection_metrics = stats["rejection_metrics"]  # noqa: E111
  assert rejection_metrics["schema_version"] == 4  # noqa: E111
  assert stats["error_summary"]["rejected_call_count"] == 2  # noqa: E111
  assert stats["error_summary"]["rejection_breaker_count"] == 1  # noqa: E111
  assert stats["error_summary"]["rejection_rate"] == rejection_metrics["rejection_rate"]  # noqa: E111
  assert rejection_metrics["rejected_call_count"] == 2  # noqa: E111
  assert rejection_metrics["rejection_breaker_count"] == 1  # noqa: E111
  assert pytest.approx(rejection_metrics["rejection_rate"], rel=1e-6) == pytest.approx(  # noqa: E111
    2 / 12, rel=1e-6
  )
  assert rejection_metrics["last_rejection_time"] == 1700000150.0  # noqa: E111
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
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111
  error_summary = stats["error_summary"]  # noqa: E111
  assert error_summary["open_breaker_count"] == 1  # noqa: E111
  assert error_summary["half_open_breaker_count"] == 0  # noqa: E111
  assert error_summary["unknown_breaker_count"] == 0  # noqa: E111
  assert error_summary["open_breakers"] == ["api"]  # noqa: E111
  assert error_summary["open_breaker_ids"] == ["api"]  # noqa: E111
  assert error_summary["half_open_breakers"] == []  # noqa: E111
  assert error_summary["half_open_breaker_ids"] == []  # noqa: E111
  assert error_summary["unknown_breakers"] == []  # noqa: E111
  assert error_summary["unknown_breaker_ids"] == []  # noqa: E111
  assert error_summary["rejection_breaker_ids"] == ["api"]  # noqa: E111
  assert error_summary["rejection_breakers"] == ["api"]  # noqa: E111


def test_build_update_statistics_handles_missing_resilience_manager(
  monkeypatch,
) -> None:
  """Coordinator stats should degrade gracefully when resilience manager is absent."""  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=_MissingResilience())  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_update_statistics(coordinator)  # noqa: E111

  assert "resilience" not in stats  # noqa: E111
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111


def test_build_update_statistics_logs_and_skips_on_resilience_error(
  monkeypatch,
) -> None:
  """Coordinator stats should skip resilience telemetry when collection fails."""  # noqa: E111

  coordinator = _build_coordinator(resilience_manager=_BrokenResilience())  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_update_statistics(coordinator)  # noqa: E111

  assert "resilience" not in stats  # noqa: E111
  assert stats["runtime_store"]["snapshot"]["status"] == "current"  # noqa: E111


def test_build_update_statistics_summarises_options_when_uncached(monkeypatch) -> None:
  """Coordinator stats should derive reconfigure telemetry from entry options."""  # noqa: E111

  telemetry = {  # noqa: E111
    "requested_profile": "advanced",
    "previous_profile": "standard",
    "dogs_count": 3,
    "estimated_entities": 36,
    "timestamp": "2024-03-01T10:00:00+00:00",
    "version": 2,
    "compatibility_warnings": ["check_gps"],
    "health_summary": {
      "healthy": False,
      "issues": ["vet_followup"],
      "warnings": ["monitor_weight"],
    },
  }
  options = {"reconfigure_telemetry": telemetry, "previous_profile": "standard"}  # noqa: E111
  coordinator = _build_coordinator(options)  # noqa: E111

  runtime_data = SimpleNamespace(  # noqa: E111
    data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
    performance_stats={},
  )
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  _patch_runtime_store(monkeypatch)  # noqa: E111

  stats = tasks.build_update_statistics(coordinator)  # noqa: E111

  summary = stats["reconfigure"]  # noqa: E111
  assert summary["requested_profile"] == "advanced"  # noqa: E111
  assert summary["warning_count"] == 1  # noqa: E111
  assert summary["health_issue_count"] == 1  # noqa: E111
  assert summary["healthy"] is False  # noqa: E111


@pytest.mark.asyncio
async def test_run_maintenance_records_success(monkeypatch) -> None:
  """Coordinator maintenance should record structured telemetry on success."""  # noqa: E111

  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  modules = _MaintenanceModules(expired=4)  # noqa: E111
  metrics = _MaintenanceMetrics(consecutive_errors=2)  # noqa: E111
  coordinator = SimpleNamespace(  # noqa: E111
    _modules=modules,
    _metrics=metrics,
    last_update_success=True,
    last_update_time=dt_util.utcnow() - timedelta(hours=3),
    hass=object(),
    config_entry=SimpleNamespace(entry_id="entry"),
    logger=_DummyLogger(),
  )

  diagnostics_payload = {"snapshots": {"modules": {"stats": {"entries": 2}}}}  # noqa: E111

  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    tasks, "capture_cache_diagnostics", lambda *_: diagnostics_payload
  )

  await tasks.run_maintenance(coordinator)  # noqa: E111

  maintenance_last = runtime_data.performance_stats["maintenance_history"][-1]  # noqa: E111
  assert maintenance_last["task"] == "coordinator_maintenance"  # noqa: E111
  assert maintenance_last["status"] == "success"  # noqa: E111
  assert maintenance_last["details"]["expired_entries"] == 4  # noqa: E111
  assert maintenance_last["details"]["cache_snapshot"] is True  # noqa: E111
  assert maintenance_last["details"]["consecutive_errors_reset"] == 2  # noqa: E111
  assert maintenance_last["diagnostics"] == diagnostics_payload  # noqa: E111
  assert maintenance_last["metadata"] == {  # noqa: E111
    "schedule": "hourly",
    "runtime_available": True,
  }
  assert maintenance_last["details"]["hours_since_last_update"] >= 3.0  # noqa: E111
  assert metrics.reset_calls == 1  # noqa: E111


@pytest.mark.asyncio
async def test_run_maintenance_records_failure(monkeypatch) -> None:
  """Coordinator maintenance should capture failures for diagnostics."""  # noqa: E111

  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  modules = _FailingModules()  # noqa: E111
  metrics = _MaintenanceMetrics(consecutive_errors=0)  # noqa: E111
  coordinator = SimpleNamespace(  # noqa: E111
    _modules=modules,
    _metrics=metrics,
    last_update_success=True,
    last_update_time=dt_util.utcnow(),
    hass=object(),
    config_entry=SimpleNamespace(entry_id="entry"),
    logger=_DummyLogger(),
  )

  diagnostics_payload = {"snapshots": {}}  # noqa: E111
  monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    tasks, "capture_cache_diagnostics", lambda *_: diagnostics_payload
  )

  with pytest.raises(RuntimeError, match="cleanup failed"):  # noqa: E111
    await tasks.run_maintenance(coordinator)

  maintenance_last = runtime_data.performance_stats["maintenance_history"][-1]  # noqa: E111
  assert maintenance_last["status"] == "error"  # noqa: E111
  assert maintenance_last["diagnostics"] == diagnostics_payload  # noqa: E111
  assert maintenance_last["metadata"] == {  # noqa: E111
    "schedule": "hourly",
    "runtime_available": True,
  }
  assert maintenance_last["details"] == {}  # noqa: E111
