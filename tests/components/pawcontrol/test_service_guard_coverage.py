"""Additional branch coverage for service guard telemetry helpers."""

from collections.abc import MutableMapping
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import helpers
from custom_components.pawcontrol.service_guard import (
    ServiceGuardResult,
    ServiceGuardSnapshot,
    _coerce_int,
    normalise_guard_history,
    normalise_guard_result_payload,
)
from custom_components.pawcontrol.types import JSONMutableMapping


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, 1),
        (False, 0),
        (3.7, 3),
        ("17", 17),
        ("not-int", 0),
        (object(), 0),
    ],
)
def test_coerce_int_handles_supported_input_and_fallbacks(
    value: object, expected: int
) -> None:
    """The coercion helper should normalise numbers and reject unknown values."""
    assert _coerce_int(value) == expected


def test_service_guard_result_bool_and_mapping_behaviour() -> None:
    """Guard result payloads should preserve optional reason/description fields."""
    executed = ServiceGuardResult("notify", "mobile_app", executed=True)
    skipped = ServiceGuardResult(
        "switch",
        "turn_on",
        executed=False,
        reason="quiet_hours",
        description="muted",
    )

    assert bool(executed) is True
    assert bool(skipped) is False
    assert executed.to_mapping() == {
        "domain": "notify",
        "service": "mobile_app",
        "executed": True,
    }
    assert skipped.to_mapping() == {
        "domain": "switch",
        "service": "turn_on",
        "executed": False,
        "reason": "quiet_hours",
        "description": "muted",
    }


def test_snapshot_summary_metrics_and_zero_payload() -> None:
    """Snapshot helpers should build stable summary and metrics payloads."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("notify", "mobile_app", executed=True),
        ServiceGuardResult("switch", "turn_on", executed=False, reason="quiet"),
        ServiceGuardResult("script", "turn_on", executed=False),
    ])

    assert snapshot.executed == 1
    assert snapshot.skipped == 2
    assert snapshot.reasons == {"quiet": 1, "unknown": 1}
    assert snapshot.history() == [
        {"domain": "notify", "service": "mobile_app", "executed": True},
        {
            "domain": "switch",
            "service": "turn_on",
            "executed": False,
            "reason": "quiet",
        },
        {"domain": "script", "service": "turn_on", "executed": False},
    ]
    assert snapshot.to_summary() == {
        "executed": 1,
        "skipped": 2,
        "reasons": {"quiet": 1, "unknown": 1},
        "results": snapshot.history(),
    }
    assert snapshot.to_metrics() == {
        "executed": 1,
        "skipped": 2,
        "reasons": {"quiet": 1, "unknown": 1},
        "last_results": snapshot.history(),
    }
    assert ServiceGuardSnapshot.zero_metrics() == {
        "executed": 0,
        "skipped": 0,
        "reasons": {},
        "last_results": [],
    }


def test_snapshot_accumulate_merges_reason_counts_and_replaces_history() -> None:
    """Accumulation should merge counters and overwrite last results with history."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("notify", "mobile_app", executed=True),
        ServiceGuardResult("switch", "turn_on", executed=False, reason="quiet"),
        ServiceGuardResult("script", "turn_on", executed=False),
    ])

    metrics: JSONMutableMapping = {
        "executed": "4",
        "skipped": 1,
        "reasons": {"quiet": 2, "other": 1.1},
        "last_results": "invalid-history",
    }

    payload = snapshot.accumulate(metrics)

    assert payload["executed"] == 5
    assert payload["skipped"] == 3
    assert payload["reasons"] == {"quiet": 3, "other": 1, "unknown": 1}
    assert payload["last_results"] == snapshot.history()


def test_snapshot_accumulate_handles_non_mapping_reasons() -> None:
    """Invalid reason payloads should be replaced with a mutable mapping."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("light", "turn_off", executed=False, reason="cooldown")
    ])

    metrics: MutableMapping[str, object] = {
        "executed": 0,
        "skipped": 0,
        "reasons": "blocked",
    }

    payload = snapshot.accumulate(metrics)

    assert payload == {
        "executed": 0,
        "skipped": 1,
        "reasons": {"cooldown": 1},
        "last_results": snapshot.history(),
    }
    assert metrics["reasons"] == {"cooldown": 1}


def test_normalise_guard_helpers_filter_invalid_values() -> None:
    """Normalisation should keep only non-empty textual metadata fields."""
    result_payload = normalise_guard_result_payload({
        "executed": 1,
        "domain": "",
        "service": "notify",
        "reason": None,
        "description": "muted",
    })
    assert result_payload == {
        "executed": True,
        "service": "notify",
        "description": "muted",
    }

    history_payload = normalise_guard_history([
        {"executed": 0, "service": "switch"},
        ServiceGuardResult("notify", "mobile_app", executed=True),
        "skip-me",
    ])
    assert history_payload == [
        {"executed": False, "service": "switch"},
        {"domain": "notify", "service": "mobile_app", "executed": True},
    ]


def test_normalise_guard_history_rejects_non_sequence_payloads() -> None:
    """Non-sequences and raw bytes/strings should return empty history."""
    assert normalise_guard_history("not-a-history") == []
    assert normalise_guard_history(b"not-a-history") == []
    assert normalise_guard_history(bytearray(b"not-a-history")) == []
    assert normalise_guard_history(123) == []


def test_normalise_guard_result_payload_marks_skipped_without_metadata() -> None:
    """Guard payloads should keep executed=False even when metadata is unusable."""
    payload = normalise_guard_result_payload({
        "executed": 0,
        "domain": "",
        "service": "",
        "reason": "",
        "description": None,
    })

    assert payload == {"executed": False}


def test_helpers_data_structure_and_quiet_hour_fallback_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Helpers should emit robust defaults for malformed storage and time payloads."""
    data_helper = helpers.PawControlData(
        hass=SimpleNamespace(async_create_task=lambda coro: SimpleNamespace(coro=coro)),
        config_entry=SimpleNamespace(entry_id="entry-1", data={}, options={}),
    )

    sanitized = data_helper._ensure_data_structure("broken-payload")
    assert sanitized == {
        "walks": {},
        "feedings": {},
        "health": {},
        "routes": {},
        "statistics": {},
    }

    class _BrokenStr:
        def __str__(self) -> str:
            raise RuntimeError("no str")

    monkeypatch.setattr(helpers, "_deserialize_datetime", lambda _candidate: None)
    monkeypatch.setattr(
        helpers.dt_util,
        "parse_time",
        lambda value: None if value == "22:00:00" else helpers.time(7, 0, 0),
        raising=False,
    )
    assert (
        helpers.PawControlNotificationManager._coerce_quiet_hours_time(
            _BrokenStr(),
            "22:00:00",
        )
        is None
    )
    assert (
        helpers.PawControlNotificationManager._coerce_quiet_hours_time(
            None,
            "07:00:00",
        )
        is not None
    )
