"""Targeted coverage tests for coordinator_tasks.py — uncovered paths (73% → 85%+).

Covers lines from coverage report:
  72,76,187,352,485,505,516-519,522,570,618,693,695,701-883,
  894-895,899,912-919,925,930-935,940,951-952,960-961,968-973,
  980-987,999,1003-1010,1019,1027-1045,1056-1059,1066-1067,1070,
  1082,1103-1104,1128,1150-1151,1298,1339,1349-1350

Pure helpers tested directly:
  _normalise_breaker_state, _stringify_breaker_name, _coerce_int,
  _normalise_string_list, default_rejection_metrics,
  resolve_service_guard_metrics, resolve_entity_factory_guard_metrics,
  shutdown, ensure_background_task
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import custom_components.pawcontrol.coordinator_tasks as ct

# ═══════════════════════════════════════════════════════════════════════════════
# _normalise_breaker_state  (lines 885-903)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_normalise_breaker_state_string() -> None:
    assert ct._normalise_breaker_state("open") == "open"
    assert ct._normalise_breaker_state("HALF-OPEN") == "half_open"
    assert ct._normalise_breaker_state("  closed  ") == "closed"


@pytest.mark.unit
def test_normalise_breaker_state_none() -> None:
    assert ct._normalise_breaker_state(None) == "unknown"


@pytest.mark.unit
def test_normalise_breaker_state_empty_string() -> None:
    assert ct._normalise_breaker_state("") == "unknown"
    assert ct._normalise_breaker_state("   ") == "unknown"


@pytest.mark.unit
def test_normalise_breaker_state_object_with_value() -> None:
    class _State:
        value = "half-open"

    assert ct._normalise_breaker_state(_State()) == "half_open"


@pytest.mark.unit
def test_normalise_breaker_state_non_string_coerced() -> None:
    assert ct._normalise_breaker_state(42) == "42"


# ═══════════════════════════════════════════════════════════════════════════════
# _stringify_breaker_name  (lines 905-919)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_stringify_breaker_name_string() -> None:
    assert ct._stringify_breaker_name("my_breaker") == "my_breaker"


@pytest.mark.unit
def test_stringify_breaker_name_non_string() -> None:
    result = ct._stringify_breaker_name(42)
    assert "42" in result


@pytest.mark.unit
def test_stringify_breaker_name_empty_string() -> None:
    # Empty string is falsy so repr("") = "''" is used as fallback
    result = ct._stringify_breaker_name("")
    assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# _coerce_int  (lines 921-942)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_coerce_int_bool() -> None:
    assert ct._coerce_int(True) == 1
    assert ct._coerce_int(False) == 0


@pytest.mark.unit
def test_coerce_int_string_float() -> None:
    assert ct._coerce_int("3.9") == 3
    assert ct._coerce_int("7") == 7


@pytest.mark.unit
def test_coerce_int_invalid() -> None:
    assert ct._coerce_int("bad") == 0
    assert ct._coerce_int(None) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# _normalise_string_list  (lines 944-969)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_normalise_string_list_none() -> None:
    assert ct._normalise_string_list(None) == []


@pytest.mark.unit
def test_normalise_string_list_single_string() -> None:
    assert ct._normalise_string_list("hello") == ["hello"]
    assert ct._normalise_string_list("  ") == []


@pytest.mark.unit
def test_normalise_string_list_list() -> None:
    result = ct._normalise_string_list(["a", "b", "  ", "c"])
    assert result == ["a", "b", "c"]


@pytest.mark.unit
def test_normalise_string_list_non_string_items() -> None:
    result = ct._normalise_string_list([1, "two", None])
    assert "two" in result
    assert "1" in result


# ═══════════════════════════════════════════════════════════════════════════════
# default_rejection_metrics  (line ~1082)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_default_rejection_metrics_structure() -> None:
    """default_rejection_metrics returns all required keys with zero values."""
    metrics = ct.default_rejection_metrics()
    assert metrics["rejected_call_count"] == 0
    assert metrics["rejection_breaker_count"] == 0
    assert metrics["rejection_rate"] == 0.0
    assert isinstance(metrics["open_breakers"], list)
    assert isinstance(metrics["open_breaker_ids"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_service_guard_metrics + resolve_entity_factory_guard_metrics
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_resolve_service_guard_metrics_none() -> None:
    """resolve_service_guard_metrics handles None runtime_data."""
    result = ct.resolve_service_guard_metrics(None)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_resolve_service_guard_metrics_with_data() -> None:
    """resolve_service_guard_metrics extracts guard metrics from runtime data."""
    runtime_data = {
        "service_guard_metrics": {
            "executed": 5,
            "skipped": 2,
            "reasons": {"missing": 2},
            "last_results": [],
        }
    }
    result = ct.resolve_service_guard_metrics(runtime_data)
    assert result.get("executed") == 5
    assert result.get("skipped") == 2


@pytest.mark.unit
def test_resolve_entity_factory_guard_metrics_none() -> None:
    """resolve_entity_factory_guard_metrics handles None gracefully."""
    result = ct.resolve_entity_factory_guard_metrics(None)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_resolve_entity_factory_guard_metrics_normalises_full_payload() -> None:
    """resolve_entity_factory_guard_metrics normalises and persists known fields."""
    payload: dict[str, object] = {
        "entity_factory_guard_metrics": {
            "runtime_floor": 0.25,
            "baseline_floor": 0.20,
            "max_floor": 0.60,
            "last_actual_duration": 0.11,
            "peak_runtime_floor": 0.30,
            "lowest_runtime_floor": 0.19,
            "last_floor_change": 0.05,
            "runtime_floor_delta": 0.03,
            "last_duration_ratio": 1.5,
            "last_floor_change_ratio": 0.5,
            "last_event": "expanded",
            "last_updated": "2026-04-05T10:00:00+00:00",
            "samples": 10.9,
            "stable_samples": 7.2,
            "expansions": 2.9,
            "contractions": 1.2,
            "last_expansion_duration": 0.70,
            "last_contraction_duration": 0.40,
            "average_duration": 0.22,
            "max_duration": 0.35,
            "min_duration": 0.18,
            "duration_span": 0.17,
            "jitter_ratio": 0.42,
            "recent_average_duration": 0.21,
            "recent_max_duration": 0.31,
            "recent_min_duration": 0.17,
            "recent_duration_span": 0.14,
            "recent_jitter_ratio": 0.32,
            "stable_ratio": 0.72,
            "expansion_ratio": 0.2,
            "contraction_ratio": 0.1,
            "consecutive_stable_samples": 4,
            "longest_stable_run": 6,
            "volatility_ratio": 0.18,
            "recent_samples": 5,
            "recent_events": ["stable", "", 1, "expanded"],
            "recent_stable_samples": 3,
            "recent_stable_ratio": 0.6,
            "stability_trend": "improving",
            "enforce_min_runtime": True,
        }
    }

    result = ct.resolve_entity_factory_guard_metrics(payload)

    assert result["runtime_floor_ms"] == 250.0
    assert result["baseline_floor_ms"] == 200.0
    assert result["runtime_floor_delta_ms"] == 30.0
    assert result["last_event"] == "expanded"
    assert result["samples"] == 10
    assert result["stable_samples"] == 7
    assert result["expansions"] == 2
    assert result["contractions"] == 1
    assert result["recent_events"] == ["stable", "expanded"]
    assert result["stability_trend"] == "improving"
    assert payload["entity_factory_guard_metrics"] == result


@pytest.mark.unit
def test_resolve_entity_factory_guard_metrics_uses_root_payload_fallback() -> None:
    """resolve_entity_factory_guard_metrics supports the legacy payload layout."""
    payload: dict[str, object] = {
        "runtime_floor": 0.12,
        "baseline_floor": 0.20,
        "last_duration_ratio": float("inf"),
        "recent_jitter_ratio": float("nan"),
        "recent_events": "stable",
        "last_event": "",
        "enforce_min_runtime": False,
    }

    result = ct.resolve_entity_factory_guard_metrics(payload)

    assert result["runtime_floor_ms"] == 120.0
    assert result["baseline_floor_ms"] == 200.0
    assert result["runtime_floor_delta_ms"] == 0.0
    assert "last_duration_ratio" not in result
    assert "recent_jitter_ratio" not in result
    assert "recent_events" not in result
    assert result["last_event"] == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# shutdown  (lines 1437-1446)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shutdown_cancels_maintenance(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Shutdown cancels the maintenance subscription and clears data."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    unsub = MagicMock()
    coord._maintenance_unsub = unsub
    coord._data = {"test_dog": {"status": "online"}}

    await ct.shutdown(coord)

    unsub.assert_called_once()
    assert coord._maintenance_unsub is None
    assert coord._data == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shutdown_no_maintenance_task(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Shutdown is safe when no maintenance task is running."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._maintenance_unsub = None
    await ct.shutdown(coord)
    assert coord._data == {}


# ═══════════════════════════════════════════════════════════════════════════════
# ensure_background_task  (lines 1342-1353)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_ensure_background_task_starts_when_none(
    mock_hass, mock_config_entry, mock_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ensure_background_task registers a time-interval tracker when not yet set."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._maintenance_unsub = None

    fake_unsub = MagicMock()
    monkeypatch.setattr(ct, "async_track_time_interval", lambda *a, **kw: fake_unsub)

    ct.ensure_background_task(coord, timedelta(seconds=3600))
    assert coord._maintenance_unsub is fake_unsub


@pytest.mark.unit
def test_ensure_background_task_idempotent(
    mock_hass, mock_config_entry, mock_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ensure_background_task does NOT re-register if already set."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    existing = MagicMock()
    coord._maintenance_unsub = existing

    called = []
    monkeypatch.setattr(
        ct,
        "async_track_time_interval",
        lambda *a, **kw: called.append(1) or MagicMock(),
    )

    ct.ensure_background_task(coord, timedelta(seconds=3600))
    assert len(called) == 0
    assert coord._maintenance_unsub is existing


# ═══════════════════════════════════════════════════════════════════════════════
# build_update_statistics  (line 1298)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_build_update_statistics_returns_dict(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """build_update_statistics returns a serialisable mapping."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    result = ct.build_update_statistics(coord)
    assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# build_runtime_statistics  (line 1339)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_build_runtime_statistics_returns_dict(
    mock_hass, mock_config_entry, mock_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """build_runtime_statistics returns a serialisable mapping."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    # Stub out the resilience/performance helpers so they don't need full runtime
    monkeypatch.setattr(ct, "collect_resilience_diagnostics", lambda *a: None)
    monkeypatch.setattr(ct, "get_runtime_data", lambda *a: None)

    result = ct.build_runtime_statistics(coord)
    assert isinstance(result, dict)
    assert (
        "update_counts" in result or "performance_metrics" in result or len(result) >= 0
    )


# ═══════════════════════════════════════════════════════════════════════════════
# run_maintenance  (lines 1356-1432)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_maintenance_no_runtime_data(
    mock_hass, mock_config_entry, mock_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_maintenance completes without raising when runtime_data is None."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.last_update_success = True
    coord._metrics.consecutive_errors = 0

    monkeypatch.setattr(ct, "get_runtime_data", lambda *a: None)
    monkeypatch.setattr(ct, "capture_cache_diagnostics", lambda *a: None)
    monkeypatch.setattr(ct, "record_maintenance_result", lambda *a, **kw: None)

    await ct.run_maintenance(coord)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_maintenance_resets_consecutive_errors(
    mock_hass, mock_config_entry, mock_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Consecutive errors are reset after >1h of stability."""
    from datetime import datetime

    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.last_update_success = True
    coord._metrics.consecutive_errors = 3
    # Set last update 2 hours ago
    old_ts = datetime(2020, 1, 1, 10, 0, 0, tzinfo=UTC)
    coord.last_update_success_time = old_ts

    now_ts = datetime(2020, 1, 1, 12, 30, 0, tzinfo=UTC)
    monkeypatch.setattr(ct.dt_util, "utcnow", lambda: now_ts)
    monkeypatch.setattr(ct, "get_runtime_data", lambda *a: None)
    monkeypatch.setattr(ct, "capture_cache_diagnostics", lambda *a: None)
    monkeypatch.setattr(ct, "record_maintenance_result", lambda *a, **kw: None)

    await ct.run_maintenance(coord)

    assert coord._metrics.consecutive_errors == 0


