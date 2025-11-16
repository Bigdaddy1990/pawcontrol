"""Telemetry helpers shared between PawControl services and coordinators."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime
from math import ceil, floor, isfinite
from statistics import median, pstdev
from typing import Any, Final, cast

from homeassistant.util import dt as dt_util

from .types import (
    BoolCoercionMetrics,
    BoolCoercionSample,
    BoolCoercionSummary,
    CircuitBreakerStatsPayload,
    ConfigEntryOptionsPayload,
    CoordinatorResilienceDiagnostics,
    CoordinatorResilienceSummary,
    DoorSensorFailureSummary,
    DoorSensorPersistenceFailure,
    DoorSensorSettingsPayload,
    EntityFactoryGuardEvent,
    EntityFactoryGuardMetrics,
    EntityFactoryGuardStabilityTrend,
    JSONLikeMapping,
    PawControlRuntimeData,
    ReconfigureOptionsUpdates,
    ReconfigureTelemetry,
    ReconfigureTelemetrySummary,
    RuntimeErrorHistoryEntry,
    RuntimePerformanceStats,
    RuntimeStoreAssessmentEvent,
    RuntimeStoreAssessmentTimelineSegment,
    RuntimeStoreAssessmentTimelineSummary,
    RuntimeStoreCompatibilitySnapshot,
    RuntimeStoreEntryStatus,
    RuntimeStoreHealthAssessment,
    RuntimeStoreHealthHistory,
    RuntimeStoreHealthLevel,
    RuntimeStoreLevelDurationAlert,
    RuntimeStoreLevelDurationPercentiles,
    RuntimeStoreOverallStatus,
)

_BOOL_COERCION_METRICS: BoolCoercionMetrics = {
    "total": 0,
    "defaulted": 0,
    "fallback": 0,
    "reset_count": 0,
    "type_counts": {},
    "reason_counts": {},
    "samples": [],
    "first_seen": None,
    "last_seen": None,
    "active_window_seconds": None,
    "last_reset": None,
    "last_reason": None,
    "last_value_type": None,
    "last_value_repr": None,
    "last_result": None,
    "last_default": None,
}
_BOOL_COERCION_SAMPLE_LIMIT = 10

_RUNTIME_STORE_STATUS_LEVELS: dict[
    RuntimeStoreOverallStatus, tuple[RuntimeStoreHealthLevel, str]
] = {
    "current": (
        "ok",
        "Runtime store metadata matches the active schema.",
    ),
    "missing": (
        "watch",
        "No runtime store metadata has been recorded for this entry yet.",
    ),
    "detached_entry": (
        "watch",
        "Runtime data exists without a matching hass.data store entry.",
    ),
    "detached_store": (
        "watch",
        "Runtime store metadata remains without an attached config entry.",
    ),
    "diverged": (
        "watch",
        "Runtime store metadata diverged from the config entry payload.",
    ),
    "needs_migration": (
        "action_required",
        "Runtime store metadata must be migrated to the current schema.",
    ),
    "future_incompatible": (
        "action_required",
        "Runtime store caches were produced by a newer schema.",
    ),
}

_RUNTIME_STORE_ENTRY_ACTION_STATUSES: set[RuntimeStoreEntryStatus] = {
    "legacy_upgrade_required",
    "future_incompatible",
}

_RUNTIME_STORE_ENTRY_WATCH_STATUSES: set[RuntimeStoreEntryStatus] = {
    "upgrade_pending",
}

_RUNTIME_STORE_RECOMMENDATIONS: dict[RuntimeStoreHealthLevel, str | None] = {
    "ok": None,
    "watch": (
        "Monitor runtime store diagnostics and run the compatibility repair if the "
        "warning persists."
    ),
    "action_required": (
        "Run the runtime store compatibility repair and reload the PawControl "
        "config entry to regenerate caches."
    ),
}

_DIVERGENCE_WATCH_THRESHOLD = 0.1
_DIVERGENCE_ACTION_THRESHOLD = 0.5
_LEVEL_DURATION_PERCENTILE_TARGETS: dict[str, float] = {
    "p75": 0.75,
    "p90": 0.9,
    "p95": 0.95,
}

_LEVEL_DURATION_GUARD_LIMITS: Final[dict[RuntimeStoreHealthLevel, float | None]] = {
    "ok": None,
    "watch": 6 * 3600.0,
    "action_required": 2 * 3600.0,
}

_LEVEL_DURATION_GUARD_SEVERITY: Final[dict[RuntimeStoreHealthLevel, str]] = {
    "ok": "info",
    "watch": "warning",
    "action_required": "critical",
}

_LEVEL_DURATION_GUARD_RECOMMENDATIONS: Final[
    dict[RuntimeStoreHealthLevel, str | None]
] = {
    "ok": None,
    "watch": (
        "Review runtime store diagnostics; run the compatibility repair if the "
        "warning persists beyond the guard window."
    ),
    "action_required": (
        "Reset the runtime store via the compatibility repair and reload PawControl "
        "to clear stale action-required segments."
    ),
}

_RUNTIME_STORE_LEVEL_ORDER: dict[RuntimeStoreHealthLevel, int] = {
    "ok": 0,
    "watch": 1,
    "action_required": 2,
}

_RUNTIME_STORE_ASSESSMENT_EVENT_LIMIT = 15


def _coerce_runtime_store_assessment_event(
    candidate: Mapping[str, object],
) -> RuntimeStoreAssessmentEvent | None:
    """Return a normalised runtime store assessment event from ``candidate``."""

    timestamp = candidate.get("timestamp")
    if not isinstance(timestamp, str):
        return None

    level_raw = candidate.get("level")
    if not isinstance(level_raw, str) or level_raw not in _RUNTIME_STORE_LEVEL_ORDER:
        return None
    level = cast(RuntimeStoreHealthLevel, level_raw)

    status_raw = candidate.get("status")
    if (
        not isinstance(status_raw, str)
        or status_raw not in _RUNTIME_STORE_STATUS_LEVELS
    ):
        return None
    status = cast(RuntimeStoreOverallStatus, status_raw)

    reason = candidate.get("reason")
    if not isinstance(reason, str):
        return None

    previous_level_raw = candidate.get("previous_level")
    previous_level: RuntimeStoreHealthLevel | None = None
    if (
        isinstance(previous_level_raw, str)
        and previous_level_raw in _RUNTIME_STORE_LEVEL_ORDER
    ):
        previous_level = cast(RuntimeStoreHealthLevel, previous_level_raw)

    recommended_action_raw = candidate.get("recommended_action")
    recommended_action: str | None
    if isinstance(recommended_action_raw, str):
        recommended_action = recommended_action_raw
    else:
        recommended_action = None

    entry_status_raw = candidate.get("entry_status")
    entry_status: RuntimeStoreEntryStatus | None
    if isinstance(entry_status_raw, str) and entry_status_raw in {
        "missing",
        "unstamped",
        "current",
        "upgrade_pending",
        "legacy_upgrade_required",
        "future_incompatible",
    }:
        entry_status = cast(RuntimeStoreEntryStatus, entry_status_raw)
    else:
        entry_status = None

    store_status_raw = candidate.get("store_status")
    store_status: RuntimeStoreEntryStatus | None
    if isinstance(store_status_raw, str) and store_status_raw in {
        "missing",
        "unstamped",
        "current",
        "upgrade_pending",
        "legacy_upgrade_required",
        "future_incompatible",
    }:
        store_status = cast(RuntimeStoreEntryStatus, store_status_raw)
    else:
        store_status = None

    divergence_detected = bool(candidate.get("divergence_detected"))

    divergence_rate_raw = candidate.get("divergence_rate")
    divergence_rate: float | None
    if isinstance(divergence_rate_raw, (int, float)) and isfinite(divergence_rate_raw):
        divergence_rate = float(divergence_rate_raw)
    else:
        divergence_rate = None

    checks_raw = candidate.get("checks")
    checks = int(checks_raw) if isinstance(checks_raw, (int, float)) else 0

    divergence_events_raw = candidate.get("divergence_events")
    divergence_events = (
        int(divergence_events_raw)
        if isinstance(divergence_events_raw, (int, float))
        else 0
    )

    level_streak_raw = candidate.get("level_streak")
    level_streak = (
        int(level_streak_raw) if isinstance(level_streak_raw, (int, float)) else 0
    )

    escalations_raw = candidate.get("escalations")
    escalations = (
        int(escalations_raw) if isinstance(escalations_raw, (int, float)) else 0
    )

    deescalations_raw = candidate.get("deescalations")
    deescalations = (
        int(deescalations_raw) if isinstance(deescalations_raw, (int, float)) else 0
    )

    level_changed = bool(candidate.get("level_changed"))

    current_duration_raw = candidate.get("current_level_duration_seconds")
    current_duration: float | None
    if isinstance(current_duration_raw, (int, float)) and isfinite(
        current_duration_raw
    ):
        current_duration = max(float(current_duration_raw), 0.0)
    else:
        current_duration = None

    event: RuntimeStoreAssessmentEvent = {
        "timestamp": timestamp,
        "level": level,
        "previous_level": previous_level,
        "status": status,
        "entry_status": entry_status,
        "store_status": store_status,
        "reason": reason,
        "recommended_action": recommended_action,
        "divergence_detected": divergence_detected,
        "divergence_rate": divergence_rate,
        "checks": checks,
        "divergence_events": divergence_events,
        "level_streak": level_streak,
        "escalations": escalations,
        "deescalations": deescalations,
        "level_changed": level_changed,
    }
    if current_duration is not None:
        event["current_level_duration_seconds"] = current_duration

    return event


def _normalise_runtime_store_assessment_events(
    source: object,
) -> list[RuntimeStoreAssessmentEvent]:
    """Return a validated list of runtime store assessment events."""

    events: list[RuntimeStoreAssessmentEvent] = []
    if not isinstance(source, Sequence):
        return events

    for candidate in source:
        if isinstance(candidate, Mapping):
            event = _coerce_runtime_store_assessment_event(candidate)
            if event is not None:
                events.append(event)

    return events


def _calculate_percentile_value(
    sorted_values: Sequence[float], percentile: float
) -> float | None:
    """Return the percentile value for ``sorted_values``."""

    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = percentile * (len(sorted_values) - 1)
    lower_index = floor(position)
    upper_index = ceil(position)
    if lower_index == upper_index:
        return sorted_values[int(position)]

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = position - lower_index
    return lower_value + (upper_value - lower_value) * weight


def _calculate_duration_percentiles(
    durations: Sequence[float],
) -> RuntimeStoreLevelDurationPercentiles:
    """Return percentile markers for ``durations``."""

    percentiles: RuntimeStoreLevelDurationPercentiles = {}
    if not durations:
        return percentiles

    sorted_values = sorted(durations)
    for label, percentile in _LEVEL_DURATION_PERCENTILE_TARGETS.items():
        percentile_value = _calculate_percentile_value(sorted_values, percentile)
        if percentile_value is not None:
            percentiles[label] = percentile_value

    return percentiles


def _summarise_runtime_store_assessment_events(
    events: Sequence[RuntimeStoreAssessmentEvent],
) -> RuntimeStoreAssessmentTimelineSummary:
    """Derive aggregate statistics for runtime store assessment events."""

    level_counts: dict[RuntimeStoreHealthLevel, int] = {
        "ok": 0,
        "watch": 0,
        "action_required": 0,
    }
    status_counts: dict[RuntimeStoreOverallStatus, int] = {
        status: 0 for status in _RUNTIME_STORE_STATUS_LEVELS
    }
    level_duration_peaks: dict[RuntimeStoreHealthLevel, float] = {
        "ok": 0.0,
        "watch": 0.0,
        "action_required": 0.0,
    }
    level_duration_latest: dict[RuntimeStoreHealthLevel, float | None] = {
        "ok": None,
        "watch": None,
        "action_required": None,
    }
    level_duration_totals: dict[RuntimeStoreHealthLevel, float] = {
        "ok": 0.0,
        "watch": 0.0,
        "action_required": 0.0,
    }
    level_duration_samples: dict[RuntimeStoreHealthLevel, int] = {
        "ok": 0,
        "watch": 0,
        "action_required": 0,
    }
    level_duration_minimums: dict[RuntimeStoreHealthLevel, float | None] = {
        "ok": None,
        "watch": None,
        "action_required": None,
    }
    level_duration_standard_deviations: dict[
        RuntimeStoreHealthLevel, float | None
    ] = {
        "ok": None,
        "watch": None,
        "action_required": None,
    }
    level_duration_distributions: dict[RuntimeStoreHealthLevel, list[float]] = {
        "ok": [],
        "watch": [],
        "action_required": [],
    }
    level_duration_percentiles: dict[
        RuntimeStoreHealthLevel, RuntimeStoreLevelDurationPercentiles
    ] = {
        "ok": {},
        "watch": {},
        "action_required": {},
    }
    level_duration_alert_thresholds: dict[RuntimeStoreHealthLevel, float | None] = {
        "ok": None,
        "watch": None,
        "action_required": None,
    }
    level_duration_guard_alerts: list[RuntimeStoreLevelDurationAlert] = []
    reason_counts: dict[str, int] = {}
    level_changes = 0

    first_event_timestamp: str | None = None
    last_event_timestamp: str | None = None
    last_level: RuntimeStoreHealthLevel | None = None
    last_status: RuntimeStoreOverallStatus | None = None
    last_reason: str | None = None
    last_recommended_action: str | None = None
    last_divergence_detected: bool | None = None
    last_divergence_rate: float | None = None
    last_level_duration_seconds: float | None = None
    divergence_rates: list[float] = []

    parsed_events: list[tuple[RuntimeStoreAssessmentEvent, datetime | None]] = []
    for event in events:
        timestamp = event.get("timestamp")
        parsed_events.append(
            (
                event,
                dt_util.parse_datetime(timestamp)
                if isinstance(timestamp, str)
                else None,
            )
        )

    for index, (event, start_dt) in enumerate(parsed_events):
        level = event.get("level")
        if level in level_counts:
            level_counts[level] += 1
        status = event.get("status")
        if status in status_counts:
            status_counts[status] += 1

        reason = event.get("reason")
        if isinstance(reason, str):
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        if event.get("level_changed"):
            level_changes += 1

        timestamp = event.get("timestamp")
        if isinstance(timestamp, str):
            if first_event_timestamp is None and index == 0:
                first_event_timestamp = timestamp
            last_event_timestamp = timestamp

        if level in level_counts:
            last_level = cast(RuntimeStoreHealthLevel, level)
        if status in status_counts:
            last_status = cast(RuntimeStoreOverallStatus, status)
        last_reason = reason if isinstance(reason, str) else last_reason
        recommended_action = event.get("recommended_action")
        if isinstance(recommended_action, str):
            last_recommended_action = recommended_action
        elif recommended_action is None:
            last_recommended_action = None
        divergence_detected = event.get("divergence_detected")
        if isinstance(divergence_detected, bool):
            last_divergence_detected = divergence_detected
        divergence_rate = event.get("divergence_rate")
        if isinstance(divergence_rate, (int, float)) and isfinite(divergence_rate):
            last_divergence_rate = float(divergence_rate)
            divergence_rates.append(last_divergence_rate)

        if level in level_counts:
            duration: float | None = None
            duration_raw = event.get("current_level_duration_seconds")
            if isinstance(duration_raw, (int, float)) and isfinite(duration_raw):
                duration = max(float(duration_raw), 0.0)
            elif start_dt is not None:
                for _candidate_event, candidate_dt in parsed_events[index + 1 :]:
                    if candidate_dt is None or candidate_dt < start_dt:
                        continue
                    duration = max((candidate_dt - start_dt).total_seconds(), 0.0)
                    break

            if duration is not None:
                level_duration_latest[level] = duration
                if duration > level_duration_peaks[level]:
                    level_duration_peaks[level] = duration
                level_duration_totals[level] += duration
                level_duration_samples[level] += 1
                minimum = level_duration_minimums[level]
                if minimum is None or duration < minimum:
                    level_duration_minimums[level] = duration
                level_duration_distributions[level].append(duration)
                last_level_duration_seconds = duration

    total_events = len(events)
    level_change_rate: float | None = (
        level_changes / total_events if total_events else None
    )

    timeline_window_seconds = _calculate_active_window_seconds(
        first_event_timestamp, last_event_timestamp
    )
    timeline_window_days: float | None = None
    events_per_day: float | None = None
    if timeline_window_seconds is not None:
        timeline_window_days = (
            timeline_window_seconds / 86400 if timeline_window_seconds else 0.0
        )
        if timeline_window_seconds > 0:
            events_per_day = total_events / (timeline_window_seconds / 86400)
        elif total_events:
            events_per_day = float(total_events)

    most_common_reason: str | None = None
    if reason_counts:
        most_common_reason = max(
            reason_counts, key=lambda item: reason_counts[item]
        )

    most_common_level: RuntimeStoreHealthLevel | None = None
    if level_counts and max(level_counts.values()) > 0:
        most_common_level = max(
            level_counts, key=lambda level_key: level_counts[level_key]
        )

    most_common_status: RuntimeStoreOverallStatus | None = None
    if status_counts and max(status_counts.values()) > 0:
        most_common_status = max(
            status_counts, key=lambda status_key: status_counts[status_key]
        )

    average_divergence_rate: float | None = None
    max_divergence_rate: float | None = None
    if divergence_rates:
        average_divergence_rate = sum(divergence_rates) / len(divergence_rates)
        max_divergence_rate = max(divergence_rates)

    level_duration_averages: dict[RuntimeStoreHealthLevel, float | None] = {}
    for level, total_duration in level_duration_totals.items():
        samples = level_duration_samples.get(level, 0)
        if samples > 0:
            level_duration_averages[level] = total_duration / samples
        else:
            level_duration_averages[level] = None

    level_duration_medians: dict[RuntimeStoreHealthLevel, float | None] = {}
    for level, durations in level_duration_distributions.items():
        if durations:
            level_duration_medians[level] = median(durations)
            if len(durations) > 1:
                level_duration_standard_deviations[level] = pstdev(durations)
            else:
                level_duration_standard_deviations[level] = 0.0
            percentiles = _calculate_duration_percentiles(durations)
            level_duration_percentiles[level] = percentiles
            alert_threshold = cast(dict[str, float], percentiles).get("p95")
            level_duration_alert_thresholds[level] = alert_threshold
            guard_limit = _LEVEL_DURATION_GUARD_LIMITS.get(level)
            if (
                guard_limit is not None
                and alert_threshold is not None
                and alert_threshold > guard_limit
            ):
                severity = _LEVEL_DURATION_GUARD_SEVERITY.get(level, "warning")
                recommendation = _LEVEL_DURATION_GUARD_RECOMMENDATIONS.get(level)
                level_duration_guard_alerts.append(
                    {
                        "level": level,
                        "percentile_label": "p95",
                        "percentile_rank": _LEVEL_DURATION_PERCENTILE_TARGETS["p95"],
                        "percentile_seconds": alert_threshold,
                        "guard_limit_seconds": guard_limit,
                        "severity": severity,
                        "recommended_action": recommendation,
                    }
                )
        else:
            level_duration_medians[level] = None
            level_duration_standard_deviations[level] = None
            level_duration_percentiles[level] = {}
            level_duration_alert_thresholds[level] = None

    summary: RuntimeStoreAssessmentTimelineSummary = {
        "total_events": total_events,
        "level_changes": level_changes,
        "level_change_rate": level_change_rate,
        "level_counts": level_counts,
        "status_counts": status_counts,
        "reason_counts": reason_counts,
        "distinct_reasons": len(reason_counts),
        "first_event_timestamp": first_event_timestamp,
        "last_event_timestamp": last_event_timestamp,
        "last_level": last_level,
        "last_status": last_status,
        "last_reason": last_reason,
        "last_recommended_action": last_recommended_action,
        "last_divergence_detected": last_divergence_detected,
        "last_divergence_rate": last_divergence_rate,
        "last_level_duration_seconds": last_level_duration_seconds,
        "timeline_window_seconds": timeline_window_seconds,
        "timeline_window_days": timeline_window_days,
        "events_per_day": events_per_day,
        "most_common_reason": most_common_reason,
        "most_common_level": most_common_level,
        "most_common_status": most_common_status,
        "average_divergence_rate": average_divergence_rate,
        "max_divergence_rate": max_divergence_rate,
        "level_duration_peaks": level_duration_peaks,
        "level_duration_latest": level_duration_latest,
        "level_duration_totals": level_duration_totals,
        "level_duration_samples": level_duration_samples,
        "level_duration_averages": level_duration_averages,
        "level_duration_minimums": level_duration_minimums,
        "level_duration_medians": level_duration_medians,
        "level_duration_standard_deviations": level_duration_standard_deviations,
        "level_duration_percentiles": level_duration_percentiles,
        "level_duration_alert_thresholds": level_duration_alert_thresholds,
        "level_duration_guard_alerts": level_duration_guard_alerts,
    }

    return summary


def _build_runtime_store_assessment_segments(
    events: Sequence[RuntimeStoreAssessmentEvent],
) -> list[RuntimeStoreAssessmentTimelineSegment]:
    """Return contiguous timeline segments derived from assessment events."""

    segments: list[RuntimeStoreAssessmentTimelineSegment] = []
    if not events:
        return segments

    parsed: list[tuple[RuntimeStoreAssessmentEvent, datetime | None]] = []
    for event in events:
        timestamp = event.get("timestamp")
        parsed.append((event, dt_util.parse_datetime(timestamp) if isinstance(timestamp, str) else None))

    for index, (event, start_dt) in enumerate(parsed):
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, str) or start_dt is None:
            continue

        segment: RuntimeStoreAssessmentTimelineSegment = {
            "start": timestamp,
            "level": cast(RuntimeStoreHealthLevel, event.get("level", "ok")),
        }

        status = event.get("status")
        if isinstance(status, str) and status in _RUNTIME_STORE_STATUS_LEVELS:
            segment["status"] = cast(RuntimeStoreOverallStatus, status)

        entry_status = event.get("entry_status")
        if isinstance(entry_status, str):
            segment["entry_status"] = cast(RuntimeStoreEntryStatus, entry_status)

        store_status = event.get("store_status")
        if isinstance(store_status, str):
            segment["store_status"] = cast(RuntimeStoreEntryStatus, store_status)

        reason = event.get("reason")
        if isinstance(reason, str):
            segment["reason"] = reason

        recommended_action = event.get("recommended_action")
        if isinstance(recommended_action, str):
            segment["recommended_action"] = recommended_action

        divergence_detected = event.get("divergence_detected")
        if isinstance(divergence_detected, bool):
            segment["divergence_detected"] = divergence_detected

        divergence_rate = event.get("divergence_rate")
        if isinstance(divergence_rate, (int, float)) and isfinite(divergence_rate):
            segment["divergence_rate"] = float(divergence_rate)

        checks = event.get("checks")
        if isinstance(checks, (int, float)):
            segment["checks"] = int(checks)

        divergence_events = event.get("divergence_events")
        if isinstance(divergence_events, (int, float)):
            segment["divergence_events"] = int(divergence_events)

        end_timestamp: str | None = None
        duration_seconds: float | None = None
        for candidate_event, candidate_dt in parsed[index + 1 :]:
            candidate_timestamp = candidate_event.get("timestamp")
            if not isinstance(candidate_timestamp, str) or candidate_dt is None:
                continue
            if candidate_dt < start_dt:
                continue
            end_timestamp = candidate_timestamp
            duration_seconds = max((candidate_dt - start_dt).total_seconds(), 0.0)
            break

        if end_timestamp is not None:
            segment["end"] = end_timestamp
        else:
            current_duration = event.get("current_level_duration_seconds")
            if isinstance(current_duration, (int, float)) and isfinite(current_duration):
                duration_seconds = max(float(current_duration), 0.0)

        if duration_seconds is not None:
            segment["duration_seconds"] = duration_seconds

        segments.append(segment)

    return segments


def _resolve_runtime_store_assessment_timeline_summary(
    history: Mapping[str, object],
    events: Sequence[RuntimeStoreAssessmentEvent],
) -> RuntimeStoreAssessmentTimelineSummary:
    """Return the timeline summary stored in ``history`` or recompute it."""

    timeline_summary_raw = history.get("assessment_timeline_summary")
    if isinstance(timeline_summary_raw, Mapping):
        return cast(
            RuntimeStoreAssessmentTimelineSummary,
            dict(timeline_summary_raw),
        )

    return _summarise_runtime_store_assessment_events(events)


def _record_runtime_store_assessment_event(
    history: RuntimeStoreHealthHistory,
    assessment: RuntimeStoreHealthAssessment,
    *,
    recorded: bool,
    previous_assessment: RuntimeStoreHealthAssessment | None,
    status: RuntimeStoreOverallStatus,
    entry_status: RuntimeStoreEntryStatus | None,
    store_status: RuntimeStoreEntryStatus | None,
) -> tuple[list[RuntimeStoreAssessmentEvent], RuntimeStoreAssessmentTimelineSummary]:
    """Persist the latest assessment event into ``history``."""

    events = _normalise_runtime_store_assessment_events(
        history.get("assessment_events")
    )
    if not events and previous_assessment is not None:
        events = _normalise_runtime_store_assessment_events(
            previous_assessment.get("events")
        )

    level = cast(RuntimeStoreHealthLevel, assessment.get("level", "ok"))
    previous_level = cast(
        RuntimeStoreHealthLevel | None, assessment.get("previous_level")
    )
    level_changed = previous_level != level

    reason = assessment.get("reason")
    if not isinstance(reason, str):
        reason = "Runtime store assessment recorded."

    recommended_action_raw = assessment.get("recommended_action")
    recommended_action: str | None
    if isinstance(recommended_action_raw, str):
        recommended_action = recommended_action_raw
    else:
        recommended_action = None

    divergence_detected = bool(assessment.get("divergence_detected"))

    divergence_rate_raw = assessment.get("divergence_rate")
    divergence_rate: float | None
    if isinstance(divergence_rate_raw, (int, float)) and isfinite(divergence_rate_raw):
        divergence_rate = float(divergence_rate_raw)
    else:
        divergence_rate = None

    checks_raw = assessment.get("checks", history.get("checks", 0))
    checks = int(checks_raw) if isinstance(checks_raw, (int, float)) else 0

    divergence_events_raw = assessment.get(
        "divergence_events", history.get("divergence_events", 0)
    )
    divergence_events = (
        int(divergence_events_raw)
        if isinstance(divergence_events_raw, (int, float))
        else 0
    )

    level_streak_raw = assessment.get(
        "level_streak", history.get("assessment_level_streak", 0)
    )
    level_streak = (
        int(level_streak_raw) if isinstance(level_streak_raw, (int, float)) else 0
    )

    escalations_raw = assessment.get(
        "escalations", history.get("assessment_escalations", 0)
    )
    escalations = (
        int(escalations_raw) if isinstance(escalations_raw, (int, float)) else 0
    )

    deescalations_raw = assessment.get(
        "deescalations", history.get("assessment_deescalations", 0)
    )
    deescalations = (
        int(deescalations_raw) if isinstance(deescalations_raw, (int, float)) else 0
    )

    current_duration_raw = assessment.get("current_level_duration_seconds")
    current_duration: float | None
    if isinstance(current_duration_raw, (int, float)) and isfinite(
        current_duration_raw
    ):
        current_duration = max(float(current_duration_raw), 0.0)
    else:
        current_duration = None

    should_record = recorded or level_changed
    if not should_record:
        history_events = list(events)
        timeline_summary = _resolve_runtime_store_assessment_timeline_summary(
            history,
            history_events,
        )
        return history_events, timeline_summary

    timestamp = cast(str | None, history.get("last_checked"))
    if timestamp is None:
        timestamp = dt_util.utcnow().isoformat()

    event: RuntimeStoreAssessmentEvent = {
        "timestamp": timestamp,
        "level": level,
        "previous_level": previous_level,
        "status": status,
        "entry_status": entry_status,
        "store_status": store_status,
        "reason": reason,
        "recommended_action": recommended_action,
        "divergence_detected": divergence_detected,
        "divergence_rate": divergence_rate,
        "checks": checks,
        "divergence_events": divergence_events,
        "level_streak": level_streak,
        "escalations": escalations,
        "deescalations": deescalations,
        "level_changed": level_changed,
    }

    if current_duration is not None:
        event["current_level_duration_seconds"] = current_duration

    if events:
        last_event = events[-1]
        if (
            last_event["timestamp"] == event["timestamp"]
            and last_event.get("level") == event["level"]
            and last_event.get("reason") == event["reason"]
            and last_event.get("status") == event["status"]
        ):
            events[-1] = event
        else:
            events.append(event)
    else:
        events.append(event)

    if len(events) > _RUNTIME_STORE_ASSESSMENT_EVENT_LIMIT:
        events = events[-_RUNTIME_STORE_ASSESSMENT_EVENT_LIMIT:]

    history_events = list(events)
    history["assessment_events"] = history_events
    timeline_summary = _summarise_runtime_store_assessment_events(history_events)
    history["assessment_timeline_summary"] = cast(
        RuntimeStoreAssessmentTimelineSummary,
        dict(timeline_summary),
    )

    return history_events, timeline_summary


def _safe_repr(value: Any, *, limit: int = 80) -> str:
    """Return a short, exception-safe representation of ``value``."""

    if value is None:
        return "None"

    try:
        rendered = repr(value)
    except Exception:  # pragma: no cover - defensive fallback
        rendered = object.__repr__(value)

    if len(rendered) > limit:
        return f"{rendered[: limit - 1]}…"
    return rendered


def _calculate_active_window_seconds(
    first_seen: str | None, last_seen: str | None
) -> float | None:
    """Return the duration between the first and last coercions when available."""

    if not first_seen or not last_seen:
        return None

    first_dt = dt_util.parse_datetime(first_seen)
    last_dt = dt_util.parse_datetime(last_seen)
    if first_dt is None or last_dt is None:
        return None

    window = (last_dt - first_dt).total_seconds()
    if window < 0:
        return 0.0
    return window


def get_runtime_performance_stats(
    runtime_data: PawControlRuntimeData | None,
) -> RuntimePerformanceStats | None:
    """Return runtime performance stats when present and mutable."""

    if runtime_data is None:
        return None

    performance_stats = getattr(runtime_data, "performance_stats", None)
    if not isinstance(performance_stats, MutableMapping):
        return None

    return cast(RuntimePerformanceStats, performance_stats)


def ensure_runtime_performance_stats(
    runtime_data: PawControlRuntimeData,
) -> RuntimePerformanceStats:
    """Return a mutable runtime performance stats mapping, initialising if needed."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is not None:
        return performance_stats

    runtime_data.performance_stats = cast(RuntimePerformanceStats, {})
    return runtime_data.performance_stats


