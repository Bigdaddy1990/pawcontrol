"""Additional branch coverage tests for coordinator_tasks helpers."""

from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import custom_components.pawcontrol.coordinator_tasks as ct


class _EmptyStringId:
    def __str__(self) -> str:
        return ""


class _BadName:
    def __str__(self) -> str:
        raise TypeError("cannot stringify")

    def __repr__(self) -> str:
        return "   "


class _IntValueErrorFloatTypeError:
    def __int__(self) -> int:
        raise ValueError("bad int")

    def __float__(self) -> float:
        raise TypeError("bad float")


class _IntTypeErrorFloatValueError:
    def __int__(self) -> int:
        raise TypeError("bad int")

    def __float__(self) -> float:
        raise ValueError("bad float")


class _BadStr:
    def __str__(self) -> str:
        raise TypeError("bad str")


class _FloatTypeError:
    def __float__(self) -> float:
        raise TypeError("bad float")


class _TimestampFailure:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.tzinfo = None

    def replace(self, *, tzinfo: object) -> "_TimestampFailure":
        self.tzinfo = tzinfo
        return self

    def timestamp(self) -> float:
        raise self._exc


class _PerfContext:
    def __init__(self, perf: Any) -> None:
        self._perf = perf

    def __enter__(self) -> Any:
        return self._perf

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


def _make_stats_coordinator(runtime_stats: dict[str, Any]) -> SimpleNamespace:
    """Build a minimal coordinator stub for runtime statistics helpers."""
    return SimpleNamespace(
        hass=object(),
        config_entry=object(),
        logger=MagicMock(),
        _modules=SimpleNamespace(
            cache_metrics=lambda: SimpleNamespace(entries=0, hit_rate=0.0),
        ),
        _entity_budget=SimpleNamespace(summary=lambda: {}),
        _adaptive_polling=SimpleNamespace(as_diagnostics=lambda: {}),
        _metrics=SimpleNamespace(
            update_statistics=lambda **_: runtime_stats,
            runtime_statistics=lambda **_: runtime_stats,
        ),
        registry={},
        update_interval=timedelta(minutes=1),
        last_update_success_time=None,
    )


@pytest.mark.unit
def test_summarise_resilience_tracks_other_state_and_stale_recovery() -> None:
    summary = ct._summarise_resilience(
        {
            "primary": {
                "state": "open",
                "failure_count": 1,
                "success_count": 1,
                "total_calls": 2,
                "total_failures": 1,
                "total_successes": 1,
                "rejected_calls": 1,
                "last_failure_time": 10.0,
                "last_success_time": 12.0,
                "last_rejection_time": 20.0,
            },
            "secondary": {
                "state": "degraded",
                "failure_count": 1,
                "success_count": 0,
                "total_calls": 1,
                "total_failures": 1,
                "total_successes": 0,
                "last_failure_time": 30.0,
                "last_success_time": 11.0,
                "last_rejection_time": 15.0,
            },
        },
    )

    assert summary["states"]["other"] == 1
    assert summary["last_rejection_breaker_name"] == "primary"
    assert summary["recovery_breaker_id"] is None


@pytest.mark.unit
def test_normalise_breaker_id_falls_back_when_stringified_value_empty() -> None:
    assert ct._normalise_breaker_id("breaker-x", {"id": _EmptyStringId()}) == "breaker-x"


@pytest.mark.unit
def test_merge_rejection_metric_values_handles_empty_sources_and_missing_mapping() -> None:
    target = ct.default_rejection_metrics()
    target["rejected_call_count"] = 7
    ct.merge_rejection_metric_values(target)
    assert target["rejected_call_count"] == 7

    merged: dict[str, Any] = {}
    ct.merge_rejection_metric_values(
        merged,
        {"rejection_rate": 0.5},
        {"failure_reasons": {"": 5, "timeout": -2}},
    )
    assert merged["rejection_rate"] == 0.5
    assert merged["failure_reasons"] == {"timeout": 0}

    empty_mapping: dict[str, Any] = {}
    ct.merge_rejection_metric_values(empty_mapping, {"rejection_rate": 0.1})
    assert empty_mapping["failure_reasons"] == {}


@pytest.mark.unit
def test_derive_rejection_metrics_normalises_failure_reason_mapping() -> None:
    metrics = ct.derive_rejection_metrics(
        {
            "last_failure_reason": "upstream_timeout",
            "failure_reasons": {"": 2, "timeout": "3", "negative": -1},
        },
    )

    assert metrics["last_failure_reason"] == "upstream_timeout"
    assert metrics["failure_reasons"] == {"timeout": 3, "negative": 0}


