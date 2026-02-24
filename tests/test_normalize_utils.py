"""Tests for JSON normalization helpers."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from custom_components.pawcontrol.utils.normalize import normalize_value


@dataclass
class PetSnapshot:
    """Simple dataclass used for normalization tests."""

    name: str
    active: bool
    walk_duration: timedelta


class _CustomObject:
    """Custom object with stable repr for fallback coverage."""

    def __repr__(self) -> str:
        return "<custom-object>"


def test_normalize_value_scalar_passthrough() -> None:
    """Scalars and None should be returned unchanged."""
    assert normalize_value(None) is None
    assert normalize_value(True) is True
    assert normalize_value(7) == 7
    assert normalize_value(3.5) == 3.5
    assert normalize_value("paws") == "paws"


def test_normalize_value_temporal_types() -> None:
    """Temporal values should be converted to JSON-safe formats."""
    moment = datetime(2025, 1, 2, 3, 4, 5)
    today = date(2025, 1, 2)
    at_time = time(3, 4, 5)
    duration = timedelta(minutes=5, seconds=30)

    assert normalize_value(moment) == "2025-01-02T03:04:05"
    assert normalize_value(today) == "2025-01-02"
    assert normalize_value(at_time) == "03:04:05"
    assert normalize_value(duration) == 330.0


def test_normalize_value_recursive_mapping_and_iterables() -> None:
    """Nested mappings, sets, and iterables should normalize recursively."""
    normalized = normalize_value({
        1: ["ok", timedelta(seconds=3)],
        "set_data": {2, 4},
        "tuple_data": (date(2024, 12, 31),),
        "byte_payload": b"ab",
    })

    assert normalized["1"] == ["ok", 3.0]
    assert sorted(normalized["set_data"]) == [2, 4]
    assert normalized["tuple_data"] == ["2024-12-31"]
    assert normalized["byte_payload"] == "b'ab'"


def test_normalize_value_dataclass_and_object_fallback() -> None:
    """Dataclasses become dictionaries and unknown objects fall back to repr."""
    snapshot = PetSnapshot(
        name="Luna", active=True, walk_duration=timedelta(minutes=12)
    )

    assert normalize_value(snapshot) == {
        "name": "Luna",
        "active": True,
        "walk_duration": 720.0,
    }
    assert normalize_value(_CustomObject()) == "<custom-object>"