def get_runtime_entity_factory_guard_metrics(
    runtime_data: PawControlRuntimeData | None,
) -> EntityFactoryGuardMetrics | None:
    """Return the cached entity factory guard metrics when available."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is None:
        return None

    metrics = performance_stats.get("entity_factory_guard_metrics")
    if not isinstance(metrics, MutableMapping):
        return None

    return cast(EntityFactoryGuardMetrics, metrics)


def get_runtime_store_health(
    runtime_data: PawControlRuntimeData | None,
) -> RuntimeStoreHealthHistory | None:
    """Return the stored runtime store compatibility history when available."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is None:
        return None

    history = performance_stats.get("runtime_store_health")
    if not isinstance(history, MutableMapping):
        return None

    return cast(RuntimeStoreHealthHistory, history)


def update_runtime_store_health(
    runtime_data: PawControlRuntimeData | None,
    snapshot: RuntimeStoreCompatibilitySnapshot,
    *,
    record_event: bool = True,
) -> RuntimeStoreHealthHistory | None:
    """Persist compatibility history derived from ``snapshot`` in runtime telemetry."""

    if runtime_data is None:
        return None

    performance_stats = ensure_runtime_performance_stats(runtime_data)

    stored_history = performance_stats.get("runtime_store_health")
    if isinstance(stored_history, MutableMapping):
        history = cast(RuntimeStoreHealthHistory, stored_history)
    else:
        history = cast(
            RuntimeStoreHealthHistory,
            {
                "schema_version": 1,
                "checks": 0,
                "status_counts": {},
                "divergence_events": 0,
            },
        )
        performance_stats["runtime_store_health"] = history

    status = snapshot["status"]
    entry_snapshot = snapshot.get("entry", {})
    store_snapshot = snapshot.get("store", {})
    entry_status = cast(RuntimeStoreEntryStatus | None, entry_snapshot.get("status"))
    store_status = cast(RuntimeStoreEntryStatus | None, store_snapshot.get("status"))
    entry_version = cast(int | None, entry_snapshot.get("version"))
    store_version = cast(int | None, store_snapshot.get("version"))
    entry_created_version = cast(int | None, entry_snapshot.get("created_version"))
    store_created_version = cast(int | None, store_snapshot.get("created_version"))
    divergence_detected = bool(snapshot.get("divergence_detected"))

    status_counts = history.get("status_counts")
    if not isinstance(status_counts, MutableMapping):
        status_counts = {}
        history["status_counts"] = status_counts

    checks = int(history.get("checks", 0) or 0)
    divergence_events = int(history.get("divergence_events", 0) or 0)

    effective_record = record_event
    if checks == 0 and not record_event:
        effective_record = True

    if effective_record:
        checks += 1
        status_counts[status] = int(status_counts.get(status, 0) or 0) + 1
        if divergence_detected:
            divergence_events += 1

    history["schema_version"] = 1
    history["checks"] = checks
    history["divergence_events"] = divergence_events
    history["last_checked"] = dt_util.utcnow().isoformat()
    history["last_status"] = cast(RuntimeStoreOverallStatus, status)
    history["last_entry_status"] = entry_status
    history["last_store_status"] = store_status
    history["last_entry_version"] = entry_version
    history["last_store_version"] = store_version
    history["last_entry_created_version"] = entry_created_version
    history["last_store_created_version"] = store_created_version
    history["divergence_detected"] = divergence_detected
    history["status_counts"] = cast(dict[RuntimeStoreOverallStatus, int], status_counts)

    previous_assessment = history.get("assessment")
    resolved_previous = None
    if isinstance(previous_assessment, Mapping):
        resolved_previous = cast(
            RuntimeStoreHealthAssessment,
            dict(previous_assessment),
        )

    assessment = _build_runtime_store_assessment(
        snapshot,
        history,
        recorded=effective_record,
        previous_assessment=resolved_previous,
    )

    events, timeline_summary = _record_runtime_store_assessment_event(
        history,
        assessment,
        recorded=effective_record,
        previous_assessment=resolved_previous,
        status=cast(RuntimeStoreOverallStatus, status),
        entry_status=entry_status,
        store_status=store_status,
    )
    segments = _build_runtime_store_assessment_segments(events)
    history["assessment_timeline_segments"] = cast(
        list[RuntimeStoreAssessmentTimelineSegment],
        list(segments),
    )
    assessment["events"] = list(events)
    assessment["timeline_summary"] = cast(
        RuntimeStoreAssessmentTimelineSummary,
        dict(timeline_summary),
    )
    assessment["timeline_segments"] = cast(
        list[RuntimeStoreAssessmentTimelineSegment],
        list(segments),
    )
    history["assessment"] = assessment

    return history


