"""Tests for utils.serialize module.

Tests JSON serialization utilities for entity attributes.
"""


from dataclasses import dataclass
from datetime import datetime, timedelta, UTC

import pytest

from custom_components.pawcontrol.utils.serialize import (
    serialize_dataclass,
    serialize_datetime,
    serialize_entity_attributes,
    serialize_timedelta,
)


def test_serialize_datetime():
    """Test datetime serialization."""
    dt = datetime(2026, 2, 15, 10, 30, 0, tzinfo=UTC)
    result = serialize_datetime(dt)

    assert isinstance(result, str)
    assert "2026-02-15" in result
    assert "10:30:00" in result


def test_serialize_datetime_with_microseconds():
    """Test datetime serialization with microseconds."""
    dt = datetime(2026, 2, 15, 10, 30, 0, 123456, tzinfo=UTC)
    result = serialize_datetime(dt)

    assert isinstance(result, str)
    assert "123456" in result


def test_serialize_timedelta_minutes():
    """Test timedelta serialization in minutes."""
    td = timedelta(minutes=30)
    result = serialize_timedelta(td)

    assert result == 1800


def test_serialize_timedelta_hours():
    """Test timedelta serialization in hours."""
    td = timedelta(hours=2)
    result = serialize_timedelta(td)

    assert result == 7200


def test_serialize_timedelta_complex():
    """Test timedelta serialization with days, hours, minutes."""
    td = timedelta(days=1, hours=2, minutes=30)
    result = serialize_timedelta(td)

    assert result == 95400  # 86400 + 7200 + 1800


def test_serialize_dataclass_simple():
    """Test simple dataclass serialization."""

    @dataclass
    class Dog:
        name: str
        age: int

    dog = Dog("Buddy", 5)
    result = serialize_dataclass(dog)

    assert result == {"name": "Buddy", "age": 5}


def test_serialize_dataclass_nested():
    """Test nested dataclass serialization."""

    @dataclass
    class Location:
        latitude: float
        longitude: float

    @dataclass
    class Dog:
        name: str
        location: Location

    dog = Dog("Buddy", Location(52.5200, 13.4050))
    result = serialize_dataclass(dog)

    assert result["name"] == "Buddy"
    assert result["location"]["latitude"] == 52.5200
    assert result["location"]["longitude"] == 13.4050


def test_serialize_dataclass_not_dataclass():
    """Test dataclass serialization with non-dataclass."""
    with pytest.raises(TypeError, match="Expected dataclass"):
        serialize_dataclass({"name": "Buddy"})


def test_serialize_entity_attributes_mixed():
    """Test entity attributes with mixed types."""
    attrs = {
        "last_update": datetime(2026, 2, 15, 10, 30, tzinfo=UTC),
        "duration": timedelta(minutes=30),
        "count": 42,
        "name": "Buddy",
        "active": True,
        "ratio": 3.14,
    }

    result = serialize_entity_attributes(attrs)

    assert isinstance(result["last_update"], str)
    assert result["duration"] == 1800
    assert result["count"] == 42
    assert result["name"] == "Buddy"
    assert result["active"] is True
    assert result["ratio"] == 3.14


def test_serialize_entity_attributes_nested_dict():
    """Test entity attributes with nested dictionary."""
    attrs = {
        "dog": {
            "name": "Buddy",
            "last_seen": datetime(2026, 2, 15, 10, 30, tzinfo=UTC),
        },
    }

    result = serialize_entity_attributes(attrs)

    assert result["dog"]["name"] == "Buddy"
    assert isinstance(result["dog"]["last_seen"], str)


def test_serialize_entity_attributes_list():
    """Test entity attributes with list of values."""
    attrs = {
        "timestamps": [
            datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
            datetime(2026, 2, 15, 11, 0, tzinfo=UTC),
        ],
        "durations": [
            timedelta(minutes=10),
            timedelta(minutes=20),
        ],
    }

    result = serialize_entity_attributes(attrs)

    assert len(result["timestamps"]) == 2
    assert all(isinstance(ts, str) for ts in result["timestamps"])
    assert result["durations"] == [600, 1200]


def test_serialize_entity_attributes_with_none():
    """Test entity attributes with None values."""
    attrs = {
        "last_update": None,
        "duration": None,
        "name": "Buddy",
    }

    result = serialize_entity_attributes(attrs)

    assert result["last_update"] is None
    assert result["duration"] is None
    assert result["name"] == "Buddy"


def test_serialize_entity_attributes_with_dataclass():
    """Test entity attributes with dataclass."""

    @dataclass
    class DogStats:
        walks: int
        meals: int

    attrs = {
        "stats": DogStats(walks=5, meals=3),
    }

    result = serialize_entity_attributes(attrs)

    assert result["stats"]["walks"] == 5
    assert result["stats"]["meals"] == 3


def test_serialize_entity_attributes_empty():
    """Test serialization of empty attributes."""
    result = serialize_entity_attributes({})
    assert result == {}


def test_serialize_entity_attributes_complex_nested():
    """Test complex nested structure serialization."""

    @dataclass
    class Session:
        start: datetime
        duration: timedelta

    attrs = {
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

    result = serialize_entity_attributes(attrs)

    assert isinstance(result["current"]["session"]["start"], str)
    assert result["current"]["session"]["duration"] == 1800
    assert result["current"]["active"] is True
    assert isinstance(result["history"][0]["timestamp"], str)
    assert result["history"][0]["duration"] == 1200


def test_serialize_entity_attributes_preserves_order():
    """Test that serialization preserves dictionary order."""
    attrs = {
        "z_last": "last",
        "a_first": "first",
        "m_middle": "middle",
    }

    result = serialize_entity_attributes(attrs)

    # Python 3.7+ dicts maintain insertion order
    keys = list(result.keys())
    assert keys == ["z_last", "a_first", "m_middle"]


def test_serialize_entity_attributes_with_tuple():
    """Test serialization of tuple values."""
    attrs = {
        "coordinates": (52.5200, 13.4050),
        "nested": (
            datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
            timedelta(minutes=30),
        ),
    }

    result = serialize_entity_attributes(attrs)

    assert result["coordinates"] == [52.5200, 13.4050]
    assert isinstance(result["nested"][0], str)
    assert result["nested"][1] == 1800


def test_serialize_entity_attributes_fallback_str():
    """Test that unsupported types fallback to string."""

    class CustomObject:
        def __str__(self):
            return "custom_repr"

    attrs = {
        "custom": CustomObject(),
    }

    result = serialize_entity_attributes(attrs)

    assert result["custom"] == "custom_repr"
