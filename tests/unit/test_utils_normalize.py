from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from custom_components.pawcontrol.utils.normalize import normalize_value


@dataclass
class _DogStats:
    """Simple dataclass payload used for normalization tests."""

    meals: int
    walk_duration: timedelta


def test_normalize_value_handles_primitives_and_datetime_types() -> None:
    """Primitive scalars and date/time types should normalize directly."""
    assert normalize_value(None) is None
    assert normalize_value(True) is True
    assert normalize_value(4) == 4
    assert normalize_value(3.5) == 3.5
    assert normalize_value("paw") == "paw"

    stamp = datetime(2026, 2, 2, 12, 30, tzinfo=UTC)
    assert normalize_value(stamp) == stamp.isoformat()

    only_date = date(2026, 2, 2)
    only_time = time(12, 30)
    assert normalize_value(only_date) == "2026-02-02"
    assert normalize_value(only_time) == only_time.isoformat()


def test_normalize_value_handles_dataclass_and_mapping_keys() -> None:
    """Dataclasses and mapping keys should normalize recursively to JSON-safe data."""
    payload = {
        1: _DogStats(meals=2, walk_duration=timedelta(minutes=15)),
        "adopted": date(2024, 1, 1),
    }

    normalized = normalize_value(payload)

    assert normalized["1"]["meals"] == 2
    assert normalized["1"]["walk_duration"] == 900.0
    assert normalized["adopted"] == "2024-01-01"


def test_normalize_value_handles_set_and_iterable_values() -> None:
    """Sets and non-string iterables should become normalized lists."""
    normalized_set = normalize_value({timedelta(minutes=1), timedelta(minutes=2)})
    assert sorted(normalized_set) == [60.0, 120.0]

    normalized_tuple = normalize_value(("one", 2, timedelta(seconds=3)))
    assert normalized_tuple == ["one", 2, 3.0]


def test_normalize_value_treats_bytes_as_repr_fallback() -> None:
    """Bytes should not be treated as iterables and should fallback to repr."""
    assert normalize_value(b"woof") == "b'woof'"


def test_normalize_value_skips_dataclass_type_objects() -> None:
    """Dataclass type objects are not instances and should use repr fallback."""

    @dataclass
    class _Config:
        enabled: bool

    assert normalize_value(_Config).startswith("<class")


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
