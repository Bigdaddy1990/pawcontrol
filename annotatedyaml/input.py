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

    if isinstance(obj, Input):
        found.add(obj.name)
        return

    if isinstance(obj, Sequence) and not isinstance(obj, str | bytes | bytearray):
        for value in obj:
            _extract_inputs(value, found)
        return

    if isinstance(obj, Mapping):
        for value in obj.values():
            _extract_inputs(value, found)
        return


def substitute(obj: Any, substitutions: Mapping[str, Any]) -> Any:
    """Replace :class:`Input` placeholders in ``obj`` using ``substitutions``."""

    if isinstance(obj, Input):
        try:
            return substitutions[obj.name]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise UndefinedSubstitution(obj.name) from exc

    if isinstance(obj, Sequence) and not isinstance(obj, str | bytes | bytearray):
        return [substitute(value, substitutions) for value in obj]

    if isinstance(obj, Mapping):
        return {key: substitute(value, substitutions) for key, value in obj.items()}

    return obj
