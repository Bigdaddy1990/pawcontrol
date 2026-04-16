"""Tests for JSON normalization helpers."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pytest

from custom_components.pawcontrol.utils.normalize import normalize_value


@dataclass(slots=True)
class SamplePayload:
    """Simple dataclass payload used for normalization coverage."""

    name: str
    due_date: date
    duration: timedelta


class UnserializableObject:
    """Object without JSON representation."""

    def __repr__(self) -> str:  # noqa: D105
        return "UnserializableObject()"


@dataclass(slots=True)
class OuterPayload:
    """Nested payload to verify recursive dataclass handling."""

    payload: SamplePayload


def test_normalize_value_handles_datetime_date_time_and_timedelta() -> None:
    """Datetime-like values are converted to ISO and seconds representations."""
    value = {
        "dt": datetime(2026, 4, 10, 13, 45, 30),
        "date": date(2026, 4, 10),
        "time": time(13, 45, 30),
        "delta": timedelta(minutes=2, seconds=30),
    }

    assert normalize_value(value) == {
        "dt": "2026-04-10T13:45:30",
        "date": "2026-04-10",
        "time": "13:45:30",
        "delta": 150.0,
    }


def test_normalize_value_normalizes_nested_dataclass_payloads() -> None:
    """Dataclasses serialize recursively through asdict conversion."""
    nested = OuterPayload(
        payload=SamplePayload(
            name="Fido",
            due_date=date(2026, 4, 10),
            duration=timedelta(hours=1),
        )
    )

    assert normalize_value(nested) == {
        "payload": {
            "name": "Fido",
            "due_date": "2026-04-10",
            "duration": 3600.0,
        }
    }


def test_normalize_value_coerces_mapping_keys_and_iterables() -> None:
    """Mappings and iterables produce normalized JSON-safe collections."""

    class IterableBox:
        def __iter__(self):
            yield 1
            yield timedelta(seconds=5)

    source = {
        5: {"a", "b"},
        "iterable": IterableBox(),
    }

    normalized = normalize_value(source)

    assert normalized["5"] in (["a", "b"], ["b", "a"])
    assert normalized["iterable"] == [1, 5.0]


def test_normalize_value_falls_back_to_repr_for_bytes_and_custom_objects() -> None:
    """Values excluded from iterable conversion use repr fallback."""
    assert normalize_value(b"raw") == "b'raw'"
    assert normalize_value(UnserializableObject()) == "UnserializableObject()"


def test_normalize_value_returns_dataclass_type_repr_when_given_class() -> None:
    """Dataclass classes should not be treated as dataclass instances."""
    assert normalize_value(SamplePayload) == repr(SamplePayload)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(None, None, id="none"),
        pytest.param(True, True, id="bool"),
        pytest.param(42, 42, id="int"),
        pytest.param(4.2, 4.2, id="float"),
        pytest.param("pawcontrol", "pawcontrol", id="str"),
    ],
)
def test_normalize_value_keeps_json_primitives_unchanged(
    value: object,
    expected: object,
) -> None:
    """Primitive JSON values should pass through without conversion."""
    assert normalize_value(value) == expected


def test_normalize_value_normalizes_tuples_and_nested_iterables() -> None:
    """Tuple values should be normalized via iterable handling branch."""
    source = (
        timedelta(seconds=1),
        [timedelta(seconds=2), {"nested": timedelta(seconds=3)}],
    )

    assert normalize_value(source) == [1.0, [2.0, {"nested": 3.0}]]


def test_normalize_value_handles_dataclass_with_mapping_field() -> None:
    """Dataclasses containing mappings should normalize keys and nested values."""

    @dataclass(slots=True)
    class MappingPayload:
        values: dict[object, object]

    payload = MappingPayload(values={1: timedelta(seconds=30), "keep": "ok"})

    assert normalize_value(payload) == {"values": {"1": 30.0, "keep": "ok"}}
