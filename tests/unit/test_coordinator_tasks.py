from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
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
    def __init__(self, payload: object | None = None) -> None:
        self._payload = payload if payload is not None else ["analytics"]

    def get_all_circuit_breakers(self) -> object:
        return self._payload


class _MissingResilience:
    """Simulate a coordinator without a resilience manager interface."""


class _BrokenResilience:
    """Resilience manager stub that raises when queried."""

    def get_all_circuit_breakers(self) -> object:
        raise RuntimeError("boom")


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


def _build_coordinator(
    options: Mapping[str, object] | None = None,
    resilience_manager: object | None = None,
) -> SimpleNamespace:
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
        resilience_manager=resilience_manager or _DummyResilience(),
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


def test_build_update_statistics_serialises_resilience_payload(monkeypatch) -> None:
    """Coordinator update statistics should expose resilience telemetry when present."""

    breaker = SimpleNamespace(
        state=SimpleNamespace(value="closed"),
        failure_count=2,
        success_count=8,
        last_failure_time=1700000000.0,
        last_state_change=1700000100.0,
        total_calls=10,
        total_failures=2,
        total_successes=8,
    )
    resilience_manager = _DummyResilience({"api": breaker})
    coordinator = _build_coordinator(resilience_manager=resilience_manager)

    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
        performance_stats={},
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    stats = tasks.build_update_statistics(coordinator)

    assert "resilience" in stats
    resilience = stats["resilience"]
    assert resilience["breakers"]["api"]["breaker_id"] == "api"
    assert resilience["breakers"]["api"]["state"] == "closed"
    assert resilience["breakers"]["api"]["failure_count"] == 2
    assert resilience["summary"]["total_breakers"] == 1
    assert resilience["summary"]["states"]["closed"] == 1
    assert resilience["summary"]["open_breaker_count"] == 0
    assert resilience["summary"]["half_open_breaker_count"] == 0


def test_collect_resilience_diagnostics_persists_summary(monkeypatch) -> None:
    """Collected resilience summaries should persist into runtime performance stats."""

    breaker = SimpleNamespace(
        state=SimpleNamespace(value="open"),
        failure_count=5,
        success_count=1,
        last_failure_time=1700000200.0,
        last_state_change=1700000300.0,
        total_calls=6,
        total_failures=5,
        total_successes=1,
    )
    resilience_manager = _DummyResilience({"automation": breaker})
    coordinator = _build_coordinator(resilience_manager=resilience_manager)

    runtime_data = SimpleNamespace(performance_stats={})
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    payload = tasks.collect_resilience_diagnostics(coordinator)

    stored = runtime_data.performance_stats["resilience_summary"]
    assert stored["total_breakers"] == 1
    assert stored["open_breaker_count"] == 1
    assert stored["half_open_breaker_count"] == 0
    assert payload["breakers"]["automation"]["breaker_id"] == "automation"
    assert payload["summary"]["open_breakers"] == ["automation"]


