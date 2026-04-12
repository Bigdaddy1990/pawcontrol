"""Coverage tests for legacy utility normalization helpers."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from custom_components.pawcontrol.utils._legacy import (
    build_error_context,
    normalise_json_mapping,
    normalise_json_value,
)


@dataclass(slots=True)
class _PetPayload:
    """Dataclass payload used to verify recursive dataclass handling."""

    name: str
    birthday: date


class _WithMapping:
    """Object exposing ``to_mapping`` for normalization."""

    def to_mapping(self) -> dict[str, object]:
        return {
            "updated": datetime(2026, 4, 10, 10, 0, 0),
            "quiet_hours": time(21, 30, 0),
            "window": timedelta(minutes=30),
        }


class _WithDict:
    """Object exposing ``to_dict`` for normalization."""

    def to_dict(self) -> dict[str, object]:
        return {"payload": _PetPayload(name="Nala", birthday=date(2022, 1, 1))}


class _Node:  # noqa: B903
    """Simple cyclic node used to validate recursion guards."""

    def __init__(self) -> None:
        self.self_ref = self


def test_build_error_context_uses_error_message_and_reason_classification() -> None:
    """Error contexts should keep explicit errors and derived classifications."""
    context = build_error_context("auth_error", RuntimeError("token expired"))

    assert context.classification == "auth_error"
    assert context.reason == "auth_error"
    assert context.message == "token expired"


def test_build_error_context_uses_unknown_fallback_without_reason_or_error() -> None:
    """Unknown contexts should still produce a stable fallback message."""
    context = build_error_context(None, None)

    assert context.classification == "unknown"
    assert context.message == "unknown"


def test_normalise_json_value_handles_to_mapping_to_dict_and_cycles() -> None:
    """Legacy normalizer should support adapter methods and cyclic references."""
    mapping_normalized = normalise_json_value(_WithMapping())
    dict_normalized = normalise_json_value(_WithDict())
    cycle_normalized = normalise_json_value(_Node())

    assert mapping_normalized == {
        "updated": "2026-04-10T10:00:00",
        "quiet_hours": "21:30:00",
        "window": "0:30:00",
    }
    assert dict_normalized == {"payload": {"name": "Nala", "birthday": "2022-01-01"}}
    assert cycle_normalized == {"self_ref": None}


def test_normalise_json_mapping_handles_empty_and_key_casting() -> None:
    """Mapping helper should support null input and stringify non-string keys."""
    assert normalise_json_mapping(None) == {}
    assert normalise_json_mapping({1: timedelta(seconds=5), "flag": True}) == {
        "1": "0:00:05",
        "flag": True,
    }
