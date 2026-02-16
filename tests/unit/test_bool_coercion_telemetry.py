"""Validate bool coercion telemetry snapshots."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from custom_components.pawcontrol.diagnostics import _get_bool_coercion_diagnostics
from custom_components.pawcontrol.telemetry import (
  get_bool_coercion_metrics,
  record_bool_coercion_event,
  reset_bool_coercion_metrics,
  summarise_bool_coercion_metrics,
)
from custom_components.pawcontrol.types import _coerce_bool


def test_coerce_bool_records_none_default() -> None:
  """None inputs should count as defaulted coercions."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  assert _coerce_bool(None, default=True) is True  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["total"] == 1  # noqa: E111
  assert metrics["defaulted"] == 1  # noqa: E111
  assert metrics["reason_counts"]["none"] == 1  # noqa: E111
  assert metrics["samples"][0]["reason"] == "none"  # noqa: E111
  assert metrics["last_result"] is True  # noqa: E111
  assert metrics["last_default"] is True  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111


def test_coerce_bool_records_blank_string_default() -> None:
  """Blank strings should increment the blank-string reason bucket."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  assert _coerce_bool("   ", default=False) is False  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["total"] == 1  # noqa: E111
  assert metrics["defaulted"] == 1  # noqa: E111
  assert metrics["reason_counts"]["blank_string"] == 1  # noqa: E111
  assert metrics["samples"][0]["value_repr"].strip() == "'   '"  # noqa: E111
  assert metrics["last_result"] is False  # noqa: E111
  assert metrics["last_default"] is False  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111


def test_coerce_bool_records_fallback_for_sequence() -> None:
  """Non-primitive payloads should register fallback coercions."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  assert _coerce_bool(["enabled"], default=False) is True  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["total"] == 1  # noqa: E111
  assert metrics["fallback"] == 1  # noqa: E111
  assert metrics["reason_counts"]["fallback"] == 1  # noqa: E111
  assert metrics["type_counts"]["list"] == 1  # noqa: E111
  sample = metrics["samples"][0]  # noqa: E111
  assert sample["reason"] == "fallback"  # noqa: E111
  assert sample["value_type"] == "list"  # noqa: E111
  assert metrics["last_result"] is True  # noqa: E111
  assert metrics["last_default"] is False  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111


def test_coerce_bool_records_numeric_reasons() -> None:
  """Numeric conversions should emit dedicated telemetry reasons."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  assert _coerce_bool(5, default=False) is True  # noqa: E111
  assert _coerce_bool(0, default=True) is False  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["total"] == 2  # noqa: E111
  assert metrics["reason_counts"]["numeric_nonzero"] == 1  # noqa: E111
  assert metrics["reason_counts"]["numeric_zero"] == 1  # noqa: E111
  first, second = metrics["samples"][:2]  # noqa: E111
  assert first["reason"] == "numeric_nonzero"  # noqa: E111
  assert second["reason"] == "numeric_zero"  # noqa: E111
  assert metrics["last_result"] is False  # noqa: E111
  assert metrics["last_default"] is True  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111


def test_coerce_bool_records_native_bool_reason() -> None:
  """Boolean inputs should register dedicated native reason buckets."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  assert _coerce_bool(True, default=False) is True  # noqa: E111
  assert _coerce_bool(False, default=True) is False  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["total"] == 2  # noqa: E111
  assert metrics["reason_counts"]["native_true"] == 1  # noqa: E111
  assert metrics["reason_counts"]["native_false"] == 1  # noqa: E111
  first, second = metrics["samples"][:2]  # noqa: E111
  assert first["reason"] == "native_true"  # noqa: E111
  assert second["reason"] == "native_false"  # noqa: E111
  assert metrics["last_result"] is False  # noqa: E111
  assert metrics["last_default"] is True  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111


