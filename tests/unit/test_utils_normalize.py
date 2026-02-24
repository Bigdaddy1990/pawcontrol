"""Tests for JSON normalization helpers."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from custom_components.pawcontrol.utils.normalize import normalize_value


@dataclass
class _SampleDataclass:
    """Dataclass fixture for normalization tests."""

    created_at: datetime
    tags: set[str]


class _ReprOnly:
    """Simple object that relies on repr fallback."""

    def __repr__(self) -> str:
        return "<repr-only>"


def test_normalize_value_handles_scalar_and_temporal_types() -> None:
    """Scalar and temporal values should be converted to JSON-compatible values."""
    now = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)

    assert normalize_value(None) is None
    assert normalize_value(True) is True
    assert normalize_value(4) == 4
    assert normalize_value(3.5) == 3.5
    assert normalize_value("paw") == "paw"
    assert normalize_value(now) == now.isoformat()
    assert normalize_value(date(2025, 1, 2)) == "2025-01-02"
    assert normalize_value(time(3, 4, 5)) == "03:04:05"
    assert normalize_value(timedelta(minutes=2, seconds=1)) == 121.0


def test_normalize_value_handles_dataclass_mapping_and_iterables() -> None:
    """Dataclasses and containers should be normalized recursively."""
    sample = _SampleDataclass(
        created_at=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
        tags={"dog", "cat"},
    )

    normalized_dataclass = normalize_value(sample)

    assert normalized_dataclass["created_at"] == "2025-01-02T03:04:05+00:00"
    assert set(normalized_dataclass["tags"]) == {"dog", "cat"}

    normalized_mapping = normalize_value({1: datetime(2025, 1, 2, tzinfo=UTC)})
    assert normalized_mapping == {"1": "2025-01-02T00:00:00+00:00"}

    normalized_set = normalize_value({1, 2, 3})
    assert set(normalized_set) == {1, 2, 3}

    normalized_iterable = normalize_value((date(2025, 1, 2), "ok"))
    assert normalized_iterable == ["2025-01-02", "ok"]


def test_normalize_value_uses_repr_for_unknown_types() -> None:
    """Unknown objects should fall back to repr output."""
    assert normalize_value(_ReprOnly()) == "<repr-only>"