def _build_runtime_store_assessment(
    snapshot: RuntimeStoreCompatibilitySnapshot,
    history: RuntimeStoreHealthHistory,
    *,
    recorded: bool,
    previous_assessment: RuntimeStoreHealthAssessment | None,
) -> RuntimeStoreHealthAssessment:
    """Derive a runtime store risk assessment from telemetry."""

    checks = int(history.get("checks", 0) or 0)
    divergence_events = int(history.get("divergence_events", 0) or 0)
    divergence_rate = float(divergence_events) / checks if checks > 0 else None
    last_status = cast(RuntimeStoreOverallStatus | None, history.get("last_status"))
    entry_status = cast(
        RuntimeStoreEntryStatus | None, history.get("last_entry_status")
    )
    store_status = cast(
        RuntimeStoreEntryStatus | None, history.get("last_store_status")
    )
    divergence_detected = bool(history.get("divergence_detected"))
    status_for_level = last_status or snapshot["status"]

    level, reason = _RUNTIME_STORE_STATUS_LEVELS.get(
        status_for_level,
        (
            "ok",
            "Runtime store metadata matches the active schema.",
        ),
    )

    if level != "action_required":
        if entry_status in _RUNTIME_STORE_ENTRY_ACTION_STATUSES or (
            store_status in _RUNTIME_STORE_ENTRY_ACTION_STATUSES
        ):
            level = "action_required"
            reason = "Runtime store entry metadata falls outside the supported schema."
        elif (
            entry_status in _RUNTIME_STORE_ENTRY_WATCH_STATUSES
            or store_status in _RUNTIME_STORE_ENTRY_WATCH_STATUSES
        ) and level == "ok":
            level = "watch"
            reason = (
                "Runtime store metadata is pending an upgrade to the current schema."
            )

    if level == "ok":
        if divergence_detected:
            level = "watch"
            reason = (
                "The latest compatibility check detected divergence between caches."
            )
        elif (
            divergence_rate is not None
            and divergence_rate >= _DIVERGENCE_WATCH_THRESHOLD
        ):
            level = "watch"
            reason = "Recent compatibility checks reported divergence events."

    if (
        level == "watch"
        and divergence_rate is not None
        and divergence_rate >= _DIVERGENCE_ACTION_THRESHOLD
    ):
        level = "action_required"
        reason = "Runtime store divergence persists across recent compatibility checks."

    if level == "action_required" and status_for_level == "future_incompatible":
        reason = (
            "Runtime store caches were produced by a newer schema and must be reset."
        )

    recommended_action = _RUNTIME_STORE_RECOMMENDATIONS[level]

    previous_level = cast(
        RuntimeStoreHealthLevel | None,
        history.get("assessment_last_level"),
    )
    if previous_level is None and previous_assessment is not None:
        previous_level = cast(
            RuntimeStoreHealthLevel | None,
            previous_assessment.get("level"),
        )

    last_level_change = cast(str | None, history.get("assessment_last_level_change"))
    previous_last_level_change = last_level_change
    level_streak = int(history.get("assessment_level_streak", 0) or 0)
    escalations = int(history.get("assessment_escalations", 0) or 0)
    deescalations = int(history.get("assessment_deescalations", 0) or 0)
    last_checked = cast(str | None, history.get("last_checked"))

    previous_current_duration_raw = history.get(
        "assessment_current_level_duration_seconds"
    )
    if isinstance(previous_current_duration_raw, (int, float)) and isfinite(
        previous_current_duration_raw
    ):
        previous_current_duration = float(previous_current_duration_raw)
    else:
        previous_current_duration = 0.0
    if previous_current_duration < 0:
        previous_current_duration = 0.0

    level_durations_raw = history.get("assessment_level_durations")
    level_durations: dict[RuntimeStoreHealthLevel, float]
    if isinstance(level_durations_raw, Mapping):
        level_durations = {}
        for key, value in level_durations_raw.items():
            if key not in _RUNTIME_STORE_LEVEL_ORDER:
                continue
            if not isinstance(value, (int, float)):
                continue
            if not isfinite(value):
                continue
            level_durations[key] = max(float(value), 0.0)
    else:
        level_durations = {}

    level_changed = previous_level != level

    parsed_last_checked = dt_util.parse_datetime(last_checked) if last_checked else None
    parsed_last_change = (
        dt_util.parse_datetime(previous_last_level_change)
        if previous_last_level_change
        else None
    )
    elapsed_since_change: float | None = None
    if parsed_last_checked and parsed_last_change:
        elapsed_since_change = max(
            (parsed_last_checked - parsed_last_change).total_seconds(), 0.0
        )

    current_level_duration = previous_current_duration

    if level_changed:
        level_streak = 1
        last_level_change = last_checked
        if previous_level is not None:
            previous_level_order = _RUNTIME_STORE_LEVEL_ORDER[previous_level]
            current_order = _RUNTIME_STORE_LEVEL_ORDER[level]
            if current_order > previous_level_order:
                escalations += 1
            elif current_order < previous_level_order:
                deescalations += 1
            resolved_previous_duration = previous_current_duration
            if elapsed_since_change is not None:
                resolved_previous_duration = elapsed_since_change
            previous_total = max(level_durations.get(previous_level, 0.0), 0.0)
            base_previous_total = max(previous_total - previous_current_duration, 0.0)
            level_durations[previous_level] = (
                base_previous_total + resolved_previous_duration
            )
        current_level_duration = 0.0
    else:
        if recorded:
            level_streak = level_streak + 1 if level_streak > 0 else 1
        elif level_streak <= 0:
            level_streak = 1
            if last_level_change is None:
                last_level_change = last_checked
        if elapsed_since_change is not None:
            current_level_duration = elapsed_since_change

    history["assessment_last_level"] = level
    history["assessment_last_level_change"] = last_level_change
    history["assessment_level_streak"] = level_streak
    history["assessment_escalations"] = escalations
    history["assessment_deescalations"] = deescalations

    previous_total_for_level = max(level_durations.get(level, 0.0), 0.0)
    previous_baseline = previous_total_for_level
    if not level_changed:
        previous_baseline = max(
            previous_total_for_level - previous_current_duration, 0.0
        )
    resolved_current_duration = (
        current_level_duration
        if elapsed_since_change is not None
        else previous_current_duration
    )

    level_durations[level] = previous_baseline + resolved_current_duration

    for level_key in _RUNTIME_STORE_LEVEL_ORDER:
        level_durations.setdefault(level_key, 0.0)

    history["assessment_level_durations"] = level_durations
    history["assessment_current_level_duration_seconds"] = resolved_current_duration

    assessment: RuntimeStoreHealthAssessment = {
        "level": level,
        "previous_level": previous_level,
        "reason": reason,
        "recommended_action": recommended_action,
        "divergence_rate": divergence_rate,
        "checks": checks,
        "divergence_events": divergence_events,
        "last_status": last_status,
        "last_entry_status": entry_status,
        "last_store_status": store_status,
        "last_checked": last_checked,
        "divergence_detected": divergence_detected,
        "level_streak": level_streak,
        "last_level_change": last_level_change,
        "escalations": escalations,
        "deescalations": deescalations,
        "level_durations": dict(level_durations),
        "current_level_duration_seconds": resolved_current_duration,
    }

    return assessment