@pytest.mark.unit
def test_normalise_entity_and_adaptive_diagnostics_missing_values() -> None:
    summary = ct._normalise_entity_budget_summary(
        {"average_utilization": "bad", "peak_utilization": "nan"},
    )
    assert summary["average_utilization"] == 0.0
    assert summary["peak_utilization"] == 0.0

    defaults = ct._normalise_adaptive_diagnostics(123)
    assert defaults["history_samples"] == 0

    partial = ct._normalise_adaptive_diagnostics(
        {
            "target_cycle_ms": None,
            "current_interval_ms": None,
            "average_cycle_ms": None,
            "entity_saturation": None,
            "idle_interval_ms": None,
            "idle_grace_ms": None,
        },
    )
    assert partial["target_cycle_ms"] == 0.0
    assert partial["current_interval_ms"] == 0.0
    assert partial["average_cycle_ms"] == 0.0
    assert partial["entity_saturation"] == 0.0


@pytest.mark.unit
def test_guard_metric_helpers_cover_immutable_payload_paths() -> None:
    guard = ct._normalise_guard_metrics(
        {"reasons": {"": 3, "timeout": 0, "slow": 2}, "last_results": []},
    )
    assert guard["executed"] == 0
    assert guard["skipped"] == 0
    assert guard["reasons"] == {"slow": 2}

    payload = MappingProxyType(
        {"service_guard_metrics": {"executed": 4, "skipped": "2"}},
    )
    resolved = ct.resolve_service_guard_metrics(payload)
    assert resolved["executed"] == 4
    assert resolved["skipped"] == 2


@pytest.mark.unit
def test_resolve_entity_factory_guard_metrics_handles_empty_recent_events() -> None:
    payload = MappingProxyType(
        {
            "entity_factory_guard_metrics": {
                "recent_events": [None, "", 0],
                "enforce_min_runtime": False,
            },
        },
    )

    snapshot = ct.resolve_entity_factory_guard_metrics(payload)
    assert snapshot["last_event"] == "unknown"
    assert "recent_events" not in snapshot
    assert "runtime_floor_delta_ms" not in snapshot


@pytest.mark.unit
def test_stringify_breaker_name_uses_generated_fallback_id() -> None:
    assert ct._stringify_breaker_name(_BadName()).startswith("breaker_")


@pytest.mark.unit
def test_coerce_int_nested_error_paths_return_zero() -> None:
    assert ct._coerce_int(_IntValueErrorFloatTypeError()) == 0
    assert ct._coerce_int(_IntTypeErrorFloatValueError()) == 0


@pytest.mark.unit
def test_normalise_string_list_non_sequence_conversion_paths() -> None:
    assert ct._normalise_string_list(42) == ["42"]
    assert ct._normalise_string_list(_BadStr()) == []