def test_coerce_bool_records_string_reasons() -> None:
  """String payloads should distinguish truthy, falsy, and unknown cases."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  assert _coerce_bool("Yes", default=False) is True  # noqa: E111
  assert _coerce_bool("OFF", default=True) is False  # noqa: E111
  assert _coerce_bool("maybe", default=True) is False  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["total"] == 3  # noqa: E111
  assert metrics["reason_counts"]["truthy_string"] == 1  # noqa: E111
  assert metrics["reason_counts"]["falsy_string"] == 1  # noqa: E111
  assert metrics["reason_counts"]["unknown_string"] == 1  # noqa: E111
  reasons = [sample["reason"] for sample in metrics["samples"][:3]]  # noqa: E111
  assert reasons == ["truthy_string", "falsy_string", "unknown_string"]  # noqa: E111
  assert metrics["last_result"] is False  # noqa: E111
  assert metrics["last_default"] is True  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111


def test_bool_coercion_metrics_include_timestamps() -> None:
  """Aggregated metrics should expose first/last timestamps."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  assert _coerce_bool("true", default=False) is True  # noqa: E111
  assert _coerce_bool("false", default=True) is False  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  first_seen_raw = metrics["first_seen"]  # noqa: E111
  last_seen_raw = metrics["last_seen"]  # noqa: E111
  assert first_seen_raw is not None  # noqa: E111
  assert last_seen_raw is not None  # noqa: E111
  assert metrics["last_reason"] == "falsy_string"  # noqa: E111
  assert metrics["last_value_type"] == "str"  # noqa: E111
  assert metrics["last_value_repr"] == "'false'"  # noqa: E111
  assert metrics["last_result"] is False  # noqa: E111
  assert metrics["last_default"] is True  # noqa: E111

  first_seen = datetime.fromisoformat(first_seen_raw)  # noqa: E111
  last_seen = datetime.fromisoformat(last_seen_raw)  # noqa: E111
  assert first_seen <= last_seen  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  cleared = get_bool_coercion_metrics()  # noqa: E111
  assert cleared["first_seen"] is None  # noqa: E111
  assert cleared["last_seen"] is None  # noqa: E111
  assert cleared["last_reset"] is not None  # noqa: E111
  assert cleared["last_result"] is None  # noqa: E111
  assert cleared["last_default"] is None  # noqa: E111


def test_bool_coercion_metrics_include_active_window_seconds() -> None:
  """The metrics should surface the active window between coercions."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  start = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)  # noqa: E111
  later = start + timedelta(seconds=42)  # noqa: E111

  with patch("custom_components.pawcontrol.telemetry.dt_util.utcnow") as mock_utcnow:  # noqa: E111
    mock_utcnow.return_value = start
    assert _coerce_bool("true", default=False) is True

    mock_utcnow.return_value = later
    assert _coerce_bool("false", default=True) is False

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["active_window_seconds"] is not None  # noqa: E111
  assert metrics["active_window_seconds"] >= 42  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111
  cleared = get_bool_coercion_metrics()  # noqa: E111
  assert cleared["active_window_seconds"] is None  # noqa: E111


def test_bool_coercion_metrics_track_reset_count() -> None:
  """Reset invocations should be tracked alongside coercion counters."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111
  baseline = get_bool_coercion_metrics()["reset_count"]  # noqa: E111

  assert _coerce_bool("true", default=False) is True  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["total"] == 1  # noqa: E111
  assert metrics["reset_count"] == baseline  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111
  after_reset = get_bool_coercion_metrics()  # noqa: E111
  assert after_reset["reset_count"] == baseline + 1  # noqa: E111
  assert after_reset["last_reset"] is not None  # noqa: E111
  assert after_reset["last_reason"] is None  # noqa: E111
  assert after_reset["last_value_type"] is None  # noqa: E111
  assert after_reset["last_value_repr"] is None  # noqa: E111
  assert after_reset["last_result"] is None  # noqa: E111
  assert after_reset["last_default"] is None  # noqa: E111


def test_bool_coercion_metrics_record_last_reset_timestamp() -> None:
  """Reset telemetry should capture the ISO timestamp of the reset."""  # noqa: E111

  first_reset = datetime(2024, 9, 18, 11, 45, tzinfo=UTC)  # noqa: E111
  second_reset = first_reset + timedelta(minutes=5)  # noqa: E111

  with patch("custom_components.pawcontrol.telemetry.dt_util.utcnow") as mock_utcnow:  # noqa: E111
    mock_utcnow.return_value = first_reset
    reset_bool_coercion_metrics()

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["last_reset"] == first_reset.isoformat()  # noqa: E111

  with patch("custom_components.pawcontrol.telemetry.dt_util.utcnow") as mock_utcnow:  # noqa: E111
    mock_utcnow.return_value = second_reset
    reset_bool_coercion_metrics()

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["last_reset"] == second_reset.isoformat()  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111