def update_runtime_entity_factory_guard_metrics(
    runtime_data: PawControlRuntimeData | None,
    *,
    runtime_floor: float,
    actual_duration: float,
    event: EntityFactoryGuardEvent,
    baseline_floor: float,
    max_floor: float,
    enforce_min_runtime: bool,
) -> EntityFactoryGuardMetrics | None:
    """Persist the latest runtime guard calibration in the performance stats."""

    if runtime_data is None:
        return None

    performance_stats = ensure_runtime_performance_stats(runtime_data)

    stored_metrics = performance_stats.get("entity_factory_guard_metrics")
    if isinstance(stored_metrics, MutableMapping):
        metrics = cast(EntityFactoryGuardMetrics, stored_metrics)
    else:
        metrics = cast(
            EntityFactoryGuardMetrics,
            {
                "schema_version": 1,
                "samples": 0,
                "stable_samples": 0,
                "expansions": 0,
                "contractions": 0,
            },
        )
        performance_stats["entity_factory_guard_metrics"] = metrics

    metrics["schema_version"] = 1
    previous_floor_raw: object | None = None
    if isinstance(stored_metrics, MutableMapping):
        previous_floor_raw = stored_metrics.get("runtime_floor")
    previous_floor: float | None = None
    if isinstance(previous_floor_raw, (int, float)) and isfinite(previous_floor_raw):
        previous_floor = float(previous_floor_raw)
    previous_samples = int(metrics.get("samples", 0) or 0)
    metrics.setdefault("stable_samples", 0)
    metrics.setdefault("expansions", 0)
    metrics.setdefault("contractions", 0)
    previous_stable_ratio = (
        float(metrics["stable_ratio"])
        if isinstance(metrics.get("stable_ratio"), (int, float))
        else None
    )
    metrics["baseline_floor"] = max(baseline_floor, 0.0)
    metrics["max_floor"] = max(max_floor, 0.0)
    metrics["runtime_floor"] = max(runtime_floor, 0.0)
    metrics["runtime_floor_delta"] = max(
        metrics["runtime_floor"] - metrics["baseline_floor"], 0.0
    )
    metrics["peak_runtime_floor"] = max(
        metrics["runtime_floor"],
        float(metrics.get("peak_runtime_floor", 0.0) or 0.0),
    )
    lowest_runtime_floor = metrics.get("lowest_runtime_floor")
    if isinstance(lowest_runtime_floor, (int, float)) and lowest_runtime_floor > 0:
        metrics["lowest_runtime_floor"] = min(
            lowest_runtime_floor,
            max(metrics["runtime_floor"], metrics["baseline_floor"]),
        )
    else:
        metrics["lowest_runtime_floor"] = max(
            metrics["runtime_floor"], metrics["baseline_floor"]
        )
    duration = max(actual_duration, 0.0)
    metrics["last_actual_duration"] = duration
    floor = metrics["runtime_floor"] or runtime_floor
    metrics["last_duration_ratio"] = duration / floor if floor > 0 else 0.0
    metrics["last_event"] = event
    metrics["last_updated"] = dt_util.utcnow().isoformat()
    metrics["enforce_min_runtime"] = enforce_min_runtime

    if previous_floor is not None:
        floor_change = metrics["runtime_floor"] - previous_floor
        metrics["last_floor_change"] = floor_change
        metrics["last_floor_change_ratio"] = (
            floor_change / previous_floor if previous_floor > 0 else 0.0
        )
    else:
        metrics.setdefault("last_floor_change", 0.0)
        metrics.setdefault("last_floor_change_ratio", 0.0)

    metrics["samples"] = previous_samples + 1
    samples = metrics["samples"]

    average_duration = metrics.get("average_duration")
    if isinstance(average_duration, (int, float)) and previous_samples > 0:
        metrics["average_duration"] = (
            (float(average_duration) * previous_samples) + duration
        ) / samples
    else:
        metrics["average_duration"] = duration

    max_duration = metrics.get("max_duration")
    if not isinstance(max_duration, (int, float)):
        metrics["max_duration"] = duration
    else:
        metrics["max_duration"] = max(float(max_duration), duration)

    min_duration = metrics.get("min_duration")
    if not isinstance(min_duration, (int, float)) or previous_samples == 0:
        metrics["min_duration"] = duration
    else:
        metrics["min_duration"] = min(float(min_duration), duration)

    if event == "expand":
        metrics["expansions"] = int(metrics.get("expansions", 0) or 0) + 1
        metrics["last_expansion_duration"] = duration
    elif event == "contract":
        metrics["contractions"] = int(metrics.get("contractions", 0) or 0) + 1
        metrics["last_contraction_duration"] = duration
    elif event == "stable":
        metrics["stable_samples"] = int(metrics.get("stable_samples", 0) or 0) + 1
    else:
        metrics.setdefault("stable_samples", int(metrics.get("stable_samples", 0) or 0))
        metrics.setdefault("expansions", int(metrics.get("expansions", 0) or 0))
        metrics.setdefault("contractions", int(metrics.get("contractions", 0) or 0))

    stable_run = int(metrics.get("consecutive_stable_samples", 0) or 0)
    longest_run = int(metrics.get("longest_stable_run", 0) or 0)
    if event == "stable":
        stable_run += 1
        if stable_run > longest_run:
            longest_run = stable_run
    else:
        stable_run = 0
    metrics["consecutive_stable_samples"] = stable_run
    metrics["longest_stable_run"] = longest_run

    if samples > 0:
        metrics["stable_ratio"] = float(metrics.get("stable_samples", 0)) / samples
        metrics["expansion_ratio"] = float(metrics.get("expansions", 0)) / samples
        metrics["contraction_ratio"] = float(metrics.get("contractions", 0)) / samples
        metrics["volatility_ratio"] = (
            float(metrics.get("expansions", 0) + metrics.get("contractions", 0))
            / samples
        )
    else:
        metrics["stable_ratio"] = 0.0
        metrics["expansion_ratio"] = 0.0
        metrics["contraction_ratio"] = 0.0
        metrics["volatility_ratio"] = 0.0

    existing_recent = metrics.get("recent_durations")
    if isinstance(existing_recent, Sequence) and not isinstance(
        existing_recent, (str, bytes, bytearray)
    ):
        recent: list[float] = [
            max(float(sample), 0.0)
            for sample in existing_recent
            if isinstance(sample, (int, float)) and isfinite(float(sample))
        ]
    else:
        recent = []

    recent.append(duration)
    if len(recent) > 5:
        recent = recent[-5:]

    metrics["recent_durations"] = recent
    recent_average = sum(recent) / len(recent)
    recent_max = max(recent)
    recent_min = min(recent)
    recent_span = max(recent_max - recent_min, 0.0)
    metrics["recent_average_duration"] = recent_average
    metrics["recent_max_duration"] = recent_max
    metrics["recent_min_duration"] = recent_min
    metrics["recent_duration_span"] = recent_span
    metrics["recent_jitter_ratio"] = recent_span / floor if floor > 0 else recent_span
    metrics["recent_samples"] = len(recent)

    existing_events = metrics.get("recent_events")
    if isinstance(existing_events, Sequence) and not isinstance(
        existing_events, (str, bytes, bytearray)
    ):
        recent_events: list[EntityFactoryGuardEvent] = [
            cast(EntityFactoryGuardEvent, event_name)
            for event_name in existing_events
            if isinstance(event_name, str) and event_name
        ]
    else:
        recent_events = []

    recent_events.append(event)
    if len(recent_events) > 5:
        recent_events = recent_events[-5:]

    metrics["recent_events"] = recent_events
    recent_stable_samples = sum(1 for name in recent_events if name == "stable")
    metrics["recent_stable_samples"] = recent_stable_samples
    if recent_events:
        recent_stable_ratio = recent_stable_samples / len(recent_events)
    else:
        recent_stable_ratio = 0.0
    metrics["recent_stable_ratio"] = recent_stable_ratio

    duration_span = max(metrics["max_duration"] - metrics["min_duration"], 0.0)
    metrics["duration_span"] = duration_span
    metrics["jitter_ratio"] = duration_span / floor if floor > 0 else duration_span

    baseline_ratio = (
        previous_stable_ratio
        if previous_stable_ratio is not None
        else metrics["stable_ratio"]
    )
    if recent_events:
        trend_delta = recent_stable_ratio - baseline_ratio
        if trend_delta > 0.05:
            trend: EntityFactoryGuardStabilityTrend = "improving"
        elif trend_delta < -0.05:
            trend = "regressing"
        else:
            trend = "steady"
    else:
        trend = "unknown"

    metrics["stability_trend"] = trend

    return metrics


