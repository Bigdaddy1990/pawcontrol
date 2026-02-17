"""Tests for utils.serialize module.

Tests JSON serialization utilities for entity attributes.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pawcontrol.utils.serialize import (
    serialize_dataclass,
    serialize_datetime,
    serialize_entity_attributes,
    serialize_timedelta,
)


def test_serialize_datetime() -> None:
    """Test datetime serialization."""  # noqa: E111
    dt = datetime(2026, 2, 15, 10, 30, 0, tzinfo=UTC)  # noqa: E111
    result = serialize_datetime(dt)  # noqa: E111

    assert isinstance(result, str)  # noqa: E111
    assert "2026-02-15" in result  # noqa: E111
    assert "10:30:00" in result  # noqa: E111


def test_serialize_datetime_with_microseconds() -> None:
    """Test datetime serialization with microseconds."""  # noqa: E111
    dt = datetime(2026, 2, 15, 10, 30, 0, 123456, tzinfo=UTC)  # noqa: E111
    result = serialize_datetime(dt)  # noqa: E111

    assert isinstance(result, str)  # noqa: E111
    assert "123456" in result  # noqa: E111


def test_serialize_timedelta_minutes() -> None:
    """Test timedelta serialization in minutes."""  # noqa: E111
    td = timedelta(minutes=30)  # noqa: E111
    result = serialize_timedelta(td)  # noqa: E111

    assert result == 1800  # noqa: E111


def test_serialize_timedelta_hours() -> None:
    """Test timedelta serialization in hours."""  # noqa: E111
    td = timedelta(hours=2)  # noqa: E111
    result = serialize_timedelta(td)  # noqa: E111

    assert result == 7200  # noqa: E111


def test_serialize_timedelta_complex() -> None:
    """Test timedelta serialization with days, hours, minutes."""  # noqa: E111
    td = timedelta(days=1, hours=2, minutes=30)  # noqa: E111
    result = serialize_timedelta(td)  # noqa: E111

    assert result == 95400  # 86400 + 7200 + 1800  # noqa: E111


def test_serialize_dataclass_simple() -> None:
    """Test simple dataclass serialization."""  # noqa: E111

    @dataclass  # noqa: E111
    class Dog:  # noqa: E111
        name: str
        age: int

    dog = Dog("Buddy", 5)  # noqa: E111
    result = serialize_dataclass(dog)  # noqa: E111

    assert result == {"name": "Buddy", "age": 5}  # noqa: E111


def test_serialize_dataclass_nested() -> None:
    """Test nested dataclass serialization."""  # noqa: E111

    @dataclass  # noqa: E111
    class Location:  # noqa: E111
        latitude: float
        longitude: float

    @dataclass  # noqa: E111
    class Dog:  # noqa: E111
        name: str
        location: Location

    dog = Dog("Buddy", Location(52.5200, 13.4050))  # noqa: E111
    result = serialize_dataclass(dog)  # noqa: E111

    assert result["name"] == "Buddy"  # noqa: E111
    assert result["location"]["latitude"] == 52.5200  # noqa: E111
    assert result["location"]["longitude"] == 13.4050  # noqa: E111


def test_serialize_dataclass_not_dataclass() -> None:
    """Test dataclass serialization with non-dataclass."""  # noqa: E111
    with pytest.raises(TypeError, match="Expected dataclass"):  # noqa: E111
        serialize_dataclass({"name": "Buddy"})


def test_serialize_entity_attributes_mixed() -> None:
    """Test entity attributes with mixed types."""  # noqa: E111
    attrs = {  # noqa: E111
        "last_update": datetime(2026, 2, 15, 10, 30, tzinfo=UTC),
        "duration": timedelta(minutes=30),
        "count": 42,
        "name": "Buddy",
        "active": True,
        "ratio": 3.14,
    }

    result = serialize_entity_attributes(attrs)  # noqa: E111

    assert isinstance(result["last_update"], str)  # noqa: E111
    assert result["duration"] == 1800  # noqa: E111
    assert result["count"] == 42  # noqa: E111
    assert result["name"] == "Buddy"  # noqa: E111
    assert result["active"] is True  # noqa: E111
    assert result["ratio"] == 3.14  # noqa: E111


def test_serialize_entity_attributes_nested_dict() -> None:
    """Test entity attributes with nested dictionary."""  # noqa: E111
    attrs = {  # noqa: E111
        "dog": {
            "name": "Buddy",
            "last_seen": datetime(2026, 2, 15, 10, 30, tzinfo=UTC),
        },
    }

    result = serialize_entity_attributes(attrs)  # noqa: E111

    assert result["dog"]["name"] == "Buddy"  # noqa: E111
    assert isinstance(result["dog"]["last_seen"], str)  # noqa: E111


def test_serialize_entity_attributes_list() -> None:
    """Test entity attributes with list of values."""  # noqa: E111
    attrs = {  # noqa: E111
        "timestamps": [
            datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
            datetime(2026, 2, 15, 11, 0, tzinfo=UTC),
        ],
        "durations": [
            timedelta(minutes=10),
            timedelta(minutes=20),
        ],
    }

    result = serialize_entity_attributes(attrs)  # noqa: E111

    assert len(result["timestamps"]) == 2  # noqa: E111
    assert all(isinstance(ts, str) for ts in result["timestamps"])  # noqa: E111
    assert result["durations"] == [600, 1200]  # noqa: E111


def test_serialize_entity_attributes_with_none() -> None:
    """Test entity attributes with None values."""  # noqa: E111
    attrs = {  # noqa: E111
        "last_update": None,
        "duration": None,
        "name": "Buddy",
    }

    result = serialize_entity_attributes(attrs)  # noqa: E111

    assert result["last_update"] is None  # noqa: E111
    assert result["duration"] is None  # noqa: E111
    assert result["name"] == "Buddy"  # noqa: E111


def test_serialize_entity_attributes_with_dataclass() -> None:
    """Test entity attributes with dataclass."""  # noqa: E111

    @dataclass  # noqa: E111
    class DogStats:  # noqa: E111
        walks: int
        meals: int

    attrs = {  # noqa: E111
        "stats": DogStats(walks=5, meals=3),
    }

    result = serialize_entity_attributes(attrs)  # noqa: E111

    assert result["stats"]["walks"] == 5  # noqa: E111
    assert result["stats"]["meals"] == 3  # noqa: E111


def test_serialize_entity_attributes_empty() -> None:
    """Test serialization of empty attributes."""  # noqa: E111
    result = serialize_entity_attributes({})  # noqa: E111
    assert result == {}  # noqa: E111


def test_serialize_entity_attributes_complex_nested() -> None:
    """Test complex nested structure serialization."""  # noqa: E111

    @dataclass  # noqa: E111
    class Session:  # noqa: E111
        start: datetime
        duration: timedelta

    attrs = {  # noqa: E111
        "current": {
            "session": Session(
                start=datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
                duration=timedelta(minutes=30),
            ),
            "active": True,
        },
        "history": [
            {
                "timestamp": datetime(2026, 2, 14, 10, 0, tzinfo=UTC),
                "duration": timedelta(minutes=20),
            },
        ],
    }

    result = serialize_entity_attributes(attrs)  # noqa: E111

    assert isinstance(result["current"]["session"]["start"], str)  # noqa: E111
    assert result["current"]["session"]["duration"] == 1800  # noqa: E111
    assert result["current"]["active"] is True  # noqa: E111
    assert isinstance(result["history"][0]["timestamp"], str)  # noqa: E111
    assert result["history"][0]["duration"] == 1200  # noqa: E111


def test_serialize_entity_attributes_preserves_order() -> None:
    """Test that serialization preserves dictionary order."""  # noqa: E111
    attrs = {  # noqa: E111
        "z_last": "last",
        "a_first": "first",
        "m_middle": "middle",
    }

    result = serialize_entity_attributes(attrs)  # noqa: E111

    # Python 3.7+ dicts maintain insertion order  # noqa: E114
    keys = list(result.keys())  # noqa: E111
    assert keys == ["z_last", "a_first", "m_middle"]  # noqa: E111


def test_serialize_entity_attributes_with_tuple() -> None:
    """Test serialization of tuple values."""  # noqa: E111
    attrs = {  # noqa: E111
        "coordinates": (52.5200, 13.4050),
        "nested": (
            datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
            timedelta(minutes=30),
        ),
    }

    result = serialize_entity_attributes(attrs)  # noqa: E111

    assert result["coordinates"] == [52.5200, 13.4050]  # noqa: E111
    assert isinstance(result["nested"][0], str)  # noqa: E111
    assert result["nested"][1] == 1800  # noqa: E111


def test_serialize_entity_attributes_fallback_str() -> None:
    """Test that unsupported types fallback to string."""  # noqa: E111

    class CustomObject:  # noqa: E111
        def __str__(self) -> str:
            return "custom_repr"  # noqa: E111

    attrs = {  # noqa: E111
        "custom": CustomObject(),
    }

    result = serialize_entity_attributes(attrs)  # noqa: E111

    assert result["custom"] == "custom_repr"  # noqa: E111
