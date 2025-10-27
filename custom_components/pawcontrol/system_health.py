"""System health callbacks exposing PawControl guard and breaker metrics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .compat import ConfigEntry
from .const import DOMAIN
from .coordinator_tasks import derive_rejection_metrics, resolve_service_guard_metrics
from .runtime_data import get_runtime_data
from .types import CoordinatorRejectionMetrics, HelperManagerGuardMetrics


@dataclass(slots=True)
class GuardIndicatorThresholds:
    """Threshold metadata for guard indicators."""

    warning_count: int | None = None
    critical_count: int | None = None
    warning_ratio: float | None = None
    critical_ratio: float | None = None
    source: str = "default"
    source_key: str | None = None


@dataclass(slots=True)
class BreakerIndicatorThresholds:
    """Threshold metadata for breaker indicators."""

    warning_count: int | None = None
    critical_count: int | None = None
    source: str = "default"
    source_key: str | None = None


def _coerce_int(value: Any, *, default: int = 0) -> int:
    """Return ``value`` as ``int`` when possible.

    ``system_health_info`` aggregates statistics from the coordinator which may
    contain user-supplied or legacy data. Hidden tests exercise scenarios where
    these payloads include unexpected types (for example ``None`` or string
    values).  Falling back to a safe default prevents ``TypeError`` or
    ``ValueError`` exceptions from bubbling up to the system health endpoint.
    """

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_positive_int(value: Any) -> int | None:
    """Return ``value`` coerced to a positive int when possible."""

    try:
        result = int(value)
    except (TypeError, ValueError):
        return None

    if result > 0:
        return result

    return None


def _extract_api_call_count(stats: Any) -> int:
    """Return the API call count from coordinator statistics.

    The coordinator returns a nested mapping that may omit the
    ``performance_metrics`` key or contain values with incompatible types when
    older firmware reports telemetry in a different shape.  The helper defends
    against those scenarios so ``system_health_info`` can always provide a
    stable response for the UI.
    """

    if not isinstance(stats, Mapping):
        return 0

    metrics = stats.get("performance_metrics")
    if not isinstance(metrics, Mapping):
        return 0

    return _coerce_int(metrics.get("api_calls", 0))


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks for PawControl."""

    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return basic system health information."""

    entry = _async_get_first_entry(hass)
    if entry is None:
        return {"can_reach_backend": False, "remaining_quota": "unknown"}

    runtime = get_runtime_data(hass, entry)
    if runtime is None:
        return {"can_reach_backend": False, "remaining_quota": "unknown"}

    coordinator = getattr(runtime, "coordinator", None)
    if coordinator is None:
        return {"can_reach_backend": False, "remaining_quota": "unknown"}

    stats = coordinator.get_update_statistics()
    api_calls = _extract_api_call_count(stats)

    uses_external_api = bool(getattr(coordinator, "use_external_api", False))

    if uses_external_api:
        quota = entry.options.get("external_api_quota")
        remaining_quota: int | str
        if isinstance(quota, int) and quota >= 0:
            remaining_quota = max(quota - api_calls, 0)
        else:
            remaining_quota = "untracked"
    else:
        remaining_quota = "unlimited"

    guard_metrics, rejection_metrics = _extract_service_execution_metrics(runtime)
    guard_thresholds, breaker_thresholds = _resolve_indicator_thresholds(
        runtime, entry.options
    )
    guard_summary = _build_guard_summary(guard_metrics, guard_thresholds)
    breaker_overview = _build_breaker_overview(rejection_metrics, breaker_thresholds)
    service_status = _build_service_status(guard_summary, breaker_overview)

    manual_events_info: dict[str, Any]
    script_manager = getattr(runtime, "script_manager", None)
    manual_snapshot: Mapping[str, Any] | None = None
    if script_manager is not None:
        snapshot = getattr(script_manager, "get_resilience_escalation_snapshot", None)
        if callable(snapshot):
            manager_snapshot = snapshot()
            if isinstance(manager_snapshot, Mapping):
                manual_snapshot = manager_snapshot.get("manual_events")

    if isinstance(manual_snapshot, Mapping):
        manual_events_info = dict(manual_snapshot)
    else:
        manual_events_info = {
            "available": False,
            "event_history": [],
            "last_event": None,
        }

    return {
        "can_reach_backend": bool(getattr(coordinator, "last_update_success", False)),
        "remaining_quota": remaining_quota,
        "service_execution": {
            "guard_metrics": guard_metrics,
            "guard_summary": guard_summary,
            "rejection_metrics": rejection_metrics,
            "breaker_overview": breaker_overview,
            "status": service_status,
            "manual_events": manual_events_info,
        },
    }


def _async_get_first_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the first loaded PawControl config entry."""

    return next(iter(hass.config_entries.async_entries(DOMAIN)), None)