def record_bool_coercion_event(
    *, value: Any, default: bool, result: bool, reason: str
) -> None:
    """Record details about a boolean coercion for diagnostics."""

    metrics = _BOOL_COERCION_METRICS
    metrics["total"] = metrics.get("total", 0) + 1

    iso_timestamp = dt_util.utcnow().isoformat()
    if metrics.get("first_seen") is None:
        metrics["first_seen"] = iso_timestamp
    metrics["last_seen"] = iso_timestamp
    if metrics.get("last_reset") is None:
        metrics["last_reset"] = iso_timestamp

    if reason in {"none", "blank_string"}:
        metrics["defaulted"] = metrics.get("defaulted", 0) + 1
    if reason == "fallback":
        metrics["fallback"] = metrics.get("fallback", 0) + 1

    value_type = type(value).__name__ if value is not None else "NoneType"
    value_repr = _safe_repr(value)
    type_counts = metrics.setdefault("type_counts", {})
    type_counts[value_type] = type_counts.get(value_type, 0) + 1

    reason_counts = metrics.setdefault("reason_counts", {})
    reason_counts[reason] = reason_counts.get(reason, 0) + 1

    samples = metrics.setdefault("samples", [])
    if len(samples) < _BOOL_COERCION_SAMPLE_LIMIT:
        samples.append(
            {
                "value_type": value_type,
                "value_repr": value_repr,
                "default": default,
                "result": result,
                "reason": reason,
            }
        )

    metrics["last_reason"] = reason
    metrics["last_value_type"] = value_type
    metrics["last_value_repr"] = value_repr
    metrics["last_result"] = bool(result)
    metrics["last_default"] = bool(default)


