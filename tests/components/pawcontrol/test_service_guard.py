"""Tests for service guard telemetry helpers."""

from custom_components.pawcontrol.service_guard import (
    ServiceGuardResult,
    ServiceGuardSnapshot,
    normalise_guard_history,
    normalise_guard_result_payload,
)


def test_service_guard_result_to_mapping_omits_empty_optional_fields() -> None:
    """Optional payload keys should only be emitted when populated."""
    executed = ServiceGuardResult(
        domain="notify",
        service="mobile_app",
        executed=True,
    )
    skipped = ServiceGuardResult(
        domain="light",
        service="turn_on",
        executed=False,
        reason="quiet_hours",
        description="Guard blocked call",
    )

    assert executed.to_mapping() == {
        "domain": "notify",
        "service": "mobile_app",
        "executed": True,
    }
    assert skipped.to_mapping() == {
        "domain": "light",
        "service": "turn_on",
        "executed": False,
        "reason": "quiet_hours",
        "description": "Guard blocked call",
    }


def test_service_guard_snapshot_accumulate_normalizes_existing_metrics() -> None:
    """Accumulate should coerce numeric payloads and merge reasons."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("notify", "mobile_app", True),
        ServiceGuardResult("light", "turn_on", False, reason="quiet_hours"),
        ServiceGuardResult("switch", "toggle", False),
    ])

    metrics: dict[str, object] = {
        "executed": "4",
        "skipped": True,
        "reasons": {"quiet_hours": 2.0, "invalid": "nope"},
        "last_results": "not-a-list",
    }

    accumulated = snapshot.accumulate(metrics)

    assert accumulated["executed"] == 5
    assert accumulated["skipped"] == 3
    assert accumulated["reasons"] == {
        "quiet_hours": 3,
        "invalid": 0,
        "unknown": 1,
    }
    assert len(accumulated["last_results"]) == 3


def test_service_guard_snapshot_zero_metrics_and_summary_payload() -> None:
    """Summary and metrics helpers should export consistent structures."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("notify", "mobile_app", True)
    ])

    assert ServiceGuardSnapshot.zero_metrics() == {
        "executed": 0,
        "skipped": 0,
        "reasons": {},
        "last_results": [],
    }
    assert snapshot.to_summary() == {
        "executed": 1,
        "skipped": 0,
        "reasons": {},
        "results": [
            {
                "domain": "notify",
                "service": "mobile_app",
                "executed": True,
            }
        ],
    }
    assert snapshot.to_metrics() == {
        "executed": 1,
        "skipped": 0,
        "reasons": {},
        "last_results": [
            {
                "domain": "notify",
                "service": "mobile_app",
                "executed": True,
            }
        ],
    }


def test_normalise_helpers_filter_invalid_values() -> None:
    """Normalization should drop empty fields and reject invalid history payloads."""
    payload = {
        "executed": 0,
        "domain": "",
        "service": "turn_off",
        "reason": None,
        "description": "blocked",
    }

    assert normalise_guard_result_payload(payload) == {
        "executed": False,
        "service": "turn_off",
        "description": "blocked",
    }

    history = normalise_guard_history([
        ServiceGuardResult("notify", "mobile_app", True),
        payload,
        "invalid",
    ])
    assert history == [
        {
            "domain": "notify",
            "service": "mobile_app",
            "executed": True,
        },
        {
            "executed": False,
            "service": "turn_off",
            "description": "blocked",
        },
    ]

    assert normalise_guard_history("not-a-sequence") == []


def test_service_guard_snapshot_accumulate_handles_invalid_reason_payloads() -> None:
    """Accumulate should initialise missing reason payloads and normalize output."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("notify", "mobile_app", False, reason="quiet_hours"),
        ServiceGuardResult("switch", "toggle", False),
    ])

    metrics: dict[str, object] = {
        "executed": 0,
        "skipped": 0,
        "reasons": "bad-payload",
        "last_results": (),
    }

    accumulated = snapshot.accumulate(metrics)

    assert accumulated == {
        "executed": 0,
        "skipped": 2,
        "reasons": {"quiet_hours": 1, "unknown": 1},
        "last_results": [
            {
                "domain": "notify",
                "service": "mobile_app",
                "executed": False,
                "reason": "quiet_hours",
            },
            {
                "domain": "switch",
                "service": "toggle",
                "executed": False,
            },
        ],
    }


def test_normalise_guard_result_payload_keeps_truthy_string_fields() -> None:
    """Payload normalization should preserve non-empty string attributes."""
    payload = {
        "executed": 1,
        "domain": "notify",
        "service": "mobile_app",
        "reason": "rate_limited",
        "description": "retry later",
    }

    assert normalise_guard_result_payload(payload) == {
        "executed": True,
        "domain": "notify",
        "service": "mobile_app",
        "reason": "rate_limited",
        "description": "retry later",
    }


def test_normalise_guard_history_and_bool_cover_edge_paths() -> None:
    """History normalization should reject bytes and mirror result truthiness."""
    executed = ServiceGuardResult("notify", "mobile_app", True)
    skipped = ServiceGuardResult("light", "turn_off", False)

    assert bool(executed) is True
    assert bool(skipped) is False
    assert normalise_guard_history(b"invalid-bytes") == []


def test_service_guard_snapshot_accumulate_coerces_invalid_numeric_strings() -> None:
    """Accumulate should treat non-numeric strings as zero counts."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("light", "turn_on", False, reason="quiet_hours"),
    ])

    metrics: dict[str, object] = {
        "executed": "bad-value",
        "skipped": "also-bad",
        "reasons": {"quiet_hours": "not-a-number"},
    }

    accumulated = snapshot.accumulate(metrics)

    assert accumulated["executed"] == 0
    assert accumulated["skipped"] == 1
    assert accumulated["reasons"] == {"quiet_hours": 1}


def test_normalise_guard_history_rejects_bytearray_payload() -> None:
    """History normalization should reject bytearray payloads like bytes."""
    assert normalise_guard_history(bytearray(b"invalid-bytearray")) == []


def test_service_guard_snapshot_accumulate_handles_non_mapping_reason_snapshot() -> (
    None
):
    """Accumulate should return empty reasons when writes are rejected."""

    class _ReasonWriteRejectingMetrics(dict[str, object]):
        def __setitem__(self, key: str, value: object) -> None:
            if key == "reasons":
                super().__setitem__(key, "rejected")
                return
            super().__setitem__(key, value)

    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("light", "turn_on", False, reason="quiet_hours")
    ])
    metrics = _ReasonWriteRejectingMetrics({
        "executed": 0,
        "skipped": 0,
        "reasons": "invalid",
    })

    accumulated = snapshot.accumulate(metrics)

    assert accumulated["executed"] == 0
    assert accumulated["skipped"] == 1
    assert accumulated["reasons"] == {}


def test_service_guard_snapshot_accumulate_coerces_non_numeric_objects_to_zero() -> (
    None
):
    """Accumulate should treat unsupported numeric payload types as zero."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("notify", "mobile_app", True),
    ])
    metrics: dict[str, object] = {
        "executed": object(),
        "skipped": object(),
        "reasons": {},
    }

    accumulated = snapshot.accumulate(metrics)

    assert accumulated["executed"] == 1
    assert accumulated["skipped"] == 0