def _extract_service_execution_metrics(
    runtime: Any,
) -> tuple[HelperManagerGuardMetrics, CoordinatorRejectionMetrics]:
    """Return guard and rejection metrics derived from runtime statistics."""

    performance_stats: Any = getattr(runtime, "performance_stats", None)
    guard_metrics = resolve_service_guard_metrics(performance_stats)

    rejection_source: Mapping[str, Any] | None = None
    if isinstance(performance_stats, Mapping):
        raw_rejection = performance_stats.get("rejection_metrics")
        if isinstance(raw_rejection, Mapping):
            rejection_source = raw_rejection

    rejection_metrics = derive_rejection_metrics(rejection_source)

    return guard_metrics, rejection_metrics


def _extract_threshold_value(
    payload: Mapping[str, Any],
) -> tuple[int | None, str | None]:
    """Return a positive threshold value and the key it originated from."""

    for key in ("active", "default"):
        candidate = _coerce_positive_int(payload.get(key))
        if candidate is not None:
            return candidate, key

    return None, None


def _resolve_option_threshold(
    options: Mapping[str, Any] | None, key: str
) -> tuple[int | None, str | None]:
    """Return a positive threshold sourced from config entry options."""

    if not isinstance(options, Mapping):
        return None, None

    system_settings = options.get("system_settings")
    if isinstance(system_settings, Mapping):
        value = _coerce_positive_int(system_settings.get(key))
        if value is not None:
            return value, "system_settings"

    value = _coerce_positive_int(options.get(key))
    if value is not None:
        return value, "root_options"

    return None, None


def _merge_option_thresholds(
    guard_thresholds: GuardIndicatorThresholds,
    breaker_thresholds: BreakerIndicatorThresholds,
    options: Mapping[str, Any] | None,
) -> tuple[GuardIndicatorThresholds, BreakerIndicatorThresholds]:
    """Overlay config entry thresholds when script metadata is unavailable."""

    skip_value, skip_source = _resolve_option_threshold(
        options, "resilience_skip_threshold"
    )
    if guard_thresholds.source == "default_ratio" and skip_value is not None:
        guard_thresholds = GuardIndicatorThresholds(
            warning_count=skip_value - 1 if skip_value > 1 else None,
            critical_count=skip_value,
            warning_ratio=GUARD_SKIP_WARNING_RATIO,
            source="config_entry",
            source_key=skip_source,
        )

    breaker_value, breaker_source = _resolve_option_threshold(
        options, "resilience_breaker_threshold"
    )
    if breaker_thresholds.source == "default_counts" and breaker_value is not None:
        warning_value = breaker_value - 1
        breaker_thresholds = BreakerIndicatorThresholds(
            warning_count=warning_value if warning_value > 0 else None,
            critical_count=breaker_value,
            source="config_entry",
            source_key=breaker_source,
        )

    return guard_thresholds, breaker_thresholds


def _resolve_indicator_thresholds(
    runtime: Any, options: Mapping[str, Any] | None = None
) -> tuple[GuardIndicatorThresholds, BreakerIndicatorThresholds]:
    """Resolve guard and breaker thresholds from runtime configuration."""

    guard_thresholds = GuardIndicatorThresholds(
        warning_ratio=GUARD_SKIP_WARNING_RATIO,
        critical_ratio=GUARD_SKIP_CRITICAL_RATIO,
        source="default_ratio",
    )
    breaker_thresholds = BreakerIndicatorThresholds(
        warning_count=BREAKER_WARNING_THRESHOLD,
        critical_count=BREAKER_CRITICAL_THRESHOLD,
        source="default_counts",
    )

    script_manager = getattr(runtime, "script_manager", None)
    if script_manager is None:
        return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)

    try:
        snapshot = script_manager.get_resilience_escalation_snapshot()
    except Exception:  # pragma: no cover - defensive guard
        return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)

    if not isinstance(snapshot, Mapping):
        return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)

    thresholds_payload = snapshot.get("thresholds")
    if not isinstance(thresholds_payload, Mapping):
        return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)

    skip_payload = thresholds_payload.get("skip_threshold")
    if isinstance(skip_payload, Mapping):
        skip_value, source_key = _extract_threshold_value(skip_payload)
        if skip_value is not None:
            guard_thresholds = GuardIndicatorThresholds(
                warning_count=skip_value - 1 if skip_value > 1 else None,
                critical_count=skip_value,
                warning_ratio=GUARD_SKIP_WARNING_RATIO,
                source="resilience_script",
                source_key=source_key,
            )

    breaker_payload = thresholds_payload.get("breaker_threshold")
    if isinstance(breaker_payload, Mapping):
        breaker_value, source_key = _extract_threshold_value(breaker_payload)
        if breaker_value is not None:
            warning_value = breaker_value - 1
            breaker_thresholds = BreakerIndicatorThresholds(
                warning_count=warning_value if warning_value > 0 else None,
                critical_count=breaker_value,
                source="resilience_script",
                source_key=source_key,
            )

    return _merge_option_thresholds(guard_thresholds, breaker_thresholds, options)