def get_bool_coercion_metrics() -> BoolCoercionMetrics:
    """Return a defensive copy of the collected bool coercion metrics."""

    first_seen = _BOOL_COERCION_METRICS.get("first_seen")
    last_seen = _BOOL_COERCION_METRICS.get("last_seen")
    snapshot: BoolCoercionMetrics = {
        "total": int(_BOOL_COERCION_METRICS.get("total", 0)),
        "defaulted": int(_BOOL_COERCION_METRICS.get("defaulted", 0)),
        "fallback": int(_BOOL_COERCION_METRICS.get("fallback", 0)),
        "reset_count": int(_BOOL_COERCION_METRICS.get("reset_count", 0)),
        "type_counts": dict(_BOOL_COERCION_METRICS.get("type_counts", {})),
        "reason_counts": dict(_BOOL_COERCION_METRICS.get("reason_counts", {})),
        "samples": [
            {
                "value_type": sample["value_type"],
                "value_repr": sample["value_repr"],
                "default": bool(sample["default"]),
                "result": bool(sample["result"]),
                "reason": sample["reason"],
            }
            for sample in _BOOL_COERCION_METRICS.get("samples", [])
        ],
        "first_seen": first_seen,
        "last_seen": last_seen,
        "active_window_seconds": _calculate_active_window_seconds(
            first_seen, last_seen
        ),
        "last_reset": _BOOL_COERCION_METRICS.get("last_reset"),
        "last_reason": _BOOL_COERCION_METRICS.get("last_reason"),
        "last_value_type": _BOOL_COERCION_METRICS.get("last_value_type"),
        "last_value_repr": _BOOL_COERCION_METRICS.get("last_value_repr"),
        "last_result": _BOOL_COERCION_METRICS.get("last_result"),
        "last_default": _BOOL_COERCION_METRICS.get("last_default"),
    }
    return snapshot


