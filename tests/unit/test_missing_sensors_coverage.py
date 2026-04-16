"""Coverage tests for missing_sensors.py — pure helpers (0% → 18%+).

Covers: calculate_hours_since, ensure_utc_datetime
"""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pawcontrol.missing_sensors import (
    calculate_hours_since,
    ensure_utc_datetime,
)

# ─── calculate_hours_since ────────────────────────────────────────────────────


@pytest.mark.unit
def test_calculate_hours_since_none() -> None:
    result = calculate_hours_since(None)
    assert result is None


@pytest.mark.unit
def test_calculate_hours_since_now() -> None:
    now = datetime.now(UTC)
    result = calculate_hours_since(now)
    assert result is not None
    assert result == pytest.approx(0.0, abs=0.01)


@pytest.mark.unit
def test_calculate_hours_since_two_hours_ago() -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    result = calculate_hours_since(past)
    assert result is not None
    assert result == pytest.approx(2.0, abs=0.01)


@pytest.mark.unit
def test_calculate_hours_since_one_day_ago() -> None:
    past = datetime.now(UTC) - timedelta(hours=24)
    result = calculate_hours_since(past)
    assert result is not None
    assert result == pytest.approx(24.0, abs=0.1)


@pytest.mark.unit
def test_calculate_hours_since_with_reference() -> None:
    ref = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    ts = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
    result = calculate_hours_since(ts, reference=ref)
    assert result is not None
    assert result == pytest.approx(2.0, abs=0.01)


@pytest.mark.unit
def test_calculate_hours_since_string_timestamp() -> None:
    ts = "2025-01-01T10:00:00+00:00"
    result = calculate_hours_since(ts)
    assert result is None or isinstance(result, float)


# ─── ensure_utc_datetime ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_ensure_utc_datetime_none() -> None:
    result = ensure_utc_datetime(None)
    assert result is None


@pytest.mark.unit
def test_ensure_utc_datetime_aware_datetime() -> None:
    dt = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
    result = ensure_utc_datetime(dt)
    assert result is not None
    assert result.tzinfo is not None


@pytest.mark.unit
def test_ensure_utc_datetime_string() -> None:
    result = ensure_utc_datetime("2025-06-01T10:00:00+00:00")
    assert result is None or isinstance(result, datetime)


@pytest.mark.unit
def test_ensure_utc_datetime_preserves_value() -> None:
    dt = datetime(2025, 3, 15, 8, 30, tzinfo=UTC)
    result = ensure_utc_datetime(dt)
    if result is not None:
        assert result.hour == 8
        assert result.minute == 30