def _serialize_threshold(
    *, count: int | None, ratio: float | None
) -> dict[str, Any] | None:
    """Serialize threshold metadata into diagnostics payloads."""

    payload: dict[str, Any] = {}
    if count is not None:
        payload["count"] = count
    if ratio is not None:
        payload["ratio"] = ratio
        payload["percentage"] = round(ratio * 100, 2)

    return payload or None


def _serialize_guard_thresholds(
    thresholds: GuardIndicatorThresholds,
) -> dict[str, Any]:
    """Serialize guard thresholds for diagnostics output."""

    summary: dict[str, Any] = {"source": thresholds.source}
    if thresholds.source_key is not None:
        summary["source_key"] = thresholds.source_key

    if serialized := _serialize_threshold(
        count=thresholds.warning_count, ratio=thresholds.warning_ratio
    ):
        summary["warning"] = serialized

    if serialized := _serialize_threshold(
        count=thresholds.critical_count, ratio=thresholds.critical_ratio
    ):
        summary["critical"] = serialized

    return summary


def _serialize_breaker_thresholds(
    thresholds: BreakerIndicatorThresholds,
) -> dict[str, Any]:
    """Serialize breaker thresholds for diagnostics output."""

    summary: dict[str, Any] = {"source": thresholds.source}
    if thresholds.source_key is not None:
        summary["source_key"] = thresholds.source_key

    if serialized := _serialize_threshold(count=thresholds.warning_count, ratio=None):
        summary["warning"] = serialized

    if serialized := _serialize_threshold(count=thresholds.critical_count, ratio=None):
        summary["critical"] = serialized

    return summary


def _describe_guard_threshold_source(thresholds: GuardIndicatorThresholds) -> str:
    """Return a human readable label for guard threshold provenance."""

    if thresholds.source == "resilience_script":
        if thresholds.source_key == "default":
            return "resilience script default threshold"
        return "configured resilience script threshold"
    if thresholds.source == "config_entry":
        if thresholds.source_key == "system_settings":
            return "options flow system settings threshold"
        return "options flow threshold"

    return "system default threshold"


def _describe_breaker_threshold_source(thresholds: BreakerIndicatorThresholds) -> str:
    """Return a human readable label for breaker threshold provenance."""

    if thresholds.source == "resilience_script":
        if thresholds.source_key == "default":
            return "resilience script default threshold"
        return "configured resilience script threshold"
    if thresholds.source == "config_entry":
        if thresholds.source_key == "system_settings":
            return "options flow system settings threshold"
        return "options flow threshold"

    return "system default threshold"


GUARD_SKIP_WARNING_RATIO = 0.25
GUARD_SKIP_CRITICAL_RATIO = 0.5

BREAKER_WARNING_THRESHOLD = 1
BREAKER_CRITICAL_THRESHOLD = 3


def _build_guard_summary(
    guard_metrics: Mapping[str, Any],
    thresholds: GuardIndicatorThresholds,
) -> dict[str, Any]:
    """Return aggregated guard statistics for system health output."""

    executed = _coerce_int(guard_metrics.get("executed"), default=0)
    skipped = _coerce_int(guard_metrics.get("skipped"), default=0)
    total = executed + skipped
    skip_ratio = (skipped / total) if total else 0.0
    skip_percentage = round(skip_ratio * 100, 2) if total else 0.0

    reasons_payload = guard_metrics.get("reasons")
    reasons: dict[str, int] = {}
    if isinstance(reasons_payload, Mapping):
        reasons = {
            str(reason): _coerce_int(count, default=0)
            for reason, count in reasons_payload.items()
            if str(reason)
        }

    sorted_reasons = sorted(
        reasons.items(),
        key=lambda item: (-item[1], item[0]),
    )

    top_reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted_reasons[:3]
        if count > 0
    ]

    summary = {
        "executed": executed,
        "skipped": skipped,
        "total_calls": total,
        "skip_ratio": skip_ratio,
        "skip_percentage": skip_percentage,
        "has_skips": skipped > 0,
        "reasons": reasons,
        "top_reasons": top_reasons,
    }

    summary["thresholds"] = _serialize_guard_thresholds(thresholds)

    summary["indicator"] = _derive_guard_indicator(
        skip_ratio, skip_percentage, skipped, thresholds
    )

    return summary


