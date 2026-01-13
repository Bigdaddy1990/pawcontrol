"""Observability helpers that keep :mod:`coordinator` concise."""
from __future__ import annotations

import sys
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from datetime import datetime
from logging import getLogger
from math import isfinite
from typing import Any
from typing import cast
from typing import Final
from typing import Literal

from .coordinator_runtime import EntityBudgetSnapshot
from .coordinator_runtime import summarize_entity_budgets
from .coordinator_support import CoordinatorMetrics
from .coordinator_tasks import default_rejection_metrics
from .coordinator_tasks import derive_rejection_metrics
from .telemetry import summarise_bool_coercion_metrics
from .types import AdaptivePollingDiagnostics
from .types import BoolCoercionSummary
from .types import CoordinatorPerformanceSnapshot
from .types import CoordinatorPerformanceSnapshotCounts
from .types import CoordinatorPerformanceSnapshotMetrics
from .types import CoordinatorRejectionMetrics
from .types import CoordinatorResilienceSummary
from .types import CoordinatorSecurityAdaptiveCheck
from .types import CoordinatorSecurityChecks
from .types import CoordinatorSecurityEntityCheck
from .types import CoordinatorSecurityScorecard
from .types import CoordinatorSecurityWebhookCheck
from .types import EntityBudgetSummary
from .types import JSONMapping
from .types import WebhookSecurityStatus

type ResilienceListField = Literal[
    'open_breakers',
    'open_breaker_ids',
    'half_open_breakers',
    'half_open_breaker_ids',
    'unknown_breakers',
    'unknown_breaker_ids',
    'rejection_breakers',
    'rejection_breaker_ids',
]

_RESILIENCE_LIST_FIELDS: Final[tuple[ResilienceListField, ...]] = (
    'open_breakers',
    'open_breaker_ids',
    'half_open_breakers',
    'half_open_breaker_ids',
    'unknown_breakers',
    'unknown_breaker_ids',
    'rejection_breakers',
    'rejection_breaker_ids',
)

_LOGGER = getLogger(__name__)


class EntityBudgetTracker:
    """Track entity budget snapshots per dog."""

    __slots__ = ('_snapshots',)

    def __init__(self) -> None:
        """Initialise the budget tracker with an empty snapshot cache."""
        self._snapshots: dict[str, EntityBudgetSnapshot] = {}

    def record(self, snapshot: EntityBudgetSnapshot) -> None:
        """Store the latest snapshot for a dog."""

        self._snapshots[snapshot.dog_id] = snapshot

    def saturation(self) -> float:
        """Return aggregate utilisation across all tracked dogs."""

        if not self._snapshots:
            return 0.0

        total_capacity = sum(
            snapshot.capacity for snapshot in self._snapshots.values()
        )
        if total_capacity <= 0:
            return 0.0

        total_allocated = sum(
            snapshot.total_allocated for snapshot in self._snapshots.values()
        )
        return max(0.0, min(1.0, total_allocated / total_capacity))

    def summary(self) -> EntityBudgetSummary:
        """Return a diagnostics friendly summary."""

        return summarize_entity_budgets(self._snapshots.values())

    def snapshots(self) -> Iterable[EntityBudgetSnapshot]:
        """Expose raw snapshots (used in diagnostics)."""

        return tuple(self._snapshots.values())


