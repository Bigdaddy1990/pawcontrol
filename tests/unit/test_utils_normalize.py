from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from custom_components.pawcontrol.utils.normalize import normalize_value


@dataclass
class DeviceSnapshot:
    dog_name: str
    feed_count: int


class ReprOnly:
    def __repr__(self) -> str:
        return "ReprOnly<snapshot>"


def test_normalize_value_handles_json_primitives() -> None:
    assert normalize_value(None) is None
    assert normalize_value(5) == 5
    assert normalize_value(1.25) == 1.25
    assert normalize_value("value") == "value"
    assert normalize_value(False) is False


def test_normalize_value_handles_datetime_related_types() -> None:
    assert normalize_value(datetime(2025, 1, 2, 3, 4, 5)) == "2025-01-02T03:04:05"
    assert normalize_value(date(2025, 1, 2)) == "2025-01-02"
    assert normalize_value(time(3, 4, 5)) == "03:04:05"
    assert normalize_value(timedelta(minutes=2, seconds=30)) == 150.0


def test_normalize_value_handles_nested_mappings_sets_and_iterables() -> None:
    value = {
        "values": (1, 2),
        "tags": {"alpha", "beta"},
        7: [timedelta(seconds=1), timedelta(seconds=2)],
    }

    normalized = normalize_value(value)

    assert normalized["values"] == [1, 2]
    assert sorted(normalized["tags"]) == ["alpha", "beta"]
    assert normalized["7"] == [1.0, 2.0]


def test_normalize_value_handles_dataclass_instances_and_fallback_repr() -> None:
    assert normalize_value(DeviceSnapshot("Luna", 3)) == {
        "dog_name": "Luna",
        "feed_count": 3,
    }
    assert normalize_value(DeviceSnapshot) == repr(DeviceSnapshot)
    assert normalize_value(ReprOnly()) == "ReprOnly<snapshot>"
