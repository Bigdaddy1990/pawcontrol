"""Validate bool coercion telemetry snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from custom_components.pawcontrol.diagnostics import (
    _get_bool_coercion_diagnostics,
)
from custom_components.pawcontrol.telemetry import (
    get_bool_coercion_metrics,
    record_bool_coercion_event,
    reset_bool_coercion_metrics,
    summarise_bool_coercion_metrics,
)
from custom_components.pawcontrol.types import _coerce_bool


def test_coerce_bool_records_none_default() -> None:
    """None inputs should count as defaulted coercions."""

    reset_bool_coercion_metrics()

    assert _coerce_bool(None, default=True) is True

    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 1
    assert metrics["defaulted"] == 1
    assert metrics["reason_counts"]["none"] == 1
    assert metrics["samples"][0]["reason"] == "none"
    assert metrics["last_result"] is True
    assert metrics["last_default"] is True

    reset_bool_coercion_metrics()


def test_coerce_bool_records_blank_string_default() -> None:
    """Blank strings should increment the blank-string reason bucket."""

    reset_bool_coercion_metrics()

    assert _coerce_bool("   ", default=False) is False

    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 1
    assert metrics["defaulted"] == 1
    assert metrics["reason_counts"]["blank_string"] == 1
    assert metrics["samples"][0]["value_repr"].strip() == "'   '"
    assert metrics["last_result"] is False
    assert metrics["last_default"] is False

    reset_bool_coercion_metrics()


def test_coerce_bool_records_fallback_for_sequence() -> None:
    """Non-primitive payloads should register fallback coercions."""

    reset_bool_coercion_metrics()

    assert _coerce_bool(["enabled"], default=False) is True

    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 1
    assert metrics["fallback"] == 1
    assert metrics["reason_counts"]["fallback"] == 1
    assert metrics["type_counts"]["list"] == 1
    sample = metrics["samples"][0]
    assert sample["reason"] == "fallback"
    assert sample["value_type"] == "list"
    assert metrics["last_result"] is True
    assert metrics["last_default"] is False

    reset_bool_coercion_metrics()


def test_coerce_bool_records_numeric_reasons() -> None:
    """Numeric conversions should emit dedicated telemetry reasons."""

    reset_bool_coercion_metrics()

    assert _coerce_bool(5, default=False) is True
    assert _coerce_bool(0, default=True) is False

    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 2
    assert metrics["reason_counts"]["numeric_nonzero"] == 1
    assert metrics["reason_counts"]["numeric_zero"] == 1
    first, second = metrics["samples"][:2]
    assert first["reason"] == "numeric_nonzero"
    assert second["reason"] == "numeric_zero"
    assert metrics["last_result"] is False
    assert metrics["last_default"] is True

    reset_bool_coercion_metrics()


def test_coerce_bool_records_native_bool_reason() -> None:
    """Boolean inputs should register dedicated native reason buckets."""

    reset_bool_coercion_metrics()

    assert _coerce_bool(True, default=False) is True
    assert _coerce_bool(False, default=True) is False

    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 2
    assert metrics["reason_counts"]["native_true"] == 1
    assert metrics["reason_counts"]["native_false"] == 1
    first, second = metrics["samples"][:2]
    assert first["reason"] == "native_true"
    assert second["reason"] == "native_false"
    assert metrics["last_result"] is False
    assert metrics["last_default"] is True

    reset_bool_coercion_metrics()


def test_coerce_bool_records_string_reasons() -> None:
    """String payloads should distinguish truthy, falsy, and unknown cases."""

    reset_bool_coercion_metrics()

    assert _coerce_bool("Yes", default=False) is True
    assert _coerce_bool("OFF", default=True) is False
    assert _coerce_bool("maybe", default=True) is False

    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 3
    assert metrics["reason_counts"]["truthy_string"] == 1
    assert metrics["reason_counts"]["falsy_string"] == 1
    assert metrics["reason_counts"]["unknown_string"] == 1
    reasons = [sample["reason"] for sample in metrics["samples"][:3]]
    assert reasons == ["truthy_string", "falsy_string", "unknown_string"]
    assert metrics["last_result"] is False
    assert metrics["last_default"] is True

    reset_bool_coercion_metrics()


def test_bool_coercion_metrics_include_timestamps() -> None:
    """Aggregated metrics should expose first/last timestamps."""

    reset_bool_coercion_metrics()

    assert _coerce_bool("true", default=False) is True
    assert _coerce_bool("false", default=True) is False

    metrics = get_bool_coercion_metrics()
    first_seen_raw = metrics["first_seen"]
    last_seen_raw = metrics["last_seen"]
    assert first_seen_raw is not None
    assert last_seen_raw is not None
    assert metrics["last_reason"] == "falsy_string"
    assert metrics["last_value_type"] == "str"
    assert metrics["last_value_repr"] == "'false'"
    assert metrics["last_result"] is False
    assert metrics["last_default"] is True

    first_seen = datetime.fromisoformat(first_seen_raw)
    last_seen = datetime.fromisoformat(last_seen_raw)
    assert first_seen <= last_seen

    reset_bool_coercion_metrics()

    cleared = get_bool_coercion_metrics()
    assert cleared["first_seen"] is None
    assert cleared["last_seen"] is None
    assert cleared["last_reset"] is not None
    assert cleared["last_result"] is None
    assert cleared["last_default"] is None


def test_bool_coercion_metrics_include_active_window_seconds() -> None:
    """The metrics should surface the active window between coercions."""

    reset_bool_coercion_metrics()

    start = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    later = start + timedelta(seconds=42)

    with patch("custom_components.pawcontrol.telemetry.dt_util.utcnow") as mock_utcnow:
        mock_utcnow.return_value = start
        assert _coerce_bool("true", default=False) is True

        mock_utcnow.return_value = later
        assert _coerce_bool("false", default=True) is False

    metrics = get_bool_coercion_metrics()
    assert metrics["active_window_seconds"] is not None
    assert metrics["active_window_seconds"] >= 42

    reset_bool_coercion_metrics()
    cleared = get_bool_coercion_metrics()
    assert cleared["active_window_seconds"] is None


def test_bool_coercion_metrics_track_reset_count() -> None:
    """Reset invocations should be tracked alongside coercion counters."""

    reset_bool_coercion_metrics()
    baseline = get_bool_coercion_metrics()["reset_count"]

    assert _coerce_bool("true", default=False) is True

    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 1
    assert metrics["reset_count"] == baseline

    reset_bool_coercion_metrics()
    after_reset = get_bool_coercion_metrics()
    assert after_reset["reset_count"] == baseline + 1
    assert after_reset["last_reset"] is not None
    assert after_reset["last_reason"] is None
    assert after_reset["last_value_type"] is None
    assert after_reset["last_value_repr"] is None
    assert after_reset["last_result"] is None
    assert after_reset["last_default"] is None


def test_bool_coercion_metrics_record_last_reset_timestamp() -> None:
    """Reset telemetry should capture the ISO timestamp of the reset."""

    first_reset = datetime(2024, 9, 18, 11, 45, tzinfo=UTC)
    second_reset = first_reset + timedelta(minutes=5)

    with patch("custom_components.pawcontrol.telemetry.dt_util.utcnow") as mock_utcnow:
        mock_utcnow.return_value = first_reset
        reset_bool_coercion_metrics()

    metrics = get_bool_coercion_metrics()
    assert metrics["last_reset"] == first_reset.isoformat()

    with patch("custom_components.pawcontrol.telemetry.dt_util.utcnow") as mock_utcnow:
        mock_utcnow.return_value = second_reset
        reset_bool_coercion_metrics()

    metrics = get_bool_coercion_metrics()
    assert metrics["last_reset"] == second_reset.isoformat()

    reset_bool_coercion_metrics()


def test_bool_coercion_diagnostics_include_reset_only_snapshots() -> None:
    """Diagnostics should expose reset metadata even when no coercions ran."""

    reset_bool_coercion_metrics()
    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 0
    assert metrics["reset_count"] >= 1
    assert metrics["last_reset"] is not None

    payload = _get_bool_coercion_diagnostics(None)
    assert payload["recorded"] is True
    assert payload["metrics"]["reset_count"] == metrics["reset_count"]
    assert payload["metrics"]["total"] == 0
    assert payload["metrics"]["last_reset"] == metrics["last_reset"]
    assert payload["metrics"]["last_reason"] is None
    assert payload["metrics"]["last_result"] is None
    assert payload["metrics"]["last_default"] is None
    summary = payload["summary"]
    assert summary["recorded"] is True
    assert summary["total"] == 0
    assert summary["reset_count"] == metrics["reset_count"]
    assert summary["samples"] == []


def test_bool_coercion_metrics_track_last_reason() -> None:
    """Metrics should expose the most recent coercion reason."""

    reset_bool_coercion_metrics()
    initial = get_bool_coercion_metrics()
    assert initial["last_reason"] is None

    assert _coerce_bool("TRUE", default=False) is True
    metrics = get_bool_coercion_metrics()
    assert metrics["last_reason"] == "truthy_string"

    assert _coerce_bool("off", default=True) is False
    updated = get_bool_coercion_metrics()
    assert updated["last_reason"] == "falsy_string"

    reset_bool_coercion_metrics()
    cleared = get_bool_coercion_metrics()
    assert cleared["last_reason"] is None


def test_bool_coercion_metrics_track_last_value_details() -> None:
    """Metrics should capture the last coerced value's type and representation."""

    reset_bool_coercion_metrics()

    assert _coerce_bool(" yes ", default=False) is True

    metrics = get_bool_coercion_metrics()
    assert metrics["last_value_type"] == "str"
    assert metrics["last_value_repr"] == "' yes '"
    assert metrics["samples"][0]["value_repr"] == "' yes '"
    assert metrics["last_result"] is True
    assert metrics["last_default"] is False

    assert _coerce_bool(0, default=True) is False

    updated = get_bool_coercion_metrics()
    assert updated["last_value_type"] == "int"
    assert updated["last_value_repr"] == "0"
    assert updated["samples"][-1]["value_repr"] == "0"
    assert updated["last_result"] is False
    assert updated["last_default"] is True

    reset_bool_coercion_metrics()
    cleared = get_bool_coercion_metrics()
    assert cleared["last_value_type"] is None
    assert cleared["last_value_repr"] is None
    assert cleared["last_result"] is None
    assert cleared["last_default"] is None


def test_summarise_bool_coercion_metrics_limits_samples() -> None:
    """Coordinator summaries should clamp sample counts and sort reason keys."""

    reset_bool_coercion_metrics()

    record_bool_coercion_event(
        value="yes",
        default=False,
        result=True,
        reason="truthy_string",
    )
    record_bool_coercion_event(
        value="no",
        default=True,
        result=False,
        reason="falsy_string",
    )
    record_bool_coercion_event(
        value="maybe",
        default=True,
        result=False,
        reason="unknown_string",
    )

    summary = summarise_bool_coercion_metrics(sample_limit=2)
    assert summary["recorded"] is True
    assert summary["total"] == 3
    assert list(summary["reason_counts"].keys()) == [
        "falsy_string",
        "truthy_string",
        "unknown_string",
    ]
    assert len(summary["samples"]) == 2
    assert summary["samples"][0]["reason"] == "truthy_string"
    assert summary["samples"][1]["reason"] == "falsy_string"

    reset_bool_coercion_metrics()
    cleared = summarise_bool_coercion_metrics()
    assert cleared["total"] == 0
    assert cleared["reason_counts"] == {}
    assert cleared["samples"] == []