def build_performance_snapshot(
    *,
    metrics: CoordinatorMetrics,
    adaptive: AdaptivePollingDiagnostics,
    entity_budget: EntityBudgetSummary,
    update_interval: float,
    last_update_time: datetime | None,
    last_update_success: bool,
    webhook_status: WebhookSecurityStatus,
    resilience: CoordinatorResilienceSummary | None = None,
) -> CoordinatorPerformanceSnapshot:
    """Generate the coordinator performance snapshot payload."""

    last_update = last_update_time.isoformat() if last_update_time else None

    update_counts: CoordinatorPerformanceSnapshotCounts = {
        'total': metrics.update_count,
        'successful': metrics.successful_cycles,
        'failed': metrics.failed_cycles,
    }
    performance_metrics: CoordinatorPerformanceSnapshotMetrics = {
        'last_update': last_update,
        'last_update_success': last_update_success,
        'success_rate': round(metrics.success_rate_percent, 2),
        'consecutive_errors': metrics.consecutive_errors,
        'update_interval_s': round(update_interval, 3),
        'current_cycle_ms': adaptive.get('current_interval_ms'),
        'rejected_call_count': 0,
        'rejection_breaker_count': 0,
        'rejection_rate': None,
        'last_rejection_time': None,
        'last_rejection_breaker_id': None,
        'last_rejection_breaker_name': None,
        'open_breaker_count': 0,
        'half_open_breaker_count': 0,
        'unknown_breaker_count': 0,
        'open_breakers': [],
        'open_breaker_ids': [],
        'half_open_breakers': [],
        'half_open_breaker_ids': [],
        'unknown_breakers': [],
        'unknown_breaker_ids': [],
        'rejection_breaker_ids': [],
        'rejection_breakers': [],
    }
    adaptive_snapshot = cast(AdaptivePollingDiagnostics, dict(adaptive))
    entity_budget_snapshot = cast(EntityBudgetSummary, dict(entity_budget))
    webhook_snapshot = cast(WebhookSecurityStatus, dict(webhook_status))

    snapshot: CoordinatorPerformanceSnapshot = {
        'update_counts': update_counts,
        'performance_metrics': performance_metrics,
        'adaptive_polling': adaptive_snapshot,
        'entity_budget': entity_budget_snapshot,
        'webhook_security': webhook_snapshot,
    }

    rejection_metrics: CoordinatorRejectionMetrics = default_rejection_metrics()

    if resilience:
        resilience_payload = _normalise_resilience_summary(resilience)
        rejection_metrics.update(derive_rejection_metrics(resilience_payload))
        snapshot['resilience_summary'] = resilience_payload

    snapshot['rejection_metrics'] = rejection_metrics
    _apply_rejection_metrics_to_performance(
        performance_metrics, rejection_metrics,
    )

    telemetry_module = sys.modules.get(
        'custom_components.pawcontrol.telemetry',
    )
    bool_summary: BoolCoercionSummary = summarise_bool_coercion_metrics()
    if telemetry_module is not None and hasattr(
        telemetry_module, 'summarise_bool_coercion_metrics',
    ):
        summary_func = cast(
            Callable[[], BoolCoercionSummary],
            telemetry_module.summarise_bool_coercion_metrics,
        )
        module_summary = summary_func()
        if (
            module_summary.get('total') or module_summary.get('reset_count')
        ) and module_summary.get('total', 0) >= bool_summary.get('total', 0):
            bool_summary = module_summary
    snapshot['bool_coercion'] = bool_summary

    return snapshot


