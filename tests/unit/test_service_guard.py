"""Unit tests for service guard telemetry models."""

from collections.abc import Iterator, MutableMapping

import pytest

from custom_components.pawcontrol.service_guard import (
    ServiceGuardResult,
    ServiceGuardSnapshot,
    _coerce_int,
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


def test_service_guard_result_to_mapping_omits_optional_fields() -> None:
    """Optional metadata should be omitted when not provided."""
    result = ServiceGuardResult(
        domain="notify",
        service="mobile_app",
        executed=True,
    )

    assert result.to_mapping() == {
        "domain": "notify",
        "service": "mobile_app",
        "executed": True,
    }


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
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("notify", "mobile_app", True),
        ServiceGuardResult("script", "turn_on", False),
        ServiceGuardResult("script", "turn_on", False, reason="cooldown"),
    ])

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


def test_service_guard_snapshot_to_metrics_exports_expected_payload() -> None:
    """to_metrics should mirror snapshot counters and serialised history."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("notify", "mobile_app", True),
        ServiceGuardResult("script", "turn_on", False, reason="cooldown"),
    ])

    assert snapshot.to_metrics() == {
        "executed": 1,
        "skipped": 1,
        "reasons": {"cooldown": 1},
        "last_results": snapshot.history(),
    }


def test_service_guard_snapshot_accumulate_replaces_invalid_reasons_payload() -> None:
    """Accumulate should reset reasons when the incoming value is not a mapping."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("script", "turn_on", False, reason="cooldown"),
        ServiceGuardResult("script", "turn_on", False),
    ])
    metrics: JSONMutableMapping = {
        "executed": "invalid",
        "skipped": None,
        "reasons": "invalid",
        "last_results": [],
    }

    payload = snapshot.accumulate(metrics)

    assert payload == {
        "executed": 0,
        "skipped": 2,
        "reasons": {"cooldown": 1, "unknown": 1},
        "last_results": snapshot.history(),
    }
    assert metrics["reasons"] == {"cooldown": 1, "unknown": 1}


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


def test_normalise_guard_result_payload_filters_invalid_text_values() -> None:
    """Normalisation should keep only non-empty string metadata values."""
    payload = normalise_guard_result_payload({
        "executed": 1,
        "domain": "",
        "service": 10,
        "reason": None,
        "description": "scheduled block",
    })

    assert payload == {
        "executed": True,
        "description": "scheduled block",
    }


def test_normalise_guard_history_keeps_mapping_entries_only() -> None:
    """History normalisation should include only valid mapping payloads."""
    history = normalise_guard_history((
        {"executed": True, "domain": "notify"},
        {"service": "switch.turn_on", "reason": "cooldown"},
        12,
    ))

    assert history == [
        {"executed": True, "domain": "notify"},
        {"executed": False, "service": "switch.turn_on", "reason": "cooldown"},
    ]


@pytest.mark.parametrize("payload", ["history", b"history", bytearray(b"history"), 42])
def test_normalise_guard_history_rejects_non_sequence_payloads(payload: object) -> None:
    """History normalisation should reject unsupported payload types."""
    assert normalise_guard_history(payload) == []


def test_service_guard_snapshot_accumulate_handles_write_ignored_mapping() -> None:
    """Accumulate should still return sane payloads when mapping writes are ignored."""

    class IgnoreWritesMapping(MutableMapping[str, object]):
        """Mutable mapping that allows reads but discards writes for selected keys."""

        def __init__(self) -> None:
            self._storage: dict[str, object] = {
                "executed": 1,
                "skipped": 1,
                "reasons": "blocked",
                "last_results": "blocked",
            }

        def __getitem__(self, key: str) -> object:
            return self._storage[key]

        def __setitem__(self, key: str, value: object) -> None:
            if key in {"reasons", "last_results"}:
                return
            self._storage[key] = value

        def __delitem__(self, key: str) -> None:
            del self._storage[key]

        def __iter__(self) -> Iterator[str]:
            return iter(self._storage)

        def __len__(self) -> int:
            return len(self._storage)

    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("script", "turn_on", False, reason="cooldown"),
    ])
    payload = snapshot.accumulate(IgnoreWritesMapping())

    assert payload == {
        "executed": 1,
        "skipped": 2,
        "reasons": {},
        "last_results": snapshot.history(),
    }


def test_service_guard_snapshot_accumulate_coerces_existing_reason_counts() -> None:
    """Reason counters should be coerced from numeric values before incrementing."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("script", "turn_on", False, reason="cooldown"),
    ])

    metrics: JSONMutableMapping = {
        "executed": 0,
        "skipped": 0,
        "reasons": {"cooldown": True},
        "last_results": [],
    }

    payload = snapshot.accumulate(metrics)

    assert payload["reasons"] == {"cooldown": 2}
    assert metrics["reasons"] == {"cooldown": 2}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, 1),
        (7, 7),
        (3.9, 3),
        ("9", 9),
        ("bad", 0),
        (None, 0),
    ],
)
def test_coerce_int_handles_supported_and_invalid_input(
    value: object, expected: int
) -> None:
    """Integer coercion should safely handle bools, numerics, and invalid input."""
    assert _coerce_int(value) == expected


def test_service_guard_snapshot_from_sequence_tracks_unknown_reason() -> None:
    """Missing reasons should aggregate under the unknown counter."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("script", "turn_on", False),
        ServiceGuardResult("script", "turn_on", False, reason="cooldown"),
    ])

    assert snapshot.executed == 0
    assert snapshot.skipped == 2
    assert snapshot.reasons == {"unknown": 1, "cooldown": 1}