@pytest.mark.unit
@pytest.mark.parametrize("exc", [ValueError("bad"), OverflowError("bad")])
def test_timestamp_from_datetime_handles_as_timestamp_errors(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    def _raise(_value: datetime) -> float:
        raise exc

    monkeypatch.setattr(ct.dt_util, "as_timestamp", _raise, raising=False)
    assert ct._timestamp_from_datetime(datetime.now(UTC)) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc",
    [OverflowError("bad"), OSError("bad"), ValueError("bad")],
)
def test_timestamp_from_datetime_fallback_timestamp_exceptions(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    monkeypatch.setattr(ct.dt_util, "as_timestamp", None, raising=False)
    monkeypatch.setattr(
        ct.dt_util,
        "as_utc",
        lambda _value: _TimestampFailure(exc),
        raising=False,
    )
    assert ct._timestamp_from_datetime(datetime.now(UTC)) is None


@pytest.mark.unit
def test_coerce_float_handles_bool_parse_type_error_and_float_type_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ct._coerce_float(True) == 1.0

    def _raise_parse(_value: str) -> None:
        raise TypeError("unsupported")

    monkeypatch.setattr(ct.dt_util, "parse_datetime", _raise_parse, raising=False)
    assert ct._coerce_float("2026-01-01T00:00:00Z") is None
    assert ct._coerce_float(_FloatTypeError()) is None


@pytest.mark.unit
@pytest.mark.parametrize("exc", [ValueError("bad"), AttributeError("bad")])
def test_coerce_float_date_start_of_day_fallback_branches(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    def _raise(_value: date) -> datetime:
        raise exc

    monkeypatch.setattr(ct.dt_util, "start_of_local_day", _raise, raising=False)
    assert ct._coerce_float(date(2026, 1, 1)) is not None


@pytest.mark.unit
def test_store_resilience_diagnostics_skips_when_runtime_data_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = SimpleNamespace(hass=object(), config_entry=object())
    calls: list[object] = []

    monkeypatch.setattr(ct, "get_runtime_data", lambda *_: None)
    monkeypatch.setattr(
        ct,
        "update_runtime_resilience_diagnostics",
        lambda *_: calls.append("called"),
    )

    ct._store_resilience_diagnostics(coordinator, {"summary": {"total_breakers": 1}})
    assert calls == []


@pytest.mark.unit
def test_collect_resilience_diagnostics_handles_iterable_tuple_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = SimpleNamespace(
        hass=object(),
        config_entry=object(),
        logger=MagicMock(),
        resilience_manager=SimpleNamespace(
            get_all_circuit_breakers=lambda: [
                ("breaker-a", {"state": 5, "failure_count": 1}),
            ],
        ),
    )

    stored: list[dict[str, Any]] = []
    monkeypatch.setattr(
        ct,
        "_store_resilience_diagnostics",
        lambda _coordinator, payload: stored.append(payload),
    )

    diagnostics = ct.collect_resilience_diagnostics(coordinator)
    assert diagnostics["breakers"]["breaker-a"]["state"] == "5"
    assert stored


@pytest.mark.unit
def test_build_update_statistics_keeps_default_rejection_metrics_for_non_mapping_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _make_stats_coordinator({"performance_metrics": {}})

    monkeypatch.setattr(ct, "_fetch_cache_repair_summary", lambda *_: None)
    monkeypatch.setattr(ct, "_fetch_reconfigure_summary", lambda *_: None)
    monkeypatch.setattr(ct, "_build_runtime_store_summary", lambda *_1, **_2: {})
    monkeypatch.setattr(ct, "get_runtime_data", lambda *_: None)
    monkeypatch.setattr(ct, "collect_resilience_diagnostics", lambda *_: {"summary": []})

    stats = ct.build_update_statistics(coordinator)
    assert stats["rejection_metrics"]["rejected_call_count"] == 0


@pytest.mark.unit
def test_build_runtime_statistics_merges_error_summary_and_reconfigure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _make_stats_coordinator(
        {"performance_metrics": {}, "error_summary": {}},
    )

    monkeypatch.setattr(ct, "_fetch_cache_repair_summary", lambda *_: None)
    monkeypatch.setattr(ct, "_fetch_reconfigure_summary", lambda *_: {"source": "options"})
    monkeypatch.setattr(ct, "_build_runtime_store_summary", lambda *_1, **_2: {})
    monkeypatch.setattr(ct, "get_runtime_data", lambda *_: None)
    monkeypatch.setattr(
        ct,
        "update_runtime_bool_coercion_summary",
        lambda *_: {"converted": 0},
    )
    monkeypatch.setattr(ct, "get_runtime_performance_stats", lambda *_: {})
    monkeypatch.setattr(ct, "collect_resilience_diagnostics", lambda *_: {"summary": []})

    stats = ct.build_runtime_statistics(coordinator)
    assert stats["reconfigure"] == {"source": "options"}
    assert stats["performance_metrics"]["rejection_breaker_count"] == 0
    assert stats["error_summary"]["rejected_call_count"] == 0


@pytest.mark.unit
def test_build_runtime_statistics_skips_error_summary_merge_for_non_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _make_stats_coordinator(
        {"performance_metrics": {}, "error_summary": []},
    )

    monkeypatch.setattr(ct, "_fetch_cache_repair_summary", lambda *_: None)
    monkeypatch.setattr(ct, "_fetch_reconfigure_summary", lambda *_: None)
    monkeypatch.setattr(ct, "_build_runtime_store_summary", lambda *_1, **_2: {})
    monkeypatch.setattr(ct, "get_runtime_data", lambda *_: None)
    monkeypatch.setattr(ct, "update_runtime_bool_coercion_summary", lambda *_: {})
    monkeypatch.setattr(ct, "get_runtime_performance_stats", lambda *_: {})
    monkeypatch.setattr(ct, "collect_resilience_diagnostics", lambda *_: {})

    stats = ct.build_runtime_statistics(coordinator)
    assert isinstance(stats["error_summary"], list)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_maintenance_resets_consecutive_errors_after_stable_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    metrics = SimpleNamespace(
        consecutive_errors=3,
        reset_consecutive=MagicMock(),
    )
    coordinator = SimpleNamespace(
        hass=object(),
        config_entry=object(),
        logger=MagicMock(),
        _modules=SimpleNamespace(cleanup_expired=MagicMock(return_value=0)),
        _metrics=metrics,
        last_update_success=True,
        last_update_success_time=now - timedelta(hours=2),
    )

    runtime_data = object()
    perf = SimpleNamespace(mark_failure=MagicMock())
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(ct, "get_runtime_data", lambda *_: runtime_data)
    monkeypatch.setattr(ct.dt_util, "utcnow", lambda: now, raising=False)
    monkeypatch.setattr(ct, "capture_cache_diagnostics", lambda *_: None)
    monkeypatch.setattr(
        ct,
        "record_maintenance_result",
        lambda *_args, **kwargs: recorded.append(kwargs),
    )
    monkeypatch.setattr(
        ct,
        "performance_tracker",
        lambda *_args, **_kwargs: _PerfContext(perf),
    )

    await ct.run_maintenance(coordinator)
    assert metrics.reset_consecutive.called
    assert recorded
    assert recorded[0]["details"]["consecutive_errors_reset"] == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_maintenance_skips_reset_when_stability_period_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    metrics = SimpleNamespace(
        consecutive_errors=2,
        reset_consecutive=MagicMock(),
    )
    coordinator = SimpleNamespace(
        hass=object(),
        config_entry=object(),
        logger=MagicMock(),
        _modules=SimpleNamespace(cleanup_expired=MagicMock(return_value=0)),
        _metrics=metrics,
        last_update_success=True,
        last_update_success_time=now - timedelta(minutes=30),
    )

    perf = SimpleNamespace(mark_failure=MagicMock())
    monkeypatch.setattr(ct, "get_runtime_data", lambda *_: object())
    monkeypatch.setattr(ct.dt_util, "utcnow", lambda: now, raising=False)
    monkeypatch.setattr(ct, "capture_cache_diagnostics", lambda *_: None)
    monkeypatch.setattr(ct, "record_maintenance_result", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ct,
        "performance_tracker",
        lambda *_args, **_kwargs: _PerfContext(perf),
    )

    await ct.run_maintenance(coordinator)
    assert not metrics.reset_consecutive.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_maintenance_error_branch_collects_diagnostics_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = SimpleNamespace(
        hass=object(),
        config_entry=object(),
        logger=MagicMock(),
        _modules=SimpleNamespace(cleanup_expired=MagicMock(side_effect=RuntimeError("boom"))),
        _metrics=SimpleNamespace(consecutive_errors=0),
        last_update_success=False,
    )

    runtime_data = object()
    perf = SimpleNamespace(mark_failure=MagicMock())
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(ct, "get_runtime_data", lambda *_: runtime_data)
    monkeypatch.setattr(ct.dt_util, "utcnow", lambda: datetime.now(UTC), raising=False)
    monkeypatch.setattr(ct, "capture_cache_diagnostics", lambda *_: {"cache": True})
    monkeypatch.setattr(
        ct,
        "record_maintenance_result",
        lambda *_args, **kwargs: recorded.append(kwargs),
    )
    monkeypatch.setattr(
        ct,
        "performance_tracker",
        lambda *_args, **_kwargs: _PerfContext(perf),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await ct.run_maintenance(coordinator)

    assert perf.mark_failure.called
    assert recorded
    assert recorded[0]["status"] == "error"
    assert recorded[0]["diagnostics"] == {"cache": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_maintenance_error_branch_reuses_existing_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = SimpleNamespace(
        hass=object(),
        config_entry=object(),
        logger=MagicMock(),
        _modules=SimpleNamespace(cleanup_expired=MagicMock(return_value=0)),
        _metrics=SimpleNamespace(consecutive_errors=0),
        last_update_success=False,
    )

    runtime_data = object()
    perf = SimpleNamespace(mark_failure=MagicMock())
    calls: list[dict[str, Any]] = []

    def _record(*_args: object, **kwargs: Any) -> None:
        calls.append(kwargs)
        if kwargs.get("status") == "success":
            raise RuntimeError("write failed")

    monkeypatch.setattr(ct, "get_runtime_data", lambda *_: runtime_data)
    monkeypatch.setattr(
        ct.dt_util,
        "utcnow",
        lambda: datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        raising=False,
    )
    monkeypatch.setattr(ct, "capture_cache_diagnostics", lambda *_: {"cache": True})
    monkeypatch.setattr(ct, "record_maintenance_result", _record)
    monkeypatch.setattr(
        ct,
        "performance_tracker",
        lambda *_args, **_kwargs: _PerfContext(perf),
    )

    with pytest.raises(RuntimeError, match="write failed"):
        await ct.run_maintenance(coordinator)

    assert perf.mark_failure.called
    assert len(calls) == 2
    assert calls[0]["status"] == "success"
    assert calls[1]["status"] == "error"