def _coerce_float(value: Any, default: float) -> float:
    """Return a finite float or the provided default."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if not isfinite(number):
        return default

    return number


def _normalise_resilience_summary(
    summary: CoordinatorResilienceSummary | Mapping[str, object],
) -> CoordinatorResilienceSummary:
    """Return a resilience summary with stable string list payloads."""

    payload = cast(CoordinatorResilienceSummary, dict(summary))

    for field in _RESILIENCE_LIST_FIELDS:
        payload[field] = _coerce_string_list(payload.get(field))

    return payload


def _coerce_string_list(value: object) -> list[str]:
    """Return a list of strings for resilience diagnostics fields."""

    if value is None:
        return []

    if isinstance(value, (str, bytes, bytearray)):
        return [_stringify_resilience_value(value)]

    if isinstance(value, Iterable):
        items: list[str] = []
        for item in value:
            if item is None:
                continue
            items.append(_stringify_resilience_value(item))
        return items

    return [_stringify_resilience_value(value)]


def _stringify_resilience_value(value: object) -> str:
    """Convert resilience identifiers to safe diagnostic strings."""

    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode()
        except Exception:  # pragma: no cover - defensive fallback
            return value.decode(errors='ignore')
    return str(value)


def _apply_rejection_metrics_to_performance(
    performance_metrics: CoordinatorPerformanceSnapshotMetrics,
    rejection_metrics: CoordinatorRejectionMetrics,
) -> None:
    """Merge rejection diagnostics into the performance snapshot payload."""

    performance_metrics.update(
        {
            'rejected_call_count': rejection_metrics['rejected_call_count'],
            'rejection_breaker_count': rejection_metrics['rejection_breaker_count'],
            'rejection_rate': rejection_metrics['rejection_rate'],
            'last_rejection_time': rejection_metrics['last_rejection_time'],
            'last_rejection_breaker_id': rejection_metrics['last_rejection_breaker_id'],
            'last_rejection_breaker_name': rejection_metrics[
                'last_rejection_breaker_name'
            ],
            'open_breaker_count': rejection_metrics['open_breaker_count'],
            'half_open_breaker_count': rejection_metrics['half_open_breaker_count'],
            'unknown_breaker_count': rejection_metrics['unknown_breaker_count'],
            'open_breakers': list(rejection_metrics['open_breakers']),
            'open_breaker_ids': list(rejection_metrics['open_breaker_ids']),
            'half_open_breakers': list(rejection_metrics['half_open_breakers']),
            'half_open_breaker_ids': list(rejection_metrics['half_open_breaker_ids']),
            'unknown_breakers': list(rejection_metrics['unknown_breakers']),
            'unknown_breaker_ids': list(rejection_metrics['unknown_breaker_ids']),
            'rejection_breaker_ids': list(rejection_metrics['rejection_breaker_ids']),
            'rejection_breakers': list(rejection_metrics['rejection_breakers']),
        },
    )


def build_security_scorecard(
    *,
    adaptive: JSONMapping,
    entity_summary: JSONMapping,
    webhook_status: WebhookSecurityStatus,
) -> CoordinatorSecurityScorecard:
    """Return a pass/fail scorecard for coordinator safety checks."""

    target_ms = _coerce_float(adaptive.get('target_cycle_ms'), 200.0)
    if target_ms <= 0:
        target_ms = 200.0

    current_ms = _coerce_float(adaptive.get('current_interval_ms'), target_ms)
    if current_ms < 0:
        current_ms = target_ms

    threshold_ms = 200.0
    adaptive_pass = current_ms <= threshold_ms
    adaptive_check: CoordinatorSecurityAdaptiveCheck = {
        'pass': adaptive_pass,
        'current_ms': current_ms,
        'target_ms': target_ms,
        'threshold_ms': threshold_ms,
    }
    if not adaptive_pass:
        adaptive_check['reason'] = 'Update interval exceeds 200ms target'

    peak_utilisation = _coerce_float(
        entity_summary.get('peak_utilization'), 0.0,
    )
    peak_utilisation = max(0.0, min(100.0, peak_utilisation))
    entity_threshold = 95.0
    entity_pass = peak_utilisation <= entity_threshold
    entity_summary_snapshot = cast(EntityBudgetSummary, dict(entity_summary))
    entity_check: CoordinatorSecurityEntityCheck = {
        'pass': entity_pass,
        'summary': entity_summary_snapshot,
        'threshold_percent': entity_threshold,
    }
    if not entity_pass:
        entity_check['reason'] = 'Entity budget utilisation above safe threshold'

    webhook_pass = (not webhook_status.get('configured')) or bool(
        webhook_status.get('secure'),
    )
    webhook_payload = dict(webhook_status)
    webhook_payload.setdefault('configured', False)
    webhook_payload.setdefault('secure', False)
    webhook_payload.setdefault('hmac_ready', False)
    webhook_payload.setdefault('insecure_configs', ())
    webhook_snapshot = cast(WebhookSecurityStatus, webhook_payload)
    webhook_check: CoordinatorSecurityWebhookCheck = {
        'pass': webhook_pass,
        'configured': webhook_snapshot['configured'],
        'secure': webhook_snapshot['secure'],
        'hmac_ready': webhook_snapshot['hmac_ready'],
        'insecure_configs': webhook_snapshot['insecure_configs'],
    }
    if 'error' in webhook_snapshot:
        webhook_check['error'] = webhook_snapshot['error']
    if not webhook_pass:
        webhook_check.setdefault(
            'reason', 'Webhook configurations missing HMAC protection',
        )

    checks: CoordinatorSecurityChecks = {
        'adaptive_polling': adaptive_check,
        'entity_budget': entity_check,
        'webhooks': webhook_check,
    }
    all_checks = (
        checks['adaptive_polling'],
        checks['entity_budget'],
        checks['webhooks'],
    )
    status_literal: Literal['pass', 'fail'] = (
        'pass' if all(check['pass'] for check in all_checks) else 'fail'
    )
    scorecard: CoordinatorSecurityScorecard = {
        'status': status_literal,
        'checks': checks,
    }
    return scorecard


def normalise_webhook_status(manager: Any) -> WebhookSecurityStatus:
    """Normalise webhook security payloads coming from notification manager."""

    if manager is None or not hasattr(manager, 'webhook_security_status'):
        return {
            'configured': False,
            'secure': True,
            'hmac_ready': False,
            'insecure_configs': (),
        }

    try:
        status = dict(manager.webhook_security_status())
    except Exception as err:  # pragma: no cover - defensive logging
        _LOGGER.debug('Webhook security inspection failed: %s', err)
        return {
            'configured': True,
            'secure': False,
            'hmac_ready': False,
            'insecure_configs': (),
            'error': str(err),
        }

    status.setdefault('configured', False)
    status.setdefault('secure', False)
    status.setdefault('hmac_ready', False)
    insecure = status.get('insecure_configs', ())
    if isinstance(insecure, Iterable) and not isinstance(
        insecure, str | bytes | bytearray,
    ):
        status['insecure_configs'] = tuple(insecure)
    else:
        status['insecure_configs'] = (insecure,) if insecure else ()
    return cast(WebhookSecurityStatus, status)