def test_collect_resilience_diagnostics_clears_summary_when_no_breakers(
    monkeypatch,
) -> None:
    """Persisted resilience summaries should be cleared when no breakers exist."""

    summary = {
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
        "last_failure_time": None,
        "last_state_change": None,
        "open_breaker_count": 0,
        "half_open_breaker_count": 0,
    }

    runtime_data = SimpleNamespace(
        performance_stats={"resilience_summary": dict(summary)}
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    coordinator = _build_coordinator(resilience_manager=_DummyResilience({}))

    payload = tasks.collect_resilience_diagnostics(coordinator)

    assert payload == {}
    assert "resilience_summary" not in runtime_data.performance_stats


def test_collect_resilience_diagnostics_clears_summary_without_manager(
    monkeypatch,
) -> None:
    """Persisted resilience summaries should be cleared when manager is unavailable."""

    summary = {
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
    }

    runtime_data = SimpleNamespace(
        performance_stats={"resilience_summary": dict(summary)}
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    coordinator = _build_coordinator(resilience_manager=_MissingResilience())

    payload = tasks.collect_resilience_diagnostics(coordinator)

    assert payload == {}
    assert "resilience_summary" not in runtime_data.performance_stats


def test_collect_resilience_diagnostics_clears_summary_on_error(monkeypatch) -> None:
    """Resilience summaries should be cleared when collection raises an exception."""

    summary = {
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
    }

    runtime_data = SimpleNamespace(
        performance_stats={"resilience_summary": dict(summary)}
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    coordinator = _build_coordinator(resilience_manager=_BrokenResilience())

    payload = tasks.collect_resilience_diagnostics(coordinator)

    assert payload == {}
    assert "resilience_summary" not in runtime_data.performance_stats


def test_collect_resilience_diagnostics_clears_summary_on_invalid_payload(
    monkeypatch,
) -> None:
    """Resilience summaries should be cleared when payload is not iterable."""

    summary = {
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
    }

    runtime_data = SimpleNamespace(
        performance_stats={"resilience_summary": dict(summary)}
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    class _InvalidResilience:
        def get_all_circuit_breakers(self) -> object:
            return object()

    coordinator = _build_coordinator(resilience_manager=_InvalidResilience())

    payload = tasks.collect_resilience_diagnostics(coordinator)

    assert payload == {}
    assert "resilience_summary" not in runtime_data.performance_stats


def test_collect_resilience_diagnostics_coerces_stats_values(monkeypatch) -> None:
    """Circuit breaker stats should coerce mixed-value payloads safely."""

    runtime_data = SimpleNamespace(performance_stats={})
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    class _MixedStats(dict):
        def __init__(self) -> None:
            super().__init__(
                state="HALF_OPEN",
                failure_count="3",
                success_count=None,
                last_failure_time="1700000000.5",
                last_state_change="not-a-number",
                total_calls="12",
                total_failures="4",
                total_successes=None,
            )

    resilience_manager = _DummyResilience({"mixed": _MixedStats()})
    coordinator = _build_coordinator(resilience_manager=resilience_manager)

    payload = tasks.collect_resilience_diagnostics(coordinator)

    entry = payload["breakers"]["mixed"]
    assert entry["breaker_id"] == "mixed"
    assert entry["state"] == "HALF_OPEN"
    assert entry["failure_count"] == 3
    assert entry["success_count"] == 0
    assert entry["total_calls"] == 12
    assert entry["total_failures"] == 4
    assert entry["total_successes"] == 0
    assert entry["last_failure_time"] == pytest.approx(1700000000.5)
    assert entry["last_state_change"] is None


def test_collect_resilience_diagnostics_defaults_unknown_state(monkeypatch) -> None:
    """Collector should normalise missing or blank states to "unknown"."""

    runtime_data = SimpleNamespace(performance_stats={})
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    class _MissingState(dict):
        def __init__(self) -> None:
            super().__init__(
                failure_count=1,
                success_count=0,
                total_calls=1,
                total_failures=1,
                total_successes=0,
            )

    class _BlankState(dict):
        def __init__(self) -> None:
            super().__init__(
                state="   ",
                failure_count=0,
                success_count=2,
                total_calls=2,
                total_failures=0,
                total_successes=2,
            )

    resilience_manager = _DummyResilience(
        {"legacy": _MissingState(), "blank": _BlankState()}
    )
    coordinator = _build_coordinator(resilience_manager=resilience_manager)

    payload = tasks.collect_resilience_diagnostics(coordinator)

    breakers = payload["breakers"]
    assert breakers["legacy"]["state"] == "unknown"
    assert breakers["blank"]["state"] == "unknown"

    summary = payload["summary"]
    assert summary["states"]["unknown"] == 2
    assert summary["states"]["other"] == 0
    assert summary["unknown_breakers"] == ["legacy", "blank"]
    assert summary["unknown_breaker_ids"] == ["legacy", "blank"]
    assert summary["unknown_breaker_count"] == 2


def test_summarise_resilience_normalises_state_metadata() -> None:
    """State aggregation should coerce whitespace, enums, and hyphenated values."""

    class _EnumState:
        def __init__(self, value: str) -> None:
            self.value = value

    summary = tasks._summarise_resilience(
        {
            "legacy": {"state": None, "breaker_id": "legacy"},
            "spaced": {"state": "  Open  ", "breaker_id": "api"},
            "hyphen": {"state": "half-open", "breaker_id": "fallback"},
            "enum": {"state": _EnumState("CLOSED"), "breaker_id": "enum"},
        }
    )

    assert summary["states"]["closed"] == 1
    assert summary["states"]["open"] == 1
    assert summary["states"]["half_open"] == 1
    assert summary["states"]["unknown"] == 1
    assert summary["open_breakers"] == ["spaced"]
    assert summary["open_breaker_ids"] == ["api"]
    assert summary["half_open_breakers"] == ["hyphen"]
    assert summary["half_open_breaker_ids"] == ["fallback"]
    assert summary["unknown_breakers"] == ["legacy"]
    assert summary["unknown_breaker_ids"] == ["legacy"]
    assert summary["unknown_breaker_count"] == 1


def test_summarise_resilience_uses_extended_breaker_identifiers() -> None:
    """Aggregation should honour identifier metadata when breaker IDs are missing."""

    summary = tasks._summarise_resilience(
        {
            "api": {"state": "OPEN", "identifier": "api-primary"},
            "fallback": {"state": "half_open", "name": "fallback-service"},
        }
    )

    assert summary["open_breaker_ids"] == ["api-primary"]
    assert summary["half_open_breaker_ids"] == ["fallback-service"]


def test_collect_resilience_diagnostics_prefers_breaker_metadata(monkeypatch) -> None:
    """Collector should use embedded breaker identifiers when provided."""

    runtime_data = SimpleNamespace(performance_stats={})
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    class _MetadataStats(dict):
        def __init__(self) -> None:
            super().__init__(
                breaker_id="api-primary",
                state="OPEN",
                failure_count=2,
                success_count=0,
                total_calls=2,
                total_failures=2,
                total_successes=0,
                last_failure_time=100.0,
            )

    resilience_manager = _DummyResilience({"api": _MetadataStats()})
    coordinator = _build_coordinator(resilience_manager=resilience_manager)

    payload = tasks.collect_resilience_diagnostics(coordinator)

    breakers = payload["breakers"]
    assert set(breakers) == {"api"}
    entry = breakers["api"]
    assert entry["breaker_id"] == "api-primary"

    summary = payload["summary"]
    assert summary["open_breakers"] == ["api"]
    assert summary["open_breaker_count"] == 1
    assert summary["open_breaker_ids"] == ["api-primary"]
    assert summary["unknown_breaker_count"] == 0
    assert summary["unknown_breakers"] == []
    assert summary["unknown_breaker_ids"] == []
    assert "recovery_breaker_name" not in summary

    stored = runtime_data.performance_stats["resilience_summary"]
    assert stored["open_breakers"] == ["api"]
    assert stored["open_breaker_count"] == 1
    assert stored["open_breaker_ids"] == ["api-primary"]
    assert stored["unknown_breaker_count"] == 0
    assert stored["unknown_breakers"] == []
    assert stored["unknown_breaker_ids"] == []
    assert "recovery_breaker_name" not in stored


def test_collect_resilience_diagnostics_converts_temporal_values(monkeypatch) -> None:
    """Resilience telemetry should normalise datetime, date, and ISO timestamps."""

    failure_time = datetime(2024, 1, 2, 12, 30, tzinfo=UTC)
    state_change_iso = "2024-03-01T08:15:00+00:00"
    fallback_date = date(2024, 4, 5)

    class _TemporalStats(dict):
        def __init__(self) -> None:
            super().__init__(
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

    resilience_manager = _DummyResilience({"temporal": _TemporalStats()})
    coordinator = _build_coordinator(resilience_manager=resilience_manager)

    runtime_data = SimpleNamespace(performance_stats={})
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    payload = tasks.collect_resilience_diagnostics(coordinator)

    entry = payload["breakers"]["temporal"]
    assert entry["breaker_id"] == "temporal"
    expected_failure = tasks._timestamp_from_datetime(failure_time)
    assert expected_failure is not None
    parsed_state_change = dt_util.parse_datetime(state_change_iso)
    assert parsed_state_change is not None
    expected_state_change = tasks._timestamp_from_datetime(parsed_state_change)
    assert expected_state_change is not None

    assert entry["last_failure_time"] == pytest.approx(expected_failure)
    assert entry["last_state_change"] == pytest.approx(expected_state_change)

    fallback = entry.get("last_success_time")
    assert fallback is not None
    try:
        start_of_day = dt_util.start_of_local_day(fallback_date)
    except AttributeError:
        start_of_day = datetime.combine(fallback_date, datetime.min.time(), tzinfo=UTC)
    expected_success = tasks._timestamp_from_datetime(start_of_day)
    assert expected_success is not None
    assert fallback == pytest.approx(expected_success)

    summary = payload["summary"]
    assert summary["last_success_time"] == pytest.approx(expected_success)
    assert summary["recovery_latency"] == pytest.approx(
        expected_success - expected_failure
    )
    assert summary["recovery_breaker_id"] == "temporal"
    assert summary["recovery_breaker_name"] == "temporal"
    assert summary["open_breaker_ids"] == ["temporal"]

    stored = runtime_data.performance_stats["resilience_summary"]
    assert stored["last_failure_time"] == pytest.approx(expected_failure)
    assert stored["last_state_change"] == pytest.approx(expected_state_change)
    assert stored["last_success_time"] == pytest.approx(expected_success)
    assert stored["recovery_latency"] == pytest.approx(
        expected_success - expected_failure
    )
    assert stored["recovery_breaker_id"] == "temporal"
    assert stored["recovery_breaker_name"] == "temporal"
    assert stored["open_breaker_ids"] == ["temporal"]


def test_collect_resilience_diagnostics_handles_unrecovered_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery latency should be omitted when success precedes the latest failure."""

    class _Unrecovered(dict):
        def __init__(self) -> None:
            super().__init__(
                state="OPEN",
                failure_count=1,
                success_count=0,
                total_calls=5,
                total_failures=1,
                total_successes=4,
                last_failure_time=200.0,
                last_success_time=150.0,
            )

    resilience_manager = _DummyResilience({"api": _Unrecovered()})
    coordinator = _build_coordinator(resilience_manager=resilience_manager)

    runtime_data = SimpleNamespace(performance_stats={})
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    payload = tasks.collect_resilience_diagnostics(coordinator)

    summary = payload["summary"]
    assert summary["recovery_latency"] is None
    assert summary["recovery_breaker_id"] is None
    assert "recovery_breaker_name" not in summary
    assert summary["open_breaker_ids"] == ["api"]

    stored = runtime_data.performance_stats["resilience_summary"]
    assert stored["recovery_latency"] is None
    assert stored["recovery_breaker_id"] is None
    assert "recovery_breaker_name" not in stored
    assert stored["open_breaker_ids"] == ["api"]


def test_collect_resilience_diagnostics_pairs_latest_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Latest recovery latency should pair success with its originating breaker."""

    stale_breaker = {
        "state": "OPEN",
        "failure_count": 4,
        "success_count": 1,
        "total_calls": 6,
        "total_failures": 4,
        "total_successes": 2,
        "last_failure_time": 200.0,
        "last_success_time": 100.0,
    }
    recovered_breaker = {
        "state": "CLOSED",
        "failure_count": 3,
        "success_count": 6,
        "total_calls": 12,
        "total_failures": 3,
        "total_successes": 9,
        "last_failure_time": 150.0,
        "last_success_time": 300.0,
    }

    resilience_manager = _DummyResilience(
        {"stale": stale_breaker, "recovered": recovered_breaker}
    )
    coordinator = _build_coordinator(resilience_manager=resilience_manager)

    runtime_data = SimpleNamespace(performance_stats={})
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    payload = tasks.collect_resilience_diagnostics(coordinator)

    summary = payload["summary"]
    assert summary["last_failure_time"] == 200.0
    assert summary["last_success_time"] == 300.0
    assert summary["recovery_latency"] == pytest.approx(150.0)
    assert summary["recovery_breaker_id"] == "recovered"
    assert summary["recovery_breaker_name"] == "recovered"
    assert summary["open_breaker_ids"] == ["stale"]

    stored = runtime_data.performance_stats["resilience_summary"]
    assert stored["recovery_latency"] == pytest.approx(150.0)
    assert stored["recovery_breaker_id"] == "recovered"
    assert stored["recovery_breaker_name"] == "recovered"
    assert stored["open_breaker_ids"] == ["stale"]


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


def test_build_runtime_statistics_omits_empty_resilience(monkeypatch) -> None:
    """Runtime statistics should skip resilience telemetry when no payload is available."""

    coordinator = _build_coordinator(resilience_manager=_DummyResilience({}))
    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: None)
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    stats = tasks.build_runtime_statistics(coordinator)

    assert "resilience" not in stats


def test_build_update_statistics_handles_missing_resilience_manager(
    monkeypatch,
) -> None:
    """Coordinator stats should degrade gracefully when resilience manager is absent."""

    coordinator = _build_coordinator(resilience_manager=_MissingResilience())
    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
        performance_stats={},
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    stats = tasks.build_update_statistics(coordinator)

    assert "resilience" not in stats


def test_build_update_statistics_logs_and_skips_on_resilience_error(
    monkeypatch,
) -> None:
    """Coordinator stats should skip resilience telemetry when collection fails."""

    coordinator = _build_coordinator(resilience_manager=_BrokenResilience())
    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(cache_repair_summary=lambda: None),
        performance_stats={},
    )
    monkeypatch.setattr(tasks, "get_runtime_data", lambda *_: runtime_data)

    stats = tasks.build_update_statistics(coordinator)

    assert "resilience" not in stats


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