def test_bool_coercion_diagnostics_include_reset_only_snapshots() -> None:
  """Diagnostics should expose reset metadata even when no coercions ran."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111
  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["total"] == 0  # noqa: E111
  assert metrics["reset_count"] >= 1  # noqa: E111
  assert metrics["last_reset"] is not None  # noqa: E111

  payload = _get_bool_coercion_diagnostics(None)  # noqa: E111
  assert payload["recorded"] is True  # noqa: E111
  assert payload["metrics"]["reset_count"] == metrics["reset_count"]  # noqa: E111
  assert payload["metrics"]["total"] == 0  # noqa: E111
  assert payload["metrics"]["last_reset"] == metrics["last_reset"]  # noqa: E111
  assert payload["metrics"]["last_reason"] is None  # noqa: E111
  assert payload["metrics"]["last_result"] is None  # noqa: E111
  assert payload["metrics"]["last_default"] is None  # noqa: E111
  summary = payload["summary"]  # noqa: E111
  assert summary["recorded"] is True  # noqa: E111
  assert summary["total"] == 0  # noqa: E111
  assert summary["reset_count"] == metrics["reset_count"]  # noqa: E111
  assert summary["samples"] == []  # noqa: E111


def test_bool_coercion_metrics_track_last_reason() -> None:
  """Metrics should expose the most recent coercion reason."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111
  initial = get_bool_coercion_metrics()  # noqa: E111
  assert initial["last_reason"] is None  # noqa: E111

  assert _coerce_bool("TRUE", default=False) is True  # noqa: E111
  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["last_reason"] == "truthy_string"  # noqa: E111

  assert _coerce_bool("off", default=True) is False  # noqa: E111
  updated = get_bool_coercion_metrics()  # noqa: E111
  assert updated["last_reason"] == "falsy_string"  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111
  cleared = get_bool_coercion_metrics()  # noqa: E111
  assert cleared["last_reason"] is None  # noqa: E111


def test_bool_coercion_metrics_track_last_value_details() -> None:
  """Metrics should capture the last coerced value's type and representation."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  assert _coerce_bool(" yes ", default=False) is True  # noqa: E111

  metrics = get_bool_coercion_metrics()  # noqa: E111
  assert metrics["last_value_type"] == "str"  # noqa: E111
  assert metrics["last_value_repr"] == "' yes '"  # noqa: E111
  assert metrics["samples"][0]["value_repr"] == "' yes '"  # noqa: E111
  assert metrics["last_result"] is True  # noqa: E111
  assert metrics["last_default"] is False  # noqa: E111

  assert _coerce_bool(0, default=True) is False  # noqa: E111

  updated = get_bool_coercion_metrics()  # noqa: E111
  assert updated["last_value_type"] == "int"  # noqa: E111
  assert updated["last_value_repr"] == "0"  # noqa: E111
  assert updated["samples"][-1]["value_repr"] == "0"  # noqa: E111
  assert updated["last_result"] is False  # noqa: E111
  assert updated["last_default"] is True  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111
  cleared = get_bool_coercion_metrics()  # noqa: E111
  assert cleared["last_value_type"] is None  # noqa: E111
  assert cleared["last_value_repr"] is None  # noqa: E111
  assert cleared["last_result"] is None  # noqa: E111
  assert cleared["last_default"] is None  # noqa: E111


def test_summarise_bool_coercion_metrics_limits_samples() -> None:
  """Coordinator summaries should clamp sample counts and sort reason keys."""  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111

  record_bool_coercion_event(  # noqa: E111
    value="yes",
    default=False,
    result=True,
    reason="truthy_string",
  )
  record_bool_coercion_event(  # noqa: E111
    value="no",
    default=True,
    result=False,
    reason="falsy_string",
  )
  record_bool_coercion_event(  # noqa: E111
    value="maybe",
    default=True,
    result=False,
    reason="unknown_string",
  )

  summary = summarise_bool_coercion_metrics(sample_limit=2)  # noqa: E111
  assert summary["recorded"] is True  # noqa: E111
  assert summary["total"] == 3  # noqa: E111
  assert list(summary["reason_counts"].keys()) == [  # noqa: E111
    "falsy_string",
    "truthy_string",
    "unknown_string",
  ]
  assert len(summary["samples"]) == 2  # noqa: E111
  assert summary["samples"][0]["reason"] == "truthy_string"  # noqa: E111
  assert summary["samples"][1]["reason"] == "falsy_string"  # noqa: E111

  reset_bool_coercion_metrics()  # noqa: E111
  cleared = summarise_bool_coercion_metrics()  # noqa: E111
  assert cleared["total"] == 0  # noqa: E111
  assert cleared["reason_counts"] == {}  # noqa: E111
  assert cleared["samples"] == []  # noqa: E111
