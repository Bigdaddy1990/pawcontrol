"""Unit tests for JSON normalization helpers."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from custom_components.pawcontrol.utils.normalize import normalize_value


@dataclass
class _DogSnapshot:
    """Simple dataclass payload used to verify recursive conversion."""

    name: str
    next_walk: datetime


class _Unserializable:
    """Object without dedicated normalization support."""


def test_normalize_value_converts_supported_types() -> None:
    """normalize_value should convert all explicitly handled branch types."""
    snapshot = _DogSnapshot(
        name="Buddy",
        next_walk=datetime(2026, 1, 2, 3, 4, 5),
    )

    normalized = normalize_value(
        {
            "int": 1,
            "float": 2.5,
            "bool": True,
            "none": None,
            "datetime": datetime(2026, 6, 7, 8, 9, 10),
            "date": date(2026, 6, 7),
            "time": time(8, 9, 10),
            "timedelta": timedelta(minutes=2),
            "dataclass": snapshot,
            "set": {"a", "b"},
            "iterable": (1, 2),
            "bytes": b"raw",
        },
    )

    assert normalized["datetime"] == "2026-06-07T08:09:10"
    assert normalized["date"] == "2026-06-07"
    assert normalized["time"] == "08:09:10"
    assert normalized["timedelta"] == 120.0
    assert normalized["dataclass"]["name"] == "Buddy"
    assert normalized["dataclass"]["next_walk"] == "2026-01-02T03:04:05"
    assert sorted(normalized["set"]) == ["a", "b"]
    assert normalized["iterable"] == [1, 2]
    assert normalized["bytes"] == "b'raw'"


def test_normalize_value_stringifies_mapping_keys_and_falls_back_to_repr() -> None:
    """Mappings should get string keys and unsupported objects should use repr."""
    payload = {1: _Unserializable()}

    normalized = normalize_value(payload)

    assert list(normalized.keys()) == ["1"]
    assert normalized["1"].startswith("<")
    assert "_Unserializable" in normalized["1"]
