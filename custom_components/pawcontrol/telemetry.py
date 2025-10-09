"""Telemetry helpers shared between PawControl services and coordinators."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, cast

from .types import (
    PawControlRuntimeData,
    ReconfigureTelemetry,
    ReconfigureTelemetrySummary,
)


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
    options: Mapping[str, Any] | MutableMapping[str, Any] | None,
) -> ReconfigureTelemetrySummary | None:
    """Build a condensed telemetry payload from config-entry options."""

    if not isinstance(options, Mapping):
        return None

    telemetry_raw = options.get("reconfigure_telemetry")
    if not isinstance(telemetry_raw, Mapping):
        return None

    telemetry = cast(ReconfigureTelemetry, telemetry_raw)

    warnings = _as_list(telemetry.get("compatibility_warnings"))
    health_summary = telemetry.get("health_summary")
    healthy = True
    health_issues: list[str] = []
    health_warnings: list[str] = []
    if isinstance(health_summary, Mapping):
        healthy = bool(health_summary.get("healthy", True))
        health_issues = _as_list(health_summary.get("issues"))
        health_warnings = _as_list(health_summary.get("warnings"))

    timestamp = str(
        telemetry.get("timestamp")
        or options.get("last_reconfigure")
        or ""
    )
    requested_profile = str(telemetry.get("requested_profile", ""))
    previous_profile = str(
        telemetry.get("previous_profile")
        or options.get("previous_profile")
        or ""
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

    performance_stats = getattr(runtime_data, "performance_stats", None)
    if not isinstance(performance_stats, Mapping):
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

    performance_stats = getattr(runtime_data, "performance_stats", None)
    if not isinstance(performance_stats, MutableMapping):
        runtime_data.performance_stats = {}
        performance_stats = runtime_data.performance_stats

    if summary is None:
        performance_stats.pop("reconfigure_summary", None)
        return None

    performance_stats["reconfigure_summary"] = summary
    return summary