def reset_bool_coercion_metrics() -> None:
    """Reset collected bool coercion metrics (primarily for testing)."""

    reset_count = int(_BOOL_COERCION_METRICS.get("reset_count", 0)) + 1
    iso_timestamp = dt_util.utcnow().isoformat()

    _BOOL_COERCION_METRICS["total"] = 0
    _BOOL_COERCION_METRICS["defaulted"] = 0
    _BOOL_COERCION_METRICS["fallback"] = 0
    _BOOL_COERCION_METRICS["reset_count"] = reset_count
    _BOOL_COERCION_METRICS["type_counts"] = {}
    _BOOL_COERCION_METRICS["reason_counts"] = {}
    _BOOL_COERCION_METRICS["samples"] = []
    _BOOL_COERCION_METRICS["first_seen"] = None
    _BOOL_COERCION_METRICS["last_seen"] = None
    _BOOL_COERCION_METRICS["active_window_seconds"] = None
    _BOOL_COERCION_METRICS["last_reset"] = iso_timestamp
    _BOOL_COERCION_METRICS["last_reason"] = None
    _BOOL_COERCION_METRICS["last_value_type"] = None
    _BOOL_COERCION_METRICS["last_value_repr"] = None
    _BOOL_COERCION_METRICS["last_result"] = None
    _BOOL_COERCION_METRICS["last_default"] = None


def summarise_bool_coercion_metrics(*, sample_limit: int = 5) -> BoolCoercionSummary:
    """Return a condensed bool coercion snapshot for observability exports."""

    metrics = get_bool_coercion_metrics()
    reason_counts_raw = metrics.get("reason_counts", {})
    type_counts_raw = metrics.get("type_counts", {})

    reason_counts = (
        {key: int(reason_counts_raw[key]) for key in sorted(reason_counts_raw)}
        if isinstance(reason_counts_raw, Mapping)
        else {}
    )
    type_counts = (
        {key: int(type_counts_raw[key]) for key in sorted(type_counts_raw)}
        if isinstance(type_counts_raw, Mapping)
        else {}
    )

    samples = metrics.get("samples", [])
    if not isinstance(samples, Sequence):
        samples_list: list[BoolCoercionSample] = []
    else:
        limited_samples = tuple(samples)[: max(0, sample_limit)]
        samples_list = [
            {
                "value_type": sample.get("value_type", ""),
                "value_repr": sample.get("value_repr", ""),
                "default": bool(sample.get("default", False)),
                "result": bool(sample.get("result", False)),
                "reason": sample.get("reason", ""),
            }
            for sample in limited_samples
            if isinstance(sample, Mapping)
        ]

    summary: BoolCoercionSummary = {
        "recorded": bool(metrics.get("total", 0) or metrics.get("reset_count", 0)),
        "total": int(metrics.get("total", 0)),
        "defaulted": int(metrics.get("defaulted", 0)),
        "fallback": int(metrics.get("fallback", 0)),
        "reset_count": int(metrics.get("reset_count", 0)),
        "first_seen": metrics.get("first_seen"),
        "last_seen": metrics.get("last_seen"),
        "last_reset": metrics.get("last_reset"),
        "active_window_seconds": metrics.get("active_window_seconds"),
        "last_reason": metrics.get("last_reason"),
        "last_value_type": metrics.get("last_value_type"),
        "last_value_repr": metrics.get("last_value_repr"),
        "last_result": metrics.get("last_result"),
        "last_default": metrics.get("last_default"),
        "reason_counts": reason_counts,
        "type_counts": type_counts,
        "samples": samples_list,
    }

    return summary


def get_runtime_bool_coercion_summary(
    runtime_data: PawControlRuntimeData | None,
) -> BoolCoercionSummary | None:
    """Return the cached bool coercion summary when stored in runtime stats."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is None:
        return None

    summary = performance_stats.get("bool_coercion_summary")
    if not isinstance(summary, Mapping):
        return None

    return cast(BoolCoercionSummary, dict(summary))


def update_runtime_bool_coercion_summary(
    runtime_data: PawControlRuntimeData | None,
    *,
    sample_limit: int = 5,
) -> BoolCoercionSummary:
    """Persist the latest bool coercion summary to runtime performance stats."""

    summary = summarise_bool_coercion_metrics(sample_limit=sample_limit)

    if runtime_data is not None:
        performance_stats = ensure_runtime_performance_stats(runtime_data)
        performance_stats["bool_coercion_summary"] = cast(
            BoolCoercionSummary, dict(summary)
        )
    return summary


def _as_int(value: Any) -> int:
    """Return ``value`` coerced to an integer when possible."""

    try:
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _as_list(value: Any) -> list[str]:
    """Return ``value`` normalised as a list of strings."""

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [str(item) for item in value if item is not None]
    if value is None:
        return []
    return [str(value)]


def summarise_reconfigure_options(
    options: ConfigEntryOptionsPayload
    | ReconfigureOptionsUpdates
    | JSONLikeMapping
    | None,
) -> ReconfigureTelemetrySummary | None:
    """Build a condensed telemetry payload from config-entry options."""

    if not isinstance(options, Mapping):
        return None

    telemetry_raw = options.get("reconfigure_telemetry")
    if not isinstance(telemetry_raw, Mapping):
        return None

    telemetry = cast(ReconfigureTelemetry, telemetry_raw)

    warnings = _as_list(telemetry.get("compatibility_warnings"))
    merge_notes = _as_list(telemetry.get("merge_notes"))
    health_summary = telemetry.get("health_summary")
    healthy = True
    health_issues: list[str] = []
    health_warnings: list[str] = []
    if isinstance(health_summary, Mapping):
        healthy = bool(health_summary.get("healthy", True))
        health_issues = _as_list(health_summary.get("issues"))
        health_warnings = _as_list(health_summary.get("warnings"))

    timestamp = str(telemetry.get("timestamp") or options.get("last_reconfigure") or "")
    requested_profile = str(telemetry.get("requested_profile", ""))
    previous_profile = str(
        telemetry.get("previous_profile") or options.get("previous_profile") or ""
    )

    summary: ReconfigureTelemetrySummary = {
        "timestamp": timestamp,
        "requested_profile": requested_profile,
        "previous_profile": previous_profile,
        "dogs_count": _as_int(telemetry.get("dogs_count")),
        "estimated_entities": _as_int(telemetry.get("estimated_entities")),
        "version": _as_int(telemetry.get("version")),
        "warnings": warnings,
        "warning_count": len(warnings),
        "merge_notes": merge_notes,
        "merge_note_count": len(merge_notes),
        "healthy": healthy,
        "health_issues": health_issues,
        "health_issue_count": len(health_issues),
        "health_warnings": health_warnings,
        "health_warning_count": len(health_warnings),
    }

    return summary


def get_runtime_reconfigure_summary(
    runtime_data: PawControlRuntimeData,
) -> ReconfigureTelemetrySummary | None:
    """Return the cached reconfigure summary stored in performance stats."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is None:
        return None

    summary = performance_stats.get("reconfigure_summary")
    if not isinstance(summary, Mapping):
        return None

    return cast(ReconfigureTelemetrySummary, dict(summary))


