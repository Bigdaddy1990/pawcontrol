from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from types import SimpleNamespace

import pytest
from custom_components.pawcontrol import coordinator_tasks as tasks
from custom_components.pawcontrol.coordinator_support import CoordinatorMetrics
from homeassistant.util import dt as dt_util


class _DummyLogger:
    def debug(self, *args, **kwargs) -> None:  # pragma: no cover - helpers
        return None

    def info(self, *args, **kwargs) -> None:  # pragma: no cover - helpers
        return None


class _DummyModules:
    def __init__(self, metrics: SimpleNamespace) -> None:
        self._metrics = metrics

    def cache_metrics(self) -> SimpleNamespace:
        return self._metrics


class _DummyBudget:
    def summary(self) -> dict[str, int]:
        return {"active_dogs": 1, "peak_utilization": 40}


class _DummyAdaptivePolling:
    def as_diagnostics(self) -> dict[str, str]:
        return {"mode": "balanced"}


class _DummyResilience:
    def get_all_circuit_breakers(self) -> list[str]:
        return ["analytics"]


class _MaintenanceModules:
    def __init__(self, expired: int = 3) -> None:
        self.expired = expired
        self.calls = 0

    def cleanup_expired(self, now: object) -> int:
        self.calls += 1
        return self.expired


class _FailingModules:
    def cleanup_expired(self, now: object) -> int:
        raise RuntimeError("cleanup failed")


class _MaintenanceMetrics:
    def __init__(self, consecutive_errors: int) -> None:
        self.consecutive_errors = consecutive_errors
        self.reset_calls = 0

    def reset_consecutive(self) -> None:
        self.reset_calls += 1
        self.consecutive_errors = 0


def _build_coordinator(options: Mapping[str, object] | None = None) -> SimpleNamespace:
    cache_metrics = SimpleNamespace(entries=5, hit_rate=80.0, hits=8, misses=2)
    modules = _DummyModules(cache_metrics)
    metrics = CoordinatorMetrics()
    metrics.update_count = 4
    metrics.failed_cycles = 1

    coordinator = SimpleNamespace(
        _modules=modules,
        _metrics=metrics,
        _entity_budget=_DummyBudget(),
        _adaptive_polling=_DummyAdaptivePolling(),
        resilience_manager=_DummyResilience(),
        registry=["dog_a"],
        last_update_time="2024-01-02T00:00:00+00:00",
        update_interval=timedelta(minutes=30),
        hass=object(),
        config_entry=SimpleNamespace(entry_id="entry", options=options or {}),
        logger=_DummyLogger(),
    )

    return coordinator


def test_build_update_statistics_includes_repair_summary(monkeypatch) -> None:
    """Coordinator update statistics should surface repair telemetry."""

    summary = {
        "total_caches": 3,
        "anomaly_count": 2,
        "severity": "warning",
        "generated_at": "2024-01-02T00:00:00+00:00",
        "issues": [{"cache": "adaptive_cache"}],
        "caches_with_errors": ["adaptive_cache"],
        "caches_with_override_flags": ["optimized_cache"],
    }

    coordinator = _build_coordinator()
    reconfigure_summary = {
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
    }

    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: summary),
        performance_stats={"reconfigure_summary": reconfigure_summary},
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    stats = tasks.build_update_statistics(coordinator)

    assert "repairs" in stats
    repairs = stats["repairs"]
    assert repairs["severity"] == "warning"
    assert repairs["anomaly_count"] == 2
    assert repairs["issues"] == 1
    assert repairs["caches_with_errors"] == 1
    assert repairs["caches_with_override_flags"] == 1
    assert "reconfigure" in stats
    assert stats["reconfigure"]["requested_profile"] == "advanced"
    assert stats["reconfigure"]["warning_count"] == 1


def test_build_runtime_statistics_omits_empty_repair_summary(monkeypatch) -> None:
    """Runtime statistics should omit repairs telemetry when unavailable."""

    coordinator = _build_coordinator()
    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: None)
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    stats = tasks.build_runtime_statistics(coordinator)

    assert "repairs" not in stats
    assert "reconfigure" not in stats


def test_build_update_statistics_summarises_options_when_uncached(monkeypatch) -> None:
    """Coordinator stats should derive reconfigure telemetry from entry options."""

    telemetry = {
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
    options = {"reconfigure_telemetry": telemetry, "previous_profile": "standard"}
    coordinator = _build_coordinator(options)

    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
        performance_stats={},
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    stats = tasks.build_update_statistics(coordinator)

    summary = stats["reconfigure"]
    assert summary["requested_profile"] == "advanced"
    assert summary["warning_count"] == 1
    assert summary["health_issue_count"] == 1
    assert summary["healthy"] is False


@pytest.mark.asyncio
async def test_run_maintenance_records_success(monkeypatch) -> None:
    """Coordinator maintenance should record structured telemetry on success."""

    runtime_data = SimpleNamespace(performance_stats={})
    modules = _MaintenanceModules(expired=4)
    metrics = _MaintenanceMetrics(consecutive_errors=2)
    coordinator = SimpleNamespace(
        _modules=modules,
        _metrics=metrics,
        last_update_success=True,
        last_update_time=dt_util.utcnow() - timedelta(hours=3),
        hass=object(),
        config_entry=SimpleNamespace(entry_id="entry"),
        logger=_DummyLogger(),
    )

    diagnostics_payload = {"snapshots": {"modules": {"stats": {"entries": 2}}}}

    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)
    monkeypatch.setattr(
        tasks, "capture_cache_diagnostics", lambda *_: diagnostics_payload
    )

    await tasks.run_maintenance(coordinator)

    maintenance_last = runtime_data.performance_stats["last_maintenance_result"]
    assert maintenance_last["task"] == "coordinator_maintenance"
    assert maintenance_last["status"] == "success"
    assert maintenance_last["details"]["expired_entries"] == 4
    assert maintenance_last["details"]["cache_snapshot"] is True
    assert maintenance_last["details"]["consecutive_errors_reset"] == 2
    assert maintenance_last["diagnostics"]["cache"] == diagnostics_payload
    assert maintenance_last["diagnostics"]["metadata"] == {
        "schedule": "hourly",
        "runtime_available": True,
    }
    assert maintenance_last["details"]["hours_since_last_update"] >= 3.0
    assert metrics.reset_calls == 1


@pytest.mark.asyncio
async def test_run_maintenance_records_failure(monkeypatch) -> None:
    """Coordinator maintenance should capture failures for diagnostics."""

    runtime_data = SimpleNamespace(performance_stats={})
    modules = _FailingModules()
    metrics = _MaintenanceMetrics(consecutive_errors=0)
    coordinator = SimpleNamespace(
        _modules=modules,
        _metrics=metrics,
        last_update_success=True,
        last_update_time=dt_util.utcnow(),
        hass=object(),
        config_entry=SimpleNamespace(entry_id="entry"),
        logger=_DummyLogger(),
    )

    diagnostics_payload = {"snapshots": {}}
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)
    monkeypatch.setattr(
        tasks, "capture_cache_diagnostics", lambda *_: diagnostics_payload
    )

    with pytest.raises(RuntimeError, match="cleanup failed"):
        await tasks.run_maintenance(coordinator)

    maintenance_last = runtime_data.performance_stats["last_maintenance_result"]
    assert maintenance_last["status"] == "error"
    assert maintenance_last["diagnostics"]["cache"] == diagnostics_payload
    assert maintenance_last["diagnostics"]["metadata"] == {
        "schedule": "hourly",
        "runtime_available": True,
    }
    assert "details" not in maintenance_last
