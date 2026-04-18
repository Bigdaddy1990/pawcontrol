"""Coverage tests for service_guard telemetry helpers."""

import pytest

from custom_components.pawcontrol.service_guard import (
    ServiceGuardResult,
    ServiceGuardSnapshot,
    _coerce_int,
    normalise_guard_history,
    normalise_guard_result_payload,
)


@pytest.mark.unit
def test_service_guard_result_to_mapping_and_bool() -> None:  # noqa: D103
    result = ServiceGuardResult(
        domain="pawcontrol",
        service="walk_start",
        executed=False,
        reason="rate_limited",
        description="Too many calls",
    )

    assert bool(result) is False
    assert result.to_mapping() == {
        "domain": "pawcontrol",
        "service": "walk_start",
        "executed": False,
        "reason": "rate_limited",
        "description": "Too many calls",
    }


@pytest.mark.unit
def test_service_guard_snapshot_aggregation_helpers() -> None:  # noqa: D103
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult(
            domain="pawcontrol",
            service="walk_start",
            executed=True,
        ),
        ServiceGuardResult(
            domain="pawcontrol",
            service="walk_start",
            executed=False,
            reason="rate_limited",
        ),
        ServiceGuardResult(
            domain="pawcontrol",
            service="walk_start",
            executed=False,
        ),
    ])

    assert snapshot.executed == 1
    assert snapshot.skipped == 2
    assert snapshot.reasons == {"rate_limited": 1, "unknown": 1}
    assert snapshot.to_summary()["executed"] == 1
    assert snapshot.to_metrics()["last_results"][1]["reason"] == "rate_limited"


@pytest.mark.unit
def test_service_guard_snapshot_accumulate_coerces_and_merges() -> None:  # noqa: D103
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult(domain="pawcontrol", service="walk", executed=False),
        ServiceGuardResult(
            domain="pawcontrol",
            service="walk",
            executed=False,
            reason="blocked",
        ),
    ])

    metrics: dict[str, object] = {
        "executed": "2",
        "skipped": True,
        "reasons": {"blocked": 4, "bad_value": "oops"},
        "last_results": "invalid",
    }

    merged = snapshot.accumulate(metrics)

    assert merged["executed"] == 2
    assert merged["skipped"] == 3
    assert merged["reasons"] == {"blocked": 5, "bad_value": 0, "unknown": 1}
    assert isinstance(merged["last_results"], list)


@pytest.mark.unit
def test_service_guard_snapshot_accumulate_reasons_recreated_when_invalid() -> None:  # noqa: D103
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult(domain="pawcontrol", service="walk", executed=False)
    ])

    metrics: dict[str, object] = {"reasons": "invalid"}
    merged = snapshot.accumulate(metrics)

    assert merged["executed"] == 0
    assert merged["skipped"] == 1
    assert merged["reasons"] == {"unknown": 1}


@pytest.mark.unit
def test_normalise_guard_result_payload_keeps_only_valid_fields() -> None:  # noqa: D103
    payload = {
        "executed": 1,
        "domain": "pawcontrol",
        "service": "walk",
        "reason": "rate_limited",
        "description": "Denied",
        "ignored": "value",
    }

    assert normalise_guard_result_payload(payload) == {
        "executed": True,
        "domain": "pawcontrol",
        "service": "walk",
        "reason": "rate_limited",
        "description": "Denied",
    }


@pytest.mark.unit
def test_normalise_guard_result_payload_drops_empty_strings() -> None:  # noqa: D103
    payload = {
        "executed": 0,
        "domain": "",
        "service": "",
        "reason": "",
        "description": "",
    }

    assert normalise_guard_result_payload(payload) == {"executed": False}


@pytest.mark.unit
def test_normalise_guard_history_non_sequence_returns_empty_list() -> None:  # noqa: D103
    assert normalise_guard_history(None) == []
    assert normalise_guard_history("not-a-list") == []


@pytest.mark.unit
def test_normalise_guard_history_accepts_result_objects_and_mappings() -> None:  # noqa: D103
    entries = [
        ServiceGuardResult(domain="pawcontrol", service="walk", executed=True),
        {
            "executed": False,
            "domain": "pawcontrol",
            "service": "walk",
            "reason": "blocked",
        },
        42,
    ]

    assert normalise_guard_history(entries) == [
        {"domain": "pawcontrol", "service": "walk", "executed": True},
        {
            "executed": False,
            "domain": "pawcontrol",
            "service": "walk",
            "reason": "blocked",
        },
    ]


@pytest.mark.unit
def test_service_guard_result_to_mapping_omits_optional_fields() -> None:  # noqa: D103
    result = ServiceGuardResult(
        domain="pawcontrol",
        service="walk_stop",
        executed=True,
    )

    assert result.to_mapping() == {
        "domain": "pawcontrol",
        "service": "walk_stop",
        "executed": True,
    }


@pytest.mark.unit
def test_service_guard_snapshot_zero_metrics_and_history() -> None:  # noqa: D103
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult(domain="pawcontrol", service="walk", executed=True)
    ])

    assert ServiceGuardSnapshot.zero_metrics() == {
        "executed": 0,
        "skipped": 0,
        "reasons": {},
        "last_results": [],
    }
    assert snapshot.history() == [
        {"domain": "pawcontrol", "service": "walk", "executed": True}
    ]


@pytest.mark.unit
def test_normalise_guard_history_filters_bytes_sequences() -> None:  # noqa: D103
    assert normalise_guard_history(b"binary") == []
    assert normalise_guard_history(bytearray(b"binary")) == []


@pytest.mark.unit
def test_coerce_int_invalid_string_and_object_values() -> None:  # noqa: D103
    assert _coerce_int("not-a-number") == 0
    assert _coerce_int(object()) == 0


@pytest.mark.unit
def test_service_guard_snapshot_accumulate_reasons_snapshot_non_mapping() -> None:  # noqa: D103
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult(domain="pawcontrol", service="walk", executed=False)
    ])

    class _ReasonsOpaqueMetrics(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            if key == "reasons":
                return "opaque"
            return super().get(key, default)

    metrics = _ReasonsOpaqueMetrics(
        {
            "executed": object(),
            "skipped": "not-a-number",
            "last_results": "invalid",
        },
    )
    merged = snapshot.accumulate(metrics)
    assert merged["executed"] == 0
    assert merged["skipped"] == 1
    assert merged["reasons"] == {}