def update_runtime_reconfigure_summary(
    runtime_data: PawControlRuntimeData,
) -> ReconfigureTelemetrySummary | None:
    """Synchronise runtime reconfigure telemetry with the active config entry."""

    coordinator = getattr(runtime_data, "coordinator", None)
    entry = getattr(coordinator, "config_entry", None)
    options = getattr(entry, "options", None)

    summary = summarise_reconfigure_options(options)

    performance_stats = ensure_runtime_performance_stats(runtime_data)

    if summary is None:
        performance_stats.pop("reconfigure_summary", None)
        return None

    performance_stats["reconfigure_summary"] = summary
    return summary


def get_runtime_resilience_summary(
    runtime_data: PawControlRuntimeData,
) -> CoordinatorResilienceSummary | None:
    """Return the cached resilience summary from performance statistics."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is None:
        return None

    summary = performance_stats.get("resilience_summary")
    if not isinstance(summary, Mapping):
        return None

    return cast(CoordinatorResilienceSummary, dict(summary))


def get_runtime_resilience_diagnostics(
    runtime_data: PawControlRuntimeData,
) -> CoordinatorResilienceDiagnostics | None:
    """Return the cached resilience diagnostics payload when available."""

    performance_stats = get_runtime_performance_stats(runtime_data)
    if performance_stats is None:
        return None

    diagnostics = performance_stats.get("resilience_diagnostics")
    if not isinstance(diagnostics, Mapping):
        return None

    payload: CoordinatorResilienceDiagnostics = {}

    breakers = diagnostics.get("breakers")
    if isinstance(breakers, Mapping):
        payload["breakers"] = {
            str(name): cast(CircuitBreakerStatsPayload, dict(values))
            for name, values in breakers.items()
            if isinstance(values, Mapping)
        }

    summary = diagnostics.get("summary")
    if isinstance(summary, Mapping):
        payload["summary"] = cast(CoordinatorResilienceSummary, dict(summary))

    if not payload:
        return None

    return payload


def update_runtime_resilience_summary(
    runtime_data: PawControlRuntimeData,
    summary: CoordinatorResilienceSummary | None,
) -> CoordinatorResilienceSummary | None:
    """Persist the latest resilience summary in runtime performance stats."""

    performance_stats = ensure_runtime_performance_stats(runtime_data)

    if summary is None:
        performance_stats.pop("resilience_summary", None)
        diagnostics = performance_stats.get("resilience_diagnostics")
        if isinstance(diagnostics, MutableMapping):
            diagnostics.pop("summary", None)
            if diagnostics:
                performance_stats["resilience_diagnostics"] = cast(
                    CoordinatorResilienceDiagnostics, dict(diagnostics)
                )
            else:
                performance_stats.pop("resilience_diagnostics", None)
        else:
            performance_stats.pop("resilience_diagnostics", None)
        return None

    stored_summary = cast(CoordinatorResilienceSummary, dict(summary))
    performance_stats["resilience_summary"] = stored_summary

    diagnostics = performance_stats.get("resilience_diagnostics")
    diagnostics_payload: CoordinatorResilienceDiagnostics
    if isinstance(diagnostics, Mapping):
        diagnostics_payload = cast(CoordinatorResilienceDiagnostics, dict(diagnostics))
    else:
        diagnostics_payload = {}

    diagnostics_payload["summary"] = stored_summary
    performance_stats["resilience_diagnostics"] = diagnostics_payload
    return stored_summary


def update_runtime_resilience_diagnostics(
    runtime_data: PawControlRuntimeData,
    diagnostics: CoordinatorResilienceDiagnostics | None,
) -> CoordinatorResilienceDiagnostics | None:
    """Persist the latest resilience diagnostics payload in runtime stats."""

    performance_stats = ensure_runtime_performance_stats(runtime_data)

    if diagnostics is None:
        performance_stats.pop("resilience_diagnostics", None)
        performance_stats.pop("resilience_summary", None)
        return None

    payload: CoordinatorResilienceDiagnostics = {}

    breakers = diagnostics.get("breakers")
    if isinstance(breakers, Mapping):
        payload["breakers"] = {
            str(name): cast(CircuitBreakerStatsPayload, dict(values))
            for name, values in breakers.items()
            if isinstance(values, Mapping)
        }

    summary = diagnostics.get("summary")
    if isinstance(summary, Mapping):
        stored_summary = cast(CoordinatorResilienceSummary, dict(summary))
        payload["summary"] = stored_summary
        performance_stats["resilience_summary"] = stored_summary
    else:
        performance_stats.pop("resilience_summary", None)

    performance_stats["resilience_diagnostics"] = payload
    return payload


def record_door_sensor_persistence_failure(
    runtime_data: PawControlRuntimeData | None,
    *,
    dog_id: str,
    dog_name: str | None = None,
    door_sensor: str | None = None,
    settings: DoorSensorSettingsPayload | JSONLikeMapping | None = None,
    error: Exception | str | None = None,
    limit: int = 10,
) -> DoorSensorPersistenceFailure | None:
    """Append door sensor persistence failure telemetry to runtime stats."""

    if runtime_data is None:
        return None

    performance_stats = ensure_runtime_performance_stats(runtime_data)

    failures_raw = performance_stats.get("door_sensor_failures")
    failures: list[DoorSensorPersistenceFailure]
    if isinstance(failures_raw, list):
        failures = cast(list[DoorSensorPersistenceFailure], failures_raw)
    elif isinstance(failures_raw, Sequence):
        failures = [
            cast(DoorSensorPersistenceFailure, dict(entry))
            for entry in failures_raw
            if isinstance(entry, Mapping)
        ]
    else:
        failures = []

    failure: DoorSensorPersistenceFailure = {
        "dog_id": dog_id,
        "recorded_at": dt_util.utcnow().isoformat(),
    }

    if dog_name is not None:
        failure["dog_name"] = dog_name

    if door_sensor is not None:
        failure["door_sensor"] = door_sensor

    if settings is not None:
        failure["settings"] = cast(DoorSensorSettingsPayload, dict(settings))

    if error is not None:
        failure["error"] = str(error)

    failures.append(failure)

    if limit > 0 and len(failures) > limit:
        del failures[:-limit]

    performance_stats["door_sensor_failures"] = failures
    performance_stats["door_sensor_failure_count"] = len(failures)
    performance_stats["last_door_sensor_failure"] = failure

    summaries_raw = performance_stats.get("door_sensor_failure_summary")
    summaries: dict[str, DoorSensorFailureSummary]
    if isinstance(summaries_raw, Mapping):
        summaries = {
            str(key): cast(DoorSensorFailureSummary, dict(value))
            for key, value in summaries_raw.items()
            if isinstance(key, str) and isinstance(value, Mapping)
        }
    else:
        summaries = {}

    summary = summaries.get(dog_id)
    if summary is None:
        summary = {
            "dog_id": dog_id,
            "failure_count": 0,
        }

    summary["failure_count"] = int(summary.get("failure_count", 0)) + 1
    if "dog_name" in failure:
        summary["dog_name"] = failure.get("dog_name")
    summary["last_failure"] = failure

    summaries[dog_id] = cast(DoorSensorFailureSummary, dict(summary))
    performance_stats["door_sensor_failure_summary"] = summaries

    error_history_raw = getattr(runtime_data, "error_history", None)
    if isinstance(error_history_raw, list):
        error_history = cast(list[RuntimeErrorHistoryEntry], error_history_raw)
        error_entry: RuntimeErrorHistoryEntry = {
            "timestamp": failure["recorded_at"],
            "source": "door_sensor_persistence",
            "dog_id": dog_id,
        }
        if door_sensor is not None:
            error_entry["door_sensor"] = door_sensor
        if error is not None:
            error_entry["error"] = str(error)
        error_history.append(error_entry)
        if len(error_history) > 50:
            del error_history[:-50]

    return failure