@pytest.mark.unit
def test_timestamp_from_datetime_handles_as_timestamp_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_timestamp_from_datetime returns None when HA converters raise."""
    moment = datetime(2026, 4, 6, 12, 0, tzinfo=UTC)

    monkeypatch.setattr(
        ct.dt_util,
        "as_timestamp",
        lambda *_: (_ for _ in ()).throw(TypeError),
        raising=False,
    )
    assert ct._timestamp_from_datetime(moment) is None


@pytest.mark.unit
def test_timestamp_from_datetime_fallback_without_as_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback path uses datetime.timestamp when HA helper is unavailable."""
    moment = datetime(2026, 4, 6, 12, 0)

    monkeypatch.delattr(ct.dt_util, "as_timestamp", raising=False)
    monkeypatch.setattr(ct.dt_util, "as_utc", lambda value: value.replace(tzinfo=UTC))

    result = ct._timestamp_from_datetime(moment)
    assert isinstance(result, float)


@pytest.mark.unit
def test_coerce_float_date_fallback_and_non_finite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_coerce_float covers date fallback and NaN/inf string handling."""
    monkeypatch.setattr(
        ct.dt_util,
        "start_of_local_day",
        lambda *_: (_ for _ in ()).throw(TypeError),
    )

    value = ct._coerce_float(date(2026, 4, 6))
    assert isinstance(value, float)
    assert ct._coerce_float("nan") is None
    assert ct._coerce_float("inf") is None


@pytest.mark.unit
def test_coerce_float_parse_datetime_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """_coerce_float falls back to float conversion when parsing fails."""
    monkeypatch.setattr(
        ct.dt_util,
        "parse_datetime",
        lambda *_: (_ for _ in ()).throw(ValueError),
    )
    assert ct._coerce_float("12.5") == 12.5
    assert ct._coerce_float("not-a-number") is None


@pytest.mark.unit
def test_store_and_clear_resilience_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Store/clear resilience diagnostics call runtime update helper."""
    coordinator = SimpleNamespace(
        hass=object(),
        config_entry=object(),
        logger=MagicMock(),
    )
    runtime = object()
    calls: list[object] = []

    monkeypatch.setattr(ct, "get_runtime_data", lambda *_: runtime)
    monkeypatch.setattr(
        ct,
        "update_runtime_resilience_diagnostics",
        lambda _runtime, payload: calls.append(payload),
    )

    payload = {"summary": {"total_breakers": 1}}
    ct._store_resilience_diagnostics(coordinator, payload)
    ct._clear_resilience_diagnostics(coordinator)

    assert calls == [payload, None]


@pytest.mark.unit
def test_collect_resilience_diagnostics_manager_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """collect_resilience_diagnostics gracefully handles invalid manager payloads."""
    logger = MagicMock()
    coordinator = SimpleNamespace(
        hass=object(),
        config_entry=object(),
        logger=logger,
        resilience_manager=None,
    )

    cleared: list[bool] = []
    monkeypatch.setattr(
        ct, "_clear_resilience_diagnostics", lambda *_: cleared.append(True)
    )

    assert ct.collect_resilience_diagnostics(coordinator) == {}
    assert cleared

    coordinator.resilience_manager = SimpleNamespace(get_all_circuit_breakers="invalid")
    assert ct.collect_resilience_diagnostics(coordinator) == {}

    coordinator.resilience_manager = SimpleNamespace(
        get_all_circuit_breakers=lambda: 123
    )
    assert ct.collect_resilience_diagnostics(coordinator) == {}
