"""Unit tests for service guard telemetry models."""

import pytest

from custom_components.pawcontrol.service_guard import (
    ServiceGuardResult,
    ServiceGuardSnapshot,
    normalise_guard_history,
    normalise_guard_result_payload,
)
from custom_components.pawcontrol.types import JSONMutableMapping


def test_service_guard_result_to_mapping() -> None:
    """Service guard results should emit structured payloads."""
    result = ServiceGuardResult(
        domain="notify",
        service="mobile_app",
        executed=False,
        reason="timeout",
        description="notification blocked by guard",
    )

    payload = result.to_mapping()

    assert payload["domain"] == "notify"
    assert payload["service"] == "mobile_app"
    assert payload["reason"] == "timeout"
    assert payload["description"] == "notification blocked by guard"
    assert payload["executed"] is False


def test_service_guard_result_bool_protocol() -> None:
    """Guard result instances should mirror the executed boolean state."""
    assert bool(ServiceGuardResult("notify", "mobile_app", True)) is True
    assert bool(ServiceGuardResult("notify", "mobile_app", False)) is False


def test_service_guard_snapshot_summary_and_metrics() -> None:
    """Snapshots should summarise guard telemetry consistently."""
    results = (
        ServiceGuardResult("notify", "mobile_app", True),
        ServiceGuardResult("light", "turn_on", False, reason="cooldown"),
        ServiceGuardResult("automation", "trigger", False, reason="cooldown"),
        ServiceGuardResult("script", "turn_on", False, reason="safety"),
    )

    snapshot = ServiceGuardSnapshot.from_sequence(results)

    summary = snapshot.to_summary()
    assert summary["executed"] == 1
    assert summary["skipped"] == 3
    assert summary["reasons"] == {"cooldown": 2, "safety": 1}
    assert [entry["service"] for entry in summary["results"]] == [
        "mobile_app",
        "turn_on",
        "trigger",
        "turn_on",
    ]

    metrics: JSONMutableMapping = {
        "executed": 2,
        "skipped": 1,
        "reasons": {"cooldown": 1},
    }
    payload = snapshot.accumulate(metrics)

    assert metrics["executed"] == 3
    assert metrics["skipped"] == 4
    assert metrics["reasons"] == {"cooldown": 3, "safety": 1}
    assert payload["last_results"][0]["domain"] == "notify"
    assert payload["last_results"][-1]["service"] == "turn_on"


def test_service_guard_snapshot_accumulate_handles_invalid_metric_types() -> None:
    """Accumulate should coerce mixed metric payload values safely."""
    snapshot = ServiceGuardSnapshot.from_sequence(
        [
            ServiceGuardResult("notify", "mobile_app", True),
            ServiceGuardResult("script", "turn_on", False),
            ServiceGuardResult("script", "turn_on", False, reason="cooldown"),
        ]
    )

    metrics: JSONMutableMapping = {
        "executed": "2",
        "skipped": True,
        "reasons": {"cooldown": "bad", "other": 1.5},
        "last_results": "not-a-list",
    }

    payload = snapshot.accumulate(metrics)

    assert payload == {
        "executed": 3,
        "skipped": 3,
        "reasons": {"cooldown": 1, "other": 1, "unknown": 1},
        "last_results": snapshot.history(),
    }


def test_service_guard_snapshot_zero_metrics_shape() -> None:
    """Zero metrics should include all expected diagnostic keys."""
    assert ServiceGuardSnapshot.zero_metrics() == {
        "executed": 0,
        "skipped": 0,
        "reasons": {},
        "last_results": [],
    }


@pytest.mark.parametrize(
    "raw_payload, expected",
    [
        ({"service": "light.turn_on", "reason": "guard"}, False),
        ({"executed": True, "domain": "notify"}, True),
        ({"executed": 0, "description": "skipped"}, False),
    ],
)
def test_normalise_guard_result_payload(
    raw_payload: JSONMutableMapping, expected: bool
) -> None:
    """Guard result payload normalisation should coerce booleans and text."""
    payload = normalise_guard_result_payload(raw_payload)
    assert payload["executed"] is expected
    assert all(isinstance(value, str | bool) for value in payload.values())


def test_normalise_guard_history_handles_mixed_entries() -> None:
    """Guard history normalisation must handle results and mappings."""
    history = normalise_guard_history([
        ServiceGuardResult("notify", "persistent_notification", True),
        {"domain": "script", "service": "turn_on", "reason": "cooldown"},
        object(),
    ])

    assert len(history) == 2
    assert history[0]["executed"] is True
    assert history[1]["domain"] == "script"
    assert history[1]["executed"] is False


@pytest.mark.parametrize("payload", ["history", b"history", bytearray(b"history"), 42])
def test_normalise_guard_history_rejects_non_sequence_payloads(payload: object) -> None:
    """History normalisation should reject unsupported payload types."""
    assert normalise_guard_history(payload) == []
