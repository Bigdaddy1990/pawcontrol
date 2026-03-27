"""Coverage tests for PawControl utility serialization/normalization helpers."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import pytest

from custom_components.pawcontrol.utils.normalize import normalize_value
from custom_components.pawcontrol.utils.serialize import (
    serialize_dataclass,
    serialize_datetime,
    serialize_entity_attributes,
    serialize_timedelta,
)


@dataclass(slots=True)
class _Dog:
    name: str
    age: int
    adopted_at: datetime


class _ReprOnly:
    def __repr__(self) -> str:
        return "repr-only"


class _StrOnly:
    def __str__(self) -> str:
        return "str-only"


def test_normalize_value_handles_scalar_datetime_and_temporal_types() -> None:
    """normalize_value should convert scalar temporal values to JSON-safe output."""
    ts = datetime(2026, 3, 1, 12, 30, tzinfo=UTC)

    assert normalize_value(None) is None
    assert normalize_value(5) == 5
    assert normalize_value(3.5) == 3.5
    assert normalize_value("hello") == "hello"
    assert normalize_value(True) is True
    assert normalize_value(ts) == "2026-03-01T12:30:00+00:00"
    assert normalize_value(date(2026, 3, 1)) == "2026-03-01"
    assert normalize_value(time(12, 30, 45)) == "12:30:45"
    assert normalize_value(timedelta(minutes=3, seconds=10)) == 190.0


def test_normalize_value_recursively_converts_dataclass_mappings_and_iterables() -> (
    None
):
    """normalize_value should recursively serialize dataclasses and containers."""
    ts = datetime(2026, 3, 1, 12, 30, tzinfo=UTC)
    dog = _Dog(name="Buddy", age=4, adopted_at=ts)

    normalized = normalize_value({
        "dog": dog,
        7: {"nested": {"tag-a", "tag-b"}},
        "numbers": (1, 2, 3),
        "byte_data": b"abc",
    })

    assert normalized["dog"] == {
        "name": "Buddy",
        "age": 4,
        "adopted_at": "2026-03-01T12:30:00+00:00",
    }
    assert normalized["7"]["nested"]
    assert set(normalized["7"]["nested"]) == {"tag-a", "tag-b"}
    assert normalized["numbers"] == [1, 2, 3]
    assert normalized["byte_data"] == "b'abc'"


def test_normalize_value_falls_back_to_repr() -> None:
    """normalize_value should use repr() for unsupported objects."""
    assert normalize_value(_ReprOnly()) == "repr-only"


def test_serialize_datetime_and_timedelta_helpers() -> None:
    """Serialize helper functions should return stable JSON values."""
    ts = datetime(2026, 2, 15, 10, 30, tzinfo=UTC)

    assert serialize_datetime(ts) == "2026-02-15T10:30:00+00:00"
    assert serialize_timedelta(timedelta(minutes=30, milliseconds=900)) == 1800


def test_serialize_dataclass_validates_instance_type() -> None:
    """serialize_dataclass should accept instances and reject invalid inputs."""

    @dataclass
    class _Payload:
        value: int

    assert serialize_dataclass(_Payload(value=42)) == {"value": 42}

    with pytest.raises(TypeError, match="Expected dataclass instance"):
        serialize_dataclass({"value": 42})

    with pytest.raises(TypeError, match="received a class"):
        serialize_dataclass(_Payload)


def test_serialize_entity_attributes_recursively_serializes_supported_values() -> None:
    """serialize_entity_attributes should recursively normalize nested structures."""
    ts = datetime(2026, 3, 1, 12, 30, tzinfo=UTC)

    @dataclass
    class _Meta:
        when: datetime
        elapsed: timedelta

    attrs = {
        "last_seen": ts,
        "duration": timedelta(seconds=75),
        "meta": _Meta(when=ts, elapsed=timedelta(seconds=9)),
        "items": [timedelta(seconds=3), (timedelta(seconds=4), _StrOnly())],
        "plain": "ok",
        "null": None,
        "other": _StrOnly(),
    }

    result = serialize_entity_attributes(attrs)

    assert result == {
        "last_seen": "2026-03-01T12:30:00+00:00",
        "duration": 75,
        "meta": {"when": "2026-03-01T12:30:00+00:00", "elapsed": 9},
        "items": [3, [4, "str-only"]],
        "plain": "ok",
        "null": None,
        "other": "str-only",
    }
