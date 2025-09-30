"""Helper functions for coordinator diagnostics and security reporting."""

from __future__ import annotations

from typing import Any, Mapping

from .coordinator_runtime import RuntimeCycleInfo


def build_performance_snapshot(
    stats: Mapping[str, Any],
    last_cycle: RuntimeCycleInfo | None,
) -> dict[str, Any]:
    """Compose a diagnostics snapshot from coordinator statistics."""

    snapshot = {
        "update_counts": dict(stats.get("update_counts", {})),
        "performance_metrics": dict(stats.get("performance_metrics", {})),
        "adaptive_polling": dict(stats.get("adaptive_polling", {})),
        "entity_budget": dict(stats.get("entity_budget", {})),
    }
    if last_cycle is not None:
        snapshot["last_cycle"] = last_cycle.to_dict()
    return snapshot


def build_security_scorecard(
    notification_status: Mapping[str, Any] | None,
    *,
    adaptive_interval: float,
    configured_interval: float,
) -> dict[str, Any]:
    """Return a structured security scorecard for diagnostics surfaces."""

    adaptive_check = {
        "pass": adaptive_interval <= configured_interval,
        "current_interval_s": round(adaptive_interval, 3),
        "configured_interval_s": round(configured_interval, 3),
    }

    webhook_status = notification_status or {}
    webhook_check = {
        "pass": bool(webhook_status.get("secure", True)),
        "configured": bool(webhook_status.get("configured", False)),
        "insecure_configs": webhook_status.get("insecure_configs", ()),
        "hmac_ready": bool(webhook_status.get("hmac_ready", False)),
    }

    overall_pass = adaptive_check["pass"] and webhook_check["pass"]
    return {
        "status": "pass" if overall_pass else "fail",
        "checks": {
            "adaptive_polling": adaptive_check,
            "webhooks": webhook_check,
        },
    }