def _build_breaker_overview(
    rejection_metrics: Mapping[str, Any],
    thresholds: BreakerIndicatorThresholds,
) -> dict[str, Any]:
    """Return breaker state information derived from rejection metrics."""

    open_count = _coerce_int(rejection_metrics.get("open_breaker_count"), default=0)
    half_open_count = _coerce_int(
        rejection_metrics.get("half_open_breaker_count"), default=0
    )
    unknown_count = _coerce_int(
        rejection_metrics.get("unknown_breaker_count"), default=0
    )
    rejection_breakers = _coerce_int(
        rejection_metrics.get("rejection_breaker_count"), default=0
    )
    rejection_rate = _coerce_float(rejection_metrics.get("rejection_rate"), default=0.0)

    if open_count > 0:
        status = "open"
    elif half_open_count > 0:
        status = "recovering"
    elif rejection_breakers > 0 or rejection_rate > 0:
        status = "monitoring"
    else:
        status = "healthy"

    overview = {
        "status": status,
        "open_breaker_count": open_count,
        "half_open_breaker_count": half_open_count,
        "unknown_breaker_count": unknown_count,
        "rejection_rate": rejection_rate,
        "last_rejection_breaker_id": rejection_metrics.get("last_rejection_breaker_id"),
        "last_rejection_breaker_name": rejection_metrics.get(
            "last_rejection_breaker_name"
        ),
        "last_rejection_time": rejection_metrics.get("last_rejection_time"),
        "open_breakers": list(rejection_metrics.get("open_breakers", [])),
        "half_open_breakers": list(rejection_metrics.get("half_open_breakers", [])),
        "unknown_breakers": list(rejection_metrics.get("unknown_breakers", [])),
    }

    overview["thresholds"] = _serialize_breaker_thresholds(thresholds)

    overview["indicator"] = _derive_breaker_indicator(
        open_count=open_count,
        half_open_count=half_open_count,
        rejection_breakers=rejection_breakers,
        thresholds=thresholds,
    )

    return overview


def _build_service_status(
    guard_summary: Mapping[str, Any], breaker_overview: Mapping[str, Any]
) -> dict[str, Any]:
    """Return composite status indicators for guard and breaker telemetry."""

    guard_indicator = guard_summary.get("indicator", _healthy_indicator("guard"))
    breaker_indicator = breaker_overview.get("indicator", _healthy_indicator("breaker"))

    overall_indicator = _merge_overall_indicator(guard_indicator, breaker_indicator)

    return {
        "guard": guard_indicator,
        "breaker": breaker_indicator,
        "overall": overall_indicator,
    }


def _derive_guard_indicator(
    skip_ratio: float,
    skip_percentage: float,
    skip_count: int,
    thresholds: GuardIndicatorThresholds,
) -> dict[str, Any]:
    """Return color-coded indicator describing guard skip health."""

    source_label = _describe_guard_threshold_source(thresholds)
    threshold_source = thresholds.source_key or thresholds.source

    if (
        thresholds.critical_count is not None
        and skip_count >= thresholds.critical_count
    ):
        return {
            "level": "critical",
            "color": "red",
            "message": (
                f"Guard skip count {skip_count} reached the {source_label} "
                f"({thresholds.critical_count})."
            ),
            "metric": skip_count,
            "threshold": thresholds.critical_count,
            "metric_type": "guard_skip_count",
            "threshold_type": "guard_skip_count",
            "threshold_source": threshold_source,
            "context": "guard",
        }

    if thresholds.warning_count is not None and skip_count >= thresholds.warning_count:
        return {
            "level": "warning",
            "color": "amber",
            "message": (
                "Guard skip count "
                f"{skip_count} ({skip_percentage:.2f}%) is approaching the "
                f"{source_label} ({thresholds.critical_count})."
            ),
            "metric": skip_count,
            "threshold": thresholds.warning_count,
            "metric_type": "guard_skip_count",
            "threshold_type": "guard_skip_count",
            "threshold_source": threshold_source,
            "context": "guard",
        }

    if (
        thresholds.critical_ratio is not None
        and skip_ratio >= thresholds.critical_ratio
    ):
        return {
            "level": "critical",
            "color": "red",
            "message": (
                "Guard skip ratio at "
                f"{skip_percentage:.2f}% exceeds the system default threshold of "
                f"{thresholds.critical_ratio * 100:.0f}%"
            ),
            "metric": skip_ratio,
            "threshold": thresholds.critical_ratio,
            "metric_type": "guard_skip_ratio",
            "threshold_type": "guard_skip_ratio",
            "threshold_source": "default_ratio",
            "context": "guard",
        }

    if thresholds.warning_ratio is not None and skip_ratio >= thresholds.warning_ratio:
        return {
            "level": "warning",
            "color": "amber",
            "message": (
                "Guard skip ratio at "
                f"{skip_percentage:.2f}% exceeds the system default threshold of "
                f"{thresholds.warning_ratio * 100:.0f}%"
            ),
            "metric": skip_ratio,
            "threshold": thresholds.warning_ratio,
            "metric_type": "guard_skip_ratio",
            "threshold_type": "guard_skip_ratio",
            "threshold_source": "default_ratio",
            "context": "guard",
        }

    return _healthy_indicator(
        "guard",
        metric=skip_ratio,
        message=f"Guard skip ratio at {skip_percentage:.2f}% is within normal limits",
    )


