"""Helper routines that keep the coordinator file compact."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from datetime import UTC, date, datetime
from math import isfinite
from typing import TYPE_CHECKING, Any, Final, cast

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .coordinator_support import ensure_cache_repair_aggregate
from .performance import (
    capture_cache_diagnostics,
    performance_tracker,
    record_maintenance_result,
)
from .runtime_data import get_runtime_data
from .telemetry import (
    get_runtime_reconfigure_summary,
    summarise_reconfigure_options,
    update_runtime_bool_coercion_summary,
    update_runtime_reconfigure_summary,
    update_runtime_resilience_summary,
)
from .types import (
    AdaptivePollingDiagnostics,
    CacheRepairAggregate,
    CircuitBreakerStateSummary,
    CircuitBreakerStatsPayload,
    CoordinatorPerformanceMetrics,
    CoordinatorRejectionMetrics,
    CoordinatorResilienceDiagnostics,
    CoordinatorResilienceSummary,
    CoordinatorRuntimeStatisticsPayload,
    CoordinatorStatisticsPayload,
    EntityBudgetSummary,
    ReconfigureTelemetrySummary,
)

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from datetime import timedelta

    from .coordinator import PawControlCoordinator


def _fetch_cache_repair_summary(
    coordinator: PawControlCoordinator,
) -> CacheRepairAggregate | None:
    """Return the latest cache repair aggregate for coordinator telemetry."""

    runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)
    if runtime_data is None:
        return None

    data_manager = getattr(runtime_data, "data_manager", None)
    if data_manager is None:
        return None

    summary_method = getattr(data_manager, "cache_repair_summary", None)
    if not callable(summary_method):
        return None

    try:
        summary = summary_method()
    except Exception as err:  # pragma: no cover - diagnostics guard
        coordinator.logger.debug("Failed to collect cache repair summary: %s", err)
        return None

    resolved_summary = ensure_cache_repair_aggregate(summary)
    if resolved_summary is not None:
        return resolved_summary
    coordinator.logger.debug(
        "Cache repair summary did not return CacheRepairAggregate: %r", summary
    )
    return None


def _fetch_reconfigure_summary(
    coordinator: PawControlCoordinator,
) -> ReconfigureTelemetrySummary | None:
    """Return the latest reconfigure summary for coordinator telemetry."""

    runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)
    if runtime_data is not None:
        summary = get_runtime_reconfigure_summary(runtime_data)
        if summary is None:
            summary = update_runtime_reconfigure_summary(runtime_data)
        if summary is not None:
            return summary

    options = getattr(coordinator.config_entry, "options", None)
    return summarise_reconfigure_options(options)


def _summarise_resilience(
    breakers: dict[str, CircuitBreakerStatsPayload],
) -> CoordinatorResilienceSummary:
    """Aggregate circuit breaker diagnostics into a concise summary."""

    state_counts: dict[str, int] = {
        "closed": 0,
        "open": 0,
        "half_open": 0,
        "unknown": 0,
        "other": 0,
    }
    failure_count = 0
    success_count = 0
    total_calls = 0
    total_failures = 0
    total_successes = 0
    rejected_call_count = 0
    latest_failure: float | None = None
    latest_state_change: float | None = None
    latest_success: float | None = None
    latest_rejection: float | None = None
    latest_recovered_pair: tuple[str, str, float, float] | None = None
    latest_rejection_pair: tuple[str, str, float] | None = None
    recovery_latency: float | None = None
    recovery_breaker_id: str | None = None
    recovery_breaker_name: str | None = None
    rejection_breaker_id: str | None = None
    rejection_breaker_name: str | None = None
    open_breakers: list[str] = []
    half_open_breakers: list[str] = []
    unknown_breakers: list[str] = []
    open_breaker_ids: list[str] = []
    half_open_breaker_ids: list[str] = []
    unknown_breaker_ids: list[str] = []
    rejection_breakers: list[str] = []
    rejection_breaker_ids: list[str] = []

    for name, stats in breakers.items():
        breaker_name = _stringify_breaker_name(name)
        breaker_id = _normalise_breaker_id(breaker_name, stats)
        state = _normalise_breaker_state(stats.get("state"))
        if state in ("closed", "open", "half_open"):
            state_counts[state] += 1
        elif state == "unknown":
            state_counts["unknown"] += 1
            unknown_breakers.append(breaker_name)
            unknown_breaker_ids.append(breaker_id)
        else:
            state_counts["other"] += 1

        if state == "open":
            open_breakers.append(breaker_name)
            open_breaker_ids.append(breaker_id)
        elif state == "half_open":
            half_open_breakers.append(breaker_name)
            half_open_breaker_ids.append(breaker_id)

        failure_count += _coerce_int(stats.get("failure_count"))
        success_count += _coerce_int(stats.get("success_count"))
        total_calls += _coerce_int(stats.get("total_calls"))
        total_failures += _coerce_int(stats.get("total_failures"))
        total_successes += _coerce_int(stats.get("total_successes"))
        rejected_calls = _coerce_int(stats.get("rejected_calls"))
        rejected_call_count += rejected_calls
        if rejected_calls > 0:
            rejection_breakers.append(breaker_name)
            rejection_breaker_ids.append(breaker_id)

        failure_value = _coerce_float(stats.get("last_failure_time"))
        if failure_value is not None:
            latest_failure = (
                failure_value
                if latest_failure is None
                else max(latest_failure, failure_value)
            )

        state_change_value = _coerce_float(stats.get("last_state_change"))
        if state_change_value is not None:
            latest_state_change = (
                state_change_value
                if latest_state_change is None
                else max(latest_state_change, state_change_value)
            )

        success_value = _coerce_float(stats.get("last_success_time"))
        if success_value is not None:
            latest_success = (
                success_value
                if latest_success is None
                else max(latest_success, success_value)
            )

            if (
                failure_value is not None
                and success_value >= failure_value
                and (
                    latest_recovered_pair is None
                    or success_value > latest_recovered_pair[2]
                )
            ):
                latest_recovered_pair = (
                    breaker_id,
                    breaker_name,
                    success_value,
                    failure_value,
                )

        rejection_value = _coerce_float(stats.get("last_rejection_time"))
        if rejection_value is not None:
            latest_rejection = (
                rejection_value
                if latest_rejection is None
                else max(latest_rejection, rejection_value)
            )
            if (
                latest_rejection_pair is None
                or rejection_value > latest_rejection_pair[2]
            ):
                latest_rejection_pair = (
                    breaker_id,
                    breaker_name,
                    rejection_value,
                )

    open_breaker_count = len(open_breakers)
    half_open_breaker_count = len(half_open_breakers)
    unknown_breaker_count = len(unknown_breakers)

    if latest_recovered_pair is not None:
        (
            recovered_breaker_id,
            recovered_breaker_name,
            success_value,
            failure_value,
        ) = latest_recovered_pair
        if latest_failure is None or success_value >= latest_failure:
            recovery_latency = max(success_value - failure_value, 0.0)
            recovery_breaker_id = recovered_breaker_id
            recovery_breaker_name = recovered_breaker_name

    if latest_rejection_pair is not None:
        rejection_breaker_id, rejection_breaker_name, latest_rejection = (
            latest_rejection_pair
        )

    rejection_rate: float | None
    total_attempts = total_calls + rejected_call_count
    if total_attempts > 0:
        rejection_rate = rejected_call_count / total_attempts
    else:
        rejection_rate = None

    summary: CoordinatorResilienceSummary = {
        "total_breakers": len(breakers),
        "states": cast(CircuitBreakerStateSummary, state_counts),
        "failure_count": failure_count,
        "success_count": success_count,
        "total_calls": total_calls,
        "total_failures": total_failures,
        "total_successes": total_successes,
        "rejected_call_count": rejected_call_count,
        "last_failure_time": latest_failure,
        "last_state_change": latest_state_change,
        "last_success_time": latest_success,
        "last_rejection_time": latest_rejection,
        "recovery_latency": recovery_latency,
        "recovery_breaker_id": recovery_breaker_id,
        "open_breaker_count": open_breaker_count,
        "half_open_breaker_count": half_open_breaker_count,
        "unknown_breaker_count": unknown_breaker_count,
        "open_breakers": list(open_breakers),
        "open_breaker_ids": list(open_breaker_ids),
        "half_open_breakers": list(half_open_breakers),
        "half_open_breaker_ids": list(half_open_breaker_ids),
        "unknown_breakers": list(unknown_breakers),
        "unknown_breaker_ids": list(unknown_breaker_ids),
        "rejection_breaker_count": len(rejection_breakers),
        "rejection_breakers": list(rejection_breakers),
        "rejection_breaker_ids": list(rejection_breaker_ids),
        "rejection_rate": rejection_rate,
    }

    if recovery_breaker_name is not None:
        summary["recovery_breaker_name"] = recovery_breaker_name

    if rejection_breaker_name is not None:
        summary["last_rejection_breaker_name"] = rejection_breaker_name

    if rejection_breaker_id is not None:
        summary["last_rejection_breaker_id"] = rejection_breaker_id

    return summary


def _extract_stat_value(stats: Any, key: str, default: Any = None) -> Any:
    """Return ``key`` from ``stats`` supporting both mapping and attribute access."""

    if isinstance(stats, Mapping):
        return stats.get(key, default)
    return getattr(stats, key, default)


def _normalise_breaker_id(name: Any, stats: Any) -> str:
    """Return a stable breaker identifier derived from diagnostics metadata."""

    candidate = _extract_stat_value(stats, "breaker_id")
    if candidate in (None, ""):
        candidate = _extract_stat_value(stats, "name")
    if candidate in (None, ""):
        candidate = _extract_stat_value(stats, "identifier")
    if candidate in (None, ""):
        candidate = _extract_stat_value(stats, "id")

    if candidate in (None, ""):
        candidate = name

    try:
        breaker_id = str(candidate)
    except Exception:  # pragma: no cover - defensive fallback
        breaker_id = str(name)

    if not breaker_id:
        breaker_id = str(name)

    return breaker_id


def _normalise_entity_budget_summary(data: Any) -> EntityBudgetSummary:
    """Return an entity budget summary with guaranteed diagnostics keys."""

    summary: EntityBudgetSummary = {
        "active_dogs": 0,
        "total_capacity": 0,
        "total_allocated": 0,
        "total_remaining": 0,
        "average_utilization": 0.0,
        "peak_utilization": 0.0,
        "denied_requests": 0,
    }

    if isinstance(data, Mapping):
        summary["active_dogs"] = _coerce_int(data.get("active_dogs"))
        summary["total_capacity"] = _coerce_int(data.get("total_capacity"))
        summary["total_allocated"] = _coerce_int(data.get("total_allocated"))
        summary["total_remaining"] = _coerce_int(data.get("total_remaining"))

        average = _coerce_float(data.get("average_utilization"))
        if average is not None:
            summary["average_utilization"] = average

        peak = _coerce_float(data.get("peak_utilization"))
        if peak is not None:
            summary["peak_utilization"] = peak

        summary["denied_requests"] = _coerce_int(data.get("denied_requests"))

    return summary


def _normalise_adaptive_diagnostics(data: Any) -> AdaptivePollingDiagnostics:
    """Return adaptive polling diagnostics with consistent numeric types."""

    diagnostics: AdaptivePollingDiagnostics = {
        "target_cycle_ms": 0.0,
        "current_interval_ms": 0.0,
        "average_cycle_ms": 0.0,
        "history_samples": 0,
        "error_streak": 0,
        "entity_saturation": 0.0,
        "idle_interval_ms": 0.0,
        "idle_grace_ms": 0.0,
    }

    if isinstance(data, Mapping):
        target = _coerce_float(data.get("target_cycle_ms"))
        if target is not None:
            diagnostics["target_cycle_ms"] = target

        current = _coerce_float(data.get("current_interval_ms"))
        if current is not None:
            diagnostics["current_interval_ms"] = current

        average = _coerce_float(data.get("average_cycle_ms"))
        if average is not None:
            diagnostics["average_cycle_ms"] = average

        diagnostics["history_samples"] = _coerce_int(data.get("history_samples"))
        diagnostics["error_streak"] = _coerce_int(data.get("error_streak"))

        saturation = _coerce_float(data.get("entity_saturation"))
        if saturation is not None:
            diagnostics["entity_saturation"] = saturation

        idle_interval = _coerce_float(data.get("idle_interval_ms"))
        if idle_interval is not None:
            diagnostics["idle_interval_ms"] = idle_interval

        idle_grace = _coerce_float(data.get("idle_grace_ms"))
        if idle_grace is not None:
            diagnostics["idle_grace_ms"] = idle_grace

    return diagnostics


_REJECTION_SCALAR_KEYS: Final[tuple[str, ...]] = (
    "rejected_call_count",
    "rejection_breaker_count",
    "rejection_rate",
    "last_rejection_time",
    "last_rejection_breaker_id",
    "last_rejection_breaker_name",
    "open_breaker_count",
    "half_open_breaker_count",
    "unknown_breaker_count",
)

_REJECTION_SEQUENCE_KEYS: Final[tuple[str, ...]] = (
    "open_breakers",
    "open_breaker_ids",
    "half_open_breakers",
    "half_open_breaker_ids",
    "unknown_breakers",
    "unknown_breaker_ids",
    "rejection_breaker_ids",
    "rejection_breakers",
)

type RejectionTargetMapping = (
    MutableMapping[str, Any]
    | CoordinatorPerformanceMetrics
    | CoordinatorRejectionMetrics
)

type RejectionSourceMapping = (
    Mapping[str, Any]
    | CoordinatorRejectionMetrics
    | CoordinatorResilienceSummary
)


def default_rejection_metrics() -> CoordinatorRejectionMetrics:
    """Return a baseline rejection metric payload for diagnostics consumers."""

    return {
        "schema_version": 3,
        "rejected_call_count": 0,
        "rejection_breaker_count": 0,
        "rejection_rate": 0.0,
        "last_rejection_time": None,
        "last_rejection_breaker_id": None,
        "last_rejection_breaker_name": None,
        "open_breaker_count": 0,
        "half_open_breaker_count": 0,
        "unknown_breaker_count": 0,
        "open_breakers": [],
        "open_breaker_ids": [],
        "half_open_breakers": [],
        "half_open_breaker_ids": [],
        "unknown_breakers": [],
        "unknown_breaker_ids": [],
        "rejection_breaker_ids": [],
        "rejection_breakers": [],
    }


def merge_rejection_metric_values(
    target: RejectionTargetMapping,
    *sources: RejectionSourceMapping,
) -> None:
    """Populate ``target`` with rejection metrics extracted from ``sources``."""

    if not sources:
        return

    mutable_target = cast(MutableMapping[str, Any], target)
    source_mappings = [cast(Mapping[str, Any], source) for source in sources]

    for key in _REJECTION_SCALAR_KEYS:
        for source in source_mappings:
            if key in source:
                mutable_target[key] = source[key]
                break

    for key in _REJECTION_SEQUENCE_KEYS:
        for source in source_mappings:
            if key in source:
                value = source[key]
                if isinstance(value, Sequence) and not isinstance(
                    value, str | bytes | bytearray
                ):
                    mutable_target[key] = list(value)
                else:
                    mutable_target[key] = []
                break
        else:
            mutable_target[key] = []


def derive_rejection_metrics(
    summary: Mapping[str, Any] | CoordinatorResilienceSummary | None,
) -> CoordinatorRejectionMetrics:
    """Return rejection counters extracted from a resilience summary."""

    metrics = default_rejection_metrics()

    if not summary:
        return metrics

    rejected_calls = summary.get("rejected_call_count")
    if rejected_calls is not None:
        metrics["rejected_call_count"] = _coerce_int(rejected_calls)

    rejection_breakers = summary.get("rejection_breaker_count")
    if rejection_breakers is not None:
        metrics["rejection_breaker_count"] = _coerce_int(rejection_breakers)

    rejection_rate = _coerce_float(summary.get("rejection_rate"))
    if rejection_rate is not None:
        metrics["rejection_rate"] = rejection_rate

    last_rejection_time = _coerce_float(summary.get("last_rejection_time"))
    if last_rejection_time is not None:
        metrics["last_rejection_time"] = last_rejection_time

    breaker_id_raw = summary.get("last_rejection_breaker_id")
    if isinstance(breaker_id_raw, str):
        metrics["last_rejection_breaker_id"] = breaker_id_raw

    breaker_name_raw = summary.get("last_rejection_breaker_name")
    if isinstance(breaker_name_raw, str):
        metrics["last_rejection_breaker_name"] = breaker_name_raw

    open_breakers = summary.get("open_breaker_count")
    if open_breakers is not None:
        metrics["open_breaker_count"] = _coerce_int(open_breakers)

    half_open_breakers = summary.get("half_open_breaker_count")
    if half_open_breakers is not None:
        metrics["half_open_breaker_count"] = _coerce_int(half_open_breakers)

    unknown_breakers = summary.get("unknown_breaker_count")
    if unknown_breakers is not None:
        metrics["unknown_breaker_count"] = _coerce_int(unknown_breakers)

    metrics["open_breakers"] = _normalise_string_list(summary.get("open_breakers"))
    metrics["open_breaker_ids"] = _normalise_string_list(
        summary.get("open_breaker_ids")
    )
    metrics["half_open_breakers"] = _normalise_string_list(
        summary.get("half_open_breakers")
    )
    metrics["half_open_breaker_ids"] = _normalise_string_list(
        summary.get("half_open_breaker_ids")
    )
    metrics["unknown_breakers"] = _normalise_string_list(
        summary.get("unknown_breakers")
    )
    metrics["unknown_breaker_ids"] = _normalise_string_list(
        summary.get("unknown_breaker_ids")
    )
    metrics["rejection_breaker_ids"] = _normalise_string_list(
        summary.get("rejection_breaker_ids")
    )
    metrics["rejection_breakers"] = _normalise_string_list(
        summary.get("rejection_breakers")
    )

    return metrics


def _derive_rejection_metrics(
    summary: Mapping[str, Any],
) -> CoordinatorRejectionMetrics:
    """Backwards-compatible wrapper for legacy imports."""

    return derive_rejection_metrics(summary)


def _normalise_breaker_state(value: Any) -> str:
    """Return a canonical breaker state used for resilience aggregation."""

    candidate = getattr(value, "value", value)

    if isinstance(candidate, str):
        text = candidate.strip()
    elif candidate is None:
        return "unknown"
    else:
        try:
            text = str(candidate).strip()
        except Exception:  # pragma: no cover - defensive fallback
            return "unknown"

    if not text:
        return "unknown"

    normalised = text.replace("-", " ")
    normalised = "_".join(normalised.split())
    normalised = normalised.lower()

    return normalised or "unknown"


def _stringify_breaker_name(name: Any) -> str:
    """Return the original breaker mapping key coerced to a string."""

    if isinstance(name, str) and name:
        return name

    for candidate in (name, repr(name)):
        try:
            text = str(candidate)
        except Exception:  # pragma: no cover - defensive fallback
            continue
        if text and not text.isspace():
            return text

    return f"breaker_{id(name)}"


def _coerce_int(value: Any) -> int:
    """Return ``value`` normalised as an integer for diagnostics payloads."""

    if isinstance(value, bool):
        return int(value)

    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _normalise_string_list(value: Any) -> list[str]:
    """Return ``value`` coerced into a list of non-empty strings."""

    if value is None:
        return []

    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []

    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        items: list[str] = []
        for entry in value:
            if isinstance(entry, str):
                candidate = entry.strip()
            else:
                try:
                    candidate = str(entry).strip()
                except Exception:  # pragma: no cover - defensive fallback
                    continue
            if candidate:
                items.append(candidate)
        return items

    try:
        text = str(value).strip()
    except Exception:  # pragma: no cover - defensive fallback
        return []

    return [text] if text else []


def _timestamp_from_datetime(value: datetime) -> float | None:
    """Return a POSIX timestamp for ``value`` with robust fallbacks."""

    convert = getattr(dt_util, "as_timestamp", None)
    if callable(convert):
        try:
            return float(convert(value))
        except (TypeError, ValueError, OverflowError):
            return None

    as_utc = getattr(dt_util, "as_utc", None)
    try:
        aware = as_utc(value) if callable(as_utc) else value
    except (TypeError, ValueError, AttributeError):  # pragma: no cover - compat guard
        aware = value

    if aware.tzinfo is None:
        aware = aware.replace(tzinfo=UTC)

    try:
        return float(aware.timestamp())
    except (OverflowError, OSError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    """Return ``value`` as a finite float when possible."""

    if value is None:
        return None

    if isinstance(value, bool):
        value = int(value)

    if isinstance(value, datetime):
        return _timestamp_from_datetime(value)

    if isinstance(value, date) and not isinstance(value, datetime):
        try:
            start_of_day = dt_util.start_of_local_day(value)
        except (TypeError, ValueError, AttributeError):
            # ``start_of_local_day`` may be unavailable in some compat paths.
            start_of_day = datetime(value.year, value.month, value.day, tzinfo=UTC)
        return _timestamp_from_datetime(start_of_day)

    if isinstance(value, str):
        try:
            parsed = dt_util.parse_datetime(value)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None:
            return _timestamp_from_datetime(parsed)

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not isfinite(number):
        return None

    return number


def _store_resilience_summary(
    coordinator: PawControlCoordinator,
    summary: CoordinatorResilienceSummary,
) -> None:
    """Persist the latest resilience summary for reuse by runtime diagnostics."""

    runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)
    if runtime_data is None:
        return

    update_runtime_resilience_summary(runtime_data, summary)


def _clear_resilience_summary(coordinator: PawControlCoordinator) -> None:
    """Remove stored resilience telemetry when no breakers are available."""

    runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)
    if runtime_data is None:
        return

    update_runtime_resilience_summary(runtime_data, None)


def collect_resilience_diagnostics(
    coordinator: PawControlCoordinator,
) -> CoordinatorResilienceDiagnostics:
    """Return a structured resilience diagnostics payload for the coordinator."""

    payload: CoordinatorResilienceDiagnostics = {}

    manager = getattr(coordinator, "resilience_manager", None)
    if manager is None:
        _clear_resilience_summary(coordinator)
        return payload

    fetch = getattr(manager, "get_all_circuit_breakers", None)
    if not callable(fetch):
        _clear_resilience_summary(coordinator)
        return payload

    try:
        raw = fetch()
    except Exception as err:  # pragma: no cover - diagnostics guard
        coordinator.logger.debug("Failed to collect circuit breaker stats: %s", err)
        _clear_resilience_summary(coordinator)
        return payload

    if isinstance(raw, Mapping):
        item_source: Iterable[tuple[Any, Any]] = raw.items()
    elif isinstance(raw, Iterable) and not isinstance(raw, str | bytes | bytearray):

        def _iter_items() -> Iterable[tuple[Any, Any]]:
            for item in raw:
                if isinstance(item, tuple) and len(item) == 2:
                    yield item
                else:
                    yield str(item), item

        item_source = _iter_items()
    else:
        coordinator.logger.debug(
            "Unexpected circuit breaker diagnostics payload: %s",
            type(raw).__name__,
        )
        _clear_resilience_summary(coordinator)
        return payload

    breakers: dict[str, CircuitBreakerStatsPayload] = {}

    for name, stats in item_source:
        state = _extract_stat_value(stats, "state")
        candidate = getattr(state, "value", state)
        if isinstance(candidate, str):
            state_value = candidate.strip() or "unknown"
        elif candidate is None:
            state_value = "unknown"
        else:
            text = str(candidate)
            state_value = "unknown" if not text or text.isspace() else text

        breaker_id = _normalise_breaker_id(name, stats)
        mapping_key = _stringify_breaker_name(name)

        entry: CircuitBreakerStatsPayload = {
            "breaker_id": breaker_id,
            "state": str(state_value),
            "failure_count": _coerce_int(
                _extract_stat_value(stats, "failure_count", 0)
            ),
            "success_count": _coerce_int(
                _extract_stat_value(stats, "success_count", 0)
            ),
            "last_failure_time": _coerce_float(
                _extract_stat_value(stats, "last_failure_time")
            ),
            "last_state_change": _coerce_float(
                _extract_stat_value(stats, "last_state_change")
            ),
            "total_calls": _coerce_int(_extract_stat_value(stats, "total_calls", 0)),
            "total_failures": _coerce_int(
                _extract_stat_value(stats, "total_failures", 0)
            ),
            "total_successes": _coerce_int(
                _extract_stat_value(stats, "total_successes", 0)
            ),
            "rejected_calls": _coerce_int(
                _extract_stat_value(stats, "rejected_calls", 0)
            ),
        }

        last_success_time = _coerce_float(
            _extract_stat_value(stats, "last_success_time")
        )
        if last_success_time is not None:
            entry["last_success_time"] = last_success_time

        last_rejection_time = _coerce_float(
            _extract_stat_value(stats, "last_rejection_time")
        )
        if last_rejection_time is not None:
            entry["last_rejection_time"] = last_rejection_time

        breakers[mapping_key] = entry

    if not breakers:
        _clear_resilience_summary(coordinator)
        return payload

    payload["breakers"] = breakers
    summary = _summarise_resilience(breakers)
    payload["summary"] = summary
    _store_resilience_summary(coordinator, summary)
    return payload


def build_update_statistics(
    coordinator: PawControlCoordinator,
) -> CoordinatorStatisticsPayload:
    """Return lightweight update statistics for diagnostics endpoints."""

    cache_metrics = coordinator._modules.cache_metrics()
    repair_summary = _fetch_cache_repair_summary(coordinator)
    reconfigure_summary = _fetch_reconfigure_summary(coordinator)
    stats = coordinator._metrics.update_statistics(
        cache_entries=cache_metrics.entries,
        cache_hit_rate=cache_metrics.hit_rate,
        last_update=coordinator.last_update_time,
        interval=coordinator.update_interval,
        repair_summary=repair_summary,
    )
    stats["entity_budget"] = _normalise_entity_budget_summary(
        coordinator._entity_budget.summary()
    )
    stats["adaptive_polling"] = _normalise_adaptive_diagnostics(
        coordinator._adaptive_polling.as_diagnostics()
    )
    rejection_metrics = default_rejection_metrics()

    resilience = collect_resilience_diagnostics(coordinator)
    if resilience:
        stats["resilience"] = resilience
        summary_payload = resilience.get("summary")
        if isinstance(summary_payload, Mapping):
            rejection_metrics = derive_rejection_metrics(summary_payload)

    stats["rejection_metrics"] = rejection_metrics

    performance_metrics = stats["performance_metrics"]
    merge_rejection_metric_values(performance_metrics, rejection_metrics)
    if reconfigure_summary is not None:
        stats["reconfigure"] = reconfigure_summary
    return stats


def build_runtime_statistics(
    coordinator: PawControlCoordinator,
) -> CoordinatorRuntimeStatisticsPayload:
    """Return expanded statistics for diagnostics pages."""

    cache_metrics = coordinator._modules.cache_metrics()
    repair_summary = _fetch_cache_repair_summary(coordinator)
    reconfigure_summary = _fetch_reconfigure_summary(coordinator)
    stats = coordinator._metrics.runtime_statistics(
        cache_metrics=cache_metrics,
        total_dogs=len(coordinator.registry),
        last_update=coordinator.last_update_time,
        interval=coordinator.update_interval,
        repair_summary=repair_summary,
    )
    runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)
    stats["bool_coercion"] = update_runtime_bool_coercion_summary(runtime_data)
    stats["entity_budget"] = _normalise_entity_budget_summary(
        coordinator._entity_budget.summary()
    )
    stats["adaptive_polling"] = _normalise_adaptive_diagnostics(
        coordinator._adaptive_polling.as_diagnostics()
    )
    rejection_metrics = default_rejection_metrics()

    resilience = collect_resilience_diagnostics(coordinator)
    if resilience:
        stats["resilience"] = resilience
        summary_payload = resilience.get("summary")
        if isinstance(summary_payload, Mapping):
            rejection_metrics = derive_rejection_metrics(summary_payload)

    stats["rejection_metrics"] = rejection_metrics

    performance_metrics = stats.get("performance_metrics")
    if isinstance(performance_metrics, dict):
        merge_rejection_metric_values(performance_metrics, rejection_metrics)

    error_summary = stats.get("error_summary")
    if isinstance(error_summary, dict):
        error_summary["rejection_rate"] = rejection_metrics["rejection_rate"]
        error_summary["rejected_call_count"] = rejection_metrics["rejected_call_count"]
        error_summary["rejection_breaker_count"] = rejection_metrics[
            "rejection_breaker_count"
        ]
        error_summary["open_breaker_count"] = rejection_metrics["open_breaker_count"]
        error_summary["half_open_breaker_count"] = rejection_metrics[
            "half_open_breaker_count"
        ]
        error_summary["unknown_breaker_count"] = rejection_metrics[
            "unknown_breaker_count"
        ]
        error_summary["open_breakers"] = list(rejection_metrics["open_breakers"])
        error_summary["open_breaker_ids"] = list(rejection_metrics["open_breaker_ids"])
        error_summary["half_open_breakers"] = list(
            rejection_metrics["half_open_breakers"]
        )
        error_summary["half_open_breaker_ids"] = list(
            rejection_metrics["half_open_breaker_ids"]
        )
        error_summary["unknown_breakers"] = list(rejection_metrics["unknown_breakers"])
        error_summary["unknown_breaker_ids"] = list(
            rejection_metrics["unknown_breaker_ids"]
        )
        error_summary["rejection_breaker_ids"] = list(
            rejection_metrics["rejection_breaker_ids"]
        )
        error_summary["rejection_breakers"] = list(
            rejection_metrics["rejection_breakers"]
        )
    if reconfigure_summary is not None:
        stats["reconfigure"] = reconfigure_summary
    return stats


@callback
def ensure_background_task(
    coordinator: PawControlCoordinator, interval: timedelta
) -> None:
    """Start the maintenance task if not already running."""

    if coordinator._maintenance_unsub is None:
        coordinator._maintenance_unsub = async_track_time_interval(
            coordinator.hass, coordinator._async_maintenance, interval
        )


async def run_maintenance(coordinator: PawControlCoordinator) -> None:
    """Perform periodic maintenance work for caches and metrics."""

    runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)
    now = dt_util.utcnow()

    diagnostics = None
    metadata = {
        "schedule": "hourly",
        "runtime_available": runtime_data is not None,
    }
    details: dict[str, Any] = {}

    with performance_tracker(
        runtime_data,
        "analytics_collector_metrics",
        max_samples=50,
    ) as perf:
        try:
            expired = coordinator._modules.cleanup_expired(now)
            if expired:
                coordinator.logger.debug("Cleaned %d expired cache entries", expired)
                details["expired_entries"] = expired

            if (
                coordinator._metrics.consecutive_errors > 0
                and coordinator.last_update_success
            ):
                hours_since_last_update = (
                    now - (coordinator.last_update_time or now)
                ).total_seconds() / 3600
                if hours_since_last_update > 1:
                    previous = coordinator._metrics.consecutive_errors
                    coordinator._metrics.reset_consecutive()
                    coordinator.logger.info(
                        "Reset consecutive error count (%d) after %d hours of stability",
                        previous,
                        int(hours_since_last_update),
                    )
                    details["consecutive_errors_reset"] = previous
                    details["hours_since_last_update"] = round(
                        hours_since_last_update, 2
                    )

            diagnostics = capture_cache_diagnostics(runtime_data)
            if diagnostics is not None:
                details["cache_snapshot"] = True

            record_maintenance_result(
                runtime_data,
                task="coordinator_maintenance",
                status="success",
                diagnostics=diagnostics,
                metadata=metadata,
                details=details,
            )
        except Exception as err:
            perf.mark_failure(err)
            if diagnostics is None:
                diagnostics = capture_cache_diagnostics(runtime_data)
            record_maintenance_result(
                runtime_data,
                task="coordinator_maintenance",
                status="error",
                message=str(err),
                diagnostics=diagnostics,
                metadata=metadata,
                details=details,
            )
            raise


async def shutdown(coordinator: PawControlCoordinator) -> None:
    """Shutdown hook for coordinator teardown."""

    if coordinator._maintenance_unsub:
        coordinator._maintenance_unsub()
        coordinator._maintenance_unsub = None

    coordinator._data.clear()
    coordinator._modules.clear_caches()
    coordinator.logger.info("Coordinator shutdown completed successfully")
