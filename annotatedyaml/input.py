"""Utility helpers for the ``annotatedyaml`` test stub."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from . import Input


class UndefinedSubstitution(Exception):
    """Error raised when a requested substitution is missing."""

    def __init__(self, input_name: str) -> None:
        super().__init__(f"No substitution found for input {input_name}")
        self.input = input_name


def extract_inputs(obj: Any) -> set[str]:
    """Collect all :class:`Input` placeholders contained in ``obj``."""

    found: set[str] = set()
    _extract_inputs(obj, found)
    return found


def _extract_inputs(obj: Any, found: set[str]) -> None:
    """Recursive helper for :func:`extract_inputs`."""

    match obj:
        case Input() as input_obj:
            found.add(input_obj.name)
        case str() | bytes() | bytearray():
            pass
        case Sequence() as seq if not isinstance(seq, str | bytes | bytearray):
            for value in seq:
                _extract_inputs(value, found)
        case Mapping() as mapping:
            for value in mapping.values():
                _extract_inputs(value, found)


def substitute(obj: Any, substitutions: Mapping[str, Any]) -> Any:
    """Replace :class:`Input` placeholders in ``obj`` using ``substitutions``."""

    match obj:
        case Input() as input_obj:
            try:
                return substitutions[input_obj.name]
            except KeyError as exc:  # pragma: no cover - defensive guard
                raise UndefinedSubstitution(input_obj.name) from exc
        case str() | bytes() | bytearray():
            return obj
        case Sequence() as seq if not isinstance(seq, str | bytes | bytearray):
            return [substitute(value, substitutions) for value in seq]
        case Mapping() as mapping:
            return {
                key: substitute(value, substitutions) for key, value in mapping.items()
            }
        case _:
            return obj
