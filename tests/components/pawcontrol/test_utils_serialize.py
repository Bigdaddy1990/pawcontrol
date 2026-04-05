"""Tests for JSON serialization helpers in ``utils.serialize``."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import importlib

import pytest

from custom_components.pawcontrol.utils.serialize import (
    _serialize_value,
    serialize_dataclass,
    serialize_datetime,
    serialize_entity_attributes,
    serialize_timedelta,
)


@dataclass
class _NestedSample:
    """Nested sample dataclass for recursive serialization tests."""

    active: bool
    duration: timedelta


@dataclass
class _Sample:
    """Sample dataclass for serialization tests."""

    name: str
    created_at: datetime
    nested: _NestedSample


class _CustomObject:
    """Simple object used to assert fallback string conversion."""

    def __str__(self) -> str:
        return "custom-object"


def test_serialize_datetime_and_timedelta_return_json_safe_values() -> None:
    """Datetime and timedelta helpers should return ISO strings and integer seconds."""
    value = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    assert serialize_datetime(value) == "2026-01-02T03:04:05+00:00"
    assert serialize_timedelta(timedelta(minutes=15, seconds=2)) == 902


def test_serialize_dataclass_serializes_instances_and_rejects_invalid_inputs() -> None:
    """Dataclass helper should serialize instances and reject non-instance values."""
    payload = _Sample(
        name="Buddy",
        created_at=datetime(2026, 5, 1, 8, 30, tzinfo=UTC),
        nested=_NestedSample(active=True, duration=timedelta(hours=1)),
    )

    assert serialize_dataclass(payload) == {
        "name": "Buddy",
        "created_at": datetime(2026, 5, 1, 8, 30, tzinfo=UTC),
        "nested": {"active": True, "duration": timedelta(hours=1)},
    }

    with pytest.raises(TypeError, match="Expected dataclass instance"):
        serialize_dataclass({"name": "not dataclass"})

    with pytest.raises(TypeError, match="Did you mean to instantiate"):
        serialize_dataclass(_Sample)


def test_serialize_entity_attributes_recursively_serializes_supported_types() -> None:
    """Complex mappings should be recursively transformed to JSON-safe values."""
    attrs = {
        "updated_at": datetime(2026, 2, 1, 12, 0, tzinfo=UTC),
        "duration": timedelta(minutes=45),
        "nested": {
            "dog": _Sample(
                name="Luna",
                created_at=datetime(2026, 2, 1, 11, 0, tzinfo=UTC),
                nested=_NestedSample(active=False, duration=timedelta(seconds=30)),
            ),
            "values": [timedelta(seconds=2), _CustomObject(), 10],
        },
        "none_value": None,
    }

    assert serialize_entity_attributes(attrs) == {
        "updated_at": "2026-02-01T12:00:00+00:00",
        "duration": 2700,
        "nested": {
            "dog": {
                "name": "Luna",
                "created_at": "2026-02-01T11:00:00+00:00",
                "nested": {"active": False, "duration": 30},
            },
            "values": [2, "custom-object", 10],
        },
        "none_value": None,
    }


def test_serialize_value_supports_tuple_and_primitive_types() -> None:
    """Private serializer should keep primitives untouched and recurse tuples."""
    assert _serialize_value(("name", 1, True, 2.5)) == ["name", 1, True, 2.5]
    assert _serialize_value("text") == "text"
    assert _serialize_value(7) == 7


def test_module_reload_syncs_parent_utils_re_exports() -> None:
    """Reloading the module should refresh ``custom_components.pawcontrol.utils`` exports."""
    parent = importlib.import_module("custom_components.pawcontrol.utils")

    parent.serialize_datetime = None
    parent.serialize_timedelta = None
    parent.serialize_dataclass = None
    parent.serialize_entity_attributes = None

    module = importlib.import_module("custom_components.pawcontrol.utils.serialize")
    reloaded_module = importlib.reload(module)

    assert parent.serialize_datetime is reloaded_module.serialize_datetime
    assert parent.serialize_timedelta is reloaded_module.serialize_timedelta
    assert parent.serialize_dataclass is reloaded_module.serialize_dataclass
    assert (
        parent.serialize_entity_attributes
        is reloaded_module.serialize_entity_attributes
    )