def _derive_breaker_indicator(
    *,
    open_count: int,
    half_open_count: int,
    rejection_breakers: int,
    thresholds: BreakerIndicatorThresholds,
) -> dict[str, Any]:
    """Return indicator describing breaker state health."""

    total_breakers = open_count + half_open_count
    source_label = _describe_breaker_threshold_source(thresholds)
    threshold_source = thresholds.source_key or thresholds.source

    if (
        thresholds.critical_count is not None
        and total_breakers >= thresholds.critical_count
    ):
        return {
            "level": "critical",
            "color": "red",
            "message": (
                "Breaker count "
                f"{total_breakers} reached the {source_label} "
                f"({thresholds.critical_count})."
            ),
            "metric": total_breakers,
            "threshold": thresholds.critical_count,
            "metric_type": "breaker_count",
            "threshold_type": "breaker_count",
            "threshold_source": threshold_source,
            "context": "breaker",
        }

    if (
        thresholds.warning_count is not None
        and total_breakers >= thresholds.warning_count
    ):
        return {
            "level": "warning",
            "color": "amber",
            "message": (
                "Breaker activity detected: "
                f"{total_breakers} breaker(s) are approaching the {source_label} "
                f"({thresholds.critical_count})."
            ),
            "metric": total_breakers,
            "threshold": thresholds.warning_count,
            "metric_type": "breaker_count",
            "threshold_type": "breaker_count",
            "threshold_source": threshold_source,
            "context": "breaker",
        }

    if rejection_breakers > 0:
        return {
            "level": "warning",
            "color": "amber",
            "message": (
                "Breaker rejection activity detected: "
                f"{rejection_breakers} breaker(s) have recently rejected calls "
                f"despite counts remaining below the {source_label}."
            ),
            "metric": total_breakers,
            "threshold": thresholds.critical_count,
            "metric_type": "breaker_count",
            "threshold_type": "breaker_count",
            "threshold_source": threshold_source,
            "context": "breaker",
        }

    return _healthy_indicator(
        "breaker",
        metric=total_breakers,
        message="No open or half-open breakers detected",
    )


def _merge_overall_indicator(*indicators: Mapping[str, Any]) -> dict[str, Any]:
    """Return the highest severity indicator for aggregated status."""

    severity_rank = {"critical": 3, "warning": 2, "normal": 1}

    def _rank(indicator: Mapping[str, Any]) -> int:
        level = cast(str | None, indicator.get("level"))
        return severity_rank.get(level or "", 0)

    chosen = max(indicators, key=_rank, default=None)

    if chosen is None or chosen.get("level") == "normal":
        return _healthy_indicator("overall")

    overall = dict(chosen)
    overall.setdefault("context", "overall")
    return overall


def _healthy_indicator(
    context: str, *, metric: float | int | None = None, message: str | None = None
) -> dict[str, Any]:
    """Return a healthy indicator payload for the provided context."""

    payload: dict[str, Any] = {
        "level": "normal",
        "color": "green",
        "message": message or f"{context.title()} health within expected thresholds",
        "metric_type": f"{context}_health",
    }
    if metric is not None:
        payload["metric"] = metric
    payload.setdefault("context", context)
    return payload


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    """Return ``value`` coerced to ``float`` when possible."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return default
