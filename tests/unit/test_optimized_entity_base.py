"""Unit tests for optimized_entity_base.py.

Focuses on pure-Python components: PerformanceTracker, CACHE_TTL_SECONDS,
MEMORY_OPTIMIZATION, and utility functions (_coordinator_is_available,
_call_coordinator_method, _normalize_cache_timestamp, _normalise_attributes).
These can be exercised without constructing a live HA entity.
"""

from dataclasses import dataclass
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.optimized_entity_base import (
    CACHE_TTL_SECONDS,
    MEMORY_OPTIMIZATION,
    PerformanceTracker,
    _call_coordinator_method,
    _coordinator_is_available,
    _normalise_attributes,
    _normalize_cache_timestamp,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cache_ttl_seconds_has_expected_keys() -> None:
    """CACHE_TTL_SECONDS contains state, attributes, and availability."""
    assert "state" in CACHE_TTL_SECONDS
    assert "attributes" in CACHE_TTL_SECONDS
    assert "availability" in CACHE_TTL_SECONDS
    for key, val in CACHE_TTL_SECONDS.items():
        assert isinstance(val, int) and val > 0, f"{key} TTL must be positive int"


@pytest.mark.unit
def test_memory_optimization_has_expected_keys() -> None:
    """MEMORY_OPTIMIZATION contains required config keys with sensible values."""
    assert MEMORY_OPTIMIZATION["max_cache_entries"] > 0
    assert 0 < MEMORY_OPTIMIZATION["cache_cleanup_threshold"] <= 1.0
    assert MEMORY_OPTIMIZATION["performance_sample_size"] > 0


# ---------------------------------------------------------------------------
# _coordinator_is_available
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_coordinator_is_available_none() -> None:
    """None coordinator is treated as available."""
    assert _coordinator_is_available(None) is True


@pytest.mark.unit
def test_coordinator_is_available_true_attr() -> None:
    """Coordinator with available=True is available."""
    coord = MagicMock()
    coord.available = True
    assert _coordinator_is_available(coord) is True


@pytest.mark.unit
def test_coordinator_is_available_false_attr() -> None:
    """Coordinator with available=False is not available."""
    coord = MagicMock()
    coord.available = False
    assert _coordinator_is_available(coord) is False


@pytest.mark.unit
def test_coordinator_is_available_callable_attr() -> None:
    """Coordinator with callable available property is evaluated."""
    coord = MagicMock()
    coord.available = lambda: True
    assert _coordinator_is_available(coord) is True


@pytest.mark.unit
def test_coordinator_is_available_missing_attr() -> None:
    """Coordinator without available attribute defaults to True."""

    class _NoAvailable:
        pass

    assert _coordinator_is_available(_NoAvailable()) is True


# ---------------------------------------------------------------------------
# _call_coordinator_method
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_call_coordinator_method_none_coordinator() -> None:
    """Returns None when coordinator is None."""
    assert _call_coordinator_method(None, "some_method") is None


@pytest.mark.unit
def test_call_coordinator_method_missing_method() -> None:
    """Returns None when coordinator lacks the method."""

    class _Sparse:
        pass

    assert _call_coordinator_method(_Sparse(), "get_data") is None


@pytest.mark.unit
def test_call_coordinator_method_returns_sync_result() -> None:
    """Returns synchronous result from coordinator method."""

    class _Coord:
        def get_info(self) -> str:
            return "hello"

    assert _call_coordinator_method(_Coord(), "get_info") == "hello"


@pytest.mark.unit
def test_call_coordinator_method_skips_async_result() -> None:
    """Returns None when method result is a coroutine (awaitable)."""

    class _Coord:
        async def fetch(self) -> str:
            return "async"

    result = _call_coordinator_method(_Coord(), "fetch")
    # The coroutine is created but not awaited; result should be None
    assert result is None


@pytest.mark.unit
def test_call_coordinator_method_handles_type_error() -> None:
    """Returns None if the method raises TypeError on call."""

    class _Coord:
        def bad(self, required_arg: str) -> str:
            return required_arg

    # Calling without the required arg should trigger TypeError → None
    assert _call_coordinator_method(_Coord(), "bad") is None


# ---------------------------------------------------------------------------
# _normalize_cache_timestamp
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalize_cache_timestamp_past() -> None:
    """Past timestamp is returned unchanged; normalised=False."""
    now = 1_000.0
    past = 999.0
    ts, normalised = _normalize_cache_timestamp(past, now)
    assert ts == past
    assert normalised is False


@pytest.mark.unit
def test_normalize_cache_timestamp_equal_to_now() -> None:
    """Timestamp equal to now is not normalised."""
    now = 1_000.0
    ts, normalised = _normalize_cache_timestamp(now, now)
    assert ts == now
    assert normalised is False


@pytest.mark.unit
def test_normalize_cache_timestamp_slight_future_within_tolerance() -> None:
    """Timestamp slightly in the future (within tolerance) is clamped to now."""
    now = 1_000.0
    slightly_ahead = now + 0.5  # within default tolerance of 1.0
    ts, normalised = _normalize_cache_timestamp(slightly_ahead, now)
    assert ts == now
    assert normalised is True


@pytest.mark.unit
def test_normalize_cache_timestamp_far_future() -> None:
    """Timestamp far in the future is normalised to now."""
    now = 1_000.0
    far_ahead = now + 500.0
    ts, normalised = _normalize_cache_timestamp(far_ahead, now)
    assert ts == now
    assert normalised is True


@pytest.mark.unit
def test_normalize_cache_timestamp_custom_tolerance() -> None:
    """Custom tolerance boundary respected."""
    now = 1_000.0
    # Exactly 5.0 ahead with tolerance=5.0 → NOT normalised (uses <=)
    ts, normalised = _normalize_cache_timestamp(now + 5.0, now, tolerance=5.0)
    assert ts == now
    assert normalised is True

    # 4.9 ahead with tolerance=5.0 → clamped
    ts2, normalised2 = _normalize_cache_timestamp(now + 4.9, now, tolerance=5.0)
    assert ts2 == now
    assert normalised2 is True


# ---------------------------------------------------------------------------
# _normalise_attributes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalise_attributes_passthrough_simple() -> None:
    """Simple string-value dict passes through as JSON-safe mapping."""
    attrs: Any = {"dog_id": "fido", "weight": 12.5, "is_active": True}
    result = _normalise_attributes(attrs)
    assert result["dog_id"] == "fido"
    assert result["weight"] == 12.5


@pytest.mark.unit
def test_normalise_attributes_empty_dict() -> None:
    """Empty dict normalises to empty dict."""
    result = _normalise_attributes({})
    assert result == {}


# ---------------------------------------------------------------------------
# PerformanceTracker
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_performance_tracker_initial_no_data() -> None:
    """Fresh tracker returns 'no_data' summary."""
    tracker = PerformanceTracker("sensor.test")
    summary = tracker.get_performance_summary()
    assert summary == {"status": "no_data"}


@pytest.mark.unit
def test_performance_tracker_record_operation_time() -> None:
    """Recording operation times produces valid averages."""
    tracker = PerformanceTracker("sensor.avg")
    tracker.record_operation_time(1.0)
    tracker.record_operation_time(3.0)
    summary = tracker.get_performance_summary()
    assert summary["avg_operation_time"] == pytest.approx(2.0)
    assert summary["min_operation_time"] == 1.0
    assert summary["max_operation_time"] == 3.0
    assert summary["total_operations"] == 2


@pytest.mark.unit
def test_performance_tracker_error_rate() -> None:
    """Error rate is computed correctly from recorded errors."""
    tracker = PerformanceTracker("sensor.err")
    tracker.record_operation_time(0.5)
    tracker.record_operation_time(0.5)
    tracker.record_error()
    summary = tracker.get_performance_summary()
    assert summary["error_count"] == 1
    assert summary["error_rate"] == pytest.approx(0.5)


@pytest.mark.unit
def test_performance_tracker_cache_hit_rate() -> None:
    """Cache hit rate is calculated as hits / (hits + misses) * 100."""
    tracker = PerformanceTracker("sensor.cache")
    tracker.record_operation_time(0.1)  # required for non-empty summary
    for _ in range(3):
        tracker.record_cache_hit()
    tracker.record_cache_miss()
    summary = tracker.get_performance_summary()
    assert summary["cache_hit_rate"] == pytest.approx(75.0)
    assert summary["total_cache_operations"] == 4


@pytest.mark.unit
def test_performance_tracker_zero_cache_hit_rate() -> None:
    """Cache hit rate is 0 when no cache operations recorded."""
    tracker = PerformanceTracker("sensor.nocache")
    tracker.record_operation_time(0.1)
    summary = tracker.get_performance_summary()
    assert summary["cache_hit_rate"] == 0


@pytest.mark.unit
def test_performance_tracker_caps_samples() -> None:
    """Tracker keeps only the most recent 'performance_sample_size' samples."""
    tracker = PerformanceTracker("sensor.cap")
    max_samples = MEMORY_OPTIMIZATION["performance_sample_size"]
    for i in range(max_samples + 20):
        tracker.record_operation_time(float(i))

    assert len(tracker._operation_times) == max_samples
    # The kept samples should be the most recent ones
    assert tracker._operation_times[-1] == float(max_samples + 19)
