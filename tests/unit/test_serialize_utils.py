"""Tests for JSON serialization helpers."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pawcontrol.utils.serialize import (
    serialize_dataclass,
    serialize_entity_attributes,
)


@dataclass
class VaccinationRecord:
    """Sample dataclass for serialization tests."""

    dose: int
    applied_at: datetime


@dataclass
class DogProfile:
    """Nested dataclass used to exercise recursive conversion."""

    name: str
    walk_duration: timedelta
    vaccination: VaccinationRecord


class _CustomAttribute:
    """Custom object with deterministic string conversion."""

    def __str__(self) -> str:
        return "custom-attribute"


def test_serialize_dataclass_rejects_non_dataclass_value() -> None:
    """serialize_dataclass should raise when given non-dataclass values."""
    with pytest.raises(TypeError, match="Expected dataclass instance"):
        serialize_dataclass({"name": "Luna"})


def test_serialize_dataclass_rejects_dataclass_type_object() -> None:
    """serialize_dataclass should reject dataclass classes (not instances)."""
    with pytest.raises(TypeError, match="received a class"):
        serialize_dataclass(DogProfile)


def test_serialize_entity_attributes_serializes_nested_structures() -> None:
    """Complex nested attributes should be converted to JSON-safe values."""
    payload = {
        "updated_at": datetime(2026, 3, 1, 8, 30, tzinfo=UTC),
        "profile": DogProfile(
            name="Luna",
            walk_duration=timedelta(minutes=12, seconds=5),
            vaccination=VaccinationRecord(
                dose=2,
                applied_at=datetime(2026, 2, 20, 9, 0, tzinfo=UTC),
            ),
        ),
        "history": (
            timedelta(minutes=1),
            {"checkpoint": datetime(2026, 3, 1, 8, 25, tzinfo=UTC)},
            _CustomAttribute(),
        ),
        "optional": None,
    }

    result = serialize_entity_attributes(payload)

    assert result == {
        "updated_at": "2026-03-01T08:30:00+00:00",
        "profile": {
            "name": "Luna",
            "walk_duration": 725,
            "vaccination": {
                "dose": 2,
                "applied_at": "2026-02-20T09:00:00+00:00",
            },
        },
        "history": [
            60,
            {"checkpoint": "2026-03-01T08:25:00+00:00"},
            "custom-attribute",
        ],
        "optional": None,
    }
