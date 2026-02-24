"""Unit tests for JSON normalization helpers."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from custom_components.pawcontrol.utils.normalize import normalize_value


@dataclass
class SamplePayload:
    """Simple dataclass payload for normalization tests."""

    name: str
    delay: timedelta


class CustomObject:
    """Object without JSON conversion support."""


def test_normalize_value_handles_json_primitives() -> None:
    """Primitive values should remain unchanged."""
    assert normalize_value(None) is None
    assert normalize_value(True) is True
    assert normalize_value(3) == 3
    assert normalize_value(1.5) == 1.5
    assert normalize_value("pawcontrol") == "pawcontrol"


def test_normalize_value_handles_datetime_types() -> None:
    """Date, time, and datetime values should be returned as ISO strings."""
    assert normalize_value(date(2026, 1, 2)) == "2026-01-02"
    assert normalize_value(time(13, 45, 5)) == "13:45:05"
    assert normalize_value(datetime(2026, 1, 2, 13, 45, 5)) == "2026-01-02T13:45:05"


def test_normalize_value_handles_dataclass_and_mapping_and_iterables() -> None:
    """Structured objects should be recursively normalized."""
    payload = SamplePayload(name="Buddy", delay=timedelta(minutes=15))

    assert normalize_value(payload) == {"name": "Buddy", "delay": 900.0}

    mapping_result = normalize_value({1: datetime(2026, 5, 1, 8, 30), "items": (1, 2)})
    assert mapping_result == {"1": "2026-05-01T08:30:00", "items": [1, 2]}

    set_result = normalize_value({"a", "b"})
    assert isinstance(set_result, list)
    assert set(set_result) == {"a", "b"}

    generator_result = normalize_value(item for item in [1, timedelta(seconds=5)])
    assert generator_result == [1, 5.0]


def test_normalize_value_falls_back_to_repr_for_unknown_values() -> None:
    """Unsupported objects should use their repr for serialization."""
    custom = CustomObject()

    assert normalize_value(custom) == repr(custom)
